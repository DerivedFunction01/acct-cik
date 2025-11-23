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

import re
import json
import re
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
    DEFINITION_INDICATORS,
    IR_REGEX,
    FX_REGEX,
    CP_REGEX,
    EQ_REGEX,
    STRICT_GEN_REGEX,
    SOFT_GEN_REGEX,
    SENTENCE_SPLIT_PATTERN,
    MIN_SENTENCE_LENGTH,
    TRADING_STATEMENTS_REGEX,
    CATEOGRY_REGEX,
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
    """Create unified clean database with category classification support and discard tracking."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        # Main table for high-confidence matches
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS webpage_result (
                url TEXT PRIMARY KEY,
                matches TEXT
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
    Only runs if batch is full or force=True.
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

        # 1. Flush main results
        if result_buffer:
            c.executemany(
                """
                INSERT OR IGNORE INTO webpage_result (url, matches) 
                VALUES (?, ?)
                """,
                [(url, json.dumps(matches)) for url, matches, _, _ in result_buffer],
            )
            c.executemany(
                """
                INSERT OR IGNORE INTO report_data (url, cik, year) 
                VALUES (?, ?, ?)
                """,
                [
                    (url, cik, year)
                    for url, matches, cik, year in result_buffer
                    if cik is not None
                ],
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
# FILTERING FUNCTIONS
# =============================================================================
# Add to derivative_regex.py or filter_database.py

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
    """
    try:
        matches = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return [], []

    if not isinstance(matches, list):
        return [], []

    final_paragraphs = []  # Output: List[(text, category_label)]
    all_discarded = []  # Output: List[(url, sentence, reason)]

    for match in matches:
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(match)]
        used_indices = set()

        for idx, sentence in enumerate(sentences):
            if idx in used_indices:
                continue

            # ═══════════════════════════════════════════════════════════
            # VALIDATION PHASE: Length and format requirements
            # ═══════════════════════════════════════════════════════════

            if len(sentence) < MIN_SENTENCE_LENGTH:
                all_discarded.append((url, sentence, "too_short"))
                continue
            
            # ═══════════════════════════════════════════════════════════
            # DEFINITION REMOVAL (before any context incorporation)
            # ═══════════════════════════════════════════════════════════
            
            if DEFINITION_INDICATORS.search(sentence):
                all_discarded.append((url, sentence, "definition_boilerplate"))
                used_indices.add(idx)  # Mark as processed to prevent context reuse
                continue

            # ═══════════════════════════════════════════════════════════
            # NOISE REDUCTION: Trading denial clause removal
            # ═══════════════════════════════════════════════════════════

            if TRADING_STATEMENTS_REGEX.search(sentence):
                deleted_text = " ".join(
                    m.group(0) for m in TRADING_STATEMENTS_REGEX.finditer(sentence)
                )
                matches_found = CATEOGRY_REGEX.findall(sentence)
                instrument = matches_found[0] if matches_found else ""
                all_discarded.append((url, deleted_text.strip(), "trading_statements"))

                sentence = TRADING_STATEMENTS_REGEX.sub("", sentence)
                sentence = cleanup_fragment(sentence)

                if not sentence:
                    continue
                else:
                    # Preserve instrument context for downstream processing
                    sentence = instrument + " " + sentence if instrument else sentence

            # ═══════════════════════════════════════════════════════════
            # NOISE REDUCTION: AOCI-only clause removal
            # ═══════════════════════════════════════════════════════════

            if NON_POSITION_INDICATORS.search(sentence):
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
                    re.search(
                        r"position|held|outstanding|notional|fair\s+value.*(?:asset|liabilit)|designated|use|employ|manage",
                        sentence,
                        re.IGNORECASE,
                    )
                )

                if has_instrument or has_position_context:
                    # Compound sentence or has instrument: surgically remove PnL part
                    deleted_text = " ".join(
                        m.group(0) for m in PNL_ONLY_NO_POSITION.finditer(sentence)
                    )
                    all_discarded.append(
                        (url, deleted_text.strip(), "pnl_only_removed")
                    )

                    sentence = PNL_ONLY_NO_POSITION.sub("", sentence)
                    sentence = cleanup_fragment(sentence)

                    if not sentence:
                        continue
                    else:
                        # Preserve instrument context if available
                        matches_found = CATEOGRY_REGEX.findall(sentence)
                        instrument = matches_found[0] if matches_found else ""
                        sentence = (
                            instrument + " " + sentence if instrument else sentence
                        )
                else:
                    # Pure PnL with no instrument → discard entirely
                    all_discarded.append((url, sentence, "pnl_only_no_position"))
                    continue
            if not ALL_REGEX.search(sentence):
                all_discarded.append((url, sentence, "no_match"))
                continue

            # ═══════════════════════════════════════════════════════════
            # CATEGORY DETECTION AND DISAMBIGUATION
            # ═══════════════════════════════════════════════════════════

            # Detect all derivative categories present
            core_categories = get_sentence_categories(sentence)

            # Separate specific categories from generic references
            specific_cats = core_categories - {"gen", "other"}

            # ═══════════════════════════════════════════════════════════
            # CASE 1: Generic-only sentence (no specific category detected)
            # ═══════════════════════════════════════════════════════════

            if not specific_cats:
                primary = get_primary_category(core_categories)
                parts = [sentence]

                # Attempt to incorporate adjacent context sentences
                context_indices = {idx}

                # Evaluate previous sentence for compatibility
                if idx > 0 and (idx - 1) not in used_indices:
                    prev = sentences[idx - 1]
                    if len(prev) >= MIN_SENTENCE_LENGTH:
                        parts.insert(0, prev)
                        context_indices.add(idx - 1)

                # Evaluate subsequent sentence for compatibility
                if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
                    nxt = sentences[idx + 1]
                    if len(nxt) >= MIN_SENTENCE_LENGTH:
                        parts.append(nxt)
                        context_indices.add(idx + 1)

                final_paragraphs.append((" ".join(parts), primary))
                used_indices.update(context_indices)

            # ═══════════════════════════════════════════════════════════
            # CASE 2: Single specific category (no disambiguation required)
            # ═══════════════════════════════════════════════════════════

            elif len(specific_cats) == 1:
                primary = list(specific_cats)[0]
                parts = [sentence]
                context_indices = {idx}

                # Evaluate previous sentence for category compatibility
                if idx > 0 and (idx - 1) not in used_indices:
                    prev = sentences[idx - 1]
                    if len(prev) >= MIN_SENTENCE_LENGTH:
                        prev_cats = get_sentence_categories(prev)
                        # Compatibility check: same category OR generic
                        if primary in prev_cats or not (prev_cats - {"gen", "other"}):
                            parts.insert(0, prev)
                            context_indices.add(idx - 1)

                # Evaluate subsequent sentence for category compatibility
                if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
                    nxt = sentences[idx + 1]
                    if len(nxt) >= MIN_SENTENCE_LENGTH:
                        nxt_cats = get_sentence_categories(nxt)
                        if primary in nxt_cats or not (nxt_cats - {"gen", "other"}):
                            parts.append(nxt)
                            context_indices.add(idx + 1)

                final_paragraphs.append((" ".join(parts), primary))
                used_indices.update(context_indices)

            # ═══════════════════════════════════════════════════════════
            # CASE 3: Multi-category sentence - Apply disambiguation protocol
            # ═══════════════════════════════════════════════════════════

            else:
                # Generate independent variant for each detected category
                for target_cat in specific_cats:
                    # Apply terminology excision for conflicting categories
                    pure_variant = generate_single_category_variant(
                        sentence, target_cat, core_categories
                    )

                    if pure_variant:
                        # Construct paragraph with compatible context
                        parts = [pure_variant]

                        # Evaluate and incorporate previous sentence if compatible
                        if idx > 0 and (idx - 1) not in used_indices:
                            prev = sentences[idx - 1]
                            if len(prev) >= MIN_SENTENCE_LENGTH:
                                prev_cats = get_sentence_categories(prev)
                                if target_cat in prev_cats or not (
                                    prev_cats - {"gen", "other"}
                                ):
                                    # Apply same excision process to context sentence
                                    clean_prev = generate_single_category_variant(
                                        prev, target_cat, prev_cats
                                    )
                                    if clean_prev:
                                        parts.insert(0, clean_prev)

                        # Evaluate and incorporate subsequent sentence if compatible
                        if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
                            nxt = sentences[idx + 1]
                            if len(nxt) >= MIN_SENTENCE_LENGTH:
                                nxt_cats = get_sentence_categories(nxt)
                                if target_cat in nxt_cats or not (
                                    nxt_cats - {"gen", "other"}
                                ):
                                    # Apply same excision process to context sentence
                                    clean_nxt = generate_single_category_variant(
                                        nxt, target_cat, nxt_cats
                                    )
                                    if clean_nxt:
                                        parts.append(clean_nxt)

                        final_paragraphs.append((" ".join(parts), target_cat))
                    else:
                        # Excision resulted in invalid output - track for analysis
                        all_discarded.append(
                            (
                                url,
                                sentence,
                                f"disambiguation_excision_failed_{target_cat}",
                            )
                        )

                # Mark sentence as processed to prevent duplicate handling
                used_indices.add(idx)

    return final_paragraphs, all_discarded


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
