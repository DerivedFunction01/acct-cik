import pandas as pd
import re
import random
import argparse
from typing import Dict, List, Any
from tqdm import tqdm

# Import regex components and lists from your centralized library
# Ensure derivative_regex.py is in the same directory
from derivative_regex import (
    COMMON_COMMODITIES, IR_REGEX, FX_REGEX, CP_REGEX, EQ_REGEX,
    ALL_REGEX,
    ALL_BASE_TYPES, ALL_SUFFIXES
)

# =============================================================================
# CONFIGURATION
# =============================================================================

def clean_terms(terms: List[str]) -> List[str]:
    """
    Cleans regex-style lists for plain text generation.
    Handles character classes ([- ]), optional markers (?), and escapes.
    """
    cleaned = []
    for t in terms:
        # 1. Handle common regex character classes found in your file
        # "total[- ]return" -> "total return"
        t = t.replace("[- ]", " ") 
        t = t.replace("[-]", "-")
        
        # 2. Remove standard regex syntax
        t = t.replace("?", "")    # Remove optional marker
        t = t.replace("\\", "")   # Remove escapes
        t = t.replace("(?:", "")  # Remove non-capturing groups (just in case)
        t = t.replace(")", "")    # Remove closing parenthesis
        
        # 3. Collapse multiple spaces and strip
        t = " ".join(t.split())
        
        # 4. remove the "s" at the end
        if t.endswith("s"):
            t = t[:-1]
        
        cleaned.append(t)
    return cleaned

# Generate clean lists for construction from the imported regex file
# We use the full lists to maximize variety
CLEAN_BASES = clean_terms(ALL_BASE_TYPES)
CLEAN_SUFFIXES = clean_terms(ALL_SUFFIXES)

# Specific full-term replacements per category (Safe Hedging Variants)
# These are used to inject specific, high-quality terms occasionally
CATEGORY_EXTRAS = {
    "IR": [
        "treasury lock contracts",
        "basis swap",
        "interest rate cap",
        "interest rate floor",
        "interest rate put optio",
    ],
    "FX": [
        "non deliverable forward",
        "deal-contingent forward",
        "foreign currency exchange forward",
        "deliverable forward option",
    ],
    "CP": ["crack spread", "spark spread", "power purchase agreement"],
    "EQ": [
        "equity variance swap",
        "dividend swap",
        "total return equity swap",
        "equity collar",
        "equity futures",
        "derivative warrant",
    ],
    "GEN": [
        "over-the-counter derivatives",
        "OTC derivatives",
        "hedging instrument",
        "embedded derivative",
        "derivative contract",
        "derivative financial instrument",
        "financial counterparty contract",
        "financial derivatives",
    ],
}

# Prefixes to construct new instruments
# Used to anchor a generic base (like "swap") to a specific category (like "Interest Rate")
# NOTE: "stock option" excluded to avoid noise classification
PLACEHOLDERS = {
    "IR": [
        "interest rate",
        "forward-rate",
        "fixed-rate", 
        "floating-rate",
        "rate basis", 
    ],
    "FX": [
        "foreign exchange",
        "forward exchange",
        "foreign currency",
        "cross-currency",
        "forward currency",
        "forward exchange rate",
        "currency exchange",
        "exchange rate",
        "FX",
    ],
    "CP": [
        "commodity price",
        "fixed commodity",
        "commodity",
    ] + COMMON_COMMODITIES,
    "EQ": [
        "equity",
        "share price",
        "market index",
        "equity index"
    ],
    "GEN": [
        "financial",
        "derivative", 
        "" # Allow purely base+suffix (e.g. "Swap Agreement")
    ],
}

# =============================================================================
# LOGIC
# =============================================================================

def determine_category(text_span: str) -> str:
    """
    Classifies a detected instrument string into a category using the strict regexes.
    If multiple match, order of precedence is IR > FX > CP > EQ > GEN.
    """
    if IR_REGEX.search(text_span): return "IR"
    if FX_REGEX.search(text_span): return "FX"
    if CP_REGEX.search(text_span): return "CP"
    if EQ_REGEX.search(text_span): return "EQ"
    return "GEN" # Fallback

