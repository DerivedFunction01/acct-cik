import pandas as pd
import json
from .analysis import Config, LabelMapper, DataLoader, BaseAnalyzer
from typing import List, Dict, Any
from pathlib import Path

class QualitativeSampler(BaseAnalyzer):
    """
    Creates a static HTML page with a random sample of reports for qualitative review.
    Displays reconstructed text, keyword flags, and model flags.
    """

    def __init__(
        self,
        config: Config,
        label_mapper: LabelMapper,
        sample_size: int = 100,
        random_state: int = 42,
        only_terminated: bool = False,
    ):
        super().__init__(config, label_mapper)
        self.data_loader = DataLoader(config)
        self.sample_size = sample_size
        self.random_state = random_state
        self.output_filename = self.config.output_dir / "qualitative_review_sample.html"
        self.only_terminated = only_terminated
        self.sampled_urls_csv = self.config.output_dir / "qualitative_review_sampled_urls.csv"
        self.json_output_filename = self.config.output_dir / "qualitative_review_sample.json"
        self.template_path = Path(__file__).parent / "qualitative_sampler_template.html"

    def _get_sentence_data(self, url: str, year: int) -> List[Dict[str, Any]]:
        """
        Fetches sentences and their corresponding model predictions from the DB.

        Returns:
            A list of dictionaries, where each dict contains 'text' and 'labels'.
        """
        with self.data_loader._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT wr.matches, sr.server_response
                FROM webpage_result wr
                JOIN server_result sr ON wr.url = sr.url
                WHERE wr.url = ?
                """,
                (url,),
            )
            row = cursor.fetchone()

        if not row or not row[0] or not row[1]:
            return [{"text": "No text or prediction data found in database.", "labels": []}]

        try:
            matches_dict = json.loads(row[0])
            predictions = json.loads(row[1])

            if isinstance(matches_dict, dict):
                sentences = [s for sentences_list in matches_dict.values() for s in sentences_list]
            elif isinstance(matches_dict, list):
                sentences = matches_dict
            else:
                return [{"text": "Matches data is not in a recognized format.", "labels": []}]

            sentence_data = []
            for i, text in enumerate(sentences):
                pred_labels: List[str] = []
                primary_label = None
                all_primary_labels: List[str] = []

                if i < len(predictions):
                    prediction_item = predictions[i]

                    # Resolve a numeric label->score vector from several shapes
                    pred_vector = {}
                    if isinstance(prediction_item, dict):
                        if "pred_vector" in prediction_item and isinstance(prediction_item.get("pred_vector"), dict):
                            pred_vector = prediction_item.get("pred_vector", {})
                        elif all(isinstance(v, (int, float)) for v in prediction_item.values()):
                            pred_vector = prediction_item
                        elif "primary_labels" in prediction_item and isinstance(prediction_item.get("primary_labels"), list):
                            # If only a list of primary labels is provided, use that as all_primary_labels
                            all_primary_labels = [str(l) for l in prediction_item.get("primary_labels", [])]

                    elif isinstance(prediction_item, int):
                        # Legacy single integer label id
                        if self.label_mapper and getattr(self.label_mapper, "primary_id2label", None) is not None:
                            label_name = self.label_mapper.primary_id2label.get(prediction_item)
                            if label_name:
                                all_primary_labels = [label_name]

                    # If we have a numeric pred_vector, compute labels and primary labels using LabelMapper when available
                    if pred_vector:
                        # Create a list of 'label (score)' for those above threshold
                        for label, score in pred_vector.items():
                            try:
                                if float(score) >= self.config.display_threshold:
                                    pred_labels.append(f"{label} ({float(score):.2f})")
                            except Exception:
                                continue

                        # Use label_mapper to derive primary labels ordering if available
                        if self.label_mapper:
                            # LabelMapper expects a mapping label->score
                            try:
                                primary_list = self.label_mapper.get_primary_labels(pred_vector) or []
                                all_primary_labels = primary_list
                                primary_label = primary_list[0] if primary_list else None
                            except Exception:
                                # Fallback: leave primary_label as None
                                pass

                sentence_data.append({
                    "text": text,
                    "labels": pred_labels,
                    "primary_label": primary_label,
                    "all_primary_labels": all_primary_labels,
                })

            return sentence_data

        except (json.JSONDecodeError, TypeError, IndexError) as e:
            return [{"text": f"Error processing sentence data: {e}", "labels": []}]

    def analyze(self, data: pd.DataFrame, **kwargs) -> dict:
        """
        Main analysis method.
        It now samples from all available reports in `server_result` and then
        merges flags from the pre-aggregated `data` DataFrame.

        Args:
            data (pd.DataFrame): Merged DataFrame containing both keyword and model flags.
        """
        print("-> Generating qualitative review sample...")

        if "url" not in data.columns:
            print("   ❌ 'url' column not found in input data. Skipping.")
            return {}

        # If 'only_terminated' is set, the sampling pool should be just the terminated reports.
        if self.only_terminated:
            print("   -> Filtering for terminated reports to create the sampling pool...")
            terminated_mask = (data['model_ir_terminated'] == 1) | \
                              (data['model_fx_terminated'] == 1) | \
                              (data['model_cp_terminated'] == 1)

            # The sampling pool is now the subset of reports that are terminated.
            sampling_pool_df = data[terminated_mask].copy()

            if sampling_pool_df.empty:
                print("   ⚠️  No terminated reports found to sample from. Aborting qualitative sampler.")
                return {}

            print(f"   -> Found {len(sampling_pool_df)} terminated reports to sample from.")
            sample_df = sampling_pool_df.sample(n=min(self.sample_size, len(sampling_pool_df)), random_state=self.random_state)
            final_sample_df = sample_df # The sample is already merged with flag data.

        # Fetch all available reports from the database to use as the sampling pool
        print("   -> Fetching all available reports from server_result for sampling...")
        with self.data_loader._get_connection() as conn:
            all_reports_df = pd.read_sql_query(
                """
                SELECT r.cik, r.year, r.url
                FROM server_result s
                JOIN report_data r ON s.url = r.url
                """,
                conn
            )
        print(f"   -> Found {len(all_reports_df)} total reports available for sampling.")

        if not self.only_terminated:
            # Check if a file with sampled URLs already exists.
            if self.sampled_urls_csv.exists():
                print(f"   -> Found existing sample file: {self.sampled_urls_csv}. Reusing URLs.")
                try:
                    sampled_keys_df = pd.read_csv(self.sampled_urls_csv)
                    # Use an inner merge to select only the rows from the full report list that match the saved sample.
                    sample_df = pd.merge(all_reports_df, sampled_keys_df[['cik', 'year']], on=['cik', 'year'], how='inner')
                    if len(sample_df) != len(sampled_keys_df):
                        print(f"   ⚠️  Warning: Mismatch between sampled URLs file and available data. Found {len(sample_df)} of {len(sampled_keys_df)} reports.")
                except Exception as e:
                    print(f"   ❌ Error reading sample file: {e}. Generating a new random sample.")
                    sample_df = all_reports_df.sample(n=min(self.sample_size, len(all_reports_df)), random_state=self.random_state)
                    # Save the new sample's keys for future runs
                    sample_df[['cik', 'year', 'url']].to_csv(self.sampled_urls_csv, index=False)
                    print(f"   -> Saved new random sample to {self.sampled_urls_csv}")
            else:
                print("   -> No existing sample file found. Generating a new random sample.")
                sample_df = all_reports_df.sample(n=min(self.sample_size, len(all_reports_df)), random_state=self.random_state)
                # Save the new sample's keys for future runs
                sample_df[['cik', 'year', 'url']].to_csv(self.sampled_urls_csv, index=False)
                print(f"   -> Saved new random sample to {self.sampled_urls_csv}")
            # Now, merge the sampled data with the pre-aggregated flags.
            final_sample_df = pd.merge(sample_df, data, on=['cik', 'year', 'url'], how='left').fillna(0)

        reports_data = []
        for _, row in final_sample_df.iterrows():
            def get_flag_status(use_flag, term_flag):
                # This logic now reads the pre-calculated flags from analysis.py
                if term_flag:
                    return "TERMINATED"
                elif use_flag:
                    return "YES"
                else:
                    return "NO"

            def get_ratio_str(current_count, terminated_count):
                if current_count > 0:
                    return f"{(terminated_count / current_count):.2f}"
                elif terminated_count > 0:
                    return "Inf"
                return "N/A"

            report = {
                "cik": row["cik"],
                "year": row["year"],
                "url": row["url"],
                "sentences": self._get_sentence_data(row["url"], row["year"]),
                # Pass the terminated flags to the report data for the JSON generation later
                "model_ir_terminated": row.get("model_ir_terminated", 0),
                "model_fx_terminated": row.get("model_fx_terminated", 0),
                "model_cp_terminated": row.get("model_cp_terminated", 0),
                "flags": [
                    {
                        "name": "IR Hedge",
                        "keyword": row.get("ir_user", 0),
                        "model": get_flag_status(row.get("model_ir_user", 0), row.get("model_ir_terminated", 0)),
                        "hist_count": int(row.get("model_ir_hist_count", 0)),
                        "current_count": int(row.get("model_ir_current_count", 0)),
                        "terminated_count": int(row.get("model_ir_terminated_count", 0)),
                        "ratio": get_ratio_str(row.get("model_ir_current_count", 0), row.get("model_ir_terminated_count", 0)),
                    },
                    {
                        "name": "FX Hedge",
                        "keyword": row.get("fx_user", 0),
                        "model": get_flag_status(row.get("model_fx_user", 0), row.get("model_fx_terminated", 0)),
                        "hist_count": int(row.get("model_fx_hist_count", 0)),
                        "current_count": int(row.get("model_fx_current_count", 0)),
                        "terminated_count": int(row.get("model_fx_terminated_count", 0)),
                        "ratio": get_ratio_str(row.get("model_fx_current_count", 0), row.get("model_fx_terminated_count", 0)),
                    },
                    {
                        "name": "CP Hedge",
                        "keyword": row.get("cp_user", 0),
                        "model": get_flag_status(row.get("model_cp_user", 0), row.get("model_cp_terminated", 0)),
                        "hist_count": int(row.get("model_cp_hist_count", 0)),
                        "current_count": int(row.get("model_cp_current_count", 0)),
                        "terminated_count": int(row.get("model_cp_terminated_count", 0)),
                        "ratio": get_ratio_str(row.get("model_cp_current_count", 0), row.get("model_cp_terminated_count", 0)),
                    },
                ],
            }
            reports_data.append(report)

        # Render the HTML
        # Using Jinja2 for safer and cleaner template rendering
        from jinja2 import Template
        import os

        try:
            with open(self.template_path, "r", encoding="utf-8") as f:
                template = Template(f.read())
        except FileNotFoundError:
            print(f"   ❌ Error: Template file not found at {self.template_path}")
            return {}

        # Define temporary and final paths
        temp_html_path = self.output_filename.with_suffix('.html.tmp')
        temp_csv_path = self.sampled_urls_csv.with_suffix('.csv.tmp')

        # Get all primary labels for the filter UI
        all_labels = []
        if self.label_mapper and self.label_mapper.primary_id2label:
            all_labels = sorted(list(self.label_mapper.primary_id2label.values()))

        # Pass reports as JSON to embed into the SPA template
        reports_json = json.dumps(reports_data, ensure_ascii=False)
        html_content = template.render(reports=reports_data, num_samples=len(reports_data), reports_json=reports_json, all_labels=all_labels)

        # Save the HTML file to a temporary location
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # --- Create and save the JSON output for the AI agent ---
        agent_reports_data = []
        for report in reports_data:
            # The AI needs the raw text and the model's flags for comparison.
            extracted_text = [s.get("text", "") for s in report.get("sentences", [])]
            # The 'model' value is already the correct string ('YES', 'NO', 'TERMINATED')
            # from when reports_data was created. We can use it directly.
            model_flags = {
                "IR": report["flags"][0]["model"],
                "FX": report["flags"][1]["model"],
                "CP": report["flags"][2]["model"],
            }

            agent_reports_data.append({
                "cik": report["cik"],
                "year": report["year"],
                "url": report["url"],
                "model_flags": model_flags,
                "extracted_text": extracted_text
            })

        temp_json_path = self.json_output_filename.with_suffix('.json.tmp')
        with open(temp_json_path, "w", encoding="utf-8") as f:
            json.dump(agent_reports_data, f, indent=2, ensure_ascii=False)

        # Atomically rename the temporary file to the final destination
        try:
            os.rename(temp_html_path, self.output_filename)
            os.rename(temp_json_path, self.json_output_filename)
        except: # Try replaceing
            os.replace(temp_html_path, self.output_filename)
            os.replace(temp_json_path, self.json_output_filename)

        print(f"   ✅ Qualitative sample saved to: {self.output_filename}")
        print(f"   ✅ JSON data saved to: {self.json_output_filename}")

        # This analyzer doesn't produce a DataFrame, so return an empty dict
        return {}
