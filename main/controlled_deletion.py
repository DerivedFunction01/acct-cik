# =============================================================================
# POST-CLASSIFICATION PAST-YEAR DELETION SCRIPT
# =============================================================================
# This script performs a second-stage filtering on the database after an initial
# classification. It is designed to remove sentences that primarily reference
# historical data, focusing the dataset on indicators of current derivative use.
#
# Workflow:
# 1. Reads 3-sentence paragraphs from the `web_data.db` database.
# 2. Fetches the corresponding reporting year for each filing.
# 3. For each paragraph, it splits it into individual sentences.
# 4. It extracts all years from each sentence.
# 5. A sentence is DISCARDED if the latest year mentioned in it is less
#    than the filing's reporting year.
# 6. Sentences with no year mentioned are KEPT by default.
# 7. The remaining, relevant sentences are re-assembled and saved to a new
#    `final_web_data.db`.
# =============================================================================
# %%
import sqlite3
import json
import re
from pathlib import Path
from tqdm import tqdm
from typing import List, Tuple, Optional, Dict
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time

# =============================================================================
# CONFIGURATION
# =============================================================================


def get_worker_count():
    """Auto-detects CPU cores to set worker count."""
    cpu_cores = mp.cpu_count()
    num_workers = max(1, cpu_cores - 1)
    print(
        f"🖥️  System Detected: {cpu_cores} CPU cores, setting NUM_WORKERS to {num_workers}"
    )
    return num_workers


NUM_WORKERS = get_worker_count()
BATCH_SIZE = 1000
SOURCE_DB_PATH = "web_data.db"
FINAL_DB_PATH = "final_web_data.db"
try:
    from derivative_regex import SENTENCE_SPLIT_PATTERN, YEAR_REGEX
except Exception:
    from .derivative_regex import SENTENCE_SPLIT_PATTERN, YEAR_REGEX


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def setup_final_db():
    """Creates the final database with the required schema."""
    if Path(FINAL_DB_PATH).exists():
        Path(FINAL_DB_PATH).unlink()
        print(f"🗑️  Deleted existing '{FINAL_DB_PATH}' to start fresh.")

    conn = sqlite3.connect(FINAL_DB_PATH)
    c = conn.cursor()
    # Create tables to mirror the source structure
    c.execute("CREATE TABLE webpage_result (url TEXT PRIMARY KEY, matches TEXT)")
    c.execute(
        "CREATE TABLE report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
    )
    c.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()
    print(f"✅ Created new database: '{FINAL_DB_PATH}'")


def get_source_data() -> Tuple[List[Tuple[str, str]], Dict[str, Tuple[int, int]]]:
    """Fetches all webpage results and a map of URL to reporting year."""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()

    print("📖 Reading webpage results from source DB...")
    c.execute("SELECT url, matches FROM webpage_result WHERE url IS NOT NULL")
    webpage_data = c.fetchall()

    print("🧠 Mapping URLs to reporting years...")
    c.execute(
        "SELECT url, year FROM report_data WHERE url IS NOT NULL AND year IS NOT NULL"
    )
    metadata_map = {row[0]: (row[1], row[2]) for row in c.fetchall()}  # (cik, year)

    conn.close()
    return webpage_data, metadata_map


def write_batch_to_db(batch: List[Tuple]):
    if not batch:
        return

    conn = sqlite3.connect(FINAL_DB_PATH, timeout=30)
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        c.executemany(
            "INSERT INTO webpage_result (url, matches) VALUES (?, ?)",
            [(url, json.dumps(matches)) for url, matches, cik, year in batch],
        )
        c.executemany(
            "INSERT INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(url, cik, year) for url, matches, cik, year in batch],
        )
        conn.commit()
    except Exception as e:
        print(f"Batch write failed: {e}")
        conn.rollback()
    finally:
        conn.close()


# =============================================================================
# WORKER FUNCTION
# =============================================================================


def filter_item_by_year(
    item: Tuple[str, str], metadata_map: Dict[str, Tuple[int, int]]
) -> Optional[Tuple[str, List[str], int, int]]:
    """
    Worker function to process a single filing's paragraphs.
    """
    url, matches_json = item
    metadata = metadata_map.get(url)
    if not metadata:
        return None
    cik, reporting_year = metadata

    # Skip if we don't have a reporting year for this URL
    if reporting_year is None:
        return None

    try:
        paragraphs = json.loads(matches_json)
        if not isinstance(paragraphs, list):
            return None
    except (json.JSONDecodeError, TypeError):
        return None

    final_paragraphs = []
    for para in paragraphs:
        sentences = SENTENCE_SPLIT_PATTERN.split(para)
        sentences_to_keep = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            extracted_years = [int(y) for y in YEAR_REGEX.findall(sentence)]

            # Rule: Keep sentence if no year is found
            if not extracted_years:
                sentences_to_keep.append(sentence)
                continue

            # Rule: Keep sentence if its max year is at least the reporting year
            max_extracted_year = max(extracted_years)
            if max_extracted_year >= reporting_year:
                sentences_to_keep.append(sentence)

        # Only add the paragraph back if it still has content
        if sentences_to_keep:
            final_paragraphs.append(" ".join(sentences_to_keep))

    if final_paragraphs:
        # We need CIK and Year for the new report_data table
        # This is a bit inefficient but necessary. A join in the initial query
        # would be better if the DB structure allowed it easily.
        # For now, we just pass it through.
        return (
            url,
            final_paragraphs,
            cik,
            reporting_year,
        )

    return None


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("🚀 Starting Stage 2 Filtering: Past-Year Deletion")
    print("=" * 80)

    setup_final_db()
    webpage_data, year_map = get_source_data()

    if not webpage_data:
        print("❌ No data found in source database. Exiting.")
    else:
        print(f"Found {len(webpage_data):,} records to process.")

        processed_results = []
        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            # Create a list of arguments for the worker function
            webpage_data, metadata_map = get_source_data()

            # In executor loop:
            tasks = [(item, metadata_map) for item in webpage_data]
            results_iter = executor.map(filter_item_by_year, *zip(*tasks))

            batch = []
            for result in tqdm(
                results_iter, total=len(webpage_data), desc="Filtering by Year"
            ):
                if result:
                    batch.append(result)
                    if len(batch) >= BATCH_SIZE:
                        write_batch_to_db(batch)
                        batch = []

            # Write any remaining items in the last batch
            if batch:
                write_batch_to_db(batch)

    print("\n" + "=" * 80)
    print("🎉 Filtering complete!")
    print(f"✅ Final, cleaned data has been saved to '{FINAL_DB_PATH}'.")
    print("=" * 80)

# %%
