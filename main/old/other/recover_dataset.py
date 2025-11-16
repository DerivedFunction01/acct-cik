from datasets import load_dataset, concatenate_datasets
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# The path to the full dataset you recovered.
FULL_DATASET_PATH = Path("./recovered_dataset.parquet")

# A list of paths to the partial parquet files you already had locally.
# You can use wildcards like "./local_parts/*.parquet".
PARTIAL_DATASET_PATHS = [
    # Example:
    Path("./english-financial-economics-problems.parquet"),
    Path("./derivative_classification.parquet"),
]

# The column to use to identify unique rows.
# This should be a column with unique values for each data entry.
# Common choices are 'text', 'instruction', or an 'id' column.
# You may need to inspect your dataset to find the right column.
UNIQUE_COLUMN = "user"

# The local path where you want to save the dataset containing only the missing rows.
OUTPUT_PATH = Path("./missing_data.parquet")


def reduce_to_missing_data(full_path: Path, partial_paths: list[Path], unique_column: str, output_path: Path):
    """
    Loads a full dataset and several partial datasets, then saves only the rows
    from the full dataset that are not present in the partial datasets.
    """
    if not partial_paths:
        print("❌ No partial dataset files specified. Please update the `PARTIAL_DATASET_PATHS` list.")
        return

    try:
        print(f"Loading full dataset from '{full_path}'...")
        full_dataset = load_dataset("parquet", data_files=str(full_path), split="train")
        print(f"✅ Loaded {len(full_dataset)} records from the full dataset.")

        print("Loading and concatenating partial datasets...")
        partial_datasets = [load_dataset("parquet", data_files=str(p), split="train") for p in partial_paths]
        combined_partial_dataset = concatenate_datasets(partial_datasets)
        print(f"✅ Loaded {len(combined_partial_dataset)} total records from {len(partial_paths)} partial files.")

        print(f"Finding missing records based on unique column '{unique_column}'...")
        partial_ids = set(combined_partial_dataset[unique_column])

        missing_dataset = full_dataset.filter(lambda x: x[unique_column] not in partial_ids)
        print(f"✅ Found {len(missing_dataset)} missing records.")

        missing_dataset.to_parquet(output_path)
        print(f"✅ Successfully saved missing records to '{output_path}'.")

    except Exception as e:
        print(f"❌ An error occurred: {e}")
        print("   Please ensure file paths are correct and the unique column exists in all datasets.")


if __name__ == "__main__":
    reduce_to_missing_data(FULL_DATASET_PATH, PARTIAL_DATASET_PATHS, UNIQUE_COLUMN, OUTPUT_PATH)
