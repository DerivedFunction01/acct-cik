import pandas as pd
import json
import sqlite3
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
        predictions = server_response if isinstance(server_response, list) else []

    if not predictions:
        return None

    # Map IDs -> labels
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
    firms_historic_only = firm_historic[(firm_historic > 0) & (firm_current == 0)].index
    return sa[sa["cik"].isin(firms_historic_only)]


def compute_firms_speculative_only(sa):
    """
    Parallel task: filter firms with only speculative/policy mentions - OPTIMIZED
    
    This function identifies firms that have speculative/policy derivative mentions
    but NO actual derivative usage (hedges, liabilities, or embedded derivatives).
    
    Speculative labels: 2 (Generic), 14 (IR), 15 (FX), 16 (CP)
    Actual usage labels: 0, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13
    """
    # Speculative/policy labels
    spec_labels = [id2label[2], id2label[14], id2label[15], id2label[16]]
    
    # All actual usage labels (current + historic for all types)
    actual_labels = [
        id2label[0], id2label[1],    # Generic hedge current + historic
        id2label[4], id2label[5],    # Liabilities current + historic
        id2label[6], id2label[7],    # Embedded current + historic
        id2label[8], id2label[9],    # IR hedge current + historic
        id2label[10], id2label[11],  # FX hedge current + historic
        id2label[12], id2label[13],  # CP hedge current + historic
    ]
    
    # Aggregate per firm
    firm_spec = sa.groupby("cik")[spec_labels].sum().sum(axis=1)
    firm_actual = sa.groupby("cik")[actual_labels].sum().sum(axis=1)
    
    # Find firms where speculative > 0 AND actual == 0
    firms_spec_only = firm_spec[(firm_spec > 0) & (firm_actual == 0)].index
    
    return sa[sa["cik"].isin(firms_spec_only)]


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
    sa_indexed["cik_year"] = (
        sa_indexed["cik"].astype(str) + "_" + sa_indexed["year"].astype(str)
    )

    hedge_type_records = []

    for hedge_name, labels in hedge_types.items():
        # Aggregate per (cik, year), then filter
        firm_year_totals = sa.groupby(["cik", "year"])[labels].sum().sum(axis=1)
        firms_with_hedge = firm_year_totals[firm_year_totals > 0].index

        # Create lookup set for fast membership testing
        firms_lookup = set(f"{cik}_{year}" for cik, year in firms_with_hedge)

        # Filter using the lookup
        temp = sa_indexed[sa_indexed["cik_year"].isin(firms_lookup)].copy()
        temp["hedge_type"] = hedge_name
        temp = temp.drop(columns=["cik_year"])

        if not temp.empty:
            hedge_type_records.append(temp)

    if hedge_type_records:
        return pd.concat(hedge_type_records, ignore_index=True)
    else:
        return pd.DataFrame(columns=["cik", "year", "hedge_type"])


def compute_hedge_cross(sa, hedge_label_groups):
    """Parallel task: compute hedge type cross-analysis"""
    hedge_flags = sa.groupby("cik")[hedge_label_groups].sum().gt(0).astype(int)

    # Map to current hedge categories only (merge historic)
    hedge_flags_simple = pd.DataFrame(
        {
            "General": hedge_flags[[hedge_label_groups[0], hedge_label_groups[4]]].max(
                axis=1
            ),
            "IR": hedge_flags[[hedge_label_groups[1], hedge_label_groups[5]]].max(
                axis=1
            ),
            "FX": hedge_flags[[hedge_label_groups[2], hedge_label_groups[6]]].max(
                axis=1
            ),
            "CP": hedge_flags[[hedge_label_groups[3], hedge_label_groups[7]]].max(
                axis=1
            ),
        }
    )

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
        model_performance_summary["Category"] = (
            model_performance_summary["Category"]
            .str.replace(
                r" \(All Derivatives: Hedges \+ Liabilities \+ Embedded\)",
                " (All Derivatives)",
                regex=True,
            )
            .str.replace(r" \(Hedges Only: IR/FX/CP\)", " (Hedges Only)", regex=True)
        )

        # Ensure the columns are in the desired final order
        desired_columns = [
            "Category",
            "File Name",
            "Accuracy",
            "Precision",
            "Recall",
            "F1_Score",
        ]
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


