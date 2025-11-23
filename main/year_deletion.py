# year_deletion.py
# =============================================================================
# PHASE 3: PAST-YEAR DELETION & CATEGORY SYNC
# =============================================================================
# Filters sentences based on historical context while maintaining
# strict alignment between 'matches' (text) and 'categories' (labels).
#
# Workflow:
# 1. Reads parallel arrays (matches, categories) from `hedge_data.db`.
# 2. Splits paragraphs into atomic sentences.
# 3. Discards ONLY the sentences where max(year) < reporting_year.
# 4. Re-assembles surviving sentences into the paragraph.
# 5. Saves the synchronized results to `current_data.db`.
# =============================================================================

import sqlite3
import json
import multiprocessing as mp
import time
from pathlib import Path
from tqdm import tqdm
from typing import List, Tuple, Optional, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

# =============================================================================
# CONFIGURATION
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "hedge_data.db"
FINAL_DB_PATH = "current_data.db"

from derivative_regex import (
    YEAR_REGEX,
    PRIOR_PATTERN,
    SENTENCE_SPLIT_PATTERN,  # Ensure this is imported
    cleanup_fragment,
)


# =============================================================================
# DATABASE SETUP
# =============================================================================


def setup_final_db():
    """Creates the final database with parallel category storage."""
    if Path(FINAL_DB_PATH).exists():
        Path(FINAL_DB_PATH).unlink()

    conn = sqlite3.connect(FINAL_DB_PATH)
    c = conn.cursor()

    # 1. Text Data
    c.execute(
        """CREATE TABLE webpage_result (
            url TEXT PRIMARY KEY, 
            matches TEXT -- JSON array of filtered sentences
        )"""
    )

    # 2. Category Data (Parallel Array)
    c.execute(
        """CREATE TABLE category (
            url TEXT PRIMARY KEY,
            categories TEXT, -- JSON array of filtered categories
            FOREIGN KEY (url) REFERENCES webpage_result(url)
        )"""
    )

    # 3. Metadata
    c.execute(
        "CREATE TABLE report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
    )

    # 4. Discard Tracking
    c.execute(
        """CREATE TABLE discarded_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            sentence TEXT,
            discard_reason TEXT
        )"""
    )

    c.execute("CREATE INDEX IF NOT EXISTS idx_url ON webpage_result (url)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cat_url ON category (url)")
    c.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()
    print(f"✅ Created '{FINAL_DB_PATH}' with category tracking.")


def get_source_data() -> Tuple[List[Tuple], Dict[str, Tuple[int, int]]]:
    """
    Fetches matches AND categories from the source DB.
    """
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()

    print("📖 Reading data from source DB...")
    # Left join to be safe
    c.execute(
        """
        SELECT wr.url, wr.matches, c.categories 
        FROM webpage_result wr
        LEFT JOIN category c ON wr.url = c.url
        WHERE wr.matches IS NOT NULL
        """
    )
    webpage_data = c.fetchall()

    print("🧠 Mapping URLs to reporting years...")
    c.execute("SELECT url, cik, year FROM report_data WHERE year IS NOT NULL")
    metadata_map = {row[0]: (row[1], row[2]) for row in c.fetchall()}

    conn.close()
    return webpage_data, metadata_map


def write_batch_to_db(batch: List[Tuple]):
    if not batch:
        return

    conn = sqlite3.connect(FINAL_DB_PATH, timeout=60)
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA journal_mode = WAL")
    c = conn.cursor()

    try:
        c.execute("BEGIN TRANSACTION")

        webpage_rows = [(b[0], b[1]) for b in batch]
        category_rows = [(b[0], b[2]) for b in batch]
        report_rows = [(b[0], b[3], b[4]) for b in batch]

        c.executemany(
            "INSERT INTO webpage_result (url, matches) VALUES (?, ?)", webpage_rows
        )
        c.executemany(
            "INSERT INTO category (url, categories) VALUES (?, ?)", category_rows
        )
        c.executemany(
            "INSERT INTO report_data (url, cik, year) VALUES (?, ?, ?)", report_rows
        )

        discarded_rows = []
        for b in batch:
            for d in b[5]:
                discarded_rows.append(d)

        if discarded_rows:
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                discarded_rows,
            )

        conn.commit()
    except Exception as e:
        print(f"Batch write failed: {e}")
        conn.rollback()
    finally:
        conn.close()


