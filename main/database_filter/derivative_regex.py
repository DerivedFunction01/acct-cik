from dataclasses import dataclass
import re
from typing import List, Tuple


def build_alternation(items: List[str], sort_longest_first: bool = True) -> str:
    """
    Build regex alternation pattern, optionally sorting by length (longest first).

    Critical for masking and safe span detection: ensures longer, more specific
    patterns like "interest rate swap" match before shorter ones like "swap".

    Args:
        items: List of regex patterns/terms to combine
        sort_longest_first: If True, sort by (word_count DESC, char_length DESC)

    Returns:
        Alternation pattern string ready for re.compile()

    Example:
        >>> build_alternation(["swap", "interest rate swap", "swap agreement"])
        # Returns: '(?:interest rate swap|swap agreement|swap)'  ✓ Correct order
        # NOT: '(?:swap|interest rate swap|swap agreement)'  ✗ Wrong order
    """
    if not items:
        return ""
    if len(items) == 1:
        return items[0]

    if sort_longest_first:
        # Remove duplicates while preserving order (for tiebreaker)
        unique_items = []
        seen = set()
        for item in items:
            if item not in seen:
                unique_items.append(item)
                seen.add(item)

        # Sort by: (word_count DESC, then char_length DESC)
        unique_items = sorted(
            unique_items,
            key=lambda x: (
                -len(x.split()),  # Primary: word count (descending)
                -len(x),  # Secondary: character length (descending)
            ),
        )
        items = unique_items

    return f'(?:{"|".join(items)})'


# =============================================================================
# SHARED COMPONENTS (moved from filter_database.py)
# =============================================================================
# In derivative_regex.py (add to your existing patterns)
# Comparison verbs phrases
comparison_phrases = [
    "compared to",
    "versus",
    "as against",
    "in comparison with",
    "whereas",
    "compared with",
    "relative to",
    "in contrast to",
    "as opposed to",
    "vis-à-vis",
    "when compared with",
]
# State Descriptors (New)
ACTIVE_STATE_DESCRIPTORS = ["outstanding", "active", "remaining", "open"]

ACTIVE_STATE_PATTERN = build_alternation(ACTIVE_STATE_DESCRIPTORS)

# STRONG: Unambiguous indicators of active usage or transaction
STRONG_ACTION_VERBS = [
    # Transactional (The "Smoking Gun")
    r"enter(?:s|ed|ing)?\s+into",
    r"engag(?:e|es|ed|ing)\s+in",
    r"transact(?:s|ed|ing)?",
    r"execut(?:e|es|ed|ing)",
    
    # Direct Usage
    r"use(?:s|d|ing)?",
    r"utiliz(?:e|es|ed|ing)",
    r"employ(?:s|ed|ing)?",
    
    # Possession / Holding
    r"hold(?:s|ing)?", 
    r"held",
    r"maintain(?:s|ed|ing)?",
    r"possess(?:e|es|ed|ing)?",
    
    # Active Management
    r"hedg(?:e|es|ed|ing)", 
    r"manag(?:e|es|ed|ing)",
    r"mitigat(?:e|es|ed|ing)",
    r"offset(?:s|ting)?",
]

# WEAK / PASSIVE: Legal or Accounting states that *imply* existence
# We include these because "carrying at fair value" implies you have it.
PASSIVE_STATE_VERBS = [
    r"appl(?:y|ies|ied|ying)",   # "We apply hedge accounting"
    r"carr(?:y|ies|ied|ying)",   # "Carries at fair value"
    r"designat(?:e|es|ed|ing)",  # "Designated as a hedge"
    r"be\s+a\s+party\s+to",      # "Is a party to interest rate swaps"
    rf"remained?\s+{ACTIVE_STATE_PATTERN}", # "remained active/open/outstanding"
]

SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<=[.!?])"  # Positive lookbehind for punctuation
    # 1. Protect Initials (e.g., "John H. Smith") -> Capital + Dot
    r"(?<!\b[A-Z]\.)"
    # 2. Protect 2-letter Acronyms (e.g., "U.S.", "U.K.", "N.Y.") -> Cap.Cap.
    r"(?<!\b[A-Z]\.[A-Z]\.)"
    # 3. Protect 3-letter and 4-letter Acronyms (e.g., "U.S.A.", "S.E.C.", "F.A.S.B.") -> Cap.Cap.Cap.Cap. 4-letter acronyms are rare
    r"(?<!\b[A-Z]\.[A-Z]\.[A-Z]\.)"
    r"(?<!\b[A-Z]\.[A-Z]\.[A-Z]\.[A-Z]\.)"
    # 4. Protect common Title/Corp abbreviations (Mixed Case)
    r"(?<!\bInc\.)"
    r"(?<!\bCorp\.)"
    r"(?<!\bLtd\.)"
    r"(?<!\bLlc\.)"
    r"(?<!\bNo\.)"  # "Note No. 5"
    r"(?<!\bNos\.)"  # Plural numbers
    r"(?<!\bVol\.)"  # Volume
    r"(?<!\bvs\.)"  # versus
    r"(?<!\bp\.)"  # p. (page) - FIXED (Separated)
    r"(?<!\bpp\.)"  # pp. (pages) - FIXED (Separated)
    r"(?<!\b[Ee]tc\.)"  # etc.
    r"\s+(?=[A-Z])"  # Must be followed by Whitespace + Uppercase
    r"|"
    r"(?<=[a-z])(?=[A-Z])"  # camelCase boundaries (unchanged)
)

COMMON_COMMODITIES = [
    # 🌾 Agriculture & Food
    "agricultural",
    "cocoa",
    "coffee",
    "corn",
    "cotton",
    "dairy",
    "grain",
    "livestock",
    "soybean",
    "sugar",
    "wool",
    # ⛽ Energy & Fuels
    "crude oil",
    "diesel fuel",
    "electricity",
    "energy",
    "ethanol",
    "fuel",
    "gas",
    "gasoline",
    "natural gas",
    "biodiesel",
    "biomass",
    # 🧪 Chemicals & Fertilizers
    "chemical",
    "fertilizer",
    "nitrogen",
    "petrochemical",
    "phosphate",
    "plastic",
    "polymer",
    "potash",
    "resin",
    "rubber",
    "soda ash",
    "sulfur",
    # 🪨 Minerals, Metals & Ores
    "aluminum",
    "base metals?",
    "copper",
    "iron",
    "gold",
    "silver",
    "metal",
    "ore",
    "precious metals?",
    "steel",
    "titanium",
    "uranium",
    # 🏗️ Construction Materials
    "asphalt",
    "bitumen",
    "cement",
    "concrete",
    "gravel",
    "limestone",
    "sand",
    # 🌲 Forestry & Wood Products
    "hardwood lumber",
    "log",
    "lumber",
    "plywood",
    "softwood lumber",
    "timber",
    "wood",
    "wood chip",
    "wood pellet",
    "paper",
    "pulp",
    # 🧩 General / Raw Inputs
    "feedstock",
    "raw material",
    "salt",
    "textile",
]


# Minimum sentence length to consider (we use swaps is 12 chars and rarely ever occurs)
MIN_SENTENCE_LENGTH = 15
MAX_SENTENCE_LENGTH = 800 # A very long sentence is probably a table that became a sentence


# Interest Rate context clues
IR_CONTEXT_TERMS = [
    # 1. Debt Instruments (The Underlying)
    r"debt",
    r"loan",
    r"borrow(?:ing|ed)?",
    r"bond",
    r"note",
    r"debenture",
    r"credit\s+facilit(?:y|ies)",
    r"revolving\s+credit",
    r"term\s+loan",
    r"senior\s+notes?",
    r"subordinated\s+notes?",
    r"commercial\s+paper",
    r"capital\s+lease",
    r"mortgages?",
    # 2. Rate Types & Benchmarks
    r"floating[- ]rate",
    r"variable[- ]rate",
    r"fixed[- ]rate",
    r"benchmark[-]rate",
    r"interest[- ]rate",
    r"treasury[- ]rate",
    r"forward[- ]rate",
    r"LIBOR",
    r"SOFR",
    r"EURIBOR",
    r"SONIA",
    r"TONAR",  # Tokyo Overnight
    r"prime\s+rate",
    r"fed(?:eral)?\s+funds\s+rate",
    r"yield\s+curve",
    # 3. Mechanics (High Precision)
    r"pay[- ]fixed",
    r"receive[- ]fixed",
    r"pay[- ]variable",
    r"receive[- ]variable",
    r"pay[- ]floating",
    r"receive[- ]floating",
    r"interest\s+expense",
    r"interest\s+income",
    r"interest\s+payment",
    r"basis\s+point",
    r"repric(?:ing|ed)",
    r"weighted\s+average\s+interest"
]


