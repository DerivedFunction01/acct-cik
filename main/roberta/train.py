# =============================================================================
# DOMAIN-ADAPTIVE PRE-TRAINING (DAPT) SCRIPT FOR ROBERTA
# Supports: MLM-only or Supervised Classification Fine-Tuning (with domain labels)
# =============================================================================

import logging
from pathlib import Path
import json
from types import SimpleNamespace

from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForMaskedLM,
    AutoModelForSequenceClassification,
    DataCollatorForLanguageModeling,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)
from huggingface_hub import login

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_FILE = ".roberta.json"


# === Login to Hugging Face Hub (if token exists) ===
if Path("hf_token").exists():
    with open("hf_token", "r") as f:
        token = f.read().strip()
    login(token=token)
    logger.info("Logged in to Hugging Face Hub")
else:
    logger.info("No hf_token found. Proceeding without push capability.")


def create_label_mapping(dataset, label_column):
    """Create label2id and id2label from string labels."""
    unique_labels = sorted(dataset.unique(label_column))
    label2id = {label: idx for idx, label in enumerate(unique_labels)}
    id2label = {idx: label for label, idx in label2id.items()}
    logger.info(f"Found {len(unique_labels)} unique labels: {unique_labels}")
    return label2id, id2label


def load_config():
    """Load config from JSON or create default."""
    config_path = Path(CONFIG_FILE)
    if config_path.exists():
        logger.info(f"Loading configuration from {CONFIG_FILE}")
        with open(config_path, "r") as f:
            return json.load(f)
    else:
        logger.info(f"Creating default configuration: {CONFIG_FILE}")
        default_config = {
            "dataset_path": "training_data.parquet",
            "model_name": "roberta-base",
            "output_dir": "roberta-domain-adapted",
            "num_train_epochs": 3,
            "batch_size": 16,
            "gradient_accumulation_steps": 1,
            "learning_rate": 5e-5,
            "weight_decay": 0.01,
            "warmup_ratio": 0.1,
            "mlm_probability": 0.15,
            "preprocessing_workers": 8,
            "eval_split_ratio": 0.05,
            "push_to_hub": False,
            "hub_model_id": None,
            "resume_from_checkpoint": None,
            "classification_column": None,  # Set to e.g. "label" to enable classification mode
        }
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=4)
        logger.info(f"Default config saved to {CONFIG_FILE}. Please edit and rerun.")
        return None


