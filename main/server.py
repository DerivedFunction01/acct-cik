from flask import Flask, request, jsonify
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import multiprocessing as mp
import os
import json

app = Flask(__name__)

# Paths
MODEL_PATH = "DerivedFunction/derivative-classifier"  # your saved Hugging Face model
# Load tokenizer & model
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)

# Check for an environment variable to force CPU, otherwise default to GPU if available
DEVICE_TYPE = os.environ.get("DEVICE_TYPE", "gpu").lower()
if DEVICE_TYPE == "cpu":
    device = torch.device("cpu")
else:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

model.to(device)
model.eval()  # evaluation mode

# Correct labels for the multi-label model
labels = [
    "ir", "fx", "cp", "eq", "gen",
    "ir_use", "fx_use", "cp_use", "eq_use", "gen_use",
    "curr", "hist", "term", "spec",
    "warr", "emb",
    "irr",
]
id2label = {i: label for i, label in enumerate(labels)}
label2id = {label: i for i, label in enumerate(labels)}


# Prediction function for batches
def predict_batch(texts):
    # Tokenize the batch
    inputs = tokenizer(
        texts, padding=True, truncation=True, max_length=512, return_tensors="pt"
    )
    # Move inputs to the same device as the model
    inputs = {key: val.to(device) for key, val in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probabilities = torch.sigmoid(logits)
        
    # Create a list of dictionaries with label probabilities
    results = []
    for text_probs in probabilities:
        label_probs = {id2label[i]: round(prob.item(), 3) for i, prob in enumerate(text_probs)}
        results.append(label_probs)

    return {"predictions": results}


# Flask route
@app.route("/predict", methods=["POST"])
def predict_endpoint():
    data = request.json
    if "texts" not in data or not isinstance(data["texts"], list):
        return (
            jsonify({"error": "Missing or invalid 'texts' field; must be a list"}),
            400,
        )
    texts = data["texts"]
    predictions = predict_batch(texts)
    return jsonify(predictions)


# GPU Info route
@app.route("/info", methods=["GET"])
def info_endpoint():
    """Provides information about the server's GPU, if available."""
    info = {"device_in_use": str(device)}
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        total_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        info = {
            "gpu_available": True,
            "gpu_name": gpu_name,
            "total_ram_gb": round(total_memory_gb, 2),
            **info
        }
    else:
        info = {
            "gpu_available": False,
            "message": "No CUDA-enabled GPU found.",
            "cpu_cores": mp.cpu_count(),
            **info
        }
    return jsonify(info)


# Run Flask app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)

# For production, use a single worker and multiple threads to share the model in memory efficiently.
# GPU Server: DEVICE_TYPE=gpu gunicorn --workers 1 --timeout 120 server:app --bind 0.0.0.0:5001 --threads 8
# CPU Server: DEVICE_TYPE=cpu gunicorn --workers 1 --timeout 120 server:app --bind 0.0.0.0:5002 --threads 8
#
# Then use a load balancer like Nginx to listen on port 5000 and distribute requests
# to the upstream servers at ports 5001 and 5002.
