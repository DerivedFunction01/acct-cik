import sqlite3
import pandas as pd
import sys
import re
from pathlib import Path

# Ensure we can import from local modules
sys.path.append(str(Path(__file__).parent))

from defs.text_cleaner import MinimalTextCleaner

DB_PATH = "web_data.db"


def find_numeric_names():
    if not Path(DB_PATH).exists():
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        # Try names table first
        try:
            df = pd.read_sql("SELECT DISTINCT name, cik FROM names", conn)
        except Exception:
            # Fallback to report_data
            df = pd.read_sql(
                "SELECT DISTINCT name, cik FROM report_data WHERE name IS NOT NULL",
                conn,
            )
    except Exception as e:
        print(f"Error querying database: {e}")
        conn.close()
        return
    finally:
        conn.close()

    if df.empty:
        print("No names found.")
        return

    cleaner = MinimalTextCleaner()

    hits = []

    print(f"Scanning {len(df)} names...")

    for _, row in df.iterrows():
        name = row["name"]
        if not isinstance(name, str):
            continue

        # Clean the name slightly to match how it might appear in text (remove Inc, Corp, etc)
        # This helps isolate the "core" name which might be "Capital One"
        core_name = cleaner.normalize_company_name(name)

        # Check if the core name contains number words
        # We use the regex from the cleaner to be exact about what it catches
        matches = list(cleaner.number_phrase_pattern.finditer(core_name))

        # Also check for "Union" to identify potential conflicts
        union_match = re.search(r"\bUnions?\b", core_name, re.IGNORECASE)

        if matches or union_match:
            matched_phrases = [m.group(0) for m in matches]
            if union_match:
                matched_phrases.append(union_match.group(0))

            hits.append(
                {
                    "cik": row["cik"],
                    "name": name,
                    "core_name": core_name,
                    "matches": ", ".join(matched_phrases),
                }
            )

    if not hits:
        print("No numeric names found.")
    else:
        hits_df = pd.DataFrame(hits)
        print(f"Found {len(hits_df)} firms.")
        print(hits_df.head(20).to_string(index=False))
        hits_df.to_csv("numeric_firm_names.csv", index=False)
        print(f"\nSaved to numeric_firm_names.csv")


if __name__ == "__main__":
    find_numeric_names()
