# =============================================================================
# CLASSIFICATION RESULTS MERGE SCRIPT
# =============================================================================
# This script is designed to merge the output from the distributed
# `classify_from_db.py` script back into the central database.
#
# It performs the following steps:
# 1. Finds all `classification_results_chunk_*.parquet` files.
# 2. If running in Colab, it ensures all chunks are copied locally from GDrive.
# 3. Reads, concatenates, and de-duplicates the data from all chunks.
# 4. Inserts the final, clean data into the `classification_results` table
#    in the `clean_web_data.db` database.
# =============================================================================

import json
import sqlite3
import numpy as np
from tqdm import tqdm
from pathlib import Path
import pandas as pd
import code
import subprocess

# =============================================================================
# CONFIGURATION
# =============================================================================

DRIVE_PATH = "./drive/MyDrive/db"
IS_COLAB = Path(DRIVE_PATH).exists()

DB_PATH = "clean_web_data.db"
PARQUET_PATTERN = "classification_results_chunk_*.parquet"
RESULTS_TABLE = "classification_results"

# =============================================================================
# HELPER FUNCTIONS (Adapted from database.py)
# =============================================================================


def _ensure_files_are_local(file_pattern: str) -> list[Path]:
    """
    Checks for files matching a pattern locally. If not found and in Colab,
    copies them from Google Drive.
    """
    local_files = list(Path(".").glob(file_pattern))

    if local_files:
        print(f"  -> Found {len(local_files)} matching file(s) locally.")

    if IS_COLAB:
        print(f"  -> Checking Google Drive for additional files: '{DRIVE_PATH}'...")
        drive_files = list(Path(DRIVE_PATH).glob(file_pattern))

        if not drive_files:
            print("  -> No matching files found in Google Drive.")
            return local_files

        # Determine which files need to be copied
        local_filenames = {f.name for f in local_files}
        files_to_copy = [df for df in drive_files if df.name not in local_filenames]

        if not files_to_copy:
            print("  -> All Google Drive files are already present locally.")
            return local_files

        print(f"  -> Found {len(files_to_copy)} new file(s) in Drive. Copying...")
        for drive_file in tqdm(files_to_copy, desc="  Copying from Drive"):
            local_dest = Path(".") / drive_file.name
            try:
                subprocess.run(["cp", str(drive_file), str(local_dest)], check=True)
                local_files.append(local_dest)
            except Exception as e:
                print(f"  -> ❌ Error copying {drive_file.name}: {e}")

    return local_files


def execute_sql(sql: str, head: int = 0) -> pd.DataFrame | int:
    """
    Execute a SQL statement on the clean database.
    """
    if not Path(DB_PATH).exists():
        print(f"❌ Cannot execute SQL: Database file '{DB_PATH}' not found.")
        return -1

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    is_select = sql.strip().upper().startswith("SELECT")

    try:
        cursor.execute(sql)
        if is_select:
            columns = [col[0] for col in cursor.description]
            data = cursor.fetchall()
            df = pd.DataFrame(data, columns=columns)
            if head > 0:
                return df.head(head)
            return df
        else:
            conn.commit()
            return cursor.rowcount
    finally:
        conn.close()


def save_db_to_drive():
    """
    Saves the local database file to Google Drive if running in Colab.
    """
    if not IS_COLAB:
        print("❌ Not running in Google Colab environment. Skipping save to Drive.")
        return

    print(f"Attempting to save '{DB_PATH}' to Google Drive at '{DRIVE_PATH}'...")
    # Use an atomic move to prevent corruption if the copy is interrupted
    save_cmd = f"cp -f {DB_PATH} {DRIVE_PATH}/{DB_PATH}.tmp && mv -f {DRIVE_PATH}/{DB_PATH}.tmp {DRIVE_PATH}/{DB_PATH}"
    try:
        subprocess.run(save_cmd, shell=True, check=True, capture_output=True)
        print(f"✅ Successfully saved '{DB_PATH}' to Google Drive.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error saving to Google Drive: {e.stderr.decode()}")
    except Exception as e:
        print(f"❌ An unexpected error occurred while saving to Drive: {e}")


def serialize_value(v):
    """
    Convert pandas/numpy types to SQLite-compatible types.
    Handles: NaN, numpy arrays, bytes, and standard types.
    """
    # Handle None explicitly
    if v is None:
        return None

    # Handle NaN/NaT values
    if isinstance(v, float) and np.isnan(v):
        return None
    if pd.isna(v):
        return None

    # Handle numpy arrays - convert to JSON string
    if isinstance(v, np.ndarray):
        return json.dumps(v.tolist())

    # Handle bytes - decode to UTF-8 string
    if isinstance(v, bytes):
        try:
            return int.from_bytes(v, 'little', signed=True) # Prefer deserializing to integer
        except (TypeError, ValueError, OverflowError):
            return v.decode('utf-8', errors='ignore') # Fallback to string

    # Handle numpy scalars (np.bool_, np.int64, etc.)
    if isinstance(v, np.generic):
        return v.item()

    # Handle pandas Series or other container types (shouldn't happen but safe)
    if isinstance(v, (pd.Series, list, dict)):
        return json.dumps(v.tolist() if isinstance(v, pd.Series) else v)

    # Return as-is for native Python types (str, int, float, bool)
    return v


