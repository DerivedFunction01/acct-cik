from enum import Enum
import re


from defs.derivatives_core import BASE, MULTI_BASE, PHYSICAL_COMMERCIAL_TERMS, PRECISE_LOOSE_GEN_REGEX, SPEC_BASE, SUFFIX, VERB_LOOKAHEAD, VERB_LOOKBEHIND, Groups, build_compound
from defs.regex_lib import add_restrictions, build_alternation, build_regex, plural, to_build_alternation
from defs.shared_context import _RISK_ALTERNATION, VALUATION_MODELS, build_risk_managment_phrase
from defs.acct_std import DERIVATIVE_STDS
from defs.exclusion_regex import ENTITY_TOKEN

class GEN_DERIVATIVE_PATTERNS(Enum):
    HEDGING_INSTRUMENT_ALONE = build_compound(
        BASE.HEDGE,
        [
            SUFFIX.CONTRACT,
            SUFFIX.INSTRUMENT,
            BASE.DERIVATIVE,
        ],
    )
    # Miscellaneous complex patterns
    OTHER_INSTRUMENTS = build_alternation(
        [
            r"(?:derivative\s+financial|risk[- ]managment)\s+instruments?",
            r"(?<!to )hedges?\s+of\s+(?:the\s+)?net\s+investments?(?!\s+(?:for|in|at))",
        ]
    )
    EMBEDDED_INSTRUMENT = build_compound([r"embedded", r"over[- ]the[- ]counter", r"otc"], BASE.DERIVATIVE)
    HEDGES = build_compound([r"fair[- ]value", r"cash[- ]flow", r"net[- ]investment"], BASE.HEDGE)
    # Base + Suffix combinations
    INSTRUMENT_COMPOUND = build_compound(
        Groups.UNAMBIGUOUS_BASES,
        [SUFFIX.CONTRACT, SUFFIX.INSTRUMENT, SUFFIX.AGREEMENT, SUFFIX.ARRANGEMENT],
    )

    DERIVATIVE_CONTRACT = build_compound(Groups.UNAMBIGUOUS_BASES + Groups.AMBIGUOUS_BASES, SUFFIX.CONTRACT)
    ASSET_LIABILITY = build_compound(
        [BASE.DERIVATIVE, BASE.SWAP], [SUFFIX.ASSET, SUFFIX.LIABILITY]
    )


# =============================================================================
# TABLE SPECIFIC REGEX
# =============================================================================
def build_table_regex() -> re.Pattern:
    """
    A stricter regex for table filtering that eliminates singular noise
    (future, option, forward) but keeps the plurals often found in headers.
    """

    # 1. Safe Plurals (Standalones that are safe in tables)
    # Note: 'swaps' and 'derivatives' are already in ALL_REGEX via GEN_REGEX
    # We add the others that are usually unsafe singular but safe plural.
    table_safe_plurals = [
        BASE.FUTURES,
        add_restrictions(
            plural(BASE.FORWARD),
            lookaheads=PHYSICAL_COMMERCIAL_TERMS + VERB_LOOKAHEAD,
            lookbehinds=VERB_LOOKBEHIND
            + [
                r"carry",
                r"carrying",
                r"carried",
                r"look",
                r"looking",
                r"looked",
                r"brought",
                r"put",
                r"push",
                r"set",
            ],
        ),
        plural(BASE.COLLAR),
        BASE.SWAPTION,
        plural(BASE.DERIVATIVE),
        plural(BASE.SWAP),
        plural(BASE.PUT),
        plural(BASE.CALL),
    ] # Rest will be caught by gen_regex
    return build_regex(table_safe_plurals)


TABLE_REGEX = build_table_regex()

