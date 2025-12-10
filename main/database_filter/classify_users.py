from pathlib import Path
import sqlite3
import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from tqdm import tqdm
from typing import Tuple, Dict, Set, Optional

# --- IMPORTS ---
from derivative_regex import (
    IR_REGEX, FX_REGEX, CP_REGEX, EQ_REGEX, CR_REGEX,
    IR_SOFT_REGEX, FX_SOFT_REGEX, CP_SOFT_REGEX, EQ_SOFT_REGEX, CR_SOFT_REGEX,
    SENTENCE_SPLIT_PATTERN, TRADING_VENUE_REGEX, BASE_REGEX,
)
from prefilter_database import is_sophisticated_content
from prefiltered_lib import MinimalTextCleaner, NoiseReason

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "evidence_data.db"
TARGET_DB_PATH = "classified_data.db"

# Tag Parsing
TAG_PARSER_STRICT = re.compile(r"^\s*(_[SD])<([^>]+)>\s+(.*)", re.DOTALL)

_cleaner = MinimalTextCleaner()


# =============================================================================
# GLOBAL INSTRUMENT TRACKER
# =============================================================================

class GlobalInstrumentTracker:
    """Tracks instrument → category mappings for resolving generic references."""

    def __init__(self):
        self.instrument_map = defaultdict(set)
        self.embedded_regex = re.compile(r"\bembedded\b", re.IGNORECASE)

    def register_paragraph(self, paragraph: str, category: str):
        """Register instruments found in paragraph to category."""
        if self.embedded_regex.search(paragraph):
            self.instrument_map["embedded"].add(category)

        # Specific matches (high confidence)
        specific_matches = [m.group(0) for m in BASE_REGEX.finditer(paragraph)]

        if specific_matches:
            for instr in specific_matches:
                match = BASE_REGEX.search(instr)
                if match:
                    token = match.group(0).lower().rstrip("s")
                    if token.startswith("hedg"):  # ignore hedge, it is too generic
                        continue
                    self.instrument_map[token].add(category)
        else:
            # Fallback: implicit context
            base_matches = BASE_REGEX.findall(paragraph)
            for instr in base_matches:
                instr = instr.lower()
                if instr.startswith("hedg"):
                    continue
                if not instr.endswith("s") and instr != "swap":
                    continue
                token = instr.rstrip("s")
                self.instrument_map[token].add(category)

    def resolve_instrument(self, sentence: str) -> Optional[str]:
        """Returns category if sentence contains unambiguous global instrument."""
        matches = BASE_REGEX.findall(sentence)
        if self.embedded_regex.search(sentence):
            matches.append("embedded")

        candidates = set()
        for m in matches:
            token = m.lower().rstrip("s")
            if token in self.instrument_map:
                candidates.update(self.instrument_map[token])

        if len(candidates) == 1:
            return list(candidates)[0]
        return None


# =============================================================================
# HELPERS
# =============================================================================

def parse_tags(text: str) -> Tuple[bool, Optional[str], str]:
    """
    Parse _D or _S tags from text.
    
    Returns:
        (is_deadweight, tag_reason, clean_text)
    """
    match = TAG_PARSER_STRICT.match(text)
    if match:
        tag_type = match.group(1)
        tag_reason = match.group(2)
        clean_text = match.group(3)
        
        is_deadweight = (tag_type == "_D")
        return is_deadweight, tag_reason, clean_text
    
    return False, None, text


def extract_categories(sentence: str) -> Set[str]:
    """
    Check which categories are mentioned in sentence.
    
    Priority: strict > soft
    For EQ: apply gating (sophisticated)
    
    Returns:
        Set of category strings: {"ir", "fx", "cp", "eq", "cr", "warr"}
    """
    cats = set()
    
    # STRICT MATCHES (highest confidence)
    if IR_REGEX.search(sentence):
        cats.add("ir")
    if FX_REGEX.search(sentence):
        cats.add("fx")
    if CP_REGEX.search(sentence):
        cats.add("cp")
    if CR_REGEX.search(sentence):
        cats.add("cr")
    if is_sophisticated_content(sentence):
        cats.add("warr")
    elif EQ_REGEX.search(sentence):
        cats.add("eq")
    
    # SOFT MATCHES (only if no strict match)
    # Safeguards already applied upstream in prefiltering stage
    if not cats:
        if IR_SOFT_REGEX.search(sentence):
            cats.add("ir")
        if FX_SOFT_REGEX.search(sentence):
            cats.add("fx")
        if CP_SOFT_REGEX.search(sentence):
            cats.add("cp")
        if CR_SOFT_REGEX.search(sentence):
            cats.add("cr")
        if is_sophisticated_content(sentence):
            cats.add("warr")
        elif EQ_SOFT_REGEX.search(sentence):
            cats.add("eq")
    
    return cats


