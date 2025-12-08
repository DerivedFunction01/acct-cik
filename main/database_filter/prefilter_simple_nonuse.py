from concurrent.futures import ProcessPoolExecutor
import sqlite3
import json
import re
import multiprocessing as mp
import time
from pathlib import Path
from typing import List, Tuple, Optional, Set, Dict
from tqdm import tqdm

# --- CONFIGURATION ---
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "prefiltered_data.db"  # Output from Step 1
TARGET_DB_PATH = "refined_data.db"  # Input for Step 3

# The token to append to deadweight paragraphs.
DEADWEIGHT_TOKEN = "_D"

# --- MODULE IMPORTS ---
from final_verification import COUNTERPARTY_REGEX, POLICY_REGEX, QUANT_REGEX
from year_deletion import extract_years

from derivative_regex import (
    ACTIVE_STATE_REGEX,
    CR_REGEX,
    ENTITY_EXCLUSION_REGEX,
    ENTITY_TOKEN,
    EXHIBIT_FRAGMENT,
    LOOSE_GEN_REGEX,
    NON_POSITION_INDICATORS,
    POTENTIAL_REGEX,
    NEGATIVE_INTENT_REGEX,
    ABSENCE_REGEX,
    DID_NOT_HOLD_REGEX,
    SENTENCE_SPLIT_PATTERN,
    SOFT_CATEGORY_REGEX,
    SOFT_REGEX,
    STRONG_POSSESSION_REGEX,
    TRADING_STATEMENTS_REGEX,
    TERMINATION_REGEX,
    VAGUE_TIMING_REGEX,
    STANDARD_ID_REGEX,
    VERB_REGEX,
    YEAR_REGEX,
    NoiseReason,
    get_tag
)

from notional_filter import (
    extract_values_and_years,
    check_is_quantitative_zero,
    DATE_DM_REGEX,
    DATE_MD_REGEX,
)

class MinimalTextCleaner:
    """
    Lightweight cleaner that prepares text for quantitative analysis.
    Removes numeric noise that would confuse extract_values_and_years().
    """

    # Bullet/footnote pattern: matches (1), 1), 1., (i), (ii), etc at line/sentence start
    # Simplified since QUANT_REGEX will protect actual monetary values first
    bullet_pattern = re.compile(
        r"(?:(?<=^)|(?<=\s))"  # Start of line OR whitespace
        r"(?:"
        r"\(?\d+\)|\d+\.|"  # (1), 1), 1.
        r"\([ivxlcdm]+\)|[ivxlcdm]+\.|"  # (i), (ii), i., ii. (roman numerals)
        r"\([a-z]\)|[a-z]\.|"  # (a), (b), a., b. (letters)
        r"\([A-Z]\)|[A-Z]\."  # (A), (B), A., B. (capitals)
        r")"
        r"(?=\s)",  # Followed by whitespace
        re.IGNORECASE,
    )

    # Dashed patterns: 1-2, 3-4 (range references)
    dashed_pattern = re.compile(r"\b\d+[-]\d+\b")

    exhibit_pattern = re.compile(
        rf"\b{EXHIBIT_FRAGMENT}\b" r"(?:\s*No\.?)?" r"\s*\d{1,3}\b",
        re.IGNORECASE,
    )

    # Standard IDs: ASC 815-20, IFRS 9, etc.
    standard_id_pattern = STANDARD_ID_REGEX

    def __init__(self):
        pass

    def clean_numerics(self, text: str, remove_years: bool = False) -> str:
        """
        Remove numeric noise that confuses quantitative parsing:
        - Bullet points (1), 1), 1.
        - Dashed ranges (1-2)
        - Dates (Dec 31, 31 December)
        - Exhibit/reference markers (Note 5, Table A)
        - Standard IDs (ASC 815, IFRS 9)

        Safety: QUANT_REGEX is applied FIRST to protect actual monetary values
        like "$ (100)" from being destroyed by the bullet pattern.
        """
        # Step 1: Identify and protect quantitative values
        quant_matches = list(QUANT_REGEX.finditer(text))
        protected_ranges = set()
        for match in quant_matches:
            for i in range(match.start(), match.end()):
                protected_ranges.add(i)

        # Step 2: Apply bullet pattern, but skip protected ranges
        def safe_bullet_sub(match):
            if any(i in protected_ranges for i in range(match.start(), match.end())):
                return match.group(0)  # Keep if protected
            return " "

        text = text.strip()
        text = self.bullet_pattern.sub(safe_bullet_sub, text)

        # Step 3: Apply other cleanups (no quant conflict)
        text = self.dashed_pattern.sub(" ", text)
        text = DATE_MD_REGEX.sub(" ", text)
        text = DATE_DM_REGEX.sub(" ", text)
        text = self.exhibit_pattern.sub(" ", text)
        text = self.standard_id_pattern.sub(" ", text)
        if remove_years:
            text = YEAR_REGEX.sub(" ", text)
        return text

    def normalize_whitespace(self, text: str) -> str:
        """Collapse multiple spaces and newlines."""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def clean_for_quant_analysis(self, text: str, remove_years: bool = False) -> str:
        """
        Prepare text for quantitative zero checking.
        Removes noise that would interfere with extract_values_and_years().

        Pipeline:
        1. Clean numeric noise (bullets, dates, IDs, years if remove_years is true)
        2. Normalize whitespace
        3. Return cleaned text ready for QUANT_REGEX/value extraction
        """
        text = self.clean_numerics(text, remove_years)
        text = self.normalize_whitespace(text)
        return text
    
    def clean(self, text: str, remove_years: bool = False) -> str:
        text = self.clean_for_quant_analysis(text, remove_years)
        text = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, text)
        return text.strip()


