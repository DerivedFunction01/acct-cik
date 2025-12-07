import sqlite3
import json
import re
import multiprocessing as mp
import time
from pathlib import Path
from queue import Empty
from typing import List, Tuple, Optional, Set
from tqdm import tqdm

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
QUEUE_SIZE = NUM_WORKERS * 50
SOURCE_DB_PATH = "web_data.db"
TARGET_DB_PATH = "prefiltered_data.db"

# --- IMPORTS ---
from derivative_regex import (
    ACCOUNTING_STANDARDS_STRICT_REGEX,
    DER_STD_REGEX,
    ENTITY_EXCLUSION_REGEX,
    ENTITY_TOKEN,
    EQ_REGEX,
    EQ_SOFT_REGEX,
    EXCLUDE_REGEX_EQUITY_COMP,
    EXCLUDE_REGEX_FILING,
    EXCLUDE_REGEX_LEGAL_LITIGATION,
    EXCLUDE_COMPETITOR_REGEX,
    EXCLUDE_NON_FINANCIAL_REGEX,
    EXCLUDE_PLAN_ASSETS_REGEX,
    EXCLUDE_HYPOTHETICAL_REGEX,
    EXCLUDE_REGEX_FORWARD_LOOKING,
    HEDGING_CONTEXT_REGEX,
    LOOSE_GEN_REGEX,
    SENTENCE_SPLIT_PATTERN,
    SOFT_GEN_REGEX,
    SOFT_REGEX,
    STRICT_REGEX,
    TABLE_REGEX,
    VALUATION_MODELS,
    aggregate_discards,
    build_alternation,
    is_contractual_noise,
    is_regulatory_noise,
)

from final_verification import QUANT_REGEX
from table_processor import TableToTextConverter

# =============================================================================
# SOPHISTICATED CONTEXT DEFINITIONS
# =============================================================================
# 1. Target Instruments (The "What") - NOW REQUIRES EQ CONTEXT
# Instead of just matching "convertible" or "warrant" standalone,
# we require them to co-occur with equity derivative signals
SOPHISTICATED_TARGETS = re.compile(
    r"\b(?:convertibles?|warrants?|conversion)\b", re.IGNORECASE
)

# NEW: Gate for Sophisticated Targets
# Ensures we only flag convertibles/warrants that are ACTUALLY equity derivatives
SOPHISTICATED_TARGET_GATE = re.compile(
    rf"(?:{EQ_REGEX.pattern}|{EQ_SOFT_REGEX.pattern})", re.IGNORECASE
)

WARRANT_CATCHER = re.compile(r"\bwarrants?\b", re.IGNORECASE)

# 2. Sophisticated Context (The "Why/How")
# Used to validate the sophisticated buffer.
SOPHISTICATED_CONTEXT_TERMS = [
    # REFINED: "embedded" must be followed by a relevant noun to be a self-validating signal
    r"embedded\s+(?:derivatives?|conversions?|features?|options?|liabilit(?:y|ies))",
    r"bifurcat(?:e|ion|ed)",
    r"derivative\s+liabilit(?:y|ies)",
    r"host\s+contracts?",
    r"conversion\s+(?:options?|features?|prices?|rates?)",
    r"cash\s+conversions?",
    r"make[- ]whole",
    r"fundamental\s+change",
    r"fair\s+value\s+options?",
] + VALUATION_MODELS  # Black-Scholes, Monte Carlo, etc.

SOPHISTICATED_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(SOPHISTICATED_CONTEXT_TERMS) + r"\b", re.IGNORECASE
)


def is_sophisticated_target(text: str) -> bool:
    """
    Returns True if text contains a sophisticated target (convertible/warrant/conversion)
    AND has equity derivative context (EQ_REGEX or EQ_SOFT_REGEX).

    This prevents false positives from unrelated mentions of "warrant" or "convertible".
    """
    # Quick exit: no target word present
    if not SOPHISTICATED_TARGETS.search(text):
        return False

    # Required: target must have equity context
    if SOPHISTICATED_TARGET_GATE.search(text):
        return True

    return False


def is_sophisticated_content(text: str) -> bool:
    """
    Returns True if text is sophisticated derivative content.
    Checks: (Target + EQ context) OR (Sophisticated context terms)

    Used throughout to gate sophisticated buffer routing.
    """
    return is_sophisticated_target(text) or bool(SOPHISTICATED_CONTEXT_REGEX.search(text))


