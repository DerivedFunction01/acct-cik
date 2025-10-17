import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from .analysis import Config, LabelMapper, DataLoader


class DisagreementSampler:
    """
    Samples sentences from firm-year reports based on the agreement or
    disagreement between keyword-based flags and model-based flags.

    Generates an Excel workbook where each sheet represents a comparison
    category (e.g., 'FP_IR_User', 'FN_FX_User') and contains sample sentences
    from the reports that fall into that category.
    """

    def __init__(
        self,
        config: Config,
        label_mapper: LabelMapper,
        data_loader: DataLoader,
        samples_per_category: int = 25,
        random_state: int = 42,
    ):
        self.config = config
        self.label_mapper = label_mapper
        self.data_loader = data_loader
        self.samples_per_category = samples_per_category
        self.random_state = random_state
        self.output_filename = "disagreement_analysis_sample.xlsx"

    def _get_relevant_sentences(self, sentences: List[str], predictions: List[Dict]) -> List[str]:
        """
        Returns all sentences from the report's 'matches' field.
        This provides the full context for analysis, as requested.
        """
        # Per user request, return all sentences to provide full context,
        # not just the ones the model flagged as relevant.
        return sentences

    def _process_chunk(self, report_chunk: pd.DataFrame) -> List[Dict]:
        """
        Process a chunk of reports to extract relevant sentences.
        Designed for parallel execution.
        """
        results = []
        for _, report_row in report_chunk.iterrows():
            sentences = self._get_relevant_sentences(
                report_row["matches"], report_row["server_response"]
            )
            # Join sentences into a single text block for readability
            sentence_block = "\n\n".join(sentences)

            record = report_row.to_dict()
            record["relevant_sentences"] = sentence_block
            results.append(record)
        return results

    def _get_sentences_for_reports(self, report_ciks: pd.DataFrame) -> pd.DataFrame:
        """
        Fetches and processes sentences for a given DataFrame of reports.
        """
        print(f"Fetching sentences for {len(report_ciks):,} reports...")
        sentence_data = self.data_loader.load_sentence_data()

        # Filter sentence_data to only include the reports we need
        reports_with_sentences = pd.merge(
            report_ciks, sentence_data, on=["cik", "year", "url"], how="inner"
        )

        if reports_with_sentences.empty:
            print("⚠️ No matching reports with sentence data found.")
            return pd.DataFrame()

        # Parallel process sentence extraction
        num_chunks = self.config.num_workers * 4
        chunk_size = (len(reports_with_sentences) + num_chunks - 1) // num_chunks
        chunks = [
            reports_with_sentences.iloc[i : i + chunk_size]
            for i in range(0, len(reports_with_sentences), chunk_size)
        ]

        all_results = []
        with ProcessPoolExecutor(max_workers=self.config.num_workers) as executor:
            futures = [executor.submit(self._process_chunk, chunk) for chunk in chunks]
            for future in tqdm(
                as_completed(futures), total=len(futures), desc="Extracting Sentences"
            ):
                all_results.extend(future.result())

        if not all_results:
            return pd.DataFrame()

        return pd.DataFrame(all_results)

    def analyze(self, detailed_comparison_df: pd.DataFrame):
        """
        Takes the detailed comparison DataFrame and generates a sampled
        Excel file for disagreement analysis.

        Args:
            detailed_comparison_df (pd.DataFrame): The 'detailed' DataFrame from
                                                  ComparisonAnalyzer.
        """
        print("-" * 70)
        print("Running Disagreement Sampler...")

        if "detailed" not in detailed_comparison_df.columns:
             # It's the detailed_df itself
            detailed_df = detailed_comparison_df
        else:
            detailed_df = detailed_comparison_df["detailed"]

        # Define the user types to analyze
        user_types = ["ir_user", "fx_user", "cp_user", "user", "user_all"]
        class_cols = {
            "ir_user": "class_ir",
            "fx_user": "class_fx",
            "cp_user": "class_cp",
            "user": "class_hedges_(ir/fx/cp)",
            "user_all": "class_all_derivatives",
        }

        # Get a list of all unique firm-years to fetch sentences for
        # This avoids fetching data multiple times
        unique_reports = detailed_df[["cik", "year", "url"]].drop_duplicates()
        reports_with_sentences = self._get_sentences_for_reports(unique_reports)

        if reports_with_sentences.empty:
            print("❌ Could not generate disagreement sample as no sentences were found.")
            return

        # Merge sentences back into the detailed comparison dataframe
        # We drop columns that are already in detailed_df to avoid duplication
        cols_to_drop = [c for c in reports_with_sentences.columns if c in detailed_df.columns and c not in ['cik', 'year', 'url']]
        detailed_with_sentences = pd.merge(
            detailed_df,
            reports_with_sentences.drop(columns=cols_to_drop),
            on=["cik", "year", "url"],
            how="left",
        )

        output_path = self.config.output_dir / self.output_filename
        print(f"\nWriting disagreement samples to {output_path}...")

        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
            workbook = writer.book
            workbook.strings_to_urls = False

            for user_type in user_types:
                keyword_col = user_type if user_type.startswith(('ir', 'fx', 'cp')) else 'user'
                if not user_type.startswith('model_'):
                    keyword_col = keyword_col.replace('_user', '')
                    if keyword_col not in ['user', 'user_all']:
                         keyword_col = f"{keyword_col}_user"

                model_col = f"model_{user_type}"
                class_col = class_cols[user_type]

                if class_col not in detailed_with_sentences.columns:
                    print(f"  - Skipping '{user_type}': classification column '{class_col}' not found.")
                    continue

                # Group by the classification (TP, FP, etc.)
                grouped = detailed_with_sentences.groupby(class_col)

                for classification, group_df in grouped:
                    # Take a random sample from each group
                    sample_df = group_df.sample(
                        n=min(len(group_df), self.samples_per_category),
                        random_state=self.random_state,
                    )

                    # Prepare for Excel
                    sheet_name = f"{classification.replace(' ', '_')}_{user_type}".replace('/', '')[:31]
                    display_cols = [
                        "cik", "year", "url",
                        keyword_col, model_col,
                        "relevant_sentences"
                    ]
                    # Ensure columns exist before trying to select them
                    display_cols = [c for c in display_cols if c in sample_df.columns]

                    print(f"  - Writing sheet: {sheet_name} ({len(sample_df)} samples)")
                    sample_df[display_cols].to_excel(writer, sheet_name=sheet_name, index=False)

                    # Auto-adjust column widths for readability
                    worksheet = writer.sheets[sheet_name]
                    worksheet.set_column("A:B", 10)  # cik, year
                    worksheet.set_column("C:C", 60)  # url
                    worksheet.set_column("D:E", 15)  # flags
                    worksheet.set_column("F:F", 100) # sentences

        print(f"✅ Disagreement analysis sample saved to {output_path}")
        print("-" * 70)