def build_strict_gen_regex() -> tuple[re.Pattern, re.Pattern]:
    """
    Returns a tuple:
        (INSTRUMENT_REGEX, NOTIONAL_REGEX)

    INSTRUMENT_REGEX  → captures ONLY safe derivative patterns
    NOTIONAL_REGEX    → captures notional amount/principal/value phrases
    """

    # # SAFE BASES: Low false-positive risk
    # safe_bases = [SWAPS, DERIVATIVES, FUTURES, TRIPLE_BASE]

    # # UNSAFE STANDALONE: Require suffix
    # unsafe_alone = [
    #     "swap",
    #     "collar",
    #     "hedge",
    #     "hedging",
    #     "futures",  # plural form
    # ]

    # # SPECIAL BASES: safe as well
    # special_bases = EXTRA_BASE_COMBOS

    # # SAFE SUFFIXES
    # suffixes = [
    #     "agreements?",
    #     "contracts?",
    #     "instruments?",
    #     "arrangements?",
    # ]

    # safe_bases_alt = build_alternation(safe_bases, sort_longest_first=True)
    # unsafe_alone_alt = build_alternation(unsafe_alone, sort_longest_first=True)
    # special_bases_alt = build_alternation(special_bases, sort_longest_first=True)
    # suffix_alt = build_alternation(suffixes, sort_longest_first=True)

    # # CRITICAL FIX: Reorder to enforce MAX MUNCH
    # # Pattern 1: Safe bases WITH suffix (HIGHEST PRIORITY - longest match first)
    # pattern1 = rf"{safe_bases_alt}[- ]{suffix_alt}"

    # # Pattern 2: Unsafe bases MUST have suffix
    # pattern2 = rf"{unsafe_alone_alt}[- ]{suffix_alt}"

    # # Pattern 3: Safe bases standalone (LOWER PRIORITY)
    # pattern3 = safe_bases_alt

    # # Pattern 4: Special bases (complete phrases)
    # pattern4 = special_bases_alt
    DERIVATIVE_PATTERNS = [
        GEN_DERIVATIVE_PATTERNS.HEDGING_INSTRUMENT_ALONE,
        GEN_DERIVATIVE_PATTERNS.OTHER_INSTRUMENTS,
        GEN_DERIVATIVE_PATTERNS.EMBEDDED_INSTRUMENT,
        GEN_DERIVATIVE_PATTERNS.HEDGES,
        SPEC_BASE.CORE_OPTION,
        SPEC_BASE.SPECIAL_SWAP,
        SPEC_BASE.SPECIAL_FUTURES,
        SPEC_BASE.SPECIAL_OTHER,
        GEN_DERIVATIVE_PATTERNS.DERIVATIVE_CONTRACT,
        GEN_DERIVATIVE_PATTERNS.INSTRUMENT_COMPOUND,
        GEN_DERIVATIVE_PATTERNS.ASSET_LIABILITY,
        MULTI_BASE.TRIPLE_BASE,
        MULTI_BASE.MIXED_DOUBLE,
        add_restrictions(
            plural(to_build_alternation([BASE.SWAP, BASE.FUTURES, BASE.DERIVATIVE])),
            lookbehinds=VERB_LOOKBEHIND,
            lookaheads=VERB_LOOKAHEAD +[ r"participants?", r"dealers?", r"markets?"]
        )
    ]
    derivative_alt = to_build_alternation(DERIVATIVE_PATTERNS, sort_longest_first=True)

    INSTRUMENT_REGEX = re.compile(
        rf"\b(?P<instrument>{derivative_alt})\b", re.IGNORECASE
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
    r"hedges?\s+of\s+(?:the\s+)?net\s+investments?"
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
    # STRICT IS THE ONLY ONE THAT IS USED FOR NO-PREFIX WEB EXTRACTION.
    # ACTUAL DERIVATIVES MUST BE STRICT, AMBIGUOUS MUST BE SOFT OR LOWER
    # LOOSE PRECISE MATCHES PLURALS
    # LOOSE MATCHES ANY
    test_cases = [
        # --- STRICT: True Derivatives ---
        ("swap contract", MatchLevel.STRICT),
        ("option contract", MatchLevel.STRICT),
        ("hedging instrument", MatchLevel.STRICT),
        ("derivative financial instruments", MatchLevel.STRICT),
        ("cash flow hedge", MatchLevel.STRICT),
        ("fair value hedge", MatchLevel.STRICT),
        ("embedded derivative", MatchLevel.STRICT),
        ("call option", MatchLevel.STRICT),
        ("put option", MatchLevel.STRICT),
        ("swap liability", MatchLevel.STRICT),
        ("derivative asset", MatchLevel.STRICT),
        ("swaps and options", MatchLevel.STRICT), # Mixed Double
        ("swaps, options and futures", MatchLevel.STRICT), # Triple Base
        ("contracts such as swaps", MatchLevel.STRICT),
        ("hedge contract", MatchLevel.STRICT),
        ("hedges of net investments", MatchLevel.STRICT),
        ("swap agreement", MatchLevel.STRICT),
        ("swaps", MatchLevel.STRICT), # Plural Unambiguous (Restricted)
        ("futures", MatchLevel.STRICT), # Plural Unambiguous (Restricted)

        # --- SOFT: Ambiguous Plurals / Double Ambiguous / Unambiguous Singular ---
        ("options", MatchLevel.SOFT), # Plural Ambiguous
        ("warrants", MatchLevel.SOFT), # Plural Ambiguous (in precise loose)
        ("caps and floors", MatchLevel.SOFT), # Double Ambiguous
        ("contracts such as options", MatchLevel.SOFT),
        ("contracts sets the cap", MatchLevel.SOFT),
        ("currency options and warrants", MatchLevel.SOFT),
        ("swap", MatchLevel.SOFT), # Singular Unambiguous is in PRECISE_LOOSE
        ("to swaps", MatchLevel.SOFT), # Restricted Strict -> Falls to Soft (PRECISE_LOOSE matches "swaps")

        # --- LOOSE: Singular Ambiguous / Broad ---
        ("stock options and warrants", MatchLevel.LOOSE),
        ("option", MatchLevel.LOOSE), # Singular Ambiguous
        ("cap", MatchLevel.LOOSE), # Singular Ambiguous
        ("market cap", MatchLevel.LOOSE), # Matches "cap" in LOOSE
    ]
    print("\nRunning Gen Regex Tests...")
    run_category_tests(test_cases, GEN_REGEX, PRECISE_LOOSE_GEN_REGEX, LOOSE_GEN_REGEX)

if __name__ == "__main__":
    
    run_tests()
