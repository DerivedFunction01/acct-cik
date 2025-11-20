# =============================================================================
# Batch Summarization Script - Chunked Processing with Memory Efficiency
# =============================================================================
# %%
import pandas as pd
import requests
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import subprocess
from pathlib import Path
import multiprocessing as mp
import argparse
import psutil
from typing import List, Optional, Tuple
import sys


# =============================================================================
# CONFIGURATION
# =============================================================================

DB_PATH = "web_data.db"
REPORT_CSV_PATH = "./report_data.csv"
SERVER_BASE_URL = "http://127.0.0.1:5001"
DEBUG = False
CHUNK_SIZE = 20  # Reports per chunk (outer loop)
TEXT_SIZE = 8192 # How long the text should be
MAX_SIZE = 8192
SERVER_BATCH_SIZE = 8  # Should match server's BATCH_SIZE
MIN_CHUNKS_PER_CALL = 8  # Minimum chunks to send (to utilize server batch)
MAX_CHUNKS_PER_CALL = 64  # Maximum chunks per call (to avoid long waits)

# =============================================================================
# COLAB CONFIGURATION
# =============================================================================
DRIVE_PATH = "./drive/MyDrive/db"
LOAD_SHELL_CMD = f"cp -f {DRIVE_PATH}/{DB_PATH} ."
IS_COLAB = Path(DRIVE_PATH).exists()
DRIVE_SAVE_INTERVAL_SECONDS = 10 * 60
DRIVE_SAVE_INTERVAL_RESULTS = 100


def get_system_config():
    """Auto-detects client and server capabilities to set configuration."""
    cpu_cores = mp.cpu_count()
    client_ram_gb = psutil.virtual_memory().total / (1024**3)
    batch_size = SERVER_BATCH_SIZE
    text_size = TEXT_SIZE
    max_size = MAX_SIZE
    print(f"🖥️  Client System: {cpu_cores} CPU cores, {client_ram_gb:.2f} GB RAM")

    try:
        info_url = f"{SERVER_BASE_URL}/info"
        response = requests.get(info_url, timeout=5)
        response.raise_for_status()
        server_info = response.json()

        if server_info.get("gpu_available"):
            gpu_ram = server_info.get("total_ram_gb", 0)
            print(
                f"✅ Server has GPU: {server_info.get('gpu_name')} with {gpu_ram:.2f} GB RAM"
            )
        else:
            print("⚠️  Server has no GPU")
        if server_info.get("max_seq_length"):
            length = server_info.get("max_seq_length") # in tokens, so roughly 4 chars per token
            text_size = length * 4// 8
            max_size = length * 4 // 6
        if server_info.get("batch_size"):
            batch_size = server_info.get("batch_size")
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to server at {SERVER_BASE_URL}.")
        print(f"   Error: {e}")

    # Adjust CHUNK_SIZE based on client RAM
    if client_ram_gb > 32:
        chunk_multiplier = 2
    elif client_ram_gb > 16:
        chunk_multiplier = 1.5
    else:
        chunk_multiplier = 1

    adjusted_chunk_size = max(10, int(CHUNK_SIZE * chunk_multiplier))
    print(
        f"⚙️  Configuration: CHUNK_SIZE={adjusted_chunk_size}"
    )
    return adjusted_chunk_size, batch_size, text_size, max_size

CHUNK_SIZE, SERVER_BATCH_SIZE, TEXT_SIZE, MAX_SIZE = get_system_config()

if IS_COLAB:
    print("Running in Google Colab environment")
    if not Path(DB_PATH).exists():
        print("Loading database from Google Drive...")
        subprocess.run(LOAD_SHELL_CMD, shell=True)
else:
    print("Running in local environment")

# %%
# =============================================================================
# DEBUG UTILITIES
# =============================================================================


def debug_print(*args):
    global DEBUG
    if DEBUG:
        print(*args)


