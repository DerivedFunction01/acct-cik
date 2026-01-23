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

MISC_CORE_TERMS = [
    r"inflation",
    r"CPI",
    VOLATILITY,
    VARIANCE,
    r"catastrophe",
    r"longevity",
    r"mortality",
    r"economic",
    r"freight",
    r"property",
    r"weather"
]

def build_misc_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    """
    Returns a tuple: (strict_misc_regex, soft_misc_regex, loose_misc_regex)
    """

    # --- 1. Core Prefix Terms ---
    strict_core_terms = MISC_CORE_TERMS

    # --- 2. Specific Instrument Phrases (Max Munch) ---
    specific_phrases = [
        r"inflation\s+swaps?",
        r"CPI\s+swaps?",
        rf"{VARIANCE}\s+swaps?",
        r"catastrophe\s+bonds?",
        r"longevity\s+swaps?",
        r"mortality\s+swaps?",
        r"VIX\s+futures?",
        r"VIX\s+options?",
    ]

    sorted_specific_phrases = sorted(
        specific_phrases, key=lambda x: (-len(x), -x.count(r"\s+"))
    )

    # --- 3. Build Patterns ---
    
    # Strict/Soft are identical for Misc context
    _MISC_CONFIG = DERIVATIVES(
        PREFIX=strict_core_terms,
        STANDALONE_BASES=[BASE.SWAP, BASE.OPTION, BASE.FUTURES, BASE.FORWARD],
        STANDALONE_SUFFIXES=[SUFFIX.CONTRACT, SUFFIX.AGREEMENT],
    )
    _MISC_PATTERN = DerivativeGenerator(config=_MISC_CONFIG).generate()
    
    strict_misc_regex = build_regex([_MISC_PATTERN] + sorted_specific_phrases)
    soft_misc_regex = build_regex([_MISC_PATTERN] + sorted_specific_phrases)

    # Loose: Allows any base/suffix with the prefix
    _LOOSE_CONFIG = DERIVATIVES(
        PREFIX=strict_core_terms,
        LOOSE=True,
    )
    _LOOSE_PATTERN = DerivativeGenerator(config=_LOOSE_CONFIG).generate()
    
    loose_misc_regex = build_regex([_LOOSE_PATTERN] + sorted_specific_phrases)

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