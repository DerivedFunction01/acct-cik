# database_export.py
# =============================================================================
# EXPORT SCRIPT: ACTIVE USERS TO CSV
# =============================================================================
# Exports a binary classification CSV (1/0) for each derivative category.
#
# Logic:
# 1. Connects to the final Single-DB (`final_active_data.db`).
# 2. Selects ONLY companies with remaining Active Sentences (matches != '[]').
# 3. Parses the 'categories' JSON to determine which instruments they hold.
# 4. Produces a flattened CSV: CIK, Year, IR_User, FX_User, etc.
# =============================================================================

import sqlite3
import json
import multiprocessing as mp
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from queue import Queue
from threading import Thread, Event
from typing import Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

BATCH_SIZE = 5000
WORKERS = max(1, mp.cpu_count() - 1)
PREFETCH_BATCHES = 4

# =============================================================================
# WORKER LOGIC
# =============================================================================


def process_batch(batch):
    """
    Process a batch of raw DB rows into CSV lines.
    Row: (url, cik, year, matches_json, categories_json)
    """
    results = []
    for url, cik, year, matches_json, categories_json in batch:

        # 1. Safety Check: Must have active matches
        if not matches_json or matches_json == "[]":
            continue

        try:
            categories = json.loads(categories_json) if categories_json else []
        except json.JSONDecodeError:
            categories = []

        # 2. Extract Unique Categories
        # Normalize to lowercase and remove structural tags
        cat_set = {
            cat.lower()
            for cat in categories
            if cat and cat.lower() not in {"other", "unknown", "table"}
        }

        if not cat_set:
            continue

        # 3. Create Binary Flags
        # Note: "gen" (Generic) is kept as a signal, but usually implies
        # ambiguous language that survived filtering.
        results.append(
            (
                cik,
                year,
                1 if "ir" in cat_set else 0,
                1 if "fx" in cat_set else 0,
                1 if "cp" in cat_set else 0,
                1 if "eq" in cat_set else 0,
                1 if "gen" in cat_set else 0,
            )
        )
    return results


def fetch_worker(db_path, batch_queue, stop_event):
    """Thread that reads from SQLite and feeds the queue."""
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA query_only=1")  # Safety

    cur = conn.cursor()

    # CRITICAL SQL:
    # Only select rows that have ACTUAL matches.
    # Empty lists '[]' represent companies that were active during the year
    # but fully terminated by year-end (and thus filtered out in Phase 5).
    query = """
        SELECT wr.url, rd.cik, rd.year, wr.matches, cat.categories
        FROM webpage_result wr
        JOIN report_data rd ON wr.url = rd.url
        LEFT JOIN category cat ON wr.url = cat.url
        WHERE wr.matches IS NOT NULL 
          AND wr.matches != '[]'
          AND wr.matches != ''
    """

    cur.execute(query)

    batch_id = 0
    while not stop_event.is_set():
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        batch_queue.put((batch_id, rows))
        batch_id += 1

    batch_queue.put(None)  # Signal done
    conn.close()


def write_worker(result_queue, temp_dir, stop_event):
    """Thread that writes processed results to temp CSVs."""
    file_writers = {}

    while not stop_event.is_set() or not result_queue.empty():
        try:
            item = result_queue.get(timeout=0.1)
            if item is None:
                break

            batch_id, batch_results = item

            # Round-robin write to avoid file lock contention if multiple writers existed
            # (Here we strictly use one writer thread, but split files for safety)
            file_id = batch_id % WORKERS

            if file_id not in file_writers:
                file_writers[file_id] = open(
                    temp_dir / f"partial_{file_id:04d}.csv", "w", encoding="utf-8"
                )

            f = file_writers[file_id]
            for row in batch_results:
                f.write(",".join(map(str, row)) + "\n")

        except Exception:
            continue

    for f in file_writers.values():
        f.close()


