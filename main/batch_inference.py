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

# Default system prompt for summarization
SYSTEM_PROMPT = """Here is a clean, simplified system prompt suitable for a small model, focused only on producing JSON output with a `summary` key for the examples section:

```plaintext
You are a financial analyst tasked with extracting information about a company's use of derivatives from short text fragments.

Your output must always be valid JSON with only one key: "summary" (a string containing 1-3 clear sentences).

Instructions:
- Only discuss derivatives if the text clearly mentions specific instruments (e.g., swaps, forwards, options, futures).
- Do not invent information — if the text is incomplete or unclear, keep the summary conservative.
- Use the provided reference year when relevant.
- If the text has no clear reference to derivatives or hedging with financial instruments, state briefly that no derivative usage is mentioned.

<example>
<input>
Reference year: 2003

We are exposed to various currency exchange rate risks, especially to our operations in China, Germany, and Russia. ... From time to time, we may use forward contracts to hedge against this risk. We settled our forward contracts in 2002, resulting in a loss of $5.5 million. ... As of December 2003, we have an interest rate swap with a notional value of $20M.
</input>
<response>
```json
{
  "summary": "As of December 2003, the company has an active interest rate swap with a notional amount of $20 million. It may periodically use forward contracts to hedge foreign currency risk related to operations in China, Germany, and Russia. All previous forward contracts were settled in 2002 with a realized loss of $5.5 million."
}
```
</response>
</example>

<example>
<input>
Reference year: 2001

Accounts receivable increased from $1.5M to $2.5M in 2001. Our cost of goods sold primarily relates to operational expenses.
</input>
<response>
```json
{
  "summary": "The provided text contains no information about the use of derivatives."
}
```
</response>
</example>

<example>
<input>
Reference year: 2022

The company does not currently enter into derivative financial instruments for trading or speculative purposes and has no material exposure requiring hedging.
</input>
<response>
```json
{
  "summary": "The company states that it does not use derivative financial instruments for trading or speculative purposes and has no material hedging activity."
}
```
</response>
</example>
```
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


def batch_summarize(
    texts: List[str],
    user_params: Optional[dict] = None,
    system_prompt: Optional[str] = None,
) -> tuple[List[str], str, int]:
    """
    Perform true batched inference on multiple texts with proper handling.

    Key fixes:
    - Validates input lengths before processing
    - Uses attention masks properly
    - Only decodes new tokens (not input)
    - Handles variable-length inputs correctly

    Args:
        texts: List of text chunks to summarize
        user_params: Optional generation parameters override
        system_prompt: Optional system prompt override

    Returns:
        Tuple of (summaries list, error message or empty string, num_batches)
    """
    global is_busy

    if not texts or len(texts) == 0:
        return [], "No texts provided", 0

    try:
        with busy_lock:
            is_busy = True

        # Use provided or default system prompt
        sys_prompt = system_prompt or SYSTEM_PROMPT

        # Merge generation parameters
        gen_params = GENERATION_PARAMS.copy()
        if user_params:
            gen_params.update(user_params)

        # --- Tier-based batching to minimize padding ---
        # 1. Store original index and length for each text
        indexed_texts = [
            {"original_index": i, "text": text, "length": len(text)}
            for i, text in enumerate(texts)
        ]

        # 2. Define length-based tiers
        tier_boundaries = [256, 512, 1024, 4096, 8192, MAX_INPUT_LENGTH]
        tiers = [[] for _ in range(len(tier_boundaries))]

        for item in indexed_texts:
            length = item["length"]
            for i, boundary in enumerate(tier_boundaries):
                if length <= boundary:
                    tiers[i].append(item)
                    break

        # 3. Create batches within each tier
        all_batches = []
        for tier in tiers:
            if not tier:
                continue
            # Sort within the tier for extra optimization
            tier.sort(key=lambda x: x["length"])
            for i in range(0, len(tier), BATCH_SIZE):
                all_batches.append(tier[i : i + BATCH_SIZE])

        num_batches = len(all_batches)
        all_summaries = [""] * len(texts)  # Pre-allocate list for results

        print(
            f"\n📦 Starting batch summarization: {len(texts)} texts in {num_batches} batches (grouped by length tiers)"
        )

        for batch_idx, batch in enumerate(all_batches):
            # Extract texts and original indices for this batch
            batch_texts = [item["text"] for item in batch]
            batch_indices = [item["original_index"] for item in batch]
            actual_batch_size = len(batch_texts)
            avg_len = sum(item["length"] for item in batch) // actual_batch_size

            print(
                f"  Batch {batch_idx + 1}/{num_batches} ({actual_batch_size} texts, avg len: {avg_len})... ",
                end="",
                flush=True,
            )

            # --- Build messages for all texts in this batch ---
            batch_messages = []
            for text in batch_texts:
                messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": text},
                ]
                batch_messages.append(messages)

            # --- Format all prompts using chat template ---
            formatted_prompts = []
            for messages in batch_messages:
                try:
                    formatted_prompt = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True,
                    )
                    formatted_prompts.append(formatted_prompt)
                except Exception as e:
                    print(f"❌ Error formatting prompt: {e}")
                    return [], f"Prompt formatting error: {e}", batch_idx

            # --- Tokenize each prompt individually first to check lengths ---
            individual_lengths = []
            for prompt in formatted_prompts:
                tokens = tokenizer.encode(prompt, add_special_tokens=False)
                individual_lengths.append(len(tokens))

            max_length_in_batch = max(individual_lengths)

            # Check if any input is too long
            if max_length_in_batch > MAX_INPUT_LENGTH:
                print(
                    f"\n⚠️  Warning: Input too long ({max_length_in_batch} tokens > {MAX_INPUT_LENGTH} max)"
                )
                print(f"     Truncating inputs in this batch...")

            # --- Tokenize the entire batch at once with proper settings ---
            inputs = tokenizer(
                formatted_prompts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=MAX_INPUT_LENGTH,
                return_attention_mask=True,
                padding_side="left",  # ← THIS IS THE CRITICAL LINE
            )

            inputs = inputs.to(device)
            input_length = inputs["input_ids"].shape[1]

            # --- Generate summaries for entire batch in parallel ---
            # Suppress the Unsloth resize warning (it's cosmetic and doesn't affect output)
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=".*An output with one or more elements was resized.*",
                )

                with torch.no_grad():
                    outputs = model.generate(
                        input_ids=inputs["input_ids"],
                        attention_mask=inputs["attention_mask"],
                        pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                        temperature=gen_params.get("temperature", 0.7),
                        top_p=gen_params.get("top_p", 0.9),
                        top_k=gen_params.get("top_k", 20),
                        repetition_penalty=gen_params.get("repetition_penalty", 1.1),
                        length_penalty=gen_params.get("length_penalty", 1.0),
                        max_new_tokens=gen_params.get("max_new_tokens", 512),
                        # do_sample=True,  # Enable sampling for temperature/top_p
                    )

            # --- Decode only the generated tokens (skip input tokens) ---
            batch_summaries = tokenizer.batch_decode(
                outputs[:, input_length:],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )

            # Place summaries back in the correct positions using original indices
            for original_idx, summary in zip(batch_indices, batch_summaries):
                all_summaries[original_idx] = summary

            print(f"✅ ({actual_batch_size} texts processed)")
            # Write it to a file
            # Write original + summary pairs to log
            with open("server.log", "a", encoding="utf-8") as f:
                for original, summary in zip(batch_texts, batch_summaries):
                    f.write("=== ITEM START ===\n")
                    f.write("ORIGINAL:\n")
                    f.write(original.strip() + "\n\n")
                    f.write("SUMMARY:\n")
                    f.write(summary.strip() + "\n")
                    f.write("=== ITEM END ===\n\n")

        print(
            f"✅ Batch summarization complete: {len(all_summaries)} summaries generated\n"
        )
        return all_summaries, "", num_batches

    except torch.cuda.OutOfMemoryError:
        print(f"❌ GPU Out of Memory error")
        return [], "GPU Out of Memory - try reducing batch size or input length", 0
    except Exception as e:
        print(f"❌ Summarization error: {e}")
        import traceback

        traceback.print_exc()
        return [], f"Summarization failed: {str(e)}", 0

    finally:
        with busy_lock:
            is_busy = False
        # Clear CUDA cache after each request
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
