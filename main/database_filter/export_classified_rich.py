"""
Rich Excel Export from classified_data.db
Generates multi-sheet Excel with binary flags, trader/hedger status, and aggregate quantitative data.
"""

import sqlite3
import json
import pandas as pd
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Any

# =============================================================================
# CONFIG
# =============================================================================
DB_PATH = "classified_data.db"
OUTPUT_PATH = "classified_export_rich.xlsx"

# =============================================================================
# HELPERS
# =============================================================================

def safe_get(d: Dict, key: str, default: Any = None):
    """Safely get nested dict values."""
    return d.get(key, default)

def get_all_records(db_path: str) -> List[Dict]:
    """Fetch all classified records from database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            c.url,
            c.categories,
            a.attributes,
            r.cik,
            r.year
        FROM category c
        LEFT JOIN attributes a ON c.url = a.url
        LEFT JOIN report_data r ON c.url = r.url
    """)
    
    records = []
    for row in cursor.fetchall():
        url, categories_json, attributes_json, cik, year = row
        
        try:
            categories = json.loads(categories_json) if categories_json else []
        except:
            categories = []
        
        try:
            attributes = json.loads(attributes_json) if attributes_json else {}
        except:
            attributes = {}
        
        records.append({
            'url': url,
            'cik': cik,
            'year': year,
            'categories': categories,
            'attributes': attributes,
        })
    
    conn.close()
    return records

# =============================================================================
# SHEET 1: BINARY FLAGS
# =============================================================================

def build_sheet_binary_flags(records: List[Dict]) -> pd.DataFrame:
    """
    Binary flags sheet: derivative usage (0/1) and empty flag.
    
    Columns:
    - url, cik, year
    - has_derivatives (1 if any category detected, 0 otherwise)
    - is_empty (1 if metadata indicates no matches found)
    - categories_list (comma-separated list)
    """
    rows = []
    
    for rec in records:
        url = rec['url']
        cik = rec['cik']
        year = rec['year']
        categories = rec['categories']
        attributes = rec['attributes']
        
        # Check if firm has derivatives (any category detected)
        has_derivatives = 1 if categories else 0
        
        # Check if empty (no matches in metadata)
        is_empty = 0
        metadata = safe_get(attributes, 'metadata', {})
        if isinstance(metadata, dict):
            # If we have metadata but no categories, likely empty
            if metadata and not categories:
                is_empty = 1
        
        categories_str = ', '.join(sorted(categories)) if categories else ''
        
        rows.append({
            'url': url,
            'cik': cik,
            'year': year,
            'has_derivatives': has_derivatives,
            'is_empty': is_empty,
            'categories': categories_str,
        })
    
    return pd.DataFrame(rows)

# =============================================================================
# SHEET 2: TRADER / HEDGER STATUS
# =============================================================================

def build_sheet_trader_hedger(records: List[Dict]) -> pd.DataFrame:
    """
    Trader/Hedger classification sheet.
    
    Columns:
    - url, cik, year
    - is_hedger
    - is_trader
    - documents_hedge_accounting
    - manages_credit_risk
    - has_aoci_activity
    - is_historical
    """
    rows = []
    
    for rec in records:
        url = rec['url']
        cik = rec['cik']
        year = rec['year']
        attributes = rec['attributes']
        
        rows.append({
            'url': url,
            'cik': cik,
            'year': year,
            'is_hedger': int(safe_get(attributes, 'is_hedger', False)),
            'is_trader': int(safe_get(attributes, 'is_trader', False)),
        })
    
    return pd.DataFrame(rows)

# =============================================================================
# SHEET 3: COMMODITIES (if any)
# =============================================================================

def build_sheet_commodities(records: List[Dict]) -> pd.DataFrame:
    """
    Commodities sheet: detailed commodity mentions by URL/year from metadata.
    Only includes firms with commodity counts > 0.
    """
    rows = []
    
    for rec in records:
        url = rec['url']
        cik = rec['cik']
        year = rec['year']
        attributes = rec['attributes']
        
        # Extract metadata with commodity counts
        metadata = safe_get(attributes, 'metadata', {})
        if not isinstance(metadata, dict):
            continue
        
        commodity_total = metadata.get('commodity_total', 0)
        commodities = metadata.get('commodities', {})
        
        if commodity_total > 0 and isinstance(commodities, dict):
            # Create a row for each commodity mentioned (only if count > 0)
            for commodity_name, count in commodities.items():
                if count > 0:
                    rows.append({
                        'url': url,
                        'cik': cik,
                        'year': year,
                        'commodity': commodity_name,
                        'count': count,
                    })
    
    if not rows:
        return pd.DataFrame(columns=['url', 'cik', 'year', 'commodity', 'count'])
    
    return pd.DataFrame(rows)

# =============================================================================
# SHEET 4: CURRENCIES (if any)
# =============================================================================

