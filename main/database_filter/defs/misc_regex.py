import re
from typing import Tuple, List

from defs.derivatives_core import (
    BASE,
    DERIVATIVES,
    DerivativeGenerator,
    SUFFIX,
)
from defs.regex_lib import add_restrictions, build_alternation, build_regex
from defs.shared_context import build_risk_managment_phrase
from defs.verb_core import build_strict_do_not_mitigate_regex

VOLATILITY = add_restrictions(r"volatility", lookbehinds=[r"rate", r"price"])
VARIANCE = add_restrictions(r"variance", lookbehinds=[r"rate", r"price"])

STRONG_MISC_WITH_OPT = [
    VOLATILITY,
    VARIANCE,
]

STRONG_MISC_NO_OPT = [
    r"inflation",
    r"CPI",
]

STRONG_MISC_TERMS = STRONG_MISC_WITH_OPT + STRONG_MISC_NO_OPT

WEAK_MISC_WITH_OPT = [r"weather", r"VIX"]

WEAK_MISC_NO_OPT = [
    r"catastrophe",
    r"longevity",
    r"mortality",
    r"economic",
    r"property",
    r"freight",
]

WEAK_MISC_TERMS = WEAK_MISC_WITH_OPT + WEAK_MISC_NO_OPT

MISC_CORE_TERMS = STRONG_MISC_TERMS + WEAK_MISC_TERMS

def build_misc_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    """
    Returns a tuple: (strict_misc_regex, soft_misc_regex, loose_misc_regex)
    """

    # --- 2. Specific Instrument Phrases (Max Munch) ---
    specific_phrases = [
        r"catastrophe\s+bonds?",
    ]

    sorted_specific_phrases = sorted(
        specific_phrases, key=lambda x: (-len(x), -x.count(r"\s+"))
    )

    # --- 3. Build Patterns ---

    # Strict/Soft are identical for Misc context

    # 1. Strong Terms (With Option): Allow "Volatility Option", "Volatility Agreement"
    _MISC_CONFIG_STRONG_OPT = DERIVATIVES(
        PREFIX=STRONG_MISC_WITH_OPT,
        STANDALONE_BASES=[BASE.SWAP, BASE.OPTION, BASE.FUTURES, BASE.FORWARD],
        STANDALONE_SUFFIXES=[SUFFIX.CONTRACT, SUFFIX.AGREEMENT],
    )
    _MISC_PATTERN_STRONG_OPT = DerivativeGenerator(config=_MISC_CONFIG_STRONG_OPT).generate()

    # 2. Strong Terms (No Option): Allow "Inflation Agreement", BLOCK "Inflation Option"
    _MISC_CONFIG_STRONG_NO_OPT = DERIVATIVES(
        PREFIX=STRONG_MISC_NO_OPT,
        STANDALONE_BASES=[BASE.SWAP, BASE.FUTURES, BASE.FORWARD],
        STANDALONE_SUFFIXES=[SUFFIX.CONTRACT, SUFFIX.AGREEMENT],
    )
    _MISC_PATTERN_STRONG_NO_OPT = DerivativeGenerator(config=_MISC_CONFIG_STRONG_NO_OPT).generate()

    # 3. Weak Terms (With Option): Allow "weather Option", BLOCK "weather Agreement"
    _MISC_CONFIG_WEAK_OPT = DERIVATIVES(
        PREFIX=WEAK_MISC_WITH_OPT,
        STANDALONE_BASES=[BASE.SWAP, BASE.OPTION, BASE.FUTURES, BASE.FORWARD],
        STANDALONE_SUFFIXES=[], 
    )
    _MISC_PATTERN_WEAK_OPT = DerivativeGenerator(config=_MISC_CONFIG_WEAK_OPT).generate()

    # 4. Weak Terms (No Option): Allow "Property Swap", BLOCK "Property Option", "Property Agreement"
    _MISC_CONFIG_WEAK_NO_OPT = DERIVATIVES(
        PREFIX=WEAK_MISC_NO_OPT,
        STANDALONE_BASES=[BASE.SWAP, BASE.FUTURES, BASE.FORWARD],
        STANDALONE_SUFFIXES=[],
    )
    _MISC_PATTERN_WEAK_NO_OPT = DerivativeGenerator(config=_MISC_CONFIG_WEAK_NO_OPT).generate()

    patterns = [
        _MISC_PATTERN_STRONG_OPT,
        _MISC_PATTERN_STRONG_NO_OPT,
        _MISC_PATTERN_WEAK_OPT,
        _MISC_PATTERN_WEAK_NO_OPT
    ]

    strict_misc_regex = build_regex(patterns + sorted_specific_phrases)
    soft_misc_regex = build_regex(patterns + sorted_specific_phrases)

    # Loose:
    # Strong terms get full loose matching (contextual)
    _LOOSE_CONFIG_STRONG = DERIVATIVES(
        PREFIX=STRONG_MISC_TERMS,
        LOOSE=True,
    )
    _LOOSE_PATTERN_STRONG = DerivativeGenerator(config=_LOOSE_CONFIG_STRONG).generate()

    # Weak terms reuse the strict patterns (must have base) to avoid noise in loose regex
    _LOOSE_PATTERN_WEAK = build_alternation([_MISC_PATTERN_WEAK_OPT, _MISC_PATTERN_WEAK_NO_OPT])

    loose_misc_regex = build_regex([_LOOSE_PATTERN_STRONG, _LOOSE_PATTERN_WEAK] + sorted_specific_phrases)

    return strict_misc_regex, soft_misc_regex, loose_misc_regex