def analyze_keyword_vs_speculative_policy(sa, hedge_labels_current):
    """
    Analyzes keyword-based derivatives data against speculative/policy labels.
    Examines if firms mentioning derivatives policies actually use derivatives.
    Includes comprehensive "any derivatives" category (hedges + liabilities + embedded).
    """
    print("  Comparing keyword search with speculative/policy labels...")
    try:
        # Load original keyword-based data
        deriv_df = pd.read_csv(DERIVATIVES_CSV_PATH)
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

        # --- SPECULATIVE/POLICY FLAGS ---

        # Generic/Unknown Speculative (id2label[2])
        spec_generic = sa.groupby(["cik", "year"])[id2label[2]].sum() > 0
        spec_generic = spec_generic.reset_index(name="spec_generic")

        # IR Speculative (id2label[14])
        spec_ir = sa.groupby(["cik", "year"])[id2label[14]].sum() > 0
        spec_ir = spec_ir.reset_index(name="spec_ir")

        # FX Speculative (id2label[15])
        spec_fx = sa.groupby(["cik", "year"])[id2label[15]].sum() > 0
        spec_fx = spec_fx.reset_index(name="spec_fx")

        # CP Speculative (id2label[16])
        spec_cp = sa.groupby(["cik", "year"])[id2label[16]].sum() > 0
        spec_cp = spec_cp.reset_index(name="spec_cp")

        # Any speculative/policy mention (hedges only)
        spec_any_hedges = (
            sa.groupby(["cik", "year"])[
                [id2label[2], id2label[14], id2label[15], id2label[16]]
            ]
            .sum()
            .sum(axis=1)
            > 0
        )
        spec_any_hedges = spec_any_hedges.reset_index(name="spec_any_hedges")

        # --- ACTUAL USAGE FLAGS (CURRENT ONLY) ---

        # Generic/Unknown Hedge (current) - id2label[0]
        actual_generic = sa.groupby(["cik", "year"])[id2label[0]].sum() > 0
        actual_generic = actual_generic.reset_index(name="actual_generic")

        # IR Hedge (current) - id2label[8]
        actual_ir = sa.groupby(["cik", "year"])[id2label[8]].sum() > 0
        actual_ir = actual_ir.reset_index(name="actual_ir")

        # FX Hedge (current) - id2label[10]
        actual_fx = sa.groupby(["cik", "year"])[id2label[10]].sum() > 0
        actual_fx = actual_fx.reset_index(name="actual_fx")

        # CP Hedge (current) - id2label[12]
        actual_cp = sa.groupby(["cik", "year"])[id2label[12]].sum() > 0
        actual_cp = actual_cp.reset_index(name="actual_cp")

        # Any actual hedge usage (current) - hedges only
        actual_any_hedges = (
            sa.groupby(["cik", "year"])[hedge_labels_current].sum().sum(axis=1) > 0
        )
        actual_any_hedges = actual_any_hedges.reset_index(name="actual_any_hedges")

        # Derivative Liabilities/Warrants (current) - id2label[4]
        actual_liabilities = sa.groupby(["cik", "year"])[id2label[4]].sum() > 0
        actual_liabilities = actual_liabilities.reset_index(name="actual_liabilities")

        # Embedded Derivatives (current) - id2label[6]
        actual_embedded = sa.groupby(["cik", "year"])[id2label[6]].sum() > 0
        actual_embedded = actual_embedded.reset_index(name="actual_embedded")

        # ANY DERIVATIVES (hedges + liabilities + embedded) - COMPREHENSIVE
        all_derivative_labels = hedge_labels_current + [id2label[4], id2label[6]]
        actual_any_all = (
            sa.groupby(["cik", "year"])[all_derivative_labels].sum().sum(axis=1) > 0
        )
        actual_any_all = actual_any_all.reset_index(name="actual_any_all")

        # --- MERGE ALL DATA ---

        comparison = keyword_users.copy()

        # Merge speculative flags
        comparison = comparison.merge(spec_generic, on=["cik", "year"], how="outer")
        comparison = comparison.merge(spec_ir, on=["cik", "year"], how="outer")
        comparison = comparison.merge(spec_fx, on=["cik", "year"], how="outer")
        comparison = comparison.merge(spec_cp, on=["cik", "year"], how="outer")
        comparison = comparison.merge(spec_any_hedges, on=["cik", "year"], how="outer")

        # Merge actual usage flags
        comparison = comparison.merge(actual_generic, on=["cik", "year"], how="outer")
        comparison = comparison.merge(actual_ir, on=["cik", "year"], how="outer")
        comparison = comparison.merge(actual_fx, on=["cik", "year"], how="outer")
        comparison = comparison.merge(actual_cp, on=["cik", "year"], how="outer")
        comparison = comparison.merge(
            actual_any_hedges, on=["cik", "year"], how="outer"
        )
        comparison = comparison.merge(
            actual_liabilities, on=["cik", "year"], how="outer"
        )
        comparison = comparison.merge(actual_embedded, on=["cik", "year"], how="outer")
        comparison = comparison.merge(actual_any_all, on=["cik", "year"], how="outer")

        # Fill NaN with False
        for col in comparison.columns:
            if col not in ["cik", "year"]:
                comparison[col] = comparison[col].fillna(False).astype(bool).astype(int)

        # --- COMPUTE TRANSLATION METRICS ---

        def compute_translation_rate(spec_col, actual_col, df):
            """
            Compute what % of firms with speculative mentions actually use derivatives.
            """
            spec_firms = df[df[spec_col] == 1]
            if len(spec_firms) == 0:
                return {
                    "Total_Spec_Mentions": 0,
                    "Actual_Users": 0,
                    "Translation_Rate": 0.0,
                    "Non_Users": 0,
                }

            actual_users = (spec_firms[actual_col] == 1).sum()
            total_spec = len(spec_firms)

            return {
                "Total_Spec_Mentions": total_spec,
                "Actual_Users": actual_users,
                "Non_Users": total_spec - actual_users,
                "Translation_Rate": (
                    round((actual_users / total_spec) * 100, 2)
                    if total_spec > 0
                    else 0.0
                ),
            }

        # Translation rates for specific types
        trans_generic = compute_translation_rate(
            "spec_generic", "actual_generic", comparison
        )
        trans_ir = compute_translation_rate("spec_ir", "actual_ir", comparison)
        trans_fx = compute_translation_rate("spec_fx", "actual_fx", comparison)
        trans_cp = compute_translation_rate("spec_cp", "actual_cp", comparison)

        # Translation rates for aggregate categories
        trans_any_hedges = compute_translation_rate(
            "spec_any_hedges", "actual_any_hedges", comparison
        )
        trans_any_all = compute_translation_rate(
            "spec_any_hedges", "actual_any_all", comparison
        )

        # Summary table
        translation_summary = pd.DataFrame(
            [
                {"Category": "Any Hedge (Gen/IR/FX/CP)", **trans_any_hedges},
                {"Category": "Any Derivative (Hedges+Liab+Embed)", **trans_any_all},
                {"Category": "Generic/Unknown", **trans_generic},
                {"Category": "Interest Rate (IR)", **trans_ir},
                {"Category": "Foreign Exchange (FX)", **trans_fx},
                {"Category": "Commodity Price (CP)", **trans_cp},
            ]
        )

        # --- MODEL-ONLY STATS (NO SPECULATIVE COMPARISON) ---

        def calculate_model_only_stats(model_col, df):
            """Calculate statistics for model predictions without speculative comparison"""
            positive = (df[model_col] == 1).sum()
            negative = (df[model_col] == 0).sum()
            total = len(df)

            return {
                "Total": total,
                "Model_Positive": positive,
                "Model_Negative": negative,
                "Positive_Rate": round((positive / total) * 100, 2) if total > 0 else 0,
            }

        stats_liab = calculate_model_only_stats("actual_liabilities", comparison)
        stats_embed = calculate_model_only_stats("actual_embedded", comparison)

        model_only_summary = pd.DataFrame(
            [
                {"Category": "Derivative Liabilities/Warrants", **stats_liab},
                {"Category": "Embedded Derivatives", **stats_embed},
            ]
        )

        # --- KEYWORD VS SPECULATIVE COMPARISON ---

        # Cross-tabulation: Keyword mentions vs Speculative mentions
        keyword_vs_spec = pd.DataFrame(
            {
                "Category": ["Any Hedge", "Generic", "IR", "FX", "CP"],
                "Keyword_Only": [
                    (
                        (comparison["keyword_user"] == 1)
                        & (comparison["spec_any_hedges"] == 0)
                    ).sum(),
                    (
                        (comparison["keyword_user"] == 1)
                        & (comparison["spec_generic"] == 0)
                    ).sum(),
                    (
                        (comparison["keyword_ir"] == 1) & (comparison["spec_ir"] == 0)
                    ).sum(),
                    (
                        (comparison["keyword_fx"] == 1) & (comparison["spec_fx"] == 0)
                    ).sum(),
                    (
                        (comparison["keyword_cp"] == 1) & (comparison["spec_cp"] == 0)
                    ).sum(),
                ],
                "Both": [
                    (
                        (comparison["keyword_user"] == 1)
                        & (comparison["spec_any_hedges"] == 1)
                    ).sum(),
                    (
                        (comparison["keyword_user"] == 1)
                        & (comparison["spec_generic"] == 1)
                    ).sum(),
                    (
                        (comparison["keyword_ir"] == 1) & (comparison["spec_ir"] == 1)
                    ).sum(),
                    (
                        (comparison["keyword_fx"] == 1) & (comparison["spec_fx"] == 1)
                    ).sum(),
                    (
                        (comparison["keyword_cp"] == 1) & (comparison["spec_cp"] == 1)
                    ).sum(),
                ],
                "Spec_Only": [
                    (
                        (comparison["keyword_user"] == 0)
                        & (comparison["spec_any_hedges"] == 1)
                    ).sum(),
                    (
                        (comparison["keyword_user"] == 0)
                        & (comparison["spec_generic"] == 1)
                    ).sum(),
                    (
                        (comparison["keyword_ir"] == 0) & (comparison["spec_ir"] == 1)
                    ).sum(),
                    (
                        (comparison["keyword_fx"] == 0) & (comparison["spec_fx"] == 1)
                    ).sum(),
                    (
                        (comparison["keyword_cp"] == 0) & (comparison["spec_cp"] == 1)
                    ).sum(),
                ],
                "Neither": [
                    (
                        (comparison["keyword_user"] == 0)
                        & (comparison["spec_any_hedges"] == 0)
                    ).sum(),
                    (
                        (comparison["keyword_user"] == 0)
                        & (comparison["spec_generic"] == 0)
                    ).sum(),
                    (
                        (comparison["keyword_ir"] == 0) & (comparison["spec_ir"] == 0)
                    ).sum(),
                    (
                        (comparison["keyword_fx"] == 0) & (comparison["spec_fx"] == 0)
                    ).sum(),
                    (
                        (comparison["keyword_cp"] == 0) & (comparison["spec_cp"] == 0)
                    ).sum(),
                ],
            }
        )

        # --- DETAILED BREAKDOWN ---

        comparison["generic_category"] = comparison.apply(
            lambda row: (
                "Spec->Actual"
                if row["spec_generic"] == 1 and row["actual_generic"] == 1
                else (
                    "Spec->NoActual"
                    if row["spec_generic"] == 1 and row["actual_generic"] == 0
                    else (
                        "NoSpec->Actual"
                        if row["spec_generic"] == 0 and row["actual_generic"] == 1
                        else "NoSpec->NoActual"
                    )
                )
            ),
            axis=1,
        )

        comparison["ir_category"] = comparison.apply(
            lambda row: (
                "Spec->Actual"
                if row["spec_ir"] == 1 and row["actual_ir"] == 1
                else (
                    "Spec->NoActual"
                    if row["spec_ir"] == 1 and row["actual_ir"] == 0
                    else (
                        "NoSpec->Actual"
                        if row["spec_ir"] == 0 and row["actual_ir"] == 1
                        else "NoSpec->NoActual"
                    )
                )
            ),
            axis=1,
        )

        comparison["fx_category"] = comparison.apply(
            lambda row: (
                "Spec->Actual"
                if row["spec_fx"] == 1 and row["actual_fx"] == 1
                else (
                    "Spec->NoActual"
                    if row["spec_fx"] == 1 and row["actual_fx"] == 0
                    else (
                        "NoSpec->Actual"
                        if row["spec_fx"] == 0 and row["actual_fx"] == 1
                        else "NoSpec->NoActual"
                    )
                )
            ),
            axis=1,
        )

        comparison["cp_category"] = comparison.apply(
            lambda row: (
                "Spec->Actual"
                if row["spec_cp"] == 1 and row["actual_cp"] == 1
                else (
                    "Spec->NoActual"
                    if row["spec_cp"] == 1 and row["actual_cp"] == 0
                    else (
                        "NoSpec->Actual"
                        if row["spec_cp"] == 0 and row["actual_cp"] == 1
                        else "NoSpec->NoActual"
                    )
                )
            ),
            axis=1,
        )

        comparison["any_hedges_category"] = comparison.apply(
            lambda row: (
                "Spec->Actual"
                if row["spec_any_hedges"] == 1 and row["actual_any_hedges"] == 1
                else (
                    "Spec->NoActual"
                    if row["spec_any_hedges"] == 1 and row["actual_any_hedges"] == 0
                    else (
                        "NoSpec->Actual"
                        if row["spec_any_hedges"] == 0 and row["actual_any_hedges"] == 1
                        else "NoSpec->NoActual"
                    )
                )
            ),
            axis=1,
        )

        comparison["any_all_category"] = comparison.apply(
            lambda row: (
                "Spec->Actual"
                if row["spec_any_hedges"] == 1 and row["actual_any_all"] == 1
                else (
                    "Spec->NoActual"
                    if row["spec_any_hedges"] == 1 and row["actual_any_all"] == 0
                    else (
                        "NoSpec->Actual"
                        if row["spec_any_hedges"] == 0 and row["actual_any_all"] == 1
                        else "NoSpec->NoActual"
                    )
                )
            ),
            axis=1,
        )

        return {
            "comparison": comparison,
            "translation_summary": translation_summary,
            "keyword_vs_spec": keyword_vs_spec,
            "model_only_summary": model_only_summary,
        }

    except FileNotFoundError:
        print(
            f"  Warning: {DERIVATIVES_CSV_PATH} not found. Skipping speculative analysis."
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
                compute_firms_speculative_only, sa
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
            "speculative_analysis": executor.submit(
                analyze_keyword_vs_speculative_policy, sa, hedge_labels_current
            ),
        }

        print("  Computing parallel tasks...")
        results = {k: f.result() for k, f in futures.items()}

    print("Writing all results to Excel files...")
    write_workbooks_modular(
        keyword_model_comparison=results["keyword_analysis"],
        sa=sa,
        other_results=results,
        max_workers=num_workers,
    )

    return sa

