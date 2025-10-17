# %%
import pandas as pd
import json
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional
from tqdm import tqdm

# Import from existing modules
from custom_analyzers.analysis import Config, LabelMapper

# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class URLAnalysisConfig(Config):
    """Configuration for URL-specific analysis pipeline"""

    input_csv: str = "firm_urls.csv"
    output_excel: str = "url_sentence_analysis.xlsx"

    # Override parent defaults if needed
    def __post_init__(self):
        super().__post_init__()
        # Don't need multi-processing for small datasets
        self.num_workers = 1


# =============================================================================
# URL ANALYZER
# =============================================================================


class URLAnalyzer:
    """Analyzes sentences for specific URLs"""

    def __init__(self, config: URLAnalysisConfig, label_mapper: LabelMapper):
        self.config = config
        self.label_mapper = label_mapper

    def _get_connection(self):
        """Create database connection"""
        return sqlite3.connect(self.config.db_path)

    def _parse_json_safe(self, value):
        """Safely parse JSON"""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value

    def load_urls_from_excel(self) -> pd.DataFrame:
        """Load URLs from the input Excel file"""
        input_path = Path(self.config.input_csv)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        print(f"📂 Loading URLs from {input_path}...")
        df = pd.read_csv(input_path)

        # Expect columns: url, firm_name (optional)
        if "url" not in df.columns:
            raise ValueError("CSV file must contain a 'url' column")

        print(f"✅ Loaded {len(df)} URLs")
        return df
    def fetch_sentences_for_url(self, url: str) -> Optional[pd.DataFrame]:
        """Fetch all sentences and predictions for a specific URL"""
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
            WHERE w.url = ?
        """

        conn = self._get_connection()
        try:
            df = pd.read_sql(query, conn, params=(url,))
        finally:
            conn.close()

        if df.empty:
            print(f"⚠️  No data found for URL: {url}")
            return None

        # Parse JSON columns
        df["matches"] = df["matches"].apply(self._parse_json_safe)
        df["server_response"] = df["server_response"].apply(self._parse_json_safe)

        return df

    def process_url_sentences(self, url: str, cik: int, data: pd.DataFrame) -> pd.DataFrame:
        """Process all sentences for a URL and create detailed results"""
        print(f"  📊 Processing CIK: {cik}")


        if data is None or data.empty:
            return pd.DataFrame()

        # Should only be one row (one report per URL)
        if len(data) > 1:
            print(f"⚠️  Multiple records found for {url}, using first one")

        row = data.iloc[0]
        matches = row["matches"]
        predictions = row["server_response"]

        if not matches or not predictions:
            print(f"⚠️  No sentences or predictions for {url}")
            return pd.DataFrame()

        # Process each sentence
        sentences_data = []
        min_len = min(len(matches), len(predictions))

        for i in range(min_len):
            sentence = matches[i]
            prob_dict = predictions[i]

            # Skip invalid predictions
            if not isinstance(prob_dict, dict) or "error" in prob_dict:
                continue

            # Get primary label(s)
            primary_labels = self.label_mapper.get_primary_labels(prob_dict)
            primary_label_str = primary_labels[0] if primary_labels else "Irrelevant"
            all_primary_labels = (
                "; ".join(primary_labels)
                if len(primary_labels) > 1
                else primary_label_str
            )

            # Get top 5 predictions with scores
            top_preds = sorted(prob_dict.items(), key=lambda x: x[1], reverse=True)[:5]
            top_preds_str = ", ".join(
                [f"{label}:{score:.3f}" for label, score in top_preds]
            )

            # Get all active binary labels (for column reporting)
            binary_labels = {
                label: (
                    1
                    if prob_dict.get(label, 0.0) >= self.config.confidence_threshold
                    else 0
                )
                for label in self.config.labels
            }

            # Get all active binary labels
            active_labels = [
                label for label, value in binary_labels.items() if value == 1
            ]
            active_labels_str = ", ".join(active_labels) if active_labels else "None"

            sentences_data.append(
                {
                    "sentence_num": i + 1,
                    "sentence": sentence,
                    "primary_label": primary_label_str,
                    "all_primary_labels": all_primary_labels,
                    "active_multilabels": active_labels_str,
                    "top_5_predictions": top_preds_str,
                    **binary_labels,  # Include all binary labels as columns
                    **{
                        f"prob_{label}": prob_dict.get(label, 0.0)
                        for label in self.config.labels
                    },  # Raw probabilities
                }
            )

        df = pd.DataFrame(sentences_data)

        # Add metadata
        df.insert(0, "cik", row["cik"])
        df.insert(1, "year", row["year"])
        df.insert(2, "url", url)

        print(f"    ✓ Processed {len(df)} sentences")
        return df

    def generate_summary_statistics(
        self, all_results: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """Generate summary statistics across all URLs"""
        summary_data = []

        for (cik, year), df in all_results.items():
            if df.empty:
                summary_data.append(
                    {
                        "cik": cik, "year": year,
                        "total_sentences": 0,
                        "status": "No data found",
                    }
                )
                continue

            # Count primary labels
            label_counts = df["primary_label"].value_counts().to_dict()

            # Count specific derivative types (current use)
            ir_use = ((df["ir_use"] == 1) & (df["curr"] == 1)).sum()
            fx_use = ((df["fx_use"] == 1) & (df["curr"] == 1)).sum()
            cp_use = ((df["cp_use"] == 1) & (df["curr"] == 1)).sum()
            eq_use = ((df["eq_use"] == 1) & (df["curr"] == 1)).sum()
            warr = ((df["warr"] == 1) & (df["curr"] == 1)).sum()
            emb = ((df["emb"] == 1) & (df["curr"] == 1)).sum()

            # Any current use
            any_current_use = (
                (df["ir_use"] == 1)
                | (df["fx_use"] == 1)
                | (df["cp_use"] == 1)
                | (df["eq_use"] == 1)
                | (df["warr"] == 1)
                | (df["emb"] == 1)
            ) & (df["curr"] == 1)

            summary_data.append(
                {
                    "cik": df["cik"].iloc[0],
                    "year": df["year"].iloc[0],
                    "url": df["url"].iloc[0],
                    "total_sentences": len(df),
                    "sentences_with_current_use": any_current_use.sum(),
                    "ir_current_use": ir_use,
                    "fx_current_use": fx_use,
                    "cp_current_use": cp_use,
                    "eq_current_use": eq_use,
                    "warrant_current": warr,
                    "embedded_current": emb,
                    "is_derivatives_user": "Yes" if any_current_use.any() else "No",
                    "most_common_label": (
                        df["primary_label"].mode()[0] if not df.empty else "N/A"
                    ),
                    "irrelevant_sentences": (df["primary_label"] == "Irrelevant").sum(),
                    **{f"count_{k}": v for k, v in label_counts.items()},
                }
            )

        summary_df = pd.DataFrame(summary_data)

        # Reorder columns for better readability
        priority_cols = [
            "cik",
            "year",
            "url",
            "total_sentences",
            "is_derivatives_user",
            "sentences_with_current_use",
            "ir_current_use",
            "fx_current_use",
            "cp_current_use",
            "eq_current_use",
            "warrant_current",
            "embedded_current",
        ]
        other_cols = [col for col in summary_df.columns if col not in priority_cols]
        summary_df = summary_df[priority_cols + other_cols]

        return summary_df

    def write_results_to_excel(
        self, all_results: Dict[str, pd.DataFrame], summary: pd.DataFrame
    ):
        """Write all results to a multi-sheet Excel workbook"""
        output_path = self.config.output_dir / self.config.output_excel
        print(f"\n📝 Writing results to {output_path}...")

        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
            workbook = writer.book
            workbook.strings_to_urls = False

            # Write summary as first sheet
            summary.to_excel(writer, sheet_name="Summary", index=False)

            # Format summary sheet
            worksheet = writer.sheets["Summary"]
            worksheet.set_column("A:D", 12)  # CIK, year, URL preview
            worksheet.set_column("E:Z", 10)  # Other columns

            # Write each firm's sentences to a separate sheet
            for (cik, year), df in all_results.items():
                if df.empty:
                    continue

                # Truncate sheet name to 31 characters (Excel limit)
                sheet_name = f"CIK_{cik}_{year}"[:31]

                df.to_excel(writer, sheet_name=sheet_name, index=False)

                # Format worksheet
                worksheet = writer.sheets[sheet_name]
                worksheet.set_column("A:D", 12)  # Metadata columns
                worksheet.set_column("E:E", 80)  # Sentence column (wide)
                worksheet.set_column("F:Z", 10)  # Other columns

                # Freeze panes at sentence column
                worksheet.freeze_panes(1, 5)

        print(f"✅ Results saved successfully")
        print(f"   - Summary sheet with {len(summary)} firms")
        print(
            f"   - {len([df for df in all_results.values() if not df.empty])} detailed firm sheets"
        )

    def run(self):
        """Execute the URL analysis pipeline"""
        print("=" * 70)
        print("URL SENTENCE ANALYSIS PIPELINE")
        print("=" * 70)

        # Load URLs
        urls_df = self.load_urls_from_excel()

        # Process each URL
        print(f"\n📊 Processing {len(urls_df)} URLs...")
        all_results = {}

        for _, row in tqdm(
            urls_df.iterrows(), total=len(urls_df), desc="Processing URLs"
        ):
            url = row["url"]
            # Fetch data once to get CIK/year and to pass to process_url_sentences
            report_data = self.fetch_sentences_for_url(url)
            if report_data is None or report_data.empty:
                print(f"⚠️ Skipping URL, no data found in DB: {url}")
                continue

            cik = report_data.iloc[0]["cik"]
            year = report_data.iloc[0]["year"]
            # Pass the already fetched data to avoid a second DB call
            sentences_df = self.process_url_sentences(url, cik, report_data)
            all_results[(cik, year)] = sentences_df

        # Generate summary
        print("\n📈 Generating summary statistics...")
        summary_df = self.generate_summary_statistics(all_results)

        # Write to Excel
        self.write_results_to_excel(all_results, summary_df)

        # Print summary to console
        print("\n" + "=" * 70)
        print("ANALYSIS SUMMARY")
        print("=" * 70)

        total_firms = len(urls_df)
        firms_with_data = len([df for df in all_results.values() if not df.empty])
        total_sentences = sum(len(df) for df in all_results.values())
        firms_using_derivatives = (summary_df["is_derivatives_user"] == "Yes").sum()

        print(f"Total firms analyzed: {total_firms}")
        print(f"Firms with data: {firms_with_data}")
        print(f"Total sentences processed: {total_sentences:,}")
        print(f"Firms using derivatives: {firms_using_derivatives}")
        print(
            f"\nResults saved to: {self.config.output_dir / self.config.output_excel}"
        )
        print("=" * 70)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("URL Sentence Analysis Pipeline")
    print("=" * 70)

    # Initialize configuration
    config = URLAnalysisConfig()

    # Initialize label mapper
    label_mapper = LabelMapper(config.keywords_json, config.labels)

    # Initialize and run analyzer
    analyzer = URLAnalyzer(config, label_mapper)
    analyzer.run()

    print("\n" + "=" * 70)
    print("Pipeline finished successfully!")
    print("=" * 70)

# %%
