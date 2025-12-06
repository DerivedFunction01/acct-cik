"""
Table Cleanup Script (Concurrent Version with Better Debugging)
Filters out non-numeric tables that are just formatting containers for text.
Keeps only tables with meaningful financial/numeric data.
"""

import re
import json
import sqlite3
import pandas as pd
from typing import List, Dict, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import multiprocessing as mp

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "web_data.db"
DEBUG = False
BATCH_SIZE = 2500  # Process database in batches
NUM_WORKERS = mp.cpu_count() - 1 if mp.cpu_count() > 1 else 1  # Leave one core free
import re
from typing import List, Tuple, Optional

# =============================================================================
# TABLE PATTERNS (Extraction Only)
# =============================================================================

# Pattern to extract footnotes from tables
FOOTNOTE_PATTERN = re.compile(r"<FN>(.*?)</FN>\s*</TABLE>", re.DOTALL | re.IGNORECASE)

# Pattern to find individual footnotes within <FN> block
INDIVIDUAL_FOOTNOTE_PATTERN = re.compile(
    r"<F\s+(\d+)>\s*(.*?)(?=<F\s+\d+>|$)", re.DOTALL
)

# Pattern to find any <TAG> or </TAG>
TAG_PATTERN = re.compile(r"<[^>]+>")

# =============================================================================
# CORE EXTRACTION (Used by table_processor.py)
# =============================================================================


def extract_table_content(table_text: str) -> Tuple[List[List[str]], List[List[str]]]:
    """
    Parses a raw <TABLE> string into headers and data rows.
    Used by TableToTextConverter.
    """
    lines = table_text.split("\n")
    rows = []

    # 1. Row Extraction
    for line in lines:
        line = line.strip()
        if "<TABLE>" in line or "<CAPTION>" in line or "</TABLE>" in line:
            continue
        if "<S>" in line or "<C>" in line:  # SEC Formatting tags
            continue
        if line.startswith("-") or not line:  # Separators or empty
            continue
        if line:
            rows.append(line)

    # 2. Header vs Data Split
    headers = []
    data = []

    # Heuristic: First 2 rows are headers if table is long enough
    if len(rows) > 2:
        headers = rows[:2]
        data = rows[2:]
    elif rows:
        headers = rows[:1]
        data = rows[1:]

    # 3. Cell Parsing (Split by 2+ spaces)
    def parse_row(row: str) -> List[str]:
        # Split on 2+ spaces to separate columns
        cells = re.split(r"\s{2,}", row.strip())
        return [c.strip() for c in cells if c.strip()]

    header_cells = [parse_row(h) for h in headers]
    data_cells = [parse_row(d) for d in data]

    return header_cells, data_cells


def extract_and_separate_footnotes(table_text: str) -> Tuple[str, List[str]]:
    """
    Extract footnotes from a table and return cleaned table + footnotes as paragraphs.
    """
    footnotes = []

    # Find the <FN>...</FN></TABLE> block
    fn_match = FOOTNOTE_PATTERN.search(table_text)

    if fn_match:
        fn_content = fn_match.group(1)

        # Extract individual footnotes
        individual_fns = INDIVIDUAL_FOOTNOTE_PATTERN.findall(fn_content)

        for fn_num, fn_text in individual_fns:
            cleaned = fn_text.strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            if cleaned:
                footnotes.append(f"Footnote {fn_num}: {cleaned}")

        # Remove the footnote block from the table text so it doesn't mess up row parsing
        cleaned_table = FOOTNOTE_PATTERN.sub("</TABLE>", table_text)
        return cleaned_table, footnotes

    return table_text, []


def strip_table_formatting(table_text: str) -> str:
    """
    Strip table formatting tags and separators, converting to plain paragraphs.
    Used when we decide a table is 'bad' and want to treat it as text.
    """
    # Remove all HTML-style tags
    text = TAG_PATTERN.sub("", table_text)

    # Remove separator lines
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        # Skip empty lines and separator lines
        if stripped and not all(c in "-\t " for c in stripped):
            cleaned_lines.append(stripped)

    # Join into paragraphs
    result = " ".join(cleaned_lines)
    result = re.sub(r"\s+", " ", result).strip()

    return result