# Initialize cleaner (shared instance)
_cleaner = MinimalTextCleaner()


def is_meaningful_quant(sentence: str, reporting_year: Optional[int]) -> bool:
    """
    Returns True if the sentence contains POSITIVE quantitative data.
    Returns False if it contains NO numbers OR only Zeros/Nil/Immaterial.

    Cleans the sentence first to remove numeric noise (bullets, dates, IDs)
    that would confuse the quantitative parser.

    Distinguishes between:
    - No numbers at all -> False
    - Only zeros/nil/immaterial -> False
    - At least one positive number -> True
    """
    # Clean numeric noise first so extract_values_and_years() works correctly
    cleaned_sent = _cleaner.clean_for_quant_analysis(sentence)

    years, values = extract_values_and_years(cleaned_sent)

    # No numbers at all
    if not values:
        return False

    # Has numbers, but are they all zero?
    is_zero_garbage = check_is_quantitative_zero(
        cleaned_sent, reporting_year if reporting_year else 0
    )
    if is_zero_garbage:
        return False

    # Has numbers, and at least one is positive
    return True


def check_refinement_exclusions(text: str, year: Optional[int] = None) -> Optional[str]:
    """
    Checks for 'Deadweight' paragraphs that passed the hard pre-filter
    but are semantically useless for derivative classification.

    Returns the specific DEADWEIGHT tag (e.g. " _D<HYPO>") if excluded, else None.
    """
    if DEADWEIGHT_TOKEN in text:
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.BOILER_BLOCK)

    def has_instrument(text: str) -> bool:
        return bool(SOFT_REGEX.search(text))

    def is_current_or_no_year(sentence: str, reporting_year: Optional[int]) -> bool:
        """
        Returns True if sentence mentions current/reporting year OR no year at all.
        Returns False if sentence mentions only past years.
        """
        if not reporting_year:
            return True
        sent_years = extract_years(sentence)
        if not sent_years:
            return True
        if any(y >= reporting_year for y in sent_years):
            return True
        return False

    def has_only_past_years(text: str, reporting_year: Optional[int]) -> bool:
        """
        Returns True if text mentions ONLY past years (no current/future).
        Returns False if no years mentioned or any year >= reporting_year.
        """
        if not reporting_year:
            return False
        all_years = extract_years(text)
        if not all_years:
            return False
        return all(y < reporting_year for y in all_years)

    has_potential = False
    has_absence = False
    has_trading_denial = False
    has_termination = False
    has_aoci = False
    has_meaningful_quant = False
    is_strictly_generic = True
    has_current_year_activity = False
    hedging_sentence_count = 0
    hedging_sentences_with_indicators = 0

    if SOFT_CATEGORY_REGEX.search(text):
        is_strictly_generic = False

    sentences = SENTENCE_SPLIT_PATTERN.split(text)
    for sent in sentences:
        if has_instrument(sent):
            hedging_sentence_count += 1
            sent_has_indicator = False

            if POTENTIAL_REGEX.search(sent) or VAGUE_TIMING_REGEX.search(sent):
                has_potential = True
                sent_has_indicator = True
            if ABSENCE_REGEX.search(sent) or DID_NOT_HOLD_REGEX.search(sent):
                has_absence = True
                sent_has_indicator = True
            if TRADING_STATEMENTS_REGEX.search(sent):
                has_trading_denial = True
                sent_has_indicator = True
            if NEGATIVE_INTENT_REGEX.search(
                sent
            ) and not TRADING_STATEMENTS_REGEX.search(sent):
                has_absence = True
                sent_has_indicator = True

            if sent_has_indicator:
                hedging_sentences_with_indicators += 1

        # Check for current year
        if is_current_or_no_year(sent, year):
            # Exclude termination-only sentences from counting as "current activity"
            if not (TERMINATION_REGEX.search(sent) and LOOSE_GEN_REGEX.search(sent)):
                has_current_year_activity = True

        # Check for meaningful quantities
        if is_meaningful_quant(sent, year):
            has_meaningful_quant = True

        if TERMINATION_REGEX.search(sent) and LOOSE_GEN_REGEX.search(sent):
            has_termination = True

        if NON_POSITION_INDICATORS.search(sent):
            has_aoci = True

    # === DECISION LOGIC ===

    # 1. AOCI + Termination = Historical Cleanup
    if has_aoci and has_termination:
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.TERM)

    # 2. Quantitative Safety
    if has_meaningful_quant:
        return None

    # 3. Full Non-Use (All signal sentences have negative indicators)
    if (
        hedging_sentence_count == hedging_sentences_with_indicators
        and hedging_sentence_count > 0
    ):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.BOILER_BLOCK)

    # 4. Potential / Hypothetical
    if has_potential:
        if is_strictly_generic and has_trading_denial:
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.HYPO)
        if has_absence:
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.HYPO)
        if has_termination:
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.HYPO)
        if has_trading_denial:
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.HYPO)

    # 5. Historical / Policy / Absence
    else:
        # Historic activity filters
        if not has_current_year_activity and has_only_past_years(text, year):
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.HIST_BLOCK)

        # Generic policy with no trade
        if has_trading_denial and is_strictly_generic:
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.BOILER_BLOCK)

        # Terminated + no outstanding
        if has_termination and has_absence:
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.TERM)

        # Stated absence
        if has_absence:
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.NEG)

        # Policy no use no trade
        if has_trading_denial and has_absence:
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.BOILER_BLOCK)

    return None


