# =============================================================================
# COMPLETE OPTIMIZED CODE
# =============================================================================
# %%
# pip install pandas requests beautifulsoup4 tqdm psutil markdownify
import queue
import string
import sys


# Increase recursion limit to handle deeply nested HTML structures
# Default is usually 1000, increase to 5000 for robust handling
sys.setrecursionlimit(5000)

import pandas as pd
import requests
import time
from bs4 import BeautifulSoup, Comment
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
MAX_LEN = 1000

SEC_RATE = 8  # requests per second
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
    num_fetchers = SEC_RATE  # I/O bound
    num_parsers = cpu_cores - 1 if cpu_cores > 2 else cpu_cores  # CPU bound

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

    print(
        f"⚙️  Configuration: {num_fetchers} fetchers, {num_parsers} parsers, CHUNK_SIZE={chunk_size}"
    )
    return num_fetchers, num_parsers, chunk_size, sec_rate_limit


# %%

# =============================================================================
# REGEX PATTERNS AND KEYWORDS
# =============================================================================
from defs.derivative_lib import ALL_REGEX, STRICT_REGEX, SOFT_REGEX

from defs.acct_std import DER_STD_REGEX
from defs.eq_regex import EXCLUDE_REGEX_EQUITY_COMP
from defs.exclusion_regex import (
    EXCLUDE_REGEX_FORWARD_LOOKING,
    EXCLUDE_REGEX_LEGAL_LITIGATION,
)
from defs.gen_regex import GEN_STRICT_CONTEXT_REGEX, TABLE_REGEX
from defs.shared_context import VALUATION_MODELS_REGEX

# New Header and Structural Cleanup Patterns
HEADER_CLEANUP_PATTERNS = [
    # 1. Markdown Headers: Targets # Title # and similar structure
    (re.compile(r"\n\#+\s*.*?\#*\n", re.IGNORECASE), "\n\n"),
    # 2. Markdown Bold/Italics Emphasis: Targets **Title** or *Title* or _Title_
    # Replaces with space to separate merged text fragments
    (re.compile(r"\*{1,}.*?\*{1,}", re.IGNORECASE), " "),
    (re.compile(r"\_[^\s_].*?[^\s_]\_", re.IGNORECASE), " "),
    # 3. ALL-CAPS DERIVATIVE HEADER DELETION
    # Targets long, non-narrative all-caps sequences containing key terms
    (
        re.compile(
            r"^(?:[^a-z\n]*?(?:DERIVATIVES?|HEDGING)[^a-z\n]*?)(?=[A-Z][a-z])",
            re.MULTILINE,
        ),
        " ",
    ),
    (
        re.compile(r"^\s*[^a-z\n]*?(?:DERIVATIVES?|HEDGING)[^a-z\n]*?$", re.MULTILINE),
        "\n\n",
    ),
    # 4. QUOTED HEADER DELETION (NEW)
    # Targets lines like: "Hedging Activities", "Derivative Instruments"
    # Logic: Start of line + Quote + (Key Terms) + Quote + End of line
    (
        re.compile(
            r'^\s*["“][^"”\n]*?(?:Derivatives?|Hedging|Fair\s+Value|Financial\s+Instruments)[^"”\n]*?["”]\s*$',
            re.MULTILINE | re.IGNORECASE,
        ),
        "\n\n",
    ),
]
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
TABLE_HINT_PATTERN = re.compile(
    r"\b(table|summary|following|below|presented|summarized|\:)\b", re.IGNORECASE
)
# Pattern to find single newlines that are not preceded or followed by another newline (i.e., wrapped lines)
WRAPPED_LINE_PATTERN = re.compile(r"(?<!\n)\n(?!\n)")
SPACE_PATTERN = re.compile(r"\s+")
DOC_PATTERN = re.compile(r'<document>\s*(.*?)\s*</document>', re.DOTALL | re.IGNORECASE)
HTML_REGEX = re.compile(r"<html", re.IGNORECASE)
# %%
# =============================================================================
# LOAD DATA
# =============================================================================
all_derivatives_df = pd.DataFrame()

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


def save_process_result_batch(batch_df):
    if batch_df.empty:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Use executemany logic via pandas to_sql or raw SQL
    try:
        data = list(zip(batch_df.url, batch_df.matches.apply(json.dumps)))
        c.executemany(
            "INSERT OR REPLACE INTO webpage_result (url, matches) VALUES (?, ?)", data
        )
        conn.commit()
    except Exception as e:
        print(f"Batch write error: {e}")
    finally:
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
        older_data = fetch_json(f"https://data.sec.gov/submissions/{f.get('name')}")
        if isinstance(older_data, dict):
            links.extend(extract_filings(older_data, cik, name, ticker))

    return links


# =============================================================================
# CONTENT EXTRACTION
# =============================================================================
import unicodedata


def normalize_unicode(text: str) -> str:
    """
    Converts common Unicode punctuation to ASCII equivalents, then
    normalizes the rest. Preserves dashes and quotes.
    """
    if not text:
        return ""

    # Map common non-ASCII characters to ASCII equivalents
    replacements = {
        # Dashes
        "\u2014": "-",  # Em-dash
        "\u2013": "-",  # En-dash
        "\u2012": "-",  # Figure dash
        "\u2015": "-",  # Horizontal bar
        # Quotes (Smart quotes)
        "\u2018": "'",  # Left single quote
        "\u2019": "'",  # Right single quote
        "\u201c": '"',  # Left double quote
        "\u201d": '"',  # Right double quote
        # Spaces (Non-breaking spaces)
        "\u00a0": " ",  # No-break space
    }

    # 1. Manual replacement of characters that NFKD doesn't handle the way we want
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # 2. Standard normalization for accents and other diacritics
    # Now that dashes are fixed, 'ignore' is safe to use for truly weird characters
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")

