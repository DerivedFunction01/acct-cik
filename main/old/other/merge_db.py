import sqlite3
import pandas as pd
from pathlib import Path


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
    # From webpage_result
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS webpage_result (
            url TEXT PRIMARY KEY,
            matches TEXT,
            FOREIGN KEY (url) REFERENCES report_data(url)
        )
        """
    )
    # From server_result
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
    # WAL
    c.execute("PRAGMA journal_mode=WAL")

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
    print(f"Source (webpage_result): {colab_db_path}")
    print(f"Source (server_result): {classify_db_path}")
    print(f"Destination: {merged_db_path}")

    try:
        with sqlite3.connect(merged_db_path) as dest_conn, sqlite3.connect(
            colab_db_path
        ) as colab_conn, sqlite3.connect(classify_db_path) as classify_conn:

            create_unified_schema(dest_conn)

            colab_tables = ["report_data", "names", "webpage_result", "fail_results"]
            classify_tables = ["report_data", "names", "server_result", "fail_results"]

            print("\nProcessing source DB from webpage_result...")
            for table in colab_tables:
                transfer_table_data(colab_conn, dest_conn, table)

            print("\nProcessing source DB from server_result...")
            for table in classify_tables:
                transfer_table_data(classify_conn, dest_conn, table)

        print("\n🎉 Merge complete! The unified database is saved at:", merged_db_path)

    except sqlite3.Error as e:
        print(f"\n❌ A database error occurred: {e}")
        print("Merge failed.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        print("Merge failed.")


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
    print("Tip: Use list_local_db_files() to find your files.")

    try:
        # 1. Get source DB paths
        colab_db_path = Path(
            input("  1. Path to webpage_result DB (source 1): ").strip()
        )
        classify_db_path = Path(
            input("  2. Path to server_result DB (source 2): ").strip()
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


if __name__ == "__main__":
    print("Database Merge Utility")
    print("=" * 50)
    print("Available functions:")
    print("  - list_local_db_files()")
    print("  - run_merge_interactive()")
    print("  - merge_databases(colab_db_path, classify_db_path, merged_db_path)")
    print("=" * 50)

    run_merge_interactive()
