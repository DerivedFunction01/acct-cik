# %%
import pandas as pd
import json
from dataclasses import dataclass
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List

# Import existing classes from the analysis module
from .analysis import Config
from .analysis import DataLoader, LabelMapper

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
# ACCURACY SAMPLER
# =============================================================================


class AccuracySampler:
    """Handles loading, processing, and sampling data for accuracy checks."""

    def __init__(
        self,
        config: Config,
        data_loader: DataLoader,
        label_mapper: LabelMapper,
        model_agg_df: pd.DataFrame = None,
    ):
        self.config = config
        self.data_loader = data_loader
        self.label_mapper = label_mapper
        self.model_agg_df = model_agg_df

    def get_highest_priority_label(self, prob_dict: dict) -> str:
        """
        Determine the single highest-priority primary label name from a dictionary of
        model probabilities by reusing the LabelMapper logic.
        """
        # Use the central LabelMapper to get a prioritized list of primary labels
        primary_labels = self.label_mapper.get_primary_labels(prob_dict) or []

        # The first label in the list is the one with the highest priority.
        if primary_labels:
            return primary_labels[0]

        # Fallback to "Irrelevant" if no other labels are produced.
        return self.label_mapper.primary_id2label.get(24, "Irrelevant")

    def _process_report_row(self, row) -> list:
        """Processes a single report row to extract and label sentences."""
        global PRED_COUNT
        try:
            matches = row["matches"]
            predictions = row["server_response"]
        except (json.JSONDecodeError, TypeError):
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
            top_str = ", ".join(
                [f"{label}:{score:.2f}" for label, score in top_preds]
            )

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

    def _load_and_flatten_data(self) -> pd.DataFrame:
        """Load sentence data from DB and flatten into one-row-per-sentence."""
        print("Loading data from database...")
        df = self.data_loader.load_sentence_data()

        print(f"Flattening {len(df)} reports into individual sentences...")

        # Convert DataFrame rows to a list of dictionaries for easier processing
        report_rows = df.to_dict("records")

        all_sentences = []

        # Use ProcessPoolExecutor for CPU-bound task of processing rows
        with ProcessPoolExecutor(max_workers=self.config.num_workers) as executor:
            # Create chunks for better load balancing
            chunks = self._chunkify(report_rows)

            # Process chunks in parallel
            future_to_chunk = {
                executor.submit(self._process_chunk, chunk): chunk for chunk in chunks
            }

            for future in tqdm(
                as_completed(future_to_chunk),
                total=len(chunks),
                desc="Processing reports",
            ):
                all_sentences.extend(future.result())

        flattened_df = pd.DataFrame(all_sentences)

        # Merge with firm-year model flags if available
        if self.model_agg_df is not None and not self.model_agg_df.empty and "cik" in self.model_agg_df.columns:
            print("Merging firm-year user flags into sentence data...")
            # Select only the flag columns to merge
            flag_cols = ["cik", "year"] + [
                col for col in self.model_agg_df.columns if col.startswith("model_")
            ]
            # Ensure we don't have duplicate cik-year entries in the flags df
            agg_flags = self.model_agg_df[flag_cols].drop_duplicates(
                subset=["cik", "year"]
            )

            flattened_df = pd.merge(
                flattened_df, agg_flags, on=["cik", "year"], how="left"
            )
            flattened_df.fillna(
                {col: 0 for col in flag_cols if col not in ["cik", "year"]},
                inplace=True,
            )

        return flattened_df

    def _process_chunk(self, chunk: List[dict]) -> List[dict]:
        """Helper function to process a chunk of report rows."""
        chunk_results = []
        for row in chunk:
            chunk_results.extend(self._process_report_row(row))
        return chunk_results

    def _create_stratified_sample(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create a stratified sample based on the primary predicted label."""
        if df.empty:
            print("⚠️ No data to sample from.")
            return pd.DataFrame()

        print(
            f"Creating stratified sample with {self.config.samples_per_label} examples per label..."
        )

        # Group by the primary label and take a random sample from each group
        sampled_df = df.groupby("predicted_primary_label", group_keys=False).apply(
            lambda x: x.sample(
                n=min(len(x), self.config.samples_per_label),
                random_state=self.config.random_state,
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
        ] + sorted(
            model_flag_cols
        )  # Add the model flags at the end

        # Ensure all columns in the order exist in the dataframe before reordering
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
        df.to_excel(output_path, index=False, engine="xlsxwriter")
        print(f"✅ Sampled data saved successfully.")

    def _chunkify(self, data: list) -> List[list]:
        """Splits a list into smaller chunks for parallel processing."""
        if not data:
            return []
        # Create a reasonable number of chunks for good load balancing
        num_chunks = self.config.num_workers * 4
        chunk_size = (len(data) + num_chunks - 1) // num_chunks  # Ceiling division
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    def run(self):
        """
        Executes the full accuracy sampling pipeline.
        """
        print("-" * 70)
        print("Running Accuracy Sampling...")
        # 1. Load and process all sentence data
        flattened_data = self._load_and_flatten_data()

        # 2. Create a stratified sample
        accuracy_sample_df = self._create_stratified_sample(flattened_data)

        # 3. Save the sample to Excel for review
        self._save_sample_to_excel(accuracy_sample_df)
        print("Accuracy sampling complete.")
        print("-" * 70)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Model Accuracy Sampling Pipeline")
    print("=" * 70)

    config = AccuracyConfig()
    # In a standalone run, model_agg_df would be None.
    # For integrated runs, it's passed by AnalysisPipeline.
    sampler = AccuracySampler(
        config=config,
        data_loader=DataLoader(config),
        label_mapper=LabelMapper(config.keywords_json, config.labels),
        model_agg_df=None,
    )
    sampler.run()

    print("\n" + "=" * 70)
    print("Pipeline finished. Please review the generated Excel file.")
    print("=" * 70)

# %%
