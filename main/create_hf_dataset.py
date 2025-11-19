
# =============================================================================
# HUGGING FACE DATASET CREATION SCRIPT
# =============================================================================
# This script creates a Parquet dataset from the raw text stored in the
# `web_data.db` SQLite database. It's designed to be memory-efficient for
# very large databases.
#
# Workflow:
# 1. Streams URLs from the source database without loading it all into memory.
# 2. Uses a ProcessPoolExecutor for parallel processing, where each process:
#    a. Connects to the database.
#    b. Fetches the data for a single filing.
#    c. Parses the JSON and randomly samples a percentage of paragraphs.
# 3. Collects the results and writes them to a single Parquet file.
# =============================================================================
#%%
import sqlite3
import json
import random
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import pandas as pd
from tqdm import tqdm

# =============================================================================
# CONFIGURATION
# =============================================================================

DB_PATH = "web_data.db"
OUTPUT_PARQUET_PATH = "training_data.parquet"
TABLE_NAME = "webpage_result"
COLUMN_NAME = "matches"

# =============================================================================
# WORKER FUNCTION (RUNS IN A SEPARATE PROCESS)
# =============================================================================


def sample_paragraphs_from_filing(
    db_path: str, url: str, year: int, sample_rate: float
) -> list[dict]:
    """
    Connects to the DB, fetches a single filing's text, and returns a
    random sample of its paragraphs.

    Args:
        db_path (str): Path to the SQLite database.
        url (str): The URL of the filing to process.
        year (int): The year of the filing.
        sample_rate (float): The fraction of paragraphs to sample (0.0 to 1.0).

    Returns:
        A list of dictionaries, each containing the sampled text, url, and year.
    """
    try:
        # Each process creates its own connection to avoid threading issues.
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT {COLUMN_NAME} FROM {TABLE_NAME} WHERE url = ?", (url,)
        )
        result = cursor.fetchone()
        conn.close()

        if not result or not result[0]:
            return []

        matches_json = result[0]
        paragraphs = json.loads(matches_json)

        if not isinstance(paragraphs, list):
            return []
        paragraphs = [p for p in paragraphs if p.find("<") == -1]
        # Determine how many paragraphs to sample
        num_to_sample = int(len(paragraphs) * sample_rate)
        if num_to_sample == 0 and sample_rate > 0 and len(paragraphs) > 0:
            num_to_sample = 1 # Ensure at least one sample if possible
        elif len(paragraphs) == 0:
            return []
        # Perform the random sampling
        sampled_paragraphs = random.sample(paragraphs, k=num_to_sample)
        random.shuffle(sampled_paragraphs)
        # Pick a single paragraph and append the year
        text = f"Text({year}):\n" + random.choice(sampled_paragraphs)
        return [{
            "text": text,
        }]

    except (sqlite3.Error, json.JSONDecodeError, TypeError) as e:
        # Return an empty list on any error to keep the pipeline moving
        print(f"Warning: Error processing {url}: {e}")
        return []


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================


def main(args):
    """Main function to orchestrate the dataset creation."""
    print("🚀 Starting dataset creation...")
    print(f"   Source DB: {args.db_path}")
    print(f"   Output File: {args.output_path}")
    print(f"   Sample Rate: {args.sample_rate:.0%}")
    print(f"   Workers: {args.workers}")

    # 1. Get the list of all URLs to process
    print("\n[1/3] Fetching list of filings to process...")
    conn = sqlite3.connect(args.db_path)
    try:
        # Join with report_data to get the year for each URL
        query = f"""
            SELECT t1.url, t2.year
            FROM {TABLE_NAME} t1
            JOIN report_data t2 ON t1.url = t2.url
            WHERE t1.{COLUMN_NAME} IS NOT NULL AND t2.year IS NOT NULL
        """
        filings_df = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    print(f"  -> Found {len(filings_df):,} filings with year information.")
    # we only need a sample of 500
    filings_df = filings_df.sample(n=min(5000, len(filings_df)), random_state=82)
    # 2. Process in parallel
    print("\n[2/3] Sampling paragraphs in parallel...")
    all_sampled_data = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Create a future for each URL
        futures = {
            executor.submit(sample_paragraphs_from_filing, args.db_path, row.url, row.year, args.sample_rate)
            for row in filings_df.itertuples(index=False)
        }

        # Collect results as they complete
        for future in tqdm(as_completed(futures), total=len(filings_df), desc="Processing Filings"):
            result = future.result()
            if result:
                all_sampled_data.extend(result)

    print(f"  -> Collected {len(all_sampled_data):,} sampled texts.")

    # 3. Save to Parquet
    print(f"\n[3/3] Saving to Parquet file '{args.output_path}'...")
    df = pd.DataFrame(all_sampled_data)
    # Drop empty or duplicates
    df = df.dropna(subset=["text"]).drop_duplicates(subset="text")
    df.to_parquet(args.output_path, index=False)

    print("\n✨ Dataset creation complete!")

#%%
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a Parquet dataset from SEC filing text in a SQLite DB.")
    parser.add_argument("--db_path", type=str, default=DB_PATH, help="Path to the source SQLite database.")
    parser.add_argument("--output_path", type=str, default=OUTPUT_PARQUET_PATH, help="Path to save the output Parquet file.")
    parser.add_argument("--sample_rate", type=float, default=0.5, help="Fraction of paragraphs to sample from each filing (0.0 to 1.0).")
    parser.add_argument("--workers", type=int, default=mp.cpu_count() - 1, help="Number of parallel worker processes to use.")
    
    args = parser.parse_args()
    main(args)

# %%
