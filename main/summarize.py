import sqlite3
import pandas as pd
from tqdm import tqdm
from pathlib import Path
import torch
from unsloth import FastLanguageModel
from transformers import TextIteratorStreamer
import gc
import argparse
import sys

# =============================================================================
# CONFIGURATION
# =============================================================================
MODEL_PATH = "DerivedFunction/Qwen3-4B-finance-base"  # The model fine-tuned on general finance data
INPUT_PATH = "high_quality_snippets.parquet"  # The clean text snippets for inspection
PROMPT_PATH = "summary_prompt.md"
SYSTEM_PROMPT_PATH = "system_prompt.md"
OUTPUT_PATH_TEMPLATE = "distilled_summary_data_chunk_{}.parquet"

# --- Generation & Processing Parameters ---
MAX_SEQ_LENGTH = 4096  # Max sequence length for the model
BATCH_SIZE = 1  # Set to 1 for streaming individual responses
MAX_NEW_TOKENS = 512  # Max tokens to generate for the summary
SAVE_CHUNK_SIZE = 100  # Save progress every N records

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_prompt_template(path: str, name: str) -> str:
    """Loads the content of a prompt file."""
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        print(f"ERROR: {name} prompt file not found at {path}")
        raise

def load_prompts() -> tuple[str, str]:
    """Loads the system and user prompt templates."""
    try:
        system_prompt = load_prompt_template(SYSTEM_PROMPT_PATH, "System")
        user_prompt = load_prompt_template(PROMPT_PATH, "User")
        return system_prompt, user_prompt
    except FileNotFoundError:
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
    system_prompt, user_prompt_template = load_prompts()
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
    
    # Use TextIteratorStreamer for real-time output
    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

    # Main generation loop
    progress_bar = tqdm(range(0, len(input_df), BATCH_SIZE), desc="Generating Summaries")
    for i in progress_bar:
        # Since BATCH_SIZE is 1, we process one snippet at a time
        text = input_df['text'].iloc[i]
        user_prompt = f"{user_prompt_template}\n\n{text}"
        formatted_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        inputs = tokenizer([formatted_prompt], return_tensors="pt").to("cuda")
        
        # Explicitly create position_ids to prevent caching issues
        position_ids = torch.arange(0, inputs.input_ids.shape[1], dtype=torch.long, device="cuda").unsqueeze(0)

        # Generation arguments
        generation_kwargs = dict(
            streamer=streamer,
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            pad_token_id=tokenizer.eos_token_id,
            use_cache=True,
        )

        # Run generation in a separate thread
        from threading import Thread
        thread = Thread(target=model.generate, kwargs=generation_kwargs)
        thread.start()

        # Stream the output to the console and collect it
        print(f"\n--- Processing Snippet {i+1}/{len(input_df)} ---")
        completion = ""
        print("------------------------------------")
        print(user_prompt)
        print("------------------------------------")
        for new_text in streamer:
            print(new_text, end='', flush=True)
            completion += new_text
        print("\n------------------------------------")

        # Add to results if valid
        if "<|think|>" in completion:
            results.append({
                "prompt": user_prompt,
                "completion": completion.strip()
            })
        else:
            print(f"\nWarning: Invalid completion for snippet {i}. Skipping.")

        # Save chunk if size is reached
        if len(results) >= SAVE_CHUNK_SIZE:
            save_chunk(results, is_first_chunk, output_path)
            results = []  # Reset for the next chunk
            is_first_chunk = False  # Subsequent saves will append
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()

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