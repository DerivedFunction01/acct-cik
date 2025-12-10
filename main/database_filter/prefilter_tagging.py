"""
MERGED PHASE: Semantic Filtering + Sentence Tagging + Refinement

Combines the old prefilter_simple_nonuse.py + prefilter_tagging.py into one stage.

This phase:
1. Tag each sentence with noise reasons (_S<REASON>)
2. Parse tags to evaluate paragraph-level deadweight combinations
3. Mark paragraphs with _D<REASON> if needed
4. Preserve all text with audit trail

Eliminates duplication and reduces processing from hours to ~30 minutes.
"""

import sqlite3
import json
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from typing import Optional, Set, Dict, List, Tuple
import re

# --- REGEX IMPORTS ---
from derivative_regex import (
    ABSENCE_REGEX,
    ACTIVE_STATE_REGEX,
    AOCI_NOISE_REGEX,
    DEFINITION_INDICATORS,
    DER_STD_REGEX,
    EMBEDDED_CAP_FLOOR_REGEX,
    EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX,
    HEDGING_CONTEXT_REGEX,
    IS_REFERENCE_REGEX,
    LOOSE_GEN_REGEX,
    MORE_INFO_REGEX,
    NEGATIVE_INTENT_REGEX,
    POTENTIAL_REGEX,
    SENTENCE_SPLIT_PATTERN,
    SOFT_REGEX,
    TERMINATION_REGEX,
    TRADING_STATEMENTS_REGEX,
    VAGUE_TIMING_REGEX,
    YEAR_REGEX,
    is_contractual_noise,
    is_hypothetical_noise,
    is_regulatory_noise,
)

from final_verification import COUNTERPARTY_REGEX, HEDGE_DOC_REGEX
from prefilter_database import is_sophisticated_content
from prefiltered_lib import (
    DEADWEIGHT_TOKEN,
    SKIP_TOKEN,
    MinimalTextCleaner,
    NoiseReason,
    get_tag,
)
from notional_filter import check_is_quantitative_zero
from prefilter_evidence import PNL_CONTEXT_REGEX

# --- CONFIGURATION ---
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "prefiltered_data.db"
TARGET_DB_PATH = "tagged_data.db"

_cleaner = MinimalTextCleaner()

# =============================================================================
# TAG PARSING (Extract what was tagged)
# =============================================================================

TAG_PARSER = re.compile(r"_S<([^>]+)>")


def extract_sentence_tags(text: str) -> Set[str]:
    """Parse _S<REASON> tags from sentence. Returns set of reason strings."""
    return set(TAG_PARSER.findall(text))


# =============================================================================
# SENTENCE-LEVEL TAGGING
# =============================================================================


def tag_paragraph(text: str, reporting_year: int) -> str:
    """
    Tag individual sentences with noise reasons.

    Applies _S<REASON> tags to mark sentences as non-evidence,
    but preserves original text for context.
    """

    masked_text = _cleaner.clean_entities(text)

    original_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
    ]
    masked_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(masked_text) if s.strip()
    ]

    if len(original_sentences) != len(masked_sentences):
        masked_sentences = original_sentences

    tagged_output = []

    for orig, masked in zip(original_sentences, masked_sentences):
        reason: Optional[str] = None

        # --- A. Structural Noise ---
        if IS_REFERENCE_REGEX.search(masked) or MORE_INFO_REGEX.search(masked):
            reason = NoiseReason.REF.value
        elif DEFINITION_INDICATORS.search(masked):
            reason = NoiseReason.DEF.value
        elif AOCI_NOISE_REGEX.search(masked):
            reason = NoiseReason.AOCI.value
        elif EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX.search(masked):
            reason = NoiseReason.NPNS.value
        elif TRADING_STATEMENTS_REGEX.search(masked):
            reason = NoiseReason.TRADING.value
        elif EMBEDDED_CAP_FLOOR_REGEX.search(masked):
            reason = NoiseReason.LOAN.value

        # --- B. Soft Kills (Policy / Credit) ---
        elif HEDGE_DOC_REGEX.search(masked):
            reason = NoiseReason.POLICY.value
        elif COUNTERPARTY_REGEX.search(masked):
            reason = NoiseReason.CREDIT.value

        # --- C. Bag-of-Words Scoring ---
        elif is_contractual_noise(masked, threshold=2):
            reason = NoiseReason.CONTRACT.value
        elif is_regulatory_noise(masked, threshold=2):
            reason = NoiseReason.REG.value
        elif not is_sophisticated_content(masked) and is_hypothetical_noise(
            masked, threshold=2
        ):
            reason = NoiseReason.HYP_SCORE.value

        # --- D. Classification Killers (Logic Helpers) ---
        if not reason:
            if reporting_year:
                text_clean = _cleaner.clean_numerics(masked, remove_years=False)
                years = [int(y) for y in YEAR_REGEX.findall(text_clean)]
                if years and all(y < reporting_year for y in years):
                    if not ACTIVE_STATE_REGEX.search(masked):
                        reason = NoiseReason.TIME.value

        if not reason:
            if POTENTIAL_REGEX.search(masked) or VAGUE_TIMING_REGEX.search(masked):
                reason = NoiseReason.HYPO.value

        if not reason:
            if NEGATIVE_INTENT_REGEX.search(masked) or ABSENCE_REGEX.search(masked):
                reason = NoiseReason.NEG.value

        if not reason:
            if TERMINATION_REGEX.search(masked):
                reason = NoiseReason.TERM.value

        if not reason:
            if reporting_year:
                text_clean = _cleaner.clean_for_quant_analysis(orig)
                if check_is_quantitative_zero(text_clean, reporting_year):
                    reason = NoiseReason.ZERO.value

        # --- TAGGING ---
        if reason:
            tagged_output.append(f"{get_tag(SKIP_TOKEN, reason)} {orig}")
        else:
            tagged_output.append(orig)

    return " ".join(tagged_output)


