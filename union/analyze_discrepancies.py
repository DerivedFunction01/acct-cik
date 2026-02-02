import sqlite3
import pandas as pd
import logging
from pathlib import Path

# Configuration
DB_PATH = "analyzed_union_data.db"
TABLE_NAME = "union_summary"
OUTPUT_CSV = "union_discrepancies.csv"
THRESHOLD = 5.0  # Percentage points difference to flag (e.g., > 5.0% diff)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def analyze_discrepancies():
    if not Path(DB_PATH).exists():
        logging.error(f"Database {DB_PATH} not found. Run aggregate.py first.")
        return

    conn = sqlite3.connect(DB_PATH)
    
    # Check if table exists
    cursor = conn.cursor()
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_NAME}'")
    if not cursor.fetchone():
        logging.error(f"Table {TABLE_NAME} not found in database.")
        conn.close()
        return

    logging.info(f"Reading data from {TABLE_NAME}...")
    
    # Select relevant columns for comparison
    query = f"""
        SELECT 
            accession, 
            cik, 
            year, 
            period_of_report,
            union_rate, 
            secondary_rate, 
            pct_north_america, 
            pct_europe, 
            pct_asia, 
            pct_latam, 
            pct_mea, 
            pct_intl
        FROM {TABLE_NAME}
        WHERE union_rate IS NOT NULL 
          AND secondary_rate IS NOT NULL
    """
    
    try:
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        logging.error(f"Error reading data: {e}")
        conn.close()
        return

    conn.close()
    
    if df.empty:
        logging.info("No records found with both likely and weighted percentages populated.")
        return

    # Calculate absolute difference
    df['pct_diff'] = (df['union_rate'] - df['secondary_rate']).abs()
    
    # Flag records exceeding threshold
    flagged_df = df[df['pct_diff'] >= THRESHOLD].copy()
    
    # Sort by magnitude of difference
    flagged_df = flagged_df.sort_values('pct_diff', ascending=False)
    
    total_records = len(df)
    flagged_count = len(flagged_df)
    
    logging.info(f"Analyzed {total_records} records.")
    logging.info(f"Found {flagged_count} records ({flagged_count/total_records:.1%}) with discrepancy >= {THRESHOLD}%.")
    
    if not flagged_df.empty:
        # Display top discrepancies
        print("\nTop 10 Discrepancies:")
        display_cols = ['cik', 'year', 'union_rate', 'secondary_rate', 'pct_diff']
        print(flagged_df[display_cols].head(10).to_string(index=False))
        
        # Save to CSV
        flagged_df.to_csv(OUTPUT_CSV, index=False)
        logging.info(f"\nFull discrepancy report saved to {OUTPUT_CSV}")
    else:
        logging.info("No significant discrepancies found.")

if __name__ == "__main__":
    analyze_discrepancies()