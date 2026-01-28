import re
from typing import Tuple, List

from defs.regex_lib import add_restrictions, build_alternation, build_compound, build_regex, to_build_alternation
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION, ALL_TERM_TERMS, build_risk_managment_phrase
from defs.derivatives_core import ALL_SUFFIXES, BASE, DERIVATIVES, MULTI_BASE, SUFFIX, SUFFIXES, DerivativeGenerator, Groups

_IR_DEBT = Rf"(?:{_DEBT_TERMS}|credit\s+facilit(?:y|ies))"
BENCHMARK_RATES = [
    "SOFR",
    "SONIA",
    "LIBOR",
    "EURIBOR",
    "ESTR",
    "EONIA",
    "TONAR",
    "BBSW",
    "CIBOR",
    "STIBOR",
    "HIBOR",
    "TIBOR",
    "PRIBOR",
    "MOSPRIME",
    r"euro(?:\s|\-)?dollars?",
]

RATE_TYPES = ["fixed", "variable", "floating"]
INTEREST = add_restrictions(
    r"(?:forward(?:[- ]starting)?\s)?interest",
    lookbehinds=[r"foreign"],
)
IR_RATE = f"{INTEREST}[- ]rates?"

STRONG_RATE_ADJECTIVES = [INTEREST]

TREASURY_RATE_LOCK = r"treasury(?:[- ]rate)? locks?"
WEAK_RATE_ADJECTIVES = [
    "benchmark",
    "prime",
    r"fed(?:eral)?[- ]funds",
    r"treasury" # completeness
] + RATE_TYPES

