# =============================================================================
# COMPLETE OPTIMIZED CODE
# =============================================================================
# %%
# pip install pandas requests beautifulsoup4 tqdm psutil
import pandas as pd
import requests
import time
from bs4 import BeautifulSoup
import json
import sqlite3
from typing import List
import random
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from tqdm import tqdm
import multiprocessing as mp
import psutil
from pathlib import Path
import threading

# Importing required module
import subprocess

# =============================================================================
# CONFIGURATION - DEFAULT
# =============================================================================
DEBUG = False
ALL_FIRMS_DATA = "derivatives_data.csv"
REPORT_CSV_PATH = "report_data.csv"
DB_PATH = "web_data.db"


SEC_RATE = 8  # requests per second
SEC_RATE_LIMIT = 1 / SEC_RATE  # requests per second
CHUNK_SIZE = 100
CHUNK_CHECK_RATE = 5  # Check every 5 iterations
NUM_FETCHERS = 1
NUM_PARSERS = 1
NUM_THREADS = 5

# =============================================================================
# COLAB CONFIGURATION
# =============================================================================
DRIVE_PATH = "./drive/MyDrive/db"
LOAD_SHELL_CMD = f"cp {DB_PATH} {DRIVE_PATH}/{DB_PATH} ."
SAVE_SHELL_CMD = f"cp {DB_PATH} {DRIVE_PATH}/."
IS_COLAB = Path(DRIVE_PATH).exists()

# Auto-detect system capabilities

def get_system_config():
    """Auto-detects system capabilities to set configuration."""
    cpu_cores = mp.cpu_count()
    ram_gb = psutil.virtual_memory().total / (1024**3)

    print(f"🖥️  System Detected: {cpu_cores} CPU cores, {ram_gb:.2f} GB RAM")

    # Set worker counts based on CPU cores
    num_fetchers =  max(cpu_cores, SEC_RATE)  # I/O bound
    num_parsers = cpu_cores  # CPU bound

    # Set CHUNK_SIZE based on RAM
    if ram_gb > 32:  # High-RAM machine
        chunk_multiplier = 10
    elif ram_gb > 16:  # Medium-RAM machine
        chunk_multiplier = 5
    elif ram_gb > 8:  # Standard machine
        chunk_multiplier = 2
    else:  # Low-RAM machine
        chunk_multiplier = 1
    chunk_size = min(CHUNK_SIZE * chunk_multiplier * cpu_cores, 10000)

    # Adjust SEC rate limit based on the number of fetchers
    sec_rate_limit = num_fetchers / SEC_RATE

    print(f"⚙️  Configuration: {num_fetchers} fetchers, {num_parsers} parsers, CHUNK_SIZE={chunk_size}")
    return num_fetchers, num_parsers, chunk_size, sec_rate_limit

NUM_FETCHERS, NUM_PARSERS, CHUNK_SIZE, SEC_RATE_LIMIT = get_system_config()

if IS_COLAB:
    print("Running in Google Colab environment")
    if not Path(DB_PATH).exists():
        print("Loading database from Google Drive...")
        subprocess.run(LOAD_SHELL_CMD, shell=True)
else:
    print("Running in local environment")
# %%
# =============================================================================
# REGEX PATTERNS AND KEYWORDS
# =============================================================================

FILING_TYPES = {
    "10-K",
    "10-KT",
    "20-F",
    "40-F",
    "10-K405",
    "10KSB",
    "10KSB40",
}

PLACEHOLDERS = {
    "€": "__EURO__",
    "£": "__POUND__",
    "¥": "__YEN__",
    "¢": "__CENTS__",
}

REPLACE_HOLDERS = PLACEHOLDERS | {
    "•": "*",
    "—": "--",
    """: '"',
    """: '"',
    "'": "'",
    "'": "'",
}

# Compile regex patterns once
NON_ASCII_PATTERN = re.compile(r"[^\x00-\x7F]+")
BULLET_PATTERN = re.compile(r"^[-*•]\s*")
NUMBERED_PATTERN = re.compile(r"^\(?\d+[\.\)]\s+")
PUNCTUATION_END_PATTERN = re.compile(r"[.!?;:•)]\s*$")
# Split on periods, but also on lowercase-to-uppercase transitions (camelCase splitting)
# This helps break up sentences that are missing periods.
SENTENCE_SPLIT_PATTERN = re.compile(r'(?<=[.!?])\s+|(?<=[a-z])(?=[A-Z])')

CRUNCHED_TEXT_PATTERNS = [
    (re.compile(r"([a-z])([A-Z])"), r"\1 \2"),
    (re.compile(r"([a-zA-Z])(\d+)"), r"\1 \2"),
    (re.compile(r"(\d+)([a-zA-Z])"), r"\1 \2"),
    (re.compile(r"([a-zA-Z0-9])(\$)"), r"\1 \2"),
]

CLEANUP_PATTERNS = [
    (re.compile(r"\s+"), " "),
    (re.compile(r"\(\s*"), "("),
    (re.compile(r"\s*\)"), ")"),
    (re.compile(r"\s*,"), ","),
    (re.compile(r"(-{3,}|={3,}|\.{3,})"), ""),
    (re.compile(r"<.*?>"), ""),
    (re.compile(r"table of contents", re.IGNORECASE), ""),
    (re.compile(r"F-\d+"), ""),
]

SEPARATOR_PATTERN = re.compile(r"[-=\s]+")
CAPTION_PATTERN = re.compile(r"<CAPTION>", re.IGNORECASE)
COLUMN_SPLIT_PATTERN = re.compile(r"\s{2,}")
TABLE_SPLIT_PATTERN = re.compile(
    r"(<TABLE>.*?</TABLE>)", re.DOTALL | re.IGNORECASE)
# %%
# =============================================================================
# SMART REGEX BUILDER - Generates optimized patterns from keyword lists
# =============================================================================

