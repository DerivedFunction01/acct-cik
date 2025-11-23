# roberta_merge.py
# =============================================================================
# HIGH-PERFORMANCE MERGE: server classification → clean_web_data.db
# Handles Parallel Arrays: Text + Category + RoBERTa Result
# =============================================================================

import sqlite3
import json
import multiprocessing as mp
import time
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# --------------------------------------------------------------------------- #
# CONFIGURATION
# --------------------------------------------------------------------------- #
SOURCE_DB_PATH = "prepared_data.db"
CLEAN_DB_PATH = "hedge_data.db"

RELEVANT_LABELS = {"hedge"}  # Keep only these
CONFIDENCE_THRESHOLD = 0.70  # Minimum confidence score

BATCH_SIZE = 2000
FLUSH_INTERVAL = 5.0
NUM_WORKERS = max(1, mp.cpu_count() - 1)
CHUNK_SIZE = 50

# Global buffers (main process only)
result_buffer: List[Dict[str, Any]] = []
discard_buffer: List[Tuple[str, str, str]] = []


# --------------------------------------------------------------------------- #
# DATABASE SETUP
# --------------------------------------------------------------------------- #
def create_clean_db():
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()

    # Main text storage
    c.execute(
        """CREATE TABLE IF NOT EXISTS webpage_result (
            url TEXT PRIMARY KEY, 
            matches TEXT  -- JSON array of filtered sentences
        )"""
    )

    # CRITICAL: Category storage (Parallel Array to matches)
    c.execute(
        """CREATE TABLE IF NOT EXISTS category (
            url TEXT PRIMARY KEY,
            categories TEXT, -- JSON array of filtered categories
            FOREIGN KEY (url) REFERENCES webpage_result(url)
        )"""
    )

    c.execute(
        """CREATE TABLE IF NOT EXISTS report_data (
            url TEXT PRIMARY KEY, 
            cik INTEGER, 
            year INTEGER
        )"""
    )

    c.execute(
        """CREATE TABLE IF NOT EXISTS discarded_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            url TEXT, 
            sentence TEXT, 
            discard_reason TEXT
        )"""
    )

    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
    c.execute("CREATE INDEX IF NOT EXISTS cat_url_idx ON category (url)")
    c.execute(
        "CREATE INDEX IF NOT EXISTS reason_idx ON discarded_sentences (discard_reason)"
    )
    c.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    conn.close()


