import re
from enum import Enum, auto
from typing import List, Optional, Tuple
from defs.regex_lib import build_alternation, build_compound, build_regex, add_restrictions, to_build_alternation


# ============================================================================
# HELPERS
# ============================================================================


VERB_LOOKBEHIND = [r"to"]
VERB_LOOKAHEAD = [r"the", r"an", r"a", r"its", r"rate", r"interest", r"forward"]

PHYSICAL_COMMERCIAL_TERMS = [  # words against "oil forward shipment, or deliverable forward receipt" from being matched
    r"deliver(?:y|ies)",
    r"orders?",
    r"sales?",
    r"suppl(?:y|ies)",
    r"confirmation",
    r"invoices?",
    r"shipments?",
    r"receipts?",
    r"inventor(?:y|ies)",
    r"stocks?",
]

COMMODITY_COMMERICIAL_PATTERN = build_alternation(
    PHYSICAL_COMMERCIAL_TERMS + [r"purchases?"], sort_longest_first=True
)


class BASE(Enum):
    SWAP = r"swaps?"
    FORWARD = (
        r"forwards?"  # Note: add_restrictions logic handled in final assembly if needed
    )
    COLLAR = r"collars?"
    DERIVATIVE = r"derivatives?"
    FUTURES = r"(?:perpetual\s+)?futures"
    SWAPTION = r"swaptions?"
    OPTION = r"options?"
    LOCK = r"locks?"
    CAP = r"caps?"
    FLOOR = r"floors?"
    PUT = r"puts?"
    CALL = r"calls?"
    HEDGE = r"hedg(?:es?|ing)"
    WARRANT = r"warrants?"


class SUFFIX(Enum):
    CONTRACT = r"contracts?"
    INSTRUMENT = r"instruments?"
    AGREEMENT = r"agreements?"
    ARRANGEMENT = r"arrangements?"
    COMMITMENT = r"commitments?"
    TRANSACTION = r"transactions?"
    POSITION = r"positions?"


# ============================================================================
# COLLECTIONS (Logical groupings - Standard Lists)
# ============================================================================
class Groups:
    UNAMBIGUOUS_BASES = [
        BASE.SWAP,
        BASE.FORWARD,
        BASE.COLLAR,
        BASE.DERIVATIVE,
        BASE.FUTURES,
        BASE.SWAPTION,
    ]
    AMBIGUOUS_BASES = [BASE.OPTION, BASE.LOCK, BASE.CAP, BASE.FLOOR]
    OTHER_BASES = [BASE.PUT, BASE.CALL, BASE.HEDGE, BASE.WARRANT]

    # Suffix Sets
    UNAMBIGUOUS_SUFFIXES = [SUFFIX.CONTRACT, SUFFIX.INSTRUMENT]
    AMBIGUOUS_SUFFIXES = [SUFFIX.AGREEMENT, SUFFIX.ARRANGEMENT]

    # Modifiers
    SPECIAL_SWAP_MODS = [
        r"basis",
        r"variance",
        r"volatility",
        r"total[- ]return",
        r"back[- ]to[- ]back",
    ]
    SPECIAL_OPTION_MODS = [
        r"asian",
        r"bermuda",
        r"basket",
        r"rainbow",
        r"lookback",
        r"exotic",
        r"barrier",
        BASE.PUT,
        BASE.CALL,
    ]
    CONTRACT_MODS = UNAMBIGUOUS_BASES + AMBIGUOUS_BASES + OTHER_BASES


# ============================================================================
# FINAL PRODUCTS (The actual patterns to match - Enums), fo
# ============================================================================
class DERIVATIVE_PATTERNS(Enum):
    pass

