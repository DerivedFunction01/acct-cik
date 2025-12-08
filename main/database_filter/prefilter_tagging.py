import sqlite3
import json
import re
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm

from derivative_regex import (
    # Structural
    ABSENCE_REGEX,
    CR_SOFT_REGEX,
    EMBEDDED_CAP_FLOOR_REGEX,
    HEDGING_CONTEXT_REGEX,
    IS_REFERENCE_REGEX,
    LOOSE_GEN_REGEX,
    MORE_INFO_REGEX,
    SENTENCE_SPLIT_PATTERN,
    DEFINITION_INDICATORS,
    ENTITY_EXCLUSION_REGEX,
    ENTITY_TOKEN,
    SOFT_REGEX,
    # Business Logic
    TRADING_STATEMENTS_REGEX,
    NON_POSITION_INDICATORS,
    EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX,
    # Classification Killers
    POTENTIAL_REGEX,
    NEGATIVE_INTENT_REGEX,
    TERMINATION_REGEX,
    VAGUE_TIMING_REGEX,
    YEAR_REGEX,
    PRIOR_PATTERN,
    ACTIVE_STATE_REGEX,
    is_contractual_noise,
    is_hypothetical_noise,
    is_regulatory_noise,
)

# Import Phase 6 Logic
from final_verification import COUNTERPARTY_REGEX, POLICY_REGEX
from notional_filter import check_is_quantitative_zero

from prefilter_simple_nonuse import DEADWEIGHT_TOKEN, MinimalTextCleaner

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "refined_data.db"
TARGET_DB_PATH = "tagged_data.db"

# Token for sentence-level skips
SKIP_TOKEN = " _S "
_cleaner = MinimalTextCleaner()

# =============================================================================
# STAGE-SPECIFIC CHECKS
# =============================================================================


def is_temporal_noise(text: str, reporting_year: int) -> bool:
    """[Phase 3] Returns True if sentence is purely historical."""
    if not reporting_year:
        return False

    years = [int(y) for y in YEAR_REGEX.findall(text)]
    if years:
        # If ALL years are in the past, it's noise.
        # (e.g. "In 2021 and 2022 we held..." vs Report 2024)
        return all(y < reporting_year for y in years)

    # Fallback: "In prior years", "During the previous period"
    if PRIOR_PATTERN.search(text):
        return True
    return False


def is_intent_noise(text: str) -> bool:
    """[Phase 4] Returns True if sentence is hypothetical or negative."""
    # "We may enter", "We expect to use" (Hypothetical)
    if POTENTIAL_REGEX.search(text) or VAGUE_TIMING_REGEX.search(text):
        return True
    # "We do not intend to use", "We have no plans" (Negative)
    if NEGATIVE_INTENT_REGEX.search(text) or ABSENCE_REGEX.search(text):
        return True
    return False


def is_termination_noise(text: str) -> bool:
    """[Phase 5] Returns True if sentence describes dead positions."""
    # "The swaps expired", "Positions were terminated"
    # Note: If you want to salvage "Expired... but replaced", add logic here.
    if TERMINATION_REGEX.search(text):
        return True
    return False


def is_quantitative_noise(text: str, reporting_year: int) -> bool:
    """[Phase 6] Returns True if values for the reporting year are zero."""
    if not reporting_year:
        return False
    # Uses your existing notional_filter logic to map Year -> Value
    # Returns True if the mapping shows $0 for the current year.
    return check_is_quantitative_zero(text, reporting_year)


def check_paragraph_level_noise(text: str, reporting_year: int) -> bool:
    """[Phase 1 & 3 Block Level] Checks if the entire paragraph is deadweight."""

    # 1. Historical Narrative Block (Phase 3)
    # If paragraph has years, and ALL are past, and no "Active" keywords
    if reporting_year:
        years = [int(y) for y in YEAR_REGEX.findall(text)]
        if years and all(y < reporting_year for y in years):
            if not ACTIVE_STATE_REGEX.search(text):
                return True

    # 2. Boilerplate / Trading Denial Block (Phase 1/4)
    # If it's just "We do not trade derivatives" repeated
    if TRADING_STATEMENTS_REGEX.search(text) and len(text) < 150:
        return True

    return False


# =============================================================================
# CORE TAGGING LOGIC
# =============================================================================