# =============================================================================
# VALIDATION LOGIC (The New Brain)
# =============================================================================


def is_text_container_table(
    table_text: str, footnotes: List[str], verbose: bool = False
) -> bool:
    """
    Determines if a table is useful by trying to process it.

    Returns True -> It is a text container (Discard/Flatten).
    Returns False -> It is a valid numeric table (Keep).
    """

    # 1. Late Import to avoid Circular Dependency
    # table_processor imports extract_table_content from THIS file.
    try:
        from table_processor import TableToTextConverter
    except ImportError:
        # Fallback if running standalone or path issues (shouldn't happen in pipeline)
        return True

    # 2. Prepare Context
    # We join footnotes and pass them as narrative context.
    # This allows the processor to find keywords like "Notional" in the footnotes
    # to anchor the table.
    context_str = " ".join(footnotes) + " notional "

    # 3. Run the Processor (High Recall Mode)
    # We set is_sophisticated=True so that if the table contains 'Soft' mentions
    # (like "Commodity Contracts") without a strict "Swap" keyword, we still try to read it.
    # If the table has NO numbers, the processor returns [] anyway.
    try:
        converter = TableToTextConverter(
            table_text, narrative_context=context_str, is_sophisticated=True
        )

        sentences = converter.process()

        # 4. The Verdict
        if sentences:
            if verbose:
                print(f"  ✅ Table Validated: Generated {len(sentences)} sentences.")
            return False  # It is NOT just a text container; it's a valid table.
        else:
            if verbose:
                print(f"  ❌ Table Invalid: Processor produced no output.")
            return True  # It IS a text container (or useless data).

    except Exception as e:
        if verbose:
            print(f"  ⚠️ Processor Error: {e}")
        return True  # Default to flattening if processing fails


def clean_matches(matches: List[str], verbose: bool = False) -> List[str]:
    """
    Filter out text-container tables from matches list and extract footnotes.
    """
    cleaned = []

    for i, match in enumerate(matches):
        if "<TABLE>" in match.upper():
            if verbose:
                print(f"\n🔍 Analyzing Table {i+1}...")

            # 1. Extract footnotes first
            cleaned_table, footnotes = extract_and_separate_footnotes(match)

            # 2. Check if numeric/useful using the Processor
            is_container = is_text_container_table(cleaned_table, footnotes, verbose)

            if not is_container:
                # KEEP: It's a real table
                cleaned.append(cleaned_table)
                # Append extracted footnotes as text paragraphs after the table
                cleaned.extend(footnotes)
            else:
                # FLATTEN: It's just text or garbage
                plain_text = strip_table_formatting(cleaned_table)

                # Only keep if meaningful content remains
                if plain_text and len(plain_text) > 50:
                    cleaned.append(plain_text)
                    if verbose:
                        print(f"  🔄 Converted to paragraph text.")

                # Keep footnotes as text too
                cleaned.extend(footnotes)

        else:
            # It's already text, keep it
            cleaned.append(match)

    return cleaned

# =============================================================================
# PARALLEL PROCESSING
# =============================================================================


def process_single_row(row_data: Tuple[str, str]) -> Tuple[str, str, Dict[str, int]]:
    """
    Process a single database row in parallel.
    """
    url, matches_json = row_data
    stats = {
        "original_count": 0,
        "new_count": 0,
        "tables_found": 0,
        "tables_kept": 0,
        "tables_removed": 0,
        "footnotes_extracted": 0,
        "changed": False,
    }

    try:
        matches = json.loads(matches_json)
        stats["original_count"] = len(matches)
        stats["tables_found"] = sum(1 for m in matches if "<TABLE>" in m.upper())

        # Clean the matches
        cleaned_matches = clean_matches(matches)
        stats["new_count"] = len(cleaned_matches)
        stats["tables_kept"] = sum(1 for m in cleaned_matches if "<TABLE>" in m.upper())
        stats["footnotes_extracted"] = sum(
            1 for m in cleaned_matches if m.startswith("Footnote ")
        )
        stats["tables_removed"] = stats["tables_found"] - stats["tables_kept"]

        # Check if anything changed
        stats["changed"] = matches_json != json.dumps(cleaned_matches)

        return url, json.dumps(cleaned_matches), stats

    except Exception as e:
        print(f"❌ Error processing {url}: {e}")
        import traceback

        traceback.print_exc()
        return url, matches_json, stats


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================


