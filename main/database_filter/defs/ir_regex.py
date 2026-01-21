import re
from typing import Tuple, List

from defs.derivatives_core import ALL_SUFFIXES, UNAMBIGUOUS_SUFFIXES, MatchLevel, build_smart_regex, expand_instruments, run_category_tests, run_category_tests_counter, suffix_alternation
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION, ALL_TERM_TERMS, build_risk_managment_phrase
from defs.verb_core import build_strict_do_not_mitigate_regex

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
]

RATE_TYPES = ["fixed", "variable", "floating"]

RATE_ADJECTIVES = [
    "treasury",
    "benchmark",
    "prime",
    r"(?<!foreign[- ])(?<!currency[- ])(?<!exchange[- ])(?:interest|forward)",
    r"fed(?:eral)?[- ]funds",
] + RATE_TYPES

def build_ir_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    # --- 1. Helper Definitions ---

    def build_pay_receive_structure() -> str:
        """Constructs the core pay/receive structure pattern."""
        rate_alternation = build_alternation(RATE_TYPES, sort_longest_first=False)
        FLEXIBLE_SEPARATOR = r"(?:\s*[,/;&]?\s*|\s+(?:and|or)\s+|\s*[- ]+)\s*"

        return (
            r"pay[- ]"
            rf"(?:{rate_alternation})"
            rf"{FLEXIBLE_SEPARATOR}"
            r"receive[- ]"
            rf"(?:{rate_alternation})"
        )

    # --- 2. Build Instrument Alternations ---
    pay_receive_pattern_string = build_pay_receive_structure()

    # --- 4. Build Core Terms and Specific Phrases ---
    ir_regex_adjectives = RATE_ADJECTIVES
    rate_alternation = build_alternation(ir_regex_adjectives, sort_longest_first=True)
    rate_adjective_phrases = [rf"{rate_alternation}[- ]rate"]

    # This pattern enforces the sequence: [P/R] + [Optional Adjectives] + [Mandatory Instrument Base]
    aggressive_capture_pattern = (
        rf"(?:{pay_receive_pattern_string})"  # 1. Start with 'pay fixed, receive fixed'
        r"(?:"  # Start of Optional Adjective Group
        r"\s+"  # Mandatory space
        rf"(?:{rate_adjective_phrases[0]})"  # 2. Optional: 'interest rate'
        r")?"
        r"(?:\s+"  # Mandatory space before the base instrument
        rf"(?:{expand_instruments(unsafe=True)})"  # 3. Mandatory: 'derivatives contracts' or 'swap'
        r")"  # This group is mandatory for this specific phrase match
    )

    benchmark_alternation = build_alternation(BENCHMARK_RATES, sort_longest_first=True)
    brate_adjective_phrases = [
        rf"(?:{benchmark_alternation})(?:[- ](?:related|linked|based))?"
    ]
    core_terms = (
        [
            "single[- ]currency",
            "interest(?:[ -]rate)?[- ]exchange"
        ]
        + rate_adjective_phrases
        + brate_adjective_phrases
    )

    specific_phrases = [
        # CRITICAL: This pattern is prioritized for Max Munch
        aggressive_capture_pattern,
        "zero[- ]coupon swaps?",
        f"treasury locks?(?:[- ]{suffix_alternation})",
        "treasury locks",
        "overnight index swaps?",
        r"forward\s+rate\s+agreements?",
    ]

    # --- 5. Final Build and Compile ---
    strict_pattern = build_smart_regex(
        core_terms,
        expand_instruments(
            unsafe=False, 
            additional_bases=["protection"], 
            additional_standalone_suffixes=["contracts?", "collars"]
        ),  # IR caps, locks, floors is not included without the word contract, etc
        specific_phrases,
    )
    soft_pattern = build_smart_regex(
        core_terms,
        expand_instruments(
            unsafe=True,
            exclude_standalone_suffixes=True,
            additional_bases=["protection"],
            additional_standalone_suffixes=["contracts?", "caps?", "floors", "locks"], # Cap can be singular, rest are plural
        ),  # IR caps, locks, floors
        specific_phrases,
    )
    loose_pattern = build_smart_regex(
        core_terms,
        expand_instruments(
            unsafe=True,
            exclude_standalone_suffixes=False,
            additional_bases=["protection"],
        ),
        specific_phrases,
    )
    strict_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)
    soft_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)
    loose_regex = re.compile(r"\b" + loose_pattern + r"\b", re.IGNORECASE)
    return strict_regex, soft_regex, loose_regex

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
    rf"{_DEBT_TERMS}"  # The actual match
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
    r"transition\s+(?:from|away\s+from)\s+LIBOR",
    r"discontinu(?:ance|ation|ed)\s+of\s+LIBOR",
    r"cessation\s+of\s+LIBOR",
    r"phase[- ]?out\s+of\s+LIBOR",
    r"replacement\s+of\s+LIBOR",
    r"migration\s+from\s+LIBOR",
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


