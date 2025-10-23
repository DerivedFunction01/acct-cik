import os
import time
import threading
import multiprocessing
import subprocess
import platform
import json
import sys
from pathlib import Path
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


# Global service object
DRIVE_SERVICE = None

# Global mounting state
MOUNT_STATE_FILE = ".mount_state.json"
MOUNT_BASE_PATH = Path("./drive/MyDrive")
MOUNTED_FOLDERS = {} # In-memory cache of state file


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

def save_mount_state():
    """Saves the current state of mounted folders to a file."""
    with open(MOUNT_STATE_FILE, "w") as f:
        json.dump(MOUNTED_FOLDERS, f, indent=4)

def load_mount_state():
    """Loads the state of mounted folders from a file."""
    global MOUNTED_FOLDERS
    if not Path(MOUNT_STATE_FILE).exists():
        MOUNTED_FOLDERS = {}
        return

    try:
        with open(MOUNT_STATE_FILE, "r") as f:
            loaded_state = json.load(f)
            # Clean up any processes that are no longer running
            for folder_name, info in list(loaded_state.items()):
                pid = info.get("pid")
                if pid:
                    try:
                        # Check if process exists
                        os.kill(pid, 0)
                    except OSError:
                        print(f"  Cleaning up stale listener process for '{folder_name}' (PID: {pid})")
                        del loaded_state[folder_name]
            MOUNTED_FOLDERS = loaded_state
    except (json.JSONDecodeError, IOError):
        MOUNTED_FOLDERS = {}

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
        print(f"      Standard removal failed: {e}")
    
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
        print(f"      Retry after GC failed: {e}")
    
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
                    capture_output=True
                )
            else:
                subprocess.run(
                    ["del", "/F", "/Q", str(file_path)],
                    shell=True,
                    check=True,
                    capture_output=True
                )
        else:
            # Linux/Mac: use rm -rf
            subprocess.run(
                ["rm", "-rf", str(file_path)],
                check=True,
                capture_output=True
            )
        
        print(f"      Removed using system command")
        return True
    except Exception as e:
        print(f"      System command failed: {e}")
    
    # Method 4: Mark for deletion on next restart (Windows only)
    if platform.system() == "Windows":
        try:
            import ctypes
            # MoveFileEx with MOVEFILE_DELAY_UNTIL_REBOOT flag
            ctypes.windll.kernel32.MoveFileExW(
                str(file_path),
                None,
                0x4  # MOVEFILE_DELAY_UNTIL_REBOOT
            )
            print(f"      File marked for deletion on next restart")
            return True
        except Exception as e:
            print(f"      Delayed deletion failed: {e}")
    
    return False