def format_time(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    elif minutes > 0:
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(seconds)}s"


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS stage1_summaries (
                url TEXT PRIMARY KEY,
                stage1_response TEXT,
                FOREIGN KEY (url) REFERENCES report_data (url)
            )
        """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_stage1_url ON stage1_summaries (url)")
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.IntegrityError:
        debug_print("Something went wrong creating the database")
    finally:
        conn.commit()
        conn.close()


def create_stage1_intermediate_table():
    """Creates the intermediate table for storing Stage 1 summarization results."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS stage1_summaries (
                url TEXT PRIMARY KEY,
                stage1_response TEXT,
                FOREIGN KEY (url) REFERENCES report_data (url)
            )
        """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_stage1_url ON stage1_summaries (url)")
        conn.commit()
    except sqlite3.Error as e:
        debug_print(f"Database error creating stage1_summaries table: {e}")
    finally:
        conn.close()


def get_chunks_for_summarization(limit: Optional[int] = None) -> pd.DataFrame:
    """
    Retrieves reports that have chunks in webpage_result but no summaries in stage1_summaries yet.

    Args:
        limit: Maximum number of reports to retrieve

    Returns:
        DataFrame with columns: url, cik, year
    """
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT DISTINCT
            wr.url,
            rd.cik,
            rd.year
        FROM webpage_result wr
        JOIN report_data rd ON wr.url = rd.url
        LEFT JOIN stage1_summaries s1 ON wr.url = s1.url
        WHERE s1.url IS NULL AND json_array_length(wr.matches) > 0
    """
    if limit:
        query += f" LIMIT {limit}"
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def get_processed_stage1_urls() -> set:
    """Return a set of URLs already processed in stage1_summaries."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url FROM stage1_summaries")
    rows = c.fetchall()
    conn.close()
    return set(url for (url,) in rows)


def save_stage1_summaries(url: str, summaries: List[str]):
    """Saves Stage 1 summarization results to the intermediate table."""
    if not summaries:
        debug_print(f"No summaries to save for {url}")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        summaries_json = json.dumps(summaries)
        c.execute(
            "INSERT OR REPLACE INTO stage1_summaries (url, stage1_response) VALUES (?, ?)",
            (url, summaries_json),
        )
        conn.commit()

    except sqlite3.Error as e:
        print(f"❌ Database error saving stage1 summaries for {url}: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_text_chunks_for_report(url: str, year: int) -> List[str]:
    global TEXT_SIZE  # Minimum size threshold for chunks
    global MAX_SIZE  # Maximum size cap for chunks
    """
    Fetch text chunks for a single report from the database.
    Returns empty list if no chunks found.
    Prepends the year to each chunk for temporal context.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT matches FROM webpage_result WHERE url=?", (url,))
        result = c.fetchone()

        if result and result[0]:
            matches = json.loads(result[0])
            if isinstance(matches, list) and matches:
                # Filter out any non-string or empty items first
                processed_chunks = [str(chunk).strip() for chunk in matches if isinstance(chunk, str) and str(chunk).strip()]
                if not processed_chunks:
                    return []

                merged_chunks = []
                buffer = ""
                year_prefix = f"Text({year}): "

                for chunk in processed_chunks:
                    # If adding the next chunk would exceed the max size,
                    # finalize the current buffer and start a new one.
                    if buffer and len(buffer) + 1 + len(chunk) > MAX_SIZE:
                        merged_chunks.append(buffer)
                        buffer = ""

                    # Add the chunk to the buffer, with a space if buffer is not empty.
                    if buffer:
                        buffer += " " + chunk
                    else:
                        buffer = chunk

                    # If the buffer is now "full" enough, finalize it.
                    if len(buffer) >= TEXT_SIZE:
                        merged_chunks.append(buffer)
                        buffer = ""

                # Don't forget to add the last buffer if it has content
                if buffer:
                    merged_chunks.append(buffer)

                return [year_prefix + chunk for chunk in merged_chunks]
    except (json.JSONDecodeError, TypeError, sqlite3.Error) as e:
        debug_print(f"⚠️ Could not process chunks for {url}: {e}")
    finally:
        conn.close()
    return []


def fetch_report_data(valid=True):
    try:
        return pd.read_csv(REPORT_CSV_PATH)
    except:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if valid:
            c.execute("SELECT * FROM report_data WHERE NOT url =''")
        else:
            c.execute("SELECT * FROM report_data WHERE url =''")
        columns = [col[0] for col in c.description]
        rows = c.fetchall()
        pre_data = pd.DataFrame(rows, columns=columns)
        conn.close()
        return pre_data


