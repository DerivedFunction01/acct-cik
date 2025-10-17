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
import psutil


# =============================================================================
# CONFIGURATION
# =============================================================================

DB_PATH = "web_data.db"
REPORT_CSV_PATH = "./report_data.csv"
SERVER_URL = "http://127.0.0.1:5000/predict"
KEYWORDS_FILE = "./keywords_find.json"
DEBUG = False  # Debug printing
CHUNK_SIZE = 100  # Base chunk size, will be adjusted based on RAM

# =============================================================================
# COLAB CONFIGURATION
# =============================================================================
DRIVE_PATH = "./drive/MyDrive/db"
DRIVE_SENTENCE_PATH = "sentence_results"
DRIVE_KEYWORDS_PATH = "keywords_results"
LOAD_SHELL_CMD = f"cp {DRIVE_PATH}/{DB_PATH} ."
SAVE_SHELL_CMD = f"cp {DB_PATH} {DRIVE_PATH}/."
IS_COLAB = Path(DRIVE_PATH).exists()

def get_system_config():
    """Auto-detects system capabilities to set configuration."""
    cpu_cores = mp.cpu_count()
    ram_gb = psutil.virtual_memory().total / (1024**3)

    print(f"🖥️  System Detected: {cpu_cores} CPU cores, {ram_gb:.2f} GB RAM")

    # Set NUM_THREADS based on CPU cores
    num_threads = cpu_cores * 5

    # Set CHUNK_SIZE based on RAM
    if ram_gb > 32:
        chunk_multiplier = 10  # High-RAM machine
    elif ram_gb > 16:
        chunk_multiplier = 5  # Medium-RAM machine
    elif ram_gb > 8:
        chunk_multiplier = 2  # Standard machine
    else:
        chunk_multiplier = 1  # Low-RAM machine

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
    except sqlite3.IntegrityError:
        debug_print("Something went wrong creating the database")
    finally:
        conn.commit()
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
    matches = json.loads(data.matches.iloc[0])
    return matches


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


def get_result_from_server(sentences, batch_size=128):
    predictions = []
    headers = {"Content-Type": "application/json"}

    for i in range(0, len(sentences), batch_size):
        batch = sentences[i : i + batch_size]
        payload = {"texts": batch}
        try:
            response = requests.post(
                SERVER_URL, headers=headers, data=json.dumps(payload)
            )
            response.raise_for_status()
            resp_json = response.json()
            preds = resp_json.get("predictions")  # Server returns a list of prediction dicts
            if not isinstance(preds, list):
                preds = []

            # If response length doesn't match batch, fill with error objects
            if len(preds) != len(batch):
                debug_print(
                    f"Warning: batch size {len(batch)} vs response {len(preds)} mismatch"
                )
                # Use a consistent error object instead of -1
                predictions.extend([{"error": -1}] * len(batch))
                continue  # Continue to the next batch
            predictions.extend(preds)
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with server: {e}")
            # Use a consistent error object for network errors
            predictions.extend([{"error": -1}] * len(batch))
    return predictions


def process_report_fully(report):
    """
    Processes a single report completely:
    1. Loads content (from cache or web).
    2. Gets analysis from the server for those sentences from `matches`.
    3. Returns the result (does NOT save to database immediately).
    """
    # Get the report's `matches`
    matches = get_matches(report.url)
    server_predictions = []

    # Prepend <reportYear> to each sentence
    if matches:
        matches_with_year = [
            f"<reportYear>{report.year}</reportYear> {s}" for s in matches
        ]
        # Get sentence analysis from the server
        server_predictions = get_result_from_server(matches_with_year)
    else:
        server_predictions = []

    # Prepare the final result row (return, don't save yet)
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


def process_reports_in_chunks():
    """Process reports in chunks with periodic saves and statistics."""
    global existing_report_df

    processed_set = get_processed_server_urls()

    # Only process reports not already in server_result
    reports_to_process = [
        r
        for r in existing_report_df.itertuples(index=False)
        if r.url not in processed_set
    ]

    total_reports = len(reports_to_process)
    print(f"Processing {total_reports:,} new reports")
    print(f"Already processed: {len(processed_set):,} reports")

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

    for chunk_idx, chunk in enumerate(chunks, 1):
        start_chunk_time = time.time()
        print(f"\n📦 Chunk {chunk_idx}/{len(chunks)} ({len(chunk)} reports)")

        chunk_results = 0
        chunk_empty = 0
        results_buffer = []

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
                        results_buffer.append(res)
                    else:
                        chunk_empty += 1
                except Exception as e:
                    debug_print(f"Error processing {future_to_report[future].url}: {e}")
                    chunk_empty += 1
        # Flush the results buffer
        save_batch_results(results_buffer)
        results_buffer.clear()

        chunk_time = time.time() - start_chunk_time
        chunk_times.append(chunk_time)
        total_time += chunk_time
        total_results += chunk_results
        total_empty += chunk_empty

        # Calculate statistics
        avg_chunk_time = sum(chunk_times) / len(chunk_times)
        remaining_chunks = len(chunks) - chunk_idx
        est_time_remaining = avg_chunk_time * remaining_chunks

        print(f"  ✓ Processed {chunk_results} reports successfully")
        print(f"  ✗ Empty/failed: {chunk_empty} reports")
        print(f"  Time taken: {format_time(chunk_time)}")
        print(f"  Avg chunk time: {format_time(avg_chunk_time)}")
        print(f"  Est. time remaining: {format_time(est_time_remaining)}")
        print(f"  Total time: {format_time(total_time)}")

        # Save to Google Drive if in Colab
        if IS_COLAB:
            print(f"  -> Saving to Google Drive...")
            subprocess.run(SAVE_SHELL_CMD, shell=True)

        # Progress summary
        processed_so_far = chunk_idx * CHUNK_SIZE
        percent_complete = (processed_so_far / total_reports) * 100
        print(
            f"  📊 Overall: {total_results:,}/{min(processed_so_far, total_reports):,} ({percent_complete:.1f}% complete)"
        )

    print("\n" + "=" * 70)
    print(f"🎉 FINAL RESULTS:")
    print(f"  ✓ Successfully processed: {total_results:,} reports")
    print(f"  ✗ Empty/failed: {total_empty:,} reports")
    if total_results + total_empty > 0:
        print(
            f"  📈 Success rate: {(total_results/(total_results+total_empty)*100):.1f}%"
        )
    print("=" * 70)

    return total_results


# =============================================================================
# INITIALIZATION
# =============================================================================
# %%
create_db()
existing_report_df = fetch_report_data()
print(f"Found {len(existing_report_df)} reports in database")
with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
    keyword_data = json.load(f)

id2label = {i: label for i, label in enumerate(keyword_data)}
label2id = {label: i for i, label in enumerate(keyword_data)}

# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
if __name__ == "__main__":
    print("=" * 70)
    print("Model Classification and Analysis Script")
    print("=" * 70)

    # Initialize database
    create_db()

    # Process reports in chunks
    print("\nProcessing reports with server predictions...")
    total_processed = process_reports_in_chunks()

    print(f"\nProcessed {total_processed} new reports in chunked parallel mode.")

    # Final save to Drive if in Colab
    if IS_COLAB:
        print("\nFinal database sync to Google Drive...")
        subprocess.run(SAVE_SHELL_CMD, shell=True)

    print("\n" + "=" * 70)
    print("All done!")
    print("=" * 70)