from pathlib import Path
import sqlite3
import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from tqdm import tqdm
from typing import Any, Tuple, Dict, Set, Optional, List

# --- IMPORTS ---
from derivative_regex import (
    CATEGORY_MAP, CURRENCY_NAMES_REGEX, HEDGING_CONTEXT_REGEX, IR_REGEX, FX_REGEX, CP_REGEX, EQ_REGEX, CR_REGEX,
    IR_SOFT_REGEX, FX_SOFT_REGEX, CP_SOFT_REGEX, EQ_SOFT_REGEX, CR_SOFT_REGEX, LOOSE_GEN_REGEX,
    SENTENCE_SPLIT_PATTERN, SOFT_GEN_REGEX, STRICT_GEN_REGEX, TRADING_VENUE_REGEX, BASE_REGEX,
)
from table_processor import TABLE_ANCHOR
from prefilter_database import is_sophisticated_content, is_sophisticated_target
from prefiltered_lib import DEADWEIGHT_TOKEN, SKIP_TOKEN, MinimalTextCleaner, NoiseReason, EvidenceReason

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
    STOPLIST = {
        "hedge",
        "hedges",
        "hedging",
        "derivative",
        "derivatives",
    }
    EMBEDDED_TERMS = {
        "embedded",
    }
    
    def __init__(self):
        self.instrument_map = defaultdict(set)

    def register_paragraph(self, sentence: str, category: str) -> None:
        """Register instruments found in sentence to category."""
        sentence_lower = sentence.lower()
        
        # Check for embedded terms
        for term in self.EMBEDDED_TERMS:
            if term in sentence_lower:
                self.instrument_map[term].add(category)

        specific_matches = [m.group(0) for m in BASE_REGEX.finditer(sentence)]

        if specific_matches:
            for instr in specific_matches:
                token = instr.lower().rstrip("s")
                if token not in self.STOPLIST:
                    self.instrument_map[token].add(category)

    def resolve_instrument(self, sentence: str) -> Optional[str]:
        """Returns category if sentence contains unambiguous known instrument."""
        matches = BASE_REGEX.findall(sentence)
        sentence_lower = sentence.lower()
        
        # Check for embedded terms
        for term in self.EMBEDDED_TERMS:
            if term in sentence_lower:
                matches.append(term)

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
        is_deadweight = tag_type in [DEADWEIGHT_TOKEN, SKIP_TOKEN]
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
    if is_sophisticated_target(sentence):
        cats.add("warr")
    elif EQ_REGEX.search(sentence):
        cats.add("eq")
    if not cats and TABLE_ANCHOR in sentence:
        if CURRENCY_NAMES_REGEX.search(sentence):
            cats.add("fx")
        if FX_SOFT_REGEX.search(sentence):
            cats.add("fx")
        if IR_SOFT_REGEX.search(sentence):
            cats.add("ir")
        if CP_SOFT_REGEX.search(sentence):
            cats.add("cp")
        if CR_SOFT_REGEX.search(sentence):
            cats.add("cr")
        if is_sophisticated_target(sentence):
            cats.add("warr")
        elif EQ_SOFT_REGEX.search(sentence):
            cats.add("eq")
        if not cats:
            cats.add("gen")
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
    if is_sophisticated_target(sentence):
        cats.add("warr")
    elif EQ_SOFT_REGEX.search(sentence):
        cats.add("eq")

    if not cats:
        if STRICT_GEN_REGEX.search(sentence) or SOFT_GEN_REGEX.search(sentence):
            cats.add("gen")
        elif LOOSE_GEN_REGEX.search(sentence) and HEDGING_CONTEXT_REGEX.search(
            sentence
        ):
            cats.add("gen")

    return cats


