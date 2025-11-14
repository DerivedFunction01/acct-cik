# %%
## Initialization
import sqlite3
from tqdm import tqdm
from pathlib import Path
import pandas as pd
import numpy as np  # Added for np.ndarray type checking
import json
import subprocess

# =============================================================================
# CONFIGURATION
# =============================================================================

DRIVE_PATH = "./drive/MyDrive/db"
IS_COLAB = Path(DRIVE_PATH).exists()

DB_PATH = "web_data.db"
BACKUP_PATH = "analysis_output/server_results_backup.xlsx"
PARQUET_PATTERN = "server_result_chunk_*.parquet"
REPORT_CSV_PATH = "report_data.csv"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _ensure_file_is_local(file_pattern: str) -> list[Path]:
    """
    Checks for files matching a pattern locally. If not found and in Colab,
    copies them from Google Drive.

    Args:
        file_pattern (str): The file name or glob pattern to look for.

    Returns:
        list[Path]: A list of local paths to the found files, or an empty list if none are found.
    """
    local_files = list(Path(".").glob(file_pattern))

    if local_files:
        print(
            f"  -> Found {len(local_files)} matching file(s) in the current directory."
        )
        return local_files

    if IS_COLAB:
        print(f"  -> No local files found. Checking Google Drive: '{DRIVE_PATH}'...")
        drive_files = list(Path(DRIVE_PATH).glob(file_pattern))

        if not drive_files:
            print(f"  -> ❌ No matching files found in Google Drive either.")
            return []

        print(
            f"  -> Found {len(drive_files)} file(s) in Google Drive. Copying to local directory..."
        )
        copied_files = []
        for drive_file in tqdm(drive_files, desc="  Copying from Drive"):
            local_dest = Path(".") / drive_file.name
            try:
                # Use subprocess for a more reliable copy
                subprocess.run(
                    ["cp", str(drive_file), str(local_dest)],
                    check=True,
                    capture_output=True,
                )
                copied_files.append(local_dest)
            except subprocess.CalledProcessError as e:
                print(f"  -> ❌ Error copying {drive_file.name}: {e.stderr.decode()}")
            except Exception as e:
                print(f"  -> ❌ Unexpected error copying {drive_file.name}: {e}")

        if not copied_files:
            print("  -> ❌ No files were successfully copied from Drive.")

        return copied_files

    # Not in Colab and no local files found
    return []


def execute_sql(sql: str, head: int = 0) -> pd.DataFrame | int:
    """
    Execute a SQL statement on a SQLite database.

    Parameters
    ----------
    sql : str
        SQL statement to execute.
    head : int, default 0
        If the query is a SELECT statement and head > 0, return the first `head` rows.
        Otherwise, returns the full DataFrame.

    Returns
    -------
    pd.DataFrame or int
        - For SELECT queries, a pandas DataFrame containing the results.
        - For other queries (INSERT, UPDATE, DELETE, etc.), an integer representing the number of affected rows.
    """
    # Ensure the database file is available locally before connecting
    if not _ensure_file_is_local(DB_PATH):
        print(f"❌ Cannot execute SQL: Database file '{DB_PATH}' not found.")
        return -1

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Automatically determine if the query is a SELECT statement
    is_select = sql.strip().upper().startswith("SELECT")

    try:
        cursor.execute(sql)
        if is_select:
            # Fetch all results for SELECT
            columns = [col[0] for col in cursor.description]
            data = cursor.fetchall()
            df = pd.DataFrame(data, columns=columns)
            if head > 0:
                return df.head(head)  # Return the top `head` rows
            return df
        else:
            # Commit changes for INSERT, UPDATE, DELETE, etc.
            conn.commit()
            return cursor.rowcount
    finally:
        conn.close()


