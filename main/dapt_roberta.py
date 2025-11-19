# =============================================================================
# DOMAIN-ADAPTIVE PRE-TRAINING (DAPT) SCRIPT FOR ROBERTA
# =============================================================================
# This script performs Domain-Adaptive Pre-Training on a RoBERTa-base model
# using a custom text corpus. It is designed to take the output from
# `create_hf_dataset.py` (a Parquet file with a 'text' column) and continue
# pre-training the model on that domain-specific data.
#
# Workflow:
# 1. Loads a Parquet dataset.
# 2. Tokenizes the text and chunks it into blocks of a specified size.
# 3. Uses a `DataCollatorForLanguageModeling` to automatically handle the
#    Masked Language Modeling (MLM) objective.
# 4. Initializes the `Trainer` with the model, data, and training arguments.
# 5. Runs the training and saves the adapted model to a specified directory.
#
# Example Usage:
# python dapt_roberta.py \
#   --dataset_path training_data.parquet \
#   --output_dir roberta-base-finance-dapt \
#   --num_train_epochs 3
# =============================================================================

import logging
from pathlib import Path
import json

from datasets import load_dataset
from transformers import (
    AutoModelForMaskedLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)
from types import SimpleNamespace

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_FILE = ".roberta.json"

from huggingface_hub import login

# Read from the hf_token file
with open("hf_token", "r") as f:
    token = f.read().strip()
    login(token=token)

def run_dapt(args):
    """Main function to run Domain-Adaptive Pre-Training."""

    # 1. Load Tokenizer and Model
    logger.info(f"Loading base model and tokenizer: {args.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForMaskedLM.from_pretrained(args.model_name)

    # 2. Load and Prepare Dataset
    logger.info(f"Loading dataset from: {args.dataset_path}")
    if not Path(args.dataset_path).exists():
        logger.error(f"Dataset file not found at {args.dataset_path}")
        raise FileNotFoundError(f"Dataset file not found at {args.dataset_path}")

    dataset = load_dataset("parquet", data_files=args.dataset_path, split="train")
    logger.info(f"Dataset loaded with {len(dataset):,} rows.")

    # Tokenize the dataset
    def tokenize_function(examples):
        return tokenizer(examples["text"], return_special_tokens_mask=True)

    tokenized_dataset = dataset.map(
        tokenize_function,
        batched=True,
        num_proc=args.preprocessing_workers,
        remove_columns=["text"],
    )

    # Chunk tokenized examples into blocks of `block_size`
    block_size = tokenizer.model_max_length

    def group_texts(examples):
        # Concatenate all texts.
        concatenated_examples = {k: sum(examples[k], []) for k in examples.keys()}
        total_length = len(concatenated_examples[list(examples.keys())[0]])
        # We drop the small remainder, we could add padding if the model supported it
        total_length = (total_length // block_size) * block_size
        # Split by chunks of max_len.
        result = {
            k: [t[i : i + block_size] for i in range(0, total_length, block_size)]
            for k, t in concatenated_examples.items()
        }
        return result

    logger.info(f"Grouping texts into blocks of size {block_size}...")
    lm_dataset = tokenized_dataset.map(
        group_texts,
        batched=True,
        num_proc=args.preprocessing_workers,
    )
    logger.info(f"Created {len(lm_dataset):,} blocks for training.")

    # 3. Setup Data Collator for MLM
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer, mlm_probability=args.mlm_probability
    )

    # 4. Define Training Arguments
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        overwrite_output_dir=True,
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.batch_size,
        save_steps=100,
        save_total_limit=2,
        prediction_loss_only=True,
        logging_steps=10,
        fp16=True,  # Use mixed-precision training if a GPU is available
        report_to="tensorboard",
        push_to_hub=args.push_to_hub,
        hub_model_id=args.hub_model_id,
    )

    # 5. Initialize Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        data_collator=data_collator,
        train_dataset=lm_dataset,
    )

    # 6. Run Training
    logger.info("🚀 Starting Domain-Adaptive Pre-Training...")
    trainer.train(
        resume_from_checkpoint=args.resume_from_checkpoint,
    )

    # 7. Save the final model and push to hub if requested
    if args.push_to_hub:
        logger.info(f"✅ Training complete. Pushing model to Hub: {args.hub_model_id}")
        # The trainer.train() call automatically pushes the model when push_to_hub=True
    else:
        logger.info(f"✅ Training complete. Saving model to {args.output_dir}")
        trainer.save_model(args.output_dir)
        tokenizer.save_pretrained(args.output_dir)
    logger.info("✨ All done!")


def load_config():
    """Loads config from JSON or creates a default one."""
    if Path(CONFIG_FILE).exists():
        logger.info(f"Loading configuration from {CONFIG_FILE}")
        with open(CONFIG_FILE, "r") as f:
            config_dict = json.load(f)
        return config_dict
    else:
        logger.info(f"Configuration file not found. Creating default {CONFIG_FILE}")
        default_config = {
            "dataset_path": "training_data.parquet",
            "model_name": "roberta-base",
            "output_dir": "roberta-base",
            "num_train_epochs": 3,
            "batch_size": 16,
            "mlm_probability": 0.15,
            "preprocessing_workers": 4,
            "push_to_hub": True,
            "hub_model_id": "DerivedFunction/roberta-base",
            "resume_from_checkpoint": True,
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        logger.info(f"Default configuration created. Please edit '{CONFIG_FILE}' and run the script again.")
        return None


if __name__ == "__main__":
    config_dict = load_config()

    if config_dict:
        # Convert dictionary to a SimpleNamespace to allow attribute access (e.g., args.model_name)
        # This keeps the run_dapt function signature unchanged.
        args = SimpleNamespace(**config_dict)
        
        # Ensure hub_model_id is set correctly if pushing to hub
        if args.push_to_hub and not args.hub_model_id:
            args.hub_model_id = args.output_dir
            
        run_dapt(args)
