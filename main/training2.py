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
    "TASK_DATA_PATH": "training_data.parquet",  # Your synthetic JSON data
    "BASE_MODEL": "unsloth/Qwen3-4B-Thinking-2507",  # Unsloth's optimized version
    "FINANCE_DATASET_HF": "DerivedFunction/Finance-Instruct-100K", # Your HF dataset
    "FINANCE_FINETUNED_MODEL": "Qwen3-4B-finance-base", # Intermediate model
    "FINAL_MODEL_NAME": "derivatives-classifier-4B",  # Renamed for clarity
    "MODEL_USER": "DerivedFunction",
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
        "batch_size": 22,
        "gradient_accumulation": 1,
        "max_seq_length": 24576,
        "load_in_4bit": False,
    },
    "2": {
        "name": "A100 / Pro (>= 30GB)",
        "r": 256,
        "lora_alpha": 512,
        "batch_size": 12,
        "gradient_accumulation": 1,
        "max_seq_length": 20480,
        "load_in_4bit": False,
    },
    "3": {
        "name": "High VRAM / Colab (>= 12GB)",
        "r": 128,
        "lora_alpha": 256,
        "batch_size": 4,
        "gradient_accumulation": 4,
        "max_seq_length": 8192,
        "load_in_4bit": False,
    },
    "4": {
        "name": "Low VRAM (6-12GB)",
        "r": 64,
        "lora_alpha": 128,
        "batch_size": 2,
        "gradient_accumulation": 4,
        "max_seq_length": 4096,
        "load_in_4bit": False,
    },
    "5": {
        "name": "CPU / Low RAM (< 6GB)",
        "r": 32,
        "lora_alpha": 32,
        "batch_size": 1,
        "gradient_accumulation": 4,
        "max_seq_length": 2048,
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


def format_task_prompt(sample):
    """Formats a sample for instruction fine-tuning using Qwen's chat template with a thought block."""
    try:
        completion_data = json.loads(sample["completion"])
        chain_of_thought = completion_data.pop("chain_of_thought", "")

        # The rest of the JSON data
        rest_of_json = json.dumps(completion_data, indent=2)

        # Construct the new format
        return f"<|im_start|>user\n{sample['prompt']}<|im_end|>\n<|im_start|>assistant\n<|think|>\n{chain_of_thought}\n<|endthink|>\n{rest_of_json}<|im_end|>"
    except (json.JSONDecodeError, KeyError):
        # Fallback for cases where completion is not a valid JSON or doesn't have the expected structure
        return f"<|im_start|>user\n{sample['prompt']}<|im_end|>\n<|im_start|>assistant\n{sample['completion']}<|im_end|>"


def format_finance_prompt(sample):
    """Formats a sample from a dataset with 'user' and 'assistant' columns."""
    # This dataset has 'user' and 'assistant' columns.
    return f"<|im_start|>user\n{sample['user']}<|im_end|>\n<|im_start|>assistant\n{sample['assistant']}<|im_end|>"


def run_training(profile: dict, model_name: str, data_path: str, formatting_func: callable, new_model_name: str, num_epochs: int = 1, is_hf_dataset: bool = False):
    """Main function to run the training process with Unsloth optimization."""
    print(f"\n--- Starting Training with Unsloth ---")
    print(f"  - Profile: {profile['name']}\n  - Base Model: {model_name}\n  - Data: {data_path}\n  - Output Model: {new_model_name}\n  - Epochs: {num_epochs}")

    # --- Load and preprocess data ---
    print("\n--- Loading and Preprocessing Data ---")
    try:
        dataset = load_dataset(data_path, split="train") if is_hf_dataset else load_dataset("parquet", data_files=data_path, split="train")

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

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=profile["max_seq_length"],
        dtype=None,  # Auto-detect (will use Float16 for Tesla T4, V100, Bfloat16 for Ampere+)
        load_in_4bit=profile["load_in_4bit"],  # Use 4bit quantization based on profile
    )

    # --- Apply LoRA with Unsloth ---
    model = FastLanguageModel.get_peft_model(
        model,
        r=profile["r"],
        # In a robust Colab environment, "all-linear" is preferred for better performance.
        # Unsloth's "all-linear" can sometimes fail. Specifying modules explicitly is more robust.
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
        lora_dropout=0,  # Unsloth optimizes better with 0 dropout
        bias="none",
        use_gradient_checkpointing="unsloth",  # Unsloth's optimized gradient checkpointing
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
        max_grad_norm=0.3, # Helps with training stability.
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10, # Log every step
        optim="adamw_8bit",  # Unsloth optimized optimizer
        weight_decay=0.01,
        lr_scheduler_type="cosine", # Cosine scheduler can sometimes yield better results
        seed=3407,
        save_strategy="steps",
        save_steps=200, # Save checkpoints more frequently
        save_total_limit=3, # Only save the last 3 checkpoints
        load_best_model_at_end=True, # Load the best model at the end of training
        evaluation_strategy="steps",
        eval_steps=eval_steps, # Use the dynamically calculated value
        report_to="tensorboard",
        push_to_hub=IS_AUTHENTICATED, # Let the Trainer handle pushing
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
    except:
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

    # Merge the adapters into the model for a final, standalone model
    if hasattr(model, "merge_and_unload"):
        print("\n--- Merging LoRA adapters into the base model ---")
        model = model.merge_and_unload()

    print(f"\n--- Saving final merged model to '{new_model_name}' ---")
    trainer.model = model # Update trainer's model reference to the merged one
    trainer.save_model(config["NEW_MODEL_NAME"])

    # The trainer will automatically push the final (merged) model if push_to_hub=True
    if training_args.push_to_hub:
        print(f"\nModel will be pushed to the Hub at '{training_args.hub_model_id}' by the Trainer.")
    else:
        print(f"Skipping push to Hub. The final model is saved locally in the '{new_model_name}' directory.")


def run_manual_test():
    """Allows for manual, interactive testing of the fine-tuned model."""
    model_path = config["FINAL_MODEL_NAME"]
    if not Path(model_path).exists():
        print(
            f"❌ Model not found at '{model_path}'. Please train a model first (Option 1)."
        )
        return

    print("\n--- Loading Model for Manual Testing ---")

    # Load the fine-tuned model with Unsloth
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_path,
        max_seq_length=config["MAX_SEQ_LENGTH"],
        dtype=None,
        load_in_4bit=True,
    )

    # Enable inference mode (faster)
    FastLanguageModel.for_inference(model)

    # Load the dataset to pull random prompts from
    try:
        dataset = load_dataset("parquet", data_files=config["TASK_DATA_PATH"], split="train")
        print("✅ Dataset loaded for random prompt selection.")
    except Exception as e:
        print(f"⚠️  Could not load dataset for random prompts: {e}")
        print("   You can still enter prompts manually.")
        dataset = None

    print(
        "✅ Model loaded. Enter your prompt below. Type 'exit' or 'quit' to return to the menu."
    )

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


