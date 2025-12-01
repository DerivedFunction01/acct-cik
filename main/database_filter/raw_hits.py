"""
DISCLOSURE SCANNER (Stage 1 Redux)
==================================
Scans the raw 'web_data.db' for mandatory disclosures (PnL, Risk, Policy).
Bypasses all 'Anchor/Orphan' logic to ensure 100% recall of disclosures
that might have been dropped by the active-user pipeline.

Outputs: disclosure_counts.csv
"""

import sqlite3
import pandas as pd
import re
import json
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm

# --- CONFIGURATION ---
SOURCE_DB = "web_data.db"
OUTPUT_FILE = "disclosure_counts.csv"
NUM_WORKERS = max(1, mp.cpu_count() - 1)
CHUNK_SIZE = 1000

# --- IMPORT REGEXES ---
# We reuse your existing robust patterns
from derivative_regex import (
    ALL_REGEX,
    EXCLUDE_REGULATION_REGEX,  # Regulatory
    PNL_ONLY_NO_POSITION,  # PnL / AOCI
    POTENTIAL_REGEX,  # Hypothetical / Intent
    build_alternation,
)

# --- DEFINE MISSING REGEXES ---
# Counterparty/Credit Risk was defined in final_verification.py, so we redefine it here.
COUNTERPARTY_POLICY_TERMS = [
    r"credit\s+risk",
    r"counterpart(?:y|ies)",
    r"credit\s+quality",
    r"credit\s+worthiness",
    r"highly[- ]rated",
    r"investment[- ]grade",
    r"financial\s+institutions",
    r"master\s+netting",
    r"isda",
    r"collateral\s+requirements",
    r"concentration\s+of\s+credit",
    r"non[- ]performance",
    r"nonperformance",
]
COUNTERPARTY_REGEX = re.compile(
    r"\b" + build_alternation(COUNTERPARTY_POLICY_TERMS) + r"\b", re.IGNORECASE
)

# Broaden PnL slightly for correlation analysis (catch "Fair Value" tables)
PNL_BROAD_REGEX = re.compile(
    r"(?:gain|loss|income|expense|fair\s+value|mark[- ]to[- ]market|aoci|oci)",
    re.IGNORECASE,
)


def process_chunk(rows):
    """
    Process a chunk of (url, matches_json) rows.
    Returns a dict: {url: {counts}}
    """
    results = {}

    for url, matches_json in rows:
        try:
            paragraphs = json.loads(matches_json)
        except:
            continue

        counts = {
            "reg_hits": 0,
            "pnl_hits": 0,
            "hypo_hits": 0,
            "credit_hits": 0,
            "total_sentences": 0,
        }

        # Iterate through every paragraph found in the 10-K
        for para in paragraphs:
            if not para or not ALL_REGEX.search(para):
                continue

            # 1. Regulation Check
            if EXCLUDE_REGULATION_REGEX.search(para):
                counts["reg_hits"] += 1

            # 2. PnL / Quantitative Disclosure Check
            # We check both the specific "No Position" regex AND broad PnL terms
            if PNL_ONLY_NO_POSITION.search(para) or PNL_BROAD_REGEX.search(para):
                counts["pnl_hits"] += 1

            # 3. Hypothetical / Policy Check
            if POTENTIAL_REGEX.search(para):
                counts["hypo_hits"] += 1

            # 4. Counterparty / Credit Risk Check
            if COUNTERPARTY_REGEX.search(para):
                counts["credit_hits"] += 1

            counts["total_sentences"] += 1

        results[url] = counts

    return results


def main():
    if not Path(SOURCE_DB).exists():
        print(f"❌ Error: {SOURCE_DB} not found. Run webpage.py first.")
        return

    print(f"📖 Reading {SOURCE_DB}...")
    conn = sqlite3.connect(SOURCE_DB)

    # Get total count for progress bar
    total_rows = conn.execute("SELECT COUNT(*) FROM webpage_result").fetchone()[0]

    # Cursor for iteration
    cursor = conn.cursor()
    cursor.execute("SELECT url, matches FROM webpage_result")

    final_data = {}

    # Process in parallel chunks
    pool = mp.Pool(NUM_WORKERS)

    rows_buffer = []

    with tqdm(total=total_rows, unit="firms") as pbar:
        while True:
            # Fetch chunk
            rows = cursor.fetchmany(CHUNK_SIZE)
            if not rows:
                break

            # Submit to pool
            # We process this block synchronously for simplicity in this script,
            # or async if you prefer. Given regex speed, simple map is fine.
            results = pool.apply(process_chunk, args=(rows,))
            final_data.update(results)

            pbar.update(len(rows))

    pool.close()
    pool.join()
    conn.close()

    print("💾 Saving results...")
    df = pd.DataFrame.from_dict(final_data, orient="index")
    df.index.name = "url"
    df.reset_index(inplace=True)

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"✅ Saved {len(df)} records to {OUTPUT_FILE}")
    print(df.describe())


if __name__ == "__main__":
    mp.freeze_support()
    main()
