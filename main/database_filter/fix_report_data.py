import pandas as pd
import sqlite3
import re
import json
import os
import sys

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "web_data.db"
REPORT_CSV_PATH = "report_data.csv"
OUTPUT_CSV_PATH = "report_data_fixed.csv"

def get_accession(url):
    """
    Extract accession number from SEC URL.
    Handles standard SEC archive formats:
    .../data/CIK/ACCESSION/document.txt
    .../data/CIK/ACCESSION/index.htm
    """
    if not isinstance(url, str):
        return None
    # Regex to capture the accession folder. 
    # SEC URLs are typically: https://www.sec.gov/Archives/edgar/data/12345/000123456712345678/doc.txt
    # The accession folder usually does not have hyphens in the URL path for 'data' structure,
    # but sometimes might. We capture digits and hyphens.
    match = re.search(r'data/\d+/([\d-]+)/', url)
    if match:
        # Standardize by removing hyphens (accession is unique sequence of digits)
        return match.group(1).replace('-', '')
    return None

def has_valid_content(matches_json):
    """
    Check if the matches JSON string contains actual data.
    Returns True if it's a non-empty list.
    """
    if not matches_json:
        return False
    try:
        data = json.loads(matches_json)
        if isinstance(data, list) and len(data) > 0:
            return True
        return False
    except (json.JSONDecodeError, TypeError):
        return False

def extract_cik_from_url(url):
    """Fallback to extract CIK from URL if not found in CSV."""
    if not isinstance(url, str):
        return None
    match = re.search(r'data/(\d+)/', url)
    if match:
        return int(match.group(1))
    return None

