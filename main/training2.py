# %%
# %pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
# Also run: pip uninstall unsloth -y && pip install --upgrade --no-cache-dir "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
import unsloth

import json
import random
import math
from pathlib import Path
import multiprocessing

# %%
# --- CONFIGURATION ---
import pandas as pd
from unsloth import FastLanguageModel
import torch
from psutil import virtual_memory
from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer
from huggingface_hub import login


config = {
    "MODEL_USER": "DerivedFunction",
    "MODEL_NAMES": [
        "unsloth/Qwen3-1.7B-unsloth-bnb-4bit",  # Smaller, faster alternative
        "DerivedFunction/Qwen3-1.7B-derivatives-base",
    ],
    "LORA_ADAPTERS": [
        # Example: "my-finance-model_lora" (local) or "YourUser/my-finance-model_lora" (Hub)
        "DerivedFunction/Qwen3-1.7B-derivatives-base_lora",
    ],
    "DATASETS": [
        ("DerivedFunction/Derivatives-Finance-200K", True),  # (path/id, is_hf_dataset)
    ],
    "HF_TOKEN_PATH": "hf_token",
    "MAX_SEQ_LENGTH": 2048,  # Qwen3 supports up to 32k, but 2048 is good for training
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
        "batch_size": 18,
        "gradient_accumulation": 4,
        "max_seq_length": 24576,
        "load_in_4bit": True,
    },
    "2": {
        "name": "L4 / Pro (>= 20 GB)",
        "r": 256,
        "lora_alpha": 512,
        "batch_size": 12,
        "gradient_accumulation": 4,
        "max_seq_length": 20480,
        "load_in_4bit": True,
    },
    "3": {
        "name": "High VRAM / Colab (>= 12GB)",
        "r": 128,
        "lora_alpha": 256,
        "batch_size": 2,
        "gradient_accumulation": 4,
        "max_seq_length": 8192,
        "load_in_4bit": True,
    },
    "4": {
        "name": "Low VRAM (6-12GB)",
        "r": 64,
        "lora_alpha": 128,
        "batch_size": 1,
        "gradient_accumulation": 4,
        "max_seq_length": 8192,
        "load_in_4bit": True,
    },
    "5": {
        "name": "CPU / Low RAM (< 6GB)",
        "r": 32,
        "lora_alpha": 32,
        "batch_size": 1,
        "gradient_accumulation": 4,
        "max_seq_length": 8192,
        "load_in_4bit": True,
    },
}

def detect_hardware():
    """Detects GPU VRAM and system RAM to suggest a profile."""
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return "gpu", vram_gb
    else:
        ram_gb = virtual_memory().total / (1024**3)
        return "cpu", ram_gb
# %%


def format_finance_prompt(sample):
    """Formats a sample from a dataset with 'system', 'user', 'think', and 'assistant' columns."""
    system_msg = f"<|im_start|>system\n{sample.get('system', '')}<|im_end|>\n"
    user_msg = f"<|im_start|>user\n{sample['user']}<|im_end|>\n"
    think_block = (
        f"<think>\n{sample.get('think', '').strip()}\n</think>\n\n"
        if sample.get("think")
        else "<think>\n\n</think>\n\n"
    )
    assistant_msg = (
        f"<|im_start|>assistant\n{think_block}{sample['assistant']}<|im_end|>"
    )
    return system_msg + user_msg + assistant_msg


