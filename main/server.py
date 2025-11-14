from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import multiprocessing as mp
import os
from threading import Thread, Lock
import asyncio

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
from transformers import TextIteratorStreamer

app = FastAPI(
    title="Model Server", description="Streaming language model inference API"
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
MODEL_PATH = "DerivedFunction/Qwen3-1.7B-derivatives-classifier"
MAX_SEQ_LENGTH = 32768
TEXT_SIZE = MAX_SEQ_LENGTH // 8
THINKING_PARAMS = {
    "temperature": 0.60,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "repetition_penalty": 1.1,
}

NON_THINKING_PARAMS = {
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "min_p": 0.0,
    "repetition_penalty": 1.1,
}

SYS_PROMPT_FILE = "sys_prompt_regular.md"
SYSTEM_PROMPT = ""
if os.path.exists(SYS_PROMPT_FILE):
    with open(SYS_PROMPT_FILE, "r") as f:
        SYSTEM_PROMPT = f.read()

# --- BUSY STATE TRACKING ---
# Lock to prevent race conditions when updating busy state
busy_lock = Lock()
is_busy = False


# --- Pydantic Models ---
class GenerateRequest(BaseModel):
    prompt: str
    params: Optional[Dict[str, Any]] = None


class InfoResponse(BaseModel):
    device: str
    max_seq_length: int
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
        if vram_gb > 20:
            batch_size = 4
        elif vram_gb > 14:
            batch_size = 3
        else:
            batch_size = 2
        load_in_4bit = vram_gb < 20
        return torch.device("cuda"), True, batch_size, load_in_4bit
    else:
        print("⚠️ No GPU detected. Running on CPU.")
        return torch.device("cpu"), False, 1, False


device, is_gpu, BATCH_SIZE, load_in_4bit = get_hardware_config()

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
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    print("✅ Standard transformers model loaded.")

print(
    f"✅ Model loaded. Server configured with BATCH_SIZE = {BATCH_SIZE}, "
    f"USE_UNSLOTH = {USE_UNSLOTH}, 4-bit = {load_in_4bit}"
)


def get_gen_params(user_params: dict = None, enable_thinking: bool = True) -> dict:
    """Selects the appropriate parameter set and merges user overrides."""
    if enable_thinking:
        params = THINKING_PARAMS.copy()
    else:
        params = NON_THINKING_PARAMS.copy()

    if user_params:
        params.update(user_params)

    params["max_new_tokens"] = params.get("max_new_tokens", MAX_SEQ_LENGTH)
    params["use_cache"] = True
    return params


def generate_stream(prompt: str, user_params: dict = None):
    """Streams tokens from model generation with optional thinking mode."""
    global is_busy

    streamer = TextIteratorStreamer(
        tokenizer, skip_prompt=True, skip_special_tokens=True, max_new_tokens=10
    )

    if user_params is None:
        user_params = {}
    else:
        user_params = user_params.copy()

    enable_thinking = user_params.pop("enable_thinking", True)
    system_prompt = user_params.pop("system_prompt", SYSTEM_PROMPT)
    params = get_gen_params(user_params, enable_thinking=enable_thinking)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        formatted_prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=enable_thinking,
        )
    except TypeError:
        formatted_prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    print(f"DEBUG: Formatted prompt length: {len(formatted_prompt)} chars")

    inputs = tokenizer([formatted_prompt], return_tensors="pt")
    token_count = inputs["input_ids"].shape[1]
    print(f"DEBUG: Token count: {token_count}")

    if token_count > MAX_SEQ_LENGTH:
        yield json.dumps(
            {"error": f"Input too long: {token_count} tokens > {MAX_SEQ_LENGTH} max"}
        )
        return

    inputs = inputs.to(device)
    eos_token_ids = [tokenizer.eos_token_id]

    gen_kwargs = {
        **inputs,
        "streamer": streamer,
        "pad_token_id": tokenizer.eos_token_id,
        "eos_token_id": eos_token_ids,
        **params,
    }

    # Mark as busy
    with busy_lock:
        is_busy = True
        print("🔴 Process marked as BUSY")

    try:
        thread = Thread(target=model.generate, kwargs=gen_kwargs)
        thread.start()

        for token in streamer:
            yield token

        thread.join()
    finally:
        # Mark as idle after generation completes
        with busy_lock:
            is_busy = False
            print("🟢 Process marked as IDLE")


@app.post("/generate-stream")
async def generate_stream_endpoint(request: GenerateRequest):
    """Endpoint for streaming token generation."""
    try:
        if not request.prompt:
            raise HTTPException(status_code=400, detail="Missing 'prompt'")

        params = request.params or {}
        return StreamingResponse(
            generate_stream(request.prompt, params), media_type="text/plain"
        )
    except Exception as e:
        print(f"ERROR in stream endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status", response_model=StatusResponse)
async def status_endpoint():
    """
    Check if this process is busy or idle.
    Useful for clients to know if they should send requests.
    """
    with busy_lock:
        if is_busy:
            return StatusResponse(
                status="busy",
                message="This process is currently generating. Request queued or try another server.",
            )
        else:
            return StatusResponse(
                status="idle", message="This process is ready to accept requests."
            )


@app.get("/info", response_model=InfoResponse)
async def info_endpoint():
    """Endpoint for server info and hardware details."""
    info_dict = {
        "device": str(device),
        "max_seq_length": MAX_SEQ_LENGTH,
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
        "message": "Model Server API",
        "docs": "/docs",
        "endpoints": {
            "generate-stream": "POST /generate-stream - Stream token generation",
            "status": "GET /status - Check if process is busy or idle",
            "info": "GET /info - Server info and hardware details",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
