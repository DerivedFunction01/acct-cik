import re
from typing import Tuple

from defs.derivatives_core import build_smart_regex, expand_instruments
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS


def build_cr_regex() -> Tuple[re.Pattern, re.Pattern]:
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

    soft_instrument_fragment = expand_instruments(unsafe=True)

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

    return strict_cr_regex, soft_cr_regex


_CR_LINKED_DEBT = rf"credit[- ]linked\s+{_DEBT_TERMS}"

CR_CONTEXT_TERMS = [
    # --- A. Explicit Instruments (Broad Match) ---
    r"credit[- ]default",  # Matches "credit default swap" (Safe)
    r"total[- ]return",  # Matches "total return swap" (Safe)
    _CR_LINKED_DEBT,  # "credit-linked notes" (Safe)
    r"basket[- ]default",  # "basket default swap" (Safe)
    r"first[- ]to[- ]default",  # (Safe)
    # REPLACEMENT FOR RISK ALTERNATION:
    # "Credit Protection" implies a transfer of risk (derivative/insurance), whereas "Credit Risk" just implies exposure.
    r"credit[- ](?:protections?|derivatives?|linked|slope|curve|tranche)",
    # --- B. Indices (Highly Specific - Keep these) ---
    r"CDX",
    r"iTraxx",
    r"Markit\s+CDX",
    r"credit\s+indices",
    r"credit\s+index",
    # --- C. Mechanics (Refined) ---
    # "Reference Entity" is the specific legal term in a CDS contract.
    r"reference\s+(?:entit(?:y|ies)|obligations?)",
    # "Protection Seller/Buyer" is unambiguous CDS terminology.
    r"protection\s+(?:buyer|seller|sold|bought)",
    # "Credit Event" is the ISDA trigger (Bankruptcy, Failure to Pay).
    r"credit\s+events?",
    r"recovery\s+rates?",  # Specific to CDS valuation
]

CR_CONTEXT_REGEX = build_regex(CR_CONTEXT_TERMS)
CR_STRICT_CONTEXT_REGEX = build_regex(CR_CONTEXT_TERMS)
CR_REGEX, CR_SOFT_REGEX = build_cr_regex()
