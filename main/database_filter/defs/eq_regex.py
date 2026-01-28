import re
from typing import Tuple, List

from defs.derivatives_core import (
    ALL_SUFFIXES,
    BASE,
    DERIVATIVES,
    UNAMBIGUOUS_BASE_TYPES,
    DerivativeGenerator,
    Groups,
    MultiBaseGenerator,
)
from defs.regex_lib import (
    add_restrictions,
    build_alternation,
    build_compound,
    build_regex,
    to_build_alternation,
)
from defs.shared_context import (
    _DEBT_TERMS,
    _RISK_ALTERNATION,
    VALUATION_MODELS,
    build_risk_managment_phrase,
)

EQ_INDICES = [
    r"S\&P\s+(?:500|400|600|1500)(?:\s+total\s+return)?(?:\s+index)?",
    r"Nasdaq(?:[-\s]?100|(?:\s+Composite)?)(?:\s+index)?",
    r"Dow\s+Jones(?:\s+Industrial\s+Average)?(?:\s+index)?",
    r"Russell\s+(?:1000|2000|3000)(?:\s+(?:Value|Growth))?(?:\s+index)?",
    r"MSCI\s+(?:World|ACWI|EAFE|Europe|Emerging\s+Markets|Asia[-\s]?Pacific|Frontier\s+Markets)(?:\s+index)?",
    r"FTSE\s+(?:100|250|350|All[-\s]?Share|Developed|Emerging)(?:\s+index)?",
    r"(?:Nikkei\s+225|TOPIX|Hang\s+Seng|HSI|DAX|Euro\s+Stoxx\s+50|CAC\s+40|IBEX\s+35|SMI|ASX\s+200|TSX\s+Composite)(?:\s+index)?",
    add_restrictions(
        r"market[- ]index",
        lookbehinds=[
            r"commodity",
            r"energy",
            r"oil",
            r"gas",
            r"power",
            r"bond",
            r"debt",
            r"credit",
            r"gold",
            r"silver",
        ],
    ),
]


