import re
from enum import Enum, auto
from typing import List, Optional, Tuple
from defs.regex_lib import build_alternation, build_regex

PHYSICAL_COMMERCIAL_TERMS = [  # words against "oil forward shipment, or deliverable forward receipt" from being matched
    "deliver(?:y|ies)",
    "purchases?",
    "orders?",
    "sales?",
    "suppl(?:y|ies)",
    "confirmation",
    "invoices?",
    "shipments?",
    "receipts?",
    "inventor(?:y|ies)",
    "liabilit(:?y|ies)",  # Forward liability
    "stocks?",
    "looking",  # Just added it here against forward-looking
]

PHYSICAL_DELIVERY_PATTERN = build_alternation(
    PHYSICAL_COMMERCIAL_TERMS, sort_longest_first=True
)

PHYSICAL_INVENTORY_TERMS = []  # "capacity forward contract?"

# Negative lookahead: forward NOT followed by physical keywords
FORWARD_NOT_PHYSICAL_AHEAD = rf"(?![- ](?:{PHYSICAL_DELIVERY_PATTERN}))"
SPECIAL_BASE = [
    "(?:call|put|swap) (?:options?|contracts?)",
    "(?:basis|variance|volatility|total[- ]return) swaps?",
    "swaptions?",
    "(?:asian|bermuda|basket|rainbow|lookback|exotic|barrier) options?",
]
UNAMBIGUOUS_BASE_TYPES = [
    "swaps?",
    rf"(?<!carry\s)forwards?{FORWARD_NOT_PHYSICAL_AHEAD}",
    "collars?",
    "derivatives?",
    "futures",  # plural form
] + SPECIAL_BASE

AMBIGUOUS_BASE_TYPES = [
    "futures?",
    "options?",
    "hedging",
    "locks?",
    "caps?",
    "floors?",
    "hedges?",
    "puts?",
    "calls?",
    "straddles?",
    "strangles?",
]


ALL_BASE_TYPES = UNAMBIGUOUS_BASE_TYPES + AMBIGUOUS_BASE_TYPES
UNAMBIGUOUS_SUFFIXES = [
    "contracts?",
    "instruments?",
]

AMBIGUOUS_SUFFIXES = [
    "agreements?",
    "commitments?",
    "arrangements?",
]
ALL_SUFFIXES = UNAMBIGUOUS_SUFFIXES + AMBIGUOUS_SUFFIXES

PRECISE_BASE_REGEX = build_regex(UNAMBIGUOUS_BASE_TYPES)

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
        "futures",
        rf"(?<!carry\s)forwards",
        "hedges",
        "collars",
        "swaptions",
        "derivatives",
        "swaps",
        "puts",
        "calls",
    ] + SPECIAL_BASE

    plural_pattern = build_alternation(table_safe_plurals, sort_longest_first=True)

    return re.compile(rf"\b{plural_pattern}\b", re.IGNORECASE)


TABLE_REGEX = build_table_regex()


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
base_alternation = build_alternation(ALL_BASE_TYPES, True)
BASE_REGEX = build_regex(ALL_BASE_TYPES)
safe_base_alternation = build_alternation(UNAMBIGUOUS_BASE_TYPES, True)
suffix_alternation = build_alternation(ALL_SUFFIXES, True)
standalone_alternation = build_alternation(UNAMBIGUOUS_SUFFIXES + UNAMBIGUOUS_BASE_TYPES, True)
unsafe_standalone_alternation = build_alternation(ALL_SUFFIXES + ALL_BASE_TYPES, True)

# ----------------------------------------------------------------------------------


def expand_instruments(
    unsafe: bool = True,
    exclude_standalone_suffixes: Optional[bool] = None,
    additional_standalone_suffixes: Optional[List[str]] = None,
    additional_bases: Optional[List[str]] = None,
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
        exclude_standalone_suffixes = unsafe

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
        base_standalone = base_alternation if unsafe else safe_base_alternation

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

    # 5. Final Assembly (Max Munch: Combined first)
    return rf"{combined_pattern}|{final_standalone}"


class MatchLevel(Enum):
    STRICT = auto()
    SOFT = auto()
    LOOSE = auto()
    NONE = auto()


def run_category_tests(test_cases: List[Tuple[str, MatchLevel]], strict_regex, soft_regex, loose_regex):
    print(f"{'Text':<40} | {'Exp':<8} | {'Strict':<6} | {'Soft':<6} | {'Loose':<6} | {'Pass':<4}")
    print("-" * 85)
    all_passed = True
    for text, expected in test_cases:
        s = bool(strict_regex.search(text))
        so = bool(soft_regex.search(text))
        l = bool(loose_regex.search(text))

        if s: actual = MatchLevel.STRICT
        elif so: actual = MatchLevel.SOFT
        elif l: actual = MatchLevel.LOOSE
        else: actual = MatchLevel.NONE

        passed = (actual == expected)
        if not passed: all_passed = False
        print(f"{text:<40} | {expected.name:<8} | {str(s):<6} | {str(so):<6} | {str(l):<6} | {str(passed):<4}")

    if not all_passed: print("\nSOME TESTS FAILED")
    else: print("\nALL TESTS PASSED")
