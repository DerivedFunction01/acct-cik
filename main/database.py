# %%
## Initialization
import sqlite3
from pathlib import Path
import pandas as pd
import json

# Default path, can be updated if needed
db_path = "./web_data.db"


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
    conn = sqlite3.connect(db_path)
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

def import_server_backup(backup_path: str = "./server_results_backup.xlsx"):
    """
    Imports data from the server backup Excel file into the server_result table.
    Uses INSERT OR REPLACE to handle duplicates, updating existing entries.
    """
    print(f"Attempting to import from '{backup_path}'...")
    try:
        backup_df = pd.read_excel(backup_path)
    except FileNotFoundError:
        print(f"❌ Error: Backup file not found at '{backup_path}'.")
        print("   Please run the 'backup_server_results' step in the analysis pipeline first.")
        return

    # The backup contains cik, year, url, server_response. We only need url and server_response.
    if "url" not in backup_df.columns or "server_response" not in backup_df.columns:
        print("❌ Error: Backup file is missing 'url' or 'server_response' columns.")
        return

    records_to_insert = backup_df[["url", "server_response"]].to_records(index=False)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        # Use executemany for efficient batch insertion.
        # INSERT OR REPLACE will update existing rows if the URL (PRIMARY KEY) matches.
        cursor.executemany(
            "INSERT OR REPLACE INTO server_result (url, server_response) VALUES (?, ?)",
            records_to_insert,
        )
        conn.commit()
        print(f"✅ Successfully imported/updated {cursor.rowcount} records into 'server_result'.")
    except sqlite3.Error as e:
        print(f"❌ A database error occurred during import: {e}")
        conn.rollback()
    finally:
        conn.close()


def import_server_results_from_parquet(directory: str = "."):
    """
    Imports data from server_result_chunk_*.parquet files into the server_result table.
    Uses INSERT OR REPLACE to handle duplicates, updating existing entries.
    """
    print(f"Searching for 'server_result_chunk_*.parquet' files in '{directory}'...")
    
    # Find all parquet files matching the pattern
    search_path = Path(directory)
    parquet_files = list(search_path.glob("server_result_chunk_*.parquet"))

    if not parquet_files:
        print("❌ No 'server_result_chunk_*.parquet' files found to import.")
        return

    print(f"Found {len(parquet_files)} files to process.")

    # Read and concatenate all parquet files
    all_dfs = [pd.read_parquet(f) for f in parquet_files]
    combined_df = pd.concat(all_dfs, ignore_index=True)

    # Drop duplicates, keeping the last entry in case of overlap
    combined_df.drop_duplicates(subset=["url"], keep="last", inplace=True)

    if "url" not in combined_df.columns or "server_response" not in combined_df.columns:
        print("❌ Error: Parquet files are missing 'url' or 'server_response' columns.")
        return

    # Convert the server_response object to a JSON string for better portability
    # and to avoid storing it as a binary blob (pickle) in SQLite.
    print("   -> Serializing server_response column to JSON...")
    combined_df["server_response"] = combined_df["server_response"].apply(json.dumps)

    records_to_insert = combined_df[["url", "server_response"]].to_records(index=False)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.executemany(
            "INSERT OR REPLACE INTO server_result (url, server_response) VALUES (?, ?)",
            records_to_insert,
        )
        conn.commit()
        print(f"✅ Successfully imported/updated {cursor.rowcount} records into 'server_result' from {len(parquet_files)} files.")
    except sqlite3.Error as e:
        print(f"❌ A database error occurred during import: {e}")
        conn.close()


# %%
## Execute SELECT Statements
#ff = execute_sql("SELECT * FROM report_data WHERE NOT url=''")
#ff.to_csv("./report_data.csv", index=False)
#len(ff)


# %%
# ff = execute_sql("SELECT * FROM names", fetch=True)
# # ff[["name"]].to_excel("./names.xlsx", index=False)
# ff.head()

# %%
## Execute SELECT Statements on webpage result
# ff = execute_sql("SELECT * FROM webpage_result")
# ff.head()

# %%
## Execute SELECT Statements on server result
#ff = execute_sql("SELECT * FROM server_result")
#ff.head()

# %%
## Execute INSERT/DELETE/UPDATE Statements
# ff = execute_sql("DELETE FROM server_result")
# print(ff)

#%%
if __name__ == "__main__":
    last_df = None  # "Global" variable to hold the last queried DataFrame
    # Create a menu for common operations
    print("Database Operations Menu:")
    print("1. SELECT * FROM webpage_result")
    print("2. SELECT * FROM server_result")
    print("3. Custom SQL Query")
    print("4. Import server_result from Excel backup")
    print("5. Import server_result from Parquet chunks")
    print("6. Inspect last DataFrame")
    print("7. Exit")
    print("-" * 30)

    while True:
        choice = input("Enter your choice (1-7): ").strip()
        if choice == "1":
            df = execute_sql("SELECT * FROM webpage_result")
            last_df = df
            print(df.head(20))
            # Print statistics
            print("-" * 30)
            print("Statistics:")
            print(df.describe())
            print("-" * 30)
        elif choice == "2":
            df = execute_sql("SELECT * FROM server_result")
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
            import_server_results_from_parquet()
        elif choice == "6":
            if last_df is not None and not last_df.empty:
                print("Last DataFrame is available as 'last_df'.")
                print("You can perform operations like 'last_df.iloc[0]' or 'last_df.info()'.")
                print("Type 'exit' or press Ctrl+Z (Windows) / Ctrl+D (Unix) to return to the menu.")
                import code
                code.interact(local=locals())
            else:
                print("No DataFrame has been loaded yet. Please run a query first.")
        elif choice == "7":
            print("Exiting the program.")
            break
        else:
            print("Invalid choice. Please try again.")