def mine_attributes(tag_reason: Optional[str], attributes: Dict) -> None:
    """
    Extract user attributes from tags using a mapped lookup.
    Consolidates redundant state indicators into unified attributes.
    """
    if not tag_reason:
        return

    # 1. Historical Special Case (Group of Noise Tags)
    if tag_reason in {
        NoiseReason.TIME.value,
        NoiseReason.TERM.value,
        NoiseReason.HIST_BLOCK.value,
    }:
        attributes["is_historical"] = True
        return

    # 2. Attribute Mapping
    # Maps Tag Reason -> Attribute Key
    TAG_MAP = {
        # --- NOISE (Identity Signals) ---
        NoiseReason.TRADING.value: "is_hedger",
        NoiseReason.DOC.value: "documents_hedge_accounting",
        NoiseReason.AOCI.value: "has_aoci_activity",
        NoiseReason.CREDIT.value: "manages_credit_risk",
        # --- EVIDENCE (Reporting Signals) ---
        # A. POSITIONS (The "We Have It" Merge)
        # Merges: Active State (Anchored), Continuous Usage (General), and Location (Accounting)
        EvidenceReason.AS_YEAR.value: "reports_positions",
        EvidenceReason.ASAIY.value: "reports_positions",
        EvidenceReason.CONT_USE.value: "reports_positions",
        EvidenceReason.CONT_USE_AMB.value: "reports_positions",
        EvidenceReason.BS_LOC.value: "reports_positions",
        # B. TRANSACTIONS (The "Flow" Merge)
        EvidenceReason.ACT_YEAR.value: "reports_transactions",
        EvidenceReason.ACT_AMB_YEAR.value: "reports_transactions",
        EvidenceReason.ACT_GEN.value: "reports_transactions",
        # C. QUANTITATIVE (Kept distinct for granularity)
        EvidenceReason.NVY.value: "reports_notional",
        EvidenceReason.NVNY.value: "reports_notional",
        EvidenceReason.FVY.value: "reports_fair_value",
        EvidenceReason.FVNY.value: "reports_fair_value",
        EvidenceReason.FVAIY.value: "reports_fair_value",
        EvidenceReason.FVAINY.value: "reports_fair_value",
        # D. DETAILS
        EvidenceReason.MAT_FUT.value: "reports_maturity",
        EvidenceReason.MAT_AMB_FUT.value: "reports_maturity",
        EvidenceReason.VAL_MODEL.value: "eq_valuation_model",
    }

    # 3. Apply
    if target_attr := TAG_MAP.get(tag_reason):
        attributes[target_attr] = True


