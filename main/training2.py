# %%
# %pip install unsloth
# Also run: pip uninstall unsloth -y && pip install --upgrade --no-cache-dir "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
import unsloth

import json
import random
import math
from pathlib import Path
import multiprocessing

# %%
# Initialization
import pandas as pd
from unsloth import FastLanguageModel
import torch
from psutil import virtual_memory
from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer
from huggingface_hub import login


config = {
    "DATA_PATH": "training_data.parquet",
    "BASE_MODEL": "unsloth/Qwen3-4B-Thinking-2507-unsloth-bnb-4bit",  # Unsloth's optimized version
    "NEW_MODEL_NAME": "derivatives-classifier-4B",  # Renamed for clarity
    "MODEL_USER": "DerivedFunction",
    "HF_TOKEN_PATH": "hf_token",
    "MAX_SEQ_LENGTH": 2048,  # Qwen2.5 supports up to 32k, but 2048 is good for training
}
IS_AUTHENTICATED = False

# =============================================================================
# DYNAMIC CONFIGURATION PROFILES (NEW)
# =============================================================================

TRAINING_PROFILES = {
    "1": {
        "name": "High VRAM / Colab (>= 16GB)",
        "r": 64,
        "lora_alpha": 128,
        "batch_size": 4,
        "gradient_accumulation": 4,
        "max_seq_length": 8192,
        "load_in_4bit": True,
    },
    "2": {
        "name": "Low VRAM (8-16GB)",
        "r": 16,
        "lora_alpha": 32,
        "batch_size": 1,
        "gradient_accumulation": 8,
        "max_seq_length": 4096,
        "load_in_4bit": True,
    },
    "3": {
        "name": "CPU / Low RAM (< 16GB)",
        "r": 8,
        "lora_alpha": 16,
        "batch_size": 1,
        "gradient_accumulation": 4,
        "max_seq_length": 2048,
        "load_in_4bit": False,  # 4-bit is not optimized for CPU
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


def format_prompt(sample):
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


def run_training(profile: dict, model_name=config["BASE_MODEL"], num_epochs=1):
    """Main function to run the training process with Unsloth optimization."""
    print(f"\n--- Starting Training with Unsloth ---")
    print(f"Profile: {profile['name']}, Base Model: {model_name}, Epochs: {num_epochs}")

    # --- Load and preprocess data ---
    print("\n--- Loading and Preprocessing Data ---")
    try:
        dataset = load_dataset("parquet", data_files=config["DATA_PATH"], split="train")

        # Format the dataset
        def formatting_func(examples):
            texts = []
            for i in range(len(examples["prompt"])):
                text = format_prompt(
                    {
                        "prompt": examples["prompt"][i],
                        "completion": examples["completion"][i],
                    }
                )
                texts.append(text)
            return {"text": texts}

        dataset = dataset.map(formatting_func, batched=True)

        # Create a 90/10 train/test split
        dataset = dataset.train_test_split(test_size=0.1)
        train_dataset = dataset["train"]
        eval_dataset = dataset["test"]

        print(
            f"Data loaded successfully. Training samples: {len(train_dataset)}, Evaluation samples: {len(eval_dataset)}"
        )
    except Exception as e:
        print(f"❌ Failed to load data from {config['DATA_PATH']}: {e}")
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

    # --- Training Arguments ---
    training_args = TrainingArguments(
        output_dir=config["NEW_MODEL_NAME"],
        num_train_epochs=num_epochs,
        per_device_train_batch_size=profile["batch_size"],
        per_device_eval_batch_size=profile["batch_size"],
        gradient_accumulation_steps=profile["gradient_accumulation"],
        warmup_steps=5,
        learning_rate=2e-4,
        max_grad_norm=0.3, # Helps with training stability.
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=1, # Log every step
        optim="adamw_8bit",  # Unsloth optimized optimizer
        weight_decay=0.01,
        lr_scheduler_type="cosine", # Cosine scheduler can sometimes yield better results
        seed=3407,
        save_strategy="steps",
        save_steps=200, # Save checkpoints more frequently
        load_best_model_at_end=True, # Load the best model at the end of training
        eval_strategy="steps",
        eval_steps=100,
        report_to="tensorboard",
        push_to_hub=True, # Let the Trainer handle pushing
        hub_model_id=f"{config['MODEL_USER']}/{config['NEW_MODEL_NAME']}",
    )

    # --- Initialize SFTTrainer ---
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",  # The field containing our formatted text
        max_seq_length=config["MAX_SEQ_LENGTH"],
        dataset_num_proc=multiprocessing.cpu_count(),  # Dynamically set based on available CPUs
        packing=False,  # Pack short sequences for faster training
        args=training_args,
    )

    # --- Train and Save ---
    print(f"\nStarting training for {num_epochs} epochs...")
    print("🚀 Unsloth provides 2-5x faster training and 60% less memory usage!")

    trainer_stats = trainer.train()

    print("\n--- Training Statistics ---")
    print(f"Training time: {trainer_stats.metrics['train_runtime']:.2f} seconds")
    print(
        f"Samples per second: {trainer_stats.metrics['train_samples_per_second']:.2f}"
    )

    # --- Merge, Save, and Push ---
    # First, save the trained LoRA adapters
    print("\n--- Saving LoRA Adapters ---")
    model.save_pretrained("lora_adapters")
    tokenizer.save_pretrained("lora_adapters")

    # Optional: Push only the adapters to the Hub
    # model.push_to_hub(f"{config['MODEL_USER']}/{config['NEW_MODEL_NAME']}-lora", token=True)
    # tokenizer.push_to_hub(f"{config['MODEL_USER']}/{config['NEW_MODEL_NAME']}-lora", token=True)

    # Merge the adapters into the model for a final, standalone model
    if hasattr(model, "merge_and_unload"):
        print("\n--- Merging LoRA adapters into the base model ---")
        model = model.merge_and_unload()

    print("\n--- Saving final merged model ---")
    trainer.model = model # Update trainer's model reference to the merged one
    trainer.save_model(config["NEW_MODEL_NAME"])

    # The trainer will automatically push the final (merged) model if push_to_hub=True
    if training_args.push_to_hub:
        print(f"\nModel will be pushed to the Hub at '{training_args.hub_model_id}' by the Trainer.")
    else:
        print(f"Skipping push to Hub. The final model is saved locally in the '{config['NEW_MODEL_NAME']}' directory.")


def run_manual_test():
    """Allows for manual, interactive testing of the fine-tuned model."""
    model_path = config["NEW_MODEL_NAME"]
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
        dataset = load_dataset("parquet", data_files=config["DATA_PATH"], split="train")
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
    data_path = config["DATA_PATH"]
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
        formatted_text = format_prompt(sample)
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
        use_saved = (
            input(f"Found a saved token. Use it? (y/n) [default: y]: ").lower().strip()
        )
        if use_saved not in ("y", ""):
            token = input("HF Token: ").strip()
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
            print("1. Start Training (Interactive Setup)")
            print("2. View Sample from Dataset")
            print("3. Manually Test Model")
            print("4. Hugging Face Login")
            print("5. Exit")
            choice = input("> ").strip()

            if choice == "1":
                # --- New Dynamic Menu ---
                print("\n--- Select a Training Profile ---")
                hardware_type, ram = detect_hardware()
                
                # Suggest a profile
                if hardware_type == "gpu" and ram >= 16:
                    recommendation = "1"
                    print(f"✅ GPU with {ram:.1f}GB VRAM detected. Profile 1 is recommended.")
                elif hardware_type == "gpu":
                    recommendation = "2"
                    print(f"✅ GPU with {ram:.1f}GB VRAM detected. Profile 2 is recommended.")
                else:
                    recommendation = "3"
                    print(f"ℹ️ No GPU detected. System has {ram:.1f}GB RAM. Profile 3 is recommended.")

                for key, prof in TRAINING_PROFILES.items():
                    print(f"  {key}. {prof['name']}")
                
                profile_choice = input(f"Enter profile number [default: {recommendation}]: ").strip() or recommendation
                selected_profile = TRAINING_PROFILES.get(profile_choice)

                if not selected_profile:
                    print("❌ Invalid profile. Aborting.")
                    continue

                num_epochs = int(input("Enter number of training epochs [default: 1]: ") or 1)
                run_training(profile=selected_profile, num_epochs=num_epochs)
            elif choice == "2":
                view_dataset_sample()
            elif choice == "3":
                run_manual_test()
            elif choice == "4":
                huggingface_auth()
            elif choice == "5":
                print("Exiting.")
                break
            else:
                print("Invalid choice, please try again.")
    except KeyboardInterrupt:
        print("\nExiting.")

# %%
