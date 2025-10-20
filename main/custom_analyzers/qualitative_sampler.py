import pandas as pd
from pathlib import Path
import random
import json
from jinja2 import Environment, FileSystemLoader
from .analysis import Config, LabelMapper, DataLoader, BaseAnalyzer
from typing import List, Dict, Any, Tuple

class QualitativeSampler(BaseAnalyzer):
    """
    Creates a static HTML page with a random sample of reports for qualitative review.
    Displays reconstructed text, keyword flags, and model flags.
    """

    def __init__(
        self,
        config: Config,
        label_mapper: LabelMapper,
        sample_size: int = 50,
        random_state: int = 42,
    ):
        super().__init__(config, label_mapper)
        self.data_loader = DataLoader(config)
        self.sample_size = sample_size
        self.random_state = random_state
        self.output_filename = self.config.output_dir / "qualitative_review_sample.html"
        self.sampled_urls_csv = self.config.output_dir / "qualitative_review_sampled_urls.csv"
        # Basic HTML template for the report
        self.html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Qualitative Review Sample</title>
    <style>
        body { font-family: sans-serif; line-height: 1.6; margin: 20px; background-color: #f4f4f9; color: #333; }
        .container { max-width: 900px; margin: auto; background: white; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .report { border-bottom: 2px solid #eee; padding-bottom: 20px; margin-bottom: 20px; }
        h1 { color: #444; }
        h2 { color: #555; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
        a { color: #007bff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f8f8f8; }
        .text-content { background-color: #fafafa; border-left: 3px solid #007bff; padding: 15px; white-space: pre-wrap; word-wrap: break-word; }
        .flag-yes { color: green; font-weight: bold; }
        .flag-no { color: red; }
        .sentence-container { margin-bottom: 1em; }
        .sentence-labels { font-size: 0.8em; color: #666; background-color: #e9e9f3; padding: 3px 8px; border-radius: 12px; display: inline-block; margin-top: 5px; }
        .sentence-labels strong { color: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Qualitative Review Sample ({{ num_samples }} Reports)</h1>
        {% for report in reports %}
        <div class="report">
            <h2>Report: CIK {{ report.cik }} ({{ report.year }})</h2>
            <p><strong>URL:</strong> <a href="{{ report.url }}" target="_blank">{{ report.url }}</a></p>
            
            <h3>Comparison Flags</h3>
            <table>
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Keyword Flag</th>
                        <th>Model Flag</th>
                    </tr>
                </thead>
                <tbody>
                    {% for flag in report.flags %}
                    <tr>
                        <td>{{ flag.name }}</td>
                        <td class="{{ 'flag-yes' if flag.keyword else 'flag-no' }}">{{ 'Yes' if flag.keyword else 'No' }}</td>
                        <td class="{{ 'flag-yes' if flag.model else 'flag-no' }}">{{ 'Yes' if flag.model else 'No' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <h3>Extracted Text</h3>
            <div class="text-content">
                {% for sentence_info in report.sentences %}
                    <div class="sentence-container">
                        <p>{{ sentence_info.text }}</p>
                        <div class="sentence-labels">
                            <strong>Primary:</strong> {{ sentence_info.primary_label if sentence_info.primary_label else 'None' }}
                            &nbsp;|&nbsp;
                            <strong>All Primary:</strong> {{ sentence_info.all_primary_labels | join(', ') if sentence_info.all_primary_labels else 'None' }}
                            &nbsp;|&nbsp;
                            <strong>Active Scores:</strong> {{ sentence_info.labels | join(', ') if sentence_info.labels else 'None' }}
                        </div>
                    </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

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
                                if float(score) > self.config.confidence_threshold:
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
        # Use a left merge to keep all sampled reports, even if they don't have flags yet.
        final_sample_df = pd.merge(sample_df, data, on=['cik', 'year', 'url'], how='left').fillna(0)

        reports_data = []
        for _, row in final_sample_df.iterrows():
            report = {
                "cik": row["cik"],
                "year": row["year"],
                "url": row["url"],
                "sentences": self._get_sentence_data(row["url"], row["year"]),
                "flags": [
                    {
                        "name": "IR Hedge",
                        "keyword": row.get("ir_user", 0),
                        "model": row.get("model_ir_user", 0),
                    },
                    {
                        "name": "FX Hedge",
                        "keyword": row.get("fx_user", 0),
                        "model": row.get("model_fx_user", 0),
                    },
                    {
                        "name": "CP Hedge",
                        "keyword": row.get("cp_user", 0),
                        "model": row.get("model_cp_user", 0),
                    },
                    {
                        "name": "Any Hedge (IR/FX/CP)",
                        "keyword": row.get("user", 0),
                        "model": row.get("model_user", 0),
                    },
                ],
            }
            reports_data.append(report)

        # Render the HTML
        # Using Jinja2 for safer and cleaner template rendering
        from jinja2 import Template
        template = Template(self.html_template)
        html_content = template.render(reports=reports_data, num_samples=len(reports_data))

        # Save the HTML file
        with open(self.output_filename, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"   ✅ Qualitative sample saved to: {self.output_filename}")

        # This analyzer doesn't produce a DataFrame, so return an empty dict
        return {}