def run_training(profile: dict, model_name: str, data_path: str, formatting_func: callable, new_model_name: str, num_epochs: int = 1, is_hf_dataset: bool = False, dataset_shard_index: int = 0, dataset_num_shards: int = 1, merge_at_end: bool = True):
    """Main function to run the training process with Unsloth optimization."""
    print(f"\n--- Starting Training with Unsloth ---")
    print(f"  - Profile: {profile['name']}")
    print(f"  - Base Model: {model_name}")
    print(f"  - Data: {data_path}")
    if dataset_num_shards > 1:
        print(f"  - Dataset Shard: {dataset_shard_index + 1} of {dataset_num_shards}")
    print(f"  - Output Model: {new_model_name}")
    print(f"  - Epochs: {num_epochs}")
    print(f"  - Merge Adapters at End: {'Yes' if merge_at_end else 'No'}")

    # --- Load and preprocess data ---
    print("\n--- Loading and Preprocessing Data ---")
    try:
        dataset = load_dataset(data_path, split="train") if is_hf_dataset else load_dataset("parquet", data_files=data_path, split="train")
        if dataset_num_shards > 1:
            print(f"Applying dataset shard: Using index {dataset_shard_index} of {dataset_num_shards} total shards.")
            dataset = dataset.shard(num_shards=dataset_num_shards, index=dataset_shard_index)

        # Use the provided formatting function and apply it to each sample.
        # The result is stored in a new 'text' column.
        dataset = dataset.map(lambda sample: {"text": formatting_func(sample)})

        # Create a 90/10 train/test split
        dataset = dataset.train_test_split(test_size=0.1)
        train_dataset = dataset["train"]
        eval_dataset = dataset["test"]

        print(
            f"Data loaded successfully. Training samples: {len(train_dataset)}, Evaluation samples: {len(eval_dataset)}"
        )
    except Exception as e:
        print(f"❌ Failed to load data from {data_path}: {e}")
        return

    # --- Load Model with Unsloth ---
    print("\n--- Initializing Model and Tokenizer with Unsloth ---")

    try:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=model_name,
            max_seq_length=profile["max_seq_length"],
            load_in_4bit=profile["load_in_4bit"],  # Use 4bit quantization based on profile
        )
    except Exception as e:
        print(f"❌❌❌ FAILED TO LOAD MODEL ❌❌❌")
        print(f"Error loading '{model_name}': {e}")
        print("If pulling from Hub, ensure the model ID is correct, you have access, and you are logged in.")
        return  # Exit the training function

    # --- Apply LoRA with Unsloth ---
    # Check if the model already has adapters. If so, we continue training them.
    # If not, we add new ones. This prevents the TypeError.
    if hasattr(model, "peft_config"):
        print("Model already has LoRA adapters. Continuing training.")
    else:
        print("Adding new LoRA adapters for fine-tuning...")
        model = FastLanguageModel.get_peft_model(
            model,
            r=profile["r"],
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            lora_alpha=profile["lora_alpha"],
            lora_dropout=0,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=3407,
            use_rslora=False,
            loftq_config=None,
        )

    # --- Dynamic Evaluation Steps ---
    # For large datasets, evaluating every 100 steps is too frequent.
    # Let's aim for 4 evaluations per epoch.
    num_train_samples = len(train_dataset)
    if num_train_samples > 20000: # Heuristic for a "large" dataset
        steps_per_epoch = math.ceil(num_train_samples / (profile["batch_size"] * profile["gradient_accumulation"]))
        eval_steps = max(100, steps_per_epoch // 4) # Evaluate 4 times per epoch, but at least every 100 steps.
    else:
        eval_steps = 100 # Default for smaller datasets
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
        max_grad_norm=0.3,  # Helps with training stability.
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,  # Log every 10 steps
        optim="adamw_8bit",  # Unsloth optimized optimizer
        weight_decay=0.01,
        lr_scheduler_type="cosine",  # Cosine scheduler can sometimes yield better results
        seed=3407,
        save_strategy="steps",
        save_steps=eval_steps,  # Save checkpoints at the same frequency as evaluation
        save_total_limit=2,  # Only save the last 2 checkpoints
        load_best_model_at_end=True,  # Load the best model at the end of training
        eval_strategy="steps",
        eval_steps=eval_steps,  # Use the dynamically calculated value
        report_to="tensorboard",
        push_to_hub=IS_AUTHENTICATED,  # Let the Trainer handle pushing
        hub_model_id=f"{config['MODEL_USER']}/{new_model_name}",
    )

    # --- Initialize SFTTrainer ---
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",  # The field containing our formatted text
        max_seq_length=profile["max_seq_length"],
        dataset_num_proc=multiprocessing.cpu_count(),  # Dynamically set based on available CPUs
        packing=False,  # Pack short sequences for faster training
        args=training_args,
    )

    # --- Train and Save ---
    print(f"\nStarting training for {num_epochs} epochs...")
    print("🚀 Unsloth provides 2-5x faster training and 60% less memory usage!")
    try:
        checkpoint_exists = Path(new_model_name).exists()
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
    # First, save the trained LoRA adapters
    print(f"\n--- Saving LoRA Adapters to '{new_model_name}_lora' ---")
    model.save_pretrained(f"{new_model_name}_lora")
    tokenizer.save_pretrained(f"{new_model_name}_lora")

    if merge_at_end:
        # Merge the adapters into the model for a final, standalone model
        if hasattr(model, "merge_and_unload"):
            print("\n--- Merging LoRA adapters into the base model ---")
            model = model.merge_and_unload()

        print(f"\n--- Saving final merged model to '{new_model_name}' ---")
        trainer.model = model # Update trainer's model reference to the merged one
        trainer.save_model(new_model_name)
        print(f"✅ Final merged model saved to '{new_model_name}'.")

    # The trainer will automatically push the final (merged) model if push_to_hub=True
    if training_args.push_to_hub:
        print(f"\nModel will be pushed to the Hub at '{training_args.hub_model_id}' by the Trainer.")
    else:
        print(f"Skipping push to Hub. The final model is saved locally in the '{new_model_name}' directory.")


