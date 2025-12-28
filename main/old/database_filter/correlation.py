"""
CORRELATION ANALYSIS: Mandatory Disclosures vs. Active Usage (Optimized)
========================================================================
1. Parallel Processing: Uses multiple cores to parse JSON/Regex.
2. Caching: Saves results to CSV to avoid re-running extraction.
3. Normalization: Normalizes specific discards against total derivative mentions.
"""

import sqlite3
import pandas as pd
import numpy as np
import statsmodels.api as sm
from pathlib import Path
import multiprocessing as mp
from functools import partial
import time
import os

# Import regex from your existing library
from derivative_regex import SENTENCE_SPLIT_PATTERN, MIN_SENTENCE_LENGTH

# Configuration
DB_PATHS = {
    "phase_1": "prepared_data.db",
    "phase_4": "active_data.db",
    "phase_7": "verified_active_data.db",
}
CACHE_FILE = "correlation_features.csv"
NUM_WORKERS = max(1, mp.cpu_count() - 1)
CHUNK_SIZE = 5000  # Process companies in batches to save RAM


def get_db_connection(db_name):
    return sqlite3.connect(db_name)


def count_sentences_in_text(text):
    """Expands a text block into a count of valid sentences."""
    if not text:
        return 0
    sentences = [
        s
        for s in SENTENCE_SPLIT_PATTERN.split(str(text))
        if len(s.strip()) > MIN_SENTENCE_LENGTH
    ]
    return len(sentences)


def worker_process_chunk(urls):
    """
    Worker function to process a specific list of URLs.
    Opens its own DB connections to avoid locking issues.
    """
    results = {}

    # --- 1. PHASE 1: Raw Volume & PnL/Hypo Blocks ---
    conn_p1 = get_db_connection(DB_PATHS["phase_1"])
    cursor_p1 = conn_p1.cursor()

    # Get Matches (Raw Volume)
    # We fetch specifically requested URLs to keep memory low
    placeholders = ",".join("?" for _ in urls)

    # A. Raw Volume (Parse JSON matches)
    cursor_p1.execute(
        f"SELECT url, matches FROM webpage_result WHERE url IN ({placeholders})", urls
    )
    for url, matches_json in cursor_p1.fetchall():
        try:
            # Fast parsing of JSON list length
            import json

            raw_count = len(json.loads(matches_json))
        except:
            raw_count = 0

        results[url] = {
            "raw_vol": raw_count,
            "pnl_discards": 0,
            "hypo_discards": 0,
            "credit_discards": 0,
            "is_active": 0,
        }

    # B. Phase 1 Discards (PnL & Hypo Blocks)
    cursor_p1.execute(
        f"""
        SELECT url, discard_reason, sentence 
        FROM discarded_sentences 
        WHERE url IN ({placeholders})
        AND discard_reason IN ('pnl_only_no_position', 'aoci_or_pnl_only', 'pnl_only_removed', 'hypo')
    """,
        urls,
    )

    for url, reason, sentence in cursor_p1.fetchall():
        if url not in results:
            continue

        if "pnl" in reason:
            results[url]["pnl_discards"] += 1
        elif "hypo" in reason:
            # EXPENSIVE OP: Regex split on block text
            results[url]["hypo_discards"] += count_sentences_in_text(sentence)

    conn_p1.close()

    # --- 2. PHASE 4: Hypo Sentences ---
    conn_p4 = get_db_connection(DB_PATHS["phase_4"])
    cursor_p4 = conn_p4.cursor()

    cursor_p4.execute(
        f"""
        SELECT url, COUNT(*) 
        FROM discarded_sentences 
        WHERE url IN ({placeholders}) AND discard_reason = 'linguistic_potential_use'
        GROUP BY url
    """,
        urls,
    )

    for url, count in cursor_p4.fetchall():
        if url in results:
            results[url]["hypo_discards"] += count

    conn_p4.close()

    # --- 3. PHASE 7: Active Status & Credit Risk ---
    conn_p7 = get_db_connection(DB_PATHS["phase_7"])
    cursor_p7 = conn_p7.cursor()

    # A. Active Status
    cursor_p7.execute(
        f"SELECT url FROM webpage_result WHERE url IN ({placeholders})", urls
    )
    for (url,) in cursor_p7.fetchall():
        if url in results:
            results[url]["is_active"] = 1

    # B. Credit Discards
    cursor_p7.execute(
        f"""
        SELECT url, COUNT(*) 
        FROM discarded_sentences 
        WHERE url IN ({placeholders}) AND discard_reason = 'discarded_counterparty_risk_boilerplate'
        GROUP BY url
    """,
        urls,
    )

    for url, count in cursor_p7.fetchall():
        if url in results:
            results[url]["credit_discards"] += count

    conn_p7.close()

    return results


