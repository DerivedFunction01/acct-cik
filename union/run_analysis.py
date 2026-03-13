import sqlite3
import json
import re
import logging
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Tuple, Any, Set
from tqdm import tqdm
import pandas as pd
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
    ANALYZER.set_domestic_country_code(home_country or "US")
    
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
    if not item1_analysis:
        # Run minimal analysis to avoid hardcoding report JSON.
        item1_analysis = ANALYZER.analyze_paragraph(
            "", item_type="item1", reporting_year=year
        )

    # Process Item 1A
    item1a_analysis = {}
    
    # For really old filings, Item 1A doesn't exist. Do not reuse Item 1.
    # We'll emit a minimal analysis instead.
    if not item1a_json:
        item1a_json = None

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
    if not item1a_analysis:
        # Run minimal analysis to avoid hardcoding report JSON.
        item1a_analysis = ANALYZER.analyze_paragraph(
            "", item_type="item1a", reporting_year=year
        )
    
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

    logging.info("Copying metadata tables (report_data, names) from source DB...")
    src_conn = sqlite3.connect(SOURCE_DB, timeout=30.0)
    tgt_conn = sqlite3.connect(TARGET_DB, timeout=30.0)
    try:
        for table in ("report_data", "names"):
            try:
                df = pd.read_sql_query(f"SELECT * FROM {table}", src_conn)
            except Exception as e:
                logging.warning("Could not read %s from source DB: %s", table, e)
                continue

            if df.empty:
                logging.warning("%s is empty in source DB; skipping.", table)
                continue

            try:
                df.to_sql(table, tgt_conn, if_exists="replace", index=False)
                logging.info("Copied %s via dataframe (%s rows).", table, len(df))
            except Exception as e:
                logging.error("Failed to write %s to target DB: %s", table, e)

        tgt_conn.commit()
        src_conn.close()
        tgt_conn.close()
        return
    except Exception as e:
        logging.error("Pandas copy failed; falling back to SQL copy: %s", e)
        src_conn.close()
        tgt_conn.close()

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
