import sqlite3
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for file saving
import matplotlib.pyplot as plt
from collections import Counter, defaultdict
from pathlib import Path
import os
import re
from defs.derivatives_core import ALL_BASE_TYPES, ALL_SUFFIXES
from defs.regex_lib import to_build_alternation

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "classified_data.db"
OUTPUT_DIR = "analysis_output/plots"
TOP_K_PLOT = 20
TOP_K_PRINT = 10

BASE_PATTERN_STR = to_build_alternation(ALL_BASE_TYPES)
VALID_BASE_REGEX = re.compile(rf"\b(?:{BASE_PATTERN_STR})$", re.IGNORECASE)

# Suffixes to strip from instrument names for aggregation.
SUFFIX_PATTERN_STR = to_build_alternation(ALL_SUFFIXES)
SUFFIX_REGEX = re.compile(rf"\s+(?:{SUFFIX_PATTERN_STR})$", re.IGNORECASE)

def normalize_instrument_name(name: str) -> str:
    """Normalizes an instrument name for aggregation."""
    norm = name.lower().strip()

    # 1. Strip common derivative suffixes
    stripped = SUFFIX_REGEX.sub("", norm)

    if stripped != norm:
        # Make sure that there is still at least two words afterwards, and there is still a valid base
        if len(stripped.split()) >= 2 and VALID_BASE_REGEX.search(stripped):
            norm = stripped

    # 2. Handle basic pluralization (e.g., swaps -> swap)
    if norm.endswith('s') and not norm.endswith('ss') and not norm.endswith("futures"):
        norm = norm[:-1]

    return norm

def load_attributes(db_path):
    """Load the attributes JSON strings from the database."""
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return []
    
    print(f"📖 Reading from {db_path}...")
    conn = sqlite3.connect(db_path)
    try:
        # We only need the attributes column
        df = pd.read_sql_query("SELECT attributes FROM attributes", conn)
        return df['attributes'].tolist()
    except Exception as e:
        print(f"❌ Error reading database: {e}")
        return []
    finally:
        conn.close()

def aggregate_counts(attributes_list):
    """Aggregate counts for instruments and metadata categories."""
    # Counters for instruments by category (e.g., IR, FX)
    instrument_counts = defaultdict(Counter)
    # Counters for metadata (e.g., currencies, commodities)
    meta_counts = defaultdict(Counter)

    # Keys expected in the 'metadata' dictionary from prefilter_database.py
    meta_keys = [
        "currencies",
        "commodities",
        "venues",
        "clearing",
        "valuation_models",
        "der_std_hits",
        "gen_hits",
        "ir_hits",
        "fx_hits",
        "cp_hits",
        "cr_hits",
        "eq_hits",
        "crypto_hits",
        "trading_hits",
        "misc_hits",
    ]

    # Map hit count keys to their target instrument category
    hit_keys_to_merge = {
        "gen_hits": "gen",
        "ir_hits": "ir",
        "fx_hits": "fx",
        "cp_hits": "cp",
        "cr_hits": "cr",
        "eq_hits": "eq",
        "crypto_hits": "crypto",
        "trading_hits": "trading",
        "misc_hits": "misc",
    }

    print("🔄 Aggregating data...")
    for attr_json in attributes_list:
        try:
            if not attr_json:
                continue
            attr = json.loads(attr_json)
        except json.JSONDecodeError:
            continue

        # 1. Aggregate Instruments (from classify_users.py logic)
        # Structure: attr['instruments'] = {'ir': ['swap', ...], ...}
        # These are unique keywords found per document.
        if 'instruments' in attr:
            for cat, keywords in attr['instruments'].items():
                normalized_keywords = [normalize_instrument_name(kw) for kw in keywords]
                instrument_counts[cat].update(normalized_keywords)

        # 2. Aggregate Metadata (from prefilter_database.py logic)
        # Structure: attr['metadata'] = {'currencies': {'USD': 5}, ...}
        # These are counts of occurrences within the document.
        if 'metadata' in attr:
            meta = attr['metadata']
            for key in meta_keys:
                if key in meta and isinstance(meta[key], dict):
                    # meta[key] is {term: count}
                    for term, count in meta[key].items():
                        meta_counts[key][term] += count

    # 3. Merge the hit counts into the main instrument counts
    print("📊 Merging instrument hit counts...")
    for hit_key, target_cat in hit_keys_to_merge.items():
        if hit_key in meta_counts:
            # Normalize keys from the hits counter before merging
            normalized_hit_counts = Counter({normalize_instrument_name(term): count for term, count in meta_counts[hit_key].items()})
            instrument_counts[target_cat].update(normalized_hit_counts)
            # Remove the hits from meta_counts to avoid double plotting
            del meta_counts[hit_key]

    return instrument_counts, meta_counts

def plot_and_print_top_k(counter, title, filename_suffix):
    """Generate a bar plot and print top K items."""
    if not counter:
        return

    # 1. Print to Console
    print(f"\n--- Top {TOP_K_PRINT} {title} ---")
    for term, count in counter.most_common(TOP_K_PRINT):
        print(f"  {term}: {count:,}")

    # 2. Generate Plot
    df = pd.DataFrame(counter.most_common(TOP_K_PLOT), columns=['Term', 'Count'])
    df = df.sort_values(by='Count', ascending=True) # Sort for horizontal bar chart
    
    plt.figure(figsize=(12, 8))
    plt.barh(df['Term'], df['Count'], color='#4c72b0')
    plt.xlabel('Frequency')
    plt.title(f'Top {TOP_K_PLOT} {title}')
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    # Save
    output_path = os.path.join(OUTPUT_DIR, f"{filename_suffix}.png")
    plt.savefig(output_path)
    plt.close()
    print(f"  [Plot saved to {output_path}]")

def main():
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    attributes_list = load_attributes(DB_PATH)
    if not attributes_list:
        return

    inst_counts, meta_counts = aggregate_counts(attributes_list)
    
    print("\n" + "="*60)
    print("ANALYSIS RESULTS")
    print("="*60)

    # Plot Instruments by Category
    for cat, counter in inst_counts.items():
        plot_and_print_top_k(counter, f"Instruments ({cat.upper()})", f"instruments_{cat}")
        
    # Plot Metadata Categories
    meta_titles = {
        "currencies": "Currencies",
        "commodities": "Commodities",
        "venues": "Trading Venues",
        "clearing": "Clearing Houses",
        "valuation_models": "Valuation Models",
        "der_std_hits": "Accounting Standards"
    }
    
    for key, counter in meta_counts.items():
        title = meta_titles.get(key, key.replace('_', ' ').title())
        plot_and_print_top_k(counter, title, f"meta_{key}")

    print("\n✅ Analysis complete.")

if __name__ == "__main__":
    main()
