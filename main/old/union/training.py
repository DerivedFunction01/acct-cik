# %%
# %pip install pandas torch scikit-learn datasets transformers numpy openpyxl accelerate


# %%
# Initialization
## Required libraries
import pandas as pd
import torch
from sklearn.model_selection import train_test_split
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding,
)
import numpy as np
from sklearn.metrics import f1_score, roc_auc_score, accuracy_score
from transformers import EvalPrediction
import json
from pathlib import Path

EXCEL_PATH = "./training_data.xlsx"
MODEL_PATH = "cb-coverage"
MODEL_USER = "DerivedFunction"
FINE_TUNE_MODEL = "ProsusAI/finbert"
MODEL_NAME = f"{MODEL_USER}/{MODEL_PATH}" if not FINE_TUNE_MODEL else FINE_TUNE_MODEL
RESUME_FROM_CHECKPOINT = Path(MODEL_PATH).exists()

labels = [
    "cb_coverage",  # Has actual collective bargaining coverage
    "cb_risk",  # Risk factor/speculative mention
    "us_risk",  # US specific risk
    "int_risk",  # International specific risk
    "cb_international",  # Only international operations
    "cb_us",  # Only US operations
    "no_cb",  # Explicit no coverage statement
]
id2label = {i: label for i, label in enumerate(labels)}
label2id = {label: i for i, label in enumerate(labels)}

# %%
# Load and preprocess data
df = pd.read_excel(EXCEL_PATH)
df.dropna(subset=["sentence", "labels"], inplace=True)


def format_labels(row):
    label_dict = json.loads(row["labels"])
    return [label_dict.get(label, 0) for label in labels]


df["labels"] = df.apply(format_labels, axis=1)
train_df, val_df = train_test_split(df, test_size=0.2, random_state=42)
train_dataset = Dataset.from_pandas(train_df)
val_dataset = Dataset.from_pandas(val_df)

batch_size = 8
num_epochs = 2


# %%
# Tokenization
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
def tokenize_function(examples):
    tokenized_input = tokenizer(examples["sentence"], truncation=True, max_length=512)
    tokenized_input["labels"] = [
        [float(x) for x in label] for label in examples["labels"]
    ]
    return tokenized_input


tokenized_train_dataset = train_dataset.map(tokenize_function, batched=True)
tokenized_val_dataset = val_dataset.map(tokenize_function, batched=True)
tokenized_train_dataset.set_format(
    "torch", columns=["input_ids", "attention_mask", "labels"]
)
tokenized_val_dataset.set_format(
    "torch", columns=["input_ids", "attention_mask", "labels"]
)


# Custom data collator
class CustomDataCollatorWithPadding(DataCollatorWithPadding):
    def __call__(self, features):
        batch = super().__call__(features)
        batch["labels"] = torch.stack(
            [torch.tensor(f["labels"], dtype=torch.float32) for f in features]
        )
        return batch


collator = CustomDataCollatorWithPadding(tokenizer=tokenizer)

# %%
# Metrics
def multi_label_metrics(predictions, labels, threshold=0.5):
    sigmoid = torch.nn.Sigmoid()
    probs = sigmoid(torch.Tensor(predictions))
    y_pred = np.zeros(probs.shape)
    y_pred[np.where(probs >= threshold)] = 1
    # Threshold the true labels to convert soft labels (floats) to binary (0 or 1)
    y_true = np.zeros(labels.shape)
    y_true[np.where(labels >= threshold)] = 1

    f1_micro_average = f1_score(y_true=y_true, y_pred=y_pred, average="micro")
    roc_auc = roc_auc_score(y_true, probs, average="micro")
    accuracy = accuracy_score(y_true, y_pred)
    return {"f1": f1_micro_average, "roc_auc": roc_auc, "accuracy": accuracy}


def compute_metrics(p: EvalPrediction):
    preds = p.predictions[0] if isinstance(p.predictions, tuple) else p.predictions
    return multi_label_metrics(predictions=preds, labels=p.label_ids)

# %%
## Training
"""Here, we define the training parameters and launch the fine-tuning process. 🚀 """
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    problem_type="multi_label_classification",
    num_labels=len(labels),
    id2label=id2label,
    label2id=label2id,
    ignore_mismatched_sizes=True,
)
device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
model.to(device)

