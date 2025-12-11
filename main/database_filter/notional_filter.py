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
    COMPARISON_PATTERN,
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
COMPARISON_REGEX = re.compile(rf"\b{COMPARISON_PATTERN}\b")

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
    """
    Determines if a sentence indicates ZERO exposure for the reporting year.
    Returns True if Discard (Zero/Nil).
    Returns False if Keep (Positive/Ambiguous).
    """

    # --- STEP 1: Extract Data ---
    # We use the cleaner inside extract_values_and_years
    years, values = extract_values_and_years(sentence)

    # If no values at all, skip
    if not values:
        return False

    # --- STEP 2: Tier 1 - Strict Mapping (The Happy Path) ---
    # If we have a perfect 1-to-1 match, we trust the order.
    # We also trust it if Years > Values (e.g. "2022 and 2023: $50m"),
    # provided we can map the reporting year strictly.

    has_mismatch = False

    # Check for mismatch conditions
    if len(years) != len(values):
        has_mismatch = True

    # Special Case: If Years > Values, it implies one value covers multiple years
    # (e.g. "In 2022 and 2023, value was $50m").
    # Strict mapping fails here because we run out of values.
    # However, if Values > Years, it's definitely a mismatch (dangling numbers).
    if len(values) > len(years):
        has_mismatch = True

    if not has_mismatch:
        # PERFECT ALIGNMENT: Map 1-to-1
        year_value_map = dict(zip(years, values))

        if reporting_year in year_value_map:
            # We found our specific year! Return its status.
            return year_value_map[reporting_year]["is_zero"]

        # If reporting year is NOT in the map, but the map was perfect,
        # it means this sentence is about other years. Safe to Keep (or Discard?).
        # Usually, if a sentence is purely about 2022, we might want to discard it
        # if we are strictly looking for 2024 data.
        return True

    # --- STEP 3: Tier 2 - The Splitter (Conditional Fallback) ---
    # We only reach here if there was a mismatch.
    # Try to resolve the mismatch by breaking the sentence on "versus"/"compared to".

    if COMPARISON_REGEX.search(sentence):
        # Split into sub-segments
        segments = [s for s in COMPARISON_REGEX.split(sentence) if s.strip()]

        # Analyze each segment independently
        for seg in segments:
            # Recurse!
            # We check if THIS segment is a "clean match" for our reporting year.
            # Note: We can't just call check_is_quantitative_zero recursively blindly,
            # because we need to know if *any* segment validates the year.

            s_years, s_values = extract_values_and_years(seg)

            # If this segment mentions our year AND has a value...
            if reporting_year in s_years and s_values:
                # ...and it's a Clean Match within this segment...
                if len(s_years) == len(s_values):
                    s_map = dict(zip(s_years, s_values))
                    # We trust this specific segment!
                    if not s_map[reporting_year]["is_zero"]:
                        return (
                            False  # Found a POSITIVE for 2024. Keep the whole sentence.
                        )
                    else:
                        # Found a ZERO for 2024.
                        # We continue checking other segments?
                        # Unlikely a sentence says "2024 was 0 vs 2024 was 100".
                        # But to be safe, we can flag it.
                        return True

    # --- STEP 4: Tier 3 - "Bag of Numbers" (Ultimate Safety Net) ---
    # If we are here, Strict Mapping failed AND Splitting didn't give a definitive answer.
    # We fall back to: "Is there ANY positive number in this mess?"

    if any(not v["is_zero"] for v in values):
        return False  # Found a positive number somewhere. Keep it.

    return True  # All numbers are zero. Discard.


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
