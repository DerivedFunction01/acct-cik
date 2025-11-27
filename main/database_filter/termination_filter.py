# final_cleanup.py (Phase 5)

import sqlite3
import json
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
import re

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
    ANCHOR_TAG,
)

# --- SALVATION LOGIC UPDATE ---
# We split strong verbs into "Usage" (Salvation) vs "Transactional" (Neutral).
# "We Entered" + "Expired" = DEAD.
# "We Use" + "Expired" = ALIVE.

USAGE_VERBS = [
    r"use(?:s|d|ing)?",
    r"utiliz(?:e|es|ed|ing)",
    r"employ(?:s|ed|ing)?",
    r"hold(?:s|ing)?",  # "Held" is ambiguous (past), "Holds" is active
    r"have",
    r"maintain(?:s|ed|ing)?",
    r"possess(?:e|es|ed|ing)?",
    r"hedg(?:e|es|ed|ing)",
    r"manag(?:e|es|ed|ing)",
]

# Explicit terms that indicate survival despite termination keywords
SALVATION_TERMS = [r"new", r"current", r"replace", r"remain"]

# Combine: State (Outstanding) + Indicators (Currently) + Terms (New) + Usage Verbs (Hold)
SALVATION_PATTERN_STR = build_alternation(
    SALVATION_TERMS + ACTIVE_INDICATORS + USAGE_VERBS
)

SALVATION_REGEX = re.compile(
    rf"(?:{ACTIVE_STATE_REGEX.pattern}|{SALVATION_PATTERN_STR})", re.IGNORECASE
)


# =============================================================================
# DB SETUP & I/O (Unchanged)
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

        # --- STEP 1: PARAGRAPH LEVEL CHECK (The Nuclear Option) ---
        has_termination = bool(TERMINATION_REGEX.search(paragraph))

        if has_termination:
            # Check for "Salvation" (Usage Verbs, Active State, New/Remaining)
            has_salvation = bool(SALVATION_REGEX.search(paragraph))

            if not has_salvation:
                # NUCLEAR OPTION: No usage/active signals found.
                # Assume the termination applies to the entire block.
                discards.append((url, paragraph, "termination_entire_block_removed"))
                continue

        # --- STEP 2: SENTENCE LEVEL FILTERING ---
        # If we reached here, the block survived. Now surgically remove the dead parts.

        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]
        kept_atomic = []

        for sent in atomic_sentences:
            # If this specific sentence is the one terminating, kill it.
            if TERMINATION_REGEX.search(sent):
                # OPTIMIZATION: If this sentence IS the Anchor, and we just killed it,
                # we don't need to do anything special here because 'validate_instrument_retention'
                # will see the missing anchor and kill the zombies automatically.
                discards.append((url, sent, "termination_clause"))
                continue

            kept_atomic.append(sent)

        # Re-assemble
        if kept_atomic:
            paragraph_text = " ".join(kept_atomic)
            final_paragraphs.append(paragraph_text)
            final_categories.append(category)

    # --- STEP 3: FINAL ANCHOR VALIDATION ---
    # This cleans up any "Zombie Context" left over from Step 2
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
