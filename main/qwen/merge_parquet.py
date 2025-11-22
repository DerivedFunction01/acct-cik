#%%
import pandas as pd
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# Define the directory to search and the pattern for the files to merge.
BASE_PATH = Path(__file__).parent
FILE_PATTERN = "q_a*.parquet"
OUTPUT_FILE = BASE_PATH / "q_a_merged.parquet"

# =============================================================================
# SCRIPT LOGIC
# =============================================================================

def merge_parquet_files(base_path: Path, pattern: str, output_path: Path):
    """
    Finds all Parquet files matching a pattern in a directory, merges them
    into a single DataFrame, and saves the result.

    Args:
        base_path (Path): The directory to search in.
        pattern (str): The glob pattern to match files (e.g., "q_a*.parquet").
        output_path (Path): The path to save the merged Parquet file.
    """
    print(f"Searching for files matching '{pattern}' in '{base_path}'...")

    # Use glob to find all files matching the pattern
    file_list = list(base_path.glob(pattern))

    if not file_list:
        print("❌ No files found to merge.")
        return

    print(f"Found {len(file_list)} files to merge:")
    for f in file_list:
        print(f"  - {f.name}")

    # Read each Parquet file into a DataFrame and store it in a list
    df_list = [pd.read_parquet(file) for file in file_list]

    # Concatenate all DataFrames in the list into a single DataFrame
    merged_df = pd.concat(df_list, ignore_index=True)
    print(f"\nSuccessfully merged data into a single DataFrame with {len(merged_df):,} rows.")

    # Save the merged DataFrame to a new Parquet file
    merged_df.to_parquet(output_path, index=False)
    print(f"✅ Merged file saved to '{output_path}'")


if __name__ == "__main__":
    merge_parquet_files(BASE_PATH, FILE_PATTERN, OUTPUT_FILE)
# %%
