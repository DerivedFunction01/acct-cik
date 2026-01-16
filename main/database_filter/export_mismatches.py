"""
Export script to create Excel file with only MISMATCHED records for manual review.
Identifies mismatches between data_check.csv and classified_data_active_users.csv,
then exports the relevant URLs and categories from the database.
"""

import sqlite3
import json
import pandas as pd
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from tqdm import tqdm
from typing import Optional, Set, Tuple

# =============================================================================
# CONFIGURATION
# =============================================================================

GROUND_TRUTH_FILE = "data_check.csv"
PREDICTED_FILE = "analysis_output/classified_data_active_users.csv"
# You can add "ir_user", "fx_user" here if you want to validate them as well
COLUMNS_TO_VALIDATE = ["ir_user"]

# Map validation columns to their corresponding check columns
CHECK_COLUMN_MAPPING = {
    "ir_user": "check_ir",
    "fx_user": "check_fx",
    "cp_user": "check_cp",
}

# =============================================================================
# DATA PREPROCESSING
# =============================================================================


def preprocess_ground_truth(df):
    """
    Invert ground truth values based on check columns.
    Logic: If check_* is 0, the labeled value is incorrect, so we invert it.
    """
    df_processed = df.copy()

    print("  ...Preprocessing Ground Truth (applying check_* logic)...")

    for val_col, check_col in CHECK_COLUMN_MAPPING.items():
        # Only process if both columns exist in the dataframe
        if val_col in df_processed.columns and check_col in df_processed.columns:
            # Find rows where check is 0 (meaning the label needs inversion)
            mask_invert = df_processed[check_col] == 0
            count_inverted = mask_invert.sum()

            if count_inverted > 0:
                # Invert 0 to 1 and 1 to 0
                df_processed.loc[mask_invert, val_col] = (
                    1 - df_processed.loc[mask_invert, val_col]
                )
                print(
                    f"    - {val_col}: Inverted {count_inverted} records where {check_col} == 0"
                )

    return df_processed


# =============================================================================
# FIND MISMATCHES
# =============================================================================


def find_mismatches(
    ground_truth_path: str, predicted_path: str
) -> Set[Tuple[int, int]]:
    """
    Find all cik,year pairs from ground_truth that have at least one mismatch
    in validated columns when compared to predictions.
    Returns a set of (cik, year) tuples.
    """
    # Load data
    gt = pd.read_csv(ground_truth_path)
    pred = pd.read_csv(predicted_path)

    # --- NEW: Apply Logic to Ground Truth ---
    gt = preprocess_ground_truth(gt)

    # Keep only validated columns (Now that values are corrected)
    gt_cols = ["cik", "year"] + COLUMNS_TO_VALIDATE
    pred_cols = ["cik", "year"] + COLUMNS_TO_VALIDATE

    # Ensure columns exist before selecting
    missing_cols = [c for c in gt_cols if c not in gt.columns]
    if missing_cols:
        raise ValueError(f"Missing columns in ground truth: {missing_cols}")

    gt = gt[gt_cols].copy()
    pred = pred[pred_cols].copy()

    # Merge on cik and year with inner join (only records in both files)
    merged = gt.merge(pred, on=["cik", "year"], suffixes=("", "_pred"))

    mismatches = set()

    # Find mismatches for each column
    for col in COLUMNS_TO_VALIDATE:
        pred_col = f"{col}_pred"

        # Rows where values don't match
        mismatched_mask = merged[col] != merged[pred_col]
        mismatched = merged[mismatched_mask][["cik", "year"]]

        for _, row in mismatched.iterrows():
            mismatches.add((int(row["cik"]), int(row["year"])))

    return mismatches


# =============================================================================
# DATABASE FETCH
# =============================================================================


def fetch_mismatched_data(db_path: str, mismatches: Set[Tuple[int, int]]):
    """Fetch all data from database for mismatched cik,year pairs."""
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA query_only=1")

    cur = conn.cursor()

    query = """
        SELECT rd.url, rd.cik, rd.year, cat.categories
        FROM category cat
        JOIN report_data rd ON cat.url = rd.url
    """

    cur.execute(query)

    results = []
    for url, cik, year, categories_json in cur.fetchall():
        if (cik, year) in mismatches:
            results.append((url, cik, year, categories_json))

    conn.close()
    return results