@dataclass
class Currency:
    code: str
    full_name: str
    symbol: str
    adjective: str
    location: str
    symbol_first: bool = True  # Default to symbol before the number (e.g., $100)


major_currencies = [
    Currency("USD", "US Dollar", "$", "U.S.", "United States"),
    Currency("EUR", "Euro", "€", "European", "Europe"),
    Currency("GBP", "British Pound", "£", "British", "U.K."),
    Currency("JPY", "Japanese Yen", "¥", "Japanese", "Japan"),
    Currency("CAD", "Canadian Dollar", "C$", "Canadian", "Canada"),
    Currency("AUD", "Australian Dollar", "A$", "Australian", "Australia"),
    Currency("CHF", "Swiss Franc", "CHF", "Swiss", "Switzerland"),
    Currency("CNY", "Chinese Yuan", "¥", "Chinese", "China"),
]

european_currencies = [
    Currency("NOK", "Norwegian Krone", "kr", "Norwegian", "Norway", symbol_first=False),
    Currency("SEK", "Swedish Krona", "kr", "Swedish", "Sweden", symbol_first=False),
    Currency("DKK", "Danish Krone", "kr", "Danish", "Denmark", symbol_first=False),
    Currency("PLN", "Polish Zloty", "zł", "Polish", "Poland", symbol_first=False),
    Currency(
        "HUF", "Hungarian Forint", "Ft", "Hungarian", "Hungary", symbol_first=False
    ),
    Currency(
        "CZK", "Czech Koruna", "Kč", "Czech", "Czech Republic", symbol_first=False
    ),
    Currency("TRY", "Turkish Lira", "₺", "Turkish", "Turkey", symbol_first=False),
    Currency("RUB", "Russian Ruble", "₽", "Russian", "Russia", symbol_first=False),
    Currency("BGN", "Bulgarian Lev", "лв", "Bulgarian", "Bulgaria", symbol_first=False),
    Currency("RON", "Romanian Leu", "lei", "Romanian", "Romania", symbol_first=False),
]

asian_currencies = [
    Currency("INR", "Indian Rupee", "₹", "Indian", "India"),
    Currency("KRW", "South Korean Won", "₩", "South Korean", "South Korea"),
    Currency("SGD", "Singapore Dollar", "S$", "Singaporean", "Singapore"),
    Currency("HKD", "Hong Kong Dollar", "HK$", "Hong Kong", "Hong Kong"),
    Currency("THB", "Thai Baht", "฿", "Thai", "Thailand", symbol_first=False),
    Currency("MYR", "Malaysian Ringgit", "RM", "Malaysian", "Malaysia"),
]

americas_currencies = [
    Currency("MXN", "Mexican Peso", "Mex$", "Mexican", "Mexico"),
    Currency("BRL", "Brazilian Real", "R$", "Brazilian", "Brazil", symbol_first=False),
    Currency("ARS", "Argentine Peso", "ARS$", "Argentine", "Argentina"),
    Currency("CLP", "Chilean Peso", "CLP$", "Chilean", "Chile"),
    Currency("COP", "Colombian Peso", "COL$", "Colombian", "Colombia"),
]

other_currencies = [
    Currency(
        "NZD", "New Zealand Dollar", "NZ$", "New Zealand", "Oceania", symbol_first=True
    ),
    Currency(
        "ZAR",
        "South African Rand",
        "R",
        "South African",
        "south Africa",
        symbol_first=True,
    ),
    Currency(
        "AED",
        "UAE Dirham",
        "د.إ",
        "Emirati",
        "United Arab Emirates",
        symbol_first=False,
    ),
    Currency("SAR", "Saudi Riyal", "ر.س", "Saudi", "Saudi Arabia", symbol_first=False),
]


all_currencies = (
    major_currencies
    + european_currencies
    + asian_currencies
    + americas_currencies
    + other_currencies
)

def build_currency_patterns() -> List[str]:
    """
    Generates regex patterns derived specifically from the Currency class objects.
    Includes codes, adjectives, locations, and specific denominating phrases.
    """
    terms = []
    for currency in all_currencies:
        # Basic terms
        terms.append(currency.code)
        terms.append(re.escape(currency.adjective))
        terms.append(re.escape(currency.location))

        # Currency name patterns
        # "U.S. Dollar", "Euro", "Japanese Yen"
        terms.append(re.escape(currency.full_name))

        # Adjective + common words
        adj_esc = re.escape(currency.adjective)
        terms.extend(
            [
                adj_esc + r"\s+(?:operations?|subsidiaries|entities)",
                adj_esc + r"\s+(?:revenue|sales|income|earnings)",
                adj_esc + r"\s+(?:assets?|liabilit(?:y|ies))",
                adj_esc + r"\s+(?:market|economy|business)",
                adj_esc + r"\s+(?:exposure|risk)",
            ]
        )

        # Code + patterns
        code = currency.code
        terms.extend(
            [
                code + r"[- ]denominated",
                code + r"[/]" + r"[A-Z]{3}",  # USD/EUR, GBP/JPY
                r"[A-Z]{3}" + r"[/]" + code,  # EUR/USD, JPY/GBP
            ]
        )
    return terms

def build_currency_iso_pattern() -> str:
    """
    Returns a regex alternation of all ISO 4217 currency codes.
    Sorted by length descending to prevent partial matches (e.g., 'NOK' before 'OK').
    """
    codes = {c.code for c in all_currencies if c.code}
    sorted_codes = sorted(codes, key=len, reverse=True)
    escaped = [re.escape(code) for code in sorted_codes]
    return build_alternation(escaped)


def build_currency_name_pattern() -> str:
    """
    FX-optimized currency fragment generator.
    """
    patterns = []
    unsafe_units = {"dollar", "pound", "yen", "won", "real"}
    codes = [c.code for c in all_currencies]

    # -----------------------------------
    # 1. ISO pairs (highest priority - longest)
    # -----------------------------------
    iso_codes = build_currency_iso_pattern()
    pair_string = rf"{iso_codes}\/{iso_codes}"
    patterns.append(pair_string)

    # -----------------------------------
    # 2. Code-denominated
    # -----------------------------------
    patterns.extend([c + r"-denominated" for c in codes])

    # -----------------------------------
    # 3. Standalone codes
    # -----------------------------------
    patterns.extend(codes)

    # -----------------------------------
    # 4. Adjective + unit pairs
    # -----------------------------------
    for curr in all_currencies:
        full = curr.full_name.strip()
        words = full.split()
        adjective = curr.adjective
        unit = words[-1]

        if adjective and unit:
            patterns.append(f"{adjective} {unit}")

        if unit.lower() not in unsafe_units:
            patterns.append(unit)

        if adjective == "U.S.":
            patterns.extend(
                [
                    r"U\.?S\.?\s+" + unit,
                    r"United\s+States\s+" + unit,
                ]
            )

    # Let build_alternation handle sorting (Max Munch)
    return build_alternation(patterns, sort_longest_first=True)


def build_currency_symbol_pattern() -> str:
    """
    Generates a comprehensive regex OR-string for all currency symbols and ISO codes.
    Used for quantitative analysis to detect amounts like "$100", "100 USD", "€50".
    Sorts by length descending to ensure multi-char symbols (e.g. 'US$') match before single ones ('$').
    """
    symbols = set()
    codes = set()

    for currency in all_currencies:
        if currency.symbol:
            symbols.add(re.escape(currency.symbol))
        if currency.code:
            codes.add(re.escape(currency.code))

    # Combine and sort by length desc (critical for regex precedence)
    all_identifiers = sorted(symbols | codes, key=len, reverse=True)

    return build_alternation(all_identifiers)


