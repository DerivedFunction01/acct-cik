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
    aggregate_discards,
    is_contractual_noise,
)

def check_hard_exclusions(text: str) -> Optional[str]:
    """
    Checks text against 'Dead Weight' filters.
    Returns the discard reason string if matched, otherwise None.
    """
    # 1. Litigation / Legal (Highest Priority)
    if EXCLUDE_REGEX_LEGAL_LITIGATION.search(text):
        return "legal_litigation"

    # 2. Forward Looking Statements
    if EXCLUDE_REGEX_FORWARD_LOOKING.search(text):
        return "forward_looking"

    # 3. Competitors / Peers
    if EXCLUDE_COMPETITOR_REGEX.search(text):
        return "competitor_analysis"

    # 4. Regulatory Boilerplate
    if EXCLUDE_REGULATION_REGEX.search(text):
        return "regulatory_boilerplate"

    # 5. Plan Assets / Pensions
    if EXCLUDE_PLAN_ASSETS_REGEX.search(text):
        return "pension_plan_assets"

    # 6. Filing Meta-text
    if EXCLUDE_REGEX_FILING.search(text):
        return "filing"

    # 7. Contractual Noise (Glossary/Definitions)
    if is_contractual_noise(text):
        return "contractual_noise"

    return None


# We need the processor to validate tables
from table_processor import TableToTextConverter

# =============================================================================
# TABLE CLEANUP HELPERS (Integrated)
# =============================================================================

FOOTNOTE_PATTERN = re.compile(r"<FN>(.*?)</FN>\s*</TABLE>", re.DOTALL | re.IGNORECASE)
INDIVIDUAL_FOOTNOTE_PATTERN = re.compile(
    r"<F\s+(\d+)>\s*(.*?)(?=<F\s+\d+>|$)", re.DOTALL
)
TAG_PATTERN = re.compile(r"<[^>]+>")
WARRANT_CATCHER = re.compile(r"\bwarrants?\b", re.IGNORECASE)


def extract_and_separate_footnotes(table_text: str) -> Tuple[str, List[str]]:
    """Extract footnotes from a table and return cleaned table + footnotes list."""
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


def strip_table_formatting(table_text: str) -> Tuple[str, List[Tuple[str, str, str]]]:
    """
    1. Removes HTML tags.
    2. Filters out 'Poison Rows' using shared exclusion logic.
    3. Merges surviving rows into a single text block.
    4. Returns cleaned text AND list of (row_text, discard_reason) tuples for excluded rows.
    """
    # Remove all HTML-style tags
    text = TAG_PATTERN.sub("", table_text)

    lines = text.split("\n")
    cleaned_lines = []
    excluded_rows = []

    for line in lines:
        stripped = line.strip()

        # Skip empty/separator lines
        if not stripped or all(c in "-\t " for c in stripped):
            continue

        # FILTER POISON ROWS
        exclusion_reason = check_hard_exclusions(stripped)
        if exclusion_reason:
            excluded_rows.append((stripped, exclusion_reason))
            continue

        cleaned_lines.append(stripped)

    # Merge
    result = " ".join(cleaned_lines)
    result = re.sub(r"\s+", " ", result).strip()

    return result, excluded_rows


def is_text_container_table(table_text: str, footnotes: List[str]) -> bool:
    """
    Returns True if table is just text (should be flattened).
    Returns False if table is valid numeric data (should be kept as table).
    """
    if not TableToTextConverter:
        return True

    # Inject 'Notional' to force High Recall on Soft Matches (e.g. Gold Contracts)
    context_str = " ".join(footnotes) + " Notional"

    try:
        converter = TableToTextConverter(
            table_text, narrative_context=context_str, is_sophisticated=True
        )
        sentences = converter.process()
        return len(sentences) == 0  # No sentences = Garbage/Text -> True
    except Exception:
        return True  # On error, treat as text container


# =============================================================================
# WORKER LOGIC
# =============================================================================


def find_hedging_context(paragraph: str) -> bool:
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
    # Tables are self-validating if they survived the TableToText check
    if "<TABLE>" in paragraph.upper() and TABLE_REGEX.search(paragraph):
        return True

    return False

