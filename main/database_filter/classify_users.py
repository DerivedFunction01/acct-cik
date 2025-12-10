from pathlib import Path
import sqlite3
import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from tqdm import tqdm
from typing import Tuple, Dict, Set, Optional, List

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
SOURCE_DB_PATH = "tagged_data.db"
TARGET_DB_PATH = "classified_data.db"

# Tag Parsing
TAG_PARSER_STRICT = re.compile(r"^\s*(_[SD])<([^>]+)>\s+(.*)", re.DOTALL)
EVIDENCE_TAG_PARSER = re.compile(r"_E<([^>]+)>")

# Evidence that elevates soft mentions to strict (unambiguous subject)
UNAMBIGUOUS_EVIDENCE = {
    "ACTIVE_STATE_YEAR",       # Strict subject + year
    "MATURITY_FUTURE",         # Strict subject + future
    "NOTIONAL_VALUE_YEAR",     # Strict subject + year
    "FAIR_VALUE_YEAR",         # Strict subject + year
    "TRANSACTION_YEAR",        # Strict subject + year
    "CONTINUOUS_USAGE",        # Strict subject (no year)
    "NOTIONAL_NO_YEAR",        # Strict subject, no year
    "FAIR_VALUE_NO_YEAR",      # Strict subject, no year
    "VALUATION_MODEL",         # Self-validating
    "BALANCE_SHEET_LOC",       # Self-validating
}

_cleaner = MinimalTextCleaner()

# =============================================================================
# GLOBAL INSTRUMENT TRACKER
# =============================================================================

class GlobalInstrumentTracker:
    """Tracks instrument → category mappings from strict mentions."""
    
    def __init__(self):
        self.instrument_map = defaultdict(set)
        self.embedded_regex = re.compile(r"\bembedded\b", re.IGNORECASE)
    
    def register_paragraph(self, sentence: str, category: str) -> None:
        """Register instruments found in sentence to category."""
        if self.embedded_regex.search(sentence):
            self.instrument_map["embedded"].add(category)
        
        specific_matches = [m.group(0) for m in BASE_REGEX.finditer(sentence)]
        
        if specific_matches:
            for instr in specific_matches:
                token = instr.lower().rstrip("s")
                if not token.startswith("hedg"):
                    self.instrument_map[token].add(category)
    
    def resolve_instrument(self, sentence: str) -> Optional[str]:
        """Returns category if sentence contains unambiguous known instrument."""
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
    """Parse _D or _S tags. Returns (is_deadweight, tag_reason, clean_text)."""
    match = TAG_PARSER_STRICT.match(text)
    if match:
        tag_type = match.group(1)
        tag_reason = match.group(2)
        clean_text = match.group(3)
        is_deadweight = (tag_type == "_D")
        return is_deadweight, tag_reason, clean_text
    
    return False, None, text


def has_unambiguous_evidence(sentence: str) -> bool:
    """Check if sentence has unambiguous evidence tags."""
    evidence_tags = set(EVIDENCE_TAG_PARSER.findall(sentence))
    return bool(evidence_tags.intersection(UNAMBIGUOUS_EVIDENCE))


def extract_categories_strict(sentence: str) -> Set[str]:
    """Extract STRICT category matches only."""
    cats = set()
    
    if IR_REGEX.search(sentence):
        cats.add("ir")
    if FX_REGEX.search(sentence):
        cats.add("fx")
    if CP_REGEX.search(sentence):
        cats.add("cp")
    if CR_REGEX.search(sentence):
        cats.add("cr")
    if EQ_REGEX.search(sentence):
        if is_sophisticated_content(sentence):
            cats.add("warr")
        else:
            cats.add("eq")
    
    return cats


def extract_categories_soft(sentence: str) -> Set[str]:
    """Extract SOFT category matches only."""
    cats = set()
    
    if IR_SOFT_REGEX.search(sentence):
        cats.add("ir")
    if FX_SOFT_REGEX.search(sentence):
        cats.add("fx")
    if CP_SOFT_REGEX.search(sentence):
        cats.add("cp")
    if CR_SOFT_REGEX.search(sentence):
        cats.add("cr")
    if EQ_SOFT_REGEX.search(sentence):
        if is_sophisticated_content(sentence):
            cats.add("warr")
        else:
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


def remove_outlier_categories(
    strict_cats: Set[str],
    soft_cats: Dict[str, int],
    threshold_pct: float = 0.10,
    min_mentions: int = 3,
) -> Set[str]:
    """
    Remove soft categories that are outliers (stray mentions).
    
    Strict categories always kept. Soft categories removed if:
    - Count < min_mentions (absolute floor), OR
    - Count < threshold_pct of largest strict category
    """
    if not soft_cats:
        return set()
    
    if not strict_cats:
        # No strict anchors, use soft that meet absolute threshold
        return {
            cat for cat, count in soft_cats.items()
            if count >= min_mentions
        }
    
    # Calculate threshold
    threshold = max(min_mentions, 1 * threshold_pct)
    
    # Keep soft categories that meet threshold
    return {
        cat for cat, count in soft_cats.items()
        if count >= threshold
    }

