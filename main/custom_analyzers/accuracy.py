# %%
import pandas as pd
import json
from dataclasses import dataclass
from tqdm import tqdm
from typing import List, Iterator
import sqlite3
from contextlib import contextmanager

# Import existing classes from the analysis module
from .analysis import Config
from .analysis import DataLoader, LabelMapper, BaseAnalyzer

# =============================================================================
# CONFIGURATION
# =============================================================================
PRED_COUNT = 5


@dataclass
class AccuracyConfig(Config):
    """Configuration for the accuracy checking pipeline."""

    output_filename: str = "accuracy_check_sample.xlsx"

    # Sampling parameters
    samples_per_label: int = 50
    random_state: int = 42


# =============================================================================
# STREAMING DATA LOADER (NEW - replaces batch loading)
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
        """
        Stream sentence data in batches from database.
        Yields small DataFrames to keep memory usage low.
        """
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
# ACCURACY SAMPLER (OPTIMIZED)
# =============================================================================


class AccuracySampler(BaseAnalyzer):
    """Handles loading, processing, and sampling data for accuracy checks."""

    def __init__(
        self,
        config: AccuracyConfig,
        label_mapper: LabelMapper,
        samples_per_label: int = 50,
        random_state: int = 42,
    ):
        super().__init__(config, label_mapper)
        self.data_loader = DataLoader(config)
        # Parameters for sampling logic
        self.samples_per_label = samples_per_label
        self.random_state = random_state
        # Streaming loader for memory efficiency
        self.streaming_loader = StreamingDataLoader(config.db_path, chunk_size=5000)

    def get_highest_priority_label(self, prob_dict: dict) -> str:
        """
        Determine the single highest-priority primary label name from a dictionary of
        model probabilities by reusing the LabelMapper logic.
        """
        primary_labels = self.label_mapper.get_primary_labels(prob_dict) or []
        if primary_labels:
            return primary_labels[0]
        return self.label_mapper.primary_id2label.get(24, "Irrelevant")

    def _process_report_row(self, row) -> list:
        """Processes a single report row to extract and label sentences."""
        global PRED_COUNT

        matches = row.get("matches")
        predictions = row.get("server_response")

        if not isinstance(matches, list) or not isinstance(predictions, list):
            return []

        min_len = min(len(matches), len(predictions))
        processed_sentences = []

        for i in range(min_len):
            prob_dict = predictions[i]
            if not isinstance(prob_dict, dict) or "error" in prob_dict:
                continue

            primary_label_name = self.get_highest_priority_label(prob_dict)

            top_preds = sorted(
                prob_dict.items(), key=lambda item: item[1], reverse=True
            )[:PRED_COUNT]
            top_str = ", ".join([f"{label}:{score:.2f}" for label, score in top_preds])

            processed_sentences.append(
                {
                    "cik": row["cik"],
                    "year": row["year"],
                    "url": row["url"],
                    "sentence": matches[i],
                    "predicted_primary_label": primary_label_name,
                    "predicted_multilabels": top_str,
                }
            )

        return processed_sentences

    def _process_batch_for_streaming(self, batch_df: pd.DataFrame) -> pd.DataFrame:
        """Process a batch of reports into individual sentence records"""
        all_sentences = []

        for _, row in batch_df.iterrows():
            sentences = self._process_report_row(row)
            all_sentences.extend(sentences)

        return pd.DataFrame(all_sentences) if all_sentences else pd.DataFrame()

    def _flatten_sentence_data_streaming(self) -> pd.DataFrame:
        """
        Flatten sentence data using streaming to minimize memory usage.
        Accumulates stratified samples across all batches.
        """
        print(f"Flattening sentence data using streaming...")

        total_records = self.streaming_loader.count_total_records()
        print(f"📊 Total records to process: {total_records:,}")

        # Use dictionaries to accumulate samples by label
        label_accumulator = {}
        total_processed = 0

        pbar = tqdm(
            self.streaming_loader.stream_sentence_data(batch_size=5000),
            desc="Processing batches",
            unit="batch",
        )

        for batch_df in pbar:
            # Process this batch
            sentences_batch = self._process_batch_for_streaming(batch_df)
            total_processed += len(batch_df)
            pbar.set_postfix({"sentences": len(sentences_batch)})

            if sentences_batch.empty:
                continue

            # Accumulate samples by label
            for label, group in sentences_batch.groupby("predicted_primary_label"):
                if label not in label_accumulator:
                    label_accumulator[label] = []

                available_slots = max(0, self.samples_per_label - len(label_accumulator[label]))
                if available_slots > 0:
                    sample_size = min(available_slots, len(group))
                    sample = group.sample(n=sample_size, random_state=self.random_state)
                    label_accumulator[label].extend(sample.to_dict("records"))

        # Combine all accumulated samples
        if label_accumulator:
            all_samples = []
            for label, rows in label_accumulator.items():
                all_samples.extend(rows)
            flattened_df = pd.DataFrame(all_samples)
        else:
            flattened_df = pd.DataFrame()

        print(f"✅ Generated {len(flattened_df)} sentence records")
        return flattened_df

    def _create_stratified_sample(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create a stratified sample based on the primary predicted label."""
        if df.empty:
            print("⚠️ No data to sample from.")
            return pd.DataFrame()

        print(
            f"Creating stratified sample with {self.samples_per_label} examples per label..."
        )

        # Already stratified from streaming, but ensure we have exactly samples_per_label per group
        sampled_df = df.groupby("predicted_primary_label", group_keys=False).apply(
            lambda x: x.sample(
                n=min(len(x), self.samples_per_label), random_state=self.random_state
            )
        )

        # Add empty columns for manual review
        sampled_df["reviewer_is_correct"] = ""
        sampled_df["reviewer_correct_primary_label"] = ""
        sampled_df["reviewer_notes"] = ""

        # Define model flag columns to include
        model_flag_cols = [
            col for col in sampled_df.columns if col.startswith("model_")
        ]

        # Reorder columns for better readability
        column_order = [
            "predicted_primary_label",
            "sentence",
            "predicted_multilabels",
            "reviewer_is_correct",
            "reviewer_correct_primary_label",
            "reviewer_notes",
            "cik",
            "year",
            "url",
        ] + sorted(model_flag_cols)

        column_order = [col for col in column_order if col in sampled_df.columns]

        sampled_df = (
            sampled_df[column_order]
            .sort_values("predicted_primary_label")
            .reset_index(drop=True)
        )

        print(f"Generated sample with {len(sampled_df)} sentences.")
        return sampled_df

    def _save_sample_to_excel(self, df: pd.DataFrame):
        """Save the sampled DataFrame to an Excel file."""
        if df.empty:
            print("⚠️ No sample to save.")
            return

        output_path = self.config.output_dir / self.config.output_filename
        print(f"Saving sample to {output_path}...")

        # Write to a temporary file first
        temp_output_path = output_path.with_suffix('.xlsx.tmp')
        df.to_excel(temp_output_path, index=False, engine="xlsxwriter")

        # Atomically rename the temp file to the final path
        import os
        try:
            os.rename(temp_output_path, output_path)
        except: # Try replaceing
            os.replace(temp_output_path, output_path)

        print(f"✅ Sampled data saved successfully.")

    def _chunkify(self, data: list) -> List[list]:
        """Splits a list into smaller chunks for parallel processing."""
        if not data:
            return []
        num_chunks = self.config.num_workers * 4
        chunk_size = (len(data) + num_chunks - 1) // num_chunks
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    def run(self):
        """
        Executes the full accuracy sampling pipeline using streaming.
        """
        print("-" * 70)
        print("Running Accuracy Sampling...")

        # Use streaming to flatten sentence data (no longer loads all into memory)
        flattened_data = self._flatten_sentence_data_streaming()
        # Create a stratified sample
        accuracy_sample_df = self._create_stratified_sample(flattened_data)

        # Save the sample to Excel for review
        self._save_sample_to_excel(accuracy_sample_df)
        print("Accuracy sampling complete.")
        print("-" * 70)


# =============================================================================
# MAIN EXECUTION (identical interface to original)
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Model Accuracy Sampling Pipeline")
    print("=" * 70)

    config = AccuracyConfig()
    sampler = AccuracySampler(
        config=config,
        data_loader=DataLoader(config),
        label_mapper=LabelMapper(config.keywords_json, config.labels),
        model_agg_df=None,
        sentence_df=None,  # Not used with streaming approach
    )
    sampler.run()

    print("\n" + "=" * 70)
    print("Pipeline finished. Please review the generated Excel file.")
    print("=" * 70)

# %%