def build_alternation(items: List[str]) -> str:
    """Build optimized alternation pattern from list of items."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f'(?:{"|".join(items)})'


def build_smart_regex(
    core_terms: List[str],
    context_terms: List[str],
    specific_phrases: List[str]
) -> str:
    """
    Builds a more targeted regex by combining core terms with context, 
    and including specific, high-confidence phrases.

    Args:
        core_terms: List of core derivative instrument names.
        context_terms: Broader financial/accounting terms that add context.
        specific_phrases: Standalone phrases that are strong indicators.

    Returns:
        A single regex pattern string.
    """
    # Pattern 1: Core term followed by either a base type (swap, option) or a common suffix (contract, instrument).
    # e.g., "interest-rate swap", "currency contract"
    core_pattern = build_alternation(core_terms)
    
    # Combine base types (context_terms)into one group
    follow_terms = context_terms
    follow_pattern = build_alternation(follow_terms)
    
    pattern1 = f"{core_pattern}[- ]{follow_pattern}"

    # Pattern 2: Specific, high-confidence phrases.
    # e.g., "notional amounts", "embedded derivatives"
    pattern2 = build_alternation(specific_phrases)

    # Combine the main patterns.
    return build_alternation([pattern1, pattern2])


# =============================================================================
# SHARED COMPONENTS
# =============================================================================

ALL_BASE_TYPES = [
    "swaps?", "forwards?", "futures?", "options?", "caps?", "floors?", "collars?", 
    "derivatives?", "swaptions?", "locks?", "hedges?", "hedging",
]

ALL_SUFFIXES = ["agreements?", "contracts?", "instruments?", "arrangements?", "assets?", "liabilit(?:y|ies)"]


COMMON_COMMODITIES = [
    "agricultural", "aluminum", "asphalt", "base metal", "biodiesel", "biomass",
    "bitumen", "cement", "chemical", "coal", "cocoa", "coffee", "concrete", "copper", "corn",
    "cotton", "crude oil", "dairy", "diesel fuel", "electricity", "energy", "ethanol",
    "feedstock", "fertilizer", "fuel", "gas", "gasoline", "grain", "gravel",
    "hardwood lumber", "iron", "limestone", "livestock", "log", "lumber", "metal",
    "mineral", "natural gas", "nitrogen", "paper", "ore", "petrochemical", "petroleum",
    "phosphate", "plastic", "plywood", "polymer", "potash", "precious metal", "pulp",
    "raw material", "resin", "rubber", "salt", "sand", "soda ash", "softwood lumber",
    "soybean", "steel", "sugar", "sulfur", "textile", "timber", "titanium", "uranium",
    "wood", "wood chip", "wood pellet", "wool",
]


# =============================================================================
# CATEGORY-SPECIFIC CONFIGURATIONS
# =============================================================================

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
        "treasury[- ]rate",
        "forward[- ]rate",
        "fixed[- ]rate",
        "floating[- ]rate",
        "variable[- ]rate",
        "benchmark[- ]rate",
    ]

    specific_phrases = [
        "zero[- ]coupon swap",
        "FRA",
        "treasury lock",
        "interest rate lock",
        "interest rate cap",
        "interest rate floor",
        "single currency basis swap"
    ]
    
    # Use ALL_SUFFIXES to catch "interest rate contract/instrument"
    pattern = build_smart_regex(core_terms, ALL_BASE_TYPES + ALL_SUFFIXES, specific_phrases)
    return re.compile(r'\b' + pattern + r'\b', re.IGNORECASE)


def build_fx_regex() -> re.Pattern:
    """Build optimized Foreign Exchange derivatives regex."""

    core_terms = [
        "foreign[- ]exchange",
        "foreign[- ]currency",
        "currency",
        "cross[- ]currency",
        "currency[- ]rate",
        "foreign[- ]exchange[- ]rate",
        "FX",
        "forex"
    ]

    specific_phrases = [
        "NDF",
        "currency swaps?",
        "currency collars?",
        "currency caps?",
        "non[- ]deliverable forwards?",
        "deliverable forwards?",
        "forward foreign exchange",
        "foreign currency contracts?",
    ]

    pattern = build_smart_regex(
        core_terms, ALL_BASE_TYPES + ALL_SUFFIXES, specific_phrases
    )
    return re.compile(r'\b' + pattern + r'\b', re.IGNORECASE)


def build_cp_regex() -> re.Pattern:
    """Build optimized Commodity Price derivatives regex."""

    # Define base commodities and modifiers separately for cleaner logic
    base_commodities = ["commodity"] + COMMON_COMMODITIES
    modifiers = ["[- ]price", "[- ]related", "[- ]based", "[- ]linked"]

    # Programmatically create variations like "commodity price", "crude oil price", etc.
    core_terms = []
    for c in base_commodities:
        core_terms.append(c)
        for mod in modifiers:
            core_terms.append(f"{c}{mod}")

    # Add other specific placeholders
    core_terms.append("fixed[- ]commodity")

    specific_phrases = [
        "commodity index",
        "commodity swaps?"
    ]
    
    # Use ALL_SUFFIXES to catch "commodity contract/instrument" etc.
    pattern = build_smart_regex(core_terms, ALL_BASE_TYPES + ALL_SUFFIXES, specific_phrases)
    return re.compile(r'\b' + pattern + r'\b', re.IGNORECASE)


def build_eq_regex() -> re.Pattern:
    """Build optimized Equity derivatives regex."""
    
    core_terms = [
        "equity",
        "equity[- ]related"
    ]
    
    specific_phrases = [ # No specific equity keywords were provided, so keeping existing
        "call options?",
        "put options?",
        "equity collar strateg(?:y|ies)",
    ]
    
    pattern = build_smart_regex(core_terms, ALL_BASE_TYPES, specific_phrases)
    return re.compile(r'\b' + pattern + r'\b', re.IGNORECASE)


def build_gen_regex() -> re.Pattern:
    """Build optimized General derivatives regex."""

    # Create patterns that require both a base type and a suffix, e.g., "swaps agreements"
    # Also include the base types on their own to match standalone terms like "swaps".
    base_with_required_suffixes = [
        f'{base}[- ]{suffix}' for base in ALL_BASE_TYPES for suffix in ALL_SUFFIXES
    ]

    # Specific multi-word phrases that are strong indicators on their own.
    specific_phrases = [
        "embedded derivatives?",
        "notional (?:amounts?|values?|principals?)", # Covered
        "derivative (?:assets?|liabilities|gains?|losses?|positions?|contracts?|instruments?)",
        "(?:gain|loss) on derivatives?",
        "change in fair value of derivatives?",
        "over[- ]the[- ]counter derivatives?",
        "total[- ]return swap",
        "designated as (?:a )?hedges?", # Covers "designated as a hedge" and "designated as hedges"
        "(?:instruments?|contracts?) are designated",
        "hedge of the net investment",
        "net investment hedges?",
        "cash flow hedges?", # Added from user input
        "fair value hedges?", # Added from user input
        "ineffective portion",
        "derivative financial instruments?",
        "derivative expense",
    ]

    # Add individual base types and suffixes as specific phrases for standalone matches
    # This ensures "hedge" or "swap" alone are caught if not followed by a specific term
    # REMOVED: The lines above were too broad, matching standalone terms like "swap" or "contract".
    # By removing them, we now require more specific phrases, reducing noise.

    pattern = build_alternation(base_with_required_suffixes + specific_phrases)
    return re.compile(r'\b' + pattern + r'\b', re.IGNORECASE)

# =============================================================================
# DYNAMICALLY GENERATE ALLOWED_KEYWORDS
# =============================================================================

def generate_allowed_keywords() -> set:
    """Collects all core terms, specific phrases, base types, and suffixes."""
    # This is a simplified approach. A more robust way would be to inspect the functions.
    # For now, we'll manually list the core concepts.
    keywords = set([
        "expire", "terminat", "outstanding", "designat", "matur", "settle",
        "unwound", "close", "liquidat", "gain", "loss", "fair value", "notional",
        "derivative", "hedg", "swap", "option", "forward", "future", "collar",
        "contract", "instrument", "agreement", "liability", "asset", "position",
        "interest", "rate", "currency", "exchange", "fx", "commodity", "equity",
        "embedded", "warrant", "cash flow", "net investment"
    ])
    
    # Clean up the keywords
    cleaned_keywords = set()
    for kw in keywords:
        # Remove regex-specific characters for simple string matching
        cleaned_kw = re.sub(r'\[- \]', ' ', kw)
        cleaned_kw = re.sub(r'[\?\(\)\|\:]', '', cleaned_kw)
        cleaned_keywords.add(cleaned_kw)

    # Add all base types and suffixes without regex chars
    for term_list in [ALL_BASE_TYPES, ALL_SUFFIXES]:
        for term in term_list:
            cleaned_term = re.sub(r'[\?\(\)\|\:]', '', term)
            cleaned_term = re.sub(r'\[- \]', ' ', cleaned_term)
            if 'ies' in cleaned_term: # for liability|liabilities
                cleaned_keywords.add(cleaned_term.replace('ies', 'y'))
            cleaned_keywords.add(cleaned_term)

    return cleaned_keywords


# Dynamically generate ALLOWED_KEYWORDS
ALLOWED_KEYWORDS = generate_allowed_keywords()
# EXPORT PATTERNS
# =============================================================================

IR_REGEX = build_ir_regex()
FX_REGEX = build_fx_regex()
CP_REGEX = build_cp_regex()
EQ_REGEX = build_eq_regex()
GEN_REGEX = build_gen_regex()

# Category regex patterns

CATEGORY_REGEX_ORDER = [
    ("ir", IR_REGEX),
    ("fx", FX_REGEX),
    ("cp", CP_REGEX),
    ("eq", EQ_REGEX),
    ("gen", GEN_REGEX),
]


# %%
# =============================================================================
# LOAD DATA
# =============================================================================
all_derivatives_df = pd.read_csv(ALL_FIRMS_DATA)

# =============================================================================
# DEBUG UTILITIES
# =============================================================================


def debug_print(*args):
    global DEBUG
    if DEBUG:
        print(*args)

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS report_data (
                cik INTEGER,
                year INTEGER,
                url TEXT
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS names (
                cik INTEGER,
                name TEXT
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS webpage_result (
                url TEXT,
                matches TEXT,
                FOREIGN KEY (url) REFERENCES report_data(url)
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS fail_results (
                cik INTEGER,
                year INTEGER,
                url TEXT,
                reason TEXT
            )
        """
        )
        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON report_data (url)")
        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        c.execute("CREATE INDEX IF NOT EXISTS name_idx ON names (name)")
    except sqlite3.IntegrityError:
        print("Something went wrong creating the database")
    finally:
        conn.commit()
        conn.close()


