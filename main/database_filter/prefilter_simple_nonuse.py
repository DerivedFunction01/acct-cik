import sqlite3
import json
import re
import multiprocessing as mp
import time
from pathlib import Path
from typing import List, Tuple, Optional, Set
from tqdm import tqdm

from year_deletion import extract_years

# --- CONFIGURATION ---
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "prefiltered_data.db"  # Output from Step 1
TARGET_DB_PATH = "refined_data.db"  # Input for Step 3

# The token to append to deadweight paragraphs.
DEADWEIGHT_TOKEN = " _D "
# --- REGEX IMPORTS ---
from derivative_regex import (
    LOOSE_GEN_REGEX,
    POTENTIAL_REGEX,
    NEGATIVE_INTENT_REGEX,
    ABSENCE_REGEX,
    DID_NOT_HOLD_REGEX,
    SENTENCE_SPLIT_PATTERN,
    SOFT_CATEGORY_REGEX,
    SOFT_REGEX,
    TRADING_STATEMENTS_REGEX,
    TERMINATION_REGEX,
    VAGUE_TIMING_REGEX,
)

from final_verification import COUNTERPARTY_REGEX, QUANT_REGEX


def check_refinement_exclusions(text: str, year: Optional[int] = None) -> Optional[str]:
    """
    Checks for 'Deadweight' paragraphs that passed the hard pre-filter
    but are semantically useless for derivative classification.

    KEY SAFEGUARD: Many filters require has_potential=True to avoid
    removing legitimate 7A statements like:
    "We use IR swaps to hedge risk. We do not trade or speculate."
    (has explicit use but lacks numerics)

    TEMPORAL AWARENESS: Filters account for reporting year to distinguish
    current vs. historical statements.

    HISTORIC ACTIVITY DETECTION: Identifies paragraphs that only discuss
    past years + terminations (e.g., "In 2022 we terminated all swaps")
    without current year activity.
    """

    def has_instrument(text: str) -> bool:
        return bool(SOFT_REGEX.search(text))

    def is_current_or_no_year(sentence: str, reporting_year: Optional[int]) -> bool:
        """
        Returns True if sentence mentions current/reporting year OR no year at all.
        Returns False if sentence mentions only past years.
        """
        if not reporting_year:
            return True

        sent_years = extract_years(sentence)

        if not sent_years:
            return True

        if any(y >= reporting_year for y in sent_years):
            return True

        return False

    def has_only_past_years(text: str, reporting_year: Optional[int]) -> bool:
        """
        Returns True if text mentions ONLY past years (no current/future).
        Returns False if no years mentioned or any year >= reporting_year.
        """
        if not reporting_year:
            return False  # No year to compare against

        all_years = extract_years(text)

        if not all_years:
            return False  # No years mentioned = ambiguous, not "only past"

        # True only if ALL years are < reporting_year
        return all(y < reporting_year for y in all_years)

    has_potential = False
    has_absence = False
    has_trading_denial = False
    has_termination = False
    has_quant = False
    is_strictly_generic = True
    has_current_year_activity = (
        False  # NEW: tracks if current year is explicitly mentioned
    )

    if SOFT_CATEGORY_REGEX.search(text):
        is_strictly_generic = False

    sentences = SENTENCE_SPLIT_PATTERN.split(text)
    for sent in sentences:
        if has_instrument(sent):
            if POTENTIAL_REGEX.search(sent) or VAGUE_TIMING_REGEX.search(sent):
                has_potential = True
            if ABSENCE_REGEX.search(sent) or DID_NOT_HOLD_REGEX.search(sent):
                has_absence = True
            if TRADING_STATEMENTS_REGEX.search(sent):
                has_trading_denial = True
            if NEGATIVE_INTENT_REGEX.search(
                sent
            ) and not TRADING_STATEMENTS_REGEX.search(sent):
                has_absence = True

        # Check if sentence mentions current year (excluding termination context)
        if is_current_or_no_year(sent, year):
            # Only count if it's not JUST a termination sentence
            if not (TERMINATION_REGEX.search(sent) and LOOSE_GEN_REGEX.search(sent)):
                has_current_year_activity = True

        if QUANT_REGEX.search(sent) and LOOSE_GEN_REGEX.search(sent):
            if is_current_or_no_year(sent, year):
                has_quant = True

        if TERMINATION_REGEX.search(sent) and LOOSE_GEN_REGEX.search(sent):
            has_termination = True

    # === SAFE REMOVAL COMBINATIONS ===

    if has_potential:
        if is_strictly_generic and has_trading_denial:
            return "generic_potential_with_trading_denial"
        if has_absence:
            return "risk_boilerplate_nonuse"
        if has_termination: 
            return "potential_future_but_terminated"
    else:
        # NEW: Historic activity filter
        # "In 2022 did something. In 2024 we terminated swaps" (only past years + termination, no current activity)
        if (
            has_termination
            and not has_current_year_activity
            and has_only_past_years(text, year)
        ):
            return "historic_activity_with_termination"

        if has_trading_denial and is_strictly_generic and not has_quant:
            return "generic_policy_no_trade"

        if has_termination and has_absence:
            return "terminated_none_outstanding"

        if has_absence and not has_quant:
            return "stated_absence_no_active_signal"

        if has_trading_denial and has_absence:
            return "policy_no_use_no_trade"

    return None


