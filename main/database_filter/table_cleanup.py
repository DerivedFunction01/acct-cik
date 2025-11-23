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

# =============================================================================
# TABLE CLASSIFICATION PATTERNS
# =============================================================================

# Pattern to extract footnotes from tables
FOOTNOTE_PATTERN = re.compile(r"<FN>(.*?)</FN>\s*</TABLE>", re.DOTALL | re.IGNORECASE)

# Pattern to find individual footnotes within <FN> block
INDIVIDUAL_FOOTNOTE_PATTERN = re.compile(
    r"<F\s+(\d+)>\s*(.*?)(?=<F\s+\d+>|$)", re.DOTALL
)

# Pattern to find separator lines
SEPARATOR_PATTERN = re.compile(r"^[\s\-]+$", re.MULTILINE)

# Pattern to find any <TAG> or </TAG>
TAG_PATTERN = re.compile(r"<[^>]+>")

# Patterns that indicate a table is just a text container
TEXT_CONTAINER_INDICATORS = [
    # Very long unbroken text (>200 chars without line breaks)
    re.compile(r".{200,}", re.DOTALL),
    # Multiple sentences in a single cell (indicates paragraph text)
    re.compile(r"[.!?]\s+[A-Z].*[.!?]\s+[A-Z]", re.DOTALL),
]

# Patterns that indicate a real numeric table
NUMERIC_TABLE_INDICATORS = [
    # Currency symbols
    re.compile(r"[\$£€¥]"),
    # Numbers with commas (1,000)
    re.compile(r"\d{1,3}(,\d{3})+"),
    # Percentages
    re.compile(r"\d+\.?\d*\s*%"),
    # Parenthetical numbers (accounting notation for negatives)
    re.compile(r"\(\s*\d+[,\d]*\.?\d*\s*\)"),
    # Numbers in thousands/millions notation
    re.compile(r"\d+\.?\d*\s*(thousand|million|billion|k|m|b)", re.IGNORECASE),
]

# Financial/numeric keywords that suggest a real table
FINANCIAL_KEYWORDS = {
    "assets",
    "liabilities",
    "revenue",
    "income",
    "expense",
    "profit",
    "loss",
    "balance",
    "cash",
    "debt",
    "equity",
    "principal",
    "interest",
    "rate",
    "cost",
    "value",
    "fair value",
    "amount",
    "total",
    "net",
    "gross",
    "payable",
    "receivable",
    "inventory",
    "goodwill",
    "depreciation",
    "amortization",
    "tax",
    "deferred",
    "current",
    "non-current",
    "fiscal year",
    "quarter",
    "year ended",
    "december",
    "january",
    "derivative",
    "swap",
    "forward",
    "option",
    "notional",
    "maturity",
}

# Column header patterns for real tables
NUMERIC_HEADER_PATTERNS = [
    re.compile(r"^\s*\d{4}\s*$"),  # Year columns (2023, 2022, etc.)
    re.compile(r"^\s*(in\s+)?(thousands|millions|billions)\s*$", re.IGNORECASE),
    re.compile(r"^\s*amount\s*$", re.IGNORECASE),
    re.compile(r"^\s*(fair\s+)?value\s*$", re.IGNORECASE),
]

# =============================================================================
# TABLE PARSING AND ANALYSIS
# =============================================================================


def extract_and_separate_footnotes(table_text: str) -> Tuple[str, List[str]]:
    """
    Extract footnotes from a table and return cleaned table + footnotes as paragraphs.

    Returns:
        (cleaned_table_text, list_of_footnote_paragraphs)
    """
    footnotes = []

    # Find the <FN>...</FN></TABLE> block
    fn_match = FOOTNOTE_PATTERN.search(table_text)

    if fn_match:
        fn_content = fn_match.group(1)

        # Extract individual footnotes
        individual_fns = INDIVIDUAL_FOOTNOTE_PATTERN.findall(fn_content)

        for fn_num, fn_text in individual_fns:
            # Clean up the footnote text
            cleaned = fn_text.strip()
            # Remove excessive whitespace
            cleaned = re.sub(r"\s+", " ", cleaned)

            if cleaned:
                footnotes.append(f"Footnote {fn_num}: {cleaned}")

        # Remove the footnote block from the table
        cleaned_table = FOOTNOTE_PATTERN.sub("</TABLE>", table_text)

        return cleaned_table, footnotes

    return table_text, []


def extract_table_content(table_text: str) -> Tuple[List[str], List[List[str]]]:
    """
    Extract rows from a <TABLE> block.
    Returns (header_rows, data_rows)
    """
    lines = table_text.split("\n")
    rows = []

    for line in lines:
        line = line.strip()
        if "<TABLE>" in line or "<CAPTION>" in line or "</TABLE>" in line:
            continue
        if "<S>" in line or "<C>" in line:
            continue
        if line.startswith("-") or not line:
            continue
        if line:
            rows.append(line)

    # Try to identify header vs data rows
    headers = []
    data = []

    # Simple heuristic: first 1-2 rows are headers, rest is data
    if len(rows) > 2:
        headers = rows[:2]
        data = rows[2:]
    elif rows:
        headers = rows[:1]
        data = rows[1:]

    # Parse rows into cells (split by multiple spaces)
    def parse_row(row: str) -> List[str]:
        # Split on 2+ spaces to separate columns
        cells = re.split(r"\s{2,}", row.strip())
        return [c.strip() for c in cells if c.strip()]

    header_cells = [parse_row(h) for h in headers]
    data_cells = [parse_row(d) for d in data]

    return header_cells, data_cells