def process_item(item: Tuple) -> Optional[Tuple]:
    url, matches_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    clean_paragraphs = []
    local_discards = []

    for p in paragraphs:

        # 1. INTELLIGENT TABLE HANDLING
        if "<TABLE>" in p.upper():
            # A. Extract components
            cleaned_table, footnotes = extract_and_separate_footnotes(p)

            # B. Validate Structure
            is_container = is_text_container_table(cleaned_table, footnotes)

            if not is_container:
                # --- VALID TABLE PATH ---
                # It contains numbers/derivatives. Keep it structure.

                # Check for Hard Legal Exclusions inside the table text
                if EXCLUDE_REGEX_LEGAL_LITIGATION.search(cleaned_table):
                    local_discards.append((url, "<table>...", "legal_table"))
                    continue

                # Append Table
                clean_paragraphs.append(cleaned_table)
                # Append Footnotes as text (processed in next loop? No, footnotes are text)
                # We add footnotes to the output immediately
                if footnotes:
                    clean_paragraphs.extend(footnotes)

                continue  # Done with this paragraph
            else:
                # --- FLATTEN PATH ---
                # It is a text container. Flatten it to a string.
                # It will now fall through to the Standard Text Filters below.
                p, excluded_rows = strip_table_formatting(cleaned_table)

                # LOG EXCLUDED ROWS (already in (url, row_text, reason) format)
                local_discards.extend(excluded_rows)

                # Append footnotes to the flattened text so they get checked together
                if footnotes:
                    p += " " + " ".join(footnotes)

                # If empty after flattening, skip
                if not p.strip():
                    continue

        # 0. Clean Entities First
        p = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, p)

        # 2. EXCLUSION FILTERS (Applies to Text AND Flattened Tables)
        exclusion_reason = check_hard_exclusions(p)
        if exclusion_reason:
            local_discards.append((url, p, exclusion_reason))
            continue
        # 3. SALVAGE LOGIC
        # Hypothetical
        if EXCLUDE_HYPOTHETICAL_REGEX.search(p):
            if STRICT_REGEX.search(p) or (
                SOFT_REGEX.search(p) and HEDGING_CONTEXT_REGEX.search(p)
            ):
                clean_paragraphs.append(p)
                continue
            else:
                local_discards.append((url, p, "hypothetical_sensitivity_methodology"))
                continue

        # Equity Comp
        if EXCLUDE_REGEX_EQUITY_COMP.search(p):
            kept = []
            sentences = SENTENCE_SPLIT_PATTERN.split(p)
            for sent in sentences:
                if EQ_REGEX.search(sent):
                    kept.append(sent)
                elif EQ_SOFT_REGEX.search(sent):
                    has_hedging_context = SOFT_GEN_REGEX.search(
                        sent
                    ) or DER_STD_REGEX.search(sent)
                    if has_hedging_context:
                        kept.append(sent)

            if kept:
                clean_paragraphs.append(" ".join(kept))

            discarded_text = " ".join(set(sentences) - set(kept))
            if discarded_text:
                local_discards.append((url, discarded_text, "comp"))
            continue

        # Accounting Standards
        if ACCOUNTING_STANDARDS_STRICT_REGEX.search(p):
            kept = []
            sentences = SENTENCE_SPLIT_PATTERN.split(p)
            for sent in sentences:
                if not ACCOUNTING_STANDARDS_STRICT_REGEX.search(sent):
                    kept.append(sent)

            if kept:
                clean_paragraphs.append(" ".join(kept))

            discarded_text = " ".join(set(sentences) - set(kept))
            if discarded_text:
                local_discards.append((url, discarded_text, "accounting_standards"))
            continue

        # 4. KEEP SURVIVOR
        clean_paragraphs.append(p)

    # 5. FINAL GATEKEEPER
    if clean_paragraphs:
        should_keep = any(find_hedging_context(p) for p in clean_paragraphs)
        if not should_keep:
            local_discards.append(
                (url, "\n\n".join(clean_paragraphs), "no_hedging_context")
            )
            return None

        return (
            url,
            json.dumps(clean_paragraphs),
            cik,
            year,
            aggregate_discards(local_discards),
        )

    # Save empty to mark progress
    return (url, "[]", cik, year, aggregate_discards(local_discards))


# =============================================================================
# QUEUE PROCESSES
# =============================================================================


def producer_task(queue: mp.Queue, db_path: str, processed_urls: Set[str]):
    print("🔌 Producer started...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Fetch all, filtering happens in loop
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


def writer_task(queue: mp.Queue, db_path: str, stop_event: mp.Event, counter: mp.Value): # type: ignore
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
            print(f"❌ Writer Error: {e}")
            conn.rollback()

    while not stop_event.is_set() or not queue.empty():
        try:
            result = queue.get(timeout=1)
            # Always append (even empty []) to ensure resume works
            buffer.append((result[0], result[1], result[2], result[3]))
            if result[4]:
                discards_buffer.extend(result[4])
            if len(buffer) >= BATCH_SIZE:
                flush()
        except Empty:
            continue

    flush()
    conn.close()
    print(f"💾 Writer finished. Total saved: {total_written:,}")


# =============================================================================
# SETUP & MAIN
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