def build_embedded_cap_floor_regex() -> re.Pattern:
    # 1. Connectors (The "Filler")
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

    # 2. Build Suffix Logic
    full_suffix_alt = build_alternation(UNAMBIGUOUS_SUFFIXES + ["options?"])
    # B. Safe Suffix List (For Short-Form Instruments)
    # Remove "agreement" so "Cap Agreement" is caught and checked for debt context.
    # We explicitly keep strong terms like "Contract" and "Option".
    safe_list = set(UNAMBIGUOUS_SUFFIXES) # Arrangements also vague
    safe_suffix_alt = build_alternation(list(safe_list))

    # 3. Targets (Caps/Floors only)
    targets = [
        rf"rate\s+(?:caps?|floors?)(?!\s+{full_suffix_alt})" # Skips interest rate cap contract, rate floor option
        # "Cap Agreement" or "rate Arrangement" will MATCH here (and risk discard)
        rf"(?:caps?|floors?|rates?)(?!\s+{safe_suffix_alt})",
    ]
    target_pat = build_alternation(targets)

    # 4. Pattern A: Debt... [gap] ... Cap/Floor
    pat_a = rf"\b{_DEBT_TERMS}\s+(?:\S+\s+){{0,10}}{conn_pat}\s+(?:\S+\s+){{0,3}}{target_pat}\b"

    # 5. Pattern B: Cap/Floor... [gap] ... Percentage
    percent_pat = r"\d+(?:\.\d+)?\s*(?:%|percent|bps|basis\s+points)"
    pat_b = rf"\b{target_pat}\s+(?:\S+\s+){{0,3}}{percent_pat}\b"

    # 6. Pattern C: Explicit "Feature" Nouns
    noun_indicators = r"(?:features?|provisions?|terms?)"
    pat_c = rf"\b{target_pat}\s+{noun_indicators}\b"

    return re.compile(rf"(?:{pat_a}|{pat_b}|{pat_c})", re.IGNORECASE)


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
        rf"(?<!foreign[- ])interest[- ]rate\s+{_RISK_ALTERNATION}",
        rf"(?<!currency[- ])interest[- ]rate\s+{_RISK_ALTERNATION}",
        r"(?:pay|receive)[- ](?:fixed|variable|floating)",
        r"fed(?:eral)?\s+funds\s+rates?",
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
    # 3. Pattern Construction
    # Matches: "fair value of debt", "change in the fair value of our facility"
    # Also matches: secured debt/facility (no gap)
    patterns = [
        rf"{prefix_gap}fair\s+value\s+of{mid_gap}(?:{_DEBT_TERMS}|facilit(?:y|ies))\b",
        rf"secured\s+(?:{_DEBT_TERMS}|facilit(?:y|ies))\b",
        cap_floor_pattern,
    ]
    pattern = build_alternation(patterns)
    return re.compile(pattern, re.IGNORECASE)


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
NON_DER_CAP_FLOOR_REGEX = build_embedded_cap_floor_regex()
IR_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(
    [
        r"(?<!foreign[- ])(?<!currency[- ])(?<!exchange[- ])interest\s+rates?",
        r"yield\s+curves?",
    ] + BENCHMARK_RATES
)
DEBT_FT_REGEX = debt_feature_regex()

def run_tests():
    test_cases = [
        ("interest rate swap", MatchLevel.STRICT),
        ("interest rate swap agreement", MatchLevel.STRICT),
        ("interest rate agreement", MatchLevel.LOOSE),
        ("swap agreement", MatchLevel.NONE),  # Should NOT match IR (no core)
        ("floating rate cap", MatchLevel.SOFT),
        ("treasury rate locks", MatchLevel.SOFT),
        ("fixed rate swap", MatchLevel.STRICT),
        ("pay fixed receive floating swap", MatchLevel.STRICT),
        (
            "interest rate protection",
            MatchLevel.NONE,
        ),  # Protection is not a standalone base in strict/soft
        ("interest rate protection agreement", MatchLevel.STRICT),
        ("interest rate contract", MatchLevel.STRICT),
        ("interest rate hedges", MatchLevel.LOOSE),
        ("floating rate hedge contract", MatchLevel.STRICT),
        ("interest rate hedging", MatchLevel.LOOSE),
    ]
    run_category_tests(test_cases, IR_REGEX, IR_SOFT_REGEX, IR_LOOSE_REGEX)

    counter_cases = [
        ("interest rate cap", MatchLevel.STRICT),  # Should NOT be strict
        ("treasury rate floor", MatchLevel.SOFT),
        ("interest rate protection", MatchLevel.LOOSE),
        ("fixed rate agreement", MatchLevel.SOFT),
        ("floating rate arrangement", MatchLevel.SOFT),
    ]
    run_category_tests_counter(counter_cases, IR_REGEX, IR_SOFT_REGEX, IR_LOOSE_REGEX)
