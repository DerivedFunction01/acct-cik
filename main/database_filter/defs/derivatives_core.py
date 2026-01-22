import re
from enum import Enum, auto
from typing import List, Optional, Tuple
from defs.regex_lib import build_alternation, build_regex

def register_base(
    base: str,
    lookaheads: Optional[List[str]] = None,
    lookbehinds: Optional[List[str]] = None,
) -> str:
    pattern = base
    if lookbehinds:
        for lb in lookbehinds:
            pattern = f"(?<!{lb}){pattern}"
    if lookaheads:
        la_pattern = build_alternation(lookaheads)
        pattern = f"{pattern}(?!{la_pattern})"
    return pattern

VERB_LOOKBEHIND = [r"to\s"]
VERB_LOOKAHEAD = [r"\s+(?:the|an|a)"]

PHYSICAL_COMMERCIAL_TERMS = [  # words against "oil forward shipment, or deliverable forward receipt" from being matched
    r"\sdeliver(?:y|ies)",
    r"\sorders?",
    r"\ssales?",
    r"\ssuppl(?:y|ies)",
    r"\sconfirmation",
    r"\sinvoices?",
    r"\sshipments?",
    r"\sreceipts?",
    r"\sinventor(?:y|ies)",
]

STANDALONE_BASES = [
    register_base(
        "swaps?",
        lookaheads=[r"[- ]rates?", r"\s+participants?", r"dealers?"] + VERB_LOOKAHEAD,
        lookbehinds=VERB_LOOKBEHIND
        + [
            r"sim\s",
            r"engine\s",
            r"face\s",
            r"asset\s",
            r"debt[- ]for[- ]equity\s",
            r"debt[- ]for[- ]debt\s",
            r"like[- ]kind\s",
        ],
    ),
    register_base(
        "forwards?",
        lookaheads=[
            r"[- ]rates?",
            r"\s+participants?",
            r"dealers?",
            r"\s+looking?",
            r"\s+stocks?",
            r"[- ]split", r"\s+earnings", r"\s+guidance", r"\s+multiple", r"\s+P/E", r"\s+auction"
        ] 
        + VERB_LOOKAHEAD
        + PHYSICAL_COMMERCIAL_TERMS,
        lookbehinds=[
            r"carry\s",
            r"carrying\s",
            r"carried\s",
            r"look\s",
            r"looking\s",
            r"looked\s",
            r"straight\s",
            r"fast\s",
            r"brought\s",
            r"step\s",
            r"go\s",
            r"move\s",
            r"put\s",
            r"push\s",
            r"set\s",
        ],
    ),
    register_base(
        "collars?",
        lookaheads=[r"[- ]rates?"] + VERB_LOOKAHEAD,
        lookbehinds=VERB_LOOKBEHIND
        + [r"blue\s", r"white\s", r"dog\s", r"shirt\s", r"cervical\s", r"white\s"],
    ),
    register_base(
        "derivatives",
        lookaheads=VERB_LOOKAHEAD + [r"\s+markets?"],
        lookbehinds=VERB_LOOKBEHIND
        + [r"its\s", r"their\s", r"plasma\s", r"chemical\s", r"cellulose\s"],
    ),
    r"(?:perpetual\s+)?futures",
    "swaptions?",
]
OPTION = register_base(
    "options?",
    lookbehinds=[
        r"an\s",
        r"the\s",
        r"equity[- ]",
        r"stock[- ]",
        r"share[- ]",
        r"treasury[- ]",
        r"restricted[- ]",
        r"strategic\s",
        r"financing\s",
        r"payment\s",
        r"renewal\s",
        r"lease\s",
        r"purchase\s",
        r"extension\s",
        r"termination\s",
        r"expansion\s",
        r"default\s",
    ],
)
AMBIGUOUS_BASE_TYPES = [
    OPTION,
    register_base(
        "locks?",
        lookaheads=[r"\s+interest", r"[- ]rates?", r"[- ]up", r"[- ]box", r"[- ]in"]
        + VERB_LOOKAHEAD,
        lookbehinds=VERB_LOOKBEHIND
        + [r"door\s", r"grid\s", r"canal\s", r"zip\s", r"inter\s"],
    ),
    register_base(
        "caps?",
        lookaheads=[r"\s+interest", r"[- ]rates?", r"[- ]ex", r"\s+table", r"\s+space"]
        + VERB_LOOKAHEAD,
        lookbehinds=VERB_LOOKBEHIND
        + [
            r"market\s",
            r"equity\s",
            r"small\s",
            r"large\s",
            r"mid\s",
            r"micro\s",
            r"nano\s",
            r"salary\s",
            r"bottle\s",
        ],
    ),
    register_base(
        "derivatives?",
        lookaheads=VERB_LOOKAHEAD + [r"\s+counterpart(?:y|ies)", r"\s+markets?"],
        lookbehinds=VERB_LOOKBEHIND + [r"its\s", r"their\s"],  # its derivatives, etc
    ),
    register_base(
        "floors?",
        lookaheads=[r"\s+interest", r"[- ]rates?", r"\s+area", r"\s+space", r"\s+plan"]
        + VERB_LOOKAHEAD,
        lookbehinds=VERB_LOOKBEHIND
        + [
            r"trading\s",
            r"factory\s",
            r"ground\s",
            r"ocean\s",
            r"sea\s",
            r"shop\s",
            r"dance\s",
            r"construction\s",
        ],
    ),
]
OTHER_BASES = [
    register_base("puts?", lookaheads=VERB_LOOKAHEAD, lookbehinds=VERB_LOOKBEHIND),
    register_base("calls?", lookaheads=VERB_LOOKAHEAD, lookbehinds=VERB_LOOKBEHIND),
    register_base("hedges?", lookaheads=VERB_LOOKAHEAD + [r"\s+for", r"\s+with", r"\s+by", r"\s+(?:of\s+hedge\s+)?funds?", r"\s+banks?"], lookbehinds=VERB_LOOKBEHIND),
]
spec_base_alternation = build_alternation(
    STANDALONE_BASES + AMBIGUOUS_BASE_TYPES + OTHER_BASES
)
SPECIAL_BASE = [
    f"{spec_base_alternation}[- ](?:options?|contracts?)",
    r"forward\s+agreements?",
    "(?:basis|variance|volatility|total[- ]return) swaps?",
    "(?:asian|bermuda|basket|rainbow|lookback|exotic|barrier) options?",
] + STANDALONE_BASES

