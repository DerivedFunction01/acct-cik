# %%
# %pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
# Also run: pip uninstall unsloth -y && pip install --upgrade --no-cache-dir "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"

import json
import random
import math
import sys
from pathlib import Path
import multiprocessing

import pandas as pd

from psutil import virtual_memory

# Dynamic Unsloth import with fallback
try:
    from unsloth import FastLanguageModel

    USE_UNSLOTH = True
    print("✅ Unsloth found. Using Unsloth for model loading.")
except ImportError:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    USE_UNSLOTH = False
    print("⚠️ Unsloth not found. Falling back to standard Hugging Face transformers.")
    
from datasets import load_dataset
from huggingface_hub import login
from trl import SFTTrainer
from transformers import TrainingArsguments

# %%
# --- CONFIGURATION ---
config = {
    "MODEL_USER": "DerivedFunction",
    "MODEL_NAMES": [
        "unsloth/Qwen3-1.7B-unsloth-bnb-4bit",
        "unsloth/Qwen3-4B-Thinking-2507",
        "DerivedFunction/Qwen3-1.7B-finance-base",
    ],
    "LORA_ADAPTERS": [],
    "DATASETS": [
        ("DerivedFunction/Derivatives-Finance-100K", True),
    ],
    "HF_TOKEN_PATH": "hf_token",
    "MAX_SEQ_LENGTH": 32768,
}
IS_AUTHENTICATED = False

# =============================================================================
# DYNAMIC CONFIGURATION PROFILES
# =============================================================================

TRAINING_PROFILES = {
    "1": {
        "name": "Max Performance (A100 40GB / H100)",
        "r": 256,
        "lora_alpha": 512,
        "batch_size": 6,
        "gradient_accumulation": 4,
        "max_seq_length": 32768,
        "load_in_4bit": True,
    },
    "2": {
        "name": "L4 / Pro (>= 20 GB)",
        "r": 256,
        "lora_alpha": 512,
        "batch_size": 4,
        "gradient_accumulation": 4,
        "max_seq_length": 32768,
        "load_in_4bit": True,
    },
    "3": {
        "name": "High VRAM / Colab (>= 12GB)",
        "r": 128,
        "lora_alpha": 256,
        "batch_size": 2,
        "gradient_accumulation": 4,
        "max_seq_length": 32768,
        "load_in_4bit": True,
    },
    "4": {
        "name": "Low VRAM (6-12GB)",
        "r": 64,
        "lora_alpha": 128,
        "batch_size": 1,
        "gradient_accumulation": 8,
        "max_seq_length": 32768,
        "load_in_4bit": True,
    },
    "5": {
        "name": "CPU / Low RAM (< 6GB)",
        "r": 32,
        "lora_alpha": 32,
        "batch_size": 1,
        "gradient_accumulation": 16,
        "max_seq_length": 32768,
        "load_in_4bit": True,
    },
}


def detect_hardware() -> tuple:
    """Detects GPU VRAM and system RAM to suggest a profile."""
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return "gpu", vram_gb
    else:
        ram_gb = virtual_memory().total / (1024**3)
        return "cpu", ram_gb


def get_target_modules(dataset_size: int) -> list:
    """
    Selects target modules for LoRA based on dataset size.
    Smaller datasets benefit from fewer trainable parameters to prevent overfitting.
    Larger datasets can utilize more modules for better fine-tuning.

    Dataset size ranges:
    - < 1K samples: minimal modules (attention layers only)
    - 1K - 10K samples: core modules (attention + gating)
    - 10K - 100K samples: standard modules (attention + feed-forward gating)
    - 100K+ samples: full modules (all attention + feed-forward)
    """
    if dataset_size < 1000:
        modules = ["q_proj", "v_proj"]
        print(
            f"📊 Small dataset ({dataset_size} samples). Using minimal LoRA modules: {modules}"
        )
    elif dataset_size < 10000:
        modules = ["q_proj", "k_proj", "v_proj", "o_proj"]
        print(
            f"📊 Medium dataset ({dataset_size} samples). Using core LoRA modules: {modules}"
        )
    elif dataset_size < 50000:
        modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj"]
        print(
            f"📊 Large dataset ({dataset_size} samples). Using standard LoRA modules: {modules}"
        )
    else:
        modules = [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]
        print(
            f"📊 Very large dataset ({dataset_size} samples). Using full LoRA modules: {modules}"
        )

    return modules


