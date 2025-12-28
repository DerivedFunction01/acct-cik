# custom_analyzers/qualitative_sampler.py
from pathlib import Path
import pandas as pd
import json
import os
from typing import List, Dict, Any
from .analysis import BaseAnalyzer


class QualitativeSampler(BaseAnalyzer):
    def __init__(self, config, sample_size=50, random_state=42):
        super().__init__(config)
        self.sample_size = sample_size
        self.random_state = random_state

        # Dynamic filename based on input DB name
        db_name = Path(config.db_path).stem
        self.output_filename = config.output_dir / f"sample_view_{db_name}.html"
        self.template_path = Path(__file__).parent / "qualitative_sampler_template.html"

    def _get_sentence_data(self, url: str) -> List[Dict[str, Any]]:
        """Fetches Kept vs Discarded sentences for visualization."""
        lifecycle = self.data_loader.load_document_lifecycle(url)

        # Convert dict to list for display
        sentence_data = []

        # Sort by text length or just list them (since we lost original order in DB storage)
        # To improve this later: store index in DB. For now, listing is fine.
        for text, info in lifecycle.items():
            status = info["status"]
            reason = info["reason"]

            # map status to CSS classes in your template
            label_class = "nli-entailment" if status == "KEPT" else "nli-contradiction"

            labels = [status]
            if reason != "Active Signal":
                labels.append(reason)

            sentence_data.append(
                {
                    "text": text,
                    "labels": labels,
                    "primary_label": f"{status}_{reason}",  # Used for coloring
                    "style_class": label_class,
                }
            )

        return sentence_data

    def analyze(self, **kwargs):
        print(f"-> Sampling from {self.config.db_path}...")

        # Load pool of available reports
        pool = self.data_loader.load_checkpoint_data()

        if pool.empty:
            print("   ⚠️ DB is empty or has no matches.")
            return

        # Sample
        sample_df = pool.sample(
            n=min(self.sample_size, len(pool)), random_state=self.random_state
        )

        reports_data = []
        for _, row in sample_df.iterrows():
            report = {
                "cik": int(row["cik"]),
                "year": int(row["year"]),
                "url": row["url"],
                "sentences": self._get_sentence_data(row["url"]),
                # Minimal flags for now
                "flags": [{"name": "Status", "model": "Processed", "keyword": 1}],
            }
            reports_data.append(report)

        self._generate_html(reports_data)
        print(f"   ✅ Visualization saved: {self.output_filename}")

    def _generate_html(self, reports_data):
        # (Keep your existing HTML generation logic, just ensure it uses the new output_filename)
        from jinja2 import Template

        if not self.template_path.exists():
            print("Template not found!")
            return

        with open(self.template_path, "r", encoding="utf-8") as f:
            template = Template(f.read())

        html_content = template.render(
            reports=reports_data,
            reports_json=json.dumps(reports_data),
            all_labels=["KEPT", "DISCARDED"],
        )

        with open(self.output_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
