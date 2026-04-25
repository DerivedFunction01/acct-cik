import sqlite3
from pathlib import Path

import pandas as pd

from merge_review_parquet_with_text import (
    _blocks_to_text,
    merge_review_parquet_with_text,
)


def test_blocks_to_text_handles_json_and_plain_strings():
    assert _blocks_to_text('["A", "B"]') == "A\n\nB"
    assert _blocks_to_text("Plain text") == "Plain text"
    assert _blocks_to_text(None) is None


def test_merge_review_parquet_with_text_joins_db_text(tmp_path: Path):
    source_db = tmp_path / "source.db"
    review_parquet = tmp_path / "review.parquet"

    conn = sqlite3.connect(source_db)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE webpage_result (
                accession TEXT PRIMARY KEY,
                item1 TEXT,
                item1a TEXT,
                period_of_report TEXT,
                home_country TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE report_data (
                cik INTEGER,
                year INTEGER,
                url TEXT,
                accession TEXT,
                original_url TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE names (
                cik INTEGER,
                name TEXT
            )
            """
        )
        cur.execute(
            "INSERT INTO webpage_result VALUES (?, ?, ?, ?, ?)",
            (
                "000000000000000001",
                '["Item 1 line one", "Item 1 line two"]',
                '["Item 1A line one"]',
                "2024",
                "US",
            ),
        )
        cur.execute(
            "INSERT INTO report_data VALUES (?, ?, ?, ?, ?)",
            (1234, 2024, "https://example.com", "000000000000000001", "https://example.com/original"),
        )
        cur.execute("INSERT INTO names VALUES (?, ?)", (1234, "Example Corp"))
        conn.commit()
    finally:
        conn.close()

    pd.DataFrame(
        [
            {"accession": "000000000000000001", "score": 0.91},
        ]
    ).to_parquet(review_parquet, index=False)

    merged = merge_review_parquet_with_text(str(review_parquet), source_db=str(source_db))

    assert len(merged) == 1
    row = merged.iloc[0]
    assert row["accession"] == "000000000000000001"
    assert row["source_item1_text"] == "Item 1 line one\n\nItem 1 line two"
    assert row["source_item1a_text"] == "Item 1A line one"
    assert row["source_full_text"] == "Item 1 line one\n\nItem 1 line two\n\nItem 1A line one"
    assert row["source_home_country"] == "US"
    assert row["source_period_of_report"] == "2024"
    assert row["source_cik"] == 1234
    assert row["source_url"] == "https://example.com"
    assert row["source_name"] == "Example Corp"