def _has_border_top(tag) -> bool:
    """Check if cell has border-top style."""
    style = tag.get("style", "").lower().replace(" ", "")
    return bool(re.search(r"border-top:\s*\w+", style))


def _has_border_bottom(tag) -> bool:
    """Check if cell has border-bottom style."""
    style = tag.get("style", "").lower().replace(" ", "")
    return bool(re.search(r"border-bottom:\s*\w+", style))


def _is_bold_style(tag) -> bool:
    """Check if cell has bold font-weight style."""
    style = tag.get("style", "").lower().replace(" ", "")
    return (
        "font-weight:bold" in style
        or "font-weight:700" in style
        or "font-weight:600" in style
        or "font-weight:bolder" in style
    )


def _detect_header_rows(rows: List[List[str]], table_soup) -> int:
    """
    Detect number of header rows using hierarchical detection logic:
    1. Explicit <th> tags
    2. Border-based detection (top or bottom)
    3. Bold style detection
    4. Fallback: treat first row as header

    Also validates that the first data row has content in the first column.
    """
    if not rows:
        return 0

    trs = table_soup.find_all("tr")

    # Filter TRs to match non-empty rows (same as in main logic)
    filtered_trs = []
    for tr in trs:
        if tr.get_text(strip=True):
            filtered_trs.append(tr)

    if not filtered_trs:
        return 0

    # Rule 1: Check for explicit <th> tags in the opening rows
    header_count = 0
    for tr in filtered_trs:
        if tr.find("th"):
            header_count += 1
        else:
            break

    if header_count > 0:
        # Verify first data row has content in first column
        if header_count < len(filtered_trs):
            first_data_tr = filtered_trs[header_count]
            first_cell = first_data_tr.find(["td", "th"])
            if first_cell and first_cell.get_text(strip=True):
                return header_count
        else:
            return header_count

    # Rule 2: Border-based detection (border-top or border-bottom)
    border_header_count = _detect_by_border(filtered_trs, rows)
    if border_header_count > 0:
        # Verify first data row has content in first column
        if border_header_count < len(filtered_trs):
            first_data_tr = filtered_trs[border_header_count]
            first_cell = first_data_tr.find(["td", "th"])
            if first_cell and first_cell.get_text(strip=True):
                return border_header_count

    # Rule 3: Bold style detection
    header_count = 0
    for tr in filtered_trs:
        has_bold = tr.find(["b", "strong"]) or any(
            _is_bold_style(cell) for cell in tr.find_all(["td", "th"])
        )
        if has_bold:
            header_count += 1
        else:
            break

    if header_count > 0:
        # Verify first data row has content in first column
        if header_count < len(filtered_trs):
            first_data_tr = filtered_trs[header_count]
            first_cell = first_data_tr.find(["td", "th"])
            if first_cell and first_cell.get_text(strip=True):
                return header_count

    # Rule 4: Fallback - treat first row as header if we have data rows
    if rows and filtered_trs:
        first_cell = filtered_trs[0].find(["td", "th"])
        if first_cell and first_cell.get_text(strip=True):
            return 1

    return 1  # Safe default


def _detect_by_border(filtered_trs: List, rows: List[List[str]]) -> int:
    """
    Detect header rows by analyzing borders (top or bottom).

    Strategy:
    - border-top on cells suggests previous row is header (row boundary)
    - border-bottom on cells suggests next row is data (row boundary)
    - Handle multi-level headers: track when borders stop
    """
    if not filtered_trs or not rows:
        return 0

    border_transitions = []  # List of (row_idx, border_type)

    for row_idx, tr in enumerate(filtered_trs):
        cells = tr.find_all(["td", "th"])

        has_border_top = any(_has_border_top(cell) for cell in cells)
        has_border_bottom = any(_has_border_bottom(cell) for cell in cells)

        if has_border_top:
            border_transitions.append((row_idx, "border_top"))
        if has_border_bottom:
            border_transitions.append((row_idx, "border_bottom"))

    if not border_transitions:
        return 0

    # Interpret borders
    # border_top on row N means row N-1 (or rows up to N-1) could be headers
    # border_bottom on row N means row N is the last header row

    first_border_row = border_transitions[0][0]
    first_border_type = border_transitions[0][1]

    if first_border_type == "border_bottom":
        # The row with border_bottom is the last header row
        return first_border_row + 1

    elif first_border_type == "border_top":
        # The row with border_top is the first data row, so headers end at row before
        return first_border_row

    # Fallback
    return 0


