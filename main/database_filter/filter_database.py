"""
DERIVATIVE CATEGORY DISAMBIGUATION MODULE
==========================================
Advanced filtering system for separating multi-category derivative disclosures
into distinct, single-category training examples through targeted text reduction.

Methodology:
1. Multi-category detection via instrument-specific and context-specific pattern matching
2. Iterative sentence duplication for each identified derivative category
3. Systematic removal of cross-category terminology using regex-based excision
4. Independent paragraph construction per category with contextual compatibility validation
5. Preservation of generic derivative references without category-specific terms

Academic Rationale:
This approach addresses the challenge of mixed-category financial disclosures where
companies discuss multiple derivative types in compound sentences. Traditional filtering
would either discard these sentences or introduce category ambiguity. Our duplication-
and-reduction strategy preserves information while ensuring training data purity.

Example Transformation:
  Source: "The Company utilizes foreign currency forwards and interest rate swaps
           to manage exposure to market volatility."

  Output (2 distinct examples):
    - FX Instance: "The Company utilizes forwards to manage exposure to market volatility."
      (Removed: interest rate instruments and IR-specific context)

    - IR Instance: "The Company utilizes swaps to manage exposure to market volatility."
      (Removed: foreign currency instruments and FX-specific context)
"""

import json
from pathlib import Path
from tqdm import tqdm
from typing import List, Tuple, Optional, Set
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time
import sqlite3

# Import all derivative regexes

from derivative_regex import (
    ALL_REGEX,
    CATEGORY_REGEX,
    DEFINITION_INDICATORS,
    EXCLUDE_REGEX_ACCOUNTING_STD,
    EXCLUDE_REGEX_EQUITY_COMP,
    EXCLUDE_REGEX_LEGAL_LITIGATION,
    IR_REGEX,
    FX_REGEX,
    CP_REGEX,
    EQ_REGEX,
    LOOSE_GEN_REGEX,
    POSITION_CONTEXT_INDICATORS,
    STRICT_GEN_REGEX,
    SOFT_GEN_REGEX,
    SENTENCE_SPLIT_PATTERN,
    MIN_SENTENCE_LENGTH,
    TRADING_STATEMENTS_REGEX,
    check_for_instrument,
    cleanup_fragment,
    CATEGORY_CONTEXT_MAP,
    IR_CONTEXT_REGEX,
    FX_CONTEXT_REGEX,
    CP_CONTEXT_REGEX,
    EQ_CONTEXT_REGEX,
    NON_POSITION_INDICATORS,
    PNL_ONLY_NO_POSITION,
)

# =============================================================================
# CONFIGURATION
# =============================================================================


def get_worker_count():
    """Auto-detects CPU cores to set worker count."""
    cpu_cores = mp.cpu_count()
    num_workers = max(1, cpu_cores - 1)
    print(
        f"🖥️  System Detected: {cpu_cores} CPU cores, setting NUM_WORKERS to {num_workers}"
    )
    return num_workers


NUM_WORKERS = get_worker_count()
BATCH_SIZE = 1000  # Optimal batch size for SQLite transactions
FLUSH_INTERVAL = 5.0  # Seconds — fallback flush if batch not full
CHUNK_SIZE = 50  # Larger chunks reduce task submission overhead — tune this
SOURCE_DB_PATH = "web_data.db"
CLEAN_DB_PATH = "prepared_data.db"

# In-memory buffers (protected by main process only)
result_buffer = []  # List of (url, matches, cik, year)
discard_buffer = []  # List of (url, sentence, reason)

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def create_clean_db():
    """Create unified clean database with parallel category tracking."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        # Main table for high-confidence matches
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS webpage_result (
                url TEXT PRIMARY KEY,
                matches TEXT NOT NULL  -- JSON array of paragraph texts
            )
            """
        )

        # CRITICAL: Category array synchronized with matches array
        # categories[i] corresponds to matches[i]
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS category (
                url TEXT PRIMARY KEY,
                categories TEXT NOT NULL,  -- JSON array of category labels ['ir', 'fx', 'gen', ...]
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
            """
        )

        # Metadata for high-confidence matches
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

        # Server result table: Roberta's results
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS server_result (
                url TEXT PRIMARY KEY,
                server_response TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
        """
        )

        # Discard tracking table - stores discarded sentences for review
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discarded_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                sentence TEXT,
                discard_reason TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url),
                FOREIGN KEY (discard_reason) REFERENCES discard_reasons(reason)
            )
            """
        )

        # Discard reasons: no_match, too_short, trading_statement
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discard_reasons (
                reason TEXT PRIMARY KEY
            )
            """
        )

        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS discard_reason_idx ON discarded_sentences (discard_reason)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS server_url_idx ON server_result (url)")
        c.execute("CREATE INDEX IF NOT EXISTS cat_url_idx ON category (url)")
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Error creating clean database: {e}")
    finally:
        try:
            reasons = [
                "no_match",
                "too_short",
                "trading_statements",
                "aoci",
                "pnl_only_no_position",
                "pnl_only_removed",
                "definition_boilerplate",
                "adoption",
                "lost_instrument_reference",
            ] + [
                f"disambiguation_excision_failed_{cat}"
                for cat in CATEGORY_CONTEXT_MAP.keys()
            ]
            c.executemany(
                "INSERT OR IGNORE INTO discard_reasons (reason) VALUES (?)",
                [(reason,) for reason in reasons],
            )
        except sqlite3.IntegrityError as e:
            print(f"⚠️  Error inserting discard reasons: {e}")
        conn.commit()
        conn.close()


