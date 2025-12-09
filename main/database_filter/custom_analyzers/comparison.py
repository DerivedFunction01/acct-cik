import pandas as pd
import os
from pathlib import Path
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from .analysis import BaseAnalyzer, Config


class WorkbookManager:
    """Manages writing Pipeline Diff results to Excel."""

    def __init__(self, config: Config):
        self.config = config

    def write_diff_workbook(self, filename: str, sheets: Dict[str, pd.DataFrame]):
        """Writes a multi-tab Excel workbook for pipeline forensics."""
        output_path = self.config.output_dir / filename
        temp_output_path = output_path.with_suffix(".xlsx.tmp")

        print(f"   💾 Saving forensic report to {output_path}...")

        try:
            with pd.ExcelWriter(temp_output_path, engine="xlsxwriter") as writer:
                writer.book.strings_to_urls = False  # type: ignore

                for sheet_name, df in sheets.items():
                    # Truncate sheet name to Excel limit (31 chars)
                    safe_name = sheet_name[:31]
                    if not df.empty:
                        df.to_excel(writer, sheet_name=safe_name, index=False)
                    else:
                        # Create empty sheet with note if DF is empty
                        pd.DataFrame({"Note": ["No data for this category"]}).to_excel(
                            writer, sheet_name=safe_name
                        )

            # Atomic Move
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_output_path, output_path)
            print("   ✅ Excel report saved.")

        except Exception as e:
            print(f"   ❌ Error writing Excel: {e}")


class ComparisonAnalyzer(BaseAnalyzer):
    """
    Compares two pipeline stages and generates a forensic Excel report.
    """

    def __init__(self, config: Config):
        super().__init__(config)
        self.workbook_manager = WorkbookManager(config)

    def compare_checkpoints(self, file_a: str, file_b: str):
        """
        Compares Start (File A) vs End (File B).
        Generates: attrition stats, dropped list, and label shift list.
        """
        path_a = self.config.output_dir / file_a
        path_b = self.config.output_dir / file_b

        if not path_a.exists() or not path_b.exists():
            print(f"❌ Missing files: {path_a} or {path_b}")
            return

        print(f"\n⚔️  COMPARING: {file_a} -> {file_b}")

        # Load Data
        df_a = pd.read_csv(path_a)
        df_b = pd.read_csv(path_b)

        # Create keys for comparison
        df_a["_key"] = df_a["cik"].astype(str) + "_" + df_a["year"].astype(str)
        df_b["_key"] = df_b["cik"].astype(str) + "_" + df_b["year"].astype(str)

        # 1. Calculate Survival
        keys_a = set(df_a["_key"])
        keys_b = set(df_b["_key"])

        survivors = keys_a.intersection(keys_b)
        dropped = keys_a - keys_b
        new_adds = keys_b - keys_a  # Should be zero

        # 2. Prepare "Dropped" Report
        dropped_df = df_a[df_a["_key"].isin(dropped)].copy()

        # 3. Prepare "Label Shifts" Report (Among Survivors)
        shifts = []
        # Align dataframes on index
        df_a_surv = df_a[df_a["_key"].isin(survivors)].set_index("_key").sort_index()
        df_b_surv = df_b[df_b["_key"].isin(survivors)].set_index("_key").sort_index()

        cols_to_check = ["ir_user", "fx_user", "cp_user", "eq_user", "cr_user", "warr_user", "gen_user"]

        for col in cols_to_check:
            if col not in df_a_surv.columns or col not in df_b_surv.columns:
                continue

            # Find mismatched values
            diff_mask = df_a_surv[col] != df_b_surv[col]
            if diff_mask.any():
                diff_rows = df_a_surv[diff_mask].copy()
                diff_rows["Category_Changed"] = col
                diff_rows["Old_Value"] = df_a_surv.loc[diff_mask, col]
                diff_rows["New_Value"] = df_b_surv.loc[diff_mask, col]
                diff_rows["Change_Type"] = diff_rows.apply(
                    lambda x: "LOST TAG" if x["Old_Value"] == 1 else "GAINED TAG",
                    axis=1,
                )
                shifts.append(diff_rows)

        shifts_df = pd.concat(shifts) if shifts else pd.DataFrame()

        # 4. Prepare Summary
        summary_data = {
            "Metric": [
                "Input Rows",
                "Output Rows",
                "Dropped Rows",
                "Attrition Rate",
                "Label Changes",
            ],
            "Value": [
                len(df_a),
                len(df_b),
                len(dropped),
                f"{(len(dropped)/len(df_a)*100):.2f}%" if len(df_a) > 0 else "0%",
                len(shifts_df),
            ],
        }
        summary_df = pd.DataFrame(summary_data)

        # Console Output
        print(
            f"   📉 Attrition: {len(dropped):,} rows dropped ({(len(dropped)/len(df_a)*100):.1f}%)"
        )
        if not shifts_df.empty:
            print(
                f"   ⚠️  Label Shifts: {len(shifts_df):,} survivors changed categories."
            )

        # 5. Write to Excel
        report_name = f"diff_{Path(file_a).stem}_vs_{Path(file_b).stem}.xlsx"

        sheets = {
            "Summary": summary_df,
            "Dropped_Rows": dropped_df,
            "Label_Shifts": shifts_df,
        }

        self.workbook_manager.write_diff_workbook(report_name, sheets)

    def analyze(self, **kwargs):
        file_a = kwargs.get("file_a")
        file_b = kwargs.get("file_b")
        if file_a and file_b:
            self.compare_checkpoints(file_a, file_b)