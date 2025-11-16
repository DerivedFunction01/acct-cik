# =============================================================================
# DATABASE NOISE REDUCTION SCRIPT WITH CATEGORY CLASSIFICATION
# =============================================================================
# Filters derivative database using smart regex patterns and classifies by type
# Creates unified clean_web_data.db with keyword matches for MNLI comparison
# =============================================================================

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
        "single currency basis swap",
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
    "hedge fund",
    "lawsuit",
]

# Minimum sentence length to consider
MIN_SENTENCE_LENGTH = 50


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
    """Create unified clean database with category classification support."""
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
        # Derivative type classification (for MNLI comparison)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS derivative_type_matches (
                url TEXT PRIMARY KEY,
                ir_matches TEXT,
                fx_matches TEXT,
                cp_matches TEXT,
                eq_matches TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
            """
        )
        # Soft matches (secondary indicators)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS soft_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                matches TEXT
            )
            """
        )
        # Discarded/noise
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discarded (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                matches TEXT
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS type_url_idx ON derivative_type_matches (url)"
        )
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
        # The 'webpage_result' table is the main table for strict matches.
        # If a URL is here, it has been processed.
        c.execute("SELECT url FROM webpage_result")
        processed_urls = {row[0] for row in c.fetchall()}
        return processed_urls
    except sqlite3.OperationalError:
        # Table might not exist yet on the very first run
        return set()
    finally:
        conn.close()

# =============================================================================
# FILTERING FUNCTIONS
# =============================================================================


def is_table_content(match: str) -> bool:
    """Detect if match is table content (starts with | or contains table markers)."""
    return match.strip().startswith("|") or "<table" in match.lower()


def filter_matches(matches_json: str) -> Tuple[List[str], List[str], List[str], str]:
    """
    Filter matches into strict, soft, and noise categories.
    Splits paragraphs into sentences before filtering.

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

    for match in matches:
        if not isinstance(match, str):
            noise.append(str(match))
            continue

        # Skip tables entirely
        if is_table_content(match):
            noise.append(match)
            continue

        # Split paragraph into sentences
        sentences = SENTENCE_SPLIT_PATTERN.split(match)

        for sentence in sentences:
            sentence = sentence.strip()

            # Skip empty or very short content
            if len(sentence) < MIN_SENTENCE_LENGTH:
                noise.append(sentence)
                continue

            # Exclude noise keywords
            if EXCLUDE_REGEX.search(sentence):
                noise.append(sentence)
                continue

            # Check for strict derivative keywords (priority)
            if STRICT_REGEX.search(sentence):
                strict.append(sentence)
            # Check for soft derivative keywords
            elif SOFT_REGEX.search(sentence):
                soft.append(sentence)
            else:
                noise.append(sentence)

    if strict:
        status = "Strict matches found"
    elif soft:
        status = "Soft matches only"
    elif noise:
        status = "Noise only"
    else:
        status = "Empty matches"

    return strict, soft, noise, status


def process_item(item: Tuple[str, str]) -> Optional[Tuple]:
    """
    Worker function to process a single URL's matches.
    Classifies sentences by derivative type for MNLI comparison.
    """
    url, matches_json = item
    try:
        (
            strict_matches,
            soft_matches,
            noise_matches,
            status,
        ) = filter_matches(matches_json)

        # Return None if there's nothing to save
        if not strict_matches and not soft_matches and not noise_matches:
            return None

        # Classify derivative types if strict matches exist
        ir_sentences, fx_sentences, cp_sentences, eq_sentences = [], [], [], []
        if strict_matches:
            for sentence in strict_matches:
                # Check specific categories (order matters for priority)
                if IR_REGEX.search(sentence):
                    ir_sentences.append(sentence)
                if FX_REGEX.search(sentence):
                    fx_sentences.append(sentence)
                if CP_REGEX.search(sentence):
                    cp_sentences.append(sentence)
                if EQ_REGEX.search(sentence):
                    eq_sentences.append(sentence)

        return (
            url,
            strict_matches,
            soft_matches,
            noise_matches,
            (ir_sentences, fx_sentences, cp_sentences, eq_sentences),
        )
    except Exception:
        return None


# =============================================================================
# SAVE FUNCTIONS
# =============================================================================


def save_to_clean_db(
    url: str, matches: List[str], cik: Optional[int] = None, year: Optional[int] = None
):
    """Save filtered matches to clean database."""
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
                INSERT OR REPLACE INTO report_data (url, cik, year) 
                VALUES (?, ?, ?)
                """,
                (url, cik, year),
            )

        conn.commit()
    except Exception as e:
        print(f"❌ Error saving to clean DB: {e}")
    finally:
        conn.close()