def generate_synthetic_instrument(category: str) -> str:
    """
    Constructs a new instrument name based on the category using 
    Base + Suffix combinations or full Extra terms.
    """
    # 1. Chance to use a pre-defined "Extra" (Full term) - 20%
    extras = CATEGORY_EXTRAS.get(category, [])
    if extras and random.random() < 0.2: 
        return random.choice(extras)
    
    # 2. Generative Construction: Prefix + Base + Suffix
    
    # Select components
    prefixes = PLACEHOLDERS.get(category, [""])
    prefix = random.choice(prefixes)
    
    # Pick any base from the comprehensive list (e.g., "swap", "collar", "future")
    base = random.choice(CLEAN_BASES)
    
    # Pick any suffix (e.g., "agreement", "contract")
    suffix = random.choice(CLEAN_SUFFIXES)
    
    # Randomly decide structure to add variety
    roll = random.random()
    
    if roll < 0.5:
        # Structure 1: Full Construction (e.g. "interest rate swap agreement")
        # Most explicit, safe for all contexts
        parts = [prefix, base, suffix]
        
    elif roll < 0.8:
        # Structure 2: Prefix + Base (e.g. "interest rate swap")
        # Common in natural language
        parts = [prefix, base]
        
    else:
        # Structure 3: Base + Suffix (e.g. "swap agreement") or Just Base
        # Only safe if we ensure context isn't totally lost, but acceptable for augmentation.
        # If the category is specific (like IR), we prefer keeping the prefix unless
        # we roll a generic structure intentionally.
        
        if not prefix and category != "GEN":
            # If no prefix available/selected for a specific category, force Structure 2 
            # to ensure we don't output generic "swap" for an IR tag
            parts = [random.choice(PLACEHOLDERS[category]), base] 
        else:
             # 50/50 split between "Base Suffix" and just "Base"
            if random.random() < 0.5:
                parts = [base, suffix]
            else:
                parts = [base]

    # Filter empty parts and join
    return " ".join([p for p in parts if p]).strip() + "s"

def apply_dynamic_substitution(text: str) -> str:
    """
    Finds an instrument using ALL_REGEX, determines its category, 
    and replaces it with a generated synthetic variant.
    """
    # 1. Find all instrument occurrences in the text
    # We use finditer to locate specific spans
    matches = list(ALL_REGEX.finditer(text))
    
    if not matches:
        return text

    # 2. Pick ONE match to substitute
    # (Replacing all might be too aggressive if they refer to different things)
    target_match = random.choice(matches)
    original_span = target_match.group()
    start, end = target_match.span()
    
    # 3. Identify Category of the matched term
    category = determine_category(original_span)
    
    # 4. Generate Replacement for that category
    replacement = generate_synthetic_instrument(category)
    
    # 5. Apply Replacement
    # Reconstruct string: before + replacement + after
    new_text = text[:start] + replacement + text[end:]
    
    return new_text

def augment_dataframe(df: pd.DataFrame, substitution_rate: float) -> pd.DataFrame:
    """
    Iterates over the DataFrame, attempts a substitution, and returns 
    a new DataFrame containing both original and synthetic samples.
    """
    augmented_data: List[Dict[str, Any]] = []
    
    # Label existing rows as non-synthetic
    df["is_synthetic"] = False
    augmented_data.extend(df.to_dict("records"))
    
    print(f"Generating synthetic samples (Rate: {substitution_rate:.0%})...")

    # Iterate over original rows to create synthetic ones
    for index, row in tqdm(df.iterrows(), total=len(df)):
        
        # Only attempt substitution on a percentage of samples
        if random.random() < substitution_rate:
            original_text = row["text"]
            synthetic_text = apply_dynamic_substitution(original_text)
            
            # Check if a meaningful substitution occurred
            if synthetic_text and synthetic_text != original_text:
                
                # Create a new row dictionary based on the original
                synthetic_row = row.to_dict()
                synthetic_row["text"] = synthetic_text
                synthetic_row["is_synthetic"] = True
                
                # Append the synthetic row to the list
                augmented_data.append(synthetic_row)
    
    # Convert the combined list back to a DataFrame
    augmented_df = pd.DataFrame(augmented_data)
    return augmented_df

# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Augment a Parquet dataset by dynamically substituting financial instruments using generative categories."
    )
    parser.add_argument(
        "--input_file",
        type=str,
        required=True,
        help="Path to the source Parquet file.",
    )
    parser.add_argument(
        "--output_suffix",
        type=str,
        default="_augmented",
        help="Suffix to add to the output filename.",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=0.75,
        help="The rate (0.0 to 1.0) of original samples to attempt substitution on.",
    )

    args = parser.parse_args()
    
    if not 0.0 <= args.rate <= 1.0:
        print("Error: Rate must be between 0.0 and 1.0.")
        exit(1)

    print(f"🚀 Starting dataset augmentation for: {args.input_file}")
    
    # 1. Load Data
    try:
        df_original = pd.read_parquet(args.input_file)
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input_file}")
        exit(1)
    
    print(f"   -> Loaded {len(df_original):,} original rows.")

    # 2. Augment Data
    df_augmented = augment_dataframe(df_original, args.rate)
    
    print(f"   -> Generated {len(df_augmented) - len(df_original):,} synthetic rows.")
    print(f"   -> Total rows after augmentation: {len(df_augmented):,}")

    # 3. Save Data
    output_path = args.input_file.replace(".parquet", f"{args.output_suffix}.parquet")
    df_augmented.to_parquet(output_path, index=False)

    print(f"\n✨ Augmentation complete! Saved to '{output_path}'")