def extract_features_parallel():
    """Main driver for parallel extraction."""

    # 1. Get Universe of URLs from Phase 1
    print("📋 Fetching URL list from Phase 1...")
    conn = get_db_connection(DB_PATHS["phase_1"])
    all_urls = [
        row[0] for row in conn.execute("SELECT url FROM webpage_result").fetchall()
    ]
    conn.close()

    total_urls = len(all_urls)
    print(f"   Found {total_urls:,} companies.")

    # 2. Chunk URLs
    chunks = [all_urls[i : i + CHUNK_SIZE] for i in range(0, total_urls, CHUNK_SIZE)]
    print(f"   Processing in {len(chunks)} chunks with {NUM_WORKERS} workers...")

    # 3. Process in Parallel
    final_data = {}

    with mp.Pool(processes=NUM_WORKERS) as pool:
        # Use simple map, or imap_unordered for progress bar
        for chunk_result in pool.imap_unordered(worker_process_chunk, chunks):
            final_data.update(chunk_result)
            print(f"   ...processed chunk ({len(final_data)}/{total_urls})", end="\r")

    print(f"\n✅ Extraction complete.")

    # Convert to DataFrame
    df = pd.DataFrame.from_dict(final_data, orient="index")
    return df


def get_data():
    """Orchestrates loading from cache or running extraction."""
    if Path(CACHE_FILE).exists():
        print(f"📂 Loading cached features from {CACHE_FILE}...")
        return pd.read_csv(CACHE_FILE, index_col=0)

    print("🚀 Cache miss. Starting fresh extraction...")
    t0 = time.time()
    df = extract_features_parallel()
    print(f"⏱️  Extraction took {time.time()-t0:.2f} seconds.")

    print(f"💾 Saving to {CACHE_FILE}...")
    df.to_csv(CACHE_FILE)
    return df


def run_regression(df):
    print("\n📈 Running Correlation Analysis (Logit Regression)...")

    # Clean data
    df = df.fillna(0)
    df = df[df["raw_vol"] > 0].copy()

    # 1. Controls
    df["log_volume"] = np.log(df["raw_vol"] + 1)

    # 2. Densities (Hits per unit of derivative talk)
    df["pnl_density"] = df["pnl_discards"] / df["raw_vol"]
    df["hypo_density"] = df["hypo_discards"] / df["raw_vol"]
    df["credit_density"] = df["credit_discards"] / df["raw_vol"]

    # 3. Regression
    features = ["log_volume", "pnl_density", "hypo_density", "credit_density"]
    X = df[features]
    X = sm.add_constant(X)
    y = df["is_active"]

    try:
        model = sm.Logit(y, X)
        result = model.fit()
        print(result.summary())

        # Calculate Odds Ratios for easier interpretation
        params = result.params
        conf = result.conf_int()
        conf["Odds Ratio"] = params
        conf.columns = ["5%", "95%", "Odds Ratio"]
        print("\nOdds Ratios (exp(coef)):")
        print(np.exp(conf))

    except Exception as e:
        print(f"Error running regression: {e}")


if __name__ == "__main__":
    # Ensure Windows compatibility for multiprocessing
    mp.freeze_support()

    df = get_data()

    print("\n📊 Summary Stats:")
    print(df.describe().loc[["mean", "std", "max"]])

    run_regression(df)