def build_misc_context_terms() -> Tuple[List[str], List[str], List[str]]:
    # 1. Explicit Instruments (Strict)
    misc_instruments = [
        r"inflation\s+linked",
        r"volatility\s+index",
        r"VIX",
    ]

    # 2. Broader terms (Soft)
    misc_broad = MISC_CORE_TERMS

    strict_terms = misc_instruments
    soft_terms = misc_broad

    # 3. Risk Management Glue
    misc_glue = MISC_CORE_TERMS

    risk_terms = [build_risk_managment_phrase(misc_glue)]

    return strict_terms, soft_terms, risk_terms


MISC_STRICT_TERMS, MISC_SOFT_TERMS, MISC_RISK_TERMS = build_misc_context_terms()
MISC_CONTEXT_TERMS = MISC_STRICT_TERMS + MISC_SOFT_TERMS + MISC_RISK_TERMS
MISC_CONTEXT_REGEX = build_regex(MISC_CONTEXT_TERMS)
MISC_STRICT_CONTEXT_REGEX = build_regex(MISC_STRICT_TERMS + MISC_RISK_TERMS)
MISC_RISK_REGEX = build_regex(MISC_RISK_TERMS)
MISC_REGEX, MISC_SOFT_REGEX, MISC_LOOSE_REGEX = build_misc_regex()

MISC_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(MISC_CORE_TERMS)

def run_tests():
    from defs.derivatives_core import (
        MatchLevel,
        run_category_tests,
        run_category_tests_counter,
    )

    test_cases = [
        # Strong Terms (With Option: Volatility, Variance)
        ("volatility option", MatchLevel.STRICT),
        ("volatility swap", MatchLevel.STRICT),
        ("volatility agreement", MatchLevel.STRICT),
        
        # Strong Terms (No Option: Inflation, CPI)
        ("inflation swap", MatchLevel.STRICT),
        ("inflation agreement", MatchLevel.STRICT),
        ("inflation option", MatchLevel.LOOSE), # Caught by LOOSE=True on Strong terms

        # Weak Terms (With Option: Weather, VIX)
        ("weather option", MatchLevel.STRICT),
        ("weather swap", MatchLevel.STRICT),
        ("weather derivatives", MatchLevel.STRICT),
        
        # Weak Terms (No Option: Property, Freight, etc.)
        ("property swap", MatchLevel.STRICT),
        ("freight futures", MatchLevel.STRICT),
        
        # Specific Phrases
        ("catastrophe bond", MatchLevel.STRICT),
    ]
    run_category_tests(test_cases, MISC_REGEX, MISC_SOFT_REGEX, MISC_LOOSE_REGEX)

    counter_cases = [
        # Weak terms should not match with generic suffixes or disallowed bases
        ("weather agreement", MatchLevel.NONE),
        ("property option", MatchLevel.NONE),
        ("property agreement", MatchLevel.NONE),
        ("freight contract", MatchLevel.NONE),
        # Restricted terms (lookbehinds)
        ("interest rate volatility swap", MatchLevel.NONE),
    ]
    run_category_tests_counter(counter_cases, MISC_REGEX, MISC_SOFT_REGEX, MISC_LOOSE_REGEX)