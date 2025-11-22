# DATABASE NOISE REDUCTION SCRIPT WITH CATEGORY CLASSIFICATION
# =============================================================================
# Filters derivative database using smart regex patterns and classifies by type
# Creates unified clean_web_data.db with keyword matches for MNLI comparison
# Uses ProcessPoolExecutor + buffered batch writes for optimal performance
# =============================================================================
# %%
import sqlite3
import json
import re
from pathlib import Path
from tqdm import tqdm
from typing import List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time

# Import all derivative regexes
try:
    from derivative_regex import (
        ALL_REGEX,
        SENTENCE_SPLIT_PATTERN,
        MIN_SENTENCE_LENGTH,
        TRADING_STATEMENTS_REGEX,
        CATEOGRY_REGEX,
        cleanup_fragment,
    )
except Exception:
    from .derivative_regex import (
        ALL_REGEX,
        SENTENCE_SPLIT_PATTERN,
        MIN_SENTENCE_LENGTH,
        TRADING_STATEMENTS_REGEX,
        CATEOGRY_REGEX,
        cleanup_fragment,
    )

# =============================================================================
# CONFIGURATION
# =============================================================================


def get_worker_count():
    """Auto-detects CPU cores to set worker count."""
    cpu_cores = mp.cpu_count()
    num_workers = max(1, cpu_cores - 1)
    print(
        f"🖥️  System Detected: {cpu_cores} CPU cores, setting NUM_WORKERS to {num_workers}"
    )
    return num_workers


NUM_WORKERS = get_worker_count()
BATCH_SIZE = 1000  # Optimal batch size for SQLite transactions
FLUSH_INTERVAL = 5.0  # Seconds — fallback flush if batch not full
CHUNK_SIZE = 50  # Larger chunks reduce task submission overhead — tune this
SOURCE_DB_PATH = "web_data.db"
CLEAN_DB_PATH = "prepared_data.db"

# In-memory buffers (protected by main process only)
result_buffer = []  # List of (url, matches, cik, year)
discard_buffer = []  # List of (url, sentence, reason)

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def create_clean_db():
    """Create unified clean database with category classification support and discard tracking."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        # Main table for high-confidence matches
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS webpage_result (
                url TEXT PRIMARY KEY,
                matches TEXT
            )
            """
        )
        # Metadata for high-confidence matches
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS report_data (
                url TEXT PRIMARY KEY,
                cik INTEGER,
                year INTEGER,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
            """
        )
        # Discard tracking table - stores discarded sentences for review
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discarded_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                sentence TEXT,
                discard_reason TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url),
                FOREIGN KEY (discard_reason) REFERENCES discard_reasons(reason)
            )
            """
        )
        # Discard reasons: no_match, too_short, trading_statement
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discard_reasons (
                reason TEXT PRIMARY KEY
            )
            """
        )

        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS discard_reason_idx ON discarded_sentences (discard_reason)"
        )
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Error creating clean database: {e}")
    finally:
        try:
            reasons = [
                "no_match",
                "too_short",
                "trading_statements",
            ]
            c.executemany(
                "INSERT OR IGNORE INTO discard_reasons (reason) VALUES (?)",
                [(reason,) for reason in reasons],
            )
        except sqlite3.IntegrityError as e:
            print(f"⚠️  Error inserting discard reasons: {e}")
        conn.commit()
        conn.close()


def get_source_data() -> List[Tuple[str, str]]:
    """Fetch all URL and matches from source database."""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT url, matches FROM webpage_result WHERE url IS NOT NULL")
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"❌ Error reading source database: {e}")
        conn.close()
        return []


def get_all_report_data() -> dict:
    """Fetch all report data into a dictionary for fast lookups."""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url, cik, year FROM report_data")
    report_map = {row[0]: (row[1], row[2]) for row in c.fetchall()}
    conn.close()
    return report_map


def get_processed_urls_from_clean_db() -> set:
    """Fetches all URLs that have already been processed and saved to the clean database."""
    if not Path(CLEAN_DB_PATH).exists():
        return set()
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT url FROM webpage_result")
        processed_urls = {row[0] for row in c.fetchall()}
        return processed_urls
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()


def flush_buffers(force: bool = False) -> bool:
    """
    Flush accumulated results and discards to database in batches.
    Only runs if batch is full or force=True.
    """
    global result_buffer, discard_buffer

    if (
        not force
        and len(result_buffer) < BATCH_SIZE
        and len(discard_buffer) < BATCH_SIZE * 10
    ):
        return False

    conn = sqlite3.connect(CLEAN_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA temp_store = MEMORY")
    c = conn.cursor()

    try:
        c.execute("BEGIN TRANSACTION")

        # 1. Flush main results
        if result_buffer:
            c.executemany(
                """
                INSERT OR IGNORE INTO webpage_result (url, matches) 
                VALUES (?, ?)
                """,
                [(url, json.dumps(matches)) for url, matches, _, _ in result_buffer],
            )
            c.executemany(
                """
                INSERT OR IGNORE INTO report_data (url, cik, year) 
                VALUES (?, ?, ?)
                """,
                [
                    (url, cik, year)
                    for url, matches, cik, year in result_buffer
                    if cik is not None
                ],
            )
            result_buffer.clear()

        # 2. Flush discarded sentences
        if discard_buffer:
            c.executemany(
                """
                INSERT INTO discarded_sentences (url, sentence, discard_reason)
                VALUES (?, ?, ?)
                """,
                discard_buffer,
            )
            discard_buffer.clear()

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Batch flush failed: {e}")
        raise
    finally:
        conn.close()


# =============================================================================
# FILTERING FUNCTIONS
# =============================================================================


# def check_exclusion_category(sentence: str) -> Optional[str]:
#     """
#     Check if sentence matches any exclusion category.
#     Returns the category name if it matches, None otherwise.
#     """
#     if EXCLUDE_REGEX_EQUITY_COMP.search(sentence):
#         return "equity_compensation"
#     if EXCLUDE_REGEX_LEGAL_LITIGATION.search(sentence):
#         return "legal_litigation"
#     if EXCLUDE_REGEX_ACCOUNTING_STD.search(sentence):
#         # Trick one: we need to make sure no other are matches
#         if not STRICT_REGEX.search(sentence):
#             return "accounting_standards"
#         return "accounting_standards"
#     return None


