import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# Import from analysis module
from .analysis import Config, LabelMapper


# =============================================================================
# SENTENCE LABELER
# =============================================================================


class SentenceLabeler:
    """Creates sentence-level labeled files with user flags"""

    def __init__(self, config: Config, label_mapper: LabelMapper):
        self.config = config
        self.label_mapper = label_mapper

    def process_sentence_chunk(self, chunk_data: List[Tuple]) -> List[Dict]:
        """Process a chunk of sentences - designed for parallel processing"""
        results = []

        for cik, year, url, matches, predictions, user_flags in chunk_data:

            # Flatten the dictionary of categorized sentences into a single list
            flattened_matches = []
            if isinstance(matches, dict):
                for category_sentences in matches.values():
                    if isinstance(category_sentences, list):
                        flattened_matches.extend(category_sentences)
            else:
                # Fallback for old list format
                flattened_matches = matches if isinstance(matches, list) else []

            min_len = min(len(flattened_matches), len(predictions))

            for i in range(min_len):
                sentence = flattened_matches[i]
                prob_dict = predictions[i]
                # Defensive check: Ensure prob_dict is a dictionary
                if not isinstance(prob_dict, dict):
                    print(
                        f"⚠️  Skipping invalid item in predictions. Expected a dict, but got {type(prob_dict)}."
                    )
                    print(f"   - Item: {prob_dict}")
                    print(f"   - URL: {url}")
                    continue

                # Skip items that are error indicators
                if "error" in prob_dict:
                    continue

                # Get primary labels
                primary_labels = self.label_mapper.get_primary_labels(prob_dict)

                # Get raw probabilities for each label
                probabilities = {
                    f"prob_{label}": prob_dict.get(label, 0.0)
                    for label in self.config.labels
                }

                # Create base record
                record = {
                    "cik": cik,
                    "year": year,
                    "url": url,
                    "sentence": sentence,
                    "labels": ", ".join(primary_labels),
                    **user_flags,  # Add all user flags
                    **probabilities,  # Add all probability columns
                }

                results.append(record)

        return results

    def create_labeled_files(
        self, sentence_df: pd.DataFrame, user_flags_df: pd.DataFrame
    ):
        """Create separate Excel files for each label category with user flags"""
        print(f"Processing {len(sentence_df):,} sentences for labeled files...")

        # Merge sentence data with user flags
        merged_sentences = pd.merge(
            sentence_df, user_flags_df, on=["cik", "year"], how="left"
        )

        # Fill NaN for any sentences whose firm-year didn't have flags
        flag_cols = [col for col in user_flags_df.columns if col not in ["cik", "year"]]
        merged_sentences[flag_cols] = merged_sentences[flag_cols].fillna(0).astype(int)

        # Prepare data for parallel processing
        chunk_data = []
        for _, row in merged_sentences.iterrows():
            user_flags = {col: row[col] for col in flag_cols}
            chunk_data.append(
                (
                    row["cik"],
                    row["year"],
                    row["url"],
                    row["matches"],
                    row["server_response"],
                    user_flags,
                )
            )

        # Process chunks in parallel
        all_sentences = []
        with ProcessPoolExecutor(max_workers=self.config.num_workers) as executor:
            futures = [
                executor.submit(self.process_sentence_chunk, chunk)
                for chunk in self._chunkify(chunk_data)
            ]
            for future in tqdm(
                as_completed(futures), total=len(futures), desc="Processing sentences"
            ):
                all_sentences.extend(future.result())

        sentences_df = pd.DataFrame(all_sentences)
        print(f"Created {len(sentences_df):,} sentence records")

        # The 'labels' column contains a comma-separated string of prioritized labels.
        # The first label is the one with the highest priority.
        sentences_df["primary_label"] = sentences_df["labels"].apply(
            lambda x: x.split(", ")[0] if x else "Irrelevant"
        )

        # Group by label category
        sentences_df["category"] = (
            sentences_df["primary_label"]
            .apply(
                lambda x: self.label_mapper.primary_label2id.get(x, 24)
            )  # Default to irrelevant ID 24
            .apply(lambda x: self.label_mapper.get_label_category(x))
        )

        # Define label groupings for workbook consolidation
        label_groups = {
            "General_Hedge": ["General_Derivative", "General_Derivative_Context"],
            "IR_Hedge": ["IR_Derivative", "IR_Context"],
            "FX_Hedge": ["FX_Derivative", "FX_Context"],
            "CP_Hedge": ["Commodity_Derivative", "Commodity_Context"],
            "EQ_Hedge": ["Equity_Derivative", "Equity_Context"],
            "Warrant": ["Warrant"],
            "Embedded_Derivative": ["Embedded_Derivative"],
            "Speculation": [
                "Speculation"
            ],  # Assuming 'Speculation' is a direct category
            "Irrelevant": ["Irrelevant_Non-Hedge", "Irrelevant"],
        }

        print("\nWriting labeled sentence files concurrently...")
        # Using ProcessPoolExecutor here is acceptable as pandas operations inside the writer can be CPU-intensive.
        with ProcessPoolExecutor(max_workers=self.config.num_workers) as executor:
            futures = []
            for workbook_name, categories_in_group in label_groups.items():
                # Filter using the list of categories for this group
                group_df = sentences_df[
                    sentences_df["category"].isin(categories_in_group)
                ].copy()

                if group_df.empty:
                    print(
                        f"  - Skipping workbook for '{workbook_name}' (no sentences found in this group)."
                    )
                    continue

                # The group_name is now the same for the file, sheet, and category filter.
                future = executor.submit(
                    self._write_group_workbook, workbook_name, group_df
                )
                futures.append(future)

            for future in tqdm(
                as_completed(futures), total=len(futures), desc="Writing workbooks"
            ):
                try:
                    result = future.result()
                    if result:
                        print(result)
                except Exception as e:
                    print(f"An error occurred while writing a workbook: {e}")

    def _write_group_workbook(
        self, workbook_name: str, group_df: pd.DataFrame
    ) -> Optional[str]:
        """Writes a single Excel workbook for a given group of sentences."""
        if group_df.empty:
            return f"  Skipping {workbook_name} (no data)"

        filename = (
            self.config.output_dir
            / self.config.sentences_dir
            / f"sentences_{workbook_name}.xlsx"
        )

        with pd.ExcelWriter(filename, engine="xlsxwriter") as writer:
            workbook = writer.book
            workbook.strings_to_urls = False
            # Since the group is now one definitive category, we can write it directly.
            sheet_name = workbook_name[:31]
            # Drop the intermediate 'category' column before writing
            group_df.drop(columns=["category"]).to_excel(
                writer, sheet_name=sheet_name, index=False
            )
        return f"  ✓ Wrote {workbook_name} workbook ({len(group_df):,} sentences) to {filename}"

    def _chunkify(self, data: list) -> List[list]:
        """Splits a list into smaller chunks for parallel processing."""
        if not data:
            return []
        # Create a reasonable number of chunks for good load balancing
        num_chunks = self.config.num_workers * 4
        chunk_size = (len(data) + num_chunks - 1) // num_chunks  # Ceiling division
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
