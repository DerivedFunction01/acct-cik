import os
import time
import threading
from pathlib import Path
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


# Global service object
DRIVE_SERVICE = None

# Global mounting state
MOUNTED_FOLDERS = (
    {}
)  # {folder_name: {"folder_id": id, "local_path": path, "listener_thread": thread, "stop_event": event}}
MOUNT_BASE_PATH = Path("./drive/MyDrive")


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
        gauth.LoadCredentialsFile("mycreds.txt")

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
        gauth.SaveCredentialsFile("mycreds.txt")

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
            overwrite = (
                input(f"  File '{file_title}' already exists. Overwrite? (y/n): ")
                .strip()
                .lower()
            )
            if overwrite != "y":
                print("  Download cancelled.")
                return

        # Create a PyDrive file object by ID
        gfile = service.CreateFile({"id": file_id})
        gfile.FetchContent()  # Download the content
        gfile.GetContentFile(str(local_path))  # Save to local file

        print(f"✅ Successfully downloaded '{file_title}' to the current directory.")

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
            file_list = service.ListFile(
                {"q": query, "orderBy": "folder, title"}
            ).GetList()

            if not file_list:
                print("  This folder is empty.")

            # Separate into folders and files
            folders = []
            files = []
            for item in file_list:
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
                print(f"    [{count}] 📁 {folder['title']}")
                item_map[str(count)] = folder
                count += 1

            print("\n  Files:")
            if not files:
                print("    (No files)")
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

            if choice == "q":
                break
            elif choice == "u" and folder_stack:
                folder_id, folder_name = folder_stack.pop()
            elif choice in item_map:
                selected_item = item_map[choice]

                if selected_item["mimeType"] == "application/vnd.google-apps.folder":
                    # Navigate into folder
                    folder_stack.append((folder_id, folder_name))  # Save current state
                    folder_id = selected_item["id"]
                    folder_name = selected_item["title"]
                else:
                    # Download file
                    download_drive_file(
                        service, selected_item["id"], selected_item["title"]
                    )
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

        file_list = service.ListFile(
            {
                "q": f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
            }
        ).GetList()

        folder_id = None
        if len(file_list) > 0:
            folder_id = file_list[0]["id"]
            print(f"  Found folder '{folder_name}' with ID: {folder_id}")
        else:
            print(f"  Folder '{folder_name}' not found, creating it...")
            folder_metadata = {
                "title": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [{"id": "root"}],  # Create it in "My Drive"
            }
            folder = service.CreateFile(folder_metadata)
            folder.Upload()
            folder_id = folder["id"]
            print(f"  Created folder '{folder_name}' with ID: {folder_id}")

        # 4. Upload the file into that folder
        file_title = os.path.basename(local_file_path)
        print(f"  Uploading '{file_title}' to folder '{folder_name}'...")

        gfile = service.CreateFile(
            {"title": file_title, "parents": [{"id": folder_id}]}
        )

        gfile.SetContentFile(local_file_path)
        gfile.Upload()

        print(f"\n✅ Success! File uploaded.")
        print(f"   File ID: {gfile['id']}")
        print(f"   In Folder: '{folder_name}'")

    except Exception as e:
        print(f"\n❌ An error occurred during upload: {e}")


def download_folder_recursive(service, folder_id, local_path):
    """
    Recursively downloads all files and subfolders from a Google Drive folder.
    """
    local_path = Path(local_path)
    local_path.mkdir(parents=True, exist_ok=True)

    try:
        query = f"'{folder_id}' in parents and trashed=false"
        file_list = service.ListFile({"q": query}).GetList()

        for item in file_list:
            if item["mimeType"] == "application/vnd.google-apps.folder":
                # It's a folder - recurse
                subfolder_path = local_path / item["title"]
                print(f"  Creating subfolder: {subfolder_path}")
                download_folder_recursive(service, item["id"], subfolder_path)
            else:
                # It's a file - download it
                file_path = local_path / item["title"]
                print(f"  Downloading: {item['title']}")
                gfile = service.CreateFile({"id": item["id"]})
                gfile.GetContentFile(str(file_path))

    except Exception as e:
        print(f"  Error downloading from folder: {e}")


