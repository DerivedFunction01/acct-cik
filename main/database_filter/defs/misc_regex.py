import re
from typing import Tuple, List

from defs.derivatives_core import (
    BASE,
    DERIVATIVES,
    MULTI_BASE,
    DerivativeGenerator,
    SUFFIX,
    Groups,
)
from defs.regex_lib import add_restrictions, build_alternation, build_regex
from defs.shared_context import build_risk_managment_phrase
from defs.verb_core import build_strict_do_not_mitigate_regex

VOLATILITY = add_restrictions(r"volatility", lookbehinds=[r"rate", r"price", r"currency"])
VARIANCE = add_restrictions(r"variance", lookbehinds=[r"rate", r"price", r"currency"])

STRONG_MISC_WITH_OPT = [
    r"weather",
    r"VIX",  # --- Volatility Indices ---
    r"VXN",
    r"RVX",
]
# Only allow futures
STRONG_MISC = [
    r"inflation(?:[- ](?:linked|rate))?",
    r"CPI(?:[- ]linked)?",
    VOLATILITY,
    VARIANCE,
    r"catastrophe(?:[- ]linked)?",
    r"longevity",
    r"mortality",
    r"economic",
]

PROPERTY = [
    r"property",
    r"land",
    r"real[- ]estate",
]

MISC_CORE_TERMS = STRONG_MISC + STRONG_MISC_WITH_OPT + PROPERTY

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
    # -------------------------------------------------------------------------

    BASES = Groups.CORE_UNAMBIGUOUS_BASES.copy()
    if BASE.FORWARD in BASES:
        BASES.remove(BASE.FORWARD)
    
    # remove some bases
    STRICTER_BASES = BASES.copy()
    if BASE.SWAP in STRICTER_BASES:
        STRICTER_BASES.remove(BASE.SWAP)
    if BASE.COLLAR in STRICTER_BASES:
        STRICTER_BASES.remove(BASE.COLLAR)

    _AMB_BASES = [BASE.SWAP, BASE.FORWARD, BASE.COLLAR]

    # 1. Strong misc with options (removes foward and collar but keeps swap)
    # Allows "Weather Option", "Weather Agreement"
    _STRONG_CONFIG = DERIVATIVES(
        PREFIX=STRONG_MISC_WITH_OPT,
        _BASES=BASES + [BASE.OPTION],
        _AMB_BASES=_AMB_BASES + Groups.AMBIGUOUS_BASES, # redundant for swaps but fixed in the generator
        STANDALONE_SUFFIXES=[],
    )
    _STRONG_PATTERN = DerivativeGenerator(config=_STRONG_CONFIG).generate()

    # 2. Strong misc without options
    # Allows "Inflation Swap", Blocks "Inflation Option".
    _WEAK_CONFIG = DERIVATIVES(
        PREFIX=STRONG_MISC,
        _BASES=BASES,
        _AMB_BASES=_AMB_BASES + Groups.AMBIGUOUS_BASES,
        STANDALONE_SUFFIXES=[],
    )
    _WEAK_PATTERN = DerivativeGenerator(config=_WEAK_CONFIG).generate()

    # 4. Property (Land, Real Estate)
    # Allows "Property Futures". Blocks "Property Swap", "Property Option", "Property Agreement".
    _PROPERTY_CONFIG = DERIVATIVES(
        PREFIX=PROPERTY,
        _BASES=STRICTER_BASES,
        _AMB_BASES=[], # No ambiguous bases allowed for property
        STANDALONE_SUFFIXES=[],
        MULTI_BASE=[MULTI_BASE.TRIPLE_BASE],
    )
    _PROPERTY_PATTERN = DerivativeGenerator(config=_PROPERTY_CONFIG).generate()

    patterns = [
        _STRONG_PATTERN,
        _WEAK_PATTERN,
        _PROPERTY_PATTERN,
    ]
    
    strict_misc_regex = build_regex(patterns + sorted_specific_phrases)
    soft_misc_regex = build_regex(patterns + sorted_specific_phrases)

    # 5. Loose Config
    _LOOSE_CONFIG = DERIVATIVES(
        PREFIX=MISC_CORE_TERMS,
        LOOSE=True,
    )
    _LOOSE_PATTERN = DerivativeGenerator(config=_LOOSE_CONFIG).generate()

    loose_misc_regex = build_regex([_LOOSE_PATTERN] + patterns + sorted_specific_phrases)

    return strict_misc_regex, soft_misc_regex, loose_misc_regex

def build_misc_context_terms() -> Tuple[List[str], List[str], List[str]]:
    # 1. Explicit Instruments (Strict)
    misc_instruments = [
        r"inflation\s+linked",
        r"volatility\s+index",
        r"VIX",
        r"VXN",
        r"RVX",
        r"catastrophe",
    ]

    # 2. Broader terms (Soft)
    misc_broad = MISC_CORE_TERMS + [
        r"temperatures?",
        r"precipitations?",
        r"snowfalls?",
        r"(?:heating|cooling)\s+degree\s+days?",
    ]

    strict_terms = misc_instruments
    soft_terms = misc_broad

    # 3. Risk Management Glue
    misc_glue = misc_instruments + PROPERTY

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
        ("weather option", MatchLevel.STRICT),
        ("weather swap", MatchLevel.STRICT),
        ("weather agreement", MatchLevel.LOOSE),
        
        # Strong Terms (No Option: Inflation, CPI)
        ("inflation swap", MatchLevel.STRICT),
        ("inflation agreement", MatchLevel.LOOSE),
        ("inflation option", MatchLevel.LOOSE), 

        # Weak Terms (With Option: Weather, VIX)
        ("volatility option", MatchLevel.LOOSE), # Volatility moved to STRONG_MISC (No Option)
        ("volatility swap", MatchLevel.STRICT),
        ("volatility derivatives", MatchLevel.STRICT),
        
        # Weak Terms (Property/Freight restrictions)
        ("property futures", MatchLevel.STRICT),
        
        # Specific Phrases
        ("catastrophe bond", MatchLevel.STRICT),
    ]
    run_category_tests(test_cases, MISC_REGEX, MISC_SOFT_REGEX, MISC_LOOSE_REGEX)

    counter_cases = [
        # Weak terms should not match with generic suffixes or disallowed bases
        ("property option", MatchLevel.NONE),
        ("property agreement", MatchLevel.NONE),
        ("property swap", MatchLevel.NONE),
        ("property forward", MatchLevel.NONE),
        # Restricted terms (lookbehinds)
        ("interest rate volatility swap", MatchLevel.NONE),
        # Non-derivative terms (Should not match Soft)
        ("economic growth", MatchLevel.NONE),
        ("economic value", MatchLevel.NONE),
        ("property tax", MatchLevel.NONE),
        ("land lease", MatchLevel.NONE),
        ("mortality rate", MatchLevel.NONE),
        ("longevity risk", MatchLevel.NONE),
        ("weather conditions", MatchLevel.NONE),
        ("CPI increase", MatchLevel.NONE),
        ("catastrophe loss", MatchLevel.NONE),
        ("inflation rate", MatchLevel.NONE),
        ("volatility index", MatchLevel.NONE),
        ("economic hedge", MatchLevel.NONE),
    ]
    run_category_tests_counter(counter_cases, MISC_REGEX, MISC_SOFT_REGEX, MISC_LOOSE_REGEX)
