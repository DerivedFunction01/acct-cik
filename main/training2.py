"""
Simplified Generative Model Training Script with Unsloth
Single JSON config file with auto-generation
"""

import json
import math
import multiprocessing
from pathlib import Path
from typing import Tuple

from psutil import virtual_memory

# Dynamic Unsloth import with fallback
try:
    import unsloth
    from unsloth import FastLanguageModel

    USE_UNSLOTH = True
    print("✅ Unsloth found. Using Unsloth for model loading.")
except ImportError:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    USE_UNSLOTH = False
    print("⚠️ Unsloth not found. Falling back to standard Hugging Face transformers.")

from datasets import load_dataset
from huggingface_hub import login
import torch
from trl import SFTTrainer
from transformers import TrainingArguments

# ============================================================================
# CONFIGURATION MANAGEMENT
# ============================================================================

CONFIG_FILE = Path(".training_config.json")
IS_AUTHENTICATED = False

def create_default_config() -> dict:
    """Creates default configuration."""
    config = {
        "model_user": "DerivedFunction",
        "hf_token_path": "hf_token",
        "training_profile": {
            "r": 64,
            "lora_alpha": 128,
            "batch_size": 1,
            "gradient_accumulation": 8,
            "max_seq_length": 32768,
            "load_in_4bit": True,
        },
        "all_target_modules": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        "model_names": [
            "unsloth/Qwen3-1.7B-unsloth-bnb-4bit",
            "unsloth/Qwen3-1.7B",
            "unsloth/Qwen3-0.6B",
            "unsloth/Qwen3-4B-Thinking-2507",
            "unsloth/Qwen3-4B-unsloth-bnb-4bit",
        ],
        "datasets": [
            {"name": "DerivedFunction/Finance-50K", "is_hf": True},
        ],
    }
    return config


def load_config() -> dict:
    """Loads config from JSON or creates default."""
    if CONFIG_FILE.exists():
        print(f"📖 Loading configuration from {CONFIG_FILE}...")
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            print(f"✅ Configuration loaded successfully.")
            return config
        except Exception as e:
            print(f"⚠️ Error reading config: {e}. Creating new config...")

    print("Creating default configuration...")
    config = create_default_config()
    save_config(config)
    return config


