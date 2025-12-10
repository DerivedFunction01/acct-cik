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
    GEN_REGEX, HEDGING_CONTEXT_REGEX, IR_REGEX, FX_REGEX, CP_REGEX, EQ_REGEX, CR_REGEX,
    IR_SOFT_REGEX, FX_SOFT_REGEX, CP_SOFT_REGEX, EQ_SOFT_REGEX, CR_SOFT_REGEX, LOOSE_GEN_REGEX,
    SENTENCE_SPLIT_PATTERN, SOFT_GEN_REGEX, STRICT_GEN_REGEX, TRADING_VENUE_REGEX, BASE_REGEX,
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
    if is_sophisticated_content(sentence):
        cats.add("warr")
    elif EQ_REGEX.search(sentence):
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
    if is_sophisticated_content(sentence):
        cats.add("warr")
    elif EQ_SOFT_REGEX.search(sentence):
        cats.add("eq")
    if not cats:
        if STRICT_GEN_REGEX.search(sentence) or SOFT_GEN_REGEX.search(sentence):
            cats.add("gen")
        elif LOOSE_GEN_REGEX.search(sentence) and HEDGING_CONTEXT_REGEX.search(sentence):
            cats.add("gen")
    
    return cats


def mine_attributes(tag_reason: Optional[str], attributes: Dict) -> None:
    """Extract user attributes from noise tags."""
    if not tag_reason:
        return

    if tag_reason == NoiseReason.TRADING.value:
        attributes["is_hedger"] = True
    elif tag_reason == NoiseReason.POLICY.value:
        attributes["documents_hedge_accounting"] = True
    elif tag_reason == NoiseReason.AOCI.value:
        attributes["has_aoci_activity"] = True
    elif tag_reason == NoiseReason.CREDIT.value:
        attributes["manages_credit_risk"] = True
    elif tag_reason in {NoiseReason.TIME.value, NoiseReason.TERM.value, NoiseReason.HIST_BLOCK.value}:
        attributes["is_historical"] = True


def remove_outlier_categories(
    strict_counts: Dict[str, int],  # Changed from Set[str] to Dict[str, int]
    soft_counts: Dict[str, int],
    threshold_pct: float = 0.10,
    min_mentions: int = 3,
) -> Set[str]:
    """
    Remove soft categories that are outliers relative to the dominant strict category.

    1. Strict categories are 'Anchors'. Their weight = Strict + Soft.
    2. Soft-only categories are 'Candidates'. Their weight = Soft only.
    3. Candidates are removed if they don't meet the % threshold of the largest Anchor.
    """

    # 1. Calculate the "True Magnitude" of strict categories
    # If a category is strict, its dominance is Strict + Soft mentions.
    anchor_magnitudes = {}

    for cat, s_count in strict_counts.items():
        # Add the strict count plus any soft mentions for this same category
        anchor_magnitudes[cat] = s_count + soft_counts.get(cat, 0)

    # If we have no strict anchors, we fall back to absolute min_mentions logic
    if not anchor_magnitudes:
        return {cat for cat, count in soft_counts.items() if count >= min_mentions}

    # 2. Determine the baseline (largest anchor)
    max_anchor_count = max(anchor_magnitudes.values())

    # Calculate threshold based on the "heaviest" user category
    # Example: If IR has 22 total, threshold is 2.2
    dynamic_threshold = max(min_mentions, max_anchor_count * threshold_pct)

    valid_soft_cats = set()

    for cat, count in soft_counts.items():
        # If this soft cat is ALSO a strict cat, it's already kept by default.
        # But for the sake of returning a clean set of "surviving softs":
        if cat in strict_counts:
            valid_soft_cats.add(cat)
            continue

        # 3. Filter Soft-Only categories against the threshold
        if count >= dynamic_threshold:
            valid_soft_cats.add(cat)

    return valid_soft_cats


# =============================================================================
# MAIN PROCESSING
# =============================================================================


def process_row(row: Tuple) -> Tuple:
    url, matches_json, cik, year = row
    
    try:
        paragraphs = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return (url, json.dumps([]), json.dumps({}), cik, year)

    # Initialize
    strict_categories = set()
    soft_categories = defaultdict(int)
    strict_counts = defaultdict(int)
    attributes = {
        "is_hedger": False,
        "documents_hedge_accounting": False,
        "has_aoci_activity": False,
        "manages_credit_risk": False,
        "is_historical": False,
        "is_trader": False,
    }
    mentions_venue = False
    tracker = GlobalInstrumentTracker()

    # --- SINGLE PASS Processing ---
    for p in paragraphs:
        # 1. Document Level Checks
        if TRADING_VENUE_REGEX.search(p):
            mentions_venue = True

        # 2. Parse Tags ONCE
        is_para_deadweight, para_tag_reason, para_content = parse_tags(p)
        mine_attributes(para_tag_reason, attributes)
        
        # Split sentences
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(para_content) if s.strip()]

        for sent in sentences:
            is_sent_deadweight, sent_tag_reason, sent_content = parse_tags(sent)
            mine_attributes(sent_tag_reason, attributes)
            
            # Determine Active Status
            is_active = not (is_para_deadweight or is_sent_deadweight)
            clean_sent = _cleaner.clean_entities(sent_content)

            # 3. Check Strict Matches First
            strict_cats = extract_categories_strict(clean_sent)
            
            if strict_cats:
                # ACTION: Register Anchor
                for cat in strict_cats:
                    tracker.register_paragraph(clean_sent, cat)
                    strict_counts[cat] += 1 # Counts towards magnitude (even if deadweight)
                    
                    if is_active:
                        strict_categories.add(cat) # Counts towards classification
                
                # If we found strict matches, we don't need to look for soft matches in this sentence
                continue 

            # 4. Check Soft Matches (Active Only)
            if not is_active:
                continue

            # Check Unambiguous Promotion
            if has_unambiguous_evidence(sent_content):
                promoted_cats = extract_categories_soft(clean_sent)
                for cat in promoted_cats:
                    strict_categories.add(cat)
                    tracker.register_paragraph(clean_sent, cat)
                    strict_counts[cat] += 1 # Add to anchor count
                continue

            # Tracker Resolution
            tracker_cat = tracker.resolve_instrument(clean_sent)
            if tracker_cat:
                soft_categories[tracker_cat] += 1
                continue

            # Standard Soft Extraction
            found_soft = extract_categories_soft(clean_sent)
            for cat in found_soft:
                soft_categories[cat] += 1

    # --- REMOVE OUTLIERS ---
    # Now strictly separated: strict_counts has the volume, soft_categories has the candidates
    valid_soft_cats = remove_outlier_categories(
        strict_counts, 
        soft_categories,
        threshold_pct=0.10,
        min_mentions=3
    )

    final_categories = strict_categories.union(valid_soft_cats)
    
    # Logic for trader check...
    if mentions_venue and not attributes["is_hedger"]:
        attributes["is_trader"] = True

    return (url, json.dumps(sorted(list(final_categories))), json.dumps(attributes), cik, year)


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