def build_fx_context_terms_advanced() -> List[str]:
    """Generate comprehensive FX context terms combining currency-specific and generic patterns."""

    # 1. Get patterns dynamically generated from Currency objects
    currency_specific_terms = build_currency_patterns()

    # 2. Define static generic FX terms
    generic_fx_terms = [
        r"remeasurement",
        r"translation",  # Be careful, "translation of documents" exists, but usually accounting
        r"foreign\s+(?:currency|exchange|operations|subsidiaries|sales|revenue)",
        # 1. Operations & Accounting
        r"functional\s+currency",
        r"reporting\s+currency",
        r"local\s+currency",
        r"foreign\s+currency",
        r"remeasurement",
        r"translation\s+adjustments?",
        r"exchange\s+rate\s+fluctuations?",
        r"currency\s+exchange\s+rates?",
        r"currency\s+fluctuations?",
        # 2. Transactional Context
        r"cross[- ]border",
        r"repatriation",
        r"intercompany",  # Strong signal for FX swaps
        r"denominated\s+in",
        # 3. Specific FX Instruments Keywords
        r"spot\s+rate",
        r"forward\s+points?",
        r"non[- ]deliverable",
    ]

    return currency_specific_terms + generic_fx_terms

CURRENCY_SYMBOL_PATTERN = build_currency_symbol_pattern()
# Generic hedging context (required for generic matches)
HEDGING_CONTEXT_TERMS = [
    r"hedge(?:s|d|ing)?",
    r"mitigat(?:e|es|ed|ing)",
    r"protect(?:s|ed|ing)?",
    r"manage(?:s|d|ing)?",
    r"exposure",
    r"risk\s+management",
    r"economic\s+risk",
    r"fair\s+value\s+hedge",
    r"cash\s+flow\s+hedge",
    r"net\s+investment\s+hedge",
    r"designated\s+as\s+(?:a\s+)?hedge",
    r"hedge\s+effectiveness",
    r"hedge\s+accounting",
]
CP_CONTEXT_TERMS = [
    # Physical quantity units
    "barrels", "bbl", "bbl/d",
    "btu", "gj", "mmbtu", "mmbtu/h", "mwh",
    "bushels", "cwt", "hundredweights", "pecks",
    "ounces", "pounds", "tons", "tonne", "long tons", "short tons",
     "joules", "gigajoules"
] + COMMON_COMMODITIES + ["commodity"]

EQ_CONTEXT_TERMS = [
    r"stock\s+price",
    r"share\s+price",
    r"equity\s+(?:award|grant|compensation)",
    r"stock\s+market",
    r"equity\s+security",
    r"market\s+index",
    r"S&P\s+500",
    r"Nasdaq",
    r"Dow\s+Jones",
    r"dividend\s+yield",
    r"warrants"
]

# ... (Rest of file) ...
# Build compiled regex patterns
IR_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(IR_CONTEXT_TERMS) + r"\b", re.IGNORECASE
)
FX_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(build_fx_context_terms_advanced()) + r"\b", re.IGNORECASE
)
CP_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(CP_CONTEXT_TERMS) + r"\b", re.IGNORECASE
)
EQ_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(EQ_CONTEXT_TERMS) + r"\b", re.IGNORECASE
)
HEDGING_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(HEDGING_CONTEXT_TERMS) + r"\b", re.IGNORECASE
)


# Map categories to their context patterns
CATEGORY_CONTEXT_MAP = {
    "ir": IR_CONTEXT_REGEX,
    "fx": FX_CONTEXT_REGEX,
    "cp": CP_CONTEXT_REGEX,
    "eq": EQ_CONTEXT_REGEX,
    "gen": HEDGING_CONTEXT_REGEX,
}


# =============================================================================
# REGEX BUILDERS (moved)
# =============================================================================

SPECIAL_BASE =  [   
    "call options?",
    "put options?",
    "basis swaps?",
    "total[- ]return swaps?"
]
UNAMBIGUOUS_BASE_TYPES = [
    "swaps?",
    "forwards?",
    "caps?",
    "floors?",
    "collars?",
    "derivatives?",
    "swaptions?",
    "hedges",  # plural form
    "locks",  # plural form
    "futures",  # plural form
 
] + SPECIAL_BASE

AMBIGUOUS_BASE_TYPES = [
    "futures?",
    "options?",
    "hedging",
    "locks?",
    "hedges?",
]

ALL_BASE_TYPES = UNAMBIGUOUS_BASE_TYPES + AMBIGUOUS_BASE_TYPES
HIGH_PRECISION_SUFFIXES = re.compile(r"\b" + build_alternation(UNAMBIGUOUS_BASE_TYPES) + r"\b", re.IGNORECASE)
ALL_SUFFIXES = [
    "agreements?",
    "contracts?",
    "instruments?",
    "arrangements?",
    "options?",
]
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
        rf"(?:{core_pattern})"           # e.g., "interest rate"
        r"[- ]"                          # MANDATORY separator (space or hyphen)
        rf"(?:{context_terms})"          # MANDATORY: base or (base + suffix)
    )

    # Specific phrases like "zero coupon swaps"
    if not specific_phrases:
        return pattern1

    pattern2 = build_alternation(specific_phrases, sort_longest_first=True)

    # Return sorted so longest specific phrases come first
    # E.g., "interest rate swap agreement" before "interest rate swap"
    return build_alternation([pattern2, pattern1], True)


# --- Central Alternations for Instrument Components (Max Munch Sorting Applied) ---
base_alternation = build_alternation(ALL_BASE_TYPES, True)
suffix_alternation = build_alternation(ALL_SUFFIXES, True)
standalone_alternation = build_alternation(ALL_SUFFIXES + UNAMBIGUOUS_BASE_TYPES, True)
unsafe_standalone_alternation = build_alternation(ALL_SUFFIXES + ALL_BASE_TYPES, True)
# ----------------------------------------------------------------------------------

def expand_instruments(unsafe: bool = True) -> str:
    """
    Creates an optimized, single alternation pattern that captures:
    1. Base + Suffix (e.g., swaps-agreement)
    2. OR Standalone base/suffix (e.g., swaps, agreements)

    This pattern enforces Maximum Munch: Base + Suffix is prioritized.

    Args:
        unsafe: If True, includes ambiguous bases (e.g., generic options, futures).
    """

    # 1. Base + Suffix Combination (Highest priority)
    combined_pattern = rf"(?:{base_alternation}[- ]{suffix_alternation})"

    # 2. Standalone Term (Lower priority)
    standalone_pattern = (
        unsafe_standalone_alternation if unsafe else standalone_alternation
    )
    
    # If build_alternation supports it, sort these alternatives by length
    # Otherwise, manually construct with longest first
    return rf"{combined_pattern}|{standalone_pattern}"


def build_ir_regex() -> re.Pattern:
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

    BENCHMARK_RATES = [
        "SOFR", "SONIA", "LIBOR", "EURIBOR",
        "ESTR", "EONIA", "TONAR", "BBSW",
        "CIBOR", "STIBOR", "HIBOR", "TIBOR",
        "PRIBOR", "MOSPRIME"
    ]

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
        rf"(?:{expand_instruments(unsafe=False)})"  # 3. Mandatory: 'derivatives contracts' or 'swap'
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
        "credit default swaps?",
        "overnight index swaps?",
    ]

    # --- 5. Final Build and Compile ---
    pattern = build_smart_regex(
        core_terms,
        expand_instruments(unsafe=False),
        specific_phrases,
    )
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_fx_dynamic_pattern() -> str:
    """
    Dynamically build comprehensive FX patterns with optional positions.

    This generates a single alternation pattern that covers almost all descriptive
    FX prefix combinations, allowing the external build_alternation function
    to sort them by length (Max Munch) automatically.
    """
    # Note: These components are simple alternations (no Max Munch needed here)
    word1 = build_alternation([r"forward", r"foreign"], sort_longest_first=True)
    compound = build_alternation(
        [r"cross[- ]currency", r"multi[- ]currency"], sort_longest_first=True
    )
    word2_alt = build_alternation([r"currency", r"exchange"], sort_longest_first=True)
    word3 = r"rate"

    # List all necessary descriptive fragments/combinations
    patterns = [
        # Longest and most specific combinations
        rf"(?:{word1})[- ](?:{word1})[- ](?:{compound})[- ](?:{word2_alt})[- ]{word3}",
        # Shorter, common combinations
        rf"(?:{word1})[- ](?:{word2_alt})[- ]{word3}",
        rf"(?:{compound})[- ](?:{word2_alt})[- ]{word3}",
        rf"(?:{word1})[- ](?:{word2_alt})",
        rf"(?:{compound})[- ](?:{word2_alt})",
        # Two-word descriptive terms
        rf"(?:{word1})[- ]{word3}",
        rf"(?:{word1})[- ](?:{word2_alt})",
        rf"(?:{compound})",
        # Single-word descriptive terms (low priority, included for completeness)
        compound,
        r"FX",
        r"forex",
        r"currency",
    ]

    # CRITICAL: We let build_alternation sort this entire list by length/word count
    # to enforce Max Munch, ensuring "forward foreign currency" matches before "forward".
    return build_alternation(patterns, sort_longest_first=True)


