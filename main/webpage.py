# =============================================================================
# COMPLETE OPTIMIZED CODE
# =============================================================================
# %%
# pip install pandas requests beautifulsoup4 tqdm psutil markdownify
import string
import sys
# Increase recursion limit to handle deeply nested HTML structures
# Default is usually 1000, increase to 5000 for robust handling
sys.setrecursionlimit(5000)

import pandas as pd
import requests
import time
from bs4 import BeautifulSoup
import json
from io import StringIO
import sqlite3
import unicodedata
from typing import List, Optional
import random
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from tqdm import tqdm
import multiprocessing as mp
import psutil
from pathlib import Path
import threading
import html2text
from defs.table_definitions import HTMLTableConverter
from bs4 import XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Importing required module
import subprocess

# =============================================================================
# CONFIGURATION - DEFAULT
# =============================================================================
DEBUG = False
ALL_FIRMS_DATA = "derivatives_data.csv"
REPORT_CSV_PATH = "report_data.csv"
DB_PATH = "web_data.db"


SEC_RATE = 8 # requests per second
SEC_RATE_LIMIT = 1 / SEC_RATE  # requests per second
CHUNK_SIZE = 100
NUM_FETCHERS = 1
NUM_PARSERS = 1
NUM_THREADS = 5

DRIVE_SAVE_INTERVAL_SECONDS = 30 * 60  # 30 minutes
DRIVE_SAVE_INTERVAL_RESULTS = 4000

# =============================================================================
# COLAB CONFIGURATION
# =============================================================================
DRIVE_PATH = "./drive/MyDrive/db"
LOAD_SHELL_CMD = f"cp -f {DRIVE_PATH}/{DB_PATH} ."
SAVE_SHELL_CMD = f"cp -f {DB_PATH} {DRIVE_PATH}/{DB_PATH}.tmp && mv -f {DRIVE_PATH}/{DB_PATH}.tmp {DRIVE_PATH}/{DB_PATH}"
IS_COLAB = Path(DRIVE_PATH).exists()

# Auto-detect system capabilities

def get_system_config():
    """Auto-detects system capabilities to set configuration."""
    cpu_cores = mp.cpu_count()
    ram_gb = psutil.virtual_memory().total / (1024**3)

    print(f"🖥️  System Detected: {cpu_cores} CPU cores, {ram_gb:.2f} GB RAM")

    # Set worker counts based on CPU cores
    num_fetchers =  SEC_RATE  # I/O bound
    num_parsers = cpu_cores - 1  if cpu_cores > 2 else  cpu_cores # CPU bound

    # Set CHUNK_SIZE based on RAM
    if ram_gb > 32:  # High-RAM machine
        chunk_multiplier = 10
    elif ram_gb > 16:  # Medium-RAM machine
        chunk_multiplier = 5
    elif ram_gb > 8:  # Standard machine
        chunk_multiplier = 2
    else:  # Low-RAM machine
        chunk_multiplier = 1
    chunk_size = min(CHUNK_SIZE * chunk_multiplier * cpu_cores, 400)

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


CRUNCHED_TEXT_PATTERNS = [
    (re.compile(r"([a-z])([A-Z])"), r"\1 \2"),
    (re.compile(r"([a-zA-Z])(\d+)"), r"\1 \2"),
    (re.compile(r"(\d+)([a-zA-Z])"), r"\1 \2"),
    (re.compile(r"([a-zA-Z0-9])(\$)"), r"\1 \2"),
]

CLEANUP_PATTERNS = [
    # remove links
    (re.compile(r"http\S+"), ""),
]

TABLE_SPLIT_PATTERN = re.compile(r"(<TABLE>.*?</TABLE>)", re.DOTALL | re.IGNORECASE)

# Pattern to find single newlines that are not preceded or followed by another newline (i.e., wrapped lines)
WRAPPED_LINE_PATTERN = re.compile(r'(?<!\n)\n(?!\n)')
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

ALL_SUFFIXES = ["agreements?", "contracts?", "instruments?", "arrangements?", "assets?", "liabilit(?:y|ies)", "commitments?", "positions?", "strateg(?:ies|y)"]


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

# EXPORT PATTERNS
# =============================================================================

IR_REGEX = build_ir_regex()
FX_REGEX = build_fx_regex()
CP_REGEX = build_cp_regex()
EQ_REGEX = build_eq_regex()
GEN_REGEX = build_gen_regex()

