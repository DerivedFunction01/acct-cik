import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from defs.region_regex import Region
from defs.output_enums import RiskType

# Configuration
SOURCE_DB = "analyzed_union_data.db"
TARGET_TABLE = "union_summary"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_region_val(region_dict: Dict[str, float], keys: List[str]) -> Optional[float]:
    """Helper to safely get region percentage using multiple possible keys."""
    for k in keys:
        if k in region_dict:
            return region_dict[k]
    return None

def process_row(row):
    """
    Parses the JSON analysis results and extracts flat metrics.
    """
    accession, item1_json, item1a_json, period, cik, year = row
    
    # Initialize result dictionary with default None/False values
    res = {
        "accession": accession,
        "cik": cik,
        "year": year,
        "period_of_report": period,
        "has_item1": False,
        "has_item1a": False,
        "union_rate": None,
        "secondary_rate": None,
        "pct_north_america": None,
        "pct_europe": None,
        "pct_asia": None,
        "pct_latam": None,
        "pct_mea": None,
        "pct_intl": None,
    }

    # --- Process Item 1 (Business Description) ---
    if item1_json:
        try:
            data = json.loads(item1_json)
            if data:
                res["has_item1"] = True
                
                # Extract Summary Metrics
                summary = data.get("summary", {})
                if summary:
                    res["union_rate"] = summary.get("likely_percentage")
                    res["secondary_rate"] = summary.get("secondary_percentage")
                    
                    # Extract Region Data
                    regions_pct = summary.get("derived_regional_coverage", {})

                    def extract_region_metrics(keys, suffix):
                        res[f"pct_{suffix}"] = get_region_val(regions_pct, keys)

                    extract_region_metrics([Region.NORTH_AMERICA.value, "US/Canada"], "north_america")
                    extract_region_metrics([Region.EUROPE.value], "europe")
                    extract_region_metrics([Region.ASIA_PACIFIC.value, "Asia"], "asia")
                    extract_region_metrics([Region.LATIN_AMERICA.value], "latam")
                    extract_region_metrics([Region.MIDDLE_EAST_AFRICA.value, "Africa"], "mea")
                    extract_region_metrics([Region.INTERNATIONAL.value], "intl")

        except json.JSONDecodeError:
            pass

    # --- Process Item 1A (Risk Factors) ---
    if item1a_json:
        try:
            data = json.loads(item1a_json)
            # Item 1A analysis returns {"items": [...], "summary": {}}
            items = data.get("items", [])
            if items:
                res["has_item1a"] = True
        except json.JSONDecodeError:
            pass
            
    return res

def main():
    if not Path(SOURCE_DB).exists():
        logging.error(f"Source database {SOURCE_DB} not found. Run analyze_paragraphs.py first.")
        return

    conn = sqlite3.connect(SOURCE_DB)
    c = conn.cursor()
    
    # Create the summary table
    logging.info(f"Creating table {TARGET_TABLE}...")
    c.execute(f"DROP TABLE IF EXISTS {TARGET_TABLE}")
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
            accession TEXT PRIMARY KEY,
            cik INTEGER,
            year INTEGER,
            period_of_report TEXT,
            has_item1 BOOLEAN,
            has_item1a BOOLEAN,
            union_rate REAL,
            secondary_rate REAL,
            pct_north_america REAL,
            pct_europe REAL,
            pct_asia REAL,
            pct_latam REAL,
            pct_mea REAL,
            pct_intl REAL
        )
    """)
    
    # Fetch raw analysis results
    logging.info("Reading analysis results...")
    try:
        c.execute("""
            SELECT a.accession, a.item1_analysis, a.item1a_analysis, a.period_of_report, r.cik, r.year 
            FROM analysis_result a
            LEFT JOIN report_data r ON a.accession = r.accession
        """)
    except sqlite3.OperationalError:
        logging.error("Could not read from 'analysis_result' table. Ensure analyze_paragraphs.py has run.")
        return

    rows = c.fetchall()
    logging.info(f"Processing {len(rows)} rows...")
    
    batch = []
    count = 0
    
    for row in rows:
        res = process_row(row)
        
        batch.append((
            res["accession"],
            res["cik"],
            res["year"],
            res["period_of_report"],
            res["has_item1"],
            res["has_item1a"],
            res["union_rate"],
            res["secondary_rate"],
            res["pct_north_america"],
            res["pct_europe"],
            res["pct_asia"],
            res["pct_latam"],
            res["pct_mea"],
            res["pct_intl"]
        ))
        
        if len(batch) >= 1000:
            c.executemany(f"""
                INSERT OR REPLACE INTO {TARGET_TABLE} VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, batch)
            count = len(batch)
            batch = []
            print(f"Processed {count} rows...", end="\r")
            
    if batch:
        c.executemany(f"""
            INSERT OR REPLACE INTO {TARGET_TABLE} VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, batch)
        count = len(batch)
        
    conn.commit()
    conn.close()
    logging.info(f"\nAggregation complete. {count} rows inserted into '{TARGET_TABLE}'.")

if __name__ == "__main__":
    main()
