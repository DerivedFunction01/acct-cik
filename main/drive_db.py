import sqlite3
import pandas as pd
import sys
from pathlib import Path
import pickle
import os.path
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# -------------------------------------------------------------------
# CORE DATABASE MERGE LOGIC (Unchanged)
# -------------------------------------------------------------------


def create_unified_schema(conn):
    """
    Creates a unified schema in the destination database.
    """
    c = conn.cursor()
    print("Creating unified schema in the destination database...")

    # report_data and names are common
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS report_data (
            cik INTEGER,
            year INTEGER,
            url TEXT,
            UNIQUE(cik, year, url)
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOTN EXISTS names (
            cik INTEGER,
            name TEXT,
            UNIQUE(cik, name)
        )
        """
    )
    # From colab.py
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS webpage_result (
            url TEXT PRIMARY KEY,
            matches TEXT,
            FOREIGN KEY (url) REFERENCES report_data(url)
        )
        """
    )
    # From classify-new.py
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS server_result (
            url TEXT PRIMARY KEY,
            server_response TEXT,
            FOREIGN KEY (url) REFERENCES report_data (url)
        )
        """
    )
    # Unified fail_results table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS fail_results (
            cik INTEGER,
            year INTEGER,
            url TEXT,
            reason TEXT,
            UNIQUE(url, reason)
        )
        """
    )

    # Create indices
    c.execute("CREATE INDEX IF NOT EXISTS url_idx_report ON report_data (url)")
    c.execute("CREATE INDEX IF NOT EXISTS url_idx_webpage ON webpage_result (url)")
    c.execute("CREATE INDEX IF NOT EXISTS url_idx_server ON server_result (url)")
    c.execute("CREATE INDEX IF NOT EXISTS name_idx ON names (name)")

    conn.commit()
    print("Schema creation complete.")


def transfer_table_data(source_conn, dest_conn, table_name):
    """
    Transfers data using pandas for reading and `INSERT OR IGNORE` for writing.
    """
    print(f"  Transferring data for table: {table_name}...")
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name}", source_conn)

        if df.empty:
            print(f"    -> No data to transfer for {table_name}.")
            return

        cols = ", ".join(df.columns)
        placeholders = ", ".join(["?"] * len(df.columns))
        sql = f"INSERT OR IGNORE INTO {table_name} ({cols}) VALUES ({placeholders})"

        data_tuples = df.to_records(index=False)

        dest_conn.executemany(sql, data_tuples)
        dest_conn.commit()

        print(
            f"    -> Processed {len(df)} rows from {table_name}. (Duplicates ignored)"
        )

    except (sqlite3.DatabaseError, pd.io.sql.DatabaseError) as e:
        print(
            f"    -> Could not read table '{table_name}'. It might not exist in this source DB. Error: {e}"
        )