def get_source_data() -> List[Tuple[str, str]]:
    """Fetch all URL and matches from source database."""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT url, matches FROM webpage_result WHERE url IS NOT NULL")
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"❌ Error reading source database: {e}")
        conn.close()
        return []


def get_all_report_data() -> dict:
    """Fetch all report data into a dictionary for fast lookups."""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url, cik, year FROM report_data")
    report_map = {row[0]: (row[1], row[2]) for row in c.fetchall()}
    conn.close()
    return report_map


def get_processed_urls_from_clean_db() -> set:
    """Fetches all URLs that have already been processed and saved to the clean database."""
    if not Path(CLEAN_DB_PATH).exists():
        return set()
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT url FROM webpage_result")
        processed_urls = {row[0] for row in c.fetchall()}
        return processed_urls
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()


def flush_buffers(force: bool = False) -> bool:
    """
    Flush accumulated results and discards to database in batches.
    Ensures matches and categories arrays are synchronized.
    """
    global result_buffer, discard_buffer

    if (
        not force
        and len(result_buffer) < BATCH_SIZE
        and len(discard_buffer) < BATCH_SIZE * 10
    ):
        return False

    conn = sqlite3.connect(CLEAN_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA temp_store = MEMORY")
    c = conn.cursor()

    try:
        c.execute("BEGIN TRANSACTION")

        # 1. Flush main results with parallel category arrays
        if result_buffer:
            # result_buffer contains: (url, [(text, category), ...], cik, year)

            for url, paragraph_tuples, cik, year in result_buffer:
                # Separate texts and categories into parallel arrays
                texts = [text for text, cat in paragraph_tuples]
                categories = [cat for text, cat in paragraph_tuples]

                # Verify array synchronization
                assert len(texts) == len(categories), f"Array mismatch for {url}"

                # Insert matches
                c.execute(
                    "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                    (url, json.dumps(texts)),
                )

                # Insert parallel categories array
                c.execute(
                    "INSERT OR IGNORE INTO category (url, categories) VALUES (?, ?)",
                    (url, json.dumps(categories)),
                )

                # Insert metadata if available
                if cik is not None:
                    c.execute(
                        "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                        (url, cik, year),
                    )

            result_buffer.clear()

        # 2. Flush discarded sentences
        if discard_buffer:
            c.executemany(
                """
                INSERT INTO discarded_sentences (url, sentence, discard_reason)
                VALUES (?, ?, ?)
                """,
                discard_buffer,
            )
            discard_buffer.clear()

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Batch flush failed: {e}")
        raise
    finally:
        conn.close()


# =============================================================================
# CATEGORY DETECTION & VALIDATION
# =============================================================================


def get_sentence_categories(sentence: str, context_sentences: Optional[List[str]] = None) -> set:
    """
    Returns derivative categories with smart disambiguation.

    Strategy:
    1. Find all matching categories in the sentence
    2. If ambiguous, use context to break ties
    3. Prefer specific over generic
    4. Use match count + context strength as tiebreaker
    """
    if context_sentences is None:
        context_sentences = []

    full_text = (
        sentence
        if not context_sentences
        else sentence + " " + " ".join(context_sentences)
    )

    scores = {"ir": 0, "fx": 0, "cp": 0, "eq": 0, "gen": 0}

    # Phase 1: Score based on instrument keyword matches
    if IR_REGEX.search(sentence):
        scores["ir"] += len(IR_REGEX.findall(sentence)) * 10
    if FX_REGEX.search(sentence):
        scores["fx"] += len(FX_REGEX.findall(sentence)) * 10
    if CP_REGEX.search(sentence):
        scores["cp"] += len(CP_REGEX.findall(sentence)) * 10
    if EQ_REGEX.search(sentence):
        scores["eq"] += len(EQ_REGEX.findall(sentence)) * 10
    if STRICT_GEN_REGEX.search(sentence) or SOFT_GEN_REGEX.search(sentence):
        scores["gen"] += 5

    # Phase 2: Add context support scores
    if context_sentences:
        for cat in ["ir", "fx", "cp", "eq"]:
            context_regex = {
                "ir": IR_CONTEXT_REGEX,
                "fx": FX_CONTEXT_REGEX,
                "cp": CP_CONTEXT_REGEX,
                "eq": EQ_CONTEXT_REGEX,
            }.get(cat)
            if context_regex and context_regex.search(full_text):
                scores[cat] += len(context_regex.findall(full_text))

    matches = {cat: score for cat, score in scores.items() if score > 0}

    if not matches:
        return {"other"}

    max_score = max(matches.values())
    top_cats = {cat for cat, score in matches.items() if score == max_score}

    specific = top_cats - {"gen"}
    return specific if specific else top_cats


def get_primary_category(categories: set) -> str:
    """Get the primary category, preferring specific over generic."""
    specific = categories - {"gen", "other"}
    if specific:
        priority = ["ir", "fx", "cp", "eq"]
        for cat in priority:
            if cat in specific:
                return cat
        return list(specific)[0]
    return "gen" if "gen" in categories else "other"


# =============================================================================
# CATEGORY-SPECIFIC TERM EXCISION ENGINE
# =============================================================================

# Mapping of derivative categories to their respective deletion patterns
# Each category maps to (instrument_pattern, context_pattern) for comprehensive removal
CATEGORY_DELETION_MAP = {
    "ir": (IR_REGEX, IR_CONTEXT_REGEX),
    "fx": (FX_REGEX, FX_CONTEXT_REGEX),
    "cp": (CP_REGEX, CP_CONTEXT_REGEX),
    "eq": (EQ_REGEX, EQ_CONTEXT_REGEX),
}


def excise_category_terminology(text: str, category: str) -> str:
    """
    Systematically remove all lexical markers associated with a specific derivative category.
    Applies both instrument-specific and contextual terminology removal.

    Args:
        text: Source text containing derivative references
        category: Target category for removal ('ir', 'fx', 'cp', or 'eq')

    Returns:
        Text with all specified category terminology removed

    Example:
        Input:  "foreign currency forwards hedge exposure"
        Call:   excise_category_terminology(text, "fx")
        Output: "hedge exposure"

        Rationale: Removes "foreign currency forwards" (FX instrument + context)
    """
    if category not in CATEGORY_DELETION_MAP:
        return text

    instrument_regex, context_regex = CATEGORY_DELETION_MAP[category]

    # Phase 1: Remove instrument-specific terminology
    text = instrument_regex.sub(" ", text)

    # Phase 2: Remove contextual terminology
    text = context_regex.sub(" ", text)

    # Phase 3: Normalize whitespace and punctuation artifacts
    text = cleanup_fragment(text)

    return text


def generate_single_category_variant(
    sentence: str, preserve_category: str, detected_categories: Set[str]
) -> Optional[str]:
    """
    Generate a category-pure variant of a multi-category sentence through
    systematic excision of conflicting category terminology.

    Args:
        sentence: Original multi-category sentence
        preserve_category: Category to retain in output
        detected_categories: Complete set of categories identified in source

    Returns:
        Category-pure sentence variant, or None if excision results in
        insufficient content or loss of preserved category

    Validation Steps:
        1. Minimum length threshold enforcement (MIN_SENTENCE_LENGTH)
        2. Verification that preserved category remains detectable post-excision
        3. Structural integrity check via cleanup_fragment()
    """
    # Identify categories requiring excision (all except preserved category)
    excision_targets = detected_categories - {preserve_category, "gen", "other"}

    cleaned = sentence

    # Iteratively excise each conflicting category
    for target_category in excision_targets:
        cleaned = excise_category_terminology(cleaned, target_category)

    # Validation 1: Minimum length requirement
    if len(cleaned) < MIN_SENTENCE_LENGTH:
        return None

    # Validation 2: Verify preserved category remains detectable
    if preserve_category not in {"gen", "other"}:
        instrument_regex = CATEGORY_DELETION_MAP[preserve_category][0]
        if not instrument_regex.search(cleaned):
            return None  # Over-excision removed target category

    return cleaned


# =============================================================================
# ENHANCED FILTER_MATCHES WITH CATEGORY DISAMBIGUATION
# =============================================================================


def filter_matches_with_disambiguation(
    matches_json: str, url: str = ""
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, str]]]:
    """
    Advanced filtering system implementing category-based sentence disambiguation
    through duplication and targeted terminology excision.

    Processing Pipeline:
        1. Sentence segmentation and initial validation
        2. Trading denial clause removal
        3. Multi-category detection via pattern matching
        4. Category-specific variant generation for mixed sentences
        5. Context sentence compatibility assessment and integration
        6. Quality validation and discard tracking

    Args:
        matches_json: JSON-encoded list of text segments from source documents
        url: Document identifier for discard tracking

    Returns:
        Tuple containing:
        - List of (paragraph_text, category_label) for category-pure examples
        - List of (url, sentence, discard_reason) for rejected content

    Category Labels:
        'ir': Interest rate derivatives
        'fx': Foreign exchange derivatives
        'cp': Commodity derivatives
        'eq': Equity derivatives
        'gen': Generic derivative references
        'other': Insufficient category signals

    Advanced filtering with hierarchical category resolution:

    Resolution Priority:
    1. Current sentence: direct instrument + context detection
    2. Within-paragraph lookback: previous sentences in same paragraph
    3. Cross-paragraph lookback: last known category from prior paragraphs

    This handles cases like:
        "We use interest rate swaps. These instruments with a notional value of XX are used hedge our debt."
        └─ Sentence 1: ir (direct) ─┘  └─ Sentence 2: ir (lookback) ─┘

    CRITICAL: Returns parallel arrays where matches[i] corresponds to categories[i]
    """
    try:
        matches = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return [], []

    if not isinstance(matches, list):
        return [], []

    final_paragraphs = []  # List of (paragraph_text, category_label)
    all_discarded = []

    # Track ALL sentences across ALL paragraphs (for cross-paragraph lookback)
    global_sentence_history = (
        []
    )  # List of (para_idx, sent_idx, category, instrument, sentence_text)

    for para_idx, match in enumerate(matches):
        # ADD THIS BLOCK:
        if '<TABLE>' in match.upper():
            # Keep table as-is without processing
            final_paragraphs.append((match, 'table'))  # Special 'table' category
            continue
        if EXCLUDE_REGEX_ACCOUNTING_STD.search(match):
            # Try to salvage the paragraph by stepping through sentence by sentence, and then try to reconstruct it
            sentences = SENTENCE_SPLIT_PATTERN.split(match)
            text = []
            discard = []
            for sentence in sentences:
                if EXCLUDE_REGEX_ACCOUNTING_STD.search(
                    sentence
                ) and not CATEGORY_REGEX.search(sentence): # Skip "derivative instruments but keep ir swaps"
                    discard.append(sentence)
                else:
                    text.append(sentence)
            discarded_text = " ".join(discard)
            if discarded_text.strip():
                all_discarded.append((url, discarded_text, "adoption"))
            match = " ".join(text)
            if not match.strip():
                continue
        if EXCLUDE_REGEX_LEGAL_LITIGATION.search(match): # If the text is all about legal problems, then there is no point salvaging "cp options" if it was part of the legal case
            all_discarded.append((url, match, "legal"))
            continue
        if EXCLUDE_REGEX_EQUITY_COMP.search(match): 
            # Try to salvage the paragraph by stepping through for derivative mentions
            sentences = SENTENCE_SPLIT_PATTERN.split(match)
            text = []
            discard = []
            for sentence in sentences:
                if CATEGORY_REGEX.search(sentence) or STRICT_GEN_REGEX.search(sentence): # Any equity derivative
                    text.append(sentence)
                else:
                    discard.append(sentence)
            discarded_text = " ".join(discard)
            if discarded_text.strip():
                all_discarded.append((url, discarded_text, "comp"))
            match = " ".join(text)
            if not match.strip():
                continue

        # Begin construction
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(match)]
        used_indices = set()

        # Track category within current paragraph
        paragraph_category_history = []  # List of (sentence_idx, category, instrument)

        for idx, sentence in enumerate(sentences):
            if idx in used_indices:
                continue

            # ═══════════════════════════════════════════════════════════
            # VALIDATION PHASE
            # ═══════════════════════════════════════════════════════════
            if len(sentence) < MIN_SENTENCE_LENGTH:
                all_discarded.append((url, sentence, "too_short"))
                continue

            if DEFINITION_INDICATORS.search(sentence):
                all_discarded.append((url, sentence, "definition_boilerplate"))
                used_indices.add(idx)
                continue

            # ═══════════════════════════════════════════════════════════
            # NOISE REDUCTION: Trading denial clause removal
            # ═══════════════════════════════════════════════════════════

            if TRADING_STATEMENTS_REGEX.search(sentence):
                deleted_text = " ".join(
                    m.group(0) for m in TRADING_STATEMENTS_REGEX.finditer(sentence)
                )
                all_discarded.append((url, deleted_text.strip(), "trading_statements"))

                # Remove the trading denial clause
                sentence = TRADING_STATEMENTS_REGEX.sub("", sentence)
                sentence = cleanup_fragment(sentence)

                # PRIORITY 1: Check remaining fragment for category
                remaining_cats = (
                    get_sentence_categories(sentence) if sentence else set()
                )
                remaining_specific_cats = remaining_cats - {"gen", "other"}

                # PRIORITY 2: Check deleted clause for category
                deleted_cats = get_sentence_categories(deleted_text)
                deleted_specific_cats = deleted_cats - {"gen", "other"}

                # Use remaining fragment category if available (higher priority)
                if remaining_specific_cats:
                    detected_cat = list(remaining_specific_cats)[0]
                    instrument_match = ALL_REGEX.search(sentence)
                    detected_instrument = (
                        instrument_match.group(0) if instrument_match else None
                    )

                    paragraph_category_history.append(
                        (idx, detected_cat, detected_instrument)
                    )
                    global_sentence_history.append(
                        (
                            para_idx,
                            idx,
                            detected_cat,
                            detected_instrument,
                            f"[TRADING-REMAINING] {sentence[:80]}",
                        )
                    )

                # Fall back to deleted clause category if remaining is generic
                elif deleted_specific_cats:
                    detected_cat = list(deleted_specific_cats)[0]
                    instrument_match = ALL_REGEX.search(deleted_text)
                    detected_instrument = (
                        instrument_match.group(0) if instrument_match else None
                    )

                    paragraph_category_history.append(
                        (idx, detected_cat, detected_instrument)
                    )
                    global_sentence_history.append(
                        (
                            para_idx,
                            idx,
                            detected_cat,
                            detected_instrument,
                            f"[TRADING-DELETED] {deleted_text[:80]}",
                        )
                    )

                if not sentence:
                    continue

            # ═══════════════════════════════════════════════════════════
            # NOISE REDUCTION: AOCI-only clause removal
            # ═══════════════════════════════════════════════════════════

            if NON_POSITION_INDICATORS.search(sentence):
                # EXTRACT CATEGORY BEFORE DISCARDING for history tracking
                aoci_cats = get_sentence_categories(sentence)
                aoci_specific_cats = aoci_cats - {"gen", "other"}

                if aoci_specific_cats:
                    detected_cat = list(aoci_specific_cats)[0]
                    instrument_match = ALL_REGEX.search(sentence)
                    detected_instrument = (
                        instrument_match.group(0) if instrument_match else None
                    )

                    # Add to history - this tells us what derivative type the document discusses
                    paragraph_category_history.append(
                        (idx, detected_cat, detected_instrument)
                    )
                    global_sentence_history.append(
                        (
                            para_idx,
                            idx,
                            detected_cat,
                            detected_instrument,
                            f"[AOCI] {sentence[:80]}",
                        )
                    )

                # AOCI statements don't indicate positions → discard entirely
                all_discarded.append((url, sentence, "aoci_or_pnl_only"))
                continue

            # ═══════════════════════════════════════════════════════════
            # NOISE REDUCTION: PnL-only clause removal (with instrument detection)
            # ═══════════════════════════════════════════════════════════

            if PNL_ONLY_NO_POSITION.search(sentence):
                # Check if there's an instrument name (strong signal to keep)
                has_instrument = bool(ALL_REGEX.search(sentence))

                # Check if there's position context
                has_position_context = bool(
                    POSITION_CONTEXT_INDICATORS.search(sentence)
                )

                if has_instrument or has_position_context:
                    # Compound sentence or has instrument: surgically remove PnL part
                    deleted_text = " ".join(
                        m.group(0) for m in PNL_ONLY_NO_POSITION.finditer(sentence)
                    )
                    all_discarded.append(
                        (url, deleted_text.strip(), "pnl_only_removed")
                    )

                    # Remove PnL clause
                    sentence = PNL_ONLY_NO_POSITION.sub("", sentence)
                    sentence = cleanup_fragment(sentence)

                    # PRIORITY 1: Check remaining fragment for category
                    remaining_cats = (
                        get_sentence_categories(sentence) if sentence else set()
                    )
                    remaining_specific_cats = remaining_cats - {"gen", "other"}

                    # PRIORITY 2: Check deleted PnL clause for category
                    pnl_cats = get_sentence_categories(deleted_text)
                    pnl_specific_cats = pnl_cats - {"gen", "other"}

                    # Use remaining fragment category if available (higher priority)
                    if remaining_specific_cats:
                        detected_cat = list(remaining_specific_cats)[0]
                        instrument_match = ALL_REGEX.search(sentence)
                        detected_instrument = (
                            instrument_match.group(0) if instrument_match else None
                        )

                        paragraph_category_history.append(
                            (idx, detected_cat, detected_instrument)
                        )
                        global_sentence_history.append(
                            (
                                para_idx,
                                idx,
                                detected_cat,
                                detected_instrument,
                                f"[PNL-REMAINING] {sentence[:80]}",
                            )
                        )

                    # Fall back to deleted clause category
                    elif pnl_specific_cats:
                        detected_cat = list(pnl_specific_cats)[0]
                        instrument_match = ALL_REGEX.search(deleted_text)
                        detected_instrument = (
                            instrument_match.group(0) if instrument_match else None
                        )

                        paragraph_category_history.append(
                            (idx, detected_cat, detected_instrument)
                        )
                        global_sentence_history.append(
                            (
                                para_idx,
                                idx,
                                detected_cat,
                                detected_instrument,
                                f"[PNL-DELETED] {deleted_text[:80]}",
                            )
                        )

                    if not sentence:
                        continue
                else:
                    # Pure PnL with no instrument → but still check for category signal
                    pnl_cats = get_sentence_categories(sentence)
                    pnl_specific_cats = pnl_cats - {"gen", "other"}

                    if pnl_specific_cats:
                        detected_cat = list(pnl_specific_cats)[0]
                        instrument_match = ALL_REGEX.search(sentence)
                        detected_instrument = (
                            instrument_match.group(0) if instrument_match else None
                        )

                        # Track even though discarding
                        paragraph_category_history.append(
                            (idx, detected_cat, detected_instrument)
                        )
                        global_sentence_history.append(
                            (
                                para_idx,
                                idx,
                                detected_cat,
                                detected_instrument,
                                f"[PNL ONLY] {sentence[:80]}",
                            )
                        )

                    all_discarded.append((url, sentence, "pnl_only_no_position"))
                    continue

            if not ALL_REGEX.search(sentence):
                all_discarded.append((url, sentence, "no_match"))
                continue

            # ═══════════════════════════════════════════════════════════
            # ENHANCED CATEGORY DETECTION WITH LOOKBACK
            # ═══════════════════════════════════════════════════════════

            # Step 1: Detect categories in current sentence
            core_categories = get_sentence_categories(sentence)
            specific_cats = core_categories - {"gen", "other"}

            # Extract instrument for tracking
            current_instrument = None
            instrument_match = ALL_REGEX.search(sentence)
            if instrument_match:
                current_instrument = instrument_match.group(0)

            # ═══════════════════════════════════════════════════════════
            # CASE 1: Generic-only sentence → Apply hierarchical resolution
            # ═══════════════════════════════════════════════════════════
            if not specific_cats:
                resolved_category = resolve_generic_reference(
                    sentence=sentence,
                    paragraph_history=paragraph_category_history,
                    global_history=global_sentence_history,
                    current_para_idx=para_idx,
                )

                if resolved_category and resolved_category not in {"gen", "other"}:
                    # Successfully resolved!
                    specific_cats = {resolved_category}
                    primary = resolved_category
                else:
                    # Could not resolve, treat as generic
                    primary = get_primary_category(core_categories)

                # Build paragraph with context
                parts = [sentence]
                context_indices = {idx}

                # Try to incorporate adjacent sentences
                if idx > 0 and (idx - 1) not in used_indices:
                    prev = sentences[idx - 1]
                    if len(prev) >= MIN_SENTENCE_LENGTH:
                        parts.insert(0, prev)
                        context_indices.add(idx - 1)

                if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
                    nxt = sentences[idx + 1]
                    if len(nxt) >= MIN_SENTENCE_LENGTH:
                        parts.append(nxt)
                        context_indices.add(idx + 1)

                final_paragraphs.append((" ".join(parts), primary))
                used_indices.update(context_indices)

                # Update both histories
                paragraph_category_history.append((idx, primary, current_instrument))
                global_sentence_history.append(
                    (para_idx, idx, primary, current_instrument, sentence[:100])
                )

            # ═══════════════════════════════════════════════════════════
            # CASE 2: Single specific category
            # ═══════════════════════════════════════════════════════════
            elif len(specific_cats) == 1:
                primary = list(specific_cats)[0]
                parts = [sentence]
                context_indices = {idx}

                # Category-compatible context incorporation
                if idx > 0 and (idx - 1) not in used_indices:
                    prev = sentences[idx - 1]
                    if len(prev) >= MIN_SENTENCE_LENGTH:
                        prev_cats = get_sentence_categories(prev)
                        if primary in prev_cats or not (prev_cats - {"gen", "other"}):
                            parts.insert(0, prev)
                            context_indices.add(idx - 1)

                if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
                    nxt = sentences[idx + 1]
                    if len(nxt) >= MIN_SENTENCE_LENGTH:
                        nxt_cats = get_sentence_categories(nxt)
                        if primary in nxt_cats or not (nxt_cats - {"gen", "other"}):
                            parts.append(nxt)
                            context_indices.add(idx + 1)

                final_paragraphs.append((" ".join(parts), primary))
                used_indices.update(context_indices)

                # Update histories AFTER successful classification
                paragraph_category_history.append((idx, primary, current_instrument))
                global_sentence_history.append(
                    (para_idx, idx, primary, current_instrument, sentence[:100])
                )

            # ═══════════════════════════════════════════════════════════
            # CASE 3: Multi-category sentence → Disambiguation
            # ═══════════════════════════════════════════════════════════
            else:
                # Track if ANY variant succeeded (only update history if at least one worked)
                any_variant_succeeded = False
                first_successful_category = None

                for target_cat in specific_cats:
                    pure_variant = generate_single_category_variant(
                        sentence, target_cat, core_categories
                    )

                    if pure_variant:
                        parts = [pure_variant]

                        # Context incorporation with excision
                        if idx > 0 and (idx - 1) not in used_indices:
                            prev = sentences[idx - 1]
                            if len(prev) >= MIN_SENTENCE_LENGTH:
                                prev_cats = get_sentence_categories(prev)
                                if target_cat in prev_cats or not (
                                    prev_cats - {"gen", "other"}
                                ):
                                    clean_prev = generate_single_category_variant(
                                        prev, target_cat, prev_cats
                                    )
                                    if clean_prev:
                                        parts.insert(0, clean_prev)

                        if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
                            nxt = sentences[idx + 1]
                            if len(nxt) >= MIN_SENTENCE_LENGTH:
                                nxt_cats = get_sentence_categories(nxt)
                                if target_cat in nxt_cats or not (
                                    nxt_cats - {"gen", "other"}
                                ):
                                    clean_nxt = generate_single_category_variant(
                                        nxt, target_cat, nxt_cats
                                    )
                                    if clean_nxt:
                                        parts.append(clean_nxt)

                        final_paragraphs.append((" ".join(parts), target_cat))
                        any_variant_succeeded = True

                        # Track first successful category for history
                        if first_successful_category is None:
                            first_successful_category = target_cat
                    else:
                        all_discarded.append(
                            (
                                url,
                                sentence,
                                f"disambiguation_excision_failed_{target_cat}",
                            )
                        )

                # Update histories ONLY if at least one variant succeeded
                # Use the first successful category as the "dominant" one for future lookback
                if any_variant_succeeded and first_successful_category:
                    paragraph_category_history.append(
                        (idx, first_successful_category, current_instrument)
                    )
                    global_sentence_history.append(
                        (
                            para_idx,
                            idx,
                            first_successful_category,
                            current_instrument,
                            sentence[:100],
                        )
                    )

                used_indices.add(idx)
    # -------------------------------------------------------------------------
    # FINAL SAFETY CHECK: Ensure instrument name survived cleaning
    # -------------------------------------------------------------------------
    # Filter out sentences where the cleaning process accidentally stripped
    # the actual instrument name (e.g., reducing "We use swaps to hedge" -> "We use to hedge")

    validated_paragraphs = []

    # Assuming final_paragraphs is a list of (text, category) tuples based on your Phase 2 script
    # If it is just a list of strings, remove the unpacking.
    for item in final_paragraphs:
        # Handle both tuple (text, cat) and string formats dynamically
        text = item[0] if isinstance(item, tuple) else item

        # strict=False: Allows "contracts", "instruments", "derivatives" (Broader)
        # strict=True:  Requires "ir swaps", "forward contract", "call options" (Stricter)
        if check_for_instrument(text, strict=False):
            validated_paragraphs.append(item)
        else:
            # Log it as a specific discard reason so you can debug regex over-pruning
            all_discarded.append((url, text, "lost_instrument_reference"))
    final_paragraphs = validated_paragraphs
    return final_paragraphs, all_discarded


