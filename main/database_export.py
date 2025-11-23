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