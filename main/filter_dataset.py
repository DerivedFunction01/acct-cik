# %%
import pandas as pd
import re
from tqdm import tqdm
import random
from typing import List, Set

# =============================================================================
# CONFIGURATION
# =============================================================================
INPUT_FILE = "Finance-500K.parquet"
OUTPUT_FILE = "finance_instruct_derivatives_subset.parquet"

# How many non-derivative samples to include.
# Adjust these numbers based on your desired final dataset size.
OTHER_FINANCE_SAMPLE_SIZE = 75000

# The columns in the dataset that contain the text to be searched.
# Based on the dataset card, these are the most likely columns.
TEXT_COLUMNS = ["user", "assistant"]

# =============================================================================
# REGEX AND KEYWORD DEFINITIONS (Adapted from webpage.py)
# =============================================================================

def build_alternation(items: List[str]) -> str:
    """Build optimized alternation pattern from list of items."""
    return f'(?:{"|".join(items)})' if items else ""

def build_smart_regex(core_terms: List[str], context_terms: List[str], specific_phrases: List[str]) -> str:
    """Builds a targeted regex by combining core terms, context, and specific phrases."""
    pattern1 = f"{build_alternation(core_terms)}[- ]{build_alternation(context_terms)}" if core_terms and context_terms else ""
    pattern2 = build_alternation(specific_phrases)
    return build_alternation([p for p in [pattern1, pattern2] if p])

# --- Derivative Keywords ---
ALL_BASE_TYPES = [
    "swaps?", "forwards?", "futures?", "options?", "caps?", "floors?", "collars?",
    "derivatives?", "swaptions?", "locks?", "hedges?", "hedging",
]
ALL_SUFFIXES = ["agreements?", "contracts?", "instruments?", "arrangements?", "assets?", "liabilit(?:y|ies)", "commitments?", "positions?", "strateg(?:ies|y)"]

IR_CORE = ["interest[- ]rate", "Eurodollar", "SOFR", "SONIA", "LIBOR", "treasury[- ]rate", "fixed[- ]rate", "floating[- ]rate"]
IR_SPECIFIC = ["zero[- ]coupon swap", "FRA", "treasury lock", "interest rate cap", "interest rate floor"]

FX_CORE = ["foreign[- ]exchange", "foreign[- ]currency", "currency", "cross[- ]currency", "FX", "forex"]
FX_SPECIFIC = ["NDF", "non[- ]deliverable forwards?", "deliverable forwards?", "forward foreign exchange", "foreign currency contracts?"]

CP_CORE = ["commodity", "crude oil", "natural gas", "aluminum", "coal", "fuel", "gasoline", "steel", "sugar", "corn", "wheat", "soybean"]
CP_SPECIFIC = ["commodity index", "commodity swaps?"]

EQ_CORE = ["equity", "equity[- ]related", "stock"]
EQ_SPECIFIC = ["call options?", "put options?", "equity collar", "index future"]

GEN_SPECIFIC = [
    "embedded derivatives?", "notional (?:amounts?|values?|principals?)",
    "derivative (?:assets?|liabilities|gains?|losses?)", "(?:gain|loss) on derivatives?",
    "over[- ]the[- ]counter derivatives?", "total[- ]return swap", "designated as (?:a )?hedges?", "(?:instruments?|contracts?) are designated",
    "cash flow hedges?", "fair value hedges?", "net investment hedges?", "derivative financial instruments?",
]

def get_derivatives_regex() -> re.Pattern:
    """Creates a single, combined regex to find any mention of derivatives or hedging."""
    ir_pattern = build_smart_regex(IR_CORE, ALL_BASE_TYPES + ALL_SUFFIXES, IR_SPECIFIC)
    fx_pattern = build_smart_regex(FX_CORE, ALL_BASE_TYPES + ALL_SUFFIXES, FX_SPECIFIC)
    cp_pattern = build_smart_regex(CP_CORE, ALL_BASE_TYPES + ALL_SUFFIXES, CP_SPECIFIC)
    eq_pattern = build_smart_regex(EQ_CORE, ALL_BASE_TYPES, EQ_SPECIFIC)
    
    # General pattern for base types followed by suffixes (e.g., "swap agreement")
    gen_base_pattern = f'{build_alternation(ALL_BASE_TYPES)}[- ]{build_alternation(ALL_SUFFIXES)}'

    full_pattern = build_alternation([
        ir_pattern, fx_pattern, cp_pattern, eq_pattern, gen_base_pattern, build_alternation(GEN_SPECIFIC)
    ])
    
    return re.compile(r'\b' + full_pattern + r'\b', re.IGNORECASE)

