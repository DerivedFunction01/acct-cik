# notional_filter.py
# =============================================================================
# PHASE 6: QUANTITATIVE ZERO FILTERING (Strict Mapping)
# =============================================================================
# Removes sentences where the quantitative amounts indicate no exposure
# specifically for the reporting year.
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

from derivative_regex import (
    IMMATERIAL_PATTERN,
    SENTENCE_SPLIT_PATTERN,
    CURRENCY_SYMBOL_PATTERN,
    YEAR_REGEX,
    check_for_instrument,
    validate_instrument_retention,
)

# =============================================================================
# REGEX PATTERNS
# =============================================================================

# 2. Zero Indicators (Text & Numeric)
ZERO_PATTERN = re.compile(
    r"\b(?:nil|none|zero)(?!\s+(?:cost|coupon|premium))\b|"  # Text: "nil"
    rf"(?:(?:{CURRENCY_SYMBOL_PATTERN})\s*)?0(?:\.0+)?\s*(?:million|billion|trillion|thousand)?\b|"  # Prefix: $0
    rf"\b0(?:\.0+)?\s*(?:{CURRENCY_SYMBOL_PATTERN})\b|"  # Suffix: 0 USD
    rf"\b(?:{IMMATERIAL_PATTERN})\b",  # Immaterial
    re.IGNORECASE,
)

# 3. Positive Numbers (Strict)
POSITIVE_PATTERN = re.compile(
    r"(?:"
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*[1-9]\d*(?:,\d{3})*(?:\.\d+)?|"  # Prefix: $100
    r"[1-9]\d*(?:,\d{3})*(?:\.\d+)?\s+(?:million|billion|trillion|thousand)|"  # Text Suffix: 100 million
    rf"[1-9]\d*(?:,\d{3})*(?:\.\d+)?\s*(?:{CURRENCY_SYMBOL_PATTERN})|"  # Code Suffix: 100 USD
    r"[1-9]\d*(?:,\d{3})*+\.\d+(?!\s*\%)"  # Decimal forced: 5.5 (but not percentages)
    r")",
    re.IGNORECASE,
)

# 4. Any Number (Loose)
ANY_NUMBER_LOOSE = re.compile(r"\b[1-9]\d*(?:,\d{3})*(?:\.\d+)?\b")

# 5. Date Exclusion Patterns
MONTHS_PATTERN = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"

# Matches: "December 31", "Dec 31st"
DATE_MD_REGEX = re.compile(
    rf"\b(?:{MONTHS_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,)?\b", re.IGNORECASE
)

# Matches: "31 December", "1st of Jan"
DATE_DM_REGEX = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{MONTHS_PATTERN})\b", re.IGNORECASE
)


# =============================================================================
# LOGIC
# =============================================================================


def extract_values_and_years(sentence: str) -> Tuple[List[int], List[Dict]]:
    """
    Parses sentence to find years and 'Value Tokens'.
    Uses a 'clean_sentence' to mask out dates so days (e.g. 31) aren't counted as values.
    """

    # 1. Create a Masked Copy
    # We replace date matches with SPACES.
    # Important: We keep the length identical so indices (start/end) remain valid
    # for the original sentence if needed, and for correct relative ordering.
    clean_sentence = sentence
    for pat in [DATE_MD_REGEX, DATE_DM_REGEX]:
        clean_sentence = pat.sub(lambda m: " " * len(m.group(0)), clean_sentence)

    # 2. Extract Years (from cleaned string, though years usually aren't inside the date patterns above)
    years = [int(y) for y in YEAR_REGEX.findall(clean_sentence)]

    # 3. Extract Values from CLEANED string
    value_tokens = []

    # Find Zeros
    for m in ZERO_PATTERN.finditer(clean_sentence):
        value_tokens.append({"start": m.start(), "is_zero": True, "text": m.group()})

    # Find Positives (Strict)
    for m in POSITIVE_PATTERN.finditer(clean_sentence):
        value_tokens.append({"start": m.start(), "is_zero": False, "text": m.group()})

    # Track ranges occupied by Strict/Zero matches to prevent double counting with Loose
    existing_ranges = set()
    for v in value_tokens:
        for i in range(v["start"], v["start"] + len(v["text"])):
            existing_ranges.add(i)

    # Track ranges occupied by Years (to prevent 2023 from being a value)
    year_ranges = set()
    for m in YEAR_REGEX.finditer(clean_sentence):
        for i in range(m.start(), m.end()):
            year_ranges.add(i)

    # Find Positives (Loose) - Safely runs on clean_sentence (No Dates)
    for m in ANY_NUMBER_LOOSE.finditer(clean_sentence):
        # Skip if overlaps with strict value
        if m.start() in existing_ranges:
            continue
        # Skip if overlaps with a year
        if m.start() in year_ranges:
            continue
        # Skip if looks like a year (e.g. raw "2023" not caught by YEAR_REGEX context)
        if re.match(r"^(19|20)\d{2}$", m.group()):
            continue

        value_tokens.append({"start": m.start(), "is_zero": False, "text": m.group()})

    # Sort by position
    value_tokens.sort(key=lambda x: x["start"])

    return years, value_tokens


def check_is_quantitative_zero(sentence: str, reporting_year: int) -> bool:
    years, values = extract_values_and_years(sentence)

    # --- STRATEGY 1: Implicit Parallel Mapping ---
    if len(years) > 0 and len(years) == len(values):
        year_value_map = dict(zip(years, values))
        if reporting_year in year_value_map:
            return year_value_map[reporting_year]["is_zero"]

    # --- STRATEGY 2: Fallback (All Zero) ---
    if not values:
        # Safeguard: If "notional" exists but NO numbers, it's likely a definition/boilerplate.
        if "notional" in sentence.lower() and not years:
            return True  # Discard
        return False  # Keep (Qualitative active statement)

    # If ANY value is positive -> Keep
    if any(not v["is_zero"] for v in values):
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
        if "<TABLE>" in paragraph:
            final_paragraphs.append(paragraph)
            final_categories.append(category)
            continue

        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]
        kept_atomic = []

        for sent in atomic_sentences:
            if check_is_quantitative_zero(sent, year):
                discards.append((url, sent, "quantitative_zero"))
                continue
            kept_atomic.append(sent)

        if kept_atomic:
            final_paragraphs.append(" ".join(kept_atomic))
            final_categories.append(category)

    # Final Validation
    final_paragraphs, final_categories, validation_discards = (
        validate_instrument_retention(
            final_paragraphs, final_categories, url, strict=False
        )
    )
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
