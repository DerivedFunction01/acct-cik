# =============================================================================
# DATABASE NOISE REDUCTION SCRIPT
# =============================================================================
# Filters derivative database using smart regex patterns
# Creates unified clean_web_data.db with:
#   - webpage_result: High confidence derivative sentences
#   - soft_matches: Secondary indicators (hedging, accounting, etc.)
#   - discarded: Noise and excluded content
# =============================================================================

import sqlite3
import json
import re
from pathlib import Path
from tqdm import tqdm
from typing import List, Tuple, Optional
import pandas as pd

# =============================================================================
# CONFIGURATION
# =============================================================================

SOURCE_DB_PATH = "web_data.db"
CLEAN_DB_PATH = "clean_web_data.db"

# Keywords to explicitly exclude (noise reducers)
EXCLUDE_KEYWORDS = [
    "stock option",
    "stock award",
    "restricted stock",
    "RSU",
    "employee compensation",
    "employee stock",
    "stock-based compensation",
    "share-based",
    "compensation expense",
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
    "convertible",
    "conversion",
]

# Minimum sentence length to consider
MIN_SENTENCE_LENGTH = 50

# =============================================================================
# BASE TYPE DEFINITIONS
# =============================================================================

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
ALL_SUFFIXES = ["agreements?", "contracts?", "instruments?"]

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
        "interest[- ]rate",  # Explicit: interest rate
        "single[- ]currency",
        "Eurodollar",
        "SOFR",
        "SONIA",
        "LIBOR",
        "LIBOR[- ]based",
        "EURIBOR",
        "(?:treasury|forward|fixed|floating|variable|benchmark)[- ]rate",  # Require qualifier before "rate"
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
        "exchange",
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
        "commodity index swaps?",
        "commodity index options?",
    ]
    pattern = build_smart_regex(
        core_terms, ALL_BASE_TYPES + ALL_SUFFIXES, specific_phrases
    )
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
    # Only unambiguous base types with suffixes
    base_with_required_suffixes = [
        f"{base}[- ]{suffix}"
        for base in UNAMBIGUOUS_BASE_TYPES
        for suffix in ALL_SUFFIXES
    ]

    specific_phrases = [
        "total[- ]return swaps?",
    ]
    pattern = build_alternation(base_with_required_suffixes + specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_soft_gen_regex() -> re.Pattern:
    """Build soft General derivatives regex (secondary indicators)."""
    specific_phrases = [
        "designated as (?:a )?hedges?",
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
        "notional (?:amounts?|values?|principals?)",
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


# Exclude regex
def build_exclude_regex() -> re.Pattern:
    """Build regex for excluding noise keywords."""
    escaped_keywords = [re.escape(kw) for kw in EXCLUDE_KEYWORDS]
    pattern = "|".join(escaped_keywords)
    return re.compile(pattern, re.IGNORECASE)


EXCLUDE_REGEX = build_exclude_regex()

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def create_clean_db():
    """Create unified clean database with webpage_result (strict) and metadata tables."""
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
            CREATE TABLE IF NOT EXISTS report_metadata (
                url TEXT PRIMARY KEY,
                cik INTEGER,
                year INTEGER,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
            """
        )
        # Soft matches (same schema with url link)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS soft_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                matches TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Discarded/noise (same schema with url link)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discarded (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                matches TEXT,
                rejection_reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        c.execute("CREATE INDEX IF NOT EXISTS cik_idx ON report_metadata (cik)")
        c.execute("CREATE INDEX IF NOT EXISTS year_idx ON report_metadata (year)")
        c.execute("CREATE INDEX IF NOT EXISTS soft_url_idx ON soft_matches (url)")
        c.execute("CREATE INDEX IF NOT EXISTS disc_url_idx ON discarded (url)")
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


def get_report_metadata(url: str) -> Optional[Tuple[int, int]]:
    """Fetch CIK and year for a URL from source database."""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT cik, year FROM report_data 
            WHERE url = ?
            """,
            (url,),
        )
        result = c.fetchone()
        conn.close()
        return result
    except Exception:
        conn.close()
        return None


# =============================================================================
# FILTERING FUNCTIONS
# =============================================================================


def is_table_content(match: str) -> bool:
    """Detect if match is table content (starts with | or contains table markers)."""
    return match.strip().startswith("|") or "<table" in match.lower()


def filter_matches(matches_json: str) -> Tuple[List[str], List[str], List[str], str]:
    """
    Filter matches into strict, soft, and noise categories.
    Splits paragraphs into sentences and filters at sentence level.

    Returns:
        (strict_matches, soft_matches, noise_matches, status)
    """
    try:
        matches = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return [], [], [], "Invalid JSON"

    if not isinstance(matches, list):
        return [], [], [], "Not a list"

    strict = []
    soft = []
    noise = []

    # Compile sentence split pattern
    sentence_split_pattern = re.compile(
        r"(?<=[.!?])\s+(?=[A-Z])|"  # Period/exclamation/question + whitespace + uppercase
        r"(?<=[a-z])(?=[A-Z])"  # camelCase boundaries (extraction artifacts)
    )

    for match in matches:
        if not isinstance(match, str):
            noise.append(str(match))
            continue

        # Skip tables entirely
        if is_table_content(match):
            noise.append(match)
            continue

        # Skip very short content
        if len(match) < MIN_SENTENCE_LENGTH:
            noise.append(match)
            continue

        # Exclude noise keywords
        if EXCLUDE_REGEX.search(match):
            noise.append(match)
            continue

        # Split paragraph into sentences
        sentences = sentence_split_pattern.split(match)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Filter sentences and categorize
        paragraph_strict = []
        paragraph_soft = []
        paragraph_noise = []

        for sentence in sentences:
            # Check for strict derivative keywords (priority)
            if STRICT_REGEX.search(sentence):
                paragraph_strict.append(sentence)
            # Check for soft derivative keywords
            elif SOFT_REGEX.search(sentence):
                paragraph_soft.append(sentence)
            else:
                paragraph_noise.append(sentence)

        # Add to appropriate lists
        strict.extend(paragraph_strict)
        soft.extend(paragraph_soft)
        noise.extend(paragraph_noise)

    if strict:
        status = "Strict matches found"
    elif soft:
        status = "Soft matches only"
    elif noise:
        status = "Noise only"
    else:
        status = "Empty matches"

    return strict, soft, noise, status


# =============================================================================
# SAVE FUNCTIONS
# =============================================================================


def save_to_clean_db(
    url: str, matches: List[str], cik: Optional[int] = None, year: Optional[int] = None
):
    """Save high-confidence matches to main webpage_result table."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT OR REPLACE INTO webpage_result (url, matches) 
            VALUES (?, ?)
            """,
            (url, json.dumps(matches)),
        )

        if cik is not None and year is not None:
            c.execute(
                """
                INSERT OR REPLACE INTO report_metadata (url, cik, year) 
                VALUES (?, ?, ?)
                """,
                (url, cik, year),
            )

        conn.commit()
    except Exception as e:
        print(f"❌ Error saving to webpage_result: {e}")
    finally:
        conn.close()


def save_to_discarded_db(
    url: str,
    strict_matches: List[str],
    soft_matches: List[str],
    noise_matches: List[str],
):
    """Save categorized discarded content to appropriate tables (all in same DB)."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        if soft_matches:
            c.execute(
                """
                INSERT INTO soft_matches (url, matches) 
                VALUES (?, ?)
                """,
                (url, json.dumps(soft_matches)),
            )

        if noise_matches:
            c.execute(
                """
                INSERT INTO discarded (url, matches, rejection_reason) 
                VALUES (?, ?, ?)
                """,
                (url, json.dumps(noise_matches), "Did not match strict criteria"),
            )

        conn.commit()
    except Exception as e:
        print(f"❌ Error saving to discarded tables: {e}")
    finally:
        conn.close()


# =============================================================================
# MAIN PROCESSING FUNCTION
# =============================================================================


def process_and_filter_database():
    """Main function to filter database and create unified clean database."""
    print("=" * 80)
    print("🔧 DATABASE NOISE REDUCTION")
    print("=" * 80)

    # Initialize database
    print("\n📦 Initializing unified clean database...")
    create_clean_db()

    # Fetch source data
    print(f"📖 Reading from {SOURCE_DB_PATH}...")
    source_data = get_source_data()

    if not source_data:
        print("❌ No data found in source database")
        return

    print(f"📊 Found {len(source_data)} URLs to process\n")

    # Process each URL
    total_kept = 0
    total_soft = 0
    total_noise = 0
    urls_kept = 0
    urls_soft = 0
    urls_noise = 0

    for url, matches_json in tqdm(source_data, desc="Processing URLs", unit="url"):
        strict_matches, soft_matches, noise_matches, status = filter_matches(
            matches_json
        )

        # Get metadata
        metadata = get_report_metadata(url)
        cik = metadata[0] if metadata else None
        year = metadata[1] if metadata else None

        if strict_matches:
            save_to_clean_db(url, strict_matches, cik, year)
            total_kept += len(strict_matches)
            urls_kept += 1

        # Always save to discarded tables (for tracking soft and noise)
        save_to_discarded_db(url, strict_matches, soft_matches, noise_matches)
        total_soft += len(soft_matches)
        total_noise += len(noise_matches)

        if soft_matches:
            urls_soft += 1
        if noise_matches:
            urls_noise += 1

    # Print summary
    print("\n" + "=" * 80)
    print("✅ FILTERING COMPLETE")
    print("=" * 80)
    print(f"\n📊 Summary Statistics:")
    print(f"  • URLs with strict matches: {urls_kept:,}")
    print(f"  • URLs with soft matches: {urls_soft:,}")
    print(f"  • URLs with noise only: {urls_noise:,}")
    print(f"  • Total strict sentences: {total_kept:,}")
    print(f"  • Total soft sentences: {total_soft:,}")
    print(f"  • Total noise sentences: {total_noise:,}")

    total_all = total_kept + total_soft + total_noise
    if total_all > 0:
        strict_pct = (total_kept / total_all) * 100
        soft_pct = (total_soft / total_all) * 100
        noise_pct = (total_noise / total_all) * 100
        print(f"\n📈 Distribution:")
        print(f"  • Strict: {strict_pct:.1f}%")
        print(f"  • Soft: {soft_pct:.1f}%")
        print(f"  • Noise: {noise_pct:.1f}%")

    print(f"\n💾 Database Output: {CLEAN_DB_PATH}")
    print(f"  • webpage_result - High confidence matches (with cik/year metadata)")
    print(f"  • soft_matches - Secondary derivative indicators (linked by url)")
    print(f"  • discarded - True noise content (linked by url)")
    print("=" * 80)

    return {
        "urls_kept": urls_kept,
        "urls_soft": urls_soft,
        "urls_noise": urls_noise,
        "total_kept": total_kept,
        "total_soft": total_soft,
        "total_noise": total_noise,
    }


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def check_clean_db_quality(sample_size: int = 10):
    """Quick quality check of cleaned database."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()

    try:
        c.execute(
            """
            SELECT url, matches FROM webpage_result 
            ORDER BY RANDOM() LIMIT ?
            """,
            (sample_size,),
        )
        samples = c.fetchall()
        conn.close()

        print(f"\n🔍 Quality Check - Sample of {len(samples)} Clean Entries:")
        print("-" * 80)

        for i, (url, matches_json) in enumerate(samples, 1):
            matches = json.loads(matches_json)
            print(f"\n{i}. URL: {url}")
            print(f"   Sentences kept: {len(matches)}")
            if matches:
                print(f"   Sample: {matches[0][:100]}...")

        print("\n" + "-" * 80)
    except Exception as e:
        print(f"❌ Error checking quality: {e}")
        conn.close()


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    # Run the filtering process
    stats = process_and_filter_database()

    # Optional: Quality check
    print("\nRunning quality check...")
    check_clean_db_quality(sample_size=5)

    print("\n✨ Done! Your unified clean_web_data.db is ready with:")
    print("  • webpage_result - High-confidence derivatives")
    print("  • soft_matches - Secondary indicators (hedging relationships, etc)")
    print("  • discarded - Noise and excluded content")
