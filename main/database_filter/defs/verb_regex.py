# =============================================================================
# VERB MAPS & PRECOMPILED REGEXES
# =============================================================================
import re
from typing import List, Optional
from defs.derivative_lib import create_target
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import ALL_TERM_TERMS, TERMINATION_VERBS, MITIGATION_VERBS, RISK_TERMS
from defs.verb_core import (
    _DENIAL_FILLER,
    GAP_CHAIN,
    INTENT_VERB_PATTERN,
    POTENTIAL_INDICATORS,
    POTENTIAL_SUFFIX_ADVERBS,
    NEGATIVE_AUXILIARY,
    PRE_VERB_GAP,
    SPECULATIVE_PHRASES,
    build_negation_prefix_pattern,
    NEGATIVE_AUXILIARY,
    build_strict_do_not_mitigate_regex,
)

_DENIAL_TARGET = create_target()


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

def build_passive_verb_regex(past_only: bool = False) -> re.Pattern:
    """
    Matches passive usage: "derivatives are used", "swaps were held"
    Structure: Instrument + [Gap] + Aux + Verb
    """
    if past_only:
        aux_verbs = r"(?:was|were)"
    else:
        aux_verbs = r"(?:is|are|was|were|have\s+been|has\s+been|be)"
    return re.compile(
        rf"\b{_DENIAL_TARGET}(?:[,\s]+)"
        rf"{_DENIAL_FILLER}"
        rf"{aux_verbs}\s+"
        rf"(?:{INTENT_VERB_PATTERN})\b",
        re.IGNORECASE,
    )

def build_active_verb_regex() -> re.Pattern:
    """
    Matches active usage: "use ... derivatives", "hold ... swaps"
    Structure: Verb + [Gap] + Instrument
    """
    return re.compile(
        rf"\b(?:{INTENT_VERB_PATTERN})\s+"
        rf"{GAP_CHAIN}"
        rf"{_DENIAL_FILLER}"
        rf"{_DENIAL_TARGET}\b",
        re.IGNORECASE,
    )