class WorkbookManager:
    """Manages multiple data sources and writes Excel workbooks in parallel."""

    def __init__(self, base_path=KEYWORDS_EXCEL_PATH):
        self.base_path = Path(base_path)
        self.data_sources = {}

    def register_data_source(self, name, data):
        """Register a data source (dict of DataFrames or single DataFrame)."""
        self.data_sources[name] = data
        return self

    def get_data(self, source_name, key=None):
        """Retrieve data from a registered source."""
        if source_name not in self.data_sources:
            return None

        source = self.data_sources[source_name]

        # If it's already a DataFrame, return it
        if isinstance(source, pd.DataFrame):
            return source

        # If it's a dict and we have a key, return the specific item
        if isinstance(source, dict) and key:
            return source.get(key)

        return None

    def create_workbook_config(self, filename, description, sheets):
        """
        Create a workbook configuration.

        sheets format:
            {
                "SheetName": ("source_name", "key", index_flag),
                "SheetName2": ("source_name", None, False),  # For direct DataFrame sources
                "SheetName3": dataframe_object,  # Direct DataFrame
            }
        """
        return {"filename": filename, "description": description, "sheets": sheets}

    def write_workbook(self, config, auto_width=True, sample_rows=1000):
        """
        Write a single workbook based on configuration.

        Args:
            config: Workbook configuration dict
            auto_width: Enable column auto-width (can be slow for large datasets)
            sample_rows: Number of rows to sample for width calculation (faster)
        """
        filename = Path(config["filename"])
        filename.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(filename, engine="xlsxwriter") as writer:
            workbook = writer.book
            workbook.strings_to_urls = False

            for sheet_name, sheet_config in config["sheets"].items():
                # Handle direct DataFrame
                if isinstance(sheet_config, pd.DataFrame):
                    df = sheet_config
                    index_flag = False
                # Handle tuple configuration
                elif isinstance(sheet_config, tuple):
                    if len(sheet_config) == 3:
                        source_name, key, index_flag = sheet_config
                    else:
                        source_name, key = sheet_config
                        index_flag = False

                    df = self.get_data(source_name, key)
                else:
                    print(
                        f"⚠️  Invalid config for '{sheet_name}' in {config['description']}"
                    )
                    continue

                # Check if data is valid
                if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                    print(f"⚠️  Skipped '{sheet_name}' in {config['description']}")
                    continue

                # Write to Excel
                df.to_excel(writer, sheet_name=sheet_name, index=index_flag)

                # OPTIMIZED: Auto-adjust column widths with sampling
                if auto_width:
                    worksheet = writer.sheets[sheet_name]

                    # Sample rows for width calculation if dataset is large
                    df_sample = (
                        df
                        if len(df) <= sample_rows
                        else df.sample(n=sample_rows, random_state=42)
                    )

                    for i, col in enumerate(df.columns):
                        try:
                            # Calculate max width from sample
                            col_max = df_sample[col].astype(str).str.len().max()
                            header_len = len(str(col))
                            max_len = max(col_max, header_len) + 2

                            # Cap at reasonable width to prevent extremely wide columns
                            max_len = min(max_len, 50)

                            worksheet.set_column(i, i, max_len)
                        except Exception:
                            # Fallback to default width
                            worksheet.set_column(i, i, 15)
        # Save it to Drive if Colab
        if IS_COLAB:
            print("Saving results to Google Drive...")
            subprocess.run(
                    f"cp {filename} {DRIVE_PATH}/{DRIVE_KEYWORDS_PATH}/.", shell=True
                )
        return f"✅ {config['description']} saved -> {filename}"

    def write_all(self, configs, max_workers=4, auto_width=True, sample_rows=1000):
        """
        Write all workbooks in parallel.

        Args:
            configs: List of workbook configurations
            max_workers: Number of parallel threads
            auto_width: Enable column auto-width (disable for speed)
            sample_rows: Number of rows to sample for width calculation
        """
        print(f"\n🚀 Writing {len(configs)} workbooks with {max_workers} threads...\n")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.write_workbook, cfg, auto_width, sample_rows)
                for cfg in configs
            ]
            for f in as_completed(futures):
                try:
                    print(f.result())
                except Exception as e:
                    print(f"❌ Error writing workbook: {e}")

        print("\n🎉 All Excel workbooks generated successfully!\n")        

