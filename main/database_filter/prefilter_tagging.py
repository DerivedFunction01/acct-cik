import sqlite3
import json
import re
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm

from derivative_regex import (
    EMBEDDED_CAP_FLOOR_REGEX,
    MORE_INFO_REGEX,
    REFERENCE_CLEANUP_REGEX,
    SENTENCE_SPLIT_PATTERN,
    DEFINITION_INDICATORS,
    ENTITY_EXCLUSION_REGEX,
    ENTITY_TOKEN
)
from prefilter_simple_nonuse import DEADWEIGHT_TOKEN

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "prefiltered_data.db"
TARGET_DB_PATH = "secondary_filtered_data.db"

# Tokens
SKIP_TOKEN = " _S "


def tag_paragraph(text):
    """
    Applies regex noise detection per sentence.
    Returns the text with _S tokens inserted.
    If ALL sentences are _S, prepends _D to the paragraph.
    """
    # 1. Create a Masked Version for Logic Checks
    # We operate on this (so "CFTC" -> "ENTITY") to catch entity noise
    masked_text = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, text)

    # 2. Split BOTH versions (Must stay aligned)
    original_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
    ]
    masked_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(masked_text) if s.strip()
    ]

    # Safety: If split counts differ (rare regex edge case), fallback to keeping original
    if len(original_sentences) != len(masked_sentences):
        return text

    tagged_output = []
    valid_count = 0

    for orig, masked in zip(original_sentences, masked_sentences):
        is_noise = False

        # --- NOISE CHECKS (Run on MASKED version) ---
        # A. Navigational / Info Pointers ("See Note 5", "For more info")
        if REFERENCE_CLEANUP_REGEX.search(masked) or MORE_INFO_REGEX.search(masked):
            is_noise = True

        # B. Definitions ("Swap shall mean...")
        elif DEFINITION_INDICATORS.search(masked):
            is_noise = True

        # C. Embedded Loan Features (unless salvaged)
        elif EMBEDDED_CAP_FLOOR_REGEX.search(masked):
            is_noise = True

        # --- TAGGING ---
        if is_noise:
            tagged_output.append(f"{SKIP_TOKEN}{orig}")
        else:
            tagged_output.append(orig)
            valid_count += 1

    # Reassemble
    final_text = " ".join(tagged_output)

    # If NO sentences survived, mark the whole block as Deadweight
    if valid_count == 0:
        return f"{DEADWEIGHT_TOKEN}{final_text}"

    return final_text


def process_row(row):
    url, matches_json, cik, year = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    new_paragraphs = []
    for p in paragraphs:
        # Skip if already deadweight from previous stage
        if p.startswith(DEADWEIGHT_TOKEN):
            new_paragraphs.append(p)
            continue

        # Run the sentence tagger
        tagged_p = tag_paragraph(p)
        new_paragraphs.append(tagged_p)

    return (url, json.dumps(new_paragraphs), cik, year)


# =============================================================================
# DATABASE SETUP
# =============================================================================

def setup_target_db(path):
    if Path(path).exists():
        pass  # Optional: uncomment to delete for fresh start
        # Path(path).unlink()
    
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
    c = conn.cursor()
    try:
        c.execute("SELECT url FROM webpage_result")
        return {row[0] for row in c.fetchall()}
    except:
        return set()


def data_generator(source_db, processed_urls, batch_size=BATCH_SIZE):
    """
    Yields rows one by one from source database.
    Prevents loading all rows into RAM.
    """
    conn = sqlite3.connect(source_db)
    c = conn.cursor()
    c.execute(
        "SELECT w.url, w.matches, r.cik, r.year FROM webpage_result w LEFT JOIN report_data r ON w.url = r.url WHERE w.matches IS NOT NULL"
    )

    while True:
        rows = c.fetchmany(batch_size)
        if not rows:
            break

        for row in rows:
            url = row[0]
            if url in processed_urls:
                continue
            yield row

    conn.close()


def write_batch(conn, buffer):
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
# MAIN LOGIC
# =============================================================================

if __name__ == "__main__":
    print(f"🚀 Starting Secondary Filter ({NUM_WORKERS} workers)")

    # 1. Setup
    setup_target_db(TARGET_DB_PATH)
    processed_urls = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed_urls)} processed URLs.")

    # 2. Connect Writer DB (Main Thread Only)
    target_conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    target_conn.execute("PRAGMA journal_mode=WAL")
    target_conn.execute("PRAGMA synchronous=NORMAL")

    # 3. Processing Loop
    buffer = []
    count = 0

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Create iterator (does not load all to RAM)
        source_iter = list(data_generator(SOURCE_DB_PATH, processed_urls))
        total_items = len(source_iter)

        # executor.map yields results in order
        results_iter = executor.map(process_row, source_iter, chunksize=CHUNK_SIZE)

        # Wrap in tqdm with total
        for result in tqdm(results_iter, desc="Tagging Sentences", total=total_items):
            if not result:
                continue

            url, matches, cik, year = result
            buffer.append((url, matches, cik, year))

            if len(buffer) >= BATCH_SIZE:
                write_batch(target_conn, buffer)
                buffer = []

            count += 1

    # 4. Final Flush
    if buffer:
        write_batch(target_conn, buffer)

    target_conn.close()
    print(f"✅ Complete. Processed {count} documents.")
