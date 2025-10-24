import os
import time
from datetime import datetime
import threading
import subprocess
import platform
import json
import argparse
from pathlib import Path
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


# Global service object
DRIVE_SERVICE = None

# Global mounting state
MOUNTED_FOLDERS = (
    {}
)  # {folder_name: {"folder_id": id, "local_path": path, "listener_thread": thread, "backup_thread": thread, "stop_event": event}}
MOUNT_BASE_PATH = Path("./drive/MyDrive")
BACKUP_PATH = Path("./backup")  # Default path, will be loaded from config
STATE_FILE = Path(".mount_state.json")
CONFIG_FILE = Path(".drive_config.json")
STATE_LOCK = threading.Lock()

# Global debug flag and log buffer
DEBUG = False
DEBUG_BUFFER = []
DEBUG_BUFFER_SIZE = 1000
DEBUG_BUFFER_LOCK = threading.Lock()

# ANSI escape codes for cursor movement and screen manipulation
CURSOR_UP = '\033[A'
CURSOR_DOWN = '\033[B'
CLEAR_LINE = '\033[2K'
SAVE_CURSOR = '\033[s'
RESTORE_CURSOR = '\033[u'
MOVE_TO_TOP = '\033[H'
CLEAR_SCREEN = '\033[2J'
HIDE_CURSOR = '\033[?25l'
SHOW_CURSOR = '\033[?25h'


def debug_print(*args, **kwargs):
    """Prints only if the global DEBUG flag is set to True and stores in buffer."""
    if DEBUG:
        message = " ".join(str(arg) for arg in args)
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"{timestamp} | {message}"
        
        # Add to circular buffer
        with DEBUG_BUFFER_LOCK:
            DEBUG_BUFFER.append(log_entry)
            if len(DEBUG_BUFFER) > DEBUG_BUFFER_SIZE:
                DEBUG_BUFFER.pop(0)
        
        print(*args, **kwargs)


def load_config():
    """Loads configuration from the JSON file, such as the backup path."""
    global BACKUP_PATH
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)

            new_path = config_data.get("backup_path")
            if new_path:
                BACKUP_PATH = Path(new_path)
                debug_print(f"  Loaded backup path from config: {BACKUP_PATH}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"  ⚠️  Could not read config file, using defaults. Error: {e}")
    else:
        debug_print(f"  No config file found, using default backup path: {BACKUP_PATH}")


def save_config():
    """Saves the current configuration to the JSON file."""
    config_data = {"backup_path": str(BACKUP_PATH)}
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=4)
    except IOError as e:
        print(f"  ❌ Error saving config file: {e}")


def backup_file_threaded(local_file: Path, base_path: Path, folder_name: str):
    """
    Copies a file to the backup location in a separate thread.
    """

    def do_backup():
        try:
            relative_path = local_file.relative_to(base_path)
            backup_dir = BACKUP_PATH / folder_name / relative_path.parent
            backup_dir.mkdir(parents=True, exist_ok=True)

            temp_backup_dest = backup_dir / f".{local_file.name}.tmp"
            final_backup_dest = backup_dir / local_file.name

            import shutil
            shutil.copy2(local_file, temp_backup_dest)
            os.replace(temp_backup_dest, final_backup_dest) # Atomic operation on the same filesystem
            debug_print(f"      🗄️  Backup successful: {final_backup_dest}")
        except Exception as backup_e:
            print(f"      ⚠️ Backup failed for {local_file.name}: {backup_e}")

    threading.Thread(target=do_backup, daemon=True).start()


def backup_monitor_thread(local_path, folder_name, stop_event):
    """
    Independent thread that monitors local files and backs them up.
    Does NOT depend on Google Drive authentication - runs completely independently.
    """
    known_files = {}  # {file_path_str: (mtime, size)}
    check_interval = 10

    debug_print(f"🗄️  Backup monitor started for '{folder_name}'")

    while not stop_event.is_set():
        try:
            local_folder = Path(local_path)
            if not local_folder.exists():
                debug_print(f"  ⚠️ Local folder doesn't exist yet: {local_folder}")
                stop_event.wait(check_interval)
                continue

            # Scan all files recursively
            for local_file in local_folder.rglob("*"):
                # Skip directories, hidden/system files, and temporary files
                if (not local_file.is_file()
                    or local_file.name.startswith(".")
                    or local_file.name.endswith(".tmp")):
                    continue

                try:
                    current_mtime = os.path.getmtime(local_file)
                    current_size = os.path.getsize(local_file)
                    file_key = str(local_file)

                    # Check if file is new or modified
                    if file_key not in known_files:
                        # New file detected
                        debug_print(
                            f"  💾 New file detected for backup: {local_file.name}"
                        )
                        known_files[file_key] = (current_mtime, current_size)
                        backup_file_threaded(local_file, local_folder, folder_name)
                    else:
                        old_mtime, old_size = known_files[file_key]
                        if current_mtime > old_mtime or current_size != old_size:
                            # File was modified
                            debug_print(
                                f"  💾 Modified file detected for backup: {local_file.name}"
                            )
                            known_files[file_key] = (current_mtime, current_size)
                            backup_file_threaded(local_file, local_folder, folder_name)

                except (FileNotFoundError, PermissionError) as e:
                    # File disappeared or inaccessible - remove from tracking
                    if file_key in known_files:
                        del known_files[file_key]
                    debug_print(f"  ⚠️ Could not access file {local_file.name}: {e}")

            # Clean up deleted files from tracking
            existing_files = set(str(f) for f in local_folder.rglob("*") if f.is_file())
            deleted_files = set(known_files.keys()) - existing_files
            for deleted_file in deleted_files:
                debug_print(
                    f"  🗑️  Removed deleted file from backup tracking: {Path(deleted_file).name}"
                )
                del known_files[deleted_file]

        except Exception as e:
            print(f"  ⚠️ Backup monitor error for '{folder_name}': {e}")

        # Wait before next check
        stop_event.wait(check_interval)

    debug_print(f"🗄️  Backup monitor stopped for '{folder_name}'")


