# %%
# %pip install pandas torch scikit-learn datasets transformers numpy accelerate bitsandbytes peft trl

import random
import math

# %%
# Initialization
import pandas as pd
import torch
from datasets import Dataset, load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    BitsAndBytesConfig,
)
from peft import LoraConfig, PeftModel
from trl.trainer.sft_trainer import SFTTrainer
from huggingface_hub import login
from transformers import EvalPrediction
from pathlib import Path

config = {
    "DATA_PATH": "training_data.parquet",
    "BASE_MODEL": "Qwen/Qwen2.5-7B-Instruct",
    "NEW_MODEL_PATH": "qwen2.5-7B-derivatives-v1",
    "MODEL_USER": "DerivedFunction",
    "HF_TOKEN_PATH": "hf_token",
}

# Required package versions for Qwen2.5
# transformers>=4.37.0, accelerate>=0.26.0, peft>=0.8.0
IS_AUTHENTICATED = False

# %%


def format_prompt(sample):
    """Formats a sample for instruction fine-tuning using Qwen's chat template."""
    return f"<|im_start|>user\n{sample['prompt']}<|im_end|>\n<|im_start|>assistant\n{sample['completion']}<|im_end|>"


def compute_metrics(p: EvalPrediction):
    """Computes evaluation metrics for Causal LM."""
    # The predictions are the logits, and the labels are the input_ids
    # The trainer automatically handles the loss calculation.
    # We can add perplexity, which is derived from the loss.
    loss = p.predictions.mean().item()
    perplexity = math.exp(loss)
    return {"loss": loss, "perplexity": perplexity}


def run_training(model_name=config["BASE_MODEL"], num_epochs=1, batch_size=1):
    """Main function to run the training process with given parameters."""
    print(f"\n--- Starting Training ---")
    print(f"Base Model: {model_name}, Epochs: {num_epochs}, Batch Size: {batch_size}")

    # --- Load and preprocess data ---
    print("\n--- Loading and Preprocessing Data ---")
    try:
        dataset = load_dataset("parquet", data_files=config["DATA_PATH"], split="train")
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

    # --- Quantization and Model Loading ---
    print("\n--- Initializing Model and Tokenizer ---")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=False,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        trust_remote_code=True,
        device_map="auto",
    )
    model.config.use_cache = False
    model.config.pretraining_tp = 1

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    tokenizer.model_max_length = 2048

    # --- PEFT/LoRA Configuration ---
    peft_config = LoraConfig(
        lora_alpha=16,
        lora_dropout=0.1,
        r=64,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )

    # --- Training Arguments ---
    training_args = TrainingArguments(
        output_dir=config["NEW_MODEL_PATH"],
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=4,
        optim="paged_adamw_32bit",
        save_steps=100,
        logging_steps=25,
        learning_rate=2e-4,
        weight_decay=0.001,
        fp16=False,
        bf16=False,
        max_grad_norm=0.3,
        max_steps=-1,
        warmup_ratio=0.03,
        group_by_length=True,
        lr_scheduler_type="constant",
        report_to="tensorboard",
        eval_strategy="steps",
        eval_steps=100,
    )

    # --- Initialize SFTTrainer ---
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        data_collator=None,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
        peft_config=peft_config,
        formatting_func=format_prompt,
    )

    # --- Train and Save ---
    print(f"\nStarting training for {num_epochs} epochs...")
    trainer.train()

    print("\n--- Saving final adapter model ---")
    trainer.save_model(config["NEW_MODEL_PATH"])

    # --- Push to Hub ---
    if not IS_AUTHENTICATED:
        huggingface_auth()

    if IS_AUTHENTICATED:
        push_to_hub = input(
            "\nDo you want to push the final model to the Hugging Face Hub? (y/n): "
        )
        if push_to_hub.lower().strip() == "y":
            print("Pushing model to the Hub...")
            trainer.push_to_hub(commit_message="End of training")
            print("Model pushed successfully!")
    else:
        print(
            f"Skipping push to Hub. The model adapter is saved locally in the '{config['NEW_MODEL_PATH']}' directory."
        )


def run_manual_test():
    """Allows for manual, interactive testing of the fine-tuned model."""
    model_path = config["NEW_MODEL_PATH"]
    if (
        not Path(model_path).exists()
        or not (Path(model_path) / "adapter_config.json").exists()
    ):
        print(
            f"❌ Model not found at '{model_path}'. Please train a model first (Option 1)."
        )
        return

    print("\n--- Loading Model for Manual Testing ---")

    # Load the base model with quantization
    base_model = AutoModelForCausalLM.from_pretrained(
        config["BASE_MODEL"],
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=False,
        ),
        trust_remote_code=True,
        device_map="auto",
    )

    # Load the fine-tuned PEFT model and merge adapters
    model = PeftModel.from_pretrained(base_model, model_path)
    model = model.merge_and_unload()
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained(
        config["BASE_MODEL"], trust_remote_code=True
    )
    tokenizer.pad_token = tokenizer.eos_token

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

        # Generate the response
        with torch.no_grad():
            outputs = model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_new_tokens=512,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
                do_sample=False,
                num_beams=1,
                use_cache=True,
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

        print("\n" + "=" * 25 + " RANDOM SAMPLE " + "=" * 25)
        print(f"\n[PROMPT]\n{sample['prompt']}")
        print(f"\n[COMPLETION]\n{sample['completion']}")
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
            print("\n--- Generative Model Training Menu ---")
            print("1. Start Training")
            print("2. View Sample from Dataset")
            print("3. Manually Test Model")
            print("4. Hugging Face Login")
            print("5. Exit")
            choice = input("> ").strip()

            if choice == "1":
                num_epochs = int(
                    input("Enter number of training epochs [default: 1]: ") or 1
                )
                batch_size = int(input("Enter training batch size [default: 1]: ") or 1)
                run_training(num_epochs=num_epochs, batch_size=batch_size)
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