def extract_content(data: str, asHTML=True) -> str:
    """
    Extract content using html2text for better recursion handling.
    Preserves tables and structure without deep recursion issues.
    """
    if not data:
        return ""

    if asHTML:
        # Use lxml for significantly faster parsing
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

        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Process tables FIRST before converting to text
        tables = soup.find_all("table")
        for table in tables:
            title = ""
            prologue_text = ""

            if table.caption:
                title = table.caption.get_text(strip=True)

            prev_text = table.find_previous(
                string=lambda s: s.strip() and len(s.strip()) > 20 # type: ignore
            )
            if prev_text:
                prev_string = prev_text.strip()
                if len(prev_string) < 500 and TABLE_HINT_PATTERN.search(prev_string):
                    prologue_text = prev_string

            if title and prologue_text:
                title = f"{prologue_text} | {title}"
            elif prologue_text:
                title = prologue_text

            rows = []
            col_count = 0

            try:
                for tr in table.find_all("tr"):
                    # Skip rows with no visible text
                    if not tr.get_text(strip=True):
                        continue

                    row_cells = []
                    for cell in tr.find_all(["td", "th"]):
                        text = cell.get_text(strip=True)
                        try:
                            colspan = int(cell.get("colspan", 1)) # type: ignore
                        except (ValueError, TypeError):
                            colspan = 1

                        row_cells.append(text)
                        if colspan > 1:
                            row_cells.extend([""] * (colspan - 1))

                    if row_cells:
                        rows.append(row_cells)
                        col_count = max(col_count, len(row_cells))
            except Exception as e:
                print(f"⚠️  Table extraction failed: {e}")

            # Detect header row count using improved logic
            header_count = _detect_header_rows(rows, table)

            # Only convert if there is at least one row and two cols
            if len(rows) > 1 and col_count > 1:
                converter = HTMLTableConverter(
                    grid=rows, title=title, header_row_count=header_count
                )
                generic_table = converter.to_generic_table()
                table_text = generic_table.build()
                pre_tag = soup.new_tag("pre")
                pre_tag.string = table_text
                table.replace_with(pre_tag)
            else:
                # Too short of a table means we convert it to paragraphs
                for tr in table.find_all("tr"):
                    for td in tr.find_all(["td", "th"]):
                        cell_text = td.get_text(strip=True)
                        if cell_text:
                            p_tag = soup.new_tag("p")
                            p_tag.string = cell_text
                            td.replace_with(p_tag)
                table.unwrap()

        # Remove headers and titles, they are false positives
        for header in soup(["h1", "h2", "h3", "h4", "h5", "h6"]):
            header.decompose()

        # Use html2text to convert remaining HTML to text
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.ignore_emphasis = False
        h.body_width = 0
        h.unicode_snob = True

        try:
            soup_str = str(soup)
            text = h.handle(soup_str)
        except Exception as e:
            print(f"⚠️  html2text conversion failed: {e}")
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

    for pattern, replacement in HEADER_CLEANUP_PATTERNS:
        text = pattern.sub(replacement, text)
    for pattern, replacement in CRUNCHED_TEXT_PATTERNS:
        text = pattern.sub(replacement, text)

    text = normalize_unicode(text)
    return text


def fetch_url(
    url: str, timeout: int = 60, rate_limiter: Optional["ThreadSafeRateLimiter"] = None
) -> str | None:
    """
    Fetch URL and properly handle different error types.
    Notifies rate_limiter of 429 errors specifically (not timeouts).
    """
    global SEC_RATE_LIMIT, SEC_RATE
    if not url:
        return None
    try:
        # Use the rate_limiter's current value for sleeping
        time.sleep(rate_limiter.value if rate_limiter else SEC_RATE_LIMIT)
        debug_print("Fetching", url)
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": "sync-fetch@example.com"}
        )
        if resp.status_code == 429:
            print(f"🛑 Rate Limited {resp.status_code} for {url}")
            # Notify rate limiter of 429 specifically
            if rate_limiter:
                rate_limiter.signal_429()
            return None
        if resp.status_code != 200:
            print(f"Error {resp.status_code} for {url}")
            return None
        return resp.text
    except requests.exceptions.Timeout:
        print(f"⏱️  Timeout fetching {url}")
        # Notify rate limiter of timeout (which should NOT increase sleep)
        if rate_limiter:
            rate_limiter.signal_timeout()
        return None
    except requests.exceptions.ConnectionError:
        print(f"🔌 Connection error fetching {url}")
        if rate_limiter:
            rate_limiter.signal_timeout()
        return None
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

# =============================================================================
# KEYWORD FILTERING (OPTIMIZED VERSION)
# =============================================================================


