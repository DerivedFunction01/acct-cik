import sqlite3
import json
import re
import multiprocessing as mp
import time
from pathlib import Path
from typing import List, Tuple, Optional
from tqdm import tqdm

from year_deletion import extract_years

# --- CONFIGURATION ---
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "prefiltered_data.db"  # Output from Step 1
TARGET_DB_PATH = "refined_data.db"  # Input for Step 3

# --- REGEX IMPORTS (Ensure these exist in your derivative_regex.py) ---
from derivative_regex import (
    CATEGORY_REGEX,
    LOOSE_GEN_REGEX,
    POTENTIAL_REGEX,  # "may use", "might enter"
    NEGATIVE_INTENT_REGEX,  # "do not use", "no intention"
    ABSENCE_REGEX,  # "none", "no outstanding"
    DID_NOT_HOLD_REGEX,
    SENTENCE_SPLIT_PATTERN,
    SOFT_CATEGORY_REGEX,
    SOFT_REGEX,
    STRICT_REGEX,  # "did not hold"
    TRADING_STATEMENTS_REGEX,  # "do not trade for speculative purposes"
    TERMINATION_REGEX,
    VAGUE_TIMING_REGEX,  # "terminated", "expired"
)

# --- LOCAL DEFINITIONS FOR "RISK FLUFF" ---