def build_sheet_currencies(records: List[Dict]) -> pd.DataFrame:
    """
    Currencies sheet: detailed currency mentions by URL/year from metadata.
    Only includes firms with currency counts > 0.
    """
    rows = []
    
    for rec in records:
        url = rec['url']
        cik = rec['cik']
        year = rec['year']
        attributes = rec['attributes']
        
        # Extract metadata with currency counts
        metadata = safe_get(attributes, 'metadata', {})
        if not isinstance(metadata, dict):
            continue
        
        currency_total = metadata.get('currency_total', 0)
        currencies = metadata.get('currencies', {})
        
        if currency_total > 0 and isinstance(currencies, dict):
            # Create a row for each currency mentioned (only if count > 0)
            for currency_code, count in currencies.items():
                if count > 0:
                    rows.append({
                        'url': url,
                        'cik': cik,
                        'year': year,
                        'currency': currency_code,
                        'count': count,
                    })
    
    if not rows:
        return pd.DataFrame(columns=['url', 'cik', 'year', 'currency', 'count'])
    
    return pd.DataFrame(rows)

# =============================================================================
# SHEET 5+: AGGREGATE QUANTITATIVE DATA
# =============================================================================

def build_sheet_aggregates(records: List[Dict]) -> pd.DataFrame:
    """
    Aggregate notional/FV by category.
    
    Columns:
    - url, cik, year
    - {category}_notional, {category}_fair_value, {category}_value
    - {category}_instrument_count
    """
    rows = []
    
    for rec in records:
        url = rec['url']
        cik = rec['cik']
        year = rec['year']
        attributes = rec['attributes']
        
        row = {
            'url': url,
            'cik': cik,
            'year': year,
        }
        
        # Add aggregated totals by category
        agg_totals = safe_get(attributes, 'aggregated_totals', {})
        if isinstance(agg_totals, dict):
            for cat, values in agg_totals.items():
                if isinstance(values, dict):
                    row[f'{cat}_notional'] = values.get('notional', 0.0)
                    row[f'{cat}_fair_value'] = values.get('fair_value', 0.0)
                    row[f'{cat}_value'] = values.get('value', 0.0)
        
        # Add instrument counts by category
        evidence_details = safe_get(attributes, 'evidence_details', {})
        if isinstance(evidence_details, dict):
            for cat, details_list in evidence_details.items():
                if isinstance(details_list, list):
                    row[f'{cat}_instrument_count'] = len(details_list)
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    # Reorder columns: url, cik, year first, then category columns
    cols = ['url', 'cik', 'year']
    other_cols = [c for c in df.columns if c not in cols]
    df = df[cols + sorted(other_cols)]
    
    return df

# =============================================================================
# SHEET 6: DETAILED INSTRUMENTS
# =============================================================================

def build_sheet_instruments(records: List[Dict]) -> pd.DataFrame:
    """
    Detailed instrument evidence sheet.
    
    Columns:
    - url, cik, year, category, instrument_name
    - amount, inferred_amount, type, currency, year_reported
    - is_explicit, explicit_multiplier, inference_note
    """
    rows = []
    
    for rec in records:
        url = rec['url']
        cik = rec['cik']
        year = rec['year']
        attributes = rec['attributes']
        
        evidence_details = safe_get(attributes, 'evidence_details', {})
        
        if not isinstance(evidence_details, dict):
            continue
        
        for cat, details_list in evidence_details.items():
            if not isinstance(details_list, list):
                continue
            
            for detail in details_list:
                if not isinstance(detail, dict):
                    continue
                
                inst_name = detail.get('name', 'unknown')
                amounts = detail.get('amounts', [])
                
                for amt in amounts:
                    if not isinstance(amt, dict):
                        continue
                    
                    rows.append({
                        'url': url,
                        'cik': cik,
                        'year': year,
                        'category': cat,
                        'instrument_name': inst_name,
                        'amount': amt.get('amount'),
                        'inferred_amount': amt.get('inferred_amount'),
                        'type': amt.get('type'),
                        'currency': amt.get('currency'),
                        'year_reported': amt.get('year'),
                        'is_explicit': int(amt.get('is_explicit', False)),
                        'explicit_multiplier': amt.get('explicit_multiplier'),
                        'is_zero': int(amt.get('is_zero', False)),
                        'inference_note': amt.get('inference_note'),
                    })
    
    if not rows:
        return pd.DataFrame(columns=[
            'url', 'cik', 'year', 'category', 'instrument_name',
            'amount', 'inferred_amount', 'type', 'currency', 'year_reported',
            'is_explicit', 'explicit_multiplier', 'is_zero', 'inference_note'
        ])
    
    return pd.DataFrame(rows)

# =============================================================================
# MAIN
# =============================================================================

def export_to_excel(output_path: str):
    """Build and export all sheets to Excel."""
    print(f"📊 Fetching records from {DB_PATH}...")
    records = get_all_records(DB_PATH)
    print(f"✅ Loaded {len(records)} records")
    
    print("📋 Building sheets...")
    
    sheets = {
        'Binary Flags': build_sheet_binary_flags(records),
        'Trader/Hedger': build_sheet_trader_hedger(records),
        'Commodities': build_sheet_commodities(records),
        'Currencies': build_sheet_currencies(records),
        'Aggregates': build_sheet_aggregates(records),
        'Instruments': build_sheet_instruments(records),
    }
    
    print(f"📝 Writing to {output_path}...")
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, df in sheets.items():
            print(f"  - {sheet_name}: {len(df)} rows")
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"✅ Export complete: {output_path}")

if __name__ == "__main__":
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        exit(1)
    
    export_to_excel(OUTPUT_PATH)
