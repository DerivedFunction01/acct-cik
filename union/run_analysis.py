import sqlite3
import json
import re
import logging
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Tuple, Any, Set
from tqdm import tqdm

# Import definitions
from analysis import UnionAnalyzer

# =============================================================================
# CONFIGURATION
# =============================================================================
SOURCE_DB = "filtered_union_data.db"
TARGET_DB = "analyzed_union_data.db"
BATCH_SIZE = 100
CHUNK_SIZE = 10
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

def process_row(row: Tuple) -> Optional[Tuple]:
    """
    Process a single row.
    Row format: (accession, item1_json, item1a_json, home_country, item1_percents, item1a_percents, company_name, year)
    """
    try:
        accession, item1_json, item1a_json, home_country, item1_percents, item1a_percents, company_name, year = row
    except ValueError as e:
        logging.error(f"Error unpacking row: {e}")
        return None

    assert ANALYZER is not None

    # Set domestic country for this filing
    ANALYZER.domestic_country_code = home_country if home_country else "US"
    
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

    if item1a_json:
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
    
    return (
        accession,
        json.dumps(item1_analysis),
        json.dumps(item1a_analysis),
        str(year) if year else None,
        item1_percents,
        item1a_percents
    )

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

def data_generator(source_db: str, processed_accessions: Set[str], batch_size: int = BATCH_SIZE):
    """Yields rows from source database that haven't been processed."""
    conn = sqlite3.connect(source_db)
    c = conn.cursor()
    
    # Join to get metadata (Company Name, Year) for filtering context
    query = """
        SELECT w.accession, w.item1, w.item1a, w.home_country, w.item1_percents, w.item1a_percents, n.name, r.year
        FROM webpage_result w
        LEFT JOIN report_data r ON w.accession = r.accession
        LEFT JOIN names n ON r.cik = n.cik
    """
    
    c.execute(query)
    
    while True:
        rows = c.fetchmany(batch_size)
        if not rows:
            break
            
        for row in rows:
            if row[0] not in processed_accessions:
                yield row
                
    conn.close()

def flush_buffers(conn, buffer):
    """Writes a batch of results to the target database."""
    if not buffer:
        return
    
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        c.executemany(
            """
            INSERT OR REPLACE INTO analysis_result 
            (accession, item1_analysis, item1a_analysis, period_of_report, item1_percents, item1a_percents)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            buffer
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Write Error: {e}")
        conn.rollback()

if __name__ == "__main__":
    print(f"🚀 Starting Analysis ({NUM_WORKERS} workers)")
    
    # 1. Setup Target DB
    create_target_db()
    copy_metadata_tables()
    processed = get_processed_accessions(TARGET_DB)
    
    # 2. Connect Writer DB
    target_conn = sqlite3.connect(TARGET_DB, timeout=60.0)
    target_conn.execute("PRAGMA journal_mode=WAL")
    target_conn.execute("PRAGMA synchronous=NORMAL")
    
    # 3. Processing Loop
    buffer = []
    count = 0
    
    # Initialize worker pool with initializer
    with ProcessPoolExecutor(max_workers=NUM_WORKERS, initializer=init_worker) as executor:
        source_data = list(data_generator(SOURCE_DB, processed))
        
        # Map processing function
        results_iter = executor.map(process_row, source_data, chunksize=CHUNK_SIZE)
        
        for result in tqdm(results_iter, total=len(source_data), desc="Analyzing"):
            if result:
                buffer.append(result)
                count += 1
                
            if len(buffer) >= BATCH_SIZE:
                flush_buffers(target_conn, buffer)
                buffer = []
                    
    # 4. Final Flush
    if buffer:
        flush_buffers(target_conn, buffer)
        
    target_conn.close()
    print(f"✅ Complete. Processed {count} documents.")