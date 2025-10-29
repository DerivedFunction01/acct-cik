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
from huggingface_hub import login
import numpy as np
from sklearn.metrics import f1_score, roc_auc_score, accuracy_score
from transformers import EvalPrediction
import json
from pathlib import Path

config = {
    "EXCEL_PATH": "./training_data.xlsx",
    "MODEL_PATH": "derivative-classifier",
    "MODEL_USER": "DerivedFunction",
    "HF_TOKEN": "hf_token"
}
IS_AUTHENTICATED = False

# %%
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
    "term",
    "spec",
    "warr",
    "emb",
    "irr",
]
id2label = {i: label for i, label in enumerate(labels)}
label2id = {label: i for i, label in enumerate(labels)}

# %%

def run_training(model_name="ProsusAI/finbert", num_epochs=4, batch_size=8):
    """Main function to run the training process with given parameters."""
    MODEL_NAME = model_name
    RESUME_FROM_CHECKPOINT = Path(config['MODEL_PATH']).exists()
    print(f"\n--- Starting Training ---")
    print(f"Model: {MODEL_NAME}, Epochs: {num_epochs}, Batch Size: {batch_size}")

    # --- Load and preprocess data ---
    print("\n--- Loading and Preprocessing Data ---")
    df = pd.read_excel(config['EXCEL_PATH'])

    # Convert the Excel file to a parquet file with timestamp in *_MO_DD_YY_HHMM.parquet
    timestamp = pd.Timestamp.now().strftime("%m_%d_%y_%H%M")
    parquet_filename = config["EXCEL_PATH"].replace(".xlsx", f"_{timestamp}.parquet")
    df.to_parquet(parquet_filename, index=False)
    print(f"Data saved to {parquet_filename}")
    df.dropna(subset=["sentence", "labels"], inplace=True)

    def format_labels(row):
        label_dict = json.loads(row["labels"])
        return [label_dict.get(label, 0) for label in labels]

    df["labels"] = df.apply(format_labels, axis=1)
    train_df, val_df = train_test_split(df, test_size=0.2, random_state=42)
    train_dataset = Dataset.from_pandas(train_df)
    val_dataset = Dataset.from_pandas(val_df)

    # --- Tokenization ---
    print("Tokenizing dataset...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    def tokenize_function(examples):
        tokenized_input = tokenizer(examples["sentence"], truncation=True, max_length=512)
        tokenized_input["labels"] = [[float(x) for x in label] for label in examples["labels"]]
        return tokenized_input

    tokenized_train_dataset = train_dataset.map(tokenize_function, batched=True)
    tokenized_val_dataset = val_dataset.map(tokenize_function, batched=True)
    tokenized_train_dataset.set_format("torch", columns=["input_ids", "attention_mask", "labels"])
    tokenized_val_dataset.set_format("torch", columns=["input_ids", "attention_mask", "labels"])
    print("Tokenization complete.")

    # --- Custom Data Collator ---
    class CustomDataCollatorWithPadding(DataCollatorWithPadding):
        def __call__(self, features):
            batch = super().__call__(features)
            # batch["labels"] = torch.stack([torch.tensor(f["labels"], dtype=torch.float32) for f in features])
            batch["labels"] = torch.stack([f["labels"].clone().detach() for f in features])
            return batch

    collator = CustomDataCollatorWithPadding(tokenizer=tokenizer)

    # --- Metrics ---
    def multi_label_metrics(predictions, labels, threshold=0.5):
        sigmoid = torch.nn.Sigmoid()
        probs = sigmoid(torch.Tensor(predictions))
        y_pred = np.zeros(probs.shape)
        y_pred[np.where(probs >= threshold)] = 1
        y_true = np.zeros(labels.shape)
        y_true[np.where(labels >= threshold)] = 1
        f1_micro_average = f1_score(y_true=y_true, y_pred=y_pred, average="micro")
        roc_auc = roc_auc_score(y_true, probs, average="micro")
        accuracy = accuracy_score(y_true, y_pred)
        return {"f1": f1_micro_average, "roc_auc": roc_auc, "accuracy": accuracy}

    def compute_metrics(p: EvalPrediction):
        preds = p.predictions[0] if isinstance(p.predictions, tuple) else p.predictions
        return multi_label_metrics(predictions=preds, labels=p.label_ids)

    # --- Model and Training ---
    print("\n--- Initializing Model and Trainer ---")
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

    training_args = TrainingArguments(
        output_dir=config['MODEL_PATH'],
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=1,
        warmup_steps=500,
        weight_decay=0.01,
        logging_dir="./logs",
        logging_steps=100,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train_dataset,
        eval_dataset=tokenized_val_dataset,
        compute_metrics=compute_metrics,
        data_collator=collator,
    )

    print(f"\nStarting training for {num_epochs} epochs with batch size {batch_size}...")
    try:
        trainer.train(resume_from_checkpoint=RESUME_FROM_CHECKPOINT)
    except:
        trainer.train() # Don't use checkpoint

    # --- Save the best model explicitly ---
    print("\n--- Saving final best model ---")
    trainer.save_model(config['MODEL_PATH'])

    # --- Save and Push to Hub ---
    push_to_hub = input("\nDo you want to push the final model to the Hugging Face Hub? (y/n): ")
    if push_to_hub.lower().strip() == 'y':
        print("Pushing model to the Hub...")
        trainer.push_to_hub(commit_message="End of training")
        print("Model pushed successfully!")
    else:
        print(f"Skipping push to Hub. The model is saved locally in the '{config['MODEL_PATH']}' directory.")

# %%

def run_training_interactive():
    """Handles the interactive prompts for training configuration."""
    print("\n--- Model Training Configuration ---")
    fine_tune_input = input("Fine-tune a new model from the Hub? (y/n) [default: y]: ").lower().strip()
    default_model = "ProsusAI/finbert"
    if fine_tune_input in ('y', ''):
        model_input = input(f"Enter model name to fine-tune [default: {default_model}]: ").strip()
        model_name = model_input if model_input else default_model
    else:
        model_name = f"{config['MODEL_USER']}/{config['MODEL_PATH']}"
        print(f"Using local model path: {model_name}")

    num_epochs = int(input("Enter number of training epochs [default: 4]: ") or 4)
    batch_size = int(input("Enter training batch size [default: 8]: ") or 8)
    run_training(model_name, num_epochs, batch_size)

# %%

def edit_config():
    """Allows interactive editing of the script's configuration."""
    global config
    while True:
        print("\n--- Edit Configuration ---")
        for i, (key, value) in enumerate(config.items(), 1):
            print(f"{i}. {key}: {value}")
        print("Enter a number to edit a value, or 'done' to return to the main menu.")

        choice = input("> ").strip().lower()
        if choice == 'done':
            break
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(config):
                key_to_edit = list(config.keys())[choice_idx]
                new_value = input(f"Enter new value for {key_to_edit}: ").strip()
                config[key_to_edit] = new_value
                print(f"Updated {key_to_edit} to '{new_value}'")
            else:
                print("Invalid number. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number or 'done'.")

# %%

def huggingface_auth():
    """Handles Hugging Face authentication."""
    global IS_AUTHENTICATED
    print("\nPlease paste your Hugging Face token below to log in.")
    print("The token will be visible as you paste it.")
    # See if "hf_token" file exists for asking for input
    if not IS_AUTHENTICATED and Path(config["HF_TOKEN"]).exists():
        token = Path(config["HF_TOKEN"]).read_text().strip()
    else:
        token = input("HF Token: ")
    try:
        login(token=token.strip())
        IS_AUTHENTICATED = True
        print("✅ Successfully authenticated with Hugging Face.")
        # Save the token to "hf_token" file
        with open(config["HF_TOKEN"], "w") as f:
            f.write(token)
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        IS_AUTHENTICATED = False

# %%


def upload_model():
    """Uploads a trained model from the local model path to the Hub."""
    if not IS_AUTHENTICATED:
        print("\n⚠️ Please authenticate with Hugging Face first (Option 3).")
        return

    import re

    output_dir = Path(config["MODEL_PATH"])
    if not output_dir.exists():
        print(
            f"\n❌ Model directory not found at '{output_dir}'. Please train a model first."
        )
        return

    # --- Find available checkpoints ---
    checkpoints = sorted(
        [p for p in output_dir.glob("checkpoint-*") if p.is_dir()],
        key=lambda p: int(re.search(r"(\d+)", str(p)).group(1)) if re.search(r"(\d+)", str(p)) else -1,
    )

    best_checkpoint_path, last_checkpoint_path = None, None

    # Find best checkpoint from trainer state
    # The best model is now saved at the root of the output directory after training completes.
    if (output_dir / "pytorch_model.bin").exists():
        best_checkpoint_path = output_dir

    # Find last checkpoint by step number
    if checkpoints:
        last_checkpoint_path = checkpoints[-1]

    if not checkpoints and not (output_dir / "pytorch_model.bin").exists():
        print(f"\n❌ No trained model or checkpoints found in '{output_dir}'.")
        return

    # --- Interactive Selection ---
    print("\n--- Select a Model to Upload ---")
    options = {}
    i = 1
    if best_checkpoint_path:
        print(f"{i}. Best Model: {best_checkpoint_path.name} (Recommended)")
        options[str(i)] = best_checkpoint_path
        i += 1
    if last_checkpoint_path:
        print(f"{i}. Last Checkpoint: {last_checkpoint_path.name}")
        options[str(i)] = last_checkpoint_path
        i += 1
    print(f"{i}. Enter a specific checkpoint number")
    options[str(i)] = "manual"

    choice = input("> ").strip()
    model_to_upload_path = options.get(choice)

    if model_to_upload_path == "manual":
        print(
            "\nAvailable checkpoint numbers:",
            ", ".join([re.search(r"(\d+)", c.name).group(1) for c in checkpoints]),
        )
        chkpt_num = input("Enter checkpoint number: ").strip()
        model_to_upload_path = output_dir / f"checkpoint-{chkpt_num}"
        if not model_to_upload_path.exists():
            print(f"❌ Checkpoint '{model_to_upload_path.name}' not found.")
            return

    if not model_to_upload_path:
        print("❌ Invalid selection.")
        return

    print(f"\n--- Uploading Model from '{model_to_upload_path}' ---")
    commit_message = input("Enter a commit message for the upload: ")
    try:
        model = AutoModelForSequenceClassification.from_pretrained(model_to_upload_path)
        tokenizer = AutoTokenizer.from_pretrained(model_to_upload_path)

        repo_name = f"{config['MODEL_USER']}/{config['MODEL_PATH']}"
        model.push_to_hub(repo_name, commit_message=commit_message)
        tokenizer.push_to_hub(repo_name, commit_message=commit_message)
        print(f"✅ Model successfully pushed to {repo_name}")
    except Exception as e:
        print(f"❌ An error occurred during upload: {e}")

# %%

if __name__ == "__main__":
    # --- Terminal Mode: Show the interactive menu ---
    while True:
        print("\n--- Main Menu ---")
        print("1. Train Model")
        print("2. Edit Configuration")
        print("3. Hugging Face Login")
        print("4. Upload Model to Hub")
        print("5. Exit")
        choice = input("> ").strip()

        if choice == '1':
            run_training_interactive()
        elif choice == '2':
            edit_config()
        elif choice == '3':
            huggingface_auth()
        elif choice == '4':
            upload_model()
        elif choice == '5':
            print("Exiting.")
            break
        else:
            print("Invalid choice, please try again.")

# %%
