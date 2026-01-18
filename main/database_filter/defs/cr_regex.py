import re
from typing import Tuple, List

from defs.derivatives_core import build_smart_regex, expand_instruments
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS


def build_cr_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    """
    Returns a tuple: (strict_cr_regex, soft_cr_regex)

    STRICT: High-precision credit derivative instrument patterns
    SOFT: Contextual credit derivative instrument patterns

    Examples matched:
      - "credit default swap"
      - "basket default swap"
      - "first-to-default swap"
    """

    # --- 1. Core Prefix Terms ---
    strict_core_terms = [
        "(?:credit|basket|first[- ]to[ -])[- ](?:default|linked|based)",
    ]
    strict_core_alt = build_alternation(strict_core_terms, sort_longest_first=True)

    soft_core_terms = strict_core_terms
    soft_core_alt = build_alternation(soft_core_terms, sort_longest_first=True)

    # --- 2. Specific Instrument Phrases (Max Munch) ---
    cln_pattern = rf"credit[- ]linked\s+{_DEBT_TERMS}"
    specific_phrases = [cln_pattern, "credit swaps"]  # None for this one

    sorted_specific_phrases = sorted(
        specific_phrases, key=lambda x: (-len(x), -x.count(r"\s+"))
    )

    # --- 3. Instrument Fragments ---

    strict_instrument_fragment = expand_instruments(
        unsafe=False,
        exclude_standalone_suffixes=True,
        additional_standalone_suffixes=["contracts?", "options?", "agreements?"],
    )

    soft_instrument_fragment = expand_instruments(
        unsafe=True,
        exclude_standalone_suffixes=True,
        additional_standalone_suffixes=["contracts?", "options?", "agreements?"],
    )

    # --- 4. Build Patterns ---

    strict_pattern = build_smart_regex(
        [strict_core_alt],
        strict_instrument_fragment,
        sorted_specific_phrases,
    )
    strict_cr_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    soft_pattern = build_smart_regex(
        [soft_core_alt],
        soft_instrument_fragment,
        sorted_specific_phrases,
    )
    soft_cr_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)
    
    loose_instrument_fragment = expand_instruments(
        unsafe=True, exclude_standalone_suffixes=False
    )
    loose_pattern = build_smart_regex(
        [soft_core_alt],
        loose_instrument_fragment,
        sorted_specific_phrases,
    )
    loose_cr_regex = re.compile(r"\b" + loose_pattern + r"\b", re.IGNORECASE)

    return strict_cr_regex, soft_cr_regex, loose_cr_regex


_CR_LINKED_DEBT = rf"credit[- ]linked\s+{_DEBT_TERMS}"


def build_cr_context_terms() -> Tuple[List[str], List[str]]:
    strict_terms = [
        # Explicit Instruments
        r"credit[- ]default",
        _CR_LINKED_DEBT,
        r"basket[- ]default",
        r"first[- ]to[- ]default",
        r"credit[- ]derivatives?",
        # Indices
        r"CDX",
        r"iTraxx",
        r"Markit\s+CDX",
        # Mechanics (Specific to CDS)
        r"reference\s+(?:entit(?:y|ies)|obligations?)",
        r"protection\s+(?:buyer|seller|sold|bought)",
    ]

    soft_terms = [
        # Broader terms
        r"credit[- ](?:protections?|linked|slope|curve|tranche)",
        r"total[- ]return",
        r"credit\s+indices",
        r"credit\s+index",
        r"credit\s+events?",
        r"recovery\s+rates?",
    ]
    return strict_terms, soft_terms


CR_STRICT_TERMS, CR_SOFT_TERMS = build_cr_context_terms()
CR_CONTEXT_TERMS = CR_STRICT_TERMS + CR_SOFT_TERMS
CR_CONTEXT_REGEX = build_regex(CR_CONTEXT_TERMS)
CR_STRICT_CONTEXT_REGEX = build_regex(CR_STRICT_TERMS)
CR_REGEX, CR_SOFT_REGEX, CR_LOOSE_REGEX = build_cr_regex()
