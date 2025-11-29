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
    CR_REGEX,
    CR_SOFT_REGEX,
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
    CR_CONTEXT_REGEX,
    HEDGING_CONTEXT_REGEX,
    EXCLUDE_REGEX_ACCOUNTING_STD,
    CATEGORY_DELETION_MAP,
    VALUATION_MODELS,
    Currency,
    cleanup_fragment,
    VERB_USE_REGEX,
    all_currencies,  # dynamic currency subsitution
    STRICT_CONTEXT_MAP,
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
L4_ADVERSE_RATIO = 0.2
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
COUNTERPARTY_POLICY_TERMS = [
    r"counterpart(?:y|ies)",
    r"credit\s+quality",
    r"credit\s+worthiness",
    r"highly[- ]rated",
    r"investment[- ]grade",
    r"financial\s+institutions",
    r"master\s+netting",
    r"isda",
    r"collateral\s+requirements",
    r"concentration\s+of\s+credit",
    r"non[- ]performance",
]

COUNTERPARTY_REGEX = re.compile(
    r"\b" + r"|".join(COUNTERPARTY_POLICY_TERMS) + r"\b", re.IGNORECASE
)
YEAR_REGEX_COLLECTOR = re.compile(r"\b(19[0-9]{2}|20[0-9]{2})\b")
NON_YEAR_NUMBER_REGEX = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\b")