def import_server_backup():
    """
    Imports data from the server backup Excel file into the server_result table.
    Uses INSERT OR REPLACE to handle duplicates, updating existing entries.
    """
    print(f"\nSearching for backup file '{BACKUP_PATH}'...")
    backup_files = _ensure_file_is_local(BACKUP_PATH)
    if not backup_files:
        print(f"❌ Backup file not found.")
        print(
            "   Please run the 'backup_server_results' step in the analysis pipeline first."
        )
        return

    backup_path = backup_files[0]  # Use the first found backup file
    print(f"Attempting to import from '{backup_path}'...")

    try:
        backup_df = pd.read_excel(backup_path)
    except Exception as e:
        print(f"❌ Error reading Excel file: {e}")
        return

    # The backup contains cik, year, url, server_response. We only need url and server_response.
    if "url" not in backup_df.columns or "server_response" not in backup_df.columns:
        print("❌ Error: Backup file is missing 'url' or 'server_response' columns.")
        return

    records_to_insert = backup_df[["url", "server_response"]].to_records(index=False)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Use executemany for efficient batch insertion.
        # INSERT OR REPLACE will update existing rows if the URL (PRIMARY KEY) matches.
        cursor.executemany(
            "INSERT OR REPLACE INTO server_result (url, server_response) VALUES (?, ?)",
            records_to_insert,
        )
        conn.commit()
        print(
            f"✅ Successfully imported/updated {cursor.rowcount} records into 'server_result'."
        )
    except sqlite3.Error as e:
        print(f"❌ A database error occurred during import: {e}")
        conn.rollback()
    finally:
        conn.close()


