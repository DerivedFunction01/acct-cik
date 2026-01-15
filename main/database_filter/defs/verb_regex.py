# =============================================================================
# VERB MAPS & PRECOMPILED REGEXES
# =============================================================================
import re
from defs.gen_regex import LOOSE_GEN_REGEX
from defs.derivative_lib import CATEGORY_REGEX
from defs.regex_lib import build_alternation, build_regex

# Speculative / Uncertain Timing Phrases
SPECULATIVE_PHRASES = [
    r"from\s+time\s+to\s+time",
    r"periodically",
    r"in\s+future\s+periods",
    r"upon\s+occurrence",
    r"when\s+(?:deemed\s+)?necessary",
    r"when\s+(?:chosen|choosed)",
]

# Potential / Hypothetical Modals & Phrases
POTENTIAL_INDICATORS = [
    r"may",
    r"occasionally",
    r"might",
    r"(?:may|might)\s+consider",
    r"could",
    r"would",
    r"will",
    r"seek\s+to",
    r"intend\s+to",
    r"plan(?:s|ned)?\s+to",
    r"if",
    r"whether",
    # FIX: Negative lookahead allows "expect to continue" (Active) while flagging "expect to use" (Potential)
    r"expect(?:s|ed)?\s+to(?![- ]continue)",
]

# Add this alongside your other lists
NEGATIVE_CONTRACTIONS = [
    # Active
    r"do[nN]['’]?[tT]",
    r"does[nN]['’]?[tT]",
    r"did[nN]['’]?[tT]",
    r"wo[nN]['’]?[tT]",
    r"would[nN]['’]?[tT]",
    r"ca[nN]['’]?[tT]",
    r"cannot",
    r"could[nN]['’]?[tT]",
    r"should[nN]['’]?[tT]",
    r"sha[nN]['’]?[tT]",
    r"have[nN]['’]?[tT]",
    r"has[nN]['’]?[tT]",
    r"had[nN]['’]?[tT]",
    # Passive
    r"are[nN]['’]?[tT]",
    r"is[nN]['’]?[tT]",
    r"was[nN]['’]?[tT]",
    r"were[nN]['’]?[tT]",
]

NEGATIVE_AUXILIARY = [
    # Active
    r"do",
    r"does",
    r"did",
    r"will",
    r"would",
    r"can",
    r"could",
    r"shall",
    r"should",
    r"have",
    r"has",
    "had",  # Added 'had'
    r"must",
    # Passive (Crucial for "Derivatives were not held")
    r"are",
    r"is",
    r"were",
    r"was",
    r"be",
]
_ABSENCE_NOUNS = [
    r"outstanding",  # "no such outstanding"
    r"positions?",
    r"exposures?",
    r"obligations?",
    r"hedges?",  # "no such hedge" (generic)
    r"activit(?:ies|y)",  # "no derivative activity"
    r"involvements?",  # "no involvement with derivatives"
    r"holdings?",  # "no holdings"
]


def build_negation_prefix_pattern() -> str:
    """
    Returns a regex string matching:
    1. Standard Negation: "did not", "was not", "will not"
    2. Contractions: "didn't", "wasn't"
    3. Absolute Negation: "never"
    """
    # 1. Standard: Auxiliary + Not
    aux_full = build_alternation(NEGATIVE_AUXILIARY)
    pattern_full = rf"\b{aux_full}\s+not\b"

    # 2. Contractions
    pattern_contract = rf"\b{build_alternation(NEGATIVE_CONTRACTIONS)}\b"

    # 3. Absolute (The new addition)
    abs_neg = ["never", "neither"]
    pattern_absolute = rf"\b{build_alternation(abs_neg)}\b"

    # Combine: (did not | didn't | never)
    return rf"(?:{pattern_full}|{pattern_contract}|{pattern_absolute})"