# =============================================================================
# TABLE CLEANUP HELPERS
# =============================================================================

FOOTNOTE_PATTERN = re.compile(r"<FN>(.*?)</FN>\s*</TABLE>", re.DOTALL | re.IGNORECASE)
INDIVIDUAL_FOOTNOTE_PATTERN = re.compile(
    r"<F\s+(\d+)>\s*(.*?)(?=<F\s+\d+>|$)", re.DOTALL
)
TAG_PATTERN = re.compile(r"<[^>]+>")


def check_hard_exclusions(text: str) -> Optional[str]:
    """
    Checks text against 'Dead Weight' filters.
    Returns the discard reason string if matched, otherwise None.

    Order optimized for performance:
    1. Structural/Boilerplate (High frequency)
    2. Specific Topic Filters (Simple Regex)
    3. Scoring Logic (Most expensive, run last)
    """

    # --- TIER 1: HIGH FREQUENCY BOILERPLATE ---
    if EXCLUDE_REGEX_FILING.search(text):
        return "filing"

    if EXCLUDE_REGEX_FORWARD_LOOKING.search(text):
        return "forward_looking"

    # --- TIER 2: SPECIFIC TOPIC FILTERS ---
    if EXCLUDE_REGEX_LEGAL_LITIGATION.search(text):
        return "legal_litigation"

    if EXCLUDE_PLAN_ASSETS_REGEX.search(text):
        return "pension_plan_assets"

    if EXCLUDE_NON_FINANCIAL_REGEX.search(text):
        return "non_financial"

    if EXCLUDE_COMPETITOR_REGEX.search(text):
        return "competitor_analysis"

    # --- TIER 3: SCORING / DENSITY CHECKS (Heavier Ops) ---
    if is_regulatory_noise(text):
        return "regulatory_boilerplate"

    if is_contractual_noise(text):
        return "contractual_noise"
    return None


def extract_and_separate_footnotes(table_text: str) -> Tuple[str, List[str]]:
    footnotes = []
    fn_match = FOOTNOTE_PATTERN.search(table_text)
    if fn_match:
        fn_content = fn_match.group(1)
        individual_fns = INDIVIDUAL_FOOTNOTE_PATTERN.findall(fn_content)
        for fn_num, fn_text in individual_fns:
            cleaned = fn_text.strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            if cleaned:
                footnotes.append(f"Footnote {fn_num}: {cleaned}")
        cleaned_table = FOOTNOTE_PATTERN.sub("</TABLE>", table_text)
        return cleaned_table, footnotes
    return table_text, []


def strip_table_formatting(
    table_text: str, url: str
) -> Tuple[str, List[Tuple[str, str, str]]]:
    text = TAG_PATTERN.sub("", table_text)
    lines = text.split("\n")
    cleaned_lines = []
    excluded_rows = []

    for line in lines:
        stripped = line.strip()
        if not stripped or all(c in "-\t " for c in stripped):
            continue

        exclusion_reason = check_hard_exclusions(stripped)
        if exclusion_reason:
            excluded_rows.append((url, stripped, exclusion_reason))
            continue

        cleaned_lines.append(stripped)

    result = " ".join(cleaned_lines)
    return re.sub(r"\s+", " ", result).strip(), excluded_rows


def is_text_container_table(table_text: str, footnotes: List[str]) -> bool:
    if not TableToTextConverter:
        return True
    context_str = " ".join(footnotes)
    try:
        converter = TableToTextConverter(
            table_text, narrative_context=context_str, is_sophisticated=True
        )
        sentences = converter.process()
        return len(sentences) == 0
    except Exception:
        return True