def filter_matches(
    matches_json: str, url: str = ""
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """
    Main filter: strict first, then soft fallback — but NEVER re-use the same sentence.
    Returns (filtered_paragraphs, discarded_list)
    """
    try:
        matches = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return [], []

    if not isinstance(matches, list):
        return [], []

    final_paragraphs = []
    all_discarded = [] # should be empty, roberta will perform it

    # Process each original match block independently
    for match in matches:
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(match)]
        used_indices = set()  # Track used sentence indices in THIS block only
        # We can use Roberta to filter our the system, instead of relying on regex
        for idx, sentence in enumerate(sentences):
            if idx in used_indices:
                continue  # Already used in strict → skip forever
            if len(sentence) < MIN_SENTENCE_LENGTH:
                all_discarded.append((url, sentence, "too_short"))
                continue
            if TRADING_STATEMENTS_REGEX.search(sentence):
                # Capture the exact text that will be deleted
                deleted_text = " ".join(m.group(0) for m in TRADING_STATEMENTS_REGEX.finditer(sentence))
                # Capture the instrument name (ignore generics,such as "derivative instruments")
                matches = CATEOGRY_REGEX.findall(sentence)
                instrument = matches[0] if matches else ""
                # Log it to your discard list with a clear reason
                all_discarded.append((url, deleted_text.strip(), "trading_statements"))

                # Now surgically remove it
                sentence = TRADING_STATEMENTS_REGEX.sub("", sentence)

                # Optional: clean up punctuation/whitespace (highly recommended)

                sentence = cleanup_fragment(sentence)
                # If the entire sentence was a denial, skip adding a paragraph
                if not sentence:
                    continue  # whole sentence gone → nothing to add
                else:
                    # Append the instrument name before the sentence so we don't lose the meaning for the remaing fragment.
                    sentence = instrument + " " + sentence if instrument else sentence
            if not ALL_REGEX.search(sentence):
                all_discarded.append((url, sentence, "no_match"))
                continue
            # No need to check any exclusion category, but we still need to create mini paragraphs, with derivative keywords
            parts = []
            context_indices = {idx}
            if idx > 0 and (idx - 1) not in used_indices:
                prev = sentences[idx - 1]
                if len(prev) >= MIN_SENTENCE_LENGTH:
                    parts.append(prev)
                    context_indices.add(idx - 1)
            parts.append(sentence)

            if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
                nxt = sentences[idx + 1]
                if len(nxt) >= MIN_SENTENCE_LENGTH:
                    parts.append(nxt)
                    context_indices.add(idx + 1)
            final_paragraphs.append(" ".join(parts))
            used_indices.update(context_indices)

        # # === PHASE 1: Strict matching (high precision) ===
        # strict_paragraphs, strict_discarded, strict_used = _process_block_strict(
        #     sentences, used_indices.copy(), url
        # )
        # final_paragraphs.extend(strict_paragraphs)
        # all_discarded.extend(strict_discarded)
        # used_indices.update(strict_used)

        # # === PHASE 2: Soft fallback only on unused sentences ===
        # if (
        #     len(strict_paragraphs) < len(sentences) // 3
        # ):  # heuristic: too few strict hits
        #     soft_paragraphs, soft_discarded, soft_used = _process_block_soft(
        #         sentences, used_indices, url  # pass current used set
        #     )
        #     final_paragraphs.extend(soft_paragraphs)
        #     all_discarded.extend(soft_discarded)
        #     used_indices.update(soft_used)

    return final_paragraphs, all_discarded


