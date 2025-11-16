#%%
import pandas as pd
from tqdm import tqdm
import random
from typing import List, Set
import re

# =============================================================================
# CONFIGURATION
# =============================================================================
INPUT_FILE = "Finance-500K.parquet"
OUTPUT_FILE = "finance_instruct_derivatives_subset.parquet"
OTHER_FINANCE_SAMPLE_SIZE = 10000
TEXT_COLUMNS = ["user", "assistant"]
FIRST_N = 11000


# =============================================================================
# DERIVATIVE REGEX
# =============================================================================
def build_alternation(items: List[str]) -> str:
    return f'(?:{"|".join(items)})' if items else ""


def build_smart_regex(
    core_terms: List[str], context_terms: List[str], specific_phrases: List[str]
) -> str:
    pattern1 = (
        f"{build_alternation(core_terms)}[- ]{build_alternation(context_terms)}"
        if core_terms and context_terms
        else ""
    )
    pattern2 = build_alternation(specific_phrases)
    return build_alternation([p for p in [pattern1, pattern2] if p])


ALL_BASE_TYPES = [
    "swaps?",
    "forwards?",
    "futures?",
    "options?",
    "caps?",
    "floors?",
    "collars?",
    "derivatives?",
    "swaptions?",
    "locks?",
    "hedges?",
    "hedging",
]
ALL_SUFFIXES = [
    "agreements?",
    "contracts?",
    "instruments?",
    "arrangements?",
    "assets?",
    "liabilit(?:y|ies)",
    "commitments?",
    "positions?",
    "strateg(?:ies|y)",
]
IR_CORE = [
    "interest[- ]rate",
    "Eurodollar",
    "SOFR",
    "SONIA",
    "LIBOR",
    "treasury[- ]rate",
    "fixed[- ]rate",
    "floating[- ]rate",
]
IR_SPECIFIC = [
    "zero[- ]coupon swap",
    "FRA",
    "treasury lock",
    "interest rate cap",
    "interest rate floor",
]
FX_CORE = [
    "foreign[- ]exchange",
    "foreign[- ]currency",
    "currency",
    "cross[- ]currency",
    "FX",
    "forex",
]
FX_SPECIFIC = [
    "NDF",
    "non[- ]deliverable forwards?",
    "deliverable forwards?",
    "forward foreign exchange",
    "foreign currency contracts?",
]
CP_CORE = [
    "commodity",
    "crude oil",
    "natural gas",
    "aluminum",
    "coal",
    "fuel",
    "gasoline",
    "steel",
    "sugar",
    "corn",
    "wheat",
    "soybean",
]
CP_SPECIFIC = ["commodity index", "commodity swaps?"]
EQ_CORE = ["equity", "equity[- ]related", "stock"]
EQ_SPECIFIC = ["call options?", "put options?", "equity collar", "index future"]
GEN_SPECIFIC = [
    "embedded derivatives?",
    "notional (?:amounts?|values?|principals?)",
    "derivative (?:assets?|liabilities|gains?|losses?)",
    "(?:gain|loss) on derivatives?",
    "over[- ]the[- ]counter derivatives?",
    "total[- ]return swap",
    "designated as (?:a )?hedges?",
    "(?:instruments?|contracts?) are designated",
    "cash flow hedges?",
    "fair value hedges?",
    "net investment hedges?",
    "derivative financial instruments?",
]


def get_derivatives_regex() -> re.Pattern:
    ir_pattern = build_smart_regex(IR_CORE, ALL_BASE_TYPES + ALL_SUFFIXES, IR_SPECIFIC)
    fx_pattern = build_smart_regex(FX_CORE, ALL_BASE_TYPES + ALL_SUFFIXES, FX_SPECIFIC)
    cp_pattern = build_smart_regex(CP_CORE, ALL_BASE_TYPES + ALL_SUFFIXES, CP_SPECIFIC)
    eq_pattern = build_smart_regex(EQ_CORE, ALL_BASE_TYPES, EQ_SPECIFIC)
    gen_base_pattern = (
        f"{build_alternation(ALL_BASE_TYPES)}[- ]{build_alternation(ALL_SUFFIXES)}"
    )
    full_pattern = build_alternation(
        [
            ir_pattern,
            fx_pattern,
            cp_pattern,
            eq_pattern,
            gen_base_pattern,
            build_alternation(GEN_SPECIFIC),
        ]
    )
    return re.compile(r"\b" + full_pattern + r"\b", re.IGNORECASE)


# =============================================================================
# MAIN
# =============================================================================
def main():
    print(f"Loading '{INPUT_FILE}'...")
    df = pd.read_parquet(INPUT_FILE)
    print(f"Loaded {len(df):,} rows.")

    derivatives_regex = get_derivatives_regex()

    # 1. Scan ENTIRE dataset for derivatives
    print("Scanning full dataset for derivatives...")
    derivative_indices: Set[int] = set()
    for index, row in tqdm(df.iterrows(), total=len(df), desc="Derivatives"):
        text = " ".join(
            str(row[col]) for col in TEXT_COLUMNS if col in row and pd.notna(row[col])
        )
        if text and derivatives_regex.search(text):
            derivative_indices.add(index)

    # 2. Take first 11K rows, dedupe with derivatives
    print(f"Taking first {FIRST_N:,} rows (deduped)...")
    first_11k_indices = set(range(FIRST_N))
    final_indices = derivative_indices.union(first_11k_indices)

    # 3. Sample if needed (optional cap)
    if len(final_indices) > OTHER_FINANCE_SAMPLE_SIZE + len(derivative_indices):
        # Keep all derivatives, sample rest from first 11K
        non_deriv = list(first_11k_indices - derivative_indices)
        sampled_non_deriv = random.sample(non_deriv, OTHER_FINANCE_SAMPLE_SIZE)
        final_indices = derivative_indices.union(sampled_non_deriv)

    final_df = df.loc[sorted(final_indices)].reset_index(drop=True)
    print(f"Final dataset: {len(final_df):,} rows.")
    final_df.to_parquet(OUTPUT_FILE, index=False)
    print(f"Saved to '{OUTPUT_FILE}'.")

#%%
if __name__ == "__main__":
    main()

# %%