def find_orphans():
    # 1. Load Report CSV (Source of Truth for Metadata)
    if not os.path.exists(REPORT_CSV_PATH):
        print(f"Error: {REPORT_CSV_PATH} not found.")
        return

    print(f"Reading {REPORT_CSV_PATH}...")
    df_csv = pd.read_csv(REPORT_CSV_PATH)

    # Extract accession for mapping
    df_csv['accession'] = df_csv['url'].apply(get_accession)

    # Create lookup: Accession -> {cik, year}
    # We drop duplicates to ensure 1:1 mapping.
    meta_lookup = df_csv.dropna(subset=['accession']).drop_duplicates('accession').set_index('accession')[['cik', 'year']].to_dict('index')

    print(f"Loaded metadata for {len(meta_lookup)} unique accessions.")

    # 2. Load Database Results
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return

    print(f"Reading {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    try:
        df_db = pd.read_sql("SELECT url, matches FROM webpage_result", conn)
    except Exception as e:
        print(f"Error reading database: {e}")
        conn.close()
        return
    conn.close()

    df_db['accession'] = df_db['url'].apply(get_accession)
    df_db['has_content'] = df_db['matches'].apply(has_valid_content)

    print(f"DB Total Rows: {len(df_db)}")

    # Split DB into Content vs Empty
    df_content = df_db[df_db['has_content']].copy()
    df_empty = df_db[~df_db['has_content']].copy()

    print(f"  With Content: {len(df_content)}")
    print(f"  Empty: {len(df_empty)}")

    final_rows = []
    processed_accessions = set()

    # =========================================================================
    # Step 1 & 2: Process Non-Empty Matches
    # =========================================================================
    # Strategy: Keep ALL content matches.
    # Map to CIK/Year using Accession from CSV.

    print("Processing content matches...")
    for _, row in df_content.iterrows():
        acc = row['accession']
        url = row['url']

        cik = None
        year = None

        if acc in meta_lookup:
            cik = meta_lookup[acc]['cik']
            year = meta_lookup[acc]['year']
        else:
            # Orphaned content (not in CSV). Try to recover CIK from URL.
            cik = extract_cik_from_url(url)
            # Year remains None/0

        final_rows.append({
            'cik': cik,
            'year': year,
            'url': url
        })
        if acc:
            processed_accessions.add(acc)

    # =========================================================================
    # Step 3: Process Empty Matches (Deduplication)
    # =========================================================================
    # Strategy: For accessions NOT yet processed (i.e., no content found),
    # pick ONE URL to keep. Prefer the one that matches the original CSV URL.

    print("Processing empty matches...")

    # Filter to relevant empty rows (accessions not in content)
    df_empty_relevant = df_empty[~df_empty['accession'].isin(processed_accessions)].copy()

    # Mark rows that are in original CSV to prioritize them
    original_urls = set(df_csv['url'])
    df_empty_relevant['is_original'] = df_empty_relevant['url'].isin(original_urls)

    # Sort: Original first, then arbitrary
    df_empty_relevant.sort_values(['accession', 'is_original'], ascending=[True, False], inplace=True)

    # Deduplicate: Keep first row per accession
    df_empty_dedup = df_empty_relevant.drop_duplicates(subset=['accession'])

    for _, row in df_empty_dedup.iterrows():
        acc = row['accession']
        url = row['url']

        cik = None
        year = None

        if acc in meta_lookup:
            cik = meta_lookup[acc]['cik']
            year = meta_lookup[acc]['year']
        else:
            cik = extract_cik_from_url(url)

        final_rows.append({
            'cik': cik,
            'year': year,
            'url': url
        })
        if acc:
            processed_accessions.add(acc)

    # =========================================================================
    # Step 4: Add Unprocessed Rows from CSV
    # =========================================================================
    # Strategy: Add rows from CSV that are not in DB at all (by accession).

    print("Adding unprocessed rows from CSV...")

    # Filter CSV rows where accession is not in processed_accessions
    df_csv_unprocessed = df_csv[~df_csv['accession'].isin(processed_accessions)]

    for _, row in df_csv_unprocessed.iterrows():
        final_rows.append({
            'cik': row['cik'],
            'year': row['year'],
            'url': row['url']
        })

    # =========================================================================
    # Finalize and Save
    # =========================================================================
    df_final = pd.DataFrame(final_rows)

    # Clean up data types
    df_final['cik'] = pd.to_numeric(df_final['cik'], errors='coerce').fillna(0).astype(int)
    df_final['year'] = pd.to_numeric(df_final['year'], errors='coerce').fillna(0).astype(int)

    # Remove duplicates on URL just in case
    df_final = df_final.drop_duplicates('url')

    print(f"Saving {len(df_final)} rows to {OUTPUT_CSV_PATH}...")
    df_final.to_csv(OUTPUT_CSV_PATH, index=False)
    print("Done.")


# =============================================================================
# CONFIGURATION
# =============================================================================
FIXED_CSV_PATH = "report_data_fixed.csv"


def clean_db():
    # 1. Validation
    if not os.path.exists(FIXED_CSV_PATH):
        print(f"❌ Error: {FIXED_CSV_PATH} not found.")
        print("   Please run fix_report_csv.py first to generate the ground truth.")
        return

    if not os.path.exists(DB_PATH):
        print(f"❌ Error: {DB_PATH} not found.")
        return

    # 2. Load Ground Truth
    print(f"📖 Loading {FIXED_CSV_PATH}...")
    df = pd.read_csv(FIXED_CSV_PATH)

    if "url" not in df.columns:
        print("❌ Error: CSV missing 'url' column.")
        return

    valid_urls = set(df["url"].dropna().unique())
    print(f"   Found {len(valid_urls):,} valid unique URLs in CSV.")

    # 3. Connect to DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Get initial counts
        cursor.execute("SELECT COUNT(*) FROM webpage_result")
        count_webpage_before = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM report_data")
        count_report_before = cursor.fetchone()[0]

        print(f"\n📊 Initial DB Counts:")
        print(f"   webpage_result: {count_webpage_before:,}")
        print(f"   report_data:    {count_report_before:,}")

        # 4. Create Temporary Table for Filtering
        # This is much faster and safer than passing a huge list to IN (...)
        print("\n⚙️  Creating temporary filter table...")
        cursor.execute("CREATE TEMP TABLE valid_urls_temp (url TEXT PRIMARY KEY)")

        # Batch insert valid URLs
        cursor.executemany(
            "INSERT OR IGNORE INTO valid_urls_temp (url) VALUES (?)",
            [(u,) for u in valid_urls],
        )

        # 5. Delete Invalid Rows (The Cleanup)
        print("🧹 Cleaning 'webpage_result' table...")
        cursor.execute(
            """
            DELETE FROM webpage_result 
            WHERE url NOT IN (SELECT url FROM valid_urls_temp)
        """
        )
        deleted_webpage = cursor.rowcount
        print(f"   -> Removed {deleted_webpage:,} rows.")

        print("🧹 Cleaning 'report_data' table...")
        cursor.execute(
            """
            DELETE FROM report_data 
            WHERE url NOT IN (SELECT url FROM valid_urls_temp)
        """
        )
        deleted_report = cursor.rowcount
        print(f"   -> Removed {deleted_report:,} rows.")

        # 6. Commit and Vacuum
        conn.commit()

        print("\n🧽 Vacuuming database to reclaim space...")
        cursor.execute("VACUUM")

        # Final counts
        cursor.execute("SELECT COUNT(*) FROM webpage_result")
        count_webpage_after = cursor.fetchone()[0]

        print(f"\n✅ Cleanup Complete.")
        print(f"   webpage_result: {count_webpage_after:,} (Valid)")
        print(f"   Total removed:  {deleted_webpage + deleted_report:,} rows")

    except Exception as e:
        print(f"❌ Database Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    find_orphans()
    clean_db()