# =============================================================================
# WORKER LOGIC
# =============================================================================
def process_accounting_standards_paragraph(
    paragraph: str, url: str
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """
    Process a paragraph that contains accounting standards boilerplate.

    Logic:
    1. Keep all sentences BEFORE the first boilerplate trigger
    2. Once we hit boilerplate, only keep sentences with quantifiable amounts
    3. Also keep sentences that precede quantifiable sentences (lookahead)

    Args:
        paragraph: Full original paragraph text
        url: Document URL (for discard logging)

    Returns:
        (kept_sentences: List[str], discards: List[(url, text, reason)])
    """
    kept = []
    sentences = SENTENCE_SPLIT_PATTERN.split(paragraph)
    in_accounting_boilerplate = False

    for sent_idx, sent in enumerate(sentences):
        if not in_accounting_boilerplate:
            # Haven't hit boilerplate yet - keep all non-boilerplate sentences
            if not ACCOUNTING_STANDARDS_STRICT_REGEX.search(sent):
                kept.append(sent)
            else:
                # We've entered the accounting standards zone
                in_accounting_boilerplate = True
                # Check if this sentence has quantifiable amounts
                if QUANT_REGEX.search(sent):
                    kept.append(sent)
                # else: discard it, and everything after
        else:
            # Already in boilerplate zone
            if QUANT_REGEX.search(sent):
                # Current sentence is quantifiable - keep it
                kept.append(sent)
            elif sent_idx + 1 < len(sentences):
                # Look ahead: keep this sentence if next sentence is quantifiable
                # and not another boilerplate trigger
                next_sent = sentences[sent_idx + 1]
                if QUANT_REGEX.search(
                    next_sent
                ) and not ACCOUNTING_STANDARDS_STRICT_REGEX.search(next_sent):
                    kept.append(sent)

    # Process discards
    discards = []
    discarded_text = " ".join(set(sentences) - set(kept))
    if discarded_text:
        discards.append((url, discarded_text, "accounting_standards"))

    return kept, discards


def find_hedging_context(paragraph: str) -> bool:
    """Standard Gatekeeper for regular derivatives."""
    if STRICT_REGEX.search(paragraph):
        return True
    elif SOFT_GEN_REGEX.search(paragraph):
        return True
    elif SOFT_REGEX.search(paragraph) and HEDGING_CONTEXT_REGEX.search(paragraph):
        return True
    elif DER_STD_REGEX.search(paragraph) and LOOSE_GEN_REGEX.search(paragraph):
        return True
    elif WARRANT_CATCHER.search(paragraph) and HEDGING_CONTEXT_REGEX.search(paragraph):
        return True
    if "<TABLE>" in paragraph.upper() and TABLE_REGEX.search(paragraph):
        return True
    return False

def validate_sophisticated_buffer(
    sophisticated_buffer: List[str], clean_paragraphs: List[str]
) -> bool:
    """
    Independent validation for Convertibles/Warrants.
    Now uses is_sophisticated_target() and is_sophisticated_content() for consistency.

    Args:
        sophisticated_buffer: List of masked texts from sophisticated buffer
        clean_paragraphs: List of masked texts from standard buffer

    Returns:
        True if sophisticated buffer passes validation, False otherwise
    """
    if not sophisticated_buffer:
        return False

    # 1. Check for Free Pass (Gated Target in standard text)
    # Use is_sophisticated_target() to ensure equity context
    for p in clean_paragraphs:
        if EQ_REGEX.search(p) and is_sophisticated_target(p):
            return True
        if find_hedging_context(p) and is_sophisticated_target(p):
            return True

    # 2. Check for Internal Sophisticated Context
    # Combined text from all sophisticated paragraphs
    combined_text = " ".join(sophisticated_buffer)
    if SOPHISTICATED_CONTEXT_REGEX.search(combined_text):
        return True

    return False


def process_item(item: Tuple) -> Optional[Tuple]:
    """
    Process a single document item through the filtering pipeline.

    Returns: (url, json_paragraphs, cik, year, discards) or None on error
    """
    try:
        url, matches_json, cik, year = item
    except (ValueError, TypeError) as e:
        print(f"❌ Error unpacking item: {e}")
        return None

    try:
        paragraphs = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"❌ Error parsing JSON for {url}: {e}")
        return None

    # Helper function to append to both buffers atomically
    def append_to_buffer(buffer_type: str, idx: int, text_orig: str, text_masked: str):
        """Append (index, text) tuples to both original and masked buffers."""
        if buffer_type == "clean":
            clean_buffer_orig.append((idx, text_orig))
            clean_buffer_masked.append((idx, text_masked))
        elif buffer_type == "sophisticated":
            sophisticated_buffer_orig.append((idx, text_orig))
            sophisticated_buffer_masked.append((idx, text_masked))

    # Parallel buffer structure
    clean_buffer_orig = []
    clean_buffer_masked = []
    sophisticated_buffer_orig = []
    sophisticated_buffer_masked = []
    local_discards = []

    for idx, p in enumerate(paragraphs):
        try:
            p_masked = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, p)

            # === ACCOUNTING STANDARDS ===
            if ACCOUNTING_STANDARDS_STRICT_REGEX.search(p):
                kept, acc_std_discards = process_accounting_standards_paragraph(p, url)
                local_discards.extend(acc_std_discards)

                if kept:
                    salvaged_p = " ".join(kept)
                    salvaged_p_masked = ENTITY_EXCLUSION_REGEX.sub(
                        ENTITY_TOKEN, salvaged_p
                    )
                    buffer_type = (
                        "sophisticated"
                        if is_sophisticated_content(salvaged_p_masked)
                        else "clean"
                    )
                    append_to_buffer(buffer_type, idx, salvaged_p, salvaged_p_masked)
                continue

            # === TABLE HANDLING ===
            if "<TABLE>" in p.upper():
                try:
                    cleaned_table, footnotes = extract_and_separate_footnotes(p)
                except Exception as e:
                    local_discards.append(
                        (url, p[:100], "table_footnote_extraction_failed")
                    )
                    continue

                try:
                    is_container = is_text_container_table(cleaned_table, footnotes)
                except Exception:
                    is_container = True

                if not is_container:
                    table_masked = ENTITY_EXCLUSION_REGEX.sub(
                        ENTITY_TOKEN, cleaned_table
                    )

                    if EXCLUDE_REGEX_LEGAL_LITIGATION.search(table_masked):
                        local_discards.append((url, "<table>...", "legal_table"))
                        continue

                    is_target = is_sophisticated_target(table_masked)
                    is_context = SOPHISTICATED_CONTEXT_REGEX.search(table_masked)

                    if is_target or is_context:
                        append_to_buffer(
                            "sophisticated", idx, cleaned_table, table_masked
                        )
                        if is_context:
                            append_to_buffer("clean", idx, cleaned_table, table_masked)
                    else:
                        append_to_buffer("clean", idx, cleaned_table, table_masked)

                    if footnotes:
                        for fn in footnotes:
                            fn_masked = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, fn)
                            append_to_buffer("clean", idx, fn, fn_masked)
                    continue
                else:
                    try:
                        p, excluded_rows = strip_table_formatting(cleaned_table, url)
                        local_discards.extend(excluded_rows)
                    except Exception as e:
                        local_discards.append(
                            (url, p[:100], "table_formatting_strip_failed")
                        )
                        continue

                    if footnotes:
                        p += " " + " ".join(footnotes)
                    if not p.strip():
                        continue

                    p_masked = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, p)

            # === EXCLUSIONS ===
            exclusion_reason = check_hard_exclusions(p_masked)
            if exclusion_reason:
                local_discards.append((url, p, exclusion_reason))
                continue

            # === SALVAGE: HYPOTHETICAL ===
            if EXCLUDE_HYPOTHETICAL_REGEX.search(p_masked):
                has_std = STRICT_REGEX.search(p_masked) or (
                    SOFT_REGEX.search(p_masked)
                    and HEDGING_CONTEXT_REGEX.search(p_masked)
                )
                has_soph = is_sophisticated_content(p_masked)

                if not (has_std or has_soph):
                    local_discards.append(
                        (url, p, "hypothetical_sensitivity_methodology")
                    )
                    continue

            # === SALVAGE: EQUITY COMP ===
            if EXCLUDE_REGEX_EQUITY_COMP.search(p_masked):
                try:
                    sentences = SENTENCE_SPLIT_PATTERN.split(p)
                    sentences_masked = SENTENCE_SPLIT_PATTERN.split(p_masked)

                    if len(sentences) != len(sentences_masked):
                        local_discards.append(
                            (url, p[:100], "equity_comp_salvage_failed")
                        )
                        continue

                    kept_indices = []
                    for sent_idx, (sent_masked,) in enumerate(zip(sentences_masked)):
                        if STRICT_REGEX.search(sent_masked):
                            kept_indices.append(sent_idx)
                        elif SOFT_REGEX.search(sent_masked):
                            if (
                                SOFT_GEN_REGEX.search(sent_masked)
                                or DER_STD_REGEX.search(sent_masked)
                                or is_sophisticated_target(sent_masked)
                                or SOPHISTICATED_CONTEXT_REGEX.search(sent_masked)
                            ):
                                kept_indices.append(sent_idx)

                    if kept_indices:
                        if len(kept_indices) == len(sentences):
                            # No discards, use original directly
                            append_to_buffer("clean", idx, p, p_masked)
                        else:
                            # Reconstruct from kept indices
                            salvaged_p = " ".join(sentences[i] for i in kept_indices)
                            salvaged_p_masked = " ".join(
                                sentences_masked[i] for i in kept_indices
                            )
                            buffer_type = (
                                "sophisticated"
                                if is_sophisticated_content(salvaged_p_masked)
                                else "clean"
                            )
                            append_to_buffer(
                                buffer_type, idx, salvaged_p, salvaged_p_masked
                            )

                            # Log discarded sentences
                            discarded_indices = set(range(len(sentences))) - set(
                                kept_indices
                            )
                            discarded_text = " ".join(
                                sentences[i] for i in sorted(discarded_indices)
                            )
                            local_discards.append((url, discarded_text, "comp"))
                except Exception as e:
                    local_discards.append((url, p[:100], "equity_comp_salvage_failed"))
                continue

            # === DISTRIBUTION ===
            is_soph_target = is_sophisticated_target(p_masked)
            is_soph_context = SOPHISTICATED_CONTEXT_REGEX.search(p_masked)

            if is_soph_target:
                append_to_buffer("sophisticated", idx, p, p_masked)
            elif is_soph_context:
                append_to_buffer("sophisticated", idx, p, p_masked)
                append_to_buffer("clean", idx, p, p_masked)
            else:
                append_to_buffer("clean", idx, p, p_masked)

        except Exception as e:
            print(f"❌ Unexpected error processing paragraph {idx} in {url}: {e}")
            local_discards.append(
                (url, str(p)[:100], f"processing_error_{type(e).__name__}")
            )
            continue

    # === FINAL GATEKEEPERS ===
    final_results = []

    try:
        # A. Validate Standard Buffer
        std_masked_texts = [text for _, text in clean_buffer_masked]
        if any(find_hedging_context(p) for p in std_masked_texts):
            final_results.extend(clean_buffer_orig)
        elif clean_buffer_orig:
            discarded = "\n\n".join([text for _, text in clean_buffer_orig])
            local_discards.append((url, discarded, "standard_check_failed"))
    except Exception as e:
        print(f"⚠️ Error validating standard buffer for {url}: {e}")

    try:
        # B. Validate Sophisticated Buffer
        soph_masked_texts = [text for _, text in sophisticated_buffer_masked]
        std_masked_texts = [text for _, text in clean_buffer_masked]

        if validate_sophisticated_buffer(soph_masked_texts, std_masked_texts):
            final_results.extend(sophisticated_buffer_orig)
        elif sophisticated_buffer_orig:
            discarded = "\n\n".join([text for _, text in sophisticated_buffer_orig])
            local_discards.append((url, discarded, "sophisticated_check_failed"))
    except Exception as e:
        print(f"⚠️ Error validating sophisticated buffer for {url}: {e}")

    # === RECONSTRUCT & SORT ===
    try:
        if final_results:
            final_results.sort(key=lambda x: x[0])
            seen = set()
            unique_paragraphs = []
            for _, text in final_results:
                if text not in seen:
                    unique_paragraphs.append(text)
                    seen.add(text)

            return (
                url,
                json.dumps(unique_paragraphs),
                cik,
                year,
                aggregate_discards(local_discards),
            )
    except Exception as e:
        print(f"❌ Error reconstructing final results for {url}: {e}")

    return (url, "[]", cik, year, aggregate_discards(local_discards))