# =============================================================================
# FILTERING LOGIC
# =============================================================================


def filter_item_by_year(
    item: Tuple[str, str, str], metadata_map: Dict[str, Tuple[int, int]]
) -> Optional[Tuple]:
    """
    Filters sub-sentences within paragraphs based on years.
    """
    url, matches_json, categories_json = item

    metadata = metadata_map.get(url)
    if not metadata:
        return None
    cik, reporting_year = metadata

    try:
        paragraphs = json.loads(matches_json)
        categories = json.loads(categories_json) if categories_json else []
    except (json.JSONDecodeError, TypeError):
        return None

    if not paragraphs:
        return None

    if not categories or len(categories) != len(paragraphs):
        categories = ["unknown"] * len(paragraphs)

    final_paragraphs = []
    final_categories = []
    discards = []

    # Iterate over the Paragraphs (Chunks)
    for paragraph, category in zip(paragraphs, categories):

        # 1. Split Paragraph into Atomic Sentences
        # The regex splits, but we need to ensure we don't get empty strings
        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]

        kept_atomic_sentences = []

        for sentence in atomic_sentences:
            original_sentence = sentence

            # 2. Check Logic Per Sentence
            has_prior_pattern = bool(PRIOR_PATTERN.search(sentence))
            extracted_years = [int(y) for y in YEAR_REGEX.findall(sentence) if y]

            # Case A: No year mentioned
            if not extracted_years:
                if has_prior_pattern:
                    discards.append((url, original_sentence, "prior_pattern_explicit"))
                    continue

                # Keep valid sentences without years
                kept_atomic_sentences.append(sentence)
                continue

            # Case B: Years present -> check against reporting year
            max_year = max(extracted_years)

            if max_year < reporting_year:
                discards.append((url, original_sentence, f"past_year_{max_year}"))
            else:
                # Current or future year -> Keep
                kept_atomic_sentences.append(sentence)

        # 3. Re-assemble Paragraph
        if kept_atomic_sentences:
            new_paragraph = ". ".join(kept_atomic_sentences) + ". "
            final_paragraphs.append(new_paragraph)
            final_categories.append(category)
        else:
            # If the entire paragraph was made of old sentences, it's fully dropped
            # The category is effectively dropped here too
            pass

    if final_paragraphs:
        return (
            url,
            json.dumps(final_paragraphs),
            json.dumps(final_categories),
            cik,
            reporting_year,
            discards,
        )

    return (url, "[]", "[]", cik, reporting_year, discards) if discards else None


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 90)
    print("PHASE 3: PAST-YEAR DELETION & CATEGORY SYNC")
    print("=" * 90)

    setup_final_db()
    webpage_data, metadata_map = get_source_data()

    if not webpage_data:
        print("❌ No data found in source database.")
    else:
        print(f"Found {len(webpage_data):,} records. Processing...")

        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = [
                executor.submit(filter_item_by_year, item, metadata_map)
                for item in webpage_data
            ]

            batch = []
            for future in tqdm(
                as_completed(futures), total=len(futures), desc="Filtering"
            ):
                result = future.result()
                if not result:
                    continue

                if result[1] != "[]":
                    batch.append(result)

                if len(batch) >= BATCH_SIZE:
                    write_batch_to_db(batch)
                    batch = []

            if batch:
                write_batch_to_db(batch)

    print("\n✅ Done. Final data in:", FINAL_DB_PATH)
