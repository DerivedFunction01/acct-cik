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
from typing import List, Optional, Tuple
import random
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from tqdm import tqdm
import multiprocessing as mp
import psutil
from pathlib import Path
import threading
import html2text
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
from table_definitions import HTMLTableConverter

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
DOC_PATTERN = re.compile(r"<document>\s*(.*?)\s*</document>", re.DOTALL | re.IGNORECASE)
HTML_REGEX = re.compile(r"<html", re.IGNORECASE)
XML_REGEX = re.compile(r"xml", re.IGNORECASE)



ITEM_1_START_PATTERN = re.compile(
    r"^\s*(?:ITEM\s+)?1[.\s]+(?:BUSINESS|DESCRIPTION OF BUSINESS|OPERATIONS)",
    re.MULTILINE | re.IGNORECASE,
)
ITEM_1A_START_PATTERN = re.compile(
    r"^\s*(?:ITEM\s+)?1A[.\s]+(?:RISK FACTORS|RISKS?)", re.MULTILINE | re.IGNORECASE
)

ITEM_1B_START_PATTERN = re.compile(
    r"^\s*(?:ITEM\s+)?1B[.\s]", re.MULTILINE | re.IGNORECASE
)

ITEM_2_START_PATTERN = re.compile(
    r"^\s*(?:ITEM\s+)?2[.\s]", re.MULTILINE | re.IGNORECASE
)

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
        # Check if report_data has the accession column, if not, recreate it
        try:
            c.execute("SELECT accession FROM report_data LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("DROP TABLE IF EXISTS report_data")

        # Drop webpage_result to enforce new schema (accession based)
        c.execute("DROP TABLE IF EXISTS webpage_result")

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS report_data (
                cik INTEGER,
                year INTEGER,
                url TEXT,
                accession TEXT,
                original_url TEXT
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
                accession TEXT PRIMARY KEY,
                item1 TEXT,
                item1a TEXT
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
        c.execute("CREATE INDEX IF NOT EXISTS report_acc_idx ON report_data (accession)")
        c.execute("CREATE INDEX IF NOT EXISTS acc_idx ON webpage_result (accession)")
        c.execute("CREATE INDEX IF NOT EXISTS name_idx ON names (name)")
        
        # Cleanup: Remove duplicates from report_data based on accession
        # Keeps the row with the minimum rowid (oldest)
        c.execute("""
            DELETE FROM report_data 
            WHERE accession IS NOT NULL 
            AND rowid NOT IN (
                SELECT MIN(rowid) FROM report_data WHERE accession IS NOT NULL GROUP BY accession
            )
        """)
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
            report = df[["cik", "year", "url"]].copy()
            report["original_url"] = report["url"]
            
            def get_acc(u):
                info = extract_accession_info(u)
                return info["accession"] if info else None
                
            report["accession"] = report["url"].apply(get_acc)
            
            # Deduplicate by accession to ensure integrity before insertion
            report = report.drop_duplicates(subset=["accession"])
            
            report.to_sql("report_data", conn, if_exists="append", index=False)
            return True
        except sqlite3.IntegrityError:
            debug_print(df.head())
            df = df[["cik", "year", "url"]]
            df["reason"] = "Error submitting batch"
            df.to_sql("fail_results", conn, if_exists="append", index=False)
            return False


def fetch_report_data(valid=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check if DB is empty
    try:
        c.execute("SELECT count(*) FROM report_data")
        count = c.fetchone()[0]
    except sqlite3.OperationalError:
        count = 0
        
    # If empty, try to load from CSV
    if count == 0 and Path(REPORT_CSV_PATH).exists():
        print(f"📥 Importing {REPORT_CSV_PATH} into database...")
        try:
            df = pd.read_csv(REPORT_CSV_PATH)
            if {'cik', 'year', 'url'}.issubset(df.columns):
                # Use a dictionary to deduplicate by accession
                unique_records = {}
                for _, row in df.iterrows():
                    u = row['url']
                    info = extract_accession_info(u)
                    acc = info['accession'] if info else None
                    # Only add if we have an accession and haven't seen it yet
                    if acc and acc not in unique_records:
                        unique_records[acc] = (row['cik'], row['year'], u, acc, u)
                
                c.executemany(
                    "INSERT INTO report_data (cik, year, url, accession, original_url) VALUES (?, ?, ?, ?, ?)", 
                    list(unique_records.values())
                )
                conn.commit()
                print(f"✅ Imported {len(unique_records)} unique rows.")
        except Exception as e:
            print(f"❌ Error importing CSV: {e}")
            
    query = "SELECT * FROM report_data"
    if valid:
        query += " WHERE url IS NOT NULL AND url != ''"
    else:
        query += " WHERE url IS NULL OR url = ''"
        
    try:
        pre_data = pd.read_sql_query(query, conn)
    except Exception:
        pre_data = pd.DataFrame(columns=["cik", "year", "url", "accession", "original_url"])
        
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


def get_processed_accessions() -> set:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT accession FROM webpage_result")
    rows = c.fetchall()
    conn.close()
    return set(r[0] for r in rows)


def save_process_result(df):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO webpage_result (accession, item1, item1a) VALUES (?, ?, ?)",
        (df.accession, json.dumps(df.item1), json.dumps(df.item1a)),
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
        data = list(zip(batch_df.accession, batch_df.item1.apply(json.dumps), batch_df.item1a.apply(json.dumps)))
        c.executemany(
            "INSERT OR REPLACE INTO webpage_result (accession, item1, item1a) VALUES (?, ?, ?)", data
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
                string=lambda s: s.strip() and len(s.strip()) > 20  # type: ignore
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
                            colspan = int(cell.get("colspan", 1))  # type: ignore
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


def filter_for_item1(content: str) -> Tuple[str, str]:
    """
    Filters content using updated Strict/Soft regex logic.

    1. CAPTURE: ITEM 1 AND ITEM 1A
    2. RETURNS: 1st element: ITEM 1, 2nd element: ITEM 1A
    """
    matches = []
    for m in ITEM_1_START_PATTERN.finditer(content):
        matches.append((m.start(), '1'))
    for m in ITEM_1A_START_PATTERN.finditer(content):
        matches.append((m.start(), '1A'))
    for m in ITEM_1B_START_PATTERN.finditer(content):
        matches.append((m.start(), '1B'))
    for m in ITEM_2_START_PATTERN.finditer(content):
        matches.append((m.start(), '2'))
    
    if not matches:
        return "", ""

    matches.sort(key=lambda x: x[0])
    
    item1 = ""
    item1a = ""
    
    # Greedy extraction: Find the longest block for Item 1 and Item 1A
    for i, (start, label) in enumerate(matches):
        end = len(content)
        if i + 1 < len(matches):
            end = matches[i+1][0]
            
        text_block = content[start:end]
        
        if label == '1':
            if len(text_block) > len(item1):
                item1 = text_block
        elif label == '1A':
            if len(text_block) > len(item1a):
                item1a = text_block
                
    return item1, item1a

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

            if self._rate_limit >= 60.0:
                print("🛑 CRITICAL: Rate limit reached 60s. Pausing for 1 minutes...")
                time.sleep(60)

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

    def adjust(
        self, current_rate: float, target_rate: float, inventory_full: bool = False
    ):
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
                if not self._recovery_mode and not inventory_full:
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


def extract_accession_info(url: str) -> Optional[dict]:
    """
    Extracts accession number, CIK, and year from an SEC EDGAR URL.
    Returns None if not a valid EDGAR URL or accession not found.
    """
    if "Archives/edgar/data" not in url:
        return None

    parts = url.split("/")
    accession = None
    cik_part = None

    # Find the part that looks like an accession (18 digits)
    for i, part in enumerate(parts):
        if len(part) == 18 and part.isdigit():
            accession = part
            if i > 0:
                cik_part = parts[i - 1]
            break

    if not accession:
        return None

    # Extract year from accession (digits 10-12)
    year_str = accession[10:12]
    try:
        year = int(year_str)
    except ValueError:
        return None
        
    # Determine if pre-2011 (approximate logic based on 2-digit year)
    # 90-99 -> 1990-1999
    # 00-10 -> 2000-2010
    is_pre_2011 = (0 <= year <= 10) or (90 <= year <= 99)

    return {
        "accession": accession,
        "cik": cik_part,
        "year_short": year,
        "is_pre_2011": is_pre_2011,
        "filename": parts[-1] if parts else ""
    }


def update_report_url(old_url: str, new_url: str):
    """Updates the URL in report_data table to maintain consistency."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE report_data SET url = ? WHERE url = ?", (new_url, old_url))
        if c.rowcount > 0:
             debug_print(f"  📝 Updated report_data: {old_url} -> {new_url}")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating report_data: {e}")


def is_url_from_accession(url: str) -> bool:
    """
    Checks if a URL is a raw text submission file derived from an accession number.
    """
    if not url.endswith(".txt"):
        return False
        
    info = extract_accession_info(url)
    if not info:
        return False
        
    accession = info["accession"]
    filename = info["filename"]
    
    expected_filename = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}.txt"
    return filename == expected_filename


def should_retry_with_plaintext(
    url: str, raw_text: str, rate_limiter: Optional[ThreadSafeRateLimiter] = None
) -> Optional[tuple]:
    """
    Checks if a pre-2011 filing should be retried with plain text URL.
    Returns:
      - ("RETRY", new_txt_url) if retry needed
      - None if no retry needed
    """
    try:
        info = extract_accession_info(url)
        if not info or not info["is_pre_2011"] or not info["cik"]:
            return None

        accession = info["accession"]
        cik_part = info["cik"]

        # Construct plain text URL filename to check against current URL
        accession_dashed = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
        txt_filename = f"{accession_dashed}.txt"

        # Prevent infinite loop: if we are already at the target .txt file, stop.
        if url.endswith(txt_filename):
            return None

        # Parse content to check Item 1/1A length
        docs = parse_multi_document_content(raw_text)
        has_valid_content = False
        
        for doc in docs:
            i1, i1a = filter_for_item1(doc)
            # Retry if either is too short (Item 1 < 1000 or Item 1A < 50)
            if len(i1) > 1000 and len(i1a) > 50:
                has_valid_content = True
                break
        
        if not has_valid_content:
            txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik_part}/{accession}/{txt_filename}"
            if txt_url != url:
                debug_print(f"  🔄 Retry with plain text for {url}")
                return "RETRY", url, txt_url

    except Exception as e:
        print(f"Error in retry logic for {url}: {e}")

    return None


def fetch_raw_content(url: str, accession: str, rate_limiter: Optional[ThreadSafeRateLimiter] = None):
    """
    Fetches raw text content from a URL. This is purely I/O-bound.
    Properly distinguishes between different failure modes.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM webpage_result WHERE accession = ?", (accession,))
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
                return retry_result

        # Successfully fetched (no retry needed)
        return url, accession, raw_text
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
        
        # Quick check: does it even mention item1 and item 1a?
        if not ITEM_1_START_PATTERN.search(doc_content) and not ITEM_1A_START_PATTERN.search(doc_content):
            continue

        # Detect if this document is HTML (only check for html/body tags)
        is_html = bool(HTML_REGEX.search(doc_content))

        try:
            if is_html:
                debug_print(f"  📄 Document {i+1}: Parsing as HTML")
                content = extract_content(doc_content, asHTML=True)
            elif XML_REGEX.search(doc_content):  # just check if the word "xml exists"
                debug_print(f"  📄 Document {i+1}: Is XML, skipping")
                continue
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

    url, accession, raw_text = data

    try:
        # 1. Parse multi-document content
        # This splits by <document> tags and extracts/parses each document
        parsed_documents = parse_multi_document_content(raw_text)

        if not parsed_documents:
            debug_print(f"No documents parsed from {url}")
            return None

        # 2. Filter each document for keywords and aggregate results
        item1_matches = []
        item1a_matches = []

        for doc_idx, content in enumerate(parsed_documents):
            if not content or len(content.strip()) < 200:
                debug_print(f"  Skipping document {doc_idx + 1}: too short")
                continue

            try:
                # Filter this document for keywords (CPU-intensive)
                item1, item1a = filter_for_item1(content)

                if item1:
                    debug_print(
                        f"  Document {doc_idx + 1}: Found item 1"
                    )
                    item1_matches.append(item1)
                else:
                    debug_print(f"  Document {doc_idx + 1}: No matches found")
                if item1a:
                    debug_print(
                        f"  Document {doc_idx + 1}: Found item 1a"
                    )
                    item1a_matches.append(item1a)
                else:
                    debug_print(f"  Document {doc_idx + 1}: No matches found")

            except Exception as e:
                print(f"  ⚠️  Error filtering document {doc_idx + 1} from {url}: {e}")
                continue

        # 3. If we found any matches across all documents, save the result
        result_row = pd.Series(
            {
                "url": url,
                "accession": accession,
                "item1": item1_matches,
                "item1a": item1a_matches,
            }
        )
        if item1_matches and item1a_matches:
            debug_print(
                f"✓ Successfully parsed {len(parsed_documents)} documents from {url}"
            )
        else:
            debug_print(f"No keyword matches found in any document from {url}")

        return result_row

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
    processed_set = get_processed_accessions()
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
        # Check if accession is in processed set
        if r.url and r.accession and r.accession not in processed_set:
            # Queue tuple: (url, accession)
            url_queue.put((r.url, r.accession))
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
        args=(
            rate_limiter,
            fetch_metrics,
            metrics_lock,
            stop_event,
            SEC_RATE,
            raw_queue,
        ),
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
    rate_limiter, fetch_metrics, metrics_lock, stop_event, target_rate, raw_queue=None
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

            # Check inventory pressure
            inventory_full = False
            if raw_queue is not None:
                try:
                    # If inventory is nearly full (e.g. > 90%), we are blocked by consumers.
                    # Don't decrease sleep time (don't speed up fetching) in this case.
                    if raw_queue.qsize() >= CHUNK_SIZE * 0.9:
                        inventory_full = True
                except Exception:
                    pass

            # Call the rate limiter's atomic adjust method
            # This returns updated sleep value and recovery mode status
            new_sleep, in_recovery, target_rate_adjusted = rate_limiter.adjust(
                current_rate, target_rate, inventory_full=inventory_full
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
            item = url_queue.get(timeout=1)
            if isinstance(item, tuple):
                url, accession = item
            else:
                # Fallback if queue has old format (shouldn't happen with new logic)
                url = item
                data = extract_accession_info(url)
                if not data:
                    continue
                accession = data["accession"]

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
            result = fetch_raw_content(url, accession, rate_limiter)

            # 4. Put into Queue
            if result:
                if result[0] == "RETRY":
                    # Re-queue the new .txt URL
                    if len(result) == 3:
                        # result is ("RETRY", old_url, new_url)
                        # We re-queue with the SAME accession
                        new_url_val = result[2]
                        url_queue.put((new_url_val, accession))
                    else:
                        # Fallback
                        url_queue.put((result[1], accession))
                if result[0] == "RATE_LIMITED":
                    # Explicit rate limit - signal the rate limiter
                    rate_limiter.signal_429()
                    # Put URL back for retry (sleep already increased)
                    url_queue.put((url, accession))

                elif result[0] == "FAILED":
                    # Other failure (timeout, connection error) - retry but don't increase sleep
                    rate_limiter.signal_timeout()
                    url_queue.put((url, accession))
                    time.sleep(0.5)

                else:
                    # Successfully fetched - put in raw queue
                    # This BLOCKS if queue is full, creating backpressure
                    try:
                        raw_queue.put(result, timeout=5)
                    except queue.Full:
                        # Queue is full - put URL back and try again later
                        url_queue.put((url, accession))
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
        data = list(zip(df_batch.accession, df_batch.item1.apply(json.dumps), df_batch.item1a.apply(json.dumps)))
        c.executemany(
            "INSERT OR REPLACE INTO webpage_result (accession, item1, item1a) VALUES (?, ?, ?)", data
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
