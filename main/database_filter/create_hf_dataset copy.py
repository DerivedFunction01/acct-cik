import sqlite3
import pandas as pd
import json
import random
import re
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from collections import Counter, defaultdict
import sys
import os
import hashlib
import logging
from typing import Tuple, Set, List, Optional, Dict, Any
from tqdm import tqdm

# Ensure we can import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from derivative_regex import (
    BASE_REGEX,
    CP_REGEX,
    CP_SOFT_REGEX,
    EQ_REGEX,
    EQ_SOFT_REGEX,
    FX_REGEX,
    FX_SOFT_REGEX,
    GEN_REGEX,
    IR_REGEX,
    IR_SOFT_REGEX,
    SENTENCE_SPLIT_PATTERN,
    STRICT_REGEX,
    MIN_SENTENCE_LENGTH,
    CATEGORY_CONTEXT_MAP,
    UNAMBIGUOUS_BASE_TYPES,
    IR_CONTEXT_REGEX,
    FX_CONTEXT_REGEX,
    CP_CONTEXT_REGEX,
    EQ_CONTEXT_REGEX,
    HEDGING_CONTEXT_REGEX,
    EXCLUDE_REGEX_ACCOUNTING_STD,
    CATEGORY_DELETION_MAP,
    VALUATION_MODELS,
    Currency,
    cleanup_fragment,
    VERB_USE_REGEX,
    all_currencies, # dynamic currency subsitution
)
from filter_database import get_sentence_categories

# Setup logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "web_data.db"
OUTPUT_PATH = "roberta/classification_data_v17_scrubbed.parquet"

# THE SEPARATOR TOKEN
SEP_TOKEN = " [SEP] "

# DYNAMIC WINDOW SETTINGS
MIN_WINDOW_SIZE = 1
MAX_WINDOW_SIZE = 3

TARGET_SAMPLES_PER_CLASS = 1250
SATURATION_LIMIT = int(TARGET_SAMPLES_PER_CLASS * 1.5)
CHUNK_SIZE = 5000
MAX_WORKERS = max(1, mp.cpu_count() - 1)

# Scrubbing configuration
SCRUBBING_CONFIG = {
    "keep_same_category_bases": True,  # Keep multiple IR swaps/caps/locks
    "remove_category_context": True,  # Remove FX/CP/EQ context signals
    "min_instruments_per_sentence": 1,  # At least one instrument remains
    "aggressive_scrub": True,  # If True, remove ALL non-target instruments
}

NUMERIC_SUBSTITUTION_CONFIG = {
    "enabled": True,
    "apply_to_years": True,
    "year_delta": 1,  # ±1 applied uniformly to ALL years
    "apply_to_numbers": True,
    "number_perturbation": 0.05,  # ±5% uniform
    "skip_zeros": True,
    "preserve_precision": True,
}

# Regex patterns
YEAR_REGEX_COLLECTOR = re.compile(r"\b(19[0-9]{2}|20[0-9]{2})\b")
NON_YEAR_NUMBER_REGEX = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\b")


LABEL_TO_CONFLICT_REGEX = {
    "ir": [
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        FX_REGEX,
        FX_SOFT_REGEX,
        CP_REGEX,
        CP_SOFT_REGEX,
        EQ_REGEX,
        EQ_SOFT_REGEX,
    ],
    "fx": [
        IR_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        IR_REGEX,
        IR_SOFT_REGEX,
        CP_REGEX,
        CP_SOFT_REGEX,
        EQ_REGEX,
        EQ_SOFT_REGEX,
    ],
    "cp": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        IR_REGEX,
        IR_SOFT_REGEX,
        FX_REGEX,
        FX_SOFT_REGEX,
        EQ_REGEX,
        EQ_SOFT_REGEX,
    ],
    "eq": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        IR_REGEX,
        IR_SOFT_REGEX,
        FX_REGEX,
        FX_SOFT_REGEX,
        CP_REGEX,
        CP_SOFT_REGEX,
    ],
    "gen": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        IR_REGEX,
        IR_SOFT_REGEX,
        FX_REGEX,
        FX_SOFT_REGEX,
        CP_REGEX,
        CP_SOFT_REGEX,
        EQ_REGEX,
        EQ_SOFT_REGEX,
    ],
}

# =============================================================================
# HELPER CLASSES
# =============================================================================

# Add these regex patterns after the NUMERIC_SUBSTITUTION_CONFIG section (around line 100)
MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

MONTH_ABBREVIATIONS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# Map month number (1-12) back to name/abbrev
MONTH_NUMBER_TO_NAME = {v: k for k, v in MONTH_NAMES.items()}
MONTH_NUMBER_TO_ABBREV = {v: k for k, v in MONTH_ABBREVIATIONS.items()}

# Regex to match month names, abbreviations, or numeric months
MONTH_REGEX = re.compile(
    r"\b("
    + "|".join(list(MONTH_NAMES.keys()) + list(MONTH_ABBREVIATIONS.keys()))
    + r")\b",
    re.IGNORECASE,
)