VERB_MAP = {
    "POSS": [
        r"hold(?:s|ing)?|held",
        r"hav(?:e|ing)|had",
        r"maintain(?:s|ed|ing)?",
        r"possess(?:e|es|ed|ing)?",
        r"carr(?:y|ies|ied|ying)",
        r"retain(?:s|ed|ing)?",
        r"remained?\s+(?:open|outstanding|active)",
        r"(?:a\s+)?party\s+to",
    ],
    "PRU": [
        r"use(?:s|d|ing)?",
        r"utiliz(?:e|es|ed|ing)",
        r"employ(?:s|ed|ing)?",
        r"apply(?:ies|ied|ying)?",
        r"participat(?:es?|ed|ing)",
    ],
    "ACT": [
        r"enter(?:s|ed|ing)?(?:\s+into)?",
        r"engag(?:e|es|ed|ing)(?:\s+in)?",
        r"execut(?:e|es|ed|ing)",
        r"transact(?:s|ed|ing)?",
        r"purchas(?:e|es|ed|ing)",
        r"issu(?:e|es|ed|ing)?",
        r"convert(?:s|ed|ing)?",
        r"secur(?:e|es|ed|ing)",
    ],
    "ACCT": [
        r"designat(?:e|es|ed|ing)",
        r"chose(?:\s+to)",
        r"choos(?:e|es|ing)(?:\s+to)",
        r"hedge"
    ],
}

ALL_VERBS = list(
    VERB_MAP["POSS"] + VERB_MAP["PRU"] + VERB_MAP["ACT"] + VERB_MAP["ACCT"]
)

INTENT_VERB_PATTERN = build_alternation(ALL_VERBS)


def build_potential_regex() -> re.Pattern:
    """
    Matches: "may enter", "might use", "expect to hedge"
    Relaxed middle group catches: "may [occasionally] use", "may [typically] enter"
    """
    return re.compile(
        rf"\b{build_alternation(POTENTIAL_INDICATORS)}[, ]"
        r"(?:\w+\s+){0,3}"
        rf"(?:, )?({INTENT_VERB_PATTERN})\b",
        re.IGNORECASE,
    )


def build_vague_timing_regex() -> re.Pattern:
    """Matches: "from time to time", "in future periods" """
    return re.compile(rf"\b{build_alternation(SPECULATIVE_PHRASES)}\b", re.IGNORECASE)


# The "Meat": Keywords that define what is being denied
_DENIAL_MODIFIERS = [
    "exchange",
    "rate",
    "currency",
    "interest",
    "foreign",
    "commodity",
    "equity",
    "credit",
    "market",
    "forward",
    "future",
    "option",
    "swap",
    "purchase",
    "sale",
    "cash",
    "fair",
    "value",
    "material",
    "significant",
    "hedging",
    "derivative",
    "financial",
    "trading",
    "proprietary",
    "speculative",
    "purchase",
]

# The "Glue": Small filler words that appear between modifiers
_DENIAL_FILLER = r"(?:\S+\s+){0,3}"

# The "Chain": A single unit of [Filler] + [Modifier]
# Supports lists like "interest rate, foreign exchange, or commodity..."
_DENIAL_SEMANTIC_MOD = (
    rf"(?:{build_alternation(_DENIAL_MODIFIERS)}|{LOOSE_GEN_REGEX.pattern})"
)
_DENIAL_GAP_UNIT = rf"(?:{_DENIAL_FILLER}{_DENIAL_SEMANTIC_MOD})"
gap_chain = rf"(?:{_DENIAL_GAP_UNIT}\s+){{0,5}}"
# The "Target": The final noun in the sequence
_DENIAL_TARGET = rf"(?:{CATEGORY_REGEX.pattern}|{LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"
# Active / Timing Indicators (New)
ACTIVE_INDICATORS = [
    "currently",
    "presently",
    "at present",
]
ACTIVE_PATTERN = build_alternation(ACTIVE_INDICATORS)
def build_did_not_hold_regex() -> re.Pattern:
    """
    Matches: "did not hold", "didn't enter", "do not, as a routine matter, use"
    Targeting: Active non-use of derivatives.
    """
    # 2. Pattern Construction

    neg_prefix = (
        build_negation_prefix_pattern()
    )  # Matches "do not", "did not", "no", etc.

    # The Fix: Allow an intervening comma-phrase or adverb between "Not" and "Verb"
    # Matches: "do not currently use" OR "do not, as a routine matter, use"
    # Logic: Optional (ActiveAdverb + Space) OR (Comma + AnyText + Comma + Space)
    _pre_verb_gap = (
        r"[, ]"  # Mandatory space or comma after "not"
        r"(?:"
        rf"{ACTIVE_PATTERN}\s+|"  # "currently "
        r"\s*[^,]{1,50}\s*,\s+"  # ", as a routine matter, " (Greedy but bounded)
        r")?"
    )

    return re.compile(
        rf"{neg_prefix}"  # "do not"
        rf"{_pre_verb_gap}"  # <--- ", in any case, "
        rf"(?:to\s+)?(?:{INTENT_VERB_PATTERN})\s+"  # "use"
        rf"{gap_chain}"  # Optional: "hedging", "foreign exchange"
        rf"{_DENIAL_FILLER}"  # Optional: "any such"
        rf"{_DENIAL_TARGET}\b",  # "instruments"
        re.IGNORECASE,
    )


