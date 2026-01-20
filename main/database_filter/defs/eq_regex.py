import re
from typing import Tuple, List

from defs.derivatives_core import MatchLevel, build_smart_regex, expand_instruments, run_category_tests, run_category_tests_counter, suffix_alternation
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION, VALUATION_MODELS, build_risk_managment_phrase
from defs.verb_regex import build_strict_do_not_mitigate_regex

def build_eq_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    # --- 1. Build Core Terms (Prefixes) ---
    liability = r"liabilit(?:y|ies)"
    option = r"options?"
    warrant = r"warrants?"
    derivative = r"derivatives?"
    # Strict Core Terms (Precise market/price references)
    strict_core_terms = [
        r"equity",
        r"equity[- ](?:based|related|linked|index)",
        r"market\s+index",
    ]
    strict_core_alternation = build_alternation(strict_core_terms, True)

    # 2. Build Specific Phrases (Max Munch) - UNIFIED LIST
    # Convertible phrases (Structural Embedded Derivatives)
    convertible_phrases = [
        rf"embedded\s+conversion\s+(?:{option}|features?|{derivative})",
        rf"conversion\s+option\s+{liability}",
        rf"bifurcated\s+conversion\s+{option}",
        rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))\s+(?:hedges?|derivatives?)",
    ]

    # Warrant liabilities (Financial Warrants only)
    warrant_phrases = [
        # Direct warrant + (liability OR derivative)
        rf"{warrant}\s+(?:and\s+|or\s+)?(?:{derivative}[- ]{liability}|{liability}|{derivative})",
        # Inverted: liability/derivative + warrant
        rf"(?:{liability}|{derivative})[- ]classified\s+{warrant}",
        # Classified context: warrant...classified as (liability|derivative)
        rf"(?:{derivative}\s+)?{warrant}.*(?:classified|accounted(?: for)?)\s+as\s+(?:a\s+)?(?:{derivative}[- ]{liability}|{derivative}|{liability})",
        rf"(?:{derivative}[- ]{liability}|{derivative}|{liability})[- ]{warrant}",
    ]

    # Other Explicitly Safe Phrases
    explicit_phrases = [
        r"call spreads?",
        r"capped calls?",
        r"accelerated\s+share\s+repurchases?",
        r"(?:forward|prepaid)\s+contracts?\s+on\s+(?:own\s+)?shares?",
        r"margin\s+loans?",
    ]

    # Combine and pre-sort all high-confidence specific phrases
    all_specifics = explicit_phrases + convertible_phrases + warrant_phrases
    sorted_specific_phrases = sorted(
        all_specifics, key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:"))
    )

    # -------------------------------------------------------------------------
    # --- A. STRICT Pattern Construction (High Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for attachment: Must exclude standalones to ensure precision in core matches
    strict_attachment_fragment = expand_instruments(
        unsafe=False, exclude_standalone_suffixes=True
    )

    strict_pattern = build_smart_regex(
        [strict_core_alternation],  # Precise prefixes (share price, S&P 500, etc.)
        strict_attachment_fragment,  # Must attach a derivative base (e.g., 'swap' or 'future')
        sorted_specific_phrases,  # All high-priority explicit phrases
    )
    strict_eq_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # --- B. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for general pattern combination: Includes all derivative terminology, including standalones.
    soft_instrument_fragment = expand_instruments(unsafe=True, exclude_standalone_suffixes=True, additional_standalone_suffixes=["options?"])

    soft_pattern = build_smart_regex(
        [strict_core_alternation],
        soft_instrument_fragment,  # Full range of instruments (e.g., 'options', 'warrants' standalones)
        sorted_specific_phrases
        + [
            rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))", # Gets defanged if nst is true
        ],
    )
    soft_eq_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)
    
    loose_instrument_fragment = expand_instruments(unsafe=True, exclude_standalone_suffixes=False)
    loose_pattern = build_smart_regex(
        [strict_core_alternation],
        loose_instrument_fragment,
        sorted_specific_phrases
        + [
            rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))",
        ],
    )
    loose_eq_regex = re.compile(r"\b" + loose_pattern + r"\b", re.IGNORECASE)

    return strict_eq_regex, soft_eq_regex, loose_eq_regex


stock_terms = [
    "prices?",
    "markets?",
    "dividends?",
    "splits?",
    "units?",
    "warrants?",
    "indices?",
    "awards?",
    "grants?",
    "compensation",
    "appreciation",
    "options?",
    "purchases",
    "capital",
    "securit(?:y|ies)",
]
stock_alt = build_alternation(stock_terms)