# =============================================================================
# USAGE IN YOUR MAIN FUNCTION
# =============================================================================


def write_workbooks_modular(
    keyword_model_comparison,
    sa,
    other_results,
    base_path=KEYWORDS_EXCEL_PATH,
    max_workers=4,
):
    """
    Modular version of write_workbooks using WorkbookManager.
    """
    # Initialize the manager
    manager = WorkbookManager(base_path)

    # Register all data sources
    manager.register_data_source("sa", sa)
    manager.register_data_source("keyword_model", keyword_model_comparison)
    manager.register_data_source(
        "speculative", other_results.get("speculative_analysis", {})
    )
    manager.register_data_source("current", other_results.get("current"))
    manager.register_data_source("historic", other_results.get("historic"))
    manager.register_data_source("speculation", other_results.get("speculation"))
    manager.register_data_source("liabilities", other_results.get("liabilities"))
    manager.register_data_source("embedded", other_results.get("embedded"))
    manager.register_data_source("unique", other_results.get("unique"))
    manager.register_data_source("cooc", other_results.get("cooc"))
    manager.register_data_source("hedge_type", other_results.get("hedge_type"))
    manager.register_data_source("hedge_cross", other_results.get("hedge_cross"))

    # Define all workbook configurations
    configs = [
        # Main server workbook
        manager.create_workbook_config(
            filename=SERVER_EXCEL_PATH,
            description="Server Sentence Analysis",
            sheets={
                "all_reports": ("sa", None, False),
                "Current Hedging": ("current", None, False),
                "Hedging Past Year": ("historic", None, False),
                "Speculation Only": ("speculation", None, False),
                "Derivative Liabilities Warrants": ("liabilities", None, False),
                "Embedded Derivatives": ("embedded", None, False),
                "unique_per_year": ("unique", None, False),
                "label_cooccurrence": ("cooc", None, True),
                "Hedging by Type": ("hedge_type", None, False),
                "Hedge Type Cross": ("hedge_cross", None, True),
            },
        ),
        # Keyword comparison workbooks
        manager.create_workbook_config(
            filename=manager.base_path.with_name(
                manager.base_path.stem + "_HEDGES_CURRENT.xlsx"
            ),
            description="Current Only - Hedges",
            sheets={
                "Summary_Current_Only": ("keyword_model", "summary_current", False),
                "Detailed_Current_Only": ("keyword_model", "detailed_current", False),
                "Basic_Current_Only": ("keyword_model", "comparison_current", False),
                "Confusion_Overall_Curr": (
                    "keyword_model",
                    "confusion_overall_current",
                    True,
                ),
                "Confusion_FX_Curr": ("keyword_model", "confusion_fx_current", True),
                "Confusion_IR_Curr": ("keyword_model", "confusion_ir_current", True),
                "Confusion_CP_Curr": ("keyword_model", "confusion_cp_current", True),
            },
        ),
        manager.create_workbook_config(
            filename=manager.base_path.with_name(
                manager.base_path.stem + "_HEDGES_ALL.xlsx"
            ),
            description="Current+Historic - Hedges",
            sheets={
                "Summary_Curr_Historic": ("keyword_model", "summary_all", False),
                "Detailed_Curr_Historic": ("keyword_model", "detailed_all", False),
                "Basic_Curr_Historic": ("keyword_model", "comparison_all", False),
                "Confusion_Overall_All": (
                    "keyword_model",
                    "confusion_overall_all",
                    True,
                ),
                "Confusion_FX_All": ("keyword_model", "confusion_fx_all", True),
                "Confusion_IR_All": ("keyword_model", "confusion_ir_all", True),
                "Confusion_CP_All": ("keyword_model", "confusion_cp_all", True),
            },
        ),
        manager.create_workbook_config(
            filename=manager.base_path.with_name(
                manager.base_path.stem + "_ALL_DERIVATIVES_CURRENT.xlsx"
            ),
            description="Current Only - All Derivatives",
            sheets={
                "Summary_Current_Only": (
                    "keyword_model",
                    "summary_any_deriv_current",
                    False,
                ),
                "Detailed_Current_Only": (
                    "keyword_model",
                    "detailed_any_deriv_current",
                    False,
                ),
                "Basic_Current_Only": ("keyword_model", "comparison_current", False),
                "Confusion_Overall_Curr": (
                    "keyword_model",
                    "confusion_any_deriv_current",
                    True,
                ),
                "Confusion_FX_Curr": ("keyword_model", "confusion_fx_current", True),
                "Confusion_IR_Curr": ("keyword_model", "confusion_ir_current", True),
                "Confusion_CP_Curr": ("keyword_model", "confusion_cp_current", True),
                "ModelOnly_Liab_Embed": ("keyword_model", "model_only_current", False),
            },
        ),
        manager.create_workbook_config(
            filename=manager.base_path.with_name(
                manager.base_path.stem + "_ALL_DERIVATIVES_FULL.xlsx"
            ),
            description="Current+Historic - All Derivatives",
            sheets={
                "Summary_Curr_Historic": (
                    "keyword_model",
                    "summary_any_deriv_all",
                    False,
                ),
                "Detailed_Curr_Historic": (
                    "keyword_model",
                    "detailed_any_deriv_all",
                    False,
                ),
                "Basic_Curr_Historic": ("keyword_model", "comparison_all", False),
                "Confusion_Overall_All": (
                    "keyword_model",
                    "confusion_any_deriv_all",
                    True,
                ),
                "Confusion_FX_All": ("keyword_model", "confusion_fx_all", True),
                "Confusion_IR_All": ("keyword_model", "confusion_ir_all", True),
                "Confusion_CP_All": ("keyword_model", "confusion_cp_all", True),
                "ModelOnly_Liab_Embed": ("keyword_model", "model_only_all", False),
            },
        ),
        manager.create_workbook_config(
            filename=manager.base_path.with_name(
                manager.base_path.stem + "_KW_MODEL_COMPARISON.xlsx"
            ),
            description="Keyword vs Model Comparison (Standalone)",
            sheets={
                "KW_Model_Comparison": ("keyword_model", "comparison_summary", False),
                "Model_Performance_Summary": (
                    "keyword_model",
                    "model_performance_summary",
                    False,
                ),
            },
        ),
        # Speculative/Policy Analysis
        manager.create_workbook_config(
            filename=manager.base_path.with_name(
                manager.base_path.stem + "_SPECULATIVE_POLICY.xlsx"
            ),
            description="Keyword vs Speculative/Policy Analysis",
            sheets={
                "Translation_Summary": ("speculative", "translation_summary", False),
                "Keyword_vs_Speculative": ("speculative", "keyword_vs_spec", False),
                "ModelOnly_Liab_Embed": ("speculative", "model_only_summary", False),
                "Detailed_Comparison": ("speculative", "comparison", False),
            },
        ),
    ]

    # Write all workbooks
    manager.write_all(configs, max_workers=max_workers)

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

            results.append(
                {
                    "cik": cik,
                    "year": year,
                    "url": url,
                    "sentence": sentence,
                    "label_id": pred,
                    "label": label,
                }
            )

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

    print(f"Processing {len(combined_df):,} reports for sentence-label mapping...")

    # Prepare data for parallel processing
    row_data_list = []
    for _, row in combined_df.iterrows():
        matches = json.loads(row["matches"])
        predictions = json.loads(row["server_response"])
        row_data_list.append(
            (row["cik"], row["year"], row["url"], matches, predictions)
        )

    # Split into chunks for better load balancing
    num_workers = mp.cpu_count()
    chunk_size = max(1, len(row_data_list) // (num_workers * 4))
    chunks = [
        row_data_list[i : i + chunk_size]
        for i in range(0, len(row_data_list), chunk_size)
    ]

    print(f"Using {num_workers} CPU cores, processing {len(chunks)} chunks")

    # Process in parallel
    all_rows = []
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = list(
            tqdm(
                executor.map(process_sentence_chunk, chunks),
                total=len(chunks),
                desc="Building sentence labels",
            )
        )

        # Flatten results
        for chunk_result in results:
            all_rows.extend(chunk_result)

    # Build final DataFrame
    final_df = pd.DataFrame(all_rows)
    print(f"Created DataFrame with {len(final_df):,} sentence-label mappings")

    # Define label groupings (pairs of related labels)
    label_groups = {
        "Gen_Hedge_0-1-2": [0, 1, 2],
        "Speculation_Policy_2_14_15_16": [2, 14, 15, 16],
        "Irrelevant_3": [3],
        "Liabilities_Warrants_4-5": [4, 5],
        "Embedded_Derivatives_6-7": [6, 7],
        "IR_Hedge_8-9-14": [8, 9, 14],
        "FX_Hedge_10-11-15": [10, 11, 15],
        "CP_Hedge_12-13-16": [12, 13, 16],
    }

    # Create a mapping from label_id to group name
    label_id_to_group = {}
    for group_name, label_ids in label_groups.items():
        for label_id in label_ids:
            label_id_to_group[label_id] = group_name

    print(f"\nWriting to separate Excel workbooks by label group...")

    # Group data by label groups
    final_df["group"] = final_df["label_id"].map(label_id_to_group)

    # Handle any unmapped labels (shouldn't happen, but defensive coding)
    unmapped = final_df[final_df["group"].isna()]
    if not unmapped.empty:
        print(
            f"  Warning: Found {len(unmapped)} rows with unmapped label_ids: {unmapped['label_id'].unique()}"
        )
        final_df["group"] = final_df["group"].fillna("Other")

    try:
        # Write each group to a separate workbook
        for group_name, label_ids in label_groups.items():
            group_df = final_df[final_df["label_id"].isin(label_ids)].copy()

            if group_df.empty:
                print(f"  Skipping {group_name} (no data)")
                continue

            # Create filename
            file_path = SENTENCE_PATH.replace(".xlsx", f"_{group_name}.xlsx")

            print(f"\n  Writing {group_name} workbook ({len(group_df):,} rows)...")

            with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
                # Disable automatic URL conversion
                workbook = writer.book
                workbook.strings_to_urls = False
                
                
                group_df_clean = group_df.drop(columns=["group"])
                
                # Write separate sheet for each label in this group
                unique_labels_in_group = sorted(group_df["label"].unique())

                for label in unique_labels_in_group:
                    label_df = group_df_clean[group_df_clean["label"] == label]
                    sheet_name = (
                        str(label)[:31]
                        .replace("/", "-")
                        .replace("\\", "-")
                        .replace(":", "-")
                    )
                    print(f"    - '{sheet_name}' sheet ({len(label_df):,} rows)...")
                    label_df.to_excel(writer, sheet_name=sheet_name, index=False)

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
                        "avg_sentences_per_firm": len(label_data)
                        / label_data["cik"].nunique(),
                        "avg_sentences_per_url": len(label_data)
                        / label_data["url"].nunique(),
                    }
                    summary_stats.append(stats)

                summary = pd.DataFrame(summary_stats)
                summary["pct_of_group"] = (
                    summary["total_sentences"] / len(group_df_clean) * 100
                ).round(2)

                summary = summary[
                    [
                        "label",
                        "label_id",
                        "total_sentences",
                        "pct_of_group",
                        "unique_firms",
                        "unique_urls",
                        "avg_sentences_per_firm",
                        "avg_sentences_per_url",
                        "year_min",
                        "year_max",
                    ]
                ]

                summary = summary.sort_values(
                    "total_sentences", ascending=False
                ).reset_index(drop=True)
                summary.to_excel(writer, sheet_name="Summary", index=False)

                # Format the summary sheet
                worksheet = writer.sheets["Summary"]
                worksheet.set_column("A:A", 30)
                worksheet.set_column("B:B", 10)
                worksheet.set_column("C:D", 18)
                worksheet.set_column("E:F", 15)
                worksheet.set_column("G:H", 22)
                worksheet.set_column("I:J", 12)

                number_format = workbook.add_format({"num_format": "#,##0"})
                percent_format = workbook.add_format({"num_format": '0.00"%"'})
                decimal_format = workbook.add_format({"num_format": "#,##0.00"})

                for row_num in range(1, len(summary) + 1):
                    worksheet.write_number(
                        row_num,
                        2,
                        summary.iloc[row_num - 1]["total_sentences"],
                        number_format,
                    )
                    worksheet.write_number(
                        row_num,
                        3,
                        summary.iloc[row_num - 1]["pct_of_group"],
                        percent_format,
                    )
                    worksheet.write_number(
                        row_num,
                        4,
                        summary.iloc[row_num - 1]["unique_firms"],
                        number_format,
                    )
                    worksheet.write_number(
                        row_num,
                        5,
                        summary.iloc[row_num - 1]["unique_urls"],
                        number_format,
                    )
                    worksheet.write_number(
                        row_num,
                        6,
                        summary.iloc[row_num - 1]["avg_sentences_per_firm"],
                        decimal_format,
                    )
                    worksheet.write_number(
                        row_num,
                        7,
                        summary.iloc[row_num - 1]["avg_sentences_per_url"],
                        decimal_format,
                    )

                total_row = len(summary) + 2
                worksheet.write(
                    total_row, 0, "TOTAL", workbook.add_format({"bold": True})
                )
                worksheet.write_number(total_row, 2, len(group_df_clean), number_format)
                worksheet.write_number(total_row, 3, 100.0, percent_format)
                worksheet.write_number(
                    total_row, 4, group_df_clean["cik"].nunique(), number_format
                )
                worksheet.write_number(
                    total_row, 5, group_df_clean["url"].nunique(), number_format
                )

            print(f"  ✓ Saved {file_path}")

            # Save to Google Drive if in Colab
            if IS_COLAB:
                subprocess.run(
                    f"cp {file_path} {DRIVE_PATH}/{DRIVE_SENTENCE_PATH}/.", shell=True
                )

        # Create overall summary workbook
        print(f"\n  Writing overall summary workbook...")
        summary_file = SENTENCE_PATH.replace(".xlsx", "_Overall_Summary.xlsx")

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
                overall_summary["total_sentences"] / len(final_df) * 100
            ).round(2)

            overall_summary = overall_summary[
                [
                    "group",
                    "label",
                    "label_id",
                    "total_sentences",
                    "pct_of_total",
                    "unique_firms",
                    "unique_urls",
                    "year_min",
                    "year_max",
                ]
            ]

            overall_summary = overall_summary.sort_values(
                "total_sentences", ascending=False
            ).reset_index(drop=True)
            overall_summary.to_excel(writer, sheet_name="Overall_Summary", index=False)

            # Format
            worksheet = writer.sheets["Overall_Summary"]
            worksheet.set_column("A:A", 25)
            worksheet.set_column("B:B", 30)
            worksheet.set_column("C:G", 15)
            worksheet.set_column("H:I", 12)

        print(f"  ✓ Saved {summary_file}")

        if IS_COLAB:
            subprocess.run(
                f"cp {summary_file} {DRIVE_PATH}/{DRIVE_SENTENCE_PATH}/.", shell=True
            )

    except ImportError:
        print(" (pip install xlsxwriter for better performance)")
        return pd.DataFrame()

    print(f"\n{'='*70}")
    print(
        f"Saved {len(final_df):,} sentence-label mappings to {len(label_groups)} workbooks"
    )
    print(f"Each workbook contains:")
    print(f"  - 1 'All_[Group]' sheet with all data for that group")
    print(f"  - Separate sheets for each label in the group")
    print(f"  - 1 'Summary' sheet with statistics")
    print(f"{'='*70}")

    return final_df
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
    print("\n" + "=" * 70)
    print("Generating sentence analysis...")
    print("=" * 70)
    sa = get_sentence_analysis()

    # Build sentence-label mapping
    print("\n" + "=" * 70)
    print("Building sentence-label Excel file...")
    print("=" * 70)
    sentence_label_df = build_sentence_label_excel()

    # Final save to Drive if in Colab
    if IS_COLAB:
        print("\nFinal database sync to Google Drive...")
        subprocess.run(SAVE_SHELL_CMD, shell=True)

    print("\n" + "=" * 70)
    print("All done!")
    print("=" * 70)
