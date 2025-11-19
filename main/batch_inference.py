# =============================================================================
# BATCH SUMMARIZATION INFERENCE SCRIPT
# =============================================================================
# This script is optimized for high-throughput batch inference using a
# finetuned generative model, particularly with Unsloth for speed.
#
# Workflow:
# 1. Loads a finetuned model (e.g., your Qwen 0.6B model).
# 2. Reads a Parquet or CSV file containing the text to be summarized.
# 3. Tokenizes the input texts in batches.
# 4. Generates summaries for the entire batch at once on the GPU.
# 5. Decodes the summaries and adds them to the results.
# 6. Saves the final DataFrame with summaries to a new file.
#
# Example Usage:
# python batch_inference.py \
#   --model_path "your-hf-username/Qwen-0.6B-finance-summarize" \
#   --input_file "data_to_summarize.parquet" \
#   --output_file "summaries_output.parquet" \
#   --text_column "article_text" \
#   --batch_size 16
# =============================================================================

import torch
import pandas as pd
from tqdm import tqdm
import argparse
from pathlib import Path

try:
    from unsloth import FastLanguageModel
    USE_UNSLOTH = True
    print("✅ Unsloth found. Using Unsloth for optimized inference.")
except ImportError:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    USE_UNSLOTH = False
    print("⚠️ Unsloth not found. Falling back to standard Hugging Face transformers.")


def load_data(input_file: Path) -> pd.DataFrame:
    """Loads data from Parquet or CSV file."""
    if input_file.suffix == ".parquet":
        return pd.read_parquet(input_file)
    elif input_file.suffix == ".csv":
        return pd.read_csv(input_file)
    else:
        raise ValueError(f"Unsupported file type: {input_file.suffix}")


def run_batch_inference(args):
    """Main function to run the batch inference process."""

    # 1. Setup Device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"⚙️  Using device: {device}")

    # 2. Load Model and Tokenizer
    print(f"🚀 Loading model: {args.model_path}")
    if USE_UNSLOTH:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=args.model_path,
            max_seq_length=args.max_seq_length,
            load_in_4bit=args.load_in_4bit,
            dtype=None, # Let unsloth decide
        )
        FastLanguageModel.for_inference(model)
    else:
        model = AutoModelForCausalLM.from_pretrained(args.model_path)
        tokenizer = AutoTokenizer.from_pretrained(args.model_path)
        model.to(device)

    # Set tokenizer padding settings
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    # 3. Load Data
    print(f"📄 Loading data from: {args.input_file}")
    df = load_data(args.input_file)
    if args.text_column not in df.columns:
        raise ValueError(f"Text column '{args.text_column}' not found in the input file.")
    
    # Ensure the text column is string type and handle missing values
    texts_to_summarize = df[args.text_column].astype(str).fillna('').tolist()
    print(f"   -> Found {len(texts_to_summarize):,} texts to summarize.")

    # 4. Batch Inference
    summaries = []
    # Use tqdm to create a progress bar
    for i in tqdm(range(0, len(texts_to_summarize), args.batch_size), desc="Summarizing Batches"):
        batch_texts = texts_to_summarize[i:i + args.batch_size]

        # Apply chat template to each item in the batch
        # This is a common format for instruction-tuned models.
        prompts = [
            tokenizer.apply_chat_template([{"role": "user", "content": text}], tokenize=False, add_generation_prompt=True)
            for text in batch_texts
        ]

        # Tokenize the batch of prompts
        inputs = tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=args.max_seq_length,
        ).to(device)

        # Generate summaries for the whole batch
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.eos_token_id,
                do_sample=True,
                temperature=0.6,
                top_p=0.9,
            )

        # Decode the generated text, skipping special tokens
        # We need to slice the output to only decode the newly generated tokens
        output_only = outputs[:, inputs['input_ids'].shape[1]:]
        batch_summaries = tokenizer.batch_decode(output_only, skip_special_tokens=True)
        summaries.extend(batch_summaries)

    # 5. Save Results
    df["summary"] = summaries
    print(f"\n💾 Saving results to: {args.output_file}")
    if args.output_file.suffix == ".parquet":
        df.to_parquet(args.output_file, index=False)
    elif args.output_file.suffix == ".csv":
        df.to_csv(args.output_file, index=False)

    print("\n✨ Batch summarization complete!")
    print(df[["summary"]].head())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast Batch Summarization Inference")
    parser.add_argument("--model_path", type=str, required=True, help="Path to the finetuned model on Hugging Face Hub or locally.")
    parser.add_argument("--input_file", type=Path, required=True, help="Path to the input Parquet or CSV file.")
    parser.add_argument("--output_file", type=Path, required=True, help="Path to save the output file with summaries.")
    parser.add_argument("--text_column", type=str, default="text", help="The name of the column containing the text to summarize.")
    parser.add_argument("--batch_size", type=int, default=8, help="Number of texts to process in a single batch.")
    parser.add_argument("--max_seq_length", type=int, default=4096, help="Maximum sequence length for the model.")
    parser.add_argument("--max_new_tokens", type=int, default=512, help="Maximum number of new tokens to generate for the summary.")
    parser.add_argument("--load_in_4bit", action="store_true", help="Load the model in 4-bit for lower memory usage.")

    args = parser.parse_args()

    run_batch_inference(args)