# =============================================================================
# MAIN PROCESSING
# =============================================================================

def process_row(row: Tuple) -> Tuple:
    """
    Process a single company document.
    
    Returns: (url, categories_json, attributes_json, cik, year)
    """
    url, matches_json, cik, year = row
    
    try:
        paragraphs = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return (url, json.dumps([]), json.dumps({}), cik, year)
    
    if not isinstance(paragraphs, list):
        return (url, json.dumps([]), json.dumps({}), cik, year)
    
    # Initialize
    strict_categories = set()
    soft_categories = defaultdict(int)
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
    
    # --- PASS 1: Collect strict mentions and build tracker ---
    for p in paragraphs:
        if TRADING_VENUE_REGEX.search(p):
            mentions_venue = True
        
        is_para_deadweight, para_tag_reason, para_content = parse_tags(p)
        mine_attributes(para_tag_reason, attributes)
        
        if is_para_deadweight:
            continue
        
        sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(para_content) if s.strip()
        ]
        
        for sent in sentences:
            is_sent_deadweight, sent_tag_reason, sent_content = parse_tags(sent)
            mine_attributes(sent_tag_reason, attributes)
            
            if is_sent_deadweight:
                continue
            
            clean_sent = _cleaner.clean_entities(sent_content)
            strict_cats = extract_categories_strict(clean_sent)
            
            if strict_cats:
                for cat in strict_cats:
                    tracker.register_paragraph(clean_sent, cat)
                strict_categories.update(strict_cats)
    
    # --- PASS 2: Collect soft mentions ---
    for p in paragraphs:
        is_para_deadweight, _, para_content = parse_tags(p)
        
        if is_para_deadweight:
            continue
        
        sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(para_content) if s.strip()
        ]
        
        for sent in sentences:
            is_sent_deadweight, _, sent_content = parse_tags(sent)
            
            if is_sent_deadweight:
                continue
            
            clean_sent = _cleaner.clean_entities(sent_content)
            
            # Skip if already has strict match
            if extract_categories_strict(clean_sent):
                continue
            
            # Check for unambiguous evidence (elevates soft to strict)
            if has_unambiguous_evidence(sent_content):
                soft_cats = extract_categories_soft(clean_sent)
                if soft_cats:
                    for cat in soft_cats:
                        strict_categories.add(cat)
                        tracker.register_paragraph(clean_sent, cat)
                    continue
            
            # Try tracker first
            tracker_cat = tracker.resolve_instrument(clean_sent)
            if tracker_cat:
                soft_categories[tracker_cat] += 1
                continue
            
            # Extract soft categories
            soft_cats = extract_categories_soft(clean_sent)
            for cat in soft_cats:
                soft_categories[cat] += 1
    
    # --- PASS 3: Remove outlier soft categories ---
    valid_soft_cats = remove_outlier_categories(
        strict_categories,
        soft_categories,
        threshold_pct=0.10,
        min_mentions=3,
    )
    
    # --- COMBINE: Strict + Valid Soft ---
    final_categories = strict_categories.union(valid_soft_cats)
    
    # --- PASS 4: Determine is_trader ---
    if mentions_venue and not attributes["is_hedger"]:
        attributes["is_trader"] = True
    
    # --- OUTPUT ---
    final_cat_list = sorted(list(final_categories))
    
    return (
        url,
        json.dumps(final_cat_list),
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
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, categories TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS attributes (url TEXT PRIMARY KEY, attributes TEXT NOT NULL, FOREIGN KEY (url) REFERENCES webpage_result(url))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES webpage_result(url))"
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
        "SELECT w.url, w.matches, r.cik, r.year FROM webpage_result w LEFT JOIN report_data r ON w.url = r.url WHERE w.matches IS NOT NULL"
    )
    
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            if row[0] not in processed_urls:
                yield row
    
    conn.close()


def write_batch(conn, buffer: List) -> None:
    """Write batch of results to database."""
    if not buffer:
        return
    
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        c.executemany(
            "INSERT OR IGNORE INTO webpage_result (url, categories) VALUES (?, ?)",
            [(r[0], r[1]) for r in buffer],
        )
        c.executemany(
            "INSERT OR IGNORE INTO attributes (url, attributes) VALUES (?, ?)",
            [(r[0], r[2]) for r in buffer],
        )
        c.executemany(
            "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(r[0], r[3], r[4]) for r in buffer],
        )
        conn.commit()
    except Exception as e:
        print(f"Write Error: {e}")
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