# =============================================================================
# QUEUE PROCESSES
# =============================================================================
def producer_task(
    queue: mp.Queue,
    source_db: str,
    target_db: str,
    processed_urls: Set[str],
    progress_queue: mp.Queue,
):
    """Producer: reads from source DB and queues items, marks empty ones as processed"""
    print("🔌 Producer started...")

    source_conn = sqlite3.connect(source_db)
    source_c = source_conn.cursor()
    source_c.execute(
        "SELECT w.url, w.matches, r.cik, r.year FROM webpage_result w LEFT JOIN report_data r ON w.url = r.url WHERE w.matches IS NOT NULL"
    )

    # Separate connection for marking empty items as processed
    target_conn = sqlite3.connect(target_db)
    target_c = target_conn.cursor()

    empty_buffer = []
    count = 0
    skipped = 0
    empty_matched = 0

    while True:
        rows = source_c.fetchmany(1000)
        if not rows:
            break
        for row in rows:
            url, matches_json, cik, year = row

            # Skip already processed
            if url in processed_urls:
                skipped += 1
                continue

            # If matches is empty JSON array, mark as processed but don't queue
            if matches_json == "[]":
                empty_matched += 1
                empty_buffer.append((url, "[]", cik, year))

                # Report progress for empty items (they're still "processed")
                progress_queue.put(("producer_progress", 1))

                # Flush empty buffer periodically
                if len(empty_buffer) >= 1000:
                    target_c.executemany(
                        "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                        [(u, m) for u, m, _, _ in empty_buffer],
                    )
                    target_c.executemany(
                        "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                        [(u, c, y) for u, _, c, y in empty_buffer],
                    )
                    target_conn.commit()
                    empty_buffer.clear()
                continue

            queue.put(row)
            count += 1

    # Final flush of empty items
    if empty_buffer:
        target_c.executemany(
            "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
            [(u, m) for u, m, _, _ in empty_buffer],
        )
        target_c.executemany(
            "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(u, c, y) for u, _, c, y in empty_buffer],
        )
        target_conn.commit()

    source_conn.close()
    target_conn.close()
    print(
        f"🔌 Producer finished. Queued {count:,} items (Skipped {skipped:,} processed, {empty_matched:,} empty marked)."
    )
    progress_queue.put(("producer_done", None))