class DERIVATIVES(DERIVATIVE_PATTERNS):
    # -------------------------------
    # These stand alone as derivatives
    # -------------------------------
    SPECIAL_OPTION = build_compound(Groups.SPECIAL_OPTION_MODS, BASE.OPTION)
    SPECIAL_SWAP = build_compound(Groups.SPECIAL_SWAP_MODS, BASE.SWAP)
    # Optional: Include raw base patterns if needed elsewhere
    UNAMBIGUOUS_BASES = build_alternation(
        [b.value for b in Groups.UNAMBIGUOUS_BASES], sort_longest_first=True
    )
    AMBIGUOUS_BASES = build_alternation(
        [b.value for b in Groups.AMBIGUOUS_BASES], sort_longest_first=True
    )
    OTHER_BASES = build_alternation(
        [b.value for b in Groups.OTHER_BASES], sort_longest_first=True
    )
    DERIVATIVE_CONTRACT = build_compound(Groups.CONTRACT_MODS, SUFFIX.CONTRACT)

    # Base + Suffix combinations
    INSTRUMENT_COMPOUND = build_compound(
        Groups.UNAMBIGUOUS_BASES,
        [SUFFIX.CONTRACT, SUFFIX.INSTRUMENT, SUFFIX.AGREEMENT, SUFFIX.ARRANGEMENT],
    )

    HEDGING_INSTRUMENT = build_compound(
        [
            SUFFIX.CONTRACT,
            SUFFIX.INSTRUMENT,
            BASE.DERIVATIVE,
            SUFFIX.ARRANGEMENT,
            SUFFIX.AGREEMENT,
        ],
        BASE.HEDGE,
    )
    ASSET_LIABILITY = build_compound(
        [BASE.DERIVATIVE, BASE.SWAP], [r"liabilit(?:y|ies)", r"assets?"]
    )


def build_double_base_pattern() -> Tuple[str, str]:
    """
    Final Refined Logic:
    Matches: 'equity warrants and option contracts'
    Blocks: 'equity options and warrants'
    """
    # 1. Base Values
    base_vals = [
        b.value
        for b in (
            Groups.UNAMBIGUOUS_BASES + Groups.AMBIGUOUS_BASES + Groups.OTHER_BASES
        )
    ]
    base_vals += [DERIVATIVES.SPECIAL_OPTION.value, DERIVATIVES.SPECIAL_SWAP.value]
    bases_alt = to_build_alternation(base_vals, sort_longest_first=True)

    _SFX = Groups.UNAMBIGUOUS_SUFFIXES + Groups.AMBIGUOUS_SUFFIXES
    _SFX_ALT = to_build_alternation(_SFX)

    # 2. Logic: The Suffix-Protected Pair Block
    sep = r"(?:\s*,?\s*(?:and|or|&)\s+|[\s,]+)"

    # Block ONLY if partner is 'naked' (no suffix).
    # If partner has a suffix, the lookahead fails and the match proceeds.
    _OPT_STRICT = add_restrictions(
        BASE.OPTION.value, lookaheads=[rf"{sep}{BASE.WARRANT.value}\b(?!\s+{_SFX_ALT})"]
    )
    _WARR_STRICT = add_restrictions(
        BASE.WARRANT.value, lookaheads=[rf"{sep}{BASE.OPTION.value}\b(?!\s+{_SFX_ALT})"]
    )

    # 3. Fixed-Width Chained Lookbehinds
    forbidden_endings = (
        r"(?<!\sa)(?<!\san)(?<!\sthe)" r"(?<!\swho)(?<!\sthat)(?<!\swhich)"
    )
    forbidden_starters = r"(?!\s+(?:to|in|on|for|of|with|by|as|at))"
    gap = r"(?:\W+(?:\w+\W+){0,2}?)"

    # 4. Assembly
    # Starters must include:
    # 1. Suffixes ("contracts", "agreements")
    # 2. Strict Options/Warrants (to enforce the lookahead block)
    # 3. All other bases ("swaps", "futures", "caps", etc.)
    _OTHER_BASES = [b for b in (Groups.UNAMBIGUOUS_BASES + Groups.AMBIGUOUS_BASES + Groups.OTHER_BASES) if b not in [BASE.OPTION, BASE.WARRANT]]
    
    _STARTERS = to_build_alternation(_SFX + [_OPT_STRICT, _WARR_STRICT] + _OTHER_BASES)
    start_pattern = rf"(?:{_STARTERS})(?!\s+to){gap}{forbidden_endings}{forbidden_starters}(?:{bases_alt})"

    double_base = rf"{start_pattern}(?:{sep}(?:{bases_alt})(?:\s+{_SFX_ALT})?)*"

    # 5. Triple Base (Standalone Catch-all)
    loose_base_vals = base_vals + [BASE.WARRANT.value]
    bases_loose_alt = to_build_alternation(loose_base_vals, sort_longest_first=True)
    triple_base = (
        rf"(?:{bases_loose_alt})"
        rf"(?!\s+to){gap}{forbidden_endings}{forbidden_starters}"
        rf"(?:{bases_loose_alt})"
        rf"(?:{sep}(?:{bases_loose_alt}))+"
    )

    return double_base, triple_base


