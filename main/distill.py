import sqlite3
import pandas as pd
import json
from tqdm import tqdm
from pathlib import Path
import re

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "web_data.db"
OUTPUT_PATH = "high_quality_snippets.parquet"

# --- Text Filtering Parameters ---
MIN_TEXT_LENGTH = 500
MAX_TEXT_LENGTH = 1500
MAX_DIGIT_RATIO = 0.15  # Reject if more than 15% of characters are digits

# --- Concurrency ---
# HELPER FUNCTIONS
# =============================================================================

def is_high_quality(text: str) -> bool:
    """
    Applies filtering logic to determine if a text snippet is high-quality.
    This is the critical function to filter out fragmented or table-like text.
    """
    if not text or not isinstance(text, str):
        return False

    # 1. Filter by length
    if not (MIN_TEXT_LENGTH <= len(text) <= MAX_TEXT_LENGTH):
        return False

    # 2. Filter by digit ratio (to exclude compressed tables)
    num_digits = sum(c.isdigit() for c in text)
    digit_ratio = num_digits / len(text)
    if digit_ratio > MAX_DIGIT_RATIO:
        return False
        
    # 3. Filter out text that looks like a list of document names
    if re.search(r'\.htm|\.txt|exhibit \d+', text, re.IGNORECASE):
        return False

    return True

def fetch_webpage_results() -> pd.DataFrame:
    """Fetches all records from the webpage_result table."""
    print(f"Reading from database: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as conn:
        try:
            df = pd.read_sql_query("SELECT url, matches FROM webpage_result", conn)
            print(f"Found {len(df)} records in webpage_result table.")
            return df
        except sqlite3.DatabaseError:
            print("ERROR: 'webpage_result' table not found or database is empty.")
            return pd.DataFrame()

# =============================================================================
# MAIN SCRIPT LOGIC
# =============================================================================

def main():
    """
    Main function to filter for high-quality text and save for inspection.
    """
    # 1. Load dependencies
    df = fetch_webpage_results()
    if df.empty:
        return

    # 2. Filter for high-quality text snippets
    high_quality_snippets = []
    print("Filtering for high-quality text snippets...")
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Filtering Snippets"):
        try:
            matches_data = json.loads(row['matches'])
            for category, snippets in matches_data.items():
                if not isinstance(snippets, list): continue
                for snippet in snippets:
                    if is_high_quality(snippet):
                        high_quality_snippets.append(snippet)
        except (json.JSONDecodeError, TypeError):
            continue # Skip rows with invalid JSON

    print(f"Found {len(high_quality_snippets)} high-quality text snippets.")
    if not high_quality_snippets:
        print("No high-quality snippets found to save. Exiting.")
        return

    # 3. Save the filtered snippets to a parquet file for inspection
    print(f"\nSaving {len(high_quality_snippets)} snippets to '{OUTPUT_PATH}'...")
    output_df = pd.DataFrame(high_quality_snippets, columns=['text'])
    output_df.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Successfully saved high-quality snippets for inspection.")

if __name__ == "__main__":
    main()