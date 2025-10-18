from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import os

# --- AUTHENTICATION ---
gauth = GoogleAuth()
gauth.CommandLineAuth()
drive = GoogleDrive(gauth)


# --- FOLDER LOGIC ---
folder_name = 'db'
file_to_upload = 'web_data.db'

# 1. Check if the local file exists
print(f"Looking for local file: {file_to_upload}")
if not os.path.exists(file_to_upload):
    print(f"Error: File not found at '{file_to_upload}'")
    print("Please make sure 'example.txt' is in the same directory.")
else:
    # 2. Find the folder ID for 'db'
    print(f"Searching for folder '{folder_name}' in your Google Drive...")
    
    # Query for the folder
    # 'root' is the alias for "My Drive"
    file_list = drive.ListFile({
        'q': f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
    }).GetList()

    folder_id = None
    if len(file_list) > 0:
        # Folder found
        folder_id = file_list[0]['id']
        print(f"Found folder '{folder_name}' with ID: {folder_id}")
    else:
        # Folder not found, create it
        print(f"Folder '{folder_name}' not found, creating it...")
        folder_metadata = {
            'title': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [{'id': 'root'}] # Create it in "My Drive"
        }
        folder = drive.CreateFile(folder_metadata)
        folder.Upload()
        folder_id = folder['id']
        print(f"Created folder '{folder_name}' with ID: {folder_id}")

    # 3. Upload the file into that folder
    print(f"Uploading '{file_to_upload}' to folder '{folder_name}'...")
    
    # Set metadata, including the parent folder
    gfile = drive.CreateFile({
        'title': os.path.basename(file_to_upload),
        'parents': [{'id': folder_id}]  # This is the key change
    })
    
    # Set the content of the file
    gfile.SetContentFile(file_to_upload)
    
    # Upload the file
    gfile.Upload()
    print(f"Success! File ID: {gfile['id']}")
    print(f"File was uploaded to the '{folder_name}' folder.")
