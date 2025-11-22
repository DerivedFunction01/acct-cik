# export_derivative_users_parallel.py
# Fully concurrent version with intermediate files + final merge
# Output: cik,year,ir_user,fx_user,cp_user,eq_user,gen_user

import sqlite3
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional
from queue import Queue
from threading import Thread, Event
import multiprocessing as mp
import tempfile
import shutil

BATCH_SIZE = 5000
WORKERS = max(1, mp.cpu_count() - 1)
PREFETCH_BATCHES = 4


def process_batch(batch):
    """Pure function — no DB access"""
    results = []
    for url, cik, year, matches_json in batch:
        try:
            matches = json.loads(matches_json)
        except json.JSONDecodeError:
            continue

        cats = set()
        for item in matches:
            cats.update(item.get("categories", []))

        cats.discard("other")

        results.append(
            (
                cik,
                year,
                1 if "ir" in cats else 0,
                1 if "fx" in cats else 0,
                1 if "cp" in cats else 0,
                1 if "eq" in cats else 0,
                1 if "gen" in cats else 0,
            )
        )
    return results


def fetch_worker(db_path, batch_queue, stop_event):
    """Background thread that continuously fetches batches"""
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-2000000")

    cur = conn.cursor()
    cur.execute(
        """
        SELECT wr.url, rd.cik, rd.year, wr.matches
        FROM webpage_result wr
        JOIN report_data rd ON wr.url = rd.url
        WHERE wr.matches IS NOT NULL
          AND wr.matches LIKE '%"categories"%'
        """
    )

    batch_id = 0
    while not stop_event.is_set():
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        batch_queue.put((batch_id, rows))
        batch_id += 1

    batch_queue.put(None)  # Sentinel
    conn.close()


def write_worker(result_queue, temp_dir, stop_event):
    """Background thread that writes results to intermediate files"""
    file_writers = {}  # {worker_id: file_handle}

    while not stop_event.is_set() or not result_queue.empty():
        try:
            item = result_queue.get(timeout=0.1)
            if item is None:  # Sentinel
                break

            batch_id, batch_results = item

            # Assign batch to a file based on batch_id % WORKERS
            file_id = batch_id % WORKERS

            if file_id not in file_writers:
                file_path = temp_dir / f"partial_{file_id:04d}.csv"
                file_writers[file_id] = open(file_path, "w", encoding="utf-8")

            f = file_writers[file_id]
            for row in batch_results:
                f.write(",".join(map(str, row)) + "\n")

        except:
            pass

    # Close all files
    for f in file_writers.values():
        f.close()


def merge_files(temp_dir: Path, output_path: str):
    """Merge all intermediate files into final output"""
    print(f"\n📝 Merging intermediate files → {output_path}")

    partial_files = sorted(temp_dir.glob("partial_*.csv"))
    print(f"   Found {len(partial_files)} intermediate files")

    total_lines = 0
    with open(output_path, "w", encoding="utf-8") as outfile:
        # Write header
        outfile.write("cik,year,ir_user,fx_user,cp_user,eq_user,gen_user\n")

        # Merge all partial files
        for partial_file in partial_files:
            with open(partial_file, "r", encoding="utf-8") as infile:
                lines = infile.readlines()
                total_lines += len(lines)
                outfile.writelines(lines)
            print(f"   ✓ Merged {partial_file.name}: {len(lines):,} records")

    print(f"   Total records written: {total_lines:,}")
    return total_lines


def export_users_production(db_path: str, csv_path: Optional[str] = None):
    db = Path(db_path)
    if not db.exists():
        print(f"DB not found: {db}")
        return

    if csv_path is None:
        csv_path = db.stem + "_derivative_users.csv"

    print(f"Exporting derivative users from {db.name} → {csv_path}")
    print(f"Using {WORKERS} workers, batch size = {BATCH_SIZE:,}")

    # Get total count
    conn = sqlite3.connect(db, timeout=60)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM webpage_result 
        WHERE matches IS NOT NULL 
          AND matches LIKE '%"categories"%'
        """
    )
    total = cur.fetchone()[0]
    conn.close()
    print(f"Found {total:,} enriched filings\n")

    # Create temp directory for intermediate files
    temp_dir = Path(tempfile.mkdtemp(prefix="export_"))
    print(f"📁 Intermediate files: {temp_dir}")

    try:
        # Set up queues
        batch_queue = Queue(maxsize=PREFETCH_BATCHES)
        result_queue = Queue(maxsize=WORKERS * 2)
        stop_fetch = Event()
        stop_write = Event()

        # Start background threads
        fetcher = Thread(
            target=fetch_worker, args=(db_path, batch_queue, stop_fetch), daemon=True
        )
        writer = Thread(
            target=write_worker, args=(result_queue, temp_dir, stop_write), daemon=True
        )

        fetcher.start()
        writer.start()

        processed = 0
        batches_processed = 0

        with ProcessPoolExecutor(max_workers=WORKERS) as executor:
            futures = {}  # {future: batch_id}

            while True:
                # Keep submitting work while we have capacity
                while len(futures) < WORKERS * 2:
                    try:
                        item = batch_queue.get_nowait()
                        if item is None:  # Sentinel
                            batch_queue.put(None)  # Put it back for safety
                            break

                        batch_id, batch = item
                        future = executor.submit(process_batch, batch)
                        futures[future] = batch_id
                    except:
                        break

                # No more batches and no pending work
                if not futures:
                    break

                # Wait for at least one future to complete
                done, pending = as_completed(futures).__next__(), set(futures.keys())

                try:
                    batch_results = done.result()
                    batch_id = futures[done]

                    # Send to write worker
                    result_queue.put((batch_id, batch_results))

                    processed += len(batch_results)
                    batches_processed += 1

                    if batches_processed % 20 == 0:
                        print(
                            f"   → {processed:,} filings processed ({batches_processed} batches)..."
                        )

                except Exception as e:
                    print(f"Error processing batch: {e}")

                # Remove completed future
                futures = {f: bid for f, bid in futures.items() if f != done}

        # Signal write worker to finish
        result_queue.put(None)
        stop_fetch.set()
        stop_write.set()

        print(f"\n⏳ Waiting for write worker to finish...")
        writer.join(timeout=30)
        fetcher.join(timeout=1)

        print(f"✓ Processing complete: {processed:,} firm-years")

        # Merge all intermediate files
        total_written = merge_files(temp_dir, csv_path)

        print(f"\n✅ Finished! {total_written:,} records written to {csv_path}")
        if total > 0:
            print(
                f"   Average per filing: {total_written/total:.2f} records (should be ~1.0)"
            )

    finally:
        # Cleanup temp directory
        print(f"\n🧹 Cleaning up temporary files...")
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    db = input("Enter database name: ").strip().split(".db")[0]
    export_users_production(f"{db}.db")