def save_batch_report_urls(df):
    with sqlite3.connect(DB_PATH) as conn:
        try:
            name = df[["cik", "name"]].drop_duplicates()
            name = name.dropna()
            name["name"] = name["name"].str.title()
            name.to_sql("names", conn, if_exists="append", index=False)
        except:
            pass
        try:
            report = df[["cik", "year", "url"]]
            report.to_sql("report_data", conn, if_exists="append", index=False)
            return True
        except sqlite3.IntegrityError:
            debug_print(df.head())
            df = df[["cik", "year", "url"]]
            df["reason"] = "Error submitting batch"
            df.to_sql("fail_results", conn, if_exists="append", index=False)
            return False


def fetch_report_data(valid=True):
    try:
        return pd.read_csv(REPORT_CSV_PATH)
    except:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if valid:
            c.execute("SELECT * FROM report_data WHERE NOT url =''")
        else:
            c.execute("SELECT * FROM report_data WHERE url =''")
        columns = [col[0] for col in c.description]
        rows = c.fetchall()
        pre_data = pd.DataFrame(rows, columns=columns)
        conn.close()
        return pre_data


def fetch_webpage_results():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM webpage_result")
    columns = [col[0] for col in c.description]
    rows = c.fetchall()
    pre_data = pd.DataFrame(rows, columns=columns)
    conn.close()
    return pre_data


