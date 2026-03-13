import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import pandas as pd


SOURCE_DB_DEFAULT = "analyzed_union_data.db"
TARGET_DB_DEFAULT = "union_provenance_risk.db"
SOURCE_TABLE = "analysis_result"
TARGET_TABLE = "provenance_risk"
BATCH_SIZE_DEFAULT = 500


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


def _extract_reports(
    analysis_obj: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not analysis_obj:
        return None, None, None
    country_report = analysis_obj.get("country_report")
    risk_summary = analysis_obj.get("risk_summary")
    bargaining_report = analysis_obj.get("bargaining_report")
    if country_report is None and risk_summary is None and bargaining_report is None:
        return None, None, None
    return (
        json.dumps(country_report) if country_report is not None else None,
        json.dumps(risk_summary) if risk_summary is not None else None,
        json.dumps(bargaining_report) if bargaining_report is not None else None,
    )


def _init_target(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TARGET_TABLE}")
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
            accession TEXT PRIMARY KEY,
            period_of_report TEXT,
            item1_country_report TEXT,
            item1a_country_report TEXT,
            item1_risk_summary TEXT,
            item1a_risk_summary TEXT,
            item1_bargaining_report TEXT,
            item1a_bargaining_report TEXT
        )
        """
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TARGET_TABLE}_period ON {TARGET_TABLE}(period_of_report)"
    )
    conn.commit()


def _copy_metadata_tables(tgt_conn: sqlite3.Connection, source_db: str) -> None:
    """Copies report_data and names tables from source to target DB using pandas."""
    if not Path(source_db).exists():
        return

    logging.info("Copying metadata tables (report_data, names) from source DB...")
    src_conn = sqlite3.connect(source_db, timeout=30.0)

    try:
        for table in ("report_data", "names"):
            try:
                df = pd.read_sql_query(f"SELECT * FROM {table}", src_conn)
            except Exception as e:
                logging.warning("Could not read %s from source DB: %s", table, e)
                continue

            if df.empty:
                logging.warning("%s is empty in source DB; skipping.", table)
                continue

            try:
                df.to_sql(table, tgt_conn, if_exists="replace", index=False)
                logging.info("Copied %s via dataframe (%s rows).", table, len(df))
            except Exception as e:
                logging.error("Failed to write %s to target DB: %s", table, e)
        tgt_conn.commit()
    except Exception as e:
        logging.error("Pandas copy failed: %s", e)
    finally:
        src_conn.close()


def export_reports(
    source_db: str,
    target_db: str,
    batch_size: int = BATCH_SIZE_DEFAULT,
    include_empty: bool = False,
) -> None:
    source_path = Path(source_db)
    if not source_path.exists():
        logging.error("Source DB not found: %s", source_db)
        return

    src = sqlite3.connect(source_db)
    tgt = sqlite3.connect(target_db)
    try:
        _init_target(tgt)
        _copy_metadata_tables(tgt, source_db)
        src_cur = src.cursor()
        tgt_cur = tgt.cursor()

        src_cur.execute(
            f"""
            SELECT accession, item1_analysis, item1a_analysis, period_of_report
            FROM {SOURCE_TABLE}
            """
        )

        total = 0
        inserted = 0
        while True:
            rows = src_cur.fetchmany(batch_size)
            if not rows:
                break

            out_rows = []
            for accession, item1_raw, item1a_raw, period_of_report in rows:
                total += 1
                item1_obj = _safe_json_loads(item1_raw)
                item1a_obj = _safe_json_loads(item1a_raw)

                item1_country, item1_risk, item1_bargaining = _extract_reports(
                    item1_obj
                )
                item1a_country, item1a_risk, item1a_bargaining = _extract_reports(
                    item1a_obj
                )

                if not include_empty and not any(
                    [
                        item1_country,
                        item1a_country,
                        item1_risk,
                        item1a_risk,
                        item1_bargaining,
                        item1a_bargaining,
                    ]
                ):
                    continue

                out_rows.append(
                    (
                        accession,
                        period_of_report,
                        item1_country,
                        item1a_country,
                        item1_risk,
                        item1a_risk,
                        item1_bargaining,
                        item1a_bargaining,
                    )
                )

            if out_rows:
                tgt_cur.executemany(
                    f"""
                    INSERT OR REPLACE INTO {TARGET_TABLE}
                    (accession, period_of_report, item1_country_report, item1a_country_report,
                     item1_risk_summary, item1a_risk_summary,
                     item1_bargaining_report, item1a_bargaining_report)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    out_rows,
                )
                tgt.commit()
                inserted += len(out_rows)

        logging.info("Scanned %s rows, wrote %s rows.", total, inserted)
        logging.info("Output DB: %s (table: %s)", target_db, TARGET_TABLE)
    finally:
        src.close()
        tgt.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export provenance (country_report) and risk_summary into a compact DB."
    )
    parser.add_argument("--source", default=SOURCE_DB_DEFAULT, help="Source DB path")
    parser.add_argument("--target", default=TARGET_DB_DEFAULT, help="Target DB path")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT)
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include rows with no provenance/risk outputs",
    )
    args = parser.parse_args()

    export_reports(
        source_db=args.source,
        target_db=args.target,
        batch_size=args.batch_size,
        include_empty=args.include_empty,
    )


if __name__ == "__main__":
    main()