def get_already_merged_urls() -> set:
    if not Path(CLEAN_DB_PATH).exists():
        return set()
    conn = sqlite3.connect(CLEAN_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT url FROM webpage_result")
    urls = {row[0] for row in cur.fetchall()}
    conn.close()
    return urls


def fetch_all_reports() -> List[Tuple[int, int, str, str, str, str]]:
    """
    Returns list of (cik, year, url, matches_json, categories_json, server_response_json)
    """
    conn = sqlite3.connect(SOURCE_DB_PATH)
    cur = conn.cursor()

    # Join with the Category table to get the parallel array
    try:
        cur.execute(
            """
            SELECT rd.cik, rd.year, wr.url, wr.matches, cat.categories, sr.server_response
            FROM webpage_result wr
            JOIN report_data rd ON wr.url = rd.url
            JOIN server_result sr ON sr.url = wr.url
            LEFT JOIN category cat ON wr.url = cat.url
            WHERE sr.server_response IS NOT NULL
            """
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Database error (schema mismatch?): {e}")
        rows = []

    conn.close()
    return rows


# --------------------------------------------------------------------------- #
# CORE PROCESSING (runs in worker processes)
# --------------------------------------------------------------------------- #
def build_discard_reason(pred: dict, best_label: str, best_score: float) -> str:
    if not isinstance(pred, dict):
        return "error_invalid_pred"
    if "error" in pred:
        return f"error_{pred.get('error', 'unknown')}"
    if best_label not in RELEVANT_LABELS:
        return f"label={best_label}|score={best_score:.4f}|rejected_noise"
    return f"label={best_label}|score={best_score:.4f}|below_threshold"


def process_single_report(
    item: Tuple[int, int, str, str, str, str], merged_urls: set
) -> Optional[tuple]:
    """
    Filters sentences based on RoBERTa predictions while maintaining
    category alignment.
    """
    cik, year, url, matches_json, categories_json, server_json = item

    if url in merged_urls:
        return None

    try:
        sentences = json.loads(matches_json) if matches_json else []
        predictions = json.loads(server_json) if server_json else []
        categories = json.loads(categories_json) if categories_json else []
    except json.JSONDecodeError:
        return (url, None, None, cik, year, [(url, "", "error_json_parse")])

    # 1. Validation: Ensure array lengths align
    # Categories might be missing (empty list) if the source DB is old, handle gracefully
    if not categories:
        categories = ["unknown"] * len(sentences)

    if len(predictions) != len(sentences):
        reason = f"mismatch|preds={len(predictions)}|sents={len(sentences)}"
        discards = [(url, s, reason) for s in sentences]
        return (url, None, None, cik, year, discards)

    if len(categories) != len(sentences):
        # Fallback if category sync broke previously, though filter_database prevents this
        reason = f"mismatch|cats={len(categories)}|sents={len(sentences)}"
        discards = [(url, s, reason) for s in sentences]
        return (url, None, None, cik, year, discards)

    kept_sentences = []
    kept_categories = []
    discarded = []

    # 2. Iterate strictly in parallel
    for sent, cat, pred in zip(sentences, categories, predictions):
        if not isinstance(pred, dict) or not pred:
            discarded.append((url, sent, "error_empty_pred"))
            continue

        label = max(pred.items(), key=lambda x: x[1])[0]
        score = pred[label]

        # 3. Filtering Logic
        if label in RELEVANT_LABELS and score >= CONFIDENCE_THRESHOLD:
            kept_sentences.append(sent)
            kept_categories.append(cat)
        else:
            reason = build_discard_reason(pred, label, score)
            discarded.append((url, sent, reason))

    if not kept_sentences:
        return (url, None, None, cik, year, discarded)

    # 4. Return parallel arrays
    return (
        url,
        json.dumps(kept_sentences),
        json.dumps(kept_categories),
        cik,
        year,
        discarded,
    )


# --------------------------------------------------------------------------- #
# BATCHED WRITES (main process only)
# --------------------------------------------------------------------------- #
def flush_buffers(force: bool = False):
    global result_buffer, discard_buffer

    if (
        not force
        and len(result_buffer) < BATCH_SIZE
        and len(discard_buffer) < BATCH_SIZE * 5
    ):
        return

    conn = sqlite3.connect(CLEAN_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    c = conn.cursor()

    try:
        c.execute("BEGIN TRANSACTION")

        if result_buffer:
            # Prepare separate lists for insertions
            webpage_data = [(r["url"], r["matches"]) for r in result_buffer]
            category_data = [(r["url"], r["categories"]) for r in result_buffer]
            report_data = [(r["url"], r["cik"], r["year"]) for r in result_buffer]

            # 1. Insert Matches
            c.executemany(
                "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                webpage_data,
            )

            # 2. Insert Categories (Linked by URL)
            c.executemany(
                "INSERT OR IGNORE INTO category (url, categories) VALUES (?, ?)",
                category_data,
            )

            # 3. Insert Metadata
            c.executemany(
                "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                report_data,
            )

            result_buffer.clear()

        if discard_buffer:
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                discard_buffer,
            )
            discard_buffer.clear()

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Flush error: {e}")
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #
def merge_server_results_parallel():
    print("=" * 90)
    print("ROBERTA MERGE: Filtering Sentences & Retaining Categories")
    print(f"Using {NUM_WORKERS} worker processes")
    print("=" * 90)

    create_clean_db()
    merged_urls = get_already_merged_urls()
    print(f"Already merged URLs: {len(merged_urls):,}")

    # Fetch data including categories
    all_reports = fetch_all_reports()
    print(f"Total reports with predictions: {len(all_reports):,}")

    to_process = [r for r in all_reports if r[2] not in merged_urls]
    print(f"Reports to process: {len(to_process):,}\n")

    if not to_process:
        print("Nothing to do!")
        return

    last_flush = time.time()

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Pass the merged_urls set to workers to double-check
        futures = [
            executor.submit(process_single_report, item, merged_urls)
            for item in to_process
        ]

        for future in tqdm(as_completed(futures), total=len(futures), desc="Merging"):
            result = future.result()
            if result is None:
                continue

            # Unpack the parallel arrays
            url, matches_json, categories_json, cik, year, discards = result

            if matches_json:
                result_buffer.append(
                    {
                        "url": url,
                        "matches": matches_json,
                        "categories": categories_json,  # Store category JSON
                        "cik": cik,
                        "year": year,
                    }
                )

            if discards:
                discard_buffer.extend(discards)

            if len(result_buffer) >= BATCH_SIZE or (
                time.time() - last_flush > FLUSH_INTERVAL
            ):
                flush_buffers()
                last_flush = time.time()

    flush_buffers(force=True)
    print("\nMerge Complete. Data saved to:", CLEAN_DB_PATH)


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    merge_server_results_parallel()
