# DATABASE NOISE REDUCTION SCRIPT WITH CATEGORY CLASSIFICATION
# =============================================================================
# Filters derivative database using smart regex patterns and classifies by type
# Creates unified clean_web_data.db with keyword matches for MNLI comparison
# Uses ProcessPoolExecutor + buffered batch writes for optimal performance
# =============================================================================
# %%
import sqlite3
import json
import re
from pathlib import Path
from tqdm import tqdm
from typing import List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time

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
CLEAN_DB_PATH = "clean_web_data.db"

# In-memory buffers (protected by main process only)
result_buffer = []  # List of (url, matches, cik, year)
discard_buffer = []  # List of (url, sentence, reason)

# =============================================================================
# SHARED COMPONENTS (from regex builder)
# =============================================================================
# Compile once at module level
SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z])|"  # Period/exclamation/question + whitespace + uppercase
    r"(?<=[a-z])(?=[A-Z])"  # camelCase boundaries (extraction artifacts)
)

# Unambiguous derivative base types (used in gen regex)
UNAMBIGUOUS_BASE_TYPES = [
    "swaps?",
    "forwards?",
    "caps?",
    "floors?",
    "collars?",
    "derivatives?",
    "swaptions?",
    "locks?",
]

# Ambiguous base types (only safe when prefixed by category)
AMBIGUOUS_BASE_TYPES = [
    "futures?",
    "options?",
]

# All base types (for category-specific regexes that prefix them)
ALL_BASE_TYPES = UNAMBIGUOUS_BASE_TYPES + AMBIGUOUS_BASE_TYPES

ALL_SUFFIXES = [
    "agreements?",
    "contracts?",
    "instruments?",
    "arrangements?",
    "assets?",
    "liabilit(?:y|ies)",
    "commitments?",
    "positions?",
    "strateg(?:ies|y)",
]

COMMON_COMMODITIES = [
    "agricultural",
    "aluminum",
    "asphalt",
    "base metal",
    "biodiesel",
    "biomass",
    "bitumen",
    "cement",
    "chemical",
    "coal",
    "cocoa",
    "coffee",
    "concrete",
    "copper",
    "corn",
    "cotton",
    "crude oil",
    "dairy",
    "diesel fuel",
    "electricity",
    "energy",
    "ethanol",
    "feedstock",
    "fertilizer",
    "fuel",
    "gas",
    "gasoline",
    "grain",
    "gravel",
    "hardwood lumber",
    "iron",
    "limestone",
    "livestock",
    "log",
    "lumber",
    "metal",
    "mineral",
    "natural gas",
    "nitrogen",
    "paper",
    "ore",
    "petrochemical",
    "petroleum",
    "phosphate",
    "plastic",
    "plywood",
    "polymer",
    "potash",
    "precious metal",
    "pulp",
    "raw material",
    "resin",
    "rubber",
    "salt",
    "sand",
    "soda ash",
    "softwood lumber",
    "soybean",
    "steel",
    "sugar",
    "sulfur",
    "textile",
    "timber",
    "titanium",
    "uranium",
    "wood",
    "wood chip",
    "wood pellet",
    "wool",
]

# =============================================================================
# CATEGORIZED EXCLUSION PATTERNS
# =============================================================================

# Section 1: Employee Equity Compensation
EQUITY_COMP_KEYWORDS = [
    "stock option",
    "stock award",
    "restricted stock",
    "RSU",
    "compensation",
    "employee",
    "share-based",
    "vesting",
    "exercisable",
    "stock purchase",
    "ESPP",
    "bonus",
    "salary",
    "wage",
    "dividend",
    "stock split",
    "stock dividend",
    "outstanding shares",
    "share repurchase",
    "buyback",
    "warrant",
    "hedge fund",
]

# Section 2: Legal/Litigation
LEGAL_LITIGATION_KEYWORDS = [
    "lawsuit",
    "civil action",
    "officer",
    "director",
    "convicted",
]

# Section 3: Accounting Standards
ACCOUNTING_STANDARDS_KEYWORDS = [
    "fasb",
    "sfas",
    "s.f.a.s",
    "asc 815",
    "a.s.c 815",
    "Credit Enhancement and Other Support",
    "Regulation AB",
    "regulat",
    "adoption",
    "amendment",
]