def run_manual_test():
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

    # --- NEW LOGIC: Check for local model, else try Hub ---
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
        print("   or log in with Option 5 to pull from the Hugging Face Hub.")
        return
    # --- END NEW LOGIC ---

    print(f"\n--- Loading Model '{model_to_load}' for Manual Testing ---")

    # Load the fine-tuned model with Unsloth
    try:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=model_to_load, # Use the determined model name
            max_seq_length=config["MAX_SEQ_LENGTH"],
            dtype=None,
            load_in_4bit=True,
        )
    except Exception as e:
        print(f"❌❌❌ FAILED TO LOAD MODEL ❌❌❌")
        print(f"Error loading '{model_to_load}': {e}")
        print("If pulling from Hub, ensure the model exists and you have access.")
        return

    # Enable inference mode (faster)
    FastLanguageModel.for_inference(model)

    # Load the dataset to pull random prompts from
    try:
        dataset = load_dataset("parquet", data_files=config["TASK_DATA_PATH"], split="train")
        print("✅ Dataset loaded for random prompt selection.")
    except Exception as e:
        print(f"⚠️  Could not load dataset for random prompts: {e}")
        print("    You can still enter prompts manually.")
        dataset = None

    print(
        "✅ Model loaded. Enter your prompt below. Type 'exit' or 'quit' to return to the menu."
    )
    print("   (Pressing Enter with no text will load a random prompt from the task dataset)")

    while True:
        user_prompt = input("\nPrompt: ")
        if user_prompt.lower() in ["exit", "quit"]:
            break

        # If the user just presses Enter, pick a random prompt from the dataset
        if not user_prompt and dataset:
            random_index = random.randint(0, len(dataset) - 1)
            sample = dataset[random_index]
            user_prompt = sample["prompt"]
            print("\n--- 🎲 Using Random Prompt from Dataset ---")
            print(user_prompt)
            print("------------------------------------------")

        if not user_prompt:
            print(
                "No prompt provided. Please enter a prompt or press Enter for a random one."
            )
            continue

        # Format the prompt using Qwen's chat template
        formatted_prompt = (
            f"<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        )
        inputs = tokenizer(formatted_prompt, return_tensors="pt").to("cuda")

        # Generate the response with Unsloth's optimized inference
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            use_cache=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id, # Suppress warnings and improve generation
        )

        # Decode and print the output
        response_text = tokenizer.batch_decode(outputs, skip_special_tokens=False)[0]
        print("\n--- Generated Response ---")

        # Extract just the assistant's response
        if "<|im_start|>assistant" in response_text:
            response = (
                response_text.split("<|im_start|>assistant")[-1]
                .replace("<|im_end|>", "")
                .strip()
            )
            print(response)
        else:
            print(response_text)


def handle_model_choice(choice: str, model_list: list) -> str:
    """Helper to resolve user's model choice from a list or custom input."""
    choice = choice.lower()
    if choice.startswith('b') and choice[1:].isdigit():
        idx = int(choice[1:]) - 1
        if 0 <= idx < len(config["MODEL_NAMES"]):
            return config["MODEL_NAMES"][idx]
    elif choice.startswith('a') and choice[1:].isdigit():
        idx = int(choice[1:]) - 1
        if 0 <= idx < len(config["LORA_ADAPTERS"]):
            return config["LORA_ADAPTERS"][idx]
    elif choice == 'c':
        return input("Enter custom model name/path: ").strip()
    
    # Fallback for old numeric or direct name entry
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(model_list):
            return model_list[idx]
    return choice # Assume it's a custom name if no prefix matches


