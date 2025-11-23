# export_derivative_users_parallel.py
# CORRECTED VERSION - Works with your actual DB schema
import sqlite3
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from queue import Queue
from threading import Thread, Event
import multiprocessing as mp
import tempfile
import shutil

BATCH_SIZE = 5000
WORKERS = max(1, mp.cpu_count() - 1)
PREFETCH_BATCHES = 4


def process_batch(batch):
    """Process a batch of (url, cik, year, matches_json, categories_json)"""
    results = []
    for url, cik, year, matches_json, categories_json in batch:
        if not matches_json or matches_json == "[]":
            continue  # No active derivative mentions → not a user

        try:
            categories = json.loads(categories_json) if categories_json else []
        except json.JSONDecodeError:
            categories = []

        # Remove "other", "unknown", etc., and deduplicate
        cat_set = {
            cat.lower()
            for cat in categories
            if cat and cat.lower() not in {"other", "unknown", "table"}
        }

        if not cat_set:
            continue  # No valid category → skip (shouldn't happen in final DB)

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
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-2000000")  # 2GB cache

    cur = conn.cursor()
    cur.execute(
        """
        SELECT wr.url, rd.cik, rd.year, wr.matches, cat.categories
        FROM webpage_result wr
        JOIN report_data rd ON wr.url = rd.url
        LEFT JOIN category cat ON wr.url = cat.url
        WHERE wr.matches IS NOT NULL 
          AND wr.matches != '[]'
          AND wr.matches != ''
    """
    )

    batch_id = 0
    while not stop_event.is_set():
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        batch_queue.put((batch_id, rows))
        batch_id += 1

    batch_queue.put(None)
    conn.close()


# write_worker and merge_files remain unchanged — they are excellent
def write_worker(result_queue, temp_dir, stop_event):
    file_writers = {}
    while not stop_event.is_set() or not result_queue.empty():
        try:
            item = result_queue.get(timeout=0.1)
            if item is None:
                break
            batch_id, batch_results = item
            file_id = batch_id % WORKERS
            if file_id not in file_writers:
                file_writers[file_id] = open(
                    temp_dir / f"partial_{file_id:04d}.csv", "w", encoding="utf-8"
                )
            f = file_writers[file_id]
            for row in batch_results:
                f.write(",".join(map(str, row)) + "\n")
        except:
            pass
    for f in file_writers.values():
        f.close()


def merge_files(temp_dir: Path, output_path: str):
    print(f"\nMerging intermediate files to {output_path}")
    partial_files = sorted(temp_dir.glob("partial_*.csv"))
    total_lines = 0
    with open(output_path, "w", encoding="utf-8") as outfile:
        outfile.write("cik,year,ir_user,fx_user,cp_user,eq_user,gen_user\n")
        for pf in partial_files:
            with open(pf, "r", encoding="utf-8") as infile:
                lines = infile.readlines()
                total_lines += len(lines)
                outfile.writelines(lines)
            print(f"   Merged {pf.name}: {len(lines):,} records")
    print(f"   Total active derivative users: {total_lines:,}")
    return total_lines


def export_users_production(db_path: str, csv_path: str = None):
    db = Path(db_path)
    if not db.exists():
        print(f"Database not found: {db}")
        return

    if csv_path is None:
        csv_path = db.stem + "_active_derivative_users.csv"

    print(f"Exporting active derivative users from: {db.name}")
    print(f"Using {WORKERS} workers, batch size = {BATCH_SIZE:,}")

    # Count eligible filings
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM webpage_result WHERE matches IS NOT NULL AND matches != '[]'"
    )
    total = cur.fetchone()[0]
    conn.close()
    print(f"Found {total:,} filings with remaining derivative content\n")

    temp_dir = Path(tempfile.mkdtemp(prefix="export_users_"))
    print(f"Temporary files: {temp_dir}")

    try:
        batch_queue = Queue(maxsize=PREFETCH_BATCHES)
        result_queue = Queue(maxsize=WORKERS * 2)
        stop_fetch = Event()
        stop_write = Event()

        fetcher = Thread(
            target=fetch_worker, args=(db_path, batch_queue, stop_fetch), daemon=True
        )
        writer = Thread(
            target=write_worker, args=(result_queue, temp_dir, stop_write), daemon=True
        )
        fetcher.start()
        writer.start()

        processed = 0
        with ProcessPoolExecutor(max_workers=WORKERS) as executor:
            pending = {}
            while True:
                # Submit new work
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

                if not pending and item is None:
                    break

                for future in as_completed(pending):
                    batch_results = future.result()
                    result_queue.put((pending[future], batch_results))
                    processed += len(batch_results)
                    del pending[future]
                    if processed % 50_000 == 0:
                        print(f"   Processed {processed:,} firm-years...")
                    break  # Only process one at a time to avoid blocking

        result_queue.put(None)
        stop_fetch.set()
        stop_write.set()
        writer.join(timeout=30)

        total_written = merge_files(temp_dir, csv_path)
        print(
            f"\nSUCCESS: Exported {total_written:,} active derivative users to {csv_path}"
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    default_db = "active_year_end.db"  # or active_nonzero_data.db
    db_input = input(f"Enter database (default: {default_db}): ").strip()
    db_name = db_input or default_db
    if not db_name.endswith(".db"):
        db_name += ".db"
    export_users_production(db_name)