def process_item(item: Tuple) -> Optional[Tuple]:
    """
    Firm-Level Filter with Token Injection:

    1. Scans paragraphs.
    2. If a paragraph is 'Deadweight', append an ANCHOR token to it.
    3. If a paragraph is Valid, keep as is.
    4. If at least one Valid paragraph exists, return the modified list (Valids + Anchors).
    5. If ALL are Deadweight, discard the firm.
    """
    url, matches_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    modified_paragraphs = []
    has_valid_signal = False
    all_discards_log = []  # We still track reasons in case we drop the firm entirely

    for p in paragraphs:
        reason = check_refinement_exclusions(p, year)

        if reason is None:
            # Case A: Valid Signal. Keep text exactly as is.
            has_valid_signal = True
            modified_paragraphs.append(p)
        else:
            # Case B: Deadweight. Append token to make it an 'Anchor'.
            # Downstream logic will see this token and know:
            # "Don't score this, but don't delete it either."
            modified_paragraphs.append(f"{DEADWEIGHT_TOKEN}{p}")

            # Log reason temporarily; only used if we return the "failure" tuple below
            all_discards_log.append((url, p, reason))

    # Firm-Level Decision
    if has_valid_signal:
        # CONDITION MET: Firm has at least one strong signal.
        # Return the MODIFIED list. Valid paragraphs are clean;
        # Weak paragraphs now have " <ANCHOR>" at the end.
        return (url, json.dumps(modified_paragraphs), cik, year, [])

    else:
        # CONDITION FAILED: No valid signal found.
        # Drop the firm entirely.
        return (url, json.dumps([]), cik, year, all_discards_log)


# --- DATABASE HELPERS ---


def setup_target_db(path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, matches TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS discarded_sentences (id INTEGER PRIMARY KEY, url TEXT, sentence TEXT, discard_reason TEXT)"
    )
    conn.commit()
    conn.close()


def get_processed_urls(path: str) -> Set[str]:
    """Get all URLs already processed in target DB"""
    if not Path(path).exists():
        return set()

    try:
        conn = sqlite3.connect(path)
        c = conn.cursor()
        c.execute("SELECT url FROM webpage_result")
        urls = {row[0] for row in c.fetchall()}
        conn.close()
        return urls
    except:
        return set()


def get_source_data(source_path: str, processed_urls: Set[str]):
    """Get unprocessed data from source DB"""
    conn = sqlite3.connect(source_path)
    c = conn.cursor()
    c.execute(
        """
        SELECT w.url, w.matches, r.cik, r.year 
        FROM webpage_result w 
        LEFT JOIN report_data r ON w.url = r.url
        WHERE w.matches IS NOT NULL
    """
    )
    data = c.fetchall()
    conn.close()

    # Filter to only unprocessed URLs
    unprocessed = [row for row in data if row[0] not in processed_urls]
    return unprocessed


# --- WORKER LOOP ---


def worker(data_chunk, out_queue):
    for item in data_chunk:
        res = process_item(item)
        if res:
            out_queue.put(res)
    out_queue.put(None)  # Signal done


def listener(queue, db_path, total_count):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()

    count = 0
    buffer_res = []
    buffer_disc = []

    with tqdm(total=total_count, unit="docs", desc="Processing") as pbar:
        workers_done = 0
        while workers_done < NUM_WORKERS:
            msg = queue.get()
            if msg is None:
                workers_done += 1
                continue

            url, matches, cik, year, discards = msg

            # Insert result (empty matches means firm was dropped, but we still mark it processed)
            buffer_res.append((url, matches, cik, year))

            if discards:
                buffer_disc.extend(discards)

            count += 1
            pbar.update(1)

            # Flush results when buffer is full
            if len(buffer_res) >= 1000:
                c.executemany(
                    "INSERT OR REPLACE INTO webpage_result (url, matches) VALUES (?, ?)",
                    [(x[0], x[1]) for x in buffer_res],
                )
                c.executemany(
                    "INSERT OR REPLACE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                    [(x[0], x[2], x[3]) for x in buffer_res],
                )
                buffer_res = []
                conn.commit()

            # Flush discards when buffer is full
            if len(buffer_disc) >= 1000:
                c.executemany(
                    "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                    buffer_disc,
                )
                buffer_disc = []
                conn.commit()

    # Final flush
    if buffer_res:
        c.executemany(
            "INSERT OR REPLACE INTO webpage_result (url, matches) VALUES (?, ?)",
            [(x[0], x[1]) for x in buffer_res],
        )
        c.executemany(
            "INSERT OR REPLACE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(x[0], x[2], x[3]) for x in buffer_res],
        )
    if buffer_disc:
        c.executemany(
            "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
            buffer_disc,
        )

    conn.commit()
    conn.close()
    print(f"✅ Processed {count} documents")


# --- MAIN ---

if __name__ == "__main__":
    print(f"🚀 Starting Refinement Script ({NUM_WORKERS} workers)...")
    setup_target_db(TARGET_DB_PATH)

    # Get already-processed URLs
    processed_urls = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed_urls)} already processed URLs")

    # Get unprocessed data
    data = get_source_data(SOURCE_DB_PATH, processed_urls)
    print(f"📦 Loaded {len(data)} unprocessed documents from {SOURCE_DB_PATH}")

    if len(data) == 0:
        print("✅ All documents already processed!")
        exit(0)

    # Chunk data for workers
    chunk_size = max(1, len(data) // NUM_WORKERS)
    chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    queue = mp.Queue()
    workers = []

    for chunk in chunks:
        p = mp.Process(target=worker, args=(chunk, queue))
        p.start()
        workers.append(p)

    # Start listener in main process
    listener(queue, TARGET_DB_PATH, len(data))

    for p in workers:
        p.join()

    print("✅ Refinement complete!")