# =============================================================================
# TAG-BASED REFINEMENT (Semantic Deadweight Detection)
# =============================================================================


def evaluate_paragraph_by_tags(
    text: str, reporting_year: Optional[int]
) -> Optional[str]:
    """
    Parse the _S<REASON> tags in a paragraph to decide if it should be marked deadweight.

    This is the **semantic refinement** step that was in prefilter_simple_nonuse.py.
    Now it reads tags instead of recounting sentences.

    Returns:
    - None: Keep the paragraph (valid evidence exists)
    - str: Tag to apply (e.g., "_D<ANLZ>")

    Logic:
    1. Extract all sentence-level tags from the paragraph
    2. Find sentences without noise tags (potential proof sentences)
    3. Check for meaningful semantic deadweight combinations
    4. Check if any proof sentences survived with derivative keywords
    """

    sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()]

    if not sentences:
        return None

    # --- Count tags across all sentences ---
    all_tags = set()
    proof_sentences = []  # Sentences without noise tags

    for sent in sentences:
        sent_tags = extract_sentence_tags(sent)
        all_tags.update(sent_tags)

        if not sent_tags:
            # This sentence has no noise tag = potential proof
            proof_sentences.append(sent)

    # --- Check for semantic deadweight combinations ---

    # 1. AOCI + Termination = Realized gains from closed positions
    #    Semantic signal: Position was closed/expired, gains realized in AOCI
    if NoiseReason.AOCI.value in all_tags and NoiseReason.TERM.value in all_tags:
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ)

    # 2. AOCI + PnL = Duplicate accounting discussions
    #    Both realized and unrealized accounting boilerplate
    if NoiseReason.AOCI.value in all_tags and NoiseReason.PNL.value in all_tags:
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ)

    # 3. All sentences tagged with noise = No actual evidence
    #    Every sentence was marked as non-evidence (TIME, HYPO, NEG, TERM, etc.)
    if not proof_sentences and sentences:
        return get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ)

    # 4. Proof sentences exist but contain no derivative keywords
    #    (Untagged sentences are just methodology/context, not position evidence)
    if proof_sentences:
        combined_proof = " ".join(proof_sentences)
        if not SOFT_REGEX.search(combined_proof):
            for sent in proof_sentences:
                if LOOSE_GEN_REGEX.search(sent):
                    if HEDGING_CONTEXT_REGEX.search(sent) or DER_STD_REGEX.search(sent):
                        return None
            # Untagged sentences don't mention derivatives
            # This is pure methodology discussion (e.g., "Derivatives are valued using...")
            return get_tag(DEADWEIGHT_TOKEN, NoiseReason.ANLZ)

    # --- All checks passed: Keep the paragraph ---
    return None


# =============================================================================
# MAIN PROCESSING
# =============================================================================


def process_row(row: Tuple) -> Optional[Tuple]:
    """
    Process a single document.

    Steps:
    1. Load paragraphs from database
    2. Tag each sentence with noise reasons
    3. Evaluate paragraph by tags (semantic combinations)
    4. Apply paragraph-level deadweight tags if needed
    5. Return modified paragraphs
    """

    url, matches_json, cik, year = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    new_paragraphs = []

    for p in paragraphs:
        # Respect existing deadweight tags from Phase 0
        if p.startswith(DEADWEIGHT_TOKEN):
            new_paragraphs.append(p)
            continue

        # Step 1: Normalize whitespace
        p_norm = _cleaner.normalize_whitespace(p)

        # Step 2: Tag individual sentences
        tagged_p = tag_paragraph(p_norm, year)

        # Step 3: Evaluate by tags (parse _S<> tags to make paragraph decision)
        para_tag = evaluate_paragraph_by_tags(tagged_p, year)

        # Step 4: Apply paragraph tag if needed
        if para_tag:
            # Paragraph is deadweight: _D<ANLZ> [tagged sentences]
            final_p = f"{para_tag} {tagged_p}"
        else:
            # Paragraph survives: [tagged sentences]
            final_p = tagged_p

        new_paragraphs.append(final_p)

    return (url, json.dumps(new_paragraphs), cik, year)


# =============================================================================
# DATABASE & INFRASTRUCTURE
# =============================================================================


def setup_target_db(path):
    """Create target database schema."""
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
    """Get URLs already processed."""
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
    """Stream unprocessed rows from source database."""
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
    """Write batch of results to database."""
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


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print(f"🚀 Starting Merged Tagging Phase ({NUM_WORKERS} workers)")
    setup_target_db(TARGET_DB_PATH)
    processed = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed)} already processed URLs")

    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    buffer = []
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        source = list(data_generator(SOURCE_DB_PATH, processed))
        print(f"📦 Processing {len(source)} documents")

        for result in tqdm(
            executor.map(process_row, source, chunksize=CHUNK_SIZE),
            total=len(source),
            unit="docs",
            desc="Tagging",
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
