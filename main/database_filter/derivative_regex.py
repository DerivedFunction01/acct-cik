from dataclasses import dataclass
import re
from typing import List, Tuple


def build_alternation(items: List[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
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
    "in comparison with",
]


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
    r"remained?\s+outstanding",
]

SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<=[.!?])"  # Positive lookbehind for punctuation
    # 1. Protect Initials (e.g., "John H. Smith") -> Capital + Dot
    r"(?<!\b[A-Z]\.)"
    # 2. Protect 2-letter Acronyms (e.g., "U.S.", "U.K.", "N.Y.") -> Cap.Cap.
    r"(?<!\b[A-Z]\.[A-Z]\.)"
    # 3. Protect 3-letter Acronyms (e.g., "U.S.A.", "S.E.C.") -> Cap.Cap.Cap.
    r"(?<!\b[A-Z]\.[A-Z]\.[A-Z]\.)"
    # 4. Protect common Title/Corp abbreviations (Mixed Case)
    r"(?<!\bInc\.)"
    r"(?<!\bCorp\.)"
    r"(?<!\bLtd\.)"
    r"(?<!\bNo\.)"  # "Note No. 5"
    r"(?<!\bNos\.)"  # Plural numbers
    r"(?<!\bVol\.)"  # Volume
    r"(?<!\bvs\.)"  # versus
    r"(?<!\bpp?\.)"  # p. or pp. (pages)
    r"(?<!\b[Ee]tc\.)"  # etc.
    r"\s+(?=[A-Z])"  # Must be followed by Whitespace + Uppercase
    r"|"
    r"(?<=[a-z])(?=[A-Z])"  # camelCase boundaries (unchanged)
)

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
    "call options?",
    "put options?",
]

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

COMMON_COMMODITIES = [
    "agricultural",
    "aluminum",
    "asphalt",
    "base metal",
    "biodiesel",
    "biomass",
    "bitumen",
    "cement",
    "chemical",
    "coal",
    "cocoa",
    "coffee",
    "concrete",
    "copper",
    "corn",
    "cotton",
    "crude oil",
    "dairy",
    "diesel fuel",
    "electricity",
    "energy",
    "ethanol",
    "feedstock",
    "fertilizer",
    "fuel",
    "gas",
    "gasoline",
    "grain",
    "gravel",
    "hardwood lumber",
    "iron",
    "limestone",
    "livestock",
    "log",
    "lumber",
    "metal",
    "mineral",
    "natural gas",
    "nitrogen",
    "paper",
    "ore",
    "petrochemical",
    "petroleum",
    "phosphate",
    "plastic",
    "plywood",
    "polymer",
    "potash",
    "precious metal",
    "pulp",
    "raw material",
    "resin",
    "rubber",
    "salt",
    "sand",
    "soda ash",
    "softwood lumber",
    "soybean",
    "steel",
    "sugar",
    "sulfur",
    "textile",
    "timber",
    "titanium",
    "uranium",
    "wood",
    "wood chip",
    "wood pellet",
    "wool",
]

# Minimum sentence length to consider (we use swaps is 12 chars and rarely ever occurs)
MIN_SENTENCE_LENGTH = 15


# =============================================================================
# REGEX BUILDERS (moved)
# =============================================================================


def build_smart_regex(
    core_terms: List[str], context_terms: List[str], specific_phrases: List[str]
) -> str:
    core_pattern = build_alternation(core_terms)
    follow_pattern = build_alternation(context_terms)
    pattern1 = f"{core_pattern}[- ]{follow_pattern}"
    pattern2 = build_alternation(specific_phrases)
    return build_alternation([pattern1, pattern2])