UNAMBIGUOUS_SUFFIXES = [
    register_base("contracts?", lookbehinds=VERB_LOOKBEHIND),
    "instruments?",
]
WARRANT = register_base(
    "warrants?",
    lookaheads=[r" (?:the|a|an)"],
    lookbehinds=[r"to\s", r"equity[- ]", r"stock[- ]", r"share[- ]", r"treasury[- ]", r"restricted[- ]"],
)
AMBIGUOUS_SUFFIXES = [
    "agreements?",
    "arrangements?",
    rf"{OPTION}(?!(?:\s*,?\s*(?:and|or|&)\s+|[\s,]+){WARRANT})",  # prevent prevent an/the option
    WARRANT,  # warrant as a verb (warrant the/an/a) but not "derivative warrants for"
]
HEDGE = register_base("hedges?", lookaheads=VERB_LOOKAHEAD + [r"with", r"by", r"for"], lookbehinds=VERB_LOOKBEHIND)
OTHER_SUFFIXES = [
    "commitments?",
    "transactions?",
    "positions?",
    HEDGE
]

SUFFIXES = UNAMBIGUOUS_SUFFIXES + AMBIGUOUS_SUFFIXES
ALL_SUFFIXES = UNAMBIGUOUS_SUFFIXES + AMBIGUOUS_SUFFIXES + OTHER_SUFFIXES
suffix_alternation = build_alternation(SUFFIXES, True)
all_suffix_alternation = build_alternation(ALL_SUFFIXES, True)