# --- NEW: Derivative Context Keywords ---
DERIVATIVE_CONTEXT_KEYWORDS = [
    # Risk Exposure Context
    'market risk', 'financial risk', 'risk management', 'risk exposure',
    # Interest Rate Context
    'interest rate', 'floating rate', 'fixed rate', 'benchmark rate', 'debt', 'credit',
    # Foreign Exchange Context
    'international', 'currency', 'foreign operations', 'translation exposure',
    # Commodity Context
    'supplier', 'energy', 'inventory', 'raw material',
    # Equity Context
    'stock', 'equity', 'share price',
    # NEW: XBRL and Structured Data Context
    'xbrl', 'xbrl tagging', 'structured data', 'financial-ner-nlp',
    'sec filing', '10-k', '10-q', 'sec'
]

# --- Other Finance Topics Keywords ---
OTHER_FINANCE_KEYWORDS = [
    # Mergers & Acquisitions
    'm&a', 'merger', 'acquisition', 'takeover', 'leveraged buyout', 'lbo',
    # Initial Public Offering
    'ipo', 'initial public offering', 'going public', 'prospectus',
    # Earnings & Financials (more general than context)
    'earnings call', 'quarterly results', 'revenue', 'net income', 'ebitda', 'balance sheet', 'cash flow statement',
    # Investing & Portfolio
    'portfolio management', 'asset allocation', 'diversification', 'equity research', 'stock pitch',
    # Markets & Economy
    'federal reserve', 'inflation', 'gdp', 'economic outlook',
    # Corporate Finance
    'capital structure', 'share buyback', 'dividends', 'corporate bond', 'credit rating',
    # Financial Analysis & Reporting
    'financial analysis', 'financial reporting', 'financial statement',
    # Legal & Regulatory
    'legal', 'regulatory', 'compliance',
]

def get_other_finance_regex() -> re.Pattern:
    """Creates a regex to find other common financial topics."""
    processed_keywords = [kw.replace(' ', '[- ]') for kw in OTHER_FINANCE_KEYWORDS]
    pattern = build_alternation(processed_keywords)
    return re.compile(r'\b' + pattern + r'\b', re.IGNORECASE)

def get_derivative_context_regex() -> re.Pattern:
    """Creates a regex to find other common financial topics."""
    # Create a pattern that looks for individual words, allowing for spaces in multi-word terms
    processed_keywords = [kw.replace(' ', '[- ]') for kw in DERIVATIVE_CONTEXT_KEYWORDS]
    pattern = build_alternation(processed_keywords)
    return re.compile(r'\b' + pattern + r'\b', re.IGNORECASE)

# =============================================================================
# MAIN SCRIPT LOGIC
# =============================================================================