# 1. Credit / Counterparty Risk Boilerplate
# Matches: "Concentration of credit risk", "Nonperformance risk", "Collateral requirements"
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
    """

    def has_instrument(text: str) -> bool:
        return bool(SOFT_REGEX.search(text))

    def is_current_or_no_year(sentence: str, reporting_year: Optional[int]) -> bool:
        """
        Returns True if sentence mentions current/reporting year OR no year at all.
        Returns False if sentence mentions only past years.
        """
        if not reporting_year:
            # No reporting year provided, assume any year-less statement is current
            return True

        sent_years = extract_years(sentence)

        if not sent_years:
            # No years mentioned, assume current context
            return True

        # If any year mentioned is >= reporting year, it's current/future
        if any(y >= reporting_year for y in sent_years):
            return True

        # All years are < reporting year, it's historical
        return False

    has_potential = False
    has_absence = False
    has_trading_denial = False
    has_termination = False
    has_quant = False
    is_strictly_generic = True

    if SOFT_CATEGORY_REGEX.search(text):
        is_strictly_generic = False

    sentences = SENTENCE_SPLIT_PATTERN.split(text)
    for sent in sentences:
        if has_instrument(sent):
            if POTENTIAL_REGEX.search(sent) or VAGUE_TIMING_REGEX.search(sent):
                has_potential = True
            if ABSENCE_REGEX.search(sent):
                has_absence = True
            if TRADING_STATEMENTS_REGEX.search(sent):
                has_trading_denial = True
            if NEGATIVE_INTENT_REGEX.search(
                sent
            ) and not TRADING_STATEMENTS_REGEX.search(sent):
                has_absence = True

        # Capture quantity ONLY if it mentions derivatives AND is current/no year
        # "We had swaps with $10M in 2020" (past) -> has_quant = False
        # "We have swaps with $10M" (current) -> has_quant = True
        # "We have $10M swaps in 2024" (current year) -> has_quant = True
        if QUANT_REGEX.search(sent) and LOOSE_GEN_REGEX.search(sent):
            if is_current_or_no_year(sent, year):
                has_quant = True

        # Termination is paired with has_absence or has_potential for discarding,
        # so temporal context doesn't matter (terminated program = terminated either way)
        if TERMINATION_REGEX.search(sent) and LOOSE_GEN_REGEX.search(sent):
            has_termination = True

    # === SAFE REMOVAL COMBINATIONS ===
    # (All must avoid removing legitimate 7A statements with explicit use)

    # BLOCK 1: has_potential = True (hypothetical/future scenarios)
    # These are safe to remove because they lack current use commitment
    if has_potential:
        if is_strictly_generic:
            return "generic_potential_boilerplate"
        if has_absence:
            # "may use" + "don't have" = pure hypothetical
            return "risk_boilerplate_nonuse"

        if has_termination:
            # "may use in future" + "terminated all" = pure hypothetical
            return "potential_future_but_terminated"

        if has_trading_denial and not has_quant:
            # "may use" + "don't trade/speculate" but no current-year explicit use = cautious talk
            return "potential_with_trading_denial_no_explicit_use"

        # Potential + Trading Denial + Generic
        # "We may use" + "We don't trade"
        # If it is strictly generic, we can safely dump it.
        if has_trading_denial and is_strictly_generic:
            return "generic_potential_with_trading_denial"

    # BLOCK 2: No has_potential (definitive statements)
    # Only remove when absence/termination/denial is unambiguous
    else:
        # A. The "Vague Policy" (New Aggressive Filter)
        # "We do not use derivative instruments for trading." -> Delete.
        if has_trading_denial and is_strictly_generic and not has_quant:
            return "generic_policy_no_trade"

        # B. Termination + Absence (no open positions left)
        # ONLY if termination is current year (has_termination already checks this)
        # "Terminated all contracts" + "none outstanding" = pure historical
        if has_termination and has_absence:
            return "terminated_none_outstanding"

        # C. Absence without ANY positive signal
        # "We have no derivatives" with no mention of use = clear statement
        # (has_absence already filtered by current/no year via sentence context)
        if has_absence and not has_quant:
            return "stated_absence_no_active_signal"

        # D. Trading denial + Absence (policy + fact)
        # "We do not use for trading" + "we have none" = policy + fact
        if has_trading_denial and has_absence:
            return "policy_no_use_no_trade"

    return None


def process_item(item: Tuple) -> Optional[Tuple]:
    """
    Firm-Level Filter:
    Reads a row. If AT LEAST ONE paragraph is valid (not deadweight),
    keeps the entire original list of paragraphs.
    If ALL paragraphs are deadweight, drops the firm.
    """
    url, matches_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    has_valid_signal = False
    all_discards_log = []

    # 1. Scan the firm to see if it has ANY life
    for p in paragraphs:
        reason = check_refinement_exclusions(p)

        if reason is None:
            # We found a "Keeper"!
            # This confirms the firm is relevant.
            has_valid_signal = True
        else:
            # Track why this specific paragraph was bad,
            # just in case we end up dropping the whole firm.
            all_discards_log.append((url, p, reason))

    # 2. The Firm-Level Decision
    if has_valid_signal:
        # CONDITION MET: At least one valid paragraph exists.
        # Action: Keep EVERYTHING "as is" (return the original full list).
        # We return an empty discards list because we aren't throwing anything away.
        return (url, json.dumps(paragraphs), cik, year, [])

    else:
        # CONDITION FAILED: Every single paragraph was "Deadweight".
        # Action: Drop the entire firm (return empty list).
        # We return the log so you can audit why the firm was dropped.
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


def get_source_data(path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    # Join to get CIK/Year if available
    c.execute(
        """
        SELECT w.url, w.matches, r.cik, r.year 
        FROM webpage_result w 
        LEFT JOIN report_data r ON w.url = r.url
    """
    )
    data = c.fetchall()
    conn.close()
    return data


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

    with tqdm(total=total_count, unit="docs") as pbar:
        while True:
            msg = queue.get()
            if msg == "DONE":
                break

            url, matches, cik, year, discards = msg

            # Only insert if there are still matches left
            if matches != "[]":
                buffer_res.append((url, matches, cik, year))

            if discards:
                buffer_disc.extend(discards)

            count += 1
            pbar.update(1)

            if len(buffer_res) >= 1000:
                c.executemany(
                    "INSERT OR REPLACE INTO webpage_result VALUES (?, ?)",
                    [(x[0], x[1]) for x in buffer_res],
                )
                c.executemany(
                    "INSERT OR REPLACE INTO report_data VALUES (?, ?, ?)",
                    [(x[0], x[2], x[3]) for x in buffer_res],
                )
                buffer_res = []
                conn.commit()

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
            "INSERT OR REPLACE INTO webpage_result VALUES (?, ?)",
            [(x[0], x[1]) for x in buffer_res],
        )
        c.executemany(
            "INSERT OR REPLACE INTO report_data VALUES (?, ?, ?)",
            [(x[0], x[2], x[3]) for x in buffer_res],
        )
    if buffer_disc:
        c.executemany(
            "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
            buffer_disc,
        )

    conn.commit()
    conn.close()


# --- MAIN ---

if __name__ == "__main__":
    print(f"🚀 Starting Refinement Script...")
    setup_target_db(TARGET_DB_PATH)

    data = get_source_data(SOURCE_DB_PATH)
    print(f"📦 Loaded {len(data)} documents from {SOURCE_DB_PATH}")

    # Chunk data for workers
    chunk_size = len(data) // NUM_WORKERS + 1
    chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    queue = mp.Queue()
    workers = []

    for chunk in chunks:
        p = mp.Process(target=worker, args=(chunk, queue))
        p.start()
        workers.append(p)

    # Start listener in main process (avoiding global lock issues)
    listener(queue, TARGET_DB_PATH, len(data))

    for p in workers:
        p.join()