def huggingface_auth():
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

    token_path = Path(config["HF_TOKEN_PATH"])
    token = ""
    if token_path.exists():
        print(f"Token found in {config['HF_TOKEN_PATH']}. Using it.")
        token = token_path.read_text().strip()
    else:
        token = input("HF Token: ").strip()

    if not token:
        print("Skipping authentication.")
        IS_AUTHENTICATED = False
        return

    try:
        login(token=token)
        IS_AUTHENTICATED = True
        print("✅ Successfully authenticated with Hugging Face.")
        # Save the token for next time
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
                # --- New Dynamic Menu ---
                print("\n--- Step 1: Select a Training Profile ---")
                hardware_type, ram = detect_hardware()
                
                # Suggest a profile based on VRAM
                if hardware_type == "gpu" and ram >= 32:
                    recommendation = "1"
                    print(f"✅ High-End GPU with {ram:.1f}GB VRAM detected. Profile 1 (Max Perf) is recommended.")
                elif hardware_type == "gpu" and ram >= 16:
                    recommendation = "2"
                    print(f"✅ High-End GPU with {ram:.1f}GB VRAM detected. Profile 2 is recommended.")
                elif hardware_type == "gpu" and ram >= 12:
                    recommendation = "3"
                    print(f"✅ High-End GPU with {ram:.1f}GB VRAM detected. Profile 2 is recommended.")
                elif hardware_type == "gpu" and ram >= 6:
                    recommendation = "4"
                    print(f"✅ GPU with {ram:.1f}GB VRAM detected. Profile 3 is recommended.")
                elif hardware_type == "gpu":
                    recommendation = "5"
                    print(f"✅ GPU with {ram:.1f}GB VRAM detected. Profile 5 is recommended.")
                else:
                    recommendation = "5"
                    print(f"ℹ️ No GPU detected. System has {ram:.1f}GB RAM. Profile 5 is recommended.")

                for key, prof in TRAINING_PROFILES.items():
                    print(f"  {key}. {prof['name']}")
                
                profile_choice = input(f"Enter profile number [default: {recommendation}]: ").strip() or recommendation
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
                base_model_name = handle_model_choice(model_choice, config["MODEL_NAMES"])

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
                elif data_choice.lower() == 'c':
                    data_path = input("Enter path to custom .parquet file: ").strip()
                    is_hf_dataset = False
                    # We assume it uses the standard 'user'/'assistant' or 'prompt'/'completion' format
                else:
                    print("❌ Invalid dataset choice.")
                    continue

                print("\n--- Step 4: Configure Training Run ---")
                num_epochs = int(input("Enter number of training epochs [default: 1]: ") or 1)
                new_model_name = input("Enter name for the new fine-tuned model: ").strip()
                if not new_model_name:
                    print("❌ Output model name cannot be empty.")
                    continue

                # --- New Sharding and Merging Logic ---
                use_sharding = input("Use dataset sharding (for very large datasets)? [y/N]: ").strip().lower() == 'y'
                num_shards = 1
                shard_index = 0
                merge_adapters = True

                if use_sharding:
                    num_shards = int(input(f"Enter total number of shards [e.g., 10]: ") or 10)
                    shard_index = int(input(f"Enter shard index to train on (0 to {num_shards - 1}): ") or 0)
                    # If using sharding, ask if this is the final run to decide on merging.
                    is_final_run = input("Is this the FINAL shard? (This will merge the adapters) [y/N]: ").strip().lower() == 'y'
                    merge_adapters = is_final_run
                else:
                    # If not sharding, we always merge.
                    merge_adapters = True

                run_training(
                    profile=selected_profile,
                    model_name=base_model_name,
                    data_path=data_path,
                    formatting_func=format_finance_prompt, # Always use the finance prompt format
                    new_model_name=new_model_name,
                    num_epochs=num_epochs,
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