def main():
    """
    Main function to filter the dataset and create a focused subset.
    """
    print(f"Loading dataset from '{INPUT_FILE}'...")
    try:
        df = pd.read_parquet(INPUT_FILE)
        print(f"✅ Successfully loaded {len(df):,} rows.")
    except Exception as e:
        print(f"❌ Error: Could not load the input file '{INPUT_FILE}'.")
        print(f"   Please ensure the file exists and is a valid Parquet file.")
        print(f"   Details: {e}")
        return

    # --- Prepare Regex ---
    derivatives_regex = get_derivatives_regex()
    derivative_context_regex = get_derivative_context_regex()
    other_finance_regex = get_other_finance_regex()

    # --- Classify Rows ---
    print("Classifying rows into categories (this may take a while)...")
    derivative_indices: List[int] = []
    other_finance_indices: List[int] = []
    derivative_context_indices: List[int] = []

    for index, row in tqdm(df.iterrows(), total=len(df), desc="Scanning rows"):
        # Combine text from specified columns for a comprehensive search
        try:
            text_to_search = " ".join(str(row[col]) for col in TEXT_COLUMNS if col in row and pd.notna(row[col]))
        except KeyError:
            print(f"❌ Error: One of the text columns {TEXT_COLUMNS} not found in the dataframe.")
            print("Please check the TEXT_COLUMNS configuration.")
            return

        if not text_to_search:
            continue

        # Check for derivatives first, as it's the priority
        if derivatives_regex.search(text_to_search):
            derivative_indices.append(index)
        # Then check for derivative-related context
        elif derivative_context_regex.search(text_to_search):
            derivative_context_indices.append(index)
        # If not a derivative, check if it's another financial topic
        elif other_finance_regex.search(text_to_search):
            other_finance_indices.append(index)

    print("\n--- Classification Summary ---")
    print(f"  - Found {len(derivative_indices):,} rows matching derivative/hedging keywords.")
    print(f"  - Found {len(derivative_context_indices):,} rows matching derivative context keywords.")
    print(f"  - Found {len(other_finance_indices):,} rows matching other general finance topics.")

    # --- Sample and Combine ---
    print("\nSampling and creating the final dataset...")

    # 1. Take all derivative-related rows
    final_indices: Set[int] = set(derivative_indices)
    print(f"  - Selected all {len(derivative_indices):,} derivative rows.")

    # 2. Take all derivative-context rows
    final_indices.update(derivative_context_indices)
    print(f"  - Selected all {len(derivative_context_indices):,} derivative context rows.")

    # 3. Sample from "other finance" topics
    if len(other_finance_indices) > OTHER_FINANCE_SAMPLE_SIZE:
        other_sample_indices = random.sample(other_finance_indices, OTHER_FINANCE_SAMPLE_SIZE)
        print(f"  - Sampled {len(other_sample_indices):,} 'other finance' rows.")
    else:
        other_sample_indices = other_finance_indices
        print(f"  - Taking all {len(other_sample_indices):,} 'other finance' rows (less than sample size).")
    
    final_indices.update(other_sample_indices)

    # --- Create and Save Final DataFrame ---
    if not final_indices:
        print("❌ No matching rows were found. No output file will be created.")
        return

    final_df = df.loc[sorted(list(final_indices))].reset_index(drop=True)

    print(f"\n✅ Final dataset created with {len(final_df):,} total rows.")

    try:
        final_df.to_parquet(OUTPUT_FILE, index=False)
        print(f"   Successfully saved to '{OUTPUT_FILE}'.")
    except Exception as e:
        print(f"❌ Error saving the output file: {e}")
if __name__ == "__main__":
    main()


# =============================================================================
# HOW TO RUN THIS SCRIPT
# =============================================================================
#
# 1. Make sure you have the required libraries:
#    pip install pandas pyarrow tqdm
#
# 2. Place this script in the same directory as your 'Finance-500K.parquet' file.
#
# 3. Run the script from your terminal:
#    python filter_dataset.py
#
# 4. The script will produce a new file named 'finance_instruct_derivatives_subset.parquet'
#    in the same directory. This is the file you can use for your two-stage fine-tuning.
#
# =============================================================================
# EXAMPLE USAGE IN TRAINING SCRIPT
# =============================================================================
#
# In your `training2.py` script, you would first fine-tune on this new subset.
#
# STAGE 1:
#
# def run_training(
#     ...
#     data_path="finance_instruct_derivatives_subset.parquet", # <--- Use the new file
#     formatting_func=format_finance_instruct_prompt,
#     new_model_name="derivatives-classifier-4B-finance-base",
#     ...
# ):
#
# STAGE 2:
#
# def run_training(
#     ...
#     model_name="derivatives-classifier-4B-finance-base", # <--- Start from the model from Stage 1
#     data_path="training_data.parquet", # <--- Use your synthetic data
#     formatting_func=format_task_prompt,
#     new_model_name="derivatives-classifier-4B-final",
#     ...
# ):
#
# =============================================================================
# %%