def check_deadweight_exclusions(text: str, year: Optional[int] = None) -> Optional[str]:
    """
    Checks for general deadweight categories (Policy, History, etc.).
    Returns the specific tag string if excluded, else None.
    """

    # --- 1. HARD KILLS (Run BEFORE Verbs) ---
    if DEADWEIGHT_TOKEN in text:
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.BOILER_BLOCK)

    # B. Historical Check
    if year:
        all_years = [int(y) for y in YEAR_REGEX.findall(text)]
        if all_years and all(y < year for y in all_years):
            if not ACTIVE_STATE_REGEX.search(text):
                return get_tag(DEADWEIGHT_TOKEN, NoiseReason.HIST_BLOCK)

    # --- 2. SAFEGUARDS (The "Active User" Signals) ---

    # A. Quantitative Check
    if is_meaningful_quant(text, year):
        return None

    # B. Active Action Check
    if STRONG_POSSESSION_REGEX.search(text):
        return None

    # --- 3. SOFT KILLS (Run AFTER Verbs) ---

    # A. Policy & Methodology
    if POLICY_REGEX.search(text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.POLICY)

    # B. AOCI / PnL Lists (Moved here to allow safeguards to protect active positions)
    if NON_POSITION_INDICATORS.search(text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.PNL)

    # C. Counterparty / Credit Risk (With exemption for explicit credit derivatives)
    if COUNTERPARTY_REGEX.search(text) and not CR_REGEX.search(text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.CREDIT)

    return None
# =============================================================================
# WORKER LOGIC
# =============================================================================