def remove_outlier_categories(
    strict_counts: Dict[str, int],  # Changed from Set[str] to Dict[str, int]
    soft_counts: Dict[str, int],
    threshold_pct: float = 0.25,
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


PRIORITY_ORDER = ["fx", "cp", "eq", "cr", "ir"]
def get_text_categories(text: str) -> Set[str]:
    """
    Determines category using Weighted Scoring and Map Iteration.

    Phases:
    1. Strict Check (Instrument + Context): High Score (Bypass).
    2. Soft Check (Context Density): Low Score (Requires volume).
       - Uses Priority Consumption (FX eats 'Currency' before IR sees it).
    """
    scores = defaultdict(int)

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: STRICT SIGNALS (Non-Destructive)
    # ═══════════════════════════════════════════════════════════
    # We check Strict Instruments (Index 0) and Strict Context (Index 2)

    for cat, (strict_inst, soft_inst, strict_ctx, _) in CATEGORY_MAP.items():
        # A. Strict Instrument ("Interest Rate Swap")
        if strict_inst and strict_inst.search(text):
            scores[cat] += 1000
        elif soft_inst and soft_inst.search(text):
            scores[cat] += 250

        # B. Strict Context ("Interest Rate Risk")
        if strict_ctx and strict_ctx.search(text):
            # Special Handling for Equity -> Warrants
            if cat == "eq" and is_sophisticated_content(text):
                scores["warr"] += 6000  # Immediate override
            else:
                scores[cat] += 2000
                

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: SOFT CONTEXT (Priority Consumption)
    # ═══════════════════════════════════════════════════════════
    # Only run if we haven't found a "Smoking Gun" (Score < 2000)
    # or if we want to resolve ties.

    remaining_text = text

    for cat in PRIORITY_ORDER:
        # Get Soft Context Regex (Index 3)
        soft_ctx = CATEGORY_MAP[cat][3]

        if soft_ctx:
            # Find all matches
            matches = list(soft_ctx.finditer(remaining_text))
            if matches:
                # Score based on density (15 pts per mention)
                scores[cat] += 15 * len(matches)

                # CRITICAL: Consume text to prevent double-counting
                # e.g. FX eats "Foreign Currency" so IR doesn't match "Currency"
                remaining_text = soft_ctx.sub(" ", remaining_text)

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: THRESHOLDING
    # ═══════════════════════════════════════════════════════════
    if not scores:
        return set()

    max_score = max(scores.values())

    # If we have a massive strict hit (>1000), raise threshold to kill weak noise
    threshold = 1000 if max_score >= 1000 else 75

    top_cats = {cat for cat, score in scores.items() if score >= threshold}
    specific = top_cats - {"gen"}

    return specific if specific else top_cats


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
    attributes: Dict[str, Any] = {
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
        local_tracker = GlobalInstrumentTracker()
        if not mentions_venue and TRADING_VENUE_REGEX.search(p):
            mentions_venue = True

        is_para_deadweight, para_tag_reason, para_content = parse_tags(p)
        mine_attributes(para_tag_reason, attributes)

        # 1. PARAGRAPH PRE-SCAN (Contextual Dominance)
        # Use the scoring classifier to determine what this paragraph is ABOUT.
        context_cats = get_text_categories(p) # Allow full original text

        # We allow multiple contexts if they are strong enough to survive get_text_categories
        local_contexts = context_cats if context_cats else set()

        sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(p) if s.strip()
        ]

        for sent in sentences:
            is_sent_deadweight, sent_tag_reason, sent_content = parse_tags(sent)
            mine_attributes(sent_tag_reason, attributes)

            evidence_tags_found = EVIDENCE_TAG_PARSER.findall(sent_content)
            for etag in evidence_tags_found:
                mine_attributes(etag, attributes)

            is_active = not (is_para_deadweight or is_sent_deadweight)
            clean_sent = _cleaner.clean_entities(sent_content)

            # -------------------------------------------------------------
            # A. Check Strict Matches (Gate 1 - Modified)
            # -------------------------------------------------------------
            strict_cats = extract_categories_strict(clean_sent)

            if strict_cats:
                # 1. Always learn Definitions from Strict matches (e.g. Headers)
                for cat in strict_cats:
                    tracker.register_paragraph(clean_sent, cat)
                    local_tracker.register_paragraph(clean_sent, cat)

                # 2. If Verified Evidence exists, Lock it in as an ANCHOR.
                if is_active and evidence_tags_found:
                    for cat in strict_cats:
                        strict_categories.add(cat)
                        strict_counts[cat] += 1  # Only increment Anchor magnitude here!
                    continue  # Done. We trust this sentence.

                # 3. If NO Evidence, fall through!
                # We do NOT increment strict_counts. This demotes the strict match
                # to a "Soft Candidate" which must pass the frequency threshold (3+).

            # -------------------------------------------------------------
            # Active Check (Gatekeeper for Soft Logic)
            # -------------------------------------------------------------
            if not is_active:
                continue

            # -------------------------------------------------------------
            # B. Check Unambiguous Promotion (Soft -> Strict via Strong Evidence)
            # -------------------------------------------------------------
            if has_unambiguous_evidence(sent_content):
                promoted_cats = extract_categories_soft(clean_sent)
                for cat in promoted_cats:
                    strict_categories.add(cat)
                    tracker.register_paragraph(clean_sent, cat)
                    local_tracker.register_paragraph(clean_sent, cat)
                    strict_counts[cat] += 1
                continue

            # -------------------------------------------------------------
            # NEW: Explicit Soft Extraction (Catching fall-through Strict)
            # -------------------------------------------------------------
            # This catches "Interest Rate Swaps" (Strict) that fell through above.
            soft_cats = extract_categories_soft(clean_sent)
            if soft_cats and soft_cats != {"gen"}:
                for cat in soft_cats:
                    tracker.register_paragraph(clean_sent, cat)
                    local_tracker.register_paragraph(clean_sent, cat)
                    soft_categories[cat] += 1
                continue

            # -------------------------------------------------------------
            # C. Tracker Resolution (Token Matching)
            # -------------------------------------------------------------
            tracker_cat = local_tracker.resolve_instrument(clean_sent)

            # Priority 2: Check Global Context (If Local failed/was empty)
            if not tracker_cat:
                tracker_cat = tracker.resolve_instrument(clean_sent)

            if tracker_cat:
                soft_categories[tracker_cat] += 1
                continue
            # -------------------------------------------------------------
            # D. Standard Soft Extraction with Local Resolution
            # -------------------------------------------------------------
            # (soft_cats already computed above, reused here if needed)
            found_soft = soft_cats if soft_cats else extract_categories_soft(clean_sent)

            # If we found ONLY "gen" (e.g. "The instruments")
            # and we have valid local contexts, resolve to ALL of them.
            if local_contexts and "gen" in found_soft and len(found_soft) == 1:
                for ctx in local_contexts:
                    soft_categories[ctx] += 1
            else:
                for cat in found_soft:
                    soft_categories[cat] += 1

    # --- REMOVE OUTLIERS ---
    valid_soft_cats = remove_outlier_categories(
        strict_counts, 
        soft_categories,
        threshold_pct=0.10,
        min_mentions=3
    )

    final_categories = strict_categories.union(valid_soft_cats)

    if len(final_categories) > 1 and "gen" in final_categories:
        final_categories.remove("gen")

    if mentions_venue and not attributes["is_hedger"]:
        attributes["is_trader"] = True

    attributes["debug"] = {"soft_counts": soft_categories, "strict_counts": strict_counts}

    return (url, json.dumps(sorted(list(final_categories))), json.dumps(attributes), cik, year)
# =============================================================================
# DATABASE
# =============================================================================

def setup_target_db(path: str) -> None:
    """Create target database schema."""
    conn = sqlite3.connect(path)
    c = conn.cursor()
    
    c.execute(
        "CREATE TABLE IF NOT EXISTS category (url TEXT PRIMARY KEY, categories TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS attributes (url TEXT PRIMARY KEY, attributes TEXT NOT NULL, FOREIGN KEY (url) REFERENCES category(url))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES category(url))"
    )
    
    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON category (url)")
    c.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    conn.close()


def get_processed_urls(path: str) -> set:
    """Get URLs already processed."""
    if not Path(path).exists():
        return set()
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT url FROM category")}
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
            "INSERT OR IGNORE INTO category (url, categories) VALUES (?, ?)",
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
