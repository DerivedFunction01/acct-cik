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
MODEL_PATH = "derivative-classifier"
MODEL_USER = "DerivedFunction"
FINE_TUNE_MODEL = "ProsusAI/finbert"
MODEL_NAME = f"{MODEL_USER}/{MODEL_PATH}" if not FINE_TUNE_MODEL else FINE_TUNE_MODEL
KEYWORDS_FILE = "./keywords_find.json"
RESUME_FROM_CHECKPOINT = Path(MODEL_PATH).exists()

labels = [
    "ir",
    "fx",
    "cp",
    "eq",
    "gen",
    "ir_use",
    "fx_use",
    "cp_use",
    "eq_use",
    "gen_use",
    "curr",
    "hist",
    "spec",
    "warr",
    "emb",
    "irr",
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
## hf upload DerivedFunction/finbert-derivative-usage-classifier [folder-path]
## from huggingface_hub import notebook_login
# notebook_login()
# trainer.push_to_hub(MODEL_CHECKPOINT)

# %%
# Prediction Setup
''' This cell loads the model and all necessary components for prediction. Run this once before running the prediction cells below.'''
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import json
import numpy as np
import pandas as pd

MODEL_PATH = "DerivedFunction/derivative-classifier"
KEYWORDS_FILE = "./keywords_find.json"

# Load keyword mappings
with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
    primary_id2label = json.load(f)

# Define the multi-label names (must match training)
labels = [
    "ir",
    "fx",
    "cp",
    "eq",
    "gen",
    "ir_use",
    "fx_use",
    "cp_use",
    "eq_use",
    "gen_use",
    "curr",
    "hist",
    "spec",
    "warr",
    "emb",
    "irr",
]

# Load model & tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
model.to(device)

# Define mappings for primary label conversion
hedge_map = {
    "ir": (0, 1, 2),
    "fx": (3, 4, 5),
    "cp": (6, 7, 8),
    "eq": (9, 10, 11),
    "gen": (12, 13, 14),
}

context_map = {
    "ir": 15,
    "fx": 16,
    "cp": 17,
    "eq": 18,
    "gen": 19,
}

def get_primary_labels(
    labels_dict: dict[str, float],
    primary_id2label_map: dict[str, str],
    threshold: float = 0.35,
) -> list[str]:
    """
    Convert multi-label predictions to primary categorical labels. This is a standalone
    version of the logic from the main `LabelMapper` class for use in notebooks.

    Returns list of labels with HIGHEST PRIORITY FIRST.

    Priority for primary label (optimized for detecting CURRENT derivative usage):
    1. Current hedge usage
    1.5. Inferred Current hedge usage (no time signal)
    2. Historical hedge usage
    3. Speculative hedge usage
    4. Current Warrant/Embedded
    5. Context with time indicators (soft hedges)
    6. Historical Warrant/Embedded or Speculative context
    7. Context-only mentions
    8. Irrelevant
    """
    all_labels = []  # (priority_rank, confidence, label_id)

    # === Identify active hedge types ===
    active_hedges = []
    for hedge_type in ["ir", "fx", "cp", "eq", "gen"]:
        context_score = labels_dict.get(hedge_type, 0)
        usage_score = labels_dict.get(f"{hedge_type}_use", 0)
        if context_score >= threshold or usage_score >= threshold:
            active_hedges.append({
                "type": hedge_type, "has_use": usage_score >= threshold,
                "context": context_score, "usage": usage_score,
            })

    # === Identify active time dimensions ===
    active_times = {}
    if labels_dict.get("curr", 0) >= threshold:
        active_times["curr"] = labels_dict.get("curr", 0)
    if labels_dict.get("hist", 0) >= threshold:
        active_times["hist"] = labels_dict.get("hist", 0)
    if labels_dict.get("spec", 0) >= threshold:
        active_times["spec"] = labels_dict.get("spec", 0)

    # === Build hedge labels (usage) ===
    any_use = any(h["has_use"] for h in active_hedges)
    for hedge in active_hedges:
        hedge_type = hedge["type"]
        resolved_type = hedge_type
        if hedge_type == "gen":
            best_specific = None
            best_score = 0
            for specific in ["ir", "fx", "cp", "eq"]:
                score = labels_dict.get(specific, 0) + labels_dict.get(f"{specific}_use", 0)
                if score > best_score and score >= (threshold * 0.7):
                    best_score, best_specific = score, specific
            if best_specific:
                resolved_type = best_specific

        # Add a small penalty to equity to deprioritize it vs other hedge types
        priority_penalty = 0.1 if resolved_type == "eq" else 0.0

        curr_id, hist_id, spec_id = hedge_map[resolved_type]

        if hedge["has_use"] and active_times:
            for time_dim, time_score in active_times.items():
                combined_score = hedge["usage"] * time_score
                if time_dim == "curr": all_labels.append((1, combined_score, curr_id))
                elif time_dim == "hist": all_labels.append((2, combined_score, hist_id))
                elif time_dim == "spec": all_labels.append((3 + priority_penalty, combined_score, spec_id))
        elif hedge["has_use"] and not active_times:
            all_labels.append((1.5 + priority_penalty, hedge["usage"], curr_id))
        elif not hedge["has_use"] and active_times and hedge["context"] >= threshold:
            for time_dim, time_score in active_times.items():
                combined_score = hedge["context"] * time_score
                if time_dim in ["curr", "hist"]:
                    all_labels.append((5 + priority_penalty, combined_score, curr_id if time_dim == "curr" else hist_id))
                elif time_dim == "spec":
                    all_labels.append((6 + priority_penalty, combined_score, spec_id))

    # === Warrant / Embedded ===
    warr_score = labels_dict.get("warr", 0)
    emb_score = labels_dict.get("emb", 0)
    if warr_score >= threshold:
        if "curr" in active_times: all_labels.append((4, warr_score * active_times["curr"], 20))
        else: all_labels.append((7, warr_score, 21))
    if emb_score >= threshold:
        if "curr" in active_times: all_labels.append((4, emb_score * active_times["curr"], 22))
        else: all_labels.append((7, emb_score, 23))

    # === Pure context-only mentions ===
    if not any_use:
        for hedge in active_hedges:
            if hedge["context"] >= threshold:
                resolved_type = hedge["type"]
                if hedge["type"] == "gen":
                    best_specific = None
                    best_score = 0
                    for specific in ["ir", "fx", "cp", "eq"]:
                        score = labels_dict.get(specific, 0)
                        if score > best_score and score >= (threshold * 0.7):
                            best_score, best_specific = score, specific
                    if best_specific:
                        resolved_type = best_specific
                # Add a small penalty to equity to deprioritize it
                priority_penalty = 0.1 if resolved_type == "eq" else 0.0
                all_labels.append((8 + priority_penalty, hedge["context"], context_map[resolved_type]))

    # === Irrelevant ===
    if labels_dict.get("irr", 0) >= threshold:
        all_labels.append((9, labels_dict.get("irr", 0), 24))

    # === Sort, Deduplicate, and Finalize ===
    all_labels.sort(key=lambda x: (x[0], -x[1]))
    final_labels = []
    seen_ids = set()
    for _, _, label_id in all_labels:
        if label_id not in seen_ids:
            final_labels.append(primary_id2label_map.get(str(label_id), "Unknown"))
            seen_ids.add(label_id)

    if not final_labels:
        return [primary_id2label_map.get("24", "Irrelevant Non-Hedge")]

    return final_labels


# --- Batch prediction ---
def predict_batch(sentences: list[str]):
    model.eval()
    inputs = tokenizer(sentences, return_tensors="pt", truncation=True, padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.sigmoid(logits.cpu())
        predictions = (probs >= 0.5).int().numpy()

    all_results = []
    for pred in predictions:
        prob_dict = {l: float(p) for l, p in zip(labels, probs[len(all_results)])}
        primary_labels = get_primary_labels(
            labels_dict=prob_dict, primary_id2label_map=primary_id2label
        )  # Pass primary_id2label explicitly
        all_results.append({"pred_vector": prob_dict, "primary_labels": primary_labels})

    return all_results


# %%
# --- Single string example ---
text = """"
<reportingYear>2001</reportingYear>
"""
result = predict_batch([text])[0]

print("--- Multi-Label Prediction ---")
print("Prediction Vector:", result["pred_vector"])
print("Primary Labels:", result["primary_labels"])

# %%
# Batch Prediction from Excel
### 1. Configuration
EVAL_FILE = "eval.xlsx"
OUTPUT_FILE = "output.xlsx"

# %%
### 2. Load Data
''' Run this cell once to load the evaluation data.'''
try:
    eval_df = pd.read_excel(EVAL_FILE)
    print(f"Successfully loaded {EVAL_FILE} with {len(eval_df)} rows.")
except FileNotFoundError:
    print(f"Error: The evaluation file '{EVAL_FILE}' was not found. Please make sure it exists.")
    eval_df = None
# %%
### 3. Set Batch and Execute
'''Set the `START_INDEX` and `BATCH_SIZE` and run this cell to process a batch.'''
if eval_df is not None:
    START_INDEX = 0
    BATCH_SIZE = 100

    # Select batch
    batch_df = eval_df.iloc[START_INDEX : START_INDEX + BATCH_SIZE]

    # Get predictions
    if not batch_df.empty:
        predictions = predict_batch(batch_df['sentence'].tolist())

        # Add predictions to dataframe
        batch_df[['predicted_labels', 'primary_label']] = predictions
        batch_df['predicted_labels'] = batch_df['predicted_labels'].apply(json.dumps)

        # Save to output file
        batch_df.to_excel(OUTPUT_FILE, index=False)

        print(f"Batch prediction complete. {len(batch_df)} rows processed. Results saved to {OUTPUT_FILE}")
    else:
        print("The specified batch is empty. Nothing to process.")
else:
    print("Cannot run batch prediction because the evaluation data failed to load.")