def save_config(config: dict) -> None:
    """Saves configuration to JSON file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"✅ Configuration saved to {CONFIG_FILE}")


# automatically create the config file if it doesn't exist
if not CONFIG_FILE.exists():
    config = create_default_config()
    save_config(config)

# ============================================================================
# TRAINING
# ============================================================================


def run_training(
    profile: dict,
    model_name: str,
    data_path: str,
    new_model_name: str,
    target_modules: list,
    num_epochs: int = 1,
    is_hf_dataset: bool = False,
    dataset_shard_index: int = 0,
    dataset_num_shards: int = 1,
) -> None:
    """Main function to run the training process with Unsloth optimization."""
    print(
        f"\n--- Starting Training with {'Unsloth' if USE_UNSLOTH else 'Hugging Face'} ---"
    )
    print(f"  - Base Model: {model_name}")
    print(f"  - Data: {data_path}")
    print(f"  - Output Model: {new_model_name}")
    print(f"  - Epochs: {num_epochs}")
    print(f"  - LoRA modules: {target_modules}")

    # --- Load Model ---
    print("\n--- Initializing Model and Tokenizer ---")
    try:
        if USE_UNSLOTH:
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=model_name,
                max_seq_length=profile["max_seq_length"],
                load_in_4bit=profile["load_in_4bit"],
            )
        else:
            quantization_config = None
            if profile["load_in_4bit"]:
                quantization_config = BitsAndBytesConfig(load_in_4bit=True)

            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=quantization_config,
                dtype=torch.float16,
            )
            tokenizer = AutoTokenizer.from_pretrained(model_name)
    except Exception as e:
        print(f"❌ FAILED TO LOAD MODEL: {e}")
        return

    # --- Load and preprocess data ---
    print("\n--- Loading and Preprocessing Data ---")
    try:
        if is_hf_dataset:
            dataset = load_dataset(data_path, split="train")
        else:
            dataset = load_dataset("parquet", data_files=data_path, split="train")

        if dataset_num_shards > 1:
            print(f"Applying shard: {dataset_shard_index + 1} of {dataset_num_shards}")
            dataset = dataset.shard(
                num_shards=dataset_num_shards, index=dataset_shard_index
            )

        def format_with_chat_template(sample: dict) -> dict:
            """Format sample using tokenizer's chat template."""
            system_msg = sample.get("system") or ""
            user_msg = sample.get("user") or ""
            think_msg = sample.get("think") or ""
            assistant_msg = sample.get("assistant") or ""

            messages = []
            if system_msg:
                messages.append({"role": "system", "content": system_msg})
            messages.append({"role": "user", "content": user_msg})

            think_block = (
                f"<think>\n{think_msg.strip()}\n</think>\n\n" if think_msg else ""
            )
            assistant_content = f"{think_block}{assistant_msg}"
            messages.append({"role": "assistant", "content": assistant_content})

            return {
                "text": tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
            }

        dataset = dataset.map(
            format_with_chat_template, remove_columns=dataset.column_names
        )
        dataset = dataset.train_test_split(test_size=0.1)
        train_dataset = dataset["train"]
        eval_dataset = dataset["test"]

        print(f"✅ Data loaded. Train: {len(train_dataset)}, Eval: {len(eval_dataset)}")
    except Exception as e:
        print(f"❌ Failed to load data: {e}")
        return

    # --- Apply LoRA ---
    if hasattr(model, "peft_config"):
        print("Model already has LoRA adapters. Continuing training.")
    else:
        print("Adding new LoRA adapters for fine-tuning...")
        if USE_UNSLOTH:
            model = FastLanguageModel.get_peft_model(
                model,
                r=profile["r"],
                target_modules=target_modules,
                lora_alpha=profile["lora_alpha"],
                lora_dropout=0,
                bias="none",
                use_gradient_checkpointing="unsloth",
                random_state=3407,
                use_rslora=False,
                loftq_config=None,
            )

    # --- Dynamic Evaluation Steps ---
    num_train_samples = len(train_dataset)
    steps_per_epoch = math.ceil(
        num_train_samples / (profile["batch_size"] * profile["gradient_accumulation"])
    )
    eval_steps = max(100, steps_per_epoch // 2)
    print(f"📊 Evaluation frequency: every {eval_steps} steps")

    # --- Training Arguments ---
    training_args = TrainingArguments(
        output_dir=new_model_name,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=profile["batch_size"],
        per_device_eval_batch_size=profile["batch_size"],
        gradient_accumulation_steps=profile["gradient_accumulation"],
        warmup_steps=50,
        learning_rate=2e-4,
        max_grad_norm=0.3,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=3407,
        save_strategy="steps",
        save_steps=eval_steps,
        save_total_limit=2,
        load_best_model_at_end=True,
        eval_strategy="steps",
        eval_steps=eval_steps,
        push_to_hub=IS_AUTHENTICATED,
        report_to="tensorboard",
    )

    # --- Post-init cleanup ---
    if hasattr(model, "config"):
        config_dict = vars(model.config).copy()
        for key, value in config_dict.items():
            if callable(value) and not isinstance(value, type):
                try:
                    delattr(model.config, key)
                except:
                    pass

    # --- Initialize SFTTrainer ---
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=profile["max_seq_length"],
        dataset_num_proc=multiprocessing.cpu_count(),
        packing=False,
        args=training_args,
    )

    # --- Train and Save ---
    print(f"\nStarting training for {num_epochs} epochs...")
    if USE_UNSLOTH:
        print("🚀 Unsloth provides 2-5x faster training and 60% less memory usage!")

    try:
        checkpoint_exists = (
            input("Resume from checkpoint? [y/N]: ").strip().lower() == "y"
        )
        trainer_stats = trainer.train(resume_from_checkpoint=checkpoint_exists)
    except Exception as e:
        print(f"Training error: {e}. Retrying without checkpoint...")
        trainer_stats = trainer.train()

    print(f"\n--- Training Complete ---")
    print(f"Training time: {trainer_stats.metrics['train_runtime']:.2f} seconds")
    print(f"Samples/second: {trainer_stats.metrics['train_samples_per_second']:.2f}")

    # --- Saving LoRA Adapters ---
    print(f"\n--- Saving LoRA Adapters ---")
    adapter_save_path = f"{new_model_name}_lora"
    model.save_pretrained(adapter_save_path)
    tokenizer.save_pretrained(adapter_save_path)
    print(f"✅ LoRA adapters saved to '{adapter_save_path}'")

    if IS_AUTHENTICATED:
        push_to_hub = (
            input("Push LoRA adapter to Hugging Face Hub? [y/N]: ").strip().lower()
            == "y"
        )
        if push_to_hub:
            print(f"🚀 Pushing to Hugging Face Hub...")
            model.push_to_hub(adapter_save_path)
            print("✅ Successfully pushed adapter to Hub.")


