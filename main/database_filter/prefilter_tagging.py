import sqlite3
import json
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from typing import Optional

# --- REGEX IMPORTS ---
from derivative_regex import (
    # Structural
    ABSENCE_REGEX,
    CR_SOFT_REGEX,
    DER_STD_REGEX,
    EMBEDDED_CAP_FLOOR_REGEX,
    HEDGING_CONTEXT_REGEX,
    IS_REFERENCE_REGEX,
    LOOSE_GEN_REGEX,
    MORE_INFO_REGEX,
    SENTENCE_SPLIT_PATTERN,
    DEFINITION_INDICATORS,
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
    PRIOR_INDICATOR,
    ACTIVE_STATE_REGEX,
    # Scoring
    is_contractual_noise,
    is_hypothetical_noise,
    is_regulatory_noise,
    # Enums & Helpers
    NoiseReason,
    get_tag,
)

# Import Phase 6 Logic
from final_verification import COUNTERPARTY_REGEX, POLICY_REGEX
from prefiltered_lib import SKIP_TOKEN, DEADWEIGHT_TOKEN, MinimalTextCleaner
from notional_filter import check_is_quantitative_zero

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "refined_data.db"
TARGET_DB_PATH = "tagged_data.db"


# Initialize shared cleaner
_cleaner = MinimalTextCleaner()

# =============================================================================
# HELPERS: MASKING & LOGIC
# =============================================================================


def mask_text(text: str) -> str:
    """
    Prepares text for logic checks.
    1. Normalizes whitespace.
    2. Masks entities (JPM -> _E) to prevent overfitting on names.
    3. DOES NOT remove years (critical for temporal checks).
    """
    return _cleaner.clean_entities(text)


# --- REASON-BASED CHECKS ---


def get_temporal_noise_reason(text: str, reporting_year: int) -> Optional[NoiseReason]:
    """Returns NoiseReason.TIME if sentence is purely historical."""
    if not reporting_year:
        return None
    text = _cleaner.clean_numerics(text, remove_years=False)
    years = [int(y) for y in YEAR_REGEX.findall(text)]
    if years:
        # If ALL years are in the past, it's noise.
        if all(y < reporting_year for y in years):
            return NoiseReason.TIME

    # Fallback: "In prior years", "During the previous period"
    if PRIOR_INDICATOR.search(text):
        return NoiseReason.TIME

    return None


def get_intent_noise_reason(text: str) -> Optional[NoiseReason]:
    """Returns HYPO or NEG based on intent."""
    if POTENTIAL_REGEX.search(text) or VAGUE_TIMING_REGEX.search(text):
        return NoiseReason.HYPO

    if NEGATIVE_INTENT_REGEX.search(text) or ABSENCE_REGEX.search(text):
        return NoiseReason.NEG

    return None


def get_termination_noise_reason(text: str) -> Optional[NoiseReason]:
    """Returns TERM if sentence describes dead positions."""
    if TERMINATION_REGEX.search(text):
        return NoiseReason.TERM
    return None


def get_quantitative_noise_reason(
    text: str, reporting_year: int
) -> Optional[NoiseReason]:
    """Returns ZERO if values are present but all zero."""
    if not reporting_year:
        return None

    # Use cleaner's specific method for quant parsing
    clean_for_quant = _cleaner.clean_for_quant_analysis(text)
    if check_is_quantitative_zero(clean_for_quant, reporting_year):
        return NoiseReason.ZERO

    return None


def get_paragraph_level_reason(text: str, reporting_year: int) -> Optional[NoiseReason]:
    """Checks if the entire paragraph block is deadweight."""

    # 1. Historical Narrative Block
    text = _cleaner.clean_numerics(text, remove_years=False)
    if reporting_year:
        years = [int(y) for y in YEAR_REGEX.findall(text)]
        if years and all(y < reporting_year for y in years):
            if not ACTIVE_STATE_REGEX.search(text):
                return NoiseReason.HIST_BLOCK

    # 2. Boilerplate / Trading Denial Block
    if TRADING_STATEMENTS_REGEX.search(text) and len(text) < 150:
        return NoiseReason.TRADING

    return None


# =============================================================================
# CORE TAGGING LOGIC
# =============================================================================