def resolve_generic_reference(
    sentence: str,
    paragraph_history: List[Tuple[int, str, Optional[str]]],
    global_history: List[Tuple[int, int, str, Optional[str], str]],
    current_para_idx: int,
) -> Optional[str]:
    """
    Resolve generic derivative references using hierarchical context.

    Resolution Strategy (in priority order):
    1. Current sentence context signals (debt → IR, currency → FX)
    2. Within-paragraph lookback (previous sentences in same paragraph)
    3. Cross-paragraph lookback (sentence-by-sentence from previous paragraphs)

    Args:
        sentence: Current generic sentence
        paragraph_history: List of (sent_idx, category, instrument) from current paragraph
        global_history: List of (para_idx, sent_idx, category, instrument, text) from all paragraphs
        current_para_idx: Index of current paragraph

    Returns:
        Resolved category or None
    """

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 1: Check for context signals in current sentence
    # ═══════════════════════════════════════════════════════════
    context_scores = {}
    for cat, ctx_regex in CATEGORY_CONTEXT_MAP.items():
        if cat == "gen":
            continue
        matches = ctx_regex.findall(sentence)
        if matches:
            context_scores[cat] = len(matches)

    if context_scores:
        # Found strong context in current sentence
        return max(context_scores.items(), key=lambda x: x[1])[0]

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 2: Within-paragraph lookback (HIGHEST PRIORITY)
    # ═══════════════════════════════════════════════════════════
    # Check if sentence has anaphoric references
    has_anaphoric = bool(LOOSE_GEN_REGEX.search(sentence))

    if has_anaphoric and paragraph_history:
        # Use the most recent category from this paragraph
        last_cat_in_para = paragraph_history[-1][1]
        if last_cat_in_para not in {"gen", "other"}:
            return last_cat_in_para

    # Even without anaphoric references, if we're in same paragraph and
    # haven't seen a category change, inherit previous category
    if paragraph_history:
        last_cat_in_para = paragraph_history[-1][1]
        last_instrument_in_para = paragraph_history[-1][2]

        # Check if the last instrument is still relevant
        if last_instrument_in_para:
            # Very weak check: if last instrument was mentioned recently, inherit
            if last_cat_in_para not in {"gen", "other"}:
                return last_cat_in_para

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 3: Cross-paragraph lookback (SENTENCE-BY-SENTENCE)
    # ═══════════════════════════════════════════════════════════
    if has_anaphoric and global_history:
        # Look backwards through ALL previous sentences across ALL paragraphs
        # Start from most recent and work backwards
        for para_idx, sent_idx, category, instrument, text in reversed(global_history):
            # Only consider sentences from previous paragraphs
            if para_idx >= current_para_idx:
                continue

            # Found a specific category in a previous sentence
            if category not in {"gen", "other"}:
                # Optional: Add proximity check - only look back N sentences
                # For now, we take the most recent specific category
                return category

        # Alternative strategy: look for the most common category in recent history
        # This handles cases where categories alternate
        recent_categories = []
        lookback_limit = min(5, len(global_history))  # Look back max 5 sentences

        for para_idx, sent_idx, category, instrument, text in reversed(
            global_history[-lookback_limit:]
        ):
            if para_idx >= current_para_idx:
                continue
            if category not in {"gen", "other"}:
                recent_categories.append(category)

        if recent_categories:
            # Use most frequent category in recent history
            from collections import Counter

            most_common = Counter(recent_categories).most_common(1)
            if most_common:
                return most_common[0][0]

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 4: Instrument-based inference (WEAKEST)
    # ═══════════════════════════════════════════════════════════
    # Look for any recent instrument mention in global history
    if global_history:
        for para_idx, sent_idx, category, instrument, text in reversed(global_history):
            if para_idx >= current_para_idx:
                continue

            if instrument:
                for cat in ["ir", "fx", "cp", "eq"]:
                    cat_regex = {
                        "ir": IR_REGEX,
                        "fx": FX_REGEX,
                        "cp": CP_REGEX,
                        "eq": EQ_REGEX,
                    }[cat]
                    if cat_regex.search(instrument):
                        return cat

    # Could not resolve
    return None