def import_server_results_from_parquet():
    """
    Imports data from server_result_chunk_*.parquet files into the server_result table.
    Uses INSERT OR REPLACE to handle duplicates, updating existing entries.
    """
    print(f"\n[1/5] Searching for '{PARQUET_PATTERN}' files...")
    parquet_files_to_process = _ensure_file_is_local(PARQUET_PATTERN)

    if not parquet_files_to_process:
        print("  -> ❌ No 'server_result_chunk_*.parquet' files found to import.")
        return

    # Read and concatenate all parquet files
    print("\n[2/5] Reading and concatenating Parquet files...")
    all_dfs = [
        pd.read_parquet(f)
        for f in tqdm(parquet_files_to_process, desc="  Reading files")
    ]
    combined_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
    print(f"  -> Concatenated to {len(combined_df):,} total records.")

    # Drop duplicates, keeping the last entry in case of overlap
    print("\n[3/5] Dropping duplicate records...")
    combined_df.drop_duplicates(subset=["url"], keep="last", inplace=True)
    print(f"  -> {len(combined_df):,} unique records remain.")

    if "url" not in combined_df.columns or "server_response" not in combined_df.columns:
        print(
            "  -> ❌ Error: Parquet files are missing 'url' or 'server_response' columns."
        )
        return

    # Convert the server_response object to a JSON string for better portability
    # and to avoid storing it as a binary blob (pickle) in SQLite.
    def safe_json_dumps(obj):
        if isinstance(obj, np.ndarray):
            return json.dumps(obj.tolist())  # Convert numpy array to a Python list
        elif isinstance(obj, bytes):
            # Attempt to decode bytes to string, ignoring errors for robustness
            return json.dumps(obj.decode("utf-8", errors="ignore"))
        return json.dumps(
            obj
        )  # For other types (list, dict, str, int, float, None), json.dumps handles them

    print("\n[4/5] Serializing 'server_response' column to JSON...")
    tqdm.pandas(desc="  Serializing")
    combined_df["server_response"] = combined_df["server_response"].progress_apply(
        safe_json_dumps
    )

    records_to_insert = combined_df[["url", "server_response"]].to_records(index=False)

    print(f"\n[5/5] Inserting {len(records_to_insert):,} records into the database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Use tqdm to show progress for the database insertion
        with tqdm(total=len(records_to_insert), desc="  Inserting") as pbar:
            # Process in chunks for memory efficiency and better progress reporting
            for i in range(0, len(records_to_insert), 10000):
                chunk = records_to_insert[i : i + 10000]
                cursor.executemany(
                    "INSERT OR REPLACE INTO server_result (url, server_response) VALUES (?, ?)",
                    chunk,
                )
                pbar.update(len(chunk))

        conn.commit()
        print(
            f"\n✅ Successfully imported/updated {cursor.rowcount} records into 'server_result' from {len(parquet_files_to_process)} files."
        )
    except sqlite3.Error as e:
        print(f"  -> ❌ A database error occurred during import: {e}")
    finally:
        conn.close()


def import_report_data_from_csv():
    """
    Imports data from report_data.csv into the report_data table.
    Uses INSERT OR IGNORE to avoid adding duplicate records.
    """
    print(f"\n[1/3] Searching for '{REPORT_CSV_PATH}' file...")
    csv_files = _ensure_file_is_local(REPORT_CSV_PATH)

    if not csv_files:
        print(f"  -> ❌ No '{REPORT_CSV_PATH}' file found to import.")
        return

    csv_path = csv_files[0]

    print(f"\n[2/3] Reading data from '{csv_path}'...")
    try:
        df = pd.read_csv(csv_path)
        print(f"  -> Found {len(df):,} records in CSV.")
    except Exception as e:
        print(f"  -> ❌ Error reading CSV file: {e}")
        return

    if "cik" not in df.columns or "year" not in df.columns or "url" not in df.columns:
        print("  -> ❌ Error: CSV file is missing 'cik', 'year', or 'url' columns.")
        return

    # Keep only necessary columns and drop rows with missing values
    df = df[["cik", "year", "url"]].dropna()

    print(f"\n[3/3] Connecting to database '{DB_PATH}'...")
    conn = sqlite3.connect(DB_PATH)
    try:
        df.to_sql("report_data", conn, if_exists="replace", index=False)
    except Exception as e:
        print(f"  -> ❌ A database error occurred during import: {e}")
        conn.rollback()
    finally:
        conn.close()


def save_db_to_drive():
    """
    Saves the local web_data.db file to Google Drive if running in a Colab environment.
    """
    if not IS_COLAB:
        print("❌ Not running in Google Colab environment. Skipping save to Drive.")
        return

    print(f"Attempting to save '{DB_PATH}' to Google Drive at '{DRIVE_PATH}'...")
    # Use an atomic move operation to prevent corruption if the copy is interrupted
    SAVE_SHELL_CMD = f"cp -f {DB_PATH} {DRIVE_PATH}/{DB_PATH}.tmp && mv -f {DRIVE_PATH}/{DB_PATH}.tmp {DRIVE_PATH}/{DB_PATH}"
    try:
        subprocess.run(SAVE_SHELL_CMD, shell=True, check=True, capture_output=True)
        print(f"✅ Successfully saved '{DB_PATH}' to Google Drive.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error saving to Google Drive: {e.stderr.decode()}")
    except Exception as e:
        print(f"❌ An unexpected error occurred while saving to Drive: {e}")


# =============================================================================
# MAIN INTERACTIVE MENU
# =============================================================================

if __name__ == "__main__":
    last_df = None  # "Global" variable to hold the last queried DataFrame

    print("\n" + "=" * 50)
    print("Database Operations Menu")
    print("=" * 50)
    print("1. SELECT * FROM webpage_result")
    print("2. SELECT * FROM server_result")
    print("3. Custom SQL Query")
    print("4. Import server_result from Excel backup")
    print("5. Import report_data from CSV")
    print("6. Import server_result from Parquet chunks")
    print("7. Save database to Google Drive (Colab only)")
    print("8. Inspect last DataFrame")
    print("9. Exit")
    print("-" * 50)

    while True:
        choice = input("Enter your choice (1-9): ").strip()
        if choice == "1":
            df = execute_sql("SELECT * FROM webpage_result")
            if isinstance(df, pd.DataFrame):
                last_df = df
                print(df.head(20))
                print("-" * 30)
                print("Statistics:")
                print(df.describe())
                print("-" * 30)
        elif choice == "2":
            df = execute_sql("SELECT * FROM server_result")
            if isinstance(df, pd.DataFrame):
                last_df = df
                print(df.head(20))
                print("-" * 30)
                print("Statistics:")
                print(df.describe())
                print("-" * 30)
        elif choice == "3":
            custom_sql = input("Enter your SQL query: ").strip()
            if custom_sql:
                result = execute_sql(custom_sql)
                if isinstance(result, pd.DataFrame):
                    last_df = result
                    print(result)
                    print("-" * 30)
                    print("Statistics:")
                    print(last_df.describe())
                    print("-" * 30)
                else:
                    print(f"Query executed successfully, {result} rows affected.")
            else:
                print("No SQL query entered.")
        elif choice == "4":
            import_server_backup()
        elif choice == "5":
            import_report_data_from_csv()
        elif choice == "6":
            import_server_results_from_parquet()
        elif choice == "7":
            save_db_to_drive()
        elif choice == "8":
            if last_df is not None and not last_df.empty:
                print("Last DataFrame is available as 'last_df'.")
                print(
                    "You can perform operations like 'last_df.iloc[0]' or 'last_df.info()'."
                )
                print(
                    "Type 'exit' or press Ctrl+Z (Windows) / Ctrl+D (Unix) to return to the menu."
                )
                import code

                code.interact(local=locals())
            else:
                print("No DataFrame has been loaded yet. Please run a query first.")
        elif choice == "9":
            print("Exiting the program.")
            break
        else:
            print("Invalid choice. Please try again.")
        print("-" * 50)

#%%
