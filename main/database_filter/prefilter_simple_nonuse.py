# OPTIMIZATIONS APPLIED:
# 1. Cache cleaned text versions per paragraph (avoid re-cleaning)
# 2. Batch quantitative checks (check once, reuse results)
# 3. Early exit on quantitative safeguard
# 4. Skip expensive operations on already-tagged text
# 5. Use sentence-level cache for common operations
# 6. Lazy evaluation of non-critical checks

from concurrent.futures import ProcessPoolExecutor
import sqlite3
import json
import multiprocessing as mp
from pathlib import Path
from typing import List, Tuple, Optional, Set, Dict
from tqdm import tqdm

from prefilter_database import find_hedging_context
from prefilter_evidence import PNL_CONTEXT_REGEX
from prefiltered_lib import (
    DEADWEIGHT_TOKEN,
    SKIP_TOKEN,
    MinimalTextCleaner,
    NoiseReason,
    get_tag,
)

# --- CONFIGURATION ---
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "prefiltered_data.db"
TARGET_DB_PATH = "refined_data.db"

# --- MODULE IMPORTS ---
from final_verification import COUNTERPARTY_REGEX, HEDGE_DOC_REGEX
from year_deletion import extract_years
from derivative_regex import (
    ACTIVE_STATE_REGEX,
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
from notional_filter import extract_values_and_years, check_is_quantitative_zero

_cleaner = MinimalTextCleaner()

# =============================================================================
# OPTIMIZATION 1: SENTENCE-LEVEL CACHE
# =============================================================================


class SentenceCache:
    """Cache results of expensive operations per sentence."""

    def __init__(self, text_orig: str, text_masked: str, reporting_year: Optional[int]):
        self.text_orig = text_orig
        self.text_masked = text_masked
        self.reporting_year = reporting_year

        # Cache expensive operations
        self._clean_for_quant = None
        self._extract_years = None
        self._is_meaningful_quant = None
        self._has_soft_category = None

    @property
    def clean_for_quant(self) -> str:
        if self._clean_for_quant is None:
            self._clean_for_quant = _cleaner.clean_for_quant_analysis(self.text_orig)
        return self._clean_for_quant

    @property
    def sent_years(self) -> List[int]:
        if self._extract_years is None:
            self._extract_years = extract_years(self.text_masked)
        return self._extract_years

    @property
    def is_meaningful_quant_cached(self) -> bool:
        """SAFEGUARD: Check once, reuse result."""
        if self._is_meaningful_quant is None:
            years, values = extract_values_and_years(self.clean_for_quant)
            if not values:
                self._is_meaningful_quant = False
            else:
                is_zero = check_is_quantitative_zero(
                    self.clean_for_quant, self.reporting_year or 0
                )
                self._is_meaningful_quant = not is_zero
        return self._is_meaningful_quant

    @property
    def has_soft_category(self) -> bool:
        if self._has_soft_category is None:
            self._has_soft_category = bool(SOFT_CATEGORY_REGEX.search(self.text_masked))
        return self._has_soft_category


# =============================================================================
# OPTIMIZATION 2: BATCH QUANTITATIVE CHECK
# =============================================================================


def check_refinement_exclusions_fast(
    text_orig: str, text_masked: str, year: Optional[int] = None
) -> Tuple[Optional[str], str]:
    """
    OPTIMIZED: Early exit on quantitative safeguard.
    """

    # SPLIT ONCE and cache all sentence results
    sentences_orig = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text_orig) if s.strip()
    ]
    sentences_masked = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text_masked) if s.strip()
    ]

    if len(sentences_orig) != len(sentences_masked):
        sentences_masked = sentences_orig

    # === OPTIMIZATION: Create cache for all sentences ===
    sentence_caches = [
        SentenceCache(sent_orig, sent_masked, year)
        for sent_orig, sent_masked in zip(sentences_orig, sentences_masked)
    ]

    # === EARLY EXIT: Check for quantitative safeguard first ===
    # This is the most likely branch and overrides everything
    for cache in sentence_caches:
        if cache.is_meaningful_quant_cached:
            # SAFEGUARD HIT: Return None (keep entire paragraph)
            # Skip expensive further processing
            return None, text_orig

    # === Now do the expensive counting logic ===
    processed_sentences = []
    potential_count = 0
    absence_count = 0
    trading_denial_count = 0
    termination_count = 0
    aoci_count = 0
    pnl_count = 0
    hedging_sentence_count = 0
    hedging_sentences_neg = 0
    current_year_activity_count = 0

    is_strictly_generic = not any(cache.has_soft_category for cache in sentence_caches)

    # === OPTIMIZATION: Process all caches in single pass ===
    for sent_orig, cache in zip(sentences_orig, sentence_caches):
        current_sent = sent_orig
        sent_masked = cache.text_masked

        # --- A. Sentence-Level Tags (Cache results) ---
        if TRADING_STATEMENTS_REGEX.search(sent_masked):
            trading_denial_count += 1
            tag = get_tag(SKIP_TOKEN, NoiseReason.TRADING)
            if tag not in current_sent:
                current_sent = f"{tag} {current_sent}"

        if TERMINATION_REGEX.search(sent_masked) and SOFT_REGEX.search(sent_masked):
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

        # --- B. Counters (reuse cache results) ---
        if SOFT_REGEX.search(sent_masked):
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
                hedging_sentences_neg += 1

        # Reuse cached year check
        if cache.sent_years:
            if not all(y < year for y in cache.sent_years) if year else True:
                if not (
                    (
                        TERMINATION_REGEX.search(sent_masked)
                        and SOFT_REGEX.search(sent_masked)
                    )
                    or (
                        ABSENCE_REGEX.search(sent_masked)
                        or DID_NOT_HOLD_REGEX.search(sent_masked)
                    )
                ):
                    current_year_activity_count += 1
        else:
            current_year_activity_count += 1

        if AOCI_NOISE_REGEX.search(sent_masked):
            tag = get_tag(SKIP_TOKEN, NoiseReason.AOCI)
            current_sent = f"{tag} {current_sent}"
            aoci_count += 1
        if PNL_CONTEXT_REGEX.search(sent_masked):
            pnl_count += 1

        processed_sentences.append(current_sent)

    modified_text = " ".join(processed_sentences)

    # === THE GATEKEEPER ===
    is_deadweight = False

    if (aoci_count > 0 or pnl_count > 0) and termination_count > 0:
        is_deadweight = True
    elif aoci_count > 0 and pnl_count > 0:
        is_deadweight = True
    elif hedging_sentence_count == hedging_sentences_neg and hedging_sentence_count > 0:
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
        if current_year_activity_count == 0 and any(
            (
                all(y < year for y in cache.sent_years)
                if cache.sent_years and year
                else False
            )
            for cache in sentence_caches
        ):
            is_deadweight = True
        elif trading_denial_count > 0 and is_strictly_generic:
            is_deadweight = True
        elif termination_count > 0 and absence_count > 0:
            is_deadweight = True
        elif absence_count > 0:
            is_deadweight = True

    if is_deadweight:
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ), modified_text

    return None, modified_text