class NumericSubstitutionEngine:
    """
    Performs dynamic numeric substitution on text windows.

    Strategy:
    - Years: Collect all, pick random base year, apply ±1 uniformly
    - Months: Collect all, pick random base month, preserve offsets
    - Numbers (non-zero): Apply ±5% uniform multiplicative perturbation
    - Zeros: Skip
    - Validation: Check perturbed years stay within window context range
    """

    def __init__(self, config=None, random_seed=None):
        """
        Args:
            config: Dict with substitution parameters
            random_seed: For reproducibility
        """
        self.config = config or NUMERIC_SUBSTITUTION_CONFIG
        self.rng = random.Random(random_seed) if random_seed else random
        self.substitution_log = []
        self.year_mapping = {}  # Maps original year -> replacement year
        self.month_mapping = (
            {}
        )  # Maps original month (1-12) -> replacement month (1-12)
        self.base_year = None
        self.base_month = None

    # ========== MONTH EXTRACTION & SUBSTITUTION ==========

    def extract_sentence_months(self, sentences: List[str]):
        """
        Extract months from each sentence, tracking both month values and offsets.

        For each sentence, compute:
        - Months found (as integers 1-12)
        - Offsets from the minimum month in that sentence (to preserve comparatives)

        Example:
            sentence = "From January to March we saw growth."
            Returns: {
                'months': [1, 3],
                'min_month': 1,
                'offsets': {1: 0, 3: 2}
            }

        Returns:
            Dict mapping sentence_idx -> {
                'months': [list of month integers],
                'min_month': minimum month in sentence,
                'offsets': {month -> offset_from_min}
            }
        """
        sentence_month_info = {}
        all_months = set()

        for idx, sent in enumerate(sentences):
            months = []
            for match in MONTH_REGEX.finditer(sent):
                month_str = match.group(1).lower()
                month_num = MONTH_NAMES.get(month_str) or MONTH_ABBREVIATIONS.get(
                    month_str
                )
                if month_num:
                    months.append(month_num)

            if months:
                min_month = min(months)
                offsets = {month: month - min_month for month in months}
                sentence_month_info[idx] = {
                    "months": months,
                    "min_month": min_month,
                    "offsets": offsets,
                }
                all_months.update(months)

        return sentence_month_info, all_months

    def pick_base_month(self, all_months):
        """Randomly select one month (1-12) as the base for perturbation."""
        if not all_months:
            return None
        return self.rng.choice(list(all_months))

    def build_month_mapping(self, sentence_month_info, all_months):
        """
        Build mapping from original month -> replacement month.

        Strategy (handles both single months and comparatives):
        1. Pick random base month (ZZ) from all_months
        2. For each sentence:
           - If single month: map to ZZ
           - If comparative (multiple months): map to ZZ + offset, wrapping around (1-12)

        Example:
            sentence_month_info = {
                0: {'months': [1], 'min_month': 1, 'offsets': {1: 0}},
                2: {'months': [1, 3], 'min_month': 1, 'offsets': {1: 0, 3: 2}}
            }
            all_months = {1, 3}
            Pick base_month = 5

            Output mapping:
                1 -> 5  (single month)
                3 -> 7  (5 + offset of 2)

        Args:
            sentence_month_info: Dict from extract_sentence_months()
            all_months: Set of all unique months across all sentences
        """
        if not all_months:
            self.month_mapping = {}
            return

        # Pick random base month
        self.base_month = self.pick_base_month(all_months)
        if not self.base_month:
            self.month_mapping = {}
            return
        # For each sentence, determine how to map its months
        for sent_idx, month_info in sentence_month_info.items():
            offsets = month_info["offsets"]

            # Map each month: base_month + offset, wrapping around 1-12
            for month, offset in offsets.items():
                replacement_month = self.base_month + offset
                replacement_month = ((replacement_month - 1) % 12) + 1
                self.month_mapping[month] = replacement_month

    def substitute_months_in_text(self, text):
        """
        Replace months in text using pre-built month_mapping.

        Preserves capitalization (January vs january).
        Must call build_month_mapping() first.
        """
        if not self.month_mapping:
            return text

        def replace_month(match):
            original_month_str = match.group(1).lower()
            original_month_num = MONTH_NAMES.get(
                original_month_str
            ) or MONTH_ABBREVIATIONS.get(original_month_str)

            if original_month_num is None:
                return match.group(0)

            replacement_month_num = self.month_mapping.get(
                original_month_num, original_month_num
            )

            # Determine if original was abbreviated or full name
            is_abbrev = original_month_str in MONTH_ABBREVIATIONS
            is_capitalized = match.group(1)[0].isupper()

            if is_abbrev:
                replacement_str = MONTH_NUMBER_TO_ABBREV[replacement_month_num]
            else:
                replacement_str = MONTH_NUMBER_TO_NAME[replacement_month_num]

            # Preserve capitalization
            if is_capitalized:
                replacement_str = replacement_str.capitalize()

            self.substitution_log.append(
                {
                    "type": "month",
                    "original": match.group(1),
                    "replacement": replacement_str,
                    "original_month_num": original_month_num,
                    "replacement_month_num": replacement_month_num,
                    "span": match.span(),
                }
            )

            return replacement_str

        return MONTH_REGEX.sub(replace_month, text)

    # ========== EXISTING YEAR & NUMBER METHODS (unchanged) ==========

    def extract_sentence_years(self, sentences: List[str]):
        """
        Extract years from each sentence, tracking both year values and offsets.

        For each sentence, compute:
        - Years found
        - Offsets from the minimum year in that sentence (to preserve comparatives)

        Returns:
            Dict mapping sentence_idx -> {
                'years': [list of years],
                'min_year': minimum year in sentence,
                'offsets': {year -> offset_from_min}
            }
        """
        sentence_year_info = {}
        all_years = set()

        for idx, sent in enumerate(sentences):
            years = [int(y) for y in YEAR_REGEX_COLLECTOR.findall(sent)]
            if years:
                min_year = min(years)
                offsets = {year: year - min_year for year in years}
                sentence_year_info[idx] = {
                    "years": years,
                    "min_year": min_year,
                    "offsets": offsets,
                }
                all_years.update(years)

        return sentence_year_info, all_years

    def pick_base_year(self, all_years):
        """Randomly select one year as the base for perturbation."""
        if not all_years:
            return None
        return self.rng.choice(list(all_years))

    def build_year_mapping(self, sentence_year_info, all_years):
        """Build mapping from original year -> replacement year (with offsets)."""
        if not all_years:
            self.year_mapping = {}
            return

        self.base_year = self.pick_base_year(all_years)

        for sent_idx, year_info in sentence_year_info.items():
            min_year = year_info["min_year"]
            offsets = year_info["offsets"]

            for year, offset in offsets.items():
                replacement_year = self.base_year + offset
                self.year_mapping[year] = replacement_year

    def substitute_years_in_text(self, text):
        """Replace years in text using pre-built year_mapping."""
        if not self.year_mapping:
            return text

        def replace_year(match):
            original_year_str = match.group(0)
            original_year = int(original_year_str)

            new_year = self.year_mapping.get(original_year, original_year)

            self.substitution_log.append(
                {
                    "type": "year",
                    "original": original_year_str,
                    "replacement": str(new_year),
                    "span": match.span(),
                }
            )

            return str(new_year)

        return YEAR_REGEX_COLLECTOR.sub(replace_year, text)

    def substitute_numbers_in_text(self, text):
        """Replace non-year numbers with ±5% uniform perturbation."""
        if not self.config["apply_to_numbers"]:
            return text

        def replace_number(match):
            num_str = match.group(0)

            try:
                num_val = int(num_str)
                if num_val in self.year_mapping:
                    return num_str
            except (ValueError, TypeError):
                pass

            try:
                num_val = float(num_str)
            except ValueError:
                return num_str

            if num_val == 0:
                return num_str

            delta = self.rng.uniform(
                -self.config["number_perturbation"], self.config["number_perturbation"]
            )
            new_val = num_val * (1 + delta)

            decimals = self._count_decimals(num_str)
            new_str = f"{new_val:.{decimals}f}".rstrip("0").rstrip(".")

            self.substitution_log.append(
                {
                    "type": "number",
                    "original": num_str,
                    "replacement": new_str,
                    "delta": delta,
                    "span": match.span(),
                }
            )

            return new_str

        return NON_YEAR_NUMBER_REGEX.sub(replace_number, text)

    def substitute_all(self, text):
        """Apply year, month, and number substitution."""
        text = self.substitute_years_in_text(text)
        text = self.substitute_months_in_text(text)
        text = self.substitute_numbers_in_text(text)
        return text

    @staticmethod
    def _count_decimals(num_str):
        """Infer decimal places from string representation."""
        num_str = num_str.strip()
        if "." not in num_str:
            return 0
        if "e" in num_str.lower():
            return 2
        return len(num_str.split(".")[1])

    def clear_log(self):
        """Reset substitution log and mappings."""
        self.substitution_log = []
        self.year_mapping = {}
        self.month_mapping = {}
        self.base_year = None
        self.base_month = None

