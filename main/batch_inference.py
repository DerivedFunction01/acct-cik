import warnings
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import multiprocessing as mp
import os
from threading import Lock
import time

try:
    import unsloth
    from unsloth import FastLanguageModel

    USE_UNSLOTH = True
    print("✅ Unsloth found. Using Unsloth for model loading.")
except ImportError:
    USE_UNSLOTH = False
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    print("⚠️ Unsloth not found. Falling back to standard Hugging Face transformers.")

import torch

app = FastAPI(
    title="Batch Summarization Server",
    description="Batched inference for efficient summarization",
)

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURATION ---
MODEL_PATH = "DerivedFunction/Qwen3-1.7B-finance"
MAX_SEQ_LENGTH = 8192
BATCH_SIZE = 4  # Number of texts to process in parallel per forward pass
MAX_INPUT_LENGTH = 6144  # Leave room for generation (8192 - 2048)

GENERATION_PARAMS = {
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "repetition_penalty": 1.15,
    "max_new_tokens": 2048,
    "length_penalty": 1.0,
}

SYSTEM_PROMPT = """You are a financial analyst extracting only clear mentions of derivative financial instruments (swaps, forwards, futures, options, etc.) from short text fragments.
RULES:
- Only include information if the text explicitly mentions derivative instruments (e.g., interest rate swaps, FX forwards, futures, options used for hedging/risk management).
- Never infer or invent usage. If unclear or absent, state that no derivative usage is mentioned.
- Distinguish carefully: equity compensation "options" or vague "options" are NOT derivatives unless explicitly used for hedging financial risks.
- Use the provided reference year when dating positions or events.
- If the text refers to data that is not shown, note that the text is incomplete.
- Even in long unrelated text, search for any hidden mention of derivatives.
CRITICAL:
- Output exactly one line of valid JSON and nothing else — no explanations, no markdown, no text before or after the JSON. The JSON must contain only one key: "summary" (a string of 1–3 concise sentences).
- Your response must end immediately after the closing brace } — do not add anything, not even a newline.
Examples:
<input>
Reference year: 2003
... From time to time, we may use forward contracts to hedge against this risk. ... As of December 2003, we have an interest rate swap with a notional value of $20M.
</input>
{"summary": "As of December 2003, the company maintains an interest rate swap with a $20 million notional amount. It occasionally uses forward contracts to hedge foreign currency risk."}

<input>
Reference year: 2021
Accounts receivable increased. Our cost of goods sold primarily relates to operational expenses.
</input>
{"summary": "The provided text contains no information about the use of derivatives."}

<input>
Reference year: 2022
The following table shows the notional values of our derivative instruments as of 2022 and 2021:
</input>
{"summary": "The text references a table of derivative notional amounts for 2022 and 2021, but the table itself is not provided."}

<input>
Reference year: 2000
We are not currently impacted by this update, as we do not have derivative instruments.
</input>
{"summary": "The company has no derivative instruments."}
"""

# --- BUSY STATE TRACKING ---
busy_lock = Lock()
is_busy = False


# --- Pydantic Models ---
class SummarizationRequest(BaseModel):
    texts: List[str]
    params: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None


class SummarizationResponse(BaseModel):
    summaries: List[str]
    success: bool
    error: Optional[str] = None
    processing_time: float
    batch_size: int
    num_batches: int


class InfoResponse(BaseModel):
    device: str
    max_seq_length: int
    batch_size: int
    gpu_available: bool
    gpu_name: Optional[str] = None
    total_ram_gb: Optional[float] = None
    load_in_4bit: Optional[bool] = None
    cpu_cores: Optional[int] = None


class StatusResponse(BaseModel):
    status: str  # "idle" or "busy"
    message: str


# --- Dynamic Hardware Detection ---
def get_hardware_config():
    """Detects GPU and sets configuration for model loading and batching."""
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"✅ GPU detected with {vram_gb:.2f} GB VRAM.")
        load_in_4bit = vram_gb < 20
        return torch.device("cuda"), True, load_in_4bit
    else:
        print("⚠️ No GPU detected. Running on CPU.")
        return torch.device("cpu"), False, False


device, is_gpu, load_in_4bit = get_hardware_config()

