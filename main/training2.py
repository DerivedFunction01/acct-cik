"""
Complete Generative Model Training Script with Unsloth
Dynamic training profiles based on hardware (VRAM multipliers of 4GB)
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
# CONFIGURATION & PROFILE MANAGEMENT
# ============================================================================

PROFILE_FILE = Path(".training_profile.json")

# Base profile - all other profiles scale from this
BASE_PROFILE = {
    "name": "Base Configuration",
    "r": 64,
    "lora_alpha": 128,
    "batch_size": 1,
    "gradient_accumulation": 8,
    "max_seq_length": 32768,
    "load_in_4bit": True,
}

config = {
    "MODEL_USER": "DerivedFunction",
    "MODEL_NAMES": [
        "unsloth/Qwen3-1.7B-unsloth-bnb-4bit",
        "unsloth/Qwen3-4B-Thinking-2507",
        "DerivedFunction/Qwen3-1.7B-finance-base",
        "DerivedFunction/Qwen3-4B-finance",
    ],
    "DATASETS": [
        ("DerivedFunction/Derivatives-Finance-100K", True),
    ],
    "HF_TOKEN_PATH": "hf_token",
    "MAX_SEQ_LENGTH": 32768,
}
IS_AUTHENTICATED = False


def detect_hardware() -> Tuple[str, float]:
    """Detects GPU VRAM and system RAM."""
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return "gpu", vram_gb
    else:
        ram_gb = virtual_memory().total / (1024**3)
        return "cpu", ram_gb


def calculate_multipliers(vram_gb: float) -> dict:
    """
    Calculates hardware multipliers based on VRAM in 4GB increments.
    Scales linearly: each 4GB of VRAM increases batch/LoRA capacity.
    """
    # Clamp to minimum 4GB (prevent negative multipliers)
    vram_gb = max(4, vram_gb)

    # Number of 4GB units
    units = vram_gb / 4.0

    # Scale multipliers based on 4GB units
    # Base = 1 unit (4GB)
    r_mult = max(0.5, units / 4)  # r scales slower
    alpha_mult = max(0.25, units / 8)  # alpha scales even slower
    batch_mult = max(1, units)  # batch scales linearly
    grad_accum_mult = max(0.25, 8 / units)  # reduce grad accum as we have more VRAM

    return {
        "r_mult": round(r_mult, 2),
        "alpha_mult": round(alpha_mult, 2),
        "batch_mult": round(batch_mult, 2),
        "grad_accum_mult": round(grad_accum_mult, 2),
    }


def get_hardware_tier(vram_gb: float) -> str:
    """Maps VRAM to a human-readable tier name."""
    if vram_gb >= 40:
        return "Ultra High (A100/H100)"
    elif vram_gb >= 24:
        return "High (L4/RTX 6000)"
    elif vram_gb >= 16:
        return "Medium-High (RTX 3090/A10)"
    elif vram_gb >= 8:
        return "Medium (RTX 3070)"
    elif vram_gb >= 4:
        return "Low (RTX 3060)"
    else:
        return "CPU / Very Low VRAM"


def scale_profile(base: dict, multipliers: dict) -> dict:
    """Scales a base profile by hardware multipliers. Ensures integer values."""
    scaled = base.copy()
    scaled["r"] = max(8, int(base["r"] * multipliers["r_mult"]))
    scaled["lora_alpha"] = max(16, int(base["lora_alpha"] * multipliers["alpha_mult"]))
    scaled["batch_size"] = max(1, int(base["batch_size"] * multipliers["batch_mult"]))
    scaled["gradient_accumulation"] = max(
        1, int(base["gradient_accumulation"] * multipliers["grad_accum_mult"])
    )
    scaled["name"] = (
        f"Auto-scaled ({get_hardware_tier(4 * (multipliers['batch_mult'] or 1))})"
    )
    scaled["load_in_4bit"] = base["load_in_4bit"]
    scaled["max_seq_length"] = base["max_seq_length"]
    return scaled


def load_training_profile() -> dict:
    """
    Loads training profile from .training_profile.json if it exists,
    otherwise generates defaults based on current hardware.
    """
    if PROFILE_FILE.exists():
        print(f"📖 Found .training_profile.json. Loading configuration...")
        try:
            with open(PROFILE_FILE, "r") as f:
                profile_data = json.load(f)

            # If it's a base profile with multipliers, scale it
            if "multipliers" in profile_data:
                base = profile_data.get("base_profile", BASE_PROFILE)
                mults = profile_data["multipliers"]
                profile_data = scale_profile(base, mults)
                profile_data["name"] = profile_data.get("name", "Custom Profile")

            # Validate required fields
            required_fields = [
                "r",
                "lora_alpha",
                "batch_size",
                "gradient_accumulation",
                "max_seq_length",
                "load_in_4bit",
            ]
            if all(field in profile_data for field in required_fields):
                if "name" not in profile_data:
                    profile_data["name"] = "Custom Profile"
                print(f"✅ Loaded profile: {profile_data.get('name')}")
                return profile_data
            else:
                print(
                    f"⚠️ .training_profile.json missing required fields. Using hardware-detected defaults."
                )
        except Exception as e:
            print(
                f"⚠️ Error reading .training_profile.json: {e}. Using hardware-detected defaults."
            )

    # Fall back to hardware detection
    hardware_type, ram = detect_hardware()
    multipliers = calculate_multipliers(ram)
    profile = scale_profile(BASE_PROFILE, multipliers)

    if hardware_type == "gpu":
        print(f"✅ GPU with {ram:.1f}GB VRAM detected. Auto-scaling profile...")
    else:
        print(f"ℹ️ No GPU detected. System has {ram:.1f}GB RAM. Using CPU profile...")

    print(f"   Profile: {profile['name']}")
    print(
        f"   LoRA r={profile['r']}, batch_size={profile['batch_size']}, grad_accum={profile['gradient_accumulation']}"
    )

    return profile


def create_profile_template() -> None:
    """Creates a template .training_profile.json based on detected hardware."""
    hardware_type, vram_gb = detect_hardware()
    multipliers = calculate_multipliers(vram_gb)

    template = {
        "base_profile": BASE_PROFILE,
        "hardware_vram_gb": round(vram_gb, 1),
        "multipliers": multipliers,
        "note": "This profile scales from BASE_PROFILE using 4GB VRAM increments. Edit multipliers to customize.",
    }

    with open(PROFILE_FILE, "w") as f:
        json.dump(template, f, indent=2)

    print(
        f"✅ Created .training_profile.json template based on detected {vram_gb:.1f}GB VRAM."
    )


def get_target_modules(dataset_size: int) -> list:
    """Selects LoRA target modules based on dataset size to prevent overfitting."""
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


# ============================================================================
# TRAINING
# ============================================================================


def run_training(
    profile: dict,
    model_name: str,
    data_path: str,
    new_model_name: str,
    num_epochs: int = 1,
    is_hf_dataset: bool = False,
    dataset_shard_index: int = 0,
    dataset_num_shards: int = 1,
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
        print(f"❌❌❌ FAILED TO LOAD MODEL ❌❌❌")
        print(f"Error: {e}")
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
                f"Applying dataset shard: {dataset_shard_index + 1} of {dataset_num_shards}"
            )
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
        hub_model_id=f"{config['MODEL_USER']}/{new_model_name}",
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
            hub_model_id = f"{config['MODEL_USER']}/{new_model_name}_lora"
            print(f"🚀 Pushing to Hugging Face Hub at '{hub_model_id}'...")
            model.push_to_hub(
                hub_model_id, token=Path(config["HF_TOKEN_PATH"]).read_text().strip()
            )
            print("✅ Successfully pushed adapter to Hub.")


def huggingface_auth() -> None:
    """Handles Hugging Face authentication."""
    global IS_AUTHENTICATED
    token_path = Path(config["HF_TOKEN_PATH"])

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
    huggingface_auth()
    try:
        while True:
            print("\n" + "=" * 60)
            print("🚀 Generative Model Training (Unsloth Optimized)")
            print("=" * 60)
            print("1. Fine-tune a base model")
            print("2. Hugging Face login")
            print("3. Create training profile template")
            print("4. Exit")
            choice = input("> ").strip()

            if choice == "1":
                print("\n--- Step 1: Load Training Profile ---")
                profile = load_training_profile()

                print("\n--- Step 2: Select Base Model ---")
                print("  --- Base Models ---")
                for i, name in enumerate(config["MODEL_NAMES"], 1):
                    print(f"  [{i}] {name}")
                print("  [c] Custom model from Hugging Face")

                model_choice = input("Enter model (e.g., 1, c): ").strip()
                if model_choice.isdigit() and 0 <= int(model_choice) - 1 < len(
                    config["MODEL_NAMES"]
                ):
                    base_model_name = config["MODEL_NAMES"][int(model_choice) - 1]
                elif model_choice.lower() == "c":
                    base_model_name = input("Enter custom model name/path: ").strip()
                else:
                    print("❌ Invalid choice.")
                    continue

                print("\n--- Step 3: Select Dataset ---")
                for i, (name, is_hf) in enumerate(config["DATASETS"], 1):
                    source = "Hugging Face" if is_hf else "Local"
                    print(f"  [{i}] {name} ({source})")
                print("  [c] Custom local dataset (.parquet)")

                data_choice = input("Enter dataset: ").strip()
                if data_choice.isdigit() and 0 <= int(data_choice) - 1 < len(
                    config["DATASETS"]
                ):
                    data_path, is_hf_dataset = config["DATASETS"][int(data_choice) - 1]
                elif data_choice.lower() == "c":
                    data_path = input("Path to .parquet file: ").strip()
                    is_hf_dataset = False
                else:
                    print("❌ Invalid choice.")
                    continue

                print("\n--- Step 4: Configure Training ---")
                num_epochs = int(input("Number of epochs [default: 1]: ") or 1)
                new_model_name = input("Output model name: ").strip()

                if not new_model_name:
                    new_model_name = base_model_name

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
                    epochs_for_this_run = 1
                    if (
                        input(
                            f"The current epoch is {shard_index + 1}, continue? [y/N]: "
                        )
                        .strip()
                        .lower()
                        == "y"
                    ):
                        epochs_for_this_run = shard_index + 1
                    else:
                        epochs_for_this_run = int(
                            input("Enter epoch number for this run: ") or 1
                        )
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
                    profile=profile,
                    model_name=base_model_name,
                    data_path=data_path,
                    new_model_name=new_model_name,
                    num_epochs=epochs_for_this_run,
                    is_hf_dataset=is_hf_dataset,
                    dataset_num_shards=num_shards,
                    dataset_shard_index=shard_index,
                    merge_at_end=merge_adapters,
                )

            elif choice == "2":
                huggingface_auth()
            elif choice == "3":
                create_profile_template()
            elif choice == "4":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice.")
    except KeyboardInterrupt:
        print("\n👋 Exiting.")