RATE_ADJECTIVES = STRONG_RATE_ADJECTIVES + WEAK_RATE_ADJECTIVES
def build_ir_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    rate_alternation = build_alternation(STRONG_RATE_ADJECTIVES + WEAK_RATE_ADJECTIVES, sort_longest_first=True)
    rate_adjective_phrases = rf"{rate_alternation}[- ]rate"
    # --- 1. Helper Definitions ---
    def build_pay_receive_structure() -> str:
        """Constructs the core pay/receive structure pattern."""
        rate_alternation = build_alternation(RATE_TYPES, sort_longest_first=False)
        FLEXIBLE_SEPARATOR = r"(?:\s*[,/;&]?\s*|\s+(?:and|or)\s+|\s*[- ]+)\s*"

        return (
            r"pay[- ]"
            rf"(?:{rate_alternation}(?:[- ]rate)?)"
            rf"{FLEXIBLE_SEPARATOR}"
            r"receive[- ]"
            rf"(?:{rate_alternation}(?:[- ]rate)?)"
            rf"(?:{rate_adjective_phrases})?"
        )

    # --- 2. Build Instrument Alternations ---
    pay_receive_pattern_string = build_pay_receive_structure()

    # --- 4. Build Core Terms and Specific Phrases ---

    benchmark_alternation = build_alternation(BENCHMARK_RATES, sort_longest_first=True)
    brate_adjective_phrases = rf"(?:{benchmark_alternation})(?:[- ](?:related|linked|based))?"

    # Split Core Terms into Strong (can take "Contract") and Weak (Must be explicit derivative)
    strong_rate_alt = build_alternation(STRONG_RATE_ADJECTIVES, sort_longest_first=True)
    strong_rate_phrases = rf"{strong_rate_alt}[- ]rate"

    weak_rate_alt = build_alternation(WEAK_RATE_ADJECTIVES, sort_longest_first=True)
    weak_rate_phrases = rf"{weak_rate_alt}[- ]rate"

    strong_core_terms = [
        "single[- ]currency",
        r"(?:(?:cross|multi)[- ])?currency\s+interest(?:[- ]rate)?",
        "interest(?:[ -]rate)?[- ]exchange",
        pay_receive_pattern_string,
        strong_rate_phrases,
        brate_adjective_phrases,
    ]

    weak_core_terms = [
        weak_rate_phrases
    ]

    # 1. Strict: Strong terms allow "Contract", Weak terms do not
    _STRICT_CONFIG_STRONG = DERIVATIVES(
        PREFIX=strong_core_terms,
        STANDALONE_SUFFIXES=[SUFFIX.CONTRACT, SUFFIX.AGREEMENT, BASE.OPTION], # Assume option has been stripped by debt feature
        ADDITIONAL_BASES=[BASE.PROTECTION],
        MULTI_BASE=[MULTI_BASE.DOUBLE_BASE],
    )

    _STRICT_CONFIG_WEAK = DERIVATIVES(
        PREFIX=weak_core_terms,
        STANDALONE_SUFFIXES=[], # Weak terms cannot be "Fixed Rate Contract"
        ADDITIONAL_BASES=[BASE.PROTECTION],
        MULTI_BASE=[]
    )

    # 2. Soft: Strong terms allow Ambiguous Bases (Option/Cap) + Contract
    _SOFT_CONFIG_STRONG = DERIVATIVES(
        PREFIX=strong_core_terms,
        STANDALONE_BASES=[BASE.OPTION, BASE.CAP, BASE.FLOOR, BASE.LOCK, BASE.HEDGE],
        STANDALONE_SUFFIXES=[SUFFIX.CONTRACT, SUFFIX.AGREEMENT],
        ADDITIONAL_BASES=[BASE.PROTECTION],
        MULTI_BASE=[MULTI_BASE.DOUBLE_BASE],
    )
    _SOFT_CONFIG_WEAK = DERIVATIVES(
        PREFIX=weak_core_terms,
        STANDALONE_BASES=[BASE.OPTION], # allow none to reduce FP
        ADDITIONAL_BASES=[BASE.PROTECTION],
        MULTI_BASE=[]
    )

    # 3. Loose: Context matching
    _LOOSE_CONFIG= DERIVATIVES(
        PREFIX=strong_core_terms + weak_core_terms,
        ADDITIONAL_BASES=[BASE.PROTECTION],
        LOOSE=True,
        MULTI_BASE=[],
    )

    # _MULTIBASE_CONFIG = DERIVATIVES(
    #     PREFIX=strong_core_terms + [],
    #     STANDALONE_SUFFIXES=[],
    #     _BASES = [],
    #     _AMB_BASES = [],
    #     SUFFIXES=[],
    #     MULTI_BASE=[]
    # )
    # _MULTIBASE_PATTERN = DerivativeGenerator(config=_MULTIBASE_CONFIG).generate()

    specific_phrases = [
        build_compound(
            [
                r"zero[- ]coupon",
                r"overnight[- ]index(?:ed)?",
                r"constant[- ]maturity",
                r"amortizing",
                r"forward[- ]start(?:ing)?",
            ],
            [BASE.SWAP, BASE.SWAPTION],
        ),
        TREASURY_RATE_LOCK,
        r"forward[- ]rate[- ]agreements?",
    ]

    SPECIFIC_PATTERN = build_alternation(specific_phrases)

    # Generate the regex strings
    _STRICT_PATTERN = build_alternation([
        DerivativeGenerator(config=_STRICT_CONFIG_STRONG).generate(),
        DerivativeGenerator(config=_STRICT_CONFIG_WEAK).generate()
    ])
    _SOFT_PATTERN = build_alternation([
        DerivativeGenerator(config=_SOFT_CONFIG_STRONG).generate(),
        DerivativeGenerator(config=_SOFT_CONFIG_WEAK).generate()
    ])

    _LOOSE_PATTERN = build_alternation([
        DerivativeGenerator(config=_LOOSE_CONFIG).generate(),
    ])

    STRICT = build_regex([_STRICT_PATTERN, SPECIFIC_PATTERN])
    SOFT = build_regex([_SOFT_PATTERN, SPECIFIC_PATTERN])

    LOOSE = build_regex([_LOOSE_PATTERN, SPECIFIC_PATTERN])

    return STRICT, SOFT, LOOSE