def build_absence_regex() -> re.Pattern:
    """
    Matches "No [Modifier] [Modifier] ... [Instrument]" patterns.

    Structure:
    1. Trigger ("No")
    2. Optional Gap Chain (0-5x):
       - Small Filler (0-3 words like "such", "material", "or")
       - Semantic Modifier (Placeholder like "interest" or Loose Regex)
    3. Final Filler (0-3 words)
    4. Target Instrument ("swaps")

    Example Match: "No [such interest] (rate), [forward] (exchange), [or commodity] (contracts)"
    """
    ABSENCE_INDICATORS = [r"no", r"none"]
    # 1. Triggers
    triggers = build_alternation(ABSENCE_INDICATORS)

    return re.compile(
        rf"\b{triggers}\b\s+"
        rf"{gap_chain}"
        rf"{_DENIAL_FILLER}"
        rf"{_DENIAL_TARGET}\b",
        re.IGNORECASE,
    )


# Termination Verbs
# If these appear before "settled", it's likely a description of mechanics, not termination.
SETTLEMENT_MODIFIERS = [
    "cash",
    "net",
    "daily",
    "monthly",
    "physically",
    "final",
    "mandatory",
    "annually",
    "weekly",
]
_settle_lookbehind = "".join([rf"(?<!\b{word}\s)" for word in SETTLEMENT_MODIFIERS])
# In termination_filter.py