def get_processed_urls() -> set:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url FROM webpage_result")
    rows = c.fetchall()
    conn.close()
    return set(rows)


def save_process_result(df):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO webpage_result (url, matches) VALUES (?, ?)",
        (df.url, json.dumps(df.matches)),
    )
    conn.commit()
    conn.close()


# =============================================================================
# FETCH SEC FILINGS
# =============================================================================

# %%
def fetch_json(url: str) -> dict | None:
    global SEC_RATE_LIMIT
    headers = {
        "User-Agent": f"{random.randint(1000,9999)}-{random.randint(1000,9999)}@{random.randint(1000,9999)}.com"
    }
    time.sleep(SEC_RATE_LIMIT)
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        debug_print("Fetching", url)
        if resp.status_code == 429:
            print(f"Rate Limited {resp.status_code} fetching {url}")
            return None
        if resp.status_code != 200:
            print(f"Error {resp.status_code} fetching {url}")
            return None
        return resp.json()
    except Exception as e:
        print(f"Exception fetching {url}: {e}")
        return None


def extract_filings(data: dict, cik: str, name: str, ticker: str) -> List[dict]:
    links = []
    forms = data.get("form", [])
    accession_numbers = data.get("accessionNumber", [])
    primary_docs = data.get("primaryDocument", [])
    filing_dates = data.get("filingDate", [])
    report_dates = data.get("reportDate", [])

    for i, f_type in enumerate(forms):
        if f_type in FILING_TYPES:
            accession = accession_numbers[i].replace("-", "")
            doc = primary_docs[i]
            if not doc or doc.endswith("txt"):
                doc = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}.txt"
            link = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
            links.append(
                {
                    "name": name,
                    "filing_date": filing_dates[i],
                    "report_date": report_dates[i],
                    "url": link,
                    "ticker": ticker,
                    "type": f_type,
                }
            )
    return links


def get_cik_filings(cik: str) -> List[dict]:
    cik = str(cik).zfill(10)
    url_main = f"https://data.sec.gov/submissions/CIK{cik}.json"

    data = fetch_json(url_main)
    if not data:
        return None

    name = data.get("name", "")
    ticker = data.get("tickers", [])[0] if data.get("tickers", []) else cik

    recent = data.get("filings", {}).get("recent", {})
    links = extract_filings(recent, cik, name, ticker)

    older_files = data.get("filings", {}).get("files", [])
    for f in older_files:
        older_data = fetch_json(
            f"https://data.sec.gov/submissions/{f.get('name')}")
        if isinstance(older_data, dict):
            links.extend(extract_filings(older_data, cik, name, ticker))

    return links


# =============================================================================
# CONTENT EXTRACTION
# =============================================================================


def extract_content(data: str, asHTML=True, max_len=600) -> str:
    if not data:
        return ""

    if asHTML:
        soup = BeautifulSoup(data, "html.parser")
        text = soup.get_text(separator="\n\n", strip=True)
        text = keep_allowed_chars(text, True)
        paragraphs = [p.strip()
                      for p in re.split(r"\n\s*\n", text) if p.strip()]
        merged_paragraphs = []

        i = 0
        while i < len(paragraphs):
            line = paragraphs[i]

            if BULLET_PATTERN.match(line):
                if len(line.strip()) == 1 and i + 1 < len(paragraphs):
                    line = f"{line} {paragraphs[i + 1]}"
                    i += 1

                if merged_paragraphs and BULLET_PATTERN.match(merged_paragraphs[-1]):
                    merged_paragraphs[-1] += f"\n{line}"
                else:
                    merged_paragraphs.append(line)

            elif NUMBERED_PATTERN.match(line):
                if merged_paragraphs and NUMBERED_PATTERN.match(merged_paragraphs[-1]):
                    merged_paragraphs[-1] += f"\n{line}"
                else:
                    merged_paragraphs.append(line)

            elif merged_paragraphs and not PUNCTUATION_END_PATTERN.search(
                merged_paragraphs[-1]
            ):
                merged_paragraphs[-1] += f" {line}"
            else:
                merged_paragraphs.append(line)

            i += 1

        final_paragraphs = []
        for para in merged_paragraphs:
            if len(para) <= max_len:
                final_paragraphs.append(para)
            else:
                parts = SENTENCE_SPLIT_PATTERN.split(para)
                current_chunk = ""

                for part in parts:
                    if len(current_chunk) + len(part) + 1 <= max_len:
                        current_chunk += f" {part}" if current_chunk else part
                    else:
                        if current_chunk:
                            final_paragraphs.append(current_chunk)
                        current_chunk = part

                if current_chunk:
                    final_paragraphs.append(current_chunk)

        paragraphs = final_paragraphs

    else:
        text = keep_allowed_chars(data)
        parts = TABLE_SPLIT_PATTERN.split(text)
        paragraphs = []

        for part in parts:
            if part.strip().lower().startswith("<table>"):
                rows = parse_plain_text_table_fixed(part)
                table_text = "\n".join(["\t".join(row) for row in rows])
                paragraphs.append(table_text)
            else:
                sub_paras = [p for p in re.split(
                    r"\n\s*\n", part) if p.strip()]
                paragraphs.extend(sub_paras)

    cleaned_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        is_list_item = BULLET_PATTERN.match(
            para) or NUMBERED_PATTERN.match(para)
        if not is_list_item:
            para = re.sub(r"\n+", " ", para)

        for pattern, replacement in CRUNCHED_TEXT_PATTERNS:
            para = pattern.sub(replacement, para)

        for pattern, replacement in CLEANUP_PATTERNS:
            para = pattern.sub(replacement, para)

        para = para.strip()

        if len(para) < 15 and cleaned_paragraphs:
            cleaned_paragraphs[-1] = f"{cleaned_paragraphs[-1]} {para}"
        elif para:
            cleaned_paragraphs.append(para)

    return "\n\n".join(cleaned_paragraphs)


