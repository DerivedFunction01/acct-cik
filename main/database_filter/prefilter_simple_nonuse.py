from concurrent.futures import ProcessPoolExecutor
import sqlite3
import json
import multiprocessing as mp
from pathlib import Path
from typing import List, Tuple, Optional, Set
from tqdm import tqdm

from prefiltered_lib import DEADWEIGHT_TOKEN, SKIP_TOKEN, MinimalTextCleaner, NoiseReason, get_tag

# --- CONFIGURATION ---
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "prefiltered_data.db"  # Output from Step 1
TARGET_DB_PATH = "refined_data.db"  # Input for Step 3


# --- MODULE IMPORTS ---
from final_verification import COUNTERPARTY_REGEX, POLICY_REGEX
from year_deletion import extract_years

from derivative_regex import (
    ACTIVE_STATE_REGEX,
    CR_REGEX,
    LOOSE_GEN_REGEX,
    AOCI_NOISE_REGEX,
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
    YEAR_REGEX,
)

from notional_filter import (
    extract_values_and_years,
    check_is_quantitative_zero,
)


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


def check_refinement_exclusions(
    text_orig: str, text_masked: str, year: Optional[int] = None
) -> Tuple[Optional[str], str]:
    """
    Checks for 'Deadweight' paragraphs.

    UPDATED: Now returns a Tuple (Tag, Modified_Text).
    - Tag: The paragraph-level decision (e.g. "_D<ANLZ>" or None).
    - Modified_Text: The text with internal sentence tags applied (e.g., _S<TRADING>).
    """
    def has_instrument(text: str) -> bool:
        return bool(SOFT_REGEX.search(text))

    def is_current_or_no_year(sentence: str, reporting_year: Optional[int]) -> bool:
        """
        Returns True if sentence mentions current/reporting year OR no year at all.
        Returns False if sentence mentions only past years.
        """
        if not reporting_year:
            return True
        text = _cleaner.clean_numerics(sentence, remove_years=False)
        sent_years = extract_years(text)
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
        text = _cleaner.clean_numerics(text, remove_years=False)
        all_years = extract_years(text)
        if not all_years:
            return False
        return all(y < reporting_year for y in all_years)

    # 1. DUAL SPLIT STRATEGY
    sentences_orig = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text_orig) if s.strip()
    ]
    sentences_masked = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text_masked) if s.strip()
    ]

    # Safety: If regex masking changed sentence boundaries (rare but possible),
    # fallback to processing the original text to avoid index mismatch.
    if len(sentences_orig) != len(sentences_masked):
        # Fallback: We process the original text for tagging logic.
        # Ideally, we would process masked, but alignment is critical for data integrity.
        sentences_orig = SENTENCE_SPLIT_PATTERN.split(text_orig)
        sentences_masked = sentences_orig  # Logic runs on unmasked as fallback

    processed_sentences = []

    # Logic Variables
    hedging_sentence_count = 0
    hedging_sentences_with_indicators = 0
    # Initialize counters instead of booleans
    potential_count = 0
    absence_count = 0
    trading_denial_count = 0
    termination_count = 0
    aoci_count = 0
    meaningful_quant_count = 0
    current_year_activity_count = 0

    # Check Soft Category on MASKED version (safer)
    is_strictly_generic = not bool(SOFT_CATEGORY_REGEX.search(text_masked))

    # 2. PARALLEL LOOP
    for sent_orig, sent_masked in zip(sentences_orig, sentences_masked):

        current_sent = sent_orig

        # --- A. Sentence-Level Tags ---
        if TRADING_STATEMENTS_REGEX.search(sent_masked):
            trading_denial_count += 1
            tag = get_tag(SKIP_TOKEN, NoiseReason.TRADING)
            if tag not in current_sent:
                current_sent = f"{tag} {current_sent}"

        if TERMINATION_REGEX.search(sent_masked) and LOOSE_GEN_REGEX.search(
            sent_masked
        ):
            termination_count += 1
            tag = get_tag(SKIP_TOKEN, NoiseReason.TERM)
            if tag not in current_sent:
                current_sent = f"{tag} {current_sent}"

        if NEGATIVE_INTENT_REGEX.search(
            sent_masked
        ) and not TRADING_STATEMENTS_REGEX.search(sent_masked):
            absence_count += 1
            tag = get_tag(SKIP_TOKEN, NoiseReason.NEG)
            if tag not in current_sent:
                current_sent = f"{tag} {current_sent}"

        # --- B. Update Logic Counters ---
        if has_instrument(sent_masked):
            hedging_sentence_count += 1
            sent_has_indicator = False

            if POTENTIAL_REGEX.search(sent_masked) or VAGUE_TIMING_REGEX.search(
                sent_masked
            ):
                potential_count += 1
                sent_has_indicator = True
            if ABSENCE_REGEX.search(sent_masked) or DID_NOT_HOLD_REGEX.search(
                sent_masked
            ):
                absence_count += 1
                sent_has_indicator = True
            if trading_denial_count > 0 or absence_count > 0:
                sent_has_indicator = True

            if sent_has_indicator:
                hedging_sentences_with_indicators += 1

        if is_current_or_no_year(sent_masked, year):
            if not (
                (
                    TERMINATION_REGEX.search(sent_masked)
                    and LOOSE_GEN_REGEX.search(sent_masked)
                )
                or (
                    ABSENCE_REGEX.search(sent_masked)
                    or DID_NOT_HOLD_REGEX.search(sent_masked)
                )
            ):
                current_year_activity_count += 1

        if is_meaningful_quant(sent_orig, year):
            meaningful_quant_count += 1

        if AOCI_NOISE_REGEX.search(sent_masked):
            tag = get_tag(SKIP_TOKEN, NoiseReason.AOCI)
            current_sent = f"{tag} {current_sent}"
            aoci_count += 1

        processed_sentences.append(current_sent)

    modified_text = " ".join(processed_sentences)

    # --- 2. THE GATEKEEPER ---
    is_deadweight = False

    # A. Quantitative Safety (Immediate Keep)
    if meaningful_quant_count > 0:
        return None, modified_text

    # B. Deadweight Combinations
    if aoci_count > 0 and termination_count > 0:
        is_deadweight = True

    elif (
        hedging_sentence_count == hedging_sentences_with_indicators
        and hedging_sentence_count > 0
    ):
        is_deadweight = True

    elif potential_count > 0:
        if is_strictly_generic and trading_denial_count > 0:
            is_deadweight = True
        elif absence_count > 0:
            is_deadweight = True
        elif termination_count > 0:
            is_deadweight = True
        elif trading_denial_count > 0:
            is_deadweight = True

    else:
        if current_year_activity_count == 0 and has_only_past_years(text_orig, year):
            is_deadweight = True
        elif trading_denial_count > 0 and is_strictly_generic:
            is_deadweight = True
        elif termination_count > 0 and absence_count > 0:
            is_deadweight = True
        elif absence_count > 0:
            is_deadweight = True
        elif trading_denial_count > 0 and absence_count > 0:
            is_deadweight = True
        elif has_only_past_years(text_orig, year):
            # Double indicators strongly suggests discarding (ex./ We closed out... The closing of the swap...). We make sure that there are no future years mentioned
            if absence_count > 1 or termination_count > 1 or potential_count > 1:
                is_deadweight = True

    if is_deadweight:
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ), modified_text

    return None, modified_text