def mine_attributes(tag_reason: Optional[str], attributes: Dict) -> None:
    """Extract user attributes from noise tags."""
    if not tag_reason:
        return
    
    if tag_reason == NoiseReason.TRADING.value:
        attributes["is_hedger"] = True
    elif tag_reason == NoiseReason.POLICY.value:
        attributes["uses_hedge_accounting"] = True
    elif tag_reason == NoiseReason.AOCI.value:
        attributes["has_pnl_activity"] = True
    elif tag_reason == NoiseReason.CREDIT.value:
        attributes["manages_credit_risk"] = True
    elif tag_reason in {NoiseReason.TIME.value, NoiseReason.TERM.value, NoiseReason.HIST_BLOCK.value}:
        attributes["is_historical"] = True


# =============================================================================
# MAIN PROCESSING
# =============================================================================

def process_row(row: Tuple) -> Tuple:
    """
    Process a single company document.
    
    Two-pass approach:
    1. Register ALL instrument mentions to tracker (including deadweight)
    2. Count categories from non-deadweight text only (using tracker for ambiguous cases)
    
    Returns:
        (url, categories_json, attributes_json, cik, year)
    """
    url, matches_json, cik, year = row
    
    try:
        paragraphs = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return (url, json.dumps([]), json.dumps({}), cik, year)
    
    if not isinstance(paragraphs, list):
        return (url, json.dumps([]), json.dumps({}), cik, year)
    
    # Initialize
    attributes = {
        "is_hedger": False,
        "uses_hedge_accounting": False,
        "has_pnl_activity": False,
        "manages_credit_risk": False,
        "is_historical": False,
        "is_trader": False,
    }
    mentions_venue = False
    tracker = GlobalInstrumentTracker()
    
    # --- PASS 1: Register ALL mentions to tracker, extract attributes ---
    for p in paragraphs:
        # Check for trading venue
        if TRADING_VENUE_REGEX.search(p):
            mentions_venue = True
        
        # Parse paragraph tag
        is_para_deadweight, para_tag_reason, para_content = parse_tags(p)
        
        # Mine paragraph-level attributes (even from deadweight)
        mine_attributes(para_tag_reason, attributes)
        
        # Split into sentences
        sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(para_content) if s.strip()
        ]
        
        for sent in sentences:
            # Parse sentence tag
            is_sent_deadweight, sent_tag_reason, sent_content = parse_tags(sent)
            
            # Mine sentence-level attributes (even from deadweight)
            mine_attributes(sent_tag_reason, attributes)
            
            # Clean for regex matching
            clean_sent = _cleaner.clean_entities(sent_content)
            
            # REGISTER TO TRACKER (from ALL text, including deadweight)
            # This builds the instrument map for later generic resolution
            if IR_REGEX.search(clean_sent):
                tracker.register_paragraph(clean_sent, "ir")
            if FX_REGEX.search(clean_sent):
                tracker.register_paragraph(clean_sent, "fx")
            if CP_REGEX.search(clean_sent):
                tracker.register_paragraph(clean_sent, "cp")
            if CR_REGEX.search(clean_sent):
                tracker.register_paragraph(clean_sent, "cr")
            if EQ_REGEX.search(clean_sent):
                if is_sophisticated_content(clean_sent):
                    tracker.register_paragraph(clean_sent, "warr")
                else:
                    tracker.register_paragraph(clean_sent, "eq")
    
    # --- PASS 2: Count categories from non-deadweight text ONLY ---
    categories_found = set()
    
    for p in paragraphs:
        # Parse paragraph tag
        is_para_deadweight, _, para_content = parse_tags(p)
        
        # Skip deadweight paragraphs for category counting
        if is_para_deadweight:
            continue
        
        # Split into sentences
        sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(para_content) if s.strip()
        ]
        
        for sent in sentences:
            # Parse sentence tag
            is_sent_deadweight, _, sent_content = parse_tags(sent)
            
            # Skip deadweight sentences for category counting
            if is_sent_deadweight:
                continue
            
            # Clean for regex matching
            clean_sent = _cleaner.clean_entities(sent_content)
            
            # Extract categories (strict > soft)
            cats = extract_categories(clean_sent)
            
            # If no direct match, try tracker resolution
            if not cats:
                tracker_cat = tracker.resolve_instrument(clean_sent)
                if tracker_cat:
                    cats.add(tracker_cat)
            
            categories_found.update(cats)
    
    # --- FINAL LOGIC: Determine is_trader ---
    # If mentions trading venue but NOT a hedger → trader
    if mentions_venue and not attributes["is_hedger"]:
        attributes["is_trader"] = True
    
    # --- OUTPUT ---
    final_categories = sorted(list(categories_found))
    
    return (
        url,
        json.dumps(final_categories),
        json.dumps(attributes),
        cik,
        year,
    )


