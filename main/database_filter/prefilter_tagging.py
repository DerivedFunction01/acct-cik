import re
import sqlite3
import json
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from typing import Dict, List, Optional, Set, Tuple

# --- REGEX IMPORTS ---f
from derivative_regex import (
    # Structural
    ABSENCE_REGEX,
    COMPARISON_PHRASES,
    DID_NOT_HOLD_REGEX,
    NON_DER_CAP_FLOOR_REGEX,
    IS_REFERENCE_REGEX,
    PRECISE_LOOSE_GEN_REGEX,
    MORE_INFO_REGEX,
    RISK_MANAGEMENT_REGEX,
    SENTENCE_SPLIT_PATTERN,
    DEFINITION_INDICATORS,
    AOCI_NOISE_REGEX,
    EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX,
    # Classification Killers
    POTENTIAL_REGEX,
    TERMINATION_REGEX,
    VAGUE_TIMING_REGEX,
    YEAR_REGEX,
    PRIOR_INDICATOR,
    build_alternation,
    build_negation_prefix_pattern,
    build_regex,
    # Scoring
    is_contractual_noise,
    is_hypothetical_noise,
    is_regulatory_noise,
)

from prefiltered_lib import (
    HEDGE_DOC_REGEX,
    SKIP_TOKEN,
    DEADWEIGHT_TOKEN,
    ZERO_QUANT_REGEX,
    MinimalTextCleaner,
    NoiseReason,
    convertible_ir,
    get_tag,
    is_pnl,
    is_sophisticated_content,
    is_sophisticated_target,
    mark_as_deadweight,
    QUANT_REGEX,
)
from prefilter_evidence import FAIR_VALUE_CONTEXT_REGEX, NOTIONAL_CONTEXT_REGEX, POSS_VERB_REGEX, TRANS_VERB_REGEX, USAGE_VERB_REGEX


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


def mask_text(text: str, is_nst: bool = True) -> str:
    """
    Prepares text for logic checks.
    1. Normalizes whitespace.
    2. Masks entities (JPM -> _E) to prevent overfitting on names.
    3. DOES NOT remove years (critical for temporal checks).
    """
    return _cleaner.clean(text, is_nst=is_nst)

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
        ABSENCE_REGEX.search(text) # No such oustanding
        or DID_NOT_HOLD_REGEX.search(text) # We did not plan to use
    ):
        if HEDGE_DOC_REGEX.search(text):
            return NoiseReason.DOC
        return NoiseReason.NEG

    return None


def get_termination_noise_reason(
    text: str, reporting_year: int
) -> Optional[NoiseReason]:
    """
    Returns TERM if sentence describes SPECIFIC dead positions (anchored by time).
    """
    if TERMINATION_REGEX.search(text):
        years = [int(y) for y in YEAR_REGEX.findall(text)]

        # CASE 1: No Date -> Likely Policy/Hypothetical ("We terminate if...")
        if not years:
            # OPTIONAL: You could return NoiseReason.POLICY here if you want to be specific,
            # or keep OTHER/None to let it flow to other filters.
            # Returning None lets the sentence survive to be checked for other signals (like Risk Mgmt).
            return None

        # CASE 2: Has Date -> Check if it's in the past
        # If any year is in the future (e.g. "Terminates in 2026"), it's NOT dead (Active).
        # We only tag as TERM if ALL dates are <= reporting year.
        if not any(y > reporting_year for y in years):
            return NoiseReason.TERM

    return None


COMPARISON_REGEX = build_regex(COMPARISON_PHRASES)

COUNTERPARTY_POLICY_TERMS = [
    r"credit\s+risk",
    r"counterpart(?:y|ies)",
    r"credit\s+quality",
    r"credit\s+worthiness",
    r"highly[- ]rated",
    r"investment[- ]grade",
    r"financial\s+institutions",
    r"master\s+netting",
    r"collateral\s+requirements",
    r"concentration\s+of\s+credit",
    r"non[- ]performance",
    r"nonperformance",
]
COUNTERPARTY_REGEX = build_regex(COUNTERPARTY_POLICY_TERMS)