def build_eq_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    # --- 1. Build Core Terms (Prefixes) ---
    liability = r"liabilit(?:y|ies)"
    option = r"options?"
    warrant = r"warrants?"
    derivative = r"derivatives?"

    # --- Construct Restricted Starters for Equity ---
    # Block "options and warrants" (naked) to avoid compensation noise
    sep = r"(?:\s*,?\s*(?:and|or|&)\s+|[\s,]+)"
    _SFX_ALT = to_build_alternation(
        Groups.UNAMBIGUOUS_SUFFIXES + Groups.AMBIGUOUS_SUFFIXES
    )

    # Define ambiguous group that needs restriction (Option, Warrant, Cap, Floor, Lock)
    ambiguous_list = [BASE.OPTION, BASE.WARRANT, BASE.CAP, BASE.FLOOR, BASE.LOCK]
    _AMBIGUOUS_ALT = to_build_alternation(ambiguous_list)
    _STRICT_ALT = to_build_alternation(UNAMBIGUOUS_BASE_TYPES)
    _AMBIGUOUS_STRICT = add_restrictions(
        _AMBIGUOUS_ALT,
        lookaheads=[rf"{sep}(?:{_AMBIGUOUS_ALT}\b(?!\s+{_SFX_ALT}))(?!{_STRICT_ALT})"],
        lookahead_sep="",
    )
    _OTHER_BASES = [
        b
        for b in (Groups.CORE_UNAMBIGUOUS_BASES + Groups.AMBIGUOUS_BASES)
        if b not in ambiguous_list
    ]
    eq_starters = [_AMBIGUOUS_STRICT] + _OTHER_BASES

    # Generate restricted multi-base patterns for Equity context
    eq_double, eq_triple = MultiBaseGenerator(
        suffix_restrictions=[r"equity"], starters=eq_starters
    ).generate()

    # Strict Core Terms (Precise market/price references)
    strict_core_terms = [
        r"equity(?:[- ](?:based|related|linked|index))?",
        rf"{to_build_alternation(EQ_INDICES)}(?:[- ](?:based|related|linked|index))?",
    ]

    # Restricted Core Terms (Common words that require SAFE bases to avoid compensation/noise)
    # These will ONLY match with Unambiguous Bases (Swaps, Futures, etc.)
    restricted_core = [
        r"dividends?",
        r"stocks?",
        r"shares?",
    ]
    restricted_core_terms = [
        rf"{to_build_alternation(restricted_core)}(?:[- ](?:based|related|linked|index))?"
    ]
    CONV = rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))"

    # 2. Build Specific Phrases (Max Munch) - UNIFIED LIST
    # Convertible phrases (Structural Embedded Derivatives)
    convertible_phrases = [
        rf"embedded\s+conversion\s+(?:{option}|features?|{derivative})",
        rf"conversion\s+option\s+{liability}",
        rf"bifurcated\s+conversion\s+{option}",
        rf"{CONV}\s+(?:hedges?|derivatives?)",
    ]

    # Warrant liabilities (Financial Warrants only)
    warrant_phrases = [
        # Warrant liability/derivative
        rf"{warrant}\s+(?:and\s+|or\s+)?(?:{liability}|{derivative})",
        # Inverted: liability/derivative (classified) warrants
        rf"(?:{liability}|{derivative})(?:[- ]classified)?\s+{warrant}",
        # Classified context: warrant...classified as (liability|derivative)
        rf"{warrant}(?:\s+\b(?!not\b)\w+\b){{0,3}}(?:accounted|classified)(?:\s+\b(?!not\b)\w+\b){{0,3}}(?:{liability}|{derivative})"
        # call/put warrants
        rf"(?:call|put)\s+{warrant}",
    ]
    soft_phrases = [
        CONV,
        rf"{_DEBT_TERMS}(?:[- ](?:linked|attached))?\s+{warrant}",
        rf"{warrant}(?:[- ](?:linked|attached))\s+{_DEBT_TERMS}",
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

    _RESTRICTED_OPTION = add_restrictions(BASE.OPTION.value, lookbehinds=[r"equity"])
    _STRICT_CONFIG = DERIVATIVES(
        PREFIX=strict_core_terms,
        MULTI_BASE=[eq_double, eq_triple],
        ADDITIONAL_BASES=[_RESTRICTED_OPTION],
    )
    _STRICT_PATTERN = DerivativeGenerator(config=_STRICT_CONFIG).generate()
    _RESTRICTED_BASES = Groups.CORE_UNAMBIGUOUS_BASES.copy()
    _RESTRICTED_BASES.remove(BASE.SWAP)
    _RESTRICTED_BASES.remove(BASE.FORWARD)

    _SWP_FWD = [BASE.SWAP, BASE.FORWARD]
    _SWP_FWD_ALT = to_build_alternation(_SWP_FWD)
    _RESTRICTED_SWP_FWD = add_restrictions(
        _SWP_FWD_ALT,
        lookbehinds=[
            r"stocks",
            r"dividends",
            r"shares",
            r"stock",
            r"dividend",
            r"share",
        ],
    )
    _RESTRICTED_BASES.append(_RESTRICTED_SWP_FWD)
    _RESTRICTED_CONFIG = DERIVATIVES(
        PREFIX=restricted_core_terms,
        _BASES=_RESTRICTED_BASES,
        _AMB_BASES=[],  # Explicitly empty
        ADDITIONAL_BASES=[],
        STANDALONE_SUFFIXES=[],  # No "Stock Agreement"
        MULTI_BASE=[
            eq_triple
        ],  # Allow triple base only to avoid "Stock options and warrants"
    )
    _RESTRICTED_PATTERN = DerivativeGenerator(config=_RESTRICTED_CONFIG).generate()

    strict_eq_regex = build_regex(
        [_STRICT_PATTERN, _RESTRICTED_PATTERN] + sorted_specific_phrases
    )

    # -------------------------------------------------------------------------
    # --- B. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    _SOFT_CONFIG = DERIVATIVES(
        PREFIX=strict_core_terms,
        MULTI_BASE=[eq_double, eq_triple],
        ADDITIONAL_BASES=[],
        STANDALONE_BASES=[_RESTRICTED_OPTION],
    )
    _SOFT_PATTERN = DerivativeGenerator(config=_SOFT_CONFIG).generate()
    soft_eq_regex = build_regex(
        [_SOFT_PATTERN, _RESTRICTED_PATTERN] + sorted_specific_phrases + soft_phrases
    )

    _LOOSE_CONFIG = DERIVATIVES(PREFIX=strict_core_terms, MULTI_BASE=[], LOOSE=True)
    _LOOSE_PATTERN = DerivativeGenerator(config=_LOOSE_CONFIG).generate()
    loose_eq_regex = build_regex(
        [_LOOSE_PATTERN, _RESTRICTED_PATTERN] + sorted_specific_phrases + soft_phrases
    )

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
    "(?:phantom|employee|common) stocks?",
    "employees?",
    "options? granted",
    "fiduciary",
    "chief (?:executives?|financial|accounting|officers?|operating|technology)",
    "(?:executive|financial|accounting|technology|operating) (?:officers?|directors?)",
    "board of directors?",
    # 2. Plan/HR Terminology
    "compensations?",
    "(?:benefit|incentive|treasury) plans?",
    "share-based payments?",
    "vest(?:ing|ed)",
    "exercis(?:able|ed)?",
    "grant dates?",
    "service period",
    "weighted-average (?:strike|exercise) price",
    # 3. Income Statement Noise
    "bonus(?:es)?",
    "salar(?:y|ies)?",
    "wages?",
    "payroll",
    "severance",
    "(?:common|treasury|outstanding) shares?",
    "asset swaps?",
]