class MULTI_BASE:
    DOUBLE_BASE, TRIPLE_BASE = build_double_base_pattern()


class DERIVATIVES_EXPORT(DERIVATIVE_PATTERNS):
    """
    Export patterns: All derivative detection patterns.
    Includes DERIVATIVES patterns plus multi-base patterns.

    Usage:
    - Standalone matching: SPECIAL_OPTION, SPECIAL_SWAP, TRIPLE_BASE, etc.
    - Prefix matching: Use DOUBLE_BASE with "interest rate", "currency", etc.
    """

    # From DERIVATIVES (already high-confidence)
    SPECIAL_OPTION = DERIVATIVES.SPECIAL_OPTION
    SPECIAL_SWAP = DERIVATIVES.SPECIAL_SWAP
    DERIVATIVE_CONTRACT = DERIVATIVES.DERIVATIVE_CONTRACT
    INSTRUMENT_COMPOUND = DERIVATIVES.INSTRUMENT_COMPOUND
    HEDGING_INSTRUMENT = DERIVATIVES.HEDGING_INSTRUMENT
    ASSET_LIABILITY = DERIVATIVES.ASSET_LIABILITY
    UNAMBIGUOUS_BASES = DERIVATIVES.UNAMBIGUOUS_BASES
    AMBIGUOUS_BASES = DERIVATIVES.AMBIGUOUS_BASES
    OTHER_BASES = DERIVATIVES.OTHER_BASES


    # Multi-base patterns
    DOUBLE_BASE = MULTI_BASE.DOUBLE_BASE  # "puts and options" (attach to prefix)
    TRIPLE_BASE = MULTI_BASE.TRIPLE_BASE  # "caps, floors, and collars" (standalone)

    STRICT_PATTERN = to_build_alternation(
        [
            DERIVATIVES.SPECIAL_OPTION,
            DERIVATIVES.SPECIAL_SWAP,
            DERIVATIVES.DERIVATIVE_CONTRACT,
            DERIVATIVES.INSTRUMENT_COMPOUND,
            DERIVATIVES.HEDGING_INSTRUMENT,
            DERIVATIVES.ASSET_LIABILITY,
            DERIVATIVES.UNAMBIGUOUS_BASES,
            MULTI_BASE.TRIPLE_BASE,
            MULTI_BASE.DOUBLE_BASE,
            
        ],
        sort_longest_first=True,
    )

def build_smart_regex(
    core_terms: List[str],
    context_terms: str,
    specific_phrases: List[str],
) -> str:
    """
    Build smart regex ensuring longest matches first.
    "interest rate swap contract" matches fully, not just "interest rate swap"
    """
    core_pattern = build_alternation(core_terms, sort_longest_first=True)

    # Core + suffix: "interest rate" + "-" + "swap"
    pattern1 = (
        rf"(?:{core_pattern})"  # e.g., "interest rate"
        r"[- ]"  # MANDATORY separator (space or hyphen)
        rf"(?:{context_terms})"  # MANDATORY: base or (base + suffix)
    )

    # Specific phrases like "zero coupon swaps"
    if not specific_phrases:
        return pattern1

    pattern2 = build_alternation(specific_phrases, sort_longest_first=True)

    # Return sorted so longest specific phrases come first
    # E.g., "interest rate swap agreement" before "interest rate swap"
    return build_alternation([pattern2, pattern1], True)


