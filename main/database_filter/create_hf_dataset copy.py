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
    cleanup_fragment,
    VERB_USE_REGEX, 
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


class NumericSubstitutionEngine:
    """
    Performs dynamic numeric substitution on text windows.

    Strategy:
    - Years: Collect all, pick random base year, apply ±1 uniformly
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
        self.base_year = None

    def extract_sentence_years(self, sentences):
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
        """
        Build mapping from original year -> replacement year.

        Strategy (handles both single years and comparatives):
        1. Pick random base year (ZZ) from all_years
        2. For each sentence:
           - If single year: map to ZZ
           - If comparative (multiple years): map to ZZ + offset

        Example:
            sentence_year_info = {
                0: {'years': [1996], 'min_year': 1996, 'offsets': {1996: 0}},
                2: {'years': [2023, 2024], 'min_year': 2023, 'offsets': {2023: 0, 2024: 1}}
            }
            all_years = {1996, 2023, 2024}
            Pick base_year = 2015

            Output mapping:
                1996 -> 2015  (single year)
                2023 -> 2015  (comparative min year)
                2024 -> 2016  (2015 + offset of 1)

        Args:
            sentence_year_info: Dict from extract_sentence_years()
            all_years: Set of all unique years across all sentences
        """
        if not all_years:
            self.year_mapping = {}
            return

        # Pick random base year (ZZ)
        self.base_year = self.pick_base_year(all_years)

        # For each sentence, determine how to map its years
        for sent_idx, year_info in sentence_year_info.items():
            min_year = year_info["min_year"]
            offsets = year_info["offsets"]

            # Map minimum year of sentence to base_year
            # All other years in that sentence get base_year + their offset
            for year, offset in offsets.items():
                replacement_year = self.base_year + offset
                self.year_mapping[year] = replacement_year

    def substitute_years_in_text(self, text):
        """
        Replace years in text using pre-built year_mapping.

        Must call build_year_mapping() first.
        """
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
        """
        Replace non-year numbers with ±5% uniform perturbation.
        Skip zeros and already-substituted years.
        """
        if not self.config["apply_to_numbers"]:
            return text

        def replace_number(match):
            num_str = match.group(0)

            # Skip if it's a year (already processed)
            try:
                num_val = int(num_str)
                if num_val in self.year_mapping:
                    return num_str
            except (ValueError, TypeError):
                pass

            # Parse the number
            try:
                num_val = float(num_str)
            except ValueError:
                return num_str

            # Skip zeros
            if num_val == 0:
                return num_str

            # Apply ±5% uniform perturbation
            delta = self.rng.uniform(
                -self.config["number_perturbation"], self.config["number_perturbation"]
            )
            new_val = num_val * (1 + delta)

            # Preserve precision
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
        """Apply year substitution followed by number substitution."""
        text = self.substitute_years_in_text(text)
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
        self.base_year = None


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
            if is_comp_talk and not is_hedging_talk:
                return -1
            if is_comp_talk and is_hedging_talk:
                score += 25
        return score

    def get_max_score_any_category(self, text: str) -> int:
        scores = [self.score(text, lbl) for lbl in ["ir", "fx", "cp", "eq"]]
        return max(scores)


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
        self.bases = [
            b.replace("?", "").replace("s", "") for b in UNAMBIGUOUS_BASE_TYPES
        ]

    def augment(self, text: str, span: tuple, match_text: str):
        start, end = span
        if random.random() < 0.3:
            replacement = random.choice(self.generic_terms)
            strategy = "Generic_Universal"
        else:
            found_base = "instrument"
            for base in self.bases:
                if base in match_text.lower():
                    found_base = base
                    break
            replacement = f"{found_base} {random.choice(['', 'contract'])}".strip()
            strategy = "Loose_Variant"
        augmented_text = text[:start] + replacement + text[end:]
        return augmented_text, strategy


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
        if not target_instrument_regex.search(scrubbed_text) or target_soft_instrument_regex.search(scrubbed_text):
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

    Args:
        sentence: Source sentence
        target_category: Category for this training example
        all_detected_categories: All categories found in sentence
        replacement_strategy: "stochastic", "base", or "generic"

    Returns:
        Tuple of (masked_text, category, metadata) or None if validation fails

    Example:
        >>> sentence = "We use interest rate swaps to hedge."
        >>> prepare_training_example(sentence, "ir", {"ir"})
        # Returns: ("We use swaps to hedge.", "ir", {...})
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
        # Find the match to determine what we're replacing
        match = target_instrument_regex.search(scrubbed_text) or target_soft_instrument_regex.search(scrubbed_text)
        if not match:
            logger.warning(
                f"Target instrument not found after scrubbing: {target_category}"
            )
            return None

        matched_text = match.group(0)

        # Apply replacement strategy
        if replacement_strategy == "stochastic":
            # 30% base, 70% loose variant
            if random.random() < 0.3:
                replacement = _get_base_form(matched_text, target_category)
                strategy = "base"
            else:
                replacement = _get_loose_variant(matched_text, target_category)
                strategy = "loose_variant"
        elif replacement_strategy == "base":
            replacement = _get_base_form(matched_text, target_category)
            strategy = "base"
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

        # Replace only the first occurrence to preserve other same-category bases
        masked_text = target_instrument_regex.sub(replacement, scrubbed_text, count=1)

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

    suffixes = ["agreement", "instrument", "contract"]
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


def _extract_all_years_from_sentences(sentences):
    """
    Helper to extract years from a list of sentences, tracking per-sentence offsets.

    Returns:
        (sentence_year_info, all_years_set)
        - sentence_year_info: Dict with year offsets per sentence
        - all_years_set: Set of all unique years
    """
    engine = NumericSubstitutionEngine()
    sentence_year_info, all_years = engine.extract_sentence_years(sentences)
    return sentence_year_info, all_years


def get_dynamic_window(
    sentences,
    target_idx,
    override_target=None,
    context_bank=None,
    apply_numeric_substitution=True,
):
    """
    Constructs a variable-width window with optional dynamic numeric substitution.

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

    window = f"{prev_block}{SEP_TOKEN}{target_sent}{SEP_TOKEN}{next_block}"

    # NEW: Apply numeric substitution to entire window
    if apply_numeric_substitution and NUMERIC_SUBSTITUTION_CONFIG["enabled"]:
        # Extract years from all sentences in window, tracking offsets
        all_sentences = prev_parts + [target_sent] + next_parts
        sentence_year_info, all_years = _extract_all_years_from_sentences(all_sentences)

        if all_years:
            subst_engine = NumericSubstitutionEngine()
            # Build mapping: pick random base year, map single years to it,
            # map comparatives to base_year + offset
            subst_engine.build_year_mapping(sentence_year_info, all_years)
            # Apply substitution to window
            window = subst_engine.substitute_all(window)

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
    scorer = ContextScorer()
    augmenter_dummy = AugmentationEngine()
    local_candidates = []
    local_noise = []

    for url, matches_json in chunk_data:
        try:
            paragraphs = json.loads(matches_json)
        except:
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
    test_sentences = [
        "In 1996, we entered into derivatives.",
        "We used 2.5M notional in interest rate swaps.",
        "The notional was 3M and 3.1M in 2023 and 2024 respectively.",
        "We manage 1500 basis points of exposure.",
    ]

    # Extract years with offsets
    engine = NumericSubstitutionEngine()
    sent_year_info, all_years = engine.extract_sentence_years(test_sentences)
    print(f"Sentence year info: {sent_year_info}")
    print(f"All years: {all_years}")

    # Build mapping with random base year
    engine.build_year_mapping(sent_year_info, all_years)
    print(f"\nBase year: {engine.base_year}")
    print(f"Year mapping: {engine.year_mapping}")
    mp.freeze_support()
    create_labeled_dataset()
