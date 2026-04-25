import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
from tqdm import tqdm


SOURCE_DB_DEFAULT = "filtered_union_data.db"
SOURCE_TABLE_DEFAULT = "webpage_result"
CHUNK_SIZE = 500


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    )
    return cur.fetchone() is not None


def _normalize_accession(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int,)):
        return str(value).zfill(18)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value)).zfill(18)
        return str(value)
    return str(value).strip() or None


def _blocks_to_text(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if part is not None and str(part).strip()]
        return "\n\n".join(parts) if parts else None
    if not isinstance(value, str):
        text = str(value).strip()
        return text or None

    stripped = value.strip()
    if not stripped:
        return None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped

    if isinstance(parsed, list):
        parts = [str(part).strip() for part in parsed if part is not None and str(part).strip()]
        return "\n\n".join(parts) if parts else None
    if isinstance(parsed, str):
        parsed = parsed.strip()
        return parsed or None
    return stripped


def _normalize_period_of_report(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _chunked(values: List[str], chunk_size: int) -> Iterable[List[str]]:
    for idx in range(0, len(values), chunk_size):
        yield values[idx : idx + chunk_size]


def load_source_text_frame(
    source_db: str,
    accessions: List[str],
    source_table: str = SOURCE_TABLE_DEFAULT,
) -> pd.DataFrame:
    if not accessions:
        return pd.DataFrame(
            columns=[
                "accession",
                "source_item1_text",
                "source_item1a_text",
                "source_full_text",
                "source_period_of_report",
                "source_home_country",
                "source_cik",
                "source_url",
                "source_name",
            ]
        )

    source_path = Path(source_db)
    if not source_path.exists():
        raise FileNotFoundError(f"Source DB not found: {source_db}")

    conn = sqlite3.connect(source_db)
    try:
        has_report_data = _table_exists(conn, "report_data")
        has_names = _table_exists(conn, "names")
        if not _table_exists(conn, source_table):
            raise ValueError(f"Source table not found: {source_table}")

        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({source_table})")
        source_columns = {row[1] for row in cur.fetchall()}
        cur.execute("PRAGMA table_info(report_data)")
        report_columns = {row[1] for row in cur.fetchall()} if has_report_data else set()
        cur.execute("PRAGMA table_info(names)")
        names_columns = {row[1] for row in cur.fetchall()} if has_names else set()

        all_rows: List[Dict[str, Any]] = []
        unique_accessions = list(dict.fromkeys(a for a in accessions if a))
        for chunk in tqdm(_chunked(unique_accessions, CHUNK_SIZE), desc="Loading text"):
            placeholders = ",".join("?" for _ in chunk)
            select_parts = ["w.accession"]
            for column in ("item1", "item1a", "home_country"):
                if column in source_columns:
                    select_parts.append(f"w.{column}")
                else:
                    select_parts.append(f"NULL AS {column}")

            if has_report_data:
                select_parts.append(
                    "r.year AS source_period_of_report" if "year" in report_columns else "NULL AS source_period_of_report"
                )
                select_parts.append("r.cik AS cik" if "cik" in report_columns else "NULL AS cik")
                select_parts.append("r.url AS url" if "url" in report_columns else "NULL AS url")
            else:
                select_parts.extend(
                    [
                        "NULL AS source_period_of_report",
                        "NULL AS cik",
                        "NULL AS url",
                    ]
                )

            if has_names and has_report_data and "cik" in report_columns and "name" in names_columns:
                select_parts.append("n.name AS source_name")
            else:
                select_parts.append("NULL AS source_name")

            query = [f"SELECT {', '.join(select_parts)} FROM {source_table} w"]
            if has_report_data:
                query.append(" LEFT JOIN report_data r ON w.accession = r.accession")
            if has_names and has_report_data and "cik" in report_columns and "name" in names_columns:
                query.append(" LEFT JOIN names n ON r.cik = n.cik")
            query.append(f" WHERE w.accession IN ({placeholders})")
            sql = "".join(query)

            cur.execute(sql, chunk)
            rows = cur.fetchall()
            for row in rows:
                accession, item1, item1a, home_country, source_period_of_report, cik, url, source_name = row
                item1_text = _blocks_to_text(item1) or ""
                item1a_text = _blocks_to_text(item1a) or ""
                all_rows.append(
                    {
                        "accession": _normalize_accession(accession),
                        "source_item1_text": "\n\n".join(item1_text),
                        "source_item1a_text": "\n\n".join(item1a_text),
                    }
                )
        text_df = pd.DataFrame(all_rows)
        if not text_df.empty:
            text_df = text_df.drop_duplicates(subset=["accession"], keep="first")
        return text_df
    finally:
        conn.close()


def merge_review_parquet_with_text(
    review_parquet: str,
    source_db: str = SOURCE_DB_DEFAULT,
    source_table: str = SOURCE_TABLE_DEFAULT,
) -> pd.DataFrame:
    review_path = Path(review_parquet)
    if not review_path.exists():
        raise FileNotFoundError(f"Review parquet not found: {review_parquet}")

    review_df = pd.read_parquet(review_path)
    if "accession" not in review_df.columns:
        raise ValueError("Review parquet must contain an 'accession' column")

    merged_review = review_df.copy()
    merged_review["accession"] = merged_review["accession"].map(_normalize_accession)

    accession_values = [
        value for value in merged_review["accession"].tolist() if value is not None
    ]
    source_df = load_source_text_frame(source_db, accession_values, source_table=source_table)
    if source_df.empty:
        return merged_review

    merged = merged_review.merge(source_df, on="accession", how="left", validate="m:1")
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge a review parquet sample with the underlying filing text from the database."
    )
    parser.add_argument("--review-parquet", required=True, help="Path to the sampled review parquet")
    parser.add_argument(
        "--source-db",
        default=SOURCE_DB_DEFAULT,
        help="SQLite DB containing webpage_result and optional metadata tables",
    )
    parser.add_argument(
        "--source-table",
        default=SOURCE_TABLE_DEFAULT,
        help="Table containing the filing text blocks",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output parquet path. Defaults to <review stem>_with_text.parquet",
    )
    args = parser.parse_args()

    merged = merge_review_parquet_with_text(
        args.review_parquet,
        source_db=args.source_db,
        source_table=args.source_table,
    )

    output_path = (
        Path(args.output)
        if args.output
        else Path(args.review_parquet).with_name(
            f"{Path(args.review_parquet).stem}_with_text.parquet"
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(output_path, index=False)
    logging.info("Wrote merged parquet: %s (rows: %s)", output_path, len(merged))


if __name__ == "__main__":
    main()
