import sqlite3
import json
import re
import logging
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Set, Tuple, Any
from tqdm import tqdm

# Import definitions
from defs.union_regex import EXCLUSION_REGEX, UNION_REGEX, DYNAMIC_UNION_REGEX, RISK_REGEX
from defs.region_regex import (
    NORTH_AMERICA,
    EUROPE,
    ASIA_PACIFIC,
    LATIN_AMERICA,
    MIDDLE_EAST_AFRICA,
    INTERNATIONAL,
)
from defs.text_cleaner import MinimalTextCleaner, CurrencyRemover, ContextualNumberCleaner, ConcisenessCleaner
from defs.table_processor import TABLE_TOK, process_table
from defs.table_sentences import generate_primitive_sentences
from defs.regex_lib import SENTENCE_SPLIT_PATTERN, build_regex
from extraction import UnionExtractor

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
RAW_PERCENT_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)

# Regex to find the pattern: Period + Space + (ALL CAPS HEADER) + Space + (Capitalized Word not No.)
MEGA_SPLIT_REGEX = re.compile(r"(\.\s+)([A-Z][A-Z\s]+)(?=\s+(?!No\.)[A-Z][a-z])")

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
    Compiles a case-sensitive regex for specific union names and keywords from regions.
    The generic UNION_REGEX (with its own flags) is used separately in filter_content.
    """
    # Get specific union names and keywords from region_regex.py
    specific_terms = get_all_specific_terms()
    
    if not specific_terms:
        # Return an empty pattern that never matches
        return re.compile(r"(?!)")
        
    return build_regex(specific_terms, ignore_case=False)
    

# Global regex for workers
FILTER_REGEX = None
CLEANER = None
CURRENCY_REMOVER = None
CONTEXTUAL_CLEANER = None
CONCISENESS_CLEANER = None
EXTRACTOR = None

def init_worker():
    """Initializer for worker processes to compile regex once."""
    global FILTER_REGEX, CLEANER, CURRENCY_REMOVER, CONTEXTUAL_CLEANER, CONCISENESS_CLEANER, EXTRACTOR
    FILTER_REGEX = compile_filtering_regex()
    CLEANER = MinimalTextCleaner()
    CURRENCY_REMOVER = CurrencyRemover()
    CONTEXTUAL_CLEANER = ContextualNumberCleaner()
    CONCISENESS_CLEANER = ConcisenessCleaner()
    EXTRACTOR = UnionExtractor()

def split_mega_paragraph(paragraphs: List[str]) -> List[str]:
    # For plain text paragraph extraction, sometimes the text is merged accidentally, so we have a mega chunk
    # This is usually for pre-2000 SEC filings, where headers are all caps, etc
    """
     There may be certain rules to look out for as candidates for splitting:
     1. If the candidate paragraph is too large (> 1600 chars)
     
    """
    output = []
    def split_paragraph(p: str) -> List[str]:
        # Split the current text chunk based on some rules
        output = split_paragraph_simple(p)
        output = remove_caps(output)
        output = cleanup_loose_fragments(output)
        return output
    def remove_caps(paragraphs: List[str]) -> List[str]:
        # Strip out ALL CAPS artifact headers (Good for 90% of cases, no need for perfection)
        # 1. if it is a single word, it must be at least 5 chars long so that CFTC, SFAS doesn't count
        # 2. Any other cases, we delete consecutive occureances of all caps, such as TEXT CORP. (MORE TEXT AS A HEADER);
        # Bulleted patterns such as 1)/1. CAP HEADERS

        cleaned_paragraphs = []
        for p in paragraphs:            
            words = p.split()
            if not words:
                continue

            new_words = []
            caps_run = []

            def process_run(run):
                if not run: return []
                # Check if run should be removed
                if len(run) >= 2:
                    return [] # Remove
                elif len(run) == 1:
                    # Check length constraint
                    w = run[0]
                    if len(w) >= 5:
                        return [] # Remove
                    else:
                        return run
                return run

            for w in words:
                # Check if word is ALL CAPS (no lowercase)
                if w.isupper():
                    caps_run.append(w)
                else:
                    # End of run
                    if caps_run:
                        new_words.extend(process_run(caps_run))
                        caps_run = []
                    new_words.append(w)

            # Process final run
            if caps_run:
                new_words.extend(process_run(caps_run))

            # Reconstruct paragraph
            cleaned_p = " ".join(new_words)
            if cleaned_p.strip():
                cleaned_paragraphs.append(cleaned_p)

        return cleaned_paragraphs

    def cleanup_loose_fragments(paragraphs: List[str]) -> List[str]:
        # Clean up simple patterns, no need for massive rules here
        # Remove stray bullet double dash patterns --: ex: 1. --; 2. --
        output = []
        for p in paragraphs:
            p = re.sub(r"[0-9]\.\s+--", "", p)
            output.append(p)
        return output

    def split_paragraph_simple(p: str) -> List[str]:
        # Split the current text chunk based on some rules
        # 1. end of sentence. ALL CAPS Capitalized Word ->   support companies. PRINCIPLES OF CONSOLIDATION The accompanying

        # Insert a unique separator (e.g., \n\n) before the header
        p_new = MEGA_SPLIT_REGEX.sub(r"\1\n\n\2", p)

        return p_new.split("\n\n")

    for paragraph in paragraphs:
        # Split by tables first to protect them
        parts = TABLE_SPLIT_PATTERN.split(paragraph)
        for part in parts:
            if not part.strip():
                continue

            # If it is a table, preserve it as is
            if "<TABLE>" in part.upper():
                output.append(part)
                continue

            if len(part) > 1600:
                output.extend(split_paragraph(part))
            else:
                output.append(part)
    return output

def filter_content(content_list: List[str], company_name: Optional[str] = None, year: Optional[int] = None, allow_risk: bool = False) -> Tuple[List[str], List[float]]:
    """
    Filters a list of text blocks (paragraphs/tables).
    Cleans the text first, then checks for matches.
    Returns a tuple: (list of CLEANED blocks, list of raw percentages found in matched blocks).
    """
    if not content_list:
        return [], []

    assert FILTER_REGEX is not None
    assert CLEANER is not None
    assert CURRENCY_REMOVER is not None
    assert CONTEXTUAL_CLEANER is not None
    assert CONCISENESS_CLEANER is not None
    assert EXTRACTOR is not None

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
                        paragraph = f'{TABLE_TOK} {" ".join(sentences)}'
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

    # Apply mega paragraph splitting and cleanup
    raw_blocks = split_mega_paragraph(raw_blocks)

    filtered = []
    extracted_percents = []
    
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

        # Remove unnecessary words and simplify
        cleaned_block = CONCISENESS_CLEANER.clean(cleaned_block)

        # Normalize whitespace
        cleaned_block = " ".join(cleaned_block.split())

        if not cleaned_block or EXCLUSION_REGEX.search(cleaned_block):
            continue

        # Check generic union regex (case-insensitive), specific terms (case-sensitive), or dynamic regex
        is_match = UNION_REGEX.search(cleaned_block) or FILTER_REGEX.search(cleaned_block) or DYNAMIC_UNION_REGEX.search(cleaned_block)

        if not is_match and allow_risk:
            is_match = RISK_REGEX.search(cleaned_block)

        if is_match:
            filtered.append(cleaned_block)
            # Extract raw percents from the original block (before number normalization)
            for sent in SENTENCE_SPLIT_PATTERN.split(block):
                if UNION_REGEX.search(sent):
                    for m in RAW_PERCENT_REGEX.findall(sent):
                        try:
                            extracted_percents.append(float(m))
                        except ValueError:
                            pass

    return filtered, extracted_percents

def create_target_db():
    conn = sqlite3.connect(TARGET_DB, timeout=30.0)
    c = conn.cursor()
    # Enable WAL mode for better concurrency
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("DROP TABLE IF EXISTS webpage_result")
    # Replicate schema from webpage.py
    c.execute("""
        CREATE TABLE IF NOT EXISTS webpage_result (
            accession TEXT PRIMARY KEY,
            item1 TEXT,
            item1a TEXT,
            period_of_report TEXT,
            home_country TEXT,
            item1_percents TEXT,
            item1a_percents TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_accession ON webpage_result(accession)")
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

def get_processed_accessions(target_db: str) -> Set[str]:
    """Get all accessions already processed in target DB."""
    if not Path(target_db).exists():
        return set()
    
    try:
        conn = sqlite3.connect(target_db, timeout=30.0)
        c = conn.cursor()
        c.execute("SELECT accession FROM webpage_result")
        processed = {row[0] for row in c.fetchall()}
        conn.close()
        logging.info(f"Found {len(processed)} already processed accessions")
        return processed
    except sqlite3.OperationalError:
        logging.info("Target DB not initialized yet")
        return set()

# =============================================================================
# WORKER LOGIC
# =============================================================================

def process_row(row: Tuple) -> Optional[Tuple]:
    """
    Process a single row from the source database.
    Row: (accession, item1_json, item1a_json, period, home_country, company_name, year)
    """
    accession, item1_json, item1a_json, period, home_country, company_name, year = row
    
    # Parse inputs
    item1_list = []
    if item1_json:
        try:
            item1_list = json.loads(item1_json)
        except (json.JSONDecodeError, TypeError):
            pass
            
    item1a_list = []
    if item1a_json:
        try:
            item1a_list = json.loads(item1a_json)
        except (json.JSONDecodeError, TypeError):
            pass
            
    # Filter Content
    # Item 1: Business Description (Strict filtering, no risk terms)
    item1_filtered, item1_percents = filter_content(
        item1_list, 
        company_name=company_name, 
        year=year, 
        allow_risk=False
    )
    
    # Item 1A: Risk Factors (Allow risk terms like "strikes", "disputes")
    item1a_filtered, item1a_percents = filter_content(
        item1a_list, 
        company_name=company_name, 
        year=year, 
        allow_risk=True
    )
    
    return (
        accession,
        json.dumps(item1_filtered),
        json.dumps(item1a_filtered),
        period,
        home_country,
        json.dumps(item1_percents),
        json.dumps(item1a_percents)
    )

def data_generator(source_db: str, processed_accessions: Set[str], batch_size: int = BATCH_SIZE):
    """Yields rows from source database that haven't been processed."""
    conn = sqlite3.connect(source_db)
    c = conn.cursor()
    
    # Join to get metadata (Company Name, Year) for filtering context
    query = """
        SELECT w.accession, w.item1, w.item1a, w.period_of_report, w.home_country, n.name, r.year
        FROM webpage_result w
        LEFT JOIN report_data r ON w.accession = r.accession
        LEFT JOIN names n ON r.cik = n.cik
        WHERE w.item1 IS NOT NULL OR w.item1a IS NOT NULL
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
            INSERT OR REPLACE INTO webpage_result 
            (accession, item1, item1a, period_of_report, home_country, item1_percents, item1a_percents)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            buffer
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Write Error: {e}")
        conn.rollback()

# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print(f"🚀 Starting Paragraph Filter ({NUM_WORKERS} workers)")
    
    # 1. Setup Target DB
    create_target_db()
    copy_metadata_tables()
    processed = get_processed_accessions(TARGET_DB)
    print(f"📋 Found {len(processed)} processed accessions.")
    
    # 2. Connect Writer DB
    target_conn = sqlite3.connect(TARGET_DB, timeout=60.0)
    target_conn.execute("PRAGMA journal_mode=WAL")
    target_conn.execute("PRAGMA synchronous=NORMAL")
    
    # 3. Processing Loop
    buffer = []
    count = 0
    
    # Initialize worker pool with initializer to compile regexes
    with ProcessPoolExecutor(max_workers=NUM_WORKERS, initializer=init_worker) as executor:
        source_iter = data_generator(SOURCE_DB, processed)
        
        # Map processing function
        results_iter = executor.map(process_row, source_iter, chunksize=20)
        
        for result in tqdm(results_iter, desc="Filtering"):
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
