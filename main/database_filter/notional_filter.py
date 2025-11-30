# filter_zero_amounts.py
# =============================================================================
# PHASE 6: QUANTITATIVE ZERO FILTERING (Strict Mapping)
# =============================================================================
# Removes sentences where the quantitative amounts indicate no exposure
# specifically for the reporting year.
#
# Logic:
# 1. Extracts Years (ordered by position) and Values (ordered by position).
# 2. Strict Mapping Check:
#    - If count(Years) == count(Values) (e.g., 2 years, 2 values):
#    - Assume parallel structure (1st Year -> 1st Value).
#    - If Reporting Year's value is Zero -> DISCARD.
# 3. Fallback "All Zero" Check:
#    - If NO positive numbers exist (excluding years) -> DISCARD.
# =============================================================================

import sqlite3
import json
import re
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
from typing import List, Tuple, Dict, Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "active_data2.db"
FINAL_DB_PATH = "active_nonzero_data.db"

from derivative_regex import IMMATERIAL_PATTERN, SENTENCE_SPLIT_PATTERN, CURRENCY_SYMBOL_PATTERN, YEAR_REGEX, check_for_instrument, validate_instrument_retention


# =============================================================================
# REGEX PATTERNS
# =============================================================================

# 2. Zero Indicators (Text & Numeric)
# Matches: "nil", "0", "$0", "0 EUR", "0 million", "$0 million"
ZERO_PATTERN = re.compile(
    r"\b(?:nil|none|zero)(?!\s+(?:cost|coupon|premium))\b|"  # Text: "nil"
    rf"(?:(?:{CURRENCY_SYMBOL_PATTERN})\s*)?0(?:\.0+)?\s*(?:million|billion|trillion|thousand)?\b|"  # Prefix: $0, USD 0
    rf"\b0(?:\.0+)?\s*(?:{CURRENCY_SYMBOL_PATTERN})\b|"  # Suffix: 0 USD
    rf"\b(?:{IMMATERIAL_PATTERN})\b",  # Immaterial
    re.IGNORECASE,
)

# 3. Positive Numbers (Strict)
# Matches: "$100", "100 EUR", "100 million", "5.5"
POSITIVE_PATTERN = re.compile(
    r"(?:"
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*[1-9]\d*(?:,\d{3})*(?:\.\d+)?|"  # Prefix: $100
    r"[1-9]\d*(?:,\d{3})*(?:\.\d+)?\s+(?:million|billion|trillion|thousand)|"  # Text Suffix: 100 million
    rf"[1-9]\d*(?:,\d{3})*(?:\.\d+)?\s*(?:{CURRENCY_SYMBOL_PATTERN})|"  # Code Suffix: 100 USD
    r"[1-9]\d*(?:,\d{3})*+\.\d+"  # Decimal forced: 5.5 (years aren't decimals)
    r")",
    re.IGNORECASE,
)

# 4. Any Number (Loose) - Used as a fallback to catch raw integers like "100"
# We filter these against years later.
ANY_NUMBER_LOOSE = re.compile(r"\b[1-9]\d*(?:,\d{3})*(?:\.\d+)?\b")

# =============================================================================
# LOGIC
# =============================================================================


def extract_values_and_years(sentence: str) -> Tuple[List[int], List[Dict]]:
    """
    Parses sentence to find years and 'Value Tokens' (ordered list of amounts).
    Returns:
        years: List[int] e.g. [2023, 2022] (Ordered by appearance)
        values: List[Dict] e.g. [{'is_zero': True}, {'is_zero': False}] (Ordered by appearance)
    """
    # 1. Extract Years (findall returns in order)
    years = [int(y) for y in YEAR_REGEX.findall(sentence)]

    # 2. Extract All Potential Values (Zero + Positive)
    value_tokens = []

    # Find Zeros
    for m in ZERO_PATTERN.finditer(sentence):
        value_tokens.append({"start": m.start(), "is_zero": True, "text": m.group()})

    # Find Positives (Strict)
    for m in POSITIVE_PATTERN.finditer(sentence):
        value_tokens.append({"start": m.start(), "is_zero": False, "text": m.group()})

    # Find Positives (Loose - e.g. "100")
    # Only add if it doesn't overlap with existing strict value or a Year
    existing_ranges = set()
    for v in value_tokens:
        for i in range(v["start"], v["start"] + len(v["text"])):
            existing_ranges.add(i)

    year_ranges = set()
    for m in YEAR_REGEX.finditer(sentence):
        for i in range(m.start(), m.end()):
            year_ranges.add(i)

    for m in ANY_NUMBER_LOOSE.finditer(sentence):
        # Skip if overlaps with strict value
        if m.start() in existing_ranges:
            continue
        # Skip if it looks like a year (e.g. raw "2023")
        if m.start() in year_ranges:
            continue
        # Skip if it looks like a year logic (4 digits, 19xx or 20xx)
        if re.match(r"^(19|20)\d{2}$", m.group()):
            continue

        value_tokens.append(
            {
                "start": m.start(),
                "is_zero": False,  # It's a non-zero number
                "text": m.group(),
            }
        )

    # Sort by position in sentence to preserve order for mapping
    value_tokens.sort(key=lambda x: x["start"])

    return years, value_tokens