def count_numeric_cells(rows: List[List[str]]) -> int:
    """Count cells that contain numbers"""
    count = 0
    for row in rows:
        for cell in row:
            if re.search(r"\d", cell):
                count += 1
    return count


def count_financial_keywords(rows: List[List[str]]) -> int:
    """Count financial keywords in cells"""
    count = 0
    for row in rows:
        for cell in row:
            cell_lower = cell.lower()
            for keyword in FINANCIAL_KEYWORDS:
                if keyword in cell_lower:
                    count += 1
                    break
    return count


def has_numeric_headers(headers: List[List[str]]) -> bool:
    """Check if headers suggest a numeric table"""
    for header_row in headers:
        for cell in header_row:
            for pattern in NUMERIC_HEADER_PATTERNS:
                if pattern.match(cell):
                    return True
    return False


def calculate_text_density(rows: List[List[str]]) -> float:
    """
    Calculate average text length per cell.
    High values suggest paragraph text, low values suggest structured data.
    """
    if not rows:
        return 0.0

    total_chars = 0
    total_cells = 0

    for row in rows:
        for cell in row:
            total_chars += len(cell)
            total_cells += 1

    return total_chars / total_cells if total_cells > 0 else 0.0


def check_separator_length(table_text: str) -> int:
    """
    Find the longest separator line in the table.
    Returns the length of the longest separator (line of dashes/spaces).
    """
    lines = table_text.split("\n")
    max_separator_len = 0

    for line in lines:
        stripped = line.strip()
        if stripped and all(c in "-\t " for c in stripped):
            dash_count = stripped.count("-")
            if dash_count > max_separator_len:
                max_separator_len = dash_count

    return max_separator_len


def strip_table_formatting(table_text: str) -> str:
    """
    Strip table formatting tags and separators, converting to plain paragraphs.
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


def is_text_container_table(table_text: str, verbose: bool = False) -> bool:
    """
    Determine if a table is just a text container (not a real numeric table).

    Returns True if the table should be REMOVED, False if it should be kept.
    """
    # Check separator length first
    max_separator = check_separator_length(table_text)
    if max_separator > 300:
        if verbose:
            print(f"  ❌ Long separator ({max_separator} chars) - removing")
        return True

    # Extract content
    headers, data = extract_table_content(table_text)
    all_rows = headers + data

    if not all_rows:
        if verbose:
            print(f"  ❌ Empty table - removing")
        return True

    # Check for very long text in cells
    has_long_text = False
    for row in all_rows:
        for cell in row:
            if len(cell) > 300 and "\n" not in cell[:200]:
                has_long_text = True
                break
        if has_long_text:
            break

    if has_long_text:
        if verbose:
            print(f"  ❌ Long text in cells - removing")
        return True

    # Count sentences
    sentence_count = 0
    for row in all_rows:
        for cell in row:
            sentences = re.findall(r"[.!?]\s+[A-Z]", cell)
            if len(sentences) > 2:
                sentence_count += 1

    if sentence_count > len(all_rows) * 0.3:
        if verbose:
            print(f"  ❌ Too many sentences ({sentence_count} cells) - removing")
        return True

    # Calculate indicators
    num_numeric_cells = count_numeric_cells(all_rows)
    num_financial_keywords = count_financial_keywords(all_rows)
    text_density = calculate_text_density(all_rows)
    has_num_headers = has_numeric_headers(headers)

    numeric_indicator_count = sum(
        len(pattern.findall(table_text)) for pattern in NUMERIC_TABLE_INDICATORS
    )

    # Scoring
    score = 0

    if num_numeric_cells > 3:
        score += 2
    if num_financial_keywords > 2:
        score += 2
    if has_num_headers:
        score += 3
    if numeric_indicator_count > 5:
        score += 2
    if text_density < 50:
        score += 1

    if text_density > 150:
        score -= 2
    if num_numeric_cells < 2:
        score -= 2
    if len(all_rows) < 3:
        score -= 1

    if verbose:
        print(f"  📊 Score: {score}")
        print(f"     - Separator: {max_separator} chars")
        print(f"     - Numeric cells: {num_numeric_cells}")
        print(f"     - Financial keywords: {num_financial_keywords}")
        print(f"     - Text density: {text_density:.1f}")
        print(f"     - Numeric headers: {has_num_headers}")
        print(f"     - Numeric indicators: {numeric_indicator_count}")
        print(f"  {'✅ KEEPING' if score > 0 else '❌ REMOVING'}")

    return score <= 0


def clean_matches(matches: List[str], verbose: bool = False) -> List[str]:
    """
    Filter out text-container tables from matches list and extract footnotes.
    """
    cleaned = []

    for i, match in enumerate(matches):
        if "<TABLE>" in match.upper():
            if verbose:
                print(f"\n🔍 Table {i+1}:")

            # Extract footnotes
            cleaned_table, footnotes = extract_and_separate_footnotes(match)

            # Check if numeric
            if not is_text_container_table(cleaned_table, verbose):
                cleaned.append(cleaned_table)
                cleaned.extend(footnotes)
                if verbose and not footnotes:
                    print(f"  ✅ Kept table (no footnotes)")
                elif verbose:
                    print(f"  ✅ Kept table + {len(footnotes)} footnotes")
            else:
                # Convert to plain text
                plain_text = strip_table_formatting(cleaned_table)

                if plain_text and len(plain_text) > 50:
                    cleaned.append(plain_text)
                    if verbose:
                        print(f"  🔄 Converted to paragraph ({len(plain_text)} chars)")

                if footnotes:
                    cleaned.extend(footnotes)
                    if verbose:
                        print(f"  📝 Kept {len(footnotes)} footnotes")
        else:
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
