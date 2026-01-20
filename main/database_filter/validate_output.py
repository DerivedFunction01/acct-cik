"""
Validation Script: Compare classified_data_active_users.csv against data_check_cleaned.csv
Validates ir_user, fx_user, and cp_user columns using cik,year as key.
Includes strict Type Handling to prevent false mismatches (1 vs 1.0).
"""

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)
import sys
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# Now pointing to the CLEANED ground truth file
GROUND_TRUTH_FILE = "data_check.csv"
PREDICTED_FILE = "analysis_output/classified_data.csv"
COLUMNS_TO_VALIDATE = ["cp_user", "ir_user", "fx_user"]

# =============================================================================
# VALIDATION LOGIC
# =============================================================================


def load_data(file_path):
    """Load CSV file and return as dataframe."""
    return pd.read_csv(file_path)


def merge_datasets(ground_truth, predicted):
    """Merge datasets on cik,year pairs."""

    # Filter only necessary columns (plus keys)
    # We use a set intersection to avoid errors if a column is missing in one file
    available_gt_cols = [c for c in COLUMNS_TO_VALIDATE if c in ground_truth.columns]
    available_pred_cols = [c for c in COLUMNS_TO_VALIDATE if c in predicted.columns]

    gt = ground_truth[["cik", "year"] + available_gt_cols].copy()
    pred = predicted[["cik", "year"] + available_pred_cols].copy()

    # Rename predicted columns to avoid collision during merge
    pred = pred.rename(columns={col: f"{col}_pred" for col in available_pred_cols})

    # Merge on cik and year (inner join = only compare records present in BOTH)
    merged = gt.merge(pred, on=["cik", "year"], how="inner")

    return merged


def calculate_metrics(y_true, y_pred, column_name):
    """Calculate metrics for a single column."""
    metrics = {
        "column": column_name,
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
    }

    # Confusion Matrix
    # Labels parameter ensures we get a 2x2 matrix even if data lacks 0s or 1s
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    metrics["tn"] = int(tn)
    metrics["fp"] = int(fp)
    metrics["fn"] = int(fn)
    metrics["tp"] = int(tp)

    return metrics


def print_metrics_table(all_metrics):
    """Pretty print metrics table."""
    print("\n" + "=" * 100)
    print("VALIDATION RESULTS")
    print("=" * 100)
    print(
        f"\n{'Column':<15} {'Accuracy':<12} {'Precision':<12} {'Recall':<12} {'F1 Score':<12}"
    )
    print("-" * 100)

    for metrics in all_metrics:
        print(
            f"{metrics['column']:<15} "
            f"{metrics['accuracy']:.4f}         "
            f"{metrics['precision']:.4f}         "
            f"{metrics['recall']:.4f}         "
            f"{metrics['f1']:.4f}"
        )


def print_confusion_matrices(all_metrics):
    """Print confusion matrices for each column."""
    print("\n" + "=" * 100)
    print("CONFUSION MATRICES")
    print("=" * 100)

    for metrics in all_metrics:
        print(f"\n{metrics['column'].upper()}:")
        print(f"  True Negatives (TN):  {metrics['tn']:>10}")
        print(f"  False Positives (FP): {metrics['fp']:>10}")
        print(f"  False Negatives (FN): {metrics['fn']:>10}")
        print(f"  True Positives (TP):  {metrics['tp']:>10}")


def print_summary(ground_truth, predicted, merged, all_metrics):
    """Print summary statistics."""
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"\nGround Truth Records:  {len(ground_truth):,}")
    print(f"Predicted Records:     {len(predicted):,}")
    print(f"Matched Records:       {len(merged):,}")

    unmatched_gt = len(ground_truth) - len(merged)
    unmatched_pred = len(predicted) - len(merged)

    if unmatched_gt > 0:
        print(f"Unmatched (GT only):   {unmatched_gt:,}")
    if unmatched_pred > 0:
        print(f"Unmatched (Pred only): {unmatched_pred:,}")


def validate(ground_truth_path=None, predicted_path=None):
    """Main validation function."""

    if ground_truth_path is None:
        ground_truth_path = GROUND_TRUTH_FILE
    if predicted_path is None:
        predicted_path = PREDICTED_FILE

    gt_file = Path(ground_truth_path)
    pred_file = Path(predicted_path)

    if not gt_file.exists():
        print(f"❌ Ground truth file not found: {gt_file}")
        print(f"   (Run 'create_clean_ground_truth.py' first if this is missing)")
        return
    if not pred_file.exists():
        print(f"❌ Predicted file not found: {pred_file}")
        return

    print(f"📂 Loading files...")
    print(f"   Ground Truth: {gt_file}")
    print(f"   Predicted:    {pred_file}\n")

    ground_truth = load_data(ground_truth_path)
    predicted = load_data(predicted_path)

    merged = merge_datasets(ground_truth, predicted)

    all_metrics = []

    # Calculate metrics for each column
    for col in COLUMNS_TO_VALIDATE:
        pred_col = f"{col}_pred"

        # Skip if column not found in merged data
        if col not in merged.columns or pred_col not in merged.columns:
            print(f"⚠️  Skipping {col}: Not found in both datasets.")
            continue

        # --- TYPE SAFETY BLOCK ---
        # Coerce to numeric, fill NaNs with -1 (or 0), then cast to int
        # This ensures 1.0 (float) == 1 (int)
        y_true = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)
        y_pred = pd.to_numeric(merged[pred_col], errors="coerce").fillna(0).astype(int)

        metrics = calculate_metrics(y_true, y_pred, col)
        all_metrics.append(metrics)

    if not all_metrics:
        print("❌ No overlapping columns found to validate.")
        return

    # Print results
    print_summary(ground_truth, predicted, merged, all_metrics)
    print_metrics_table(all_metrics)
    print_confusion_matrices(all_metrics)

    # Overall accuracy
    # We recalculate strictly on the validated columns
    total_comparisons = 0
    total_correct = 0

    for m in all_metrics:
        col = m["column"]
        tn = m["tn"]
        tp = m["tp"]
        fn = m["fn"]
        fp = m["fp"]

        total_correct += tn + tp
        total_comparisons += tn + tp + fn + fp

    if total_comparisons > 0:
        overall_accuracy = total_correct / total_comparisons
        print("\n" + "=" * 100)
        print(f"OVERALL ACCURACY (weighted average): {overall_accuracy:.4f}")
        print("=" * 100 + "\n")


if __name__ == "__main__":
    validate()