# Minimum sentence length to consider
MIN_SENTENCE_LENGTH = 50


def build_exclude_regex(keywords: List[str]) -> re.Pattern:
    """Build regex for excluding noise keywords."""
    escaped_keywords = [re.escape(kw) for kw in keywords]
    pattern = "|".join(escaped_keywords)
    return re.compile(pattern, re.IGNORECASE)


EXCLUDE_REGEX_EQUITY_COMP = build_exclude_regex(EQUITY_COMP_KEYWORDS)
EXCLUDE_REGEX_LEGAL_LITIGATION = build_exclude_regex(LEGAL_LITIGATION_KEYWORDS)
EXCLUDE_REGEX_ACCOUNTING_STD = build_exclude_regex(ACCOUNTING_STANDARDS_KEYWORDS)

# Combined exclusion regex (tested first - very fast)
COMBINED_EXCLUDE_REGEX = re.compile(
    f"({EXCLUDE_REGEX_EQUITY_COMP.pattern})|({EXCLUDE_REGEX_LEGAL_LITIGATION.pattern})|({EXCLUDE_REGEX_ACCOUNTING_STD.pattern})",
    re.IGNORECASE,
)

# =============================================================================
# REGEX PATTERN BUILDERS
# =============================================================================


def build_alternation(items: List[str]) -> str:
    """Build optimized alternation pattern from list of items."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f'(?:{"|".join(items)})'


def build_smart_regex(
    core_terms: List[str], context_terms: List[str], specific_phrases: List[str]
) -> str:
    """Build regex combining core terms with context and specific phrases."""
    core_pattern = build_alternation(core_terms)
    follow_pattern = build_alternation(context_terms)
    pattern1 = f"{core_pattern}[- ]{follow_pattern}"
    pattern2 = build_alternation(specific_phrases)
    return build_alternation([pattern1, pattern2])


def build_ir_regex() -> re.Pattern:
    """Build optimized Interest Rate derivatives regex."""
    core_terms = [
        "interest[- ]rate",
        "single[- ]currency",
        "Eurodollar",
        "SOFR",
        "SONIA",
        "LIBOR",
        "LIBOR[- ]based",
        "EURIBOR",
        "(?:treasury|forward|fixed|floating|variable|benchmark)[- ]rate",
    ]
    specific_phrases = [
        "zero[- ]coupon swap",
        "FRA",
        "treasury lock",
        "basis swap",
    ]
    pattern = build_smart_regex(
        core_terms, ALL_BASE_TYPES + ALL_SUFFIXES, specific_phrases
    )
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_fx_regex() -> re.Pattern:
    """Build optimized Foreign Exchange derivatives regex."""
    core_terms = [
        "foreign[- ]exchange",
        "forward[- ]exchange",
        "currency",
        "currency[- ]rate",
        "exchange[- ]rate",
        "FX",
        "forex",
    ]
    specific_phrases = [
        "NDF",
        "deliverable forwards?",
    ]
    pattern = build_smart_regex(
        core_terms, ALL_BASE_TYPES + ALL_SUFFIXES, specific_phrases
    )
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_cp_regex() -> re.Pattern:
    """Build optimized Commodity Price derivatives regex."""
    base_commodities = ["commodity"]
    modifiers = ["[- ]price", "[- ]related", "[- ]based", "[- ]linked"]
    core_terms = [c for c in base_commodities] + [
        f"{c}{mod}" for c in base_commodities for mod in modifiers
    ]
    core_terms.append("fixed[- ]commodity")
    specific_phrases = [
        "commodity index"
    ]
    pattern = build_smart_regex(core_terms, ALL_BASE_TYPES, specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_eq_regex() -> re.Pattern:
    """Build optimized Equity derivatives regex."""
    core_terms = ["equity", "equity[- ]related"]
    specific_phrases = [
        "call options?",
        "put options?",
    ]
    pattern = build_smart_regex(core_terms, ALL_BASE_TYPES, specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_strict_gen_regex() -> re.Pattern:
    """Build strict General derivatives regex (high confidence only)."""
    base_with_required_suffixes = [
        f"{base}[- ]{suffix}"
        for base in UNAMBIGUOUS_BASE_TYPES
        for suffix in ALL_SUFFIXES
    ]
    specific_phrases = [
        "total[- ]return swaps?",
        "notional (?:amounts?|values?|principals?)",
        "designated as (?:a )?hedges?",
        "hedge of the net investment",
        "net investment hedges?",
        "cash flow hedges?",
        "fair value hedges?",
    ]
    pattern = build_alternation(base_with_required_suffixes + specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_soft_gen_regex() -> re.Pattern:
    """Build soft General derivatives regex (secondary indicators)."""
    specific_phrases = [
        "(?:instruments?|contracts?) are designated",
        "ineffective portion",
        "hedging relationship",
        "hedge accounting",
        "change in fair value of derivatives?",
        "derivative expense",
        "derivative financial instruments?",
        "embedded derivatives?",
        "derivative (?:assets?|liabilities|gains?|losses?|positions?|contracts?|instruments?)",
        "(?:gain|loss) on derivatives?",
        "over[- ]the[- ]counter derivatives?",
    ]
    pattern = build_alternation(specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


# Build all regex patterns
IR_REGEX = build_ir_regex()
FX_REGEX = build_fx_regex()
CP_REGEX = build_cp_regex()
EQ_REGEX = build_eq_regex()
STRICT_GEN_REGEX = build_strict_gen_regex()
SOFT_GEN_REGEX = build_soft_gen_regex()

# Combined regexes
STRICT_REGEX = re.compile(
    r"|".join(
        [
            IR_REGEX.pattern,
            FX_REGEX.pattern,
            CP_REGEX.pattern,
            EQ_REGEX.pattern,
            STRICT_GEN_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)
SOFT_REGEX = SOFT_GEN_REGEX
ALL_REGEX = re.compile(
    r"|".join([STRICT_REGEX.pattern, SOFT_REGEX.pattern]), re.IGNORECASE)

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
        # Discard tracking table - stores discarded sentences for review
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discarded_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                sentence TEXT,
                discard_reason TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
            """
        )

        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS discard_reason_idx ON discarded_sentences (discard_reason)"
        )
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Error creating clean database: {e}")
    finally:
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