def merge_files(temp_dir: Path, output_path: str):
    """Merges temp CSV chunks into the final file."""
    print(f"\nMerging intermediate files to {output_path}...")
    partial_files = sorted(temp_dir.glob("partial_*.csv"))

    total_lines = 0
    with open(output_path, "w", encoding="utf-8") as outfile:
        # Header
        outfile.write("cik,year,ir_user,fx_user,cp_user,eq_user,gen_user\n")

        for pf in partial_files:
            with open(pf, "r", encoding="utf-8") as infile:
                # Read/Write in chunks to avoid memory issues with massive files
                while True:
                    chunk = infile.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    outfile.write(chunk)
                    # Rough line count estimation isn't needed, exact is better:
                    total_lines += chunk.count("\n")

            print(f"  Merged segment: {pf.name}")

    print(f"  Total Active User Records: {total_lines:,}")
    return total_lines


# =============================================================================
# MAIN CONTROLLER
# =============================================================================


def export_users_production(db_path: str, csv_path: Optional[str] = None):
    db = Path(db_path)
    if not db.exists():
        print(f"❌ Database not found: {db}")
        return

    if csv_path is None:
        csv_path = db.stem + "_active_users.csv"

    print(f"=" * 60)
    print(f"EXPORTING ACTIVE YEAR-END USERS")
    print(f"Source: {db.name}")
    print(f"Target: {csv_path}")
    print(f"Workers: {WORKERS}")
    print(f"=" * 60)

    # 1. Pre-Scan Counts
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("📊 Scanning Database...")

    # Count Active
    cur.execute(
        "SELECT COUNT(*) FROM webpage_result WHERE matches != '[]' AND matches IS NOT NULL"
    )
    active_count = cur.fetchone()[0]

    # Count Terminated (Present in DB but matches are empty)
    cur.execute("SELECT COUNT(*) FROM webpage_result WHERE matches = '[]'")
    terminated_count = cur.fetchone()[0]

    conn.close()

    print(f"   Active Year-End Users: {active_count:,}")
    print(f"   Terminated During Year: {terminated_count:,} (Skipped)")
    print(f"   Total Records: {active_count + terminated_count:,}\n")

    if active_count == 0:
        print("⚠️ No active users found. Check your filtering logic.")
        return

    # 2. Execution
    temp_dir = Path(tempfile.mkdtemp(prefix="export_users_"))

    try:
        batch_queue = Queue(maxsize=PREFETCH_BATCHES)
        result_queue = Queue(maxsize=WORKERS * 2)
        stop_fetch = Event()
        stop_write = Event()

        # Start Threads
        fetcher = Thread(
            target=fetch_worker, args=(db_path, batch_queue, stop_fetch), daemon=True
        )
        writer = Thread(
            target=write_worker, args=(result_queue, temp_dir, stop_write), daemon=True
        )

        fetcher.start()
        writer.start()

        # Start Processes
        processed_count = 0
        with ProcessPoolExecutor(max_workers=WORKERS) as executor:
            pending = {}

            while True:
                # Feed workers
                item = None
                while len(pending) < WORKERS * 2:
                    try:
                        item = batch_queue.get_nowait()
                        if item is None:
                            break
                        batch_id, rows = item
                        future = executor.submit(process_batch, rows)
                        pending[future] = batch_id
                    except:
                        break

                # Check for completion
                if not pending and item is None:
                    break

                # Collect results
                done_futures = [f for f in pending if f.done()]
                for f in done_futures:
                    batch_results = f.result()
                    result_queue.put((pending[f], batch_results))
                    processed_count += len(batch_results)
                    del pending[f]

                    if processed_count % 25000 == 0:
                        print(f"   Processed: {processed_count:,}...")

        # Cleanup
        result_queue.put(None)
        stop_fetch.set()
        stop_write.set()

        fetcher.join()
        writer.join()

        # Merge
        merge_files(temp_dir, csv_path)
        print(f"\n✅ Export Complete: {csv_path}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)  # Required for stability

    # Default to the final single DB
    default_db = "verified_active_data.db"
    db_input = input(f"Enter database (default: {default_db}): ").strip()
    db_name = db_input or default_db

    if not db_name.endswith(".db"):
        db_name += ".db"

    export_users_production(db_name)
