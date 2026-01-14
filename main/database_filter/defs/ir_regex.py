import re
from typing import Tuple

from defs.derivatives_core import build_smart_regex, expand_instruments, suffix_alternation
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
    r"(?benchmark|(?<!currency[- ])interest|forward)[- ]rates?",
    r"basis\s+points?",
    r"weighted\s+average\s+interest",
]

IR_CONTEXT = [IR_DEBT_LOOKBEHIND_TERM] + IR_OTHER_TERMS + BENCHMARK_RATES + IR_STRICT_TERMS
IR_CONTEXT_REGEX = build_regex(IR_CONTEXT)
IR_STRICT_CONTEXT_REGEX = build_regex(IR_STRICT_TERMS)
