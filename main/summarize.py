import time
import subprocess
import pandas as pd
from tqdm import tqdm
from pathlib import Path
import torch
from unsloth import FastLanguageModel
import gc
import argparse

# =============================================================================
# CONFIGURATION
# =============================================================================
MODEL_PATH = "DerivedFunction/Qwen3-4B-finance-base"
INPUT_PATH = "high_quality_snippets.parquet"
PROMPT_PATH = "summary_prompt.md"
SYSTEM_PROMPT_PATH = "system_prompt.md"
OUTPUT_PATH_TEMPLATE = "distilled_summary_data_chunk_{}.parquet"
DRIVE_PATH = "./drive/MyDrive/db"
LOAD_SHELL_CMD = f"cp -f {DRIVE_PATH}/{OUTPUT_PATH_TEMPLATE} ."
SAVE_SHELL_CMD = f"cp -f {OUTPUT_PATH_TEMPLATE} {DRIVE_PATH}/{OUTPUT_PATH_TEMPLATE}.tmp && mv -f {DRIVE_PATH}/{OUTPUT_PATH_TEMPLATE}.tmp {DRIVE_PATH}/{OUTPUT_PATH_TEMPLATE}"
IS_COLAB = Path(DRIVE_PATH).exists()

# --- Generation & Processing Parameters ---
MAX_SEQ_LENGTH = 4096
BATCH_SIZE = input("Enter batch size [default: 2]") or 2
BATCH_SIZE = int(BATCH_SIZE)  # Increased for batched generation
MAX_NEW_TOKENS = 512
SAVE_CHUNK_SIZE = 100

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def load_prompt_template(path: str, name: str) -> str:
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        print(f"ERROR: {name} prompt file not found at {path}")
        raise


def load_prompts() -> tuple[str, str]:
    try:
        system_prompt = load_prompt_template(SYSTEM_PROMPT_PATH, "System")
        user_prompt = load_prompt_template(PROMPT_PATH, "User")
        return system_prompt, user_prompt
    except FileNotFoundError:
        raise


last_drive_save_time, DRIVE_SAVE_INTERVAL_SECONDS = time.time(), 180


def save_chunk(results: list, is_first_chunk: bool, output_path: str):
    global last_drive_save_time
    if not results:
        return
    df_chunk = pd.DataFrame(results)
    if is_first_chunk:
        df_chunk.to_parquet(output_path, index=False)
        print(f"Saved first chunk of {len(results)} results to '{output_path}'.")
    else:
        old_df = pd.read_parquet(output_path)
        combined_df = pd.concat([old_df, df_chunk], ignore_index=True)
        combined_df.to_parquet(output_path, index=False)
        print(f"Appended chunk of {len(results)} results.")
    if IS_COLAB and (time.time() - last_drive_save_time >= DRIVE_SAVE_INTERVAL_SECONDS):
        try:
            subprocess.Popen(
                SAVE_SHELL_CMD,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"  → Saving to database in background.")
            last_drive_save_time = time.time()
        except Exception as e:
            print(f"  ⚠️  Background save failed: {e}")


# =============================================================================
# MAIN SCRIPT LOGIC
# =============================================================================


def main(total_chunks: int, chunk_index: int):
    print(f"--- Loading model: {MODEL_PATH} ---")
    try:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=MODEL_PATH,
            max_seq_length=MAX_SEQ_LENGTH,
            dtype=None,
            load_in_4bit=True,
        )
        model = FastLanguageModel.for_inference(model)
        print("✅ Model loaded successfully.")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return

    output_path = OUTPUT_PATH_TEMPLATE.format(chunk_index)
    system_prompt, user_prompt_template = load_prompts()
    try:
        input_df = pd.read_parquet(INPUT_PATH)
        input_df = input_df.sample(frac=0.1, random_state=42).reset_index(drop=True) if len(input_df) > 10000 else input_df
        print(f"Found {len(input_df)} snippets to process from '{INPUT_PATH}'.")
    except FileNotFoundError:
        print(
            f"❌ Input file not found: '{INPUT_PATH}'. Please run the filtering script first."
        )
        return

    # Resume logic
    if Path(output_path).exists():
        print(f"🔄 Found existing output file '{output_path}'. Resuming session.")
        try:
            resume_df = pd.read_parquet(output_path)
            processed_texts = set(resume_df["prompt"].str.split("\n\n").str[-1])
            input_df = input_df[~input_df["text"].isin(processed_texts)]
            print(
                f"   -> Skipping {len(processed_texts)} previously processed snippets."
            )
        except Exception as e:
            print(f"   ⚠️  Could not read resume file, starting fresh. Error: {e}")

    # Mega-chunk splitting
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

    results = []
    is_first_chunk = not Path(output_path).exists()

    progress_bar = tqdm(
        range(0, len(input_df), BATCH_SIZE), desc="Generating Summaries"
    )
    for i in progress_bar:
        batch_df = input_df.iloc[i : i + BATCH_SIZE]
        texts = batch_df["text"].tolist()
        user_prompts = [f"{user_prompt_template}\n\n{text}" for text in texts]
        formatted_prompts = [
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{up}<|im_end|>\n<|im_start|>assistant\n<|think|>"
            for up in user_prompts
        ]

        inputs = tokenizer(
            formatted_prompts, return_tensors="pt", padding=True, truncation=True
        ).to("cuda")

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                pad_token_id=tokenizer.eos_token_id,
                use_cache=True,
                do_sample=False,
            )

        completions = tokenizer.batch_decode(
            output_ids[:, inputs.input_ids.shape[1] :], skip_special_tokens=True
        )
        for up, comp in zip(user_prompts, completions):
            full_comp = "<|im_start|>assistant\n<|think|>" + comp.strip()
            if "<|think|>" in full_comp:
                results.append({"prompt": up, "completion": full_comp})
            else:
                print(f"\nWarning: Invalid completion. Skipping one entry.")

        if len(results) >= SAVE_CHUNK_SIZE:
            save_chunk(results, is_first_chunk, output_path)
            results = []
            is_first_chunk = False
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()

    if results:
        save_chunk(results, is_first_chunk, output_path)

    print(
        f"\n✅ Distillation complete for chunk {chunk_index}. Dataset saved to '{output_path}'."
    )


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
        print(
            f"   Will process chunk {args.chunk_index} of {args.total_chunks} and then exit."
        )
    else:
        print("🚀 Starting Distillation Service (Standalone Mode)")
    print("=" * 70)

    main(args.total_chunks, args.chunk_index)
