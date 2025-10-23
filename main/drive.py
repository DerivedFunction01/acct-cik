import os
from pathlib import Path
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


# Global service object
DRIVE_SERVICE = None


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


def main_menu():
    """Displays the main interactive menu for Google Drive utilities."""
    while True:
        print("\n====== 📁 Google Drive Utility ======")
        print("  [1] Browse/Download from Google Drive")
        print("  [2] Upload file to Google Drive")
        print("  [3] Exit")
        print("=====================================")

        choice = input("Enter your choice (1-3): ").strip()

        if choice == "1":
            drive_service = get_drive_service()
            if drive_service:
                browse_google_drive(drive_service)

        elif choice == "2":
            drive_service = get_drive_service()
            if drive_service:
                upload_to_drive_interactive(drive_service)

        elif choice == "3":
            print("Exiting. Goodbye! 👋")
            break

        else:
            print("\nInvalid choice. Please enter a number between 1 and 3.")


if __name__ == "__main__":
    main_menu()
