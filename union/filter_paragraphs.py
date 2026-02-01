import sqlite3
import json
import re
import logging
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from typing import List, Optional, Set, Tuple, Any
from tqdm import tqdm

# Import definitions
from defs.union_regex import UNION_REGEX, DYNAMIC_UNION_REGEX, RISK_REGEX
from defs.region_regex import (
    NORTH_AMERICA,
    EUROPE,
    ASIA_PACIFIC,
    LATIN_AMERICA,
    MIDDLE_EAST_AFRICA,
    INTERNATIONAL,
)
from defs.text_cleaner import MinimalTextCleaner, CurrencyRemover, ContextualNumberCleaner
from defs.table_processor import process_table
from defs.table_sentences import generate_primitive_sentences

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

TABLE_SPLIT_PATTERN = re.compile(r"(<TABLE>.*?</TABLE>)", re.DOTALL | re.IGNORECASE)

# =============================================================================
# REGEX COMPILATION
# =============================================================================

def strip_html_tags(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r'<[^>]+>', ' ', text)

def get_all_specific_terms() -> Set[str]:
    """Extracts all specific union names and translated keywords from defined regions."""
    regions = [
        NORTH_AMERICA,
        EUROPE,
        ASIA_PACIFIC,
        LATIN_AMERICA,
        MIDDLE_EAST_AFRICA,
        INTERNATIONAL,
    ]
    
    terms = set()
    for region in regions:
        for nation in region:
            # Add unions defined in the nation
            if nation.unions:
                terms.update(nation.unions)
            # Add translated keywords (e.g. "Huelga", "Grève")
            if nation.keywords:
                terms.update(nation.keywords)
                
    return terms

def compile_filtering_regex() -> re.Pattern:
    """
    Combines the generic UNION_REGEX with specific union names from regions.
    """
    # 1. Get generic pattern from union_regex.py
    generic_pattern = UNION_REGEX.pattern
    
    # 2. Get specific union names and keywords from region_regex.py
    specific_terms = get_all_specific_terms()
    
    if not specific_terms:
        return UNION_REGEX
        
    # Escape and sort by length (descending) to ensure longest match first
    # This prevents "UAW" matching inside "UAW-Ford" if that was a separate term, etc.
    sorted_terms = sorted(list(specific_terms), key=len, reverse=True)
    escaped_terms = [re.escape(u) for u in sorted_terms]
    
    # Create a pattern for specific unions/keywords
    # We use non-capturing group (?:...) joined by OR
    specific_pattern = r"(?:" + "|".join(escaped_terms) + r")"
    
    # Combine: (Generic)|(Specific)
    # Note: UNION_REGEX likely already has flags, but we re-compile with IGNORECASE
    combined_pattern = f"(?:{generic_pattern})|(?:{specific_pattern})"
    
    return re.compile(combined_pattern, re.IGNORECASE)

# Global regex for workers
FILTER_REGEX = None
CLEANER = None
CURRENCY_REMOVER = None
CONTEXTUAL_CLEANER = None

def init_worker():
    """Initializer for worker processes to compile regex once."""
    global FILTER_REGEX, CLEANER, CURRENCY_REMOVER, CONTEXTUAL_CLEANER
    FILTER_REGEX = compile_filtering_regex()
    CLEANER = MinimalTextCleaner()
    CURRENCY_REMOVER = CurrencyRemover()
    CONTEXTUAL_CLEANER = ContextualNumberCleaner()

def filter_content(content_list: List[str], company_name: Optional[str] = None, year: Optional[int] = None, allow_risk: bool = False) -> List[str]:
    """
    Filters a list of text blocks (paragraphs/tables).
    Cleans the text first, then checks for matches.
    Returns a list of CLEANED blocks that match the regex.
    """
    if not content_list:
        return []

    assert FILTER_REGEX is not None
    assert CLEANER is not None
    assert CURRENCY_REMOVER is not None
    assert CONTEXTUAL_CLEANER is not None

    # Flatten and split content
    raw_blocks = []
    for block in content_list:
        if not block:
            continue

        # Split by tables
        parts = TABLE_SPLIT_PATTERN.split(block)
        for part in parts:
            if not part.strip():
                continue

            # Check if it's a table (keep as one block)
            if part.strip().lower().startswith("<table"):
                try:
                    processed = process_table(part.strip())
                    sentences = generate_primitive_sentences(processed)
                    if sentences:
                        paragraph = " ".join(sentences)
                        raw_blocks.append(paragraph)
                    else:
                        raw_blocks.append(strip_html_tags(part.strip()))
                except Exception:
                    raw_blocks.append(strip_html_tags(part.strip()))

            else:
                # Split text by double newlines
                lines = part.split('\n\n')
                for line in lines:
                    if line.strip():
                        raw_blocks.append(line.strip())

    filtered = []
    for block in raw_blocks:

        # Clean the text to remove false positives (e.g. "Credit Union")
        # and normalize company names
        cleaned_block = CLEANER.clean(
            block, 
            company_name=company_name, 
            reporting_year=year
        )

        # Remove currency figures to avoid confusion with employee counts
        cleaned_block = CURRENCY_REMOVER.clean(cleaned_block)

        # Remove non-employee numerics (facilities, growth rates)
        cleaned_block = CONTEXTUAL_CLEANER.clean(cleaned_block)

        # Normalize whitespace
        cleaned_block = " ".join(cleaned_block.split())

        if not cleaned_block:
            continue

        is_match = FILTER_REGEX.search(cleaned_block) or DYNAMIC_UNION_REGEX.search(cleaned_block)

        if not is_match and allow_risk:
            is_match = RISK_REGEX.search(cleaned_block)

        if is_match:
            filtered.append(cleaned_block)

    return filtered

def process_batch(rows: List[Tuple]) -> List[Tuple]:
    """
    Process a batch of rows.
    Row format: (accession, item1_json, item1a_json, period_of_report, company_name, report_year)
    """
    results = []
    for row in rows:
        accession, item1_json, item1a_json, period, company_name, report_year = row
        
        # Determine year for cleaner
        year = None
        if report_year:
            year = int(report_year)
        elif period:
             # Try to extract year from period string
            m = re.search(r'\d{4}', str(period))
            if m:
                year = int(m.group(0))
        
        try:
            item1_list = json.loads(item1_json) if item1_json else []
            item1a_list = json.loads(item1a_json) if item1a_json else []
        except json.JSONDecodeError:
            continue
            
        filtered_item1 = filter_content(item1_list, company_name, year, allow_risk=False)
        filtered_item1a = filter_content(item1a_list, company_name, year, allow_risk=True)
        
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
    
    # Update query to join with report_data and names
    # We use GROUP BY accession to handle potential duplicates in metadata tables
    query = """
        SELECT w.accession, w.item1, w.item1a, w.period_of_report, n.name, r.year
        FROM webpage_result w
        LEFT JOIN report_data r ON w.accession = r.accession
        LEFT JOIN names n ON r.cik = n.cik
        GROUP BY w.accession
    """
    src_cursor.execute(query)
    
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