def import_classification_results_from_parquet():
    """
    Imports data from `classification_results_chunk_*.parquet` files into
    the `classification_results` table using pandas.to_sql().
    """
    print(f"\n[1/4] Searching for '{PARQUET_PATTERN}' files...")
    parquet_files = _ensure_files_are_local(PARQUET_PATTERN)

    if not parquet_files:
        print("  -> ❌ No Parquet chunk files found to import.")
        return

    print(f"\n[2/4] Reading and concatenating {len(parquet_files)} Parquet files...")
    all_dfs = [pd.read_parquet(f) for f in tqdm(parquet_files, desc="  Reading files")]
    combined_df = pd.concat(all_dfs, ignore_index=True)
    print(f"  -> Concatenated to {len(combined_df):,} total records.")

    print("\n[3/4] Dropping duplicate records (keeping last entry)...")
    combined_df.drop_duplicates(subset=["url"], keep="last", inplace=True)
    print(f"  -> {len(combined_df):,} unique records remain.")

    # Ensure all required columns exist
    required_cols = [
        "url",
        "category",
        "cik",
        "year",
        "found_policy",
        "found_existence",
        "found_notional",
        "found_pnl",
        "status",
        "duration_s",
        "error_message",
    ]
    if not all(col in combined_df.columns for col in required_cols):
        print("  -> ❌ Error: Parquet files are missing one or more required columns.")
        print(f"     Expected: {required_cols}")
        print(f"     Found:    {list(combined_df.columns)}")
        return

    # Select only required columns and ensure correct order
    combined_df = combined_df[required_cols]

    print("\n[4/4] Inserting records into database...")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Since we want to handle duplicates (update if exists), we use INSERT OR REPLACE
        # This is more efficient than if_exists='replace' which would drop the whole table
        records = combined_df.values.tolist()

        print(f"  Inserting {len(records):,} records (updating duplicates)...")
        with tqdm(total=len(records), desc="  Inserting to DB") as pbar:
            chunk_size = 10000
            for i in range(0, len(records), chunk_size):
                chunk = records[i : i + chunk_size]
                cursor.executemany(
                    f"""INSERT OR REPLACE INTO {RESULTS_TABLE}
                       (url, category, cik, year, found_policy, found_existence, found_notional, found_pnl, status, duration_s, error_message)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    chunk,
                )
                pbar.update(len(chunk))

        conn.commit()

        print(f"✅ Successfully imported/updated {len(combined_df):,} records.")

        # Show summary statistics
        summary_df = execute_sql(
            f"""
            SELECT 
                category,
                COUNT(*) as total_records,
                SUM(found_policy) as with_policy,
                SUM(found_notional) as with_notional,
                SUM(found_existence) as with_existence,
                SUM(found_pnl) as with_pnl
            FROM {RESULTS_TABLE}
        """
            "GROUP BY category"
        )
        if isinstance(summary_df, pd.DataFrame):
            print("\n📊 Database Summary:")
            print(summary_df.to_string(index=False))

    except Exception as e:
        print(f"  -> ❌ An error occurred during import: {e}")
        import traceback

        traceback.print_exc()


# =============================================================================
# MAIN INTERACTIVE MENU
# =============================================================================

if __name__ == "__main__":
    last_df = None  # Variable to hold the last queried DataFrame

    while True:
        print("\n" + "=" * 50)
        print("Database Management Menu")
        print("=" * 50)
        print(f"  Database: {DB_PATH}")
        print("1. Merge Parquet chunks into database")
        print("2. Query classification_results table")
        print("3. Run Custom SQL Query")
        print("4. Save database to Google Drive (Colab only)")
        print("5. Inspect last DataFrame")
        print("6. Exit")
        print("-" * 50)

        choice = input("Enter your choice (1-6): ").strip()

        if choice == "1":
            try:
                import_classification_results_from_parquet()
            except Exception as e:
                print(f"\n❌ An unexpected error occurred: {e}")
                import traceback

                traceback.print_exc()

        elif choice == "2":
            df = execute_sql(f"SELECT * FROM {RESULTS_TABLE}")
            if isinstance(df, pd.DataFrame):
                last_df = df
                print(f"\n📊 Showing first 20 of {len(df):,} records:\n")
                print(df.head(20))
                print("\n" + "-" * 30)
                print("Summary Statistics:")
                print(f"  Total records: {len(df):,}")
                print(
                    f"  With policy evidence: {df['found_policy'].sum():,} ({df['found_policy'].sum()/len(df)*100:.1f}%)"
                )
                print(
                    f"  With notional amounts: {df['found_notional'].sum():,} ({df['found_notional'].sum()/len(df)*100:.1f}%)"
                )
                print(
                    f"  With position existence: {df['found_existence'].sum():,} ({df['found_existence'].sum()/len(df)*100:.1f}%)"
                )
                print(
                    f"  With P&L impact: {df['found_pnl'].sum():,} ({df['found_pnl'].sum()/len(df)*100:.1f}%)"
                )
                print(f"\n  Average processing time: {df['duration_s'].mean():.2f}s")
                print(
                    f"  Min/Max processing time: {df['duration_s'].min():.2f}s / {df['duration_s'].max():.2f}s"
                )
                print(f"\n  Status breakdown:")
                print(df["status"].value_counts())

        elif choice == "3":
            custom_sql = input("Enter your SQL query: ").strip()
            if custom_sql:
                result = execute_sql(custom_sql)
                if isinstance(result, pd.DataFrame):
                    last_df = result
                    print(result)
                else:
                    print(f"Query executed successfully, {result} rows affected.")

        elif choice == "4":
            save_db_to_drive()

        elif choice == "5":
            if last_df is not None and not last_df.empty:
                print("Last DataFrame is available as 'last_df'.")
                print("Type 'exit' or press Ctrl+D to return to the menu.")
                code.interact(local=locals())
            else:
                print("No DataFrame has been loaded yet. Run a query first.")

        elif choice == "6":
            print("Exiting.")
            break

        else:
            print("Invalid choice. Please try again.")