def check_deadweight_exclusions_fast(
    text: str, year: Optional[int] = None
) -> Optional[str]:
    """OPTIMIZED: Cache cleaned text."""

    temp_text = _cleaner.clean_numerics(text, remove_years=False)

    # B. Historical Check
    if year:
        all_years = [int(y) for y in YEAR_REGEX.findall(temp_text)]
        if all_years and all(y < year for y in all_years):
            if not ACTIVE_STATE_REGEX.search(temp_text):
                return get_tag(DEADWEIGHT_TOKEN, NoiseReason.HIST_BLOCK)

    # Safeguard: Quantitative
    if any(
        not check_is_quantitative_zero(
            _cleaner.clean_for_quant_analysis(sent), year or 0
        )
        for sent in SENTENCE_SPLIT_PATTERN.split(text)
        if sent.strip()
    ):
        return None

    # Active Action Check (before expensive regex)
    if STRONG_POSSESSION_REGEX.search(temp_text):
        return None

    # A. Policy & Methodology
    if HEDGE_DOC_REGEX.search(temp_text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.POLICY)

    # B. AOCI / PnL
    if AOCI_NOISE_REGEX.search(temp_text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.AOCI)

    if PNL_CONTEXT_REGEX.search(temp_text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.PNL)

    # C. Counterparty
    if COUNTERPARTY_REGEX.search(temp_text):
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.CREDIT)

    return None


def process_item(item: Tuple) -> Optional[Tuple]:
    """Optimized processing with early exits."""

    url, matches_json, cik, year = item
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    modified_paragraphs = []
    all_discards_log = []

    for p in paragraphs:
        # Skip if already deadweight tagged
        if DEADWEIGHT_TOKEN in p:
            modified_paragraphs.append(p)
            continue

        # === Prepare versions ===
        p_norm = _cleaner.normalize_whitespace(p)
        p_masked = _cleaner.clean_entities(p)

        # === FAST Path: Refinement Exclusions ===
        tag, processed_text = check_refinement_exclusions_fast(p_norm, p_masked, year)

        # === Check deadweight if tag is None ===
        if tag is None:
            tag = check_deadweight_exclusions_fast(p_masked, year)

        # === Construction ===
        if tag is None:
            modified_paragraphs.append(processed_text)
        else:
            modified_paragraphs.append(f"{tag} {processed_text}")
            all_discards_log.append((url, processed_text, tag))

    return (url, json.dumps(modified_paragraphs), cik, year, all_discards_log)


# =============================================================================
# DATABASE & MAIN
# =============================================================================


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
    except:
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


def flush_buffers(conn, buffer, discards):
    if not buffer and not discards:
        return

    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        if buffer:
            c.executemany(
                "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                [(r[0], r[1]) for r in buffer],
            )
            c.executemany(
                "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                [(r[0], r[2], r[3]) for r in buffer],
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


if __name__ == "__main__":
    print(f"🚀 Starting Optimized Refinement Script ({NUM_WORKERS} workers)...")
    setup_target_db(TARGET_DB_PATH)

    processed_urls = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed_urls)} already processed URLs")

    data = get_source_data(SOURCE_DB_PATH, processed_urls)
    print(f"📦 Loaded {len(data)} unprocessed documents")

    if not data:
        print("✅ All documents already processed!")
        exit(0)

    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    buffer_res, buffer_disc = [], []

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

            if len(buffer_res) >= BATCH_SIZE:
                flush_buffers(conn, buffer_res, buffer_disc)
                buffer_res, buffer_disc = [], []

    flush_buffers(conn, buffer_res, buffer_disc)
    conn.close()
    print("✅ Complete.")