def view_dataset_sample():
    """Loads and displays a random sample from the training dataset."""
    data_path = config["TASK_DATA_PATH"]
    if not Path(data_path).exists():
        print(f"❌ Dataset file not found at '{data_path}'.")
        print("   Please ensure the training data has been generated.")
        return

    print(f"\n--- Loading a random sample from {data_path} ---")
    try:
        # Load the full dataset
        dataset = load_dataset("parquet", data_files=data_path, split="train")

        # Select a random sample
        random_index = random.randint(0, len(dataset) - 1)
        sample = dataset[random_index]

        print("\n" + "=" * 25 + " RANDOM FORMATTED SAMPLE " + "=" * 25)
        # Use the same formatting function as the trainer to see the final input
        formatted_text = format_task_prompt(sample)
        print(formatted_text)
        print("\n" + "=" * 65)
    except Exception as e:
        print(f"❌ Failed to load or read the dataset: {e}")


def huggingface_auth():
    """Handles Hugging Face authentication."""
    global IS_AUTHENTICATED
    print("\nPlease paste your Hugging Face token below to log in.")

    token_path = Path(config["HF_TOKEN_PATH"])
    token = ""
    if token_path.exists():
        token = token_path.read_text().strip()
    else:
        token = input("HF Token: ").strip()

    if not token:
        print("Skipping authentication.")
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
            print("1. [Stage 1] Fine-tune on general finance data (from Hugging Face)")
            print("2. [Stage 2] Fine-tune on specific task data (JSON generation)")
            print("-------------------------------------------------------------")
            print("3. View Sample from Task Dataset")
            print("4. Manually Test Final Model")
            print("5. Hugging Face Login")
            print("6. Exit")
            choice = input("> ").strip()
            
            if choice == "1":
                # --- New Dynamic Menu ---
                print("\n--- Select a Training Profile ---")
                hardware_type, ram = detect_hardware()
                
                # Suggest a profile based on VRAM
                if hardware_type == "gpu" and ram >= 32:
                    recommendation = "1"
                    print(f"✅ High-End GPU with {ram:.1f}GB VRAM detected. Profile 1 (Max Perf) is recommended.")
                elif hardware_type == "gpu" and ram >= 12:
                    recommendation = "2"
                    print(f"✅ High-End GPU with {ram:.1f}GB VRAM detected. Profile 1 (A100) is recommended.")
                elif hardware_type == "gpu" and ram >= 6:
                    recommendation = "3"
                    print(f"✅ GPU with {ram:.1f}GB VRAM detected. Profile 3 is recommended.")
                elif hardware_type == "gpu":
                    recommendation = "4"
                    print(f"✅ GPU with {ram:.1f}GB VRAM detected. Profile 4 is recommended.")
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

                print("\n--- Stage 1: General Finance Fine-tuning ---")
                num_epochs = int(input("Enter number of training epochs [default: 1]: ") or 1)
                
                # Use the dataset from Hugging Face Hub directly
                run_training(
                    profile=selected_profile,
                    model_name=config["BASE_MODEL"],
                    data_path=config["FINANCE_DATASET_HF"],
                    formatting_func=format_finance_prompt,
                    new_model_name=config["FINANCE_FINETUNED_MODEL"],
                    num_epochs=num_epochs,
                    is_hf_dataset=True,
                )

            elif choice == "2":
                # --- Stage 2 Training ---
                print("\n--- Select a Training Profile ---")
                if hardware_type == "gpu" and ram >= 70:
                    recommendation = "1"
                elif hardware_type == "gpu" and ram >= 35:
                    recommendation = "2"
                elif hardware_type == "gpu":
                    recommendation = "3"
                elif hardware_type == "gpu" and ram >= 15:
                    recommendation = "3"
                elif hardware_type == "gpu":
                    recommendation = "4"
                else:
                    recommendation = "5"

                for key, prof in TRAINING_PROFILES.items(): print(f"  {key}. {prof['name']}")
                profile_choice = input(f"Enter profile number [default: {recommendation}]: ").strip() or recommendation
                selected_profile = TRAINING_PROFILES.get(profile_choice)
                if not selected_profile:
                    print("❌ Invalid profile. Aborting.")
                    continue

                print("\n--- Stage 2: Task-Specific Fine-tuning (JSON Generation) ---")
                num_epochs = int(input("Enter number of training epochs [default: 4]: ") or 4)
                run_training(
                    profile=selected_profile,
                    model_name=config["FINANCE_FINETUNED_MODEL"], # Start from the finance-tuned model
                    data_path=config["TASK_DATA_PATH"],
                    formatting_func=format_task_prompt,
                    new_model_name=config["FINAL_MODEL_NAME"],
                    num_epochs=num_epochs,
                    is_hf_dataset=False,
                )
            elif choice == "3":
                view_dataset_sample()
            elif choice == "4":
                run_manual_test()
            elif choice == "5":
                huggingface_auth()
            elif choice == "6":
                print("Exiting.")
                break
            else:
                print("Invalid choice, please try again.")
    except KeyboardInterrupt:
        print("\nExiting.")

# %%