def check_is_quantitative_zero(sentence: str, reporting_year: int) -> bool:
    """
    Determines if the sentence indicates Zero exposure for the Reporting Year.
    """
    years, values = extract_values_and_years(sentence)

    # --- STRATEGY 1: Implicit Parallel Mapping ---
    # If we have equal numbers of years and values, we assume they map 1-to-1 in order.
    if len(years) > 0 and len(years) == len(values):
        year_value_map = dict(zip(years, values))

        if reporting_year in year_value_map:
            val = year_value_map[reporting_year]
            if val["is_zero"]:
                return True
            else:
                return False

    # --- STRATEGY 2: Fallback (All Zero) ---
    # If NO values found, assume qualitative active -> Keep
    if not values:
        # NEW: Safeguard against Notional Definitions / Boilerplate
        # If the sentence mentions "notional" but has NO numbers (values or years),
        # it is likely a definition (e.g., "Notional amounts represent...").
        # DISCARD it.
        if "notional" in sentence.lower() and not years:
            return True  # True = Is Zero/Discard

        # Otherwise, assume it's a qualitative active statement (e.g., "We hold swaps.")
        return False

    # If ANY value is positive -> Keep
    has_positive = any(not v["is_zero"] for v in values)
    if has_positive:
        return False

    # If ALL values are zero -> Discard
    return True


def process_company(item):
    url, matches_json, cats_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
        categories = json.loads(cats_json)
    except:
        return None

    final_paragraphs = []
    final_categories = []
    discards = []

    for paragraph, category in zip(paragraphs, categories):
        if "<TABLE>" in paragraph: # pass the table
            final_paragraphs.append(paragraph)
            final_categories.append(category)
        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]
        kept_atomic = []

        for sent in atomic_sentences:
            # Check if sentence indicates quantitative zero for current year
            if check_is_quantitative_zero(sent, year):
                discards.append((url, sent, "quantitative_zero"))
                continue

            kept_atomic.append(sent)

        if kept_atomic:
            final_paragraphs.append(" ".join(kept_atomic))
            final_categories.append(category)
    # 4. Final Validation Helper
    final_paragraphs, final_categories, validation_discards = (
        validate_instrument_retention(
            final_paragraphs, final_categories, url, strict=False
        )
    )

    # Add validation discards to your main discard pile
    discards.extend(validation_discards)

    if final_paragraphs:
        return (
            url,
            json.dumps(final_paragraphs),
            json.dumps(final_categories),
            cik,
            year,
            discards,
        )

    return (url, "[]", "[]", cik, year, discards) if discards else None


# =============================================================================
# DB HELPERS
# =============================================================================


def setup_db():
    if Path(FINAL_DB_PATH).exists():
        Path(FINAL_DB_PATH).unlink()
    conn = sqlite3.connect(FINAL_DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE webpage_result (url TEXT PRIMARY KEY, matches TEXT)")
    c.execute(
        "CREATE TABLE category (url TEXT PRIMARY KEY, categories TEXT, FOREIGN KEY(url) REFERENCES webpage_result(url))"
    )
    c.execute(
        "CREATE TABLE report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
    )
    c.execute(
        "CREATE TABLE discarded_sentences (id INTEGER PRIMARY KEY, url TEXT, sentence TEXT, discard_reason TEXT)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_url ON webpage_result (url)")
    c.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()


def get_source_data():
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT wr.url, wr.matches, c.categories, rd.cik, rd.year
        FROM webpage_result wr
        JOIN category c ON wr.url = c.url
        JOIN report_data rd ON wr.url = rd.url
    """
    )
    data = c.fetchall()
    conn.close()
    return data


def write_batch(batch):
    if not batch:
        return
    conn = sqlite3.connect(FINAL_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        webpage_rows = [(b[0], b[1]) for b in batch]
        cat_rows = [(b[0], b[2]) for b in batch]
        meta_rows = [(b[0], b[3], b[4]) for b in batch]
        c.executemany("INSERT INTO webpage_result VALUES (?, ?)", webpage_rows)
        c.executemany("INSERT INTO category VALUES (?, ?)", cat_rows)
        c.executemany("INSERT INTO report_data VALUES (?, ?, ?)", meta_rows)

        all_discards = []
        for b in batch:
            if b[5]:
                all_discards.extend(b[5])
        if all_discards:
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                all_discards,
            )
        conn.commit()
    except Exception as e:
        print(f"Write error: {e}")
        conn.rollback()
    finally:
        conn.close()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 90)
    print("PHASE 6: QUANTITATIVE ZERO FILTERING (Implicit Mapping)")
    print("=" * 90)

    setup_db()
    data = get_source_data()

    if not data:
        print("❌ No data found in source database.")
    else:
        print(f"Processing {len(data):,} records...")
        batch = []
        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            results = executor.map(process_company, data)
            for result in tqdm(results, total=len(data)):
                if not result:
                    continue
                batch.append(result)
                if len(batch) >= BATCH_SIZE:
                    write_batch(batch)
                    batch = []
        if batch:
            write_batch(batch)

    print("\n✅ Done.")
    print(f"Final Clean Data: {FINAL_DB_PATH}")