def keep_allowed_chars(text, asHTML=False):
    if not isinstance(text, str):
        return text

    if asHTML:
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass

    for sym, ph in REPLACE_HOLDERS.items():
        text = text.replace(sym, ph)

    text = NON_ASCII_PATTERN.sub("", text)

    for sym, ph in PLACEHOLDERS.items():
        text = text.replace(ph, sym)
    return text


def parse_plain_text_table_fixed(block: str):
    rows = []
    first_col_buffer = ""
    first_col_active = True

    lines = [line.rstrip() for line in block.splitlines() if line.strip()]

    for line in lines:
        if SEPARATOR_PATTERN.fullmatch(line) or CAPTION_PATTERN.match(line.strip()):
            continue

        if "<S>" in line:
            first_col_active = False
            line = line.replace("<S>", "").lstrip()

        if first_col_active:
            first_col_buffer = f"{first_col_buffer} {line.strip()}".strip()
            continue

        cols = [col.strip() for col in COLUMN_SPLIT_PATTERN.split(line)]

        if first_col_buffer:
            rows.append([first_col_buffer] + cols)
            first_col_buffer = ""
        else:
            rows.append(cols)

    return rows


def fetch_url(url: str, timeout: int = 10, rate_limiter: "ThreadSafeRateLimiter" = None) -> str | None:
    global SEC_RATE_LIMIT, SEC_RATE
    if not url:
        return None
    try:
        # Use the rate_limiter's current value for sleeping
        time.sleep(rate_limiter.value if rate_limiter else SEC_RATE_LIMIT)
        debug_print("Fetching", url)
        resp = requests.get(
            url, timeout=timeout, headers={
                "User-Agent": "sync-fetch@example.com"}
        )
        if resp.status_code == 429:
            print(f"Rate Limited {resp.status_code} for {url}")
            return None
        if resp.status_code != 200:
            print(f"Error {resp.status_code} for {url}")
            return None
        return resp.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def process_url(url: str):
    raw_text = fetch_url(url)
    if not raw_text:
        debug_print(f"Error fetching {url}: No text found")
        return ""

    if url.endswith("htm"):
        debug_print("Processing as html")
        content = extract_content(raw_text, True)
    else:
        debug_print("Processing as text")
        content = extract_content(raw_text, False)
    return content


# =============================================================================
# KEYWORD FILTERING (OPTIMIZED VERSION)
# =============================================================================


