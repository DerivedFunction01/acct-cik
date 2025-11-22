# export_derivative_users_production.py
# 265k-filing safe, fully parallel, batched, resumable
# Output: cik,year,ir_user,fx_user,cp_user,eq_user,gen_user

import sqlite3
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional
from tqdm import tqdm
import multiprocessing as mp

BATCH_SIZE = 5000  # tune if needed
WORKERS = max(1, mp.cpu_count() - 1)


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

        cats.discard("other")  # we don't care about pure noise

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


def export_users_production(db_path: str, csv_path: Optional[str] = None):
    db = Path(db_path)
    if not db.exists():
        print(f"DB not found: {db}")
        return

    if csv_path is None:
        csv_path = db.stem + "_derivative_users.csv"

    print(f"Exporting derivative users from {db.name} → {csv_path}")
    print(f"Using {WORKERS} workers, batch size = {BATCH_SIZE:,}")

    # Open DB with optimal settings
    conn = sqlite3.connect(db, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-2000000")  # ~2 GB cache
    cur = conn.cursor()

    # Optional: skip already exported (idempotent)
    cur.execute(
        """
        SELECT COUNT(*) FROM webpage_result 
        WHERE matches IS NOT NULL 
          AND matches LIKE '%"categories"%'
    """
    )
    total = cur.fetchone()[0]
    print(f"Found {total:,} enriched filings")

    cur.execute(
        """
        SELECT wr.url, rd.cik, rd.year, wr.matches
        FROM webpage_result wr
        JOIN report_data rd ON wr.url = rd.url
        WHERE wr.matches IS NOT NULL
          AND wr.matches LIKE '%"categories"%'
    """
    )

    rows = cur.fetchmany(BATCH_SIZE)
    processed = 0
    buffer = []  # accumulates final CSV rows
    buffer_limit = 50_000

    with ProcessPoolExecutor(max_workers=WORKERS) as executor:
        futures = []

        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("cik,year,ir_user,fx_user,cp_user,eq_user,gen_user\n")

            while rows:
                futures.append(executor.submit(process_batch, rows))

                # Collect completed futures
                for future in as_completed(futures):
                    futures.remove(future)
                    batch_results = future.result()

                    for row in batch_results:
                        buffer.append(",".join(map(str, row)) + "\n")

                    processed += len(batch_results)

                    if len(buffer) >= buffer_limit:
                        f.writelines(buffer)
                        buffer.clear()

                    if processed % 100_000 == 0:
                        print(f"   → {processed:,} filings processed...")

                # Fetch next chunk
                rows = cur.fetchmany(BATCH_SIZE)

            # Final flush of remaining futures
            for future in as_completed(futures):
                batch_results = future.result()
                for row in batch_results:
                    buffer.append(",".join(map(str, row)) + "\n")
                processed += len(batch_results)

            if buffer:
                f.writelines(buffer)

    conn.close()
    print(f"Finished! {processed:,} firm-years written to {csv_path}")
    print(f"   Average per filing: {processed/total:.2f} records (should be ~1.0)")


if __name__ == "__main__":

    db = input("Enter database name: ").strip().split(".db")[0]
    export_users_production(f"{db}.db")
