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
from defs.shared_context import build_risk_managment_phrase
from defs.verb_core import build_strict_do_not_mitigate_regex

CRYPTO_CORE_TERMS = [
    r"crypto(?:currenc(?:y|ies))?",
    r"digital\s+assets?",
    r"(?:virtual|digital|crypto)[- ]currenc(?:y|ies)",
    r"bitcoins?",
    r"ether(?:eum)?",
    r"BTC",
    r"ETH",
    r"stablecoins?"
]

def build_crypto_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    """
    Returns a tuple: (strict_crypto_regex, soft_crypto_regex, loose_crypto_regex)
    """

    # --- 1. Core Prefix Terms ---
    strict_core_terms = CRYPTO_CORE_TERMS

    # --- 2. Specific Instrument Phrases (Max Munch) ---
    specific_phrases = [
        r"digital\s+asset\s+securities?",
    ]

    sorted_specific_phrases = sorted(
        specific_phrases, key=lambda x: (-len(x), -x.count(r"\s+"))
    )

    # --- 3. Build Patterns ---
    
    # Strict/Soft are identical in Crypto context
    _CRYPTO_CONFIG = DERIVATIVES(
        PREFIX=strict_core_terms,
        STANDALONE_BASES=[BASE.OPTION],
        ADDITIONAL_BASES=[],
        STANDALONE_SUFFIXES=[SUFFIX.CONTRACT, SUFFIX.AGREEMENT],
    )
    _CRYPTO_PATTERN = DerivativeGenerator(config=_CRYPTO_CONFIG).generate()
    
    strict_crypto_regex = build_regex([_CRYPTO_PATTERN] + sorted_specific_phrases)
    soft_crypto_regex = build_regex([_CRYPTO_PATTERN] + sorted_specific_phrases)

    # Loose: Allows any base/suffix with the prefix
    _LOOSE_CONFIG = DERIVATIVES(
        PREFIX=strict_core_terms,
        ADDITIONAL_BASES=[],
        LOOSE=True,
    )
    _LOOSE_PATTERN = DerivativeGenerator(config=_LOOSE_CONFIG).generate()
    
    loose_crypto_regex = build_regex([_LOOSE_PATTERN] + sorted_specific_phrases)

    return strict_crypto_regex, soft_crypto_regex, loose_crypto_regex


def build_crypto_context_terms() -> Tuple[List[str], List[str], List[str]]:
    # 1. Explicit Instruments (Strict)
    crypto_instruments = [
        r"bitcoin\s+futures?",
        r"crypto\s+derivatives?",
    ]

    # 2. Specific Terms
    crypto_specifics = [
        r"blockchain",
        r"distributed\s+ledger",
        r"wallet",
        r"coinbase",
        r"mining",
        r"tokens?",
        r"stablecoins?",
        r"DeFi",
        r"NFTs?",
        r"smart\s+contracts?",
    ]

    # 3. Broader terms (Soft)
    crypto_broad = [
        r"digital\s+wallets?",
        r"custody",
        r"staking",
    ]

    strict_terms = crypto_instruments + crypto_specifics
    soft_terms = crypto_broad

    # 4. Risk Management Glue
    crypto_glue = CRYPTO_CORE_TERMS

    risk_terms = [build_risk_managment_phrase(crypto_glue)]

    return strict_terms, soft_terms, risk_terms


CRYPTO_STRICT_TERMS, CRYPTO_SOFT_TERMS, CRYPTO_RISK_TERMS = build_crypto_context_terms()
CRYPTO_CONTEXT_TERMS = CRYPTO_STRICT_TERMS + CRYPTO_SOFT_TERMS + CRYPTO_RISK_TERMS
CRYPTO_CONTEXT_REGEX = build_regex(CRYPTO_CONTEXT_TERMS)
CRYPTO_STRICT_CONTEXT_REGEX = build_regex(CRYPTO_STRICT_TERMS + CRYPTO_RISK_TERMS)
CRYPTO_RISK_REGEX = build_regex(CRYPTO_RISK_TERMS)
CRYPTO_REGEX, CRYPTO_SOFT_REGEX, CRYPTO_LOOSE_REGEX = build_crypto_regex()

CRYPTO_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(CRYPTO_CORE_TERMS)

def run_tests():
    from defs.derivatives_core import (
        MatchLevel,
        run_category_tests,
        run_category_tests_counter,
    )

    test_cases = [
        ("bitcoin futures", MatchLevel.STRICT),
        ("crypto swap", MatchLevel.STRICT),
        ("digital asset option", MatchLevel.STRICT),
        ("cryptocurrency derivative", MatchLevel.STRICT),
        ("virtual currency contract", MatchLevel.STRICT),
        ("crypto assets", MatchLevel.LOOSE),
    ]
    run_category_tests(test_cases, CRYPTO_REGEX, CRYPTO_SOFT_REGEX, CRYPTO_LOOSE_REGEX)

    counter_cases = [
        ("digital tokens", MatchLevel.LOOSE),
    ]
    run_category_tests_counter(counter_cases, CRYPTO_REGEX, CRYPTO_SOFT_REGEX, CRYPTO_LOOSE_REGEX)
