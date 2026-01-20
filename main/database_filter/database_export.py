# database_export_aggregated.py
# =============================================================================
# EXPORT SCRIPT: ACTIVE USERS TO CSV (WITH AGGREGATION)
# =============================================================================
# 1. Extracts categories in parallel
# 2. Aggregates duplicate (CIK, YEAR) pairs via Union (OR) logic

import sqlite3
import json
import multiprocessing as mp
import pandas as pd
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import subprocess
from tqdm import tqdm
from typing import Optional, List, Tuple

# =============================================================================
# CONFIGURATION
# =============================================================================

BATCH_SIZE = 5000
WORKERS = max(1, mp.cpu_count() - 1)

# =============================================================================
# WORKER LOGIC
# =============================================================================


def process_batch(batch):
    """
    Process a batch of raw database rows.
    Returns a list of tuples: (cik, year, ir, fx, cp, eq, cr, warr, gen)
    """
    results = []

    for url, cik, year, categories_json in batch:
        if not categories_json:
            continue

        try:
            categories_array = json.loads(categories_json)
        except json.JSONDecodeError:
            continue

        doc_cat_set = set()
        for combined_cat_str in categories_array:
            individual_cats = combined_cat_str.lower().split("_")
            for cat in individual_cats:
                if cat and cat not in {"other", "unknown", "table"}:
                    doc_cat_set.add(cat)

        # Create binary flags
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
    conn.execute("PRAGMA query_only=1")

    cur = conn.cursor()
    # Note: We fetch URL to join properly, but we only care about CIK/Year for grouping
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
# AGGREGATION LOGIC
# =============================================================================


def aggregate_and_save(temp_csv_path: Path, final_csv_path: Path):
    """
    Reads the raw extraction, groups by (CIK, Year), performs logical OR, and saves.
    """
    print(f"\n🔄 Aggregating duplicate (CIK, Year) entries...")

    # Read the temp CSV using Pandas
    # Use chunksize if the file is larger than RAM (e.g., >2GB)
    # For typical SEC data (<1M rows), reading all at once is fine.
    try:
        df = pd.read_csv(temp_csv_path)
    except pd.errors.EmptyDataError:
        print("⚠️ No data found to aggregate.")
        return

    initial_count = len(df)

    # Group by CIK and Year, then take the Max (which acts as bitwise OR for 0/1)
    # 1 OR 0 = 1, 0 OR 0 = 0, 1 OR 1 = 1
    grouped_df = df.groupby(["cik", "year"], as_index=False).max()

    final_count = len(grouped_df)

    # Save Final
    grouped_df.to_csv(final_csv_path, index=False)

    # Clean up temp file
    temp_csv_path.unlink()

    print(f"   Original Rows: {initial_count:,}")
    print(f"   Final Unique (CIK, Year): {final_count:,}")
    print(f"   Merged duplicates: {initial_count - final_count:,}")


# =============================================================================
# MAIN CONTROLLER
# =============================================================================


def export_users_production(db_path: str, csv_path: Optional[str] = None):
    db = Path(db_path)
    if not db.exists():
        print(f"❌ Database not found: {db}")
        return

    folder_name = "analysis_output"
    output_folder = Path(folder_name)
    output_folder.mkdir(exist_ok=True)

    if csv_path is None:
        csv_path = db.stem + ".csv"

    final_output_path = output_folder / csv_path
    temp_output_path = output_folder / "temp_raw_extraction.csv"

    print(f"{'=' * 60}")
    print(f"EXPORTING ACTIVE YEAR-END USERS (WITH AGGREGATION)")
    print(f"Source: {db.name}")
    print(f"Temp Output: {temp_output_path}")
    print(f"Final Output: {final_output_path}")
    print(f"Workers: {WORKERS}")
    print(f"{'=' * 60}")

    # 1. Parallel Extraction to Temp File
    print("🚀 Starting extraction...\n")

    total_records = 0

    # Open temp file
    with open(temp_output_path, "w", encoding="utf-8") as outfile:
        # Write header
        headers = [
            "cik",
            "year",
            "ir_user",
            "fx_user",
            "cp_user",
            "eq_user",
            "cr_user",
            "warr_user",
            "gen_user",
        ]
        outfile.write(",".join(headers) + "\n")

        with ProcessPoolExecutor(max_workers=WORKERS) as executor:
            futures = []
            for batch in tqdm(
                fetch_all_data(db_path), desc="🔄 Fetching batches", unit="batch"
            ):
                future = executor.submit(process_batch, batch)
                futures.append(future)

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
                except Exception as e:
                    print(f"  ❌ Batch processing error: {e}")

    print(f"\n✅ Extraction Complete. Raw records: {total_records:,}")

    # 2. Aggregation Step
    if total_records > 0:
        aggregate_and_save(temp_output_path, final_output_path)
        print(f"\n✅ Export Complete: {final_output_path}")
    else:
        print("\n⚠️ No records extracted.")
        if temp_output_path.exists():
            temp_output_path.unlink()


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
