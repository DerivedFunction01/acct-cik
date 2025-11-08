import sqlite3
import pandas as pd
from tqdm import tqdm
from pathlib import Path
import torch
from unsloth import FastLanguageModel
import gc
import argparse
import sys

# =============================================================================
# CONFIGURATION
# =============================================================================
MODEL_PATH = "DerivedFunction/Qwen3-4B-finance-base"  # The model fine-tuned on general finance data
INPUT_PATH = "high_quality_snippets.parquet"  # The clean text snippets for inspection
PROMPT_PATH = "/home/denny/acct-cik/main/summary_prompt.md"
OUTPUT_PATH_TEMPLATE = "distilled_summary_data_chunk_{}.parquet"

# --- Generation & Processing Parameters ---
MAX_SEQ_LENGTH = 4096  # Max sequence length for the model
BATCH_SIZE = 4  # Adjust based on your GPU VRAM. 4 is a safe start.
MAX_NEW_TOKENS = 512  # Max tokens to generate for the summary
SAVE_CHUNK_SIZE = 100  # Save progress every N records

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_prompt_template() -> str:
    """Loads the content of the summary prompt."""
    try:
        return Path(PROMPT_PATH).read_text()
    except FileNotFoundError:
        print(f"ERROR: Prompt file not found at {PROMPT_PATH}")
        raise

def save_chunk(results: list, is_first_chunk: bool, output_path: str):
    """Saves a chunk of results to the parquet file."""
    if not results:
        return

    df_chunk = pd.DataFrame(results)
    if is_first_chunk:
        # For the first chunk, overwrite the file
        df_chunk.to_parquet(output_path, index=False)
        print(f"Saved first chunk of {len(results)} results to '{output_path}'.")
    else:
        # For subsequent chunks, append
        df_chunk.to_parquet(output_path, index=False, engine="pyarrow", append=True)
        print(f"Appended chunk of {len(results)} results.")

# =============================================================================
# MAIN SCRIPT LOGIC
# =============================================================================

def main(total_chunks: int, chunk_index: int):
    """Main function to generate summaries from high-quality text snippets."""
    
    # 1. Load Model and Tokenizer
    print(f"--- Loading model: {MODEL_PATH} ---")
    try:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=MODEL_PATH,
            max_seq_length=MAX_SEQ_LENGTH,
            dtype=None,
            load_in_4bit=True,  # Use 4-bit for memory efficiency
        )
        FastLanguageModel.for_inference(model)
        print("✅ Model loaded successfully.")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return

    # 2. Load prompt and data
    output_path = OUTPUT_PATH_TEMPLATE.format(chunk_index)
    prompt_template = load_prompt_template()
    try:
        input_df = pd.read_parquet(INPUT_PATH)
        print(f"Found {len(input_df)} snippets to process from '{INPUT_PATH}'.")
    except FileNotFoundError:
        print(f"❌ Input file not found: '{INPUT_PATH}'. Please run the filtering script first.")
        return

    # --- Resume Logic ---
    if Path(output_path).exists():
        print(f"🔄 Found existing output file '{output_path}'. Resuming session.")
        try:
            resume_df = pd.read_parquet(output_path)
            # The prompt contains the original text. We can extract it to find what's been processed.
            # This is a bit slow but robust.
            processed_texts = set(resume_df["prompt"].str.split("\n\n").str[-1])
            input_df = input_df[~input_df["text"].isin(processed_texts)]
            print(f"   -> Skipping {len(processed_texts)} previously processed snippets.")
        except Exception as e:
            print(f"   ⚠️  Could not read resume file, starting fresh for this chunk. Error: {e}")

    # --- Mega-Chunk Splitting Logic ---
    if total_chunks > 1:
        print(
            f"\nSplitting workload into {total_chunks} mega-chunks. This machine will process index {chunk_index}."
        )
        num_snippets = len(input_df)
        mega_chunk_size = (num_snippets + total_chunks - 1) // total_chunks
        start_index = chunk_index * mega_chunk_size
        end_index = start_index + mega_chunk_size

        input_df = input_df.iloc[start_index:end_index]
        print(
            f"  -> This machine's workload: {len(input_df)} snippets (from index {start_index} to {end_index})."
        )

    if input_df.empty:
        print("No new snippets to process for this chunk. Exiting.")
        return

    # 3. Process snippets in batches and save chunks
    results = []
    is_first_chunk = not Path(output_path).exists()
    
    # Main generation loop
    progress_bar = tqdm(range(0, len(input_df), BATCH_SIZE), desc="Generating Summaries")
    for i in progress_bar:
        # Prepare batch
        batch_texts = input_df['text'][i:i+BATCH_SIZE].tolist()
        
        # Construct full prompts for the batch
        prompts = [f"{prompt_template}\n\n{text}" for text in batch_texts]
        
        # Format for Qwen chat model
        formatted_prompts = [f"<|im_start|>user\n{p}<|im_end|>\n<|im_start|>assistant\n" for p in prompts]
        
        # Tokenize and generate
        inputs = tokenizer(formatted_prompts, return_tensors="pt", padding=True).to("cuda")
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs, 
                max_new_tokens=MAX_NEW_TOKENS, 
                pad_token_id=tokenizer.eos_token_id,
                use_cache=True
            )
        
        # Decode and extract completions
        decoded_outputs = tokenizer.batch_decode(outputs, skip_special_tokens=False)
        
        for idx, full_output in enumerate(decoded_outputs):
            # Extract only the assistant's response
            try:
                completion = full_output.split("<|im_start|>assistant\n")[-1].replace("<|im_end|>", "").strip()
                if "<|think|>" in completion: # Basic validation
                    results.append({
                        "prompt": prompts[idx],
                        "completion": completion
                    })
            except IndexError:
                print(f"\nWarning: Could not parse model output for a snippet in batch starting at index {i}.")
                continue

        # Save chunk if size is reached
        if len(results) >= SAVE_CHUNK_SIZE:
            save_chunk(results, is_first_chunk, output_path)
            results = []  # Reset for the next chunk
            is_first_chunk = False  # Subsequent saves will append
            gc.collect()  # Clean up memory

    # Save any remaining results in the last chunk
    if results:
        save_chunk(results, is_first_chunk, output_path)

    print(f"\n✅ Distillation complete for chunk {chunk_index}. Dataset saved to '{output_path}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the distillation script in standalone or chunked mode."
    )
    parser.add_argument(
        "--total-chunks",
        type=int,
        default=1,
        help="Total number of mega-chunks to split the workload into.",
    )
    parser.add_argument(
        "--chunk-index",
        type=int,
        default=0,
        help="The index of the mega-chunk this instance should process (0-based).",
    )
    args = parser.parse_args()

    print("=" * 70)
    if args.total_chunks > 1:
        print("🚀 Starting Distillation Service (Chunked Mode)")
        print(f"   Will process chunk {args.chunk_index} of {args.total_chunks} and then exit.")
    else:
        print("🚀 Starting Distillation Service (Standalone Mode)")
    print("=" * 70)

    main(args.total_chunks, args.chunk_index)