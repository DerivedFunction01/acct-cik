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
        "likely_union_pct": None,
        "weighted_union_pct": None,
        "total_employees": None,
        "pct_north_america": None,
        "pct_europe": None,
        "pct_asia": None,
        "pct_latam": None,
        "pct_mea": None,
        "pct_intl": None,
        "risk_count_total": 0,
        "risk_count_union": 0,
        "unions_mentioned": [],
        "countries_mentioned": []
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
                    res["likely_union_pct"] = summary.get("likely_percentage")
                    res["weighted_union_pct"] = summary.get("weighted_average_percentage")
                    
                    # Extract Region Percentages
                    regions = summary.get("region_percentages", {})
                    if regions:
                        res["pct_north_america"] = get_region_val(regions, [Region.NORTH_AMERICA.value, "US/Canada"])
                        res["pct_europe"] = get_region_val(regions, [Region.EUROPE.value])
                        res["pct_asia"] = get_region_val(regions, [Region.ASIA_PACIFIC.value, "Asia"])
                        res["pct_latam"] = get_region_val(regions, [Region.LATIN_AMERICA.value])
                        res["pct_mea"] = get_region_val(regions, [Region.MIDDLE_EAST_AFRICA.value, "Africa"])
                        res["pct_intl"] = get_region_val(regions, [Region.INTERNATIONAL.value])

                # Extract Specific Entities (Unions & Countries)
                items = data.get("items", [])
                unions = set()
                countries = set()
                
                for item in items:
                    geo = item.get("geographic_context", {})
                    
                    # Extract specific union names if identified
                    if geo.get("union_names_mentioned"):
                        for u in geo["union_names_mentioned"]:
                            unions.add(u)
                    elif geo.get("union_name_indicator"):
                        unions.add(geo["union_name_indicator"])
                    
                    # Extract countries
                    if geo.get("countries"):
                        for c in geo["countries"]:
                            countries.add(c["code"])
                
                res["unions_mentioned"] = sorted(list(unions))
                res["countries_mentioned"] = sorted(list(countries))

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
                res["risk_count_total"] = len(items)
                # Count risks specifically flagged as UNION_RISK
                res["risk_count_union"] = sum(1 for i in items if i.get("type") == RiskType.UNION_RISK.value)
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
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
            accession TEXT PRIMARY KEY,
            cik INTEGER,
            year INTEGER,
            period_of_report TEXT,
            has_item1 BOOLEAN,
            has_item1a BOOLEAN,
            likely_union_pct REAL,
            weighted_union_pct REAL,
            pct_north_america REAL,
            pct_europe REAL,
            pct_asia REAL,
            pct_latam REAL,
            pct_mea REAL,
            pct_intl REAL,
            risk_count_total INTEGER,
            risk_count_union INTEGER,
            unions_mentioned TEXT,
            countries_mentioned TEXT
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
            res["likely_union_pct"],
            res["weighted_union_pct"],
            res["pct_north_america"],
            res["pct_europe"],
            res["pct_asia"],
            res["pct_latam"],
            res["pct_mea"],
            res["pct_intl"],
            res["risk_count_total"],
            res["risk_count_union"],
            ", ".join(res["unions_mentioned"]),
            ", ".join(res["countries_mentioned"])
        ))
        
        if len(batch) >= 1000:
            c.executemany(f"""
                INSERT OR REPLACE INTO {TARGET_TABLE} VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, batch)
            count = len(batch)
            batch = []
            print(f"Processed {count} rows...", end="\r")
            
    if batch:
        c.executemany(f"""
            INSERT OR REPLACE INTO {TARGET_TABLE} VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, batch)
        count = len(batch)
        
    conn.commit()
    conn.close()
    logging.info(f"\nAggregation complete. {count} rows inserted into '{TARGET_TABLE}'.")

if __name__ == "__main__":
    main()