def process_database(verbose: bool = False):
    """
    Process all webpage results in the database.
    """
    print(f"🔧 Using {NUM_WORKERS} worker processes")

    # Fetch all results
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url, matches FROM webpage_result")
    rows = c.fetchall()
    conn.close()

    total_rows = len(rows)
    print(f"📊 Processing {total_rows:,} webpage results...")

    # Overall statistics
    total_cleaned = 0
    total_tables_found = 0
    total_tables_kept = 0
    total_tables_removed = 0
    total_footnotes = 0

    # Process in batches
    for batch_start in range(0, total_rows, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch = rows[batch_start:batch_end]

        print(
            f"\n📦 Batch {batch_start//BATCH_SIZE + 1}: rows {batch_start:,} to {batch_end:,}"
        )

        # Process batch
        batch_results = []
        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = [executor.submit(process_single_row, row) for row in batch]

            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="  Processing",
                leave=False,
            ):
                try:
                    result = future.result()
                    batch_results.append(result)
                except Exception as e:
                    print(f"  ⚠️  Worker error: {e}")

        # Update database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        batch_cleaned = 0
        batch_tables_removed = 0

        for url, cleaned_matches_json, stats in batch_results:
            if stats["changed"]:
                batch_cleaned += 1
                total_tables_found += stats["tables_found"]
                total_tables_kept += stats["tables_kept"]
                total_tables_removed += stats["tables_removed"]
                total_footnotes += stats["footnotes_extracted"]

                c.execute(
                    "UPDATE webpage_result SET matches = ? WHERE url = ?",
                    (cleaned_matches_json, url),
                )

        conn.commit()
        conn.close()

        total_cleaned += batch_cleaned

        if batch_cleaned > 0:
            print(f"  ✅ Updated {batch_cleaned:,} URLs in this batch")
        else:
            print(f"  ℹ️  No changes in this batch")

    print(f"\n" + "=" * 70)
    print(f"✅ Processing complete!")
    print(f"  - {total_cleaned:,} URLs modified")
    print(f"  - {total_tables_found:,} tables analyzed")
    print(f"  - {total_tables_kept:,} tables kept")
    print(f"  - {total_tables_removed:,} tables removed/converted")
    print(f"  - {total_footnotes:,} footnotes extracted")
    print("=" * 70)


def analyze_sample(sample_size: int = 10):
    """
    Analyze a sample with verbose output.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url, matches FROM webpage_result LIMIT ?", (sample_size,))
    rows = c.fetchall()
    conn.close()

    print(f"🔍 Analyzing {len(rows)} sample results...\n")

    for url, matches_json in rows:
        matches = json.loads(matches_json)
        tables = [m for m in matches if "<TABLE>" in m.upper()]

        if tables:
            print(f"\n{'='*70}")
            print(f"📄 URL: {url}")
            print(f"📊 Found {len(tables)} table(s), {len(matches)} total matches")

            cleaned = clean_matches(matches, verbose=True)

            print(f"\n📈 Result: {len(matches)} → {len(cleaned)} matches")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up non-numeric tables from webpage results"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze sample tables with verbose output",
    )
    parser.add_argument(
        "--sample-size", type=int, default=10, help="Number of samples to analyze"
    )
    parser.add_argument(
        "--workers", type=int, default=NUM_WORKERS, help="Number of worker processes"
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE, help="Batch size for processing"
    )

    args = parser.parse_args()
    NUM_WORKERS = args.workers
    BATCH_SIZE = args.batch_size

    if args.analyze:
        analyze_sample(args.sample_size)
    else:
        process_database()
