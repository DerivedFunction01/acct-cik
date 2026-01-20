# =============================================================================
# VERB MAPS & PRECOMPILED REGEXES
# =============================================================================
import re
from typing import List, Tuple, Optional
from defs.gen_regex import LOOSE_GEN_REGEX
from defs.derivative_lib import STRICT_REGEX
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import ALL_TERM_TERMS, TERMINATION_VERBS, MITIGATION_VERBS
from defs.verb_core import (
    build_negation_prefix_pattern,
    build_strict_do_not_mitigate_regex,
    ACTIVE_PATTERN,
    ACTIVE_INDICATORS
)

# Speculative / Uncertain Timing Phrases
SPECULATIVE_PHRASES = [
    r"from\s+time\s+to\s+time",
    r"periodically",
    r"in\s+future\s+periods",
    r"upon\s+occurrence",
    r"when\s+(?:deemed\s+)?necessary",
    r"when\s+(?:chosen|choosed)",
]

POTENTIAL_SUFFIX_ADVERBS = [
    r"occasionally",
    r"selectively",
    r"typically",
    r"generally",
    r"routinely",
    r"customarily",
    r"regularly",
    r"normally",
    r"often",
    r"frequently",
    r"sometimes",
    r"rarely",
]

# Potential / Hypothetical Modals & Phrases
POTENTIAL_INDICATORS = [
    r"may",
    r"might",
    r"(?:may|might|are|were)\s+(?:consider|plann?)(?:ing)?",
    r"could",
    r"would",
    r"will",
    r"seek\s+to",
    r"intend\s+to",
    r"plan(?:s|ned)?\s+to",
    r"if",
    r"whether",
    r"limited", # limited use
    # FIX: Negative lookahead allows "expect to continue" (Active) while flagging "expect to use" (Potential)
    r"expect(?:s|ed)?\s+to(?![- ]continue)",
] + POTENTIAL_SUFFIX_ADVERBS

_ABSENCE_NOUNS = [
    r"positions?",
    r"obligations?",
    r"activit(?:ies|y)",  # "no derivative activity"
    r"involvements?",  # "no involvement with derivatives"
    r"holdings?",  # "no holdings"
]

VERB_MAP = {
    "POSS": [
        r"hold(?:s|ing)?|held",
        r"(?:hav(?:e|ing)|had)(?![- ]designat(?:e|es|ed|ing))",
        r"maintain(?:s|ed|ing)?",
        r"possess(?:e|es|ed|ing)?",
        r"carr(?:y|ies|ied|ying)",
        r"(?:remained|is|are|was|were)?\s+(?:open|outstanding|active)",
        r"(?:a\s+)?party\s+to",
    ],
    "PRU": [
        r"us(?:e(?:s|d)?|ing)",
        r"utiliz(?:e|es|ed|ing)",
        r"employ(?:s|ed|ing)?",
        r"appl(?:ies|ied|ying|y)",
        r"participat(?:es?|ed|ing)",
        r"designat(?:e|es|ed|ing)(?![- ]as)",
        r"hedg(?:e|es|ed|ing)\s+(?:with|using|by)",
        r"trad(?:e|es|ed|ing)",
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
        r"retain(?:s|ed|ing)?",
    ],
}

ALL_VERBS = list(
    VERB_MAP["POSS"] + VERB_MAP["PRU"] + VERB_MAP["ACT"] + VERB_MAP["ACCT"]
)

INTENT_VERB_PATTERN = build_alternation(ALL_VERBS)
VERB_REGEX = build_regex(VERB_MAP["POSS"] + VERB_MAP["PRU"] + VERB_MAP["ACT"])

def build_potential_regex() -> re.Pattern:
    """
    Matches: "may enter", "might use", "expect to hedge"
    Relaxed middle group catches: "may [occasionally] use", "may [typically] enter"
    Also matches suffix adverbs: "use ... rarely", "enter ... occasionally"
    """
    prefix = (
        rf"\b{build_alternation(POTENTIAL_INDICATORS)}[, ]"
        r"(?:\w+\s+){0,4}"
        rf"(?:, )?({INTENT_VERB_PATTERN})\b"
    )
    
    suffix = (
        rf"\b({INTENT_VERB_PATTERN})\s+"
        r"(?:\w+\s+){0,8}"
        rf"{build_alternation(POTENTIAL_SUFFIX_ADVERBS)}\b"
    )

    return re.compile(
        rf"(?:{prefix}|{suffix})",
        re.IGNORECASE,
    )

