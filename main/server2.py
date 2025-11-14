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
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    print("⚠️ Unsloth not found. Falling back to standard Hugging Face transformers.")

import torch
from transformers import TextIteratorStreamer

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
MODEL_PATH = "DerivedFunction/Qwen3-1.7B-derivatives-classifier"
MAX_SEQ_LENGTH = 32768 
TEXT_SIZE = MAX_SEQ_LENGTH // 8

THINKING_PARAMS = {
    "do_sample": False,  # Deterministic during debugging
    "temperature": 0.55,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "repetition_penalty": 1.1,
}

NON_THINKING_PARAMS = {
    "do_sample": False,  # Deterministic during debugging
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
    streamer = TextIteratorStreamer(
        tokenizer, skip_prompt=True, skip_special_tokens=True
    )
    enable_thinking = user_params.pop("enable_thinking", True) if user_params else True
    system_prompt = (
        user_params.pop("system_prompt", SYSTEM_PROMPT)
        if user_params
        else SYSTEM_PROMPT
    )
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
        # Fallback for models that don't support enable_thinking parameter
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

    thread = Thread(target=model.generate, kwargs=gen_kwargs)
    thread.start()

    for token in streamer:
        yield token


@app.route("/generate", methods=["POST"])
def generate_endpoint():
    """Endpoint for non-streaming generation."""
    try:
        data = request.json or {}
        prompt = data.get("prompt", "")
        if not prompt:
            return jsonify({"error": "Missing 'prompt'"}), 400

        params = data.get("params", {})
        if not isinstance(params, dict):
            return jsonify({"error": "'params' must be a dictionary"}), 400

        params_copy = params.copy()
        enable_thinking = params_copy.pop("enable_thinking", False)  # Default to False
        system_prompt = params_copy.pop("system_prompt", SYSTEM_PROMPT)
        gen_params = get_gen_params(params_copy, enable_thinking=enable_thinking)

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
            # Fallback for models without enable_thinking support
            formatted_prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

        print(f"DEBUG: Formatted prompt length: {len(formatted_prompt)} chars")

        # Tokenize first, check size, then move to device
        inputs = tokenizer([formatted_prompt], return_tensors="pt")
        token_count = inputs["input_ids"].shape[1]
        print(f"DEBUG: Token count: {token_count} / {MAX_SEQ_LENGTH}")

        if token_count > MAX_SEQ_LENGTH:
            return (
                jsonify(
                    {
                        "error": "Input too long",
                        "token_count": token_count,
                        "max_allowed": MAX_SEQ_LENGTH,
                    }
                ),
                400,
            )

        inputs = inputs.to(device)

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=[tokenizer.eos_token_id],
                **gen_params,
            )

        # Decode the generated output
        output_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)
        print(f"DEBUG: Generated text (first 300 chars): {output_text[:300]}")

        # Try to parse as JSON
        try:
            result = json.loads(output_text)
        except json.JSONDecodeError:
            result = {"response": output_text}

        return jsonify({"prediction": result})

    except torch.cuda.OutOfMemoryError as e:
        return (
            jsonify(
                {
                    "error": "Out of GPU memory",
                    "suggestion": "Try reducing max_new_tokens or enabling 4-bit quantization",
                }
            ),
            507,
        )
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": "Generation failed", "details": str(e)}), 500


@app.route("/generate-stream", methods=["POST"])
def generate_stream_endpoint():
    """Endpoint for streaming token generation."""
    try:
        data = request.json or {}
        prompt = data.get("prompt", "")
        if not prompt:
            return jsonify({"error": "Missing 'prompt'"}), 400
        params = data.get("params", {})
        return Response(generate_stream(prompt, params), mimetype="text/plain")
    except Exception as e:
        print(f"ERROR in stream endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/info", methods=["GET"])
def info_endpoint():
    """Endpoint for server info and hardware details."""
    info = {"device": str(device), "max_seq_length": MAX_SEQ_LENGTH}
    if is_gpu:
        prop = torch.cuda.get_device_properties(0)
        info.update(
            {
                "gpu_available": True,
                "gpu_name": torch.cuda.get_device_name(0),
                "total_ram_gb": round(prop.total_memory / (1024**3), 2),
                "load_in_4bit": load_in_4bit,
            }
        )
    else:
        info.update({"gpu_available": False, "cpu_cores": mp.cpu_count()})
    return jsonify(info)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