def extract_values_and_years(sentence: str) -> Tuple[List[int], List[Dict]]:
    """
    Parses sentence to find years and 'Value Tokens'.
    Uses a 'clean_sentence' to mask out dates so days (e.g. 31) aren't counted as values.
    """

    # 2. Extract Years (from cleaned string, though years usually aren't inside the date patterns above)
    years = [int(y) for y in YEAR_REGEX.findall(sentence)]
    sentence = YEAR_REGEX.sub("YEAR", sentence)

    value_tokens = []

    def mask_span(text, start, end):
        return text[:start] + ("_" * (end - start)) + text[end:]

    # 1. Masked working copy
    masked = sentence

    # 2. Strict numerics first
    for m in QUANT_REGEX.finditer(sentence):
        value_tokens.append({"start": m.start(), "is_zero": False, "text": m.group()})
        masked = mask_span(masked, m.start(), m.end())

    # 3. Zeros second (on masked string)
    for m in ZERO_QUANT_REGEX.finditer(masked):
        value_tokens.append(
            {
                "start": m.start(),
                "is_zero": True,
                "text": sentence[m.start() : m.end()],  # original text
            }
        )

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
        return False

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


def get_quantitative_noise_reason(
    text: str, reporting_year: int
) -> Optional[NoiseReason]:
    """Returns ZERO if values are present but all zero."""
    if not reporting_year:
        return None
    is_notional = bool(NOTIONAL_CONTEXT_REGEX.search(text))
    is_fair_value = bool(FAIR_VALUE_CONTEXT_REGEX.search(text))
    has_active_verb = (
        POSS_VERB_REGEX.search(text)
        or USAGE_VERB_REGEX.search(text)
        or TRANS_VERB_REGEX.search(text)
    )
    if not (is_notional or is_fair_value or has_active_verb): # Not related
        return None
    if check_is_quantitative_zero(text, reporting_year):
        return NoiseReason.ZERO
    return None
# In prefilter_tagging.py

# Core concept: What are they denying?
_TRADING_CORE = [
    r"trad(?:ing|es?|ed)",
    r"speculat(?:ive|es?|ion)",
    r"proprietary",
    r"arbitrage",
]
_TRADING_CORE_ALT = build_alternation(_TRADING_CORE)
TRADING_CORE_REGEX = build_regex(_TRADING_CORE)

# Veto/Authorization: For "not permitted/authorized" logic
_AUTH = [r"authorize(?:d|s)?", r"permit(?:s|ted)?", r"allow(?:s|ed)?"]
_NOT_AUTH = [r"prohibit(?:s|ed)?", r"forbid(?:s)?", r"forbade", r"prevent(?:s|ed)?"]

TRADING_NOT_AUTH_REGEX = build_regex(_NOT_AUTH)
TRADING_NOT_AUTH_REGEX2 = re.compile(rf"\bnot\s+{build_alternation(_AUTH)}\b")

# Direct Denial without needing an instrument (e.g. "We do not speculate")
_NEG = build_negation_prefix_pattern()
TRADING_DENIAL_SIMPLE = re.compile(
    rf"\b(?:{_NEG}|no)\s+(?:\w+\s+){{0,3}}(?:for\s+)?(?:{_TRADING_CORE_ALT})\b", re.IGNORECASE
)


def is_trading_statement(text: str) -> bool:
    """
    Simplified Multi-Gate Trading Denial Check.
    Logic: (Quant Veto) -> (Keyword Gate) -> (Path Checks)
    """
    # GATE 0: Quantitative Veto (Actual trades have numbers/currencies)
    if QUANT_REGEX.search(text):
        return False

    # GATE 1: Core Keyword Check
    if not TRADING_CORE_REGEX.search(text):
        return False

    # GATE 2: Path-Based Logical Matching
    # Path A: Policy-based (Not permitted / Prohibited)
    if TRADING_NOT_AUTH_REGEX.search(text) or TRADING_NOT_AUTH_REGEX2.search(text):
        return True

    # Path B: Direct Denial (e.g., "We do not speculate")
    if TRADING_DENIAL_SIMPLE.search(text):
        return True

    # Path C: Structural Denial (Instrument required, e.g. "No trading swaps")
    # Note: Ensure build_absence_regex includes "trading" in its modifiers
    if DID_NOT_HOLD_REGEX.search(text) or ABSENCE_REGEX.search(text):
        return True

    return False