# =============================================================================
# SERVER COMMUNICATION
# =============================================================================


def batch_summarize_texts(text_chunks: List[str]) -> Tuple[List[str], str]:
    """
    Sends text chunks to the server in batches.

    Args:
        text_chunks: List of text strings to summarize

    Returns:
        Tuple of (summaries list, error message or empty string)
    """
    if not text_chunks:
        return [], "No text chunks provided"

    headers = {"Content-Type": "application/json"}
    all_summaries = []

    payload = {"texts": text_chunks}

    try:
        summarize_url = f"{SERVER_BASE_URL}/batch-summarize"
        response = requests.post(
            summarize_url, headers=headers, json=payload, timeout=600
        )
        response.raise_for_status()

        result = response.json()

        if result.get("success"):
            summaries = result.get("summaries", [])
            all_summaries.extend(summaries)
            print(f"✅", end="", flush=True)
        else:
            error_msg = result.get("error", "Unknown error from server")
            return [], f"Server Error: {error_msg}"

    except requests.exceptions.Timeout:
        return [], f"Timeout after 600s"
    except requests.exceptions.RequestException as e:
        return [], f"Network error: {str(e)}"
    except Exception as e:
        return [], f"Unexpected error: {str(e)}"

    print(" ✅")
    return all_summaries, ""


# =============================================================================
# CHUNKED PROCESSING (NESTED: Outer=Reports, Inner=Texts)
# =============================================================================


def process_report_batch(reports_batch: List) -> List[Tuple[str, List[str]]]:
    """
    Process a batch of reports with smart chunk accumulation.

    Strategy:
    - Accumulate chunks from multiple reports until we hit MIN_CHUNKS_PER_CALL
    - Don't exceed MAX_CHUNKS_PER_CALL to keep response times reasonable
    - Send accumulated chunks in a single server call
    - Track boundaries to split results back to individual reports

    Args:
        reports_batch: List of report namedtuples with (url, cik, year)

    Returns:
        List of (url, summaries) tuples
    """
    batch_results = []

    # Step 1: Fetch all reports and their chunks
    reports_with_chunks = []
    for report in reports_batch:
        text_chunks = get_text_chunks_for_report(report.url, report.year)
        if text_chunks:
            reports_with_chunks.append((report, text_chunks))
        else:
            # No chunks - add empty result immediately
            debug_print(f"⚠️  No text chunks for {report.url}, storing empty array")
            batch_results.append((report.url, []))

    if not reports_with_chunks:
        return batch_results

    # Step 2: Accumulate chunks intelligently
    accumulated_chunks = []
    accumulated_reports = []  # Track (url, start_idx, end_idx)

    for report, chunks in tqdm(
        reports_with_chunks, desc="  Processing reports", leave=False
    ):
        num_chunks = len(chunks)

        # Case 1: Single report has too many chunks - send it alone
        if num_chunks >= MAX_CHUNKS_PER_CALL:
            # First, flush any accumulated chunks
            if accumulated_chunks:
                summaries, error = batch_summarize_texts(accumulated_chunks)
                if not error and len(summaries) == len(accumulated_chunks):
                    for url, start_idx, end_idx in accumulated_reports:
                        batch_results.append((url, summaries[start_idx:end_idx]))
                else:
                    print(f"  ⚠️  Error processing accumulated batch: {error}")

                # Reset accumulator
                accumulated_chunks = []
                accumulated_reports = []

            # Send this large report alone
            summaries, error = batch_summarize_texts(chunks)
            if not error and len(summaries) == num_chunks:
                batch_results.append((report.url, summaries))
            else:
                print(f"  ⚠️  Error processing large report {report.url}: {error}")
            continue

        # Case 2: Adding this report would exceed MAX_CHUNKS_PER_CALL - flush first
        if (
            accumulated_chunks
            and len(accumulated_chunks) + num_chunks > MAX_CHUNKS_PER_CALL
        ):
            summaries, error = batch_summarize_texts(accumulated_chunks)
            if not error and len(summaries) == len(accumulated_chunks):
                for url, start_idx, end_idx in accumulated_reports:
                    batch_results.append((url, summaries[start_idx:end_idx]))
            else:
                print(f"  ⚠️  Error processing accumulated batch: {error}")

            # Reset accumulator
            accumulated_chunks = []
            accumulated_reports = []

        # Case 3: Accumulate this report
        start_idx = len(accumulated_chunks)
        accumulated_chunks.extend(chunks)
        end_idx = len(accumulated_chunks)
        accumulated_reports.append((report.url, start_idx, end_idx))

        # Case 4: If we've reached minimum threshold, consider sending
        if len(accumulated_chunks) >= MIN_CHUNKS_PER_CALL:
            summaries, error = batch_summarize_texts(accumulated_chunks)
            if not error and len(summaries) == len(accumulated_chunks):
                for url, start_idx, end_idx in accumulated_reports:
                    batch_results.append((url, summaries[start_idx:end_idx]))
            else:
                print(f"  ⚠️  Error processing accumulated batch: {error}")

            # Reset accumulator
            accumulated_chunks = []
            accumulated_reports = []

    # Step 3: Send any remaining accumulated chunks
    if accumulated_chunks:
        summaries, error = batch_summarize_texts(accumulated_chunks)
        if not error and len(summaries) == len(accumulated_chunks):
            for url, start_idx, end_idx in accumulated_reports:
                batch_results.append((url, summaries[start_idx:end_idx]))
        else:
            print(f"  ⚠️  Error processing final accumulated batch: {error}")

    return batch_results