# combined regex combines all of the regex
COMBINED_REGEX = re.compile(r'|'.join([IR_REGEX.pattern, FX_REGEX.pattern, CP_REGEX.pattern, EQ_REGEX.pattern, GEN_REGEX.pattern]), re.IGNORECASE)

# --- NEW: Regex for matching only base derivative types, intended for use within tables ---. Remove the question mark
TABLE_BASE_TYPES_REGEX = re.compile(r'\b' + build_alternation([base.rstrip("?") for base in ALL_BASE_TYPES] + ["derivative"]) + r'\b', re.IGNORECASE)
IGNORE_REGEX = re.compile(r'|'.join([r"stock option", r"share", r"exercis"]),  re.IGNORECASE)

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
        # WAL
        c.execute("PRAGMA journal_mode=WAL")
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
        "User-Agent": f"{random.randint(1000,9999)}-{random.randint(1000,9999)}@{''.join(random.choice(string.ascii_lowercase) for _ in range(random.randint(8,15)))}.com"
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


def get_cik_filings(cik: str) -> Optional[List[dict]]:
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

def normalize_unicode(text: str) -> str:
    """
    Converts common Unicode punctuation and spacing characters to their
    ASCII equivalents. For example, converts non-breaking spaces to regular
    spaces and curly quotes to straight quotes.

    Args:
        text: The string to normalize.

    Returns:
        The normalized string.
    """
    # NFKD form decomposes compatibility characters into their base characters.
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8', 'ignore')


def extract_content(data: str, asHTML=True) -> str:
    """
    Extract content using html2text for better recursion handling.
    Preserves tables and structure without deep recursion issues.
    """
    if not data:
        return ""

    if asHTML:
        # Use lxml for significantly faster parsing. Ensure you have it installed: pip install lxml
        soup = BeautifulSoup(data, "lxml")

        # Decompose hidden elements
        for element in soup(
            ["head", "script", "style", "title", "meta", "noscript", "ix:hidden"]
        ):
            element.decompose()

        for element in soup.find_all(
            style=re.compile(r"display:\s*none|visibility:\s*hidden", re.IGNORECASE)
        ):
            element.decompose()

        # Process tables FIRST before converting to text
        # This preserves SEC-style formatted tables
        tables = soup.find_all("table")
        for table in tables:
            title = "Financial Table"
            prev_sibling = table.find_previous_sibling()
            if table.caption:
                title = table.caption.get_text(strip=True)
            elif prev_sibling and prev_sibling.name == "p":
                title = prev_sibling.get_text(strip=True)

            # OPTIMIZATION: Avoid re-parsing with pd.read_html.
            # Extract rows directly from the BeautifulSoup table object.
            rows = []
            try:
                for tr in table.find_all("tr"):
                    row = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    rows.append(row)
            except Exception as e:
                debug_print(f"⚠️  Table extraction failed: {e}")

            if rows:
                converter = HTMLTableConverter(grid=rows, title=title)
                generic_table = converter.to_generic_table()
                table_text = generic_table.build()
                pre_tag = soup.new_tag("pre")
                pre_tag.string = table_text
                table.replace_with(pre_tag)

        # Use html2text to convert remaining HTML to text
        # This handles complex nested structures without recursion issues
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.ignore_emphasis = False  # Keep bold/italic formatting
        h.body_width = 0  # Don't wrap text
        h.unicode_snob = True  # Use unicode characters

        try:
            soup_str = str(soup)
            text = h.handle(soup_str)
        except Exception as e:
            print(f"⚠️  html2text conversion failed: {e}")
            # Fallback to simple text extraction
            text = soup.get_text(separator="\n", strip=True)

    else:
        # Plain text processing (unchanged)
        for pattern, replacement in CLEANUP_PATTERNS:
            data = pattern.sub(replacement, data)
        parts = TABLE_SPLIT_PATTERN.split(data)
        processed_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                processed_parts.append(part)
            else:
                paragraphs = part.split("\n\n")
                processed_paragraphs = [
                    WRAPPED_LINE_PATTERN.sub(" ", p).strip()
                    for p in paragraphs
                    if p.strip()
                ]
                processed_parts.append(
                    "\n\n".join(p for p in processed_paragraphs if p)
                )
        text = "".join(processed_parts)

    # Apply crunched text patterns
    for pattern, replacement in CRUNCHED_TEXT_PATTERNS:
        text = pattern.sub(replacement, text)

    # Normalize unicode
    text = normalize_unicode(text)

    return text


