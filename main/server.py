from flask import Flask, request, jsonify
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import json

app = Flask(__name__)

# Paths
MODEL_PATH = "DerivedFunction/derivative-classifier"  # your saved Hugging Face model
# Load tokenizer & model
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
model.eval()  # evaluation mode

# Correct labels for the multi-label model
labels = [
    "ir", "fx", "cp", "eq", "gen",
    "ir_use", "fx_use", "cp_use", "eq_use", "gen_use",
    "curr", "hist", "spec",
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


# Run Flask app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)

# gunicorn --workers {num_workers} --timeout 120 server:app --bind 0.0.0.0:5000"