def build_fx_regex() -> re.Pattern:
    # --- 1. Helper Definitions ---
    currency_name_alternation = build_currency_name_pattern()
    fx_dynamic_pattern = build_fx_dynamic_pattern()

    # --- 2. Build Core Terms (Prefixes) ---
    core_terms = [
        rf"(?:{fx_dynamic_pattern})",  # Optimized FX prefix combinations
        rf"(?:{currency_name_alternation}[- ](?:denominated|linked|related|based))",  # Optimized currency names (USD, JPY, etc.)
        rf"(?:{currency_name_alternation})",
    ]
    forward_types = [
        "non[- ]deliverable",
        "deliverable",
        "deal[- ]contingent",
    ]
    forward_types_alternation = build_alternation(forward_types, sort_longest_first=True)

    # These capture the longest matches before falling back to pattern1
    specific_phrases = [
        # All forward types with optional suffixes (e.g., "non-deliverable forward contract")
        rf"(?:{forward_types_alternation})\s+forwards?\s+(?:{suffix_alternation})",
        rf"(?:{forward_types_alternation})\s+forwards?",
        # Other long-form specific FX instruments
        "NDF",
        r"hedges?\s+of\s+(?:the\s+)?net\s+investments?",
        "net investment hedges?",
    ]
    # Then pre-sort longest-first before passing to build_smart_regex
    specific_phrases = sorted(
        specific_phrases, key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:"))
    )

    pattern = build_smart_regex(
        core_terms,
        expand_instruments(unsafe=False),
        specific_phrases,
    )
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_cp_regex() -> re.Pattern:
    # 1. Base Terms: Generic + Specific List

    # Sorted alternation of all commodities (Max Munch applied internally)
    commodity_alternation = build_alternation(
        ["commodity", "commodities"] + COMMON_COMMODITIES, sort_longest_first=True
    )

    # Optimized modifiers (Max Munch applied internally)
    modifier_terms = [
        "prices?",
        "costs?",
        "related",
        "based",
        "linked",
        "index",
        "spreads?",
    ]
    modifier_alternation = build_alternation(modifier_terms, sort_longest_first=True)

    # 2. Generate Core Terms (Prefixes)

    # Optimized Core: Commodity Name + Modifier (e.g., Crude Oil[- ]price)
    # Build this way (what you should do):
    all_patterns = [
        rf"fixed[- ](?:{commodity_alternation})[- ](?:{modifier_alternation})",
        rf"(?:{commodity_alternation})[- ](?:{modifier_alternation})",
        rf"(?:{commodity_alternation})",
    ]

    # Then wrap in build_alternation with sort_longest_first=True
    core_alternation = build_alternation(all_patterns, sort_longest_first=True)
    spread_types = [
        "crack",
        "spark",
        "dark",
    ]
    spread_types_alternation = build_alternation(spread_types, sort_longest_first=True)

    specific_phrases = [
        r"weather derivatives?",                     # raw string for regex
        r"power purchase agreements?",               # raw string for regex
        # LONGEST FIRST: spreads with suffix
        rf"(?:{spread_types_alternation})\s+spreads?\s+(?:{standalone_alternation})",
        # SHORTER: spreads alone
        rf"(?:{spread_types_alternation})\s+spreads?",
        r"virtual power purchase agreements?",       # raw string for regex
        r"virtual PPA",
    ]

    # Then pre-sort longest-first before passing to build_smart_regex
    specific_phrases = sorted(
        specific_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:" ))
    )


    pattern = build_smart_regex([core_alternation], expand_instruments(unsafe=True), specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)

def build_eq_regex() -> re.Pattern:
    # Common fragments for readability and consistency
    liability = r"liabilit(?:y|ies)"
    option = r"options?"
    warrant = r"warrants?"
    derivative = r"derivatives?"

    # 1. Build Core Terms (Prefixes)
    core_terms = [
        r"equity",
        r"equity[- ](?:based|related|linked|index)",
        # RESTORED CRITICAL TERMS: These are needed for combinations like "S&P 500 swap"
        r"share\s+price",
        r"stock\s+price",
        r"market\s+index",
        r"S&P\s+500",
        r"Nasdaq",
        r"Dow\s+Jones",
    ]
    core_alternation = build_alternation(core_terms, True)

    # 2. Build Specific Phrases (Max Munch)

    # Convertible phrases (Structural Embedded Derivatives)
    convertible_phrases = [
        rf"embedded\s+conversion\s+(?:{option}|features?|{derivative})",
        rf"conversion\s+option\s+{liability}",
        rf"bifurcated\s+conversion\s+{option}",
        rf"{derivative}\s+{liability}\s+\S*convertible\s+notes?",  # Retained long structure
    ]

    # Warrant liabilities (Financial Warrants only)
    warrant_phrases = [
        # Direct warrant + (liability OR derivative)
        rf"{warrant}\s+(?:{derivative}[- ]{liability}|{liability}|{derivative})",
        # Inverted: liability/derivative + warrant
        rf"(?:{liability}|{derivative})[- ]classified\s+{warrant}",
        # Classified context: warrant...classified as (liability|derivative)
        rf"(?:{derivative}\s+)?{warrant}.*classified\s+as\s+(?:a\s+)?(?:{derivative}[- ]{liability}|{derivative}|{liability})",
        rf"(?:{derivative}[- ]{liability}|{derivative}|{liability})[- ]{warrant}",
    ]

    all_specifics = convertible_phrases + warrant_phrases

    pattern = build_smart_regex(
        [core_alternation],
        expand_instruments(unsafe=True),
        all_specifics,
    )

    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)

def build_strict_gen_regex() -> tuple[re.Pattern, re.Pattern]:
    """
    Returns a tuple:
        (INSTRUMENT_REGEX, NOTIONAL_REGEX)

    INSTRUMENT_REGEX  → captures pure derivative instrument names (strict)
    NOTIONAL_REGEX    → captures notional amount/principal/value phrases
    Both use named groups for convenient extraction.
    """
    # Pattern 1: Specific phrases (highest priority - most specific/longest)
    instrument_specific = [
        "total[- ]return swaps?",
        "cash flow hedges?",
        "fair value hedges?",
        "embedded derivatives?",
        "over[- ]the[- ]counter derivatives?",
        "derivative financial instruments?",
        "financial derivatives?"
    ]

    specific_alternation = build_alternation(
        instrument_specific, sort_longest_first=True
    )

    # Pattern 2: Generic base + suffix combinations and standalones
    generic_instruments = expand_instruments(unsafe=True)

    # Combine with specific phrases first (longest match priority)
    instrument_pattern = build_alternation(
        [specific_alternation, generic_instruments], 
        sort_longest_first=True
    )

    INSTRUMENT_REGEX = re.compile(
        rf"\b(?P<instrument>{instrument_pattern})\b", re.IGNORECASE
    )

    # ── 2. Notional phrases (very high precision, no overlap with instruments) ──
    notional_variants = [
        r"notional\s+(?:amounts?|values?|principals?)",
    ]

    NOTIONAL_REGEX = re.compile(
        rf"\b(?P<notional>(?:{'|'.join(notional_variants)}))\b", re.IGNORECASE
    )

    return INSTRUMENT_REGEX, NOTIONAL_REGEX


# Re-build the strict generic pair at import time
GEN_REGEX, STRICT_NOTIONAL_REGEX = build_strict_gen_regex()

# Optional: a combined strict regex that still catches *either* (for legacy code)
STRICT_GEN_REGEX = re.compile(
    rf"\b(?:{GEN_REGEX.pattern}|{STRICT_NOTIONAL_REGEX.pattern})\b",
    re.IGNORECASE,
)


def build_soft_gen_regex() -> re.Pattern:
    specific_phrases = [
        "(?:instruments?|contracts?) are designated",
        "ineffective portion",
        "hedging relationship",
        "hedge accounting",
        "change in fair value of derivatives?",
        "derivative expense",
        "designated as (?:a )?hedges?",
        "(?:gain|loss) on derivatives?",
    ]
    pattern = build_alternation(specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)

def build_loose_gen_regex() -> re.Pattern:
    pattern = build_alternation(ALL_BASE_TYPES + ALL_SUFFIXES)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)

# =============================================================================
# COMPILED REGEXES (exported)
# =============================================================================
IR_REGEX = build_ir_regex()
FX_REGEX = build_fx_regex()
CP_REGEX = build_cp_regex()
EQ_REGEX = build_eq_regex()