# %%


def run_training(
    profile: dict,
    model_name: str,
    data_path: str,
    new_model_name: str,
    num_epochs: int = 1,
    is_hf_dataset: bool = False,
    dataset_shard_index: int = 0,
    dataset_num_shards: int = 1,
    merge_at_end: bool = True,
) -> None:
    """Main function to run the training process with Unsloth optimization."""
    print(
        f"\n--- Starting Training with {'Unsloth' if USE_UNSLOTH else 'Hugging Face'} ---"
    )
    print(f"  - Profile: {profile['name']}")
    print(f"  - Base Model: {model_name}")
    print(f"  - Data: {data_path}")
    if dataset_num_shards > 1:
        print(f"  - Dataset Shard: {dataset_shard_index + 1} of {dataset_num_shards}")
    print(f"  - Output Model: {new_model_name}")
    print(f"  - Epochs: {num_epochs}")
    print(f"  - Merge Adapters at End: {'Yes' if merge_at_end else 'No'}")

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
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                load_in_4bit=profile["load_in_4bit"],
                torch_dtype=torch.float16,
            )
            tokenizer = AutoTokenizer.from_pretrained(model_name)

    except Exception as e:
        print(f"❌❌❌ FAILED TO LOAD MODEL ❌❌❌")
        print(f"Error loading '{model_name}': {e}")
        print(
            "If pulling from Hub, ensure the model ID is correct, you have access, and you are logged in."
        )
        return

    # --- Load and preprocess data ---
    print("\n--- Loading and Preprocessing Data ---")
    try:
        if is_hf_dataset:
            dataset = load_dataset(data_path, split="train")
        else:
            dataset = load_dataset("parquet", data_files=data_path, split="train")

        dataset_size = len(dataset)
        if dataset_num_shards > 1:
            print(
                f"Applying dataset shard: Using index {dataset_shard_index} of {dataset_num_shards} total shards."
            )
            dataset = dataset.shard(
                num_shards=dataset_num_shards, index=dataset_shard_index
            )

        def format_with_chat_template(sample: dict) -> dict:
            """Format sample using the tokenizer's chat template."""
            system_msg = sample.get("system") or ""
            user_msg = sample.get("user") or ""
            think_msg = sample.get("think") or ""
            assistant_msg = sample.get("assistant") or ""

            messages = []
            if system_msg:
                messages.append({"role": "system", "content": system_msg})
            messages.append({"role": "user", "content": user_msg})

            think_block = f"<think>\n{think_msg.strip()}\n</think>\n\n"
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

        print(
            f"Data loaded successfully. Training samples: {len(train_dataset)}, "
            f"Evaluation samples: {len(eval_dataset)}"
        )
    except Exception as e:
        print(f"❌ Failed to load data from {data_path}: {e}")
        return

    # --- Apply LoRA with Unsloth ---
    if hasattr(model, "peft_config"):
        print("Model already has LoRA adapters. Continuing training.")
    else:
        print(
            "Adding new LoRA adapters for fine-tuning..."
            if USE_UNSLOTH
            else "PEFT LoRA not available without Unsloth. Training all parameters."
        )
        if USE_UNSLOTH:
            model = FastLanguageModel.get_peft_model(
                model,
                r=profile["r"],
                target_modules=get_target_modules(dataset_size),
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
    if num_train_samples > 1000:
        steps_per_epoch = math.ceil(
            num_train_samples
            / (profile["batch_size"] * profile["gradient_accumulation"])
        )
        eval_steps = max(100, steps_per_epoch // 2)
    else:
        eval_steps = num_train_samples
    print(f"📊 Setting evaluation frequency to every {eval_steps} steps.")

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
        hub_model_id=f"{config['MODEL_USER']}/{new_model_name}",
    )

    # --- Post-init cleanup ---
    if hasattr(model, "config"):
        config_dict = vars(model.config).copy()
        for key, value in config_dict.items():
            if callable(value) and not isinstance(value, type):
                delattr(model.config, key)

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
        if checkpoint_exists:
            print("Checkpoint found. Resuming training from checkpoint...")
        trainer_stats = trainer.train(resume_from_checkpoint=checkpoint_exists)
    except Exception as e:
        print(f"Training failed: {e}. Trying to train without resuming.")
        trainer_stats = trainer.train()

    print("\n--- Training Statistics ---")
    print(f"Training time: {trainer_stats.metrics['train_runtime']:.2f} seconds")
    print(
        f"Samples per second: {trainer_stats.metrics['train_samples_per_second']:.2f}"
    )

    # --- Merge, Save, and Push ---
    print(f"\n--- Saving LoRA Adapters to '{new_model_name}_lora' ---")
    model.save_pretrained(f"{new_model_name}_lora")
    tokenizer.save_pretrained(f"{new_model_name}_lora")

    if merge_at_end:
        if hasattr(model, "merge_and_unload"):
            print("\n--- Merging LoRA adapters into the base model ---")
            model = model.merge_and_unload()

        print(f"\n--- Saving final merged model to '{new_model_name}' ---")
        trainer.model = model
        trainer.save_model(new_model_name)
        print(f"✅ Final merged model saved to '{new_model_name}'.")

    if training_args.push_to_hub:
        print(
            f"\nModel will be pushed to the Hub at '{training_args.hub_model_id}' by the Trainer."
        )
    else:
        print(
            f"Skipping push to Hub. The final model is saved locally in the '{new_model_name}' directory."
        )


def run_manual_test() -> None:
    """Allows for manual, interactive testing of the fine-tuned model."""
    print("\n--- Manual Model Test ---")

    print("Available models to test:")
    print("  --- Base/Merged Models ---")
    for i, name in enumerate(config["MODEL_NAMES"], 1):
        print(f"  [b{i}] {name}")
    print("  --- LoRA Adapters ---")
    for i, name in enumerate(config["LORA_ADAPTERS"], 1):
        print(f"  [a{i}] {name}")
    print("  [c] Enter a custom model name/path")
    model_choice = input("Choose model to load (e.g., b1, a1, c): ").strip()
    model_path = handle_model_choice(model_choice, config["MODEL_NAMES"])

    # --- Check for local model, else try Hub ---
    local_model_path = Path(model_path)
    hub_model_id = f"{config['MODEL_USER']}/{model_path}"
    model_to_load = ""

    if local_model_path.exists():
        print(f"✅ Found local model at '{model_path}'. Loading...")
        model_to_load = model_path
    elif IS_AUTHENTICATED:
        print(f"ℹ️ Local model not found. Attempting to pull from Hub: '{hub_model_id}'")
        model_to_load = hub_model_id
    else:
        print(
            f"❌ Model not found locally at '{model_path}'. Please train the model first"
        )
        print("   or log in with Option 3 to pull from the Hugging Face Hub.")
        return

    print(f"\n--- Loading Model '{model_to_load}' for Manual Testing ---")

    try:
        if USE_UNSLOTH:
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=model_to_load,
                max_seq_length=config["MAX_SEQ_LENGTH"],
                dtype=None,
                load_in_4bit=True,
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(
                model_to_load,
                load_in_4bit=True,
                torch_dtype=torch.float16,
            )
            tokenizer = AutoTokenizer.from_pretrained(model_to_load)

    except Exception as e:
        print(f"❌❌❌ FAILED TO LOAD MODEL ❌❌❌")
        print(f"Error loading '{model_to_load}': {e}")
        print("If pulling from Hub, ensure the model exists and you have access.")
        return

    if USE_UNSLOTH:
        FastLanguageModel.for_inference(model)

    print(
        "✅ Model loaded. Enter your prompt below. Type 'exit' or 'quit' to return to the menu."
    )

    from transformers import TextIteratorStreamer
    from threading import Thread
    while True:
        user_prompt = input("\nPrompt: ")
        if user_prompt.lower() in ["exit", "quit"]:
            break

        if not user_prompt:
            print("No prompt provided. Please enter a prompt.")
            continue

        # Use the tokenizer's chat template
        messages = [{"role": "user", "content": user_prompt}]
        formatted_prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(formatted_prompt, return_tensors="pt").to("cuda")

        # Set up streaming
        streamer = TextIteratorStreamer(
            tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        # Generate with streaming
        gen_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=config["MAX_SEQ_LENGTH"],
            use_cache=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )

        # Run generation in background thread
        thread = Thread(target=model.generate, kwargs=gen_kwargs)
        thread.start()

        print("\n--- Generated Response ---")
        for token in streamer:
            print(token, end="", flush=True)
        print("\n")
        thread.join()


def handle_model_choice(choice: str, model_list: list) -> str:
    """Helper to resolve user's model choice from a list or custom input."""
    choice = choice.lower()
    if choice.startswith("b") and choice[1:].isdigit():
        idx = int(choice[1:]) - 1
        if 0 <= idx < len(config["MODEL_NAMES"]):
            return config["MODEL_NAMES"][idx]
    elif choice.startswith("a") and choice[1:].isdigit():
        idx = int(choice[1:]) - 1
        if 0 <= idx < len(config["LORA_ADAPTERS"]):
            return config["LORA_ADAPTERS"][idx]
    elif choice == "c":
        return input("Enter custom model name/path: ").strip()

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(model_list):
            return model_list[idx]
    return choice


def huggingface_auth() -> None:
    """Handles Hugging Face authentication."""
    global IS_AUTHENTICATED
    token_path = Path(config["HF_TOKEN_PATH"])

    if token_path.exists():
        print("Found saved Hugging Face token.")
        try:
            login(token=token_path.read_text().strip())
            IS_AUTHENTICATED = True
            print("✅ Successfully authenticated with Hugging Face.")
            return
        except Exception as e:
            print(f"⚠️  Authentication with saved token failed: {e}")

    print("\nPlease paste your Hugging Face token below to log in (optional).")
    print("(You can get a token from https://huggingface.co/settings/tokens)")

    token = input("HF Token: ").strip()

    if not token:
        print("Skipping authentication.")
        IS_AUTHENTICATED = False
        return

    try:
        login(token=token)
        IS_AUTHENTICATED = True
        print("✅ Successfully authenticated with Hugging Face.")
        with open(config["HF_TOKEN_PATH"], "w") as f:
            f.write(token)
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        IS_AUTHENTICATED = False


if __name__ == "__main__":
    huggingface_auth()
    try:
        while True:
            print("\n--- Generative Model Training Menu (Unsloth Optimized) ---")
            print("1. Fine-tune a base model")
            print("-------------------------------------------------------------")
            print("2. Manually Test Model")
            print("3. Hugging Face Login")
            print("4. Exit")
            choice = input("> ").strip()

            if choice == "1":
                print("\n--- Step 1: Select a Training Profile ---")
                hardware_type, ram = detect_hardware()

                if hardware_type == "gpu" and ram >= 32:
                    recommendation = "1"
                    print(
                        f"✅ High-End GPU with {ram:.1f}GB VRAM detected. Profile 1 (Max Perf) is recommended."
                    )
                elif hardware_type == "gpu" and ram >= 16:
                    recommendation = "2"
                    print(
                        f"✅ High-End GPU with {ram:.1f}GB VRAM detected. Profile 2 is recommended."
                    )
                elif hardware_type == "gpu" and ram >= 12:
                    recommendation = "3"
                    print(
                        f"✅ High-End GPU with {ram:.1f}GB VRAM detected. Profile 3 is recommended."
                    )
                elif hardware_type == "gpu" and ram >= 6:
                    recommendation = "4"
                    print(
                        f"✅ GPU with {ram:.1f}GB VRAM detected. Profile 4 is recommended."
                    )
                elif hardware_type == "gpu":
                    recommendation = "5"
                    print(
                        f"✅ GPU with {ram:.1f}GB VRAM detected. Profile 5 is recommended."
                    )
                else:
                    recommendation = "5"
                    print(
                        f"ℹ️ No GPU detected. System has {ram:.1f}GB RAM. Profile 5 is recommended."
                    )

                for key, prof in TRAINING_PROFILES.items():
                    print(f"  {key}. {prof['name']}")

                profile_choice = (
                    input(f"Enter profile number [default: {recommendation}]: ").strip()
                    or recommendation
                )
                selected_profile = TRAINING_PROFILES.get(profile_choice)

                if not selected_profile:
                    print("❌ Invalid profile. Aborting.")
                    continue

                print("\n--- Step 2: Select a Base Model ---")
                print("  --- Base Models ---")
                for i, name in enumerate(config["MODEL_NAMES"], 1):
                    print(f"  [b{i}] {name}")
                print("  --- LoRA Adapters (to continue training) ---")
                for i, name in enumerate(config["LORA_ADAPTERS"], 1):
                    print(f"  [a{i}] {name}")
                print("  [c] Enter a custom model name/path from Hugging Face")
                model_choice = input(
                    "Enter model to fine-tune (e.g., b1, a1, c): "
                ).strip()
                base_model_name = handle_model_choice(
                    model_choice, config["MODEL_NAMES"]
                )

                print("\n--- Step 3: Select a Dataset ---")
                for i, (name, is_hf) in enumerate(config["DATASETS"], 1):
                    source = "Hugging Face" if is_hf else "Local"
                    print(f"  [{i}] {name} ({source})")
                print("  [c] Custom local dataset (.parquet)")
                data_choice = input("Enter dataset to use: ").strip()

                if data_choice.isdigit():
                    idx = int(data_choice) - 1
                    if 0 <= idx < len(config["DATASETS"]):
                        data_path, is_hf_dataset = config["DATASETS"][idx]
                    else:
                        print("❌ Invalid dataset choice.")
                        continue
                elif data_choice.lower() == "c":
                    data_path = input("Enter path to custom .parquet file: ").strip()
                    is_hf_dataset = False
                else:
                    print("❌ Invalid dataset choice.")
                    continue

                print("\n--- Step 4: Configure Training Run ---")
                num_epochs = int(
                    input("Enter number of training epochs [default: 1]: ") or 1
                )
                new_model_name = input(
                    "Enter name for the new fine-tuned model: "
                ).strip()
                if not new_model_name:
                    print("❌ Output model name cannot be empty.")
                    continue

                use_sharding = (
                    input("Use dataset sharding (for very large datasets)? [y/N]: ")
                    .strip()
                    .lower()
                    == "y"
                )
                num_shards = 1
                shard_index = 0
                merge_adapters = True
                epochs_for_this_run = num_epochs

                if use_sharding:
                    num_shards = int(
                        input(f"Enter total number of shards [e.g., 10]: ") or 10
                    )
                    shard_index = int(
                        input(
                            f"Enter shard index to train on (0 to {num_shards - 1}): "
                        )
                        or 0
                    )
                    epochs_for_this_run = shard_index + 1
                    is_final_run = (
                        input(
                            "Is this the FINAL shard? (This will merge the adapters) [y/N]: "
                        )
                        .strip()
                        .lower()
                        == "y"
                    )
                    merge_adapters = is_final_run
                else:
                    merge_adapters = True
                    epochs_for_this_run = num_epochs

                run_training(
                    profile=selected_profile,
                    model_name=base_model_name,
                    data_path=data_path,
                    new_model_name=new_model_name,
                    num_epochs=epochs_for_this_run,
                    is_hf_dataset=is_hf_dataset,
                    dataset_shard_index=shard_index,
                    dataset_num_shards=num_shards,
                    merge_at_end=merge_adapters,
                )
            elif choice == "2":
                run_manual_test()
            elif choice == "3":
                huggingface_auth()
            elif choice == "4":
                print("Exiting.")
                break
            else:
                print("Invalid choice, please try again.")
    except KeyboardInterrupt:
        print("\nExiting.")

# %%