IR_REGEX, IR_SOFT_REGEX, IR_LOOSE_REGEX = build_ir_regex()

# 1. Complex Debt Term (Consolidated)
# Logic: Match DEBT only if:
#   - NOT preceded by "convertible" (Equity context)
#   - NOT preceded by "foreign" (FX context)
#   - NOT preceded by "denominated" (FX context)
#   - NOT followed by "denominated" (FX context)
IR_DEBT_LOOKBEHIND_TERM = (
    r"(?<!convertible\s)"  # Negative Lookbehind 1
    r"(?<!foreign\s)"  # Negative Lookbehind 2
    r"(?<!denominated\s)"  # Negative Lookbehind 3
    rf"{_IR_DEBT}"  # The actual match
    r"(?!\s+denominated)"  # Negative Lookahead (NEW)
)


# =============================================================================
# BANK ENTITY LISTS (New)
# =============================================================================

CENTRAL_BANKS = [
    r"Bank\s+of\s+England",
    r"\bBoE\b",
    r"Federal\s+Reserve",
    r"the\s+Fed\b",  # Careful with "Fed", usually safe with "the"
    r"Federal\s+Reserve\s+Bank\s+of\s+New\s+York",
    r"New\s+York\s+Fed",
    r"\bNY\s+Fed\b",
    r"European\s+Central\s+Bank",
    r"\bECB\b",
    r"Swiss\s+National\s+Bank",
    r"\bSNB\b",
    r"Bank\s+of\s+Japan",
    r"\bBoJ\b",
    r"Financial\s+Conduct\s+Authority",  # UK Regulator (LIBOR killer)
    r"\bFCA\b",
]
# Major Global & US Banks (Counterparties / Lenders)
BANK_ENTITIES = [
    # US Majors
    r"J\.?P\.?\s+Morgan(?:\s+Chase)?",
    r"Goldman\s+Sachs",
    r"Morgan\s+Stanley",
    r"Bank\s+of\s+America",
    r"BofA(?:\s+Securities)?",
    r"Merrill\s+Lynch",
    r"Citigroup",
    r"Citibank",
    r"Wells\s+Fargo",
    r"State\s+Street",
    r"Bank\s+of\s+New\s+York(?:\s+Mellon)?",
    r"BNY\s+Mellon",
    # International Majors
    r"Barclays",
    r"HSBC",
    r"Deutsche\s+Bank",
    r"UBS",
    r"Credit\s+Suisse",
    r"BNP\s+Paribas",
    r"Soci[eé]t[eé]\s+G[eé]n[eé]rale",
    r"SocGen",
    r"Credit\s+Agricole",
    r"NatWest",
    r"Standard\s+Chartered",
    r"Santander",
    r"Mizuho",
    r"Nomura",
    r"Sumitomo\s+Mitsui",
    r"MUFG",
    r"Royal\s+Bank\s+of\s+Canada",
    r"RBC",
    r"Toronto[- ]Dominion",
    r"TD\s+Bank",
    r"Scotiabank",
    r"Bank\s+of\s+Montreal",
    r"BMO",
] + CENTRAL_BANKS


# Compile for Bag-of-Words Scoring
BANK_SCORING_REGEX = build_regex(BANK_ENTITIES)