_CURRENCY_PATTERNS_CACHE = None


def _get_currency_patterns() -> Dict[str, re.Pattern]:
    """Lazy-load currency regex patterns once."""
    global _CURRENCY_PATTERNS_CACHE

    if _CURRENCY_PATTERNS_CACHE is not None:
        return _CURRENCY_PATTERNS_CACHE

    names = "|".join(re.escape(c.full_name) for c in all_currencies)
    locations = "|".join(re.escape(c.location) for c in all_currencies)
    codes = "|".join(c.code for c in all_currencies)
    adjectives = "|".join(re.escape(c.adjective) for c in all_currencies)

    _CURRENCY_PATTERNS_CACHE = {
        "name": re.compile(rf"\b({names})\b", re.IGNORECASE),
        "location": re.compile(rf"\b({locations})\b", re.IGNORECASE),
        "code": re.compile(rf"\b({codes})\b", re.IGNORECASE),
        "adjective": re.compile(rf"\b({adjectives})\b", re.IGNORECASE),
    }

    return _CURRENCY_PATTERNS_CACHE


# =============================================================================
# CURRENCY SUBSTITUTION ENGINE (UPDATED)
# =============================================================================

class DynamicCurrencySubstitution:
    """
    Performs dynamic currency substitution on text, maintaining semantic consistency
    across Names, Codes, Locations, and Adjectives.
    """

    def __init__(
        self,
        currency_pool: Optional[List[Currency]] = None,
        random_seed: Optional[int] = None,
    ):
        self.currency_pool = currency_pool or all_currencies
        self.rng = random.Random(random_seed) if random_seed else random
        self.substitution_log = []
        
        # Cache for the regex patterns so we don't rebuild them every row
        self._patterns_cache = _get_currency_patterns()

    def build_currency_regex_patterns(self) -> Dict[str, re.Pattern]:
        """
        Builds or returns cached regex patterns for Name, Location, Code, and Adjective.
        """
        if self._patterns_cache:
            return self._patterns_cache
        else:
            self._patterns_cache = _get_currency_patterns()
        return self._patterns_cache

    def detect_currencies(self, text: str) -> Dict[str, List[Tuple[str, Currency]]]:
        """
        Detect all currency references.
        Returns: Dict[type, List[(original_text_span, CurrencyObject)]]
        """
        patterns = self.build_currency_regex_patterns()
        detected = defaultdict(list)

        # Create lookup maps (lowercased keys for case-insensitive matching)
        # Note: We iterate pool once to build these
        maps = {
            "name": {c.full_name.lower(): c for c in self.currency_pool},
            "location": {c.location.lower(): c for c in self.currency_pool},
            "code": {c.code.upper(): c for c in self.currency_pool}, # Codes are usually UPPER
            "adjective": {c.adjective.lower(): c for c in self.currency_pool},
        }

        # 1. Names
        for match in patterns["name"].finditer(text):
            original = match.group(1)
            curr = maps["name"].get(original.lower())
            if curr: detected["name"].append((original, curr))

        # 2. Locations
        for match in patterns["location"].finditer(text):
            original = match.group(1)
            curr = maps["location"].get(original.lower())
            if curr: detected["location"].append((original, curr))

        # 3. Codes
        for match in patterns["code"].finditer(text):
            original = match.group(1)
            curr = maps["code"].get(original.upper())
            if curr: detected["code"].append((original, curr))

        # 4. Adjectives
        for match in patterns["adjective"].finditer(text):
            original = match.group(1)
            curr = maps["adjective"].get(original.lower())
            if curr: detected["adjective"].append((original, curr))

        return detected

    def _match_case(self, original: str, replacement: str) -> str:
        """Helper to match capitalization of the original text."""
        if original.isupper():
            return replacement.upper()
        if original.islower():
            return replacement.lower()
        if original[0].isupper():
            # Capitalize each word
            return " ".join(w.capitalize() for w in replacement.split())
        return replacement

    def build_text_mapping(
        self, detected: Dict[str, List[Tuple[str, Currency]]]
    ) -> Dict[str, str]:
        """
        Builds the final text-to-text mapping.
        
        Logic:
        1. Identify unique Currency Identities found in text.
        2. Select distinct Replacements.
        3. Map specific text spans (e.g. 'Polish') to the correct attribute 
           of the replacement (e.g. 'Malaysian').
        """
        
        # 1. Identify unique underlying currencies (using Code as ID)
        unique_detected_codes = set()
        for det_type, items in detected.items():
            for _, currency in items:
                unique_detected_codes.add(currency.code)
        
        if not unique_detected_codes:
            return {}

        n_needed = len(unique_detected_codes)

        # 2. Select Replacements (exclude those present in text to avoid confusion)
        available = [c for c in self.currency_pool if c.code not in unique_detected_codes]
        
        # Fallback if pool exhausted
        if len(available) < n_needed:
            available = self.currency_pool

        replacements = self.rng.sample(available, min(n_needed, len(available)))
        
        # Create Map: Original Currency Code -> New Currency Object
        # e.g., 'PLN' -> Currency(MYR)
        code_map = {}
        detected_list = list(unique_detected_codes)
        for i, original_code in enumerate(detected_list):
            if i < len(replacements):
                code_map[original_code] = replacements[i]

        # 3. Build Text Substitution Map
        text_mapping = {}

        for det_type, items in detected.items():
            for original_text, currency in items:
                
                # Get the assigned replacement currency object
                new_curr = code_map.get(currency.code)
                if not new_curr:
                    continue

                # Select the correct attribute based on detection type
                if det_type == "name":
                    raw_replacement = new_curr.full_name
                elif det_type == "location":
                    raw_replacement = new_curr.location
                elif det_type == "code":
                    raw_replacement = new_curr.code
                elif det_type == "adjective":
                    raw_replacement = new_curr.adjective
                else:
                    raw_replacement = new_curr.full_name

                # Apply casing
                final_replacement = self._match_case(original_text, raw_replacement)
                
                text_mapping[original_text] = final_replacement

        return text_mapping

    def substitute_all(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Execute the substitution pipeline.
        """
        self.substitution_log = [] # Clear previous log
        
        # 1. Detect
        detected = self.detect_currencies(text)
        if not any(detected.values()):
            return text, []

        # 2. Build Mapping
        # Returns: {'Polish': 'Malaysian', 'PLN': 'MYR'}
        mapping = self.build_text_mapping(detected)
        
        if not mapping:
            return text, []

        # 3. Substitute (Greedy by length)
        # Sort keys by length descending to match "US Dollar" before "US"
        sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
        pattern = re.compile(r'\b(' + '|'.join(map(re.escape, sorted_keys)) + r')\b', re.IGNORECASE)

        def replace_callback(match):
            original = match.group(1)
            # Retrieve replacement (mapping keys are exactly as they appeared in text)
            replacement = mapping.get(original, original)
            
            self.substitution_log.append({
                "original": original,
                "replacement": replacement,
                "span": match.span()
            })
            return replacement

        new_text = pattern.sub(replace_callback, text)
        
        return new_text, self.substitution_log

    def clear_log(self):
        self.substitution_log = []
        # cache persists
class ContentDeduplicator:
    def __init__(self):
        self.seen_hashes = set()
        self.dupe_count = 0

    def is_duplicate(self, text: str) -> bool:
        norm = re.sub(r"\d+", "0", text.lower())
        norm = re.sub(r"[^\w]", "", norm)
        if len(norm) < 10:
            return False
        content_hash = hashlib.md5(norm.encode("utf-8")).hexdigest()
        if content_hash in self.seen_hashes:
            self.dupe_count += 1
            return True
        self.seen_hashes.add(content_hash)
        return False


class ContextScorer:
    def score(self, text: str, label: str) -> int:
        if len(text) > 500: # penalize long text; it may be a table
            return 0
        regex = CATEGORY_CONTEXT_MAP.get(label)
        if not regex:
            return 0
        matches = regex.findall(text)
        unique_hits = set(m.lower() for m in matches)
        score = len(unique_hits) * 10
        if re.search(r"\b(hedg|mitigat|manag)(?:e|es|ed|ing)\b", text, re.I):
            score += 15
        if label == "ir" and re.search(
            r"\b(variable|floating|fixed)\s+rate\b", text, re.I
        ):
            score += 20
        if label == "fx" and re.search(r"\b(foreign rate|exchange rate|denominated)\b", text, re.I):
            score += 20
        if label == "cp" and re.search(r"\b(price|commodity|fuel|oil)\b", text, re.I):
            score += 20
        if label == "eq":
            text_lower = text.lower()
            is_comp_talk = any(
                x in text_lower
                for x in ["employee", "compensation", "vesting", "grant", "award"]
            )
            is_hedging_talk = re.search(
                r"\b(hedg|mitigat|manag|offset)(?:e|es|ed|ing)\b", text, re.I
            )
            is_convertible = re.search(r"\b(?:convertible\s+(?:debt|notes?|bonds?|securit(?:y|ies)))\b", text, re.I)
            is_valuation_model = re.search(r"\b" + "|".join(VALUATION_MODELS) + r"\b", text, re.I)
            if is_valuation_model:
                score += 50
            if is_convertible:
                score += 50
            if is_comp_talk and not is_hedging_talk:
                return -1
            if is_comp_talk and is_hedging_talk:
                score += 25
        return score

    def get_max_score_any_category(self, text: str) -> int:
        scores = [self.score(text, lbl) for lbl in ["fx", "cp", "eq", "ir"]]
        return max(scores)


class AugmentationEngine:
    """Enhanced version with dynamic base substitution."""

    def __init__(self):
        self.generic_terms = [
            "derivatives",
            "instruments",
            "contracts",
            "agreements",
            "hedging arrangements",
            "hedging instruments",
            "hedge contracts",
            "hedges",
            "positions",
        ]
        # Extract bases from regex patterns (remove '?')
        self.bases = [base.replace("?", "") for base in UNAMBIGUOUS_BASE_TYPES]

    def augment(
        self,
        text: str,
        span: tuple,
        match_text: str,
        strategy: str = "dynamic_base",
    ) -> Tuple[str, str]:
        """
        Augment text by replacing matched instrument with a variant.

        Args:
            text: Original text
            span: (start, end) indices of match
            match_text: The matched text
            strategy: "generic", "loose_variant", "dynamic_base", or "stochastic"

        Returns:
            Tuple of (augmented_text, strategy_used)
        """
        start, end = span

        if strategy == "dynamic_base":
            # Try to replace base with semantically similar variant
            base_replacement = _get_dynamic_base(match_text)
            if base_replacement != match_text:
                augmented_text = text[:start] + base_replacement + text[end:]
                return augmented_text, "DynamicBase"
            # Fall through to loose variant if no substitution
            strategy = "loose_variant"

        if strategy == "loose_variant":
            base_form = _get_dynamic_base(match_text)
            suffix = random.choice(["", "contract", "agreement"])
            if suffix:
                replacement_str = f"{base_form} {suffix}"
            else:
                replacement_str = base_form
            augmented_text = text[:start] + replacement_str + text[end:]
            return augmented_text, "LooseVariant_DynamicBase"

        if strategy == "generic":
            replacement = random.choice(self.generic_terms)
            augmented_text = text[:start] + replacement + text[end:]
            return augmented_text, "Generic"

        if strategy == "stochastic":
            # Random choice between strategies
            choice = random.random()
            if choice < 0.3:
                return self.augment(text, span, match_text, strategy="dynamic_base")
            elif choice < 0.6:
                return self.augment(text, span, match_text, strategy="loose_variant")
            else:
                return self.augment(text, span, match_text, strategy="generic")

        return text, "NoChange"


class DynamicContextBank:
    def __init__(self):
        # Store valid sentences to use as "Noise" later
        self.noise_pool = []

    def add_noise_candidate(self, text):
        # Keep pool manageable
        if len(self.noise_pool) < 5000:
            self.noise_pool.append(text)
        elif random.random() < 0.1:  # Random replacement to keep fresh
            self.noise_pool[random.randint(0, 4999)] = text

    def get_noise(self):
        if not self.noise_pool:
            return "See Note X."
        return random.choice(self.noise_pool)


# =============================================================================
# SCRUBBING FUNCTIONS
# =============================================================================


def scrub_non_target_instruments(
    text: str,
    target_category: str,
    all_detected_categories: Set[str],
    keep_same_category_bases: bool = True,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Remove all derivative instruments NOT matching the target category.
    Preserves target category instruments unless aggressive mode is enabled.

    Args:
        text: Original sentence
        target_category: Category to preserve ("ir", "fx", "cp", "eq")
        all_detected_categories: Set of all categories found in text
        keep_same_category_bases: If True, keep multiple same-category instruments
                                  (e.g., keep "caps" when masking "swap" for IR).
                                  If False, remove all but the first.

    Returns:
        Tuple of (cleaned_text, list_of_removed_info)

    Example:
        >>> text = "We use interest rate swaps and FX forwards."
        >>> scrub_non_target_instruments(text, "ir", {"ir", "fx"})
        # Returns: ("We use interest rate swaps and forwards.", [...])
        # Removed FX context but kept both instrument names
    """

    removed_info = []
    cleaned_text = text

    # Identify categories to scrub (all except target)
    categories_to_scrub = all_detected_categories - {target_category, "gen", "other"}

    if not categories_to_scrub:
        return cleaned_text, removed_info

    # For each non-target category, remove its instruments and context
    for scrub_cat in categories_to_scrub:
        if scrub_cat not in CATEGORY_DELETION_MAP:
            continue

        instrument_regex, soft_instrument_regex, context_regex = CATEGORY_DELETION_MAP[scrub_cat]

        # Track what we're removing
        instrument_matches = [
            m.group(0) for m in instrument_regex.finditer(cleaned_text)
        ]
        # Scrub soft mentions not caught by the strict one
        soft_instrument_matches = [
            m.group(0) for m in soft_instrument_regex.finditer(cleaned_text)
        ]
        context_matches = [m.group(0) for m in context_regex.finditer(cleaned_text)]

        if instrument_matches or context_matches or soft_instrument_matches:
            removed_info.append(
                {
                    "category": scrub_cat,
                    "instruments": instrument_matches + soft_instrument_matches,
                    "context_terms": context_matches,
                }
            )

        # Remove cross-category instruments
        cleaned_text = instrument_regex.sub(" ", cleaned_text)

        # Remove cross-category context clues
        cleaned_text = context_regex.sub(" ", cleaned_text)

    # Normalize whitespace and punctuation
    cleaned_text = cleanup_fragment(cleaned_text)

    return cleaned_text, removed_info


def validate_scrubbed_example(
    scrubbed_text: str,
    target_category: str,
    removed_info: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """
    Validate that scrubbing produced a usable training example.

    Checks:
    1. Scrubbed text meets minimum length
    2. Target category instrument still present
    3. Text is non-empty after scrubbing

    Returns:
        Tuple of (is_valid, error_reason_or_none)
    """

    # Check 1: Minimum length
    if len(scrubbed_text) < MIN_SENTENCE_LENGTH:
        return (
            False,
            f"Scrubbed text too short: {len(scrubbed_text)} < {MIN_SENTENCE_LENGTH}",
        )

    # Check 2: Target instrument still present (if specific category)
    if target_category not in {"gen", "other"}:
        target_instrument_regex = CATEGORY_DELETION_MAP[target_category][0] # strict
        target_soft_instrument_regex = CATEGORY_DELETION_MAP[target_category][1] # soft
        if not (target_instrument_regex.search(scrubbed_text) or target_soft_instrument_regex.search(scrubbed_text)):
            return (
                False,
                f"Target category {target_category} instrument lost after scrubbing",
            )

    # Check 3: Text not empty
    if not scrubbed_text.strip():
        return False, "Text became empty after scrubbing"

    return True, None


def prepare_training_example(
    sentence: str,
    target_category: str,
    all_detected_categories: Set[str],
    replacement_strategy: str = "stochastic",
) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """
    Convert a sentence into a training example by:
    1. Scrubbing non-target category instruments/context
    2. Masking the target category instrument
    3. Validating output quality
    """

    # Step 1: Scrub non-target instruments/context
    scrubbed_text, removed = scrub_non_target_instruments(
        sentence,
        target_category,
        all_detected_categories,
        keep_same_category_bases=SCRUBBING_CONFIG["keep_same_category_bases"],
    )

    # Step 2: Validate scrubbed result
    is_valid, error_reason = validate_scrubbed_example(
        scrubbed_text, target_category, removed
    )

    if not is_valid:
        logger.debug(f"Scrubbed example invalid: {error_reason}")
        return None

    # Step 3: Mask the target instrument
    masked_text = scrubbed_text
    replacement_info = {}

    if target_category not in {"gen", "other"}:
        target_instrument_regex = CATEGORY_DELETION_MAP[target_category][0]
        target_soft_instrument_regex = CATEGORY_DELETION_MAP[target_category][1]

        # Search using both to ensure we have a match object to derive the base from
        match = target_instrument_regex.search(
            scrubbed_text
        ) or target_soft_instrument_regex.search(scrubbed_text)
        if not match:
            logger.warning(
                f"Target instrument not found after scrubbing: {target_category}"
            )
            return None

        matched_text = match.group(0)

        # 1. Get the base form (e.g., 'swap')
        base_form = _get_base_form(matched_text, target_category)

        # 2. Apply dynamic substitution
        dynamically_substituted_base = _get_dynamic_base(
            base_form,
            random_seed=random.randint(0, 2**31 - 1),
            substitution_probability=0.25,
        )

        # Apply replacement strategy
        if replacement_strategy == "stochastic":
            rand_val = random.random()
            if rand_val < 0.30:
                replacement = dynamically_substituted_base
                strategy = "base_dynamic"
            elif rand_val < 0.60:
                replacement = _get_base_form(matched_text, target_category)
                strategy = "base"
            else:
                replacement = _get_loose_variant(matched_text, target_category)
                strategy = "loose_variant"

        elif replacement_strategy == "base":
            replacement = dynamically_substituted_base
            strategy = "base_dynamic"
        elif replacement_strategy == "generic":
            replacement = _get_generic_form(target_category)
            strategy = "generic"
        else:
            replacement = matched_text
            strategy = "none"

        replacement_info = {
            "original_instrument": matched_text,
            "replacement": replacement,
            "strategy": strategy,
        }

        # ---------------------------------------------------------
        # STRATEGY: Prioritize Strict Masking, Fallback to Soft
        # ---------------------------------------------------------

        # 1. Try to mask using the STRICT regex (Max Munch)
        masked_text = target_instrument_regex.sub(replacement, scrubbed_text)

        # 2. If Strict failed (count=0), it means we found the instrument
        #    via the Soft regex in the search block above. Mask using Soft anyways
        if target_soft_instrument_regex.search(scrubbed_text):
            masked_text = target_soft_instrument_regex.sub(
                replacement, scrubbed_text
            )
        else:
            # Should be unreachable given the initial check, but safe to keep
            return None

    # Step 4: Final validation
    if len(masked_text) < MIN_SENTENCE_LENGTH:
        logger.debug(f"Masked text too short after replacement")
        return None

    metadata = {
        "removed_categories": removed,
        "replacement_info": replacement_info,
        "scrubbing_applied": bool(removed),
    }

    return (masked_text, target_category, metadata)


# =============================================================================
# REPLACEMENT STRATEGY HELPERS
# =============================================================================
_SAFE_BASES = ["derivative", "hedge"] # Ir swap contract to ir hedge contract
_UNSAFE_BASES = {
    "swaption",
    "straddle",
    "strangle",
    "spread",
}
_SIMILAR_BASES = {
    "swap": ["collar", "swaption"],  # Make collars/swaptions more frequent
    "cap": ["collar", "floor"],  # Less common than cap
    "floor": ["collar", "cap"],  # Less common alone
    "collar": ["swap", "cap",],  # Make other instruments more frequent
    "forward": ["options"],  # Make options appear more often
}
def _normalize_base(base: str) -> str:
    """
    Normalize base for matching (lowercase, remove plural 's').

    Examples:
        "swaps" -> "swap"
        "Forwards" -> "forward"
        "CAPS" -> "cap"
    """
    base_lower = base.lower()
    # Remove trailing 's' if it exists (but not for words that end in 's' naturally)
    if base_lower.endswith("s") and base_lower not in {
        "hedges",
        "locks",
        "futures",
        "options",
    }:
        base_normalized = base_lower[:-1]
    else:
        base_normalized = base_lower

    return base_normalized


def _get_dynamic_base(
    base: str,
    random_seed: Optional[int] = None,
    substitution_probability: float = 0.75,
) -> str:
    """
    Replace a common instrument base with a semantically similar but less common variant.

    Strategy: Increase dataset diversity by replacing frequent bases (swap, cap, forward)
    with less common variants (collar, swaption, option), preventing overfitting to
    common terminology.

    Args:
        base: Instrument base form (e.g., "swap", "swaps", "Swaps")
        random_seed: Optional seed for reproducibility in testing
        substitution_probability: Probability to substitute when alternatives exist (default 0.75)
                                 Higher = more diversity, lower = preserve more originals

    Returns:
        Original base or a less common semantic variant (preserves input case/plurality)

    Examples:
        >>> _get_dynamic_base("swap", random_seed=42)
        "collar"  # Common base replaced with less common variant

        >>> _get_dynamic_base("Swaps", random_seed=42)
        "Collars"

        >>> _get_dynamic_base("swaption")
        "swaption"  # Unsafe, never substituted
    """
    rng = random.Random(random_seed) if random_seed else random

    original_base = base
    is_plural = base.lower().endswith("s") and base.lower() not in {
        "hedges",
        "locks",
        "futures",
        "options",
    }
    is_capitalized = base and base[0].isupper()

    base_normalized = _normalize_base(base)

    # Don't substitute unsafe bases
    if base_normalized in _UNSAFE_BASES:
        return original_base

    # Base not in substitution map
    if base_normalized not in _SIMILAR_BASES:
        return original_base

    alternatives = _SIMILAR_BASES[base_normalized] + _SAFE_BASES

    # No alternatives available
    if not alternatives:
        return original_base

    # Only substitute with configured probability
    if rng.random() < substitution_probability:
        substitute = rng.choice(alternatives)

        # Restore plurality
        if is_plural:
            substitute = substitute + "s"

        # Restore capitalization
        if is_capitalized:
            substitute = substitute.capitalize()

        return substitute

    return original_base


def _get_base_form(matched_text: str, category: str) -> str:
    """
    Extract base instrument form using BASE_REGEX.
    E.g., "interest rate swap agreement" → "swap" or "swaps"
    """
    # BASE_REGEX captures the instrument portion
    match = BASE_REGEX.search(matched_text)
    if match:
        instrument = match.group(0)
        return instrument

    # Fallback: just use last word of original match
    words = matched_text.split()
    return words[-1] if len(words) > 1 else matched_text


def _get_loose_variant(matched_text: str, category: str) -> str:
    """
    Create a loose variant (e.g., "swap" → "swap agreement" or "swap instrument").
    """
    base = _get_base_form(matched_text, category)

    suffixes = ["agreements", "instruments", "contracts", "arrangements"]
    chosen_suffix = random.choice(suffixes)

    return f"{base} {chosen_suffix}"


def _get_generic_form(category: str) -> str:
    """
    Use generic hedging language without category-specific signals.
    """
    generics = [
        "hedging instruments",
        "derivative contracts",
        "financial instruments",
        "hedging agreements",
        "derivative positions",
        "derivatives",
    ]

    return random.choice(generics)


# =============================================================================
# DYNAMIC WINDOW LOGIC
# =============================================================================
def get_dynamic_window(
    sentences,
    target_idx,
    override_target=None,
    context_bank=None,
    apply_numeric_substitution=True,
):
    """
    Constructs a variable-width window with optional dynamic numeric substitution.

    Applies substitution to:
    - Years (with offset preservation)
    - Months (with offset preservation)
    - Other numbers (±5% perturbation)

    Args:
        sentences: List of sentences
        target_idx: Index of target sentence
        override_target: Optional replacement for target sentence
        context_bank: Optional noise injection bank
        apply_numeric_substitution: If True, apply numeric substitution to final window

    Returns:
        Window text with [SEP] tokens
    """
    target_sent = (
        override_target if override_target is not None else sentences[target_idx]
    )

    current_width = random.randint(MIN_WINDOW_SIZE, MAX_WINDOW_SIZE)
    prev_parts = []
    next_parts = []

    for dist in range(1, current_width + 1):
        if target_idx - dist >= 0:
            sent = sentences[target_idx - dist]
            noise_prob = 0.0
            if dist == 2:
                noise_prob = 0.2
            if dist >= 3:
                noise_prob = 0.5

            if context_bank and random.random() < noise_prob:
                sent = context_bank.get_noise()

            prev_parts.insert(0, sent)

        if target_idx + dist < len(sentences):
            sent = sentences[target_idx + dist]
            noise_prob = 0.0
            if dist == 2:
                noise_prob = 0.2
            if dist >= 3:
                noise_prob = 0.5

            if context_bank and random.random() < noise_prob:
                sent = context_bank.get_noise()

            next_parts.append(sent)

    prev_block = " ".join(prev_parts)
    next_block = " ".join(next_parts)

    window = f"{prev_block}<<>>{target_sent}<<>>{next_block}"

    # Inside get_dynamic_window, after building window string:
    if apply_numeric_substitution and NUMERIC_SUBSTITUTION_CONFIG["enabled"]:
        all_sentences = prev_parts + [target_sent] + next_parts

        # Extract info
        engine = NumericSubstitutionEngine()
        month_info, all_months = engine.extract_sentence_months(all_sentences)
        year_info, all_years = engine.extract_sentence_years(all_sentences)

        # Build mappings
        if all_years:
            engine.build_year_mapping(year_info, all_years)
        if all_months:
            engine.build_month_mapping(month_info, all_months)

        # Apply all substitutions
        window = engine.substitute_all(window)

        # Currency substitution (the )
        curr_sub = DynamicCurrencySubstitution()
        window, _ = curr_sub.substitute_all(window)
        
    window.replace("<<>>", SEP_TOKEN)

    return window


def has_conflict(text, label):
    for regex in LABEL_TO_CONFLICT_REGEX.get(label, []):
        if regex.search(text):
            return True
    return False


# =============================================================================
# ENHANCED PROCESSING WITH SCRUBBING
# =============================================================================


def process_chunk(chunk_data):
    import time

    random.seed(os.getpid() + time.time())
    scorer = ContextScorer()
    augmenter_dummy = AugmentationEngine()
    local_candidates = []
    local_noise = []

    for url, matches_json in chunk_data:
        try:
            paragraphs = json.loads(matches_json)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON for URL {url}: {e}")
            continue
        if not isinstance(paragraphs, list):
            continue

        for para in paragraphs:
            if "<TABLE>" in para:
                continue

            if not (
                STRICT_REGEX.search(para)
                or HEDGING_CONTEXT_REGEX.search(para)
                or EXCLUDE_REGEX_ACCOUNTING_STD.search(para)
            ):
                continue

            sentences = [
                s.strip()
                for s in SENTENCE_SPLIT_PATTERN.split(para)
                if len(s.strip()) >= MIN_SENTENCE_LENGTH
            ]

            if len(sentences) > 2:
                local_noise.append(random.choice(sentences))

            for i, sentence in enumerate(sentences):
                match = STRICT_REGEX.search(sentence)

                # --- Branch A: Strict Match ---
                if match:
                    cats = get_sentence_categories(sentence)
                    specific_cats = cats - {"gen", "other"}

                    if len(specific_cats) == 1:
                        label = list(specific_cats)[0]

                        target_sent = sentences[i]
                        blanked_target = (
                            target_sent[: match.start()]
                            + "       "
                            + target_sent[match.end() :]
                        )
                        validation_text = get_dynamic_window(
                            sentences, i, override_target=blanked_target
                        )

                        score = (
                            -1
                            if has_conflict(validation_text, label)
                            else scorer.score(validation_text, label)
                        )

                        local_candidates.append(
                            {
                                "label": label,
                                "sentences": sentences,
                                "target_idx": i,
                                "match_span": match.span(),
                                "match_text": match.group(0),
                                "original_sent": sentence,
                                "score": score,
                                "url": url,
                                "detected_categories": cats,
                            }
                        )

                    elif len(specific_cats) == 0:
                        full_window = get_dynamic_window(sentences, i)
                        max_score = scorer.get_max_score_any_category(full_window)
                        if max_score < 10:
                            local_candidates.append(
                                {
                                    "label": "gen",
                                    "sentences": sentences,
                                    "target_idx": i,
                                    "match_span": match.span(),
                                    "match_text": match.group(0),
                                    "original_sent": sentence,
                                    "score": 0,
                                    "url": url,
                                    "subtype": "L0_Ambiguous_Instrument",
                                    "detected_categories": cats,
                                }
                            )

                # --- Branch B: No Strict Match ---
                else:
                    is_hedging_talk = bool(HEDGING_CONTEXT_REGEX.search(sentence))
                    is_accounting = bool(EXCLUDE_REGEX_ACCOUNTING_STD.search(sentence))

                    if is_hedging_talk or is_accounting:
                        cats = get_sentence_categories(sentence)
                        specific_cats = cats - {"gen", "other"}

                        if len(specific_cats) == 0:
                            if VERB_USE_REGEX.search(sentence) and GEN_REGEX.search(sentence): # We use derivatives within the boilerplate
                                continue 
                            full_window = get_dynamic_window(sentences, i)
                            max_score = scorer.get_max_score_any_category(full_window)

                            if max_score < 10:
                                subtype = (
                                    "L0_Accounting"
                                    if is_accounting
                                    else "L0_Risk_Policy"
                                )
                                local_candidates.append(
                                    {
                                        "label": "gen",
                                        "sentences": sentences,
                                        "target_idx": i,
                                        "match_span": None,
                                        "match_text": "None",
                                        "original_sent": sentence,
                                        "score": 0,
                                        "url": url,
                                        "subtype": subtype,
                                        "detected_categories": cats,
                                    }
                                )

    return local_candidates, local_noise


# =============================================================================
# MAIN GENERATION WITH SCRUBBING
# =============================================================================


def create_labeled_dataset():
    print(f"🚀 Starting Dataset Generation v17 (Scrubbing + Masking)")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT count(*) FROM webpage_result WHERE matches IS NOT NULL")
        total_rows = cursor.fetchone()[0]
    except:
        total_rows = 0
    print(f"   Source DB Rows: {total_rows:,}")

    df_iter = pd.read_sql_query(
        "SELECT url, matches FROM webpage_result WHERE matches IS NOT NULL",
        conn,
        chunksize=CHUNK_SIZE,
    )

    global_candidates = defaultdict(list)
    context_bank = DynamicContextBank()
    augmenter = AugmentationEngine()
    deduplicator = ContentDeduplicator()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        future_sizes = {}
        iterator = iter(df_iter)
        active = True

        with tqdm(total=total_rows, desc="Scanning DB", unit="rows") as pbar:
            while active or futures:
                while len(futures) < MAX_WORKERS * 2 and active:
                    try:
                        chunk = next(iterator)
                        chunk_data = list(zip(chunk["url"], chunk["matches"]))
                        ft = executor.submit(process_chunk, chunk_data)
                        futures.append(ft)
                        future_sizes[ft] = len(chunk)
                    except StopIteration:
                        active = False

                if not futures:
                    break

                import concurrent.futures

                done, _ = concurrent.futures.wait(
                    futures, return_when=concurrent.futures.FIRST_COMPLETED
                )

                for future in done:
                    futures.remove(future)
                    pbar.update(future_sizes.pop(future, 0))
                    try:
                        candidates, noise_samples = future.result()

                        for n in noise_samples:
                            context_bank.add_noise_candidate(n)

                        for c in candidates:
                            if not deduplicator.is_duplicate(c["original_sent"]):
                                global_candidates[c["label"]].append(c)

                        pbar.set_postfix(
                            {k: len(v) for k, v in global_candidates.items()}
                        )
                    except Exception as e:
                        pbar.write(f"Error: {e}")
    conn.close()
    print(f"   🚫 Deduped {deduplicator.dupe_count:,} redundant sentences.")

    # --- PHASE 2: GENERATION WITH SCRUBBING ---
    print("\n🏆 PASS 2: Generating Dataset with Scrubbing & Masking...")
    final_data = []
    stats = Counter()
    scrubbing_stats = Counter()

    for label, items in global_candidates.items():
        if label == "gen":
            random.shuffle(items)
        else:
            items.sort(key=lambda x: x["score"], reverse=True)

        for item in tqdm(items, desc=f"Generating {label}", leave=False):
            if stats[label] >= TARGET_SAMPLES_PER_CLASS:
                break

            sentences = item["sentences"]
            idx = item["target_idx"]
            orig = item["original_sent"]
            score = item.get("score", 0)
            url = item["url"]
            detected_cats = item.get("detected_categories", {label})

            row = {
                "text": "",
                "label": label,
                "difficulty": "",
                "debug_original": orig,
                "debug_score": score,
                "debug_hint": "None",
                "scrubbing_applied": False,
            }

            if label == "gen":
                row["text"] = get_dynamic_window(
                    sentences, idx, context_bank=context_bank
                )
                row["difficulty"] = item.get("subtype", "L0_Ambiguous")

            elif score == -1:
                row["text"] = get_dynamic_window(
                    sentences, idx, context_bank=context_bank
                )
                row["difficulty"] = "L4_Natural_Adverse"

            elif score >= 20:
                # Use scrubbing + masking approach
                prep_result = prepare_training_example(
                    orig, label, detected_cats, replacement_strategy="stochastic"
                )

                if prep_result:
                    masked_text, _, metadata = prep_result
                    row["text"] = get_dynamic_window(
                        sentences,
                        idx,
                        override_target=masked_text,
                        context_bank=context_bank,
                    )
                    row["difficulty"] = "L2_Masked_Scrubbed"
                    row["scrubbing_applied"] = metadata["scrubbing_applied"]
                    scrubbing_stats["L2_scrubbed"] += 1
                else:
                    # Fallback to old method if scrubbing fails
                    match_span = item["match_span"]
                    match_text = item["match_text"]
                    aug, _ = augmenter.augment(orig, match_span, match_text)
                    row["text"] = get_dynamic_window(
                        sentences, idx, override_target=aug, context_bank=context_bank
                    )
                    row["difficulty"] = "L2_Masked"
                    scrubbing_stats["L2_fallback"] += 1

            elif score > 0:
                # L1 Weak context
                prep_result = prepare_training_example(
                    orig, label, detected_cats, replacement_strategy="base"
                )

                if prep_result:
                    masked_text, _, metadata = prep_result
                    row["text"] = get_dynamic_window(
                        sentences,
                        idx,
                        override_target=masked_text,
                        context_bank=context_bank,
                    )
                    row["difficulty"] = "L1_WeakContext_Scrubbed"
                    row["scrubbing_applied"] = metadata["scrubbing_applied"]
                    scrubbing_stats["L1_scrubbed"] += 1
                else:
                    row["text"] = get_dynamic_window(
                        sentences, idx, context_bank=context_bank
                    )
                    row["difficulty"] = "L1_WeakContext"
                    scrubbing_stats["L1_unscrubbed"] += 1

            else:
                row["text"] = get_dynamic_window(
                    sentences, idx, context_bank=context_bank
                )
                row["difficulty"] = "L1_NoContext"

            final_data.append(row)
            stats[label] += 1

    df = pd.DataFrame(final_data)
    print("\n📊 Final Distribution:")
    print(df["label"].value_counts())
    print("\n🧹 Scrubbing Statistics:")
    print(dict(scrubbing_stats))
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    mp.freeze_support()

    create_labeled_dataset()
