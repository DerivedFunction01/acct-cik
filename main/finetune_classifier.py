#%%
# =============================================================================
# SENTENCE CLASSIFIER FINE-TUNING SCRIPT
# =============================================================================
# This script fine-tunes a DistilBERT model for classifying derivative-related
# sentences into five categories: current, historical, terminated, speculative,
# and irrelevant.
#
# To run this, you'll need to install the required libraries:
# pip install transformers datasets scikit-learn torch
# =============================================================================

import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
)
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

# =============================================================================
# CONFIGURATION
# =============================================================================

# The base model to fine-tune. DistilBERT is a great choice for efficiency.
BASE_MODEL = "distilbert-base-uncased"

# The directory where the final fine-tuned model will be saved.
OUTPUT_MODEL_DIR = "./fine-tuned-derivative-classifier"

# Define the labels for classification.
LABELS = ["current", "historical", "terminated", "speculative", "irrelevant"]

# =============================================================================
# DATA GENERATION (SYNTHETIC)
# =============================================================================

def generate_training_data():
    """
    Generates synthetic training data.
    *** REPLACE THIS with your actual data generator from old1/old2 ***
    The expected format is a list of tuples: (sentence, label_text).
    """
    print("🏭 Generating synthetic training data...")
    data = [
        # Current
        ("As of December 31, 2023, we held several interest rate swap agreements.", "current"),
        ("The company currently has foreign exchange forward contracts to hedge currency risk.", "current"),

        # Historical
        ("During 2022, the company entered into and settled commodity futures.", "historical"),
        ("In the prior year, all outstanding options were exercised or expired.", "historical"),

        # Terminated
        ("The cross-currency swap was terminated in the first quarter of 2023.", "terminated"),
        ("We unwound our portfolio of credit default swaps, resulting in a net gain.", "terminated"),

        # Speculative
        ("The company may use derivative instruments to manage future interest rate exposure.", "speculative"),
        ("We do not currently hold derivatives, but we may in the future.", "speculative"),

        # Irrelevant (Crucial for reducing false positives)
        ("The company's stock options for employees are detailed in Note 5.", "irrelevant"),
        ("Our compensation expense includes costs for share-based payments.", "irrelevant"),
        ("This report contains forward-looking statements about our business.", "irrelevant"),
    ]
    # For a real scenario, you would want hundreds or thousands of examples per category.
    # Let's duplicate the data to simulate a slightly larger dataset for this example.
    return data * 50

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def compute_metrics(pred):
    """Computes accuracy, precision, recall, and F1 for evaluation."""
    labels = pred.label_ids
    preds = np.argmax(pred.predictions, axis=1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average='weighted')
    acc = accuracy_score(labels, preds)
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall': recall
    }

# =============================================================================
# MAIN FINE-TUNING EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("="*80)
    print("🚀 Starting Classifier Fine-Tuning")
    print("="*80)

    # 1. Load and prepare data
    training_data = generate_training_data()
    
    # Create a mapping from label names to integer IDs and vice-versa
    label2id = {label: i for i, label in enumerate(LABELS)}
    id2label = {i: label for i, label in enumerate(LABELS)}

    # Convert to a dictionary format suitable for datasets.Dataset
    data_dict = {'text': [item[0] for item in training_data],
                 'label': [label2id[item[1]] for item in training_data]}

    # Create the Hugging Face Dataset
    dataset = Dataset.from_dict(data_dict)

    # Split into training and testing sets (e.g., 80% train, 20% test)
    dataset = dataset.train_test_split(test_size=0.2, shuffle=True, seed=42)
    train_dataset = dataset['train']
    eval_dataset = dataset['test']
    
    print(f"📚 Dataset prepared: {len(train_dataset)} training examples, {len(eval_dataset)} evaluation examples.")

    # 2. Load tokenizer and model
    print(f"🔄 Loading tokenizer and model for '{BASE_MODEL}'...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(LABELS),
        id2label=id2label,
        label2id=label2id
    )

    # 3. Tokenize the datasets
    def tokenize_function(examples):
        return tokenizer(examples["text"], padding="max_length", truncation=True)

    train_dataset = train_dataset.map(tokenize_function, batched=True)
    eval_dataset = eval_dataset.map(tokenize_function, batched=True)

    # 4. Set up Training Arguments
    training_args = TrainingArguments(
        output_dir=OUTPUT_MODEL_DIR,
        num_train_epochs=3,              # Number of times to iterate over the training data
        per_device_train_batch_size=16,  # Batch size for training
        per_device_eval_batch_size=16,   # Batch size for evaluation
        warmup_steps=500,                # Number of steps for learning rate warmup
        weight_decay=0.01,               # Strength of weight decay
        logging_dir='./logs',            # Directory for storing logs
        logging_steps=10,
        evaluation_strategy="epoch",     # Evaluate at the end of each epoch
        save_strategy="epoch",           # Save at the end of each epoch
        load_best_model_at_end=True,     # Load the best model found during training
    )

    # 5. Initialize the Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        compute_metrics=compute_metrics,
    )

    # 6. Start Fine-Tuning
    print("\n🤖 Starting model fine-tuning...")
    trainer.train()

    # 7. Save the final model and tokenizer
    print(f"\n💾 Saving fine-tuned model to '{OUTPUT_MODEL_DIR}'...")
    trainer.save_model(OUTPUT_MODEL_DIR)
    tokenizer.save_pretrained(OUTPUT_MODEL_DIR)

    print("\n✨ Fine-tuning complete!")
    print(f"You can now load your custom model from '{OUTPUT_MODEL_DIR}'.")
    print("="*80)