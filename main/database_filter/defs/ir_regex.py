import re
from typing import Tuple

from defs.derivatives_core import ALL_SUFFIXES, build_smart_regex, expand_instruments, suffix_alternation
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION

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
def build_ir_regex() -> Tuple[re.Pattern, re.Pattern]:
    # --- 1. Helper Definitions ---
    RATE_TYPES = ["fixed", "variable", "floating"]
    # RATES is for descriptive prefixes that combine with 'rate'
    RATES_ADJECTIVES = [
        "treasury",
        "forward",
        "benchmark",
        "interest",
        "prime",
        "fed[- ]funds",
    ] + RATE_TYPES

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
    rate_alternation = build_alternation(RATES_ADJECTIVES, sort_longest_first=True)
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
        ]
        + rate_adjective_phrases
        + brate_adjective_phrases
    )

    specific_phrases = [
        # CRITICAL: This pattern is prioritized for Max Munch
        aggressive_capture_pattern,
        "zero[- ]coupon swaps?",
        "FRA",
        f"treasury locks?(?:[- ]{suffix_alternation})",
        "treasury locks?",
        "overnight index swaps?",
    ]

    # --- 5. Final Build and Compile ---
    strict_pattern = build_smart_regex(
        core_terms,
        expand_instruments(
            unsafe=False, additional_bases=["protection"]
        ),  # IR caps, locks, floors is not included without the word contract, etc
        specific_phrases,
    )
    soft_pattern = build_smart_regex(
        core_terms,
        expand_instruments(
            unsafe=True, additional_bases=["protection"]
        ),  # IR caps, locks, floors
        specific_phrases,
    )
    strict_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)
    soft_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)
    return strict_regex, soft_regex  # return the same thing as a tuple for consistency

IR_REGEX, IR_SOFT_REGEX = build_ir_regex()

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

# 1. INTEREST RATE (Strict)
# Focus: Specific rates, benchmarks, and directional payment terms
# In derivative_regex.py

IR_STRICT_TERMS = [
    rf"(?<!foreign[- ])interest[- ]rate\s+{_RISK_ALTERNATION}",
    rf"(?<!currency[- ])interest[- ]rate\s+{_RISK_ALTERNATION}",
    r"(?:pay|receive)[- ](?:fixed|variable|floating)",
    r"interest\s+payments?",
    r"amortization\s+of\s+debt",
    r"commercial\s+papers?",
    rf"treasury\s+{_DEBT_TERMS}",
    # --- NEW ADDITIONS (The Safe Rates) ---
    # These imply Interest Rate mechanics specifically
    r"(?:floating|variable|fixed|prime|treasury|(?<!currency[- ])interest|(?<!foreign[- ])interest)[- ]rates?",
    r"fed(?:eral)?\s+funds\s+rates?",
    r"credit\s+agreements?",
] + BENCHMARK_RATES
# 2. All Other IR Context Terms (No Lookbehind Required)
IR_OTHER_TERMS = [
    # Debt + Payment Combinations (Strong IR signals)
    rf"{_DEBT_TERMS}\s+payables?",
    r"interest\s+payables?",
    rf"(?:long|short)[- ]term\s+{_DEBT_TERMS}",
    r"credit\s+facilit(?:y|ies)",
    r"revolving\s+credits?",
    r"term\s+loans?",
    r"subordinated\s+notes?",
    r"capital\s+leases?",
    r"mortgages?",
    # Rate Types & Benchmarks
    r"(?:benchmark|(?<!currency[- ])interest|forward)[- ]rates?",
    r"basis\s+points?",
    r"weighted\s+average\s+interest",
]


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
        r"subject\s+to",
        r"contain(?:s|ed|ing)?",
        r"include(?:s|d|ing)?",
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
    # ALL_SUFFIXES includes: agreements, contracts, commitments, instruments, arrangements, options

    # A. Full Suffix List (For Long-Form Instruments)
    # "Interest Rate Cap Agreement" -> SAFE (Excluded from match)
    full_suffix_alt = build_alternation(ALL_SUFFIXES)

    # B. Safe Suffix List (For Short-Form Instruments)
    # Remove "agreement" so "Cap Agreement" is caught and checked for debt context.
    # We explicitly keep strong terms like "Contract" and "Option".
    safe_list = set(ALL_SUFFIXES) - {
        "agreements?",
        "arrangements?",
    }  # Arrangements also vague
    safe_suffix_alt = build_alternation(list(safe_list))

    # 3. Targets (Caps/Floors only)
    targets = [
        # Long Form: Trust ALL suffixes (Agreements included)
        rf"interest\s+rate\s+(?:caps?|floors?|collars?)(?!\s+{full_suffix_alt})",
        # Short Form: Trust only STRONG suffixes (Contracts/Options)
        # "Cap Agreement" or "Cap Arrangement" will MATCH here (and risk discard)
        rf"caps?(?!\s+{safe_suffix_alt})",
        rf"floors?(?!\s+{safe_suffix_alt})",
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


# Compile
IR_CONTEXT = (
    [IR_DEBT_LOOKBEHIND_TERM] + IR_OTHER_TERMS + BENCHMARK_RATES + IR_STRICT_TERMS + BANK_ENTITIES
)
IR_CONTEXT_REGEX = build_regex(IR_CONTEXT)
IR_STRICT_CONTEXT_REGEX = build_regex(IR_STRICT_TERMS)
EXCLUDE_REGEX_LIBOR_TRANSITION = build_regex(LIBOR_TRANSITION_KEYWORDS)
NON_DER_CAP_FLOOR_REGEX = build_embedded_cap_floor_regex()
