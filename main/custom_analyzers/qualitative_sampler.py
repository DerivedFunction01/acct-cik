"""
Qualitative Sampler Analyzer
=============================
Generates an interactive HTML viewer and JSON output for qualitative review.
"""

import pandas as pd
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from .analysis import BaseAnalyzer, Config, DataLoader


class QualitativeSampler(BaseAnalyzer):
    """
    Creates a static HTML page with a random sample of reports for qualitative review.
    Displays reconstructed text with NLI classifications, keyword flags, and model flags.
    """

    def __init__(
        self,
        config: Config,
        data_loader: Optional[DataLoader] = None,
        sample_size: int = 100,
        random_state: int = 42,
        only_with_findings: bool = False,
    ):
        """
        Args:
            config: Pipeline configuration
            data_loader: DataLoader instance (will create if not provided)
            sample_size: Number of reports to sample
            random_state: Random seed for reproducible sampling
            only_with_findings: If True, only sample from reports with model findings
        """
        super().__init__(config, data_loader)
        self.sample_size = sample_size
        self.random_state = random_state
        self.only_with_findings = only_with_findings

        # Output paths
        self.output_filename = self.config.output_dir / "qualitative_review_sample.html"
        self.sampled_urls_csv = (
            self.config.output_dir / "qualitative_review_sampled_urls.csv"
        )
        self.json_output_filename = (
            self.config.output_dir / "qualitative_review_sample.json"
        )
        self.template_path = Path(__file__).parent / "qualitative_sampler_template.html"

        # Initialize data loader if not provided
        if self.data_loader is None:
            self.data_loader = DataLoader(config)

    def _get_sentence_data(self, url: str, year: int) -> List[Dict[str, Any]]:
        """
        Fetches sentences and their NLI classifications from the DB.

        Returns:
            A list of dictionaries with 'text', 'labels', and 'primary_label'.
        """
        import sqlite3

        with self.data_loader._get_connection() as conn:
            cursor = conn.cursor()

            # Get sentences from derivative_type_matches
            cursor.execute(
                """
                SELECT ir_matches, fx_matches, cp_matches, eq_matches
                FROM derivative_type_matches
                WHERE url = ?
                """,
                (url,),
            )
            sentence_row = cursor.fetchone()

            # Get classifications from classification_results
            cursor.execute(
                """
                SELECT category, found_policy, found_existence, found_notional, found_pnl
                FROM classification_results
                WHERE url = ?
                """,
                (url,),
            )
            classification_rows = cursor.fetchall()

        if not sentence_row:
            return [
                {
                    "text": "No sentence data found in database.",
                    "labels": [],
                    "primary_label": None,
                }
            ]

        try:
            # Parse sentence arrays
            all_sentences = []
            categories = ["ir", "fx", "cp", "eq"]
            category_map = {}  # Maps sentence index to category

            for i, cat in enumerate(categories):
                sentences_json = sentence_row[i]
                if sentences_json:
                    sentences = (
                        json.loads(sentences_json)
                        if isinstance(sentences_json, str)
                        else sentences_json
                    )
                    if isinstance(sentences, list):
                        for sent in sentences:
                            idx = len(all_sentences)
                            all_sentences.append(sent)
                            category_map[idx] = cat

            # Build classification map
            classifications_by_category = {}
            for row in classification_rows:
                cat, policy, existence, notional, pnl = row

                # Parse JSON arrays
                def parse_array(val):
                    if isinstance(val, str):
                        return json.loads(val) if val else []
                    return val if isinstance(val, list) else []

                classifications_by_category[cat] = {
                    "policy": set(parse_array(policy)),
                    "existence": set(parse_array(existence)),
                    "notional": set(parse_array(notional)),
                    "pnl": set(parse_array(pnl)),
                }

            # Build sentence data with classifications
            sentence_data = []
            for idx, text in enumerate(all_sentences):
                cat = category_map.get(idx, "unknown")
                classif = classifications_by_category.get(cat, {})

                labels = []
                primary_label = None

                # Check which classifications apply to this sentence
                # Note: idx here is global, but we need the index within the category
                # We'll use a simplified approach assuming sentences are in order

                has_policy = idx in classif.get("policy", set())
                has_existence = idx in classif.get("existence", set())
                has_notional = idx in classif.get("notional", set())
                has_pnl = idx in classif.get("pnl", set())

                # Determine primary label (highest priority classification)
                if has_notional:
                    primary_label = f"{cat.upper()}_Notional"
                    labels.append(f"{cat.upper()}_Notional")
                elif has_pnl:
                    primary_label = f"{cat.upper()}_PnL"
                    labels.append(f"{cat.upper()}_PnL")
                elif has_existence:
                    primary_label = f"{cat.upper()}_Existence"
                    labels.append(f"{cat.upper()}_Existence")
                elif has_policy:
                    primary_label = f"{cat.upper()}_Policy"
                    labels.append(f"{cat.upper()}_Policy")

                # Add additional labels for display
                if has_policy and primary_label != f"{cat.upper()}_Policy":
                    labels.append(f"{cat.upper()}_Policy")
                if has_existence and primary_label != f"{cat.upper()}_Existence":
                    labels.append(f"{cat.upper()}_Existence")
                if has_pnl and primary_label != f"{cat.upper()}_PnL":
                    labels.append(f"{cat.upper()}_PnL")

                sentence_data.append(
                    {
                        "text": text,
                        "labels": labels,
                        "primary_label": primary_label,
                        "all_primary_labels": labels,  # For compatibility with template
                    }
                )

            return sentence_data

        except (json.JSONDecodeError, TypeError, IndexError) as e:
            return [
                {
                    "text": f"Error processing sentence data: {e}",
                    "labels": [],
                    "primary_label": None,
                }
            ]

    def _get_sampling_pool(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Determine which reports to sample from based on configuration.
        """
        if self.only_with_findings:
            print("   -> Filtering for reports with model findings...")
            # Reports with any model user flags
            finding_mask = (
                (data.get("model_ir_user", 0) == 1)
                | (data.get("model_fx_user", 0) == 1)
                | (data.get("model_cp_user", 0) == 1)
                | (data.get("model_eq_user", 0) == 1)
            )
            pool = data[finding_mask].copy()

            if pool.empty:
                print("   ⚠️  No reports with findings found. Using all reports.")
                return data

            print(f"   -> Found {len(pool)} reports with findings to sample from.")
            # conver the pool to a dataframe
            return pd.DataFrame(pool)
        else:
            return data

    def analyze(self, data: pd.DataFrame, **kwargs) -> dict:
        """
        Main analysis method.
        Samples reports and generates interactive HTML viewer and JSON output.

        Args:
            data (pd.DataFrame): Merged DataFrame containing both keyword and model flags.
        """
        print("-> Generating qualitative review sample...")

        if "url" not in data.columns:
            print("   ❌ 'url' column not found in input data. Skipping.")
            return {}

        # Get sampling pool
        sampling_pool = self._get_sampling_pool(data)

        # Check for existing sample file
        if self.sampled_urls_csv.exists():
            print(
                f"   -> Found existing sample file: {self.sampled_urls_csv}. Reusing URLs."
            )
            try:
                sampled_keys_df = pd.read_csv(self.sampled_urls_csv)
                sample_df = pd.merge(
                    sampling_pool,
                    sampled_keys_df[["cik", "year"]],
                    on=["cik", "year"],
                    how="inner",
                )
                if len(sample_df) != len(sampled_keys_df):
                    print(
                        f"   ⚠️  Warning: Found {len(sample_df)} of {len(sampled_keys_df)} saved reports."
                    )
            except Exception as e:
                print(f"   ❌ Error reading sample file: {e}. Generating new sample.")
                sample_df = sampling_pool.sample(
                    n=min(self.sample_size, len(sampling_pool)),
                    random_state=self.random_state,
                )
                sample_df[["cik", "year", "url"]].to_csv(
                    self.sampled_urls_csv, index=False
                )
                print(f"   -> Saved new sample to {self.sampled_urls_csv}")
        else:
            print("   -> No existing sample file found. Generating new sample.")
            sample_df = sampling_pool.sample(
                n=min(self.sample_size, len(sampling_pool)),
                random_state=self.random_state,
            )
            sample_df[["cik", "year", "url"]].to_csv(self.sampled_urls_csv, index=False)
            print(f"   -> Saved new sample to {self.sampled_urls_csv}")

        # Build report data
        reports_data = []
        for _, row in sample_df.iterrows():

            def get_flag_status(use_flag):
                return "YES" if use_flag else "NO"

            report = {
                "cik": int(row["cik"]),
                "year": int(row["year"]),
                "url": row["url"],
                "sentences": self._get_sentence_data(row["url"], row["year"]),
                "flags": [
                    {
                        "name": "IR Hedge",
                        "keyword": int(row.get("ir_user", 0)),
                        "model": get_flag_status(row.get("model_ir_user", 0)),
                        "hist_count": 0,  # Placeholder - no longer used
                        "current_count": 0,
                        "terminated_count": 0,
                        "ratio": "N/A",
                    },
                    {
                        "name": "FX Hedge",
                        "keyword": int(row.get("fx_user", 0)),
                        "model": get_flag_status(row.get("model_fx_user", 0)),
                        "hist_count": 0,
                        "current_count": 0,
                        "terminated_count": 0,
                        "ratio": "N/A",
                    },
                    {
                        "name": "CP Hedge",
                        "keyword": int(row.get("cp_user", 0)),
                        "model": get_flag_status(row.get("model_cp_user", 0)),
                        "hist_count": 0,
                        "current_count": 0,
                        "terminated_count": 0,
                        "ratio": "N/A",
                    },
                    {
                        "name": "EQ Derivative",
                        "keyword": 0,  # No keyword equivalent
                        "model": get_flag_status(row.get("model_eq_user", 0)),
                        "hist_count": 0,
                        "current_count": 0,
                        "terminated_count": 0,
                        "ratio": "N/A",
                    },
                ],
            }
            reports_data.append(report)

        # Generate HTML
        self._generate_html(reports_data)

        # Generate JSON
        self._generate_json(reports_data)

        print(f"   ✅ Qualitative sample saved to: {self.output_filename}")
        print(f"   ✅ JSON data saved to: {self.json_output_filename}")

        return {}

    def _generate_html(self, reports_data: List[Dict]):
        """Generate interactive HTML viewer."""
        from jinja2 import Template
        import os

        try:
            with open(self.template_path, "r", encoding="utf-8") as f:
                template = Template(f.read())
        except FileNotFoundError:
            print(f"   ❌ Error: Template file not found at {self.template_path}")
            return

        # Get all unique labels for filter UI
        all_labels = set()
        for report in reports_data:
            for sentence in report.get("sentences", []):
                if sentence.get("primary_label"):
                    all_labels.add(sentence["primary_label"])
        all_labels = sorted(list(all_labels))

        # Render template
        reports_json = json.dumps(reports_data, ensure_ascii=False)
        html_content = template.render(
            reports=reports_data,
            num_samples=len(reports_data),
            reports_json=reports_json,
            all_labels=all_labels,
        )

        # Save atomically
        temp_html_path = self.output_filename.with_suffix(".html.tmp")
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        try:
            os.rename(temp_html_path, self.output_filename)
        except:
            os.replace(temp_html_path, self.output_filename)

    def _generate_json(self, reports_data: List[Dict]):
        """Generate JSON output for AI agent analysis."""
        import os

        agent_reports_data = []
        for report in reports_data:
            extracted_text = [s.get("text", "") for s in report.get("sentences", [])]

            model_flags = {
                "IR": report["flags"][0]["model"],
                "FX": report["flags"][1]["model"],
                "CP": report["flags"][2]["model"],
                "EQ": report["flags"][3]["model"],
            }

            agent_reports_data.append(
                {
                    "cik": report["cik"],
                    "year": report["year"],
                    "url": report["url"],
                    "model_flags": model_flags,
                    "extracted_text": extracted_text,
                }
            )

        # Save atomically
        temp_json_path = self.json_output_filename.with_suffix(".json.tmp")
        with open(temp_json_path, "w", encoding="utf-8") as f:
            json.dump(agent_reports_data, f, indent=2, ensure_ascii=False)

        try:
            os.rename(temp_json_path, self.json_output_filename)
        except:
            os.replace(temp_json_path, self.json_output_filename)