def main():
    config_dict = load_config()
    if not config_dict:
        return

    args = SimpleNamespace(**config_dict)
    classification_column = args.classification_column
    is_classification = classification_column is not None

    # === Load tokenizer ===
    logger.info(f"Loading tokenizer: {args.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)

    # === Load dataset ===
    if not Path(args.dataset_path).exists():
        raise FileNotFoundError(f"Dataset not found: {args.dataset_path}")

    dataset = load_dataset("parquet", data_files=args.dataset_path)["train"]
    logger.info(f"Loaded dataset with {len(dataset):,} examples")

    # === Optional train/eval split ===
    eval_dataset = None
    if args.eval_split_ratio and args.eval_split_ratio > 0:
        split = dataset.train_test_split(test_size=args.eval_split_ratio, seed=42)
        dataset = split["train"]
        eval_dataset = split["test"]
        logger.info(f"Split: {len(dataset):,} train | {len(eval_dataset):,} eval")

    # === Classification mode setup ===
    label2id = id2label = None
    if is_classification:
        logger.info(
            f"Classification mode enabled using column: '{classification_column}'"
        )
        label2id, id2label = create_label_mapping(dataset, classification_column)

        def map_labels(example):
            example["labels"] = label2id[example[classification_column]]
            return example

        dataset = dataset.map(map_labels, remove_columns=[classification_column])
        if eval_dataset:
            eval_dataset = eval_dataset.map(
                map_labels, remove_columns=[classification_column]
            )

    # === Tokenization function ===
    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"],
            truncation=True,
            max_length=512,
            padding=False,  # Let collator handle padding
        )
        # In MLM mode, we need special tokens mask
        if not is_classification:
            tokenized["special_tokens_mask"] = tokenized.get(
                "special_tokens_mask", None
            )
        return tokenized

    # Tokenize train
    tokenized_train = dataset.map(
        tokenize_function,
        batched=True,
        num_proc=args.preprocessing_workers,
        remove_columns=["text"],
    )

    # Tokenize eval (if exists)
    tokenized_eval = None
    if eval_dataset is not None:
        tokenized_eval = eval_dataset.map(
            tokenize_function,
            batched=True,
            num_proc=args.preprocessing_workers,
            remove_columns=["text"],
        )

    # === Block grouping for MLM (only) ===
    if not is_classification:
        block_size = 512

        def group_texts(examples):
            concatenated = {k: sum(examples[k], []) for k in examples.keys()}
            total_length = len(concatenated[list(examples.keys())[0]])
            total_length = (total_length // block_size) * block_size
            result = {
                k: [t[i : i + block_size] for i in range(0, total_length, block_size)]
                for k, t in concatenated.items()
            }
            result["labels"] = result["input_ids"].copy()
            return result

        logger.info("Grouping texts for MLM (block_size=512)...")
        tokenized_train = tokenized_train.map(
            group_texts,
            batched=True,
            num_proc=args.preprocessing_workers,
        )
        if tokenized_eval:
            tokenized_eval = tokenized_eval.map(
                group_texts,
                batched=True,
                num_proc=args.preprocessing_workers,
            )

    # === Data collator ===
    if is_classification:
        data_collator = DataCollatorWithPadding(tokenizer=tokenizer)
    else:
        data_collator = DataCollatorForLanguageModeling(
            tokenizer=tokenizer, mlm_probability=args.mlm_probability
        )

    # === Load model ===
    if is_classification:
        model = AutoModelForSequenceClassification.from_pretrained(
            args.model_name,
            num_labels=len(label2id),
            label2id=label2id,
            id2label=id2label,
        )
        logger.info(f"Loaded SequenceClassification model with {len(label2id)} labels")
    else:
        model = AutoModelForMaskedLM.from_pretrained(args.model_name)
        logger.info("Loaded MaskedLM model for unsupervised DAPT")

    # === Training arguments ===
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        overwrite_output_dir=True,
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        gradient_accumulation_steps=getattr(args, "gradient_accumulation_steps", 1),
        learning_rate=getattr(args, "learning_rate", 5e-5),
        weight_decay=getattr(args, "weight_decay", 0.01),
        warmup_ratio=getattr(args, "warmup_ratio", 0.1),
        logging_steps=10,
        eval_strategy="steps" if eval_dataset else "no",
        eval_steps=500,
        save_steps=1000,
        save_total_limit=3,
        prediction_loss_only=False,
        fp16=True,
        dataloader_num_workers=4,
        report_to="tensorboard",
        load_best_model_at_end=True if eval_dataset else False,
        metric_for_best_model="eval_loss" if eval_dataset else None,
        greater_is_better=False,
        remove_unused_columns=False,  # CRITICAL for classification mode
        push_to_hub=args.push_to_hub,
        hub_model_id=args.hub_model_id or args.output_dir,
        hub_strategy="end",
        resume_from_checkpoint=args.resume_from_checkpoint,
    )

    # === Trainer ===
    trainer = Trainer(
        model=model,
        args=training_args,
        data_collator=data_collator,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_eval,
    )

    # === Train ===
    logger.info("Starting training...")
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    # === Save final model ===
    logger.info(f"Saving model to {args.output_dir}")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    if is_classification:
        label_path = Path(args.output_dir) / "label_mapping.json"
        with open(label_path, "w") as f:
            json.dump({"label2id": label2id, "id2label": id2label}, f, indent=4)
        logger.info(f"Label mapping saved to {label_path}")

    if args.push_to_hub:
        logger.info(f"Pushing model to Hub: {training_args.hub_model_id}")
        trainer.push_to_hub()

    logger.info("Domain-Adaptive Pre-Training completed successfully!")


if __name__ == "__main__":
    main()
