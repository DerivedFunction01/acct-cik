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
BATCH_SIZE = 1000
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
    EXCLUDE_REGULATION_REGEX,
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
)

# We need the processor to validate tables
try:
    from table_processor import TableToTextConverter
except ImportError:
    print(
        "⚠️ Warning: Could not import TableToTextConverter. Table validation will default to True."
    )
    TableToTextConverter = None

# =============================================================================
# SOPHISTICATED CONTEXT DEFINITIONS
# =============================================================================

# 1. Target Instruments (The "What")
SOPHISTICATED_TARGETS = re.compile(
    r"\b(?:convertibles?|warrants?|conversion)\b", re.IGNORECASE
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

# =============================================================================
# TABLE CLEANUP HELPERS
# =============================================================================

FOOTNOTE_PATTERN = re.compile(r"<FN>(.*?)</FN>\s*</TABLE>", re.DOTALL | re.IGNORECASE)
INDIVIDUAL_FOOTNOTE_PATTERN = re.compile(
    r"<F\s+(\d+)>\s*(.*?)(?=<F\s+\d+>|$)", re.DOTALL
)
TAG_PATTERN = re.compile(r"<[^>]+>")


def check_hard_exclusions(text: str) -> Optional[str]:
    if EXCLUDE_REGEX_LEGAL_LITIGATION.search(text):
        return "legal_litigation"
    if EXCLUDE_REGEX_FORWARD_LOOKING.search(text):
        return "forward_looking"
    if EXCLUDE_COMPETITOR_REGEX.search(text):
        return "competitor_analysis"
    if EXCLUDE_REGULATION_REGEX.search(text):
        return "regulatory_boilerplate"
    if EXCLUDE_PLAN_ASSETS_REGEX.search(text):
        return "pension_plan_assets"
    if EXCLUDE_REGEX_FILING.search(text):
        return "filing"
    # is_contractual_noise is run later or separately depending on logic,
    # but here we include it as a hard exclusion check.
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
    context_str = " ".join(footnotes) + " Notional"
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
    """
    if not sophisticated_buffer:
        return False

    # 1. Check for Free Pass (Strict Anchor in standard text)
    for p in clean_paragraphs:
        if EQ_REGEX.search(p) and SOPHISTICATED_TARGETS.search(p):
            return True
        if find_hedging_context(p) and SOPHISTICATED_TARGETS.search(p):
            return True

    # 2. Check for Internal Sophisticated Context
    # Since we now append paragraphs with Context to the buffer, this will succeed
    # if any paragraph in the buffer has the required keywords.
    combined_text = " ".join(sophisticated_buffer)
    if SOPHISTICATED_CONTEXT_REGEX.search(combined_text):
        return True

    return False


def process_item(item: Tuple) -> Optional[Tuple]:
    try:
        url, matches_json, cik, year = item
    except (ValueError, TypeError) as e:
        print(f"❌ Error unpacking item: {e}")
        print(f"   Item: {item}")
        return None

    try:
        paragraphs = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"❌ Error parsing JSON for {url}: {e}")
        return None

    # BUFFER STRUCTURE: List of (index, text) tuples
    clean_buffer = []  # Standard Buffer
    sophisticated_buffer = []  # Warrant/Convertible Buffer
    local_discards = []

    for idx, p in enumerate(paragraphs):
        try:
            # Accounting Standards (runs first to avoid subbing FASB with an entity token)
            if ACCOUNTING_STANDARDS_STRICT_REGEX.search(p):
                kept = []
                sentences = SENTENCE_SPLIT_PATTERN.split(p)
                for sent in sentences:
                    if not ACCOUNTING_STANDARDS_STRICT_REGEX.search(sent):
                        kept.append(sent)
                    else:  # Discard the remaining text
                        break
                if kept:
                    salvaged_p = " ".join(kept)
                    if SOPHISTICATED_TARGETS.search(
                        salvaged_p
                    ) or SOPHISTICATED_CONTEXT_REGEX.search(salvaged_p):
                        sophisticated_buffer.append(salvaged_p)
                    else:
                        clean_buffer.append((idx, salvaged_p))

                discarded_text = " ".join(set(sentences) - set(kept))
                if discarded_text:
                    local_discards.append((url, discarded_text, "accounting_standards"))
                continue

            # 1. TABLE HANDLING
            if "<TABLE>" in p.upper():
                try:
                    cleaned_table, footnotes = extract_and_separate_footnotes(p)
                except Exception as e:
                    print(f"⚠️ Error extracting footnotes from table in {url}: {e}")
                    local_discards.append(
                        (url, p[:100], "table_footnote_extraction_failed")
                    )
                    continue

                try:
                    is_container = is_text_container_table(cleaned_table, footnotes)
                except Exception as e:
                    print(f"⚠️ Error validating table in {url}: {e}")
                    is_container = True  # Default to treating as container on error

                if not is_container:
                    if EXCLUDE_REGEX_LEGAL_LITIGATION.search(cleaned_table):
                        local_discards.append((url, "<table>...", "legal_table"))
                        continue

                    # Check where to send this table
                    is_target = SOPHISTICATED_TARGETS.search(cleaned_table)
                    is_context = SOPHISTICATED_CONTEXT_REGEX.search(cleaned_table)

                    if is_target or is_context:
                        sophisticated_buffer.append((idx, cleaned_table))
                        clean_buffer.append((idx, cleaned_table))
                    else:
                        clean_buffer.append((idx, cleaned_table))

                    if footnotes:
                        clean_buffer.extend([(idx, fn) for fn in footnotes])
                    continue
                else:
                    try:
                        p, excluded_rows = strip_table_formatting(cleaned_table, url)
                        local_discards.extend(excluded_rows)
                    except Exception as e:
                        print(f"⚠️ Error stripping table formatting in {url}: {e}")
                        local_discards.append(
                            (url, p[:100], "table_formatting_strip_failed")
                        )
                        continue

                    if footnotes:
                        p += " " + " ".join(footnotes)
                    if not p.strip():
                        continue

            try:
                p = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, p)
            except Exception as e:
                print(f"⚠️ Error applying entity exclusion regex in {url}: {e}")
                # Continue without this substitution

            # 2. EXCLUSIONS
            exclusion_reason = check_hard_exclusions(p)
            if exclusion_reason:
                local_discards.append((url, p, exclusion_reason))
                continue

            # 3. SALVAGE LOGIC
            # Hypothetical
            if EXCLUDE_HYPOTHETICAL_REGEX.search(p):
                has_std = STRICT_REGEX.search(p) or (
                    SOFT_REGEX.search(p) and HEDGING_CONTEXT_REGEX.search(p)
                )
                has_soph = SOPHISTICATED_TARGETS.search(
                    p
                ) or SOPHISTICATED_CONTEXT_REGEX.search(p)

                if has_std or has_soph:
                    # Flow through to distribution
                    pass
                else:
                    local_discards.append(
                        (url, p, "hypothetical_sensitivity_methodology")
                    )
                    continue

            # Equity Comp (Logic modified to populate buffers)
            if EXCLUDE_REGEX_EQUITY_COMP.search(p):
                try:
                    kept = []
                    sentences = SENTENCE_SPLIT_PATTERN.split(p)
                    for sent in sentences:
                        if EQ_REGEX.search(sent):
                            kept.append(sent)
                        elif EQ_SOFT_REGEX.search(sent):
                            # Standard Context
                            has_hedging_context = SOFT_GEN_REGEX.search(
                                sent
                            ) or DER_STD_REGEX.search(sent)
                            # Sophisticated Targets (Buffer even without context)
                            is_buffered_target = SOPHISTICATED_TARGETS.search(sent)
                            # Sophisticated Context (New Trigger)
                            is_soph_context = SOPHISTICATED_CONTEXT_REGEX.search(sent)

                            if (
                                has_hedging_context
                                or is_buffered_target
                                or is_soph_context
                            ):
                                kept.append(sent)

                    if kept:
                        salvaged_p = " ".join(kept)
                        # Distribution
                        if SOPHISTICATED_TARGETS.search(
                            salvaged_p
                        ) or SOPHISTICATED_CONTEXT_REGEX.search(salvaged_p):
                            sophisticated_buffer.append((idx, salvaged_p))
                        else:
                            clean_buffer.append((idx, salvaged_p))

                    discarded_text = " ".join(set(sentences) - set(kept))
                    if discarded_text:
                        local_discards.append((url, discarded_text, "comp"))
                except Exception as e:
                    print(f"⚠️ Error in equity comp salvage logic for {url}: {e}")
                    local_discards.append((url, p[:100], "equity_comp_salvage_failed"))
                continue

            # 4. DISTRIBUTION (Standard vs. Sophisticated)
            is_soph_target = SOPHISTICATED_TARGETS.search(p)
            is_soph_context = SOPHISTICATED_CONTEXT_REGEX.search(p)

            if is_soph_target:
                # A. TARGETS: Exclusive to Sophisticated Buffer
                sophisticated_buffer.append((idx, p))

            elif is_soph_context:
                # B. CONTEXT: Shared to BOTH Buffers
                sophisticated_buffer.append((idx, p))
                clean_buffer.append((idx, p))
            else:
                # C. STANDARD: Exclusive to Standard Buffer
                clean_buffer.append((idx, p))

        except Exception as e:
            print(f"❌ Unexpected error processing paragraph {idx} in {url}: {e}")
            local_discards.append(
                (url, str(p)[:100], f"processing_error_{type(e).__name__}")
            )
            continue

    # 5. FINAL GATEKEEPERS
    final_results = []  # List of (index, text)

    try:
        # A. Validate Standard Buffer
        # Extract text only for validation
        std_texts = [text for _, text in clean_buffer]
        if any(find_hedging_context(p) for p in std_texts):
            final_results.extend(clean_buffer)
        else:
            if clean_buffer:
                discarded = "\n\n".join(std_texts)
                local_discards.append((url, discarded, "standard_check_failed"))
    except Exception as e:
        print(f"⚠️ Error validating standard buffer for {url}: {e}")

    try:
        # B. Validate Sophisticated Buffer
        # Extract text only for validation
        soph_texts = [text for _, text in sophisticated_buffer]
        # Pass text lists to validator
        if validate_sophisticated_buffer(soph_texts, std_texts):
            final_results.extend(sophisticated_buffer)
        else:
            if sophisticated_buffer:
                discarded = "\n\n".join(soph_texts)
                local_discards.append((url, discarded, "sophisticated_check_failed"))
    except Exception as e:
        print(f"⚠️ Error validating sophisticated buffer for {url}: {e}")

    # C. RECONSTRUCT & SORT
    try:
        if final_results:
            # Sort by original index to restore narrative flow
            final_results.sort(key=lambda x: x[0])

            # Extract text and deduplicate (preserving order)
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

    return (url, "[]", cik, year, aggregate_discards(local_discards))


# =============================================================================
# QUEUE PROCESSES (Unchanged)
# =============================================================================
# ... (producer_task, worker_task, writer_task, setup_target_db, etc.) ...
def producer_task(queue: mp.Queue, db_path: str, processed_urls: Set[str]):
    print("🔌 Producer started...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "SELECT w.url, w.matches, r.cik, r.year FROM webpage_result w LEFT JOIN report_data r ON w.url = r.url WHERE w.matches IS NOT NULL"
    )

    count = 0
    skipped = 0
    while True:
        rows = c.fetchmany(1000)
        if not rows:
            break
        for row in rows:
            if row[0] in processed_urls:
                skipped += 1
                continue
            queue.put(row)
            count += 1

    conn.close()
    print(f"🔌 Producer finished. Queued {count:,} items (Skipped {skipped:,}).")


def worker_task(in_queue: mp.Queue, out_queue: mp.Queue):
    while True:
        item = in_queue.get()
        if item is None:
            break
        try:
            result = process_item(item)
            if result:
                out_queue.put(result)
        except Exception as e:
            print(f"⚠️ Worker error: {e}")


def writer_task(queue: mp.Queue, db_path: str, stop_event: mp.Event, counter: mp.Value):
    print("💾 Writer started...")
    setup_target_db(db_path)
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    c = conn.cursor()

    buffer = []
    discards_buffer = []
    total_written = 0

    def flush():
        nonlocal buffer, discards_buffer, total_written
        if not buffer and not discards_buffer:
            return
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
            with counter.get_lock():
                counter.value += len(buffer)
            total_written += len(buffer)
            buffer.clear()
            discards_buffer.clear()
        except Exception as e:
            print(f"❌ Writer Flush Error: {e}")
            conn.rollback()

    while not stop_event.is_set() or not queue.empty():
        try:
            result = queue.get(timeout=1)
        except Empty:
            continue

        try:
            # Unpack result with explicit error handling
            if not isinstance(result, tuple) or len(result) != 5:
                print(
                    f"❌ Invalid result format: expected 5-tuple, got {type(result)} with length {len(result) if isinstance(result, tuple) else 'N/A'}"
                )
                print(f"   Result: {result}")
                continue

            url, matches, cik, year, discards = result
            buffer.append((url, matches, cik, year))

            if discards:
                try:
                    discards_buffer.extend(discards)
                except TypeError as e:
                    print(f"❌ Error extending discards buffer: {e}")
                    print(f"   Discards type: {type(discards)}, value: {discards}")

            if len(buffer) >= BATCH_SIZE:
                flush()

        except (ValueError, TypeError) as e:
            print(f"❌ Error unpacking result in writer_task: {e}")
            print(f"   Result: {result}")
            continue
        except Exception as e:
            print(f"❌ Unexpected error in writer_task: {e}")
            continue

    flush()
    conn.close()
    print(f"💾 Writer finished. Total saved: {total_written:,}")


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


if __name__ == "__main__":
    print(f"🚀 Starting Merged Pre-Filter ({NUM_WORKERS} workers)")
    processed_urls = get_processed_urls(TARGET_DB_PATH)
    total_items = get_total_count(SOURCE_DB_PATH)

    task_queue = mp.Queue(maxsize=QUEUE_SIZE)
    result_queue = mp.Queue(maxsize=QUEUE_SIZE)
    stop_event = mp.Event()
    processed_counter = mp.Value("i", len(processed_urls))

    writer_p = mp.Process(
        target=writer_task,
        args=(result_queue, TARGET_DB_PATH, stop_event, processed_counter),
    )
    writer_p.start()

    workers = [
        mp.Process(target=worker_task, args=(task_queue, result_queue))
        for _ in range(NUM_WORKERS)
    ]
    for p in workers:
        p.start()

    producer_p = mp.Process(
        target=producer_task, args=(task_queue, SOURCE_DB_PATH, processed_urls)
    )
    producer_p.start()

    try:
        with tqdm(
            total=total_items, initial=len(processed_urls), unit="docs", smoothing=0.1
        ) as pbar:
            while True:
                time.sleep(1)
                pbar.n = processed_counter.value
                pbar.refresh()
                if (
                    not producer_p.is_alive()
                    and task_queue.empty()
                    and not any(p.is_alive() for p in workers)
                    and result_queue.empty()
                ):
                    break
    except KeyboardInterrupt:
        print("\n⚠️ Stopping...")

    for _ in range(NUM_WORKERS):
        try:
            task_queue.put_nowait(None)
        except:
            pass
    producer_p.join()
    for p in workers:
        p.join()
    stop_event.set()
    writer_p.join()
    print("✅ Complete.")
