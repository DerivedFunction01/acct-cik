import sqlite3
import json
import multiprocessing as mp
import time
from pathlib import Path
from queue import Empty
import logging
from typing import Optional, Tuple, Set

from tqdm import tqdm

logging.basicConfig(level=logging.INFO)

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000  # Transaction size for writer
QUEUE_SIZE = NUM_WORKERS * 50  # Buffer size to keep memory stable
SOURCE_DB_PATH = "web_data.db"
TARGET_DB_PATH = "prefiltered_data.db"

# Import exclusions
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
    aggregate_discards,
    is_contractual_noise,
)

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
    elif "warrants" in paragraph.lower() and HEDGING_CONTEXT_REGEX.search(paragraph): # soft regex does not have warrantss
        return True
    return False


def process_item(item: Tuple) -> Optional[Tuple]:
    # Unpack based on query: url, matches, cik, year
    url, matches_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    clean_paragraphs = []
    local_discards = []

    for p in paragraphs:
        # 0. Clean Entities First
        p = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, p)

        # 1. Skip Tables (Pass-through for later processing)
        if "<TABLE>" in p.upper():
            clean_paragraphs.append(p)
            continue

        # 2. Exclusion Filters
        if EXCLUDE_REGEX_LEGAL_LITIGATION.search(p):
            local_discards.append((url, p, "legal_litigation"))
            continue

        if EXCLUDE_REGEX_FORWARD_LOOKING.search(p):
            local_discards.append((url, p, "forward_looking"))
            continue

        if EXCLUDE_COMPETITOR_REGEX.search(p):
            local_discards.append((url, p, "competitor_analysis"))
            continue

        if EXCLUDE_REGULATION_REGEX.search(p):
            local_discards.append((url, p, "regulatory_boilerplate"))
            continue

        if EXCLUDE_PLAN_ASSETS_REGEX.search(p):
            local_discards.append((url, p, "pension_plan_assets"))
            continue

        if EXCLUDE_REGEX_FILING.search(p):
            local_discards.append((url, p, "filing"))
            continue
        # Do not want to have later stages try to salvage contractual noise
        if is_contractual_noise(p):
            local_discards.append((url, p, "contractual_noise"))
            continue

        # Hypothetical: Salvage Logic
        if EXCLUDE_HYPOTHETICAL_REGEX.search(p):
            # If explicit instrument OR soft+context found, keep it.
            if STRICT_REGEX.search(p) or (
                SOFT_REGEX.search(p) and HEDGING_CONTEXT_REGEX.search(p)
            ):
                clean_paragraphs.append(p)
                continue
            else:
                local_discards.append((url, p, "hypothetical_sensitivity_methodology"))
                continue

        # Equity Comp: Salvage Logic
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

            # Reconstruct
            if kept:
                clean_paragraphs.append(" ".join(kept))

            # Log discard (approximate)
            discarded_text = " ".join(set(sentences) - set(kept))
            if discarded_text:
                local_discards.append((url, discarded_text, "comp"))
            continue

        # Accounting Standards: Salvage Logic
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


        # 3. Keep Survivor
        clean_paragraphs.append(p)

    # 4. Final Gatekeeper (Hedging Context)
    if clean_paragraphs:
        # Check if *any* remaining paragraph has context
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
    elif local_discards:
        # Log purely discarded items
        return (url, "[]", cik, year, aggregate_discards(local_discards))

    return None


# =============================================================================
# QUEUE PROCESSES
# =============================================================================


