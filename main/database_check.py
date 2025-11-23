# populate_categories_array.py
# Identical style to all your other scripts — uses JSON array in matches column

import sqlite3
import json
import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional
from tqdm import tqdm
import multiprocessing as mp

from derivative_regex import (
  IR_REGEX,
  FX_REGEX,
  CP_REGEX,
  EQ_REGEX,
  GEN_REGEX,
  STRICT_GEN_REGEX,
  SOFT_GEN_REGEX,
  LOOSE_GEN_REGEX,
)

# ——————————————————————————————————————————————————————————————
# Regex setup
# ——————————————————————————————————————————————————————————————


REGEX_TO_CAT = [
    (IR_REGEX, "ir"),
    (FX_REGEX, "fx"),
    (CP_REGEX, "cp"),
    (EQ_REGEX, "eq"),
    (GEN_REGEX, "gen"),
    (STRICT_GEN_REGEX, "gen"),
    (SOFT_GEN_REGEX, "gen"),
]


# ——————————————————————————————————————————————————————————————
# Worker: returns enriched sentences as list of dicts
# ——————————————————————————————————————————————————————————————
def enrich_sentences(batch):
    results = []
    for url, matches_json in batch:
        try:
            sentences = json.loads(matches_json)
            if not isinstance(sentences, list):
                continue
        except json.JSONDecodeError:
            continue

        enriched = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            cats = set()
            for regex, cat in REGEX_TO_CAT:
                if regex.search(sent):
                    cats.add(cat)
            # If it only matches the gen regex, check to see if we can match the gen_regex (ie swap agreement) to any known types. Strict/soft have hedge, derivative, notional, etc
            if len(cats) == 1 and list(cats)[0] == "gen":
                if GEN_REGEX.search(sent): # (ie swap agreement)
                    pass
                elif LOOSE_GEN_REGEX.search(sent): # ie (swap, contract)
                    pass
                else:
                    pass
            if not cats:
                cats.add("other")  # fallback

            enriched.append(
                {
                    "sentence": sent,
                    "categories": sorted(
                        list(cats)
                    ),  # e.g. ["ir"], ["fx","gen"], ["other"]
                }
            )

        if enriched:
            results.append(
                (url, json.dumps(enriched, ensure_ascii=False, separators=(",", ":")))
            )
    return results


# ——————————————————————————————————————————————————————————————
# Batch writer (same pattern as your other scripts)
# ——————————————————————————————————————————————————————————————
def write_batch(db_path: str, batch_data: list):
    if not batch_data:
        return
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()
    cur.executemany(
        """
        UPDATE webpage_result 
        SET matches = ? 
        WHERE url = ?
    """,
        [(json_str, url) for url, json_str in batch_data],
    )
    conn.commit()
    conn.close()


# ——————————————————————————————————————————————————————————————
# Main function — fully parallel + resumable
# ——————————————————————————————————————————————————————————————
def populate_categories_array(db_path: str, num_workers: Optional[int] = None):
    db = Path(db_path)
    if not db.exists():
        print(f"Skipping {db.name} — not found")
        return

    print(f"Enriching matches with categories in {db.name} ...")
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    # Add column if missing (idempotent)
    try:
        cur.execute(
            "ALTER TABLE webpage_result ADD COLUMN categories_processed INTEGER DEFAULT 0"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column exists

    # Only process URLs not yet enriched
    cur.execute(
        """
        SELECT url, matches 
        FROM webpage_result 
        WHERE matches IS NOT NULL 
          AND (categories_processed IS NULL OR categories_processed = 0)
    """
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"All URLs already enriched in {db.name}")
        return

    print(f"Found {len(rows):,} URLs to enrich")

    num_workers = num_workers or max(1, mp.cpu_count() - 1)
    batch_size = 100
    batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]

    buffer = []
    buffer_size = 5000

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(enrich_sentences, batch) for batch in batches]

        for future in tqdm(as_completed(futures), total=len(futures), desc="Enriching"):
            results = future.result()
            for url, enriched_json in results:
                buffer.append((enriched_json, url))

            if len(buffer) >= buffer_size:
                write_batch(db_path, buffer)
                # Mark as processed
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.executemany(
                    "UPDATE webpage_result SET categories_processed = 1 WHERE url = ?",
                    [(url,) for _, url in buffer],
                )
                conn.commit()
                conn.close()
                buffer.clear()

    # Final flush
    if buffer:
        write_batch(db_path, buffer)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.executemany(
            "UPDATE webpage_result SET categories_processed = 1 WHERE url = ?",
            [(url,) for _, url in buffer],
        )
        conn.commit()
        conn.close()

    print(f"Completed {db.name} — matches now contain 'categories' array\n")


# ——————————————————————————————————
# Run on all your databases
# ——————————————————————————————————
if __name__ == "__main__":
    import sys

    workers = int(sys.argv[1]) if len(sys.argv) > 1 else None
    database = input("Enter database name: ").strip().split(".db")[0]
    populate_categories_array(f"{database}.db", num_workers=workers)
