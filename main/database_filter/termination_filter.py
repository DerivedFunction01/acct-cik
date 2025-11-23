# final_cleanup.py
# =============================================================================
# PHASE 5: YEAR-END ACTIVE USER ISOLATION (SINGLE DB OUTPUT)
# =============================================================================
# Refines the dataset by moving "termination" clauses to the discard table.
#
# Architecture:
# - Input: active_data.db (Contains all mentions of use during the year)
# - Output: active_data2.db
#
# Logic:
# 1. Splits paragraphs into atomic sentences.
# 2. If a sentence matches TERMINATION_REGEX ("expired", "matured", "settled"):
#    - Move it to the `discarded_sentences` table (Reason: "termination_clause").
# 3. If a sentence describes active use:
#    - Keep it in the `webpage_result` (matches) table.
#
# Result Interpretation:
# - Company with Matches != []: Active Year-End User.
# - Company with Matches == [] AND Discards > 0: Active During Year, Terminated Year-End.
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
FINAL_DB_PATH = "active_data2.db"

from derivative_regex import (
    SENTENCE_SPLIT_PATTERN,
    TERMINATION_REGEX,
    ACTIVE_STATE_REGEX,
    ACTIVE_INDICATORS,
    check_for_instrument,
    validate_instrument_retention,
    build_alternation,
)
import re

# Create a "Salvation" regex - words that indicate something survives the termination
# Combining ACTIVE_STATE ("outstanding") with explicit "New" indicators
SALVATION_TERMS = [r"new", r"current", r"replace", r"remain"]
SALVATION_PATTERN = build_alternation(SALVATION_TERMS + ACTIVE_INDICATORS)
SALVATION_REGEX = re.compile(
    rf"(?:{ACTIVE_STATE_REGEX.pattern}|{SALVATION_PATTERN})", re.IGNORECASE
)

# =============================================================================
# DB SETUP
# =============================================================================


def setup_db():
    if Path(FINAL_DB_PATH).exists():
        Path(FINAL_DB_PATH).unlink()

    conn = sqlite3.connect(FINAL_DB_PATH)
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

    # Discard Tracking Table
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

    c.execute("CREATE INDEX IF NOT EXISTS idx_url ON webpage_result (url)")
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


def write_batch(batch):
    if not batch:
        return
    conn = sqlite3.connect(FINAL_DB_PATH, timeout=60)
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
        print(f"Write error: {e}")
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

    for paragraph, category in zip(paragraphs, categories):
        if "<TABLE>" in paragraph:
            final_paragraphs.append(paragraph)
            final_categories.append(category)
            continue

        # --- STEP 1: PARAGRAPH LEVEL CHECK ---
        has_termination = bool(TERMINATION_REGEX.search(paragraph))

        # If termination exists, check if there is "Salvation" (evidence of remaining position)
        # We assume if they say "expired", the whole block is dead UNLESS they explicitly say "outstanding/new/remain"
        if has_termination:
            has_salvation = bool(SALVATION_REGEX.search(paragraph))

            if not has_salvation:
                # NUCLEAR OPTION: The whole paragraph describes a dead instrument.
                # Discard the whole thing to prevent "We entered" from surviving alone.
                discards.append((url, paragraph, "termination_entire_block_removed"))
                continue

            # If has_salvation is True, we proceed to sentence-level filtering (Churn scenario)

        # --- STEP 2: SENTENCE LEVEL FILTERING ---
        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]
        kept_atomic = []

        for sent in atomic_sentences:
            # If sentence explicitly describes termination, remove it
            # (Even in a "Churn" paragraph, we don't want the specific "it expired" sentence)
            if TERMINATION_REGEX.search(sent):
                discards.append((url, sent, "termination_clause"))
                continue

            kept_atomic.append(sent)

        if kept_atomic:
            final_paragraphs.append(" ".join(kept_atomic))
            final_categories.append(category)

    # Final Validation (as before)
    final_paragraphs, final_categories, validation_discards = (
        validate_instrument_retention(
            final_paragraphs, final_categories, url, strict=False
        )
    )
    discards.extend(validation_discards)

    if final_paragraphs:
        return (
            url,
            json.dumps(final_paragraphs),
            json.dumps(final_categories),
            cik,
            year,
            discards,
        )

    return (url, "[]", "[]", cik, year, discards) if discards else None

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 90)
    print("PHASE 5: FINAL CLEANUP (Termination Isolation)")
    print("=" * 90)

    setup_db()
    data = get_source_data()

    if not data:
        print("❌ No data found in source database.")
    else:
        print(f"Processing {len(data):,} records...")

        batch = []
        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            results = executor.map(process_company, data)

            for result in tqdm(results, total=len(data)):
                if not result:
                    continue

                batch.append(result)

                if len(batch) >= BATCH_SIZE:
                    write_batch(batch)
                    batch = []

        if batch:
            write_batch(batch)

    print("\n✅ Done.")
    print(f"Final Processed Data saved to: {FINAL_DB_PATH}")
    print(
        "You can now run comparison scripts on the 'matches' vs 'discarded_sentences' tables."
    )