def tag_paragraph(text: str, reporting_year: int) -> str:
    # 1. Masking for Logic Checks
    masked_text = mask_text(text)

    # 2. Paragraph-Level Pre-Check
    para_reason = get_paragraph_level_reason(masked_text, reporting_year)
    if para_reason:
        # Return: "_D<HIST_BLOCK> Original text..."
        return f"{get_tag(DEADWEIGHT_TOKEN, para_reason)} {text}"

    # 3. Dual Split (Original vs Masked)
    original_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
    ]
    masked_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(masked_text) if s.strip()
    ]

    # Safety: Align lengths
    if len(original_sentences) != len(masked_sentences):
        # Fallback: Run logic on unmasked to ensure alignment if regex failed
        masked_sentences = original_sentences

    tagged_output = []
    surviving_text_parts = []

    for orig, masked in zip(original_sentences, masked_sentences):
        reason: Optional[NoiseReason] = None

        # --- A. Structural Noise ---
        if IS_REFERENCE_REGEX.search(masked) or MORE_INFO_REGEX.search(masked):
            reason = NoiseReason.REF
        elif DEFINITION_INDICATORS.search(masked):
            reason = NoiseReason.DEF
        elif NON_POSITION_INDICATORS.search(masked):
            reason = NoiseReason.PNL
        elif EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX.search(masked):
            reason = NoiseReason.NPNS  # or COMM_EXEMPT
        elif TRADING_STATEMENTS_REGEX.search(masked):
            reason = NoiseReason.TRADING
        elif EMBEDDED_CAP_FLOOR_REGEX.search(masked):
            reason = NoiseReason.LOAN

        # --- B. Soft Kills (Policy / Credit) ---
        elif POLICY_REGEX.search(masked):
            reason = NoiseReason.POLICY
        elif COUNTERPARTY_REGEX.search(masked) and not CR_SOFT_REGEX.search(masked):
            reason = NoiseReason.CREDIT

        # --- C. Bag-of-Words Scoring ---
        elif is_contractual_noise(masked, threshold=2):
            reason = NoiseReason.CONTRACT
        elif is_regulatory_noise(masked, threshold=2):
            reason = NoiseReason.REG
        elif is_hypothetical_noise(masked, threshold=2):
            reason = NoiseReason.HYP_SCORE

        # --- D. Classification Killers (Logic Helpers) ---
        if not reason:
            reason = get_temporal_noise_reason(masked, reporting_year)
        if not reason:
            reason = get_intent_noise_reason(masked)
        if not reason:
            reason = get_termination_noise_reason(masked)
        if not reason:
            reason = get_quantitative_noise_reason(masked, reporting_year)

        # --- TAGGING ---
        if reason:
            # Inject: "_S<TIME> In 2021..."
            tagged_output.append(f"{get_tag(SKIP_TOKEN, reason)} {orig}")
        else:
            # Keep clean
            tagged_output.append(orig)
            surviving_text_parts.append(masked)

    # --- E. Final Signal Check (Fluff Detector) ---
    # If valid sentences remain, do they actually mention a derivative?

    if not surviving_text_parts:
        # All sentences were tagged as noise
        final_text = " ".join(tagged_output)
        # Use ANLZ or a specific FLUFF reason
        return f"{get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ)} {final_text}"

    combined_survivors = " ".join(surviving_text_parts)
    has_signal = False

    if SOFT_REGEX.search(combined_survivors):
        has_signal = True
    else:
        for s in surviving_text_parts:
            if HEDGING_CONTEXT_REGEX.search(s) or DER_STD_REGEX.search(s):
                if LOOSE_GEN_REGEX.search(s):
                    has_signal = True
                    break

    final_text = " ".join(tagged_output)

    if has_signal:
        return final_text
    else:
        # It survived the filters but has no "Derivative" keywords (e.g. just "Risk Management")
        return f"{get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ)} {final_text}"


# =============================================================================
# PROCESS ROW
# =============================================================================


def process_row(row):
    url, matches_json, cik, year, categories = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    new_paragraphs = []
    for p in paragraphs:
        # Respect existing tags from previous steps (Prefilter Simple Nonuse)
        if p.startswith(DEADWEIGHT_TOKEN):
            new_paragraphs.append(p)
            continue

        tagged_p = tag_paragraph(p, year)
        new_paragraphs.append(tagged_p)

    return (url, json.dumps(new_paragraphs), json.dumps(categories), cik, year)


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
        """
        SELECT w.url, w.matches, r.cik, r.year, c.categories
        FROM webpage_result w 
        LEFT JOIN report_data r ON w.url = r.url
        LEFT JOIN category c ON w.url = c.url
        WHERE w.matches IS NOT NULL
        """
    )
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            if row[0] not in processed_urls:
                yield row
    conn.close()


def flush_buffers(conn, buffer):
    if not buffer:
        return
    c = conn.cursor()
    try:
        # Buffer is list of (url, matches, categories, cik, year)
        # url = 0, matches = 1, categories = 2, cik = 3, year = 4
        c.executemany(
            "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
            [(r[0], r[1]) for r in buffer],
        )
        c.executemany(
            "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(r[0], r[3], r[4]) for r in buffer],
        )
        c.executemany(
            "INSERT OR IGNORE INTO category (url, categories) VALUES (?, ?)",
            [(r[0], r[2]) for r in buffer],
        )
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
                    flush_buffers(conn, buffer)
                    buffer = []

    if buffer:
        flush_buffers(conn, buffer)
    conn.close()
    print("✅ Complete.")