def filter_by_keywords(
    content: str, min_char_length: int = 500, max_char_length=1200
) -> dict:
    """
    OPTIMIZED: Pre-filter sentences by category before expansion.
    'gen' category can now expand with ANY other category.
    """
    allowed_keywords = [kw.lower() for kw in ALLOWED_KEYWORDS]

    def get_keyword_category(text: str) -> str:
        try:
            for category, regex in CATEGORY_REGEX_ORDER:
                if regex.search(text):
                    return category
        except Exception as e:
            print(f"Regex error in category '{category}': {e}")
            print(f"Regex pattern: {regex.pattern}")
        return None

    def clean_sentence(sentence: str) -> str:
        return re.sub(r"\s+", " ", sentence.strip())

    def measure_merged_length(sentences: list) -> int:
        return len(". ".join(sentences).strip() + ".")

    OVERLAP_COUNT = 2  # A sentence can appear in up to this many final paragraphs

    def _expand_one_side(
        direction: str,
        current_idx: int,
        merged_sentences: list,
        used_indices: set,
        target_category: str,
        all_sentences: list,
        seen_counts: dict,
    ) -> tuple[bool, int, bool]:
        """Helper to expand context in one direction (left or right)."""
        is_left = direction == "left"
        next_idx = current_idx - 1 if is_left else current_idx + 1

        if (
            not (0 <= next_idx < len(all_sentences))
            or seen_counts.get(next_idx, 0) >= OVERLAP_COUNT
        ):
            return False, -1 if is_left else len(all_sentences), False

        sentence_to_add = all_sentences[next_idx]  # This is a full sentence
        category = get_keyword_category(sentence_to_add)
        is_allowed = should_allow(sentence_to_add)

        # Allow expansion if the next sentence has a matching category, is generic, is allowed, or has no category at all (is neutral).
        # Stop expansion only if it has a *different, non-generic* category.
        if (
            category
            and category != target_category
            and category != "gen"
            and not is_allowed
        ):
            return False, -1 if is_left else len(all_sentences), False

        # Prepare candidate for length check
        candidate = (
            [sentence_to_add] + merged_sentences
            if is_left
            else merged_sentences + [sentence_to_add]
        )
        candidate_length = measure_merged_length(candidate)

        if candidate_length <= max_char_length:
            (
                merged_sentences.insert(0, sentence_to_add)
                if is_left
                else merged_sentences.append(sentence_to_add)
            )
            used_indices.add(next_idx)
            return True, next_idx, False  # Not truncated
        else:
            # Trim and add, then stop expansion on this side
            excess = candidate_length - max_char_length
            trimmed_sentence = (
                sentence_to_add[excess:] if is_left else sentence_to_add[:-excess]
            )
            (
                merged_sentences.insert(0, trimmed_sentence)
                if is_left
                else merged_sentences.append(trimmed_sentence)
            )
            used_indices.add(next_idx)
            return True, -1 if is_left else len(all_sentences), True  # Was truncated

    def should_allow(text: str) -> bool:
        normalized = text.lower()
        return any(kw in normalized for kw in allowed_keywords)

    def expand_context(
        all_sentences: list, target_idx: int, target_category: str, seen_counts: dict
    ) -> tuple[str, set, set]:
        # The seed sentence is always included, so we check its count in the main loop.
        merged = [all_sentences[target_idx]]  # This is a full sentence
        used_indices_in_this_expansion = {target_idx}
        truncated_indices = set()
        left_idx = target_idx - 1
        right_idx = target_idx + 1

        while True:
            if measure_merged_length(merged) >= min_char_length:
                break

            added_left, new_left_idx, truncated_left = _expand_one_side(
                "left",
                left_idx,
                merged,
                used_indices_in_this_expansion,
                target_category,
                all_sentences,
                seen_counts,
            )
            left_idx = new_left_idx
            if truncated_left:
                truncated_indices.add(new_left_idx)

            added_right, new_right_idx, truncated_right = _expand_one_side(
                "right",
                right_idx,
                merged,
                used_indices_in_this_expansion,
                target_category,
                all_sentences,
                seen_counts,
            )
            right_idx = new_right_idx
            if truncated_right:
                truncated_indices.add(new_right_idx)

            if not added_left and not added_right:
                break

        final_text = ". ".join(merged).strip() + "."

        return final_text, used_indices_in_this_expansion, truncated_indices

    # --- Sentence preprocessing ---
    text = re.sub(r"\s+", " ", content.strip())
    raw_sentences = [
        s.strip() for s in re.split(SENTENCE_SPLIT_PATTERN, text) if s.strip()
    ]
    all_sentences = [clean_sentence(sentence) for sentence in raw_sentences]

    # --- Pre-categorize ---
    sentence_categories = []
    for i, sentence in enumerate(all_sentences):
        category = get_keyword_category(sentence)
        sentence_categories.append((i, category))
    debug_print("Pre-categorized sentences")
    # Print the count of sentences per category for debugging
    category_counts = {}
    for _, category in sentence_categories:
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1
    debug_print("Sentence counts by category:", category_counts)
    # Grab the tuple from CATEGORY_REGEX_ORDER
    categorized_matches = {category: [] for category, _ in CATEGORY_REGEX_ORDER}
    seen_matches = {category: set() for category, _ in CATEGORY_REGEX_ORDER}
    seen_sentences_global = {}  # Using a dict as a counter: {index: count}

    # --- Pass 1: non-gen categories ---
    for i, category in sentence_categories:
        if category and category != "gen":
            # Skip if the seed sentence has already been used max times
            if seen_sentences_global.get(i, 0) >= OVERLAP_COUNT:
                continue

            final_sentence, used_indices, truncated_indices = expand_context(
                all_sentences, i, category, seen_sentences_global
            )
            normalized = final_sentence.lower().strip()

            if normalized not in seen_matches[category]:
                seen_matches[category].add(normalized)
                categorized_matches[category].append(final_sentence)
                # Increment the counter for all sentences used in this expansion
                # Do NOT increment count for truncated sentences
                for idx in used_indices:
                    if idx in truncated_indices:
                        continue
                    seen_sentences_global[idx] = seen_sentences_global.get(idx, 0) + 1
            else:
                debug_print(
                    f"Ignoring paragraph for category '{category}' as it is a duplicate."
                )

    # # --- Pass 2: 'gen' category (can attach anywhere) ---
    for i, category in sentence_categories:
        if category == "gen":
            # Skip if the seed sentence has already been used max times
            if (
                len(all_sentences[i].split()) < 6
                or seen_sentences_global.get(i, 0) >= OVERLAP_COUNT
            ):
                continue

            # ✅ Will expand freely due to logic above
            final_sentence, used_indices, truncated_indices = expand_context(
                all_sentences, i, "gen", seen_sentences_global
            )
            normalized = final_sentence.lower().strip()

            if normalized not in seen_matches["gen"]:
                seen_matches["gen"].add(normalized)
                categorized_matches["gen"].append(final_sentence)
                # Increment the counter for all sentences used in this expansion
                # Do NOT increment count for truncated sentences
                for idx in used_indices:
                    if idx in truncated_indices:
                        continue
                    seen_sentences_global[idx] = seen_sentences_global.get(idx, 0) + 1
            else:
                debug_print("Ignoring 'gen' paragraph as it is a duplicate.")

    debug_print(
        "Done generating sentences", sum(len(v) for v in categorized_matches.values())
    )

    return categorized_matches

# =============================================================================
# PARALLEL PROCESSING FUNCTIONS (OPTIMIZED FOR PARALLEL CORES)
# =============================================================================


def filter_by_fyear(filings: list[dict], fyear: int) -> list[dict]:
    return [
        f
        for f in filings
        if f.get("report_date") and f.get("report_date").startswith(str(fyear))
    ]


