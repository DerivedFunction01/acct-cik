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
        sample_size: int = 100,
        random_state: int = 42,
    ):
        super().__init__(config, label_mapper)
        self.data_loader = DataLoader(config)
        self.sample_size = sample_size
        self.random_state = random_state
        self.output_filename = self.config.output_dir / "qualitative_review_sample.html"
        self.sampled_urls_csv = self.config.output_dir / "qualitative_review_sampled_urls.csv"
        self.json_output_filename = self.config.output_dir / "qualitative_review_sample.json"
        # Basic HTML template for the report
        self.html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Qualitative Review Sample</title>
    <style>
        :root { --sidebar-width: 320px; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; margin: 0; color: #222; }
        .app { display: flex; height: 100vh; }
        .sidebar { width: var(--sidebar-width); background: #0f1724; color: #e6eef8; overflow: auto; padding: 12px; box-sizing: border-box; }
        .sidebar h2 { margin: 8px 0 12px; font-size: 16px; }
        .report-link { display: block; padding: 8px; border-radius: 6px; margin-bottom: 6px; color: inherit; text-decoration: none; }
        .report-link:hover { background: rgba(255,255,255,0.03); }
        .report-link.active { background: rgba(255,255,255,0.06); font-weight: 600; }
        .main { flex: 1; overflow: auto; padding: 20px; box-sizing: border-box; background: #f6f7fb; }
        .header { display:flex; justify-content:space-between; align-items:center; gap:12px; }
        .card { background: #fff; padding: 16px; border-radius: 8px; box-shadow: 0 6px 18px rgba(18, 38, 63, 0.06); margin-top: 12px; }
        table { border-collapse: collapse; width: 100%; margin-top: 8px; }
        th, td { border: 1px solid #eee; padding: 8px; text-align: left; }
        .text-content { background-color: #fcfdff; border-left: 3px solid #2b6cb0; padding: 12px; white-space: pre-wrap; }
        .sentence { margin-bottom: 12px; }
        .sentence-labels { font-size: 0.82em; color: #444; background: #eef2ff; padding: 6px 8px; border-radius: 8px; display:inline-block; }
        .controls { display:flex; gap:8px; align-items:center; }
        .btn { background:#2b6cb0; color:white; padding:8px 12px; border-radius:6px; text-decoration:none; cursor:pointer; border:none; }
        .btn.secondary { background:#edf2ff; color:#1e293b; }
        .meta { color:#475569; font-size:0.95em; }
        .small { font-size:0.85em; color:#64748b; }
    </style>
</head>
<body>
    <div class="app">
        <aside class="sidebar">
            <h2>Qualitative Review ({{ num_samples }} reports)</h2>
            <div id="report-list"></div>
        </aside>
        <main class="main">
            <div class="header">
                <div>
                    <h1 id="report-title">Report</h1>
                    <div class="meta" id="report-meta"></div>
                </div>
                <div class="controls">
                    <button class="btn" id="prev-btn">Previous</button>
                    <button class="btn" id="next-btn">Next</button>
                    <a id="open-url" class="btn secondary" target="_blank">Open URL</a>
                </div>
            </div>

            <div id="report-content" class="card">
                <!-- Flags -->
                <h3>Comparison Flags</h3>
                <table id="flags-table"><thead><tr><th>Category</th><th>Keyword Flag</th><th>Model Flag</th><th>Current Count</th><th>Terminated Count</th></tr></thead><tbody></tbody></table>

                <!-- Extracted text -->
                <h3 style="margin-top:18px">Extracted Text</h3>
                <div id="sentences" class="text-content"></div>
            </div>
        </main>
    </div>

    <!-- Embedded data -->
    <script id="reports-data" type="application/json">{{ reports_json | safe }}</script>

    <script>
        // Small SPA to render each report on its own "page"
        const reports = JSON.parse(document.getElementById('reports-data').textContent || '[]');
        const listEl = document.getElementById('report-list');
        const titleEl = document.getElementById('report-title');
        const metaEl = document.getElementById('report-meta');
        const flagsTableBody = document.querySelector('#flags-table tbody');
        const sentencesEl = document.getElementById('sentences');
        const openUrlEl = document.getElementById('open-url');

        function makeList() {
            reports.forEach((r, idx) => {
                const a = document.createElement('a');
                a.href = `#${idx}`;
                a.className = 'report-link';
                a.textContent = `CIK ${r.cik} (${r.year})`;
                a.dataset.idx = idx;
                listEl.appendChild(a);
            });
        }

        function renderReport(idx) {
            const r = reports[idx];
            if (!r) return;
            // highlight
            Array.from(document.querySelectorAll('.report-link')).forEach(el => el.classList.toggle('active', el.dataset.idx == idx));

            titleEl.textContent = `CIK ${r.cik} — ${r.year}`;
            metaEl.textContent = r.url;
            openUrlEl.href = r.url;
            openUrlEl.textContent = 'Open URL';

            // flags table
            flagsTableBody.innerHTML = '';
            r.flags.forEach(f => {
                const tr = document.createElement('tr');
                const tdName = document.createElement('td'); tdName.textContent = f.name;
                const tdKw = document.createElement('td');
                tdKw.textContent = f.keyword ? 'Yes' : 'No';
                tdKw.style.color = f.keyword ? 'green' : 'red';

                const tdModel = document.createElement('td');
                tdModel.textContent = f.model; // Now a string: 'YES', 'NO', 'TERMINATED'
                if (f.model === 'YES') tdModel.style.color = 'green';
                else if (f.model === 'NO') tdModel.style.color = 'red';
                else if (f.model === 'TERMINATED') tdModel.style.color = 'orange';
                else tdModel.style.color = 'grey';

                const tdCurrCount = document.createElement('td');
                tdCurrCount.textContent = f.current_count;

                const tdTermCount = document.createElement('td');
                tdTermCount.textContent = f.terminated_count;

                tr.appendChild(tdName); tr.appendChild(tdKw); tr.appendChild(tdModel);
                tr.appendChild(tdCurrCount); tr.appendChild(tdTermCount);
                flagsTableBody.appendChild(tr);
            });

            // sentences
            sentencesEl.innerHTML = '';
            (r.sentences || []).forEach(s => {
                const div = document.createElement('div'); div.className = 'sentence';
                const p = document.createElement('p'); p.textContent = s.text;
                const labelsDiv = document.createElement('div'); labelsDiv.className = 'sentence-labels';
                const primary = s.primary_label || 'None';
                const allPrimary = (s.all_primary_labels && s.all_primary_labels.length) ? s.all_primary_labels.join(', ') : 'None';
                const active = (s.labels && s.labels.length) ? s.labels.join(', ') : 'None';
                labelsDiv.innerHTML = `<strong>Primary:</strong> ${primary} &nbsp;|&nbsp; <strong>All Primary:</strong> ${allPrimary} &nbsp;|&nbsp; <strong>Active Scores:</strong> ${active}`;
                div.appendChild(p); div.appendChild(labelsDiv);
                sentencesEl.appendChild(div);
            });
        }

        function route() {
            const hash = window.location.hash.replace('#','');
            let idx = parseInt(hash, 10);
            if (Number.isNaN(idx) || idx < 0 || idx >= reports.length) idx = 0;
            renderReport(idx);
            // update prev/next buttons
            const prevBtn = document.getElementById('prev-btn');
            const nextBtn = document.getElementById('next-btn');
            prevBtn.disabled = idx === 0; nextBtn.disabled = idx === reports.length - 1;
            prevBtn.onclick = () => { window.location.hash = Math.max(0, idx - 1); };
            nextBtn.onclick = () => { window.location.hash = Math.min(reports.length - 1, idx + 1); };
        }

        window.addEventListener('hashchange', route);

        // init
        makeList();
        if (!window.location.hash) window.location.hash = '#0';
        route();
    </script>
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
            def get_flag_status(use_flag, term_flag):
                # This logic now reads the pre-calculated flags from analysis.py
                if term_flag:
                    return "TERMINATED"
                elif use_flag:
                    return "YES"
                else:
                    return "NO"

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
                        "current_count": int(row.get("model_ir_current_count", 0)),
                        "terminated_count": int(row.get("model_ir_terminated_count", 0)),
                    },
                    {
                        "name": "FX Hedge",
                        "keyword": row.get("fx_user", 0),
                        "model": get_flag_status(row.get("model_fx_user", 0), row.get("model_fx_terminated", 0)),
                        "current_count": int(row.get("model_fx_current_count", 0)),
                        "terminated_count": int(row.get("model_fx_terminated_count", 0)),
                    },
                    {
                        "name": "CP Hedge",
                        "keyword": row.get("cp_user", 0),
                        "model": get_flag_status(row.get("model_cp_user", 0), row.get("model_cp_terminated", 0)),
                        "current_count": int(row.get("model_cp_current_count", 0)),
                        "terminated_count": int(row.get("model_cp_terminated_count", 0)),
                    },
                ],
            }
            reports_data.append(report)

        # Render the HTML
        # Using Jinja2 for safer and cleaner template rendering
        from jinja2 import Template
        import os
        template = Template(self.html_template)

        # Define temporary and final paths
        temp_html_path = self.output_filename.with_suffix('.html.tmp')
        temp_csv_path = self.sampled_urls_csv.with_suffix('.csv.tmp')

        # Pass reports as JSON to embed into the SPA template
        reports_json = json.dumps(reports_data, ensure_ascii=False)
        html_content = template.render(reports=reports_data, num_samples=len(reports_data), reports_json=reports_json)

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