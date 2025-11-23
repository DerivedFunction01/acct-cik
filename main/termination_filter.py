# final_cleanup.py
# =============================================================================
# PHASE 5: YEAR-END ACTIVE USER ISOLATION
# =============================================================================
# Distinguishes between "Active Year-End Users" and "Terminated Users".
# Now tracks discarded termination clauses in the database.
#
# Logic:
# 1. Reads from `active_data.db` (which contains ALL active usage during year).
# 2. Deletes any sentence matching TERMINATION_REGEX ("expired", "matured").
# 3. Checks what remains:
#    - If sentences remain -> User is Active Year-End (Partial termination or full active).
#      * Deleted termination sentences are logged to `discarded_sentences`
#    - If NO sentences remain -> User was Active During Year, but Terminated Year-End.
#      * Entire record moved to `terminated_during_year.db`
# =============================================================================

import sqlite3
import json
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
from typing import List, Tuple, Dict, Any

# =============================================================================
# CONFIGURATION
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "active_data.db"
ACTIVE_YEAR_END_DB = "active_year_end.db"
TERMINATED_DB = "terminated_during_year.db"

try:
    from derivative_regex import SENTENCE_SPLIT_PATTERN, TERMINATION_REGEX
except ImportError:
    raise ImportError("Missing derivative_regex.py or TERMINATION_REGEX.")

# =============================================================================
# DB SETUP
# =============================================================================


def setup_dbs():
    for db_path in [ACTIVE_YEAR_END_DB, TERMINATED_DB]:
        if Path(db_path).exists():
            Path(db_path).unlink()

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Main Data Tables
        c.execute("CREATE TABLE webpage_result (url TEXT PRIMARY KEY, matches TEXT)")
        c.execute(
            """
            CREATE TABLE category (
                url TEXT PRIMARY KEY, 
                categories TEXT, 
                FOREIGN KEY(url) REFERENCES webpage_result(url)
            )
        """
        )
        c.execute(
            "CREATE TABLE report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
        )

        # Discard Tracking Table (Consistent with pipeline)
        c.execute(
            """
            CREATE TABLE discarded_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT, 
                sentence TEXT, 
                discard_reason TEXT
            )
        """
        )

        c.execute("PRAGMA journal_mode=WAL;")
        conn.commit()
        conn.close()


def get_source_data():
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT wr.url, wr.matches, c.categories, rd.cik, rd.year
        FROM webpage_result wr
        JOIN category c ON wr.url = c.url
        JOIN report_data rd ON wr.url = rd.url
    """
    )
    data = c.fetchall()
    conn.close()
    return data


def write_batch(batch, db_path):
    if not batch:
        return
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")

        # Unpack results: (url, matches, cats, cik, year, discards)
        webpage_rows = [(b[0], b[1]) for b in batch]
        cat_rows = [(b[0], b[2]) for b in batch]
        meta_rows = [(b[0], b[3], b[4]) for b in batch]

        c.executemany("INSERT INTO webpage_result VALUES (?, ?)", webpage_rows)
        c.executemany("INSERT INTO category VALUES (?, ?)", cat_rows)
        c.executemany("INSERT INTO report_data VALUES (?, ?, ?)", meta_rows)

        # Handle discards
        all_discards = []
        for b in batch:
            if b[5]:  # Check if discards list exists
                all_discards.extend(b[5])

        if all_discards:
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                all_discards,
            )

        conn.commit()
    except Exception as e:
        print(f"Write error on {db_path}: {e}")
        conn.rollback()
    finally:
        conn.close()


# =============================================================================
# LOGIC
# =============================================================================


def process_company(item):
    url, matches_json, cats_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
        categories = json.loads(cats_json)
    except:
        return None

    final_paragraphs = []
    final_categories = []
    discards = []

    # 1. Sentence-Level Filtering
    for paragraph, category in zip(paragraphs, categories):
        # ADD THIS BLOCK:
        if "<TABLE>" in paragraph.upper():
            # Keep table as-is without processing
            final_paragraphs.append(paragraph)  # Special 'table' category
            final_categories.append("table")
            continue
        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]
        kept_atomic = []

        for sent in atomic_sentences:
            # If sentence describes termination, DELETE it from Active set
            if TERMINATION_REGEX.search(sent):
                discards.append((url, sent, "termination_clause"))
                continue
            kept_atomic.append(sent)

        if kept_atomic:
            final_paragraphs.append(" ".join(kept_atomic))
            final_categories.append(category)

    # 2. Classification & Packaging
    # If ANY sentences remain -> Active Year End
    if final_paragraphs:
        return "ACTIVE", (
            url,
            json.dumps(final_paragraphs),
            json.dumps(final_categories),
            cik,
            year,
            discards,  # Log the partial termination sentences here
        )

    # If NO sentences remain (but input wasn't empty) -> Terminated During Year
    # For the terminated DB, we usually keep the original text as proof of why they are there.
    # We pass an empty list for discards because we aren't "discarding" them from the Terminated DB;
    # they ARE the content of the Terminated DB.
    return "TERMINATED", (url, matches_json, cats_json, cik, year, [])


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 90)
    print("PHASE 5: SEPARATING YEAR-END ACTIVE vs. TERMINATED")
    print("=" * 90)

    setup_dbs()
    data = get_source_data()

    active_batch = []
    terminated_batch = []

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        results = executor.map(process_company, data)

        for status, result in tqdm(results, total=len(data)):
            if not result:
                continue

            if status == "ACTIVE":
                active_batch.append(result)
            else:
                terminated_batch.append(result)

            if len(active_batch) >= BATCH_SIZE:
                write_batch(active_batch, ACTIVE_YEAR_END_DB)
                active_batch = []

            if len(terminated_batch) >= BATCH_SIZE:
                write_batch(terminated_batch, TERMINATED_DB)
                terminated_batch = []

    # Final flush
    write_batch(active_batch, ACTIVE_YEAR_END_DB)
    write_batch(terminated_batch, TERMINATED_DB)

    print("\n✅ Done.")
    print(f"Active Year-End Users saved to: {ACTIVE_YEAR_END_DB}")
    print(f"Terminated Users saved to: {TERMINATED_DB}")
