import sqlite3
import json
import multiprocessing as mp
import time
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
from typing import List, Tuple, Optional

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "web_data.db"  # Raw Input
TARGET_DB_PATH = "prefiltered_data.db"  # Clean Input for Categorizer

# Import only the exclusion regexes
from derivative_regex import (
    ACCOUNTING_STANDARDS_STRICT_REGEX,
    DER_STD_REGEX,
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
# DATABASE SETUP
# =============================================================================
def setup_target_db():
    """Creates the intermediate pre-filtered database."""
    if Path(TARGET_DB_PATH).exists():
        Path(TARGET_DB_PATH).unlink()

    conn = sqlite3.connect(TARGET_DB_PATH)
    c = conn.cursor()

    # Simple Schema: URL + JSON Matches + Metadata
    # We keep it compatible with what filter_database expects
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS webpage_result (
            url TEXT PRIMARY KEY,
            matches TEXT NOT NULL  -- JSON array of clean paragraphs
        )
    """
    )

    # Metadata table (Pass-through)
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

    # Discard tracking (Essential for auditing the noise removal)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS discarded_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            sentence TEXT,
            discard_reason TEXT
        )
    """
    )

    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
    c.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    conn.close()


def get_source_data() -> List[Tuple]:
    """Fetch raw data from web_data.db"""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    try:
        # Join with report_data to pass metadata through
        c.execute(
            """
            SELECT w.url, w.matches, r.cik, r.year 
            FROM webpage_result w
            LEFT JOIN report_data r ON w.url = r.url
            WHERE w.matches IS NOT NULL
        """
        )
        return c.fetchall()
    except Exception as e:
        print(f"❌ Error reading source DB: {e}")
        return []
    finally:
        conn.close()


def write_batch(buffer: List[Tuple], discards: List[Tuple]):
    if not buffer and not discards:
        return

    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")

        if buffer:
            # 1. Write Clean Matches
            c.executemany(
                "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                [(row[0], row[1]) for row in buffer],
            )
            # 2. Write Metadata
            c.executemany(
                "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                [(row[0], row[2], row[3]) for row in buffer],
            )

        if discards:
            # 3. Write Discards
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                discards,
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Write failed: {e}")
    finally:
        conn.close()


# =============================================================================
# FILTER LOGIC
# =============================================================================
def process_item(item: Tuple) -> Optional[Tuple]:
    url, matches_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    clean_paragraphs = []
    local_discards = []
    for i, p in enumerate(paragraphs):
        # 1. Skip Tables (Pass them through for the Table Processor in next stage)
        # Or you can choose to filter noise WITHIN tables here if you want.
        # For now, we pass them safely.
        if "<TABLE>" in p.upper():
            clean_paragraphs.append(p)
            continue

        # 2. Paragraph-Level Exclusion Filters
        # These are the "Obvious Deadweights"

        if EXCLUDE_REGEX_LEGAL_LITIGATION.search(p):
            local_discards.append((url, p, "legal_litigation"))
            continue

        if EXCLUDE_REGEX_FORWARD_LOOKING.search(p):
            # Forward looking is high volume, so we discard it early
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

        if EXCLUDE_HYPOTHETICAL_REGEX.search(p):
            # Sensitivity analysis often mentions ACTUAL instruments.
            # We only discard if it's purely generic methodology without naming names.

            # If it mentions a specific instrument (Strict) or Soft+Context, KEEP IT.
            if STRICT_REGEX.search(p) or (
                SOFT_REGEX.search(p) and HEDGING_CONTEXT_REGEX.search(p)
            ):
                clean_paragraphs.append(p)
                continue
            else:
                local_discards.append((url, p, "hypothetical_sensitivity_methodology"))
                continue
        if EXCLUDE_REGEX_FILING.search(p):
            local_discards.append((url, p, "filing"))
            continue
        if is_contractual_noise(p, loose_threshold=2):
            local_discards.append((url, p, "contractual_noise"))
            continue
        if EXCLUDE_REGEX_EQUITY_COMP.search(p):
            kept = []
            sentences = SENTENCE_SPLIT_PATTERN.split(p)
            for idx, sent in enumerate(sentences):
                if EQ_REGEX.search(sent):
                    kept.append(sent)
                elif EQ_SOFT_REGEX.search(sent):
                    has_hedging_context = SOFT_GEN_REGEX.search(sent) or DER_STD_REGEX.search(sent)
                    if has_hedging_context:
                        kept.append(sent)
                else:
                    continue
            # Join whatever is left
            p = " ".join(kept)
            # Join whatever is not in kept (using set)
            discarded = " ".join(list(set(sentences) - set(kept)))
            local_discards.append((url, discarded, "comp"))
            clean_paragraphs.append(p)
            continue

        if ACCOUNTING_STANDARDS_STRICT_REGEX.search(p):
            kept = []
            sentences = SENTENCE_SPLIT_PATTERN.split(p)
            for idx, sent in enumerate(sentences):
                if not ACCOUNTING_STANDARDS_STRICT_REGEX.search(sent):
                    kept.append(sent)
                else:
                    break
            # Join whatever is left
            p = " ".join(kept)
            # Join whatever is not in kept (using set)
            discarded = " ".join(list(set(sentences) - set(kept)))
            local_discards.append((url, discarded, "accounting_standards"))
            clean_paragraphs.append(p)
            continue

        # 3. If it survives, keep it
        clean_paragraphs.append(p)

    # 4. Return result if we have content left
    if clean_paragraphs:
        should_keep = any(find_hedging_context(p) for p in clean_paragraphs)
        if not should_keep:
            local_discards.append((url, "\n\n".join(clean_paragraphs), "no_hedging_context"))
            return None
        return (
            url,
            json.dumps(clean_paragraphs),
            cik,
            year,
            aggregate_discards(local_discards),
        )
    elif local_discards:
        # If everything was filtered, we still want to log the discards
        return (url, "[]", cik, year, aggregate_discards(local_discards))

    return None

def find_hedging_context(paragraph: str) -> bool:
    if STRICT_REGEX.search(paragraph):
        return True
    elif SOFT_GEN_REGEX.search(paragraph):
        return True
    elif SOFT_REGEX.search(paragraph) and HEDGING_CONTEXT_REGEX.search(paragraph):
        return True
    elif DER_STD_REGEX.search(paragraph) and LOOSE_GEN_REGEX.search(paragraph):
        return True
    return False


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print(f"🚀 Starting Pre-Filter (Noise Removal)...")
    setup_target_db()

    data = get_source_data()
    print(f"📊 Processing {len(data):,} items...")

    batch_buffer = []
    discard_buffer = []

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        results = executor.map(process_item, data, chunksize=50)

        for res in tqdm(results, total=len(data)):
            if not res:
                continue

            # Unpack
            url, clean_json, cik, year, discards = res

            # Add to buffers
            if clean_json != "[]":
                batch_buffer.append((url, clean_json, cik, year))

            discard_buffer.extend(discards)

            # Flush if full
            if len(batch_buffer) >= BATCH_SIZE:
                write_batch(batch_buffer, discard_buffer)
                batch_buffer = []
                discard_buffer = []

    # Final Flush
    if batch_buffer or discard_buffer:
        write_batch(batch_buffer, discard_buffer)

    print(f"✅ Done. Clean data saved to: {TARGET_DB_PATH}")
