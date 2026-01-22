import re

from defs.derivatives_core import PRECISE_LOOSE_GEN_REGEX, UNAMBIGUOUS_BASE_TYPES
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _RISK_ALTERNATION, VALUATION_MODELS, build_risk_managment_phrase
from defs.acct_std import DERIVATIVE_STDS
from defs.exclusion_regex import ENTITY_TOKEN

def build_strict_gen_regex() -> tuple[re.Pattern, re.Pattern]:
    """
    Returns a tuple:
        (INSTRUMENT_REGEX, NOTIONAL_REGEX)

    INSTRUMENT_REGEX  → captures ONLY safe derivative patterns
    NOTIONAL_REGEX    → captures notional amount/principal/value phrases
    """

    # SAFE BASES: Low false-positive risk
    safe_bases = ["swaps", r"(?<!\bits\s)derivatives", "futures", "the derivative"]

    # UNSAFE STANDALONE: Require suffix
    unsafe_alone = [
        "swap",
        "collar",
        "hedge",
        "hedging",
        "futures",  # plural form
    ]

    # SPECIAL BASES: safe as well
    special_bases = UNAMBIGUOUS_BASE_TYPES

    # SAFE SUFFIXES
    suffixes = [
        "agreements?",
        "contracts?",
        "instruments?",
        "arrangements?",
    ]

    safe_bases_alt = build_alternation(safe_bases, sort_longest_first=True)
    unsafe_alone_alt = build_alternation(unsafe_alone, sort_longest_first=True)
    special_bases_alt = build_alternation(special_bases, sort_longest_first=True)
    suffix_alt = build_alternation(suffixes, sort_longest_first=True)

    # CRITICAL FIX: Reorder to enforce MAX MUNCH
    # Pattern 1: Safe bases WITH suffix (HIGHEST PRIORITY - longest match first)
    pattern1 = rf"{safe_bases_alt}[- ]{suffix_alt}"

    # Pattern 2: Unsafe bases MUST have suffix
    pattern2 = rf"{unsafe_alone_alt}[- ]{suffix_alt}"

    # Pattern 3: Safe bases standalone (LOWER PRIORITY)
    pattern3 = safe_bases_alt

    # Pattern 4: Special bases (complete phrases)
    pattern4 = special_bases_alt

    # Combine with specific phrases first (highest priority)
    specific_phrases = [
        "(?:cash[- ]flow|fair[- ]value|net[- ]investment) hedges?",
        r"hedges?\s+of\s+(?:the\s+)?net\s+investments?",
        "(?:embedded|financial|over[- ]the[- ]counter|otc) derivatives?",
        "(?:derivative[ -]financial|risk[ -]management) instruments?",
        # Derivative/Swap Balance Sheet Items
        "(?:derivative|swap) (?:liabilit(?:y|ies)|assets?)",
        # Explicit "Safe" Variants for Ambiguous Bases
        "zero[- ]cost collars?",
    ]
    specific_alt = build_alternation(specific_phrases, sort_longest_first=True)

    # FINAL: Specific phrases FIRST, then combined+suffix patterns, then standalone
    instrument_pattern = rf"{specific_alt}|{pattern4}|{pattern1}|{pattern2}|{pattern3}"

    INSTRUMENT_REGEX = re.compile(
        rf"\b(?P<instrument>{instrument_pattern})\b", re.IGNORECASE
    )
    NOTIONAL_REGEX = build_regex(["notional"])

    return INSTRUMENT_REGEX, NOTIONAL_REGEX


RISK_MANAGEMENT_TERMS = [
    r"to\s+hedge",
    r"exposures?",
    r"exposed\s+to",
    r"risk\s+management",
    rf"economic\s+{_RISK_ALTERNATION}",
    r"economic\s+hedges?",
    # --- Safe for Phase 1 Contextual Capture ---
    rf"(?:market|rate|currency|credit|equity|price)[ -]{_RISK_ALTERNATION}",
    r"fluctuations?",  # e.g., "protect against fluctuations"
    r"volatility",  # e.g., "manage volatility"
    build_risk_managment_phrase(),
]

# Generic hedging context (required for generic matches)
hedging_terms = [
    r"relationships?",
    r"strateg(?:y|ies)",
    r"activit(?:y|ies)",
    r"programs?",
    r"positions?",
    r"assets?",
    r"vehicles?",
    r"liabilit(?:y|ies)",
    r"polic(?:y|ies)",
    r"transactions?",
    r"designations?",
    r"(?:in)?effectiveness",
    r"objectives?",
    r"instruments?",
    r"arrangements?",
    r"exposures?",
    r"derivatives?",
    r"items?",
    r"horizons?",
    r"document(?:s|ations?)?",
    r"terms?",
    r"accounting",
    r"expenses?",
]
hedge_phrases = build_alternation(hedging_terms, sort_longest_first=True)
SOFT_GEN_TERMS = [
    r"(?:in)?effective portions?",
    # Expanded Hedging Noun Contexts (Strategy, Activity, Program, etc.)
    rf"(?:hedg(?:es?|ing)|derivatives?)\s+{hedge_phrases}",
    r"(?:not\s+)?designat(?:ed?|es|ion)\s+(?:as\s+)?(?:a\s+|the\s+)?(?:hedg(?:es?|ing))",
    r"(?:gain|loss) on derivatives?",
    r"value of derivatives?",
    r"notional",
    r"bifurcat(?:ed|ion|ing)",
]


HEDGING_CONTEXT_TERMS = (
    [ 
        ENTITY_TOKEN.strip(),
    ]
    + SOFT_GEN_TERMS
    + RISK_MANAGEMENT_TERMS
    + VALUATION_MODELS
    + DERIVATIVE_STDS
)


HEDGING_CONTEXT_REGEX = build_regex(HEDGING_CONTEXT_TERMS)
RISK_MANAGEMENT_REGEX = build_regex(RISK_MANAGEMENT_TERMS)

GEN_REGEX, NOTIONAL_REGEX = build_strict_gen_regex()
GEN_STRICT_CONTEXT_REGEX = build_regex(SOFT_GEN_TERMS)
GEN_HEDGES = build_regex(
    [  # Specific FX Instrument Names/Hedges
        r"hedges?\s+of\s+(?:the\s+)?net\s+investments?",
        r"(?:[\"“\'])?(?:net investment|fair\s+value|cash\s+flow)(?:[\"“\'])?\s+hedges?",
    ]
)

def run_tests():
    from defs.derivatives_core import (
        LOOSE_GEN_REGEX,
        MatchLevel,
        run_category_tests,
    )
    test_cases = [
        ("currency options and warrants", MatchLevel.STRICT),
        (
            "equity options and warrants",
            MatchLevel.LOOSE,
        ),  # Fails double base (equity exclusion), caught as Loose Generic (warrants)
        ("stock options and warrants", MatchLevel.LOOSE),
        ("options and warrants", MatchLevel.STRICT),
        ("swaps and futures", MatchLevel.STRICT),
        ("caps and floors", MatchLevel.STRICT),
        ("contracts such as swaps", MatchLevel.STRICT),
        ("contracts such as options", MatchLevel.STRICT),
        ("contracts sets the cap", MatchLevel.STRICT),
    ]
    print("\nRunning Double Base Tests...")
    run_category_tests(test_cases, GEN_REGEX, PRECISE_LOOSE_GEN_REGEX, LOOSE_GEN_REGEX)

if __name__ == "__main__":
    run_tests()
