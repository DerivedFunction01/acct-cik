# %%
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Qwen3-1.7B-finance-lora",  # YOUR MODEL YOU USED FOR TRAINING
    max_seq_length=32768,
    load_in_4bit=True,
)

# %%
model.save_pretrained_merged(
    "model",
    tokenizer,
    save_method="merged_16bit",
)

# %%
# Authenthicate
from huggingface_hub import login
# Read from the hf_token file
with open("hf_token", "r") as f:
    token = f.read().strip()
    login(token=token)
# %%
model.push_to_hub_merged("DerivedFunction/Qwen3-1.7B-finance", tokenizer, save_method="merged_16bit")

# %%