def check_exclusion_category(sentence: str) -> Optional[str]:
    """
    Check if sentence matches any exclusion category.
    Returns the category name if it matches, None otherwise.
    """
    if EXCLUDE_REGEX_EQUITY_COMP.search(sentence):
        return "equity_compensation"
    if EXCLUDE_REGEX_LEGAL_LITIGATION.search(sentence):
        return "legal_litigation"
    if EXCLUDE_REGEX_ACCOUNTING_STD.search(sentence):
        # Trick one: we need to make sure no other are matches
        if not STRICT_REGEX.search(sentence):
            return "accounting_standards"
        return "accounting_standards"
    return None


def filter_matches(
    matches_json: str, url: str = ""
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """
    Main filter: strict first, then soft fallback — but NEVER re-use the same sentence.
    Returns (filtered_paragraphs, discarded_list)
    """
    try:
        matches = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return [], []

    if not isinstance(matches, list):
        return [], []

    final_paragraphs = []
    all_discarded = [] # should be empty, roberta will perform it

    # Process each original match block independently
    for match in matches:
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(match)]
        used_indices = set()  # Track used sentence indices in THIS block only
        # We can use Roberta to filter our the system, instead of relying on regex
        for idx, sentence in enumerate(sentences):
            if idx in used_indices:
                continue  # Already used in strict → skip forever
            if len(sentence) < MIN_SENTENCE_LENGTH:
                continue
            if not ALL_REGEX.search(sentence):
                continue
            # No need to check any exclusion category, but we still need to create mini paragraphs, with derivative keywords
            parts = []
            context_indices = {idx}
            if idx > 0 and (idx - 1) not in used_indices:
                prev = sentences[idx - 1]
                if len(prev) >= MIN_SENTENCE_LENGTH:
                    parts.append(prev)
                    context_indices.add(idx - 1)
            parts.append(sentence)

            if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
                nxt = sentences[idx + 1]
                if len(nxt) >= MIN_SENTENCE_LENGTH:
                    parts.append(nxt)
                    context_indices.add(idx + 1)
            final_paragraphs.append(" ".join(parts))
            used_indices.update(context_indices)

        # # === PHASE 1: Strict matching (high precision) ===
        # strict_paragraphs, strict_discarded, strict_used = _process_block_strict(
        #     sentences, used_indices.copy(), url
        # )
        # final_paragraphs.extend(strict_paragraphs)
        # all_discarded.extend(strict_discarded)
        # used_indices.update(strict_used)

        # # === PHASE 2: Soft fallback only on unused sentences ===
        # if (
        #     len(strict_paragraphs) < len(sentences) // 3
        # ):  # heuristic: too few strict hits
        #     soft_paragraphs, soft_discarded, soft_used = _process_block_soft(
        #         sentences, used_indices, url  # pass current used set
        #     )
        #     final_paragraphs.extend(soft_paragraphs)
        #     all_discarded.extend(soft_discarded)
        #     used_indices.update(soft_used)

    return final_paragraphs, all_discarded