def filter_by_keywords(content: str) -> list[str]:
    """
    Filters content using updated Strict/Soft regex logic.

    1. CAPTURE: ALL_REGEX or (LOOSE + CONTEXT)
    2. EXCLUDE: Litigation
    3. SALVAGE: If Comp -> Keep only if STRICT_REGEX (Swap/Forward) or SOFT_GEN (Accounting)
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

        # ---------------------------------------------------------
        # HANDLE TABLES
        # ---------------------------------------------------------
        if "<table" in lower_part:
            # 1. Hard Exclusion
            if EXCLUDE_REGEX_LEGAL_LITIGATION.search(part):
                continue

            # 2. Capture Logic (Tables are often minimal, so we trust matches more)
            if TABLE_REGEX.search(part) or ALL_REGEX.search(part):

                # 3. Salvage Logic (Comp)
                if EXCLUDE_REGEX_EQUITY_COMP.search(part):
                    # STRICT SAVIOR:
                    # STRICT_REGEX includes IR/FX/CP/Strict-EQ (Swaps), but NOT Options.
                    # SOFT_GEN includes "Hedge Accounting".
                    if not (
                        STRICT_REGEX.search(part)
                        or GEN_STRICT_CONTEXT_REGEX.search(part)
                        or DER_STD_REGEX.search(part)
                        or VALUATION_MODELS_REGEX.search(part)
                        
                    ):
                        continue

                if lower_part not in seen:
                    filtered.append(part)
                    seen.add(lower_part)
            continue

        # ---------------------------------------------------------
        # HANDLE TEXT BLOCKS
        # ---------------------------------------------------------
        paragraphs = part.split("\n\n")
        i = 0
        while i < len(paragraphs):
            para = paragraphs[i].strip()
            para = SPACE_PATTERN.sub(" ", para).strip() if para else ""

            if not para or len(para) < 30:
                i += 1
                continue

            # -----------------------------------------------------
            # 1. CAPTURE LOGIC
            # -----------------------------------------------------
            is_match = False
            # A. Litigation: Hard Delete
            if EXCLUDE_REGEX_LEGAL_LITIGATION.search(para):
                i += 1
                continue
            if EXCLUDE_REGEX_FORWARD_LOOKING.search(para):
                i += 1
                continue
            # Rule A: Standard Regex Match
            if ALL_REGEX.search(para):
                is_match = True

            if is_match:
                # -------------------------------------------------
                # 2. PAGE BREAK MERGING
                # -------------------------------------------------
                ending = para[-1] if para else ""
                if ending and ending not in [".", "?", "!", ">", ":"]:
                    look_ahead_idx = i + 1
                    while look_ahead_idx < len(paragraphs):
                        next_para_raw = paragraphs[look_ahead_idx].strip()
                        next_para = (
                            SPACE_PATTERN.sub(" ", next_para_raw).strip()
                            if next_para_raw
                            else ""
                        )
                        # if it is too short or begins in all caps -> skip
                        if len(next_para) < 30 or next_para.isupper():
                            look_ahead_idx += 1
                            continue

                        # Merge if next paragraph isn't litigation noise
                        if (
                            not EXCLUDE_REGEX_LEGAL_LITIGATION.search(next_para)
                            and len(next_para) + len(para) < MAX_LEN
                        ):
                            para = para + " " + next_para
                            i = look_ahead_idx
                        break

                # -------------------------------------------------
                # 3. EXCLUSION / SALVAGE LOGIC
                # -------------------------------------------------

                # B. Equity Compensation: Conditional Delete
                if EXCLUDE_REGEX_EQUITY_COMP.search(para):
                    # THE SAVIOR CHECK:
                    # STRICT_REGEX now contains "Equity Swaps" but NOT "Equity Options".
                    # So "Equity Options" (without hedge accounting) will fail this check and be discarded.
                    if not (
                        SOFT_REGEX.search(para) or DER_STD_REGEX.search(para)
                    ):
                        i += 1
                        continue

                para_lower = para.lower()
                if para_lower not in seen:
                    filtered.append(para)
                    seen.add(para_lower)

            i += 1

    return filtered


# =============================================================================
# PARALLEL PROCESSING FUNCTIONS (OPTIMIZED FOR PARALLEL CORES)
# =============================================================================


def filter_by_fyear(filings: list[dict], fyear: int) -> list[dict]:
    return [f for f in filings if f.get("report_date", "").startswith(str(fyear))]


def fetch_all_grouped(saveIteration: int = 100):
    """
    Fetch filings using ProcessPoolExecutor for parallelism.
    """
    global existing_report_df, all_derivatives_df, SEC_RATE_LIMIT, SEC_RATE

    records = []

    if existing_report_df is None or existing_report_df.empty:
        existing_report_df = pd.DataFrame(columns=["cik", "year"])

    already_done = set(zip(existing_report_df["cik"], existing_report_df["year"]))
    cik_groups = all_derivatives_df.groupby("cik")["year"].apply(list).reset_index()

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

    Distinguishes between 429 (rate limit) and timeout errors.
    """

    def __init__(self, initial_rate_limit: float):
        self._rate_limit = initial_rate_limit
        self._lock = threading.Lock()
        self._last_429_time = 0
        self._recovery_mode = False
        self._initial_rate_limit = float(initial_rate_limit)
        self._timeout_count = 0  # Track timeouts separately

    @property
    def value(self) -> float:
        """Get the current rate limit value."""
        with self._lock:
            return self._rate_limit

    def signal_429(self):
        """Signal that a 429 (Too Many Requests) response was received."""
        with self._lock:
            self._last_429_time = time.time()
            self._recovery_mode = True
            # Increase sleep time by 50%, capped at 60s
            self._rate_limit = min(self._rate_limit * 1.5, 60.0)
            print(f"🛑 429 Rate Limited! Increasing sleep to {self._rate_limit:.2f}s")

    def signal_timeout(self):
        """Signal that a timeout error occurred (NOT a rate limit)."""
        with self._lock:
            self._timeout_count += 1
            # DO NOT increase sleep time for timeouts - they're network issues, not rate limits
            # Just log it for debugging
            if self._timeout_count % 10 == 0:
                print(
                    f"⏱️  {self._timeout_count} timeouts detected (not increasing sleep rate)"
                )

    def adjust(self, current_rate: float, target_rate: float):
        """Atomically adjust the rate limit based on performance."""
        with self._lock:
            time_since_last_429 = time.time() - self._last_429_time

            # Exit recovery mode if no 429s for 30 seconds
            if self._recovery_mode and time_since_last_429 > 30:
                self._recovery_mode = False

            # Determine target rate based on recovery status
            target_rate_adjusted = (
                target_rate * 0.5 if self._recovery_mode else target_rate
            )

            # --- Main Adjustment Logic (Performance-based) ---
            # This is key: adjust sleep based on ACTUAL vs TARGET fetch rate
            if current_rate > target_rate_adjusted * 1.05:  # Over target - TOO FAST
                # Fetching too fast - increase sleep to slow down
                increase_factor = (
                    1.0
                    + min(
                        (current_rate - target_rate_adjusted) / target_rate_adjusted,
                        1.0,
                    )
                    * 0.1
                )
                self._rate_limit *= increase_factor

            elif current_rate < target_rate_adjusted * 0.95:  # Under target - TOO SLOW
                # Fetching too slow - decrease sleep to speed up
                # NO LOWER BOUND - can go below initial rate if needed!
                if not self._recovery_mode:
                    decrease_factor = 0.98
                    self._rate_limit *= decrease_factor

            # --- Gradual Recovery Logic ---
            # Only decay back to initial if we're above it AND not in recovery
            if not self._recovery_mode and self._rate_limit > self._initial_rate_limit:
                gap = self._rate_limit - self._initial_rate_limit
                decay_step = 0.10  # 10% decay per check
                self._rate_limit = max(
                    self._initial_rate_limit, self._rate_limit - gap * decay_step
                )

            return self._rate_limit, self._recovery_mode, target_rate_adjusted


