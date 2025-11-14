# =============================================================================
# Model Classification Script - Chunked Processing
# =============================================================================
# %%
import pandas as pd
import requests
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from tqdm import tqdm
from collections import Counter
import subprocess
from pathlib import Path
import multiprocessing as mp
import argparse
import psutil
import sys


# =============================================================================
# CONFIGURATION
# =============================================================================

DB_PATH = "web_data.db"
REPORT_CSV_PATH = "./report_data.csv"
SERVER_BASE_URL = "http://127.0.0.1:5000"
DEBUG = False  # Debug printing
CHUNK_SIZE = 20  # Base chunk size, will be adjusted based on RAM
TEXT_SIZE = 3000  # Maximum number of chars a select text (the model will perform deep reasoning, and we want to prevent attention dropoff)

# =============================================================================
# COLAB CONFIGURATION
# =============================================================================
DRIVE_PATH = "./drive/MyDrive/db"
LOAD_SHELL_CMD = f"cp -f {DRIVE_PATH}/{DB_PATH} ."
IS_COLAB = Path(DRIVE_PATH).exists()
DRIVE_SAVE_INTERVAL_SECONDS = 10 * 60  # 10 minutes
DRIVE_SAVE_INTERVAL_RESULTS = 100

def get_system_config():
    """Auto-detects client and server capabilities to set configuration."""
    cpu_cores = mp.cpu_count()
    client_ram_gb = psutil.virtual_memory().total / (1024**3)

    print(f"🖥️  Client System: {cpu_cores} CPU cores, {client_ram_gb:.2f} GB RAM")

    # Query server for GPU info to determine NUM_THREADS
    try:
        info_url = f"{SERVER_BASE_URL}/info"
        response = requests.get(info_url, timeout=5)
        response.raise_for_status()
        server_info = response.json()

        if server_info.get("gpu_available"):
            gpu_ram = server_info.get("total_ram_gb", 0)
            print(f"✅ Server has GPU: {server_info.get('gpu_name')} with {gpu_ram:.2f} GB RAM")
            # Scale threads based on GPU RAM. More RAM can handle more concurrent requests.
            if gpu_ram > 20:  # A100, etc.
                num_threads = 5
            elif gpu_ram > 14: # T4, P100
                num_threads = 3
            elif gpu_ram > 6: # Smaller GPUs
                num_threads = 2
            else:
                num_threads = 1
        else:
            print("⚠️  Server has no GPU, defaulting to CPU-based threading")
            num_threads = 1
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to server at {SERVER_BASE_URL}. Defaulting to CPU-based thread count.")
        print(f"   Error: {e}")
        num_threads = cpu_cores # Fallback if server is down, use client's cores as a guess

    if client_ram_gb > 32:
        chunk_multiplier = 10  # High-RAM machine
    elif client_ram_gb > 16:
        chunk_multiplier = 5  # Medium-RAM machine
    elif client_ram_gb > 8:
        chunk_multiplier = 2  # Standard machine
    else:
        chunk_multiplier = 1  # Low-RAM machine

    chunk_size = min(10, CHUNK_SIZE * chunk_multiplier * cpu_cores)
    print(f"⚙️  Configuration: NUM_THREADS={num_threads}, CHUNK_SIZE={chunk_size}")
    return num_threads, chunk_size

NUM_THREADS, CHUNK_SIZE = get_system_config()

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
            CREATE TABLE IF NOT EXISTS server_result (
                url TEXT PRIMARY KEY,
                server_response TEXT,
                FOREIGN KEY (url) REFERENCES report_data (url)
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS fail_results (
                cik INTEGER,
                year INTEGER,
                url TEXT PRIMARY KEY
            )
        """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS url_idx ON server_result (url)
            """
        )
        # WAL
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.IntegrityError:
        debug_print("Something went wrong creating the database")
    finally:
        conn.commit()
        conn.close()