CATEGORY_REGEX = re.compile(
    r"|".join(
        [
            IR_REGEX.pattern,
            FX_REGEX.pattern,
            CP_REGEX.pattern,
            EQ_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)

SOFT_GEN_REGEX = build_soft_gen_regex()

STRICT_REGEX = re.compile(
    r"|".join(
        [
            CATEGORY_REGEX.pattern,
            STRICT_GEN_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)
LOOSE_GEN_REGEX = build_loose_gen_regex()
ALL_REGEX = re.compile(
    r"|".join([STRICT_REGEX.pattern, SOFT_GEN_REGEX.pattern]), re.IGNORECASE
)
CATEGORY_DELETION_MAP = {
    "ir": (IR_REGEX, IR_CONTEXT_REGEX),
    "fx": (FX_REGEX, FX_CONTEXT_REGEX),
    "cp": (CP_REGEX, CP_CONTEXT_REGEX),
    "eq": (EQ_REGEX, EQ_CONTEXT_REGEX),
}

# =============================================================================
# EXCLUSION PATTERNS (from filter_database.py)
# =============================================================================

# Section 1: Employee Equity Compensation
EQUITY_COMP_KEYWORDS = [
    "stock (?:options?|awards?|splits?|dividends?|purchases?)",
    "restricted stock",
    "RSU",
    "compensation",
    "employee",
    "share-based",
    "vesting",
    "exercisable",
    "ESPP",
    "bonus",
    "salary",
    "wage",
    "dividend",
    "outstanding shares",
    "share repurchase",
    "buyback",
    "hedge fund",
]

# Section 2: Legal/Litigation
# === More specific legal/litigation patterns ===
LEGAL_LITIGATION_KEYWORDS = [
    # Core litigation terms
    r"\blawsuit\b",
    r"\blitigation\b",
    r"\barbitration\s+(?:proceeding|hearing|case)\b",
    r"\blegal\s+(?:action|proceeding|case|dispute)\b",
    # Types of legal actions (use full context)
    r"\bcivil\s+(?:action|suit|case|proceeding)\b",
    r"\bcriminal\s+(?:action|case|proceeding|charges?)\b",
    r"\badministrative\s+(?:action|proceeding|hearing)\b",
    # Parties in litigation (must be in litigation context)
    r"\b(?:named\s+as\s+)?(?:a\s+)?(?:plaintiff|defendant|respondent|claimant)\b",
    r"\b(?:co-)?defendants?\s+(?:in|include|are)\b",
    # Convictions and violations
    r"\bconvicted\s+of\b",
    r"\bpled\s+guilty\b",
    r"\bplea\s+(?:agreement|bargain|deal)\b",
    r"\bviolated\s+(?:securities|federal|state)\b",
    r"\balleges?\s+(?:that|violations?)\b",
    r"\bcharges?\s+(?:filed|brought|pending)\b",
    # Court proceedings
    r"\bcourt\s+(?:case|proceeding|order|judgment|ruling)\b",
    r"\bjudgme?nt\s+(?:against|in\s+favor|rendered)\b",  # Fixed typo
    # Officers/Directors in legal context (more specific)
    r"\b(?:former\s+)?(?:officer|director)s?\s+(?:was|were|are)\s+(?:charged|indicted|convicted|sued)\b",
    r"\bagainst\s+(?:former\s+)?(?:officer|director)s?\b",
    r"\b(?:officer|director)s?\s+(?:and|or)\s+(?:officer|director)s?\s+(?:were\s+)?(?:named|charged|sued)\b",
    # Securities litigation specific
    r"\bsecurities\s+(?:fraud|litigation|class\s+action)\b",
    r"\bclass\s+action\s+lawsuit\b",
    r"\bshareholder\s+(?:lawsuit|litigation|suit)\b",
]
# Section 3: Accounting Standards
# === FASB ISSUANCE & ADOPTION ONLY ===
ACCOUNTING_STANDARDS_KEYWORDS = [
    # Issuance announcements (the boilerplate you want to remove)
    r"(FASB|Financial Accounting Standards Board|F.A.S.B.)\s+(?:issued|has\s+issued|released|published)",
    r"(?:SFAS|FAS|ASU|ASC)\s+(?:No\.\s+)?\d+(?:-\d+)*\s+(?:was|is)\s+issued",
    r"issued.*(?:SFAS|FAS|ASU|Statement)\s+(?:No\.\s+)?\d+",
    r"in\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}.*(?:issued|released)",
    # Adoption language (future application)
    r"will\s+adopt",
    r"plan(?:s|ned)?\s+to\s+adopt",
    r"expect(?:s|ed)?\s+to\s+adopt",
    r"required?\s+to\s+adopt",
    r"adopt(?:ing|ed)?\s+(?:the\s+)?(?:new\s+)?(?:guidance|standard|amendment|ASU|Statement)",
    r"early\s+adopt(?:ed|ing|ion)?",
    r"upon\s+adoption\s+of",
    r"prior\s+to\s+adoption",
    # Evaluation of future standards
    r"evaluat(?:ing|ed|e|es)\s+(?:the\s+)?(?:impact|effect)\s+of.*(?:adoption|standard|guidance)",
    r"assess(?:ing|ed|es)\s+the\s+(?:impact|effect)\s+of.*(?:new|upcoming|proposed)\s+(?:standard|guidance)",
    r"currently\s+(?:evaluating|assessing)\s+(?:the\s+)?(?:impact|effect)",
    r"continu(?:ing|es)\s+to\s+evaluate",
    # Effective date language (future application)
    r"effective\s+for\s+(?:fiscal\s+years|annual\s+periods)\s+beginning",
    r"effective\s+(?:in|for|after)\s+(?:fiscal\s+)?(?:year\s+)?\d{4}",
    r"becomes\s+effective",
    r"will\s+be\s+effective",
    # Impact assessment (only future standards)
    r"(?:not\s+)?expected\s+to\s+have\s+a\s+material\s+(?:impact|effect).*(?:adoption|effective)",
    r"no\s+material\s+impact.*(?:upon|from)\s+adoption",
    # Standard descriptions (only in issuance context)
    r"establishes?\s+accounting\s+and\s+reporting\s+standards\s+(?:for|requiring)",
    r"(?:this|the)\s+(?:statement|standard|guidance|amendment)\s+(?:addresse(?:d|s)|clarifie(?:d|s)|amend(?:ed|s))",
    r"Accounting for Derivative Instruments and Hedging Activities",
]


def build_exclude_regex(keywords: list) -> re.Pattern:
    """Build regex for excluding noise keywords."""
    escaped_keywords = [re.escape(kw) for kw in keywords]
    pattern = "|".join(escaped_keywords)
    return re.compile(pattern, re.IGNORECASE)


EXCLUDE_REGEX_EQUITY_COMP = build_exclude_regex(EQUITY_COMP_KEYWORDS)
EXCLUDE_REGEX_LEGAL_LITIGATION = re.compile(
    r"|".join(LEGAL_LITIGATION_KEYWORDS), re.IGNORECASE
)
EXCLUDE_REGEX_ACCOUNTING_STD = re.compile(
    r"|".join(ACCOUNTING_STANDARDS_KEYWORDS), re.IGNORECASE
)

# Combined exclusion regex (tested first - very fast)
COMBINED_EXCLUDE_REGEX = re.compile(
    f"({EXCLUDE_REGEX_EQUITY_COMP.pattern})|({EXCLUDE_REGEX_LEGAL_LITIGATION.pattern})|({EXCLUDE_REGEX_ACCOUNTING_STD.pattern})",
    re.IGNORECASE,
)
SUBJECTS = [
    # Simple pronouns
    r"we",
    r"us",
    # Generic entity terms
    r"(?:the\s+)?(?:company|firm|partnership|group|trust|entity|issuer|registrant|organization|association|co\.?)",
    r"(?:our\s+)(?:company|firm|partnership|group|trust|entity|issuer|registrant|organization|association|co\.?)",
    # Management references
    r"(?:the\s+)?(?:our\s+)?management",
    # LLC / LP / GP structures
    r"(?:the\s+|our\s+)?(?:llc|l\.l\.c\.|lp|l\.p\.|gp|g\.p\.)",
    # Partnership (general/limited)
    r"(?:the\s+|our\s+)?(?:general\s+partner|limited\s+partner|partnership)",
    # Corporate forms
    r"(?:the\s+|our\s+)?(?:corporation|corp\.|co\.|inc\.|incorporated)",
    # Parent entity references
    r"(?:the\s+|our\s+)?(?:parent(?:\s+company)?)",
    # Subsidiary references
    r"(?:the\s+|our\s+)?(?:wholly[-\s]+owned\s+)?(?:subsidiary|subsidiaries)",
]
SUBJ = build_alternation(SUBJECTS)
# ============================================================================
# TIME-RELATED PATTERNS (Reusable)
# ============================================================================

TIME_UNITS = [
    r"year",
    r"period",
    r"quarter",
    r"month",
]

PAST_TIME_INDICATORS = [
    r"prior",  # prior, priors rarely used → no inflection needed
    r"previous",  # previous(ly)? rarely plural
    r"preced(?:e|es|ed|ing)",
    r"earlier",  # earlier/earliest already covered as comparative
    r"last",  # last/lasts/lasting → but usually adjective; add if needed
    r"past",  # past/pasts rarely plural in this context
    r"comparable",  # comparable/comparably
    r"correspond(?:s|ed|ing)",  # corresponding is very common
    r"historical",  # historical/historically
    r"former",  # very common synonym for past periods
    r"before",  # e.g., "before the reporting date"
    r"earlier\s+(?:in|during|as\s+of)",  # common collocations
]

CURRENT_TIME_INDICATORS = [
    r"present(?:ly)?",
    r"current(?:ly)?",
    r"now",
    r"today",
    r"as\s+of\s+(?:the\s+date|today|current\s+period)",
    r"at\s+present",
    r"ongoing",
    r"existing",
]
NON_POSITION_INDICATORS = re.compile(
    r"""
    (?:
        (?:accumulated\s+)?other\s+comprehensive\s+(?:income|loss)|
        (?:AOCI|OCI)\b|
        (?:reclassified?|reclassifi).*(?:AOCI|OCI|comprehensive)|
        deferred\s+(?:tax\s+)?(?:gain|loss)|
        realized\s+(?:gain|loss)|
        unrealized\s+(?:gain|loss)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Build alternations once
TIME_UNIT_PATTERN = build_alternation(TIME_UNITS)
PAST_TIME_PATTERN = build_alternation(PAST_TIME_INDICATORS)
CURRENT_TIME_PATTERN = build_alternation(CURRENT_TIME_INDICATORS)
COMPARISON_PATTERN = build_alternation(comparison_phrases)
STRONG_VERB_PATTERN = build_alternation(STRONG_ACTION_VERBS)
WEAK_VERB_PATTERN = build_alternation(PASSIVE_STATE_VERBS)
VERB_PATTERN = "|".join([STRONG_VERB_PATTERN, WEAK_VERB_PATTERN])
VERB_REGEX = re.compile(rf"\b(?:{VERB_PATTERN})\b", re.IGNORECASE)
def build_trading_denial_pattern() -> re.Pattern:
    """Build regex pattern for detecting trading denial statements to remove/mask them."""

    NEGATORS = [
        r"do\s+not",
        r"does\s+not",
        r"did\s+not",
        r"are\s+not",
        r"is\s+not",
        r"were\s+not",
        r"will\s+not",
        r"have\s+not",
        r"has\s+not",
        r"would\s+not",
        r"cannot",
        r"can\s+not",
        r"never",
        r"not",
    ]

    ACTIONS = [
        r"use(?:d|s)?",
        r"using",
        r"enter(?:ed|s)?\s+into",
        r"entering\s+into",
        r"engage(?:d|s)?\s+in",
        r"engaging\s+in",
        r"hold(?:s)?",
        r"held",
        r"holding",
        r"conduct(?:ed|s)?",
        r"conducting",
        r"undertake(?:n|s)?",
        r"undertaking",
        r"employ(?:ed|s)?",
        r"maintain(?:ed|s)?",
    ]

    OBJ = STRICT_REGEX.pattern # Not needed, we already had caught them in intial filtering

    TRADING_WORDS = [
        r"trading",
        r"speculative",
        r"speculation",
        r"proprietary\s+trading",
    ]

    PURPOSE_WORDS = [
        r"purposes?",
        r"activities?",
        r"basis",
        r"transactions?",
    ]

    NEG = build_alternation(NEGATORS)
    ACT = build_alternation(ACTIONS)
    TRAD = build_alternation(TRADING_WORDS)
    PURP = build_alternation(PURPOSE_WORDS)

    # Clause 1: Subject + negator + action + [anything] + trading purpose
    CLAUSE_1 = (
        rf"\b(?:{SUBJ})\s+(?:{NEG})\s+(?:{ACT})\s+"
        rf"(?:any\s+|such\s+)?\S+(?:\s+\S+){{0,7}}\s+"  # Captures  words for the object (longest: derivative financial instruments and other derivative financial instruments)
        rf"(?:for\s+)?(?:on\s+a\s+)?(?:{TRAD})\s+(?:{PURP})?\b"
    )

    # Clause 2: [Anything] + negator + action + trading
    CLAUSE_2 = (
        rf"\b(?:any\s+|such\s+|these\s+|the\s+)?\S+(?:\s+\S+){{0,7}}\s+"  # Captures  words
        rf"(?:{NEG})\s+(?:be\s+)?(?:{ACT})\s+"
        rf"(?:for\s+)?(?:on\s+a\s+)?(?:{TRAD})(?:\s+(?:{PURP}))?\b"
    )

    # Clause 3: Short negative form
    CLAUSE_3 = (
        rf"\b(?:{NEG})\s+(?:be\s+)?(?:{ACT})\s+"
        rf"(?:(?:any\s+|such\s+)?\S+(?:\s+\S+){{0,7}}\s+)?"  # Optional object
        rf"(?:for\s+)?(?:on\s+a\s+)?(?:{TRAD})(?:\s+(?:{PURP}))?\b"
    )

    # Clause 4: Direct speculation denial
    CLAUSE_4 = rf"\b(?:{SUBJ})\s+(?:{NEG})\s+speculate\b"

    # Clause 5: "None of [anything]..."
    CLAUSE_5 = (
        rf"\bnone\s+of\s+(?:the\s+|our\s+)?\S+(?:\s+\S+){{0,7}}\s+"
        rf"(?:are|is|were|was)\s+(?:{ACT})\s+"
        rf"(?:for\s+)?(?:{TRAD})(?:\s+(?:{PURP}))?\b"
    )

    # Clause 6: "No trading or speculative purposes"
    CLAUSE_6 = (
        rf"\bno\s+(?:{TRAD})(?:\s+or\s+(?:{TRAD}))?(?:\s+(?:{PURP}))?\b"
    )
    CLAUSE_7 = (
        rf"\b(?:{SUBJ}|derivatives?|instruments?|contracts?)\s+"
        rf"(?:are|is|were|was)\s+not\s+"
        rf"(?:used|held|entered|designated)\s+"
        rf"(?:for\s+)?(?:{TRAD})(?:\s+(?:{PURP}))?\b"
    )
    pattern = build_alternation(
        [
            CLAUSE_1,
            CLAUSE_2,
            CLAUSE_3,
            CLAUSE_4,
            CLAUSE_5,
            CLAUSE_6,
            CLAUSE_7,
        ]
    )
    return re.compile(pattern, re.IGNORECASE)


TRADING_STATEMENTS_REGEX = build_trading_denial_pattern()
# =============================================================================
# DEFINITION DETECTION (Isolated boilerplate)
# =============================================================================


def build_definition_regex() -> re.Pattern:
    """
    Builds a comprehensive definition detection regex using:
    - CATEGORY_REGEX: all derivative instruments
    - SUBJ: company/subject references
    - VERB_PATTERN: negative check (definitions shouldn't have action verbs)
    """

    instr = f"(?:{CATEGORY_REGEX.pattern})"
    subject = SUBJ

    # Negative lookahead: don't match if sentence contains action verbs
    # (those indicate actual usage, not pure definition)
    no_action_verb = rf"(?!.*\b(?:{VERB_PATTERN})\b)"

    pattern_list = [
        rf"{no_action_verb}(?:a\s+)?{instr}\s+(?:is\s+)?defined\s+as",
        rf"{no_action_verb}definition\s+(?:of|for)\s+(?:a\s+)?{instr}",
        rf"{no_action_verb}(?:{subject})\s+(?:consider|define)s?\s+(?:a\s+)?{instr}.*as",
        rf'{no_action_verb}"(?:{instr})".*(?:means|refers\s+to)',
    ]

    combined = "|".join(f"(?:{p})" for p in pattern_list)
    return re.compile(combined, re.IGNORECASE | re.VERBOSE)


# Compile at module load
DEFINITION_INDICATORS = build_definition_regex()

def build_prior_statement_pattern() -> re.Pattern:
    """
    Build regex pattern for detecting prior period statements to remove them.
    Works after you have already stripped numerical years.
    Deletes ONLY the historical fragment — preserves everything after
    but/however/currently/we use/etc.
    Example:
      "In prior year we used swaps, but currently we use forwards"
       └────DELETE THIS─────────┘  └────KEEP THIS────────────┘
    """

    # Prepositions that introduce time references
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

    PRIOR_TERMS = [
        rf"(?:{PAST_TIME_PATTERN})\s+(?:fiscal\s+)?(?:{TIME_UNIT_PATTERN})s?",
        r"same\s+period\s+last\s+year",
        r"year\s+ago",
        r"months?\s+ago",
        r"quarters?\s+ago",
        r"prior\s+to",
    ]

    PREP = build_alternation(PREPOSITIONS)
    PRIOR = build_alternation(PRIOR_TERMS)
    SUBJ = build_alternation(SUBJECTS)  # Already available
    # Strong boundary — stop deletion exactly when a current-period statement begins
    BOUNDARY = rf"""
        (?=                                       
            \s*[,;:.]\s*                        
            | \s+(?:but|however|whereas|although|though|while|yet)\b
            | \s+(?:{CURRENT_TIME_PATTERN})\b
            | \s+this\s+(?:{TIME_UNIT_PATTERN})\b
            | \s+during\s+the\s+(?:current\s+)?(?:{TIME_UNIT_PATTERN})\b
            | \s+as\s+of\s+(?:year[- ]end)\b
            | \s+(?:{SUBJ})\s+{VERB_PATTERN}\b           
            | $                                   
        )
    """

    # Core patterns for prior-period references
    pattern1 = rf"(?:\b(?:{SUBJ})\s+)?(?:{PREP})\s+(?:{PRIOR})\b[^,.;]*?"
    pattern2 = rf"\b(?:{PREP})\s+(?:{PRIOR})\b[^,.;]*?"
    pattern3 = rf"\b(?:{COMPARISON_PATTERN})\s+to\s+(?:{PRIOR})[^,.;]*?"

    full_pattern = f"({pattern1}|{pattern2}|{pattern3}){BOUNDARY}"

    return re.compile(full_pattern, re.IGNORECASE | re.VERBOSE)
PRIOR_PATTERN = build_prior_statement_pattern()
# =============================================================================
# EXCLUSION PATTERNS (from webpage.py)
# =============================================================================

IGNORE_REGEX = re.compile(r"|".join(LEGAL_LITIGATION_KEYWORDS + EQUITY_COMP_KEYWORDS), re.IGNORECASE)

# =============================================================================
# TABLE AND MISCELLANEOUS PATTERNS
# =============================================================================

# Regex for matching only base derivative types, intended for use within tables
TABLE_BASE_TYPES_REGEX = re.compile(
    r"\b" + build_alternation([base.rstrip("?") for base in UNAMBIGUOUS_BASE_TYPES]) + r"\b",
    re.IGNORECASE,
)

# Combined regex for webpage.py
COMBINED_REGEX = re.compile(
    r"|".join(
        [
            IR_REGEX.pattern,
            FX_REGEX.pattern,
            CP_REGEX.pattern,
            EQ_REGEX.pattern,
            STRICT_GEN_REGEX.pattern,
            SOFT_GEN_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)

# Regex to find years between 1980-2049, followed by a word boundary character
YEAR_REGEX = re.compile(r"\b(19[8-9]\d|20[0-4]\d)\b")

PNL_ONLY_NO_POSITION = re.compile(
    rf"""
    (?:
        (?:realized|unrealized)\s+(?:gain|loss)|
        mark(?:\s+to)?[- ]market|
        (?:gain|loss)\s+on\s+derivative|
        change\s+in\s+fair\s+value|
        ineffective\s+portion|
        hedge\s+ineffectiveness|
        reclassifi(?:ed|cation).*earnings|
        net\s+(?:gain|loss)\s+on
    )
    (?!.*(?:
        {VERB_PATTERN}|
        position|outstanding|active|open|notional|
        fair\s+value\s+(?:asset|liabilit(?:y|ies))|
        derivative.*(?:asset|liabilit(?:y|ies))|designated|hedging\s+relationship
    ))
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Position context: verbs + structural indicators
POSITION_CONTEXT_INDICATORS = re.compile(
    rf"""
    (?:
        {VERB_PATTERN}|
        position|outstanding|notional|
        fair\s+value.*(?:asset|liabilit(?:y|ies))|
        designated
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
# ──────────────────────────────────────────────────────────────
# Pre-compiled cleanup regexes (put at module level, once)
# ──────────────────────────────────────────────────────────────
_CLEAN_LEADING_JUNK = re.compile(r"^[\s.;,]+")
_CLEAN_TRAILING_JUNK = re.compile(r"[\s.;,]+$")
_CLEAN_SPACE_COMMA = re.compile(r"\s+,")
_CLEAN_COMMA_SPACE = re.compile(r",\s+")
_CLEAN_SPACE_SEMICOLON = re.compile(r"\s+;")


def cleanup_fragment(sentence: str) -> str:
    """
    Clean up punctuation mess after surgically removing trading-denial clauses.
    This turns: ", but we hedge." → "but we hedge."
                "We only use swaps to manage risk ;" → "We only use swaps to manage risk"
    """
    sentence = _CLEAN_SPACE_COMMA.sub(",", sentence)
    sentence = _CLEAN_COMMA_SPACE.sub(", ", sentence)
    sentence = _CLEAN_SPACE_SEMICOLON.sub(";", sentence)
    sentence = _CLEAN_LEADING_JUNK.sub("", sentence)
    sentence = _CLEAN_TRAILING_JUNK.sub("", sentence)
    sentence = sentence.strip()
    return sentence if len(sentence) > 10 else "" # too short we don't return anything

# ... existing code ...
# =============================================================================
# LINGUISTIC INTENT & FILTERING PATTERNS
# =============================================================================

# --------------------------------------------------------------------------- #
# 1. HELPER LISTS
# --------------------------------------------------------------------------- #

# Transaction verbs (Action)
_TRANSACTION_VERBS = [r"enter", r"engage", r"transact"]
_TRANSACTION_PATTERN = build_alternation(_TRANSACTION_VERBS)

# Combined intent verbs: standard (hold, use, hedge) + transaction (enter, engage)
INTENT_VERB_PATTERN = build_alternation([VERB_PATTERN, _TRANSACTION_PATTERN])

# Speculative / Uncertain Timing Phrases
SPECULATIVE_PHRASES = [
    r"from\s+time\s+to\s+time",
    r"periodically",
    r"occasionally",
    r"in\s+the\s+future",
    r"upon\s+occurrence",
]

# Potential / Hypothetical Modals & Phrases
POTENTIAL_INDICATORS = [
    r"may",
    r"might",
    r"could",
    r"seek\s+to",
    r"intend\s+to",
    r"plans?\s+to",
    # FIX: Negative lookahead allows "expect to continue" (Active) while flagging "expect to use" (Potential)
    r"expect\s+to\s+(?!continue)",
]

# Negative Intent Components
NEGATIVE_AUXILIARY = [r"do", r"does", r"did", r"will"]
NEGATIVE_INTENT_VERBS = [r"seek", r"intend", r"plan", r"expect"]

# Absence Indicators
ABSENCE_INDICATORS = [r"no", r"none"]

# Absence/Termination Nouns (Abstract concepts not covered by instrument regexes)
_ABSENCE_NOUNS = [
    r"outstanding",  # "no such outstanding"
    r"positions?",
    r"exposures?",
    r"obligations?",
    r"hedge",  # "no such hedge" (generic)
    r"activity",  # "no derivative activity"
    r"involvement",  # "no involvement with derivatives"
    r"holdings?",  # "no holdings"
]

# Termination Verbs
TERMINATION_VERBS = [
    r"expired",
    r"matured",
    r"settled",
    r"terminated",
    r"ceased",
    r"closed",
    r"unwound",
    r"exercised", # Essential for options/swaptions
    r"extinguished",
    r"novated", # Transferring the trade to another counterparty (implies exit)
]

# Active / Timing Indicators (New)
ACTIVE_INDICATORS = [
    "currently",
    "actively",
    "presently",
    "ongoingly",
    "continually",
    "regularly",
    "at the moment",
    "as of now",
    "now",
]

# Materiality (New)
IMMATERIAL = [
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
    "inconsequential",
    "zero",
]

MATERIAL = [
    "material",
    "significant",
    "substantial",
]

# Build Patterns
ACTIVE_PATTERN = build_alternation(ACTIVE_INDICATORS)
ACTIVE_STATE_REGEX = re.compile(r"\b" + ACTIVE_STATE_PATTERN + r"\b", re.IGNORECASE)
IMMATERIAL_PATTERN = build_alternation(IMMATERIAL)
MATERIAL_PATTERN = build_alternation(MATERIAL)

# --------------------------------------------------------------------------- #
# 2. REGEX BUILDER FUNCTIONS
# --------------------------------------------------------------------------- #


def build_potential_regex() -> re.Pattern:
    """
    Matches: "may enter", "might use", "expect to hedge"
    Relaxed middle group catches: "may [occasionally] use", "may [typically] enter"
    """
    return re.compile(
        rf"\b{build_alternation(POTENTIAL_INDICATORS)}\s+"
        r"(?:\w+\s+){0,7}"
        rf"({INTENT_VERB_PATTERN})\b",
        re.IGNORECASE,
    )


def build_vague_timing_regex() -> re.Pattern:
    """Matches: "from time to time", "in the future" """
    return re.compile(rf"\b{build_alternation(SPECULATIVE_PHRASES)}\b", re.IGNORECASE)


def build_negative_intent_regex() -> re.Pattern:
    """
    Matches: "does not intend to", "will not seek to", "has no plans to"
    Incorporates ACTIVE_PATTERN to catch: "does not [currently] intend to"
    """
    _neg_aux = build_alternation(NEGATIVE_AUXILIARY)
    _neg_verb = build_alternation(NEGATIVE_INTENT_VERBS)

    _neg_pattern_standard = (
        rf"\b{_neg_aux}\s+not\s+(?:{ACTIVE_PATTERN}\s+)?{_neg_verb}\s+to"
    )
    _neg_pattern_plans = r"\bhas\s+no\s+plans\s+to"

    return re.compile(
        rf"(?:{_neg_pattern_standard}|{_neg_pattern_plans})\b", re.IGNORECASE
    )


def build_absence_regex() -> re.Pattern:
    """
    Matches: "no interest rate swaps", "no such outstanding positions"
    Uses master object pattern + state/materiality fillers
    """
    # Create master object pattern
    _instrument_object = rf"(?:{STRICT_REGEX.pattern}|{LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"

    # Fillers: "such", "any", plus our new Material/State patterns
    # Matches: "no [material] [outstanding] swaps"
    _fillers = (
        r"(?:such\s+|any\s+|" rf"{MATERIAL_PATTERN}\s+|" rf"{ACTIVE_STATE_PATTERN}\s+)*"
    )

    return re.compile(
        rf"\b{build_alternation(ABSENCE_INDICATORS)}\s+"  # No/None
        rf"{_fillers}"  # Optional fillers
        rf"{_instrument_object}\b",  # The Object
        re.IGNORECASE,
    )


def build_did_not_hold_regex() -> re.Pattern:
    """
    Matches: "did not hold [swaps]", "does not enter into [derivatives]"
    Expanded start anchor to (did|does|do|will)
    """
    _instrument_object = rf"(?:{STRICT_REGEX.pattern}|{LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"

    _fillers = (
        r"(?:such\s+|any\s+|" rf"{MATERIAL_PATTERN}\s+|" rf"{ACTIVE_STATE_PATTERN}\s+)*"
    )

    return re.compile(
        rf"\b(?:did|does|do|will)\s+not\s+(?:{ACTIVE_PATTERN}\s+)?(?:{INTENT_VERB_PATTERN})\s+"
        rf"{_fillers}"
        rf"{_instrument_object}\b",
        re.IGNORECASE,
    )


def build_termination_regex() -> re.Pattern:
    """Matches: "expired", "matured", "unwound" """
    return re.compile(rf"\b{build_alternation(TERMINATION_VERBS)}\b", re.IGNORECASE)

def check_for_instrument(sentence: str, strict: bool = False) -> bool:
    """
    Determines if the instrument name is still present in the paragraph/sentence.

    Args:
        sentence: The text to scan.
        strict: If True, only returns True for specific instrument names (swaps, options)
                or explicit categories (interest rate, foreign exchange).
                Ignores loose terms like "contracts", "agreements", "instruments".
    """
    # High-confidence matches (Category specific + Specific Instruments like 'Swap agreement')
    if CATEGORY_REGEX.search(sentence) or STRICT_GEN_REGEX.search(sentence):
        return True

    # Loose matches (Generic terms like 'Contracts', 'Agreements', "swaps")
    # Only checked if strict mode is OFF
    if not strict and LOOSE_GEN_REGEX.search(sentence):
        return True

    return False


def validate_instrument_retention(
    paragraphs: List[str], categories: List[str], url: str, strict: bool = False
) -> Tuple[List[str], List[str], List[Tuple[str, str, str]]]:
    """
    Final safety check to ensure cleaning didn't strip the instrument name.
    Iterates parallel arrays and filters them in sync.

    Returns:
        (kept_paragraphs, kept_categories, list_of_discards)
    """
    validated_paragraphs = []
    validated_categories = []
    discards = []

    for text, cat in zip(paragraphs, categories):
        # Strict=False allows "contracts", "instruments" (Broader)
        # Strict=True requires "swaps", "options" (Stricter)
        if check_for_instrument(text, strict=strict):
            validated_paragraphs.append(text)
            validated_categories.append(cat)
        else:
            discards.append((url, text, "lost_instrument_reference"))

    return validated_paragraphs, validated_categories, discards


# --------------------------------------------------------------------------- #
# 3. COMPILED REGEX EXPORTS
# --------------------------------------------------------------------------- #

POTENTIAL_REGEX = build_potential_regex()
VAGUE_TIMING_REGEX = build_vague_timing_regex()
NEGATIVE_INTENT_REGEX = build_negative_intent_regex()
ABSENCE_REGEX = build_absence_regex()
DID_NOT_HOLD_REGEX = build_did_not_hold_regex()
TERMINATION_REGEX = build_termination_regex()

__all__ = [
    "SENTENCE_SPLIT_PATTERN",
    "MIN_SENTENCE_LENGTH",
    "IR_REGEX",
    "FX_REGEX",
    "CP_REGEX",
    "EQ_REGEX",
    "STRICT_GEN_REGEX",
    "SOFT_GEN_REGEX",
    "STRICT_REGEX",
    "ALL_REGEX",
    "COMBINED_REGEX",
    "COMMON_COMMODITIES",
    "EQUITY_COMP_KEYWORDS",
    "LEGAL_LITIGATION_KEYWORDS",
    "ACCOUNTING_STANDARDS_KEYWORDS",
    "EXCLUDE_REGEX_EQUITY_COMP",
    "EXCLUDE_REGEX_LEGAL_LITIGATION",
    "EXCLUDE_REGEX_ACCOUNTING_STD",
    "COMBINED_EXCLUDE_REGEX",
    "TRADING_STATEMENTS_REGEX",
    "IGNORE_REGEX",
    "TABLE_BASE_TYPES_REGEX",
    "YEAR_REGEX",
    "cleanup_fragment",
    "PRIOR_PATTERN",
    "IR_CONTEXT_REGEX",
    "FX_CONTEXT_REGEX",
    "CP_CONTEXT_REGEX",
    "EQ_CONTEXT_REGEX",
    "HEDGING_CONTEXT_REGEX",
    "CATEGORY_CONTEXT_MAP",
    "NON_POSITION_INDICATORS",
    "PNL_ONLY_NO_POSITION",
    "DEFINITION_INDICATORS",
    "GEN_REGEX",
    "POTENTIAL_REGEX",
    "VAGUE_TIMING_REGEX",
    "NEGATIVE_INTENT_REGEX",
    "ABSENCE_REGEX",
    "DID_NOT_HOLD_REGEX",
    "TERMINATION_REGEX",
    "CURRENCY_SYMBOL_PATTERN",
    "VERB_REGEX",
    "STRONG_VERB_PATTERN",
    "WEAK_VERB_PATTERN",
    "ACTIVE_STATE_REGEX",
    "validate_instrument_retention",
    "HIGH_PRECISION_SUFFIXES",
]
