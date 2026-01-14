import os
import glob
import shutil

def delete_folder(path):
    """Delete a folder if it exists."""
    if os.path.isdir(path):
        shutil.rmtree(path)

def delete_files_except(pattern, keep):
    """
    Delete files matching `pattern` except those in `keep`.
    `keep` is a set of basenames.
    """
    keep = set(keep)
    for path in glob.glob(pattern):
        if os.path.basename(path) not in keep:
            try:
                os.remove(path)
            except OSError:
                pass

def delete_intermediate(pattern):
    """Delete intermediate state files like *.db-*."""
    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError:
            pass

def cleanup():
    # 1. Delete the folder
    delete_folder("analysis_output")

    # 2. Delete all .db files except the two you want to keep
    keep_dbs = {"web_data.db", "prefiltered_data.db"}
    delete_files_except("*.db", keep_dbs)

    # 3. Delete intermediate DB states (*.db-*)
    delete_intermediate("*.db-*")

    # 4. Delete logs if you want
    delete_intermediate("*.log")

if __name__ == "__main__":
    cleanup()
