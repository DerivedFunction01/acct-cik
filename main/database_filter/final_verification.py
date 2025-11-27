# final_verification.py
# =============================================================================
# PHASE 7: ACTIVE USAGE VERIFICATION
# =============================================================================
# The Final Gatekeeper.
# Ensures every remaining sentence contains a "Strong Signal" of activity.
#
# Filters out passive context like:
# - "The effectiveness is determined quarterly." (No action verb, no amount)
# - "Risk management policies are reviewed." (No instrument state)
#
# Keeps Strong Signals:
# - "We use swaps." (Action Verb)
# - "Notional was $100." (Quantitative)
# - "Positions remain outstanding." (State Descriptor)
# =============================================================================

import sqlite3
import json
import re
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor

# =============================================================================
# CONFIGURATION
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "active_nonzero_data.db"
FINAL_DB_PATH = "verified_active_data.db"

from derivative_regex import (
    SENTENCE_SPLIT_PATTERN,
    CURRENCY_SYMBOL_PATTERN,
    STRONG_VERB_PATTERN,
    build_alternation, 
    ACTIVE_STATE_REGEX,
    validate_instrument_retention,
)
# =============================================================================
# VERIFICATION REGEXES
# =============================================================================

VERB_REGEX = re.compile(rf"\b{STRONG_VERB_PATTERN}\b", re.IGNORECASE)

# 2. QUANTITATIVE INDICATORS (Money & Metrics)
# Matches: "$100", "5%", "Notional", "Fair Value"
# We assume if they give a number or mention "Fair Value", they have the instrument.
QUANT_TERMS = [
    r"notional",
    r"fair\s+value",
    r"carrying\s+(?:amount|value)",
    r"market\s+value",
    r"weighted\s+average",
]
# Looks for Currency Symbols or defined terms
QUANT_REGEX = re.compile(
    rf"{CURRENCY_SYMBOL_PATTERN}|"  # $ €
    r"\b\d+(?:\.\d+)?%|"  # 5.5%
    rf"\b{build_alternation(QUANT_TERMS)}\b",
    re.IGNORECASE,
)


# =============================================================================
# LOGIC
# =============================================================================


def check_strong_signal(sentence: str) -> bool:
    """
    Returns True if the sentence contains at least one strong signal of activity.
    """
    # 1. Check Action Verbs ("We use...")
    if VERB_REGEX.search(sentence):
        return True

    # 2. Check Quantitative ("$100 million", "Notional")
    if QUANT_REGEX.search(sentence):
        return True

    # 3. Check State ("Outstanding")
    if ACTIVE_STATE_REGEX.search(sentence):
        return True

    return False


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
        # Atomic split is crucial here - we validate sentence by sentence
        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]
        kept_atomic = []

        for sent in atomic_sentences:
            # --- VERIFICATION CHECK ---
            if check_strong_signal(sent):
                kept_atomic.append(sent)
            else:
                # Discard passive sentences (e.g. "The policy was adopted.")
                discards.append((url, sent, "weak_evidence_no_verb_or_quant"))

        if kept_atomic:
            final_paragraphs.append(" ".join(kept_atomic))
            final_categories.append(category)
    # 4. Final Validation Helper
    final_paragraphs, final_categories, validation_discards = (
        validate_instrument_retention(
            final_paragraphs, final_categories, url, strict=False
        )
    )

    # Add validation discards to your main discard pile
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

# =============================================================================
# DB HELPERS
# =============================================================================


def setup_db():
    if Path(FINAL_DB_PATH).exists():
        Path(FINAL_DB_PATH).unlink()
    conn = sqlite3.connect(FINAL_DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE webpage_result (url TEXT PRIMARY KEY, matches TEXT)")
    c.execute(
        "CREATE TABLE category (url TEXT PRIMARY KEY, categories TEXT, FOREIGN KEY(url) REFERENCES webpage_result(url))"
    )
    c.execute(
        "CREATE TABLE report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
    )
    c.execute(
        "CREATE TABLE discarded_sentences (id INTEGER PRIMARY KEY, url TEXT, sentence TEXT, discard_reason TEXT)"
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
        webpage_rows = [(b[0], b[1]) for b in batch]
        cat_rows = [(b[0], b[2]) for b in batch]
        meta_rows = [(b[0], b[3], b[4]) for b in batch]
        c.executemany("INSERT INTO webpage_result VALUES (?, ?)", webpage_rows)
        c.executemany("INSERT INTO category VALUES (?, ?)", cat_rows)
        c.executemany("INSERT INTO report_data VALUES (?, ?, ?)", meta_rows)

        all_discards = []
        for b in batch:
            if b[5]:
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
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 90)
    print("PHASE 7: FINAL VERIFICATION (Action/Quant Check)")
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
    print(f"Final Verified Data: {FINAL_DB_PATH}")