# =============================================================================
# EXCEL CREATION
# =============================================================================


def format_excel(ws, total_rows):
    """Apply formatting to worksheet."""
    # Header styling
    header_fill = PatternFill(
        start_color="C00000", end_color="C00000", fill_type="solid"
    )
    header_font = Font(bold=True, color="FFFFFF", size=12)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )

    # Set column widths
    ws.column_dimensions["A"].width = 60  # URL
    ws.column_dimensions["B"].width = 12  # CIK
    ws.column_dimensions["C"].width = 8  # Year
    ws.column_dimensions["D"].width = 50  # Categories

    # Alternating row colors
    light_fill = PatternFill(
        start_color="FCE4D6", end_color="FCE4D6", fill_type="solid"
    )
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    for row_idx in range(2, total_rows + 2):
        for col_idx in range(1, 5):
            cell = ws.cell(row=row_idx, column=col_idx)
            if row_idx % 2 == 0:
                cell.fill = light_fill
            cell.border = border
            if col_idx == 2 or col_idx == 3:  # CIK and Year
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 4:  # Categories
                cell.alignment = Alignment(
                    horizontal="left", vertical="top", wrap_text=True
                )

    # Freeze header row
    ws.freeze_panes = "A2"


def export_mismatches_to_excel(db_path: str, excel_path: Optional[str] = None):
    """Export mismatched records from database to Excel file."""

    db = Path(db_path)
    if not db.exists():
        print(f"❌ Database not found: {db}")
        return

    gt_file = Path(GROUND_TRUTH_FILE)
    pred_file = Path(PREDICTED_FILE)

    if not gt_file.exists():
        print(f"❌ Ground truth file not found: {gt_file}")
        return
    if not pred_file.exists():
        print(f"❌ Predicted file not found: {pred_file}")
        return

    if excel_path is None:
        excel_path = "mismatches_review.xlsx"

    print(f"{'=' * 70}")
    print(f"EXPORTING MISMATCHES TO EXCEL FOR REVIEW")
    print(f"Source DB: {db.name}")
    print(f"Ground Truth: {gt_file.name}")
    print(f"Predictions: {pred_file.name}")
    print(f"Target: {excel_path}")
    print(f"{'=' * 70}\n")

    # Find mismatches
    print("🔍 Finding mismatches...")
    mismatches = find_mismatches(str(gt_file), str(pred_file))
    print(f"   Found {len(mismatches):,} mismatched cik,year pairs\n")

    if len(mismatches) == 0:
        print("✅ No mismatches found!")
        return

    # Fetch mismatched data
    print("🔄 Fetching data from database...")
    data = fetch_mismatched_data(str(db), mismatches)
    print(f"   Retrieved {len(data):,} URLs for mismatched records\n")

    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mismatches"

    # Write header
    ws.append(["URL", "CIK", "Year", "Categories"])

    # Write data
    print("📝 Writing to Excel...")
    for url, cik, year, categories_json in tqdm(data, desc="Writing rows", unit="row"):
        # Parse categories
        try:
            if categories_json:
                categories_array = json.loads(categories_json)
                categories_str = ", ".join(categories_array)
            else:
                categories_str = ""
        except json.JSONDecodeError:
            categories_str = "ERROR: Invalid JSON"

        ws.append([url, cik, year, categories_str])

    # Format
    print("✨ Formatting Excel...")
    format_excel(ws, len(data))

    # Save workbook
    wb.save(excel_path)

    print(f"\n{'=' * 70}")
    print(f"✅ Export Complete: {excel_path}")
    print(f"   Total Records: {len(data):,}")
    print(f"   Mismatched cik,year pairs: {len(mismatches):,}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        db_name = sys.argv[1]
        excel_name = sys.argv[2] if len(sys.argv) > 2 else None
        export_mismatches_to_excel(db_name, excel_name)
    else:
        default_db = "classified_data.db"
        db_input = input(f"Enter database (default: {default_db}): ").strip()
        db_name = db_input or default_db

        if not db_name.endswith(".db"):
            db_name += ".db"

        export_mismatches_to_excel(db_name)
