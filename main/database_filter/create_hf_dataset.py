import sqlite3
import json
import random
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import pandas as pd
from tqdm import tqdm
import re
from typing import List, Tuple, Dict, Any, Callable

# NOTE: Assuming policy_config.py is in the same directory and contains
# POLICY_KEYWORD_SETS and DEFAULT_EXTRACTION_CONFIG
from derivative_regex import (
    SENTENCE_SPLIT_PATTERN,
    STRICT_NOTIONAL_REGEX,
    VERB_USE_REGEX,
)
from policy_config import POLICY_KEYWORD_SETS, DEFAULT_EXTRACTION_CONFIG

# =============================================================================
# GLOBAL CONFIGURATION LOAD
# =============================================================================

DB_PATH = DEFAULT_EXTRACTION_CONFIG["DB_PATH"]
TABLE_NAME = DEFAULT_EXTRACTION_CONFIG["TABLE_NAME"]
COLUMN_NAME = DEFAULT_EXTRACTION_CONFIG["COLUMN_NAME"]
MAX_SAMPLES_PER_FILING = DEFAULT_EXTRACTION_CONFIG["MAX_SAMPLES_PER_FILING"]
MAX_FILINGS_TO_SAMPLE = DEFAULT_EXTRACTION_CONFIG["MAX_FILINGS_TO_SAMPLE"]

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

QUANTITY_INDICATORS_TO_EXCLUDE = [
    r"\$[ ]?\d[\d,\.]*",  # $100, $1,000.00, $ 50
    r"\b€[ ]?\d[\d,\.]*",  # €50
    r"\b£[ ]?\d[\d,\.]*",  # £50
    r"\d[\d,\.]*\s+(?:million|billion|trillion)\b",  # 5 million, 1.2 billion
    r"\b(?:MM|BN|TR)\b",  # MM (Millions), BN (Billions), TR (Trillions)
    r"\b(?:thousands?|millions?|billions?)\b",  # full words
    r"\b\d+,\d{3}\b",  # General numbers with comma separators (e.g., 100,000)
]
NUMERIC_QUANTITY_EXCLUSION_REGEX = re.compile(
    r"(?i)" + "|".join(QUANTITY_INDICATORS_TO_EXCLUDE)
)

def get_extraction_details(key: str) -> Tuple[str, re.Pattern]:
    """
    Retrieves the label prefix and compiled regex for a given policy key.

    Args:
        key: The key from POLICY_KEYWORD_SETS (e.g., 'fair_value_hierarchy').

    Returns:
        Tuple of (label_prefix, compiled_regex)

    Raises:
        ValueError: If the key is not found.
    """
    if key not in POLICY_KEYWORD_SETS:
        raise ValueError(f"Unknown policy key: {key}")

    prefix, keywords = POLICY_KEYWORD_SETS[key]

    # Combine keywords into a case-insensitive regex pattern
    # NOTE: This ensures we ignore explicit numeric dollar values when searching
    regex_pattern = r"(?i)" + "|".join(keywords)

    return prefix, re.compile(regex_pattern)


# =============================================================================
# MODULAR STAGE FUNCTIONS
# =============================================================================


def fetch_filings_metadata(db_path: str) -> pd.DataFrame:
    """Fetches all URLs and years from the report_data table."""
    conn = sqlite3.connect(db_path)
    try:
        query = f"""
            SELECT t1.url, t2.year
            FROM {TABLE_NAME} t1
            JOIN report_data t2 ON t1.url = t2.url
            WHERE t1.{COLUMN_NAME} IS NOT NULL AND t2.year IS NOT NULL
        """
        filings_df = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    return filings_df


def process_filings_in_parallel(
    filings_df: pd.DataFrame,
    db_path: str,
    extraction_function: Callable,
    max_workers: int,
    policy_key: str,
) -> List[Dict[str, Any]]:
    """Executes the specific extraction function across all filings in parallel."""
    all_extracted_data = []

    # Randomly sample a smaller set of filings for efficiency
    filings_df = filings_df.sample(
        n=min(MAX_FILINGS_TO_SAMPLE, len(filings_df)),
        random_state=DEFAULT_EXTRACTION_CONFIG["RANDOM_SEED"],
    )

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                extraction_function,
                db_path,
                row.url,
                row.year,
                MAX_SAMPLES_PER_FILING,
                policy_key,
            )
            for row in filings_df.itertuples(index=False)
        }

        for future in tqdm(
            as_completed(futures),
            total=len(filings_df),
            desc=f"Extracting {policy_key.replace('_', ' ').title()}",
        ):
            result = future.result()
            if result:
                all_extracted_data.extend(result)

    return all_extracted_data


def save_to_parquet(data: List[Dict[str, Any]], output_path: str):
    """Converts the collected data to a DataFrame and saves it."""
    df = pd.DataFrame(data)
    # Drop empty or duplicates
    df = df.dropna(subset=["text"]).drop_duplicates(subset="text")
    df.to_parquet(output_path, index=False)


# =============================================================================
# EXTRACTION WORKER FUNCTION (SWAPPABLE COMPONENT)
# =============================================================================


# =============================================================================
# EXTRACTION WORKER FUNCTION (WITH GROUP MERGE)
# =============================================================================


