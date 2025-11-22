# populate_categories.py
# Run this once per database, in order: prepared → hedge → current → active

import sqlite3
import json
import re
from pathlib import Path
from derivative_regex import (
    build_ir_regex,
    build_fx_regex,
    build_cp_regex,
    build_eq_regex,
    build_strict_gen_regex,
    build_soft_gen_regex,
)

# Build regexes (exactly the same as your pipeline)
IR_REGEX = build_ir_regex()
FX_REGEX = build_fx_regex()
CP_REGEX = build_cp_regex()
EQ_REGEX = build_eq_regex()
GEN_STRICT = build_strict_gen_regex()
GEN_SOFT = build_soft_gen_regex()

REGEX_TO_CAT = [
    (IR_REGEX, "ir"),
    (FX_REGEX, "fx"),
    (CP_REGEX, "cp"),
    (EQ_REGEX, "eq"),
    (GEN_STRICT, "gen"),
    (GEN_SOFT, "gen"),  # soft generic also counts as generic
]


def populate_category_table(db_path: str, stage_name: str):
    db = Path(db_path)
    if not db.exists():
        print(f"Skipping {db.name} — not found")
        return

    print(f"Populating category_result in {db.name} (stage = {stage_name}) ...")
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    # Create table + indexes if missing
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS category_result (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            sentence TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('ir','fx','cp','eq','gen', 'other')),
            source TEXT NOT NULL DEFAULT 'regex',
            stage TEXT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(url) REFERENCES webpage_result(url) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_category_url   ON category_result(url);
        CREATE INDEX IF NOT EXISTS idx_category_cat   ON category_result(category);
        CREATE INDEX IF NOT EXISTS idx_category_stage ON category_result(stage);
    """
    )
    conn.commit()

    cur.execute("SELECT url, matches FROM webpage_result WHERE matches IS NOT NULL")
    rows = cur.fetchall()

    inserts = []
    total_sentences = 0

    for url, matches_json in rows:
        try:
            sentences = json.loads(matches_json)
            if not isinstance(sentences, list):
                continue
        except json.JSONDecodeError:
            continue

        for sent in sentences:
            if not sent.strip():
                continue
            found = False
            for regex, cat in REGEX_TO_CAT:
                if regex.search(sent):
                    inserts.append((url, sent.strip(), cat, "regex", stage_name))
                    found = True
                    break
            # Very rare fallback — sentence survived but matched nothing specific
            if not found:
                inserts.append((url, sent.strip(), "other", "regex", stage_name))
            total_sentences += 1

        if len(inserts) >= 10_000:  # batch commit
            cur.executemany(
                """
                INSERT INTO category_result (url, sentence, category, source, stage)
                VALUES (?, ?, ?, ?, ?)
            """,
                inserts,
            )
            conn.commit()
            inserts.clear()
            print(f"   → {total_sentences:,} sentences processed so far...")

    # final insert
    if inserts:
        cur.executemany(
            """
            INSERT INTO category_result (url, sentence, category, source, stage)
            VALUES (?, ?, ?, ?, ?)
        """,
            inserts,
        )
        conn.commit()

    print(
        f"Done {db.name} → {total_sentences:,} sentences → {len(inserts)+cur.rowcount:,} category rows\n"
    )

    conn.close()


# ——————————————————————————————————
# Run on all relevant databases
# ——————————————————————————————————
if __name__ == "__main__":
    populate_category_table("prepared_data.db", "prepared")
    populate_category_table("hedge_data.db", "hedge")
    populate_category_table("current_data.db", "current")
    populate_category_table("active_data.db", "active")