def huggingface_auth() -> None:
    """Handles Hugging Face authentication."""
    global IS_AUTHENTICATED
    config = load_config()
    token_path = Path(config["hf_token_path"])

    if token_path.exists():
        print("Found saved Hugging Face token.")
        try:
            login(token=token_path.read_text().strip())
            IS_AUTHENTICATED = True
            print("✅ Authenticated with Hugging Face.")
            return
        except Exception as e:
            print(f"⚠️ Authentication failed: {e}")

    print(
        "\nPaste your Hugging Face token (get one from https://huggingface.co/settings/tokens)"
    )
    token = input("HF Token (or press Enter to skip): ").strip()

    if not token:
        print("Skipping authentication.")
        IS_AUTHENTICATED = False
        return

    try:
        login(token=token)
        IS_AUTHENTICATED = True
        print("✅ Authenticated with Hugging Face.")
        token_path.write_text(token)
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        IS_AUTHENTICATED = False


# ============================================================================
# MAIN MENU
# ============================================================================

if __name__ == "__main__":
    config = load_config()
    huggingface_auth()

    try:
        while True:
            print("\n" + "=" * 60)
            print("🚀 Generative Model Training (Unsloth Optimized)")
            print("=" * 60)
            print("1. Fine-tune a base model")
            print("2. Hugging Face login")
            print("3. Edit configuration")
            print("4. Exit")
            choice = input("> ").strip()

            if choice == "1":
                print("\n--- Step 1: Select Base Model ---")
                for i, name in enumerate(config["model_names"], 1):
                    print(f"  [{i}] {name}")
                print("  [c] Custom model from Hugging Face")

                model_choice = input("Enter model (e.g., 1, c): ").strip()
                if model_choice.isdigit() and 0 <= int(model_choice) - 1 < len(
                    config["model_names"]
                ):
                    base_model_name = config["model_names"][int(model_choice) - 1]
                elif model_choice.lower() == "c":
                    base_model_name = input("Enter custom model name/path: ").strip()
                else:
                    print("❌ Invalid choice.")
                    continue

                print("\n--- Step 2: Select Dataset ---")
                for i, ds in enumerate(config["datasets"], 1):
                    source = "Hugging Face" if ds["is_hf"] else "Local"
                    print(f"  [{i}] {ds['name']} ({source})")
                print("  [c] Custom local dataset (.parquet)")

                data_choice = input("Enter dataset: ").strip()
                if data_choice.isdigit() and 0 <= int(data_choice) - 1 < len(
                    config["datasets"]
                ):
                    ds = config["datasets"][int(data_choice) - 1]
                    data_path, is_hf_dataset = ds["name"], ds["is_hf"]
                elif data_choice.lower() == "c":
                    data_path = input("Path to .parquet file: ").strip()
                    is_hf_dataset = False
                else:
                    print("❌ Invalid choice.")
                    continue

                print("\n--- Step 3: Configure Training ---")
                num_epochs = int(input("Number of epochs [default: 1]: ") or 1)
                new_model_name = input("Output model name: ").strip()

                if not new_model_name:
                    new_model_name = base_model_name.split("/")[-1]

                use_sharding = (
                    input("Use dataset sharding? [y/N]: ").strip().lower() == "y"
                )
                num_shards = 1
                shard_index = 0

                if use_sharding:
                    num_shards = int(input("Enter total number of shards: ") or 1)
                    shard_index = int(
                        input(f"Enter shard index (0 to {num_shards - 1}): ") or 0
                    )
                    # Ask for the epoch number
                    num_epochs = shard_index + 1 if input(f"Resume from shard epoch [default: {shard_index + 1}] [y/N]: ").strip().lower() != "y" else num_epochs
                run_training(
                    profile=config["training_profile"],
                    model_name=base_model_name,
                    data_path=data_path,
                    new_model_name=new_model_name,
                    target_modules=config["all_target_modules"],
                    num_epochs=num_epochs,
                    is_hf_dataset=is_hf_dataset,
                    dataset_num_shards=num_shards,
                    dataset_shard_index=shard_index,
                )

            elif choice == "2":
                huggingface_auth()
            elif choice == "3":
                print(f"📝 Open {CONFIG_FILE} to edit configuration.")
                print("Changes will be loaded on next startup.")
            elif choice == "4":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice.")
    except KeyboardInterrupt:
        print("\n👋 Exiting.")