# Section 1: Employee Equity Compensation (Updated)
EQUITY_COMP_KEYWORDS = [
    # 1. Standard Compensation Terms
    "stock (?:options?|awards?|splits?|dividends?|purchases?)",
    "restricted (?:stock|shares?|units?)",
    "RSUs?",
    "PSUs?",  # Performance Share Units
    "DSUs?",  # Deferred Share Units
    "ESPP",  # Employee Stock Purchase Plan
    "SARs?",  # Stock Appreciation Rights
    "stock appreciation rights?",
    "(?:phantom|employee) stocks?",
    "employees?",
    # 2. Plan/HR Terminology
    "compensations?",
    "(?:benefit|incentive|treasury) plans?",
    "share-based payment",
    "vesting",
    "exercisable",
    "grant date",
    "service period",
    "unrecognized compensation",
    "weighted-average exercise price",
    # 3. Income Statement Noise
    "bonus",
    "salary",
    "wage",
    "payroll",
    "severance",
    "common shares?",
    "exercise",
]


def build_eq_context_terms() -> Tuple[List[str], List[str], List[str]]:

    # 2. Prices & Markets
    eq_prices_markets = [
        rf"(?:stock|share|equity)\s+{stock_alt}",
        r"market\s+index(?:es)?",
    ]

    # 3. Indices
    eq_indices = [
        r"S\&P\s+500",
        r"Nasdaq(?:\s+Composite|\s+Index)?",
        r"Dow\s+Jones(?:\s+Industrial\s+Average|\s+Index)?",
        r"Russell\s+2000",
    ]

    # 4. Equity Components (Types of stock)
    eq_components = [
        r"(?:preferred|common|treasury|outstanding|restricted|capital|equity)\s+(?:stocks?|shares)",
        r"outstanding equity",
    ]

    # 5. Structures & Events
    eq_structures = [
        r"initial\s+public\s+offering|IPO",
        r"(?:primary|secondary)\s+markets?",
        r"acquisition date",
    ]

    # 6. Risk Integration
    eq_risk = [
        rf"equity\s+{_RISK_ALTERNATION}",
    ]

    # 7. Specific Instruments (Strict)
    eq_instruments = [
        r"accelerated\s+share\s+repurchases?",
        r"capped\s+calls?",
    ]

    strict_terms = eq_risk + eq_instruments + VALUATION_MODELS

    soft_terms = (
        eq_prices_markets
        + eq_indices
        + eq_components
        + eq_structures
        + EQUITY_COMP_KEYWORDS
    )

    eq_glue = eq_indices + eq_components + eq_prices_markets
    risk_terms = [build_risk_managment_phrase(eq_glue)]

    return strict_terms, soft_terms, risk_terms


EQ_STRICT_TERMS, EQ_SOFT_TERMS, EQ_RISK_TERMS = build_eq_context_terms()
EQ_CONTEXT_TERMS = EQ_STRICT_TERMS + EQ_SOFT_TERMS + EQ_RISK_TERMS
EQ_CONTEXT_REGEX = build_regex(EQ_CONTEXT_TERMS)
EQ_STRICT_CONTEXT_REGEX = build_regex(EQ_STRICT_TERMS + EQ_RISK_TERMS)
EQ_RISK_REGEX = build_regex(EQ_RISK_TERMS)
EQ_REGEX, EQ_SOFT_REGEX, EQ_LOOSE_REGEX = build_eq_regex()
EXCLUDE_REGEX_EQUITY_COMP = build_regex(EQUITY_COMP_KEYWORDS)
EQ_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(
    [rf"(?:stock|share|equity)\s+{stock_alt}"]
)

def run_tests():
    test_cases = [
        ("equity swap", MatchLevel.STRICT),
        ("equity option", MatchLevel.SOFT),
        ("equity derivative", MatchLevel.STRICT),
        ("equity linked swap", MatchLevel.STRICT),
        ("market index option", MatchLevel.SOFT),
        ("embedded conversion option", MatchLevel.STRICT),
        ("warrant liability", MatchLevel.STRICT),
        ("equity contract", MatchLevel.LOOSE),
        ("equity hedges", MatchLevel.LOOSE),
        ("convertible debt", MatchLevel.SOFT),
        ("convertible debt hedge", MatchLevel.STRICT),
    ]
    run_category_tests(test_cases, EQ_REGEX, EQ_SOFT_REGEX, EQ_LOOSE_REGEX)

    counter_cases = [
        ("stock option", MatchLevel.LOOSE),
        ("share option", MatchLevel.LOOSE),
        ("equity compensation", MatchLevel.LOOSE),
        ("equity award", MatchLevel.LOOSE),
        ("warrants", MatchLevel.LOOSE),
        ("convertible debt", MatchLevel.STRICT),
        ("equity", MatchLevel.LOOSE),
        ("stock hedging", MatchLevel.LOOSE),
    ]
    run_category_tests_counter(counter_cases, EQ_REGEX, EQ_SOFT_REGEX, EQ_LOOSE_REGEX)
