from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import torch
import os
import json
from unsloth import FastLanguageModel
from transformers import TextIteratorStreamer
from threading import Thread
import multiprocessing as mp

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
MODEL_PATH = "Qwen3-1.7B-finance-base"
MAX_SEQ_LENGTH = 32768

# --- Recommended generation parameters ---
THINKING_PARAMS = {
    "do_sample": True,
    "temperature": 0.6,
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
    "repetition_penalty": 1.1
}

# --- Device & VRAM detection ---
DEVICE_TYPE = os.environ.get("DEVICE_TYPE", "gpu").lower()
load_in_4bit = True
if DEVICE_TYPE == "cpu":
    device = torch.device("cpu")
    load_in_4bit = False
else:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# --- Load model ---
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_PATH,
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=None,
    load_in_4bit=load_in_4bit,
)
FastLanguageModel.for_inference(model)
print("Model loaded.")


def get_gen_params(user_params: dict = None, enable_thinking: bool = True):
    """Selects the appropriate parameter set and merges user overrides."""
    if enable_thinking:
        params = THINKING_PARAMS.copy()
    else:
        params = NON_THINKING_PARAMS.copy()

    if user_params:
        params.update(user_params)

    params["max_new_tokens"] = params.get("max_new_tokens", MAX_SEQ_LENGTH)
    params["use_cache"] = True # Always use cache for inference
    return params


def generate_response(prompt: str, user_params: dict = None):
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
    streamer = TextIteratorStreamer(
        tokenizer, skip_prompt=True, skip_special_tokens=True
    )
    # --- NEW: Use tokenizer's chat template for proper formatting ---
    # This allows us to control the <think> block via the `enable_thinking` flag.
    enable_thinking = user_params.pop("enable_thinking", True) if user_params else True
    params = get_gen_params(user_params, enable_thinking=enable_thinking)
    messages = [{"role": "user", "content": prompt}]
    formatted_prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    inputs = tokenizer([formatted_prompt], return_tensors="pt").to(device)

    gen_kwargs = dict(
        inputs,
        streamer=streamer,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        **params,
    )
    thread = Thread(target=model.generate, kwargs=gen_kwargs)
    thread.start()
    for token in streamer:
        yield token


@app.route("/generate", methods=["POST"])
def generate_endpoint():
    data = request.json or {}
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "Missing 'prompt'"}), 400
    params = data.get("params", {})
    result = generate_response(prompt, params)
    return jsonify({"prediction": result})


@app.route("/generate-stream", methods=["POST"])
def generate_stream_endpoint():
    data = request.json or {}
    prompt = data.get("prompt", "")
    params = data.get("params", {})
    # The 'enable_thinking' flag is now passed within the params dictionary
    return Response(generate_stream(prompt, params), mimetype="text/plain")


@app.route("/info", methods=["GET"])
def info_endpoint():
    info = {"device": str(device)}
    if torch.cuda.is_available():
        prop = torch.cuda.get_device_properties(0)
        info.update(
            {
                "gpu": True,
                "name": torch.cuda.get_device_name(0),
                "vram_gb": round(prop.total_memory / (1024**3), 2),
            }
        )
    else:
        info.update({"gpu": False, "cpu_cores": mp.cpu_count()})
    return jsonify(info)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
