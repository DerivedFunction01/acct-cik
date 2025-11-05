# %%
# %pip install pandas torch scikit-learn datasets transformers numpy accelerate bitsandbytes peft trl

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
from pathlib import Path

config = {
    "DATA_PATH": "training_data.parquet",
    "BASE_MODEL": "microsoft/Phi-4-mini-instruct",
    "NEW_MODEL_PATH": "phi4-mini-derivatives-v1",
    "MODEL_USER": "DerivedFunction",
    "HF_TOKEN_PATH": "hf_token",
}
IS_AUTHENTICATED = False

# %%


def format_prompt(sample):
    """Formats a sample for instruction fine-tuning."""
    return f"<|user|>\n{sample['prompt']}<|end|>\n<|assistant|>\n{sample['completion']}<|end|>"


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
        per_device_eval_batch_size=batch_size, # Use same batch size for eval
        gradient_accumulation_steps=4, # Accumulate gradients to simulate a larger batch size
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
        processing_class=tokenizer,  # This is the correct parameter name
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
            print("2. Hugging Face Login")
            print("3. Exit")
            choice = input("> ").strip()

            if choice == "1":
                num_epochs = int(
                    input("Enter number of training epochs [default: 1]: ") or 1
                )
                batch_size = int(input("Enter training batch size [default: 1]: ") or 1)
                run_training(num_epochs=num_epochs, batch_size=batch_size)
            elif choice == "2":
                huggingface_auth()
            elif choice == "3":
                print("Exiting.")
                break
            else:
                print("Invalid choice, please try again.")
    except KeyboardInterrupt:
        print("\nExiting.")

# %%
