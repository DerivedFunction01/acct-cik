from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import multiprocessing as mp
import os
from threading import Thread

try:
    import unsloth
    from unsloth import FastLanguageModel
    USE_UNSLOTH = True
    print("✅ Unsloth found. Using Unsloth for model loading.")
except ImportError:
    USE_UNSLOTH = False
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print("⚠️ Unsloth not found. Falling back to standard Hugging Face transformers.")
import torch
from transformers import TextIteratorStreamer

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
MODEL_PATH = "DerivedFunction/Qwen3-1.7B-derivatives-classifier"
MAX_SEQ_LENGTH = 32768 # How many tokens the entire conversation should hold (reasoning may take up the majority)
TEXT_SIZE = MAX_SEQ_LENGTH // 4 # A good estimate of how much text should use
# --- Recommended generation parameters ---
THINKING_PARAMS = {
    "do_sample": True,
    "temperature": 0.55,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "repetition_penalty": 1.1,
}

NON_THINKING_PARAMS = {
    "do_sample": True,
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
        SYSTEM_PROMPT = f.read() # Sys prompt is around 3000 chars

# --- Dynamic Hardware Detection ---
def get_hardware_config():
    """Detects GPU and sets configuration for model loading and batching."""
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"✅ GPU detected with {vram_gb:.2f} GB VRAM.")
        # Set batch size based on VRAM. More VRAM allows for larger batches.
        if vram_gb > 20:
            batch_size = 4  # High-end GPUs (A100, etc.)
        elif vram_gb > 14:
            batch_size = 3  # Desktop GPUs (15GB+)
        else:
            batch_size = 2  # Laptop GPUs (8GB+)
        return torch.device("cuda"), True, batch_size
    else:
        print("⚠️ No GPU detected. Running on CPU.")
        return torch.device("cpu"), False, 1  # Batch size of 1 for CPU


device, is_gpu, BATCH_SIZE = get_hardware_config()
load_in_4bit = True

# --- Load model ---
if USE_UNSLOTH:
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_PATH,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=load_in_4bit,
    )
    FastLanguageModel.for_inference(model)
else:
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        load_in_4bit=load_in_4bit,
        torch_dtype=torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

print(
    f"✅ Model loaded. Server configured with BATCH_SIZE = {BATCH_SIZE}, "
    f"USE_UNSLOTH = {USE_UNSLOTH}"
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
    params["use_cache"] = True  # Always use cache for inference
    return params


def generate_response(prompt: str, user_params: dict = None) -> dict:
    """
    Generates a complete JSON response by consuming the token stream from `generate_stream`.
    """
    # Consume the generator to get the full response string.
    full_response = "".join(token for token in generate_stream(prompt, user_params))
    try:
        # The stream is already the clean assistant output, so we can parse it directly.
        return json.loads(full_response)
    except Exception as e:
        return {"error": "JSON parse failed", "raw": full_response, "exception": str(e)}


def generate_stream(prompt: str, user_params: dict = None):
    """Streams tokens from model generation with optional thinking mode."""
    streamer = TextIteratorStreamer(
        tokenizer, skip_prompt=True, skip_special_tokens=True
    )
    # Use tokenizer's chat template for proper formatting.
    # Control the <think> block via the `enable_thinking` flag.
    enable_thinking = user_params.pop("enable_thinking", True) if user_params else True
    # Use the user-provided system prompt, or fall back to the global default.
    system_prompt = user_params.pop("system_prompt", SYSTEM_PROMPT) if user_params else SYSTEM_PROMPT
    params = get_gen_params(user_params, enable_thinking=enable_thinking)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    formatted_prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    inputs = tokenizer([formatted_prompt], return_tensors="pt").to(device)

    # Define EOS tokens to force the model to complete thinking process.
    # This prevents premature stopping if it generates an <|im_end|> token
    # inside the <think> block while still allowing completion.
    eos_token_ids = [tokenizer.eos_token_id]

    gen_kwargs = dict(
        inputs,
        streamer=streamer,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=eos_token_ids,
        **params,
    )
    thread = Thread(target=model.generate, kwargs=gen_kwargs)
    thread.start()
    for token in streamer:
        yield token


@app.route("/generate", methods=["POST"])
def generate_endpoint():
    """Endpoint for non-streaming generation."""
    data = request.json or {}
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "Missing 'prompt'"}), 400
    params = data.get("params", {})
    result = generate_response(prompt, params)
    return jsonify({"prediction": result})


@app.route("/generate-stream", methods=["POST"])
def generate_stream_endpoint():
    """Endpoint for streaming token generation."""
    data = request.json or {}
    prompt = data.get("prompt", "")
    params = data.get("params", {})
    # The 'enable_thinking' flag is passed within the params dictionary
    return Response(generate_stream(prompt, params), mimetype="text/plain")


@app.route("/info", methods=["GET"])
def info_endpoint():
    """Endpoint for server info and hardware details."""
    info = {"device": str(device), "max_seq_length": TEXT_SIZE}
    if is_gpu:
        prop = torch.cuda.get_device_properties(0)
        info.update(
            {
                "gpu_available": True,
                "gpu_name": torch.cuda.get_device_name(0),
                "total_ram_gb": round(prop.total_memory / (1024**3), 2),
            }
        )
    else:
        info.update({"gpu_available": False, "cpu_cores": mp.cpu_count()})
    return jsonify(info)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
