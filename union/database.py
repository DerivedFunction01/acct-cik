# %%
## Initialization
import sqlite3
from tqdm import tqdm
from pathlib import Path
import pandas as pd
import subprocess
import re

# =============================================================================
# CONFIGURATION
# =============================================================================

DRIVE_PATH = "./drive/MyDrive/db"
IS_COLAB = Path(DRIVE_PATH).exists()

DB_PATH = "web_data.db"
REPORT_CSV_PATH = "report_data.csv"
NAMES_CSV_PATH = "names_export.csv"

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


def extract_accession(url):
    if not isinstance(url, str):
        return None
    # Simple extraction for 18-digit accession number
    # Matches /data/CIK/ACCESSION/ or just /ACCESSION/
    match = re.search(r"/(\d{18})/", url)
    if match:
        return match.group(1)
    return None


def import_report_data_from_csv():
    """
    Imports data from report_data.csv into the report_data and names tables.
    Matches the schema:
    - report_data: cik, year, url, accession, original_url
    - names: cik, name
    """
    print(f"\n[1/3] Searching for '{REPORT_CSV_PATH}' file...")
    csv_files = _ensure_file_is_local(REPORT_CSV_PATH)

    if not csv_files:
        print(f"  -> ❌ No '{REPORT_CSV_PATH}' file found to import.")
        return

    csv_path = csv_files[0]

    print(f"\n[2/3] Reading data from '{csv_path}'...")
    try:
        # Check columns first to enforce string dtype for accession to prevent precision loss
        header = pd.read_csv(csv_path, nrows=0)
        dtype_map = {}
        if "accession" in header.columns:
            dtype_map["accession"] = str
        df = pd.read_csv(csv_path, dtype=dtype_map)
        print(f"  -> Found {len(df):,} records in CSV.")
    except Exception as e:
        print(f"  -> ❌ Error reading CSV file: {e}")
        return

    if "cik" not in df.columns or "year" not in df.columns or "url" not in df.columns:
        print("  -> ❌ Error: CSV file is missing 'cik', 'year', or 'url' columns.")
        return

    print(f"\n[3/3] Connecting to database '{DB_PATH}'...")
    conn = sqlite3.connect(DB_PATH)
    try:
        # 1. Import Names
        # Check for names_export.csv first
        names_files = _ensure_file_is_local(NAMES_CSV_PATH)
        if names_files:
            print(f"  -> Found '{NAMES_CSV_PATH}'. Importing names from there...")
            try:
                names_df = pd.read_csv(names_files[0])
                if "cik" in names_df.columns and "name" in names_df.columns:
                    names_df = names_df[["cik", "name"]].dropna().drop_duplicates()
                    names_df.to_sql("names", conn, if_exists="replace", index=False)
                    conn.execute("CREATE INDEX IF NOT EXISTS name_idx ON names (name)")
                    print(f"     ✅ Imported {len(names_df)} names.")
            except Exception as e:
                print(f"     ❌ Error importing names from '{NAMES_CSV_PATH}': {e}")
        elif "name" in df.columns:
            print("  -> Importing names from report_data (fallback)...")
            names_df = df[["cik", "name"]].dropna().drop_duplicates()
            names_df.to_sql("names", conn, if_exists="replace", index=False)
            conn.execute("CREATE INDEX IF NOT EXISTS name_idx ON names (name)")

        # 2. Import Report Data
        print("  -> Preparing report_data...")

        # Ensure schema columns
        if "accession" not in df.columns:
            df["accession"] = df["url"].apply(extract_accession)
        else:
            # Ensure it is padded and cleaned if imported
            df["accession"] = (
                df["accession"].astype(str).str.replace(r"\.0$", "", regex=True)
            )
            df["accession"] = df["accession"].apply(
                lambda x: (
                    x.zfill(18) if x and x.lower() not in ("nan", "none", "") else None
                )
            )

        if "original_url" not in df.columns:
            df["original_url"] = df["url"]

        # Select columns matching schema
        report_df = df[["cik", "year", "url", "accession", "original_url"]]

        # Drop rows where essential info is missing
        report_df = report_df.dropna(subset=["cik", "year", "url"])

        report_df.to_sql("report_data", conn, if_exists="replace", index=False)

        # Re-create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS url_idx ON report_data (url)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS report_acc_idx ON report_data (accession)"
        )

        print("✅ Import successful.")
    except Exception as e:
        print(f"  -> ❌ A database error occurred during import: {e}")
        conn.rollback()
    finally:
        conn.close()


def export_data_to_csv():
    """
    Exports report_data and names tables to CSV files.
    """
    print(f"\nExporting data from '{DB_PATH}'...")
    if not Path(DB_PATH).exists():
        print(f"❌ Database file '{DB_PATH}' not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        # Export report_data
        print("  -> Exporting report_data...")
        try:
            df_report = pd.read_sql("SELECT * FROM report_data", conn)

            # Ensure accession is formatted correctly as string and 0-padded
            if "accession" in df_report.columns:
                # Fill NaN values first, then convert to string
                df_report["accession"] = (
                    df_report["accession"]
                    .fillna("")
                    .astype(str)
                    .apply(
                        lambda x: (
                            x.zfill(18)
                            if x and x not in ("nan", "none", "", "NaN")
                            else ""
                        )
                    )
                )

            df_report.to_csv(REPORT_CSV_PATH, index=False)
            print(f"     ✅ Saved {len(df_report)} rows to {REPORT_CSV_PATH}")
        except Exception as e:
            print(f"     ❌ Error exporting report_data: {e}")

        # Export names
        print("  -> Exporting names...")
        try:
            df_names = pd.read_sql("SELECT * FROM names", conn)
            df_names.to_csv(NAMES_CSV_PATH, index=False)
            print(f"     ✅ Saved {len(df_names)} rows to {NAMES_CSV_PATH}")
        except Exception as e:
            print(f"     ❌ Error exporting names: {e}")

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
    print("2. Custom SQL Query")
    print("3. Import report_data from CSV")
    print("4. Save database to Google Drive (Colab only)")
    print("5. Inspect last DataFrame")
    print("6. Export report_data and names to CSV")
    print("7. Exit")
    print("-" * 50)

    while True:
        choice = input("Enter your choice: ").strip()
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
        elif choice == "3":
            import_report_data_from_csv()
        elif choice == "4":
            save_db_to_drive()
        elif choice == "5":
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
        elif choice == "6":
            export_data_to_csv()
        elif choice == "7":
            print("Exiting the program.")
            break
        else:
            print("Invalid choice. Please try again.")
        print("-" * 50)

# %%
