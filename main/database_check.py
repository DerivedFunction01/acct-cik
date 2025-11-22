# populate_categories_parallel.py
# Fast, resumable, parallel category tagging with ProcessPoolExecutor
# Skips URLs that already have categories for the given stage

import sqlite3
import json
import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional
from tqdm import tqdm
import multiprocessing as mp

from derivative_regex import (
    build_ir_regex,
    build_fx_regex,
    build_cp_regex,
    build_eq_regex,
    build_strict_gen_regex,
    build_soft_gen_regex,
)

# ——————————————————————————————————————————————————————————————
# Regex setup (same as before)
# ——————————————————————————————————————————————————————————————
IR_REGEX = build_ir_regex()
FX_REGEX = build_fx_regex()
CP_REGEX = build_cp_regex()
EQ_REGEX = build_eq_regex()
GEN_STRICT = build_strict_gen_regex()
GEN_SOFT = build_soft_gen_regex()

REGEX_TO_CAT = [
    (IR_REGEX, "ir"),
    (FX_REGEX, "fx"),
    (CP_REGEX, "cp"),
    (EQ_REGEX, "eq"),
    (GEN_STRICT, "gen"),
    (GEN_SOFT, "gen"),
]

BATCH_SIZE = 1000
# ——————————————————————————————————————————————————————————————
# Worker function — pure, no DB access
# ——————————————————————————————————————————————————————————————
def process_url_batch(batch):
    results = []
    for url, matches_json in batch:
        try:
            sentences = json.loads(matches_json)
            if not isinstance(sentences, list):
                continue
        except json.JSONDecodeError:
            continue

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            found = False
            for regex, cat in REGEX_TO_CAT:
                if regex.search(sent):
                    results.append((url, sent, cat, "regex"))
                    found = True
                    break
            if not found:
                results.append((url, sent, "other", "regex"))
    return results


# ——————————————————————————————————————————————————————————————
# Main function — now parallel + resumable
# ——————————————————————————————————————————————————————————————
def populate_category_table_parallel(
    db_path: str, stage_name: str, num_workers: Optional[int] = None
):
    db = Path(db_path)
    if not db.exists():
        print(f"Skipping {db.name} — not found")
        return

    print(f"Populating category_result in {db.name} (stage = {stage_name}) ...")
    conn = sqlite3.connect(db, timeout=60)
    cur = conn.cursor()

    # Create table + indexes
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS category_result (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            sentence TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('ir','fx','cp','eq','gen','other')),
            source TEXT NOT NULL DEFAULT 'regex',
            stage TEXT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(url) REFERENCES webpage_result(url) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_category_url_stage ON category_result(url, stage);
    """
    )
    conn.commit()

    # ——— Find URLs that are NOT yet processed for this stage ———
    cur.execute(
        """
        SELECT wr.url, wr.matches
        FROM webpage_result wr
        LEFT JOIN category_result cr ON wr.url = cr.url AND cr.stage = ?
        WHERE wr.matches IS NOT NULL AND cr.url IS NULL
    """,
        (stage_name,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"All URLs already processed for stage '{stage_name}' in {db.name}")
        return

    total_urls = len(rows)
    print(f"Found {total_urls:,} URLs needing category tagging")

    # ——— Parallel processing ———
    num_workers = num_workers or max(1, mp.cpu_count() - 1)
    batch_size = 100  # good balance

    batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]
    all_inserts = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(process_url_batch, batch) for batch in batches]

        for future in tqdm(as_completed(futures), total=len(futures), desc="Tagging"):
            all_inserts.extend(future.result())

            # Batch write every N rows
            if len(all_inserts) >= BATCH_SIZE:
                _write_batch(db_path, all_inserts, stage_name)
                all_inserts.clear()

    # Final write
    if all_inserts:
        _write_batch(db_path, all_inserts, stage_name)

    print(f"Completed {db.name} → {total_urls:,} URLs processed\n")


def _write_batch(db_path: str, rows: list, stage_name: str):
    conn = sqlite3.connect(db_path, timeout=60)
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO category_result (url, sentence, category, source, stage)
        VALUES (?, ?, ?, ?, ?)
    """,
        [(url, sent, cat, src, stage_name) for url, sent, cat, src in rows],
    )
    conn.commit()
    conn.close()


# ——————————————————————————————————
# Run on all databases — safe & resumable
# ——————————————————————————————————
if __name__ == "__main__":
    import sys

    # Optional: pass number of workers via CLI
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else None

    populate_category_table_parallel("prepared_data.db", "prepared", workers)
    populate_category_table_parallel("hedge_data.db", "hedge", workers)
    populate_category_table_parallel("current_data.db", "current", workers)
    populate_category_table_parallel("active_data.db", "active", workers)
