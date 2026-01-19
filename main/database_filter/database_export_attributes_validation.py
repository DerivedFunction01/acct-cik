"""
Export script to create Excel file with Attributes for validation firms.
Filters the database for CIK/Year pairs present in data_check.csv (or specified ground truth).
Exports URL and raw JSON attributes.
"""

import pandas as pd
import sqlite3
import sys
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_DB_PATH = "classified_data.db"
DEFAULT_GROUND_TRUTH = "data_check.csv"
DEFAULT_OUTPUT = "analysis_output/attributes_validation.xlsx"

def export_attributes(db_path=None, gt_path=None, out_path=None):
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if gt_path is None:
        gt_path = DEFAULT_GROUND_TRUTH
    if out_path is None:
        out_path = DEFAULT_OUTPUT

    db_file = Path(db_path)
    gt_file = Path(gt_path)
    out_file = Path(out_path)

    # 1. Validation
    if not db_file.exists():
        print(f"❌ Database not found: {db_file}")
        return
    if not gt_file.exists():
        print(f"❌ Ground truth file not found: {gt_file}")
        print("   (This file is needed to select which firms to export)")
        return

    print(f"📂 Loading ground truth from {gt_file}...")
    try:
        gt_df = pd.read_csv(gt_file)
        # Normalize keys
        gt_df['cik'] = pd.to_numeric(gt_df['cik'], errors='coerce').fillna(0).astype(int)
        gt_df['year'] = pd.to_numeric(gt_df['year'], errors='coerce').fillna(0).astype(int)
        
        # Get unique pairs
        target_keys = gt_df[['cik', 'year']].drop_duplicates()
        print(f"   Found {len(target_keys)} unique CIK/Year pairs to fetch.")
    except Exception as e:
        print(f"❌ Error reading ground truth: {e}")
        return

    # 2. Fetch from DB
    print(f"🔄 Querying database {db_file}...")
    conn = sqlite3.connect(db_file)
    try:
        # We fetch report_data to link CIK/Year to URL, and attributes for the JSON
        query = """
            SELECT r.cik, r.year, r.url, a.attributes
            FROM report_data r
            JOIN attributes a ON r.url = a.url
        """
        db_df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"❌ Database error: {e}")
        conn.close()
        return
    finally:
        conn.close()

    # Normalize DB keys
    db_df['cik'] = pd.to_numeric(db_df['cik'], errors='coerce').fillna(0).astype(int)
    db_df['year'] = pd.to_numeric(db_df['year'], errors='coerce').fillna(0).astype(int)

    # 3. Merge/Filter
    print("🔍 Filtering records...")
    merged_df = target_keys.merge(db_df, on=['cik', 'year'], how='inner')

    if merged_df.empty:
        print("⚠️  No matching records found in the database for the provided CIK/Year pairs.")
        return

    print(f"   Matched {len(merged_df)} records.")

    # 4. Export
    out_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"💾 Saving to {out_file}...")
    
    try:
        merged_df.to_excel(out_file, index=False)
        print("✅ Done!")
    except Exception as e:
        print(f"❌ Error saving Excel file: {e}")

if __name__ == "__main__":
    # Simple CLI: python script.py [db_path] [gt_path] [out_path]
    args = sys.argv[1:]
    db = args[0] if len(args) > 0 else None
    gt = args[1] if len(args) > 1 else None
    out = args[2] if len(args) > 2 else None
    
    export_attributes(db, gt, out)