# --- Central Alternations for Instrument Components (Max Munch Sorting Applied) ---
base_alternation = build_alternation(BASE_TYPES, True)
BASE_REGEX = build_regex(ALL_BASE_TYPES)
safe_base_alternation = build_alternation(UNAMBIGUOUS_BASE_ENDING, True)
standalone_alternation = build_alternation(
    UNAMBIGUOUS_SUFFIXES + UNAMBIGUOUS_BASE_ENDING, True
)
unsafe_standalone_alternation = build_alternation(SUFFIXES + BASE_TYPES, True)
full_suffix_alternation = build_alternation(ALL_SUFFIXES + ALL_BASE_TYPES + ["hedging"], True)
# ----------------------------------------------------------------------------------


def expand_instruments(
    unsafe: bool = True,
    exclude_standalone_suffixes: Optional[bool] = None,
    additional_standalone_suffixes: Optional[List[str]] = None,
    additional_bases: Optional[List[str]] = None,
    full_alternation: bool = False,
) -> str:
    """
    Creates an optimized alternation pattern.

    Fixed Logic:
    1. Ensures (OldBase OR NewBase) + Suffix is treated as a single unit.
    2. Ensures additional_bases are NOT matched as standalone words.
    """
    # Default: If unsafe (Soft), exclude suffixes to prevent "Corn Agreement" (Context).
    # If safe (Strict), include suffixes to allow "Interest Rate Contract" (Instrument).
    if exclude_standalone_suffixes is None:
        exclude_standalone_suffixes = not unsafe

    # 1. Construct the Base Component for the Combined PatternW
    # We wrap (Existing | New) together so the suffix applies to BOTH.
    if additional_bases:
        new_base_alt = build_alternation(additional_bases, True)
        # Result: (?:(?:existing_bases)|(?:new_bases))
        effective_base_pattern = rf"(?:{base_alternation}|{new_base_alt})"
    else:
        effective_base_pattern = base_alternation

    # 2. Base + Suffix Combination (Highest priority)
    # The [- ] separator now applies to everything in effective_base_pattern
    # Matches: "swap agreement", "protection contract"
    combined_pattern = rf"(?:{effective_base_pattern}[- ]{suffix_alternation})"

    # 3. Standalone Term (Lower priority)
    # Note: We DO NOT add additional_bases here. They will fail to match if they lack a suffix.
    if not exclude_standalone_suffixes:
        base_standalone = (
            unsafe_standalone_alternation if unsafe else standalone_alternation
        )
    else:
        base_standalone = safe_base_alternation

    # 4. Integrate Additional Standalone SUFFIXES
    extras = []
    if additional_standalone_suffixes:
        extras.append(build_alternation(additional_standalone_suffixes, True))

    if extras:
        # Append extras to the standalone pattern
        extras_pattern = "|".join(extras)
        final_standalone = rf"{base_standalone}|{extras_pattern}"
    else:
        final_standalone = base_standalone
    if full_alternation:
        return rf"{combined_pattern}|{final_standalone}|{full_suffix_alternation}"
    else:
        # 5. Final Assembly (Max Munch: Combined first)
        return rf"{combined_pattern}|{final_standalone}"


def build_loose_gen_regex() -> re.Pattern:
    # Matches any base or suffix
    # Used for broad filtering/denial logic
    all_bases = [b.value for b in (Groups.UNAMBIGUOUS_BASES + Groups.AMBIGUOUS_BASES + Groups.OTHER_BASES)]
    all_suffixes = [s.value for s in (Groups.UNAMBIGUOUS_SUFFIXES + Groups.AMBIGUOUS_SUFFIXES)] + [SUFFIX.COMMITMENT.value, SUFFIX.TRANSACTION.value, SUFFIX.POSITION.value]
    
    return build_regex(all_bases + all_suffixes)