def fetch_all_grouped(saveIteration: int = 100):
    """
    Fetch filings using ProcessPoolExecutor for parallelism.
    """
    global existing_report_df, all_derivatives_df, SEC_RATE_LIMIT, SEC_RATE

    records = []

    if existing_report_df is None or existing_report_df.empty:
        existing_report_df = pd.DataFrame(columns=["cik", "year"])

    already_done = set(
        zip(existing_report_df["cik"], existing_report_df["year"]))
    cik_groups = all_derivatives_df.groupby(
        "cik")["year"].apply(list).reset_index()

    def process_cik(row):
        cik = row.cik
        years = row.year
        cik_records = []

        years_to_fetch = [y for y in years if (cik, y) not in already_done]
        if not years_to_fetch:
            return cik_records

        debug_print("Fetching", years_to_fetch)
        filings = get_cik_filings(cik)
        if filings is None:
            print("Error fetching filings for", cik)
            return cik_records

        for fyear in years_to_fetch:
            year_filings = filter_by_fyear(filings, fyear)
            for filing in year_filings:
                cik_records.append({"cik": cik, "year": fyear, **filing})

        for year in years:
            if (cik, year) not in already_done:
                cik_records.append({"cik": cik, "year": year, "url": ""})

        return cik_records

    # Use fewer workers for SEC API to avoid rate limiting
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        future_to_cik = {
            executor.submit(process_cik, row): i
            for i, row in enumerate(cik_groups.itertuples(index=False), start=1)
        }
        SEC_RATE_LIMIT = NUM_THREADS / SEC_RATE
        for future in tqdm(as_completed(future_to_cik), total=len(future_to_cik)):
            i = future_to_cik[future]
            try:
                cik_records = future.result()
                records.extend(cik_records)

                if i % saveIteration == 0 and records:
                    save_batch_report_urls(pd.DataFrame(records))
                    debug_print(f"Saved {len(records)} urls to database")
                    records = []
            except Exception as exc:
                print(f"CIK processing generated an exception: {exc}")

    if records:
        save_batch_report_urls(pd.DataFrame(records))
        print(f"Saved {len(records)} urls to database")

    return fetch_report_data()


class ThreadSafeRateLimiter:
    """
    A thread-safe class to manage a shared rate limit value.
    Threads share memory, so we can use a simple lock instead of a
    heavier multiprocessing.Manager.
    """
    def __init__(self, initial_rate_limit: float):
        self._rate_limit = initial_rate_limit
        self._lock = threading.Lock()

    @property
    def value(self) -> float:
        """Get the current rate limit value."""
        with self._lock:
            return self._rate_limit

    @value.setter
    def value(self, new_value: float):
        """Set a new rate limit value."""
        with self._lock:
            self._rate_limit = new_value


def adjust_rate_in_background(
    tqdm_bar: tqdm,
    rate_limiter: ThreadSafeRateLimiter,
    target_rate: float,
    stop_event: threading.Event,
):
    """
    A background thread function to dynamically adjust the sleep rate.
    This runs independently of the main fetch loop.
    """
    while not stop_event.is_set():
        time.sleep(1.0)  # Check once per second

        # Ensure the tqdm bar and its rate are available
        if not hasattr(tqdm_bar, "rate") or tqdm_bar.rate is None:
            continue

        current_rate = tqdm_bar.rate
        current_sleep = rate_limiter.value

        # Proactive adjustment logic
        # If we are going too fast, increase sleep time
        if current_rate > target_rate:
            # Increase sleep time proportionally to how much we are over
            overshoot_factor = (current_rate - target_rate) / target_rate
            rate_limiter.value += 0.001 + (0.01 * overshoot_factor)
        # If we are too slow, decrease sleep time (but not below zero)
        elif current_rate < (target_rate * 0.9):  # Leave a 10% buffer
            rate_limiter.value = max(0, current_sleep - 0.002)

        tqdm_bar.set_postfix(
            rate=f"{current_rate:.1f} req/s", sleep=f"{rate_limiter.value*1000:.1f}ms"
        )


