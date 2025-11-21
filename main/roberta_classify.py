# =============================================================================
# Model Classification Script - Chunked Processing (Single-Label)
# =============================================================================
import pandas as pd
import requests
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
DEBUG = False
CHUNK_SIZE = 100
DRIVE_SAVE_INTERVAL_SECONDS = 10 * 60
DRIVE_SAVE_INTERVAL_RESULTS = 4000

# =============================================================================
# COLAB CONFIGURATION
# =============================================================================
DRIVE_PATH = "./drive/MyDrive/db"
LOAD_SHELL_CMD = f"cp -f {DRIVE_PATH}/{DB_PATH} ."
IS_COLAB = Path(DRIVE_PATH).exists()


def get_system_config():
    """Auto-detects client and server capabilities to set configuration."""
    cpu_cores = mp.cpu_count()
    client_ram_gb = psutil.virtual_memory().total / (1024**3)

    print(f"🖥️  Client System: {cpu_cores} CPU cores, {client_ram_gb:.2f} GB RAM")

    try:
        info_url = f"{SERVER_BASE_URL}/info"
        response = requests.get(info_url, timeout=5)
        response.raise_for_status()
        server_info = response.json()

        if server_info.get("gpu_available"):
            gpu_ram = server_info.get("gpu_memory_gb", 0)
            print(
                f"✅ Server has GPU: {server_info.get('gpu_name')} with {gpu_ram:.2f} GB RAM"
            )
            if gpu_ram > 20:
                num_threads = 20
            elif gpu_ram > 14:
                num_threads = 8
            elif gpu_ram > 6:
                num_threads = 4
            else:
                num_threads = 2
        else:
            print("⚠️  Server has no GPU, defaulting to CPU-based threading")
            server_cpu_cores = server_info.get("cpu_cores", cpu_cores)
            num_threads = min(1, server_cpu_cores // 8 if server_cpu_cores > 8 else 1)
    except requests.exceptions.RequestException as e:
        print(
            f"❌ Could not connect to server at {SERVER_BASE_URL}. Defaulting to CPU-based thread count."
        )
        print(f"   Error: {e}")
        num_threads = cpu_cores

    if client_ram_gb > 32:
        chunk_multiplier = 10
    elif client_ram_gb > 16:
        chunk_multiplier = 5
    elif client_ram_gb > 8:
        chunk_multiplier = 2
    else:
        chunk_multiplier = 1

    chunk_size = min(10000, CHUNK_SIZE * chunk_multiplier * cpu_cores)
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
        sql = "DELETE FROM server_result WHERE server_response LIKE '%\"error\":%'"
        c.execute(sql)
        rows_deleted = c.rowcount
        conn.commit()
        if rows_deleted > 0:
            print(f"🧹 Cleaned up {rows_deleted} error responses from the database.")
    finally:
        conn.close()


def get_matches(url):
    """Fetch matches from webpage_result. Returns a list of sentences."""
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
        categorized_matches = json.loads(data.matches.iloc[0])

        if isinstance(categorized_matches, dict):
            flattened_sentences = []
            for category_sentences in categorized_matches.values():
                if isinstance(category_sentences, list):
                    flattened_sentences.extend(category_sentences)
            return flattened_sentences
        elif isinstance(categorized_matches, list):
            return categorized_matches
        else:
            return []
    except (json.JSONDecodeError, IndexError):
        return []


def get_unprocessed_reports() -> pd.DataFrame:
    """Finds reports in webpage_result not yet in server_result."""
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


def get_processed_server_urls() -> set:
    """Return a set of URLs already processed in `server_result`."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url FROM server_result")
    rows = c.fetchall()
    conn.close()
    return set(url for (url,) in rows)


def save_batch_results(results_buffer):
    """Batch insert multiple results into the server_result table."""
    if not results_buffer:
        return 0, 0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    success_count = 0
    fail_count = 0

    try:
        batch_data = []
        fail_data = []

        for result in results_buffer:
            try:
                batch_data.append((result.url, json.dumps(result.server_response)))
            except Exception as e:
                debug_print(f"Error preparing data for {result.url}: {e}")
                c.execute(
                    "SELECT cik, year FROM report_data WHERE url=?", (result.url,)
                )
                db_result = c.fetchone()
                if db_result:
                    cik, year = db_result
                    fail_data.append((cik, year, result.url))
                fail_count += 1

        if batch_data:
            c.executemany(
                "INSERT OR REPLACE INTO server_result (url, server_response) VALUES (?, ?)",
                batch_data,
            )
            success_count = len(batch_data)

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


def get_result_from_server(sentences, batch_size=128):
    """Send sentences to server and get single-label predictions."""
    predictions = []
    headers = {"Content-Type": "application/json"}

    for i in range(0, len(sentences), batch_size):
        batch = sentences[i : i + batch_size]
        payload = {"texts": batch}
        try:
            predict_url = f"{SERVER_BASE_URL}/predict"
            response = requests.post(
                predict_url, headers=headers, data=json.dumps(payload)
            )
            response.raise_for_status()
            resp_json = response.json()
            preds = resp_json.get("predictions")
            if not isinstance(preds, list):
                preds = []

            # Ensure response matches batch size
            if len(preds) != len(batch):
                debug_print(
                    f"Warning: batch size {len(batch)} vs response {len(preds)} mismatch"
                )
                predictions.extend([{"error": "mismatch"}] * len(batch))
                continue
            predictions.extend(preds)
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with server: {e}")
            predictions.extend([{"error": "network_error"}] * len(batch))
    return predictions


def process_report_fully(report):
    """
    Processes a single report:
    1. Gets matches (sentences) from cache.
    2. Gets single-label predictions from server.
    3. Returns result (dict with url and predictions).
    """
    matches = get_matches(report.url)
    server_predictions = []

    if matches:
        matches_with_year = [
            f"<reportYear>{report.year}</reportYear> {s}" for s in matches
        ]
        server_predictions = get_result_from_server(matches_with_year)
    else:
        server_predictions = []

    result_row = pd.Series(
        {
            "url": report.url,
            "server_response": server_predictions,
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
    all_chunk_results = []

    # Resume logic
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

    db_processed_urls = get_processed_server_urls()
    processed_set = db_processed_urls.union(resumed_urls)

    reports_to_process_df = get_unprocessed_reports()
    reports_to_process_df = reports_to_process_df[
        ~reports_to_process_df["url"].isin(processed_set)
    ]

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

    if total_reports < min_chunk_size:
        print(
            f"Skipping run: Found {total_reports} reports, which is less than the minimum of {min_chunk_size}."
        )
        if Path(output_parquet_file).exists():
            Path(output_parquet_file).unlink()
        return 0, 0, ""

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
                        all_chunk_results.append(res.to_dict())
                    else:
                        chunk_empty += 1
                except Exception as e:
                    debug_print(f"Error processing {future_to_report[future].url}: {e}")
                    chunk_empty += 1

        if all_chunk_results:
            pd.DataFrame(all_chunk_results).to_parquet(output_parquet_file)
            print(
                f"  -> Saved {len(all_chunk_results)} results to '{output_parquet_file}'"
            )

        chunk_time = time.time() - start_chunk_time
        chunk_times.append(chunk_time)
        total_time += chunk_time
        total_results += chunk_results
        total_empty += chunk_empty
        results_since_last_save += chunk_results

        avg_chunk_time = sum(chunk_times) / len(chunk_times)
        remaining_chunks = len(chunks) - chunk_idx
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

        print(f"  ✓ Processed {chunk_results} reports successfully")
        print(f"  ✗ Empty/failed: {chunk_empty} reports")
        print(f"  Time taken: {format_time(chunk_time)}")
        print(f"  Avg chunk time: {format_time(avg_chunk_time)}")
        print(f"  Est. time remaining: {format_time(est_time_remaining)}")
        print(f"  Total time: {format_time(total_time)}")

        processed_so_far = chunk_idx * CHUNK_SIZE
        percent_complete = (processed_so_far / total_reports) * 100
        print(
            f"  📊 Overall: {total_results:,}/{min(processed_so_far, total_reports):,} ({percent_complete:.1f}% complete)"
        )

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
# INITIALIZATION
# =============================================================================

create_db()

# =============================================================================
# MAIN EXECUTION
# =============================================================================


def run_classification(total_chunks=1, chunk_index=0):
    """The main classification loop."""
    is_first_run = True
    try:
        while True:
            create_db()
            min_size_for_run = 1 if is_first_run else 20

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
                wait_time = 60 * 5
                print(
                    f"\nNo new reports to process. Waiting for {wait_time} seconds..."
                )
                time.sleep(wait_time)

            cleanup_error_responses()
            is_first_run = False

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
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(
            description="Run the classification script in standalone or chunked mode."
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
        args = parser.parse_args()
        print("=" * 70)
        if args.total_chunks > 1:
            print("🚀 Starting Model Classification Service (Chunked Mode)")
            print(
                f"   Will process chunk {args.chunk_index} of {args.total_chunks} and then exit."
            )
        else:
            print("🚀 Starting Model Classification Service (Standalone Mode)")
            print(
                "   This script will run continuously, checking for new data to classify."
            )
            print("   Press Ctrl+C to stop.")
        print("=" * 70)
        run_classification(args.total_chunks, args.chunk_index)
    else:
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
                print(
                    "   This script will run continuously, checking for new data to classify."
                )
                print("   Press Ctrl+C to stop.")
                print("=" * 70)
                run_classification(total_chunks=1, chunk_index=0)
                break
            elif choice == "2":
                try:
                    total_chunks = int(
                        input("   Enter total number of chunks (e.g., 2 for 2 PCs): ")
                    )
                    chunk_index = int(
                        input(
                            f"   Enter this machine's chunk index (0 to {total_chunks - 1}): "
                        )
                    )
                    if not (0 <= chunk_index < total_chunks):
                        print("   ❌ Error: Chunk index is out of range.")
                        continue

                    print("\n🚀 Starting Model Classification Service (Chunked Mode)")
                    print(
                        f"   Will process chunk {chunk_index} of {total_chunks} and then exit."
                    )
                    print("=" * 70)
                    run_classification(total_chunks, chunk_index)
                    break
                except ValueError:
                    print("   ❌ Error: Please enter valid numbers for chunks.")
            elif choice == "3":
                print("Exiting.")
                break
            else:
                print("Invalid choice. Please try again.")