def cleanup_error_responses():
    """Removes records from server_result where the response indicates an error."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # The server now returns JSON objects like {"error": "network_error"}
        # We can search for the substring '"error":' to find these.
        sql = "DELETE FROM server_result WHERE server_response LIKE '%\"error\":%'"
        c.execute(sql)
        rows_deleted = c.rowcount
        conn.commit()
        if rows_deleted > 0:
            print(f"🧹 Cleaned up {rows_deleted} error responses from the database.")
    finally:
        conn.close()


def get_matches(url):
    """
    Fetch matches from webpage_result, which has (url, matches).
    Return: a list
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM webpage_result WHERE url=?", (url,))
    columns = [col[0] for col in c.description]
    result = c.fetchone()
    conn.close()
    if not result:
        return []
    data = pd.DataFrame([result], columns=columns)    
    try:
        # Load the matches, an array
        categorized_matches = json.loads(data.matches.iloc[0])
        if isinstance(categorized_matches, list):
            return categorized_matches
        else:
            return [] # Return empty list if it is not a list
    except (json.JSONDecodeError, IndexError):
        return []

def get_unprocessed_reports() -> pd.DataFrame:
    """
    Finds reports that are in webpage_result but not yet in server_result.
    It joins with report_data to get the necessary 'year' for processing.
    """
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT
            rd.cik,
            rd.year,
            wr.url
        FROM webpage_result wr
        JOIN report_data rd ON wr.url = rd.url
        LEFT JOIN server_result sr ON wr.url = sr.url
        WHERE sr.url IS NULL;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def fetch_server_results():
    """
    Fetch results from server_result
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM server_result")
    columns = [col[0] for col in c.description]
    rows = c.fetchall()
    pre_data = pd.DataFrame(rows, columns=columns)
    conn.close()
    return pre_data


def get_processed_server_urls() -> set:
    """
    Return a set of URLs that are already processed in `server_result`.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url FROM server_result")
    rows = c.fetchall()
    conn.close()
    return set(url for (url,) in rows)


