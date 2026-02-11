import sqlite3
import json
import re
import logging
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Tuple, Any
from tqdm import tqdm

# Import definitions
from analysis import UnionAnalyzer

# =============================================================================
# CONFIGURATION
# =============================================================================
SOURCE_DB = "filtered_union_data.db"
TARGET_DB = "analyzed_union_data.db"
BATCH_SIZE = 100
NUM_WORKERS = max(1, multiprocessing.cpu_count() - 1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# =============================================================================
# WORKER INITIALIZATION
# =============================================================================

# Global analyzer instance for workers
ANALYZER = None

def init_worker():
    """Initializer for worker processes."""
    global ANALYZER
    ANALYZER = UnionAnalyzer()

def process_batch(rows: List[Tuple]) -> List[Tuple]:
    """
    Process a batch of rows.
    Row format: (accession, item1_json, item1a_json, period_of_report, home_country, company_name, report_year, item1_percents, item1a_percents)
    """
    results = []
    assert ANALYZER is not None

    for row in rows:
        accession, item1_json, item1a_json, period, home_country, company_name, report_year, item1_percents, item1a_percents = row
        
        # Set domestic country for this filing
        ANALYZER.domestic_country_code = home_country if home_country else "US"
        
        # Determine year
        year = None
        if report_year:
            try:
                year = int(report_year)
            except (ValueError, TypeError):
                pass
        elif period:
             # Try to extract year from period string
            m = re.search(r'\d{4}', str(period))
            if m:
                year = int(m.group(0))
        
        # Process Item 1
        item1_analysis = {}
        if item1_json:
            try:
                item1_list = json.loads(item1_json)
                if item1_list:
                    # Rejoin text by double new lines
                    item1_text = "\n\n".join(item1_list)
                    item1_analysis = ANALYZER.analyze_paragraph(
                        item1_text, 
                        item_type="item1", 
                        reporting_year=year
                    )
            except json.JSONDecodeError:
                pass

        # Process Item 1A
        item1a_analysis = {}
        
        # For really old filings, Item 1A doesn't exist. So we use the Item 1.
        if not item1a_json:
            item1a_json = item1_json
        try:
            item1a_list = json.loads(item1a_json)
            if item1a_list:
                # Rejoin text by double new lines
                item1a_text = "\n\n".join(item1a_list)
                item1a_analysis = ANALYZER.analyze_paragraph(
                    item1a_text, 
                    item_type="item1a", 
                    reporting_year=year
                )
        except json.JSONDecodeError:
            pass
        
        # Store the result, even when empty (allows cases where the text is empty)
        results.append((
            accession,
            json.dumps(item1_analysis),
            json.dumps(item1a_analysis),
            period,
            item1_percents,
            item1a_percents
        ))
            
    return results

def create_target_db():
    conn = sqlite3.connect(TARGET_DB, timeout=30.0)
    c = conn.cursor()
    # Enable WAL mode for better concurrency
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("DROP TABLE IF EXISTS analysis_result")
    c.execute("""
        CREATE TABLE IF NOT EXISTS analysis_result (
            accession TEXT PRIMARY KEY,
            item1_analysis TEXT,
            item1a_analysis TEXT,
            period_of_report TEXT,
            item1_percents TEXT,
            item1a_percents TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_accession ON analysis_result(accession)")
    conn.commit()
    conn.close()

def copy_metadata_tables():
    """Copies report_data and names tables from source to target DB."""
    if not Path(SOURCE_DB).exists():
        return

    conn = sqlite3.connect(TARGET_DB, timeout=30.0)
    c = conn.cursor()
    
    # Check if report_data already exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='report_data'")
    if c.fetchone():
        logging.info("report_data table already exists in target DB. Skipping copy.")
        conn.close()
        return

    logging.info("Copying metadata tables (report_data, names) from source DB...")
    
    try:
        # Attach source database
        c.execute("ATTACH DATABASE ? AS src", (SOURCE_DB,))
        
        # Copy report_data
        c.execute("CREATE TABLE report_data AS SELECT * FROM src.report_data")
        c.execute("CREATE INDEX IF NOT EXISTS idx_report_accession ON report_data(accession)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_report_url ON report_data(url)")
        
        # Copy names if exists
        c.execute("SELECT name FROM src.sqlite_master WHERE type='table' AND name='names'")
        if c.fetchone():
            c.execute("CREATE TABLE names AS SELECT * FROM src.names")
            c.execute("CREATE INDEX IF NOT EXISTS idx_names_cik ON names(cik)")
            
        conn.commit()
        logging.info("Metadata tables copied successfully.")
        
    except sqlite3.Error as e:
        logging.error(f"Error copying metadata: {e}")
    finally:
        try:
            c.execute("DETACH DATABASE src")
        except sqlite3.Error:
            pass
        conn.close()

def get_processed_accessions(target_db: str) -> set:
    """Get all accessions already processed in target DB."""
    if not Path(target_db).exists():
        return set()
    
    try:
        conn = sqlite3.connect(target_db, timeout=30.0)
        c = conn.cursor()
        c.execute("SELECT accession FROM analysis_result")
        processed = {row[0] for row in c.fetchall()}
        conn.close()
        logging.info(f"Found {len(processed)} already processed accessions")
        return processed
    except sqlite3.OperationalError:
        logging.info("Target DB not initialized yet")
        return set()