# --- Load model ---
print(f"Loading model from {MODEL_PATH}...")
if USE_UNSLOTH:
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_PATH,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=load_in_4bit,
    )
    FastLanguageModel.for_inference(model)

    print("✅ Unsloth model loaded and set to inference mode.")
    print(
        f"⚙️  Padding side: {tokenizer.padding_side}, Pad token: {tokenizer.pad_token}"
    )
else:
    quantization_config = None
    if load_in_4bit:
        quantization_config = BitsAndBytesConfig(load_in_4bit=True)

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=quantization_config,
        device_map="auto",
    )
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

    print("✅ Standard transformers model loaded.")
    print(
        f"⚙️  Padding side: {tokenizer.padding_side}, Pad token: {tokenizer.pad_token}"
    )

print(f"USE_UNSLOTH = {USE_UNSLOTH}, 4-bit = {load_in_4bit}")

# ──────────────────────────────────────────────────────────────
# CONFIGURABLE: How aggressive do you want to pack the GPU?
# ──────────────────────────────────────────────────────────────
# BASE = MAX_INPUT_LENGTH (e.g. 6144)
# Multiplier → total prompt tokens allowed per forward pass
TOKEN_BUDGET_MULTIPLIER = 4  # ← EDIT THIS ONE NUMBER
# Examples:
#   8.0  → safe, works on 16GB GPUs
#  12.0  → excellent for RTX 4090 / A40 (24GB)
#  16.0  → aggressive, great for A100 80GB
#  20.0+ → only with very small models or 4-bit + flash-attn-v2
# ──────────────────────────────────────────────────────────────

def batch_summarize(
    texts: List[str],
    user_params: Optional[dict] = None,
    system_prompt: Optional[str] = None,
) -> tuple[List[str], str, int]:
    """
    High-throughput batched inference with dynamic packing.
    Maximizes GPU utilization regardless of input length distribution.
    """
    global is_busy, TOKEN_BUDGET_MULTIPLIER
    if not texts:
        return [], "No texts provided", 0

    try:
        with busy_lock:
            is_busy = True

        sys_prompt = system_prompt or SYSTEM_PROMPT
        gen_params = GENERATION_PARAMS.copy()
        if user_params:
            gen_params.update(user_params)
        MAX_TOKENS_PER_BATCH = int(MAX_INPUT_LENGTH * TOKEN_BUDGET_MULTIPLIER)

        print(
            f"\nStarting dynamic batching — token budget per batch: {MAX_TOKENS_PER_BATCH:,} "
            f"({TOKEN_BUDGET_MULTIPLIER}× max input length)"
        )

        # Step 1: Build full prompts and measure exact token length
        items = []
        for idx, text in enumerate(texts):
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text},
            ]
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            input_ids = tokenizer.encode(prompt, add_special_tokens=False)
            items.append(
                {
                    "idx": idx,
                    "text": text,
                    "prompt": prompt,
                    "length": len(input_ids),
                }
            )

        # Step 2: Sort longest → shortest (greedy bin packing)
        items.sort(key=lambda x: x["length"], reverse=True)

        # Step 3: Pack into batches (first-fit decreasing)
        batches = []
        for item in items:
            placed = False
            for batch in batches:
                if (
                    sum(x["length"] for x in batch) + item["length"]
                    <= MAX_TOKENS_PER_BATCH
                ):
                    batch.append(item)
                    placed = True
                    break
            if not placed:
                batches.append([item])

        num_batches = len(batches)
        all_summaries = [""] * len(texts)

        print(f"Packed {len(texts)} texts → {num_batches} batch(es):")
        for i, b in enumerate(batches):
            total_tokens = sum(x["length"] for x in b)
            print(f"  Batch {i+1}: {len(b)} items, {total_tokens:,} prompt tokens")

        # ──────────────────────────────────────────────────────────────
        # Step 4: Process each packed batch
        # ──────────────────────────────────────────────────────────────
        for batch_idx, batch in enumerate(batches):
            batch_prompts = [item["prompt"] for item in batch]
            batch_indices = [item["idx"] for item in batch]

            print(
                f"  → Generating batch {batch_idx + 1}/{num_batches} ({len(batch_prompts)} texts)... ",
                end="",
                flush=True,
            )

            inputs = tokenizer(
                batch_prompts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=MAX_INPUT_LENGTH,
                return_attention_mask=True,
                padding_side="left"
            ).to(device)

            input_length = inputs["input_ids"].shape[1]

            with torch.no_grad():
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    outputs = model.generate(
                        **inputs,
                        pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                        max_new_tokens=gen_params["max_new_tokens"],
                        temperature=gen_params["temperature"],
                        top_p=gen_params["top_p"],
                        top_k=gen_params["top_k"],
                        repetition_penalty=gen_params["repetition_penalty"],
                        do_sample=True,
                    )

            generated_texts = tokenizer.batch_decode(
                outputs[:, input_length:],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )

            for orig_idx, summary in zip(batch_indices, generated_texts):
                all_summaries[orig_idx] = summary.strip()

            # Optional: log to file
            with open("server.log", "a", encoding="utf-8") as f:
                for text, summary in zip(batch_prompts, generated_texts):
                    f.write("=== BATCH ITEM ===\nORIGINAL:\n")
                    f.write(text + "\n\nSUMMARY:\n" + summary.strip() + "\n\n")

            print("Done")

        print(f"\nAll {len(all_summaries)} summaries generated successfully.")
        return all_summaries, "", num_batches

    except torch.cuda.OutOfMemoryError:
        error_msg = f"OOM with multiplier {TOKEN_BUDGET_MULTIPLIER}. Reduce TOKEN_BUDGET_MULTIPLIER and retry."
        print(f"Error: {error_msg}")
        return [], error_msg, 0
    except Exception as e:
        import traceback

        traceback.print_exc()
        return [], f"Inference failed: {str(e)}", 0
    finally:
        with busy_lock:
            is_busy = False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()    