# def _process_block_strict(
#     sentences: List[str], used_indices: set, url: str
# ) -> Tuple[List[str], List[Tuple[str, str, str]], set]:
#     """Internal: strict pass on one block."""
#     paragraphs = []
#     discarded = []
#     newly_used = set()

#     for idx, sentence in enumerate(sentences):
#         if idx in used_indices:
#             continue

#         if len(sentence) < MIN_SENTENCE_LENGTH:
#             discarded.append((url, sentence, "too_short"))
#             continue

#         if check_exclusion_category(sentence):
#             reason = check_exclusion_category(sentence)
#             discarded.append((url, sentence, reason))
#             continue

#         if not STRICT_REGEX.search(sentence):
#             discarded.append((url, sentence, "no_strict_match"))
#             continue

#         # Build paragraph from current + optional prev/next (if not used)
#         parts = []
#         context_indices = {idx}

#         if idx > 0 and (idx - 1) not in used_indices:
#             prev = sentences[idx - 1]
#             if len(prev) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(prev):
#                 parts.append(prev)
#                 context_indices.add(idx - 1)

#         parts.append(sentence)

#         if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
#             nxt = sentences[idx + 1]
#             if len(nxt) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(nxt):
#                 parts.append(nxt)
#                 context_indices.add(idx + 1)

#         paragraphs.append(" ".join(parts))
#         newly_used.update(context_indices)

#     return paragraphs, discarded, newly_used


# def _process_block_soft(
#     sentences: List[str], used_indices: set, url: str
# ) -> Tuple[List[str], List[Tuple[str, str, str]], set]:
#     """Internal: soft pass — only on sentences NOT used in strict phase."""
#     paragraphs = []
#     discarded = []
#     newly_used = set()

#     for idx, sentence in enumerate(sentences):
#         if idx in used_indices:
#             continue  # Already used in strict → skip forever

#         if len(sentence) < MIN_SENTENCE_LENGTH:
#             discarded.append((url, sentence, "too_short_soft"))
#             continue

#         if check_exclusion_category(sentence):
#             reason = check_exclusion_category(sentence)
#             discarded.append((url, sentence, reason))
#             continue

#         if not SOFT_REGEX.search(sentence):
#             discarded.append((url, sentence, "no_soft_match"))
#             continue

#         # Same context logic as strict
#         parts = []
#         context_indices = {idx}

#         if idx > 0 and (idx - 1) not in used_indices:
#             prev = sentences[idx - 1]
#             if len(prev) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(prev):
#                 parts.append(prev)
#                 context_indices.add(idx - 1)

#         parts.append(sentence)

