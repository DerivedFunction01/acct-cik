import pandas as pd
from pathlib import Path
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, TYPE_CHECKING

from .analysis import BaseAnalyzer, Config, LabelMapper


# =============================================================================
# WORKBOOK MANAGER
# =============================================================================


class WorkbookManager:
    """Manages writing comparison results to Excel"""

    def __init__(self, config: Config):
        self.config = config

    def _write_sheet(self, writer, sheet_name: str, df: pd.DataFrame, index: bool):
        """Helper to write a single sheet."""
        df.to_excel(writer, sheet_name=sheet_name, index=index)

    def write_comparison_workbook(self, comparison_results: Dict[str, pd.DataFrame]):
        """Write comparison results to Excel workbook"""
        output_path = self.config.output_dir / self.config.comparison_excel
        print(f"\nWriting comparison workbook to {output_path}...")

        # Define sheets to be written
        sheets_to_write = []
        if "summary" in comparison_results:
            sheets_to_write.append(("Summary", comparison_results["summary"], False))
        if "detailed" in comparison_results:
            sheets_to_write.append(("Detailed", comparison_results["detailed"], False))
        if "model_results" in comparison_results:
            sheets_to_write.append(("Model_Results", comparison_results["model_results"], False))
        if "model_only_results" in comparison_results:
            sheets_to_write.append(("Model_Only_Results", comparison_results["model_only_results"], False))

        for key, df in comparison_results.items():
            if key.startswith("confusion_"):
                sheet_name = key.replace("confusion_", "CM_")[:31]
                sheets_to_write.append((sheet_name, df, True))

        # Use ThreadPoolExecutor for I/O-bound task of writing sheets
        # This is faster than ProcessPoolExecutor for this use case.
        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer, ThreadPoolExecutor(max_workers=self.config.num_workers) as executor:
            # Disable automatic URL conversion for performance
            writer.book.strings_to_urls = False

            # Submit all write tasks
            futures = [
                executor.submit(self._write_sheet, writer, name, df, idx)
                for name, df, idx in sheets_to_write
            ]

            # Wait for all tasks to complete
            for future in as_completed(futures):
                try:
                    future.result()  # Raise exceptions if any occurred
                except Exception as e:
                    print(f"Error writing a sheet: {e}")

        print(f"✅ Comparison workbook saved successfully")


# =============================================================================
# COMPARISON ANALYZER
# =============================================================================


