import re
from typing import Tuple, List

from defs.derivatives_core import (
    BASE,
    DERIVATIVES,
    MULTI_BASE,
    SPEC_BASE,
    DerivativeGenerator,
    Groups,
)
from defs.regex_lib import build_regex
from defs.shared_context import build_risk_managment_phrase
from defs.verb_core import build_strict_do_not_mitigate_regex

TRADING_CORE_TERMS = [
    r"trading",
    r"speculative",
    r"arbitrage",
    r"market[- ]making",
    r"proprietary",
    r"naked",
    r"short\s+sales?",
]

def build_trading_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    """
    Returns a tuple: (strict_trading_regex, soft_trading_regex, loose_trading_regex)
    """

    # --- 1. Build Patterns ---

    # Strict: Only allows Trading Bases (Spreads, Straddles, Exotics)
    # We do not attach prefixes here because these bases are strong enough on their own
    _STANDALONE_TRADING_CONFIG = DERIVATIVES(
        PREFIX=[],
        _BASES=[],
        _AMB_BASES=[],
        STANDALONE_BASES=Groups.TRADING_BASES,
        STANDALONE_SUFFIXES=[],
        SUFFIXES=[],
        ADDITIONAL_BASES=[],
        MULTI_BASE=[], # Everything else empty
    )
    _STANDALONE_TRADING_PATTERN = DerivativeGenerator(
        config=_STANDALONE_TRADING_CONFIG
    ).generate()

    _TRADING_CONFIG = DERIVATIVES(
        PREFIX=TRADING_CORE_TERMS,
        _BASES=Groups.TRADING_BASES + [BASE.DERIVATIVE],
        _AMB_BASES=Groups.CORE_UNAMBIGUOUS_BASES,  # allows trading swap agreement, set. Mot trading lock
        STANDALONE_BASES=[],
        STANDALONE_SUFFIXES=[],
        MULTI_BASE=[MULTI_BASE.TRIPLE_BASE],  # Enforce stricter matches
    )
    _TRADING_PATTERN = DerivativeGenerator(config=_TRADING_CONFIG).generate()

    strict_trading_regex = build_regex([_TRADING_PATTERN, _STANDALONE_TRADING_PATTERN])
    soft_trading_regex = build_regex([_TRADING_PATTERN, _STANDALONE_TRADING_PATTERN])

    # Loose: Allows any base with Trading prefix
    _LOOSE_CONFIG = DERIVATIVES(
        PREFIX=TRADING_CORE_TERMS,
        _BASES=Groups.CORE_UNAMBIGUOUS_BASES + Groups.AMBIGUOUS_BASES,
        _AMB_BASES=[], # prevent trading cap, market cap, etc
        LOOSE=True,
    )
    _LOOSE_PATTERN = DerivativeGenerator(config=_LOOSE_CONFIG).generate()

    loose_trading_regex = build_regex([_LOOSE_PATTERN])

    return strict_trading_regex, soft_trading_regex, loose_trading_regex


def build_trading_context_terms() -> Tuple[List[str], List[str], List[str]]:
    strict_terms = TRADING_CORE_TERMS
    soft_terms = TRADING_CORE_TERMS + [
        r"strike\s+prices?",
        r"exercise\s+prices?",
        r"spot\s+prices?",
        r"initial\s+prices?",
    ]
    
    # Risk Management Glue
    trading_glue = TRADING_CORE_TERMS
    risk_terms = [build_risk_managment_phrase(trading_glue)]

    return strict_terms, soft_terms, risk_terms


TRADING_STRICT_TERMS, TRADING_SOFT_TERMS, TRADING_RISK_TERMS = build_trading_context_terms()
TRADING_CONTEXT_TERMS = TRADING_STRICT_TERMS + TRADING_SOFT_TERMS + TRADING_RISK_TERMS
TRADING_CONTEXT_REGEX = build_regex(TRADING_CONTEXT_TERMS)
TRADING_STRICT_CONTEXT_REGEX = build_regex(TRADING_STRICT_TERMS + TRADING_RISK_TERMS)
TRADING_RISK_REGEX = build_regex(TRADING_RISK_TERMS)
TRADING_REGEX, TRADING_SOFT_REGEX, TRADING_LOOSE_REGEX = build_trading_regex()

TRADING_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(TRADING_CORE_TERMS)

def run_tests():
    from defs.derivatives_core import (
        MatchLevel,
        run_category_tests,
        run_category_tests_counter,
    )

    test_cases = [
        ("Asian option", MatchLevel.STRICT),
        ("call spread", MatchLevel.STRICT),
        ("trading derivatives", MatchLevel.STRICT),
        ("speculative swap agreement", MatchLevel.STRICT),
        ("trading swap", MatchLevel.LOOSE),
    ]
    run_category_tests(test_cases, TRADING_REGEX, TRADING_SOFT_REGEX, TRADING_LOOSE_REGEX)

    counter_cases = [
        ("trading cap", MatchLevel.NONE),
        ("market cap", MatchLevel.NONE),
    ]
    run_category_tests_counter(counter_cases, TRADING_REGEX, TRADING_SOFT_REGEX, TRADING_LOOSE_REGEX)