# %%
# Training arguments
training_args = TrainingArguments(
    output_dir=MODEL_PATH,
    num_train_epochs=num_epochs,
    per_device_train_batch_size=batch_size,
    per_device_eval_batch_size=1,
    warmup_steps=500,
    weight_decay=0.01,
    logging_dir="./logs",
    logging_steps=10,
    eval_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="f1",
)
# Debug batch shape
sample_batch = collator([tokenized_train_dataset[i] for i in range(batch_size)])
print("Input IDs shape:", sample_batch["input_ids"].shape)
print("Attention Mask shape:", sample_batch["attention_mask"].shape)
print("Labels shape:", sample_batch["labels"].shape)
print(f"Training set size: {len(train_df)}")
print(f"Validation set size: {len(val_df)}")


# %%
# Initialize the Trainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_train_dataset,
    eval_dataset=tokenized_val_dataset,
    compute_metrics=compute_metrics,
    data_collator=collator,  # Pass the data collator
)

# Start training!
trainer.train(resume_from_checkpoint=RESUME_FROM_CHECKPOINT)  # resume_from_checkpoint=True


# %%
# Save the model %pip install -U "huggingface_hub[cli]"
## hf auth login
## hf upload DerivedFunction/. [folder-path]
## from huggingface_hub import notebook_login
# notebook_login()
# trainer.push_to_hub(MODEL_CHECKPOINT)

# %%
# Prediction
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import json
from enum import Enum


class PrimaryLabel(Enum):
    """Defines the primary integer labels for classification."""

    CB_COVERAGE = 0
    CB_RISK = 2
    NO_CB_EXPLICIT = 3
    INTERNATIONAL_ONLY = 4
    CB_US_ONLY = 5
    IRRELEVANT = 6


primary_id2label = {
    PrimaryLabel.CB_COVERAGE.value: "CB_Coverage_Disclosed",
    PrimaryLabel.CB_RISK.value: "CB_Risk_Only",
    PrimaryLabel.NO_CB_EXPLICIT.value: "No_CB_Explicit",
    PrimaryLabel.INTERNATIONAL_ONLY.value: "International_Only",
    PrimaryLabel.CB_US_ONLY.value: "CB_US_Only",
    PrimaryLabel.IRRELEVANT.value: "Irrelevant",
}


def get_primary_cb_label(labels: dict) -> str:
    """
    Assigns a single primary label name based on a dictionary of multi-hot labels.
    Priority Order:
    1. US-Only Coverage
    2. International-Only Coverage
    3. General Coverage
    4. Risk Mentions
    5. No Coverage
    6. Irrelevant
    """
    if labels.get("cb_us") and not labels.get("cb_international"):
        return primary_id2label[PrimaryLabel.CB_US_ONLY.value]

    if labels.get("cb_international") and not labels.get("cb_us"):
        return primary_id2label[PrimaryLabel.INTERNATIONAL_ONLY.value]

    if labels.get("cb_coverage"):
        return primary_id2label[PrimaryLabel.CB_COVERAGE.value]

    if labels.get("cb_risk"):
        return primary_id2label[PrimaryLabel.CB_RISK.value]

    if labels.get("no_cb"):
        return primary_id2label[PrimaryLabel.NO_CB_EXPLICIT.value]

    return primary_id2label[PrimaryLabel.IRRELEVANT.value]


# --- Batch prediction ---
def predict_batch(sentences: list[str]):
    model.eval()
    inputs = tokenizer(
        sentences, return_tensors="pt", truncation=True, padding=True, max_length=512
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.sigmoid(logits.cpu())

    all_results = []
    for i, text_probs in enumerate(probs):
        prob_dict = {label: float(prob) for label, prob in zip(labels, text_probs)}
        primary_label = get_primary_cb_label(prob_dict)
        all_results.append({"pred_vector": prob_dict, "primary_label": primary_label})

    return all_results


# %%
# --- Single string example ---
text = """
As of December 31, 2022, approximately 45% of our employees were represented by unions. 
We consider our employee relations to be good.
"""
result = predict_batch([text])[0]

print("--- Multi-Label Prediction ---")
print("Prediction Vector:")
for label, score in result["pred_vector"].items():
    print(f"  - {label}: {score:.4f}")

print("\n--- Primary Label Prediction ---")
print(result["primary_label"])