# def _process_block_strict(
#     sentences: List[str], used_indices: set, url: str
# ) -> Tuple[List[str], List[Tuple[str, str, str]], set]:
#     """Internal: strict pass on one block."""
#     paragraphs = []
#     discarded = []
#     newly_used = set()

#     for idx, sentence in enumerate(sentences):
#         if idx in used_indices:
#             continue

#         if len(sentence) < MIN_SENTENCE_LENGTH:
#             discarded.append((url, sentence, "too_short"))
#             continue

#         if check_exclusion_category(sentence):
#             reason = check_exclusion_category(sentence)
#             discarded.append((url, sentence, reason))
#             continue

#         if not STRICT_REGEX.search(sentence):
#             discarded.append((url, sentence, "no_strict_match"))
#             continue

#         # Build paragraph from current + optional prev/next (if not used)
#         parts = []
#         context_indices = {idx}

#         if idx > 0 and (idx - 1) not in used_indices:
#             prev = sentences[idx - 1]
#             if len(prev) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(prev):
#                 parts.append(prev)
#                 context_indices.add(idx - 1)

#         parts.append(sentence)

#         if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
#             nxt = sentences[idx + 1]
#             if len(nxt) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(nxt):
#                 parts.append(nxt)
#                 context_indices.add(idx + 1)

#         paragraphs.append(" ".join(parts))
#         newly_used.update(context_indices)

#     return paragraphs, discarded, newly_used


# def _process_block_soft(
#     sentences: List[str], used_indices: set, url: str
# ) -> Tuple[List[str], List[Tuple[str, str, str]], set]:
#     """Internal: soft pass — only on sentences NOT used in strict phase."""
#     paragraphs = []
#     discarded = []
#     newly_used = set()

#     for idx, sentence in enumerate(sentences):
#         if idx in used_indices:
#             continue  # Already used in strict → skip forever

#         if len(sentence) < MIN_SENTENCE_LENGTH:
#             discarded.append((url, sentence, "too_short_soft"))
#             continue

#         if check_exclusion_category(sentence):
#             reason = check_exclusion_category(sentence)
#             discarded.append((url, sentence, reason))
#             continue

#         if not SOFT_REGEX.search(sentence):
#             discarded.append((url, sentence, "no_soft_match"))
#             continue

#         # Same context logic as strict
#         parts = []
#         context_indices = {idx}

#         if idx > 0 and (idx - 1) not in used_indices:
#             prev = sentences[idx - 1]
#             if len(prev) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(prev):
#                 parts.append(prev)
#                 context_indices.add(idx - 1)

#         parts.append(sentence)

#         if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
#             nxt = sentences[idx + 1]
#             if len(nxt) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(nxt):
#                 parts.append(nxt)
#                 context_indices.add(idx + 1)

#         paragraphs.append(" ".join(parts))
#         newly_used.update(context_indices)

#     return paragraphs, discarded, newly_used


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
        strict_matches, discarded = filter_matches(matches_json, url)

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