def fetch_url(url: str, timeout: int = 10, rate_limiter: Optional["ThreadSafeRateLimiter"] = None) -> str | None:
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


def filter_by_keywords(content: str) -> list[str]:
    """
    Filters content for derivative-related keywords and creates larger text
    chunks for analysis by a generative model. Tables are treated as
    separate, whole chunks. If a paragraph matches but ends without a period,
    the next valid paragraph is appended if it doesn't match ignore regex.
    """

    filtered = []
    seen = set()

    # Split the document into text parts and table blocks.
    parts = TABLE_SPLIT_PATTERN.split(content)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        lower_part = part.lower()

        # Handle tables
        if "<table" in lower_part and not IGNORE_REGEX.search(part):
            if COMBINED_REGEX.search(part) or TABLE_BASE_TYPES_REGEX.search(part):
                if lower_part not in seen:
                    filtered.append(part)
                    seen.add(lower_part)
            continue

        # Handle text blocks
        paragraphs = part.split('\n\n')
        i = 0
        while i < len(paragraphs):
            para = paragraphs[i].strip()
            if not para or len(para) < 30:  # Skip very short paragraphs
                i += 1
                continue

            if COMBINED_REGEX.search(para) and not IGNORE_REGEX.search(para):
                para_lower = para.lower()
                # Check if paragraph ends without a period
                if not para.endswith('.'):
                    if i + 1 < len(paragraphs):
                        next_para = paragraphs[i + 1].strip()
                        # Skip short next paragraphs (likely headers or cut-offs)
                        if next_para and len(next_para) >= 30:
                            if not IGNORE_REGEX.search(next_para):
                                # Merge with next paragraph
                                para = para + " " + next_para
                                i += 1  # Skip next paragraph since it's merged
                if para_lower not in seen:
                    filtered.append(para)
                    seen.add(para_lower)
            i += 1
    return filtered

# =============================================================================
# PARALLEL PROCESSING FUNCTIONS (OPTIMIZED FOR PARALLEL CORES)
# =============================================================================


