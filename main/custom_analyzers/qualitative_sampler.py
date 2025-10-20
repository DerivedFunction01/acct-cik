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
                        <div class="sentence-labels"><strong>Labels:</strong> {{ sentence_info.labels | join(', ') if sentence_info.labels else 'None' }}</div>
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
                pred_labels = []
                if i < len(predictions) and isinstance(predictions[i], dict):
                    # Process multi-label prediction vector
                    pred_vector = predictions[i].get("pred_vector", {})
                    for label, score in pred_vector.items():
                        if score > self.config.confidence_threshold:
                            pred_labels.append(f"{label} ({score:.2f})")
                sentence_data.append({"text": text, "labels": pred_labels})

            return sentence_data

        except (json.JSONDecodeError, TypeError, IndexError) as e:
            return [{"text": f"Error processing sentence data: {e}", "labels": []}]

    def analyze(self, data: pd.DataFrame, **kwargs) -> dict:
        """
        Main analysis method.

        Args:
            data (pd.DataFrame): Merged DataFrame containing both keyword and model flags.
        """
        print("-> Generating qualitative review sample...")

        if "url" not in data.columns:
            print("   ❌ 'url' column not found in input data. Skipping.")
            return {}

        # Take a random sample of the reports
        sample_df = data.sample(
            n=min(self.sample_size, len(data)), random_state=self.random_state
        )

        reports_data = []
        for _, row in sample_df.iterrows():
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