def producer_task(queue: mp.Queue, db_path: str, processed_urls: Set[str]):
    """Reads raw data and feeds the queue, skipping already processed URLs."""
    print("🔌 Producer started...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Note: We fetch everything valid from source, filtering is done in Python
    # (faster than attaching DBs for this use case usually)
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
            url = row[0]
            if url in processed_urls:
                skipped += 1
                continue

            queue.put(row)
            count += 1

    conn.close()
    print(
        f"🔌 Producer finished. Queued {count:,} items (Skipped {skipped:,} already done)."
    )


def worker_task(in_queue: mp.Queue, out_queue: mp.Queue):
    """Consumes raw items, processes them, sends to writer."""
    while True:
        item = in_queue.get()
        if item is None:  # Sentinel
            break

        try:
            result = process_item(item)
            if result:
                out_queue.put(result)
        except Exception as e:
            print(f"⚠️ Worker error: {e}")


def setup_target_db(path):
    """Creates the DB if it doesn't exist, ensures schema if it does."""
    conn = sqlite3.connect(path)
    c = conn.cursor()
    # Using IF NOT EXISTS preserves data if the file is already there
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


def get_processed_urls(target_db_path: str) -> Set[str]:
    """Retrieves set of URLs that have already been processed into the target DB."""
    if not Path(target_db_path).exists():
        return set()

    print("🔍 Checking for existing progress...")
    try:
        conn = sqlite3.connect(target_db_path)
        c = conn.cursor()
        # We need to check both successes and failures/empty results to avoid re-processing
        # Assuming webpage_result stores both valid matches and empty lists "[]"
        c.execute("SELECT url FROM webpage_result")
        urls = {row[0] for row in c.fetchall()}
        conn.close()
        return urls
    except sqlite3.OperationalError:
        # Table might not exist yet
        return set()


# =============================================================================
# MAIN
# =============================================================================
def get_total_count(db_path):
    """Counts valid rows in source DB for progress bar."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM webpage_result WHERE matches IS NOT NULL")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def writer_task(queue: mp.Queue, db_path: str, stop_event: mp.Event, counter: mp.Value):
    """Batches writes to the database and updates shared progress counter."""
    print("💾 Writer started...")
    # Ensure schema exists (safe to call multiple times)
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

            # UPDATE PROGRESS
            # Note: We update based on buffer size, which corresponds to successful processing
            # But the progress bar tracks Total Input Items.
            # To sync correctly, the writer should arguably not control the main progress bar
            # if we want to track items *processed* (including filtered/skipped).
            # However, for a simple resume, updating here is fine as long as we add the initial offset.
            batch_len = len(buffer)
            with counter.get_lock():
                counter.value += batch_len

            total_written += batch_len
            buffer.clear()
            discards_buffer.clear()
        except Exception as e:
            print(f"❌ Writer Error: {e}")
            conn.rollback()

    while not stop_event.is_set() or not queue.empty():
        try:
            result = queue.get(timeout=1)

            # unpack
            url, clean_json, cik, year, discards = result

            if clean_json != "[]":
                buffer.append((url, clean_json, cik, year))

            if discards:
                discards_buffer.extend(discards)

            if len(buffer) >= BATCH_SIZE or len(discards_buffer) >= BATCH_SIZE * 5:
                flush()

        except Empty:
            continue

    # Final flush
    flush()
    conn.close()
    print(f"💾 Writer finished. Total saved: {total_written:,}")


if __name__ == "__main__":
    print(f"🚀 Starting Multi-Process Pre-Filter ({NUM_WORKERS} workers)")

    # 0. Check for Resume
    processed_urls = get_processed_urls(TARGET_DB_PATH)
    processed_count = len(processed_urls)

    # 1. Get Total for Progress Bar
    total_items = get_total_count(SOURCE_DB_PATH)
    remaining_items = total_items - processed_count

    print(f"📊 Total items: {total_items:,}")
    print(f"♻️  Already done: {processed_count:,}")
    print(f"⏳ Remaining:    {remaining_items:,}")

    # 2. Queues & Shared Counter
    task_queue = mp.Queue(maxsize=QUEUE_SIZE)
    result_queue = mp.Queue(maxsize=QUEUE_SIZE)
    stop_event = mp.Event()

    # Initialize counter with what we already have
    processed_counter = mp.Value("i", processed_count)

    # 3. Start Writer
    writer_p = mp.Process(
        target=writer_task,
        args=(result_queue, TARGET_DB_PATH, stop_event, processed_counter),
    )
    writer_p.start()

    # 4. Start Workers
    workers = []
    for _ in range(NUM_WORKERS):
        p = mp.Process(target=worker_task, args=(task_queue, result_queue))
        p.start()
        workers.append(p)

    # 5. Start Producer (Passing the processed set to skip them)
    producer_p = mp.Process(
        target=producer_task, args=(task_queue, SOURCE_DB_PATH, processed_urls)
    )
    producer_p.start()

    # 6. Monitoring Loop
    try:
        # Initialize tqdm with total and initial value
        with tqdm(
            total=total_items, initial=processed_count, unit="docs", smoothing=0.1
        ) as pbar:
            while True:
                time.sleep(1)

                # Update Progress
                current = processed_counter.value
                pbar.n = current
                pbar.refresh()

                # Visual Indicators for Queues
                try:
                    in_q = task_queue.qsize()
                    out_q = result_queue.qsize()
                except NotImplementedError:
                    in_q = "N/A"
                    out_q = "N/A"

                pbar.set_postfix(in_queue=f"{in_q}/{QUEUE_SIZE}", out_queue=f"{out_q}")

                # Exit Condition
                # We are done when the producer finishes AND workers finish AND queues empty
                if (
                    not producer_p.is_alive()
                    and task_queue.empty()
                    and not any(p.is_alive() for p in workers)
                    and result_queue.empty()
                ):
                    break

                # Alternate exit: if we reached total count (sometimes unreliable if discards happen silently)
                # Ideally rely on process liveness check above

    except KeyboardInterrupt:
        print("\n⚠️ Stopping...")

    # 7. Shutdown
    print("Shutting down workers...")
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

    print("✅ Processing Complete.")
