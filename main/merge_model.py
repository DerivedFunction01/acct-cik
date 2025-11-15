from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = "unsloth/Qwen3-1.7B-unsloth-bnb-4bit"  # or exact base used
model = AutoModelForCausalLM.from_pretrained(
    base, load_in_4bit=False, dtype="auto", device_map="auto"
)
model = PeftModel.from_pretrained(model, model_id="DerivedFunction/Qwen3-1.7B-finance-base", load_in_4bit=False)
merged = model.merge_and_unload()

tokenizer = AutoTokenizer.from_pretrained("DerivedFunction/Qwen3-1.7B-finance-base")

merged.save_pretrained("./merged")
tokenizer.save_pretrained("./merged")

# Save it to HF:
merged.push_to_hub("merged")
tokenizer.push_to_hub("merged")