#         if idx + 1 < len(sentences) and (idx + 1) not in used_indices:
#             nxt = sentences[idx + 1]
#             if len(nxt) >= MIN_SENTENCE_LENGTH and not check_exclusion_category(nxt):
#                 parts.append(nxt)
#                 context_indices.add(idx + 1)

#         paragraphs.append(" ".join(parts))
#         newly_used.update(context_indices)

#     return paragraphs, discarded, newly_used


# =============================================================================
# WORKER FUNCTION (NO DB ACCESS)
# =============================================================================


def process_item_buffered(
    item: Tuple[str, str], report_data_map: dict
) -> Optional[Tuple]:
    """
    Worker function to process a single URL's matches.
    Returns data instead of writing to database.
    """
    url, matches_json = item
    try:
        strict_matches, discarded = filter_matches(matches_json, url)

        if not strict_matches:
            return None

        # Get metadata from the passed-in map
        cik, year = report_data_map.get(url, (None, None))
        return (url, strict_matches, cik, year, discarded)
    except Exception:
        return None


# =============================================================================
# MAIN PROCESSING FUNCTION
# =============================================================================


def process_and_filter_database():
    """Main function to filter database with buffered batch writes."""
    print("=" * 80)
    print("🔧 DATABASE NOISE REDUCTION WITH BATCHED BUFFERED WRITES")
    print("=" * 80)

    # Initialize database
    print("\n📦 Initializing clean database...")
    create_clean_db()

    # Get already processed URLs
    print(f"🔍 Checking for previously processed URLs in {CLEAN_DB_PATH}...")
    processed_urls = get_processed_urls_from_clean_db()
    if processed_urls:
        print(
            f"  • Found {len(processed_urls):,} already processed URLs. They will be skipped."
        )

    # Fetch source data
    print(f"📖 Reading from {SOURCE_DB_PATH}...")
    source_data = get_source_data()

    if not source_data:
        print("❌ No data found in source database.")
        return

    # Filter out already processed URLs
    unprocessed_data = [item for item in source_data if item[0] not in processed_urls]
    if not unprocessed_data:
        print("✅ All URLs have already been processed. Nothing to do.")
        return

    print("🧠 Loading report metadata into memory...")
    report_data_map = get_all_report_data()
    print(f"  • Loaded metadata for {len(report_data_map)} reports.")

    print(f"📊 Found {len(unprocessed_data)} new URLs to process\n")

    global result_buffer, discard_buffer
    result_buffer = []
    discard_buffer = []

    last_flush = time.time()

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Use map() with chunksize for better task batching
        results_iter = executor.map(
            process_item_buffered,
            unprocessed_data,
            [report_data_map] * len(unprocessed_data),
            chunksize=CHUNK_SIZE,
        )

        for result in tqdm(
            results_iter, total=len(unprocessed_data), desc="Filtering URLs"
        ):
            if result is None:
                continue

            url, matches, cik, year, discarded = result
            result_buffer.append((url, matches, cik, year))
            discard_buffer.extend(discarded)

            # Periodic flush
            if len(result_buffer) >= BATCH_SIZE or (
                time.time() - last_flush > FLUSH_INTERVAL
            ):
                flush_buffers()
                last_flush = time.time()

    # Final flush
    if result_buffer or discard_buffer:
        print("\n💾 Final buffer flush...")
        flush_buffers(force=True)

    print_discard_summary()


def print_discard_summary():
    """Print summary of discarded sentences by category."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "SELECT discard_reason, COUNT(*) as count FROM discarded_sentences GROUP BY discard_reason ORDER BY count DESC"
        )
        stats = c.fetchall()

        print("\n" + "=" * 80)
        print("📊 DISCARDED SENTENCES SUMMARY")
        print("=" * 80)

        total_discarded = sum(count for _, count in stats)

        for reason, count in stats:
            reason_display = reason.replace("_", " ").title()
            print(f"  • {reason_display}: {count:,}")

        print(f"\n  Total Discarded: {total_discarded:,}")
        print(f"  View details in 'discarded_sentences' table")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"⚠️  Error reading discard summary: {e}")
    finally:
        conn.close()


# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
if __name__ == "__main__":
    # Run the filtering process
    process_and_filter_database()

# %%