LABEL_TO_CONFLICT_REGEX = {
    "ir": [
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        CR_CONTEXT_REGEX,
        FX_REGEX,
        FX_SOFT_REGEX,
        CP_REGEX,
        CP_SOFT_REGEX,
        EQ_REGEX,
        EQ_SOFT_REGEX,
        CR_REGEX,
        CR_SOFT_REGEX,
    ],
    "fx": [
        IR_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        CR_CONTEXT_REGEX,
        IR_REGEX,
        IR_SOFT_REGEX,
        CP_REGEX,
        CP_SOFT_REGEX,
        EQ_REGEX,
        EQ_SOFT_REGEX,
        CR_REGEX,
        CR_SOFT_REGEX,
    ],
    "cp": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        CR_CONTEXT_REGEX,
        IR_REGEX,
        IR_SOFT_REGEX,
        FX_REGEX,
        FX_SOFT_REGEX,
        EQ_REGEX,
        EQ_SOFT_REGEX,
        CR_REGEX,
        CR_SOFT_REGEX,
    ],
    "eq": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        CR_CONTEXT_REGEX,
        IR_REGEX,
        IR_SOFT_REGEX,
        FX_REGEX,
        FX_SOFT_REGEX,
        CP_REGEX,
        CP_SOFT_REGEX,
        CR_REGEX,
        CR_SOFT_REGEX,
    ],
    "gen": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        CR_CONTEXT_REGEX,
        IR_REGEX,
        IR_SOFT_REGEX,
        FX_REGEX,
        FX_SOFT_REGEX,
        CP_REGEX,
        CP_SOFT_REGEX,
        EQ_REGEX,
        EQ_SOFT_REGEX,
        CR_REGEX,
        CR_SOFT_REGEX,
    ],
    "cr": [
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

MONTH_NUMBER_TO_NAME = {v: k for k, v in MONTH_NAMES.items()}
MONTH_NUMBER_TO_ABBREV = {v: k for k, v in MONTH_ABBREVIATIONS.items()}

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
        self.config = config or NUMERIC_SUBSTITUTION_CONFIG
        self.rng = random.Random(random_seed) if random_seed else random
        self.substitution_log = []
        self.year_mapping = {}
        self.month_mapping = {}
        self.base_year = None
        self.base_month = None

    # ========== MONTH EXTRACTION & SUBSTITUTION ==========

    def extract_sentence_months(self, sentences: List[str]):
        """
        Extract months, skipping lowercase 'may' (modal verb).
        """
        sentence_month_info = {}
        all_months = set()

        for idx, sent in enumerate(sentences):
            months = []
            for match in MONTH_REGEX.finditer(sent):
                raw_str = match.group(1)
                month_str = raw_str.lower()

                # FIX: Skip 'may' if it is not capitalized (likely a modal verb)
                if month_str == "may" and not raw_str[0].isupper():
                    continue

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
        if not all_months:
            return None
        return self.rng.choice(list(all_months))

    def build_month_mapping(self, sentence_month_info, all_months):
        if not all_months:
            self.month_mapping = {}
            return

        self.base_month = self.pick_base_month(all_months)
        if not self.base_month:
            self.month_mapping = {}
            return

        for sent_idx, month_info in sentence_month_info.items():
            offsets = month_info["offsets"]
            for month, offset in offsets.items():
                replacement_month = self.base_month + offset
                replacement_month = ((replacement_month - 1) % 12) + 1
                self.month_mapping[month] = replacement_month

    def substitute_months_in_text(self, text):
        """
        Replace months, ensuring 'may' (verb) is not touched.
        """
        if not self.month_mapping:
            return text

        def replace_month(match):
            raw_str = match.group(1)
            original_month_str = raw_str.lower()

            if original_month_str == "may" and not raw_str[0].isupper():
                return match.group(0)

            original_month_num = MONTH_NAMES.get(
                original_month_str
            ) or MONTH_ABBREVIATIONS.get(original_month_str)

            if original_month_num is None:
                return match.group(0)

            replacement_month_num = self.month_mapping.get(
                original_month_num, original_month_num
            )

            is_abbrev = original_month_str in MONTH_ABBREVIATIONS
            is_capitalized = raw_str[0].isupper()

            if is_abbrev:
                replacement_str = MONTH_NUMBER_TO_ABBREV[replacement_month_num]
            else:
                replacement_str = MONTH_NUMBER_TO_NAME[replacement_month_num]

            if is_capitalized:
                replacement_str = replacement_str.capitalize()

            self.substitution_log.append(
                {
                    "type": "month",
                    "original": raw_str,
                    "replacement": replacement_str,
                    "span": match.span(),
                }
            )

            return replacement_str

        return MONTH_REGEX.sub(replace_month, text)

    # ========== YEAR & NUMBER METHODS ==========

    def extract_sentence_years(self, sentences: List[str]):
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
        if not all_years:
            return None
        return self.rng.choice(list(all_years))

    def build_year_mapping(self, sentence_year_info, all_years):
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
        text = self.substitute_years_in_text(text)
        text = self.substitute_months_in_text(text)
        text = self.substitute_numbers_in_text(text)
        return text

    @staticmethod
    def _count_decimals(num_str):
        num_str = num_str.strip()
        if "." not in num_str:
            return 0
        if "e" in num_str.lower():
            return 2
        return len(num_str.split(".")[1])

    def clear_log(self):
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
        maps = {
            "name": {c.full_name.lower(): c for c in self.currency_pool},
            "location": {c.location.lower(): c for c in self.currency_pool},
            "code": {c.code.upper(): c for c in self.currency_pool}, # Codes are usually UPPER
            "adjective": {c.adjective.lower(): c for c in self.currency_pool},
        }

        for match in patterns["name"].finditer(text):
            original = match.group(1)
            curr = maps["name"].get(original.lower())
            if curr:
                detected["name"].append((original, curr))

        # 2. Locations
        for match in patterns["location"].finditer(text):
            original = match.group(1)
            curr = maps["location"].get(original.lower())
            if curr:
                detected["location"].append((original, curr))

        # 3. Codes
        for match in patterns["code"].finditer(text):
            original = match.group(1)
            curr = maps["code"].get(original.upper())
            if curr:
                detected["code"].append((original, curr))

        for match in patterns["adjective"].finditer(text):
            original = match.group(1)
            curr = maps["adjective"].get(original.lower())
            if curr:
                detected["adjective"].append((original, curr))

        return detected

    def _match_case(self, original: str, replacement: str) -> str:
        """Helper to match capitalization of the original text."""
        if original.isupper():
            return replacement.upper()
        if original.islower():
            return replacement.lower()
        if original[0].isupper():
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
        available = [
            c for c in self.currency_pool if c.code not in unique_detected_codes
        ]

        if len(available) < n_needed:
            available = self.currency_pool

        replacements = self.rng.sample(available, min(n_needed, len(available)))

        code_map = {}
        detected_list = list(unique_detected_codes)
        for i, original_code in enumerate(detected_list):
            if i < len(replacements):
                code_map[original_code] = replacements[i]

        text_mapping = {}
        for det_type, items in detected.items():
            for original_text, currency in items:
                new_curr = code_map.get(currency.code)
                if not new_curr:
                    continue

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

                final_replacement = self._match_case(original_text, raw_replacement)
                text_mapping[original_text] = final_replacement

        return text_mapping

    def substitute_all(self, text: str) -> Tuple[str, List[Dict]]:
        self.substitution_log = []
        detected = self.detect_currencies(text)
        if not any(detected.values()):
            return text, []

        mapping = self.build_text_mapping(detected)
        if not mapping:
            return text, []

        sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
        pattern = re.compile(
            r"\b(" + "|".join(map(re.escape, sorted_keys)) + r")\b", re.IGNORECASE
        )

        def replace_callback(match):
            original = match.group(1)
            replacement = mapping.get(original, original)
            self.substitution_log.append(
                {
                    "original": original,
                    "replacement": replacement,
                    "span": match.span(),
                }
            )
            return replacement

        new_text = pattern.sub(replace_callback, text) # type: ignore
        return new_text, self.substitution_log


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


class DynamicEntitySubstitution:
    """
    Substitutes specific accounting entities (FASB, SEC) and standard references (ASC, IFRS)
    with generic or alternative names to prevent overfitting to specific regulatory bodies.
    """

    def __init__(self, random_seed=None):
        self.rng = random.Random(random_seed) if random_seed else random

        # Targets to find
        self.target_issuers = [
            "FASB",
            "IASB",
            "SEC",
            "Securities and Exchange Commission",
            "Financial Accounting Standards Board",
        ]
        self.target_standards = [
            "ASC",
            "ASU",
            "IFRS",
            "IAS",
            "GAAP",
            "SFAS",
            "EITF",
            "Accounting Standards Codification",
        ]

        # Replacements
        self.generic_issuers = [
            "The Board",
            "The Authority",
            "The Council",
            "Regulatory Body",
            "The Commission",
            "Standards Committee",
            "The Agency",
            "Oversight Board",
        ]
        self.generic_standards = [
            "Standard",
            "Topic",
            "Guidance",
            "Regulation",
            "Rule",
            "Section",
            "Protocol",
            "Framework",
            "Provision",
            "Requirement",
        ]

        # Build Regex for fast detection
        self.issuer_pattern = re.compile(
            r"\b(" + "|".join(map(re.escape, self.target_issuers)) + r")\b"
        )
        self.standard_pattern = re.compile(
            r"\b(" + "|".join(map(re.escape, self.target_standards)) + r")\b"
        )

    def substitute(self, text: str) -> str:
        # Create a consistent mapping for this specific text window
        # (e.g. if FASB appears twice, map it to the same generic name both times)

        mapping = {}

        # 1. Find and map Issuers
        found_issuers = set(self.issuer_pattern.findall(text))
        if found_issuers:
            # Shuffle replacements to ensure diversity
            replacements = self.rng.sample(
                self.generic_issuers, len(self.generic_issuers)
            )
            for i, original in enumerate(found_issuers):
                mapping[original] = replacements[i % len(replacements)]

        # 2. Find and map Standards
        found_standards = set(self.standard_pattern.findall(text))
        if found_standards:
            replacements = self.rng.sample(
                self.generic_standards, len(self.generic_standards)
            )
            for i, original in enumerate(found_standards):
                mapping[original] = replacements[i % len(replacements)]

        if not mapping:
            return text

        # 3. Apply substitution
        # Sort keys by length (descending) to handle subsets (e.g. avoid partial match issues)
        pattern = re.compile(
            r"\b("
            + "|".join(map(re.escape, sorted(mapping.keys(), key=len, reverse=True)))
            + r")\b"
        )

        return pattern.sub(lambda m: mapping[m.group(1)], text)


class ContextScorer:
    def score(self, text: str, label: str) -> int:
        if len(text) > 600 or len(text) < 25:
            return -2
        # 0. Check instrument context (most accurate)
        _, instr_regex, _ = CATEGORY_DELETION_MAP.get(label, (None, None, None))
        if instr_regex:
            if instr_regex.search(text):
                return 100
        # 1. Check STRICT Context (The "Smoking Gun")
        strict_regex = STRICT_CONTEXT_MAP.get(label)
        if strict_regex and strict_regex.search(text):
            return 100

        # 2. Check Standard Context
        regex = CATEGORY_CONTEXT_MAP.get(label)
        if not regex:
            return 0

        matches = regex.findall(text)
        unique_hits = set(m.lower() for m in matches)
        score = len(unique_hits) * 15

        # 3. Context Boosters
        if re.search(r"\b(hedg|mitigat|manag)(?:e|es|ed|ing)\b", text, re.I):
            score += 15
        if label == "cr": # cr is highy specific
            score +=20
        if label == "ir":
            if re.search(r"\b(variable|floating|fixed)\s+rate\b", text, re.I):
                score += 10
            if re.search(
                r"\b(mortages?|basis\s+points?)\b",
                text,
                re.I,
            ):
                score += 10

        if label == "fx" and re.search(
            r"\b(foreign rate|exchange rate|denominated)\b", text, re.I
        ):
            score += 30

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
            is_convertible = re.search(
                r"\b(?:convertible\s+(?:debt|notes?|bonds?|securit(?:y|ies)))\b",
                text,
                re.I,
            )
            is_valuation_model = re.search(
                r"\b" + "|".join(VALUATION_MODELS) + r"\b", text, re.I
            )

            if is_valuation_model:
                score += 50
            if is_convertible:
                score += 50
            if is_comp_talk and not is_hedging_talk:
                return -1
            if is_comp_talk and is_hedging_talk:
                score += 25

        return score

    def get_best_category(self, text: str) -> Tuple[str, int]:
        scores = {
            lbl: self.score(text, lbl)
            for lbl in [
                "cr" ,
                "fx",
                "cp",
                "eq",
                "ir",
            ]
        }
        best_cat = max(scores, key=scores.get) # type: ignore
        best_score = scores[best_cat]
        return best_cat, best_score

    def get_max_score_any_category(self, text: str) -> int:
        _, score = self.get_best_category(text)
        return score


class AugmentationEngine:
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
            base_replacement = _get_dynamic_base(match_text)
            if base_replacement != match_text:
                augmented_text = text[:start] + base_replacement + text[end:]
                return augmented_text, "DynamicBase"
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
            choice = random.random()
            if choice < 0.3:
                return self.augment(text, span, match_text, strategy="dynamic_base")
            elif choice < 0.6:
                return self.augment(text, span, match_text, strategy="loose_variant")
            else:
                return self.augment(text, span, match_text, strategy="generic")

        return text, "NoChange"

def detect_noise_categories(text: str) -> Set[str]:
    """
    Scans text for specific category signals.
    Returns a set of categories found: {'ir', 'fx', 'cp', 'eq'}
    If empty, the text is 'Safe' (Generic).
    """
    found_cats = set()
    for cat, (strict_inst, soft_inst, context_regex) in CATEGORY_DELETION_MAP.items():
        if soft_inst.search(text) or context_regex.search(text) or strict_inst.search(text):
            found_cats.add(cat)
    for cat, regex in STRICT_CONTEXT_MAP.items():
        if regex.search(text):
            found_cats.add(cat)
    return found_cats


class DynamicContextBank:
    def __init__(self):
        self.general_pool = []
        self.safe_pool = []
        self.safe_specific_pool = []
        self.category_pools = {"cr":[], "ir": [], "fx": [], "cp": [], "eq": [], "ctr": []}

    def add_noise_candidate(self, text):
        detected_cats = detect_noise_categories(text)
        if len(self.general_pool) < 5000:
            self.general_pool.append(text)
        elif random.random() < 0.1:
            self.general_pool[random.randint(0, 4999)] = text

        if not detected_cats:
            if len(self.safe_pool) < 2500:
                self.safe_pool.append(text)
            elif random.random() < 0.1:
                self.safe_pool[random.randint(0, 2499)] = text
        else:
            for cat in detected_cats:
                if cat in self.category_pools:
                    pool = self.category_pools[cat]
                    if len(pool) < 1000:
                        pool.append(text)
                    elif random.random() < 0.1:
                        pool[random.randint(0, 999)] = text

    def get_noise(self, target_label: Optional[str] = None) -> str:
        """
        Retrieves contextually appropriate noise.

        - gen -> Safe Pool
        - ir/fx/etc -> Specific Pool (fallback to General)
        """
        # Case A: Generic / Ambiguous (Needs PURE noise)
        if target_label == "gen":
            if random.random() < 0.15:
                if self.safe_specific_pool: # choose one of the "counter categories", which are sentences that seem related to a category but it is not
                    return random.choice(self.safe_specific_pool)
            if self.safe_pool:
                return random.choice(self.safe_pool)
            return "See Note X."

        if target_label in self.category_pools:
            specific_pool = self.category_pools[target_label]
            if specific_pool and random.random() < 0.7:
                return random.choice(specific_pool)

        if self.category_pools and random.random() < 0.7:
            random_cat = random.choice(list(self.category_pools.keys()))
            return self.get_noise(random_cat)

        if self.general_pool:
            return random.choice(self.general_pool)

        return "See Note X."


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
        target_category: Category to preserve ("cr", "ir", "fx", "cp", "eq")
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
    categories_to_scrub = all_detected_categories - {target_category, "gen", "other"}

    if not categories_to_scrub:
        return cleaned_text, removed_info

    for scrub_cat in categories_to_scrub:
        if scrub_cat not in CATEGORY_DELETION_MAP:
            continue
        instrument_regex, soft_instrument_regex, context_regex = CATEGORY_DELETION_MAP[
            scrub_cat
        ]
        strict_context_regex = STRICT_CONTEXT_MAP[scrub_cat]
        
        instrument_matches = [
            m.group(0) for m in instrument_regex.finditer(cleaned_text)
        ]
        soft_instrument_matches = [
            m.group(0) for m in soft_instrument_regex.finditer(cleaned_text)
        ]
        context_matches = [m.group(0) for m in context_regex.finditer(cleaned_text)]
        strict_content_matches = [
            m.group(0) for m in strict_context_regex.finditer(cleaned_text)
        ]

        if instrument_matches or context_matches or soft_instrument_matches or strict_content_matches:
            removed_info.append(
                {
                    "category": scrub_cat,
                    "instruments": instrument_matches + soft_instrument_matches,
                    "context_terms": context_matches + strict_content_matches,
                }
            )
        cleaned_text = instrument_regex.sub(" ", cleaned_text)
        cleaned_text = context_regex.sub(" ", cleaned_text)
        cleaned_text = soft_instrument_regex.sub(" ", cleaned_text)
        cleaned_text = strict_context_regex.sub(" ", cleaned_text)

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
        return (False, "Too Short")

    if target_category not in {"gen", "other"}:
        target_instrument_regex = CATEGORY_DELETION_MAP[target_category][0]
        target_soft_instrument_regex = CATEGORY_DELETION_MAP[target_category][1]
        if not (
            target_instrument_regex.search(scrubbed_text)
            or target_soft_instrument_regex.search(scrubbed_text)
        ):
            return (False, "Target Lost")

    if not scrubbed_text.strip():
        return False, "Empty Text"

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

    is_valid, _ = validate_scrubbed_example(scrubbed_text, target_category, removed)
    if not is_valid:
        return None

    masked_text = scrubbed_text
    replacement_info = {}

    if target_category not in {"gen", "other"}:
        target_instrument_regex = CATEGORY_DELETION_MAP[target_category][0]
        target_soft_instrument_regex = CATEGORY_DELETION_MAP[target_category][1]
        match = target_instrument_regex.search(
            scrubbed_text
        ) or target_soft_instrument_regex.search(scrubbed_text)

        if not match:
            return None

        matched_text = match.group(0)
        base_form = _get_base_form(matched_text, target_category)
        dynamically_substituted_base = _get_dynamic_base(
            base_form,
            random_seed=random.randint(0, 2**31 - 1),
            substitution_probability=0.25,
        )

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

        masked_text = target_instrument_regex.sub(replacement, scrubbed_text)
        if target_soft_instrument_regex.search(scrubbed_text):
            masked_text = target_soft_instrument_regex.sub(
                replacement, scrubbed_text
            )
        else:
            # Fallback if strict replacement didn't happen but soft exists
            pass
        if masked_text == scrubbed_text:
            return None  # Fail this example rather than leaking the label

    if len(masked_text) < MIN_SENTENCE_LENGTH:
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
_SAFE_BASES = ["derivative", "hedge"]
_UNSAFE_BASES = {
    "swaption",
    "straddle",
    "strangle",
    "spread",
}
_SIMILAR_BASES = {
    "swap": ["collar", "swaption"],
    "cap": ["collar", "floor"],
    "floor": ["collar", "cap"],
    "collar": ["swap", "cap"],
    "forward": ["options"],
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

    if base_normalized in _UNSAFE_BASES:
        return original_base
    if base_normalized not in _SIMILAR_BASES:
        return original_base

    alternatives = _SIMILAR_BASES[base_normalized] + _SAFE_BASES
    if not alternatives:
        return original_base

    if rng.random() < substitution_probability:
        substitute = rng.choice(alternatives)
        if is_plural:
            substitute = substitute + "s"
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
    generics = [
        "hedging instruments",
        "derivative contracts",
        "financial instruments",
        "hedging agreements",
        "hedge contracts",
        "derivative positions",
        "derivatives",
        "embedded derivatives",
    ]
    return random.choice(generics)


# =============================================================================
# DYNAMIC WINDOW LOGIC
# =============================================================================

def is_category_specific(text: str) -> bool:
    """
    Returns True if the text contains strong signals for IR, FX, CP, or EQ.
    Used to prevent injecting specific noise into 'gen' examples.
    """
    # 1. Check Instrument & Context Regexes from Deletion Map
    for cat, (strict_inst, soft_inst, context_regex) in CATEGORY_DELETION_MAP.items():
        # We check strict instruments and explicit context.
        # We typically skip soft_inst here to be slightly permissive with vague words,
        # but if you want 100% purity, include soft_inst.search(text) as well.
        if soft_inst.search(text) or context_regex.search(text):
            return True

    # 2. Check Strict Context Map (The "Smoking Guns")
    for cat, regex in STRICT_CONTEXT_MAP.items():
        if regex.search(text):
            return True

    return False


def get_dynamic_window(
    sentences,
    target_idx,
    label=None,
    override_target=None,
    context_bank=None,
    apply_numeric_substitution=True,
):
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

            is_toxic_neighbor = False
            if label == "gen":
                cats = detect_noise_categories(sent)
                if cats:
                    is_toxic_neighbor = True

            should_swap = is_toxic_neighbor or (random.random() < noise_prob)

            if context_bank and should_swap:
                sent = context_bank.get_noise(target_label=label)

            prev_parts.insert(0, sent)

        if target_idx + dist < len(sentences):
            sent = sentences[target_idx + dist]

            noise_prob = 0.0
            if dist == 2:
                noise_prob = 0.2
            if dist >= 3:
                noise_prob = 0.5

            is_toxic_neighbor = False
            if label == "gen":
                cats = detect_noise_categories(sent)
                if cats:
                    is_toxic_neighbor = True

            should_swap = is_toxic_neighbor or (random.random() < noise_prob)

            if context_bank and should_swap:
                sent = context_bank.get_noise(target_label=label)

            next_parts.append(sent)

    prev_block = " ".join(prev_parts)
    next_block = " ".join(next_parts)

    window = f"{prev_block}<<>>{target_sent}<<>>{next_block}"

    if apply_numeric_substitution and NUMERIC_SUBSTITUTION_CONFIG["enabled"]:
        all_sentences = prev_parts + [target_sent] + next_parts
        engine = NumericSubstitutionEngine()
        entity_sub = DynamicEntitySubstitution()
        window = entity_sub.substitute(window)
        month_info, all_months = engine.extract_sentence_months(all_sentences)
        year_info, all_years = engine.extract_sentence_years(all_sentences)

        if all_years:
            engine.build_year_mapping(year_info, all_years)
        if all_months:
            engine.build_month_mapping(month_info, all_months)

        window = engine.substitute_all(window)

        curr_sub = DynamicCurrencySubstitution()
        window, _ = curr_sub.substitute_all(window)

    window = re.sub("<<>>", SEP_TOKEN, window)
    return window


def has_conflict(text, label):
    for regex in LABEL_TO_CONFLICT_REGEX.get(label, []):
        if regex.search(text):
            return True
    return False


def get_hostile_window(sentences, target_idx, target_label, context_bank):
    """
    Build context window with ONLY hostile signals, using variable geometry.

    Structure Variants:
    1. Sandwich: [Hostile] [SEP] [Target] [SEP] [Hostile] (Standard)
    2. Buried:   [Hostile] [SEP] [Hostile] [SEP] [Target] (Left-heavy)
    3. Leading:  [Target] [SEP] [Hostile] [SEP] [Hostile] (Right-heavy)
    """

    available_cats = ["ir", "fx", "cp", "eq", "cr"]
    hostile_pool = [c for c in available_cats if c != target_label]

    # 1. Determine Geometry (Randomize structure so position isn't a cheat)
    # Weights favors "sandwich" slightly as it's the hardest (conflicts on both sides)
    structure_type = random.choices(
        ["sandwich", "left_heavy", "right_heavy"], weights=[0.5, 0.25, 0.25]
    )[0]

    prev_noise_sents = []
    next_noise_sents = []
    conflict_meta = {"prev_conflicts": [], "next_conflicts": []}

    # Helper to get unique hostile category (try not to repeat immediate neighbors)
    def get_hostile_cat(exclude=None):
        pool = [c for c in hostile_pool if c != exclude]
        return random.choice(pool) if pool else random.choice(hostile_pool)

    # 2. Build the Segments
    if structure_type == "sandwich":
        # 1-2 sentences before, 1-2 after
        n_prev = random.randint(1, 2)
        n_next = random.randint(1, 2)

        last_cat = None
        for _ in range(n_prev):
            cat = get_hostile_cat(exclude=last_cat)
            prev_noise_sents.append(context_bank.get_noise(target_label=cat))
            conflict_meta["prev_conflicts"].append(cat)
            last_cat = cat

        last_cat = None
        for _ in range(n_next):
            cat = get_hostile_cat(exclude=last_cat)
            next_noise_sents.append(context_bank.get_noise(target_label=cat))
            conflict_meta["next_conflicts"].append(cat)
            last_cat = cat

    elif structure_type == "left_heavy":
        # 2-3 sentences BEFORE the target (Target is at end)
        n_prev = random.randint(2, 3)
        last_cat = None
        for _ in range(n_prev):
            cat = get_hostile_cat(exclude=last_cat)
            prev_noise_sents.append(context_bank.get_noise(target_label=cat))
            conflict_meta["prev_conflicts"].append(cat)
            last_cat = cat

    elif structure_type == "right_heavy":
        # 2-3 sentences AFTER the target (Target is at start)
        n_next = random.randint(2, 3)
        last_cat = None
        for _ in range(n_next):
            cat = get_hostile_cat(exclude=last_cat)
            next_noise_sents.append(context_bank.get_noise(target_label=cat))
            conflict_meta["next_conflicts"].append(cat)
            last_cat = cat

    target_sent = f"<<>>{sentences[target_idx]}<<>>"

    # 3. Assemble Window
    # We join ALL parts with the separator to maintain consistent tokenization
    all_parts = prev_noise_sents + [target_sent] + next_noise_sents
    window = " ".join(all_parts)

    return window, conflict_meta


# =============================================================================
# PROCESSING
# =============================================================================


def process_chunk(chunk_data):
    import time

    random.seed(os.getpid() + time.time())
    scorer = ContextScorer()
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
                            sentences,
                            i,
                            override_target=blanked_target,
                            label=label,  # Pass label for safe noise
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
                        full_window = get_dynamic_window(
                            sentences, i, label="gen"
                        )  # Pass "gen" for safe window
                        best_cat, best_score = scorer.get_best_category(full_window)

                        if best_score >= 30:
                            local_candidates.append(
                                {
                                    "label": best_cat,
                                    "sentences": sentences,
                                    "target_idx": i,
                                    "match_span": match.span(),
                                    "match_text": match.group(0),
                                    "original_sent": sentence,
                                    "score": best_score,
                                    "url": url,
                                    "subtype": "L2_Disambiguated_Context",
                                    "detected_categories": {best_cat},
                                }
                            )
                        elif best_score < 10:
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

                else:
                    # 1. Check for Counterparty/Credit Policy (HARD NEGATIVES)
                    if COUNTERPARTY_REGEX.search(sentence):
                        # Ensure we don't accidentally grab a subtle instrument
                        # (Double check it doesn't have a strict instrument hidden in it)
                        if not STRICT_REGEX.search(sentence):
                            local_candidates.append(
                                {
                                    "label": "gen",
                                    "sentences": sentences,
                                    "target_idx": i,
                                    "match_span": None,
                                    "match_text": "HardNegative",
                                    "original_sent": sentence,
                                    "score": 0,
                                    "url": url,
                                    "subtype": "L0_Hard_Negative_Credit",  # <-- Useful for debugging
                                    "detected_categories": {"ctr"},
                                }
                            )
                            continue
                    is_hedging_talk = bool(HEDGING_CONTEXT_REGEX.search(sentence))
                    is_accounting = bool(EXCLUDE_REGEX_ACCOUNTING_STD.search(sentence))

                    if is_hedging_talk or is_accounting:
                        cats = get_sentence_categories(sentence)
                        specific_cats = cats - {"gen", "other"}

                        if len(specific_cats) == 0:
                            if VERB_USE_REGEX.search(sentence) and GEN_REGEX.search(
                                sentence
                            ):
                                continue
                            full_window = get_dynamic_window(
                                sentences, i, label="gen"
                            )  # Pass "gen"
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
    deduplicator = ContentDeduplicator()
    augmenter = AugmentationEngine()

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
            detected_cats = item.get("detected_categories", {label})
            window_label_arg = "gen" if label == "gen" else None

            row = {
                "text": "",
                "label": label,
                "difficulty": "",
                "debug_original": orig,
                "debug_score": score,
                "scrubbing_applied": False,
            }

            if label == "gen":
                row["text"] = get_dynamic_window(
                    sentences,
                    idx,
                    label=window_label_arg,
                    context_bank=context_bank,
                )
                row["difficulty"] = item.get("subtype", "L0_Ambiguous")

            if label != "gen" and score > 40 and random.random() < L4_ADVERSE_RATIO:

                # 1. Generate Hostile Window
                window, conflict_info = get_hostile_window(
                    sentences, idx, label, context_bank
                )

                # 2. Apply Substitutions Manually (since we built window manually)
                numeric_engine = NumericSubstitutionEngine()
                month_info, all_months = numeric_engine.extract_sentence_months(
                    sentences
                )  # Use original sentences for context
                year_info, all_years = numeric_engine.extract_sentence_years(sentences)
                if all_years:
                    numeric_engine.build_year_mapping(year_info, all_years)
                if all_months:
                    numeric_engine.build_month_mapping(month_info, all_months)

                window = numeric_engine.substitute_all(window)
                curr_sub = DynamicCurrencySubstitution()  # Use full class in prod
                window, _ = curr_sub.substitute_all(window)
                window = re.sub("<<>>", SEP_TOKEN, window)

                row["text"] = window
                row["difficulty"] = "L4_Natural_Adverse"
                row["debug_conflict_sources"] = str(conflict_info)

                # IMPORTANT: We do NOT mask the instrument. The user must see the signal clearly
                # to override the hostile context.

                final_data.append(row)
                stats[label] += 1
                continue
            elif score >= 20:
                prep_result = prepare_training_example(
                    orig, label, detected_cats, replacement_strategy="stochastic"
                )
                if prep_result:
                    masked_text, _, metadata = prep_result
                    row["text"] = get_dynamic_window(
                        sentences,
                        idx,
                        override_target=masked_text,
                        label=window_label_arg,
                        context_bank=context_bank,
                    )
                    row["difficulty"] = "L2_Masked_Scrubbed"
                    row["scrubbing_applied"] = metadata["scrubbing_applied"]
                    scrubbing_stats["L2_scrubbed"] += 1
                else:
                    match_span = item["match_span"]
                    match_text = item["match_text"]
                    aug, _ = augmenter.augment(orig, match_span, match_text)
                    row["text"] = get_dynamic_window(
                        sentences,
                        idx,
                        override_target=aug,
                        label=window_label_arg,
                        context_bank=context_bank,
                    )
                    row["difficulty"] = "L2_Masked"
                    scrubbing_stats["L2_fallback"] += 1

            elif score > 0:
                prep_result = prepare_training_example(
                    orig, label, detected_cats, replacement_strategy="base"
                )
                if prep_result:
                    masked_text, _, metadata = prep_result
                    row["text"] = get_dynamic_window(
                        sentences,
                        idx,
                        override_target=masked_text,
                        label=window_label_arg,
                        context_bank=context_bank,
                    )
                    row["difficulty"] = "L1_WeakContext_Scrubbed"
                    row["scrubbing_applied"] = metadata["scrubbing_applied"]
                    scrubbing_stats["L1_scrubbed"] += 1
                else:
                    row["text"] = get_dynamic_window(
                        sentences,
                        idx,
                        label=window_label_arg,
                        context_bank=context_bank,
                    )
                    row["difficulty"] = "L1_WeakContext"
                    scrubbing_stats["L1_unscrubbed"] += 1

            else:
                row["text"] = get_dynamic_window(
                    sentences,
                    idx,
                    label=window_label_arg,
                    context_bank=context_bank,
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