def listen_for_changes(service, folder_id, local_path, folder_name, stop_event):
    """
    Background thread that periodically checks for changes in the Drive folder
    and syncs them to the local path.
    """
    print(f"🔊 Listener started for '{folder_name}'")

    # Track files we've seen (file_id -> modified_time)
    known_files = {}
    check_interval = 30  # Check every 30 seconds

    while not stop_event.is_set():
        try:
            # Get all files in the folder (and subfolders)
            query = f"'{folder_id}' in parents and trashed=false"
            file_list = service.ListFile({"q": query}).GetList()

            current_file_ids = set()

            for item in file_list:
                file_id = item["id"]
                current_file_ids.add(file_id)
                modified_time = item.get("modifiedDate", "")

                if item["mimeType"] == "application/vnd.google-apps.folder":
                    # Ensure subfolder exists
                    subfolder_path = Path(local_path) / item["title"]
                    subfolder_path.mkdir(parents=True, exist_ok=True)
                    known_files[file_id] = modified_time
                else:
                    # Check if file is new or modified
                    if (
                        file_id not in known_files
                        or known_files[file_id] != modified_time
                    ):
                        file_path = Path(local_path) / item["title"]
                        print(f"  📥 Syncing: {item['title']}")
                        gfile = service.CreateFile({"id": file_id})
                        gfile.GetContentFile(str(file_path))
                        known_files[file_id] = modified_time

            # Check for deleted files (files that were known but aren't in current list)
            deleted_ids = set(known_files.keys()) - current_file_ids
            for deleted_id in deleted_ids:
                print(f"  🗑️  Detected deletion in Drive (file ID: {deleted_id})")
                del known_files[deleted_id]

        except Exception as e:
            print(f"  ⚠️ Listener error for '{folder_name}': {e}")

        # Wait before next check (with ability to interrupt)
        stop_event.wait(check_interval)

    print(f"🔇 Listener stopped for '{folder_name}'")


def mount_drive_folder(service, folder_name, folder_id=None):
    """
    Mounts a Google Drive folder to the local filesystem and starts listening for changes.
    """
    # Check if already mounted
    if folder_name in MOUNTED_FOLDERS:
        print(f"⚠️  Folder '{folder_name}' is already mounted.")
        return False

    try:
        # If folder_id not provided, search for it
        if not folder_id:
            print(f"  Searching for folder '{folder_name}' in Google Drive...")
            file_list = service.ListFile(
                {
                    "q": f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
                }
            ).GetList()

            if len(file_list) == 0:
                print(f"  ❌ Folder '{folder_name}' not found in your Drive.")
                return False

            folder_id = file_list[0]["id"]
            print(f"  Found folder with ID: {folder_id}")

        # Create local mount path
        local_path = MOUNT_BASE_PATH / folder_name
        print(f"  Creating local directory: {local_path}")
        local_path.mkdir(parents=True, exist_ok=True)

        # Download all contents
        print(f"  📦 Downloading all files from '{folder_name}'...")
        download_folder_recursive(service, folder_id, local_path)
        print(f"  ✅ Initial download complete!")

        # Start listener thread
        stop_event = threading.Event()
        listener_thread = threading.Thread(
            target=listen_for_changes,
            args=(service, folder_id, local_path, folder_name, stop_event),
            daemon=True,
        )
        listener_thread.start()

        # Store mount info
        MOUNTED_FOLDERS[folder_name] = {
            "folder_id": folder_id,
            "local_path": str(local_path),
            "listener_thread": listener_thread,
            "stop_event": stop_event,
        }

        print(f"\n✅ Successfully mounted '{folder_name}' to {local_path}")
        print(f"   Background sync is now active.")
        return True

    except Exception as e:
        print(f"❌ Failed to mount folder: {e}")
        return False


def reactivate_listener(service, folder_name):
    """
    Reactivates the background listener for an existing local folder without re-downloading.
    Useful after a restart when the folder is already on disk.
    """
    # Check if already active
    if folder_name in MOUNTED_FOLDERS:
        if MOUNTED_FOLDERS[folder_name]["listener_thread"].is_alive():
            print(f"⚠️  Listener for '{folder_name}' is already active.")
            return False
        else:
            # Thread exists but is dead, clean it up
            print(f"  Cleaning up dead listener for '{folder_name}'...")
            del MOUNTED_FOLDERS[folder_name]

    try:
        # Check if local folder exists
        local_path = MOUNT_BASE_PATH / folder_name
        if not local_path.exists():
            print(f"  ❌ Local folder not found at: {local_path}")
            print(f"     Use option 3 (Mount Drive Folder) to download it first.")
            return False

        # Search for folder in Drive
        print(f"  Searching for folder '{folder_name}' in Google Drive...")
        file_list = service.ListFile(
            {
                "q": f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
            }
        ).GetList()

        if len(file_list) == 0:
            print(f"  ❌ Folder '{folder_name}' not found in your Drive.")
            return False

        folder_id = file_list[0]["id"]
        print(f"  Found folder with ID: {folder_id}")

        # Start listener thread
        stop_event = threading.Event()
        listener_thread = threading.Thread(
            target=listen_for_changes,
            args=(service, folder_id, local_path, folder_name, stop_event),
            daemon=True,
        )
        listener_thread.start()

        # Store mount info
        MOUNTED_FOLDERS[folder_name] = {
            "folder_id": folder_id,
            "local_path": str(local_path),
            "listener_thread": listener_thread,
            "stop_event": stop_event,
        }

        print(f"\n✅ Successfully reactivated listener for '{folder_name}'")
        print(f"   Local path: {local_path}")
        print(f"   Background sync is now active.")
        return True

    except Exception as e:
        print(f"❌ Failed to reactivate listener: {e}")
        return False