def filter_by_fyear(filings: list[dict], fyear: int) -> list[dict]:
    return [
        f
        for f in filings
        if f.get("report_date", "").startswith(str(fyear))
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
    A thread-safe class to manage a shared rate limit value using atomic
    update methods to prevent race conditions.
    """
    def __init__(self, initial_rate_limit: float):
        self._rate_limit = initial_rate_limit
        self._lock = threading.Lock()
        self._last_429_time = 0
        self._recovery_mode = False
        self._initial_rate_limit = float(initial_rate_limit)

    @property
    def value(self) -> float:
        """Get the current rate limit value."""
        with self._lock:
            return self._rate_limit

    def signal_429(self):
        """Signal that a 429 response was received."""
        with self._lock:
            self._last_429_time = time.time()
            self._recovery_mode = True
            # Increase sleep time by 50%, capped at 60s
            self._rate_limit = min(self._rate_limit * 1.5, 60.0)

    def adjust(self, current_rate: float, target_rate: float):
        """Atomically adjust the rate limit based on performance."""
        with self._lock:
            time_since_last_429 = time.time() - self._last_429_time

            # Exit recovery mode if no 429s for 30 seconds
            if self._recovery_mode and time_since_last_429 > 30:
                self._recovery_mode = False

            # Determine target rate based on recovery status
            target_rate_adjusted = target_rate * 0.5 if self._recovery_mode else target_rate

            # --- Main Adjustment Logic ---
            if current_rate > target_rate_adjusted * 1.05:  # Over target
                # Multiplicatively increase sleep time to slow down
                increase_factor = 1.0 + min((current_rate - target_rate_adjusted) / target_rate_adjusted, 1.0) * 0.1
                self._rate_limit *= increase_factor

            elif current_rate < target_rate_adjusted * 0.95:  # Under target
                if not self._recovery_mode:
                    # Only decrease sleep time if not in recovery
                    self._rate_limit = max(0, self._rate_limit * 0.98)
            
            # --- Gradual Recovery Logic ---
            # Always try to decay back towards the initial rate limit
            if self._rate_limit > self._initial_rate_limit:
                # If we've been clear of 429s for a while, recover faster
                step = 0.05 if time_since_last_429 > 15 else 0.01
                gap = self._rate_limit - self._initial_rate_limit
                self._rate_limit -= gap * step

            return self._rate_limit, self._recovery_mode, target_rate_adjusted

def adjust_rate_in_background(
    tqdm_bar: tqdm,
    rate_limiter: ThreadSafeRateLimiter,
    target_rate: float,
    stop_event: threading.Event,
):
    """A background thread to dynamically adjust the sleep rate."""
    prev_count = getattr(tqdm_bar, "n", 0)
    prev_time = time.time()

    while not stop_event.is_set():
        time.sleep(0.25)  # Check 4 times per second

        # Estimate current rate (requests/sec) from progress increments
        try:
            now = time.time()
            current_count = getattr(tqdm_bar, "n", prev_count)
            elapsed = now - prev_time if now - prev_time > 0 else 1e-6
            current_rate = (current_count - prev_count) / elapsed
            prev_count = current_count
            prev_time = now
        except Exception:
            current_rate = 0.0

                # Not in recovery: always decay back toward initial value slowly
        # Atomically adjust the rate and get the current state
        current_sleep, in_recovery, target_rate_adjusted = rate_limiter.adjust(current_rate, target_rate)
        mode = "Recovery" if in_recovery else "Normal"

        tqdm_bar.set_postfix(
            rate=f"{current_rate:.1f} req/s",
            sleep=f"{current_sleep*1000:.1f}ms",
            mode=mode,
            target=f"{target_rate_adjusted:.1f} req/s"
        )


def fetch_raw_content(url: str, rate_limiter: Optional[ThreadSafeRateLimiter] = None):
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
    elif raw_text is None and url:  # Check if fetch_url returned None due to rate limit
        # Notify the rate limiter (if provided) that we saw a 429
        try:
            if rate_limiter:
                rate_limiter.signal_429()
        except Exception:
            pass
        # Return sentinel for the main loop to react to
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

    last_drive_save_time = time.time()
    results_since_last_save = 0

    for chunk_idx, chunk in enumerate(chunks, 1):
        start_chunk_time = time.time()
        print(f"\n📦 Chunk {chunk_idx}/{len(chunks)} ({len(chunk)} reports)")

        # Stage 1: Fetch this chunk
        print(f"  → Fetching with {NUM_FETCHERS} workers...")
        fetched_data = []
        with ThreadPoolExecutor(max_workers=NUM_FETCHERS) as fetch_executor:
            fetch_futures = [
                fetch_executor.submit(fetch_raw_content, url, rate_limiter)
                for url in chunk if isinstance(url, str)
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
                daemon=True,  # Must be True to prevent deadlock on exit
            )
            adjuster_thread.start()

            try:
                for future in tqdm_bar:
                    try:
                        result = future.result()
                        if result and result[0] != "RATE_LIMITED":
                            fetched_data.append(result)
                        elif result and result[0] == "RATE_LIMITED":
                            # Rate limit detected. Notify the limiter and increase sleep time a bit.
                            try:
                                rate_limiter.signal_429()
                                tqdm_bar.set_postfix_str(f"RATE LIMITED! New sleep: {rate_limiter.value*1000:.1f}ms")
                            except Exception:
                                pass

                    except Exception as e:
                        print(f"Fetch error: {e}")
            finally:
                # Ensure the background thread is stopped when the loop is done
                stop_event.set()


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
        
        chunk_time = time.time() - start_chunk_time
        chunk_times.append(chunk_time)
        total_time += chunk_time
        avg_chunk_time = sum(chunk_times) / len(chunk_times)
        remaining_chunks = len(chunks) - chunk_idx
        est_time_remaining = avg_chunk_time * remaining_chunks

        total_results += chunk_results
        total_empty += chunk_empty
        results_since_last_save += chunk_results

        print(f"  ✓ Parsed {chunk_results} reports successfully")
        print(f"  Time taken: {format_time(chunk_time)}")
        print(f"  Current sleep rate: {rate_limiter.value:.2f}")
        print(f"  Avg chunk time: {format_time(avg_chunk_time)}")
        print(f"  Est. time remaining: {format_time(est_time_remaining)}")

        # Clear memory
        del fetched_data
        import gc

        gc.collect()

        time_since_last_save = time.time() - last_drive_save_time
        if IS_COLAB and (
            time_since_last_save >= DRIVE_SAVE_INTERVAL_SECONDS
            or results_since_last_save >= DRIVE_SAVE_INTERVAL_RESULTS
        ):
            try:
                subprocess.Popen(
                    SAVE_SHELL_CMD,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"  → Saving to database in background.")
                last_drive_save_time = time.time()
                results_since_last_save = 0
            except Exception as e:
                print(f"  ⚠️  Background save failed: {e}")

        print(f"  Total time: {format_time(total_time)}")

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
