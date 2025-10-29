import pandas as pd
from typing import Dict, List, Iterator
from tqdm import tqdm
import sqlite3
from contextlib import contextmanager
import json

from .analysis import Config, LabelMapper, DataLoader
from .analysis import BaseAnalyzer

# =============================================================================
# STREAMING DATA LOADER (shared)
# =============================================================================


class StreamingDataLoader:
    """Streams data from database in chunks instead of loading everything into memory"""

    def __init__(self, db_path: str, chunk_size: int = 5000):
        self.db_path = db_path
        self.chunk_size = chunk_size

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _parse_json_safely(self, value):
        """Safely parse JSON column"""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value

    def _flatten_matches(self, matches_dict):
        """Flatten a dictionary of sentence lists into a single list."""
        if not isinstance(matches_dict, dict):
            if isinstance(matches_dict, list):
                return matches_dict
            return []

        flattened = []
        for category_sentences in matches_dict.values():
            if isinstance(category_sentences, list):
                flattened.extend(category_sentences)
        return flattened

    def stream_sentence_data(self, batch_size: int = 5000) -> Iterator[pd.DataFrame]:
        """Stream sentence data in batches from database."""
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
            ORDER BY r.cik, r.year
        """

        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.arraysize = batch_size

            cursor.execute(query)

            batch = []
            for row in cursor:
                batch.append(
                    {
                        "cik": row["cik"],
                        "year": row["year"],
                        "url": row["url"],
                        "matches": self._parse_json_safely(row["matches"]),
                        "server_response": self._parse_json_safely(
                            row["server_response"]
                        ),
                    }
                )

                if len(batch) >= batch_size:
                    df = pd.DataFrame(batch)
                    df["matches"] = df["matches"].apply(self._flatten_matches)
                    df = df[(df["matches"].notna()) & (df["server_response"].notna())]
                    if not df.empty:
                        yield df
                    batch = []

            if batch:
                df = pd.DataFrame(batch)
                df["matches"] = df["matches"].apply(self._flatten_matches)
                df = df[(df["matches"].notna()) & (df["server_response"].notna())]
                if not df.empty:
                    yield df

    def count_total_records(self) -> int:
        """Get total count of records to process"""
        query = """
            SELECT COUNT(*) as count
            FROM webpage_result w
            JOIN report_data r ON w.url = r.url
            JOIN server_result s ON w.url = s.url
        """
        with self._get_connection() as conn:
            result = pd.read_sql(query, conn)
        return result["count"].iloc[0]


# =============================================================================
# DISAGREEMENT SAMPLER (OPTIMIZED - STREAMING)
# =============================================================================


class DisagreementSampler(BaseAnalyzer):
    """
    Samples sentences from firm-year reports based on agreement/disagreement
    between keyword-based and model-based flags using streaming.

    Generates an Excel workbook where each sheet represents a comparison
    category (e.g., 'FP_IR_User', 'FN_FX_User').
    """

    def __init__(
        self,
        config: Config,
        label_mapper: LabelMapper,
        samples_per_category: int = 25,
        random_state: int = 42,
    ):
        super().__init__(config, label_mapper)
        self.data_loader = DataLoader(config)
        self.samples_per_category = samples_per_category
        self.random_state = random_state
        self.output_filename = "disagreement_analysis_sample.xlsx"
        self.streaming_loader = StreamingDataLoader(config.db_path, chunk_size=5000)

    def _get_relevant_sentences(
        self, sentences: List[str], predictions: List[Dict]
    ) -> str:
        """
        Returns all sentences as a single text block for readability.
        """
        sentence_block = "\n\n".join(sentences)
        return sentence_block

    def _process_batch(
        self, batch_df: pd.DataFrame, detailed_comparison_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Process a batch of reports and merge with detailed comparison data.
        """
        # Merge batch with detailed comparison data
        merged = pd.merge(
            detailed_comparison_df,
            batch_df[["cik", "year", "url", "matches", "server_response"]],
            on=["cik", "year", "url"],
            how="inner",
        )

        if merged.empty:
            return pd.DataFrame()

        # Extract sentences for each report
        results = []
        for _, row in merged.iterrows():
            sentences = row.get("matches", [])
            if isinstance(sentences, list) and sentences:
                sentence_block = self._get_relevant_sentences(
                    sentences, row.get("server_response", [])
                )

                record = row.to_dict()
                record["relevant_sentences"] = sentence_block
                results.append(record)

        return pd.DataFrame(results) if results else pd.DataFrame()

    def _analyze_from_comparison(self, detailed_comparison_df: pd.DataFrame):
        """
        Takes the detailed comparison DataFrame and generates sampled Excel files
        for disagreement analysis using streaming.

        Args:
            detailed_comparison_df (pd.DataFrame): The 'detailed' DataFrame from
                                                  ComparisonAnalyzer.
        """
        print("-" * 70)
        print("Running Disagreement Sampler (streaming mode)...")

        if detailed_comparison_df.empty:
            print("❌ No detailed comparison data provided.")
            return

        # Define the user types and classification columns to analyze
        user_types = ["ir_user", "fx_user", "cp_user", "user", "user_all"]
        class_cols = {
            "ir_user": "class_ir",
            "fx_user": "class_fx",
            "cp_user": "class_cp",
            "user": "class_hedges_(ir/fx/cp)",
            "user_all": "class_all_derivatives",
        }

        total_records = self.streaming_loader.count_total_records()
        print(f"📊 Processing {total_records:,} sentences from database")

        # In-memory accumulators for each sheet
        sheet_accumulators = {}
        sampled_sheets_data = {} # New: Store final sampled data for each sheet
        total_processed = 0

        pbar = tqdm(
            self.streaming_loader.stream_sentence_data(batch_size=5000),
            desc="Processing sentence batches",
            unit="batch",
        )

        for batch_df in pbar:
            # Merge batch with detailed comparison
            merged_batch = self._process_batch(batch_df, detailed_comparison_df)
            total_processed += len(batch_df)
            pbar.set_postfix({"extracted": len(merged_batch)})

            if merged_batch.empty:
                continue

            # Group by classification for each user type
            for user_type in user_types:
                keyword_col = (
                    user_type if user_type.startswith(("ir", "fx", "cp")) else "user"
                )
                if not user_type.startswith("model_"):
                    keyword_col = keyword_col.replace("_user", "")
                    if keyword_col not in ["user", "user_all"]:
                        keyword_col = f"{keyword_col}_user"

                model_col = f"model_{user_type}"
                class_col = class_cols.get(user_type)

                if class_col not in merged_batch.columns:
                    continue

                # Group by classification
                for classification, group_df in merged_batch.groupby(class_col):
                    if not isinstance(classification, str):
                        return
                    sheet_name = (
                        f"{classification.replace(' ', '_')}_{user_type}".replace(
                            "/", ""
                        )[:31]
                    )

                    if sheet_name not in sheet_accumulators:
                        sheet_accumulators[sheet_name] = {
                            "data": [],
                            "user_type": user_type,
                            "keyword_col": keyword_col,
                            "model_col": model_col,
                        }

                    sheet_accumulators[sheet_name]["data"].append(group_df)

        # After processing all batches, perform the sampling and prepare for writing
        print("\n🔬 Consolidating and sampling disagreement data...")
        for sheet_name, sheet_info in sheet_accumulators.items():
            combined_df = pd.concat(sheet_info["data"], ignore_index=True)
            if not combined_df.empty:
                sample_df = combined_df.sample(
                    n=min(len(combined_df), self.samples_per_category),
                    random_state=self.random_state,
                )
                sampled_sheets_data[sheet_name] = {
                    "data": sample_df,
                    "info": sheet_info
                }

        # Now, write all sampled sheets to a single Excel file atomically
        print("\n💾 Writing final sampled data to Excel workbook...")
        output_path = self.config.output_dir / self.output_filename
        temp_output_path = output_path.with_suffix('.xlsx.tmp')
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(temp_output_path, engine="openpyxl") as writer:
            for sheet_name, sheet_data in sampled_sheets_data.items():
                sample_df = sheet_data["data"]
                sheet_info = sheet_data["info"]
                keyword_col = sheet_info["keyword_col"]
                model_col = sheet_info["model_col"]
                display_cols = [
                    "cik", "year", "url", keyword_col, model_col, "relevant_sentences"
                ]
                display_cols = [c for c in display_cols if c in sample_df.columns]

                sample_df[display_cols].to_excel(writer, sheet_name=sheet_name, index=False)

                # Format columns
                worksheet = writer.sheets[sheet_name]
                worksheet.column_dimensions["A"].width = 10
                worksheet.column_dimensions["B"].width = 10
                worksheet.column_dimensions["C"].width = 60
                worksheet.column_dimensions["D"].width = 15
                worksheet.column_dimensions["E"].width = 15
                worksheet.column_dimensions["F"].width = 100
                print(f"  ✓ Prepared sheet: {sheet_name} ({len(sample_df)} samples)")
        
        # Atomically rename the temporary file to the final destination
        import os
        try:
            os.rename(temp_output_path, output_path)
        except: # Try replaceing
            os.replace(temp_output_path, output_path)
        print(
            f"✅ Disagreement analysis complete ({total_processed:,} records processed)"
        )
        print("-" * 70)

    def run(self, **kwargs):
        """
        Main execution method. Loads data, runs comparison, and then samples disagreements.
        """
        print("-" * 70)
        print("Running Disagreement Sampler...")

        # This analyzer needs to run a comparison first to find disagreements.
        # It initializes its own components to be self-contained.
        from .analysis import DataLoader, PredictionsProcessor
        from custom_analyzers.comparison import ComparisonAnalyzer

        # 1. Load data
        data_loader = DataLoader(self.config)
        keyword_df = data_loader.load_keyword_data()

        predictions_processor = PredictionsProcessor(self.config, self.label_mapper)
        model_df = data_loader.load_model_predictions()
        model_agg_df = predictions_processor.process_predictions(model_df)

        # 2. Run comparison to get the 'detailed' disagreement dataframe
        print("  -> Running internal comparison to find disagreements...")
        comparison_analyzer = ComparisonAnalyzer(self.config, self.label_mapper)
        comparison_results = comparison_analyzer.analyze(
            keyword_df=keyword_df, model_df=model_agg_df
        )

        # 3. Run the sampler with the disagreement data
        self._analyze_from_comparison(comparison_results["detailed"])
