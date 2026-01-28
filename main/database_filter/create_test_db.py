import pandas as pd
import sqlite3
from pathlib import Path
import os

# Configuration
SOURCE_DB = "web_data.db"
TARGET_DB = "test.db"
TEST_CASES_CSV = "data_check.csv"

def create_test_db():
    if not Path(SOURCE_DB).exists():
        print(f"❌ Source database '{SOURCE_DB}' not found.")
        return

    if not Path(TEST_CASES_CSV).exists():
        print(f"❌ Test cases file '{TEST_CASES_CSV}' not found.")
        return

    # 1. Load Test Cases
    print(f"📖 Reading {TEST_CASES_CSV}...")
    try:
        df_test = pd.read_csv(TEST_CASES_CSV)
        # Ensure columns exist
        if 'cik' not in df_test.columns or 'year' not in df_test.columns:
             print("❌ CSV must contain 'cik' and 'year' columns.")
             return
        
        # Normalize types
        df_test['cik'] = pd.to_numeric(df_test['cik'], errors='coerce').fillna(0).astype(int)
        df_test['year'] = pd.to_numeric(df_test['year'], errors='coerce').fillna(0).astype(int)
        
        target_pairs = df_test[['cik', 'year']].drop_duplicates()
        print(f"   Found {len(target_pairs)} unique CIK/Year pairs.")
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return

    # 2. Connect to Source DB and Fetch Data
    print(f"🔄 Connecting to {SOURCE_DB}...")
    src_conn = sqlite3.connect(SOURCE_DB)
    
    try:
        # Read metadata tables
        df_report = pd.read_sql("SELECT * FROM report_data", src_conn)
        df_names = pd.read_sql("SELECT * FROM names", src_conn)
    except Exception as e:
        print(f"❌ Error reading source DB: {e}")
        src_conn.close()
        return

    # Filter report_data for target pairs
    print("🔍 Filtering report_data...")
    merged_report = df_report.merge(target_pairs, on=['cik', 'year'], how='inner')
    
    if merged_report.empty:
        print("⚠️ No matching records found in report_data.")
        src_conn.close()
        return

    target_urls = merged_report['url'].unique().tolist()
    target_ciks = merged_report['cik'].unique().tolist()
    
    print(f"   Identified {len(merged_report)} reports and {len(target_urls)} URLs to transfer.")

    # Filter names
    merged_names = df_names[df_names['cik'].isin(target_ciks)]

    # Fetch webpage_result for these URLs (Chunked to avoid SQL limits)
    print("🔍 Fetching webpage_result data...")
    webpage_rows = []
    chunk_size = 900 
    
    cursor = src_conn.cursor()
    for i in range(0, len(target_urls), chunk_size):
        chunk = target_urls[i:i+chunk_size]
        placeholders = ','.join(['?'] * len(chunk))
        query = f"SELECT url, matches FROM webpage_result WHERE url IN ({placeholders})"
        cursor.execute(query, chunk)
        webpage_rows.extend(cursor.fetchall())
    
    src_conn.close()
    print(f"   Retrieved {len(webpage_rows)} webpage_result rows.")

    # 3. Create Target DB
    if Path(TARGET_DB).exists():
        print(f"⚠️  Removing existing {TARGET_DB}...")
        os.remove(TARGET_DB)
        
    print(f"🔨 Creating {TARGET_DB}...")
    tgt_conn = sqlite3.connect(TARGET_DB)
    tgt_cursor = tgt_conn.cursor()
    
    # Recreate Schema
    tgt_cursor.execute("CREATE TABLE IF NOT EXISTS report_data (cik INTEGER, year INTEGER, url TEXT)")
    tgt_cursor.execute("CREATE TABLE IF NOT EXISTS names (cik INTEGER, name TEXT)")
    tgt_cursor.execute("""
        CREATE TABLE IF NOT EXISTS webpage_result (
            url TEXT,
            matches TEXT,
            FOREIGN KEY (url) REFERENCES report_data(url)
        )
    """)
    tgt_cursor.execute("CREATE INDEX IF NOT EXISTS url_idx_report ON report_data (url)")
    tgt_cursor.execute("CREATE INDEX IF NOT EXISTS url_idx_webpage ON webpage_result (url)")
    tgt_cursor.execute("CREATE INDEX IF NOT EXISTS name_idx ON names (name)")

    # 4. Insert Data
    print("💾 Writing data to test.db...")
    merged_report.to_sql('report_data', tgt_conn, if_exists='append', index=False)
    merged_names.to_sql('names', tgt_conn, if_exists='append', index=False)
    tgt_cursor.executemany("INSERT INTO webpage_result (url, matches) VALUES (?, ?)", webpage_rows)
    
    tgt_conn.commit()
    tgt_conn.close()
    print("✅ Successfully created test.db!")

if __name__ == "__main__":
    create_test_db()