def worker_task(
    in_queue: mp.Queue, out_queue: mp.Queue, progress_queue: mp.Queue, worker_id: int
):
    """Worker: processes items and sends results to output queue"""
    items_processed = 0
    while True:
        item = in_queue.get()
        if item is None:  # Sentinel value to exit
            break
        try:
            result = process_item(item)
            if result:
                out_queue.put(result)
            items_processed += 1
            # Report progress every 10 items
            if items_processed % 10 == 0:
                progress_queue.put(("worker_progress", items_processed))
        except Exception as e:
            print(f"⚠️ Worker {worker_id} error: {e}")


def writer_task(
    queue: mp.Queue, db_path: str, stop_event: mp.Event, progress_queue: mp.Queue
):
    """Writer: writes results to database and reports progress"""
    print("💾 Writer started...")
    setup_target_db(db_path)
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    c = conn.cursor()

    buffer = []
    discards_buffer = []
    total_written = 0
    last_flush_time = time.time()
    FLUSH_TIMEOUT = 30

    def flush():
        nonlocal buffer, discards_buffer, total_written, last_flush_time
        last_flush_time = time.time()
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
            if discards_buffer:
                c.executemany(
                    "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                    discards_buffer,
                )
            conn.commit()
            flushed = len(buffer)
            total_written += flushed
            buffer.clear()
            discards_buffer.clear()
            return flushed
        except Exception as e:
            print(f"❌ Writer Flush Error: {e}")
            conn.rollback()
            return 0

    while not stop_event.is_set() or not queue.empty():
        try:
            result = queue.get(timeout=1)
        except Empty:
            # Timeout occurred - check if we should flush based on time
            current_time = time.time()
            if (buffer or discards_buffer) and (
                current_time - last_flush_time
            ) >= FLUSH_TIMEOUT:
                flushed = flush()
                if flushed > 0:
                    progress_queue.put(("writer_progress", flushed))
            continue

        try:
            if not isinstance(result, tuple) or len(result) != 5:
                print(f"❌ Invalid result format: expected 5-tuple, got {type(result)}")
                continue

            url, matches, cik, year, discards = result
            buffer.append((url, matches, cik, year))

            if discards:
                try:
                    discards_buffer.extend(discards)
                except TypeError as e:
                    print(f"❌ Error extending discards buffer: {e}")

            # Flush on BATCH_SIZE
            if len(buffer) >= BATCH_SIZE or len(discards_buffer) >= BATCH_SIZE:
                flushed = flush()
                if flushed > 0:
                    progress_queue.put(("writer_progress", flushed))

        except Exception as e:
            print(f"❌ Unexpected error in writer_task: {e}")
            continue

    # Final flush on shutdown
    if buffer or discards_buffer:
        flushed = flush()
        if flushed > 0:
            progress_queue.put(("writer_progress", flushed))

    conn.close()
    print(f"💾 Writer finished. Total saved: {total_written:,}")
    progress_queue.put(("writer_done", None))


