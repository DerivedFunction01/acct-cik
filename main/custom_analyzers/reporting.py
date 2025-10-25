# %%
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import sqlite3
from contextlib import contextmanager
import json

# Import from analysis module
from .analysis import Config, LabelMapper, DataLoader, BaseAnalyzer


# =============================================================================
# STREAMING DATA LOADER (shared with accuracy.py)
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
# SENTENCE LABELER (OPTIMIZED - STREAMING)
# =============================================================================


class SentenceLabeler(BaseAnalyzer):
    """Creates sentence-level labeled files with user flags using streaming"""

    def __init__(self, config: Config, label_mapper: LabelMapper):
        super().__init__(config, label_mapper)
        self.streaming_loader = StreamingDataLoader(config.db_path, chunk_size=5000)

    def process_sentence_batch(
        self, batch_df: pd.DataFrame, model_agg_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Process a batch of sentences and merge with user flags"""
        # Merge with user flags
        merged = pd.merge(batch_df, model_agg_df, on=["cik", "year"], how="left")

        # Fill NaN flag columns with 0
        flag_cols = [col for col in model_agg_df.columns if col not in ["cik", "year"]]
        for col in flag_cols:
            if col in merged.columns:
                merged[col] = merged[col].fillna(0).astype(int)

        sentences_data = []
        for _, row in merged.iterrows():
            matches = row.get("matches", [])
            predictions = row.get("server_response", [])

            if not isinstance(matches, list) or not isinstance(predictions, list):
                continue

            min_len = min(len(matches), len(predictions))

            for i in range(min_len):
                prob_dict = predictions[i]
                if not isinstance(prob_dict, dict) or "error" in prob_dict:
                    continue

                primary_labels = self.label_mapper.get_primary_labels(prob_dict)
                probabilities = {
                    f"prob_{label}": prob_dict.get(label, 0.0)
                    for label in self.config.labels
                }

                record = {
                    "cik": row["cik"],
                    "year": row["year"],
                    "url": row["url_x"],  # Use the URL from the sentence data batch
                    "sentence": matches[i],
                    "labels": ", ".join(primary_labels),
                    **{col: row.get(col, 0) for col in flag_cols},
                    **probabilities,
                }
                sentences_data.append(record)

        return pd.DataFrame(sentences_data)

    def _create_labeled_files_from_agg(self, model_agg_df: pd.DataFrame):
        """Create separate Excel files for each label category using streaming"""
        print(f"Creating labeled sentence files using streaming...")
        print(f"Model aggregated data: {len(model_agg_df):,} firm-year records")

        total_records = self.streaming_loader.count_total_records()
        print(f"Processing {total_records:,} total sentences from database")

        # Define label groupings for workbook consolidation
        label_groups = {
            "General_Hedge": ["General_Derivative", "General_Derivative_Context"],
            "IR_Hedge": ["IR_Derivative", "IR_Context"],
            "FX_Hedge": ["FX_Derivative", "FX_Context"],
            "CP_Hedge": ["Commodity_Derivative", "Commodity_Context"],
            "EQ_Hedge": ["Equity_Derivative", "Equity_Context"],
            "Warrant": ["Warrant"],
            "Embedded_Derivative": ["Embedded_Derivative"],
            "Speculation": ["Speculation"],
            "Irrelevant": ["Irrelevant_Non-Hedge", "Irrelevant"],
        }

        # In-memory accumulators for each workbook
        workbook_accumulators = {name: [] for name in label_groups.keys()}
        total_sentences = 0

        pbar = tqdm(
            self.streaming_loader.stream_sentence_data(batch_size=5000),
            desc="Processing sentence batches",
            unit="batch",
        )

        for batch_df in pbar:
            sentences_batch = self.process_sentence_batch(batch_df, model_agg_df)
            total_sentences += len(sentences_batch)
            pbar.set_postfix({"total_sentences": total_sentences})

            if sentences_batch.empty:
                continue

            # Categorize sentences
            sentences_batch["primary_label"] = sentences_batch["labels"].apply(
                lambda x: x.split(", ")[0] if x else "Irrelevant"
            )

            # Map to category
            sentences_batch["category"] = (
                sentences_batch["primary_label"]
                .apply(lambda x: self.label_mapper.primary_label2id.get(x, 24))
                .apply(lambda x: self.label_mapper.get_label_category(x))
            )

            # Accumulate by workbook group
            for workbook_name, categories_in_group in label_groups.items():
                group_df = sentences_batch[
                    sentences_batch["category"].isin(categories_in_group)
                ].copy()

                if not group_df.empty:
                    workbook_accumulators[workbook_name].append(group_df)

                    # Flush if this workbook gets too large
                    total_in_workbook = sum(
                        len(df) for df in workbook_accumulators[workbook_name]
                    )
                    if total_in_workbook > 50000:
                        self._flush_workbook(
                            workbook_name, workbook_accumulators[workbook_name]
                        )
                        workbook_accumulators[workbook_name] = []

        # Flush remaining data
        print("\n💾 Writing final batches to Excel files...")
        for workbook_name, dfs in workbook_accumulators.items():
            if dfs:
                self._flush_workbook(workbook_name, dfs)

        print(f"\n✅ Created labeled sentence files with {total_sentences:,} sentences")

    def _flush_workbook(self, workbook_name: str, dfs: List[pd.DataFrame]):
        """Write a workbook's accumulated data to Excel"""
        if not dfs:
            return

        combined_df = pd.concat(dfs, ignore_index=True)

        if combined_df.empty:
            print(f"  - Skipping {workbook_name} (no data)")
            return

        filename = (
            self.config.output_dir
            / self.config.sentences_dir
            / f"sentences_{workbook_name}.xlsx"
        )
        filename.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(filename, engine="xlsxwriter") as writer:
            writer.book.strings_to_urls = False
            # Drop intermediate 'category' and 'primary_label' columns before writing
            write_df = combined_df.drop(
                columns=["category", "primary_label"], errors="ignore"
            )
            write_df.to_excel(writer, sheet_name=workbook_name[:31], index=False)

        print(f"  ✓ Wrote {workbook_name} workbook ({len(combined_df):,} sentences)")

    def run(self, **kwargs):
        """
        Main execution method. Loads necessary data and runs the labeling process.
        """
        print("-" * 70)
        print("Running Sentence Labeler...")

        # This analyzer needs the aggregated model predictions to join user flags.
        # It initializes its own data loader and processor to be self-contained.
        from .analysis import DataLoader, PredictionsProcessor

        data_loader = DataLoader(self.config)
        predictions_processor = PredictionsProcessor(self.config, self.label_mapper)

        model_df = data_loader.load_model_predictions()
        model_agg_df = predictions_processor.process_predictions(model_df)

        self._create_labeled_files_from_agg(model_agg_df)
        print("-" * 70)

# =============================================================================
# MAIN EXECUTION (identical interface to original)
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Sentence Labeling Pipeline")
    print("=" * 70)

    config = Config()
    label_mapper = LabelMapper(config.keywords_json, config.labels)

    # Load model aggregated results
    from .analysis import PredictionsProcessor

    data_loader = DataLoader(config)
    predictions_processor = PredictionsProcessor(config, label_mapper)

    model_df = data_loader.load_model_predictions()
    model_agg_df = predictions_processor.process_predictions(model_df)

    # Create labeled files
    labeler = SentenceLabeler(config, label_mapper)
    labeler.run()

    print("\n" + "=" * 70)
    print("Pipeline finished successfully!")
    print("=" * 70)

# %%
