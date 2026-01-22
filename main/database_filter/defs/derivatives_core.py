import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, List, Optional, Tuple
from defs.regex_lib import build_alternation, build_compound, build_regex, add_restrictions, plural, to_build_alternation


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
    
    
    
    # Other bases that are not used standalone
    PUT = r"puts?"
    CALL = r"calls?"
    HEDGE = r"hedg(?:es?|ing)"
    WARRANT = r"warrants?"
    
    # IR bases
    PROTECTION = r"protections?"
    
    # CP bases
    FORWARD_PURCHASE = r"forward\s+purchase"
    STRADDLE = r"straddles?"
    STRANGLE = r"strangles?"


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
class SPEC_BASE(Enum):
    # Modifiers
    SPECIAL_SWAP = build_compound([
        r"basis",
        r"variance",
        r"volatility",
        r"total[- ]return",
        r"back[- ]to[- ]back",
    ], BASE.SWAP)
    SPECIAL_OPTION = build_compound([
        r"asian",
        r"bermuda",
        r"basket",
        r"rainbow",
        r"lookback",
        r"exotic",
        r"barrier",
        BASE.PUT,
        BASE.CALL,
    ], BASE.OPTION)

class Groups:
    UNAMBIGUOUS_BASES = [
        BASE.SWAP,
        BASE.FORWARD,
        BASE.COLLAR,
        BASE.DERIVATIVE,
        BASE.FUTURES,
        BASE.SWAPTION,
        SPEC_BASE.SPECIAL_SWAP,
        SPEC_BASE.SPECIAL_OPTION,    
    ]
    AMBIGUOUS_BASES = [BASE.OPTION, BASE.LOCK, BASE.CAP, BASE.FLOOR]
    # Bases that may not be used in a soft match
    OTHER_BASES = [BASE.PUT, BASE.CALL, BASE.HEDGE]
    MISC_BASES = [BASE.PROTECTION, BASE.FORWARD_PURCHASE, BASE.STRADDLE, BASE.STRANGLE, BASE.WARRANT]

    # Suffix Sets
    UNAMBIGUOUS_SUFFIXES = [SUFFIX.CONTRACT, SUFFIX.INSTRUMENT]
    AMBIGUOUS_SUFFIXES = [SUFFIX.AGREEMENT, SUFFIX.ARRANGEMENT]
    MISC_SUFFIXES = [SUFFIX.COMMITMENT, SUFFIX.TRANSACTION, SUFFIX.POSITION]


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

@dataclass
class DERIVATIVES:
    # Default groups
    
    # What placeholder to use
    PREFIX: List[Any] = field(default_factory=list)
    
    # Can add additional to this list (adds to _BASES)
    STANDALONE_BASES: List[Any] = field(default_factory=list)
    # Default fixed group (adds to the suffixes attribute)
    _BASES: List[Any] = field(default_factory=lambda: Groups.UNAMBIGUOUS_BASES)
    
    # Fixed, for all categories (no suffix attachment)
    MULTI_BASE: List[Any] = field(default_factory=lambda: [MULTI_BASE.DOUBLE_BASE, MULTI_BASE.TRIPLE_BASE])
    
    # Can add additional to this list, or force the list to be empty or override it
    AMBIGUOUS_BASES: List[Any] = field(default_factory=lambda: Groups.AMBIGUOUS_BASES)
    
    # Standalone suffixes will not be a prefix for a base
    STANDALONE_SUFFIXES: List[Any] = field(default_factory=list)
    
    # Adds suffixes (not standalone) to the pool to add to a base
    ADDITIONAL_SUFFIXES: List[Any] = field(default_factory=list)
    SUFFIXES: List[Any] = field(default_factory=lambda: Groups.UNAMBIGUOUS_SUFFIXES + Groups.AMBIGUOUS_SUFFIXES)


@dataclass
class DerivativeGenerator:
    """
    Generates regex patterns for derivative instruments based on configurable pools.
    Allows creating Strict, Soft, and Loose patterns dynamically.
    Allows adding specific prefixes and suffixes.
    Does not generate the full regex.
    # So multiple instances are needed for specific phrases
    # For example, setting multi_base to [] for certain phrases to avoid redundant computation
    """
    config: DERIVATIVES

    def generate(
        self
    ):
        # 1. Determine Effective Lists
        # Start with defaults or overrides

        # Build the strict base set
        eff_strict = self.config._BASES + self.config.STANDALONE_BASES 
        # Allow ambigous to use the list from strict
        eff_ambig = self.config.AMBIGUOUS_BASES + eff_strict
        # Premake the suffix list (to attach to bases)
        eff_suff = (
            self.config.SUFFIXES
            + self.config.ADDITIONAL_SUFFIXES
            + self.config.STANDALONE_SUFFIXES
        )
        # Strict pattern that requires no additional attachments (includes strict bases/suffixes/multibase)
        eff_strict += self.config.STANDALONE_SUFFIXES

        # 2. Build regex parts

        # Prepare combo base + suffix
        ambig_str = to_build_alternation(eff_ambig, sort_longest_first=True)
        suffix_str = to_build_alternation(eff_suff, sort_longest_first=True)

        # 3. All the three patterns
        combo_str = rf"{ambig_str}[- ]{suffix_str}"
        multi_str = to_build_alternation(
            self.config.MULTI_BASE, sort_longest_first=True
        )
        standalone_str = to_build_alternation(eff_strict, sort_longest_first=True)

        full_suffix_pattern = to_build_alternation([combo_str, multi_str, standalone_str], sort_longest_first=True)
        prefix_pattern = to_build_alternation(self.config.PREFIX, sort_longest_first=True)
        
        # Create the final pattern
        full_pattern = rf"{prefix_pattern}[- ]{full_suffix_pattern}"
        
        return full_pattern

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
safe_base_alternation = build_alternation(UNAMBIGUOUS_BASE_ENDING, True)
suffix_alternation = build_alternation(SUFFIXES, True)
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
    all_bases = [b.value for b in (Groups.UNAMBIGUOUS_BASES + Groups.AMBIGUOUS_BASES + Groups.OTHER_BASES + [BASE.WARRANT])]
    all_suffixes = [s.value for s in (Groups.UNAMBIGUOUS_SUFFIXES + Groups.AMBIGUOUS_SUFFIXES + Groups.MISC_SUFFIXES)]
    
    return build_regex(all_bases + all_suffixes)


def build_loose_gen_regex_precise() -> re.Pattern:
    # Matches unambiguous bases + specific plurals of ambiguous ones
    # Used for stricter context checks
    unambiguous = [b.value for b in Groups.UNAMBIGUOUS_BASES]
    plurals = [
        *[plural(b.value) for b in Groups.AMBIGUOUS_BASES + Groups.OTHER_BASES],
        *[plural(s.value) for s in Groups.UNAMBIGUOUS_SUFFIXES],
        plural(BASE.WARRANT)
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
