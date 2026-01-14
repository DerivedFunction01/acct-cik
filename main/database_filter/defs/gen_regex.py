import re
from typing import Tuple

from defs.derivatives_core import ALL_BASE_TYPES, ALL_SUFFIXES, SPECIAL_BASE, UNAMBIGUOUS_BASE_TYPES
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION, VALUATION_MODELS

def build_strict_gen_regex() -> tuple[re.Pattern, re.Pattern]:
    """
    Returns a tuple:
        (INSTRUMENT_REGEX, NOTIONAL_REGEX)

    INSTRUMENT_REGEX  → captures ONLY safe derivative patterns
    NOTIONAL_REGEX    → captures notional amount/principal/value phrases
    """

    # SAFE BASES: Low false-positive risk
    safe_bases = ["swaps", r"(?<!\bits\s)derivatives", "futures"]

    # UNSAFE STANDALONE: Require suffix
    unsafe_alone = [
        "swap",
        "cap",
        "floor",
        "collar",
        "derivative",
        "hedge",
        "hedging",
        "lock",  # plural form
        "futures",  # plural form
    ]

    # SPECIAL BASES: safe as well
    special_bases = SPECIAL_BASE

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
    # Combine with specific phrases first (highest priority)
    specific_phrases = [
        "(?:cash[- ]flow|fair[- ]value) hedges?",
        "(?:embedded|financial|over[- ]the[- ]counter|otc) derivatives?",
        "(?:derivative[ -]financial|risk[ -]management) instruments?",
        # Derivative/Swap Balance Sheet Items
        "(?:derivative|swap) (?:liabilit(?:y|ies)|assets?)",
        # Hedging Balance Sheet Items
        "hedging (?:liabilit(?:y|ies)|assets?|vehicles?)",  # <-- NEW
        # Explicit "Safe" Variants for Ambiguous Bases
        "forward contracts?",
        "forward agreements?",  # <-- NEW
        "option contracts?",  # <-- NEW
    ]
    specific_alt = build_alternation(specific_phrases, sort_longest_first=True)

    # FINAL: Specific phrases FIRST, then combined+suffix patterns, then standalone
    instrument_pattern = rf"{specific_alt}|{pattern4}|{pattern1}|{pattern2}|{pattern3}"

    INSTRUMENT_REGEX = re.compile(
        rf"\b(?P<instrument>{instrument_pattern})\b", re.IGNORECASE
    )
    NOTIONAL_REGEX = build_regex(["notional"])

    return INSTRUMENT_REGEX, NOTIONAL_REGEX

def build_loose_gen_regex_precise() -> re.Pattern:
    plurals = [
        "caps",
        "floors",
        "warrants",
        "puts",
        "calls",
        "contracts?",
        "instruments?",
    ]
    return build_regex(UNAMBIGUOUS_BASE_TYPES + plurals)


def build_loose_gen_regex() -> re.Pattern:
    plurals = [
        "warrants",
    ]
    return build_regex(ALL_BASE_TYPES + plurals + ALL_SUFFIXES)


DERIVATIVE_STDS = [
    # US GAAP - Derivatives & Hedging
    r"ASC\s+815",  # The big one (Derivatives and Hedging)
    r"SFAS\s+133",  # The legacy big one
    r"FAS\s+133",
    r"Statement\s+133",
    # US GAAP - Fair Value (Strong signal when combined with "Option/Warrant")
    r"ASC\s+820",
    r"SFAS\s+157",
    # US GAAP - Distinguishing Liabilities from Equity (Crucial for Warrants)
    r"ASC\s+480",  # Distinguishing Liabilities from Equity
    r"SFAS\s+150",
    # International (IFRS)
    r"IFRS\s+9",  # Financial Instruments
    r"IAS\s+39",  # Legacy Financial Instruments
    r"IAS\s+32",  # Presentation (Liability vs Equity)
    r"SFAS\s+150",
    # --- NEW: EITF 00-19 (The "Warrant Liability" Key) ---
    # Matches: "EITF 00-19", "EITF Issue No. 00-19", "EITF 0019"
    # Note: We allow flexible separators between '00' and '19'
    r"EITF\s+(?:Issue\s+)?(?:No\.?\s+)?00[-–—\s]?19",
    # --- NEW: The Codified Version (ASC 815-40) ---
    # EITF 00-19 was codified into ASC 815-40 "Contracts in Entity's Own Equity"
    r"ASC\s+815[-–—\s]?40",
    # Just adding this here
    r"bifurcat(?:ed|ion|ing)",
]
RISK_MANAGEMENT_TERMS = [
    r"to\s+hedge",
    r"mitigat(?:e|es|ed|ing)",
    r"protect(?:s|ed|ing)?",
    r"manage(?:s|d|ing)?",
    r"exposures?",
    r"exposed\s+to",
    r"risk\s+management",
    rf"economic\s+{_RISK_ALTERNATION}",
    r"economic\s+hedges?",
    # --- Safe for Phase 1 Contextual Capture ---
    rf"(?:market|rate|currency|credit|equity|price)[ -]{_RISK_ALTERNATION}",
    r"fluctuations?",  # e.g., "protect against fluctuations"
    r"volatility",  # e.g., "manage volatility"
    r"stabiliz(?:e|es|ed|ing)",
    r"to\s+(?:limit|control|reduce|offset)",
]

# Generic hedging context (required for generic matches)
hedging_terms = [
    r"relationships?",
    r"strateg(?:y|ies)",
    r"activit(?:y|ies)",
    r"programs?",
    r"positions?",
    r"assets?",
    r"liabilit(?:y|ies)",
    r"polic(?:y|ies)",
    r"transactions?",
    r"designations?",
    r"effectiveness",
    r"ineffectiveness",
    r"objectives?",
    r"instruments?",
    r"arrangements?",
    r"exposures?",
    r"derivatives?",
    r"items?",
    r"horizons?",
    r"document(?:s|ations?)",
    r"terms?",
    r"accounting",
]
hedge_phrases = build_alternation(hedging_terms, sort_longest_first=True)
SOFT_GEN_TERMS = [
    r"(?:instruments?|contracts?) are designated",
    r"(?:ineffective|effective) portions?",
    # Expanded Hedging Noun Contexts (Strategy, Activity, Program, etc.)
    rf"hedg(?:es?|ing)\s+{hedge_phrases}",
    r"derivative expenses?",
    r"designated as (?:a )?hedg(?:es?|ing)",
    r"(?:gain|loss) on derivatives?",
]


HEDGING_CONTEXT_TERMS = (
    [
        r"bifurcat(?:ed|ion|ing)",
    ]
    + SOFT_GEN_TERMS
    + RISK_MANAGEMENT_TERMS
    + VALUATION_MODELS
    + DERIVATIVE_STDS
)


DER_STD_REGEX = build_regex(DERIVATIVE_STDS)
HEDGING_CONTEXT_REGEX = build_regex(HEDGING_CONTEXT_TERMS)
RISK_MANAGEMENT_REGEX = build_regex(RISK_MANAGEMENT_TERMS)
LOOSE_GEN_REGEX = build_loose_gen_regex()
PRECISE_LOOSE_GEN_REGEX = build_loose_gen_regex_precise()
GEN_REGEX, NOTIONAL_REGEX = build_strict_gen_regex()
GEN_STRICT_CONTEXT_REGEX = build_regex(SOFT_GEN_TERMS + DERIVATIVE_STDS)
