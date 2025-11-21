# =============================================================================
# DATABASE NOISE REDUCTION SCRIPT WITH CATEGORY CLASSIFICATION
# =============================================================================
# Filters derivative database using smart regex patterns and classifies by type
# Creates unified clean_web_data.db with keyword matches for MNLI comparison
# Tracks discard reasons with categorized exclusion patterns
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
CHUNK_SIZE = 500  # Number of items to process in each parallel chunk
SOURCE_DB_PATH = "web_data.db"
CLEAN_DB_PATH = "clean_web_data.db"

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
    "officer",
    "director",
]

# Section 2: Legal/Litigation
LEGAL_LITIGATION_KEYWORDS = [
    "lawsuit",
    "civil action",
    "convicted",
    "litigation",
    "defend",
    "court",
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
        "commodity index",
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
    ]
    pattern = build_alternation(base_with_required_suffixes + specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_soft_gen_regex() -> re.Pattern:
    """Build soft General derivatives regex (secondary indicators)."""
    specific_phrases = [
        "(?:instruments?|contracts?) are designated",
        "hedge of the net investment",
        "net investment hedges?",
        "cash flow hedges?",
        "fair value hedges?",
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
        # Discard tracking table - tracks what was filtered out and why
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discard_stats (
                discard_reason TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Error creating clean database: {e}")
    finally:
        # Initialize discard_stats with the three categories
        c.execute(
            "INSERT OR IGNORE INTO discard_stats (discard_reason, count) VALUES (?, ?)",
            ("equity_compensation", 0),
        )
        c.execute(
            "INSERT OR IGNORE INTO discard_stats (discard_reason, count) VALUES (?, ?)",
            ("legal_litigation", 0),
        )
        c.execute(
            "INSERT OR IGNORE INTO discard_stats (discard_reason, count) VALUES (?, ?)",
            ("accounting_standards", 0),
        )
        c.execute(
            "INSERT OR IGNORE INTO discard_stats (discard_reason, count) VALUES (?, ?)",
            ("too_short", 0),
        )
        c.execute(
            "INSERT OR IGNORE INTO discard_stats (discard_reason, count) VALUES (?, ?)",
            ("no_match", 0),
        )
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
        # The 'webpage_result' table is the main table for matches.
        # If a URL is here, it has been processed.
        c.execute("SELECT url FROM webpage_result")
        processed_urls = {row[0] for row in c.fetchall()}
        return processed_urls
    except sqlite3.OperationalError:
        # Table might not exist yet on the very first run
        return set()
    finally:
        conn.close()


def increment_discard_stat(reason: str):
    """Increment the count for a specific discard reason."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "UPDATE discard_stats SET count = count + 1 WHERE discard_reason = ?",
            (reason,),
        )
        conn.commit()
    except Exception as e:
        print(f"⚠️  Error incrementing discard stat for {reason}: {e}")
    finally:
        conn.close()


# =============================================================================
# FILTERING FUNCTIONS
# =============================================================================


def is_table_content(match: str) -> bool:
    """Detect if match is table content (starts with | or contains table markers)."""
    return match.strip().startswith("|") or "<table" in match.lower()


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
        return "accounting_standards"
    return None


def filter_matches(matches_json: str) -> Tuple[List[str], str]:
    """
    Filter matches to reduce the paragraph length.

    Returns:
        (new_simple_paragraphs, status)
    """
    try:
        matches = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return [], "Invalid JSON"

    if not isinstance(matches, list):
        return [], "Not a list"

    new_paragraphs = []
    used = set()

    for match in matches:
        sentences = SENTENCE_SPLIT_PATTERN.split(match)

        for idx, sentence in enumerate(sentences):
            sentence = sentence.strip()

            if len(sentence) < MIN_SENTENCE_LENGTH:
                increment_discard_stat("too_short")
                continue

            exclusion_category = check_exclusion_category(sentence)
            if exclusion_category:
                increment_discard_stat(exclusion_category)
                continue

            if not STRICT_REGEX.search(sentence):
                increment_discard_stat("no_match")
                continue

            # Check if any of the context indices are already used
            context_indices = {idx - 1, idx, idx + 1}
            if context_indices & used:
                continue

            paragraph_parts = []

            # Add previous sentence if valid
            if idx > 0:
                prev = sentences[idx - 1].strip()
                if len(prev) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(
                    prev
                ):
                    paragraph_parts.append(prev)

            # Add current sentence
            paragraph_parts.append(sentence)

            # Add next sentence if valid
            if idx + 1 < len(sentences):
                nxt = sentences[idx + 1].strip()
                if len(nxt) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(
                    nxt
                ):
                    paragraph_parts.append(nxt)

            # Mark indices as used
            used.update(context_indices)

            # Join into a paragraph
            new_paragraphs.append(" ".join(paragraph_parts))

    # Final check: if the only match is extremely short, we can reject it
    if len(new_paragraphs) == 1 and len(new_paragraphs[0].strip()) < 50:
        increment_discard_stat("too_short")
        return [], "Filtered"

    return new_paragraphs, "Filtered"


def process_item(item: Tuple[str, str]) -> Optional[Tuple]:
    """
    Worker function to process a single URL's matches.
    Classifies sentences by derivative type for MNLI comparison.
    """
    url, matches_json = item
    try:
        (
            strict_matches,
            status,
        ) = filter_matches(matches_json)

        # Return None if there's nothing to save
        if not strict_matches:
            return None
        return (
            url,
            strict_matches,
        )
    except Exception:
        return None


# =============================================================================
# SAVE FUNCTIONS
# =============================================================================


def save_full_result_atomically(
    url: str,
    strict_matches: List[str],
    cik: Optional[int],
    year: Optional[int],
) -> bool:
    """
    Saves the complete processed result for a single URL in a single atomic transaction.
    """
    conn = sqlite3.connect(CLEAN_DB_PATH, timeout=10)
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")

        # 1. Save strict matches and report data
        if strict_matches:
            c.execute(
                "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                (url, json.dumps(strict_matches)),
            )
            if cik is not None and year is not None:
                c.execute(
                    "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                    (url, cik, year),
                )
        c.execute("COMMIT")
        return True
    except Exception as e:
        c.execute("ROLLBACK")
        print(f"❌ Transaction failed for {url}, rolling back. Error: {e}")
        return False
    finally:
        conn.close()


def print_discard_stats():
    """Print discard statistics from the database."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT discard_reason, count FROM discard_stats ORDER BY count DESC")
        stats = c.fetchall()

        print("\n" + "=" * 80)
        print("📊 DISCARD STATISTICS")
        print("=" * 80)

        total_discarded = sum(count for _, count in stats)

        for reason, count in stats:
            reason_display = reason.replace("_", " ").title()
            print(f"  • {reason_display}: {count:,}")

        print(f"\n  Total Discarded: {total_discarded:,}")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"⚠️  Error reading discard stats: {e}")
    finally:
        conn.close()


# =============================================================================
# MAIN PROCESSING FUNCTION
# =============================================================================


def process_and_filter_database():
    """Main function to filter database and create classified clean database."""
    print("=" * 80)
    print("🔧 DATABASE NOISE REDUCTION WITH CATEGORY CLASSIFICATION")
    print("=" * 80)

    # Initialize database
    print("\n📦 Initializing clean database...")
    create_clean_db()

    # Get already processed URLs to make the script resumable
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
        print_discard_stats()
        return

    print("🧠 Loading report metadata into memory...")
    report_data_map = get_all_report_data()
    print(f"  • Loaded metadata for {len(report_data_map)} reports.")

    print(f"📊 Found {len(unprocessed_data)} new URLs to process\n")

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        results_iterator = executor.map(
            process_item, unprocessed_data, chunksize=CHUNK_SIZE
        )

        for result in tqdm(
            results_iterator, total=len(unprocessed_data), desc="Filtering URLs"
        ):
            if result is None:
                continue

            (
                url,
                strict_matches,
            ) = result
            # Get metadata from the in-memory map
            metadata = report_data_map.get(url)
            cik = metadata[0] if metadata else None
            year = metadata[1] if metadata else None

            # Atomically save all results for this URL
            save_full_result_atomically(url, strict_matches, cik, year)

    # Print final statistics
    print_discard_stats()


# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
if __name__ == "__main__":
    # Run the filtering process
    process_and_filter_database()

# %%