def adjust_rate_in_background(
    tqdm_bar: tqdm,
    rate_limiter: ThreadSafeRateLimiter,
    target_rate: float,
    stop_event: threading.Event,
):
    """
    A background thread to dynamically adjust the sleep rate.
    Only adjusts for actual rate limit conditions, not timeouts.
    """
    prev_count = getattr(tqdm_bar, "n", 0)
    prev_time = time.time()
    last_sleep = rate_limiter.value

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

        # Atomically adjust the rate and get the current state
        current_sleep, in_recovery, target_rate_adjusted = rate_limiter.adjust(
            current_rate, target_rate
        )
        mode = "Recovery" if in_recovery else "Normal"

        # Only update postfix if sleep time changed (reduce noise)
        if abs(current_sleep - last_sleep) > 0.001:  # Changed by more than 1ms
            tqdm_bar.set_postfix(
                rate=f"{current_rate:.1f} req/s",
                sleep=f"{current_sleep*1000:.1f}ms",
                mode=mode,
                target=f"{target_rate_adjusted:.1f} req/s",
            )
            last_sleep = current_sleep

def should_retry_with_plaintext(url: str, raw_text: str, rate_limiter: Optional[ThreadSafeRateLimiter] = None) -> Optional[tuple]:
    """
    Checks if a pre-2011 filing should be retried with plain text URL.
    Returns:
      - ("RETRY", new_txt_url) if retry needed
      - None if no retry needed
      - (url, new_content) if retry succeeded
    """
    try:
        # Check if URL looks like an EDGAR filing
        if "Archives/edgar/data" not in url:
            return None
        
        parts = url.split('/')
        accession = None
        cik_part = None
        
        # Find the part that looks like an accession (18 digits)
        for i, part in enumerate(parts):
            if len(part) == 18 and part.isdigit():
                accession = part
                if i > 0:
                    cik_part = parts[i-1]
                break
        
        if not accession or not cik_part:
            return None
        
        # Extract year from accession (digits 10-12)
        year_str = accession[10:12]
        year = int(year_str)
        is_pre_2011 = (0 <= year <= 10) or (90 <= year <= 99)
        
        if not is_pre_2011:
            return None
        
        # Check length (alphanumeric only)
        if len(raw_text) < 2000000:  # 2MB limit for check
            clean_len = len(re.sub(r'[^a-zA-Z0-9]', '', raw_text))
            
            if clean_len < 100000:
                # Check for strict derivative mentions
                if not STRICT_REGEX.search(raw_text):
                    # Construct plain text URL
                    accession_dashed = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
                    txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik_part}/{accession}/{accession_dashed}.txt"
                    
                    if txt_url != url:
                        debug_print(f"  🔄 Retry with plain text for {url} (Len: {clean_len})")
                        # Return signal to re-queue the new URL
                        return "RETRY", txt_url
    except Exception as e:
        print(f"Error in retry logic for {url}: {e}")
    
    return None


# ============================================================================
# UPDATE fetch_raw_content() - Replace the retry block with this:
# ============================================================================

