import pandas as pd
import re
from tqdm import tqdm
from collections import Counter
import sys
import os
import hashlib

# Ensure we can import local modules for regex access
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from derivative_regex import CATEGORY_REGEX, CP_CONTEXT_REGEX, EQ_CONTEXT_REGEX, EXCLUDE_REGEX_EQUITY_COMP, FX_CONTEXT_REGEX, IR_CONTEXT_REGEX
from filter_database import get_sentence_categories

# =============================================================================
# CONFIGURATION
# =============================================================================
INPUT_PATH = "roberta/financial-sentences-filtered.parquet"  # Your raw candidates
OUTPUT_PATH = "roberta/gen_terms_cleaned.parquet"
TARGET_SIZE = 5000  # How many "Best" generics to keep

# Terms that should NEVER appear in a generic class
# (If these appear, the sentence is either specific IR/FX or unwanted noise)
FORBIDDEN_REGEX = re.compile(
    r"|".join(
        [
            CATEGORY_REGEX.pattern,
            IR_CONTEXT_REGEX.pattern,
            FX_CONTEXT_REGEX.pattern,
            CP_CONTEXT_REGEX.pattern,
            EQ_CONTEXT_REGEX.pattern,
            EXCLUDE_REGEX_EQUITY_COMP.pattern,
            "equity"
        ]
    ), re.IGNORECASE
)

# =============================================================================
# CLASSES
# =============================================================================


class GenericRanker:
    """
    Scores generic sentences based on their 'Professional Financial Density'.
    We want high-quality boilerplate, not random sentence fragments.
    """

    def __init__(self):
        self.good_terms = [
            "risk",
            "management",
            "policy",
            "exposure",
            "financial",
            "statement",
            "reporting",
            "fair value",
            "assets",
            "liabilities",
            "hedging",
            "derivative",
            "instrument",
            "contract",
            "agreement",
            "strategies",
            "objectives",
            "market",
            "credit",
            "liquidity",
        ]

    def score(self, text: str) -> int:
        # 1. Base Score: Length (Too short is bad, too long is messy)
        length = len(text.split())
        if length < 5:
            return -100  # Garbage
        if length > 80:
            return 0  # Too complex/messy

        score = 10

        # 2. Vocabulary Bonus
        text_lower = text.lower()
        for term in self.good_terms:
            if term in text_lower:
                score += 5

        # 3. Structure Bonus (looks like a full sentence)
        if text[0].isupper() and text[-1] == ".":
            score += 10

        # 4. "Derivative" Bonus (We prefer ambiguity over pure noise)
        if "derivative" in text_lower or "hedge" in text_lower:
            score += 15

        return score


class ContentDeduplicator:
    def __init__(self):
        self.seen_hashes = set()

    def is_duplicate(self, text: str) -> bool:
        # Normalize: remove numbers and punctuation
        norm = re.sub(r"\d+", "0", text.lower())
        norm = re.sub(r"[^\w]", "", norm)
        if len(norm) < 10:
            return False

        h = hashlib.md5(norm.encode("utf-8")).hexdigest()
        if h in self.seen_hashes:
            return True
        self.seen_hashes.add(h)
        return False


# =============================================================================
# MAIN PROCESS
# =============================================================================
CAPS_REGEX = re.compile(r"\b[A-Z]{2,}\b")

def clean_and_rank_generics():
    print(f"🧹 Loading Raw Generics from {INPUT_PATH}...")
    try:
        df = pd.read_parquet(INPUT_PATH)
    except Exception as e:
        print(f"❌ Could not load file: {e}")
        return

    print(f"   -> Loaded {len(df):,} raw candidates.")

    ranker = GenericRanker()
    deduper = ContentDeduplicator()

    cleaned_data = []
    stats = Counter()

    print("⚙️  Filtering and Scoring...")
    for row in tqdm(df.itertuples(), total=len(df)):

        assert isinstance(row.text, str)
        text = row.text.strip() 
        # -------------------------------------------------------
        # NEW STEP: STRIP CAPS HEADERS
        # -------------------------------------------------------
        # Transforms "ITEM 7A. DERIVATIVES" -> " 7. " -> Filtered out by length later
        # Transforms "We use SWAPS." -> "We use ."
        text = CAPS_REGEX.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()  # Clean up the left-over spaces
        # -------------------------------------------------------
        # FILTER 1: FORBIDDEN KEYWORDS
        # -------------------------------------------------------
        # Remove specific category leaks (e.g. hidden IR) or unwanted noise (Stock Comp)
        if FORBIDDEN_REGEX.search(text):
            stats["dropped_forbidden"] += 1
            continue

        # -------------------------------------------------------
        # FILTER 2: CATEGORY SAFETY CHECK
        # -------------------------------------------------------
        # Double check with your full pipeline logic.
        # If it detects IR/FX/CP/EQ, it is NOT generic.
        cats = get_sentence_categories(text)
        specific_cats = cats - {"gen", "other"}
        if len(specific_cats) > 0:
            stats[f"dropped_reclassified_{list(specific_cats)[0]}"] += 1
            continue

        # -------------------------------------------------------
        # FILTER 3: DEDUPLICATION
        # -------------------------------------------------------
        if deduper.is_duplicate(text):
            stats["dropped_duplicate"] += 1
            continue

        # -------------------------------------------------------
        # FILTER 4: SCORING & RANKING
        # -------------------------------------------------------
        score = ranker.score(text)
        if score <= 0:
            stats["dropped_low_quality"] += 1
            continue

        cleaned_data.append(
            {
                "text": text,
                "label": "gen",
                "score": score,
                "difficulty": "L0_Cleaned_Generic",
            }
        )
        stats["kept"] += 1

    # Sort by Score (Best first)
    cleaned_data.sort(key=lambda x: x["score"], reverse=True)

    # Take Top N
    final_list = cleaned_data[:TARGET_SIZE]

    print("\n📊 Filtering Report:")
    print(f"   - Original: {len(df):,}")
    print(f"   - Forbidden Terms: {stats['dropped_forbidden']:,}")
    print(
        f"   - Specific Leaks (IR/FX...): {stats['dropped_reclassified_ir'] + stats['dropped_reclassified_fx'] + stats['dropped_reclassified_cp'] + stats['dropped_reclassified_eq']:,}"
    )
    print(f"   - Duplicates: {stats['dropped_duplicate']:,}")
    print(f"   - Low Quality: {stats['dropped_low_quality']:,}")
    print(f"   - Candidates Kept: {len(cleaned_data):,}")
    print(f"   - Final Selection: {len(final_list):,}")

    # Export
    final_df = pd.DataFrame(final_list)
    final_df.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Saved Best-in-Class Generics to {OUTPUT_PATH}")


if __name__ == "__main__":
    clean_and_rank_generics()