# =============================================================================
# DATABASE
# =============================================================================

def setup_target_db(path: str) -> None:
    """Create target database schema."""
    conn = sqlite3.connect(path)
    c = conn.cursor()
    
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS webpage_result (
            url TEXT PRIMARY KEY,
            categories TEXT NOT NULL
        )
        """
    )
    
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS attributes (
            url TEXT PRIMARY KEY,
            attributes TEXT NOT NULL,
            FOREIGN KEY (url) REFERENCES webpage_result(url)
        )
        """
    )
    
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS report_data (
            url TEXT PRIMARY KEY,
            cik INTEGER,
            year INTEGER,
            FOREIGN KEY (url) REFERENCES webpage_result(url)
        )
        """
    )
    
    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
    c.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    conn.close()


def get_processed_urls(path: str) -> set:
    """Get URLs already processed."""
    if not Path(path).exists():
        return set()
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT url FROM webpage_result")}
    except:
        return set()
    finally:
        conn.close()


def data_generator(source_db: str, processed_urls: set, batch_size: int = BATCH_SIZE):
    """Stream unprocessed rows from source database."""
    conn = sqlite3.connect(source_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT w.url, w.matches, r.cik, r.year 
        FROM webpage_result w 
        LEFT JOIN report_data r ON w.url = r.url 
        WHERE w.matches IS NOT NULL
        """
    )
    
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        
        for row in rows:
            if row[0] not in processed_urls:
                yield row
    
    conn.close()


def write_batch(conn, buffer: list) -> None:
    """Write batch of results to database."""
    if not buffer:
        return
    
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        
        # Insert categories
        c.executemany(
            "INSERT OR IGNORE INTO webpage_result (url, categories) VALUES (?, ?)",
            [(r[0], r[1]) for r in buffer],
        )
        
        # Insert attributes
        c.executemany(
            "INSERT OR IGNORE INTO attributes (url, attributes) VALUES (?, ?)",
            [(r[0], r[2]) for r in buffer],
        )
        
        # Insert report data
        c.executemany(
            "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(r[0], r[3], r[4]) for r in buffer],
        )
        
        conn.commit()
    except Exception as e:
        print(f"❌ Write Error: {e}")
        conn.rollback()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print(f"🚀 Starting Classification ({NUM_WORKERS} workers)")
    
    setup_target_db(TARGET_DB_PATH)
    processed_urls = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed_urls)} already processed URLs")
    
    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    
    buffer = []
    
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        source = list(data_generator(SOURCE_DB_PATH, processed_urls))
        print(f"📦 Processing {len(source)} unprocessed URLs")
        
        for result in tqdm(
            executor.map(process_row, source, chunksize=50),
            total=len(source),
            desc="Classifying",
        ):
            if result:
                buffer.append(result)
                
                if len(buffer) >= BATCH_SIZE:
                    write_batch(conn, buffer)
                    buffer = []
    
    if buffer:
        write_batch(conn, buffer)
    
    conn.close()
    print("✅ Classification complete")