def build_active_verb_regex() -> re.Pattern:
    """
    Matches active usage: "use ... derivatives", "hold ... swaps"
    Structure: Verb + [Gap] + Instrument
    """
    return re.compile(
        rf"\b(?:{INTENT_VERB_PATTERN})\s+"
        rf"{gap_chain}"
        rf"{_DENIAL_FILLER}"
        rf"{_DENIAL_TARGET}\b",
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
    "contracted",
    "volume",
    "price",
    "speculative",
    "thousands?",
    "millions?",
    "billions?",
    "trillions?",
    "forward[- ]starting",
    "months?",
    "years?",
    "net",
    "aggregated?",
    "total",
    "notional",
    "amounts?",
    "new",
    "open",
    "active",
    "outstanding",
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
_DENIAL_TARGET = rf"(?:{STRICT_REGEX.pattern}|{LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"

def build_potential_mitigation_regex() -> re.Pattern:
    """
    Matches mitigation pattern: "occasionally mitigates ... by using ... [derivative]"
    """
    return re.compile(
        rf"\b{build_alternation(POTENTIAL_INDICATORS)}[, ]"
        r"(?:\w+\s+){0,2}"
        rf"{build_alternation(MITIGATION_VERBS)}\s+"
        r"(?:\w+\s+){0,15}"
        r"by\s+"
        rf"(?:{INTENT_VERB_PATTERN})\s+"
        rf"{_DENIAL_FILLER}"
        rf"{_DENIAL_TARGET}\b",
        re.IGNORECASE,
    )


def build_immaterial_regexes() -> List[re.Pattern]:
    immaterial = [
        "immaterial",
        "not significant",
        "limited",
        "not material",
        "negligible",
        "minimal",
        "insignificant",
        "not substantial",
        "minor",
        "trivial",
        "nominal",
        "zero",
        "inconsequential",
        "de minimis",
    ]
    
    imm_pat = build_alternation(immaterial)

    subjects = [
        r"(?:the|these)\s+(?:amounts?|values?)", # Tighten what value/amount
        r"(?:fair|carrying|market|notional)\s+values?",
        r"notional\s+(?:amounts?|values?)",
    ]
    subj_pat = build_alternation(subjects)
    
    verbs = r"(?:were|was|are|is|considered|deemed|remained)"

    # 1. Short / Strict (No instrument required)
    # "The notional amount was immaterial"
    # Gap: Subject -> [0-2 words] -> Verb -> [0-2 words] -> Immaterial
    pat_strict = rf"\b(?:{subj_pat})\s+(?:\w+\s+){{0,2}}{verbs}\s+(?:\w+\s+){{0,2}}{imm_pat}\b"
    regex_strict = re.compile(pat_strict, re.IGNORECASE)

    # 2. Instrument-Anchored (Permissive)
    # "The fair value of the interest rate swaps was immaterial"
    # Structure: Subject + (of/from/related to) + Instrument + ... + Immaterial
    pat_instrument = (
        rf"\b(?:{subj_pat})\s+(?:of|from|related\s+to)\s+"
        rf"{_DENIAL_TARGET}\s+"
        rf"(?:\w+\s+){{0,5}}{imm_pat}\b"
    )
    regex_pat_instrument = re.compile(pat_instrument, re.IGNORECASE)

    # 3. Instrument as Subject (Strict)
    # "The interest rate swap was immaterial"
    pat_instrument_subject = (
        rf"\b{_DENIAL_TARGET}\s+(?:\w+\s+){{0,2}}{verbs}\s+(?:\w+\s+){{0,2}}{imm_pat}\b"
    )
    regex_pat_instrument_subject = re.compile(pat_instrument_subject, re.IGNORECASE)

    return [regex_strict, regex_pat_instrument, regex_pat_instrument_subject]


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
    ABSENCE_INDICATORS = [r"no", r"none", r"neither", r"nor"]
    # 1. Triggers
    triggers = build_alternation(ABSENCE_INDICATORS)

    return re.compile(
        rf"\b{triggers}\b\s+"
        rf"{gap_chain}"
        rf"{_DENIAL_FILLER}"
        rf"{_DENIAL_TARGET}\b",
        re.IGNORECASE,
    )

def build_strict_termination_regex() -> List[re.Pattern]:
    """
    Matches termination events anchored to derivative instruments.
    1. Verb + Target: "terminated the swap"
    2. Target + Verb: "swap expired"
    """
    verbs = build_alternation(TERMINATION_VERBS)
    
    # 1. Verb ... Target
    # "terminated [the] [interest rate] swap"
    pat_verb_target = (
        rf"\b{verbs}\s+"
        rf"(?:{_DENIAL_FILLER})?" # Optional filler
        rf"{_DENIAL_TARGET}\b"
    )

    # 2. Target ... Verb
    # "swap [was] terminated", "swap expired"
    pat_target_verb = (
        rf"\b{_DENIAL_TARGET}\s+"
        rf"(?:{_DENIAL_FILLER})?"
        rf"{verbs}\b"
    )

    return [
        re.compile(pat_verb_target, re.IGNORECASE),
        re.compile(pat_target_verb, re.IGNORECASE)
    ]

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

ACTIVE_VERB_REGEX = build_active_verb_regex()

DID_NOT_HOLD_REGEX = build_did_not_hold_regex()
ABSENCE_REGEX = build_absence_regex()
POTENTIAL_REGEX = build_potential_regex()
POT_MITIGATION_REGEX = build_potential_mitigation_regex()
VAGUE_TIMING_REGEX = build_vague_timing_regex()
PRIOR_INDICATOR = build_prior_statement_pattern_2()
IMMATERIAL_REGEX = build_immaterial_regexes()
STRICT_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex()

TERMINATION_ALL_REGEX = build_regex(ALL_TERM_TERMS)
TERMINATION_REGEX = build_regex(TERMINATION_VERBS)
STRICT_TERMINATION_REGEXES = build_strict_termination_regex()

def is_strict_termination(text: str) -> bool:
    for regex in STRICT_TERMINATION_REGEXES:
        if regex.search(text):
            return True
    return False

def is_immaterial(text: str) -> bool:
    for regex in IMMATERIAL_REGEX:
        if regex.search(text):
            return True
    return False


def run_tests():
    print("Running tests for verb_regex.py...")

    test_cases = [
        # DID_NOT_HOLD_REGEX
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "Kronos was not a party to such a contract at December 31, 2004",
            True,
        ),
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "We do not, as a routine matter, use hedging vehicles",
            True,
        ),
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "We possess foreign exchange, interest rate, and commodity contracts",
            False,
        ),
        # ABSENCE_REGEX
        (
            "ABSENCE",
            ABSENCE_REGEX,
            "At March 31, 2004 and March 31, 2003, no financial instruments existed",
            True,
        ),
        (
            "ABSENCE",
            ABSENCE_REGEX,
            "We have no foreign exchange, interest rate, or other contracts",
            True,
        ),
        ("ABSENCE", ABSENCE_REGEX, "We have swaps", False),
        # POTENTIAL_REGEX
        (
            "POTENTIAL",
            POTENTIAL_REGEX,
            "We may continue to enter into interest rate swaps",
            True,
        ),
        ("POTENTIAL", POTENTIAL_REGEX, "We expect to hedge our exposure", False),
        (
            "POTENTIAL",
            POTENTIAL_REGEX,
            "We are planning to use currency contracts",
            True,
        ),
        (
            "POTENTIAL",
            POTENTIAL_REGEX,
            "We may consider using oil swap contracts",
            True,
        ),
        ("POTENTIAL", POTENTIAL_REGEX, "We expect to hedge with derivatives", True),
        ("POTENTIAL", POTENTIAL_REGEX, "We entered into swaps", False),
        # VAGUE_TIMING
        ("VAGUE_TIMING", VAGUE_TIMING_REGEX, "We use swaps from time to time", True),
        ("VAGUE_TIMING", VAGUE_TIMING_REGEX, "We use swaps periodically", True),
        # PRIOR
        (
            "PRIOR",
            PRIOR_INDICATOR,
            "In the prior year, we had interest rate swaps",
            True,
        ),
        ("PRIOR", PRIOR_INDICATOR, "During previous reporting periods", True),
        ("PRIOR", PRIOR_INDICATOR, "Historically", True),
        # TERMINATION
        ("TERMINATION", TERMINATION_REGEX, "The swaps expired", True),
        ("TERMINATION", TERMINATION_REGEX, "We terminated the agreement", True),
        ("TERMINATION", TERMINATION_REGEX, "The swaps matured", True),
        ("TERMINATION", TERMINATION_REGEX, "The swaps settles weekly", False),
        ("TERMINATION", TERMINATION_REGEX, "The swaps weekly settles", False),
        ("TERMINATION", TERMINATION_ALL_REGEX, "The annual settlement", False),
        # IMMATERIAL_REGEX
        (
            "IMM: Strict - Notional",
            IMMATERIAL_REGEX,
            "The notional amount was immaterial",
            True,
        ),
        (
            "IMM: Strict - Fair Value",
            IMMATERIAL_REGEX,
            "The fair value was insignificant",
            True,
        ),
        (
            "IMM: Strict - Carrying Value",
            IMMATERIAL_REGEX,
            "The carrying value of these instruments is de minimis",
            True,
        ),
        (
            "IMM: Strict - Market Value",
            IMMATERIAL_REGEX,
            "The market values were nominal",
            True,
        ),
        (
            "IMM: Counter - Impact",
            IMMATERIAL_REGEX,
            "The impact on earnings was not significant",
            False,
        ),
        (
            "IMM: Counter - Effect",
            IMMATERIAL_REGEX,
            "The effect of derivative instruments was immaterial",
            False,
        ),
        (
            "IMM: Counter - Gain/Loss",
            IMMATERIAL_REGEX,
            "The gain on the swap was trivial",
            False,
        ),
        (
            "IMM: Counter - Results",
            IMMATERIAL_REGEX,
            "The results of operations were not materially affected",
            False,
        ),
        (
            "IMM: Counter - Exposure",
            IMMATERIAL_REGEX,
            "The exposure related to foreign exchange contracts is insignificant",
            False,
        ),
        (
            "IMM: Instrument - FV of Swaps",
            IMMATERIAL_REGEX,
            "The fair value of the three month interest rate swaps was immaterial",
            True,
        ),
        (
            "IMM: Subject - Swaps",
            IMMATERIAL_REGEX,
            "The interest rate swap was immaterial",
            True,
        ),
        (
            "IMM: Subject - Derivatives",
            IMMATERIAL_REGEX,
            "Derivative instruments were considered trivial",
            True,
        ),
        (
            "IMM: Neg - Material",
            IMMATERIAL_REGEX,
            "The amount was material",
            False,
        ),
        (
            "IMM: Neg - Significant",
            IMMATERIAL_REGEX,
            "The value was significant",
            False,
        ),
        (
            "STRICT_TERM: Verb-Target",
            STRICT_TERMINATION_REGEXES,
            "We terminated the three month interest rate swap",
            True,
        ),
        (
            "STRICT_TERM: Target-Verb",
            STRICT_TERMINATION_REGEXES,
            "The foreign currency contracts has recently expired",
            True,
        ),
        (
            "STRICT_DO_NOT_MITIGATE",
            STRICT_DO_NOT_MITIGATE_REGEX,
            "We do not hedge our exposure to foreign currency fluctuations",
            True,
        ),
        (
            "STRICT_DO_NOT_MITIGATE",
            STRICT_DO_NOT_MITIGATE_REGEX,
            "We do not currently mitigate interest rate risk",
            True,
        ),
        (
            "STRICT_DO_NOT_MITIGATE",
            STRICT_DO_NOT_MITIGATE_REGEX,
            "We do not hedge",
            False,
        ),
    ]

    failures = 0
    for name, pattern, text, expected in test_cases:
        if isinstance(pattern, list):
            pass
        else:
            pattern = [pattern]
        passed = False
        # Run through each list of patterns. We pass if one at least passes
        for p in pattern:
            assert isinstance(p, re.Pattern)
            match = p.search(text)
            is_match = bool(match)
            if is_match == expected:
                passed = True
        if not passed:
            print(f"FAIL [{name}]: '{text}' -> Expected {expected}, Got {not expected}")
            failures += 1

    if failures == 0:
        print(f"All {len(test_cases)} tests passed.")
    else:
        print(f"{failures} tests failed.")