def tag_paragraph(text: str, reporting_year: int) -> str:
    masked_text = mask_text(text)

    if check_paragraph_level_noise(masked_text, reporting_year):
        return f"{DEADWEIGHT_TOKEN}{text}"

    original_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
    ]
    masked_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(masked_text) if s.strip()
    ]

    if len(original_sentences) != len(masked_sentences):
        return text

    tagged_output = []
    surviving_text_parts = []

    for orig, masked in zip(original_sentences, masked_sentences):
        is_noise = False

        # --- A. Structural Noise ---
        if IS_REFERENCE_REGEX.search(masked) or MORE_INFO_REGEX.search(masked):
            is_noise = True
        elif DEFINITION_INDICATORS.search(masked):
            is_noise = True
        elif NON_POSITION_INDICATORS.search(masked):
            is_noise = True
        elif EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX.search(masked):
            is_noise = True
        elif TRADING_STATEMENTS_REGEX.search(masked):
            is_noise = True
        elif EMBEDDED_CAP_FLOOR_REGEX.search(masked):
            is_noise = True

        # --- B. Soft Kills (Policy / Credit) ---
        # No safeguard needed! If this sentence is Policy, tag it.
        # If the NEXT sentence is Usage, it survives.
        elif POLICY_REGEX.search(masked):
            is_noise = True
        elif COUNTERPARTY_REGEX.search(masked) and not CR_SOFT_REGEX.search(masked):
            is_noise = True

        # --- C. Bag-of-Words Scoring ---
        elif is_contractual_noise(masked, threshold=2):
            is_noise = True
        elif is_regulatory_noise(masked, threshold=2):
            is_noise = True
        elif is_hypothetical_noise(masked, threshold=2):
            is_noise = True

        # --- D. Classification Killers ---
        elif is_temporal_noise(masked, reporting_year):
            is_noise = True
        elif is_intent_noise(masked):
            is_noise = True
        elif is_termination_noise(masked):
            is_noise = True
        elif is_quantitative_noise(masked, reporting_year):
            is_noise = True

        # --- TAGGING ---
        if is_noise:
            tagged_output.append(f"{SKIP_TOKEN}{orig}")
        else:
            tagged_output.append(orig)
            surviving_text_parts.append(masked)

    # --- E. Final Signal Check ---
    if not surviving_text_parts:
        final_text = " ".join(tagged_output)
        return f"{DEADWEIGHT_TOKEN}{final_text}"

    combined_survivors = " ".join(surviving_text_parts)
    has_signal = False

    if SOFT_REGEX.search(combined_survivors):
        has_signal = True
    elif LOOSE_GEN_REGEX.search(combined_survivors) and HEDGING_CONTEXT_REGEX.search(
        combined_survivors
    ):
        has_signal = True

    final_text = " ".join(tagged_output)


    if has_signal:
        return final_text
    else:
        return f"{DEADWEIGHT_TOKEN}{final_text}"

# Should be:
def mask_text(text, remove_years=False):
    return _cleaner.clean_for_quant_analysis(text, remove_years=remove_years)


def process_row(row):
    url, matches_json, cik, year = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    new_paragraphs = []
    for p in paragraphs:
        if p.startswith(DEADWEIGHT_TOKEN):
            new_paragraphs.append(p)
            continue

        tagged_p = tag_paragraph(p, year)
        new_paragraphs.append(tagged_p)

    return (url, json.dumps(new_paragraphs), cik, year)


# =============================================================================
# INFRASTRUCTURE
# =============================================================================


def setup_target_db(path):
    if Path(path).exists():
        pass
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, matches TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES webpage_result(url))"
    )
    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
    conn.commit()
    conn.close()


def get_processed_urls(path):
    if not Path(path).exists():
        return set()
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT url FROM webpage_result")}
    except:
        return set()
    finally:
        conn.close()


def data_generator(source_db, processed_urls, batch_size=BATCH_SIZE):
    conn = sqlite3.connect(source_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT w.url, w.matches, r.cik, r.year FROM webpage_result w LEFT JOIN report_data r ON w.url = r.url WHERE w.matches IS NOT NULL"
    )
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            if row[0] not in processed_urls:
                yield row
    conn.close()


def write_batch(conn, buffer):
    if not buffer:
        return
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        c.executemany(
            "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
            [(r[0], r[1]) for r in buffer],
        )
        c.executemany(
            "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(r[0], r[2], r[3]) for r in buffer],
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Write Error: {e}")
        conn.rollback()


if __name__ == "__main__":
    print(f"🚀 Starting 7-Stage Tagger ({NUM_WORKERS} workers)")
    setup_target_db(TARGET_DB_PATH)
    processed = get_processed_urls(TARGET_DB_PATH)

    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")

    buffer = []
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        source = list(data_generator(SOURCE_DB_PATH, processed))
        for result in tqdm(
            executor.map(process_row, source, chunksize=CHUNK_SIZE), total=len(source)
        ):
            if result:
                buffer.append(result)
                if len(buffer) >= BATCH_SIZE:
                    write_batch(conn, buffer)
                    buffer = []

    if buffer:
        write_batch(conn, buffer)
    conn.close()
    print("✅ Complete.")