# --- LIBOR TRANSITION NOISE (Updated) ---
LIBOR_TRANSITION_KEYWORDS = [
    # ... (Your existing transition terms: cessation, phase-out) ...
    r"LIBOR\s+transition",
    r"(?:phase(?:\s|\-)?out|replacement|migration|discontinu(?:ance|ation|ed)|transition|cessation)\s+(?:of|(?:away\s+)?from)\s+LIBOR",
    # Regulatory Bodies & Committees
    r"Alternative\s+Reference\s+Rates?\s+Committee",
    r"\bARRC\b",
    r"reference\s+rate\s+reform",
    r"interbank\s+offered\s+rates?\s+reform",
    r"IBOR\s+reform",
    # Specific Dates
    r"publication\s+of\s+(?:certain\s+|all\s+)?LIBOR\s+rates?",
    r"no\s+longer\s+publish(?:ed)?",
    r"cease\s+to\s+be\s+representative",
    r"synthetic\s+LIBOR",
    r"ASC\s+848",
    r"Facilitation\s+of\s+the\s+Effects\s+of\s+Reference\s+Rate\s+Reform",
    r"publication\s+(?:of\s+)?(?:certain\s+|all\s+)?(?:USD\s+)?LIBOR.*June\s+30,?\s+2023",
    # 2. "Cease... after June 30"
    # Matches: "cease to be representative after June 30, 2023"
    r"cease\s+to\s+be.*June\s+30,?\s+2023",
    # 3. "Transition... by June 30"
    r"transition.*by\s+June\s+30,?\s+2023",
] + CENTRAL_BANKS


def is_bank_list_noise(text: str, threshold: int = 3) -> bool:
    """
    Bag-of-Words Score for Banking Lists.

    Logic: If a paragraph mentions 3+ distinct banks, it is likely a
    Credit Agreement / Syndication list, not a specific derivative trade.

    Example: "The lenders include JPM, Citi, and BofA." -> Score 3 -> True (Noise)
    """
    # Use set to count unique banks (avoid double counting "JPM... JPM")
    hits = set(match.group(0).lower() for match in BANK_SCORING_REGEX.finditer(text))
    return len(hits) >= threshold


def build_ir_context_terms() -> Tuple[List[str], List[str], List[str]]:
    context_adjectives = RATE_ADJECTIVES

    risk_glue_rates = [rf"{adj}[- ]rates?" for adj in context_adjectives]

    shared_debt_terms = [
        IR_DEBT_LOOKBEHIND_TERM,
        r"revolving\s+credits?",
        r"term\s+loans?",
        r"subordinated\s+notes?",
        r"commercial\s+papers?",
        r"capital\s+leases?",
        r"mortgages?",
    ]

    interest_financials = r"interest\s+(?:payables?|expenses?|income|payments?|costs?)"

    common_terms = risk_glue_rates + shared_debt_terms + [interest_financials]

    risk_glue = common_terms + [
        r"borrowing\s+costs?",
        r"financing\s+costs?",
        r"yield\s+curves?",
        r"re-?pricing",
        r"(?:floating|fixed|variable)\s+rate\s+debt",
    ] + BENCHMARK_RATES

    strict_terms = [
        rf"{INTEREST}[- ]rate\s+{_RISK_ALTERNATION}",
        r"(?:pay|receive)[- ](?:fixed|variable|floating)",
        r"fed(?:eral)?\s+funds\s+rates?",
        r"forward[- ]starting",
    ] + BENCHMARK_RATES

    soft_terms = common_terms + [
        rf"{_DEBT_TERMS}\s+payables?",
        rf"(?:long|short)[- ]term\s+{_DEBT_TERMS}",
        r"amortization\s+of\s+debt",
        rf"treasury\s+{_DEBT_TERMS}",
        r"credit\s+agreements?",
        r"basis\s+points?",
        r"weighted\s+average\s+interest",
    ] + BANK_ENTITIES

    risk_terms = [
        build_risk_managment_phrase(risk_glue)
    ]

    return strict_terms, soft_terms, risk_terms