# =============================================================================
# WORKER FUNCTION (NO DB ACCESS)
# =============================================================================


def process_item_buffered(
    item: Tuple[str, str], report_data_map: dict
) -> Optional[Tuple]:
    """
    Worker function to process a single URL's matches.
    Returns data instead of writing to database.
    """
    url, matches_json = item
    try:
        strict_matches, discarded = filter_matches_with_disambiguation(matches_json, url)

        if not strict_matches:
            return None

        # Get metadata from the passed-in map
        cik, year = report_data_map.get(url, (None, None))
        return (url, strict_matches, cik, year, discarded)
    except Exception:
        return None


# =============================================================================
# MAIN PROCESSING FUNCTION
# =============================================================================


def process_and_filter_database():
    """Main function to filter database with buffered batch writes."""
    print("=" * 80)
    print("🔧 DATABASE NOISE REDUCTION WITH BATCHED BUFFERED WRITES")
    print("=" * 80)

    # Initialize database
    print("\n📦 Initializing clean database...")
    create_clean_db()

    # Get already processed URLs
    print(f"🔍 Checking for previously processed URLs in {CLEAN_DB_PATH}...")
    processed_urls = get_processed_urls_from_clean_db()
    if processed_urls:
        print(
            f"  • Found {len(processed_urls):,} already processed URLs. They will be skipped."
        )

    # Fetch source data
    print(f"📖 Reading from {SOURCE_DB_PATH}...")
    source_data = get_source_data()

    if not source_data:
        print("❌ No data found in source database.")
        return

    # Filter out already processed URLs
    unprocessed_data = [item for item in source_data if item[0] not in processed_urls]
    if not unprocessed_data:
        print("✅ All URLs have already been processed. Nothing to do.")
        return

    print("🧠 Loading report metadata into memory...")
    report_data_map = get_all_report_data()
    print(f"  • Loaded metadata for {len(report_data_map)} reports.")

    print(f"📊 Found {len(unprocessed_data)} new URLs to process\n")

    global result_buffer, discard_buffer
    result_buffer = []
    discard_buffer = []

    last_flush = time.time()

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Use map() with chunksize for better task batching
        results_iter = executor.map(
            process_item_buffered,
            unprocessed_data,
            [report_data_map] * len(unprocessed_data),
            chunksize=CHUNK_SIZE,
        )

        for result in tqdm(
            results_iter, total=len(unprocessed_data), desc="Filtering URLs"
        ):
            if result is None:
                continue

            url, matches, cik, year, discarded = result
            result_buffer.append((url, matches, cik, year))
            discard_buffer.extend(discarded)

            # Periodic flush
            if len(result_buffer) >= BATCH_SIZE or (
                time.time() - last_flush > FLUSH_INTERVAL
            ):
                flush_buffers()
                last_flush = time.time()

    # Final flush
    if result_buffer or discard_buffer:
        print("\n💾 Final buffer flush...")
        flush_buffers(force=True)

    print_discard_summary()


def print_discard_summary():
    """Print summary of discarded sentences by category."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "SELECT discard_reason, COUNT(*) as count FROM discarded_sentences GROUP BY discard_reason ORDER BY count DESC"
        )
        stats = c.fetchall()

        print("\n" + "=" * 80)
        print("📊 DISCARDED SENTENCES SUMMARY")
        print("=" * 80)

        total_discarded = sum(count for _, count in stats)

        for reason, count in stats:
            reason_display = reason.replace("_", " ").title()
            print(f"  • {reason_display}: {count:,}")

        print(f"\n  Total Discarded: {total_discarded:,}")
        print(f"  View details in 'discarded_sentences' table")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"⚠️  Error reading discard summary: {e}")
    finally:
        conn.close()


# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
if __name__ == "__main__":
    # Run the filtering process
    process_and_filter_database()

# %%