def save_derivative_types(
    url: str,
    ir_matches: List[str],
    fx_matches: List[str],
    cp_matches: List[str],
    eq_matches: List[str],
):
    """Save derivative type classifications for MNLI comparison."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT OR REPLACE INTO derivative_type_matches (url, ir_matches, fx_matches, cp_matches, eq_matches)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                url,
                json.dumps(ir_matches),
                json.dumps(fx_matches),
                json.dumps(cp_matches),
                json.dumps(eq_matches),
            ),
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Error saving derivative types: {e}")
    finally:
        conn.close()


def save_to_discarded_db(url: str, soft_matches: List[str], noise_matches: List[str]):
    """Save categorized discarded content to appropriate tables."""
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
                INSERT INTO discarded (url, matches)
                VALUES (?, ?)
                """,
                (url, json.dumps(noise_matches)),
            )

        conn.commit()
    except Exception as e:
        print(f"❌ Error saving to discarded DB: {e}")
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
        print(f"  • Found {len(processed_urls):,} already processed URLs. They will be skipped.")

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

    # Process each URL
    total_kept = 0
    total_soft = 0
    total_noise = 0
    urls_kept = 0
    urls_soft = 0
    urls_noise = 0

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        results_iterator = executor.map(process_item, unprocessed_data, chunksize=CHUNK_SIZE)

        for result in tqdm(
            results_iterator, total=len(unprocessed_data), desc="Filtering URLs"
        ):
            if result is None:
                continue

            (
                url,
                strict_matches,
                soft_matches,
                noise_matches,
                type_matches,
            ) = result

            # Get metadata from the in-memory map
            metadata = report_data_map.get(url)
            cik = metadata[0] if metadata else None
            year = metadata[1] if metadata else None

            # Save strict matches
            if strict_matches:
                save_to_clean_db(url, strict_matches, cik, year)
                total_kept += len(strict_matches)
                urls_kept += 1

                # Save derivative type classifications
                ir_matches, fx_matches, cp_matches, eq_matches = type_matches
                save_derivative_types(
                    url, ir_matches, fx_matches, cp_matches, eq_matches
                )

            # Save soft and noise matches
            if soft_matches or noise_matches:
                save_to_discarded_db(url, soft_matches, noise_matches)

            if soft_matches:
                total_soft += len(soft_matches)
                urls_soft += 1
            if noise_matches:
                total_noise += len(noise_matches)
                urls_noise += 1

    # Print summary
    print("\n" + "=" * 80)
    print("✅ FILTERING COMPLETE")
    print("=" * 80)
    print(f"📊 Summary Statistics:")
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
    print(f"  • webpage_result - High-confidence matches (sentences)")
    print(f"  • derivative_type_matches - IR/FX/CP/EQ classified sentences (for MNLI)")
    print(f"  • report_data - CIK/year metadata")
    print(f"  • soft_matches - Secondary indicators (linked by url)")
    print(f"  • discarded - Noise and excluded content (linked by url)")
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

    print("\n✨ Done! Your clean_web_data.db is ready with:")
    print("  • webpage_result - High-confidence keyword-matched sentences")
    print(
        "  • derivative_type_matches - Classified by IR/FX/CP/EQ (for MNLI validation)"
    )
    print("  • soft_matches - Secondary indicators")
    print("  • discarded - Noise and excluded content")