def merge_databases(colab_db_path, classify_db_path, merged_db_path):
    """
    Merges two SQLite databases into a new one.
    """
    print(f"\nStarting database merge process...")
    print(f"Source (colab.py): {colab_db_path}")
    print(f"Source (classify-new.py): {classify_db_path}")
    print(f"Destination: {merged_db_path}")

    try:
        with sqlite3.connect(merged_db_path) as dest_conn, sqlite3.connect(
            colab_db_path
        ) as colab_conn, sqlite3.connect(classify_db_path) as classify_conn:

            create_unified_schema(dest_conn)

            colab_tables = ["report_data", "names", "webpage_result", "fail_results"]
            classify_tables = ["report_data", "names", "server_result", "fail_results"]

            print("\nProcessing source DB from colab.py...")
            for table in colab_tables:
                transfer_table_data(colab_conn, dest_conn, table)

            print("\nProcessing source DB from classify-new.py...")
            for table in classify_tables:
                transfer_table_data(classify_conn, dest_conn, table)

        print("\n🎉 Merge complete! The unified database is saved at:", merged_db_path)

    except sqlite3.Error as e:
        print(f"\n❌ A database error occurred: {e}")
        print("Merge failed.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        print("Merge failed.")


# -------------------------------------------------------------------
# NEW GOOGLE DRIVE LOGIC
# -------------------------------------------------------------------

# Scopes: If modifying these, delete token.pickle.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_drive_service():
    """Authenticates and returns a Google Drive API service object."""
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                print("❌ Error: 'credentials.json' not found.")
                print(
                    "Please follow the setup instructions to download it and place it in this directory."
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("drive", "v3", credentials=creds)


def download_file(service, file_id, file_name):
    """Downloads a file from Google Drive."""
    print(f"\nDownloading '{file_name}'...")
    try:
        # Check for overwrite
        local_path = Path(file_name)
        if local_path.exists():
            overwrite = (
                input(f"  File '{file_name}' already exists. Overwrite? (y/n): ")
                .strip()
                .lower()
            )
            if overwrite != "y":
                print("  Download cancelled.")
                return

        request = service.files().get_media(fileId=file_id)
        fh = local_path.open("wb")
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(f"  Download {int(status.progress() * 100)}%.")

        print(f"✅ Successfully downloaded '{file_name}' to the current directory.")

    except Exception as e:
        print(f"❌ An error occurred during download: {e}")


def browse_google_drive(service):
    """Provides an interactive shell to browse and download files from Google Drive."""
    folder_id = "root"
    folder_name = "My Drive"
    folder_stack = []  # To store (id, name) tuples for "up" navigation

    while True:
        print(f"\n--- 🛰️  Browsing Google Drive: {folder_name} ---")
        try:
            # List files and folders
            query = f"'{folder_id}' in parents and trashed=false"
            results = (
                service.files()
                .list(
                    q=query,
                    pageSize=100,
                    fields="files(id, name, mimeType)",
                    orderBy="folder, name",
                )
                .execute()
            )
            items = results.get("files", [])

            if not items:
                print("  This folder is empty.")

            # Separate into folders and files
            folders = []
            files = []
            for item in items:
                if item["mimeType"] == "application/vnd.google-apps.folder":
                    folders.append(item)
                else:
                    files.append(item)

            # Display items with numbers
            item_map = {}
            count = 1
            print("  Folders:")
            if not folders:
                print("    (No folders)")
            for folder in folders:
                print(f"    [{count}] 📁 {folder['name']}")
                item_map[str(count)] = folder
                count += 1

            print("\n  Files:")
            if not files:
                print("    (No files)")
            for f in files:
                print(f"    [{count}] 📄 {f['name']}")
                item_map[str(count)] = f
                count += 1

            print("-------------------------------------------------")
            print("  Type a number to open/download.")
            if folder_stack:
                print("  Type 'u' to go up one level.")
            print("  Type 'q' to return to the main menu.")

            # Get user input
            choice = input("  > ").strip().lower()

            if choice == "q":
                break
            elif choice == "u" and folder_stack:
                folder_id, folder_name = folder_stack.pop()
            elif choice in item_map:
                selected_item = item_map[choice]
                item_type = selected_item["mimeType"]

                if item_type == "application/vnd.google-apps.folder":
                    # Navigate into folder
                    folder_stack.append((folder_id, folder_name))  # Save current state
                    folder_id = selected_item["id"]
                    folder_name = selected_item["name"]
                else:
                    # Download file
                    download_file(service, selected_item["id"], selected_item["name"])
            else:
                print("  Invalid choice.")

        except Exception as e:
            print(f"❌ An error occurred while browsing Drive: {e}")
            break


# -------------------------------------------------------------------
# INTERACTIVE MENU SHELL (Updated)
# -------------------------------------------------------------------


def list_local_db_files():
    """Lists all .db files in the current directory."""
    print("\n--- 🗂️  Local Database Files in Current Directory ---")
    try:
        # Use .glob() to find files ending in .db or .sqlite
        db_files = sorted(list(Path.cwd().glob("*.db")))
        db_files.extend(sorted(list(Path.cwd().glob("*.sqlite"))))

        if not db_files:
            print("  No .db or .sqlite files found.")
        else:
            for f in db_files:
                print(f"  > {f.name}")
    except Exception as e:
        print(f"  An error occurred while listing files: {e}")
    print("-----------------------------------------------------")


def run_merge_interactive():
    """Guides the user through the merge process."""
    print("\n--- 🚀 Starting New Database Merge ---")
    print("Tip: Use Option '2' or '3' from the main menu to find your files.")

    try:
        # 1. Get source DB paths
        colab_db_path = Path(input("  1. Path to colab.py DB (source 1): ").strip())
        classify_db_path = Path(
            input("  2. Path to classify-new.py DB (source 2): ").strip()
        )

        # Check if source files exist
        if not colab_db_path.exists():
            print(f"\n⚠️ Error: Source file not found: {colab_db_path}")
            return
        if not classify_db_path.exists():
            print(f"\n⚠️ Error: Source file not found: {classify_db_path}")
            return

        # 3. Get destination DB path
        merged_db_path = Path(
            input("  3. Path for new *merged* DB (destination): ").strip()
        )

        # Check for overwrite
        if merged_db_path.exists():
            overwrite = (
                input(f"  File '{merged_db_path}' already exists. Overwrite? (y/n): ")
                .strip()
                .lower()
            )
            if overwrite != "y":
                print("  Merge cancelled.")
                return

        # Run the actual merge
        merge_databases(colab_db_path, classify_db_path, merged_db_path)

    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")


def main_menu():
    """Displays the main interactive menu."""
    drive_service = None

    while True:
        print("\n====== 🗃️  Database Merge Utility ======")
        print("  [1] Run the merge process")
        print("  [2] View *local* database files")
        print("  [3] Browse Google Drive & download DB")
        print("  [4] Exit")
        print("========================================")

        choice = input("Enter your choice (1-4): ").strip()

        if choice == "1":
            run_merge_interactive()
        elif choice == "2":
            list_local_db_files()
        elif choice == "3":
            try:
                if not drive_service:
                    print("  Authenticating with Google Drive...")
                    drive_service = get_drive_service()

                if drive_service:
                    browse_google_drive(drive_service)
                else:
                    print("  Could not connect to Google Drive. Please check setup.")

            except Exception as e:
                # Catch potential import errors if libraries aren't installed
                print(f"\n❌ Failed to initialize Google Drive browser.")
                print(f"  Error: {e}")
                print("  Please ensure you have installed the required libraries:")
                print("  pip install google-api-python-client google-auth-oauthlib")

        elif choice == "4":
            print("Exiting. Goodbye! 👋")
            sys.exit()
        else:
            print("\nInvalid choice. Please enter a number between 1 and 4.")


if __name__ == "__main__":
    main_menu()
