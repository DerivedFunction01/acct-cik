# final_linguistic_filter.py
# =============================================================================
# PHASE 4: LINGUISTIC INTENT FILTERING
# =============================================================================
# Refines the dataset by removing "Potential", "Hypothetical", and "Absence"
# statements using the robust regexes defined in derivative_regex.py.
#
# Workflow:
# 1. Reads 3-sentence paragraphs from `current_data.db`.
# 2. Splits them into atomic sentences.
# 3. Applies linguistic filters (Potential, Negative Intent, Absence).
# 4. Saves only Active/Termination statements to `active_data.db`.
# =============================================================================

import sqlite3
import json
import multiprocessing as mp
import time
from pathlib import Path
from tqdm import tqdm
from typing import List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor

# =============================================================================
# CONFIGURATION
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "current_data.db"
FINAL_DB_PATH = "active_data.db"

# Import the robust, battle-tested regexes
from derivative_regex import (
    SENTENCE_SPLIT_PATTERN,
    POTENTIAL_REGEX,
    VAGUE_TIMING_REGEX,
    NEGATIVE_INTENT_REGEX,
    ABSENCE_REGEX,
    DID_NOT_HOLD_REGEX,
    check_for_instrument
)

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def setup_final_db():
    if Path(FINAL_DB_PATH).exists():
        Path(FINAL_DB_PATH).unlink()

    conn = sqlite3.connect(FINAL_DB_PATH)
    c = conn.cursor()

    # Standard Schema
    c.execute("CREATE TABLE webpage_result (url TEXT PRIMARY KEY, matches TEXT)")
    c.execute(
        """CREATE TABLE category (
            url TEXT PRIMARY KEY,
            categories TEXT, 
            FOREIGN KEY (url) REFERENCES webpage_result(url)
        )"""
    )
    c.execute(
        "CREATE TABLE report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
    )

    # Tracking Discards for Analysis
    c.execute(
        """CREATE TABLE discarded_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT, sentence TEXT, discard_reason TEXT)"""
    )

    c.execute("CREATE INDEX IF NOT EXISTS idx_url ON webpage_result (url)")
    c.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()


def get_source_data() -> List[Tuple]:
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    # Join text, categories, and metadata
    c.execute(
        """
        SELECT wr.url, wr.matches, c.categories, rd.cik, rd.year
        FROM webpage_result wr
        LEFT JOIN category c ON wr.url = c.url
        JOIN report_data rd ON wr.url = rd.url
        WHERE wr.matches IS NOT NULL AND wr.matches != '[]'
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

        # Prepare lists
        webpage_rows = [(b[0], b[1]) for b in batch]
        cat_rows = [(b[0], b[2]) for b in batch]
        meta_rows = [(b[0], b[3], b[4]) for b in batch]

        c.executemany("INSERT INTO webpage_result VALUES (?, ?)", webpage_rows)
        c.executemany("INSERT INTO category VALUES (?, ?)", cat_rows)
        c.executemany("INSERT INTO report_data VALUES (?, ?, ?)", meta_rows)

        discards = []
        for b in batch:
            discards.extend(b[5])

        if discards:
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                discards,
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Write error: {e}")
    finally:
        conn.close()


# =============================================================================
# FILTERING LOGIC
# =============================================================================


def process_item(item):
    url, matches_json, cats_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
        categories = json.loads(cats_json) if cats_json else []
    except:
        return None

    if not paragraphs:
        return None
    if not categories:
        categories = ["unknown"] * len(paragraphs)

    final_paragraphs = []
    final_categories = []
    discards = []

    for paragraph, category in zip(paragraphs, categories):

        # ADD THIS BLOCK:
        if "<TABLE>" in paragraph.upper():
            # Keep table as-is without processing
            final_paragraphs.append(paragraph)  # Special 'table' category
            final_categories.append(category)
            continue
        # Atomic split for precision
        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]
        kept_sentences = []

        for sent in atomic_sentences:
            original = sent

            # 1. Check POTENTIAL Use (May, Might, Seek to, Expect to use)
            if POTENTIAL_REGEX.search(sent):
                discards.append((url, original, "linguistic_potential_use"))
                continue

            # 2. Check VAGUE TIMING (From time to time, in the future)
            if VAGUE_TIMING_REGEX.search(sent):
                discards.append((url, original, "linguistic_vague_timing"))
                continue

            # 3. Check NEGATIVE INTENT (Does not intend, Has no plans)
            if NEGATIVE_INTENT_REGEX.search(sent):
                discards.append((url, original, "linguistic_negative_intent"))
                continue

            # 4. Check ABSENCE (No such outstanding positions)
            if ABSENCE_REGEX.search(sent):
                discards.append((url, original, "linguistic_explicit_absence"))
                continue

            # 5. Check DID NOT HOLD (Did not enter into derivatives)
            if DID_NOT_HOLD_REGEX.search(sent):
                discards.append((url, original, "linguistic_did_not_hold"))
                continue

            # 6. TERMINATION (Explicitly kept)
            # We don't filter these out, but we acknowledge them.
            # if TERMINATION_REGEX.search(sent): pass

            kept_sentences.append(sent)

        # Re-assemble paragraph if valid sentences remain
        if kept_sentences:
            final_paragraphs.append(" ".join(kept_sentences))
            final_categories.append(category)

    # -------------------------------------------------------------------------
    # FINAL SAFETY CHECK: Ensure instrument name survived cleaning
    # -------------------------------------------------------------------------
    # Filter out sentences where the cleaning process accidentally stripped
    # the actual instrument name (e.g., reducing "We use swaps to hedge" -> "We use to hedge")

    validated_paragraphs = []

    # Assuming final_paragraphs is a list of (text, category) tuples based on your Phase 2 script
    # If it is just a list of strings, remove the unpacking.
    for item in final_paragraphs:
        # Handle both tuple (text, cat) and string formats dynamically
        text = item[0] if isinstance(item, tuple) else item

        # strict=False: Allows "contracts", "instruments", "derivatives" (Broader)
        # strict=True:  Requires "ir swaps", "forward contract", "call options" (Stricter)
        if check_for_instrument(text, strict=False):
            validated_paragraphs.append(item)
        else:
            # Log it as a specific discard reason so you can debug regex over-pruning
            discards.append((url, text, "lost_instrument_reference"))

    if final_paragraphs:
        return (
            url,
            json.dumps(final_paragraphs),
            json.dumps(final_categories),
            cik,
            year,
            discards,
        )

    # Return discards even if file is empty now to track what happened
    return (url, "[]", "[]", cik, year, discards) if discards else None


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 90)
    print("PHASE 4: LINGUISTIC FILTERING (Active Data Generation)")
    print("=" * 90)

    setup_final_db()
    data = get_source_data()

    if not data:
        print("❌ No data found in source database (current_data.db).")
    else:
        print(f"Processing {len(data):,} records...")

        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            batch = []
            results = executor.map(process_item, data)

            for res in tqdm(results, total=len(data)):
                if not res:
                    continue

                # Logic: Save if there are matches OR discards (to track empty files)
                # But typically we only want valid rows in the main table
                if res[1] != "[]":
                    batch.append(res)

                # If you want to save discard reasons even for files that become empty,
                # you need to handle that in write_batch (it currently handles discards from the tuple)
                elif res[5]:  # If matches are empty but discards exist
                    batch.append(res)

                if len(batch) >= BATCH_SIZE:
                    write_batch(batch)
                    batch = []

            if batch:
                write_batch(batch)

    print(f"\n✅ Active User Dataset created: {FINAL_DB_PATH}")