@app.post("/batch-summarize", response_model=SummarizationResponse)
async def batch_summarize_endpoint(request: SummarizationRequest):
    """
    Endpoint for batch summarization.

    Accepts an array of texts and returns an array of summaries.
    All texts are processed in parallel batches for efficiency.
    """
    try:
        if not request.texts:
            raise HTTPException(status_code=400, detail="Missing 'texts' array")

        start_time = time.time()

        summaries, error, num_batches = batch_summarize(
            request.texts,
            user_params=request.params,
            system_prompt=request.system_prompt,
        )

        processing_time = time.time() - start_time

        if error:
            raise HTTPException(status_code=500, detail=error)

        return SummarizationResponse(
            summaries=summaries,
            success=True,
            processing_time=processing_time,
            batch_size=len(request.texts),
            num_batches=num_batches,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR in batch summarize endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status", response_model=StatusResponse)
async def status_endpoint():
    """
    Check if this process is busy or idle.
    """
    with busy_lock:
        if is_busy:
            return StatusResponse(
                status="busy",
                message="This process is currently generating. Request queued or try another server.",
            )
        else:
            return StatusResponse(
                status="idle",
                message="This process is ready to accept requests.",
            )


@app.get("/info", response_model=InfoResponse)
async def info_endpoint():
    """Endpoint for server info and hardware details."""
    info_dict = {
        "device": str(device),
        "max_seq_length": MAX_SEQ_LENGTH,
        "batch_size": BATCH_SIZE,
        "gpu_available": is_gpu,
    }

    if is_gpu:
        prop = torch.cuda.get_device_properties(0)
        info_dict.update(
            {
                "gpu_name": torch.cuda.get_device_name(0),
                "total_ram_gb": round(prop.total_memory / (1024**3), 2),
                "load_in_4bit": load_in_4bit,
            }
        )
    else:
        info_dict["cpu_cores"] = mp.cpu_count()

    return InfoResponse(**info_dict)


@app.get("/")
async def root():
    """Root endpoint with API documentation link."""
    return {
        "message": "Batch Summarization Server",
        "docs": "/docs",
        "endpoints": {
            "batch-summarize": "POST /batch-summarize - Batch summarization of text chunks",
            "status": "GET /status - Check if process is busy or idle",
            "info": "GET /info - Server info and hardware details",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5001)