def build_eq_context_terms() -> Tuple[List[str], List[str], List[str]]:

    # 2. Prices & Markets
    eq_prices_markets = [
        rf"(?:stock|share|equity)\s+{stock_alt}",
        r"market\s+index(?:es)?",
    ]

    # 3. Indices
    eq_indices = EQ_INDICES

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
        r"series\s+(?:A|B|C|D|E|F|G|H|I|J)",
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

from defs.verb_core import build_strict_do_not_mitigate_regex

EQ_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(
    [rf"(?:stock|share|equity|treasury)\s+{stock_alt}"]
)


def run_tests():
    from defs.derivatives_core import (
        MatchLevel,
        run_category_tests,
        run_category_tests_counter,
    )

    test_cases = [
        ("equity swap", MatchLevel.STRICT),
        ("equity option", MatchLevel.LOOSE),
        ("equity derivative", MatchLevel.STRICT),
        ("equity linked swap", MatchLevel.STRICT),
        ("market index option", MatchLevel.SOFT),
        ("embedded conversion option", MatchLevel.STRICT),
        ("warrant liability", MatchLevel.STRICT),
        ("warrant accounted for as a liability", MatchLevel.STRICT),
        ("call warrants", MatchLevel.STRICT),
        ("bond warrants", MatchLevel.SOFT),
        ("derivative warrants", MatchLevel.STRICT),
        ("equity contract", MatchLevel.LOOSE),
        ("equity hedges", MatchLevel.LOOSE),
        ("convertible debt", MatchLevel.SOFT),
        ("convertible debt hedge", MatchLevel.STRICT),
        ("equity option and warrants", MatchLevel.LOOSE),
        (
            "equity options, warrants and futures",
            MatchLevel.STRICT,
        ),  # TRIPLE_BASE overrides equity exclusion
        (
            "stock options, warrants and caps",
            MatchLevel.STRICT,
        ),  # TRIPLE_BASE with stock prefix
        (
            "stock agreement, options and warrants",
            MatchLevel.NONE,
        ),  # TRIPLE_BASE with agreement start
        (
            "equity options and swaps",
            MatchLevel.STRICT,
        ),  # Double Base (Ambiguous + Unambiguous)
        ("stock swap", MatchLevel.NONE),
        ("dividend futures", MatchLevel.STRICT),
        ("S&P 500 swap", MatchLevel.STRICT),
        ("S&P 500 option", MatchLevel.SOFT),
        ("market index swap", MatchLevel.STRICT),
        ("commodity market index swap", MatchLevel.NONE),
    ]
    print("Equity Derivatives tests:")
    run_category_tests(test_cases, EQ_REGEX, EQ_SOFT_REGEX, EQ_LOOSE_REGEX)

    counter_cases = [
        ("stock option", MatchLevel.LOOSE),
        ("stock option agreement", MatchLevel.LOOSE),
        ("dividend option", MatchLevel.LOOSE),
        ("share option", MatchLevel.LOOSE),
        ("equity option and warrants", MatchLevel.STRICT),
        ("equity compensation", MatchLevel.LOOSE),
        ("equity award", MatchLevel.LOOSE),
        ("warrants", MatchLevel.LOOSE),
        ("convertible debt", MatchLevel.STRICT),
        ("equity", MatchLevel.LOOSE),
        ("stock hedging", MatchLevel.LOOSE),
        ("warranty liability", MatchLevel.LOOSE),
        ("derivative warranty", MatchLevel.LOOSE),
        ("equity instruments", MatchLevel.SOFT)
    ]
    run_category_tests_counter(counter_cases, EQ_REGEX, EQ_SOFT_REGEX, EQ_LOOSE_REGEX)
