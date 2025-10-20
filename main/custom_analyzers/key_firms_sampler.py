import pandas as pd
from pathlib import Path
from typing import Dict, Optional

from .analysis import BaseAnalyzer, Config, DataLoader


class KeyFirmsSampler(BaseAnalyzer):
    """
    A custom analyzer to sample specific firm-year keys based on model results.

    This analyzer creates an Excel workbook with sheets for:
    - Firms flagged for IR, FX, or CP derivative usage by the model.
    - Firms for which no text was extracted during the initial processing.
    """

    def __init__(self, config: Config):
        super().__init__(config)
        self.data_loader = DataLoader(config)
        self.output_filename = self.config.output_dir / "key_firms_sample.xlsx"

    def _get_reports_with_no_text(self) -> pd.DataFrame:
        """
        Identifies reports where the 'matches' field in the database is empty,
        indicating no text was extracted.

        Returns:
            pd.DataFrame: A DataFrame with 'cik' and 'year' for reports with no text.
        """
        print("   -> Identifying reports with no extracted text...")
        # This query joins report_data with webpage_result to find reports
        # that have an entry but where the 'matches' field is empty JSON ('[]').
        query = """
            SELECT r.cik, r.year
            FROM report_data r
            LEFT JOIN webpage_result w ON r.url = w.url
            WHERE w.url IS NULL OR w.matches = '[]' OR w.matches = '{}' OR w.matches IS NULL
        """
        with self.data_loader._get_connection() as conn:
            no_text_df = pd.read_sql(query, conn)

        # Drop duplicates to ensure unique firm-year pairs
        no_text_df = no_text_df.drop_duplicates(subset=['cik', 'year']).reset_index(drop=True)
        print(f"   -> Found {len(no_text_df)} reports with no text.")
        return no_text_df

    def analyze(self, data: pd.DataFrame, **kwargs) -> Dict[str, pd.DataFrame]:
        """
        Analyzes the aggregated model data to extract key firm-year samples.

        Args:
            data (pd.DataFrame): The aggregated model results DataFrame (model_agg_df).

        Returns:
            A dictionary of DataFrames, where each key is a sheet name.
        """
        if data.empty:
            print("   ❌ Model aggregated data is empty. Skipping KeyFirmsSampler.")
            return {}

        results = {}

        # 1. Get firms flagged for specific derivative usage
        print("   -> Sampling firms with IR, FX, and CP model flags...")
        for user_type in ["ir", "fx", "cp"]:
            col_name = f"model_{user_type}_user"
            if col_name in data.columns:
                df = data[data[col_name] == 1][["cik", "year"]].copy()
                sheet_name = f"model_{user_type}_users"
                results[sheet_name] = df
                print(f"   -> Found {len(df)} firms for {sheet_name}")

        # 2. Get firms with no extracted text
        results["no_extracted_text"] = self._get_reports_with_no_text()

        return results

    def run(self, model_agg_df: pd.DataFrame):
        """
        Main execution method for the analyzer.

        Args:
            model_agg_df (pd.DataFrame): The aggregated model results.
        """
        print("\n[Extra] Running Key Firms Sampler...")
        analysis_results = self.analyze(data=model_agg_df)

        if not analysis_results:
            return

        print(f"   -> Writing results to {self.output_filename}...")
        with pd.ExcelWriter(self.output_filename, engine="xlsxwriter") as writer:
            for sheet_name, df in analysis_results.items():
                if not df.empty:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

        print("   ✅ Key Firms Sampler finished successfully.")