# =============================================================================
# DATABASE HELPERS
# =============================================================================


def setup_target_db(path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, matches TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES webpage_result(url))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS discarded_sentences (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, sentence TEXT, discard_reason TEXT)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
    conn.commit()
    conn.close()


def get_processed_urls(path):
    if not Path(path).exists():
        return set()
    conn = sqlite3.connect(path)
    c = conn.cursor()
    try:
        c.execute("SELECT url FROM webpage_result")
        return {row[0] for row in c.fetchall()}
    except:
        return set()


def get_total_count(path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM webpage_result WHERE matches IS NOT NULL")
    count = c.fetchone()[0]
    conn.close()
    return count


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print(f"🚀 Starting Merged Pre-Filter ({NUM_WORKERS} workers)")
    processed_urls = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed_urls)} already processed URLs")

    total_items = get_total_count(SOURCE_DB_PATH)
    remaining_items = total_items - len(processed_urls)
    print(f"📦 Total in source: {total_items:,} | Remaining: {remaining_items:,}")

    if remaining_items == 0:
        print("✅ All documents already processed!")
        exit(0)

    task_queue = mp.Queue(maxsize=QUEUE_SIZE)
    result_queue = mp.Queue(maxsize=QUEUE_SIZE)
    progress_queue = mp.Queue()
    stop_event = mp.Event()

    writer_p = mp.Process(
        target=writer_task,
        args=(result_queue, TARGET_DB_PATH, stop_event, progress_queue),
    )
    writer_p.start()

    workers = [
        mp.Process(
            target=worker_task, args=(task_queue, result_queue, progress_queue, i)
        )
        for i in range(NUM_WORKERS)
    ]
    for p in workers:
        p.start()

    producer_p = mp.Process(
        target=producer_task,
        args=(
            task_queue,
            SOURCE_DB_PATH,
            TARGET_DB_PATH,
            processed_urls,
            progress_queue,
        ),
    )
    producer_p.start()

    try:
        with tqdm(
            total=remaining_items, unit="docs", smoothing=0.1, desc="Processing"
        ) as pbar:
            producer_done = False
            writer_done = False

            while not (producer_done and writer_done):
                try:
                    msg_type, msg_data = progress_queue.get(timeout=2)

                    if msg_type == "worker_progress":
                        pbar.update(msg_data)
                    elif msg_type == "writer_progress":
                        pbar.update(msg_data)
                    elif msg_type == "producer_progress":
                        pbar.update(msg_data)
                    elif msg_type == "producer_done":
                        producer_done = True
                    elif msg_type == "writer_done":
                        writer_done = True
                except:
                    # Timeout - just continue
                    pass

            print("✅ Producer finished. Waiting for workers...")

            # Send sentinel values to stop workers
            for _ in range(NUM_WORKERS):
                try:
                    task_queue.put(None)
                except:
                    pass

            # Join all workers
            for p in workers:
                p.join(timeout=10)
                if p.is_alive():
                    p.terminate()

            # Signal writer to stop and wait
            stop_event.set()
            writer_p.join(timeout=10)
            if writer_p.is_alive():
                writer_p.terminate()
                writer_p.join()

            print("✅ Complete.")

    except KeyboardInterrupt:
        print("\n⚠️ Stopping...")
        stop_event.set()
        producer_p.terminate()
        for p in workers:
            p.terminate()
        writer_p.terminate()

    producer_p.join()
    for p in workers:
        p.join()
    writer_p.join()
    print("✅ Complete.")
