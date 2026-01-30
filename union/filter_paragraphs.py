import sqlite3
import json
import re
import logging
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from tqdm import tqdm

# Import definitions
from defs.union_regex import UNION_REGEX
from defs.region_regex import (
    NORTH_AMERICA,
    EUROPE,
    ASIA_PACIFIC,
    LATIN_AMERICA,
    MIDDLE_EAST_AFRICA,
    INTERNATIONAL,
)

# =============================================================================
# CONFIGURATION
# =============================================================================
SOURCE_DB = "web_data.db"
TARGET_DB = "filtered_union_data.db"
BATCH_SIZE = 500
NUM_WORKERS = max(1, multiprocessing.cpu_count() - 1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# =============================================================================
# REGEX COMPILATION
# =============================================================================

def get_all_specific_unions():
    """Extracts all specific union names from defined regions."""
    regions = [
        NORTH_AMERICA,
        EUROPE,
        ASIA_PACIFIC,
        LATIN_AMERICA,
        MIDDLE_EAST_AFRICA,
        INTERNATIONAL,
    ]
    
    union_names = set()
    for region in regions:
        for nation in region:
            # Add unions defined in the nation
            if nation.unions:
                union_names.update(nation.unions)
                
    return union_names

def compile_filtering_regex():
    """
    Combines the generic UNION_REGEX with specific union names from regions.
    """
    # 1. Get generic pattern from union_regex.py
    generic_pattern = UNION_REGEX.pattern
    
    # 2. Get specific union names from region_regex.py
    specific_unions = get_all_specific_unions()
    
    if not specific_unions:
        return UNION_REGEX
        
    # Escape and sort by length (descending) to ensure longest match first
    # This prevents "UAW" matching inside "UAW-Ford" if that was a separate term, etc.
    sorted_unions = sorted(list(specific_unions), key=len, reverse=True)
    escaped_unions = [re.escape(u) for u in sorted_unions]
    
    # Create a pattern for specific unions
    # We use non-capturing group (?:...) joined by OR
    specific_pattern = r"(?:" + "|".join(escaped_unions) + r")"
    
    # Combine: (Generic)|(Specific)
    # Note: UNION_REGEX likely already has flags, but we re-compile with IGNORECASE
    combined_pattern = f"(?:{generic_pattern})|(?:{specific_pattern})"
    
    return re.compile(combined_pattern, re.IGNORECASE)

# Global regex for workers
FILTER_REGEX = None

def init_worker():
    """Initializer for worker processes to compile regex once."""
    global FILTER_REGEX
    FILTER_REGEX = compile_filtering_regex()

def filter_content(content_list):
    """
    Filters a list of text blocks (paragraphs/tables).
    Returns a list of blocks that match the regex.
    """
    if not content_list:
        return []
        
    assert FILTER_REGEX is not None
    filtered = []
    for block in content_list:
        if not block:
            continue
        # Check for match
        # Note: Tables are passed as string blocks (converted in webpage.py).
        # If the regex matches anywhere in the table text, we keep the whole table.
        if FILTER_REGEX.search(block):
            filtered.append(block)
            
    return filtered

def process_batch(rows):
    """
    Process a batch of rows.
    Row format: (accession, item1_json, item1a_json, period_of_report)
    """
    results = []
    for row in rows:
        accession, item1_json, item1a_json, period = row
        
        try:
            item1_list = json.loads(item1_json) if item1_json else []
            item1a_list = json.loads(item1a_json) if item1a_json else []
        except json.JSONDecodeError:
            continue
            
        filtered_item1 = filter_content(item1_list)
        filtered_item1a = filter_content(item1a_list)
        
        # Only keep row if we have relevant content in either section
        if filtered_item1 or filtered_item1a:
            results.append((
                accession,
                json.dumps(filtered_item1),
                json.dumps(filtered_item1a),
                period
            ))
            
    return results

def create_target_db():
    conn = sqlite3.connect(TARGET_DB)
    c = conn.cursor()
    # Replicate schema from webpage.py
    c.execute("""
        CREATE TABLE IF NOT EXISTS webpage_result (
            accession TEXT PRIMARY KEY,
            item1 TEXT,
            item1a TEXT,
            period_of_report TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_accession ON webpage_result(accession)")
    conn.commit()
    conn.close()

def copy_metadata_tables():
    """Copies report_data and names tables from source to target DB."""
    if not Path(SOURCE_DB).exists():
        return

    conn = sqlite3.connect(TARGET_DB)
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

def main():
    if not Path(SOURCE_DB).exists():
        logging.error(f"Source database {SOURCE_DB} not found.")
        return

    create_target_db()
    copy_metadata_tables()
    
    src_conn = sqlite3.connect(SOURCE_DB)
    src_cursor = src_conn.cursor()
    
    # Get total count for progress bar
    try:
        src_cursor.execute("SELECT COUNT(*) FROM webpage_result")
        total_rows = src_cursor.fetchone()[0]
    except sqlite3.OperationalError:
        logging.error("Could not query webpage_result table. Is the DB initialized?")
        return

    logging.info(f"Total rows to process: {total_rows}")
    
    src_cursor.execute("SELECT accession, item1, item1a, period_of_report FROM webpage_result")
    
    with ProcessPoolExecutor(max_workers=NUM_WORKERS, initializer=init_worker) as executor:
        batch_futures = {} # {future: batch_size}
        
        def write_results(res_list):
            if not res_list:
                return
            tgt_conn = sqlite3.connect(TARGET_DB)
            tgt_c = tgt_conn.cursor()
            tgt_c.executemany(
                "INSERT OR REPLACE INTO webpage_result (accession, item1, item1a, period_of_report) VALUES (?, ?, ?, ?)",
                res_list
            )
            tgt_conn.commit()
            tgt_conn.close()

        with tqdm(total=total_rows, unit="rows") as pbar:
            while True:
                rows = src_cursor.fetchmany(BATCH_SIZE)
                if not rows:
                    break
                
                future = executor.submit(process_batch, rows)
                batch_futures[future] = len(rows)
                
                # Manage memory: if too many futures pending, wait for some to finish
                if len(batch_futures) >= NUM_WORKERS * 2:
                    done, _ = wait(batch_futures.keys(), return_when=FIRST_COMPLETED)
                    for f in done:
                        res = f.result()
                        write_results(res)
                        pbar.update(batch_futures[f])
                        del batch_futures[f]
            
            # Process remaining futures
            for f in list(batch_futures.keys()):
                res = f.result()
                write_results(res)
                pbar.update(batch_futures[f])

    src_conn.close()
    logging.info(f"Filtering complete. Data saved to {TARGET_DB}")

if __name__ == "__main__":
    main()