def update_mount_state(folder_name, status, message=""):
    """Updates the status of a folder in the .mount_state.json file."""
    with STATE_LOCK:
        state = {}
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass  # Overwrite if corrupt or unreadable

        if folder_name in state:
            state[folder_name]["status"] = status
            state[folder_name]["status_message"] = message
            state[folder_name][
                "pid"
            ] = os.getpid()  # Update PID in case it's a reactivation

            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=4)


def add_mount_to_state(folder_name, folder_id, local_path):
    """Adds a new folder to the .mount_state.json file."""
    with STATE_LOCK:
        state = {}
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        state[folder_name] = {
            "folder_id": folder_id,
            "local_path": str(local_path),
            "pid": os.getpid(),
            "status": "INITIALIZING",
            "status_message": "Starting mount process...",
        }

        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)


def remove_mount_from_state(folder_name):
    """Removes a folder from the .mount_state.json file."""
    with STATE_LOCK:
        state = {}
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)

                if folder_name in state:
                    del state[folder_name]

                    with open(STATE_FILE, "w") as f:
                        json.dump(state, f, indent=4)
            except (json.JSONDecodeError, IOError):
                pass  # File is gone or corrupt, nothing to do


def get_drive_service():
    """
    Authenticates with pydrive2 using client_secrets.json and returns
    a GoogleDrive object. Caches the object globally.
    """
    global DRIVE_SERVICE
    if DRIVE_SERVICE:
        return DRIVE_SERVICE

    try:
        debug_print("\n  Authenticating with Google Drive...")
        gauth = GoogleAuth()
        # Try to load saved credentials
        gauth.LoadCredentialsFile("mycreds.txt")

        if gauth.credentials is None:
            # Authenticate if they're not there
            print(
                "  No valid credentials found. Please follow the link in your browser to authorize:"
            )
            gauth.CommandLineAuth()
        elif gauth.access_token_expired:
            # Refresh them if expired
            debug_print("  Refreshing expired credentials...")
            gauth.Refresh()
        else:
            # Initialize the saved creds
            gauth.Authorize()

        # Save the current credentials to a file for next time
        gauth.SaveCredentialsFile("mycreds.txt")

        DRIVE_SERVICE = GoogleDrive(gauth)
        debug_print("  Authentication successful.")
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
        debug_print(f"  Searching for folder '{folder_name}' in your Google Drive...")

        file_list = service.ListFile(
            {
                "q": f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
            }
        ).GetList()

        folder_id = None
        if len(file_list) > 0:
            folder_id = file_list[0]["id"]
            debug_print(f"  Found folder '{folder_name}' with ID: {folder_id}")
        else:
            debug_print(f"  Folder '{folder_name}' not found, creating it...")
            folder_metadata = {
                "title": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [{"id": "root"}],  # Create it in "My Drive"
            }
            folder = service.CreateFile(folder_metadata)
            folder.Upload()
            folder_id = folder["id"]
            debug_print(f"  Created folder '{folder_name}' with ID: {folder_id}")

        # 4. Upload the file into that folder
        file_title = os.path.basename(local_file_path)
        debug_print(f"  Uploading '{file_title}' to folder '{folder_name}'...")

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
                debug_print(f"  Creating subfolder: {subfolder_path}")
                download_folder_recursive(service, item["id"], subfolder_path)
            else:
                # It's a file - download it
                file_path = local_path / item["title"]
                debug_print(f"  Downloading: {item['title']}")
                gfile = service.CreateFile({"id": item["id"]})
                gfile.GetContentFile(str(file_path))

    except Exception as e:
        print(f"  Error downloading from folder: {e}")