def fetch_raw_content(url: str, rate_limiter: Optional[ThreadSafeRateLimiter] = None):
    """
    Fetches raw text content from a URL. This is purely I/O-bound.
    Properly distinguishes between different failure modes.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM webpage_result WHERE url = ?", (url,))
    exists = c.fetchone()
    conn.close()
    if exists:
        return None

    raw_text = fetch_url(url, rate_limiter=rate_limiter)

    if raw_text:
        # Try retry logic for short pre-2011 reports
        retry_result = should_retry_with_plaintext(url, raw_text, rate_limiter)
        if retry_result:
            if retry_result[0] == "RETRY":
                # Return signal to re-queue the new .txt URL
                return "RETRY", retry_result[1]
        
        # Successfully fetched (no retry needed)
        return url, raw_text
    elif raw_text is None and url:
        # fetch_url returned None - could be 429, timeout, or other error
        # The rate_limiter was already notified by fetch_url
        return "FAILED", url

    return None


def parse_multi_document_content(raw_text: str) -> List[str]:
    """
    Splits a multi-document .txt file (from SEC EDGAR) into individual documents.
    Each document is wrapped in <document></document> tags.
    
    For each document:
    - If it contains HTML, parse as HTML
    - Otherwise, parse as plain text
    
    Returns list of cleaned content strings (one per document).
    """
    if not raw_text:
        return []
    
    # Split by <document> tags (exact match, no attributes)
    
    documents = DOC_PATTERN.findall(raw_text)
    
    if not documents:
        # No document tags found, treat entire content as single document
        documents = [raw_text]
    
    parsed_contents = []
    
    for i, doc_content in enumerate(documents):
        doc_content = doc_content.strip()
        
        if not doc_content:
            continue
        
        # Detect if this document is HTML (only check for html/body tags)
        is_html = bool(HTML_REGEX.search(doc_content))
        
        try:
            if is_html:
                debug_print(f"  📄 Document {i+1}: Parsing as HTML")
                content = extract_content(doc_content, asHTML=True)
            else:
                debug_print(f"  📄 Document {i+1}: Parsing as plain text")
                content = extract_content(doc_content, asHTML=False)
            
            if content and len(content.strip()) > 0:
                parsed_contents.append(content)
        
        except Exception as e:
            print(f"  ⚠️  Error parsing document {i+1}: {e}")
            continue
    
    return parsed_contents

def parse_content(data):
    """
    Parses raw HTML/text, handles multi-document files, filters for keywords, 
    and saves to the database. This is a CPU-bound task.
    
    Handles:
    - Multi-document .txt files (split by <document> tags)
    - HTML and plain text documents
    - Keyword filtering per document
    - Returns aggregated results across all documents
    """
    if data is None:
        return None

    url, raw_text = data

    try:
        # 1. Parse multi-document content
        # This splits by <document> tags and extracts/parses each document
        parsed_documents = parse_multi_document_content(raw_text)
        
        if not parsed_documents:
            debug_print(f"No documents parsed from {url}")
            return None

        # 2. Filter each document for keywords and aggregate results
        all_matches = []
        
        for doc_idx, content in enumerate(parsed_documents):
            if not content or len(content.strip()) < 50:
                debug_print(f"  Skipping document {doc_idx + 1}: too short")
                continue
            
            try:
                # Filter this document for keywords (CPU-intensive)
                doc_matches = filter_by_keywords(content)
                
                if doc_matches:
                    debug_print(f"  Document {doc_idx + 1}: Found {len(doc_matches)} matches")
                    all_matches.extend(doc_matches)
                else:
                    debug_print(f"  Document {doc_idx + 1}: No matches found")
                    
            except Exception as e:
                print(f"  ⚠️  Error filtering document {doc_idx + 1} from {url}: {e}")
                continue
        
        # 3. If we found any matches across all documents, save the result
        if all_matches:
            result_row = pd.Series({
                "url": url, 
                "matches": all_matches,
            })
            debug_print(f"✓ Successfully parsed {len(parsed_documents)} documents from {url}")
            return result_row
        else:
            debug_print(f"No keyword matches found in any document from {url}")
            return None

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
        reports_to_process[i : i + CHUNK_SIZE]
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
                for url in chunk
                if isinstance(url, str)
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
                                tqdm_bar.set_postfix_str(
                                    f"RATE LIMITED! New sleep: {rate_limiter.value*1000:.1f}ms"
                                )
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

        batch_results = []
        with ProcessPoolExecutor(max_workers=NUM_PARSERS) as parse_executor:
            parse_futures = [
                parse_executor.submit(parse_content, data) for data in fetched_data
            ]

            for future in tqdm(
                as_completed(parse_futures),
                total=len(parse_futures),
                desc=f"  Parsing chunk {chunk_idx}",
                leave=False,
            ):
                try:
                    result = future.result()
                    if result is not None:
                        debug_print("Parse successful")
                        batch_results.append(result)  # Collect it
                        chunk_results += 1
                    else:
                        chunk_empty += 1
                        debug_print("Error with processing")
                except Exception as e:
                    print(f"Parse error: {e}")
                    chunk_empty += 1

        if batch_results:
            print(f"  💾 Saving batch of {len(batch_results)} records...")
            # Convert list of Series to DataFrame
            df_batch = pd.DataFrame(batch_results)
            save_process_result_batch(df_batch)

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
def process_producer_consumer_adaptive():
    """
    Producer-Consumer model with ADAPTIVE rate limiting.
    Continuously monitors fetch rate and adjusts sleep dynamically.
    """
    manager = mp.Manager()

    # 1. Setup Queues
    url_queue = manager.Queue()
    raw_queue = manager.Queue(maxsize=CHUNK_SIZE)
    result_queue = manager.Queue()

    # 2. Shared Stats
    items_processed = manager.dict({"count": 0})
    counter_lock = manager.Lock()

    # 3. Shared rate limiter (for all fetchers to use)
    rate_limiter = ThreadSafeRateLimiter(SEC_RATE_LIMIT)

    # 4. Metrics for rate adjustment (shared across fetchers)
    fetch_metrics = manager.dict(
        {
            "fetch_count": 0,
            "last_sample_time": time.time(),
            "last_adjustment_time": time.time(),
        }
    )
    metrics_lock = manager.Lock()

    # 5. Populate Queue
    processed_set = get_processed_urls()
    total_files_in_manifest = len(existing_report_df)
    already_in_warehouse = len(processed_set)

    print("=" * 60)
    print(f"   • Total Files in Manifest:    {total_files_in_manifest:,}")
    print(f"   • Already Processed:          {already_in_warehouse:,}")
    print(
        f"   • Net Requirements (ToDo):    {total_files_in_manifest - already_in_warehouse:,}"
    )
    print("=" * 60)

    print("Populating Queue with Net Requirements...")
    initial_count = 0

    for r in existing_report_df.itertuples(index=False):
        if r.url and (r.url,) not in processed_set:
            url_queue.put(r.url)
            initial_count += 1

    print(f"Queue populated with {initial_count} reports.")

    if initial_count == 0:
        print("Nothing to process.")
        return

    # 6. Start Workers
    db_thread = threading.Thread(
        target=db_writer_worker,
        args=(result_queue, DB_PATH, items_processed, counter_lock, initial_count),
        daemon=False,
    )
    db_thread.start()

    parsers = []
    for _ in range(NUM_PARSERS):
        p = mp.Process(target=parse_worker, args=(raw_queue, result_queue))
        p.start()
        parsers.append(p)

    # 7. Start fetchers WITH rate limiter
    fetchers = []
    stop_event = threading.Event()

    for _ in range(NUM_FETCHERS):
        t = threading.Thread(
            target=fetch_worker_adaptive,
            args=(
                url_queue,
                raw_queue,
                rate_limiter,
                stop_event,
                fetch_metrics,
                metrics_lock,
            ),
            daemon=False,
        )
        t.start()
        fetchers.append(t)

    # 8. Start RATE ADJUSTER thread (monitors and adjusts sleep rate)
    rate_adjuster = threading.Thread(
        target=rate_adjuster_worker,
        args=(rate_limiter, fetch_metrics, metrics_lock, stop_event, SEC_RATE),
        daemon=False,
    )
    rate_adjuster.start()

    # 9. Monitoring Loop
    last_save_time = time.time()

    with tqdm(total=initial_count, unit="files", smoothing=0.1) as pbar:
        try:
            stalled_count = 0
            prev_done = 0

            while True:
                time.sleep(1)

                # A. Update Progress Bar
                current_done = items_processed["count"]
                pbar.n = current_done
                pbar.refresh()

                # B. Update Stats (Postfix)
                q_rem = url_queue.qsize() if hasattr(url_queue, "qsize") else "N/A"
                inv_size = raw_queue.qsize() if hasattr(raw_queue, "qsize") else "N/A"

                pbar.set_postfix(
                    remaining=q_rem,
                    inventory=f"{inv_size}/{CHUNK_SIZE}",
                    sleep=f"{rate_limiter.value*1000:.1f}ms",
                )

                # C. Check Backup Trigger
                if IS_COLAB and (
                    time.time() - last_save_time > DRIVE_SAVE_INTERVAL_SECONDS
                ):
                    pbar.write("  💾 Triggering Background Backup...")
                    try:
                        subprocess.Popen(
                            SAVE_SHELL_CMD,
                            shell=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        last_save_time = time.time()
                    except Exception as e:
                        pbar.write(f"  ⚠️ Backup failed: {e}")

                # D. Exit Condition
                if current_done >= initial_count and initial_count > 0:
                    pbar.write("✓ All items processed!")
                    break

                # E. Stall detection
                if current_done == prev_done:
                    stalled_count += 1
                    if stalled_count >= 100 and stalled_count % 25 == 0:
                        pbar.write("⚠️  Pipeline stalled! Checking queue status...")
                        pbar.write(
                            f"   URL Queue: {url_queue.qsize()}, Raw Queue: {raw_queue.qsize()}, Result Queue: {result_queue.qsize()}"
                        )
                        if stalled_count > 600:
                            pbar.write("⚠️  Force-exiting stalled pipeline...")
                            break
                else:
                    stalled_count = 0

                prev_done = current_done

        except KeyboardInterrupt:
            pbar.write("Stopping pipeline...")

        finally:
            # SHUTDOWN SEQUENCE
            pbar.write("Initiating shutdown...")
            stop_event.set()

            # Wait for rate adjuster
            rate_adjuster.join(timeout=5)

            # Wait for fetchers to complete
            for t in fetchers:
                t.join(timeout=5)
                if t.is_alive():
                    pbar.write("⚠️  Fetcher thread did not terminate gracefully")

            # Signal parsers to stop
            for _ in range(NUM_PARSERS):
                raw_queue.put(None)

            for p in parsers:
                p.join(timeout=5)
                if p.is_alive():
                    pbar.write("⚠️  Parser process did not terminate gracefully")
                    p.terminate()

            # Signal DB writer to stop
            result_queue.put(None)
            db_thread.join(timeout=10)
            if db_thread.is_alive():
                pbar.write("⚠️  DB writer thread did not terminate gracefully")

            # Final Save
            if IS_COLAB:
                print("Performing final backup...")
                subprocess.run(SAVE_SHELL_CMD, shell=True)

            print("Pipeline finished.")


def rate_adjuster_worker(
    rate_limiter, fetch_metrics, metrics_lock, stop_event, target_rate
):
    """
    BACKGROUND THREAD: Continuously monitors fetch rate and adjusts sleep dynamically.

    This is the "adaptive" component that makes the producer-consumer model responsive
    to server throttling and network conditions.
    """
    prev_fetch_count = 0
    prev_time = time.time()
    last_recovery_check = time.time()

    while not stop_event.is_set():
        time.sleep(0.5)  # Check 2x per second (more responsive than old 0.25s)

        try:
            with metrics_lock:
                current_fetch_count = fetch_metrics["fetch_count"]
                sample_time = fetch_metrics["last_sample_time"]

            now = time.time()
            elapsed = now - prev_time

            # Calculate current fetch rate (requests/second)
            if elapsed > 0:
                current_rate = (current_fetch_count - prev_fetch_count) / elapsed
            else:
                current_rate = 0.0

            prev_fetch_count = current_fetch_count
            prev_time = now

            # Call the rate limiter's atomic adjust method
            # This returns updated sleep value and recovery mode status
            new_sleep, in_recovery, target_rate_adjusted = rate_limiter.adjust(
                current_rate, target_rate
            )

            # Log periodically (every 5 seconds)
            if now - last_recovery_check > 5:
                last_recovery_check = now

        except Exception as e:
            print(f"⚠️  Rate adjuster error: {e}")


def fetch_worker_adaptive(
    url_queue, raw_queue, rate_limiter, stop_event, fetch_metrics, metrics_lock
):
    """
    PRODUCER: Downloads content and puts into raw_queue.
    Reports fetch attempts to metrics for rate adjustment.
    """
    while not stop_event.is_set():
        try:
            # Get a URL with timeout to allow checking stop_event
            url = url_queue.get(timeout=1)
        except queue.Empty:
            continue

        try:
            # 1. Apply Rate Limit (dynamically adjusted by rate_adjuster_worker)
            sleep_time = rate_limiter.value
            time.sleep(sleep_time)

            # 2. Update metrics (increment fetch attempt)
            with metrics_lock:
                fetch_metrics["fetch_count"] += 1
                fetch_metrics["last_sample_time"] = time.time()

            # 3. Fetch
            result = fetch_raw_content(url, rate_limiter)

            # 4. Put into Queue
            if result:
                if result[0] == "RETRY":
                    # Re-queue the new .txt URL
                    url_queue.put(result[1])
                if result[0] == "RATE_LIMITED":
                    # Explicit rate limit - signal the rate limiter
                    rate_limiter.signal_429()
                    # Put URL back for retry (sleep already increased)
                    url_queue.put(url)

                elif result[0] == "FAILED":
                    # Other failure (timeout, connection error) - retry but don't increase sleep
                    rate_limiter.signal_timeout()
                    url_queue.put(url)
                    time.sleep(0.5)

                else:
                    # Successfully fetched - put in raw queue
                    # This BLOCKS if queue is full, creating backpressure
                    try:
                        raw_queue.put(result, timeout=5)
                    except queue.Full:
                        # Queue is full - put URL back and try again later
                        url_queue.put(url)
                        time.sleep(0.5)

        except Exception as e:
            print(f"Fetch worker error: {e}")

        finally:
            # Always mark as done for queue accounting
            url_queue.task_done()


def save_batch(conn, buffer):
    if not buffer:
        return
    try:
        df_batch = pd.DataFrame(buffer)
        c = conn.cursor()
        data = list(zip(df_batch.url, df_batch.matches.apply(json.dumps)))
        c.executemany(
            "INSERT OR REPLACE INTO webpage_result (url, matches) VALUES (?, ?)", data
        )
        conn.commit()
    except Exception as e:
        print(f"DB Write Error: {e}")


def db_writer_worker(
    result_queue,
    db_path,
    shared_counter,
    counter_lock,
    total_expected,
    save_interval=50,
):
    """Consumes results, writes to DB, and updates the shared_counter."""
    buffer = []
    conn = sqlite3.connect(db_path)
    processed = 0

    while processed < total_expected:
        try:
            result = result_queue.get(timeout=2)
        except queue.Empty:
            if buffer:
                save_batch(conn, buffer)
                with counter_lock:
                    shared_counter["count"] += len(buffer)
                processed += len(buffer)
                buffer = []
            continue

        if result is None:
            if buffer:
                save_batch(conn, buffer)
                with counter_lock:
                    shared_counter["count"] += len(buffer)
                processed += len(buffer)
            break

        buffer.append(result)

        if len(buffer) >= save_interval:
            save_batch(conn, buffer)
            with counter_lock:
                shared_counter["count"] += len(buffer)
            processed += len(buffer)
            buffer = []

    conn.close()


def parse_worker(raw_queue, result_queue):
    """CONSUMER: Takes raw content and puts parsed results into result_queue."""
    while True:
        try:
            data = raw_queue.get(timeout=2)
        except queue.Empty:
            continue

        if data is None:
            break

        try:
            parsed_result = parse_content(data)
            if parsed_result is not None:
                result_queue.put(parsed_result)
        except Exception as e:
            print(f"Parse worker error: {e}")


# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
if __name__ == "__main__":
    create_db()
    existing_report_df = fetch_report_data()
    print(f"Found {len(existing_report_df)} reports in database")
    NUM_FETCHERS, NUM_PARSERS, CHUNK_SIZE, SEC_RATE_LIMIT = get_system_config()
    all_derivatives_df = pd.read_csv(ALL_FIRMS_DATA)
    if IS_COLAB:
        print("Running in Google Colab environment")
        if not Path(DB_PATH).exists():
            print("Loading database from Google Drive...")
            subprocess.run(LOAD_SHELL_CMD, shell=True)
    else:
        print("Running in local environment")

    print("=" * 70)
    print("STEP 1: Fetch all 10-K report URLs from SEC")
    print("=" * 70)
    # Uncomment to run:
    # fetch_all_grouped()

    print("\n" + "=" * 70)
    print(f"STEP 2: Perform keyword extraction in parallel (ADAPTIVE)")
    print("=" * 70)

    # Use the adaptive version
    process_producer_consumer_adaptive()

    print("\n" + "=" * 70)
    print("All done!")
    print("=" * 70)


existing_report_df = pd.DataFrame()
# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
if __name__ == "__main__":
    create_db()
    existing_report_df = fetch_report_data()
    print(f"Found {len(existing_report_df)} reports in database")
    NUM_FETCHERS, NUM_PARSERS, CHUNK_SIZE, SEC_RATE_LIMIT = get_system_config()
    all_derivatives_df = pd.read_csv(ALL_FIRMS_DATA)
    if IS_COLAB:
        print("Running in Google Colab environment")
        if not Path(DB_PATH).exists():
            print("Loading database from Google Drive...")
            subprocess.run(LOAD_SHELL_CMD, shell=True)
    else:
        print("Running in local environment")
    print("=" * 70)
    print("STEP 1: Fetch all 10-K report URLs from SEC")
    print("=" * 70)
    # Uncomment to run:
    # fetch_all_grouped()

    print("\n" + "=" * 70)
    print(f"STEP 2: Perform keyword extraction in parallel")
    print("=" * 70)
    # Uncomment to run:
    # process_all_reports_fully()
    process_producer_consumer_adaptive()
    print("\n" + "=" * 70)
    print("All done!")
    print("=" * 70)

# %%