def listen_for_changes(folder_id, local_path, folder_name):
    """
    Background thread that periodically checks for changes in the Drive folder
    and syncs them to the local path. Also detects local changes (additions,
    deletions, modifications) and syncs them to Drive.
    """
    print(f"🔊 Listener started for '{folder_name}'")
    
    # Each process needs its own service object
    service = get_drive_service()

    # Track files we've seen (file_id -> {"modified_time": time, "local_path": path, "title": name})
    known_files = {}
    # Track local files by their path (local_path -> file_id)
    local_to_drive = {}
    
    check_interval = 10  # Check every 10 seconds
    
    while True: # This process will be killed externally
        try:
            # Get all files in the folder (and subfolders)
            query = f"'{folder_id}' in parents and trashed=false"
            file_list = service.ListFile({"q": query}).GetList()
            
            current_file_ids = set()
            drive_file_names = set()
            
            for item in file_list:
                file_id = item["id"]
                current_file_ids.add(file_id)
                modified_time = item.get("modifiedDate", "")
                file_title = item["title"]
                drive_file_names.add(file_title)
                
                if item["mimeType"] == "application/vnd.google-apps.folder":
                    # Ensure subfolder exists
                    subfolder_path = Path(local_path) / file_title
                    subfolder_path.mkdir(parents=True, exist_ok=True)
                    known_files[file_id] = {
                        "modified_time": modified_time,
                        "local_path": str(subfolder_path),
                        "title": file_title
                    }
                    local_to_drive[str(subfolder_path)] = file_id
                else:
                    file_path = Path(local_path) / file_title
                    # Check if file is new or modified
                    if file_id not in known_files or known_files[file_id]["modified_time"] != modified_time:
                        print(f"  📥 Syncing from Drive: {file_title}")
                        gfile = service.CreateFile({"id": file_id})
                        gfile.GetContentFile(str(file_path))
                        known_files[file_id] = {
                            "modified_time": modified_time,
                            "local_path": str(file_path),
                            "title": file_title
                        }
                        local_to_drive[str(file_path)] = file_id
                    else:
                        # File exists in Drive, update tracking info
                        known_files[file_id] = {
                            "modified_time": modified_time,
                            "local_path": str(file_path),
                            "title": file_title
                        }
                        local_to_drive[str(file_path)] = file_id
            
            # Check for deleted files in Drive (files that were known but aren't in current list)
            deleted_ids = set(known_files.keys()) - current_file_ids
            for deleted_id in deleted_ids:
                file_info = known_files[deleted_id]
                print(f"  🗑️  Detected deletion in Drive: {file_info['title']}")
                # Remove local file if it exists
                local_file_path = Path(file_info["local_path"])
                if local_file_path.exists():
                    if force_remove_file(local_file_path):
                        print(f"      Removed local file: {file_info['title']}")
                    else:
                        print(f"      ⚠️ Could not remove local file (in use): {file_info['title']}")
                        continue  # Skip cleanup if we couldn't delete
                        
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
                    print(f"  🗑️  Deleting from Drive (local deletion detected): {file_title}")
                    gfile = service.CreateFile({"id": file_id})
                    gfile.Delete()
                    if file_id in known_files:
                        local_path_str = known_files[file_id]["local_path"]
                        if local_path_str in local_to_drive:
                            del local_to_drive[local_path_str]
                        del known_files[file_id]
                except Exception as e:
                    print(f"      Failed to delete from Drive: {e}")
            
            # Check for new local files (files that exist locally but not in Drive)
            local_folder = Path(local_path)
            if local_folder.exists():
                for local_file in local_folder.iterdir():
                    local_file_str = str(local_file)
                    file_name = local_file.name
                    
                    # Skip if already tracked or if it's a system file
                    if local_file_str in local_to_drive or file_name.startswith('.'):
                        continue
                    
                    # Skip if file exists in Drive with same name
                    if file_name in drive_file_names:
                        continue
                    
                    # This is a new local file - upload it
                    if local_file.is_file():
                        try:
                            print(f"  📤 Uploading new local file to Drive: {file_name}")
                            gfile = service.CreateFile(
                                {"title": file_name, "parents": [{"id": folder_id}]}
                            )
                            gfile.SetContentFile(local_file_str)
                            gfile.Upload()
                            
                            # Add to tracking
                            new_file_id = gfile["id"]
                            known_files[new_file_id] = {
                                "modified_time": gfile.get("modifiedDate", ""),
                                "local_path": local_file_str,
                                "title": file_name
                            }
                            local_to_drive[local_file_str] = new_file_id
                            print(f"      Successfully uploaded: {file_name}")
                        except Exception as e:
                            print(f"      Failed to upload {file_name}: {e}")
            
        except Exception as e:
            print(f"  ⚠️ Listener error for '{folder_name}': {e}")
        
        # Wait before next check
        time.sleep(check_interval)
    
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
        
        # --- Launch listener as a detached background process ---
        python_executable = sys.executable
        script_path = os.path.abspath(__file__)
        
        # Use subprocess.Popen to run the script in the background
        # On Windows, DETACHED_PROCESS creates a new process without a console window.
        # On Linux/macOS, start_new_session=True detaches it from the current terminal.
        creation_flags = 0
        preexec_fn = None
        if platform.system() == "Windows":
            creation_flags = subprocess.DETACHED_PROCESS
        else: # Linux/macOS
            preexec_fn = os.setsid

        process = subprocess.Popen(
            [python_executable, script_path, "--listen-folder", folder_name, "--folder-id", folder_id, "--local-path", str(local_path)],
            creationflags=creation_flags,
            preexec_fn=preexec_fn,
            stdout=subprocess.DEVNULL, # Redirect stdout
            stderr=subprocess.DEVNULL  # Redirect stderr
        )
        
        # Store mount info
        MOUNTED_FOLDERS[folder_name] = {
            "folder_id": folder_id,
            "local_path": str(local_path),
            "pid": process.pid
        }
        save_mount_state()
        
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
        pid = MOUNTED_FOLDERS[folder_name].get("pid")
        if pid:
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
        
        # --- Launch listener as a detached background process ---
        python_executable = sys.executable
        script_path = os.path.abspath(__file__)

        creation_flags = 0
        preexec_fn = None
        if platform.system() == "Windows":
            creation_flags = subprocess.DETACHED_PROCESS
        else: # Linux/macOS
            preexec_fn = os.setsid

        process = subprocess.Popen(
            [python_executable, script_path, "--listen-folder", folder_name, "--folder-id", folder_id, "--local-path", str(local_path)],
            creationflags=creation_flags,
            preexec_fn=preexec_fn,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Store mount info
        MOUNTED_FOLDERS[folder_name] = {
            "folder_id": folder_id,
            "local_path": str(local_path),
            "pid": process.pid
        }
        save_mount_state()
        
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
        
        # Terminate the listener process
        pid = mount_info.get("pid")
        if pid:
            print(f"  Stopping listener process for '{folder_name}' (PID: {pid})...")
            try:
                proc = multiprocessing.Process(pid=pid)
                proc.terminate()
                proc.join(timeout=5)
            except Exception as e:
                print(f"    Could not terminate process {pid}. It may already be stopped. Error: {e}")
        
        # Remove from mounted folders
        del MOUNTED_FOLDERS[folder_name]
        save_mount_state()
        
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
        # Also check the file in case the script was just started
        if Path(MOUNT_STATE_FILE).exists():
            print("  (Run 'Show Mounted Folders' to load state from disk)")
    else:
        for folder_name, info in MOUNTED_FOLDERS.items():
            status = "🟢 Active" if info["listener_thread"].is_alive() else "🔴 Stopped"
            print(f"  {status} {folder_name}")
            print(f"      Local path: {info['local_path']}")
            print(f"      Drive ID: {info['folder_id']}")
    
    print("------------------------------------")


def main_menu():
    """Displays the main interactive menu for Google Drive utilities."""
    load_mount_state() # Load state on startup
    while True:
        print("\n====== 📁 Google Drive Utility ======")
        print("  [1] Browse & Download from Google Drive")
        print("  [2] Upload a file to Google Drive")
        print("  [3] Mount a Drive Folder (sync & watch)")
        print("  [4] Unmount a Drive Folder")
        print("  [5] Reactivate a Folder Listener")
        print("  [6] Show Mounted Folders")
        print("  [7] Stop all & Exit")
        print("  [8] Exit (keep listeners running)")
        print("=====================================")

        choice = input("Enter your choice (1-8): ").strip()

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
            load_mount_state() # Refresh state from disk
            show_mounted_folders()

        elif choice == "7":
            # Stop all listeners before exiting
            print("\nStopping all folder listeners...")
            for folder_name in list(MOUNTED_FOLDERS.keys()):
                unmount_drive_folder(folder_name)
            print("All services stopped. Exiting. Goodbye! 👋")
            break

        elif choice == "8":
            print("\nExiting menu. Background listeners will continue to run.")
            print("To stop them, restart the script and select 'Stop all & Exit'.")
            print("Goodbye! 👋")
            break

        else:
            print("\nInvalid choice. Please enter a number between 1 and 8.")


if __name__ == "__main__":
    # Check for listener-only mode
    if "--listen-folder" in sys.argv:
        try:
            folder_name_index = sys.argv.index("--listen-folder") + 1
            folder_id_index = sys.argv.index("--folder-id") + 1
            local_path_index = sys.argv.index("--local-path") + 1

            folder_name = sys.argv[folder_name_index]
            folder_id = sys.argv[folder_id_index]
            local_path = sys.argv[local_path_index]

            # This call will run forever until the process is terminated
            listen_for_changes(folder_id, local_path, folder_name)
        except (ValueError, IndexError) as e:
            # This will be written to a log file if output is redirected
            print(f"Listener mode error: Missing or invalid arguments. {e}")
    else:
        # Run the interactive menu
        main_menu()