# =============================================================================
# CORE TAGGING LOGIC
# =============================================================================


def tag_paragraph(text: str, reporting_year: int, is_nst: bool = False) -> str:
    # 1. Masking for Logic Checks
    masked_text = mask_text(text, is_nst=is_nst)

    # 3. Dual Split (Original vs Masked)
    original_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
    ]
    masked_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(masked_text) if s.strip()
    ]
    reasons: Set[NoiseReason] = set()
    if len(original_sentences) != len(masked_sentences):
        masked_sentences = original_sentences

    tagged_output = []
    surviving_text_parts = []

    for orig, masked in zip(original_sentences, masked_sentences):
        reason: Optional[NoiseReason] = None

        # --- TIER 1: CONTEXT & TIME (The "Gatekeepers") ---
        # If it's not about derivatives or it's ancient history, nothing else matters.
        temp_sent = RISK_MANAGEMENT_REGEX.sub("", masked)
        if not PRECISE_LOOSE_GEN_REGEX.search(temp_sent) and not is_sophisticated_target(
            temp_sent
        ):
            if RISK_MANAGEMENT_REGEX.search(masked):
                reason = NoiseReason.RISK
            elif is_pnl(masked, context_only=True): # PNL is tricky
                reason = NoiseReason.PNL

        if not reason:
            reason = get_temporal_noise_reason(masked, reporting_year)

        # --- TIER 2: EVIDENCE / SIGNAL (The "High Value" Tags) ---
        # We check these BEFORE Structural Noise (REF).
        # "See note 5 re: termination" -> TERM (Signal), not REF (Noise).

        if not reason:
            if is_trading_statement(masked):
                # "We do not trade..." -> Critical End User Signal
                reason = NoiseReason.TRADING
            elif is_pnl(masked):
                reason = NoiseReason.PNL
            elif not reason:
                # Check Termination (e.g., "Terminated in [Current Year]")
                # Note: Temporal check above already killed "Terminated in [Past Year]"
                reason = get_termination_noise_reason(masked, reporting_year=reporting_year)
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
            if COUNTERPARTY_REGEX.search(masked):
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
            reasons.add(reason)
            tagged_output.append(f"{get_tag(SKIP_TOKEN, reason)} {orig}")
        else:
            tagged_output.append(orig)
            surviving_text_parts.append(masked)

    final_text = " ".join(tagged_output)
    # --- E. Final Signal Check ---
    if not surviving_text_parts:
        return mark_as_deadweight(final_text, noise=reasons)
    return final_text


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
    is_nst = False  # Default to False unless metadata says otherwise

    # 1. Extract and Handle Metadata
    if paragraphs and paragraphs[0].startswith('{"type": "metadata"'):
        try:
            metadata_str = paragraphs.pop(0)  # Remove it so it isn't tagged as text
            metadata = json.loads(metadata_str)
            is_nst = metadata.get(
                "NST", False
            )  # Use the key "NST" from your earlier plan

            # Re-add the metadata to the top of the NEW list
            # so it persists for the next stage (Phase 2/3)
            new_paragraphs.append(metadata_str)
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. Process remaining actual text paragraphs
    for p in paragraphs:
        # Respect existing tags (e.g., DEADWEIGHT from Phase 0)
        if DEADWEIGHT_TOKEN in p:
            new_paragraphs.append(p)
            continue
        # Pass the is_nst flag to the tagger to inform its logic
        local_is_nst = convertible_ir(p)
        tagged_p = tag_paragraph(p, year, is_nst=is_nst or local_is_nst)
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
