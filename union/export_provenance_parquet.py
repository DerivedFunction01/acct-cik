import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from defs.region_regex import (
    DOMESTIC_SET,
    INT_SET,
    REGION_NAME_MAP,
    _CODE_TO_REGION,
)

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


def _domestic_explicit(report: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    dom_code = report.get("domestic_country_code")
    if not dom_code:
        return None, None

    for entry in report.get("countries") or []:
        if entry.get("country_code") == dom_code:
            reported = entry.get("reported_totals") or {}
            cov = reported.get("cov")
            pct = reported.get("pct")
            return cov, pct
    return None, None

def _int_reported_totals(report: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    dom_code = report.get("domestic_country_code")
    countries = report.get("countries") or []
    
    total_cov = 0.0
    total_tot = 0.0
    total_not_cov = 0.0
    has_cov = False
    has_tot = False
    has_not_cov = False
    
    for entry in countries:
        if entry.get("country_code") == dom_code:
            continue
        reported = entry.get("reported_totals") or {}
        cov = reported.get("cov")
        tot = reported.get("tot")
        not_cov = reported.get("not_cov")
        
        if cov is not None:
            total_cov += float(cov)
            has_cov = True
        if tot is not None:
            total_tot += float(tot)
            has_tot = True
        if not_cov is not None:
            total_not_cov += float(not_cov)
            has_not_cov = True
            
    int_cov = total_cov if has_cov else None
    int_tot = total_tot if has_tot else None
    int_not_cov = total_not_cov if has_not_cov else None
    
    return int_cov, int_tot, int_not_cov

def _agg_is_purely_international(
    agg_entry: Dict[str, Any], domestic_country_code: Optional[str]
) -> bool:
    if not domestic_country_code:
        return False

    children = agg_entry.get("children") or {}
    child_codes = list(children.keys())

    if not child_codes:
        agg_key = agg_entry.get("aggregate_key")
        return bool(agg_key in INT_SET)

    dom_region_name = _CODE_TO_REGION.get(domestic_country_code)
    dom_region_code = REGION_NAME_MAP.get(dom_region_name) if dom_region_name else None

    for code in child_codes:
        if code == domestic_country_code:
            return False
        if dom_region_code and code == dom_region_code:
            return False
        if dom_region_name and code == dom_region_name:
            return False
        if code in DOMESTIC_SET:
            return False
    return True


def _agg_international_totals(
    report: Dict[str, Any],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    dom_code = report.get("domestic_country_code")
    agg_entries = report.get("agg") or []

    total_cov = 0.0
    total_tot = 0.0
    total_not_cov = 0.0
    has_cov = False
    has_tot = False
    has_not_cov = False

    for agg in agg_entries:
        if not _agg_is_purely_international(agg, dom_code):
            continue
        cov = agg.get("cov")
        tot = agg.get("tot")
        not_cov = agg.get("not_cov")

        if cov is not None:
            total_cov += float(cov)
            has_cov = True
        if tot is not None:
            total_tot += float(tot)
            has_tot = True
        if not_cov is not None:
            total_not_cov += float(not_cov)
            has_not_cov = True

    return (
        total_cov if has_cov else None,
        total_tot if has_tot else None,
        total_not_cov if has_not_cov else None,
    )

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


def _flatten_summary_dict(d: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(d, dict):
        return []
    flat = set()
    for v in d.values():
        if isinstance(v, list):
            flat.update(v)
    return sorted(list(flat))

def generate_stratified_sample(df: pd.DataFrame, target_size: int, explicit_csv: Optional[str] = None) -> pd.DataFrame:
    sampled_accessions = set()
    
    if explicit_csv and Path(explicit_csv).exists():
        explicit_df = pd.read_csv(explicit_csv)
        if "accession" in explicit_df.columns:
            explicit_accs = set(explicit_df["accession"].astype(str))
            sampled_accessions.update(explicit_accs)
            logging.info("Added %d explicit accessions from %s", len(explicit_accs), explicit_csv)

    if target_size <= 0:
        return df[df["accession"].astype(str).isin(sampled_accessions)].copy()

    def print_and_sample(series_col, num_per_group):
        counts = series_col.value_counts(dropna=False)
        logging.info("--- Category: %s ---", series_col.name)
        for val, count in counts.items():
            logging.info("  %s: %d candidates", val, count)
            
        # Sample
        for val in counts.index:
            if pd.isna(val):
                mask = series_col.isna()
            else:
                mask = series_col == val
            
            pool = df[mask & (~df["accession"].isin(sampled_accessions))]
            if len(pool) > 0:
                k = min(num_per_group, len(pool))
                chosen = pool.sample(n=k, random_state=42)
                sampled_accessions.update(chosen["accession"])

    # Calculate rough distribution to hit the target target_size (~8 dimensions = ~40 buckets)
    n_per_stratum = max(1, target_size // 40)

    df_sample = df.copy()
    
    # Setup stratified buckets for numeric and keyword variables
    df_sample["dom_pct_bucket"] = pd.cut(
        df_sample["dom_pct"].fillna(-1), 
        bins=[-2, -0.1, 0.1, 25, 50, 75, 100], 
        labels=["Null", "0", "1-25", "26-50", "51-75", "76-100"]
    )
    
    df_sample["tot_count_bucket"] = pd.cut(
        df_sample["tot_count"].fillna(-1), 
        bins=[-2, -0.1, 0.1, 1000, 10000, 100000, float("inf")], 
        labels=["Null", "0", "1-1K", "1K-10K", "10K-100K", ">100K"]
    )

    df_sample["int_count_bucket"] = pd.cut(
        df_sample["int_count"].fillna(-1), 
        bins=[-2, -0.1, 0.1, 1000, 10000, 100000, float("inf")], 
        labels=["Null", "0", "1-1K", "1K-10K", "10K-100K", ">100K"]
    )

    df_sample["kw_bucket"] = pd.cut(
        df_sample["global_keyword_count"].fillna(-1), 
        bins=[-2, -0.1, 0.1, 5, 20, float("inf")], 
        labels=["Null", "0", "1-5", "6-20", ">20"]
    )
    
    # Domestic code (Top 5 + Rest)
    top_codes = df_sample["domestic_country_code"].value_counts().nlargest(5).index
    df_sample["dom_code_bucket"] = df_sample["domestic_country_code"].where(
        df_sample["domestic_country_code"].isin(top_codes), "OTHER"
    )

    print_and_sample(df_sample["year"], n_per_stratum)
    print_and_sample(df_sample["dom_cov"], n_per_stratum)
    print_and_sample(df_sample["int_cov"], n_per_stratum)
    print_and_sample(df_sample["dom_pct_bucket"], n_per_stratum)
    print_and_sample(df_sample["tot_count_bucket"], n_per_stratum)
    print_and_sample(df_sample["int_count_bucket"], n_per_stratum)
    print_and_sample(df_sample["dom_code_bucket"], n_per_stratum)
    print_and_sample(df_sample["kw_bucket"], n_per_stratum)

    # Fill any remaining samples with random selection to hit target size exactly
    remaining = target_size - len(sampled_accessions)
    if remaining > 0:
        pool = df[~df["accession"].isin(sampled_accessions)]
        if len(pool) > 0:
            chosen = pool.sample(n=min(remaining, len(pool)), random_state=42)
            sampled_accessions.update(chosen["accession"])
            
    logging.info("Total unique sampled accessions: %d", len(sampled_accessions))
    return df[df["accession"].astype(str).isin(sampled_accessions)].copy()


def export_parquet(
    source_db: str, 
    output_path: str, 
    sample_size: int = 0, 
    explicit_csv: Optional[str] = None
) -> None:
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

        summary_cov_flat = _flatten_summary_dict(summary_cov)
        summary_not_cov_flat = _flatten_summary_dict(summary_not_cov)

        item1_risk = _safe_json_loads(row.get("item1_risk_summary"))
        item1a_risk = _safe_json_loads(row.get("item1a_risk_summary"))
        item1_barg = _safe_json_loads(row.get("item1_bargaining_report"))
        item1a_barg = _safe_json_loads(row.get("item1a_bargaining_report"))

        risk_summary = {}
        if item1_risk or item1a_risk:
            risk_summary = _merge_counts(item1_risk or {}, item1a_risk or {})
            if "n" in risk_summary:
                risk_summary["n"] = (
                    (item1_risk or {}).get("n", 0)
                    + (item1a_risk or {}).get("n", 0)
                )

        dom_domestic_count, dom_domestic_pct = _domestic_explicit(country_report)
        
        dom_pulled_from_risk = False
        # Note: 'not dom_domestic_count' is True if count is 0.0 or None
        if dom_domestic_count in (None, 0, 0.0) and risk_summary:
            risk_cov = risk_summary.get("cov_t", {}).get("cov")
            risk_pct = risk_summary.get("cov_t", {}).get("pct")
            if risk_cov is not None:
                dom_domestic_count = float(risk_cov)
                dom_pulled_from_risk = True
            if risk_pct is not None and float(risk_pct) != 100.0:
                dom_domestic_pct = float(risk_pct)
                dom_pulled_from_risk = True

        if summary.get("dom_cov") is False and not dom_pulled_from_risk:
            dom_domestic_count = 0.0
            dom_domestic_pct = 0.0

        int_cov, int_tot, int_not_cov = _int_reported_totals(country_report)

        agg_int_cov, agg_int_tot, agg_int_not_cov = _agg_international_totals(
            country_report
        )
        if agg_int_cov is not None:
            int_cov = (int_cov or 0.0) + agg_int_cov
        if agg_int_tot is not None:
            int_tot = (int_tot or 0.0) + agg_int_tot
        if agg_int_not_cov is not None:
            int_not_cov = (int_not_cov or 0.0) + agg_int_not_cov

        summary_int_false = summary.get("int_cov") is False
        if summary_int_false and agg_int_cov is None:
            int_cov = 0.0

        if int_cov is not None and int_cov > 0 and int_tot == 0:
            int_tot = None
        if (not summary_int_false) and int_cov == 0 and int_tot == 0 and (
            int_not_cov in (0, None)
        ):
            int_cov = None
            int_tot = None
            int_not_cov = None

        # Calculate total explicit coverage (dom + int + non-intl agg),
        # only when both dom and int are known (int can be 0.0).
        total_cov = None
        if dom_domestic_count is not None and int_cov is not None:
            total_cov_val = float(dom_domestic_count) + float(int_cov)
            for a in (country_report.get("agg") or []):
                if _agg_is_purely_international(
                    a, country_report.get("domestic_country_code")
                ):
                    continue
                acov = a.get("cov")
                if acov is not None:
                    total_cov_val += float(acov)
            total_cov = total_cov_val

        return {
            "domestic_country_code": country_report.get("domestic_country_code"),
            "dom_cov": summary.get("dom_cov") if isinstance(summary, dict) else None,
            "int_cov": summary.get("int_cov") if isinstance(summary, dict) else None,
            "summary_cov": _safe_json_dumps(summary_cov_flat),
            "summary_not_cov": _safe_json_dumps(summary_not_cov_flat),
            "countries": _safe_json_dumps(country_report.get("countries") or []),
            "agg": _safe_json_dumps(country_report.get("agg") or []),
            "global_keywords": _safe_json_dumps(
                country_report.get("global_keywords") or []
            ),
            "global_keyword_count": country_report.get("global_keyword_count"),
            "risk_summary": _safe_json_dumps(risk_summary or {}),
            "bargaining_report": _safe_json_dumps(item1_barg or item1a_barg or {}),
            "dom_count": dom_domestic_count,
            "dom_pct": dom_domestic_pct,
            "int_count": int_cov,
            "tot_count": total_cov,
        }

    extracted = df.apply(extract_fields, axis=1, result_type="expand")
    out = pd.concat([df[["accession", "cik", "url", "year"]], extracted], axis=1)

    if sample_size > 0 or explicit_csv:
        out = generate_stratified_sample(out, target_size=sample_size, explicit_csv=explicit_csv)

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
    parser.add_argument(
        "--sample-size", type=int, default=0, help="If > 0, randomly sample this many rows across stratified buckets"
    )
    parser.add_argument(
        "--explicit-sample-csv", type=str, default=None, help="Path to CSV containing an 'accession' column to include in sample"
    )
    args = parser.parse_args()

    export_parquet(args.source, args.output, args.sample_size, args.explicit_sample_csv)


if __name__ == "__main__":
    main()
