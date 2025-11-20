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
MAX_MODEL_LENGTH = MAX_SEQ_LENGTH * 4

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
TOKEN_BUDGET_MULTIPLIER = 8  # ← EDIT THIS ONE NUMBER
# Examples:
#   8.0  → safe, works on 16GB GPUs
#  12.0  → excellent for RTX 4090 / A40 (24GB)
#  16.0  → aggressive, great for A100 80GB
#  20.0+ → only with very small models or 4-bit + flash-attn-v2
# ──────────────────────────────────────────────────────────────
TIER_MULTIPLIER = 1.3  # ← EDIT THIS
# ─── CONFIG: Single knob to control padding vs packing trade-off ───
# 1.0 = very strict (almost no padding, lower GPU utilization)
# 1.3 = excellent balance (recommended for 24GB+ GPUs)
# 1.6 = aggressive (max throughput, slight padding)


def is_valid_output(output: str) -> tuple[bool, str]:
    """
    Validate that output contains:
    1. <think>...</think> tags with substantial content
    2. Valid JSON with 'summary' key

    Returns: (is_valid, error_message)
    """
    output = output.strip()

    # Check for think tags
    if "<think>" not in output or "</think>" not in output:
        return False, "Missing <think>...</think> tags"

    think_start = output.find("<think>")
    think_end = output.find("</think>")

    if think_start >= think_end:
        return False, "Invalid <think> tag structure"

    think_content = output[think_start + 7 : think_end].strip()
    if len(think_content) < 50:  # Minimum thought content
        return False, "Insufficient thinking content (too short)"

    # Extract JSON after </think>
    json_part = output[think_end + 8 :].strip()

    if not json_part:
        return False, "No JSON output after </think>"

    # Try to parse JSON
    try:
        parsed = json.loads(json_part)
        if "summary" not in parsed:
            return False, "JSON missing 'summary' key"
        if not isinstance(parsed["summary"], str) or len(parsed["summary"]) < 10:
            return False, "Summary is empty or too short"
        return True, ""
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {str(e)}"


from typing import List, Optional, Tuple, Dict, Any
import torch
import traceback
from threading import Lock

# Assuming these globals are defined elsewhere
# busy_lock: Lock
# is_busy: bool
# tokenizer, model, device
# SYSTEM_PROMPT, GENERATION_PARAMS, MAX_INPUT_LENGTH
# TIER_MULTIPLIER


def batch_summarize(
    texts: List[str],
    user_params: Optional[Dict[str, Any]] = None,
    system_prompt: Optional[str] = None,
    max_retries: int = 2,
) -> Tuple[List[str], str, int]:
    """
    Perform tiered batch summarization with validation and automatic retries.

    Returns:
        Tuple containing:
        - List of summaries (in original order)
        - Error message (empty if successful)
        - Number of batches processed
    """
    global is_busy, TIER_MULTIPLIER

    if not texts:
        return [], "No texts provided", 0

    try:
        with busy_lock:
            is_busy = True

        sys_prompt = system_prompt or SYSTEM_PROMPT
        gen_params = GENERATION_PARAMS.copy()
        if user_params:
            gen_params.update(user_params)

        # Step 1: Prepare and measure prompts
        items = _prepare_items(texts, sys_prompt)
        if not items:
            return [], "No valid inputs after prompt construction", 0

        # Step 2–3: Tiered batching
        batches = _create_tiered_batches(items, TIER_MULTIPLIER)
        _log_batch_statistics(batches, len(texts))

        # Step 4: Process batches
        summaries = [""] * len(texts)
        failed_items = _process_batches(batches, summaries, gen_params, texts)

        # Step 5: Retry failed items
        if failed_items and max_retries > 0:
            failed_items = _retry_failed_items(
                failed_items, sys_prompt, gen_params, max_retries
            )

        # Mark permanent failures
        for item in failed_items:
            idx = item["idx"]
            summaries[idx] = f"[ERROR] {item['error']}"

        valid_count = sum(1 for s in summaries if s and not s.startswith("[ERROR]"))
        print(f"\nSuccess: {valid_count} / {len(summaries)} summaries valid.")
        return summaries, "", len(batches)

    except torch.cuda.OutOfMemoryError as e:
        return (
            [],
            f"OOM — consider lowering TIER_MULTIPLIER (current: {TIER_MULTIPLIER:.1f})",
            0,
        )
    except Exception as e:
        traceback.print_exc()
        return [], f"Inference failed: {str(e)}", 0
    finally:
        with busy_lock:
            is_busy = False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


# ————————————————————————————————
# Helper functions
# ————————————————————————————————


def _prepare_items(texts: List[str], system_prompt: str) -> List[Dict]:
    """Build prompts and measure token lengths."""
    items = []
    for idx, text in enumerate(texts):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        length = len(tokenizer.encode(prompt, add_special_tokens=False))
        items.append({"idx": idx, "text": text, "prompt": prompt, "length": length})
    return items


def _create_tiered_batches(
    items: List[Dict], tier_multiplier: float
) -> List[List[Dict]]:
    """Group items into tiers based on prompt length (longest first)."""
    items.sort(key=lambda x: x["length"], reverse=True)
    batches = []
    current_batch = []

    tier_max = items[0]["length"] if items else 0

    for item in items:
        if current_batch and item["length"] >= tier_max / tier_multiplier:
            current_batch.append(item)
        else:
            if current_batch:
                batches.append(current_batch)
            current_batch = [item]
            tier_max = item["length"]

    if current_batch:
        batches.append(current_batch)

    return batches