SPECIAL_BASE += [rf"hedg(?:e|ing)\s+(?:{suffix_alternation}|derivatives?)"]

def build_double_base_alternation() -> str:
    """
    Matches combinations of ambiguous bases which together strongly imply derivatives.
    e.g. "caps and floors", "options and futures"
    Also matches: "contracts such as swaps, collars"
    """
    base_terms = AMBIGUOUS_BASE_TYPES + OTHER_BASES + SPECIAL_BASE + ["warrants?"]
    bases = build_alternation(base_terms, sort_longest_first=True)

    prefix_terms = (
        STANDALONE_BASES
        + SUFFIXES
        + [HEDGE]
    )
    # Start terms can be either a prefix (contract) or a base (swap)
    start_terms = list(set(prefix_terms + base_terms))
    start_alt = build_alternation(start_terms, sort_longest_first=True)

    sep = r"(?:\s*,?\s*(?:and|or|&)\s+|[\s,]+)"
    # Gap allows 0-2 words between the first and second term
    # e.g. "swaps, options" (0 words), "contracts such as options" (2 words) but not option to swap, etc
    gap = r"(?:\W+(?:\w+\W+){0,2}?)"

    # Forbidden fillers to prevent false positives like "agreement sets the cap"
    # 1. Lookbehind: Gap must not end with articles or relative pronouns
    forbidden_endings = r"(?<!\s(?:the|an|a|that|which|who))"
    # 2. Lookahead: Next term must not start with prepositions (unless consumed by gap)
    forbidden_starters = r"(?!\s+(?:to|in|on|for|of|with|by|as|at))"

    return rf"(?:{start_alt})(?!\s+to){gap}{forbidden_endings}{forbidden_starters}(?:{bases})(?:{sep}(?:{bases}))*"


double_base_alternation = build_double_base_alternation()

UNAMBIGUOUS_BASE_TYPES = (
    SPECIAL_BASE
    + [double_base_alternation]
)
UNAMBIGUOUS_BASE_ENDING = UNAMBIGUOUS_BASE_TYPES + ["derivatives?"]
BASE_TYPES = UNAMBIGUOUS_BASE_ENDING + AMBIGUOUS_BASE_TYPES
ALL_BASE_TYPES = BASE_TYPES + OTHER_BASES

DOUBLE_BASE_REGEX = re.compile(rf"\b{double_base_alternation}\b", re.IGNORECASE)
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
    plurals = [
        "warrants",
    ]
    return build_regex(BASE_TYPES + plurals + SUFFIXES)


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
    return build_regex(UNAMBIGUOUS_BASE_ENDING + plurals)


LOOSE_GEN_REGEX = build_loose_gen_regex()
PRECISE_LOOSE_GEN_REGEX = build_loose_gen_regex_precise()

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

def run_category_tests_counter(test_cases: List[Tuple[str, MatchLevel]], strict_regex, soft_regex, loose_regex):
    print(f"{'Text (Counter)':<40} | {'Avoid':<8} | {'Strict':<6} | {'Soft':<6} | {'Loose':<6} | {'Pass':<4}")
    print("-" * 85)
    all_passed = True
    for text, avoid_level in test_cases:
        s = bool(strict_regex.search(text))
        so = bool(soft_regex.search(text))
        l = bool(loose_regex.search(text))

        passed = True
        if avoid_level == MatchLevel.STRICT and s: passed = False
        elif avoid_level == MatchLevel.SOFT and so: passed = False
        elif avoid_level == MatchLevel.LOOSE and l: passed = False

        if not passed: all_passed = False
        print(f"{text:<40} | {avoid_level.name:<8} | {str(s):<6} | {str(so):<6} | {str(l):<6} | {str(passed):<4}")

    if not all_passed: print("\nSOME COUNTER TESTS FAILED")
    else: print("\nALL COUNTER TESTS PASSED")
