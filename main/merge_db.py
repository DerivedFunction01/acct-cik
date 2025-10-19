import sqlite3
import pandas as pd
import argparse
from pathlib import Path


def create_unified_schema(conn):
    """
    Creates a unified schema in the destination database that accommodates
    tables and columns from both colab.py and classify-new.py.
    """
    c = conn.cursor()
    print("Creating unified schema in the destination database...")

    # Combined schema for all tables
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
    Transfers data from a table in the source database to the destination database.
    Uses pandas for reading and `INSERT OR IGNORE` for writing to handle duplicates.
    """
    print(f"  Transferring data for table: {table_name}...")
    try:
        # 1. Read all data from the source table
        df = pd.read_sql(f"SELECT * FROM {table_name}", source_conn)
        
        if df.empty:
            print(f"    -> No data to transfer for {table_name}.")
            return

        # 2. Use executemany to perform an "INSERT OR IGNORE"
        # This correctly handles duplicates in common tables (report_data, names, etc.)
        cols = ', '.join(df.columns)
        placeholders = ', '.join(['?'] * len(df.columns))
        sql = f"INSERT OR IGNORE INTO {table_name} ({cols}) VALUES ({placeholders})"
        
        # Get data as a list of tuples for executemany
        data_tuples = df.to_records(index=False)
        
        dest_conn.executemany(sql, data_tuples)
        # We must commit here since we're not using the pandas `to_sql` context
        dest_conn.commit() 
        
        print(f"    -> Processed {len(df)} rows from {table_name}. (Duplicates ignored)")

    except (sqlite3.DatabaseError, pd.io.sql.DatabaseError) as e:
        print(f"    -> Could not read table '{table_name}'. It might not exist in this source DB. Error: {e}")


def merge_databases(colab_db_path, classify_db_path, merged_db_path):
    """
    Merges two SQLite databases into a new one.
    """
    print(f"Starting database merge process...")
    print(f"Source (colab.py): {colab_db_path}")
    print(f"Source (classify-new.py): {classify_db_path}")
    print(f"Destination: {merged_db_path}")

    # Connect to all three databases
    with sqlite3.connect(merged_db_path) as dest_conn, \
         sqlite3.connect(colab_db_path) as colab_conn, \
         sqlite3.connect(classify_db_path) as classify_conn:

        # 1. Create the unified schema in the destination DB
        create_unified_schema(dest_conn)

        # 2. Define which tables to transfer from which source
        colab_tables = ["report_data", "names", "webpage_result", "fail_results"]
        classify_tables = ["report_data", "names", "server_result", "fail_results"]

        # 3. Transfer data
        print("\nProcessing source DB from colab.py...")
        for table in colab_tables:
            transfer_table_data(colab_conn, dest_conn, table)

        print("\nProcessing source DB from classify-new.py...")
        for table in classify_tables:
            transfer_table_data(classify_conn, dest_conn, table)

    print("\n🎉 Merge complete! The unified database is saved at:", merged_db_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge two SQLite databases from the SEC data pipeline.")
    parser.add_argument("colab_db", type=Path, help="Path to the database from colab.py (contains webpage_result).")
    parser.add_argument("classify_db", type=Path, help="Path to the database from classify-new.py (contains server_result).")
    parser.add_argument("merged_db", type=Path, help="Path for the new merged database file.")
    args = parser.parse_args()

    merge_databases(args.colab_db, args.classify_db, args.merged_db)