def force_remove_file(file_path):
    """
    Attempts to remove a file or directory using multiple methods.
    Returns True if successful, False otherwise.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return True

    # Method 1: Standard Python removal
    try:
        if file_path.is_dir():
            import shutil

            shutil.rmtree(file_path)
        else:
            file_path.unlink()
        return True
    except Exception as e:
        debug_print(f"      Standard removal failed: {e}")

    # Method 2: Try to close any file handles and retry
    try:
        import gc

        gc.collect()  # Force garbage collection to release file handles
        time.sleep(0.5)

        if file_path.is_dir():
            import shutil

            shutil.rmtree(file_path)
        else:
            file_path.unlink()
        return True
    except Exception as e:
        debug_print(f"      Retry after GC failed: {e}")

    # Method 3: Use OS-specific commands
    try:
        system = platform.system()

        if system == "Windows":
            # Windows: use del for files, rmdir for directories
            if file_path.is_dir():
                subprocess.run(
                    ["rmdir", "/S", "/Q", str(file_path)],
                    shell=True,
                    check=True,
                    capture_output=True,
                )
            else:
                subprocess.run(
                    ["del", "/F", "/Q", str(file_path)],
                    shell=True,
                    check=True,
                    capture_output=True,
                )
        else:
            # Linux/Mac: use rm -rf
            subprocess.run(
                ["rm", "-rf", str(file_path)], check=True, capture_output=True
            )

        debug_print(f"      Removed using system command")
        return True
    except Exception as e:
        debug_print(f"      System command failed: {e}")

    # Method 4: Mark for deletion on next restart (Windows only)
    if platform.system() == "Windows":
        try:
            import ctypes

            # MoveFileEx with MOVEFILE_DELAY_UNTIL_REBOOT flag
            ctypes.windll.kernel32.MoveFileExW(
                str(file_path), None, 0x4  # MOVEFILE_DELAY_UNTIL_REBOOT
            )
            debug_print(f"      File marked for deletion on next restart")
            return True
        except Exception as e:
            debug_print(f"      Delayed deletion failed: {e}")

    return False


def listen_for_changes(
    service,
    folder_id,
    local_path,
    folder_name,
    stop_event,
    initial_sync_mode="from_drive",
):
    """
    Background thread that periodically checks for changes in the Drive folder
    and syncs them to the local path. Also detects local changes (additions,
    deletions, modifications) and syncs them to Drive.

    NOTE: This thread handles ONLY Drive sync. Backups are handled by a separate
    independent thread (backup_monitor_thread) that continues even if Drive auth expires.
    """
    print(f"🔊 Listener started for '{folder_name}'")
    debug_print(f"   Watching local path: {local_path}")
    # Track files we've seen (file_id -> {"modified_time": time, "local_path": path, "title": name, "local_mtime": mtime, "local_size": size})
    known_files = {}
    # Track local files by their path (local_path -> file_id)
    local_to_drive = {}

    check_interval = 10  # Check every 10 seconds
    consecutive_errors = 0
    max_consecutive_errors = (
        6  # Allow up to 6 errors (1 minute) before going into degraded mode
    )

    update_mount_state(folder_name, "IDLE", "Awaiting changes...")

    is_first_run = True

    while not stop_event.is_set():
        drive_sync_successful = False

        try:
            current_file_ids = set()
            folders_to_scan = [
                (folder_id, Path(local_path))
            ]  # Queue of (folder_id, local_path)

            # On first run for a reactivated listener, respect the sync mode
            sync_from_drive = (
                is_first_run and initial_sync_mode == "from_drive"
            ) or not is_first_run

            # --- Recursively scan Drive for remote changes ---
            while folders_to_scan:
                parent_id, parent_local_path = folders_to_scan.pop(0)

                query = f"'{parent_id}' in parents and trashed=false"
                file_list = service.ListFile({"q": query}).GetList()

                for item in file_list:
                    item_id = item["id"]
                    current_file_ids.add(item_id)
                    modified_time = item.get("modifiedDate", "")
                    item_title = item["title"]

                    item_local_path = parent_local_path / item_title

                    if item["mimeType"] == "application/vnd.google-apps.folder":
                        # This is a folder, ensure it exists locally and add to scan queue
                        item_local_path.mkdir(parents=True, exist_ok=True)
                        folders_to_scan.append((item_id, item_local_path))
                        if item_id not in known_files:
                            known_files[item_id] = {
                                "modified_time": modified_time,
                                "local_path": str(item_local_path),
                                "title": item_title,
                                "local_mtime": 0,
                                "local_size": 0,
                            }
                        local_to_drive[str(item_local_path)] = item_id
                    else:
                        # This is a file, check if it needs downloading
                        if sync_from_drive and (
                            item_id not in known_files
                            or known_files[item_id]["modified_time"] != modified_time
                        ):
                            debug_print(
                                f"  📥 Syncing from Drive: {item_local_path.relative_to(local_path)}"
                            )
                            update_mount_state(
                                folder_name, "SYNCING_DOWN", f"Downloading {item_title}"
                            )
                            gfile = service.CreateFile({"id": item_id})
                            gfile.GetContentFile(str(item_local_path))
                            local_mtime = os.path.getmtime(item_local_path)
                            local_size = os.path.getsize(item_local_path)
                            # Update known files with the new state
                            known_files[item_id] = {
                                "modified_time": modified_time,
                                "local_path": str(item_local_path),
                                "title": item_title,
                                "local_mtime": local_mtime,
                                "local_size": local_size,
                            }
                            local_to_drive[str(item_local_path)] = item_id
                        else:
                            # File is unchanged, but ensure tracking is up-to-date
                            known_files[item_id] = {
                                "modified_time": modified_time,
                                "local_path": str(item_local_path),
                                "title": item_title,
                                "local_mtime": known_files.get(item_id, {}).get(
                                    "local_mtime", 0
                                ),
                                "local_size": known_files.get(item_id, {}).get(
                                    "local_size", 0
                                ),
                            }
                            local_to_drive[str(item_local_path)] = item_id

            # Check for deleted files in Drive (files that were known but aren't in current list)
            deleted_ids = set(known_files.keys()) - current_file_ids
            for deleted_id in deleted_ids:
                if deleted_id == folder_id:
                    continue  # Don't delete the root mount folder

                file_info = known_files[deleted_id]
                debug_print(f"  🗑️  Detected deletion in Drive: {file_info['title']}")
                update_mount_state(
                    folder_name,
                    "DELETING",
                    f"Removing local copy of {file_info['title']}",
                )
                # Remove local file if it exists
                local_file_path = Path(file_info["local_path"])
                if local_file_path.exists():
                    if force_remove_file(local_file_path):
                        debug_print(f"      Removed local file: {file_info['title']}")
                    else:
                        print(
                            f"      ⚠️ Could not remove local file (in use): {file_info['title']}"
                        )
                        continue

                if str(local_file_path) in local_to_drive:
                    del local_to_drive[str(local_file_path)]
                del known_files[deleted_id]

            # Check for local deletions (files we're tracking that no longer exist locally)
            files_to_delete_from_drive = []
            for file_id, file_info in list(known_files.items()):
                local_file_path = Path(file_info["local_path"])
                if not local_file_path.exists() and file_id in current_file_ids:
                    # File was deleted locally but still exists in Drive
                    files_to_delete_from_drive.append((file_id, file_info["title"]))

            # Delete files from Drive
            for file_id, file_title in files_to_delete_from_drive:
                try:
                    debug_print(
                        f"  🗑️  Deleting from Drive (local deletion detected): {file_title}"
                    )
                    update_mount_state(
                        folder_name, "DELETING", f"Deleting {file_title} from Drive"
                    )
                    gfile = service.CreateFile({"id": file_id})
                    gfile.Delete()
                    if file_id in known_files:
                        local_path_str = known_files[file_id]["local_path"]
                        if local_path_str in local_to_drive:
                            del local_to_drive[local_path_str]
                        del known_files[file_id]
                except Exception as e:
                    debug_print(f"      Failed to delete from Drive: {e}")

            # --- Check for local modifications and upload them ---
            for local_path_str, file_id in list(local_to_drive.items()):
                local_file = Path(local_path_str)
                if local_file.is_file() and local_file.exists():
                    try:
                        current_mtime = os.path.getmtime(local_file)
                        current_size = os.path.getsize(local_file)

                        known_info = known_files.get(file_id)
                        if not known_info:
                            continue

                        # Check for modification
                        if current_mtime > known_info.get(
                            "local_mtime", 0
                        ) or current_size != known_info.get("local_size", 0):
                            debug_print(
                                f"  📤 Syncing to Drive (local modification): {local_file.name}"
                            )
                            update_mount_state(
                                folder_name,
                                "SYNCING_UP",
                                f"Uploading {local_file.name}",
                            )

                            gfile = service.CreateFile({"id": file_id})
                            gfile.SetContentFile(str(local_file))
                            gfile.Upload()
                            if gfile.content:
                                gfile.content.close()

                            # Update tracking info after successful upload
                            known_files[file_id]["modified_time"] = gfile.get(
                                "modifiedDate"
                            )
                            known_files[file_id]["local_mtime"] = current_mtime
                            known_files[file_id]["local_size"] = current_size

                    except FileNotFoundError:
                        pass
                    except Exception as e:
                        debug_print(
                            f"      Error checking local file {local_file.name}: {e}"
                        )

            # Check for new local files (files that exist locally but not in Drive)
            local_folder = Path(local_path)
            if not local_folder.exists():
                continue

            # Use rglob to recursively find all files and directories
            for local_item in local_folder.rglob("*"):
                local_item_str = str(local_item)
                item_name = local_item.name

                # Skip if already tracked, a system/state file, or a temporary file
                if (local_item_str in local_to_drive
                    or item_name.startswith(".")
                    or item_name.endswith(".tmp")):
                    continue

                # Determine the parent folder ID for the upload
                relative_path = local_item.relative_to(local_folder)
                parent_path_str = str(local_folder / relative_path.parent)
                parent_folder_id = local_to_drive.get(parent_path_str, folder_id)

                # Check if item with same name already exists in Drive parent folder
                existing_item = None
                for item_id, item_info in known_files.items():
                    item_parent_path = str(Path(item_info["local_path"]).parent)
                    if (
                        item_info["title"] == item_name
                        and item_parent_path == parent_path_str
                    ):
                        existing_item = item_info
                        existing_item["id"] = item_id
                        break

                if local_item.is_dir():
                    if existing_item:
                        local_to_drive[local_item_str] = existing_item["id"]
                        debug_print(
                            f"  🔗 Linking local directory to existing remote one: {item_name}"
                        )
                    else:
                        try:
                            debug_print(
                                f"  📤 Creating new remote directory: {item_name}"
                            )
                            update_mount_state(
                                folder_name,
                                "SYNCING_UP",
                                f"Creating directory {item_name}",
                            )
                            folder_metadata = {
                                "title": item_name,
                                "mimeType": "application/vnd.google-apps.folder",
                                "parents": [{"id": parent_folder_id}],
                            }
                            gfolder = service.CreateFile(folder_metadata)
                            gfolder.Upload()

                            # Add to tracking
                            new_folder_id = gfolder["id"]
                            known_files[new_folder_id] = {
                                "modified_time": gfolder.get("modifiedDate", ""),
                                "local_path": local_item_str,
                                "title": item_name,
                            }
                            local_to_drive[local_item_str] = new_folder_id
                            debug_print(
                                f"      Successfully created remote directory: {item_name}"
                            )
                        except Exception as e:
                            debug_print(
                                f"      Failed to create remote directory {item_name}: {e}"
                            )

                elif local_item.is_file():
                    if existing_item:
                        local_to_drive[local_item_str] = existing_item["id"]
                        debug_print(
                            f"  🔗 Linking local file to existing remote one: {item_name}"
                        )
                    else:
                        try:
                            debug_print(
                                f"  📤 Uploading new local file to Drive: {item_name}"
                            )
                            update_mount_state(
                                folder_name, "SYNCING_UP", f"Uploading {item_name}"
                            )
                            gfile = service.CreateFile(
                                {
                                    "title": item_name,
                                    "parents": [{"id": parent_folder_id}],
                                }
                            )
                            gfile.SetContentFile(local_item_str)
                            gfile.Upload()
                            if gfile.content:
                                gfile.content.close()

                            local_mtime = os.path.getmtime(local_item_str)
                            local_size = os.path.getsize(local_item_str)
                            new_file_id = gfile["id"]
                            known_files[new_file_id] = {
                                "modified_time": gfile.get("modifiedDate", ""),
                                "local_path": local_item_str,
                                "title": item_name,
                                "local_mtime": local_mtime,
                                "local_size": local_size,
                            }
                            local_to_drive[local_item_str] = new_file_id
                            debug_print(f"      Successfully uploaded: {item_name}")
                        except Exception as e:
                            debug_print(f"      Failed to upload {item_name}: {e}")

            # If we got here, Drive sync was successful
            drive_sync_successful = True
            consecutive_errors = 0
            update_mount_state(folder_name, "IDLE", "Awaiting changes...")

        except Exception as e:
            # Drive sync failed - could be auth expiration, network issue, etc.
            consecutive_errors += 1
            error_msg = str(e)

            if consecutive_errors <= max_consecutive_errors:
                print(
                    f"  ⚠️ Drive sync error for '{folder_name}' (attempt {consecutive_errors}/{max_consecutive_errors}): {error_msg}"
                )
                update_mount_state(
                    folder_name,
                    "DRIVE_ERROR",
                    f"Retrying... ({consecutive_errors}/{max_consecutive_errors})",
                )
            else:
                print(
                    f"  ⚠️ Drive sync failed for '{folder_name}' - entering degraded mode"
                )
                print(f"     Error: {error_msg}")
                print(
                    f"     Note: Backups continue independently via backup monitor thread"
                )
                update_mount_state(
                    folder_name, "DRIVE_OFFLINE", "Drive unavailable - backups continue"
                )

        is_first_run = False
        # Wait before next check (with ability to interrupt)
        stop_event.wait(check_interval)

    print(f"🔇 Listener stopped for '{folder_name}'")


def mount_drive_folder(service, folder_name, folder_id=None):
    """
    Mounts a Google Drive folder to the local filesystem and starts listening for changes.
    Also starts an independent backup monitor thread.
    """
    # Check if already mounted
    if folder_name in MOUNTED_FOLDERS:
        print(f"⚠️  Folder '{folder_name}' is already mounted.")
        return False

    try:
        # If folder_id not provided, search for it
        if not folder_id:
            debug_print(f"  Searching for folder '{folder_name}' in Google Drive...")
            file_list = service.ListFile(
                {
                    "q": f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
                }
            ).GetList()

            if len(file_list) == 0:
                print(f"  ❌ Folder '{folder_name}' not found in your Drive.")
                return False

            folder_id = file_list[0]["id"]
            debug_print(f"  Found folder with ID: {folder_id}")

        # Create local mount path
        local_path = MOUNT_BASE_PATH / folder_name
        debug_print(f"  Creating local directory: {local_path}")
        local_path.mkdir(parents=True, exist_ok=True)
        add_mount_to_state(folder_name, folder_id, local_path)

        # Download all contents
        print(f"  📦 Downloading all files from '{folder_name}'...")
        download_folder_recursive(service, folder_id, local_path)
        update_mount_state(folder_name, "IDLE", "Initial download complete.")
        print(f"  ✅ Initial download complete!")

        # Start listener thread for Drive sync
        stop_event = threading.Event()
        listener_thread = threading.Thread(
            target=listen_for_changes,
            args=(
                service,
                folder_id,
                local_path,
                folder_name,
                stop_event,
                "from_drive",
            ),
            daemon=True,
        )
        listener_thread.start()

        # Start independent backup monitor thread
        backup_thread = threading.Thread(
            target=backup_monitor_thread,
            args=(local_path, folder_name, stop_event),
            daemon=True,
        )
        backup_thread.start()

        # Store mount info
        MOUNTED_FOLDERS[folder_name] = {
            "folder_id": folder_id,
            "local_path": str(local_path),
            "listener_thread": listener_thread,
            "backup_thread": backup_thread,
            "stop_event": stop_event,
        }

        print(f"\n✅ Successfully mounted '{folder_name}' to {local_path}")
        print(f"   Drive sync is now active.")
        print(f"   Independent backup monitor is now active.")
        return True

    except Exception as e:
        print(f"❌ Failed to mount folder: {e}")
        return False


def reactivate_listener(service, folder_name, sync_mode="from_drive"):
    """
    Reactivates the background listener for an existing local folder without re-downloading.
    Also starts the independent backup monitor.
    """
    # Check if already active
    if folder_name in MOUNTED_FOLDERS:
        if MOUNTED_FOLDERS[folder_name]["listener_thread"].is_alive():
            print(f"⚠️  Listener for '{folder_name}' is already active.")
            return False
        else:
            # Thread exists but is dead, clean it up
            debug_print(f"  Cleaning up dead listener for '{folder_name}'...")
            del MOUNTED_FOLDERS[folder_name]

    try:
        # Check if local folder exists
        local_path = MOUNT_BASE_PATH / folder_name
        if not local_path.exists():
            print(f"  ❌ Local folder not found at: {local_path}")
            print(f"     Use option 3 (Mount Drive Folder) to download it first.")
            return False

        # Search for folder in Drive
        debug_print(f"  Searching for folder '{folder_name}' in Google Drive...")
        file_list = service.ListFile(
            {
                "q": f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
            }
        ).GetList()

        if len(file_list) == 0:
            print(f"  ❌ Folder '{folder_name}' not found in your Drive.")
            return False

        folder_id = file_list[0]["id"]
        debug_print(f"  Found folder with ID: {folder_id}")
        add_mount_to_state(folder_name, folder_id, local_path)

        # Start listener thread for Drive sync
        stop_event = threading.Event()
        listener_thread = threading.Thread(
            target=listen_for_changes,
            args=(service, folder_id, local_path, folder_name, stop_event, sync_mode),
            daemon=True,
        )
        listener_thread.start()

        # Start independent backup monitor thread
        backup_thread = threading.Thread(
            target=backup_monitor_thread,
            args=(local_path, folder_name, stop_event),
            daemon=True,
        )
        backup_thread.start()

        # Store mount info
        MOUNTED_FOLDERS[folder_name] = {
            "folder_id": folder_id,
            "local_path": str(local_path),
            "listener_thread": listener_thread,
            "backup_thread": backup_thread,
            "stop_event": stop_event,
        }

        print(f"\n✅ Successfully reactivated listener for '{folder_name}'")
        print(f"   Local path: {local_path}")
        print(f"   Drive sync is now active.")
        print(f"   Independent backup monitor is now active.")
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
            print("  Use option 3 (Mount Drive Folder) to download a folder first.")
            return
    else:
        print("  No mount directory found.")
        print("  Use option 3 (Mount Drive Folder) to download a folder first.")
        return

    folder_name = (
        input("\n  Enter folder name or number to reactivate: ").strip().lower()
    )

    # Sync mode prompt
    print("\n  Choose a sync strategy for reactivation:")
    print("    [1] Sync to Drive (upload local changes)")
    print("    [2] Sync from Drive (overwrite local changes)")
    sync_choice = input("  > ").strip()

    if sync_choice == "1":
        sync_mode = "to_drive"
    elif sync_choice == "2":
        sync_mode = "from_drive"
    else:
        print("  Invalid choice. Defaulting to 'Sync from Drive'.")
        sync_mode = "from_drive"

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

    reactivate_listener(service, folder_name, sync_mode)


def unmount_drive_folder(folder_name):
    """
    Unmounts a folder and stops its listener and backup threads.
    """
    if folder_name not in MOUNTED_FOLDERS:
        print(f"⚠️  Folder '{folder_name}' is not currently mounted.")
        return False

    try:
        mount_info = MOUNTED_FOLDERS[folder_name]

        # Signal both threads to stop
        mount_info["stop_event"].set()

        # Wait for threads to finish (with timeout)
        mount_info["listener_thread"].join(timeout=5)
        if "backup_thread" in mount_info:
            mount_info["backup_thread"].join(timeout=5)

        # Remove from mounted folders
        del MOUNTED_FOLDERS[folder_name]
        remove_mount_from_state(folder_name)

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


def change_backup_path_interactive():
    """Interactive interface for changing the backup path."""
    global BACKUP_PATH
    # Ensure the current backup path exists for resolving
    BACKUP_PATH.mkdir(parents=True, exist_ok=True)

    print("\n--- 💾 Change Backup Path ---")
    print(f"  Current backup path is: {BACKUP_PATH.resolve()}")
    new_path_str = input(
        "  Enter new path (e.g., H:/my_backups or ./backups) (leave blank to cancel): "
    ).strip()

    if new_path_str:
        try:
            new_path = Path(new_path_str)
            new_path.mkdir(
                parents=True, exist_ok=True
            )  # Create dir to ensure it's valid
            BACKUP_PATH = new_path
            save_config()
            print(
                f"  ✅ Backup path updated. Files will be saved to: {BACKUP_PATH.resolve()}"
            )
        except Exception as e:
            print(f"  ❌ Invalid path. Could not set backup location. Error: {e}")
    else:
        print("  Backup path change cancelled.")


def show_mounted_folders():
    """Displays all currently mounted folders."""
    print("\n--- 📋 Currently Mounted Folders ---")

    if not MOUNTED_FOLDERS:
        print("  No folders are currently mounted.")
    else:
        for folder_name, info in MOUNTED_FOLDERS.items():
            drive_status = (
                "🟢 Active" if info["listener_thread"].is_alive() else "🔴 Stopped"
            )
            backup_status = (
                "🟢 Active"
                if info.get("backup_thread") and info["backup_thread"].is_alive()
                else "🔴 Stopped"
            )
            print(
                f"  Drive Sync: {drive_status} | Backup: {backup_status} | {folder_name}"
            )
            print(f"      Local path: {info['local_path']}")
            print(f"      Drive ID: {info['folder_id']}")

    print("------------------------------------")

def toggle_debug_mode():
    """Toggles the debug mode with an interactive monitoring dashboard."""
    global DEBUG
    DEBUG = not DEBUG
    print(f"  Debug mode is now {'ON' if DEBUG else 'OFF'}")
    
    if not DEBUG:
        return

    import os
    import time
    import select
    import sys
    from datetime import datetime

    def enable_ansi_support():
        """Enable ANSI escape sequence support for Windows."""
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    def write_at(text, save_pos=False):
        """Write text and optionally save cursor position."""
        if save_pos:
            print(SAVE_CURSOR + text, end='', flush=True)
        else:
            print(text, end='', flush=True)

    def update_time_section():
        """Update just the time section."""
        print(RESTORE_CURSOR + CLEAR_LINE, end='')
        current_datetime = datetime.now()
        write_at(f"Time: {current_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print()  # New line after time

    def update_debug_log(last_size):
        """Update debug log section only if there are new messages.
        Returns the new buffer size."""
        current_size = len(DEBUG_BUFFER)
        if current_size == last_size:
            return last_size
            
        with DEBUG_BUFFER_LOCK:
            start_idx = max(0, len(DEBUG_BUFFER) - 10)
            logs = DEBUG_BUFFER[start_idx:]
        
        # Move to debug log section (saved position + offset)
        print(RESTORE_CURSOR, end='')
        for _ in range(20):  # Approximate number of lines to debug section
            print(CURSOR_DOWN, end='')
        
        # Clear and rewrite debug logs
        for _ in range(12):  # Clear area for logs (10 logs + header + separator)
            print(CLEAR_LINE + CURSOR_DOWN, end='')
        print(CURSOR_UP * 12, end='')  # Move back up
        
        print(CLEAR_LINE + "📝 Recent Debug Messages:")
        print(CLEAR_LINE + "-" * 50)
        for log_entry in logs:
            print(CLEAR_LINE + f"  {log_entry}")
            
        return current_size

    # Enable ANSI support and setup display
    enable_ansi_support()
    print(HIDE_CURSOR + CLEAR_SCREEN)  # Initial clear and hide cursor
    
    refresh_interval = 2.0  # Refresh every 2 seconds
    last_refresh = 0
    full_refresh_interval = 30.0  # Full refresh every 30 seconds
    last_full_refresh = 0
    last_debug_size = 0  # Track size of debug buffer
    
    while DEBUG:
        try:
            current_time = time.time()
            
            # Full refresh periodically to prevent display corruption
            if current_time - last_full_refresh >= full_refresh_interval:
                print(CLEAR_SCREEN + MOVE_TO_TOP)
                
                # Header (save position after header for time updates)
                write_at("\n=== 🔍 Drive Sync Monitor ===\n", save_pos=True)
                write_at(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                write_at(f"Auto-refresh: Every {refresh_interval} seconds\n")
                write_at("=" * 50 + "\n")
                
                # Mounted Folders Status
                write_at("\n📂 Mounted Folders:\n")
                if not MOUNTED_FOLDERS:
                    write_at("  No folders currently mounted\n")
                else:
                    for folder_name, info in MOUNTED_FOLDERS.items():
                        drive_thread = info["listener_thread"]
                        backup_thread = info.get("backup_thread")
                        
                        # Thread status indicators
                        drive_status = "🟢" if drive_thread.is_alive() else "🔴"
                        backup_status = "🟢" if backup_thread and backup_thread.is_alive() else "🔴"
                        
                        write_at(f"\n  📁 {folder_name}:\n")
                        write_at(f"    Drive Sync Thread: {drive_status} {'Active' if drive_thread.is_alive() else 'Stopped'}\n")
                        write_at(f"    Backup Thread:     {backup_status} {'Active' if backup_thread and backup_thread.is_alive() else 'Stopped'}\n")
                        write_at(f"    Local Path:        {info['local_path']}\n")
                        write_at(f"    Drive Folder ID:   {info['folder_id']}\n")
                        
                        # Count files in local directory
                        try:
                            local_path = Path(info['local_path'])
                            file_count = sum(1 for _ in local_path.rglob('*') if _.is_file())
                            write_at(f"    Files Watched:     {file_count}\n")
                        except Exception:
                            write_at("    Files Watched:     Unable to count\n")
                
                # Mount State Info
                write_at("\n📊 Mount State:\n")
                if STATE_FILE.exists():
                    try:
                        with open(STATE_FILE, 'r') as f:
                            state = json.load(f)
                            for folder, status in state.items():
                                status_icon = "🟢" if status.get('status') == 'IDLE' else "🔄"
                                write_at(f"  {status_icon} {folder}: {status.get('status', 'Unknown')} - {status.get('status_message', '')}\n")
                    except Exception:
                        write_at("  Unable to read mount state file\n")
                else:
                    write_at("  No mount state file exists\n")
                
                # Backup Info
                write_at(f"\n💾 Backup Location: {BACKUP_PATH}\n")
                
                # Initial debug log display
                last_debug_size = update_debug_log(0)  # Force full update on initial display
                
                last_full_refresh = current_time
            
            # Regular refresh for time and logs
            if current_time - last_refresh >= refresh_interval:
                update_time_section()
                last_debug_size = update_debug_log(last_debug_size)  # Only updates if there are new messages
                last_refresh = current_time
                
                # Update countdown
                print(RESTORE_CURSOR, end='')
                for _ in range(30):  # Move to bottom
                    print(CURSOR_DOWN, end='')
                print(CLEAR_LINE + f"Auto-refresh in {refresh_interval - (time.time() - last_refresh):.1f}s")
                print(CLEAR_LINE + "Press Ctrl+C to exit debug mode, Enter to force refresh...")
            
            # Check for user input (non-blocking)
            if os.name == 'nt':
                import msvcrt
                if msvcrt.kbhit():
                    if msvcrt.getch() == b'\r':
                        last_refresh = 0  # Force refresh
            else:
                # Unix-like systems
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if rlist:
                    sys.stdin.readline()
                    last_refresh = 0  # Force refresh
            
            time.sleep(0.1)  # Prevent CPU overuse
            
        except KeyboardInterrupt:
            DEBUG = False
            print(SHOW_CURSOR + "\nExiting debug mode...")
            break
        except Exception as e:
            print(SHOW_CURSOR + f"\nError in debug display: {e}")
            print("Press Enter to retry, Ctrl+C to exit...")
            try:
                input()
            except KeyboardInterrupt:
                DEBUG = False
                print(SHOW_CURSOR)  # Ensure cursor is visible
                break
        

def main():
    """Displays the main interactive menu for Google Drive utilities."""
    # Load configuration at startup
    load_config()

    parser = argparse.ArgumentParser(
        description="Google Drive Utility with command-line support."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Mount command
    mount_parser = subparsers.add_parser(
        "mount", help="Mount a Google Drive folder and start syncing."
    )
    mount_parser.add_argument(
        "folder_name", type=str, help="The name of the Drive folder to mount."
    )

    # Unmount command
    unmount_parser = subparsers.add_parser(
        "unmount", help="Unmount a folder and stop syncing. (Requires running process)"
    )
    unmount_parser.add_argument(
        "folder_name", type=str, help="The name of the mounted folder to unmount."
    )

    # Reactivate command
    reactivate_parser = subparsers.add_parser(
        "reactivate", help="Reactivate listener for an existing local folder."
    )
    reactivate_parser.add_argument(
        "folder_name", type=str, help="The name of the local folder to reactivate."
    )
    reactivate_parser.add_argument(
        "--sync-mode",
        choices=["to_drive", "from_drive"],
        default="from_drive",
        help="Sync direction on reactivation: 'to_drive' (upload local changes) or 'from_drive' (overwrite local).",
    )

    # Add debug flag to all subparsers and the main parser
    for p in [parser, mount_parser, unmount_parser, reactivate_parser]:
        p.add_argument(
            "-d", "--debug", action="store_true", help="Enable detailed debug logging."
        )

    args = parser.parse_args()

    if args.debug:
        global DEBUG
        DEBUG = True
        debug_print("--- 🐞 Debug mode enabled ---")

    if args.command:
        # --- Command-Line Mode ---
        if args.command in ["mount", "reactivate"]:
            service = get_drive_service()
            if not service:
                return  # Exit if auth fails

            if args.command == "mount":
                success = mount_drive_folder(service, args.folder_name)
            else:  # reactivate
                success = reactivate_listener(service, args.folder_name, args.sync_mode)

            if success:
                print(f"\n🚀 Command '{args.command} {args.folder_name}' successful.")
                print("   The script will continue running to keep the sync active.")
                print("   Press Ctrl+C to stop all listeners and exit.")
                try:
                    # Keep the main thread alive so daemon threads can run
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n🛑 Keyboard interrupt received. Shutting down...")
                    for folder_name in list(MOUNTED_FOLDERS.keys()):
                        unmount_drive_folder(folder_name)
                    remove_mount_from_state(
                        args.folder_name
                    )  # Ensure state is clean on exit
                    print("Exiting. Goodbye! 👋")
            else:
                print(f"\n❌ Command '{args.command} {args.folder_name}' failed.")

        elif args.command == "unmount":
            print(
                "\nNOTE: The 'unmount' command only works if this script is already running and managing the mount."
            )
            print(
                "It cannot stop a separate, running process. Use the interactive menu for that."
            )

    else:
        # --- Interactive Mode ---
        while True:
            print("\n====== 📁 Google Drive Utility ======")
            print("  [1] Browse/Download from Google Drive")
            print("  [2] Upload file to Google Drive")
            print("  [3] Mount Drive Folder (sync & watch)")
            print("  [4] Unmount Drive Folder")
            print("  [5] Reactivate Folder Listener")
            print("  [6] Show Mounted Folders")
            print("  [7] Change Backup Path")
            print("  [8] Debug/Log Mode")
            print("  [9] Exit")
            print("=====================================")

            choice = input("Enter your choice (1-8): ").strip()
            drive_service = None  # Reset service

            if choice in ["1", "2", "3", "5"]:
                drive_service = get_drive_service()
                if not drive_service:
                    continue

            if choice == "1":
                browse_google_drive(drive_service)
            elif choice == "2":
                upload_to_drive_interactive(drive_service)
            elif choice == "3":
                mount_drive_folder_interactive(drive_service)
            elif choice == "4":
                unmount_drive_folder_interactive()
            elif choice == "5":
                reactivate_listener_interactive(drive_service)
            elif choice == "6":
                show_mounted_folders()
            elif choice == "7":
                change_backup_path_interactive()
            elif choice == "8":
                toggle_debug_mode()
            elif choice == "9":
                print("\nStopping all folder listeners...")
                for folder_name in list(MOUNTED_FOLDERS.keys()):
                    unmount_drive_folder(folder_name)
                if STATE_FILE.exists():  # Clean up state file on graceful exit
                    STATE_FILE.unlink()
                print("Exiting. Goodbye! 👋")
                break
            else:
                print("\nInvalid choice. Please enter a number between 1 and 8.")


if __name__ == "__main__":
    main()
    # Final cleanup of state file on exit
    with STATE_LOCK:
        if STATE_FILE.exists() and not MOUNTED_FOLDERS:
            debug_print("Final cleanup: Removing state file as no folders are mounted.")
            STATE_FILE.unlink()
