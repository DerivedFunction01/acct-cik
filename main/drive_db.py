import sqlite3
import pandas as pd
import sys
from pathlib import Path
import os
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

# -------------------------------------------------------------------
# GLOBAL SERVICE OBJECTS
# -------------------------------------------------------------------

# This will hold the authenticated GoogleDrive object
DRIVE_SERVICE = None

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
        CREATE TABLE IF NOT EXISTS names (
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

        cols = ', '.join(df.columns)
        placeholders = ', '.join(['?']*len(df.columns))
        sql = f"INSERT OR IGNORE INTO {table_name} ({cols}) VALUES ({placeholders})"
        
        data_tuples = df.to_records(index=False)
        
        dest_conn.executemany(sql, data_tuples)
        dest_conn.commit() 
        
        print(f"    -> Processed {len(df)} rows from {table_name}. (Duplicates ignored)")

    except (sqlite3.DatabaseError, pd.io.sql.DatabaseError) as e:
        print(f"    -> Could not read table '{table_name}'. It might not exist in this source DB. Error: {e}")


def merge_databases(colab_db_path, classify_db_path, merged_db_path):
    """
    Merges two SQLite databases into a new one.
    """
    print(f"\nStarting database merge process...")
    print(f"Source (colab.py): {colab_db_path}")
    print(f"Source (classify-new.py): {classify_db_path}")
    print(f"Destination: {merged_db_path}")

    try:
        with sqlite3.connect(merged_db_path) as dest_conn, \
             sqlite3.connect(colab_db_path) as colab_conn, \
             sqlite3.connect(classify_db_path) as classify_conn:

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
# NEW GOOGLE DRIVE LOGIC (Using PyDrive2)
# -------------------------------------------------------------------

def get_drive_service():
    """
    Authenticates with pydrive2 using client_secrets.json and returns 
    a GoogleDrive object. Caches the object globally.
    """
    global DRIVE_SERVICE
    if DRIVE_SERVICE:
        return DRIVE_SERVICE
            
    try:
        print("\n  Authenticating with Google Drive...")
        gauth = GoogleAuth()
        # Try to load saved credentials
        gauth.LoadCredentialsFile("client_secrets.json")
        
        if gauth.credentials is None:
            # Authenticate if they're not there
            print("  Please follow the link in your browser to authorize:")
            gauth.CommandLineAuth()
        elif gauth.access_token_expired:
            # Refresh them if expired
            print("  Refreshing expired credentials...")
            gauth.Refresh()
        else:
            # Initialize the saved creds
            gauth.Authorize()
        
        # Save the current credentials to a file for next time
        gauth.SaveCredentialsFile("client_secrets.json")
            
        DRIVE_SERVICE = GoogleDrive(gauth)
        print("  Authentication successful.")
        return DRIVE_SERVICE
    
    except Exception as e:
        print(f"\n❌ Failed to authenticate with Google Drive.")
        print(f"  Error: {e}")
        print("  Please ensure 'client_secrets.json' is in this directory.")
        print("  You may need to install pydrive2: pip install pydrive2")
        return None


def download_drive_file(service, file_id, file_title):
    """Downloads a file from Google Drive using PyDrive2."""
    print(f"\nDownloading '{file_title}'...")
    try:
        local_path = Path(file_title)
        if local_path.exists():
            overwrite = input(f"  File '{file_title}' already exists. Overwrite? (y/n): ").strip().lower()
            if overwrite != 'y':
                print("  Download cancelled.")
                return

        # Create a PyDrive file object by ID
        gfile = service.CreateFile({'id': file_id})
        gfile.FetchContent() # Download the content
        gfile.GetContentFile(str(local_path)) # Save to local file
        
        print(f"✅ Successfully downloaded '{file_title}' to the current directory.")

    except Exception as e:
        print(f"❌ An error occurred during download: {e}")


def browse_google_drive(service):
    """Provides an interactive shell to browse and download files from Google Drive."""
    folder_id = 'root'
    folder_name = 'My Drive'
    folder_stack = [] # To store (id, name) tuples for "up" navigation

    while True:
        print(f"\n--- 🛰️  Browsing Google Drive: {folder_name} ---")
        try:
            # List files and folders
            query = f"'{folder_id}' in parents and trashed=false"
            file_list = service.ListFile({
                'q': query,
                'orderBy': 'folder, title'
            }).GetList()

            if not file_list:
                print("  This folder is empty.")
            
            # Separate into folders and files
            folders = []
            files = []
            for item in file_list:
                if item['mimeType'] == 'application/vnd.google-apps.folder':
                    folders.append(item)
                else:
                    files.append(item)
            
            # Display items with numbers
            item_map = {}
            count = 1
            print("  Folders:")
            if not folders: print("    (No folders)")
            for folder in folders:
                print(f"    [{count}] 📁 {folder['title']}")
                item_map[str(count)] = folder
                count += 1
            
            print("\n  Files:")
            if not files: print("    (No files)")
            for f in files:
                print(f"    [{count}] 📄 {f['title']}")
                item_map[str(count)] = f
                count += 1
            
            print("-------------------------------------------------")
            print("  Type a number to open/download.")
            if folder_stack:
                print("  Type 'u' to go up one level.")
            print("  Type 'q' to return to the main menu.")

            # Get user input
            choice = input("  > ").strip().lower()

            if choice == 'q':
                break
            elif choice == 'u' and folder_stack:
                folder_id, folder_name = folder_stack.pop()
            elif choice in item_map:
                selected_item = item_map[choice]
                
                if selected_item['mimeType'] == 'application/vnd.google-apps.folder':
                    # Navigate into folder
                    folder_stack.append((folder_id, folder_name)) # Save current state
                    folder_id = selected_item['id']
                    folder_name = selected_item['title']
                else:
                    # Download file
                    download_drive_file(service, selected_item['id'], selected_item['title'])
            else:
                print("  Invalid choice.")

        except Exception as e:
            print(f"❌ An error occurred while browsing Drive: {e}")
            break


def upload_to_drive_interactive(service):
    """Interactively uploads a local file to a specified folder on Google Drive."""
    print("\n--- 📤 Upload File to Google Drive ---")
    
    try:
        # 1. Get local file path and check
        local_file_path = input("  1. Path to *local file* to upload: ").strip()
        if not os.path.exists(local_file_path):
            print(f"  Error: File not found at '{local_file_path}'")
            return
            
        # 2. Get destination folder name
        folder_name = input(f"  2. Name of *Drive folder* to upload to: ").strip()
        if not folder_name:
            print("  Error: Folder name cannot be empty.")
            return

        # 3. Find or create the folder ID
        print(f"  Searching for folder '{folder_name}' in your Google Drive...")
        
        file_list = service.ListFile({
            'q': f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
        }).GetList()

        folder_id = None
        if len(file_list) > 0:
            folder_id = file_list[0]['id']
            print(f"  Found folder '{folder_name}' with ID: {folder_id}")
        else:
            print(f"  Folder '{folder_name}' not found, creating it...")
            folder_metadata = {
                'title': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [{'id': 'root'}] # Create it in "My Drive"
            }
            folder = service.CreateFile(folder_metadata)
            folder.Upload()
            folder_id = folder['id']
            print(f"  Created folder '{folder_name}' with ID: {folder_id}")

        # 4. Upload the file into that folder
        file_title = os.path.basename(local_file_path)
        print(f"  Uploading '{file_title}' to folder '{folder_name}'...")
        
        gfile = service.CreateFile({
            'title': file_title,
            'parents': [{'id': folder_id}]
        })
        
        gfile.SetContentFile(local_file_path)
        gfile.Upload()
        
        print(f"\n✅ Success! File uploaded.")
        print(f"   File ID: {gfile['id']}")
        print(f"   In Folder: '{folder_name}'")

    except Exception as e:
        print(f"\n❌ An error occurred during upload: {e}")


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
        classify_db_path = Path(input("  2. Path to classify-new.py DB (source 2): ").strip())

        # Check if source files exist
        if not colab_db_path.exists():
            print(f"\n⚠️ Error: Source file not found: {colab_db_path}")
            return
        if not classify_db_path.exists():
            print(f"\n⚠️ Error: Source file not found: {classify_db_path}")
            return

        # 3. Get destination DB path
        merged_db_path = Path(input("  3. Path for new *merged* DB (destination): ").strip())

        # Check for overwrite
        if merged_db_path.exists():
            overwrite = input(f"  File '{merged_db_path}' already exists. Overwrite? (y/n): ").strip().lower()
            if overwrite != 'y':
                print("  Merge cancelled.")
                return

        # Run the actual merge
        merge_databases(colab_db_path, classify_db_path, merged_db_path)

    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")


def main_menu():
    """Displays the main interactive menu."""
    while True:
        print("\n====== 🗃️  Database Merge & Drive Utility ======")
        print("  [1] Run the merge process")
        print("  [2] View *local* database files")
        print("  [3] Browse/Download from Google Drive")
        print("  [4] Upload DB to Google Drive")
        print("  [5] Exit")
        print("================================================")
        
        choice = input("Enter your choice (1-5): ").strip()
        
        if choice == '1':
            run_merge_interactive()
        
        elif choice == '2':
            list_local_db_files()
        
        elif choice == '3':
            drive_service = get_drive_service()
            if drive_service:
                browse_google_drive(drive_service)
        
        elif choice == '4':
            drive_service = get_drive_service()
            if drive_service:
                upload_to_drive_interactive(drive_service)
        
        elif choice == '5':
            print("Exiting. Goodbye! 👋")
            sys.exit()
        
        else:
            print("\nInvalid choice. Please enter a number between 1 and 5.")


if __name__ == "__main__":
    main_menu()