TERMINATION_VERBS = [
    # --- SAFE VERBS (Past/Present/Participle) ---
    # Regex note: We removed |ion, |ity, |ment, |y suffixes
    r"expir(?:e(?:d|s)?|ing)",  # Matches: expire, expired, expiring.  STOPS: expiration, expiry
    r"matur(?:e(?:d|s)?|ing)",  # Matches: mature, matured, maturing.  STOPS: maturity
    r"terminat(?:e(?:d|s)?|ing)",  # Matches: terminate, terminated.      STOPS: termination
    r"ceas(?:e(?:d|s)?|ing)",  # Matches: cease, ceased
    r"retir(?:e(?:d|s)?|ing)",  # Matches: retire, retired.
    r"clos(?:e(?:d|s)?|ing)(?!\s+(?:price|rate|date|balance|value))",
    r"liquidat(?:e(?:d|s)?|ing)",  # Matches: liquidate, liquidated.  STOPS: liquidation
    r"unwound",
    r"unwind",
    r"exercis(?:e(?:d|s)?|ing)",  # Matches: exercise, exercised.        STOPS: exercisable
    r"extinguish(?:e(?:d|s)?|ing)",  # Matches: extinguish, extinguished.   STOPS: extinguishment
    r"novat(?:e(?:d|s)?|ing)",  # Matches: novate, novated.            STOPS: novation
    r"cancel(?:l(?:ed|ing)|s)?",  # Matches: cancel, cancelled.          STOPS: cancellation
    r"rescind(?:e(?:d|s)?|ing)",  # Matches: rescind, rescinded.         STOPS: rescission
    r"void(?:ed)?",
    r"withdraw(?:n|s|ing)?",
    r"withdrew",
    r"discontinu(?:e(?:d|s)?|ing)",  # Matches: discontinued.               STOPS: discontinuation
    r"exit(?:ed|s|ing)?",
    r"redeem(?:e(?:d|s)?|ing)",  # Matches: redeem, redeemed.           STOPS: redemption
    r"repudiat(?:e(?:d|s)?|ing)",
    # --- SAFEGUARDED SETTLEMENT (From previous turn) ---
    rf"(?<!{_settle_lookbehind}\s)settl(?:e(?:d)|ing)",
    r"sold",
    r"wind(?:ing)?\s+down",
    r"dispos(?:e(?:d|s)?|ing)",
    r"derecogni[sz](?:e|ed|ing)",
    r"divest(?:ed|s|ing)?",
    r"preterminat(?:e(?:d|s)?|ing)",
    r"accelerat(?:e(?:d|s)?|ing)",
    r"relinquish(?:ed|es|ing)?",
    r"lapse(?:d|s|ing)?",
    r"forfeit(?:ed|s|ing)?",
]
TERMINATION_NOUNS = [
    # --- STATES (Strongest) ---
    r"expir(?:ation|y)",  # Matches: expiration, expiry
    r"maturit(?:y|ies)",  # Matches: maturity, maturities
    r"terminat(?:ion|or)",  # Matches: termination
    r"redemption",  # Matches: redemption
    # --- EVENTS (Transactional) ---
    r"extinguishment",  # Matches: extinguishment
    r"settlement",  # Matches: settlement
    r"cancellation",  # Matches: cancellation
    r"novation",  # Matches: novation
    r"rescission",  # Matches: rescission
    r"discontinu(?:ance|ation)",  # Matches: discontinuance, discontinuation
    r"withdrawal",  # Matches: withdrawal
    r"retirement",  # Matches: retirement
    r"unwinding",  # Matches: unwinding
    r"repudiation",  # Matches: repudiation
    r"cessation",  # Matches: cessation
    r"closure",  # Matches: closure
    r"exit",  # Matches: exit (noun form)
    r"liquidation",
    r"forfeiture",
    r"acceleration",
    r"close[- ]?out",
    r"lapse",
    r"forfeiture",
    r"derecognition",
    r"wind[- ]?down",
    r"sale",
    r"disposition",
    r"transfer",
    r"assignment",
    r"relinquishment",
    r"voiding",
    r"divestiture",
]

ALL_TERM_TERMS = TERMINATION_VERBS + TERMINATION_NOUNS

def build_prior_statement_pattern_2() -> re.Pattern:
    """
    Build regex pattern for DETECTING prior period statements.

    Strategy:
    1. Compositional: Preposition + (Optional 'the') + Adjective + Noun
       matches: "In the prior year", "During previous reporting periods"
    2. Catch-Alls: Standalone adverbs/phrases
       matches: "Historically", "Prior to 2022"
    """

    # --- 1. COMPOSITIONAL COMPONENTS ---
    PREPOSITIONS = [
        r"in",
        r"during",
        r"for",
        r"as\s+of",
        r"at",
        r"from",
        r"throughout",
        r"over",
    ]

    PRIOR_INDICATORS = [
        "past",
        "previous",
        "last",
        "prior",
        "earlier",
        "former",
        "preceding",
        "historical",
        "retroactive",
    ]

    TIME_NOUNS = r"(?:\b\S+\s+)?(?:years?|periods?|quarters?|months?)\b"

    # --- 2. BUILD FRAGMENTS ---
    PREP_ALT = build_alternation(PREPOSITIONS)
    ADJ_ALT = build_alternation(PRIOR_INDICATORS)
    DETERMINER = r"(?:the\s+|our\s+)?"

    # --- 3. PATTERNS ---
    # Pattern A: Compositional
    pat_compositional = (
        r"\b" rf"{PREP_ALT}\s+" rf"{DETERMINER}" rf"{ADJ_ALT}\s+" rf"{TIME_NOUNS}" r"\b"
    )

    # Pattern B: Standalone Catch-Alls
    # FIX 2: Ensure TIME_NOUNS is handled as a clean string here
    CATCH_ALLS = [
        r"historically",
        r"previously",
        r"formerly",
        r"in\s+the\s+past",
        rf"prior\s+to\s+(?:the\s+)?(?:{TIME_NOUNS}|\d{{4}})",  # Corrected f-string braces
        r"years?\s+ago",
        r"same\s+period\s+last\s+year",
    ]
    pat_catchall = rf"\b{build_alternation(CATCH_ALLS)}\b"

    # --- 4. COMBINE ---
    return re.compile(rf"(?:{pat_compositional}|{pat_catchall})", re.IGNORECASE)