def save_process_result(df):
    """
    Inserts a new item into the server_result table
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR REPLACE INTO server_result (url, server_response) VALUES (?, ?)",
            (df.url, json.dumps(df.server_response)),
        )
    except sqlite3.Error as e:
        debug_print(f"DB error on {df.url}: {e}")
        # Get cik and year from report_data for fail_results
        c.execute("SELECT cik, year FROM report_data WHERE url=?", (df.url,))
        result = c.fetchone()
        if result:
            cik, year = result
            c.execute(
                "INSERT OR IGNORE INTO fail_results (cik, year, url) VALUES (?, ?, ?)",
                (cik, year, df.url),
            )

    conn.commit()
    conn.close()


def save_batch_results(results_buffer):
    """
    Batch insert multiple results into the server_result table
    """
    if not results_buffer:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    success_count = 0
    fail_count = 0

    try:
        # Prepare batch data
        batch_data = []
        fail_data = []

        for result in results_buffer:
            try:
                batch_data.append((result.url, json.dumps(result.server_response)))
            except Exception as e:
                debug_print(f"Error preparing data for {result.url}: {e}")
                # Get cik and year from report_data for fail_results
                c.execute(
                    "SELECT cik, year FROM report_data WHERE url=?", (result.url,)
                )
                db_result = c.fetchone()
                if db_result:
                    cik, year = db_result
                    fail_data.append((cik, year, result.url))
                fail_count += 1

        # Batch insert successful results
        if batch_data:
            c.executemany(
                "INSERT OR REPLACE INTO server_result (url, server_response) VALUES (?, ?)",
                batch_data,
            )
            success_count = len(batch_data)

        # Batch insert failures
        if fail_data:
            c.executemany(
                "INSERT OR IGNORE INTO fail_results (cik, year, url) VALUES (?, ?, ?)",
                fail_data,
            )

        conn.commit()
        debug_print(f"Batch saved: {success_count} success, {fail_count} failures")

    except sqlite3.Error as e:
        print(f"Batch DB error: {e}")
        conn.rollback()
    finally:
        conn.close()

    return success_count, fail_count


def fetch_report_data(valid=True):
    global REPORT_CSV_PATH
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


def get_result_from_server(text_chunk: str) -> dict:
    """
    Sends a single text chunk to the model server and returns the generated JSON.
    This replaces the old batch-based function.
    """
    headers = {"Content-Type": "application/json"}
    # The new server expects a 'prompt' key, not 'texts'
    payload = {"prompt": text_chunk}
    try:
        # The new server endpoint is /generate
        predict_url = f"{SERVER_BASE_URL}/generate"
        response = requests.post(predict_url, headers=headers, data=json.dumps(payload), timeout=300)
        response.raise_for_status()
        # The server returns a dictionary with a 'prediction' key
        return response.json().get("prediction", {})
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with server: {e}")
        # Return a consistent error object for network or other request errors
        return {"error": "network_error", "details": str(e)}


def process_report_fully(report):
    """
    Processes a single report completely:
    1. Gets matches from the database.
    2. Gets analysis from the server for those sentences from `matches`.
    3. Returns the result (does NOT save to database immediately).
    """
    # Get the report's `matches`
    original_matches = get_matches(report.url)
    all_predictions = []

    if original_matches:
        # This logic creates larger, semantically grouped chunks of text.
        # It combines consecutive paragraphs until the TEXT_SIZE limit is approached.
        text_chunks = []
        current_chunk = ""
        year_prefix = f"Incomplete Text ({report.year}): "

        for match in original_matches:
            # If adding the next match would exceed the size, save the current chunk and start a new one.
            if len(current_chunk) + len(match) + len(year_prefix) > TEXT_SIZE:
                if current_chunk: # Ensure we don't add empty chunks
                    text_chunks.append(year_prefix + current_chunk)
                current_chunk = match
            else:
                # Add a newline for readability between concatenated paragraphs.
                if current_chunk:
                    current_chunk += "\n" + match
                else:
                    current_chunk = match
        
        # Add the last remaining chunk
        if current_chunk:
            text_chunks.append(year_prefix + current_chunk)

        # The server expects one prompt at a time. Since we have multiple chunks,
        # we'll get one prediction for each. The ThreadPoolExecutor in the main
        # loop will handle running these requests in parallel.
        if text_chunks:
            # For each chunk, create a dictionary containing both the prompt and the prediction.
            # This provides full context for later analysis and debugging.
            all_predictions = [
                {"prompt": chunk, "prediction": get_result_from_server(chunk)}
                for chunk in text_chunks
            ]

    # The server_response will be a list of JSON objects, one for each chunk processed.
    # Prepare the final result row (return, don't save yet)
    result_row = pd.Series(
        {
            "url": report.url,
            "server_response": all_predictions,
        }
    )

    return result_row


# =============================================================================
# CHUNKED PROCESSING
# =============================================================================


def process_reports_in_chunks(
    total_mega_chunks: int, chunk_index: int, min_chunk_size: int = 1
) -> tuple[int, int, str]:
    """Process reports in chunks with periodic saves and statistics."""
    output_parquet_file = f"server_result_chunk_{chunk_index}.parquet"
    resumed_urls = set()
    all_chunk_results = []  # This will hold results from the current run.

    # --- Resume Logic ---
    # Check if an intermediate parquet file exists from a previous, interrupted run.
    if Path(output_parquet_file).exists():
        print(f"🔄 Found existing output file '{output_parquet_file}'. Resuming session.")
        try:
            resume_df = pd.read_parquet(output_parquet_file)
            resumed_urls = set(resume_df["url"])
            all_chunk_results = resume_df.to_dict("records")
            print(f"   -> Loaded {len(resumed_urls)} previously processed URLs to skip.")
        except Exception as e:
            print(f"   ⚠️  Could not read resume file, starting fresh. Error: {e}")
            # If file is corrupt, start over.
            all_chunk_results = []

    # Get URLs that are already fully processed and stored in the main database.
    db_processed_urls = get_processed_server_urls()
    processed_set = db_processed_urls.union(resumed_urls)

    # Find reports in webpage_result that are not yet in server_result
    reports_to_process_df = get_unprocessed_reports()
    reports_to_process_df = reports_to_process_df[~reports_to_process_df['url'].isin(processed_set)]
    # =========================================================================
    # NEW: Splitting the workload into mega-chunks for parallel processing
    # =========================================================================
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

    # Check if the number of reports meets the minimum chunk size
    if total_reports < min_chunk_size:
        print(f"Skipping run: Found {total_reports} reports, which is less than the minimum of {min_chunk_size}.")
        # If a parquet file exists from a previous run, remove it to avoid stale data
        if Path(output_parquet_file).exists():
            Path(output_parquet_file).unlink()
        return 0, 0, ""

    # Create chunks
    chunks = [
        reports_to_process[i : i + CHUNK_SIZE]
        for i in range(0, total_reports, CHUNK_SIZE)
    ]

    print(f"\nProcessing in {len(chunks)} chunks of {CHUNK_SIZE} reports each")
    print("=" * 70)

    chunk_times = []
    total_time = 0
    total_results = 0
    total_empty = 0

    last_drive_save_time = time.time()
    results_since_last_save = 0

    for chunk_idx, chunk in enumerate(chunks, 1):
        start_chunk_time = time.time()
        print(f"\n📦 Chunk {chunk_idx}/{len(chunks)} ({len(chunk)} reports)")

        chunk_results = 0
        chunk_empty = 0

        # Process chunk with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            future_to_report = {
                executor.submit(process_report_fully, r): r for r in chunk
            }

            for future in tqdm(
                as_completed(future_to_report),
                total=len(future_to_report),
                desc=f"  Processing chunk {chunk_idx}",
                leave=False,
            ):
                try:
                    res = future.result()
                    if res is not None:
                        chunk_results += 1
                        # Append result dictionary to the main list
                        all_chunk_results.append(res.to_dict())
                    else:
                        chunk_empty += 1
                except Exception as e:
                    debug_print(f"Error processing {future_to_report[future].url}: {e}")
                    chunk_empty += 1

        # Periodically save the accumulated results to the parquet file
        # This ensures progress is not lost on large runs.
        # The file will be overwritten with the complete data up to this point.
        if all_chunk_results:
            pd.DataFrame(all_chunk_results).to_parquet(output_parquet_file)
            print(f"  -> Saved {len(all_chunk_results)} results to '{output_parquet_file}'")

        chunk_time = time.time() - start_chunk_time
        chunk_times.append(chunk_time)
        total_time += chunk_time
        total_results += chunk_results
        total_empty += chunk_empty
        results_since_last_save += chunk_results

        # Calculate statistics
        avg_chunk_time = sum(chunk_times) / len(chunk_times)
        remaining_chunks = len(chunks) - chunk_idx
        est_time_remaining = avg_chunk_time * remaining_chunks

        time_since_last_save = time.time() - last_drive_save_time
        if IS_COLAB and (
            time_since_last_save >= DRIVE_SAVE_INTERVAL_SECONDS
            or results_since_last_save >= DRIVE_SAVE_INTERVAL_RESULTS
        ):
            print(f"  -> Saving to Google Drive...")
            # Dynamically create the save command for the current parquet file
            save_cmd = f"cp -f {output_parquet_file} {DRIVE_PATH}/{output_parquet_file}.tmp && mv -f {DRIVE_PATH}/{output_parquet_file}.tmp {DRIVE_PATH}/{output_parquet_file}"
            subprocess.run(
                save_cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            last_drive_save_time = time.time()
            results_since_last_save = 0

        print(f"  ✓ Processed {chunk_results} reports successfully")
        print(f"  ✗ Empty/failed: {chunk_empty} reports")
        print(f"  Time taken: {format_time(chunk_time)}")
        print(f"  Avg chunk time: {format_time(avg_chunk_time)}")
        print(f"  Est. time remaining: {format_time(est_time_remaining)}")
        print(f"  Total time: {format_time(total_time)}")

        # Progress summary
        processed_so_far = chunk_idx * CHUNK_SIZE
        percent_complete = (processed_so_far / total_reports) * 100
        print(
            f"  📊 Overall: {total_results:,}/{min(processed_so_far, total_reports):,} ({percent_complete:.1f}% complete)"
        )

    # Final save of all results for this mega-chunk
    if all_chunk_results:
        pd.DataFrame(all_chunk_results).to_parquet(output_parquet_file)

    print("\n" + "=" * 70)
    print(f"🎉 FINAL RESULTS:")
    print(f"  ✓ Successfully processed: {total_results:,} reports")
    print(f"  ✗ Empty/failed: {total_empty:,} reports")
    if total_results + total_empty > 0:
        print(
            f"  📈 Success rate: {(total_results/(total_results+total_empty)*100):.1f}%"
        )
    print("=" * 70)

    return total_results, len(chunks), output_parquet_file


# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
def run_classification(total_chunks=1, chunk_index=0):
    """The main classification loop."""
    is_first_run = True
    try:
        while True:
            # Initialize database schema if it doesn't exist
            create_db()

            # Set minimum chunk size. On first run, process anything available.
            # On subsequent runs, wait for at least 20 reports to accumulate.
            min_size_for_run = 1 if is_first_run else 20

            # The process_reports_in_chunks function now finds unprocessed reports and
            # filters them based on the chunk index.
            (
                total_processed_in_run,
                _,
                output_file,
            ) = process_reports_in_chunks(
                total_mega_chunks=total_chunks,
                chunk_index=chunk_index,
                min_chunk_size=min_size_for_run,
            )

            if total_processed_in_run > 0:
                print(
                    f"\n✅ Run complete. Processed {total_processed_in_run} new reports."
                )
                if total_chunks > 1:
                    print(f"   Results for this chunk saved to: {output_file}")
            elif total_chunks == 1:
                # If no reports were processed in standalone mode, wait before checking again.
                wait_time = 60 * 5  # 5 minutes
                print(f"\nNo new reports to process. Waiting for {wait_time} seconds...")
                time.sleep(wait_time)

            # Cleanup error responses after every loop (successful or not)
            cleanup_error_responses()
            is_first_run = False  # Subsequent runs are not the first run

            # If running in chunked mode, exit after the first run.
            if total_chunks > 1:
                print("\nChunk processing complete. Exiting.")
                break

    except KeyboardInterrupt:
        print("\n\n🛑 Service stopped by user.")
    finally:
        print("=" * 70)
        print("All done! 👋")
        print("=" * 70)


if __name__ == "__main__":
    # Check if command-line arguments were provided
    if len(sys.argv) > 1:
        # --- Command-Line Mode ---
        parser = argparse.ArgumentParser(
            description="Run the classification script in standalone or chunked mode for parallel processing."
        )
        parser.add_argument(
            "--total-chunks",
            type=int,
            default=1,
            help="Total number of mega-chunks to split the workload into (e.g., number of PCs).",
        )
        parser.add_argument(
            "--chunk-index",
            type=int,
            default=0,
            help="The index of the mega-chunk this instance should process (0-based).",
        )
        args = parser.parse_args()
        print("=" * 70)
        if args.total_chunks > 1:
            print("🚀 Starting Model Classification Service (Chunked Mode)")
            print(f"   Will process chunk {args.chunk_index} of {args.total_chunks} and then exit.")
        else:
            print("🚀 Starting Model Classification Service (Standalone Mode)")
            print("   This script will run continuously, checking for new data to classify.")
            print("   Press Ctrl+C to stop.")
        print("=" * 70)
        run_classification(args.total_chunks, args.chunk_index)
    else:
        # --- Interactive Mode ---
        while True:
            print("\n" + "=" * 70)
            print("🚀 Model Classification Service Menu")
            print("=" * 70)
            print("  1. Run in Standalone Mode (continuous)")
            print("  2. Run in Chunked Mode (for parallel processing)")
            print("  3. Exit")
            choice = input("Enter your choice (1-3): ").strip()

            if choice == "1":
                print("\n🚀 Starting Model Classification Service (Standalone Mode)")
                print("   This script will run continuously, checking for new data to classify.")
                print("   Press Ctrl+C to stop.")
                print("=" * 70)
                run_classification(total_chunks=1, chunk_index=0)
                break # Exit menu after standalone run finishes
            elif choice == "2":
                try:
                    total_chunks = int(input("   Enter total number of chunks (e.g., 2 for 2 PCs): "))
                    chunk_index = int(input(f"   Enter this machine's chunk index (0 to {total_chunks - 1}): "))
                    if not (0 <= chunk_index < total_chunks):
                        print("   ❌ Error: Chunk index is out of range.")
                        continue
                    
                    print("\n🚀 Starting Model Classification Service (Chunked Mode)")
                    print(f"   Will process chunk {chunk_index} of {total_chunks} and then exit.")
                    print("=" * 70)
                    run_classification(total_chunks, chunk_index)
                    break # Exit menu after chunked run finishes
                except ValueError:
                    print("   ❌ Error: Please enter valid numbers for chunks.")
            elif choice == "3":
                print("Exiting.")
                break
            else:
                print("Invalid choice. Please try again.")
