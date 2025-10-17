# =============================================================================
# Model Classification Script - Chunked Processing
# =============================================================================

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


# =============================================================================
# CONFIGURATION
# =============================================================================

DB_PATH = "web_data.db"
REPORT_CSV_PATH = "./report_data.csv"
DERIVATIVES_CSV_PATH = "./derivatives_data.csv"
SERVER_EXCEL_PATH = "./server_results.xlsx"
KEYWORDS_EXCEL_PATH = "./keywords_comparison.xlsx"
SENTENCE_PATH = "./sentence_labels.xlsx"
SERVER_URL = "http://127.0.0.1:5000/predict"
KEYWORDS_FILE = "./keywords_find.json"
DEBUG = False  # Debug printing

# =============================================================================
# COLAB CONFIGURATION
# =============================================================================
DRIVE_PATH = "./drive/MyDrive/db"
DRIVE_SENTENCE_PATH = "sentence_results"
DRIVE_KEYWORDS_PATH = "keywords_results"
LOAD_SHELL_CMD = f"cp {DRIVE_PATH}/{DB_PATH} ."
SAVE_SHELL_CMD = f"cp {DB_PATH} {DRIVE_PATH}/."
IS_COLAB = Path(DRIVE_PATH).exists()

# Chunking configuration
CHUNK_SIZE = 1000 * (1 if not IS_COLAB else 5)
NUM_THREADS = 6 * (1 if not IS_COLAB else 5)

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
                batch_data.append(
                    (result.url, json.dumps(result.server_response)))
            except Exception as e:
                debug_print(f"Error preparing data for {result.url}: {e}")
                # Get cik and year from report_data for fail_results
                c.execute(
                    "SELECT cik, year FROM report_data WHERE url=?", (
                        result.url,)
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
        debug_print(
            f"Batch saved: {success_count} success, {fail_count} failures")

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
        batch = sentences[i: i + batch_size]
        payload = {"texts": batch}
        try:
            response = requests.post(
                SERVER_URL, headers=headers, data=json.dumps(payload)
            )
            response.raise_for_status()
            resp_json = response.json()
            preds = resp_json.get("predictions")
            if not isinstance(preds, list):
                preds = []
            if len(preds) != len(batch):
                debug_print(
                    f"Warning: batch size {len(batch)} vs response {len(preds)} mismatch"
                )
                return [-1] * len(batch)
            predictions.extend(preds)
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with server: {e}")
            predictions.extend([-1] * len(batch))
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
# ANALYSIS FUNCTIONS
# =============================================================================


def parse_json(json_str):
    """Helper function to parse JSON strings safely"""
    try:
        return json.loads(json_str) if isinstance(json_str, str) else json_str
    except (json.JSONDecodeError, TypeError):
        return []


def get_final_results():
    """Get all processed results from the database, joined with report_data for cik/year"""
    conn = sqlite3.connect(DB_PATH)

    # Join server_result with report_data to get cik and year
    query = """
        SELECT
            r.cik,
            r.year,
            s.url,
            s.server_response
        FROM server_result s
        JOIN report_data r ON s.url = r.url
    """

    wr = pd.read_sql(query, conn)
    conn.close()

    if wr.empty:
        print("No results found in server_result table")
        return pd.DataFrame()

    # Parse JSON columns
    wr["server_response"] = wr["server_response"].apply(parse_json)

    return wr

# =============================================================================
# PARALLELIZED ANALYSIS FUNCTIONS
# =============================================================================


def process_row_for_analysis(row_data):
    """Process a single row for sentence analysis - designed for ProcessPoolExecutor"""
    cik, year, url, server_response = row_data

    # Parse server_response if it's a string
    if isinstance(server_response, str):
        try:
            predictions = json.loads(server_response)
        except (json.JSONDecodeError, TypeError):
            predictions = []
    else:
        predictions = server_response if isinstance(
            server_response, list) else []

    if not predictions:
        return None

    # Map IDs → labels
    predicted_labels = [id2label.get(pid, "Unknown") for pid in predictions]
    pred_counts = Counter(predicted_labels)

    result = {
        "cik": cik,
        "year": year,
        "url": url,
        "total_sentences": len(predictions),
        **pred_counts,
    }

    return result


def compute_firms_current_hedge(sa, hedge_labels_current):
    """Parallel task: filter firms with current hedge - OPTIMIZED"""
    # Aggregate first, then filter - much faster than groupby().filter()
    firm_totals = sa.groupby("cik")[hedge_labels_current].sum().sum(axis=1)
    firms_with_current = firm_totals[firm_totals > 0].index
    return sa[sa["cik"].isin(firms_with_current)]


def compute_firms_historic_only(sa, hedge_labels_historic, hedge_labels_current):
    """Parallel task: filter firms with only historic hedge - OPTIMIZED"""
    # Compute totals per firm for both categories
    firm_historic = sa.groupby("cik")[hedge_labels_historic].sum().sum(axis=1)
    firm_current = sa.groupby("cik")[hedge_labels_current].sum().sum(axis=1)

    # Find firms with historic > 0 AND current == 0
    firms_historic_only = firm_historic[(
        firm_historic > 0) & (firm_current == 0)].index
    return sa[sa["cik"].isin(firms_historic_only)]


def compute_firms_label2_only(sa, label2_col, exclude_cols):
    """Parallel task: filter firms with only label 2 - OPTIMIZED"""
    # Aggregate per firm
    firm_label2 = sa.groupby("cik")[label2_col].sum()
    firm_others = sa.groupby("cik")[exclude_cols].sum().sum(axis=1)

    # Find firms where label2 > 0 AND others < label2
    firms_label2_only = firm_label2[(firm_label2 > 0) & (
        firm_others < firm_label2)].index
    return sa[sa["cik"].isin(firms_label2_only)]


def compute_firms_liabilities(sa, label4_col, label5_col):
    """Parallel task: filter firms with liabilities"""
    return sa.loc[(sa[label4_col] > 0) | (sa[label5_col] > 0)]


def compute_embedded_derivatives(sa, label6_col, label7_col):
    """Parallel task: filter embedded derivatives"""
    return sa.loc[(sa[label6_col] > 0) | (sa[label7_col] > 0)]


def compute_unique_counts(sa, label_cols):
    """Parallel task: compute unique firms per label/year"""
    return (
        sa.melt(id_vars=["cik", "year"], value_vars=label_cols)
        .query("value > 0")
        .drop_duplicates(["cik", "year", "variable"])
        .groupby(["year", "variable"])["cik"]
        .nunique()
        .reset_index(name="unique_firms")
    )


def compute_label_cooccurrence(sa, label_cols):
    """Parallel task: compute label co-occurrence matrix"""
    return sa[label_cols].gt(0).astype(int).T.dot(sa[label_cols].gt(0).astype(int))


def compute_hedge_by_type(sa, hedge_types):
    """Parallel task: compute hedging by type - OPTIMIZED v2"""
    # Pre-compute a multi-index column for fast lookups
    sa_indexed = sa.copy()
    sa_indexed['cik_year'] = sa_indexed['cik'].astype(
        str) + '_' + sa_indexed['year'].astype(str)

    hedge_type_records = []

    for hedge_name, labels in hedge_types.items():
        # Aggregate per (cik, year), then filter
        firm_year_totals = sa.groupby(["cik", "year"])[
            labels].sum().sum(axis=1)
        firms_with_hedge = firm_year_totals[firm_year_totals > 0].index

        # Create lookup set for fast membership testing
        firms_lookup = set(f"{cik}_{year}" for cik, year in firms_with_hedge)

        # Filter using the lookup
        temp = sa_indexed[sa_indexed['cik_year'].isin(firms_lookup)].copy()
        temp["hedge_type"] = hedge_name
        temp = temp.drop(columns=['cik_year'])

        if not temp.empty:
            hedge_type_records.append(temp)

    if hedge_type_records:
        return pd.concat(hedge_type_records, ignore_index=True)
    else:
        return pd.DataFrame(columns=["cik", "year", "hedge_type"])


def compute_hedge_cross(sa, hedge_label_groups):
    """Parallel task: compute hedge type cross-analysis"""
    hedge_flags = (
        sa.groupby("cik")[hedge_label_groups]
        .sum()
        .gt(0)
        .astype(int)
    )

    # Map to current hedge categories only (merge historic)
    hedge_flags_simple = pd.DataFrame({
        "General": hedge_flags[[hedge_label_groups[0], hedge_label_groups[4]]].max(axis=1),
        "IR": hedge_flags[[hedge_label_groups[1], hedge_label_groups[5]]].max(axis=1),
        "FX": hedge_flags[[hedge_label_groups[2], hedge_label_groups[6]]].max(axis=1),
        "CP": hedge_flags[[hedge_label_groups[3], hedge_label_groups[7]]].max(axis=1),
    })

    return hedge_flags_simple.T.dot(hedge_flags_simple)


def analyze_keyword_vs_model(sa, hedge_labels_current):
    """
    Analyzes the original keyword-based derivatives data against the model's results.
    Now includes detailed breakdowns by hedge type, confusion matrices, and accuracy metrics.
    Includes both current-only and current+historic comparisons.
    ENHANCED: Now includes derivative liabilities and embedded derivatives analysis.
    """
    print("  Comparing keyword search results with model results...")
    try:
        # Load original keyword-based data
        deriv_df = pd.read_csv(DERIVATIVES_CSV_PATH)
        # Ensure CIK is integer for merging
        deriv_df["cik"] = deriv_df["cik"].astype(int)

        # Get keyword flags for each cik/year
        keyword_users = (
            deriv_df.groupby(["cik", "year"])[["user", "fx_user", "ir_user", "cp_user"]]
            .max()
            .reset_index()
        )
        keyword_users.rename(
            columns={
                "user": "keyword_user",
                "fx_user": "keyword_fx",
                "ir_user": "keyword_ir",
                "cp_user": "keyword_cp",
            },
            inplace=True,
        )

        # --- CURRENT ONLY MODEL FLAGS ---

        # General hedge (any current hedge - IR, FX, CP only)
        model_general_current = (
            sa.groupby(["cik", "year"])[hedge_labels_current].sum().sum(axis=1) > 0
        )
        model_general_current = model_general_current.reset_index(
            name="model_user_current"
        )

        # Any derivatives (includes hedges, liabilities, and embedded)
        all_derivative_labels_current = hedge_labels_current + [
            id2label[4],
            id2label[6],
        ]
        model_any_deriv_current = (
            sa.groupby(["cik", "year"])[all_derivative_labels_current].sum().sum(axis=1)
            > 0
        )
        model_any_deriv_current = model_any_deriv_current.reset_index(
            name="model_any_deriv_current"
        )

        # FX hedge - id2label[10] is FX Hedge (current)
        model_fx_current = sa.groupby(["cik", "year"])[id2label[10]].sum() > 0
        model_fx_current = model_fx_current.reset_index(name="model_fx_current")

        # IR hedge - id2label[8] is IR Hedge (current)
        model_ir_current = sa.groupby(["cik", "year"])[id2label[8]].sum() > 0
        model_ir_current = model_ir_current.reset_index(name="model_ir_current")

        # CP hedge - id2label[12] is CP Hedge (current)
        model_cp_current = sa.groupby(["cik", "year"])[id2label[12]].sum() > 0
        model_cp_current = model_cp_current.reset_index(name="model_cp_current")

        # Derivative Liabilities - id2label[4] is current
        model_liab_current = sa.groupby(["cik", "year"])[id2label[4]].sum() > 0
        model_liab_current = model_liab_current.reset_index(name="model_liab_current")

        # Embedded Derivatives - id2label[6] is current
        model_embed_current = sa.groupby(["cik", "year"])[id2label[6]].sum() > 0
        model_embed_current = model_embed_current.reset_index(
            name="model_embed_current"
        )

        # --- CURRENT + HISTORIC MODEL FLAGS ---

        # General hedge (current + historic - IR, FX, CP only)
        hedge_labels_all = [
            id2label[0],
            id2label[1],  # General current + historic
            id2label[8],
            id2label[9],  # IR current + historic
            id2label[10],
            id2label[11],  # FX current + historic
            id2label[12],
            id2label[13],  # CP current + historic
        ]
        model_general_all = (
            sa.groupby(["cik", "year"])[hedge_labels_all].sum().sum(axis=1) > 0
        )
        model_general_all = model_general_all.reset_index(name="model_user_all")

        # Any derivatives (includes hedges, liabilities, and embedded)
        all_derivative_labels_all = hedge_labels_all + [
            id2label[4],
            id2label[5],  # Liabilities current + historic
            id2label[6],
            id2label[7],  # Embedded current + historic
        ]
        model_any_deriv_all = (
            sa.groupby(["cik", "year"])[all_derivative_labels_all].sum().sum(axis=1) > 0
        )
        model_any_deriv_all = model_any_deriv_all.reset_index(
            name="model_any_deriv_all"
        )

        # FX hedge (current + historic) - id2label[10] and id2label[11]
        model_fx_all = (
            sa.groupby(["cik", "year"])[[id2label[10], id2label[11]]].sum().sum(axis=1)
            > 0
        )
        model_fx_all = model_fx_all.reset_index(name="model_fx_all")

        # IR hedge (current + historic) - id2label[8] and id2label[9]
        model_ir_all = (
            sa.groupby(["cik", "year"])[[id2label[8], id2label[9]]].sum().sum(axis=1)
            > 0
        )
        model_ir_all = model_ir_all.reset_index(name="model_ir_all")

        # CP hedge (current + historic) - id2label[12] and id2label[13]
        model_cp_all = (
            sa.groupby(["cik", "year"])[[id2label[12], id2label[13]]].sum().sum(axis=1)
            > 0
        )
        model_cp_all = model_cp_all.reset_index(name="model_cp_all")

        # Derivative Liabilities (current + historic) - id2label[4] and id2label[5]
        model_liab_all = (
            sa.groupby(["cik", "year"])[[id2label[4], id2label[5]]].sum().sum(axis=1)
            > 0
        )
        model_liab_all = model_liab_all.reset_index(name="model_liab_all")

        # Embedded Derivatives (current + historic) - id2label[6] and id2label[7]
        model_embed_all = (
            sa.groupby(["cik", "year"])[[id2label[6], id2label[7]]].sum().sum(axis=1)
            > 0
        )
        model_embed_all = model_embed_all.reset_index(name="model_embed_all")

        # Merge all model results (current)
        model_users_current = model_general_current.merge(
            model_fx_current, on=["cik", "year"], how="outer"
        )
        model_users_current = model_users_current.merge(
            model_ir_current, on=["cik", "year"], how="outer"
        )
        model_users_current = model_users_current.merge(
            model_cp_current, on=["cik", "year"], how="outer"
        )
        model_users_current = model_users_current.merge(
            model_liab_current, on=["cik", "year"], how="outer"
        )
        model_users_current = model_users_current.merge(
            model_embed_current, on=["cik", "year"], how="outer"
        )
        model_users_current = model_users_current.merge(
            model_any_deriv_current, on=["cik", "year"], how="outer"
        )

        # Merge all model results (current + historic)
        model_users_all = model_general_all.merge(
            model_fx_all, on=["cik", "year"], how="outer"
        )
        model_users_all = model_users_all.merge(
            model_ir_all, on=["cik", "year"], how="outer"
        )
        model_users_all = model_users_all.merge(
            model_cp_all, on=["cik", "year"], how="outer"
        )
        model_users_all = model_users_all.merge(
            model_liab_all, on=["cik", "year"], how="outer"
        )
        model_users_all = model_users_all.merge(
            model_embed_all, on=["cik", "year"], how="outer"
        )
        model_users_all = model_users_all.merge(
            model_any_deriv_all, on=["cik", "year"], how="outer"
        )

        # Fill NaN with False and convert to int
        for col in [
            "model_user_current",
            "model_fx_current",
            "model_ir_current",
            "model_cp_current",
            "model_liab_current",
            "model_embed_current",
            "model_any_deriv_current",
        ]:
            model_users_current[col] = (
                model_users_current[col].fillna(False).astype(bool).astype(int)
            )

        for col in [
            "model_user_all",
            "model_fx_all",
            "model_ir_all",
            "model_cp_all",
            "model_liab_all",
            "model_embed_all",
            "model_any_deriv_all",
        ]:
            model_users_all[col] = (
                model_users_all[col].fillna(False).astype(bool).astype(int)
            )

        # Merge keyword and model results
        comparison_current = pd.merge(
            keyword_users, model_users_current, on=["cik", "year"], how="outer"
        )
        comparison_all = pd.merge(
            keyword_users, model_users_all, on=["cik", "year"], how="outer"
        )

        # Fill NaN values - if missing from either dataset, assume False
        for col in comparison_current.columns:
            if col not in ["cik", "year"]:
                comparison_current[col] = (
                    comparison_current[col].fillna(False).astype(bool).astype(int)
                )

        for col in comparison_all.columns:
            if col not in ["cik", "year"]:
                comparison_all[col] = (
                    comparison_all[col].fillna(False).astype(bool).astype(int)
                )

        # --- Helper function for metrics ---
        def calculate_metrics(keyword_col, model_col, df):
            """Calculate accuracy, precision, recall, F1 for a given comparison"""
            # True Positives, False Positives, True Negatives, False Negatives
            tp = ((df[keyword_col] == 1) & (df[model_col] == 1)).sum()
            fp = ((df[keyword_col] == 0) & (df[model_col] == 1)).sum()
            tn = ((df[keyword_col] == 0) & (df[model_col] == 0)).sum()
            fn = ((df[keyword_col] == 1) & (df[model_col] == 0)).sum()

            total = len(df)
            accuracy = (tp + tn) / total if total > 0 else 0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = (
                2 * (precision * recall) / (precision + recall)
                if (precision + recall) > 0
                else 0
            )

            return {
                "True_Positives": tp,
                "False_Positives": fp,
                "True_Negatives": tn,
                "False_Negatives": fn,
                "Total": total,
                "Accuracy": round(accuracy * 100, 2),
                "Precision": round(precision * 100, 2),
                "Recall": round(recall * 100, 2),
                "F1_Score": round(f1 * 100, 2),
                "Agreement_Rate": (
                    round(((tp + tn) / total) * 100, 2) if total > 0 else 0
                ),
            }

        # --- Helper function for model-only analysis (no keyword comparison) ---
        def calculate_model_only_stats(model_col, df):
            """Calculate statistics for model predictions without keyword comparison"""
            positive = (df[model_col] == 1).sum()
            negative = (df[model_col] == 0).sum()
            total = len(df)

            return {
                "Total": total,
                "Model_Positive": positive,
                "Model_Negative": negative,
                "Positive_Rate": round((positive / total) * 100, 2) if total > 0 else 0,
            }

        # --- CURRENT ONLY ANALYSIS ---

        # Confusion matrices - current only (for hedges with keyword comparison)
        # Using more descriptive labels for clarity
        confusion_overall_current = pd.crosstab(
            comparison_current["keyword_user"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_current["model_user_current"].map(
                {0: "Model_No", 1: "Model_Yes"}
            ),
            rownames=["Keyword_Search"],
            colnames=["Model_Prediction"],
            margins=True,
        )

        # Confusion matrix for ANY derivative (hedge + liabilities + embedded) vs keyword hedge
        confusion_any_deriv_current = pd.crosstab(
            comparison_current["keyword_user"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_current["model_any_deriv_current"].map(
                {0: "Model_No", 1: "Model_Yes"}
            ),
            rownames=["Keyword_Search"],
            colnames=["Model_Prediction"],
            margins=True,
        )

        confusion_fx_current = pd.crosstab(
            comparison_current["keyword_fx"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_current["model_fx_current"].map({0: "Model_No", 1: "Model_Yes"}),
            rownames=["Keyword_FX"],
            colnames=["Model_FX"],
            margins=True,
        )

        confusion_ir_current = pd.crosstab(
            comparison_current["keyword_ir"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_current["model_ir_current"].map({0: "Model_No", 1: "Model_Yes"}),
            rownames=["Keyword_IR"],
            colnames=["Model_IR"],
            margins=True,
        )

        confusion_cp_current = pd.crosstab(
            comparison_current["keyword_cp"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_current["model_cp_current"].map({0: "Model_No", 1: "Model_Yes"}),
            rownames=["Keyword_CP"],
            colnames=["Model_CP"],
            margins=True,
        )

        # Calculate metrics - current only
        metrics_overall_current = calculate_metrics(
            "keyword_user", "model_user_current", comparison_current
        )
        metrics_fx_current = calculate_metrics(
            "keyword_fx", "model_fx_current", comparison_current
        )
        metrics_ir_current = calculate_metrics(
            "keyword_ir", "model_ir_current", comparison_current
        )
        metrics_cp_current = calculate_metrics(
            "keyword_cp", "model_cp_current", comparison_current
        )
        metrics_any_deriv_current = calculate_metrics(
            "keyword_user", "model_any_deriv_current", comparison_current
        )

        # Model-only statistics for liabilities and embedded derivatives (current)
        stats_liab_current = calculate_model_only_stats(
            "model_liab_current", comparison_current
        )
        stats_embed_current = calculate_model_only_stats(
            "model_embed_current", comparison_current
        )

        summary_current = pd.DataFrame(
            [
                {
                    "Category": "Overall (Hedges Only: IR/FX/CP)",
                    **metrics_overall_current,
                },
                {"Category": "Foreign Exchange (FX)", **metrics_fx_current},
                {"Category": "Interest Rate (IR)", **metrics_ir_current},
                {"Category": "Commodity Price (CP)", **metrics_cp_current},
            ]
        )

        # Combined summary for all derivatives workbook (Overall = All Derivatives)
        summary_any_deriv_current = pd.DataFrame(
            [
                {
                    "Category": "Overall (All Derivatives: Hedges + Liabilities + Embedded)",
                    **metrics_any_deriv_current,
                },
                {"Category": "Foreign Exchange (FX)", **metrics_fx_current},
                {"Category": "Interest Rate (IR)", **metrics_ir_current},
                {"Category": "Commodity Price (CP)", **metrics_cp_current},
            ]
        )

        # Model-only summary for current
        model_only_current = pd.DataFrame(
            [
                {"Category": "Derivative Liabilities/Warrants", **stats_liab_current},
                {"Category": "Embedded Derivatives", **stats_embed_current},
            ]
        )

        # Detailed comparison - current only (Hedges only)
        detailed_current = comparison_current.copy()
        detailed_current["overall_agree"] = (
            detailed_current["keyword_user"] == detailed_current["model_user_current"]
        ).astype(int)
        detailed_current["fx_agree"] = (
            detailed_current["keyword_fx"] == detailed_current["model_fx_current"]
        ).astype(int)
        detailed_current["ir_agree"] = (
            detailed_current["keyword_ir"] == detailed_current["model_ir_current"]
        ).astype(int)
        detailed_current["cp_agree"] = (
            detailed_current["keyword_cp"] == detailed_current["model_cp_current"]
        ).astype(int)

        detailed_current["overall_classification"] = detailed_current.apply(
            lambda row: (
                "True Positive"
                if row["keyword_user"] == 1 and row["model_user_current"] == 1
                else (
                    "True Negative"
                    if row["keyword_user"] == 0 and row["model_user_current"] == 0
                    else (
                        "False Positive"
                        if row["keyword_user"] == 0 and row["model_user_current"] == 1
                        else "False Negative"
                    )
                )
            ),
            axis=1,
        )

        # Detailed comparison - current only (All Derivatives)
        detailed_any_deriv_current = comparison_current.copy()
        detailed_any_deriv_current["overall_agree"] = (
            detailed_any_deriv_current["keyword_user"]
            == detailed_any_deriv_current["model_any_deriv_current"]
        ).astype(int)
        detailed_any_deriv_current["fx_agree"] = (
            detailed_any_deriv_current["keyword_fx"]
            == detailed_any_deriv_current["model_fx_current"]
        ).astype(int)
        detailed_any_deriv_current["ir_agree"] = (
            detailed_any_deriv_current["keyword_ir"]
            == detailed_any_deriv_current["model_ir_current"]
        ).astype(int)
        detailed_any_deriv_current["cp_agree"] = (
            detailed_any_deriv_current["keyword_cp"]
            == detailed_any_deriv_current["model_cp_current"]
        ).astype(int)

        detailed_any_deriv_current["overall_classification"] = (
            detailed_any_deriv_current.apply(
                lambda row: (
                    "True Positive"
                    if row["keyword_user"] == 1 and row["model_any_deriv_current"] == 1
                    else (
                        "True Negative"
                        if row["keyword_user"] == 0
                        and row["model_any_deriv_current"] == 0
                        else (
                            "False Positive"
                            if row["keyword_user"] == 0
                            and row["model_any_deriv_current"] == 1
                            else "False Negative"
                        )
                    )
                ),
                axis=1,
            )
        )

        # --- CURRENT + HISTORIC ANALYSIS ---

        # Confusion matrices - current + historic (for hedges with keyword comparison)
        confusion_overall_all = pd.crosstab(
            comparison_all["keyword_user"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_all["model_user_all"].map({0: "Model_No", 1: "Model_Yes"}),
            rownames=["Keyword_Search"],
            colnames=["Model_Prediction"],
            margins=True,
        )

        # Confusion matrix for ANY derivative (hedge + liabilities + embedded) vs keyword hedge
        confusion_any_deriv_all = pd.crosstab(
            comparison_all["keyword_user"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_all["model_any_deriv_all"].map({0: "Model_No", 1: "Model_Yes"}),
            rownames=["Keyword_Search"],
            colnames=["Model_Prediction"],
            margins=True,
        )

        confusion_fx_all = pd.crosstab(
            comparison_all["keyword_fx"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_all["model_fx_all"].map({0: "Model_No", 1: "Model_Yes"}),
            rownames=["Keyword_FX"],
            colnames=["Model_FX"],
            margins=True,
        )

        confusion_ir_all = pd.crosstab(
            comparison_all["keyword_ir"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_all["model_ir_all"].map({0: "Model_No", 1: "Model_Yes"}),
            rownames=["Keyword_IR"],
            colnames=["Model_IR"],
            margins=True,
        )

        confusion_cp_all = pd.crosstab(
            comparison_all["keyword_cp"].map({0: "Keyword_No", 1: "Keyword_Yes"}),
            comparison_all["model_cp_all"].map({0: "Model_No", 1: "Model_Yes"}),
            rownames=["Keyword_CP"],
            colnames=["Model_CP"],
            margins=True,
        )

        # Calculate metrics - current + historic
        metrics_overall_all = calculate_metrics(
            "keyword_user", "model_user_all", comparison_all
        )
        metrics_fx_all = calculate_metrics("keyword_fx", "model_fx_all", comparison_all)
        metrics_ir_all = calculate_metrics("keyword_ir", "model_ir_all", comparison_all)
        metrics_cp_all = calculate_metrics("keyword_cp", "model_cp_all", comparison_all)
        metrics_any_deriv_all = calculate_metrics(
            "keyword_user", "model_any_deriv_all", comparison_all
        )

        # Model-only statistics for liabilities and embedded derivatives (all)
        stats_liab_all = calculate_model_only_stats("model_liab_all", comparison_all)
        stats_embed_all = calculate_model_only_stats("model_embed_all", comparison_all)

        summary_all = pd.DataFrame(
            [
                {"Category": "Overall (Hedges Only: IR/FX/CP)", **metrics_overall_all},
                {"Category": "Foreign Exchange (FX)", **metrics_fx_all},
                {"Category": "Interest Rate (IR)", **metrics_ir_all},
                {"Category": "Commodity Price (CP)", **metrics_cp_all},
            ]
        )

        # Combined summary for all derivatives workbook (Overall = All Derivatives)
        summary_any_deriv_all = pd.DataFrame(
            [
                {
                    "Category": "Overall (All Derivatives: Hedges + Liabilities + Embedded)",
                    **metrics_any_deriv_all,
                },
                {"Category": "Foreign Exchange (FX)", **metrics_fx_all},
                {"Category": "Interest Rate (IR)", **metrics_ir_all},
                {"Category": "Commodity Price (CP)", **metrics_cp_all},
            ]
        )

        # Model-only summary for all
        model_only_all = pd.DataFrame(
            [
                {"Category": "Derivative Liabilities/Warrants", **stats_liab_all},
                {"Category": "Embedded Derivatives", **stats_embed_all},
            ]
        )

        # Detailed comparison - current + historic (Hedges only)
        detailed_all = comparison_all.copy()
        detailed_all["overall_agree"] = (
            detailed_all["keyword_user"] == detailed_all["model_user_all"]
        ).astype(int)
        detailed_all["fx_agree"] = (
            detailed_all["keyword_fx"] == detailed_all["model_fx_all"]
        ).astype(int)
        detailed_all["ir_agree"] = (
            detailed_all["keyword_ir"] == detailed_all["model_ir_all"]
        ).astype(int)
        detailed_all["cp_agree"] = (
            detailed_all["keyword_cp"] == detailed_all["model_cp_all"]
        ).astype(int)

        detailed_all["overall_classification"] = detailed_all.apply(
            lambda row: (
                "True Positive"
                if row["keyword_user"] == 1 and row["model_user_all"] == 1
                else (
                    "True Negative"
                    if row["keyword_user"] == 0 and row["model_user_all"] == 0
                    else (
                        "False Positive"
                        if row["keyword_user"] == 0 and row["model_user_all"] == 1
                        else "False Negative"
                    )
                )
            ),
            axis=1,
        )

        # Detailed comparison - current + historic (All Derivatives)
        detailed_any_deriv_all = comparison_all.copy()
        detailed_any_deriv_all["overall_agree"] = (
            detailed_any_deriv_all["keyword_user"]
            == detailed_any_deriv_all["model_any_deriv_all"]
        ).astype(int)
        detailed_any_deriv_all["fx_agree"] = (
            detailed_any_deriv_all["keyword_fx"]
            == detailed_any_deriv_all["model_fx_all"]
        ).astype(int)
        detailed_any_deriv_all["ir_agree"] = (
            detailed_any_deriv_all["keyword_ir"]
            == detailed_any_deriv_all["model_ir_all"]
        ).astype(int)
        detailed_any_deriv_all["cp_agree"] = (
            detailed_any_deriv_all["keyword_cp"]
            == detailed_any_deriv_all["model_cp_all"]
        ).astype(int)

        detailed_any_deriv_all["overall_classification"] = detailed_any_deriv_all.apply(
            lambda row: (
                "True Positive"
                if row["keyword_user"] == 1 and row["model_any_deriv_all"] == 1
                else (
                    "True Negative"
                    if row["keyword_user"] == 0 and row["model_any_deriv_all"] == 0
                    else (
                        "False Positive"
                        if row["keyword_user"] == 0 and row["model_any_deriv_all"] == 1
                        else "False Negative"
                    )
                )
            ),
            axis=1,
        )

        # --- COMPARISON SUMMARY (Current vs Current+Historic) ---
        comparison_summary = pd.DataFrame(
            [
                {
                    "Metric": "Hedges Only - Accuracy",
                    "Current_Only": metrics_overall_current["Accuracy"],
                    "Current_Historic": metrics_overall_all["Accuracy"],
                    "Improvement": round(
                        metrics_overall_all["Accuracy"]
                        - metrics_overall_current["Accuracy"],
                        2,
                    ),
                },
                {
                    "Metric": "Hedges Only - Precision",
                    "Current_Only": metrics_overall_current["Precision"],
                    "Current_Historic": metrics_overall_all["Precision"],
                    "Improvement": round(
                        metrics_overall_all["Precision"]
                        - metrics_overall_current["Precision"],
                        2,
                    ),
                },
                {
                    "Metric": "Hedges Only - Recall",
                    "Current_Only": metrics_overall_current["Recall"],
                    "Current_Historic": metrics_overall_all["Recall"],
                    "Improvement": round(
                        metrics_overall_all["Recall"]
                        - metrics_overall_current["Recall"],
                        2,
                    ),
                },
                {
                    "Metric": "Hedges Only - F1 Score",
                    "Current_Only": metrics_overall_current["F1_Score"],
                    "Current_Historic": metrics_overall_all["F1_Score"],
                    "Improvement": round(
                        metrics_overall_all["F1_Score"]
                        - metrics_overall_current["F1_Score"],
                        2,
                    ),
                },
                {
                    "Metric": "Any Derivative - Accuracy",
                    "Current_Only": metrics_any_deriv_current["Accuracy"],
                    "Current_Historic": metrics_any_deriv_all["Accuracy"],
                    "Improvement": round(
                        metrics_any_deriv_all["Accuracy"]
                        - metrics_any_deriv_current["Accuracy"],
                        2,
                    ),
                },
                {
                    "Metric": "Any Derivative - Recall",
                    "Current_Only": metrics_any_deriv_current["Recall"],
                    "Current_Historic": metrics_any_deriv_all["Recall"],
                    "Improvement": round(
                        metrics_any_deriv_all["Recall"]
                        - metrics_any_deriv_current["Recall"],
                        2,
                    ),
                },
                {
                    "Metric": "FX Accuracy",
                    "Current_Only": metrics_fx_current["Accuracy"],
                    "Current_Historic": metrics_fx_all["Accuracy"],
                    "Improvement": round(
                        metrics_fx_all["Accuracy"] - metrics_fx_current["Accuracy"], 2
                    ),
                },
                {
                    "Metric": "IR Accuracy",
                    "Current_Only": metrics_ir_current["Accuracy"],
                    "Current_Historic": metrics_ir_all["Accuracy"],
                    "Improvement": round(
                        metrics_ir_all["Accuracy"] - metrics_ir_current["Accuracy"], 2
                    ),
                },
                {
                    "Metric": "CP Accuracy",
                    "Current_Only": metrics_cp_current["Accuracy"],
                    "Current_Historic": metrics_cp_all["Accuracy"],
                    "Improvement": round(
                        metrics_cp_all["Accuracy"] - metrics_cp_current["Accuracy"], 2
                    ),
                },
                {
                    "Metric": "Liabilities Positive Rate",
                    "Current_Only": stats_liab_current["Positive_Rate"],
                    "Current_Historic": stats_liab_all["Positive_Rate"],
                    "Improvement": round(
                        stats_liab_all["Positive_Rate"]
                        - stats_liab_current["Positive_Rate"],
                        2,
                    ),
                },
                {
                    "Metric": "Embedded Der. Positive Rate",
                    "Current_Only": stats_embed_current["Positive_Rate"],
                    "Current_Historic": stats_embed_all["Positive_Rate"],
                    "Improvement": round(
                        stats_embed_all["Positive_Rate"]
                        - stats_embed_current["Positive_Rate"],
                        2,
                    ),
                },
            ]
        )

        # --- AGGREGATE PERFORMANCE METRICS ---
        all_performance_data = []

        # Dictionary mapping the file names to their corresponding summary DataFrames
        sources = {
            "keywords_comp_ALL_DERIVATIVES_CURRENT.xlsx": summary_any_deriv_current,
            "keywords_comp_ALL_DERIVATIVES_FULL.xlsx": summary_any_deriv_all,
            "keywords_comparison_HEDGES_ALL.xlsx": summary_all,
            "keywords_comparison_HEDGES_CURRENT.xlsx": summary_current,
        }

        for file_name, df_source in sources.items():
            # Make a copy to avoid modifying the original DataFrame
            df = df_source.copy()
            # Add the 'File Name' column
            df["File Name"] = file_name
            all_performance_data.append(df)

        # Combine all the individual DataFrames into one
        model_performance_summary = pd.concat(all_performance_data, ignore_index=True)

        # Clean up the 'Category' names for consistency and readability
        model_performance_summary['Category'] = model_performance_summary['Category'].str.replace(
            r' \(All Derivatives: Hedges \+ Liabilities \+ Embedded\)',
            ' (All Derivatives)',
            regex=True
        ).str.replace(
            r' \(Hedges Only: IR/FX/CP\)',
            ' (Hedges Only)',
            regex=True
        )

        # Ensure the columns are in the desired final order
        desired_columns = ['Category', 'File Name', 'Accuracy', 'Precision', 'Recall', 'F1_Score']
        model_performance_summary = model_performance_summary[desired_columns]

        return {
            # Current only - Hedges (IR/FX/CP)
            "comparison_current": comparison_current,
            "detailed_current": detailed_current,
            "confusion_overall_current": confusion_overall_current,
            "confusion_fx_current": confusion_fx_current,
            "confusion_ir_current": confusion_ir_current,
            "confusion_cp_current": confusion_cp_current,
            "summary_current": summary_current,
            # Current only - All Derivatives (Hedges + Liabilities + Embedded)
            "detailed_any_deriv_current": detailed_any_deriv_current,
            "confusion_any_deriv_current": confusion_any_deriv_current,
            "summary_any_deriv_current": summary_any_deriv_current,
            "model_only_current": model_only_current,
            # Current + Historic - Hedges (IR/FX/CP)
            "comparison_all": comparison_all,
            "detailed_all": detailed_all,
            "confusion_overall_all": confusion_overall_all,
            "confusion_fx_all": confusion_fx_all,
            "confusion_ir_all": confusion_ir_all,
            "confusion_cp_all": confusion_cp_all,
            "summary_all": summary_all,
            # Current + Historic - All Derivatives (Hedges + Liabilities + Embedded)
            "detailed_any_deriv_all": detailed_any_deriv_all,
            "confusion_any_deriv_all": confusion_any_deriv_all,
            "summary_any_deriv_all": summary_any_deriv_all,
            "model_only_all": model_only_all,
            # Comparison
            "comparison_summary": comparison_summary,
            "model_performance_summary": model_performance_summary,
        }

    except FileNotFoundError:
        print(
            f"  Warning: {DERIVATIVES_CSV_PATH} not found. Skipping keyword vs. model analysis."
        )
        return None


def get_sentence_analysis():
    """Get sentence analysis with server predictions using parallel processing."""
    wr = get_final_results()
    if wr.empty:
        print("No processed results found for sentence analysis")
        return pd.DataFrame()

    print(f"Processing {len(wr):,} rows with parallel processing...")

    # Prepare data for parallel processing
    row_data_list = [
        (row.cik, row.year, row.url, row.server_response)
        for row in wr.itertuples(index=False)
    ]

    # Process in parallel
    num_workers = mp.cpu_count()
    print(f"Using {num_workers} CPU cores for row processing")

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = list(
            tqdm(
                executor.map(process_row_for_analysis, row_data_list),
                total=len(row_data_list),
                desc="Analyzing sentences",
            )
        )

    # Filter out None results
    analysis_data = [r for r in results if r is not None]
    sa = pd.DataFrame(analysis_data)
    sa = sa.fillna({col: 0 for col in sa.select_dtypes("number").columns})

    print(f"Sentence analysis for {len(sa)} reports:")
    print(f"Computing Excel sheets in parallel...")

    # --- Define label groups ---
    hedge_labels_current = [id2label[0], id2label[8], id2label[10], id2label[12]]
    hedge_labels_historic = [id2label[1], id2label[9], id2label[11], id2label[13]]
    label_cols = [id2label[i] for i in id2label]
    exclude_cols = [id2label[i] for i in id2label if i != 2]
    hedge_types = {
        "General": [id2label[0], id2label[1]],
        "IR": [id2label[8], id2label[9]],
        "FX": [id2label[10], id2label[11]],
        "CP": [id2label[12], id2label[13]],
    }
    hedge_label_groups = hedge_labels_current + hedge_labels_historic

    # Submit all computation tasks in parallel
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            "current": executor.submit(
                compute_firms_current_hedge, sa, hedge_labels_current
            ),
            "historic": executor.submit(
                compute_firms_historic_only,
                sa,
                hedge_labels_historic,
                hedge_labels_current,
            ),
            "speculation": executor.submit(
                compute_firms_label2_only, sa, id2label[2], exclude_cols
            ),
            "liabilities": executor.submit(
                compute_firms_liabilities, sa, id2label[4], id2label[5]
            ),
            "embedded": executor.submit(
                compute_embedded_derivatives, sa, id2label[6], id2label[7]
            ),
            "unique": executor.submit(compute_unique_counts, sa, label_cols),
            "cooc": executor.submit(compute_label_cooccurrence, sa, label_cols),
            "hedge_type": executor.submit(compute_hedge_by_type, sa, hedge_types),
            "hedge_cross": executor.submit(compute_hedge_cross, sa, hedge_label_groups),
            "keyword_analysis": executor.submit(
                analyze_keyword_vs_model, sa, hedge_labels_current
            ),
        }

        print("  Computing parallel tasks...")
        results = {k: f.result() for k, f in futures.items()}

    print("Writing all results to Excel files...")
    write_workbooks(
        keyword_model_comparison=results["keyword_analysis"],
        sa=sa,
        other_results=results,
        max_workers=num_workers,
    )

    # Save to Google Drive if in Colab
    if IS_COLAB:
        print("Saving results to Google Drive...")
        subprocess.run(f"cp *.xlsx {DRIVE_PATH}/{DRIVE_KEYWORDS_PATH}/.", shell=True)

    return sa


def write_workbooks(
    keyword_model_comparison,
    sa,
    other_results,
    base_path=KEYWORDS_EXCEL_PATH,
    max_workers=4,
):
    """
    Write main and keyword comparison Excel workbooks in parallel.
    """
    base_path = Path(base_path)

    # --- 1. Main server workbook ---
    main_server_workbook = {
        "filename": SERVER_EXCEL_PATH,
        "description": "Server Sentence Analysis",
        "sheets": {
            "all_reports": (sa, False),
            "Current Hedging": (other_results["current"], False),
            "Hedging Past Year": (other_results["historic"], False),
            "Speculation Only": (other_results["speculation"], False),
            "Derivative Liabilities Warrants": (other_results["liabilities"], False),
            "Embedded Derivatives": (other_results["embedded"], False),
            "unique_per_year": (other_results["unique"], False),
            "label_cooccurrence": (other_results["cooc"], True),
            "Hedging by Type": (other_results["hedge_type"], False),
            "Hedge Type Cross": (other_results["hedge_cross"], True),
        },
    }

    # --- 2. Keyword workbooks ---
    keyword_workbooks = [
        {
            "filename": base_path.with_name(base_path.stem + "_HEDGES_CURRENT.xlsx"),
            "description": "Current Only - Hedges",
            "sheets": {
                "Summary_Current_Only": ("summary_current", False),
                "Detailed_Current_Only": ("detailed_current", False),
                "Basic_Current_Only": ("comparison_current", False),
                "Confusion_Overall_Curr": ("confusion_overall_current", True),
                "Confusion_FX_Curr": ("confusion_fx_current", True),
                "Confusion_IR_Curr": ("confusion_ir_current", True),
                "Confusion_CP_Curr": ("confusion_cp_current", True),
            },
        },
        {
            "filename": base_path.with_name(base_path.stem + "_HEDGES_ALL.xlsx"),
            "description": "Current+Historic - Hedges",
            "sheets": {
                "Summary_Curr_Historic": ("summary_all", False),
                "Detailed_Curr_Historic": ("detailed_all", False),
                "Basic_Curr_Historic": ("comparison_all", False),
                "Confusion_Overall_All": ("confusion_overall_all", True),
                "Confusion_FX_All": ("confusion_fx_all", True),
                "Confusion_IR_All": ("confusion_ir_all", True),
                "Confusion_CP_All": ("confusion_cp_all", True),
            },
        },
        {
            "filename": base_path.with_name(
                base_path.stem + "_ALL_DERIVATIVES_CURRENT.xlsx"
            ),
            "description": "Current Only - All Derivatives",
            "sheets": {
                "Summary_Current_Only": ("summary_any_deriv_current", False),
                "Detailed_Current_Only": ("detailed_any_deriv_current", False),
                "Basic_Current_Only": ("comparison_current", False),
                "Confusion_Overall_Curr": ("confusion_any_deriv_current", True),
                "Confusion_FX_Curr": ("confusion_fx_current", True),
                "Confusion_IR_Curr": ("confusion_ir_current", True),
                "Confusion_CP_Curr": ("confusion_cp_current", True),
                "ModelOnly_Liab_Embed": ("model_only_current", False),
            },
        },
        {
            "filename": base_path.with_name(
                base_path.stem + "_ALL_DERIVATIVES_FULL.xlsx"
            ),
            "description": "Current+Historic - All Derivatives",
            "sheets": {
                "Summary_Curr_Historic": ("summary_any_deriv_all", False),
                "Detailed_Curr_Historic": ("detailed_any_deriv_all", False),
                "Basic_Curr_Historic": ("comparison_all", False),
                "Confusion_Overall_All": ("confusion_any_deriv_all", True),
                "Confusion_FX_All": ("confusion_fx_all", True),
                "Confusion_IR_All": ("confusion_ir_all", True),
                "Confusion_CP_All": ("confusion_cp_all", True),
                "ModelOnly_Liab_Embed": ("model_only_all", False),
            },
        },
        {
            # Separate workbook just for KW_Model_Comparison
            "filename": base_path.with_name(
                base_path.stem + "_KW_MODEL_COMPARISON.xlsx"
            ),
            "description": "Keyword vs Model Comparison (Standalone)",
            "sheets": {
                "KW_Model_Comparison": ("comparison_summary", False),
                # Add this line to create the new sheet
                "Model_Performance_Summary": ("model_performance_summary", False)
            },
        },
    ]

    all_workbooks = [main_server_workbook] + keyword_workbooks

    def write_one_workbook(config):
        filename = Path(config["filename"])
        filename.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(filename, engine="xlsxwriter") as writer:
            workbook = writer.book
            workbook.strings_to_urls = False

            for sheet_name, data_cfg in config["sheets"].items():
                if isinstance(data_cfg[0], pd.DataFrame):
                    df = data_cfg[0]
                else:
                    df = keyword_model_comparison.get(data_cfg[0])

                if df is None or df.empty:
                    print(f"⚠️  Skipped '{sheet_name}' in {config['description']}")
                    continue

                df.to_excel(writer, sheet_name=sheet_name, index=data_cfg[1])

                worksheet = writer.sheets[sheet_name]
                for i, col in enumerate(df.columns):
                    try:
                        max_len = (
                            max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                        )
                        worksheet.set_column(i, i, max_len)
                    except Exception:
                        pass

        return f"✅ {config['description']} saved → {filename}"

    print(
        f"\n🚀 Writing {len(all_workbooks)} workbooks with {max_workers} threads...\n"
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(write_one_workbook, cfg) for cfg in all_workbooks]
        for f in as_completed(futures):
            try:
                print(f.result())
            except Exception as e:
                print(f"❌ Error writing workbook: {e}")

    print("\n🎉 All Excel workbooks generated successfully!\n")


def process_sentence_chunk(chunk_data):
    """Process a chunk of sentences for label mapping - designed for ProcessPoolExecutor"""
    results = []

    for row_data in chunk_data:
        cik, year, url, matches, predictions = row_data

        # Defensive check: align lengths
        min_len = min(len(matches), len(predictions))

        for i in range(min_len):
            sentence = matches[i]
            pred = predictions[i]
            label = id2label.get(pred, "Unknown")

            results.append({
                "cik": cik,
                "year": year,
                "url": url,
                "sentence": sentence,
                "label_id": pred,
                "label": label,
            })

    return results


def build_sentence_label_excel():
    """Build sentence-label Excel files using parallel processing, split into separate workbooks by label groups."""
    # Load both DB tables with a join to get cik and year
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT
            r.cik,
            r.year,
            w.url,
            w.matches,
            s.server_response
        FROM webpage_result w
        JOIN report_data r ON w.url = r.url
        JOIN server_result s ON w.url = s.url
    """
    combined_df = pd.read_sql(query, conn)
    conn.close()

    print(
        f"Processing {len(combined_df):,} reports for sentence-label mapping...")

    # Prepare data for parallel processing
    row_data_list = []
    for _, row in combined_df.iterrows():
        matches = json.loads(row["matches"])
        predictions = json.loads(row["server_response"])
        row_data_list.append(
            (row["cik"], row["year"], row["url"], matches, predictions))

    # Split into chunks for better load balancing
    num_workers = mp.cpu_count()
    chunk_size = max(1, len(row_data_list) // (num_workers * 4))
    chunks = [row_data_list[i:i + chunk_size]
              for i in range(0, len(row_data_list), chunk_size)]

    print(f"Using {num_workers} CPU cores, processing {len(chunks)} chunks")

    # Process in parallel
    all_rows = []
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = list(tqdm(
            executor.map(process_sentence_chunk, chunks),
            total=len(chunks),
            desc="Building sentence labels"
        ))

        # Flatten results
        for chunk_result in results:
            all_rows.extend(chunk_result)

    # Build final DataFrame
    final_df = pd.DataFrame(all_rows)
    print(f"Created DataFrame with {len(final_df):,} sentence-label mappings")

    # Define label groupings (pairs of related labels)
    label_groups = {
        "General_Hedge_0-1": [0, 1],
        "Speculation_2": [2],
        "Irrelevant_3": [3],
        "Liabilities_Warrants_4-5": [4, 5],
        "Embedded_Derivatives_6-7": [6, 7],
        "Interest_Rate_8-9": [8, 9],
        "Foreign_Exchange_10-11": [10, 11],
        "Commodity_Price_12-13": [12, 13],
    }

    # Create a mapping from label_id to group name
    label_id_to_group = {}
    for group_name, label_ids in label_groups.items():
        for label_id in label_ids:
            label_id_to_group[label_id] = group_name

    print(f"\nWriting to separate Excel workbooks by label group...")

    # Group data by label groups
    final_df['group'] = final_df['label_id'].map(label_id_to_group)

    # Handle any unmapped labels (shouldn't happen, but defensive coding)
    unmapped = final_df[final_df['group'].isna()]
    if not unmapped.empty:
        print(
            f"  Warning: Found {len(unmapped)} rows with unmapped label_ids: {unmapped['label_id'].unique()}")
        final_df['group'] = final_df['group'].fillna('Other')

    try:
        # Write each group to a separate workbook
        for group_name, label_ids in label_groups.items():
            group_df = final_df[final_df['label_id'].isin(label_ids)].copy()

            if group_df.empty:
                print(f"  Skipping {group_name} (no data)")
                continue

            # Create filename
            file_path = SENTENCE_PATH.replace('.xlsx', f'_{group_name}.xlsx')

            print(
                f"\n  Writing {group_name} workbook ({len(group_df):,} rows)...")

            with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
                # Disable automatic URL conversion
                workbook = writer.book
                workbook.strings_to_urls = False

                # Write complete group dataset to first sheet
                group_df_clean = group_df.drop(columns=['group'])
                print(f"    - 'All_{group_name}' sheet...")
                group_df_clean.to_excel(
                    writer, sheet_name=f"All_{group_name}"[:31], index=False)

                # Write separate sheet for each label in this group
                unique_labels_in_group = sorted(group_df["label"].unique())

                for label in unique_labels_in_group:
                    label_df = group_df_clean[group_df_clean["label"] == label]
                    sheet_name = str(label)[:31].replace(
                        "/", "-").replace("\\", "-").replace(":", "-")
                    print(
                        f"    - '{sheet_name}' sheet ({len(label_df):,} rows)...")
                    label_df.to_excel(
                        writer, sheet_name=sheet_name, index=False)

                # Write summary for this group
                print(f"    - 'Summary' sheet...")
                summary_stats = []

                for label in unique_labels_in_group:
                    label_data = group_df_clean[group_df_clean["label"] == label]
                    label_id = label_data["label_id"].iloc[0]

                    stats = {
                        "label": label,
                        "label_id": label_id,
                        "total_sentences": len(label_data),
                        "unique_firms": label_data["cik"].nunique(),
                        "unique_urls": label_data["url"].nunique(),
                        "year_min": label_data["year"].min(),
                        "year_max": label_data["year"].max(),
                        "avg_sentences_per_firm": len(label_data) / label_data["cik"].nunique(),
                        "avg_sentences_per_url": len(label_data) / label_data["url"].nunique(),
                    }
                    summary_stats.append(stats)

                summary = pd.DataFrame(summary_stats)
                summary["pct_of_group"] = (
                    summary["total_sentences"] / len(group_df_clean) * 100).round(2)

                summary = summary[[
                    "label", "label_id", "total_sentences", "pct_of_group",
                    "unique_firms", "unique_urls",
                    "avg_sentences_per_firm", "avg_sentences_per_url",
                    "year_min", "year_max"
                ]]

                summary = summary.sort_values(
                    "total_sentences", ascending=False).reset_index(drop=True)
                summary.to_excel(writer, sheet_name="Summary", index=False)

                # Format the summary sheet
                worksheet = writer.sheets["Summary"]
                worksheet.set_column('A:A', 30)
                worksheet.set_column('B:B', 10)
                worksheet.set_column('C:D', 18)
                worksheet.set_column('E:F', 15)
                worksheet.set_column('G:H', 22)
                worksheet.set_column('I:J', 12)

                number_format = workbook.add_format({'num_format': '#,##0'})
                percent_format = workbook.add_format({'num_format': '0.00"%"'})
                decimal_format = workbook.add_format(
                    {'num_format': '#,##0.00'})

                for row_num in range(1, len(summary) + 1):
                    worksheet.write_number(
                        row_num, 2, summary.iloc[row_num-1]["total_sentences"], number_format)
                    worksheet.write_number(
                        row_num, 3, summary.iloc[row_num-1]["pct_of_group"], percent_format)
                    worksheet.write_number(
                        row_num, 4, summary.iloc[row_num-1]["unique_firms"], number_format)
                    worksheet.write_number(
                        row_num, 5, summary.iloc[row_num-1]["unique_urls"], number_format)
                    worksheet.write_number(
                        row_num, 6, summary.iloc[row_num-1]["avg_sentences_per_firm"], decimal_format)
                    worksheet.write_number(
                        row_num, 7, summary.iloc[row_num-1]["avg_sentences_per_url"], decimal_format)

                total_row = len(summary) + 2
                worksheet.write(total_row, 0, "TOTAL",
                                workbook.add_format({'bold': True}))
                worksheet.write_number(total_row, 2, len(
                    group_df_clean), number_format)
                worksheet.write_number(total_row, 3, 100.0, percent_format)
                worksheet.write_number(
                    total_row, 4, group_df_clean["cik"].nunique(), number_format)
                worksheet.write_number(
                    total_row, 5, group_df_clean["url"].nunique(), number_format)

            print(f"  ✓ Saved {file_path}")

            # Save to Google Drive if in Colab
            if IS_COLAB:
                subprocess.run(f"cp {file_path} {DRIVE_PATH}/{DRIVE_SENTENCE_PATH}/.", shell=True)

        # Create overall summary workbook
        print(f"\n  Writing overall summary workbook...")
        summary_file = SENTENCE_PATH.replace('.xlsx', '_Overall_Summary.xlsx')

        with pd.ExcelWriter(summary_file, engine="xlsxwriter") as writer:
            # Disable automatic URL conversion
            workbook = writer.book
            workbook.strings_to_urls = False
            # Overall summary by label
            overall_summary_stats = []
            for label in sorted(final_df["label"].unique()):
                label_data = final_df[final_df["label"] == label]
                label_id = label_data["label_id"].iloc[0]
                group = label_id_to_group.get(label_id, "Other")

                stats = {
                    "group": group,
                    "label": label,
                    "label_id": label_id,
                    "total_sentences": len(label_data),
                    "unique_firms": label_data["cik"].nunique(),
                    "unique_urls": label_data["url"].nunique(),
                    "year_min": label_data["year"].min(),
                    "year_max": label_data["year"].max(),
                }
                overall_summary_stats.append(stats)

            overall_summary = pd.DataFrame(overall_summary_stats)
            overall_summary["pct_of_total"] = (
                overall_summary["total_sentences"] / len(final_df) * 100).round(2)

            overall_summary = overall_summary[[
                "group", "label", "label_id", "total_sentences", "pct_of_total",
                "unique_firms", "unique_urls", "year_min", "year_max"
            ]]

            overall_summary = overall_summary.sort_values(
                "total_sentences", ascending=False).reset_index(drop=True)
            overall_summary.to_excel(
                writer, sheet_name="Overall_Summary", index=False)

            # Format
            worksheet = writer.sheets["Overall_Summary"]
            worksheet.set_column('A:A', 25)
            worksheet.set_column('B:B', 30)
            worksheet.set_column('C:G', 15)
            worksheet.set_column('H:I', 12)

        print(f"  ✓ Saved {summary_file}")

        if IS_COLAB:
            subprocess.run(
                f"cp {summary_file} {DRIVE_PATH}/{DRIVE_SENTENCE_PATH}/.", shell=True)

    except ImportError:
        print(" (pip install xlsxwriter for better performance)")
        return pd.DataFrame()

    print(f"\n{'='*70}")
    print(
        f"Saved {len(final_df):,} sentence-label mappings to {len(label_groups)} workbooks")
    print(f"Each workbook contains:")
    print(f"  - 1 'All_[Group]' sheet with all data for that group")
    print(f"  - Separate sheets for each label in the group")
    print(f"  - 1 'Summary' sheet with statistics")
    print(f"{'='*70}")

    return final_df

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
        reports_to_process[i: i + CHUNK_SIZE]
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
                    debug_print(
                        f"Error processing {future_to_report[future].url}: {e}")
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
            print(f"  → Saving to Google Drive...")
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

create_db()
existing_report_df = fetch_report_data()
print(f"Found {len(existing_report_df)} reports in database")
with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
    keyword_data = json.load(f)

id2label = {int(id): label for id, label in keyword_data["id2label"].items()}
label2id = {label: int(id) for id, label in id2label.items()}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Model Classification and Analysis Script")
    print("=" * 70)

    # Initialize database
    create_db()

    # Process reports in chunks
    print("\nProcessing reports with server predictions...")
    total_processed = process_reports_in_chunks()

    print(
        f"\nProcessed {total_processed} new reports in chunked parallel mode.")

    # Generate analysis
    print("\n" + "=" * 70)
    print("Generating sentence analysis...")
    print("=" * 70)
    sa = get_sentence_analysis()
    print(f"\nFirst 10 rows of analysis:")
    print(sa.head(10))

    # Build sentence-label mapping
    print("\n" + "=" * 70)
    print("Building sentence-label Excel file...")
    print("=" * 70)
    sentence_label_df = build_sentence_label_excel()
    print(f"\nFirst 10 rows of sentence labels:")
    print(sentence_label_df.head(10))

    # Final save to Drive if in Colab
    if IS_COLAB:
        print("\nFinal database sync to Google Drive...")
        subprocess.run(SAVE_SHELL_CMD, shell=True)

    print("\n" + "=" * 70)
    print("All done!")
    print("=" * 70)
