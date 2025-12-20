# database_export_FIXED_v2.py
# =============================================================================
# EXPORT SCRIPT: ACTIVE USERS TO CSV (PRODUCTION READY)
# =============================================================================
# Simplified, robust version without thread-queue complexity

import sqlite3
import json
import multiprocessing as mp
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import subprocess
from tqdm import tqdm
from typing import Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

BATCH_SIZE = 5000
WORKERS = max(1, mp.cpu_count() - 1)

# =============================================================================
# WORKER LOGIC
# =============================================================================


# --- MODIFIED: process_batch in database_export.py ---
def process_batch(batch):
    results = []
    # Row: (url, cik, year, matches_json, categories_json)
    # NOTE: Assuming categories_json now holds the array of "ir_fx", "eq_gen", etc.
    for url, cik, year, categories_json in batch:

        if not categories_json or categories_json == "[]":
            continue

        try:
            # 1. Load the array of combined category strings
            categories_array = json.loads(categories_json)
        except json.JSONDecodeError:
            continue

        # 2. Extract Unique Categories using the underscore convention
        doc_cat_set = set()
        for combined_cat_str in categories_array:
            # Split the combined string (e.g., "ir_fx_gen" -> ["ir", "fx", "gen"])
            individual_cats = combined_cat_str.lower().split("_")

            # Add all individual categories to the document set
            for cat in individual_cats:
                if cat and cat not in {"other", "unknown", "table"}:
                    doc_cat_set.add(cat)

        if not doc_cat_set:
            continue

        # 3. Create Binary Flags based on the final document set
        results.append(
            (
                cik,
                year,
                1 if "ir" in doc_cat_set else 0,
                1 if "fx" in doc_cat_set else 0,
                1 if "cp" in doc_cat_set else 0,
                1 if "eq" in doc_cat_set else 0,
                1 if "cr" in doc_cat_set else 0,
                1 if "warr" in doc_cat_set else 0,
                1 if "gen" in doc_cat_set else 0,
            )
        )
    return results


def fetch_all_data(db_path: str):
    """Fetch all data from database in batches."""
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA query_only=1")

    cur = conn.cursor()

    query = """
        SELECT rd.url, rd.cik, rd.year, cat.categories
        FROM category cat
        JOIN report_data rd ON cat.url = rd.url
    """

    cur.execute(query)

    batch = []
    while True:
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            if batch:
                yield batch
            break
        batch.extend(rows)
        if len(batch) >= BATCH_SIZE:
            yield batch
            batch = []

    conn.close()


# =============================================================================
# MAIN CONTROLLER
# =============================================================================


def export_users_production(db_path: str, csv_path: Optional[str] = None):
    db = Path(db_path)
    if not db.exists():
        print(f"❌ Database not found: {db}")
        return

    # Create output folder if it doesn't exist
    folder_name = "analysis_output"
    output_folder = Path(folder_name)
    output_folder.mkdir(exist_ok=True)

    if csv_path is None:
        csv_path = (db.stem + "_active_users.csv")

    print(f"{'=' * 60}")
    print(f"EXPORTING ACTIVE YEAR-END USERS")
    print(f"Source: {db.name}")
    print(f"Target: {csv_path}")
    print(f"Workers: {WORKERS}")
    print(f"{'=' * 60}")

    # 1. Pre-Scan Counts
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("🔍 Scanning Database...")

    # Count Active
    cur.execute(
        "SELECT COUNT(*) FROM category"
    )
    active_count = cur.fetchone()[0]

    # # Count Terminated
    # cur.execute("SELECT COUNT(*) FROM webpage_result WHERE matches = '[]'")
    # terminated_count = cur.fetchone()[0]

    # conn.close()

    # print(f"   Active Year-End Users: {active_count:,}")
    # print(f"   Terminated During Year: {terminated_count:,} (Skipped)")
    # print(f"   Total Records: {active_count + terminated_count:,}\n")

    if active_count == 0:
        print("⚠️  No active users found. Check your filtering logic.")
        return

    # 2. Execution: Fetch, Process, Write
    print("🚀 Starting export...\n")

    total_records = 0
    processed_batches = 0

    with open(csv_path, "w", encoding="utf-8") as outfile:
        # Write header
        outfile.write(
            "cik,year,ir_user,fx_user,cp_user,eq_user,cr_user,warr_user,gen_user\n"
        )

        # Process batches with progress bar
        with ProcessPoolExecutor(max_workers=WORKERS) as executor:
            # Submit all batches
            futures = []
            for batch in tqdm(
                fetch_all_data(db_path), desc="🔄 Fetching batches", unit="batch"
            ):
                future = executor.submit(process_batch, batch)
                futures.append(future)

            # Collect results as they complete
            print(f"\n📊 Processing {len(futures)} batches...\n")
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="⚙️  Processing",
                unit="batch",
            ):
                try:
                    batch_results = future.result()
                    for row in batch_results:
                        outfile.write(",".join(map(str, row)) + "\n")
                        total_records += 1
                    processed_batches += 1
                except Exception as e:
                    print(f"  ❌ Batch processing error: {e}")
    # Move the file to the folder
    subprocess.run(["mv", csv_path, str(output_folder)])

    print(f"\n✅ Export Complete: {csv_path}")
    print(f"   Total Records Written: {total_records:,}")
    print(f"   Batches Processed: {processed_batches:,}")


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

    import sys

    if len(sys.argv) > 1:
        db_name = sys.argv[1]
        csv_name = sys.argv[2] if len(sys.argv) > 2 else None
        export_users_production(db_name, csv_name)
    else:
        default_db = "classified_data.db"
        db_input = input(f"Enter database (default: {default_db}): ").strip()
        db_name = db_input or default_db

        if not db_name.endswith(".db"):
            db_name += ".db"

        export_users_production(db_name)