def build_loose_gen_regex_precise() -> re.Pattern:
    # Matches unambiguous bases + specific plurals of ambiguous ones
    # Used for stricter context checks
    unambiguous = [b.value for b in Groups.UNAMBIGUOUS_BASES]
    plurals = [
        "options", "warrants", "caps", "floors", "locks", 
        "puts", "calls", "contracts", "instruments"
    ]
    return build_regex(unambiguous + plurals)


# --- Definitions for Export/Usage in other files ---
BASE_TYPES = [b.value for b in Groups.UNAMBIGUOUS_BASES + Groups.AMBIGUOUS_BASES]
ALL_BASE_TYPES = BASE_TYPES + [b.value for b in Groups.OTHER_BASES]
UNAMBIGUOUS_BASE_ENDING = [b.value for b in Groups.UNAMBIGUOUS_BASES]
UNAMBIGUOUS_BASE_TYPES = UNAMBIGUOUS_BASE_ENDING # Alias

UNAMBIGUOUS_SUFFIXES = [s.value for s in Groups.UNAMBIGUOUS_SUFFIXES]
SUFFIXES = UNAMBIGUOUS_SUFFIXES + [s.value for s in Groups.AMBIGUOUS_SUFFIXES]
ALL_SUFFIXES = SUFFIXES + [SUFFIX.COMMITMENT.value, SUFFIX.TRANSACTION.value, SUFFIX.POSITION.value]

LOOSE_GEN_REGEX = build_loose_gen_regex()
PRECISE_LOOSE_GEN_REGEX = build_loose_gen_regex_precise()


class MatchLevel(Enum):
    STRICT = auto()
    SOFT = auto()
    LOOSE = auto()
    NONE = auto()


def run_category_tests(
    test_cases: List[Tuple[str, MatchLevel]], strict_regex, soft_regex, loose_regex
):
    print(
        f"{'Text':<40} | {'Exp':<8} | {'Strict':<6} | {'Soft':<6} | {'Loose':<6} | {'Pass':<4}"
    )
    print("-" * 85)
    all_passed = True
    for text, expected in test_cases:
        s = bool(strict_regex.search(text))
        so = bool(soft_regex.search(text))
        l = bool(loose_regex.search(text))

        if s:
            actual = MatchLevel.STRICT
        elif so:
            actual = MatchLevel.SOFT
        elif l:
            actual = MatchLevel.LOOSE
        else:
            actual = MatchLevel.NONE

        passed = actual == expected
        if not passed:
            all_passed = False
        print(
            f"{text:<40} | {expected.name:<8} | {str(s):<6} | {str(so):<6} | {str(l):<6} | {str(passed):<4}"
        )

    if not all_passed:
        print("\nSOME TESTS FAILED")
    else:
        print("\nALL TESTS PASSED")


def run_category_tests_counter(
    test_cases: List[Tuple[str, MatchLevel]], strict_regex, soft_regex, loose_regex
):
    print(
        f"{'Text (Counter)':<40} | {'Avoid':<8} | {'Strict':<6} | {'Soft':<6} | {'Loose':<6} | {'Pass':<4}"
    )
    print("-" * 85)
    all_passed = True
    for text, avoid_level in test_cases:
        s = bool(strict_regex.search(text))
        so = bool(soft_regex.search(text))
        l = bool(loose_regex.search(text))

        passed = True
        if avoid_level == MatchLevel.STRICT and s:
            passed = False
        elif avoid_level == MatchLevel.SOFT and so:
            passed = False
        elif avoid_level == MatchLevel.LOOSE and l:
            passed = False

        if not passed:
            all_passed = False
        print(
            f"{text:<40} | {avoid_level.name:<8} | {str(s):<6} | {str(so):<6} | {str(l):<6} | {str(passed):<4}"
        )

    if not all_passed:
        print("\nSOME COUNTER TESTS FAILED")
    else:
        print("\nALL COUNTER TESTS PASSED")