def extract_policy_paragraphs(
    db_path: str, url: str, year: int, max_samples_per_filing: int, policy_key: str
) -> list[dict]:
    """
    Worker function that collects ALL policy sentences from the filing and
    merges them into dense, multi-sentence samples (Group Merge).
    """
    try:
        label_type, policy_regex = get_extraction_details(policy_key)
    except ValueError:
        return []

    try:
        # --- 1. FETCH AND PARSE DATA ---
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT {COLUMN_NAME} FROM {TABLE_NAME} WHERE url = ?", (url,))
        result = cursor.fetchone()
        conn.close()

        if not result or not result[0]:
            return []
        paragraphs = json.loads(result[0])
        if not isinstance(paragraphs, list):
            return []

        # --- 2. COLLECT ALL POLICY SENTENCES ACROSS FILING ---
        all_policy_candidates = []

        for paragraph in paragraphs:
            if paragraph.find("<") != -1 or len(paragraph.strip()) < 50:
                continue

            # Check paragraph first for efficiency
            if policy_regex.search(paragraph):
                sentences = SENTENCE_SPLIT_PATTERN.split(paragraph)

                for sent in sentences:
                    # Apply specific criteria for policy sentences (Max Munch)
                    if len(sent) > 300:
                        continue  # Skip large tables/fragments

                    if policy_regex.search(sent):
                        # Filter out quantitative or usage signals
                        quant_check = (
                            NUMERIC_QUANTITY_EXCLUSION_REGEX.search(sent)
                            or STRICT_NOTIONAL_REGEX.search(sent)
                            or VERB_USE_REGEX.search(sent)
                        )

                        if not quant_check:
                            # Keep the sentence for later merging
                            all_policy_candidates.append(sent)

        # --- 3. GROUP MERGE AND SAMPLE GENERATION ---

        if not all_policy_candidates:
            return []

        extracted_samples = []
        max_sentences_per_sample = 5  # Create dense samples of 3-5 sentences

        # Determine number of merged samples to create (up to max_samples_per_filing)
        num_samples_to_create = min(
            max_samples_per_filing,
            len(all_policy_candidates) // max_sentences_per_sample,
        )

        # If the candidate list is short, ensure at least one merged sample is created
        if num_samples_to_create == 0 and len(all_policy_candidates) >= 2:
            num_samples_to_create = 1

        for i in range(num_samples_to_create):
            # Randomly sample 3 to 5 sentences without replacement
            sample_size = random.randint(3, max_sentences_per_sample)

            # Ensure sample size doesn't exceed remaining candidates
            if len(all_policy_candidates) < sample_size:
                sample_size = len(all_policy_candidates)

            # Select sentences, remove them from the pool for non-replacement behavior
            # Shuffling the candidates ensures variety if we don't fully exhaust the list
            random.shuffle(all_policy_candidates)
            sample_sentences = [all_policy_candidates.pop() for _ in range(sample_size)]

            if sample_sentences:
                text = " ".join(sample_sentences).strip()

                extracted_samples.append(
                    {
                        "text": text,
                        "url": url,
                        "year": year,
                        "label_type": label_type,
                        "policy_key": policy_key,
                    }
                )

        return extracted_samples

    except (sqlite3.Error, json.JSONDecodeError, TypeError) as e:
        print(f"Warning: Error processing {url} ({policy_key} Extraction): {e}")
        return []


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def run_extraction_pipeline(args, policy_key: str):
    """
    Main function to orchestrate the dataset creation for a single policy key.
    """
    output_path = (
        f"{DEFAULT_EXTRACTION_CONFIG['OUTPUT_PARQUET_PATH_BASE']}_{policy_key}.parquet"
    )

    print("🚀 Starting modular policy extraction...")
    print(f"   Source DB: {args.db_path}")
    print(f"   Target Key: {policy_key}")
    print(f"   Output File: {output_path}")
    print(f"   Workers: {args.workers}")

    # 1. Fetch metadata
    print("\n[1/3] Fetching list of filings to process...")
    filings_df = fetch_filings_metadata(args.db_path)
    print(f"  -> Found {len(filings_df):,} filings with year information.")

    # 2. Process in parallel using the provided extraction function
    print("\n[2/3] Extracting policy paragraphs in parallel...")
    all_extracted_data = process_filings_in_parallel(
        filings_df, args.db_path, extract_policy_paragraphs, args.workers, policy_key
    )
    print(f"  -> Collected {len(all_extracted_data):,} policy texts.")

    # 3. Save to Parquet
    print(f"\n[3/3] Saving to Parquet file '{output_path}'...")
    save_to_parquet(all_extracted_data, output_path)

    print("\n✨ Dataset creation complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a Parquet dataset from SEC filing text in a SQLite DB."
    )
    parser.add_argument(
        "--db_path",
        type=str,
        default=DB_PATH,
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=mp.cpu_count() - 1,
        help="Number of parallel worker processes to use.",
    )
    parser.add_argument(
        "--key",
        type=str,
        default="fair_value_hierarchy",
        help="The policy key to extract (e.g., 'fair_value_hierarchy').",
    )

    args = parser.parse_args()

    # --- Execute the Pipeline ---
    run_extraction_pipeline(args, args.key)