def fetch_raw_content(url: str, rate_limiter: ThreadSafeRateLimiter = None):
    """
    Fetches raw text content from a URL. This is purely I/O-bound.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check if the URL is already in the database to avoid re-fetching
    # This is a quick check before the more expensive fetch_url call
    # Note: This is a read-only operation, so it's thread-safe without locks
    # for this specific use case.
    c.execute("SELECT 1 FROM webpage_result WHERE url = ?", (url,))
    exists = c.fetchone()
    conn.close()
    if exists:
        return None

    raw_text = fetch_url(url, rate_limiter=rate_limiter)
    if raw_text:
        return url, raw_text
    elif raw_text is None and url: # Check if fetch_url returned None due to rate limit
        # This is a signal that we might have been rate-limited
        # We can return a special value to notify the main loop
        return "RATE_LIMITED", url

    return None


def parse_and_save_content(data):
    """
    Parses raw HTML/text, filters for keywords, and saves to the database.
    This is a CPU-bound task.
    """
    if data is None:
        return None

    url, raw_text = data

    try:
        # 1. Extract clean content from raw text (CPU-intensive)
        if url.endswith("htm"):
            content = extract_content(raw_text, True)
        else:
            content = extract_content(raw_text, False)

        if not content:
            return None

        # 2. Filter for keywords to get relevant sentences (CPU-intensive)
        # CPU-intensive parsing
        categorized_sentences = filter_by_keywords(content)
        # 3. Save the result to the database
        result_row = pd.Series({"url": url, "matches": categorized_sentences})

        save_process_result(result_row)
        return True
    except Exception as e:
        print(f"Parse error for {url}: {e}")
        return None


def format_time(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    elif minutes > 0:
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(seconds)}s"


def process_all_reports_fully():
    # Initialize a thread-safe rate limiter for the fetching stage.
    rate_limiter = ThreadSafeRateLimiter(SEC_RATE_LIMIT)

    processed_set = get_processed_urls()

    reports_to_process = [
        (r.url)
        for r in existing_report_df.itertuples(index=False)
        if (r.url,) not in processed_set and r.url
    ]

    total_reports = len(reports_to_process)
    print(f"Processing {total_reports:,} new reports")
    print(f"Already processed: {len(processed_set):,} reports")
    print(f"\n⚙️  Rate Limiting Configuration:")
    print(f"  • {NUM_FETCHERS} parallel fetchers")
    print(f"  • Each worker waits {SEC_RATE_LIMIT:.2f}s between requests")
    print(f"  • Effective rate: ~{NUM_FETCHERS / SEC_RATE_LIMIT:.2f} req/sec")
    total_results = 0
    total_empty = 0

    chunks = [
        reports_to_process[i: i + CHUNK_SIZE]
        for i in range(0, total_reports, CHUNK_SIZE)
    ]

    print(f"\nProcessing in {len(chunks)} chunks of {CHUNK_SIZE} reports each")
    print("=" * 70)

    chunk_times = []
    total_time = 0

    for chunk_idx, chunk in enumerate(chunks, 1):
        rate_limited_in_chunk = False
        start_chunk_time = time.time()
        print(f"\n📦 Chunk {chunk_idx}/{len(chunks)} ({len(chunk)} reports)")

        # Stage 1: Fetch this chunk
        print(f"  → Fetching with {NUM_FETCHERS} workers...")
        fetched_data = []
        with ThreadPoolExecutor(max_workers=NUM_FETCHERS) as fetch_executor:
            fetch_futures = [
                fetch_executor.submit(fetch_raw_content, url, rate_limiter)
                for url in chunk
            ]

            # Create the tqdm bar instance
            tqdm_bar = tqdm(
                as_completed(fetch_futures),
                total=len(fetch_futures),
                desc=f"  Fetching chunk {chunk_idx}",
                leave=False,
            )

            # Start the background thread for rate adjustment
            stop_event = threading.Event()
            adjuster_thread = threading.Thread(
                target=adjust_rate_in_background,
                args=(tqdm_bar, rate_limiter, SEC_RATE, stop_event),
                daemon=True,  # Allows main program to exit even if thread is running
            )
            adjuster_thread.start()

            try:
                for future in tqdm_bar:
                    try:
                        result = future.result()
                        if result and result[0] != "RATE_LIMITED":
                            fetched_data.append(result)
                            debug_print(result)
                        elif result and result[0] == "RATE_LIMITED":
                            rate_limited_in_chunk = True

                    except Exception as e:
                        print(f"Fetch error: {e}")
            finally:
                # Ensure the background thread is stopped when the loop is done
                stop_event.set()
                adjuster_thread.join(timeout=2)

        # If we were rate-limited in this chunk, enforce a cool-down
        if rate_limited_in_chunk:
            cool_down_period = 5  # seconds
            print(f"🧊 Rate limit detected in chunk. Cooling down for {cool_down_period}s...")
            time.sleep(cool_down_period)
            # Optionally, you could also make the rate limiter more conservative here

        chunk_time = time.time() - start_chunk_time
        chunk_times.append(chunk_time)
        total_time += chunk_time
        avg_chunk_time = sum(chunk_times) / len(chunk_times)
        remaining_chunks = len(chunks) - chunk_idx
        est_time_remaining = avg_chunk_time * remaining_chunks

        print(f"  ✓ Fetched {len(fetched_data)} reports.")

        # Stage 2: Parse this chunk
        print(f"  → Parsing with {NUM_PARSERS} workers...")
        chunk_results = 0
        chunk_empty = 0

        with ProcessPoolExecutor(max_workers=NUM_PARSERS) as parse_executor:
            parse_futures = [
                parse_executor.submit(parse_and_save_content, data) for data in fetched_data
            ]

            for future in tqdm(
                as_completed(parse_futures),
                total=len(parse_futures),
                desc=f"  Parsing chunk {chunk_idx}",
                leave=False,
            ):
                try:
                    result = future.result()
                    if result:
                        debug_print("Parse successful")
                        chunk_results += 1
                    else:
                        chunk_empty += 1
                        debug_print("Error with processing")
                except Exception as e:
                    print(f"Parse error: {e}")
                    chunk_empty += 1

        total_results += chunk_results
        total_empty += chunk_empty

        print(f"  ✓ Parsed {chunk_results} reports successfully")
        print(f"  Time taken: {format_time(chunk_time)}")
        print(f"  Current sleep rate: {rate_limiter.value:.2f}")
        print(f"  Avg chunk time: {format_time(avg_chunk_time)}")
        print(f"  Est. time remaining: {format_time(est_time_remaining)}")
        print(f"  Total time: {format_time(total_time)}")

        # Clear memory
        del fetched_data
        import gc

        gc.collect()
        if IS_COLAB:
            subprocess.Popen(SAVE_SHELL_CMD, shell=True)
            print(f"  → Saving to database.")

        # Progress summary
        processed_so_far = chunk_idx * CHUNK_SIZE
        percent_complete = (processed_so_far / total_reports) * 100
        print(
            f"  📊 Overall: {total_results:,}/{min(processed_so_far, total_reports):,} ({percent_complete:.1f}% complete)"
        )

    print("\n" + "=" * 70)
    print(f"🎉 FINAL RESULTS:")
    print(f"  ✓ Successfully processed: {total_results:,} reports")
    print(f"  ✗ Empty/failed: {total_empty:,} reports")
    if total_results + total_empty > 0:
        print(
            f"  📈 Success rate: {(total_results/(total_results+total_empty)*100):.1f}%"
        )
    print("=" * 70)


# =============================================================================
# INITIALIZATION
# =============================================================================
# %%
create_db()
existing_report_df = fetch_report_data()
print(f"Found {len(existing_report_df)} reports in database")

# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
if __name__ == "__main__":
    print("=" * 70)
    print("STEP 1: Fetch all 10-K report URLs from SEC")
    print("=" * 70)
    # Uncomment to run:
    # fetch_all_grouped()

    print("\n" + "=" * 70)
    print(f"STEP 2: Perform keyword extraction in parallel")
    print("=" * 70)
    # Uncomment to run:
    process_all_reports_fully()

    print("\n" + "=" * 70)
    print("All done!")
    print("=" * 70)

# %%