# Interest Rate context clues
IR_CONTEXT_TERMS = [
    r"debt",
    r"loan",
    r"borrow(?:ing|ed)?",
    r"bond",
    r"note",
    r"credit\s+facilit(?:y|ies)",
    r"floating[- ]rate",
    r"variable[- ]rate",
    r"benchmark[-]rate",
    r"interest[- ]rate",
    r"treasury[-]rate",
    r"forward[- ]rate",
    r"LIBOR",
    r"SOFR",
    r"EURIBOR",
    r"SONIA",
    r"interest\s+(?:rate\s+)?(?:risk|exposure|volatility)",
    r"fixed[- ](?:rate|to[- ]floating)",
    r"basis\s+point",
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
                adj_esc + r"\s+(?:assets?|liabilities)",
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

    Produces:
      - ISO codes (USD, EUR)
      - ISO pairs (USD/JPY, EUR/USD)
      - code-denominated (USD-denominated)
      - adjective + unit (Canadian dollar)
      - safe unit-only (forint, zloty, rand)
    """
    patterns = set()

    unsafe_units = {"dollar", "pound", "yen", "won", "real"}

    # ISO code set for cross patterns
    codes = [c.code for c in all_currencies]

    # -----------------------------------
    # 1. ISO codes and ISO FX pairs
    # -----------------------------------
    for c in codes:
        patterns.add(re.escape(c))
        patterns.add(re.escape(c) + r"-denominated")
        patterns.add(re.escape(c) + r"/" + r"[A-Z]{3}")
        patterns.add(r"[A-Z]{3}/" + re.escape(c))

    # -----------------------------------
    # 2. Adjective + unit pairs
    # -----------------------------------
    for curr in all_currencies:
        full = curr.full_name.strip()
        words = full.split()
        adjective = curr.adjective
        unit = words[-1]

        # e.g., "Canadian dollar"
        if adjective and unit:
            patterns.add(re.escape(f"{adjective} {unit}"))

        # Unit-only when safe
        if unit.lower() not in unsafe_units:
            patterns.add(re.escape(unit))

        # U.S. variants
        if adjective == "U.S.":
            patterns.update(
                [
                    r"U\.?S\.?\s+" + re.escape(unit),
                    r"United\s+States\s+" + re.escape(unit),
                ]
            )

    sorted_patterns = sorted(patterns, key=len, reverse=True)
    return build_alternation(sorted_patterns)

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
        r"cross[- ]border",
        r"repatriation",
        r"remeasurement",
        r"translation",  # Be careful, "translation of documents" exists, but usually accounting
        r"foreign\s+(?:currency|exchange|operations|subsidiaries|sales|revenue)",
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
    "kiloliters", "liters", "cubic", "gallons", "joules", "gigajoules"
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


def build_ir_regex() -> re.Pattern:
    core_terms = [
        "interest[- ]rate",
        "single[- ]currency",
        "SOFR",
        "SONIA",
        "LIBOR",
        "LIBOR[- ]based",
        "EURIBOR",
        "(?:treasury|forward|fixed|floating|variable|benchmark)[- ]rate",
    ]
    specific_phrases = [
        "zero[- ]coupon swap",
        "FRA",
        "treasury lock",
        "basis swap",
    ]
    pattern = build_smart_regex(
        core_terms, ALL_BASE_TYPES + ALL_SUFFIXES, specific_phrases
    )
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_fx_regex() -> re.Pattern:
    core_terms = [
        "foreign[- ]exchange",
        "forward[- ]exchange",
        "currency",
        "currency[- ]rate",
        "exchange[- ]rate",
        "FX",
        "forex",
        "cross[- ]currency",
        "multi[- ]currency",
    ]

    # --- DEFINE FX-SPECIFIC SAFE TYPES ---
    # 1. Start with the strictly safe stuff (Swaps, Forwards, Caps)
    fx_expanded_types = UNAMBIGUOUS_BASE_TYPES.copy()


    iso = build_currency_iso_pattern()
    name = build_currency_name_pattern()

    specific_phrases = [
        "NDF",
        "deliverable forwards?",
        "hedge of the net investment",
        "net investment hedges?",
        # Use fx_expanded_types here instead of UNAMBIGUOUS_BASE_TYPES
        f"{iso}\\s*(?:denominated|based|linked)?\\s*{build_alternation(fx_expanded_types)}",
        f"{name}\\s*(?:denominated|based)?\\s*{build_alternation(fx_expanded_types)}",
    ]

    pattern = build_smart_regex(
        core_terms, ALL_BASE_TYPES + ALL_SUFFIXES, specific_phrases
    )
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_cp_regex() -> re.Pattern:
    # 1. Base Terms: Generic + Specific List
    # Ensure "commodities" (plural) is covered in base
    base_commodities = ["commodity", "commodities"] + COMMON_COMMODITIES

    # 2. Modifiers: MUST include optional 's' for prices/costs to catch "Oil prices"
    modifiers = ["[- ]prices?", "[- ]costs?", "[- ]related", "[- ]based", "[- ]linked"]

    # 3. Generate Core Terms (e.g., "Gold", "Gold-linked", "Oil price")
    core_terms = [c for c in base_commodities] + [
        f"{c}{mod}" for c in base_commodities for mod in modifiers
    ]
    core_terms.append("fixed[- ]commodity")

    # 4. Define Safe Follow-up Instruments
    # We use ALL_BASE_TYPES (Swaps, Futures, Options, Forwards)
    # CRITICAL: We do NOT use ALL_SUFFIXES (Agreements, Contracts) here.
    # Why? "Gold Swaps" is a derivative. "Gold Contracts" is likely a physical supply deal.
    safe_cp_instruments = ALL_BASE_TYPES

    specific_phrases = [
        "commodity index",
        "weather derivatives?",
        # Add these to catch specific PPA nuances if needed:
        "power purchase agreements?",
    ]

    pattern = build_smart_regex(core_terms, safe_cp_instruments, specific_phrases)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_eq_regex() -> re.Pattern:
    core_terms = ["equity", "equity[- ]related"]

    # Custom base types for Equity to be safer
    eq_base_types = UNAMBIGUOUS_BASE_TYPES.copy()
    eq_base_types.extend(
        [
            "options?",  # Equity options (usually comp, but syntactically an instrument)
            "futures",  # MANDATORY PLURAL for Equity
        ]
    )

    pattern = build_smart_regex(core_terms, eq_base_types, [])  # Empty specific phrases
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_strict_gen_regex() -> tuple[re.Pattern, re.Pattern]:
    """
    Returns a tuple:
        (INSTRUMENT_REGEX, NOTIONAL_REGEX)

    INSTRUMENT_REGEX  → captures pure derivative instrument names (strict)
    NOTIONAL_REGEX    → captures notional amount/principal/value phrases
    Both use named groups for convenient extraction.
    """
    # ── 1. Strict instrument names (require a recognised base + suffix) ──
    base_strict = UNAMBIGUOUS_BASE_TYPES  # swaps?, forwards?, caps?, …
    suffix_strict = ALL_SUFFIXES  # agreements?, contracts?, instruments?, …

    instrument_parts = [
        f"{base}[- ]{suffix}" for base in base_strict for suffix in suffix_strict
    ]

    instrument_specific = [
        "total[- ]return swaps?",
        "cash flow hedges?",
        "fair value hedges?",
        "embedded derivatives?",
    ]

    instrument_pattern = build_alternation(instrument_parts + instrument_specific)

    INSTRUMENT_REGEX = re.compile(
        rf"\b(?P<instrument>{instrument_pattern})\b", re.IGNORECASE
    )

    # ── 2. Notional phrases (very high precision, no overlap with instruments) ──
    notional_variants = [
        r"notional\s+(?:amounts?|values?|principals?)\b",
        r"notional\s+(?:amount|value|principal)\s+(?:thereof|outstanding)?\b",
        r"(?:aggregate|total)\s+notional\s+(?:amount|value|principal)\b",
        r"notional\s+(?:of\s+)?(?:[\d,]+(?:\.\d+)?\s*(?:million|billion|trillion)?|approximately?\s*[\d,]+)",
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
        "derivative financial instruments?",
        "derivative (?:assets?|liabilities|gains?|losses?|positions?|contracts?|instruments?)",
        "(?:gain|loss) on derivatives?",
        "over[- ]the[- ]counter derivatives?",
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
# =============================================================================
# EXCLUSION PATTERNS (from filter_database.py)
# =============================================================================

# Section 1: Employee Equity Compensation
EQUITY_COMP_KEYWORDS = [
    "stock option",
    "stock award",
    "restricted stock",
    "RSU",
    "compensation",
    "employee",
    "share-based",
    "vesting",
    "exercisable",
    "stock purchase",
    "ESPP",
    "bonus",
    "salary",
    "wage",
    "dividend",
    "stock split",
    "stock dividend",
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
    r"FASB\s+(?:issued|has\s+issued|released|published)",
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
    r"(?:this|the)\s+(?:statement|standard|guidance|amendment)\s+(?:addresses|clarifies|amends)",
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
    pattern = build_alternation(
        [
            CLAUSE_1,
            CLAUSE_2,
            CLAUSE_3,
            CLAUSE_4,
            CLAUSE_5,
            CLAUSE_6,
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

EQUITY_COMP_KEYWORDS_WEBPAGE = [
    "stock (?:options?|awards?|splits?|dividends?|purchases?)",
    "restricted stock",
    "RSU",
    "compensation",
    "employee",
    "share[- ]based",
    "vesting",
    "exercisable",
    "ESPP",
    "bonus",
    "salary",
    "wage",
    "dividend",
    "shares",
    "share repurchase",
    "buyback",
    "warrant",
    "hedge fund",
    "pension",
    "renewal",
]

LEGAL_LITIGATION_KEYWORDS_WEBPAGE = [
    "lawsuit",
    "litigation",
    "arbitration",
    "(?:civil|legal|administrative|criminal) action",
    "officer",
    "director",
    "convicted",
    "judgement",
    "violated",
]

IGNORE_WORDS = EQUITY_COMP_KEYWORDS_WEBPAGE + LEGAL_LITIGATION_KEYWORDS_WEBPAGE
IGNORE_REGEX = re.compile(r"|".join(IGNORE_WORDS), re.IGNORECASE)

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
        fair\s+value\s+(?:asset|liabilit)|
        derivative.*(?:asset|liabilit)|designated|hedging\s+relationship
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
        fair\s+value.*(?:asset|liabilit)|
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

# State Descriptors (New)
ACTIVE_STATE_DESCRIPTORS = ["outstanding", "active", "remaining", "open"]

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
ACTIVE_STATE_PATTERN = build_alternation(ACTIVE_STATE_DESCRIPTORS)
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
    "EQUITY_COMP_KEYWORDS_WEBPAGE",
    "LEGAL_LITIGATION_KEYWORDS_WEBPAGE",
    "IGNORE_WORDS",
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
