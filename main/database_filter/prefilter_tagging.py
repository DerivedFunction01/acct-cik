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
    DID_NOT_HOLD_REGEX,
    NON_DER_CAP_FLOOR_REGEX,
    HEDGING_CONTEXT_REGEX,
    IS_REFERENCE_REGEX,
    LOOSE_GEN_REGEX,
    MORE_INFO_REGEX,
    SENTENCE_SPLIT_PATTERN,
    DEFINITION_INDICATORS,
    SOFT_REGEX,
    # Business Logic
    TRADING_STATEMENTS_REGEX,
    AOCI_NOISE_REGEX,
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
)

# Import Phase 6 Logic
from final_verification import COUNTERPARTY_REGEX, HEDGE_DOC_REGEX
from prefilter_evidence import PNL_CONTEXT_REGEX
from prefilter_database import is_sophisticated_content, is_sophisticated_target
from prefiltered_lib import (
    SKIP_TOKEN,
    DEADWEIGHT_TOKEN,
    MinimalTextCleaner,
    NoiseReason,
    get_tag,
    mark_as_deadweight,
    parse_noise_tags,
)
from notional_filter import check_is_quantitative_zero

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "prefiltered_data.db"
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
    return _cleaner.clean(text)


# --- REASON-BASED CHECKS ---


def get_temporal_noise_reason(text: str, reporting_year: int) -> Optional[NoiseReason]:
    """Returns NoiseReason.TIME if sentence is purely historical."""
    if not reporting_year:
        return None
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
        return NoiseReason.POT

    if (
        NEGATIVE_INTENT_REGEX.search(text)
        or ABSENCE_REGEX.search(text)
        or DID_NOT_HOLD_REGEX.search(text)
    ):
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
    
    if check_is_quantitative_zero(text, reporting_year):
        return NoiseReason.ZERO

    return None


# =============================================================================
# CORE TAGGING LOGIC
# =============================================================================


def tag_paragraph(text: str, reporting_year: int) -> str:
    # 1. Masking for Logic Checks
    masked_text = mask_text(text)

    # 3. Dual Split (Original vs Masked)
    original_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
    ]
    masked_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(masked_text) if s.strip()
    ]

    if len(original_sentences) != len(masked_sentences):
        masked_sentences = original_sentences

    tagged_output = []
    surviving_text_parts = []

    for orig, masked in zip(original_sentences, masked_sentences):
        reason: Optional[NoiseReason] = None

        # --- TIER 1: CONTEXT & TIME (The "Gatekeepers") ---
        # If it's not about derivatives or it's ancient history, nothing else matters.
        if not LOOSE_GEN_REGEX.search(masked) or is_sophisticated_target(text):
            reason = NoiseReason.CTX

        if not reason:
            reason = get_temporal_noise_reason(masked, reporting_year)

        # --- TIER 2: EVIDENCE / SIGNAL (The "High Value" Tags) ---
        # We check these BEFORE Structural Noise (REF).
        # "See note 5 re: termination" -> TERM (Signal), not REF (Noise).

        if not reason:
            if TRADING_STATEMENTS_REGEX.search(masked):
                # "We do not trade..." -> Critical End User Signal
                reason = NoiseReason.TRADING

            elif not reason:
                # Check Termination (e.g., "Terminated in [Current Year]")
                # Note: Temporal check above already killed "Terminated in [Past Year]"
                reason = get_termination_noise_reason(masked)
            # Prevents no hedge ineffectiveness from being negated
            elif PNL_CONTEXT_REGEX.search(masked):
                reason = NoiseReason.PNL
            if not reason:
                # Check Absence (e.g., "We do not hold...")
                reason = get_intent_noise_reason(masked)

        # --- TIER 3: STRUCTURAL NOISE (The "Format" Tags) ---
        # Only check these if we didn't find a strong Evidence signal above.
        if not reason:
            if IS_REFERENCE_REGEX.search(masked) or MORE_INFO_REGEX.search(masked):
                reason = NoiseReason.REF
            elif DEFINITION_INDICATORS.search(masked):
                reason = NoiseReason.DEF
            elif AOCI_NOISE_REGEX.search(masked):
                reason = NoiseReason.AOCI
            elif EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX.search(masked):
                reason = NoiseReason.NPNS
            elif NON_DER_CAP_FLOOR_REGEX.search(masked):
                reason = NoiseReason.LOAN

        # --- TIER 4: SOFT KILLS (The "Generic" Tags) ---
        if not reason:
            if HEDGE_DOC_REGEX.search(masked):
                reason = NoiseReason.DOC
            elif COUNTERPARTY_REGEX.search(masked) and not CR_SOFT_REGEX.search(masked):
                reason = NoiseReason.CREDIT

        # --- TIER 5: FALLBACK SCORING ---
        if not reason:
            if is_contractual_noise(masked, threshold=2):
                reason = NoiseReason.CONTRACT
            elif is_regulatory_noise(masked, threshold=2):
                reason = NoiseReason.REG
            elif not is_sophisticated_content(masked) and is_hypothetical_noise(
                masked, threshold=2
            ):
                reason = NoiseReason.HYP_SCORE
        if not reason:
            # Check 0/nil
            reason = get_quantitative_noise_reason(masked, reporting_year)
        # --- CONSTRUCTION ---
        if reason:
            tagged_output.append(f"{get_tag(SKIP_TOKEN, reason)} {orig}")
        else:
            tagged_output.append(orig)
            surviving_text_parts.append(masked)

    # --- E. Final Signal Check ---
    if not surviving_text_parts:
        final_text = " ".join(tagged_output)
        return f"{get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ)} {final_text}"

    # Perform some paragraph-level check here
    combined_survivors = " ".join(surviving_text_parts)
    final_text = " ".join(tagged_output)

    has_signal = False

    if SOFT_REGEX.search(combined_survivors):
        has_signal = True
    else:
        for s in surviving_text_parts:
            if HEDGING_CONTEXT_REGEX.search(s) or DER_STD_REGEX.search(s):
                has_signal = True
                break

    if has_signal:
        return final_text
    else:
        return mark_as_deadweight(final_text, NoiseReason.ANLZ)


# =============================================================================
# PROCESS ROW
# =============================================================================


def process_row(row):
    url, matches_json, cik, year = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    new_paragraphs = []
    for p in paragraphs:
        # Respect existing tags from previous steps (Prefilter Simple Nonuse)
        if DEADWEIGHT_TOKEN in p:
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
        """
        SELECT w.url, w.matches, r.cik, r.year
        FROM webpage_result w 
        LEFT JOIN report_data r ON w.url = r.url
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
        c.execute("BEGIN TRANSACTION")
        # Buffer is list of (url, matches, categories, cik, year)
        # url = 0, matches = 1,  cik = 2, year = 3
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
    conn.execute("PRAGMA synchronous=NORMAL")

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