def process_item(item: Tuple) -> Optional[Tuple]:
    """
    Firm-Level Filter with Token Injection & Entity Masking.
    Drops firms that have 0 valid paragraphs.
    """
    url, matches_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    modified_paragraphs = []
    has_valid_signal = False
    all_discards_log = []

    for p in paragraphs:
        # --- 0. PRE-CHECK: Existing Deadweight ---
        # If Step 1 already tagged this (e.g. Contractual/Regulatory "Salvage"),
        # we treat it as deadweight (Context only, no Signal).
        if DEADWEIGHT_TOKEN in p:
            modified_paragraphs.append(p)
            # Do NOT set has_valid_signal = True
            continue

        # --- 1. Masking ---
        p_masked = _cleaner.clean(p)

        # --- 2. Level 2 Filter (Refinement) ---
        tag = check_refinement_exclusions(p_masked, year)

        # --- 3. Level 3 Filter (Deadweight) ---
        if tag is None:
            tag = check_deadweight_exclusions(p_masked, year)

        # --- 4. Decision ---
        if tag is None:
            # It survived! It's a valid signal.
            has_valid_signal = True
            modified_paragraphs.append(p)
        else:
            # It failed. Tag it and log it.
            # tag is "_D<REASON>"
            modified_paragraphs.append(f"{tag} {p}")
            all_discards_log.append((url, p, tag))

    # Firm-Level Decision
    if has_valid_signal:
        return (url, json.dumps(modified_paragraphs), cik, year, [])
    else:
        # Drop firm: No valid signals found (all paragraphs are Deadweight or Boilerplate)
        return (url, json.dumps([]), cik, year, all_discards_log)


def setup_target_db(path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, matches TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS discarded_sentences (id INTEGER PRIMARY KEY, url TEXT, sentence TEXT, discard_reason TEXT)"
    )
    conn.commit()
    conn.close()


def get_processed_urls(path: str) -> Set[str]:
    if not Path(path).exists():
        return set()
    try:
        conn = sqlite3.connect(path)
        c = conn.cursor()
        c.execute("SELECT url FROM webpage_result")
        urls = {row[0] for row in c.fetchall()}
        conn.close()
        return urls
    except Exception:
        return set()


def get_source_data(source_path: str, processed_urls: Set[str]) -> List[Tuple]:
    conn = sqlite3.connect(source_path)
    c = conn.cursor()
    c.execute(
        """
        SELECT w.url, w.matches, r.cik, r.year 
        FROM webpage_result w 
        LEFT JOIN report_data r ON w.url = r.url
        WHERE w.matches IS NOT NULL
        """
    )
    data = c.fetchall()
    conn.close()
    return [row for row in data if row[0] not in processed_urls]


# --- NEW: Buffer flush helper ---
def flush_buffers(conn, buffer_res, buffer_disc):
    """Write buffered results and discards to DB, then clear buffers."""
    c = conn.cursor()
    if buffer_res:
        c.executemany(
            "INSERT OR REPLACE INTO webpage_result (url, matches) VALUES (?, ?)",
            [(x[0], x[1]) for x in buffer_res],
        )
        c.executemany(
            "INSERT OR REPLACE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(x[0], x[2], x[3]) for x in buffer_res],
        )
        buffer_res.clear()

    if buffer_disc:
        c.executemany(
            "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
            buffer_disc,
        )
        buffer_disc.clear()

    conn.commit()


# --- MAIN ---
if __name__ == "__main__":
    print(f"🚀 Starting Refinement Script ({NUM_WORKERS} workers)...")
    setup_target_db(TARGET_DB_PATH)

    processed_urls = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed_urls)} already processed URLs")

    data = get_source_data(SOURCE_DB_PATH, processed_urls)
    print(f"📦 Loaded {len(data)} unprocessed documents from {SOURCE_DB_PATH}")

    if not data:
        print("✅ All documents already processed!")
        exit(0)

    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    buffer_res, buffer_disc = [], []
    count = 0

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        results_iter = executor.map(process_item, data, chunksize=CHUNK_SIZE)

        for result in tqdm(
            results_iter, total=len(data), unit="docs", desc="Processing"
        ):
            if not result:
                continue

            url, matches, cik, year, discards = result
            buffer_res.append((url, matches, cik, year))
            if discards:
                buffer_disc.extend(discards)

            if len(buffer_res) >= BATCH_SIZE or len(buffer_disc) >= BATCH_SIZE:
                flush_buffers(conn, buffer_res, buffer_disc)

            count += 1

    # Final flush
    flush_buffers(conn, buffer_res, buffer_disc)

    conn.close()
    print(f"✅ Complete. Processed {count} documents.")
