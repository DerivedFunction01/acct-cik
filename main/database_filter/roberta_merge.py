# roberta_merge.py
# =============================================================================
# HIGH-PERFORMANCE MERGE: server classification → clean_web_data.db
# Handles Parallel Arrays: Text + Category + RoBERTa Result
# IDEMPOTENT: Skips already-processed URLs to avoid duplicates/re-processing
# =============================================================================

import sqlite3
import json
import multiprocessing as mp
import time
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any, Set
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
    """Create target database with schema."""
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


def get_already_processed_urls() -> Set[str]:
    """
    Returns set of URLs that have already been processed and written to CLEAN_DB.
    This is the idempotency mechanism.
    """
    if not Path(CLEAN_DB_PATH).exists():
        return set()

    conn = sqlite3.connect(CLEAN_DB_PATH, timeout=30)
    try:
        cur = conn.cursor()
        # Query URLs from the target database
        cur.execute("SELECT url FROM webpage_result")
        urls = {row[0] for row in cur.fetchall()}
        conn.close()
        return urls
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        conn.close()
        return set()


def get_source_urls() -> Set[str]:
    """
    Returns set of ALL URLs available in source database.
    Used for statistics only.
    """
    if not Path(SOURCE_DB_PATH).exists():
        return set()

    conn = sqlite3.connect(SOURCE_DB_PATH, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT url FROM webpage_result")
        urls = {row[0] for row in cur.fetchall()}
        conn.close()
        return urls
    except sqlite3.OperationalError:
        conn.close()
        return set()


def fetch_all_reports() -> List[Tuple[int, int, str, str, str, str]]:
    """
    Returns list of (cik, year, url, matches_json, categories_json, dummy_server_json)
    """
    conn = sqlite3.connect(SOURCE_DB_PATH, timeout=30)
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT rd.cik, rd.year, wr.url, wr.matches, cat.categories, NULL as server_response
            FROM webpage_result wr
            JOIN report_data rd ON wr.url = rd.url
            LEFT JOIN category cat ON wr.url = cat.url
            """
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        print(f"❌ Database error: {e}")
        rows = []

    conn.close()
    return rows


# --------------------------------------------------------------------------- #
# CORE PROCESSING (runs in worker processes)
# --------------------------------------------------------------------------- #
def process_single_report(item: Tuple[int, int, str, str, str, str]) -> Optional[tuple]:
    """
    Pass-through: Copy all sentences without RoBERTa filtering.

    NOTE: We don't check processed_urls here because we want all workers
    to be independent. The main process filters before submission.
    """
    cik, year, url, matches_json, categories_json, _ = item  # Ignore server_json

    try:
        sentences = json.loads(matches_json) if matches_json else []
        categories = json.loads(categories_json) if categories_json else []
    except json.JSONDecodeError:
        return (url, None, None, cik, year, [])

    # Handle missing categories
    if not categories:
        categories = ["unknown"] * len(sentences)
        categories_json = json.dumps(categories)

    # Validate alignment
    if len(categories) != len(sentences):
        return (url, None, None, cik, year, [])

    if not sentences:
        return (url, None, None, cik, year, [])

    # PASS-THROUGH: Keep everything as-is
    return (
        url,
        matches_json,  # Keep original
        categories_json,  # Keep original
        cik,
        year,
        [],  # No discards
    )


# --------------------------------------------------------------------------- #
# BATCHED WRITES (main process only)
# --------------------------------------------------------------------------- #
def flush_buffers(force: bool = False):
    """Flush accumulated results to database."""
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
        print(f"❌ Flush error: {e}")
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #
def merge_server_results_parallel():
    print("=" * 90)
    print("ROBERTA MERGE: Pass-Through with Idempotency")
    print(f"Using {NUM_WORKERS} worker processes")
    print("=" * 90)

    # 1. Setup target database
    create_clean_db()

    # 2. Get already-processed URLs (IDEMPOTENCY CHECK)
    print("\n🔍 Checking for already-processed URLs...")
    processed_urls = get_already_processed_urls()
    print(f"   ✓ Already processed: {len(processed_urls):,}")

    # 3. Fetch source data
    print("\n📥 Fetching source data...")
    all_reports = fetch_all_reports()
    source_urls = get_source_urls()
    print(f"   ✓ Total source URLs: {len(source_urls):,}")
    print(f"   ✓ Source reports with metadata: {len(all_reports):,}")

    # 4. Filter: Keep only NEW (not yet processed)
    to_process = [r for r in all_reports if r[2] not in processed_urls]
    print(f"\n⏭️  Reports to process (NEW): {len(to_process):,}")

    if not to_process:
        print("✅ All reports already processed! Nothing to do.")
        return

    # 5. Show progress
    print(f"   Progress: {len(processed_urls):,} / {len(all_reports):,} complete")
    print(
        f"   Remaining: {len(to_process):,} ({100*len(to_process)/len(all_reports):.1f}%)\n"
    )

    # 6. Process new reports
    print("🚀 Starting processing...\n")
    last_flush = time.time()
    batch_count = 0
    result_count = 0

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Submit ONLY new reports (already filtered above)
        futures = [executor.submit(process_single_report, item) for item in to_process]

        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="⚙️  Processing",
            unit="report",
        ):
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
                result_count += 1

            if discards:
                discard_buffer.extend(discards)

            # Periodic flush
            if len(result_buffer) >= BATCH_SIZE or (
                time.time() - last_flush > FLUSH_INTERVAL
            ):
                flush_buffers()
                batch_count += 1
                last_flush = time.time()

    # Final flush
    if result_buffer or discard_buffer:
        flush_buffers(force=True)
        batch_count += 1

    print(f"\n✅ Processing Complete!")
    print(f"   Reports processed: {result_count:,}")
    print(f"   Batches written: {batch_count}")
    print(f"   Data saved to: {CLEAN_DB_PATH}")
    print(f"   Total now in database: {len(processed_urls) + result_count:,}")


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    merge_server_results_parallel()