# Export
POSS_VERB_REGEX = build_regex(VERB_MAP["POSS"])
USAGE_VERB_REGEX = build_regex(VERB_MAP["PRU"])
TRANS_VERB_REGEX = build_regex(VERB_MAP["ACT"])
ACCT_VERB_REGEX = build_regex(VERB_MAP["ACCT"])
ALL_VERB_REGEX = build_alternation(ALL_VERBS)


DID_NOT_HOLD_REGEX = build_did_not_hold_regex()
ABSENCE_REGEX = build_absence_regex()
POTENTIAL_REGEX = build_potential_regex()
VAGUE_TIMING_REGEX = build_vague_timing_regex()
PRIOR_INDICATOR = build_prior_statement_pattern_2()

TERMINATION_ALL_REGEX = build_regex(ALL_TERM_TERMS)
TERMINATION_REGEX = build_regex(TERMINATION_VERBS)

def run_tests():
    print("Running tests for verb_regex.py...")

    test_cases = [
        # DID_NOT_HOLD_REGEX
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "We did not hold any such derivatives",
            True,
        ),
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "We do not, as a routine matter, use interest rate swaps",
            True,
        ),
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "We possess foreign exchange, interest rate, and commodity contracts",
            False,
        ),
        # ABSENCE_REGEX
        ("ABSENCE", ABSENCE_REGEX, "There were no such interest rate swaps", True),
        ("ABSENCE", ABSENCE_REGEX, "We have no foreign exchange, interest rate, or other contracts", True),
        ("ABSENCE", ABSENCE_REGEX, "We have swaps", False),
        # POTENTIAL_REGEX
        ("POTENTIAL", POTENTIAL_REGEX, "We may continue to enter into interest rate swaps", True),
        ("POTENTIAL", POTENTIAL_REGEX, "We expect to hedge our exposure", True),
        ("POTENTIAL", POTENTIAL_REGEX, "We entered into swaps", False),
        # VAGUE_TIMING
        ("VAGUE_TIMING", VAGUE_TIMING_REGEX, "We use swaps from time to time", True),
        ("VAGUE_TIMING", VAGUE_TIMING_REGEX, "We use swaps periodically", True),
        # PRIOR
        ("PRIOR", PRIOR_INDICATOR, "In the prior year, we had interest rate swaps", True),
        ("PRIOR", PRIOR_INDICATOR, "During previous reporting periods", True),
        ("PRIOR", PRIOR_INDICATOR, "Historically", True),
        # TERMINATION
        ("TERMINATION", TERMINATION_REGEX, "The swaps expired", True),
        ("TERMINATION", TERMINATION_REGEX, "We terminated the agreement", True),
        ("TERMINATION", TERMINATION_REGEX, "The swaps matured", True),
    ]

    failures = 0
    for name, pattern, text, expected in test_cases:
        match = pattern.search(text)
        is_match = bool(match)
        if is_match != expected:
            print(f"FAIL [{name}]: '{text}' -> Expected {expected}, Got {is_match}")
            failures += 1

    if failures == 0:
        print(f"All {len(test_cases)} tests passed.")
    else:
        print(f"{failures} tests failed.")
