import re
import sqlite3
import json
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from typing import Dict, List, Optional, Tuple

# --- REGEX IMPORTS ---
from derivative_regex import (
    # Structural
    ABSENCE_REGEX,
    COMPARISON_PHRASES,
    CR_SOFT_REGEX,
    CURRENCY_SYMBOL_PATTERN,
    DER_STD_REGEX,
    DID_NOT_HOLD_REGEX,
    IMMATERIAL_PATTERN,
    NON_DER_CAP_FLOOR_REGEX,
    HEDGING_CONTEXT_REGEX,
    IS_REFERENCE_REGEX,
    LOOSE_GEN_REGEX,
    MORE_INFO_REGEX,
    RISK_MANAGEMENT_REGEX,
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
    build_regex,
    # Scoring
    is_contractual_noise,
    is_hypothetical_noise,
    is_regulatory_noise,
)


from prefilter_database import is_sophisticated_content, is_sophisticated_target
from prefiltered_lib import (
    SKIP_TOKEN,
    DEADWEIGHT_TOKEN,
    MinimalTextCleaner,
    NoiseReason,
    get_tag,
    mark_as_deadweight,
    QUANT_REGEX,
)
from prefilter_evidence import HAD_CHANGE_REGEX


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
        if PNL_CONTEXT_REGEX.search(text):
            return NoiseReason.PNL
        if HEDGE_DOC_REGEX.search(text):
            return NoiseReason.DOC
        return NoiseReason.NEG

    return None


def get_termination_noise_reason(text: str, reporting_year: int) -> Optional[NoiseReason]:
    """Returns TERM if sentence describes dead positions."""
    if TERMINATION_REGEX.search(text):
        years = [int(y) for y in YEAR_REGEX.findall(text)]
        if not any(y > reporting_year for y in years):
            return NoiseReason.TERM
    return None


# 2. Zero Indicators (Text & Numeric)
ZERO_PATTERN = re.compile(
    r"\b(?:nil|zero)(?!\s+(?:cost|coupon|premium))\b|"  # Text: "nil"
    rf"(?:(?:{CURRENCY_SYMBOL_PATTERN})\s*)?0(?:\.0+)?\s*(?:million|billion|trillion|thousand)?\b|"  # Prefix: $0
    rf"\b0(?:\.0+)?\s*(?:{CURRENCY_SYMBOL_PATTERN})\b",  # Suffix: 0 USD
    re.IGNORECASE,
)

# 4. Any Number (Loose)
ANY_NUMBER_LOOSE = re.compile(r"\b[1-9]\d*(?:,\d{3})*(?:\.\d+)?\b")
COMPARISON_REGEX = build_regex(COMPARISON_PHRASES)


G = r"(?:\W+\w+){0,3}"  # up to 3 intermediate words

HEDGE_DOC_TERMS = [
    rf"formally{G}document",
    rf"hedge{G}documentation",
    r"documentation",
    rf"at{G}inception",
    rf"effectiveness{G}(?:is|was){G}assessed",
    rf"highly{G}effective",
    rf"qualif(?:y|ies|ied){G}(?:for|as){G}hedg(?:ing|e?){G}(?:accounting|relationship|documentation)?",
    rf"(?:not)?{G}designated",
    rf"(?:dis)?continu(?:es?|ed|ing){G}hedge{G}(?:accounting|relationship|documentation)?",
    rf"economic{G}relationship",
    rf"nature{G}of",
]

HEDGE_DOC_REGEX = build_regex(HEDGE_DOC_TERMS)

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
PNL_TERMS = [
    # 1. Explicit Gains/Losses (Anchored to avoid "Total Gains")
    r"(?:realized|unrealized)\s+(?:net\s+)?(?:gains?|loss(?:es)?)",
    # 2. "On" Construction (e.g., "Gain on derivatives")
    r"(?:net\s+)?(?:gains?|loss(?:es)?)",
    # 3. Fair Value CHANGES (Strictly Flow)
    # 4. Ineffectiveness (Strictly PnL context)
    r"ineffective\s+portion",
    r"hedge\s+ineffectiveness",
    # 6. Mark-to-Market (Action/Result, usually implies flow)
    # Distinguishes from "Fair Value" measurement policy
    r"mark(?:ed)?[- ]to[- ]market",
    # 7. Impact statements
    r"impact\s+(?:on|to)\s+(?:earnings|income|revenue)",
]
PNL_CONTEXT_REGEX = build_regex(PNL_TERMS)
def extract_values_and_years(sentence: str) -> Tuple[List[int], List[Dict]]:
    """
    Parses sentence to find years and 'Value Tokens'.
    Uses a 'clean_sentence' to mask out dates so days (e.g. 31) aren't counted as values.
    """

    # 2. Extract Years (from cleaned string, though years usually aren't inside the date patterns above)
    years = [int(y) for y in YEAR_REGEX.findall(sentence)]

    # 3. Extract Values from CLEANED string
    value_tokens = []

    # Find Zeros
    for m in ZERO_PATTERN.finditer(sentence):
        value_tokens.append({"start": m.start(), "is_zero": True, "text": m.group()})

    # Find Numerics (Strict)
    for m in QUANT_REGEX.finditer(sentence):
        value_tokens.append({"start": m.start(), "is_zero": False, "text": m.group()})

    # # Track ranges occupied by Strict/Zero matches to prevent double counting with Loose
    # existing_ranges = set()
    # for v in value_tokens:
    #     for i in range(v["start"], v["start"] + len(v["text"])):
    #         existing_ranges.add(i)

    # # Track ranges occupied by Years (to prevent 2023 from being a value)
    # year_ranges = set()
    # for m in YEAR_REGEX.finditer(sentence):
    #     for i in range(m.start(), m.end()):
    #         year_ranges.add(i)

    # # Find Positives (Loose) - Safely runs on clean_sentence (No Dates)
    # for m in ANY_NUMBER_LOOSE.finditer(sentence):
    #     # Skip if overlaps with strict value
    #     if m.start() in existing_ranges:
    #         continue
    #     # Skip if overlaps with a year
    #     if m.start() in year_ranges:
    #         continue

    #     value_tokens.append({"start": m.start(), "is_zero": False, "text": m.group()})

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
        temp_sent = RISK_MANAGEMENT_REGEX.sub("", masked)
        if not LOOSE_GEN_REGEX.search(temp_sent) or not is_sophisticated_target(
            temp_sent
        ):
            if RISK_MANAGEMENT_REGEX.search(masked):
                reason = NoiseReason.RISK
            else:
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
                reason = get_termination_noise_reason(masked, reporting_year=reporting_year)
            # Prevents no hedge ineffectiveness from being negated
            elif PNL_CONTEXT_REGEX.search(masked) or HAD_CHANGE_REGEX.search(masked):
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
            elif COUNTERPARTY_REGEX.search(masked):
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