def check_deadweight_exclusions(text: str, year: Optional[int] = None) -> Optional[str]:
    """
    Checks for general deadweight categories (Policy, History, etc.).
    Returns the specific tag string if excluded, else None.
    """

    # B. Historical Check
    if year:
        temp_text = _cleaner.clean_numerics(text, remove_years=False)
        all_years = [int(y) for y in YEAR_REGEX.findall(temp_text)]
        if all_years and all(y < year for y in all_years):
            if not ACTIVE_STATE_REGEX.search(temp_text):
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
    if AOCI_NOISE_REGEX.search(text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.AOCI)

    # C. Counterparty / Credit Risk (With exemption for explicit credit derivatives)
    if COUNTERPARTY_REGEX.search(text) and not CR_REGEX.search(text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.CREDIT)

    return None

def process_item(item: Tuple) -> Optional[Tuple]:
    """
    Firm-Level Filter with Token Injection & Entity Masking.

    UPDATED: Now passes ALL firms through, even if they have 0 valid signals.
    Deadweight paragraphs are tagged, but the firm is NOT dropped.
    """
    url, matches_json, cik, year, categories_json = item
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    modified_paragraphs = []
    all_discards_log = []

    for p in paragraphs:
        # 0. Pre-Check
        if DEADWEIGHT_TOKEN in p:
            modified_paragraphs.append(p)
            continue

        # 1. PREPARE VERSIONS
        # A. Normalized Original (For Final Output & Quant Checks)
        # preserves "JPM", "Goldman", "2023"
        p_norm = _cleaner.normalize_whitespace(p)

        # B. Masked (For Logic Checks)
        # replaces "JPM" -> "_E", cleans layout for regex safety
        p_masked = _cleaner.clean_entities(p)
        # Note: clean_entities calls normalize_whitespace internally

        # 2. Level 2 Filter (Pass BOTH)
        # We logic-check p_masked, but we insert tags into p_norm
        tag, processed_text = check_refinement_exclusions(p_norm, p_masked, year)

        # 3. Level 3 Filter (Deadweight Check on MASKED)
        if tag is None:
            tag = check_deadweight_exclusions(p_masked, year)
            # If tag found here, apply it to the (potentially modified) text
            # processed_text usually matches p_norm here if no sentence tags were added above,
            # but if check_refinement added inner tags but returned None for paragraph tag,
            # we want to keep those inner tags.

        # 4. Construction
        if tag is None:
            # Valid Active Signal
            modified_paragraphs.append(processed_text)
        else:
            # Deadweight (Historical / Boilerplate)
            # Result: "_D<ANLZ> _S<TRADING> We do not trade..."
            modified_paragraphs.append(f"{tag} {processed_text}")
            all_discards_log.append((url, processed_text, tag))

    # PASS EVERYTHING (No dropping)
    return (url, json.dumps(modified_paragraphs), categories_json, cik, year, all_discards_log)


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
        """
        CREATE TABLE IF NOT EXISTS category (
            url TEXT PRIMARY KEY,
            categories TEXT NOT NULL,  -- JSON array of category labels ['ir', 'fx', 'gen', ...]
            FOREIGN KEY (url) REFERENCES webpage_result(url)
        )
        """
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS discarded_sentences (id INTEGER PRIMARY KEY, url TEXT, sentence TEXT, discard_reason TEXT)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
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
        SELECT w.url, w.matches, r.cik, r.year, c.categories
        FROM webpage_result w 
        LEFT JOIN report_data r ON w.url = r.url
        LEFT JOIN category c ON w.url = c.url
        WHERE w.matches IS NOT NULL
        """
    )
    data = c.fetchall()
    conn.close()
    return [row for row in data if row[0] not in processed_urls]


# --- NEW: Buffer flush helper ---
def flush_buffers(conn, buffer, discards):
    if not buffer and not discards:
        return

    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        if buffer:
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
        if discards:
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                discards,
            )
        conn.commit()
    except Exception as e:
        print(f"❌ Write Error: {e}")
        conn.rollback()


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

            url, matches, categories, cik, year, discards = result
            buffer_res.append((url, matches, categories, cik, year))
            if discards:
                buffer_disc.extend(discards)

            if len(buffer_res) >= BATCH_SIZE or len(buffer_disc) >= BATCH_SIZE:
                flush_buffers(conn, buffer_res, buffer_disc)

            count += 1

    # Final flush
    flush_buffers(conn, buffer_res, buffer_disc)

    conn.close()
    print(f"✅ Complete. Processed {count} documents.")
