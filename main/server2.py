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
MODEL_PATH = "DerivedFunction/Qwen3-1.7B-derivatives-base"
MAX_SEQ_LENGTH = 8192

# --- Global default generation parameters ---
DEFAULT_GEN_PARAMS = {
    "max_new_tokens": MAX_SEQ_LENGTH,
    "do_sample": False,
    "temperature": 0.7,
    "top_p": 1.0,
    "repetition_penalty": 1.0,
    "use_cache": True,
}

# --- Device & VRAM detection ---
DEVICE_TYPE = os.environ.get("DEVICE_TYPE", "gpu").lower()
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
    load_in_4bit=False,
)
FastLanguageModel.for_inference(model)
print("Model loaded.")


def get_gen_params(user_params: dict = None):
    params = DEFAULT_GEN_PARAMS.copy()
    if user_params:
        params.update(user_params)
    return params


def generate_response(prompt: str, user_params: dict = None):
    params = get_gen_params(user_params)
    formatted = f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
    inputs = tokenizer([formatted], return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            **params,
        )

    text = tokenizer.batch_decode(outputs, skip_special_tokens=False)[0]
    try:
        assistant = text.split("<|im_start|>assistant")[-1]
        clean = assistant.split("<|im_end|>")[0].strip()
        return json.loads(clean)
    except Exception as e:
        return {"error": "JSON parse failed", "raw": text, "exception": str(e)}


def generate_stream(prompt: str, user_params: dict = None):
    streamer = TextIteratorStreamer(
        tokenizer, skip_prompt=True, skip_special_tokens=True
    )
    params = get_gen_params(user_params)
    formatted = f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
    inputs = tokenizer([formatted], return_tensors="pt").to(device)

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