def debt_feature_regex() -> re.Pattern:
    # 1. Optional Prefix: "Changes in", "increase in", etc.
    # 0-3 words like "changes in the" or "fluctuations in"
    prefix_gap = r"(?:\b(?:changes?|fluctuations?|increase|decrease|impact)\s+(?:in|to)\s+(?:the\s+)?)?"

    # 2. Mid Gap: "fair value of [the/our] debt"
    mid_gap = r"(?:\s+(?:the|our|total|aggregate))?\s*"

    # setting the rates (reduces false IR caps as instruments)
    verbs = [
        r"set(?:s?|ting)?",
        r"establish(?:es|ing)?",
        r"(?:in|de)creas(?:es?|ed|ing)",
        r"lower(?:s|ed|ing)?",
        r"rais(?:es?|ed|ing)",
        r"limit(?:s|ed|ing)?",
        r"fix(?:es|ed|ing)?",
        r"adjust(?:s|ed|ing)?",
        r"target(?:s|ed|ing)?",
        r"determin(?:e|es|ed|ing)?",
        r"implement(?:s|ed|ing)?",
        r"provid(?:e|es|ed|ing)",
        r"contain(?:s|ed|ing)?",
        r"subject(?:ed|s)?\s+to",
    ]

    VERB = build_alternation(verbs)
    targets = [r"caps?", r"floors?", r"locks?", r"limits?", r"collars?"]
    TARGET = build_alternation(targets)
    rates = build_alternation(RATE_TYPES + ["interest"])
    IR = rf"{rates}(?:[- ]rates?)?"
    GAP = r"(?:\S+\s+){0,2}"
    cap_floor_pattern = (
        rf"{VERB}\s+{GAP}{IR}\s+{GAP}{TARGET}"
        rf"(?:\s+(?:and|or)\s+{GAP}(?:{IR}\s+)?{TARGET})?"
    )

    # --- Embedded Cap/Floor Logic ---
    connectors = [
        r"subject(?:ed|s)?\s+to",
        r"contain(?:s|ed|ing)?",
        r"includ(?:es?|ed|ing)",
        r"have",
        r"has",
        r"had",
        r"with",
        r"bears?\s+interest",
        r"features?",
        r"sets?",
        r"provisions?",
        r"terms?",
    ]
    conn_pat = build_alternation(connectors)

    full_suffix_alt = to_build_alternation(ALL_SUFFIXES + [BASE.OPTION])
    safe_list = set(SUFFIXES)
    safe_suffix_alt = to_build_alternation(safe_list)
    targets = [
        BASE.CAP,
        BASE.FLOOR,
        BASE.LOCK,
        BASE.OPTION,
    ]
    target_alt = to_build_alternation(targets)
    targets_embedded = [
        rf"rate\s+{target_alt}(?!\s+{full_suffix_alt})",
        rf"(?:{target_alt}|rates?)(?!\s+{safe_suffix_alt})",
    ]
    target_pat_embedded = build_alternation(targets_embedded)

    pat_a = rf"\b{_IR_DEBT}\s+(?:\S+\s+){{0,10}}{conn_pat}\s+(?:\S+\s+){{0,3}}{target_pat_embedded}\b"
    percent_pat = r"\d+(?:\.\d+)?\s*(?:%|percent|bps|basis\s+points)"
    pat_b = rf"\b{target_pat_embedded}\s+(?:\S+\s+){{0,3}}{percent_pat}\b"
    noun_indicators = r"(?:features?|provisions?|terms?)"
    pat_c = rf"\b{target_pat_embedded}\s+{noun_indicators}\b"

    # 3. Pattern Construction
    # Matches: "fair value of debt", "change in the fair value of our facility"
    # Also matches: secured debt/facility (no gap)
    patterns = [
        rf"{prefix_gap}fair\s+value\s+of{mid_gap}(?:{_IR_DEBT}|facility)\b",
        rf"secured\s+(?:{_IR_DEBT}|facility)\b",
        cap_floor_pattern,
        pat_a,
        pat_b,
        pat_c,
    ]
    pattern = build_alternation(patterns)
    return re.compile(pattern, re.IGNORECASE)

