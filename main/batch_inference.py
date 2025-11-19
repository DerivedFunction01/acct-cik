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
MODEL_PATH = "DerivedFunction/Qwen3-0.6B-mk-deriv-summarize"
MAX_SEQ_LENGTH = 8192
BATCH_SIZE = 8  # Number of texts to process in parallel per forward pass
MAX_INPUT_LENGTH = 6144  # Leave room for generation (8192 - 2048)

GENERATION_PARAMS = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 20,
    "repetition_penalty": 1.1,
    "max_new_tokens": 512,  # Reduced from 1028 to be safer
}

# Default system prompt for summarization
SYSTEM_PROMPT = """Produce a concise 2-4 sentence summary of the financial text.
Focus on whether derivatives are used, what risks they hedge, the instruments involved,
and whether usage is active, terminated, non-use, potential, or policy/accounting treatement.
State the dollar amounts and year if present.
Do not add information not present in the text."""

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
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, padding_side="left")
    print("✅ Standard transformers model loaded.")

# Set pad token if not set
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
    print(f"⚙️  Set pad_token to eos_token: {tokenizer.eos_token}")

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

        summaries = []
        num_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

        print(
            f"\n📦 Starting batch summarization: {len(texts)} texts in {num_batches} batches"
        )

        for batch_idx in range(num_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, len(texts))
            batch_texts = texts[start_idx:end_idx]

            print(
                f"  Batch {batch_idx + 1}/{num_batches} ({len(batch_texts)} texts)... ",
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
            )

            inputs = inputs.to(device)
            input_length = inputs["input_ids"].shape[1]

            # --- Generate summaries for entire batch in parallel ---
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
                    max_new_tokens=gen_params.get("max_new_tokens", 512),
                    do_sample=True,  # Enable sampling for temperature/top_p
                )

            # --- Decode only the generated tokens (skip input tokens) ---
            batch_summaries = tokenizer.batch_decode(
                outputs[:, input_length:],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )

            summaries.extend(batch_summaries)
            print(f"✅ ({len(batch_texts)} texts processed)")

        print(
            f"✅ Batch summarization complete: {len(summaries)} summaries generated\n"
        )
        return summaries, "", num_batches

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