def _log_batch_statistics(batches: List[List[Dict]], total_texts: int):
    print(f"\nTiered batching: tier boundary = {TIER_MULTIPLIER:.1f}x")
    print(f"Packed {total_texts} texts → {len(batches)} tier(s):")
    for i, batch in enumerate(batches):
        lengths = [it["length"] for it in batch]
        max_len, min_len = max(lengths), min(lengths)
        total_tokens = sum(lengths)
        avg_tokens = total_tokens / len(batch)
        padding_ratio = max_len / avg_tokens if avg_tokens > 0 else 0
        print(
            f"  Tier {i+1}: {len(batch)} items, "
            f"size range: {min_len:,}–{max_len:,} tokens, "
            f"total: {total_tokens:,}, padding: {padding_ratio:.2f}x"
        )


def _process_batches(
    batches: List[List[Dict]],
    summaries: List[str],
    gen_params: Dict[str, Any],
    original_texts: List[str],
) -> List[Dict]:
    """Generate summaries for all batches and return list of failed items."""
    failed_items = []

    for batch_idx, batch in enumerate(batches):
        prompts = [item["prompt"] for item in batch]
        indices = [item["idx"] for item in batch]

        print(
            f"  → Generating tier {batch_idx+1} ({len(prompts)} texts)... ",
            end="",
            flush=True,
        )

        inputs = tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_INPUT_LENGTH,
            return_attention_mask=True,
            padding_side="left",
        ).to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
                max_new_tokens=gen_params["max_new_tokens"],
                temperature=gen_params["temperature"],
                top_p=gen_params["top_p"],
                top_k=gen_params["top_k"],
                repetition_penalty=gen_params["repetition_penalty"],
                do_sample=True,
            )

        generated_texts = tokenizer.batch_decode(
            outputs[:, inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )

        invalid_count = 0
        for idx, text, item in zip(indices, generated_texts, batch):
            is_valid, error = is_valid_output(text.strip())
            if is_valid:
                summaries[idx] = text.strip()
                _log_success(item["original_texts"][idx], text.strip())
            else:
                invalid_count += 1
                failed_items.append(
                    {"item": item, "idx": idx, "error": error, "retry_count": 0}
                )

        print(f"Done ({invalid_count} invalid)")

    return failed_items


def _retry_failed_items(
    failed_items: List[Dict],
    base_system_prompt: str,
    gen_params: Dict[str, Any],
    max_retries: int,
) -> List[Dict]:
    """Retry generation for invalid outputs with stricter prompt."""
    print(f"\n⚠️  Retrying {len(failed_items)} invalid output(s)...")

    retry_system_prompt = (
        base_system_prompt
        + "\n\nIMPORTANT: You MUST output your reasoning inside <think>...</think> tags, "
        "then output ONLY valid JSON."
    )

    still_failed = failed_items[:]

    for attempt in range(max_retries):
        if not still_failed:
            break

        next_round = []
        for data in still_failed:
            item = data["item"]
            idx = data["idx"]
            error = data["error"]

            print(
                f"  Retry {attempt+1}/{max_retries} for item {idx} (error: {error})... ",
                end="",
                flush=True,
            )

            messages = [
                {"role": "system", "content": retry_system_prompt},
                {"role": "user", "content": item["text"]},
            ]
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

            inputs = tokenizer(
                [prompt],
                return_tensors="pt",
                padding=True,
                max_length=MAX_INPUT_LENGTH,
                padding_side="left",
            ).to(device)

            with torch.no_grad():
                output = model.generate(
                    **inputs,
                    pad_token_id=tokenizer.eos_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    max_new_tokens=gen_params["max_new_tokens"],
                    temperature=gen_params["temperature"] * 0.9,
                    top_p=gen_params["top_p"],
                    top_k=gen_params["top_k"],
                    repetition_penalty=gen_params["repetition_penalty"],
                    do_sample=True,
                )

            generated = tokenizer.decode(
                output[0, inputs["input_ids"].shape[1] :],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            ).strip()

            is_valid, new_error = is_valid_output(generated)
            if is_valid:
                summaries[idx] = generated
                print("✅ Valid")
                _log_retry_success(item["text"], generated)
            else:
                print(f"❌ Still invalid: {new_error}")
                data["error"] = new_error
                data["retry_count"] = attempt + 1
                next_round.append(data)

        still_failed = next_round

    # Log permanent failures
    if still_failed:
        print(f"\n❌ {len(still_failed)} items failed all retries.")
        with open("server.log", "a", encoding="utf-8") as f:
            for data in still_failed:
                f.write(f"=== FINAL FAILURE (idx {data['idx']}) ===\n")
                f.write(f"Error: {data['error']}\n")
                f.write("USER TEXT:\n" + data["item"]["text"].strip() + "\n")
                f.write("=== FINAL FAILURE END ===\n\n")

    return still_failed


def _log_success(user_text: str, summary: str):
    with open("server.log", "a", encoding="utf-8") as f:
        f.write("=== ITEM START ===\n")
        f.write("USER TEXT:\n" + user_text.strip() + "\n\n")
        f.write("ASSISTANT RESPONSE:\n" + summary.strip() + "\n")
        f.write("=== ITEM END ===\n\n")


def _log_retry_success(user_text: str, summary: str):
    with open("server.log", "a", encoding="utf-8") as f:
        f.write("=== RETRY SUCCESS ===\n")
        f.write("USER TEXT:\n" + user_text.strip() + "\n\n")
        f.write("ASSISTANT RESPONSE:\n" + summary + "\n")
        f.write("=== RETRY SUCCESS END ===\n\n")


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