def rename_cap_floor_regex() -> Tuple[re.Pattern, str]:
    BASES = [BASE.CAP, BASE.FLOOR]
    _CP_FLR_RATE = to_build_alternation(BASES)
    pattern = [
        rf"{_CP_FLR_RATE}[- ]interest(?:[- ]rates?)?",
        rf"{_CP_FLR_RATE}[- ]rates?",
    ]
    return build_regex(pattern), " interest rate"

def debt_expiration_regex() -> re.Pattern:
    # 1. We use a non-greedy gap (?:\s+\S+){0,3}?
    # 2. We ensure the termination verb is checked at every step
    WORD_GAP = r"(?:\s+\S+){0,3}?"

    # We strip the \b from the alternation to allow it to match
    # immediately after the gap
    verbs = build_alternation(ALL_TERM_TERMS)

    pattern = rf"\b(?:{_DEBT_TERMS}|facilit(?:y|ies))(?:,)?{WORD_GAP}\s+{verbs}\b"
    return re.compile(pattern, re.IGNORECASE)


DEBT_TOKEN = " debt "
DEBT_EXP_REGEX = debt_expiration_regex()

IR_STRICT_TERMS, IR_SOFT_TERMS, IR_RISK_TERMS = build_ir_context_terms()
IR_CONTEXT_TERMS = IR_STRICT_TERMS + IR_SOFT_TERMS + IR_RISK_TERMS
IR_CONTEXT_REGEX = build_regex(IR_CONTEXT_TERMS)
IR_STRICT_CONTEXT_REGEX = build_regex(IR_STRICT_TERMS + IR_RISK_TERMS)
IR_RISK_REGEX = build_regex(IR_RISK_TERMS)
EXCLUDE_REGEX_LIBOR_TRANSITION = build_regex(LIBOR_TRANSITION_KEYWORDS)
CAP_FLOOR_REGEX, IR_TOK = rename_cap_floor_regex()

from defs.verb_core import build_strict_do_not_mitigate_regex


IR_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(
    [
        IR_RATE,
        r"yield\s+curves?",
    ]
    + BENCHMARK_RATES
)
DEBT_FT_REGEX = debt_feature_regex()

def run_tests():
    from defs.derivatives_core import (
        MatchLevel,
        run_category_tests,
        run_category_tests_counter,
    )

    test_cases = [
        ("interest rate swap", MatchLevel.STRICT),
        ("interest rate cap agreement", MatchLevel.STRICT),
        ("interest rate agreement", MatchLevel.STRICT),
        ("floating rate cap", MatchLevel.LOOSE),
        ("treasury rate locks", MatchLevel.STRICT),
        ("fixed rate swap", MatchLevel.STRICT),
        ("pay fixed receive floating swap", MatchLevel.STRICT),
        ("interest rate protection", MatchLevel.LOOSE),
        ("interest rate protection agreement", MatchLevel.STRICT),
        ("interest rate contract", MatchLevel.STRICT),
        ("interest rate hedges", MatchLevel.SOFT),
        ("floating rate hedge contract", MatchLevel.STRICT),
        ("interest rate hedging", MatchLevel.SOFT),
        ("Eurodollar futures", MatchLevel.STRICT),
        ("Eurodollar options", MatchLevel.STRICT),
        ("single currency basis swap", MatchLevel.STRICT),
    ]

    print("Interest Rate Derivatives tests:")
    run_category_tests(test_cases, IR_REGEX, IR_SOFT_REGEX, IR_LOOSE_REGEX)

    counter_cases = [
        ("interest rate cap", MatchLevel.STRICT),  # Should NOT be strict
        ("treasury rate floor", MatchLevel.STRICT),
        ("fixed rate agreement", MatchLevel.SOFT),
        ("floating rate arrangement", MatchLevel.SOFT),
        ("forward rate swap", MatchLevel.STRICT),
        ("swap agreement", MatchLevel.STRICT),  # Should NOT match IR (no core)
    ]
    run_category_tests_counter(counter_cases, IR_REGEX, IR_SOFT_REGEX, IR_LOOSE_REGEX)
