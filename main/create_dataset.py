#%%
import sqlite3
import pandas as pd
import json
from tqdm import tqdm

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "web_data.db"
DEFAULT_OUTPUT_PATH = "processed_filings.parquet"


def merge_text(matches_json: str) -> str:
    """
    Parses a JSON string containing a list of text snippets and merges them
    into a single coherent string.

    Args:
        matches_json: A JSON string representing a list of strings.

    Returns:
        A single string with snippets joined by double newlines.
    """
    try:
        snippets = json.loads(matches_json)
        if isinstance(snippets, list) and snippets:
            # Join with double newline to preserve paragraph/table separation
            return "\n\n".join(str(s).strip() for s in snippets)
    except (json.JSONDecodeError, TypeError):
        # Return empty string if JSON is invalid or not a list
        return ""
    return ""


def create_dataset(db_path: str, output_path: str, num_samples: int = None):
    """
    Pulls extracted text from the database, merges it, and saves it to a
    Parquet file.

    Args:
        db_path: Path to the SQLite database.
        output_path: Path to save the output Parquet file.
        num_samples: The number of random samples to process. If None, all
                     records are processed.
    """
    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)

    # Construct the query to join tables and get all necessary data
    query = """
    SELECT
        r.cik,
        n.name AS company_name,
        r.year,
        w.url,
        w.matches
    FROM
        webpage_result w
    JOIN
        report_data r ON w.url = r.url
    LEFT JOIN
        names n ON r.cik = n.cik
    """

    print("Fetching data from the database...")
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("No data found in 'webpage_result' table. Exiting.")
        return

    print(f"Found {len(df):,} records.")

    if num_samples and num_samples < len(df):
        print(f"Sampling {num_samples} records...")
        df = df.sample(n=num_samples, random_state=42)

    # Use tqdm for a progress bar during text processing
    tqdm.pandas(desc="Merging text snippets")
    df["merged_text"] = df["matches"].progress_apply(merge_text)

    # Drop the original 'matches' column as it's no longer needed
    df = df.drop(columns=["matches"])

    print(f"Saving {len(df)} processed records to {output_path}...")
    df.to_parquet(output_path, index=False)
    print("✅ Dataset creation complete.")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("Interactive Dataset Creation")
    print("=" * 50)

    # Get number of samples from the user
    num_samples_str = input("Enter number of samples to process (or press Enter for all): ").strip()
    num_samples = None
    if num_samples_str.isdigit():
        num_samples = int(num_samples_str)
    elif num_samples_str:
        print("Invalid input for samples. Defaulting to process all records.")

    # Get output file path from the user
    output_path = input(f"Enter output file path [default: {DEFAULT_OUTPUT_PATH}]: ").strip()
    if not output_path:
        output_path = DEFAULT_OUTPUT_PATH

    create_dataset(DB_PATH, output_path, num_samples)
# %%
