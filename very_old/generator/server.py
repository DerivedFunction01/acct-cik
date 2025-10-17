from flask import Flask, request, jsonify
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import json

app = Flask(__name__)

# Paths
MODEL_PATH = "DerivedFunction/derivative-type-classifier"  # your saved Hugging Face model
KEYWORDS_FILE = "./keywords_find.json"
# Load tokenizer & model
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
model.eval()  # evaluation mode

# Mapping IDs to labels
with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
    keyword_data = json.load(f)

id2label = keyword_data["id2label"]
label2id = {label: id for id, label in id2label.items()}


# Prediction function for batches
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
        predicted_ids = torch.argmax(logits, dim=1).tolist()
    # Write results to tab-separated file
    # with open('predictions.xml', 'a') as f:
    #     for idx, (text, pred) in enumerate(zip(texts, predictions['predictions'])):
    #         case_string = f"<case num=\"{idx}\"><text>{text}</text><label>{pred['label']}</label><label_id>{pred['label_id']}</label_id></case>\n"
    #         f.write(case_string)
    return {"predictions": predicted_ids}


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
