import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


SOURCE_DB_DEFAULT = "union_provenance_risk.db"
TARGET_PARQUET_DEFAULT = "union_provenance_risk.parquet"
SOURCE_TABLE = "provenance_risk"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def _safe_json_loads(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _safe_json_dumps(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    try:
        return json.dumps(obj)
    except TypeError:
        return None


def export_parquet(source_db: str, output_path: str) -> None:
    source_path = Path(source_db)
    if not source_path.exists():
        logging.error("Source DB not found: %s", source_db)
        return

    conn = sqlite3.connect(source_db)
    try:
        query = f"""
            SELECT
                p.accession,
                r.cik,
                r.url,
                r.year,
                p.item1_country_report,
                p.item1a_country_report,
                p.item1_risk_summary,
                p.item1a_risk_summary,
                p.item1_bargaining_report,
                p.item1a_bargaining_report
            FROM {SOURCE_TABLE} p
            LEFT JOIN report_data r ON p.accession = r.accession
        """
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    def extract_fields(row) -> Dict[str, Any]:
        item1_report = _safe_json_loads(row.get("item1_country_report"))
        item1a_report = _safe_json_loads(row.get("item1a_country_report"))
        country_report = item1_report or item1a_report or {}

        summary = country_report.get("summary") or {}
        summary_cov = summary.get("cov") if isinstance(summary, dict) else None
        summary_not_cov = summary.get("not_cov") if isinstance(summary, dict) else None

        item1_risk = _safe_json_loads(row.get("item1_risk_summary"))
        item1a_risk = _safe_json_loads(row.get("item1a_risk_summary"))
        item1_barg = _safe_json_loads(row.get("item1_bargaining_report"))
        item1a_barg = _safe_json_loads(row.get("item1a_bargaining_report"))

        def _merge_counts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(a)
            for k, v in b.items():
                if isinstance(v, dict):
                    if k not in out or not isinstance(out[k], dict):
                        out[k] = dict(v)
                    else:
                        for sk, sv in v.items():
                            out[k][sk] = out[k].get(sk, 0) + sv
                elif isinstance(v, list):
                    if k not in out or not isinstance(out[k], list):
                        out[k] = list(v)
                    else:
                        for item in v:
                            if item not in out[k]:
                                out[k].append(item)
                elif isinstance(v, (int, float)):
                    out[k] = out.get(k, 0) + v
                else:
                    if k not in out:
                        out[k] = v
            return out

        risk_summary = {}
        if item1_risk or item1a_risk:
            risk_summary = _merge_counts(item1_risk or {}, item1a_risk or {})
            if "n" in risk_summary:
                risk_summary["n"] = (
                    (item1_risk or {}).get("n", 0)
                    + (item1a_risk or {}).get("n", 0)
                )

        return {
            "domestic_country_code": country_report.get("domestic_country_code"),
            "dom_cov": summary.get("dom_cov") if isinstance(summary, dict) else None,
            "int_cov": summary.get("int_cov") if isinstance(summary, dict) else None,
            "summary_cov": _safe_json_dumps(summary_cov or {}),
            "summary_not_cov": _safe_json_dumps(summary_not_cov or {}),
            "countries": _safe_json_dumps(country_report.get("countries") or []),
            "agg": _safe_json_dumps(country_report.get("agg") or []),
            "risk_summary": _safe_json_dumps(risk_summary or {}),
            "bargaining_report": _safe_json_dumps(item1_barg or item1a_barg or {}),
        }

    extracted = df.apply(extract_fields, axis=1, result_type="expand")
    out = pd.concat([df[["accession", "cik", "url", "year"]], extracted], axis=1)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    logging.info("Wrote parquet: %s (rows: %s)", out_path, len(out))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export provenance DB into a compact parquet file."
    )
    parser.add_argument("--source", default=SOURCE_DB_DEFAULT, help="Source DB path")
    parser.add_argument(
        "--output", default=TARGET_PARQUET_DEFAULT, help="Output parquet path"
    )
    args = parser.parse_args()

    export_parquet(args.source, args.output)


if __name__ == "__main__":
    main()