def build_vague_timing_regex() -> re.Pattern:
    """Matches: "from time to time", "in future periods" """
    return re.compile(rf"\b{build_alternation(SPECULATIVE_PHRASES)}\b", re.IGNORECASE)


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
        rf"{GAP_CHAIN}"
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
        r"The(?:se)?\s+(?:amounts?|values?)", # Tighten what value/amount
        r"The\s+(?:fair|carrying|market|notional)\s+values?",
        r"The\s+notional\s+:amounts?",
    ]
    subj_pat = build_alternation(subjects)
    
    verbs = r"(?:were|was|are|is|considered|deemed|remained)"

    # 1. Short / Strict (No instrument required)
    # "The notional amount was immaterial"
    # Gap: Subject -> [0-2 words] -> Verb -> [0-2 words] -> Immaterial
    pat_strict = rf"\b(?:{subj_pat})\s+(?:\w+\s+){{0,2}}{verbs}\s+(?:\w+\s+){{0,2}}{imm_pat}\b"
    regex_strict = re.compile(pat_strict)

    # 2. Instrument-Anchored (Permissive)
    # "The fair value of the interest rate swaps was immaterial"
    # Structure: Subject + (of/from/related to) + Instrument + ... + Immaterial
    pat_instrument = (
        rf"\b(?:{subj_pat})\s+(?:of|from|related\s+to)\s+"
        rf"{_DENIAL_TARGET}\s+"
        rf"(?:\w+\s+){{0,5}}{imm_pat}\b"
    )
    regex_pat_instrument = re.compile(pat_instrument)

    # 3. Instrument as Subject (Strict)
    # "The interest rate swap was immaterial"
    pat_instrument_subject = (
        rf"\b{_DENIAL_TARGET}\s+(?:\w+\s+){{0,2}}{verbs}\s+(?:\w+\s+){{0,2}}{imm_pat}\b"
    )
    regex_pat_instrument_subject = re.compile(pat_instrument_subject)

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
    
    aux = build_alternation(NEGATIVE_AUXILIARY)

    # The Fix: Allow an intervening comma-phrase or adverb between "Not" and "Verb"
    # Matches: "do not currently use" OR "do not, as a routine matter, use"
    # Logic: Optional (ActiveAdverb + Space) OR (Comma + AnyText + Comma + Space)
    # Also handles inversion: "nor did the company use"

    return re.compile(
        rf"{neg_prefix}"  # "do not"
        rf"{PRE_VERB_GAP}"  # <--- ", in any case, "
        rf"(?:to\s+)?(?:{INTENT_VERB_PATTERN})\s+"  # "use"
        rf"{GAP_CHAIN}"  # Optional: "hedging", "foreign exchange"
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
        rf"{GAP_CHAIN}"
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
        rf"{GAP_CHAIN}"
        rf"{_DENIAL_FILLER}"
        rf"{_DENIAL_TARGET}\b"
    )

    # 2. Target ... Verb
    # "swap [was] terminated", "swap expired"
    pat_target_verb = (
        rf"\b{_DENIAL_TARGET}\s+"
        rf"{GAP_CHAIN}"
        rf"{_DENIAL_FILLER}"
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


ACTIVE_VERB_REGEX = build_active_verb_regex()
PASSIVE_VERB_REGEX = build_passive_verb_regex(past_only=False)
PASSIVE_PAST_VERB_REGEX = build_passive_verb_regex(past_only=True)

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
        # ACTIVE_VERB_REGEX
        (
            "ACTIVE: Simple",
            ACTIVE_VERB_REGEX,
            "We hold interest rate swaps",
            True,
        ),
        (
            "ACTIVE: Quant + Modifiers",
            ACTIVE_VERB_REGEX,
            "The Company uses approximately two million in notional interest rate swaps",
            True,
        ),
        (
            "ACTIVE: Long Chain",
            ACTIVE_VERB_REGEX,
            "We entered into three separate foreign currency forward exchange contracts",
            True,
        ),
        (
            "ACTIVE: Negative (No Instrument)",
            ACTIVE_VERB_REGEX,
            "We use significant estimates",
            False,
        ),
        # PASSIVE_VERB_REGEX
        (
            "PASSIVE: Simple",
            PASSIVE_VERB_REGEX,
            "Interest rate swaps are used to hedge risk",
            True,
        ),
        (
            "PASSIVE: Past",
            PASSIVE_VERB_REGEX,
            "Foreign currency contracts were entered into",
            True,
        ),
        (
            "PASSIVE: Gap",
            PASSIVE_VERB_REGEX,
            "Commodity contracts, which are held for trading",
            True,
        ),
        (
            "PASSIVE: Past Only",
            PASSIVE_PAST_VERB_REGEX,
            "Swaps were held",
            True,
        ),
        (
            "PASSIVE: Past Only (Fail Present)",
            PASSIVE_PAST_VERB_REGEX,
            "Swaps are held",
            False,
        ),
        # DID_NOT_HOLD_REGEX
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "Kronos was not a party to any such material contract at December 31, 2004",
            True,
        ),
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "We do not, as a routine matter, use any speculative hedging vehicles",
            True,
        ),
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "We did not enter into any of the five million notional interest rate swaps",
            True,
        ),
        (
            "DID_NOT_HOLD",
            DID_NOT_HOLD_REGEX,
            "We possess foreign exchange, interest rate, and commodity contracts",
            False,
        ),
        (
            "DID_NOT_HOLD_INVERSION",
            DID_NOT_HOLD_REGEX,
            "Nor did the company use any such interest rate swaps",
            True,
        ),
        # ABSENCE_REGEX
        (
            "ABSENCE",
            ABSENCE_REGEX,
            "At March 31, 2004 and March 31, 2003, no such material financial instruments existed",
            True,
        ),
        (
            "ABSENCE",
            ABSENCE_REGEX,
            "We have no outstanding foreign exchange, interest rate, or other contracts",
            True,
        ),
        (
            "ABSENCE",
            ABSENCE_REGEX,
            "There were no open two million notional commodity swaps",
            True,
        ),
        ("ABSENCE", ABSENCE_REGEX, "We have swaps", False),
        # POTENTIAL_REGEX
        (
            "POTENTIAL",
            POTENTIAL_REGEX,
            "We may continue to enter into three separate interest rate swaps",
            True,
        ),
        ("POTENTIAL", POTENTIAL_REGEX, "We expect to hedge our exposure", False),
        (
            "POTENTIAL",
            POTENTIAL_REGEX,
            "We are planning to use approximately five million in currency contracts",
            True,
        ),
        (
            "POTENTIAL",
            POTENTIAL_REGEX,
            "We may consider using two million notional oil swap contracts",
            True,
        ),
        (
            "POTENTIAL",
            POTENTIAL_REGEX,
            "We expect to hedge with financial derivatives",
            True,
        ),
        ("POTENTIAL", POTENTIAL_REGEX, "We entered into swaps", False),
        # VAGUE_TIMING
        ("VAGUE_TIMING", VAGUE_TIMING_REGEX, "We use swaps from time to time", True),
        ("VAGUE_TIMING", VAGUE_TIMING_REGEX, "We use swaps periodically", True),
        # PRIOR
        (
            "PRIOR",
            PRIOR_INDICATOR,
            "In the prior year, we had two million in interest rate swaps",
            True,
        ),
        ("PRIOR", PRIOR_INDICATOR, "During previous reporting periods", True),
        ("PRIOR", PRIOR_INDICATOR, "Historically", True),
        # TERMINATION
        (
            "TERMINATION",
            TERMINATION_REGEX,
            "The two million notional swaps expired",
            True,
        ),
        (
            "TERMINATION",
            TERMINATION_REGEX,
            "We terminated the interest rate swap agreement",
            True,
        ),
        ("TERMINATION", TERMINATION_REGEX, "The swaps matured", True),
        ("TERMINATION", TERMINATION_REGEX, "The swaps settles weekly", False),
        ("TERMINATION", TERMINATION_REGEX, "The swaps weekly settles", False),
        ("TERMINATION", TERMINATION_ALL_REGEX, "The annual settlement", False),
        (
            "TERMINATION: Settlement Date",
            TERMINATION_ALL_REGEX,
            "The settlement date of the swap",
            True,
        ),
        (
            "TERMINATION: Annual Settlement",
            TERMINATION_ALL_REGEX,
            "The annual settlement of the swap",
            False,
        ),
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
            "We terminated the three month two million notional interest rate swap",
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
