import re
from typing import Tuple, List

from defs.derivatives_core import (
    BASE,
    DERIVATIVES,
    DerivativeGenerator,
    SUFFIX,
    Groups,
)
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, build_risk_managment_phrase


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
        "(?:credit|basket|first[- ]to[ -])[- ](?:default|linked|based|protection)",
    ]

    # --- 2. Specific Instrument Phrases (Max Munch) ---
    cln_pattern = rf"credit[- ]linked\s+{_DEBT_TERMS}"
    specific_phrases = [
        cln_pattern,
        "credit (?:swaps?(?![- ]rates?)|derivatives?)",
    ]  # None for this one

    sorted_specific_phrases = sorted(
        specific_phrases, key=lambda x: (-len(x), -x.count(r"\s+"))
    )

    # --- 3. Build Patterns ---

    # Strict/Soft are identical in CR because exclude_standalone_suffixes=True
    # forces safe bases only, but we explicitly allow Option/Contract/Agreement standalone.
    BASES = Groups.UNAMBIGUOUS_BASES.copy()
    if BASE.FORWARD in BASES:
        BASES.remove(BASE.FORWARD)
    if BASE.COLLAR in BASES:
        BASES.remove(BASE.COLLAR)
    _AMB_BASES = [BASE.SWAP, BASE.COLLAR]

    _CR_CONFIG = DERIVATIVES(
        PREFIX=strict_core_terms,
        _BASES=BASES,
        _AMB_BASES=_AMB_BASES + Groups.AMBIGUOUS_BASES,
        ADDITIONAL_BASES=Groups.TRADING_BASES,
    )
    _CR_PATTERN = DerivativeGenerator(config=_CR_CONFIG).generate()

    strict_cr_regex = build_regex([_CR_PATTERN] + sorted_specific_phrases)
    soft_cr_regex = build_regex([_CR_PATTERN] + sorted_specific_phrases)

    # Loose: Allows any base/suffix with the prefix
    _LOOSE_CONFIG = DERIVATIVES(
        PREFIX=strict_core_terms,
        _BASES=BASES,
        _AMB_BASES=_AMB_BASES + Groups.AMBIGUOUS_BASES,
        ADDITIONAL_BASES=Groups.TRADING_BASES,
        LOOSE=True,
    )
    _LOOSE_PATTERN = DerivativeGenerator(config=_LOOSE_CONFIG).generate()

    loose_cr_regex = build_regex([_LOOSE_PATTERN] + sorted_specific_phrases)

    return strict_cr_regex, soft_cr_regex, loose_cr_regex


_CR_LINKED_DEBT = rf"credit[- ]linked\s+{_DEBT_TERMS}"


def build_cr_context_terms() -> Tuple[List[str], List[str], List[str]]:
    # 1. Explicit Instruments (Strict)
    cr_instruments = [
        r"credit[- ]default",
        _CR_LINKED_DEBT,
        r"basket[- ]default",
        r"first[- ]to[- ]default",
        r"credit[- ]derivatives?",
    ]

    # 2. Indices (Strict/Soft)
    cr_indices = [
        r"CDX",
        r"iTraxx",
        r"Markit\s+CDX",
    ]

    # 3. Mechanics (Specific to CDS)
    cr_mechanics = [
        r"reference\s+(?:entit(?:y|ies)|obligations?)",
        r"protection\s+(?:buyer|seller|sold|bought)",
    ]

    # 4. Broader terms (Soft)
    cr_broad = [
        r"credit[- ](?:protections?|linked|slope|curve|tranche)",
        r"total[- ]return",
        r"credit\s+indices",
        r"credit\s+index",
        r"credit\s+events?",
        r"recovery\s+rates?",
    ]

    strict_terms = cr_instruments + cr_indices + cr_mechanics
    soft_terms = cr_broad

    # 5. Risk Management Glue
    cr_glue = cr_indices

    risk_terms = [build_risk_managment_phrase(cr_glue)]

    return strict_terms, soft_terms, risk_terms


CR_STRICT_TERMS, CR_SOFT_TERMS, CR_RISK_TERMS = build_cr_context_terms()
CR_CONTEXT_TERMS = CR_STRICT_TERMS + CR_SOFT_TERMS + CR_RISK_TERMS
CR_CONTEXT_REGEX = build_regex(CR_CONTEXT_TERMS)
CR_STRICT_CONTEXT_REGEX = build_regex(CR_STRICT_TERMS + CR_RISK_TERMS)
CR_RISK_REGEX = build_regex(CR_RISK_TERMS)
CR_REGEX, CR_SOFT_REGEX, CR_LOOSE_REGEX = build_cr_regex()
from defs.verb_core import build_strict_do_not_mitigate_regex

CR_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(
    [
        r"credit",
        r"counterparty",
        r"default",
    ]
)


def run_tests():
    from defs.derivatives_core import (
        MatchLevel,
        run_category_tests,
        run_category_tests_counter,
    )

    test_cases = [
        ("credit default swap", MatchLevel.STRICT),
        ("credit default swap agreement", MatchLevel.STRICT),
        ("credit linked note", MatchLevel.STRICT),
        ("credit swap", MatchLevel.STRICT),
        ("credit default option", MatchLevel.LOOSE),
        ("basket default swap", MatchLevel.STRICT),
        ("credit derivative", MatchLevel.STRICT),
        ("credit default agreement", MatchLevel.LOOSE),
        ("credit protection swap", MatchLevel.STRICT),
    ]
    run_category_tests(test_cases, CR_REGEX, CR_SOFT_REGEX, CR_LOOSE_REGEX)

    counter_cases = [
        ("credit agreement", MatchLevel.LOOSE),
        ("credit facility", MatchLevel.LOOSE),
        ("credit risk", MatchLevel.LOOSE),
        ("credit protection", MatchLevel.LOOSE),
        ("credit default", MatchLevel.LOOSE),
        ("credit hedges", MatchLevel.LOOSE),
    ]
    run_category_tests_counter(counter_cases, CR_REGEX, CR_SOFT_REGEX, CR_LOOSE_REGEX)
