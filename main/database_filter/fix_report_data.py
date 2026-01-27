"""
Script to reconcile URLs in webpage_result with report_data.
Handles cases where webpage.py modified the URL (e.g. to .txt) by matching Accession Numbers.
Outputs:
    - fixed_report_data.csv: Matched records with correct CIK/Year and the actual URL from webpage_result.
    - leftover_report_data.csv: Records from report_data that were not found in webpage_result.
"""

import sqlite3
import pandas as pd
import re
from pathlib import Path

# Configuration
DB_PATH = "web_data.db"
FIXED_CSV = "fixed_report_data.csv"
LEFTOVER_CSV = "leftover_report_data.csv"

def extract_accession(url):
    """
    Extracts the 18-digit accession number from an EDGAR URL.
    Example: .../data/123456/000012345612345678/doc.txt -> 000012345612345678
    """
    if not isinstance(url, str) or not url:
        return None
    
    # Split by slash and look for the 18-digit part
    parts = url.split('/')
    for part in parts:
        if len(part) == 18 and part.isdigit():
            return part
    return None

def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database {DB_PATH} not found.")
        return

    print(f"📂 Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    
    # --- PHASE 1: EXACT URL MATCHING (SQL) ---
    print("\n🔍 Phase 1: Exact URL matching (SQL)...")
    
    # 1. Get exact matches directly via SQL JOIN
    # This is much faster than loading everything into Python
    query_exact = """
        SELECT r.cik, r.year, w.url 
        FROM webpage_result w 
        JOIN report_data r ON w.url = r.url
    """
    try:
        fixed_df_exact = pd.read_sql(query_exact, conn)
        print(f"   Exact matches found: {len(fixed_df_exact)}")
    except Exception as e:
        print(f"❌ Error in Phase 1: {e}")
        conn.close()
        return

    # --- PHASE 2: PREPARE FOR ACCESSION MATCHING ---
    print("\n🔍 Phase 2: Accession number matching...")

    # 2. Get Orphans: URLs in webpage_result that are NOT in report_data
    # These are the URLs that were modified (e.g. .htm -> .txt)
    query_orphans = """
        SELECT url 
        FROM webpage_result 
        WHERE url NOT IN (SELECT url FROM report_data)
    """
    try:
        orphans_df = pd.read_sql(query_orphans, conn)
        orphans = orphans_df['url'].tolist()
        print(f"   Orphaned URLs (modified/mismatched): {len(orphans)}")
    except Exception as e:
        print(f"❌ Error getting orphans: {e}")
        conn.close()
        return

    # 3. Get Potential Leftovers: Rows in report_data that are NOT in webpage_result
    # These are the candidates we try to match against the orphans
    query_leftovers = """
        SELECT cik, year, url 
        FROM report_data 
        WHERE url NOT IN (SELECT url FROM webpage_result)
    """
    try:
        leftovers_df = pd.read_sql(query_leftovers, conn)
        print(f"   Unmatched report_data rows: {len(leftovers_df)}")
    except Exception as e:
        print(f"❌ Error getting leftovers: {e}")
        conn.close()
        return

    conn.close()

    # --- PHASE 3: PERFORM ACCESSION MATCHING IN PYTHON ---
    
    # Add accession column to leftovers for fast lookup
    leftovers_df['accession'] = leftovers_df['url'].apply(extract_accession)
    
    # Create a map: Accession -> List of indices in leftovers_df
    acc_to_indices = {}
    for idx, row in leftovers_df.iterrows():
        acc = row['accession']
        if acc:
            if acc not in acc_to_indices:
                acc_to_indices[acc] = []
            acc_to_indices[acc].append(idx)
            
    fixed_rows_acc = []
    matched_indices = set()
    
    for w_url in orphans:
        acc = extract_accession(w_url)
        if acc and acc in acc_to_indices and acc_to_indices[acc]:
            # Match found via Accession. Consume one instance.
            idx = acc_to_indices[acc].pop(0)
            matched_indices.add(idx)
            
            row = leftovers_df.loc[idx]
            fixed_rows_acc.append({
                'cik': row['cik'], 
                'year': row['year'], 
                'url': w_url  # Use the actual processed URL from webpage_result
            })
            
            # Clean up map if empty
            if not acc_to_indices[acc]:
                del acc_to_indices[acc]
            
    print(f"   Matched via Accession: {len(fixed_rows_acc)}")
    
    # --- OUTPUT GENERATION ---
    
    # 1. Fixed Data (Exact Matches + Accession Matches)
    if fixed_rows_acc:
        fixed_df_acc = pd.DataFrame(fixed_rows_acc)
        final_fixed = pd.concat([fixed_df_exact, fixed_df_acc], ignore_index=True)
    else:
        final_fixed = fixed_df_exact

    if not final_fixed.empty:
        # Ensure integer types for CIK/Year
        final_fixed['cik'] = pd.to_numeric(final_fixed['cik'], errors='coerce').fillna(0).astype(int)
        final_fixed['year'] = pd.to_numeric(final_fixed['year'], errors='coerce').fillna(0).astype(int)
        final_fixed = final_fixed[['cik', 'year', 'url']]
    else:
        final_fixed = pd.DataFrame(columns=['cik', 'year', 'url'])
        
    final_fixed.to_csv(FIXED_CSV, index=False)
    print(f"\n✅ Saved {len(final_fixed)} rows to {FIXED_CSV}")
    
    # 2. Leftover Data (Original Leftovers - Matched Accessions)
    final_leftovers = leftovers_df.drop(index=list(matched_indices))
    final_leftovers = final_leftovers.drop(columns=['accession']) # Clean up temp col
    
    if not final_leftovers.empty:
        final_leftovers['cik'] = pd.to_numeric(final_leftovers['cik'], errors='coerce').fillna(0).astype(int)
        final_leftovers['year'] = pd.to_numeric(final_leftovers['year'], errors='coerce').fillna(0).astype(int)
    else:
        final_leftovers = pd.DataFrame(columns=['cik', 'year', 'url'])

    final_leftovers.to_csv(LEFTOVER_CSV, index=False)
    print(f"✅ Saved {len(final_leftovers)} rows to {LEFTOVER_CSV}")

if __name__ == "__main__":
    main()