def reactivate_listener_interactive(service):
    """Interactive interface for reactivating a listener for an existing folder."""
    print("\n--- 🔄 Reactivate Folder Listener ---")

    # Show available local folders
    if MOUNT_BASE_PATH.exists():
        local_folders = [f.name for f in MOUNT_BASE_PATH.iterdir() if f.is_dir()]
        if local_folders:
            print("  Available local folders:")
            for i, name in enumerate(local_folders, 1):
                status = "🟢 Active" if name in MOUNTED_FOLDERS else "⚪ Inactive"
                print(f"    [{i}] {status} {name}")
        else:
            print("  No local folders found.")
            return
    else:
        print("  No mount directory found.")
        return

    folder_name = input("\n  Enter folder name or number to reactivate: ").strip()

    # Handle numeric choice
    if folder_name.isdigit():
        idx = int(folder_name) - 1
        if 0 <= idx < len(local_folders):
            folder_name = local_folders[idx]
        else:
            print("  Invalid number.")
            return

    if not folder_name:
        print("  Error: Folder name cannot be empty.")
        return

    reactivate_listener(service, folder_name)


def unmount_drive_folder(folder_name):
    """
    Unmounts a folder and stops its listener thread.
    """
    if folder_name not in MOUNTED_FOLDERS:
        print(f"⚠️  Folder '{folder_name}' is not currently mounted.")
        return False

    try:
        mount_info = MOUNTED_FOLDERS[folder_name]

        # Signal the listener to stop
        mount_info["stop_event"].set()

        # Wait for thread to finish (with timeout)
        mount_info["listener_thread"].join(timeout=5)

        # Remove from mounted folders
        del MOUNTED_FOLDERS[folder_name]

        print(f"✅ Unmounted '{folder_name}'")
        print(f"   Local files remain at: {mount_info['local_path']}")
        return True

    except Exception as e:
        print(f"❌ Error unmounting folder: {e}")
        return False


def mount_drive_folder_interactive(service):
    """Interactive interface for mounting a Drive folder."""
    print("\n--- 🗂️  Mount Google Drive Folder ---")
    folder_name = input("  Enter the name of the Drive folder to mount: ").strip()

    if not folder_name:
        print("  Error: Folder name cannot be empty.")
        return

    mount_drive_folder(service, folder_name)


def unmount_drive_folder_interactive():
    """Interactive interface for unmounting a Drive folder."""
    print("\n--- 🔌 Unmount Google Drive Folder ---")

    if not MOUNTED_FOLDERS:
        print("  No folders are currently mounted.")
        return

    print("  Currently mounted folders:")
    for i, name in enumerate(MOUNTED_FOLDERS.keys(), 1):
        print(f"    [{i}] {name}")

    choice = input("  Enter folder name or number to unmount: ").strip()

    # Handle numeric choice
    if choice.isdigit():
        idx = int(choice) - 1
        folder_list = list(MOUNTED_FOLDERS.keys())
        if 0 <= idx < len(folder_list):
            choice = folder_list[idx]

    unmount_drive_folder(choice)


def show_mounted_folders():
    """Displays all currently mounted folders."""
    print("\n--- 📋 Currently Mounted Folders ---")

    if not MOUNTED_FOLDERS:
        print("  No folders are currently mounted.")
    else:
        for folder_name, info in MOUNTED_FOLDERS.items():
            status = "🟢 Active" if info["listener_thread"].is_alive() else "🔴 Stopped"
            print(f"  {status} {folder_name}")
            print(f"      Local path: {info['local_path']}")
            print(f"      Drive ID: {info['folder_id']}")

    print("------------------------------------")


def main_menu():
    """Displays the main interactive menu for Google Drive utilities."""
    while True:
        print("\n====== 📁 Google Drive Utility ======")
        print("  [1] Browse/Download from Google Drive")
        print("  [2] Upload file to Google Drive")
        print("  [3] Mount Drive Folder (sync & watch)")
        print("  [4] Unmount Drive Folder")
        print("  [5] Reactivate Folder Listener")
        print("  [6] Show Mounted Folders")
        print("  [7] Exit")
        print("=====================================")

        choice = input("Enter your choice (1-7): ").strip()

        if choice == "1":
            drive_service = get_drive_service()
            if drive_service:
                browse_google_drive(drive_service)

        elif choice == "2":
            drive_service = get_drive_service()
            if drive_service:
                upload_to_drive_interactive(drive_service)

        elif choice == "3":
            drive_service = get_drive_service()
            if drive_service:
                mount_drive_folder_interactive(drive_service)

        elif choice == "4":
            unmount_drive_folder_interactive()

        elif choice == "5":
            drive_service = get_drive_service()
            if drive_service:
                reactivate_listener_interactive(drive_service)

        elif choice == "6":
            show_mounted_folders()

        elif choice == "7":
            # Stop all listeners before exiting
            print("\nStopping all folder listeners...")
            for folder_name in list(MOUNTED_FOLDERS.keys()):
                unmount_drive_folder(folder_name)
            print("Exiting. Goodbye! 👋")
            break

        else:
            print("\nInvalid choice. Please enter a number between 1 and 7.")


if __name__ == "__main__":
    main_menu()