def process_stage1_chunked(
    total_mega_chunks: int, chunk_index: int, min_chunk_size: int = 1
) -> Tuple[int, str]:
    """
    Process Stage 1 summarization with memory-efficient nested chunking.

    Outer loop: Process reports in CHUNK_SIZE batches
    Inner loop: Within each batch, send texts to server in SERVER_BATCH_SIZE sub-batches

    Args:
        total_mega_chunks: Number of machines/processes running in parallel
        chunk_index: Index of this machine's chunk (0-based)
        min_chunk_size: Minimum reports to process in this run

    Returns:
        Tuple of (total_processed, output_parquet_file)
    """
    output_parquet_file = f"stage1_summaries_chunk_{chunk_index}.parquet"
    resumed_urls = set()
    all_chunk_results = []

    # --- Resume Logic ---
    if Path(output_parquet_file).exists():
        print(
            f"🔄 Found existing output file '{output_parquet_file}'. Resuming session."
        )
        try:
            resume_df = pd.read_parquet(output_parquet_file)
            resumed_urls = set(resume_df["url"])
            all_chunk_results = resume_df.to_dict("records")
            print(
                f"   -> Loaded {len(resumed_urls)} previously processed URLs to skip."
            )
        except Exception as e:
            print(f"   ⚠️  Could not read resume file, starting fresh. Error: {e}")
            all_chunk_results = []

    # Get URLs already processed in the database
    db_processed_urls = get_processed_stage1_urls()
    processed_set = db_processed_urls.union(resumed_urls)

    # Find reports to process
    reports_to_process_df = get_chunks_for_summarization()
    reports_to_process_df = reports_to_process_df[
        ~reports_to_process_df["url"].isin(processed_set)
    ]

    # --- Mega-chunk splitting for parallel processing ---
    if total_mega_chunks > 1:
        print(
            f"\nSplitting workload into {total_mega_chunks} mega-chunks. This machine will process index {chunk_index}."
        )
        num_reports = len(reports_to_process_df)
        mega_chunk_size = (num_reports + total_mega_chunks - 1) // total_mega_chunks
        start_index = chunk_index * mega_chunk_size
        end_index = start_index + mega_chunk_size

        reports_to_process_df = reports_to_process_df.iloc[start_index:end_index]
        print(
            f"  -> This machine's workload: {len(reports_to_process_df)} reports (from index {start_index} to {end_index})."
        )

    reports_to_process = list(reports_to_process_df.itertuples(index=False))

    total_reports = len(reports_to_process)
    print(f"Processing {total_reports:,} new reports")
    print(f"Already processed: {len(processed_set):,} reports")

    # Check minimum chunk size
    if total_reports < min_chunk_size:
        print(
            f"Skipping run: Found {total_reports} reports, which is less than the minimum of {min_chunk_size}."
        )
        if Path(output_parquet_file).exists():
            Path(output_parquet_file).unlink()
        return 0, ""

    # Create outer chunks of reports
    report_chunks = [
        reports_to_process[i : i + CHUNK_SIZE]
        for i in range(0, total_reports, CHUNK_SIZE)
    ]

    print(f"\nProcessing in {len(report_chunks)} chunks of {CHUNK_SIZE} reports each")
    print("=" * 70)

    chunk_times = []
    total_time = 0
    total_saved = 0

    last_drive_save_time = time.time()
    results_since_last_save = 0

    for chunk_idx, report_batch in enumerate(report_chunks, 1):
        start_chunk_time = time.time()
        print(
            f"\n📦 Report Chunk {chunk_idx}/{len(report_chunks)} ({len(report_batch)} reports)"
        )

        # Process this batch of reports
        # Each report's texts are fetched and sent to server in SERVER_BATCH_SIZE chunks
        batch_results = process_report_batch(report_batch)

        # Save results from this batch
        for url, summaries in batch_results:
            all_chunk_results.append(
                {
                    "url": url,
                    "stage1_response": json.dumps(summaries),
                }
            )
            total_saved += 1
            results_since_last_save += 1

        # Periodically save accumulated results to parquet
        if all_chunk_results:
            pd.DataFrame(all_chunk_results).to_parquet(output_parquet_file)
            debug_print(
                f"  -> Saved {len(all_chunk_results)} results to '{output_parquet_file}'"
            )

        chunk_time = time.time() - start_chunk_time
        chunk_times.append(chunk_time)
        total_time += chunk_time

        # Calculate statistics
        avg_chunk_time = sum(chunk_times) / len(chunk_times)
        remaining_chunks = len(report_chunks) - chunk_idx
        est_time_remaining = avg_chunk_time * remaining_chunks

        time_since_last_save = time.time() - last_drive_save_time
        if IS_COLAB and (
            time_since_last_save >= DRIVE_SAVE_INTERVAL_SECONDS
            or results_since_last_save >= DRIVE_SAVE_INTERVAL_RESULTS
        ):
            print(f"  -> Saving to Google Drive...")
            save_cmd = f"cp -f {output_parquet_file} {DRIVE_PATH}/{output_parquet_file}.tmp && mv -f {DRIVE_PATH}/{output_parquet_file}.tmp {DRIVE_PATH}/{output_parquet_file}"
            subprocess.run(
                save_cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            last_drive_save_time = time.time()
            results_since_last_save = 0

        print(f"  ✓ Saved {len(batch_results)} reports")
        print(f"  Time taken: {format_time(chunk_time)}")
        print(f"  Avg chunk time: {format_time(avg_chunk_time)}")
        print(f"  Est. time remaining: {format_time(est_time_remaining)}")
        print(f"  Total time: {format_time(total_time)}")
        print(
            f"  📊 Overall: {total_saved:,}/{total_reports:,} ({(total_saved/total_reports)*100:.1f}% complete)"
        )

    # Final save
    if all_chunk_results:
        pd.DataFrame(all_chunk_results).to_parquet(output_parquet_file)

    print("\n" + "=" * 70)
    print(f"🎉 FINAL RESULTS:")
    print(f"  ✓ Successfully saved: {total_saved:,} reports")
    print("=" * 70)

    return total_saved, output_parquet_file


def finalize_stage1_results(chunk_files: List[str]):
    """
    After all chunks are processed, merge parquet files and save to database.

    Args:
        chunk_files: List of parquet file paths from all chunks
    """
    print("\n" + "=" * 70)
    print("🔄 FINALIZING STAGE 1 RESULTS")
    print("=" * 70)

    all_results = []
    for chunk_file in chunk_files:
        if Path(chunk_file).exists():
            try:
                df = pd.read_parquet(chunk_file)
                all_results.append(df)
                print(f"✅ Loaded {len(df)} results from {chunk_file}")
            except Exception as e:
                print(f"❌ Error reading {chunk_file}: {e}")

    if not all_results:
        print("No results to finalize.")
        return

    # Merge all results
    merged_df = pd.concat(all_results, ignore_index=True)
    print(f"\n📊 Total results to save: {len(merged_df)}")

    # Save to database
    print("💾 Saving results to database...")
    for _, row in tqdm(merged_df.iterrows(), total=len(merged_df), desc="Saving to DB"):
        summaries = json.loads(row["stage1_response"])
        save_stage1_summaries(row["url"], summaries)

    print(f"✅ All {len(merged_df)} results saved to database!")
    print("=" * 70)


# =============================================================================
# MAIN EXECUTION
# =============================================================================


def run_classification(total_chunks=1, chunk_index=0):
    """The main summarization loop with memory-efficient chunked processing."""
    is_first_run = True
    try:
        # Initialize database schema
        create_db()
        create_stage1_intermediate_table()

        # Set minimum chunk size
        min_size_for_run = 1 if is_first_run else 20

        print("\n" + "=" * 70)
        print("🚀 STAGE 1: BATCH SUMMARIZATION (MEMORY-EFFICIENT)")
        print("=" * 70)

        (
            total_processed,
            output_file,
        ) = process_stage1_chunked(
            total_mega_chunks=total_chunks,
            chunk_index=chunk_index,
            min_chunk_size=min_size_for_run,
        )

        if total_processed > 0:
            print(f"\n✅ Run complete. Processed {total_processed} new reports.")
            if total_chunks > 1:
                print(f"   Results for this chunk saved to: {output_file}")
                print(
                    f"   After all chunks complete, merge files with finalize_stage1_results()"
                )
        else:
            print("\n⚠️  No reports were processed in this run.")

    except KeyboardInterrupt:
        print("\n\n🛑 Service stopped by user.")
    finally:
        print("=" * 70)
        print("All done! 👋")
        print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # --- Command-Line Mode ---
        parser = argparse.ArgumentParser(
            description="Run Stage 1 batch summarization in chunked mode."
        )
        parser.add_argument(
            "--total-chunks",
            type=int,
            default=1,
            help="Total number of mega-chunks to split the workload into.",
        )
        parser.add_argument(
            "--chunk-index",
            type=int,
            default=0,
            help="The index of the mega-chunk this instance should process (0-based).",
        )
        parser.add_argument(
            "--finalize",
            action="store_true",
            help="Finalize results from all chunks (merge parquet files to database).",
        )
        parser.add_argument(
            "--chunk-files",
            type=str,
            nargs="+",
            help="List of parquet files to finalize.",
        )
        args = parser.parse_args()

        print("=" * 70)
        if args.finalize:
            print("🚀 Finalizing Stage 1 Results")
            print("=" * 70)
            chunk_files = args.chunk_files or [
                f"stage1_summaries_chunk_{i}.parquet" for i in range(args.total_chunks)
            ]
            finalize_stage1_results(chunk_files)
        else:
            if args.total_chunks > 1:
                print("🚀 Starting Stage 1 (Chunked Mode)")
                print(
                    f"   Will process chunk {args.chunk_index} of {args.total_chunks} and then exit."
                )
            else:
                print("🚀 Starting Stage 1 (Standalone Mode)")
            print("=" * 70)
            run_classification(args.total_chunks, args.chunk_index)
    else:
        # --- Interactive Mode ---
        while True:
            print("\n" + "=" * 70)
            print("🚀 Batch Summarization Menu")
            print("=" * 70)
            print("  1. Run in Standalone Mode")
            print("  2. Run in Chunked Mode (for parallel processing)")
            print("  3. Toggle Debug Mode")
            print("  4. Exit")
            choice = input("Enter your choice (1-4): ").strip()

            if choice == "1":
                run_classification(total_chunks=1, chunk_index=0)
                break
            elif choice == "2":
                try:
                    total_chunks = int(input("   Enter total number of chunks: "))
                    chunk_index = int(
                        input(
                            f"   Enter this machine's chunk index (0 to {total_chunks - 1}): "
                        )
                    )
                    if not (0 <= chunk_index < total_chunks):
                        print("   ❌ Error: Chunk index is out of range.")
                        continue
                    run_classification(total_chunks, chunk_index)
                    break
                except ValueError:
                    print("   ❌ Error: Please enter valid numbers.")
            elif choice == "3":
                DEBUG = not DEBUG
                print(f"Debug mode is now {'on' if DEBUG else 'off'}.")
            elif choice == "4":
                print("Exiting.")
                break
            else:
                print("Invalid choice. Please try again.")