class ComparisonAnalyzer(BaseAnalyzer):
    """Analyzes differences between keyword and model predictions"""

    def merge_data(
        self, keyword_df: pd.DataFrame, model_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Merge keyword and model data"""
        # Inner merge to only compare firm-years processed by BOTH the model and keyword search
        merged = pd.merge(model_df, keyword_df, on=["cik", "year"], how="inner")

        # Identify only the numeric flag columns for conversion, excluding 'url' and other text columns.
        flag_cols = [
            col
            for col in merged.columns
            if col not in ["cik", "year", "url"]
            and pd.api.types.is_numeric_dtype(merged[col])
        ]
        # Fill NaN with 0 and convert only the appropriate flag columns to int
        merged[flag_cols] = merged[flag_cols].fillna(0).astype(int)

        return merged

    def calculate_metrics(
        self, keyword_col: str, model_col: str, df: pd.DataFrame
    ) -> Dict:
        """Calculate confusion matrix metrics"""
        # Confusion matrix components
        tp = ((df[keyword_col] == 1) & (df[model_col] == 1)).sum()
        fp = ((df[keyword_col] == 0) & (df[model_col] == 1)).sum()
        tn = ((df[keyword_col] == 0) & (df[model_col] == 0)).sum()
        fn = ((df[keyword_col] == 1) & (df[model_col] == 0)).sum()

        total = len(df)

        # Calculate metrics with zero-division protection
        accuracy = (tp + tn) / total if total > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        return {
            "True_Positives": int(tp),
            "False_Positives": int(fp),
            "True_Negatives": int(tn),
            "False_Negatives": int(fn),
            "Total": int(total),
            "Accuracy": round(accuracy * 100, 2),
            "Precision": round(precision * 100, 2),
            "Recall": round(recall * 100, 2),
            "F1_Score": round(f1 * 100, 2),
        }

    def _classify(self, keyword: int, model: int) -> str:
        """Classify comparison result"""
        if keyword == 1 and model == 1:
            return "True Positive"
        elif keyword == 0 and model == 0:
            return "True Negative"
        elif keyword == 0 and model == 1:
            return "False Positive"
        else:  # keyword == 1 and model == 0
            return "False Negative"

    def _encode_agreement(self, keyword: int, model: int) -> int:
        """Encode agreement: 0 for agree, 1 for FP, -1 for FN."""
        if keyword == model:
            return 0  # Agreement (TP or TN)
        elif keyword == 0 and model == 1:
            return 1  # False Positive (Model found, keyword missed)
        else:  # keyword == 1 and model == 0
            return -1 # False Negative (Keyword found, model missed)

    def create_detailed_view(self, merged_df: pd.DataFrame, comparisons: Dict) -> pd.DataFrame:
        """Create a detailed view with classification for each comparison."""
        detailed_df = merged_df.copy()
        print("Vectorizing detailed comparison view...")

        for name, (kw_col, model_col) in comparisons.items():
            # Vectorized agreement encoding
            agree_conditions = [
                (detailed_df[kw_col] == 0) & (detailed_df[model_col] == 1),  # FP
                (detailed_df[kw_col] == 1) & (detailed_df[model_col] == 0),  # FN
            ]
            agree_choices = [1, -1]
            detailed_df[f"agree_{name.lower().replace(' ', '_')}"] = np.select(agree_conditions, agree_choices, default=0)

            # Vectorized classification
            class_conditions = [
                (detailed_df[kw_col] == 1) & (detailed_df[model_col] == 1),  # TP
                (detailed_df[kw_col] == 0) & (detailed_df[model_col] == 0),  # TN
                (detailed_df[kw_col] == 0) & (detailed_df[model_col] == 1),  # FP
            ]
            class_choices = ["True Positive", "True Negative", "False Positive"]
            detailed_df[f"class_{name.lower().replace(' ', '_')}"] = np.select(class_conditions, class_choices, default="False Negative")

        return detailed_df

    def analyze(
        self,
        data: Optional[pd.DataFrame] = None,
        keyword_df: Optional[pd.DataFrame] = None,
        model_df: Optional[pd.DataFrame] = None,
        **kwargs,
    ) -> Dict[str, pd.DataFrame]:
        """
        Generate comprehensive comparison report.
        """
        if keyword_df is None or model_df is None:
            raise ValueError("'keyword_df' and 'model_df' must be provided")

        merged_df = self.merge_data(keyword_df, model_df)

        print("Generating comparison metrics...")

        comparisons = {
            "IR": ("ir_user", "model_ir_user"),
            "FX": ("fx_user", "model_fx_user"),
            "CP": ("cp_user", "model_cp_user"),
            "Hedges (IR/FX/CP)": ("user", "model_user"),
            "All Derivatives": ("user", "model_user_all"),
        }

        results = {}
        summary_data = []

        for name, (kw_col, model_col) in comparisons.items():
            metrics = self.calculate_metrics(kw_col, model_col, merged_df)
            summary_data.append({"Category": name, **metrics})

            confusion = pd.crosstab(
                merged_df[kw_col].map({0: "Keyword_No", 1: "Keyword_Yes"}),
                merged_df[model_col].map({0: "Model_No", 1: "Model_Yes"}),
                rownames=["Keyword"], colnames=["Model"], margins=True,
            )
            results[f"confusion_{name.lower().replace(' ', '_').replace('/', '_')}"] = confusion

        results["summary"] = pd.DataFrame(summary_data)
        results["merged_df"] = merged_df

        # Add the standalone model results
        results["model_results"] = model_df.copy()

        # Create and add the detailed view
        detailed_view = self.create_detailed_view(merged_df, comparisons)
        results["detailed"] = detailed_view

        # Create and add the model-only results view
        model_only_df = detailed_view[
            (detailed_view["user"] == 0) & (detailed_view["model_user_all"] == 1)
        ].copy()
        if not model_only_df.empty:
            results["model_only_results"] = model_only_df

        print(f"✅ Comparison analysis complete ({len(merged_df):,} firm-years)")
        return results
