from collections import defaultdict
from dataclasses import dataclass
import re
from typing import List, Optional, Tuple


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

def build_regex(keywords: list, ignore_case: bool = True) -> re.Pattern:
    """Build regex for that also builds the alternation."""
    # Add word boundaries (\b) around each keyword to prevent partial matches
    pattern = build_alternation(keywords)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE if ignore_case else 0)

# =============================================================================
# SHARED COMPONENTS (moved from filter_database.py)
# =============================================================================
# Comparison verbs phrases
COMPARISON_PHRASES = [
    r"compared to",
    r"versus",
    r"vs\.?",  # Abbreviated version
    r"as against",
    r"in comparison with",
    r"whereas",
    r"compared with",
    r"relative to",
    r"in contrast to",
    r"as opposed to",
    r"vis-à-vis",
    r"when compared with",
    r"from",  # "decreased to $X from $Y"
    r"but",
    r"however",
    r"whereas",
    r"although",
    r"though",
    r"while",
    r"yet",
]
# State Descriptors (New)
ACTIVE_STATE_DESCRIPTORS = ["outstanding", "active", "remaining", "open", "current(?:ly)?"]

ACTIVE_STATE_PATTERN = build_alternation(ACTIVE_STATE_DESCRIPTORS)
RISK_TERMS = [
    "risks?",
    "fluctuations?",
    "volatilit(?:y|ies)",
    "exposures?",
    "movements?",
    "variabilit(?:y|ies)",
    "changes?",
    "management?",
    "costs?",
    "prices?",
    "hedges?",
    "hedging?",
]
_RISK_ALTERNATION = build_alternation(RISK_TERMS)

# STRONG: Unambiguous indicators of active usage or transaction
USAGE_VERBS = [
    # Direct Usage
    r"use(?:s|d|ing)?",
    r"utiliz(?:e|es|ed|ing)",
    r"employ(?:s|ed|ing)?",
    # Possession / Holding
    r"hold(?:s|ing)?",
    r"held",
    r"have",
    r"maintain(?:s|ed|ing)?",
    r"possess(?:e|es|ed|ing)?",
]
ACTION_VERBS = [
    # Transactional (The "Smoking Gun")
    r"enter(?:s|ed|ing)?\s+(?:into)?",
    r"engag(?:e|es|ed|ing)\s+(?:in)?",
    r"transact(?:s|ed|ing)?",
    r"execut(?:e|es|ed|ing)",
] + USAGE_VERBS

STRONG_ACTION_VERBS = ACTION_VERBS + [
    r"issu(?:e|es|ed|ing)?",  # Active Management
    r"convert(?:s|ed|ing)?",
    r"continue\s+to",
    r"secured",
    r"participat(?:e|es|ed|ing)",
]  # NEW: For embedded derivatives/warrants, but separate against "FASB issued"
VERB_USE_REGEX = re.compile(
    r"\b" + build_alternation(ACTION_VERBS) + r"\b", re.IGNORECASE
)
# WEAK / PASSIVE: Legal or Accounting states that *imply* existence
# We include these because "carrying at fair value" implies you have it.
PASSIVE_STATE_VERBS = [
    r"hedg(?:e|es|ed|ing)",
    r"manag(?:e|es|ed|ing)",
    r"carr(?:y|ies|ied|ying)",  # "Carries at fair value"
    r"(?:a\s+)?party\s+to",  # "Is a party to interest rate swaps"
    rf"remained?\s+{ACTIVE_STATE_PATTERN}",  # "remained active/open/outstanding"
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
    "biodiesel",
    "biomass",
    "bunker fuel",
    "butane",
    "coal",
    "coking coal",
    "condensate",
    "crude oil",
    "diesel fuel",
    "diesel",
    "distillates",
    "electricity",
    "energy",
    "ethane",
    "ethanol",
    "fuel",
    "fuel oil",
    "gas",
    "gas oil",
    "gasoline",
    "heating oil",
    "jet fuel",
    "kerosene",
    "liquefied natural gas",
    "liquefied petroleum gas",
    "LNG",
    "LPG",
    "marine fuel",
    "naphtha",
    "natural gas",
    "natural gas liquids",
    "oil",
    "petroleum",
    "power",
    "propane",
    "renewable energy",
    "solar power",
    "thermal coal",
    "wind power",
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
    # Generic
    "commodity",
    "commodities",
]


# Minimum sentence length to consider (we use swaps is 12 chars and rarely ever occurs)
MIN_SENTENCE_LENGTH = 15
MAX_SENTENCE_LENGTH = (
    800  # A very long sentence is probably a table that became a sentence
)

# 1. Complex Debt Term (Requires Lookbehind)
# Helper for the base terms to avoid repetition
_DEBT_TERMS = r"(?:debts?|loans?|borrowings?|bonds?|senior notes?|notes?|debentures?)"

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

# 2. All Other IR Context Terms (No Lookbehind Required)
IR_OTHER_TERMS = [
    # Debt + Payment Combinations (Strong IR signals)
    rf"{_DEBT_TERMS}\s+payables?",
    r"interest\s+payables?",
    rf"(?:long|short)[- ]term\s+{_DEBT_TERMS}",
    rf"(?<!foreign[- ])interest[- ]rate\s+{_RISK_ALTERNATION}",
    r"credit\s+facilit(?:y|ies)",
    r"revolving\s+credits?",
    r"term\s+loans?",
    r"subordinated\s+notes?",
    r"commercial\s+papers?",
    r"capital\s+leases?",
    r"mortgages?",
    # Rate Types & Benchmarks
    r"(?:(?:floating|variable|fixed|benchmark|(?<!currency[- ])interest|treasury|forward|prime)[- ]rates?|fed(?:eral)?\s+funds\s+rates?)",
    r"SOFR",
    r"SONIA",
    r"LIBOR",
    r"EURIBOR",
    r"ESTR",
    r"EONIA",
    r"TONAR",
    r"BBSW",
    r"CIBOR",
    r"STIBOR",
    r"HIBOR",
    r"TIBOR",
    r"PRIBOR",
    r"MOSPRIME",
    # Mechanics (High Precision)
    r"(?:pay|receive)[- ](?:fixed|variable|floating)",
    r"interest\s+payments?",
    r"basis\s+points?",
    r"weighted\s+average\s+interest",
]

IR_CONTEXT = f"(?:{IR_DEBT_LOOKBEHIND_TERM}|{build_alternation(IR_OTHER_TERMS)})"


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
    Currency("PHP", "Philippine Peso", "₱", "Philippine", "Philippines"),
    Currency("VND", "Vietnamese Dong", "₫", "Vietnamese", "Vietnam", symbol_first=False),
    Currency("IDR", "Indonesian Rupiah", "Rp", "Indonesian", "Indonesia"),
    Currency("PKR", "Pakistani Rupee", "₨", "Pakistani", "Pakistan"),
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
        "AED",
        "UAE Dirham",
        "د.إ",
        "Emirati",
        "United Arab Emirates",
        symbol_first=False,
    ),
    Currency("SAR", "Saudi Riyal", "ر.س", "Saudi", "Saudi Arabia", symbol_first=False),
    Currency("ZAR", "South African Rand", "R", "South African", "South Africa"), # added _ to prevent R from matching
    Currency("ILS", "Israeli Shekel", "₪", "Israeli", "Israel"),
    Currency("KWD", "Kuwaiti Dinar", "د.ك", "Kuwaiti", "Kuwait", symbol_first=False),
]


all_currencies = (
    major_currencies
    + european_currencies
    + asian_currencies
    + americas_currencies
    + other_currencies
)

def build_currency_names_regex() -> re.Pattern:
    terms = []
    for currency in all_currencies:
        terms.append(re.escape(currency.full_name))
    return build_regex(terms)
CURRENCY_NAMES_REGEX = build_currency_names_regex()


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
                adj_esc + r"\s+(?:operations?|subsidiar(?:y|ies)|entit(?:y|ies))",
                adj_esc + r"\s+(?:revenue|sales|income|earnings)",
                adj_esc + r"\s+(?:assets?|liabilit(?:y|ies))",
                adj_esc + r"\s+(?:markets?|econom(?:y|ies)|busine(?:ss|sses))",
                adj_esc + rf"\s+{_RISK_ALTERNATION}",
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
    terms.extend(["foreign[- ]denominated"])
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
        r"translations?",  # Be careful, "translation of documents" exists, but usually accounting
        r"foreign\s+(?:currenc(?:y|ies)|exchanges?|operations?|subsidiar(?:y|ies)|sales?|revenues?)",
        # 1. Operations & Accounting
        r"functional\s+currenc(?:y|ies)",
        r"reporting\s+currenc(?:y|ies)",
        r"local\s+currenc(?:y|ies)",
        r"foreign\s+currenc(?:y|ies)",
        r"remeasurements?",
        r"(?:currency|foreign)\s+exchanges?",
        r"exchange\s+rates?",
        r"translation\s+adjustments?",
        rf"exchange\s+rate\s+{_RISK_ALTERNATION}",
        r"foreign\s+interest\s+rates?",
        rf"foreign\s+interest[- ]rate\s+{_RISK_ALTERNATION}",
        r"currenc(?:y|ies)\s+exchange\s+rates?",
        rf"currenc(?:y|ies)\s+{_RISK_ALTERNATION}",
        # 2. Transactional Context
        r"cross[- ]border",
        r"repatriation",
        r"intercompany",  # Strong signal for FX swaps
        r"denominated\s+in",
        # 3. Specific FX Instruments Keywords
        r"spot\s+rate",
        r"non[- ]deliverable",
        rf"foreign\s+{_DEBT_TERMS}",
        rf"foreign\s+currency\s+{_DEBT_TERMS}",
        # 1. Catch "Euro-denominated debt"
        rf"(?:[a-z]+[- ])?denominated\s+{_DEBT_TERMS}",
        # 2. Catch "Debt denominated in..." (CRITICAL for preventing IR false positives)
        rf"{_DEBT_TERMS}\s+denominated\s+(?:in|by)",
    ]

    return currency_specific_terms + generic_fx_terms


CURRENCY_SYMBOL_PATTERN = build_currency_symbol_pattern()
# Generic hedging context (required for generic matches)
hedging_terms = [
    r"relationships?",
    r"strateg(?:y|ies)",
    r"activit(?:y|ies)",
    r"programs?",
    r"positions?",
    r"assets?",
    r"liabilit(?:y|ies)",
    r"polic(?:y|ies)",
    r"transactions?",
    r"designations?",
    r"effectiveness",
    r"ineffectiveness",
    r"objectives?",
    r"instruments?",
    r"arrangements?",
    r"exposures?",
    r"derivatives?",
    r"items?",
    r"horizons?",
    r"document(?:s|ations?)",
    r"terms?",
    r"accounting",
]
hedge_phrases = build_alternation(hedging_terms, sort_longest_first=True)
SOFT_GEN_TERMS = [
    r"(?:instruments?|contracts?) are designated",
    r"(?:ineffective|effective) portions?",
    # Expanded Hedging Noun Contexts (Strategy, Activity, Program, etc.)
    rf"hedg(?:es?|ing)\s+{hedge_phrases}",
    r"change in fair value of derivatives?",
    r"derivative expenses?",
    r"designated as (?:a )?hedg(?:es?|ing)",
    r"(?:gain|loss) on derivatives?",
    r"derivative\s+assets?|derivative\s+liabilit(?:y|ies)",
    r"fair\s+value\s+hedges?",
    r"cash\s+flow\s+hedges?",
]
VALUATION_MODELS = [
    # The Gold Standard for Equity Options/Warrants
    r"Black[- ]Scholes(?:[- ]Merton)?",
    r"\bBSM\b",  # Abbreviation for Black-Scholes-Merton
    # Used for path-dependent equity features (e.g., Market conditions, TSR awards)
    r"Monte[- ]Carlo(?:[- ]simulations?)?",
    # Used for American options (exercisable early) and Convertibles
    r"Binomial(?:[- ]Lattice)?\s+models?",
    r"Lattice\s+models?",
    # General descriptive
    r"option[- ]pricing\s+models?",
]
VALUATION_MODELS_REGEX = re.compile(
    r"\b" + build_alternation(VALUATION_MODELS) + r"\b", re.IGNORECASE
)
RISK_MANAGEMENT_TERMS = [
    r"to\s+hedge",
    r"mitigat(?:e|es|ed|ing)",
    r"protect(?:s|ed|ing)?",
    r"manage(?:s|d|ing)?",
    r"exposures?",
    r"exposed\s+to",
    r"risk\s+management",
    rf"economic\s+{_RISK_ALTERNATION}",
    # --- Safe for Phase 1 Contextual Capture ---
    rf"(?:market|rate|currency|credit|equity|price)[ -]{_RISK_ALTERNATION}",
    r"fluctuations?",  # e.g., "protect against fluctuations"
    r"volatility",  # e.g., "manage volatility"
    r"stabiliz(?:e|es|ed|ing)",
    r"to\s+(?:limit|control|reduce|offset)",
]
RISK_MANAGEMENT_REGEX = build_regex(RISK_MANAGEMENT_TERMS)
HEDGING_CONTEXT_TERMS = (
    [
       r"bifurcat(?:ed|ion|ing)",
    ]
    + SOFT_GEN_TERMS + RISK_MANAGEMENT_TERMS
    + VALUATION_MODELS
)

# Strict commodity units (high confidence)
CP_UNITS_STRICT = [
    "barrels", "bbl", "bbl/d", "btu", "gj", "mmbtu", "mmbtu/h", "mwh",
    "bushels", "cwt", "hundredweights", "pecks", "ounces", "pounds",
    "tons", "tonne", "long tons", "short tons", "joules", "gigajoules",
    "mcf", "mmcf", "bcf", "therm", "therms", "dth", "dekatherms",
]
CP_UNITS = [
    "units", "items", "packages", "containers", "loads",
    "gallons", "gal", "liters", "ltr",
    "cubic meters", "m3", "cubic feet", "ft3",
    "hectoliters", "hL", "kiloliters", "kL",
    "megaliters", "ML", "gigaliters", "GL",
    "board foot", "bf", "sheets", "coils", "bundles", "pallets",
    "sacks", "bales", "heads", "carats", "ingots", "bars",
] + CP_UNITS_STRICT
COMMODITY_UNIT_PATTERN = build_alternation(CP_UNITS)
CP_CONTEXT_TERMS = [
    # Power Grids / ISOs (Strongest context for "power swaps")
    "PJM",
    "ERCOT",
    "MISO",
    "SPP",
    "CAISO",
    "NYISO",
    "ISO-NE",
    # Load Types
    "baseload",
    "peak load",
    "off-peak",
    "on-peak",
    "capacity",
    "power generation",
    "power assets",
    # Gas/NGL Hubs & Benchmarks
    "Henry Hub",
    "WTI",
    "West Texas Intermediate",
    "Cushing",
    "Mont Belvieu",
    "TTF",
    "JKM",
    "Dominion South",
    "Platts",
    "Argus",
    "OPIS",  # Pricing reporting agencies
    "Brent"
    # Exchanges
    # Exchanges
    "LME",
    "London Metal Exchange",
    "CBOT",
    "Chicago Board of Trade",
    "ICE Futures",
    "Intercontinental Exchange",
    "COMEX",
    "NYMEX",
] + COMMON_COMMODITIES + CP_UNITS_STRICT

EQ_CONTEXT_TERMS = [
    # --- A. Core Prices & Markets ---
    r"stock\s+prices?",
    r"share\s+prices?",
    r"stock\s+markets?",
    r"market\s+index(?:es)?",
    # --- B. Specific Indices ---
    r"S\&P\s+500",
    r"Nasdaq(?:\s+Composite|\s+Index)?",
    r"Dow\s+Jones(?:\s+Industrial\s+Average|\s+Index)?",
    r"Russell\s+2000",
    # --- C. Equity Components ---
    r"equity\s+(?:awards?|grants?|compensation|options?|derivatives?|capital)",
    r"equity\s+securit(?:y|ies)",
    r"dividend\s+yields?",
    r"(?:preferred|common)\s+stock",
    # --- D. Structures & Events ---
    r"stock\s+warrants?",
    rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))",
    r"initial\s+public\s+offering|IPO",
    r"primary\s+market|secondary\s+market",
    r"accelerated\s+share\s+repurchases?",  # ASR is a derivative
    # --- E. Risk Integration (Smart Expansion) ---
    rf"(?:stock|share|equity)\s+{_RISK_ALTERNATION}",
    # --- F. Fallback ---
    r"stock",  # Careful, but usually okay in context
]

EQ_CONTEXT_TERMS += VALUATION_MODELS

_CR_LINKED_DEBT = rf"credit[- ]linked\s+{_DEBT_TERMS}"

CR_CONTEXT_TERMS = [
    # --- A. Explicit Instruments (Broad Match) ---
    r"credit[- ]default",  # Matches "credit default swap" (Safe)
    r"total[- ]return",  # Matches "total return swap" (Safe)
    _CR_LINKED_DEBT,  # "credit-linked notes" (Safe)
    r"basket[- ]default",  # "basket default swap" (Safe)
    r"first[- ]to[- ]default",  # (Safe)
    # REPLACEMENT FOR RISK ALTERNATION:
    # "Credit Protection" implies a transfer of risk (derivative/insurance), whereas "Credit Risk" just implies exposure.
    r"credit[- ](?:protections?|derivatives?|linked|slope|curve|tranche)",
    # --- B. Indices (Highly Specific - Keep these) ---
    r"CDX",
    r"iTraxx",
    r"Markit\s+CDX",
    r"credit\s+indices",
    r"credit\s+index",
    # --- C. Mechanics (Refined) ---
    # "Reference Entity" is the specific legal term in a CDS contract.
    r"reference\s+(?:entit(?:y|ies)|obligations?)",
    # "Protection Seller/Buyer" is unambiguous CDS terminology.
    r"protection\s+(?:buyer|seller|sold|bought)",
    # "Credit Event" is the ISDA trigger (Bankruptcy, Failure to Pay).
    r"credit\s+events?",
    r"recovery\s+rates?",  # Specific to CDS valuation
]

# Compile the Regex
CR_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(CR_CONTEXT_TERMS) + r"\b", re.IGNORECASE
)

IR_CONTEXT_REGEX = re.compile(r"\b" + IR_CONTEXT + r"\b", re.IGNORECASE)

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
    "cr": CR_CONTEXT_REGEX,
    "gen": HEDGING_CONTEXT_REGEX,
}


# =============================================================================
# REGEX BUILDERS (moved)
# =============================================================================
PHYSICAL_COMMERCIAL_TERMS = [  # words against "oil forward shipment, or deliverable forward receipt" from being matched
    "delivery",
    "purchase",
    "order",
    "sales?",
    "supply",
    "confirmation",
    "invoice",
    "shipment",
    "receipt",
    "inventory",
    "liability",  # Forward liability
    "stock",
    "looking",  # Just added it here against forward-looking
]
PHYSICAL_DELIVERY_PATTERN = build_alternation(
    PHYSICAL_COMMERCIAL_TERMS, sort_longest_first=True
)

PHYSICAL_INVENTORY_TERMS = []  # "capacity forward contract?"

# Negative lookahead: forward NOT followed by physical keywords
FORWARD_NOT_PHYSICAL_AHEAD = rf"(?![- ](?:{PHYSICAL_DELIVERY_PATTERN}))"
SPECIAL_BASE = [
    "call options?",
    "put options?",
    "basis swaps?",
    "total[- ]return swaps?",
    "barrier options?",
    "asian options?",
    "bermuda options?",
    "variance swaps?",
    "volatility swaps?",
    "swaptions?",
    "basket options?",  # Generic multi-asset
    "rainbow options?",  # Generic multi-asset
    "lookback options?",
    "exotic options?",
]
UNAMBIGUOUS_BASE_TYPES = [
    "swaps?",
    rf"forwards?{FORWARD_NOT_PHYSICAL_AHEAD}",
    "collars?",
    "derivatives?",
    "hedges",  # plural form
    "futures",  # plural form
] + SPECIAL_BASE

AMBIGUOUS_BASE_TYPES = [
    "futures?",
    "options?",
    "hedging",
    "locks?",
    "caps?",
    "floors?",
    "hedges?",
    "puts?",
    "calls?",
    "straddles?",
    "strangles?",
]


ALL_BASE_TYPES = UNAMBIGUOUS_BASE_TYPES + AMBIGUOUS_BASE_TYPES
HIGH_PRECISION_SUFFIXES = re.compile(
    r"\b" + build_alternation(UNAMBIGUOUS_BASE_TYPES) + r"\b", re.IGNORECASE
)
ALL_SUFFIXES = [
    "agreements?",
    "contracts?",
    "commitments?",
    "instruments?",
    "arrangements?",
    "options?",
]


# =============================================================================
# TABLE SPECIFIC REGEX
# =============================================================================
def build_table_regex() -> re.Pattern:
    """
    A stricter regex for table filtering that eliminates singular noise
    (future, option, forward) but keeps the plurals often found in headers.
    """

    # 1. Safe Plurals (Standalones that are safe in tables)
    # Note: 'swaps' and 'derivatives' are already in ALL_REGEX via GEN_REGEX
    # We add the others that are usually unsafe singular but safe plural.
    table_safe_plurals = [
        "futures",
        rf"(?<!carry\s)forwards",
        "hedges",
        "collars",
        "swaptions",
        "derivatives",
        "swaps",
        "puts",
        "calls",
    ] + SPECIAL_BASE

    plural_pattern = build_alternation(table_safe_plurals, sort_longest_first=True)

    return re.compile(rf"\b{plural_pattern}\b", re.IGNORECASE)


TABLE_REGEX = build_table_regex()


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
        rf"(?:{core_pattern})"  # e.g., "interest rate"
        r"[- ]"  # MANDATORY separator (space or hyphen)
        rf"(?:{context_terms})"  # MANDATORY: base or (base + suffix)
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
BASE_REGEX = re.compile(r"\b" + base_alternation + r"\b", re.IGNORECASE)
safe_base_alternation = build_alternation(UNAMBIGUOUS_BASE_TYPES, True)
suffix_alternation = build_alternation(ALL_SUFFIXES, True)
standalone_alternation = build_alternation(ALL_SUFFIXES + UNAMBIGUOUS_BASE_TYPES, True)
unsafe_standalone_alternation = build_alternation(ALL_SUFFIXES + ALL_BASE_TYPES, True)
# ----------------------------------------------------------------------------------


def expand_instruments(
    unsafe: bool = True,
    exclude_standalone_suffixes: bool = False,
    additional_standalone_suffixes: Optional[List[str]] = None,
    additional_bases: Optional[List[str]] = None,
) -> str:
    """
    Creates an optimized alternation pattern.

    Fixed Logic:
    1. Ensures (OldBase OR NewBase) + Suffix is treated as a single unit.
    2. Ensures additional_bases are NOT matched as standalone words.
    """

    # 1. Construct the Base Component for the Combined Pattern
    # We wrap (Existing | New) together so the suffix applies to BOTH.
    if additional_bases:
        new_base_alt = build_alternation(additional_bases, True)
        # Result: (?:(?:existing_bases)|(?:new_bases))
        effective_base_pattern = rf"(?:{base_alternation}|{new_base_alt})"
    else:
        effective_base_pattern = base_alternation

    # 2. Base + Suffix Combination (Highest priority)
    # The [- ] separator now applies to everything in effective_base_pattern
    # Matches: "swap agreement", "protection contract"
    combined_pattern = rf"(?:{effective_base_pattern}[- ]{suffix_alternation})"

    # 3. Standalone Term (Lower priority)
    # Note: We DO NOT add additional_bases here. They will fail to match if they lack a suffix.
    if not exclude_standalone_suffixes:
        base_standalone = (
            unsafe_standalone_alternation if unsafe else standalone_alternation
        )
    else:
        base_standalone = base_alternation if unsafe else safe_base_alternation

    # 4. Integrate Additional Standalone SUFFIXES
    extras = []
    if additional_standalone_suffixes:
        extras.append(build_alternation(additional_standalone_suffixes, True))

    if extras:
        # Append extras to the standalone pattern
        extras_pattern = "|".join(extras)
        final_standalone = rf"{base_standalone}|{extras_pattern}"
    else:
        final_standalone = base_standalone

    # 5. Final Assembly (Max Munch: Combined first)
    return rf"{combined_pattern}|{final_standalone}"


def build_cr_regex() -> Tuple[re.Pattern, re.Pattern]:
    """
    Returns a tuple: (strict_cr_regex, soft_cr_regex)

    STRICT: High-precision credit derivative instrument patterns
    SOFT: Contextual credit derivative instrument patterns

    Examples matched:
      - "credit default swap"
      - "basket default swap"
      - "first-to-default swap"
    """

    # --- 1. Core Prefix Terms ---
    strict_core_terms = [
        "(?:credit|basket|first[- ]to[ -])[- ](?:default|linked|based)",
    ]
    strict_core_alt = build_alternation(strict_core_terms, sort_longest_first=True)

    soft_core_terms = strict_core_terms
    soft_core_alt = build_alternation(soft_core_terms, sort_longest_first=True)

    # --- 2. Specific Instrument Phrases (Max Munch) ---
    cln_pattern = rf"credit[- ]linked\s+{_DEBT_TERMS}"
    specific_phrases = [cln_pattern, "credit swaps"]  # None for this one

    sorted_specific_phrases = sorted(
        specific_phrases, key=lambda x: (-len(x), -x.count(r"\s+"))
    )

    # --- 3. Instrument Fragments ---

    strict_instrument_fragment = expand_instruments(
        unsafe=False,
        exclude_standalone_suffixes=True,
        additional_standalone_suffixes=["contracts?", "options?", "agreements?"],
    )

    soft_instrument_fragment = expand_instruments(unsafe=True)

    # --- 4. Build Patterns ---

    strict_pattern = build_smart_regex(
        [strict_core_alt],
        strict_instrument_fragment,
        sorted_specific_phrases,
    )
    strict_cr_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    soft_pattern = build_smart_regex(
        [soft_core_alt],
        soft_instrument_fragment,
        sorted_specific_phrases,
    )
    soft_cr_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)

    return strict_cr_regex, soft_cr_regex


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
        rf"(?:{word1})[- ](?:{word1})[- ](?:{compound})[- ](?:{word2_alt})[- ]{word3}",  # forward foreign cross currency exchange rate
        rf"(?:{word1})[- ](?:{word1})[- ](?:{word2_alt})[- ]{word3}",  # forward foreign exchange rate
        # Shorter, common combinations
        rf"(?:{word1})[- ](?:{word2_alt})[- ]{word3}",  # forward/foreign currency/exchange rate
        rf"(?:{compound})[- ](?:{word2_alt})[- ]{word3}",  # cross currency exchange rate
        rf"(?:{word1})[- ](?:{word1})[- ](?:{word2_alt})",  # forward foreign exchange/currency
        rf"(?:{compound})[- ](?:{word2_alt})",  # cross currency exchange
        # Two-word descriptive terms
        rf"(?:{word1})[- ](?:{word2_alt})",  # forward exchange, foreign currency
        rf"(?:{compound})",  # cross currency
        # Single-word descriptive terms (low priority, included for completeness)
        r"FX",
        r"forex",
    ]

    # CRITICAL: We let build_alternation sort this entire list by length/word count
    # to enforce Max Munch, ensuring "forward foreign currency" matches before "forward".
    return build_alternation(patterns, sort_longest_first=True)


def _replace_dynamic_placeholder(
    phrases: List[str], replacement_fragment: str
) -> List[str]:
    """Replaces the '__DYNAMIC__' placeholder in a list of phrase templates."""
    return [p.replace(r"__DYNAMIC__", replacement_fragment) for p in phrases]


def build_fx_regex() -> Tuple[re.Pattern, re.Pattern]:
    # --- 1. Helper Definitions ---
    currency_name_alternation = build_currency_name_pattern()
    fx_dynamic_pattern = build_fx_dynamic_pattern()

    # --- 2. Build Core Terms (Prefixes) ---
    # Precise prefixes (e.g., 'forward foreign currency')
    strict_core_terms = [
        rf"(?:{fx_dynamic_pattern})",
        r"cross[- ]currency\s+interest\s+rate",
        r"cross[- ]currency\s+interest",
    ]
    # Broad prefixes (e.g., 'currency', 'fx')
    soft_core_terms = [
        r"foreign\s+exchange",
        r"(?<!single[- ])currency",
        r"fx",
        r"exchange",
        r"forex",
    ]
    soft_core_alternation = build_alternation(soft_core_terms, sort_longest_first=True)

    forward_types = [
        "non[- ]deliverable",
        "deliverable",
        "deal[- ]contingent",
    ]
    forward_types_alternation = build_alternation(
        forward_types, sort_longest_first=True
    )

    # -------------------------------------------------------------------------
    # --- A. UNIFIED TEMPLATE PHRASES ---
    # -------------------------------------------------------------------------

    # Templates for phrases that attach instrument bases to currency context
    dynamic_templates = [
        rf"(?:{currency_name_alternation}[- ](?:denominated|linked|related|based))[- ](?:__DYNAMIC__)",
        rf"(?:{currency_name_alternation})[- ](?:__DYNAMIC__)",
        rf"(?<!single[- ])currency[- ](?:__DYNAMIC__)",
    ]

    # Fixed (non-dynamic) specific phrases
    fixed_phrases = [
        # Explicitly safe Forward Types
        rf"(?:{forward_types_alternation})\s+(?:forwards?|options?)\s+(?:{suffix_alternation})",
        rf"(?:{forward_types_alternation})\s+(?:forwards?|options?)",
        # Specific FX Instrument Names/Hedges
        r"hedges?\s+of\s+(?:the\s+)?net\s+investments?",
        "net investment hedges?",
    ]

    # -------------------------------------------------------------------------
    # --- B. STRICT Pattern Construction (High Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for dynamic replacement: safe bases only (no suffixes as standalones, but include safe ones)
    strict_dynamic_fragment = expand_instruments(
        unsafe=False,
        exclude_standalone_suffixes=True,
        additional_standalone_suffixes=["contracts?", "options?"],
    )

    # 1. Substitute the dynamic fragment into the templates
    strict_dynamic_phrases = _replace_dynamic_placeholder(
        dynamic_templates, strict_dynamic_fragment
    )

    # 2. Combine and sort all specific phrases
    strict_specific_phrases = sorted(
        strict_dynamic_phrases + fixed_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:")),
    )

    # 3. Final pattern build
    strict_instrument_fragment = expand_instruments(
        unsafe=False
    )  # Safe standalone bases allowed here
    strict_pattern = build_smart_regex(
        strict_core_terms,  # Precise prefixes
        strict_instrument_fragment,  # Safe bases only
        strict_specific_phrases,  # Final list of specific phrases
    )
    strict_fx_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # --- C. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for dynamic replacement: includes all instrument bases (unsafe=True, exclude standalones)
    soft_dynamic_fragment = expand_instruments(
        unsafe=True, exclude_standalone_suffixes=True
    )

    # 1. Substitute the dynamic fragment into the templates
    soft_dynamic_phrases = _replace_dynamic_placeholder(
        dynamic_templates, soft_dynamic_fragment
    )

    # 2. Combine and sort all specific phrases
    soft_specific_phrases = sorted(
        soft_dynamic_phrases + fixed_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:")),
    )

    # 3. Final pattern build
    soft_instrument_fragment = expand_instruments(
        unsafe=True
    )  # Unsafe standalone bases allowed here
    soft_pattern = build_smart_regex(
        [soft_core_alternation],  # Broad prefixes
        soft_instrument_fragment,  # Unsafe bases included
        soft_specific_phrases,  # Final list of specific phrases
    )
    soft_fx_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)

    # Return the tuple of (strict, soft)
    return strict_fx_regex, soft_fx_regex


def build_cp_regex() -> Tuple[re.Pattern, re.Pattern]:
    # --- 1. Helper Definitions ---

    # Sorted alternation of all commodities (Max Munch applied internally)
    commodity_alternation = build_alternation(
        COMMON_COMMODITIES, sort_longest_first=True
    )
    spread_types = [
        "crack",
        "spark",
        "dark",
    ]
    spread_types_alternation = build_alternation(spread_types, sort_longest_first=True)
    # Optimized modifiers (Max Munch applied internally)
    modifier_terms = [
        "prices?",
        "costs?",
        "related",
        "based",
        "linked",
        "index",
        rf"{spread_types_alternation}\s+spreads?",
        "spreads?",
        "capacity",
    ]
    modifier_alternation = build_alternation(modifier_terms, sort_longest_first=True)

    # 2. Generate Core Terms (Prefixes) for STRICT pattern

    # Optimized Core: Commodity Name + Modifier (e.g., Crude Oil[- ]price)
    # This is the original, high-precision core alternation
    strict_core_patterns = [
        rf"fixed[- ](?:{commodity_alternation})[- ](?:{modifier_alternation})",
        rf"(?:{commodity_alternation})[- ](?:{modifier_alternation})",
        rf"(?:{commodity_alternation})",
    ]
    strict_core_alternation = build_alternation(
        strict_core_patterns, sort_longest_first=True
    )

    # 3. Unified Specific Phrases
    # These contain the max-munch phrases and apply to both strict and soft.
    specific_phrases = [
        r"weather derivatives?",  # raw string for regex
        r"power purchase agreements?",  # raw string for regex
        # LONGEST FIRST: spreads with suffix (uses standalone_alternation for bases/suffixes)
        rf"(?:{spread_types_alternation})\s+spreads?\s+(?:{standalone_alternation})",
        # SHORTER: spreads alone
        rf"(?:{spread_types_alternation})\s+spreads?",
        r"fixed[- ]price swaps?"
    ]

    # Pre-sort longest-first for Max Munch precedence
    sorted_specific_phrases = sorted(
        specific_phrases, key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:"))
    )

    # -------------------------------------------------------------------------
    # --- A. STRICT Pattern Construction (High Precision) ---
    # -------------------------------------------------------------------------

    # Fragment used for attachment to core terms: Requires an instrument base, excludes standalones.
    # This maintains the high precision of the original function's core logic.
    strict_attachment_fragment = expand_instruments(
        unsafe=False, exclude_standalone_suffixes=True
    )

    strict_pattern = build_smart_regex(
        [strict_core_alternation],  # Highly precise core prefixes
        strict_attachment_fragment,  # Must attach a derivative base (e.g., 'swap' or 'future')
        sorted_specific_phrases,  # All high-priority explicit phrases
    )
    strict_cp_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # --- B. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    # Fragment used for general pattern combination: Includes all derivative terminology.
    soft_instrument_fragment = expand_instruments(unsafe=True)

    # Soft pattern combines simple prefixes ('commodity', 'CP') with the full range of instrument terms.
    soft_pattern = build_smart_regex(
        [strict_core_alternation],  # Simple prefixes
        soft_instrument_fragment,  # Full range of instruments (e.g., 'options', 'futures')
        sorted_specific_phrases,  # All high-priority explicit phrases
    )
    soft_cp_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)

    # Return the tuple of (strict, soft)
    return strict_cp_regex, soft_cp_regex


def build_eq_regex() -> Tuple[re.Pattern, re.Pattern]:
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
        rf"{warrant}\s+(?:{derivative}[- ]{liability}|{liability}|{derivative})",
        # Inverted: liability/derivative + warrant
        rf"(?:{liability}|{derivative})[- ]classified\s+{warrant}",
        # Classified context: warrant...classified as (liability|derivative)
        rf"(?:{derivative}\s+)?{warrant}.*classified\s+as\s+(?:a\s+)?(?:{derivative}[- ]{liability}|{derivative}|{liability})",
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
    soft_instrument_fragment = expand_instruments(unsafe=True)

    soft_pattern = build_smart_regex(
        [strict_core_alternation],
        soft_instrument_fragment,  # Full range of instruments (e.g., 'options', 'warrants' standalones)
        sorted_specific_phrases
        + [
            rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))",
        ],
    )
    soft_eq_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)

    # Return the tuple of (strict, soft)
    return strict_eq_regex, soft_eq_regex


def build_strict_gen_regex() -> tuple[re.Pattern, re.Pattern]:
    """
    Returns a tuple:
        (INSTRUMENT_REGEX, NOTIONAL_REGEX)

    INSTRUMENT_REGEX  → captures ONLY safe derivative patterns
    NOTIONAL_REGEX    → captures notional amount/principal/value phrases
    """

    # SAFE BASES: Low false-positive risk
    safe_bases = ["swaps", r"(?<!\bits\s)derivatives", "futures"]

    # UNSAFE STANDALONE: Require suffix
    unsafe_alone = [
        "swap",
        "cap",
        "floor",
        "collar",
        "derivative",
        "hedge",
        "hedging",
        "lock",  # plural form
        "futures",  # plural form
    ]

    # SPECIAL BASES: safe as well
    special_bases = SPECIAL_BASE

    # SAFE SUFFIXES
    suffixes = [
        "agreements?",
        "contracts?",
        "instruments?",
        "arrangements?",
    ]

    safe_bases_alt = build_alternation(safe_bases, sort_longest_first=True)
    unsafe_alone_alt = build_alternation(unsafe_alone, sort_longest_first=True)
    special_bases_alt = build_alternation(special_bases, sort_longest_first=True)
    suffix_alt = build_alternation(suffixes, sort_longest_first=True)

    # CRITICAL FIX: Reorder to enforce MAX MUNCH
    # Pattern 1: Safe bases WITH suffix (HIGHEST PRIORITY - longest match first)
    pattern1 = rf"{safe_bases_alt}[- ]{suffix_alt}"

    # Pattern 2: Unsafe bases MUST have suffix
    pattern2 = rf"{unsafe_alone_alt}[- ]{suffix_alt}"

    # Pattern 3: Safe bases standalone (LOWER PRIORITY)
    pattern3 = safe_bases_alt

    # Pattern 4: Special bases (complete phrases)
    pattern4 = special_bases_alt

    # Combine with specific phrases first (highest priority)
    # Combine with specific phrases first (highest priority)
    specific_phrases = [
        "cash flow hedges?",
        "fair value hedges?",
        "embedded derivative (?:asset|liabilit(?:y|ies))",
        "embedded derivatives?",
        "over[- ]the[- ]counter derivatives?",
        "derivative financial instruments?",
        "financial derivatives?",
        # Derivative/Swap Balance Sheet Items
        "derivative assets?",
        "derivative liabilit(?:y|ies)",
        "swap liabilit(?:y|ies)",
        "swap assets?",  # <-- NEW
        # Hedging Balance Sheet Items
        "hedging assets?",  # <-- NEW
        "hedging liabilit(?:y|ies)",  # <-- NEW
        # Explicit "Safe" Variants for Ambiguous Bases
        "forward contracts?",
        "forward agreements?",  # <-- NEW
        "option contracts?",  # <-- NEW
    ]
    specific_alt = build_alternation(specific_phrases, sort_longest_first=True)

    # FINAL: Specific phrases FIRST, then combined+suffix patterns, then standalone
    instrument_pattern = rf"{specific_alt}|{pattern4}|{pattern1}|{pattern2}|{pattern3}"

    INSTRUMENT_REGEX = re.compile(
        rf"\b(?P<instrument>{instrument_pattern})\b", re.IGNORECASE
    )

    # Notional phrases (will catch unsafe variants as standalone if important)
    notional_variants = [
        r"notional\s+(?:amounts?|values?|principals?)",
        r"notional",
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
    # Combine and prioritize based on length/specificity
    pattern = build_alternation(SOFT_GEN_TERMS)

    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_derivative_standards() -> re.Pattern:
    stds = [
        # US GAAP - Derivatives & Hedging
        r"ASC\s+815",  # The big one (Derivatives and Hedging)
        r"SFAS\s+133",  # The legacy big one
        r"FAS\s+133",
        r"Statement\s+133",
        # US GAAP - Fair Value (Strong signal when combined with "Option/Warrant")
        r"ASC\s+820",
        r"SFAS\s+157",
        # US GAAP - Distinguishing Liabilities from Equity (Crucial for Warrants)
        r"ASC\s+480",  # Distinguishing Liabilities from Equity
        r"SFAS\s+150",
        # International (IFRS)
        r"IFRS\s+9",  # Financial Instruments
        r"IAS\s+39",  # Legacy Financial Instruments
        r"IAS\s+32",  # Presentation (Liability vs Equity)
        r"SFAS\s+150",
        # --- NEW: EITF 00-19 (The "Warrant Liability" Key) ---
        # Matches: "EITF 00-19", "EITF Issue No. 00-19", "EITF 0019"
        # Note: We allow flexible separators between '00' and '19'
        r"EITF\s+(?:Issue\s+)?(?:No\.?\s+)?00[-–—\s]?19",
        # --- NEW: The Codified Version (ASC 815-40) ---
        # EITF 00-19 was codified into ASC 815-40 "Contracts in Entity's Own Equity"
        r"ASC\s+815[-–—\s]?40",
        # Just adding this here
        r"bifurcat(?:ed|ion|ing)",
    ]
    pattern = build_alternation(stds)
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


DER_STD_REGEX = build_derivative_standards()


def build_loose_gen_regex() -> re.Pattern:
    bases = ALL_BASE_TYPES.copy()
    bases.remove("hedging")
    pattern = build_alternation(bases + ALL_SUFFIXES + ["warrants"])
    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


# =============================================================================
# COMPILED REGEXES (exported)
# =============================================================================
IR_REGEX, IR_SOFT_REGEX = build_ir_regex()
FX_REGEX, FX_SOFT_REGEX = build_fx_regex()
CP_REGEX, CP_SOFT_REGEX = build_cp_regex()
EQ_REGEX, EQ_SOFT_REGEX = build_eq_regex()
CR_REGEX, CR_SOFT_REGEX = build_cr_regex()

CATEGORY_REGEX = re.compile(
    r"|".join(
        [
            IR_REGEX.pattern,
            FX_REGEX.pattern,
            CP_REGEX.pattern,
            EQ_REGEX.pattern,
            CR_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)
SOFT_CATEGORY_REGEX = re.compile(
    r"|".join(
        [
            IR_SOFT_REGEX.pattern,
            FX_SOFT_REGEX.pattern,
            CP_SOFT_REGEX.pattern,
            EQ_SOFT_REGEX.pattern,
            CR_SOFT_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)
BOTH_CATEGORY_REGEX = re.compile(
    r"|".join(
        [
            IR_SOFT_REGEX.pattern,
            FX_SOFT_REGEX.pattern,
            CP_SOFT_REGEX.pattern,
            EQ_SOFT_REGEX.pattern,
            CR_SOFT_REGEX.pattern,
            IR_REGEX.pattern,
            FX_REGEX.pattern,
            CP_REGEX.pattern,
            EQ_REGEX.pattern,
            CR_REGEX.pattern,
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
SOFT_REGEX = re.compile(
    r"|".join(
        [
            SOFT_CATEGORY_REGEX.pattern,
            STRICT_GEN_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)
LOOSE_GEN_REGEX = build_loose_gen_regex()
ALL_REGEX = re.compile(
    r"|".join(
        [
            FX_REGEX.pattern,
            CP_REGEX.pattern,
            EQ_REGEX.pattern,
            IR_REGEX.pattern,
            CR_REGEX.pattern,
            FX_SOFT_REGEX.pattern,
            CP_SOFT_REGEX.pattern,
            EQ_SOFT_REGEX.pattern,
            IR_SOFT_REGEX.pattern,
            CR_SOFT_REGEX.pattern,
            GEN_REGEX.pattern,
            SOFT_GEN_REGEX.pattern,
            STRICT_NOTIONAL_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)
CATEGORY_DELETION_MAP = {
    "ir": (IR_REGEX, IR_SOFT_REGEX, IR_CONTEXT_REGEX),
    "fx": (FX_REGEX, FX_SOFT_REGEX, FX_CONTEXT_REGEX),
    "cp": (CP_REGEX, CP_SOFT_REGEX, CP_CONTEXT_REGEX),
    "eq": (EQ_REGEX, EQ_SOFT_REGEX, EQ_CONTEXT_REGEX),
    "cr": (CR_REGEX, CR_SOFT_REGEX, CR_CONTEXT_REGEX),
}


# =============================================================================
# EXCLUSION PATTERNS (from filter_database.py)
# =============================================================================

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
    "phantom stocks?",
    "employee stocks?",
    "employees?",
    # 2. Plan/HR Terminology
    "compensations?",
    "benefit plans?",
    "incentive plans?",
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
    "treasury stocks?",
    "exercise",
]

PLAN_ASSETS_KEYWORDS = [
    r"\bplan\s+assets\b",
    r"\bpension\s+(?:plan|fund|trust|benefit)",
    r"\bpost[- ]?retirement\s+(?:benefit|plan)",
    r"\bdefined\s+benefit\s+(?:plan|pension)",
    r"\bretirement\s+(?:plan|system)",
    r"\btrust\s+assets\b",
    r"\b401\(?k\)?\s+plan",
    r"\bVEBA\b",  # Voluntary Employees' Beneficiary Association
    r"hedge funds?"
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
    r"derivative\s+(?:action|lawsuit|suit|litigation|settlement|claim|proceeding)",
    r"shareholder\s+derivative",
    r"courts?",
    r"petitions?",
    r"defenses?",
    r"corrections?",
    r"corrective\s+actions?",
]
# =============================================================================
# CONTRACTUAL NOISE LISTS (SPLIT)
# =============================================================================

# 1. STRICT: Capitalized Definitions & Structural Headers (High Confidence)
# Single match is usually sufficient to identify a contract/indenture.
CONTRACTUAL_KEYWORDS_STRICT = [
    # ROLES
    r"\bAgents?\b",
    r"\b(?:Co-)?Lenders?\b",
    r"\b(?:Co-)?Borrowers?\b",
    r"\bGuarantors?\b",
    r"\bPersons?\b",
    r"\bIssuing\s+Banks?\b",
    r"\bSwingline\s+Lenders?\b",
    r"\bNoteholders?\b",
    r"\bGrantors?\b",
    r"\bPledgors?\b",
    r"\bTrustees?\b",
    r"\bRegistrars?\b",
    r"\bCustodians?\b",
    r"\bDepositaries?\b",
    r"\bAssignees?\b",
    r"\bIndemnitees?\b",
    r"\bLiquidators?\b",
    r"\bReceivers?\b",
    r"\bSuccessors?(?:\s+and\s+Assigns?)?\b",
    # IDIOMS
    r"\b(?:any|such|no|each|another)\s+Person\b",
    r"\bSurviving\s+Person\b",
    r"\bSuccessor\s+Person\b",
    # DOCUMENTS
    r"\bGlobal\s+Notes?\b",
    r"\bDefinitive\s+Notes?\b",
    r"\bSupplemental\s+Indenture\b",
    r"\bOfficer['’]s\s+Certificate\b",
    # STRUCTURE
    r"\bArticles?\s+(?:[IVXLCDM]+|\d+)\s+(?:hereof|thereof|of\s+the\s+(?:Credit|Loan|Indenture|Agreement))\b",
    r"\bArticles?\s+[IVXLCDM]+\b",
    r"\bSections?\s+\d+\.\d+(?:\([a-z]\))?\b",
    r"\bRecitals?\b",
    r"\bSchedules?\s+(?:\d+|[A-Z])\b",
    r"\bExhibits?\s+(?:\d+|[A-Z])\b",
    r"\bAnnex(?:es)?\s+(?:\d+|[A-Z])\b",
]

# 2. LOOSE SINGLE: Archaic Adverbs (High Risk of False Positive)
# These require high density (>3) or combination with phrases to trigger discard.
CONTRACTUAL_KEYWORDS_SINGLE = [
    r"\bhereby\b",
    r"\bhereof\b",
    r"\bthereof\b",
    r"\bthereunder\b",
    r"\bhereunder\b",
    r"\bwitnesseth\b",
    r"\bwhereas\b",
    r"\bhereto\b",
]

# 3. LOOSE PHRASE: Legal Actions & Boilerplate (Medium Confidence)
CONTRACTUAL_KEYWORDS_PHRASE = [
    # Latin/Legal Idioms
    r"\bmutatis\s+mutandis\b",
    r"\binter\s+alia\b",
    r"\binure\s+to\s+the\s+benefit\b",
    r"\bnow\s*,?\s*therefore\b",
    # Actions
    r"acknowledge(?:s|d)?\s+and\s+agree(?:s|d)?",
    r"reaffirm(?:s|ed|ing)?\s+(?:its|their|the)\s+obligations",
    r"ratif(?:y|ies|ied)\s+and\s+confirm(?:s|ed)?",
    r"constitute\s+valid\s+and\s+subsisting\s+obligations",
    r"waive(?:s|d)?\s+any\s+(?:defense|claim|offset)",
    r"operat(?:e|es|ed)\s+to\s+reduce\s+or\s+discharge",
    # Consent/Evidence
    r"prior\s+written\s+consent",
    r"consent\s+of\s+the\s+(?:Administrative\s+Agent|Lenders?|Banks?)",
    r"without\s+the\s+consent\s+of",
    r"evidenced\s+(?:or\s+represented\s+)?by\s+(?:a|an|the|any)\s+(?:Note|Certificate|Instrument|Agreement|Contract)",
    # Pointers
    r"the\s+foregoing\s+(?:recitals|definitions|provisions|conditions|covenants)",
    r"under\s+the\s+Credit\s+Agreement",
    r"under\s+the\s+Loan\s+Documents",
    r"under\s+the\s+Guarantee",
    r"terms\s+defined\s+in\s+the\s+Credit\s+Agreement",
    # Governance
    r"certificate\s+of\s+incorporation",
    r"articles\s+of\s+incorporation",
    r"certificate\s+of\s+designation",
    r"by[- ]?laws",
    r"organizational\s+documents",
    r"delaware\s+law",
    r"general\s+corporation\s+law",
    r"DGCL",
    r"anti[- ]takeover",
    r"change\s+of\s+control\s+provisions?",
    r"stockholder\s+rights\s+plan",
    r"poison\s+pill",
    # Definition indicators
    # 1. "Shall mean" (The classic legal definition)
    r"shall\s+(?:mean|refers?)",
    # 2. "Have the meaning ascribed"
    r"have\s+the\s+meanings?\s+(?:ascribed|assigned|given|set\s+forth)",
    # 3. "As defined in/under" (Pointer to definition)
    r"(?:as|is|are|were|was)\s+defined\s+(?:in|under|by|as)",
    # 5. Anchored Term Definition: "The term 'X' means"
    # This is safe because it requires "The term" anchor.
    r"[Tt]he\s+term\s+[\"“].*?[\"”]\s+(?:means?|refers?)",
]


# Section 3: Accounting Standards
# === FASB ISSUANCE & ADOPTION ONLY ===
ISSUER_TERMS = [
    r"\bFASB\b",
    r"\bFinancial Accounting Standards Board\b",
    r"\bF\.A\.S\.B\.\b",
    r"\bIASB\b",
    r"\bInternational Accounting Standards Board\b",
    r"\bI\.A\.S\.B\.\b",
    r"\bGASB\b",
    r"\bGovernmental Accounting Standards Board\b",
    r"\bG\.A\.S\.B\.\b",
    r"\bAICPA\b",
    r"\bAmerican Institute of Certified Public Accountants\b",
    r"\bA\.I\.C\.P\.A\.\b",
    r"\bPCAOB\b",
    r"\bPublic Company Accounting Oversight Board\b",
    r"\bP\.C\.A\.O\.B\.\b",
    r"\bFASAB\b",
    r"\bFederal Accounting Standards Advisory Board\b",
    r"\bF\.A\.S\.A\.B\.\b",
    r"\bSEC\b",
    r"\bSecurities and Exchange Commission\b",
    r"\bS\.E\.C\.\b",
    r"\bAccounting Standards Board\b",
    r"\bEITF\b",
    r"\bE\.I\.T\.F\.\b",
    r"\bEmerging Issues Task Force\b",
    r"\bTask Force\b",
]

# --- STANDARD TYPES & ACRONYMS ---
STANDARDS_TERMS = [
    r"\bSFAS\b", "Statement of Financial Accounting Standards?",
    r"\bFAS\b", "Financial Accounting Standards?",
    r"\bASU\b", "Accounting Standards Update",
    r"\bASC\b", "Accounting Standards Codification",
    r"\bIFRS\b", "International Financial Reporting Standards?",
    r"\bIAS\b", "International Accounting Standards?",
    r"\bIFRIC\b", "International Financial Reporting Interpretations Committee",
    r"\bSIC\b", "Standing Interpretations Committee",
    r"\bEITF\b", "Emerging Issues Task Force",
    r"\bSOP\b", "Statement of Position",
    r"\bFSP\b", "FASB Staff Position",
    r"\bFIN\b", "FASB Interpretation",
    r"\bTB\b", r"\bTechnical\s+Bulletin\b",
    r"\bSFAC\b", "Statement of Financial Accounting Concepts",
    r"\bConcept\s+Statement\b",
    r"\bAPB\s+Opinion\b", "Accounting Principles Board Opinion",
]


# --- MONTHS (for date boilerplate) ---
MONTHS_TERMS = [
    r"January",
    r"February",
    r"March",
    r"April",
    r"May",
    r"June",
    r"July",
    r"August",
    r"September",
    r"October",
    r"November",
    r"December",
]
MONTHS_FRAGMENT = build_alternation(MONTHS_TERMS)
# --- ADOPTION TIMING TYPES ---
ADOPTION_TIMING_TYPES = [
    r"early",
    r"late",
    r"future",
    r"current",
    r"past",
    r"prospective",
    r"retrospective",
]
# --- ISSUANCE VERBS ---
ISSUANCE_VERBS = [
    # Core issuance verbs (Present/Past/Participle)
    r"issu(?:es?|ed|ing)",  # issue, issues, issued, issuing
    r"releas(?:es?|ed|ing)",  # release, releases, released...
    r"publish(?:es?|ed|ing)?",  # publish, publishes, published...
    r"ratif(?:y|ies|ied|ying)",  # ratify, ratifies, ratified...
    r"updat(?:es?|ed|ing)",  # update, updates, updated...
    r"announc(?:es?|ed|ing)",  # announce, announces, announced...
    r"expos(?:es?|ed|ing)",  # expose, exposes, exposed...
    r"propos(?:es?|ed|ing)",  # propose, proposes, proposed...
    r"approv(?:es?|ed|ing)",  # approve, approves, approved...
    r"finaliz(?:es?|ed|ing)",  # finalize, finalizes, finalized...
    r"adopt(?:s|ed|ing)?",  # adopt, adopts, adopted...
    r"re-?issu(?:es?|ed|ing)",  # reissue, re-issues, reissued...
    r"amend(?:s|ed|ing)?",  # amend, amends, amended...
    r"revis(?:es?|ed|ing)",  # revise, revises, revised...
    # Phrases
    r"reached?\s+a\s+(?:final\s+)?consensus",  # reach/reached a consensus
]

# --- DESCRIPTION VERBS ---
DESCRIPTION_VERBS = [
    r"address(?:es|ed|ing)",  # address, addresses, addressed
    r"provid(?:es?|ed|ing)\s+(?:guidance|standards|accounting\s+(?:for|treatment))",  # Focused phrase
    r"clarif(?:y|ies|ied|ying)",  # clarify, clarifies, clarified
    r"amend(?:s|ed|ing)?",  # amend, amends, amended
    r"requir(?:es?|ed|ing)",  # require, requires, required
    r"relat(?:es?|ed|ing)\s+to",  # relate/relates/related to
    r"appl(?:y|ies|ied|ying)\s+to",  # apply/applies/applied to
    r"establish(?:es|ed|ing)",  # establish, establishes, established
    r"prescrib(?:es?|ed|ing)",  # prescribe, prescribes, prescribed
    r"defin(?:es?|ed|ing)",  # define, defines, defined
    r"modif(?:y|ies|ied|ying)",  # modify, modifies, modified
    r"specif(?:y|ies|ied|ying)",  # specify, specifies, specified
    r"govern(?:s|ed|ing)?",  # govern, governs, governed
    r"affect(?:s|ed|ing)?",  # affect, affects, affected
    r"impact(?:s|ed|ing)?",  # impact, impacts, impacted
    r"cover(?:s|ed|ing)?",  # cover, covers, covered
    r"deal(?:s|t|ing)?\s+with",  # deal, deals, dealt with
    r"pertain(?:s|ed|ing)?\s+to",  # pertain, pertains, pertained to
    r"concern(?:s|ed|ing)?",  # concern, concerns, concerned
    r"prohibit(?:s|ed|ing)?",  # prohibit, prohibits, prohibited
    r"permit(?:s|ted|ting)?",  # permit, permits, permitted
    r"allow(?:s|ed|ing)?",  # allow, allows, allowed
    r"restrict(?:s|ed|ing)?",  # restrict, restricts, restricted
    r"mandat(?:es?|ed|ing)",  # mandate, mandates, mandated
    r"expand(?:s?|ed|ing)?",  # expand, expands (added per your previous request)
]

# --- ADOPTION VERBS: FUTURE INTENT ---
ADOPTION_VERBS_FUTURE = [
    r"will\s+adopt",
    r"plan(?:s|ned)?\s+to\s+adopt",
    r"expect(?:s|ed)?\s+to\s+adopt",
    r"required?\s+to\s+adopt",
    r"must\s+adopt",
    r"shall\s+adopt",
    r"intend(?:s|ed)?\s+to\s+adopt",
    r"anticipate(?:s|d)?\s+(?:adopting|adoption)",
    r"scheduled\s+to\s+adopt",
    r"targeted\s+to\s+adopt",
    r"is\s+required\s+to\s+adopt",
    r"will\s+be\s+required\s+to\s+adopt",
    r"(?:is|will\s+be)\s+(?:eligible|required)\s+for\s+(?:early\s+)?adoption",
    r"(?:adopted|adoption)\s+by"
]

# --- ADOPTION VERBS: GENERAL ACTION ---
ADOPTION_VERBS_GENERAL = [
    r"adopt(?:ing|ed)?",  # ✓ Direct adoption
    r"early\s+adopt(?:ed|ing|ion)?",  # ✓ Early adoption (accounting-specific)
    r"application\s+of",  # ✓ "Application of ASC 815" (accounting context)
    r"implement(?:ing|ed|ation)",  # ✓ Implementation (accounting standards)
    r"transition(?:ing|ed)?",  # ✓ Transition (accounting-specific in this context)
    r"compliance\s+with",
    r"conform(?:ing|ed|ity)\s+to",
    r"(?:early\s+)?application",
    r"retroactive\s+(?:application|adoption)",  # ✓ Retroactive adoption (accounting-specific)
    r"prospective\s+(?:application|adoption)",  # ✓ Prospective adoption (accounting-specific)
]

# --- EFFECTIVE DATE PHRASES ---
EFFECTIVE_DATE_PHRASES = [
    r"effective\s+for\s+(?:fiscal\s+years|annual\s+periods)",
    r"effective\s+(?:in|for|after)\s+(?:fiscal\s+)?(?:year\s+)?\d{4}",
    r"becomes\s+effective",
    r"will\s+be\s+effective",
    rf"(?:ending|beginning)\s+after\s+{MONTHS_FRAGMENT}",
]

EFFECT_NOUNS = [
    r"impacts?",
    r"effects?",
    r"implications?",
    r"outcomes?",
    r"results?",
    r"consequences?",
    r"repercussions?",
    r"ramifications?",
    r"influences?",
    r"significance",
    r"aftermath",
    r"corollaries?",
    r"byproducts?",
]
ASSESSMENT_VERBS = [
    r"assess(?:es|ed|ing)?",
    r"(?:re)?evaluate(?:s|d|ing)?",
    r"review(?:s|ed|ing)?",
    r"test(?:s|ed|ing)?",
    r"monitor(?:s|ed|ing)?",
    r"analyz(?:e|es|ed|ing)",
    r"apprais(?:e|es|ed|ing)",
    r"audit(?:s|ed|ing)?",
    r"examin(?:e|es|ed|ing)",
    r"inspect(?:s|ed|ing)?",
    r"scrutiniz(?:e|es|ed|ing)",
    r"stud(?:y|ies|ied|ying)",
    r"investigat(?:e|es|ed|ing)",
    r"consider(?:s|ed|ing)?",
    r"validat(?:e|es|ed|ing)",
    r"verif(?:y|ies|ied|ying)",
    r"check(?:s|ed|ing)?",
    r"measur(?:e|es|ed|ing)",
    r"weigh(?:s|ed|ing)?",
]


EFFECT_FRAGMENT = build_alternation(EFFECT_NOUNS)
ASSESSMENT_FRAGMENT = build_alternation(ASSESSMENT_VERBS)

# --- IMPACT ASSESSMENT PHRASES ---
IMPACT_PHRASES = [
    # Generic evaluation/assessment of effects
    rf"{ASSESSMENT_FRAGMENT}\s+(?:the\s+)?{EFFECT_FRAGMENT}\s+of",
    # Ongoing evaluation/assessment
    rf"currently\s+{ASSESSMENT_FRAGMENT}",
    rf"continu(?:ing|es)\s+to\s+{ASSESSMENT_FRAGMENT}",
    # Specific financial reporting context
]

# --- IMPACT RESULT PHRASES ---
IMPACT_RESULT_PHRASES = [
    # Expected materiality with up to 3 intervening words
    rf"(?:not\s+)?expected\s+to\s+have\s+a\s+material(?:\s+\w+){{0,3}}\s+{EFFECT_FRAGMENT}",
    # Explicit immateriality with flexibility
    rf"no\s+material(?:\s+\w+){{0,3}}\s+{EFFECT_FRAGMENT}",
    rf"immaterial(?:\s+\w+){{0,3}}\s+{EFFECT_FRAGMENT}",
    rf"{EFFECT_FRAGMENT}\s+on(?:\s+\w+){{0,3}}\s+statements",
]

# --- ADOPTION PERMISSIBILITY PHRASES ---
ADOPTION_PERMISSION_PHRASES = [
    r"early\s+application\s+(?:is\s+)?permitted",
    r"early\s+adoption\s+(?:is\s+)?permitted",
    rf"(?:{build_alternation(ADOPTION_TIMING_TYPES)})\s+(?:adoption|application)",
    r"(?:adoption|application)\s+(?:is\s+)?(?:permitted|allowed|optional)",
    r"(?:adoption|application)\s+(?:is\s+)?(?:required|mandatory)",
    r"optional\s+(?:adoption|application)",
    r"permitted\s+(?:adoption|application)",
    r"voluntary\s+(?:adoption|application)",
]

# --- GUIDANCE OBJECT TYPES ---
GUIDANCE_OBJECT_TYPES = [
    r"Guidance",
    r"Standards?",
    r"Amendments?",
    r"Statements?",
    r"Provisions?",
    r"Regulations?",
    r"Abstracts?",
    r"Opinions?",
    r"Codifications?",
    r"Pronouncements?",
    r"Interpretations?",
    r"Bulletins?",
    r"Frameworks?",
    r"Concept\s+Statements?",
    r"Clarifications?",
    r"Rules?",
    r"Principals?",
    r"Principles?",
]

# --- STANDALONE PHRASES (context-specific, non-generic) ---
STANDALONE_PHRASES = [
    r"adoption\s+of",
    r"prior\s+to\s+adoption",
    r"transition\s+period",
    r"cumulative\s+effect\s+adjustment",
    r"transition\s+method",
    r"adoption\s+method",
    r"retrospective\s+restatement",
    r"prospective\s+application\s+only",
    r"no\s+restatement\s+(?:of\s+)?(?:prior\s+)?periods",
    r"grandfathering",
    r"grandfather\s+provision",
    r"deemed\s+cost\s+(?:option|election)",
    r"first-?time\s+adoption",
    r"adoption\s+date",
    r"adoption\s+guidance",
    r"implementation\s+guidance",
    r"transition\s+guidance",
    r"effective\s+date\s+(?:of\s+adoption|guidance)",
    r"safe\s+harbor",
    r"optional\s+expedient",
    r"practical\s+expedient",
]

# --- BUILD REGEX FRAGMENTS ---
# Matches: FASB, "FASB", (FASB), ("FASB"), ('FASB')
# We allow any combination of opening parens/quotes and closing parens/quotes
ISSUER_FRAGMENT = rf"(?:[\(\"\'\s]+)?{build_alternation(ISSUER_TERMS)}(?:[\)\"\'\s]+)?"
STANDARDS_FRAGMENT = rf"(?:[\(\"\'\s]+)?{build_alternation(STANDARDS_TERMS)}(?:[\)\"\'\s]+)?"

ISSUANCE_VERBS_FRAGMENT = build_alternation(ISSUANCE_VERBS)
DESCRIPTION_VERBS_FRAGMENT = build_alternation(DESCRIPTION_VERBS)
ADOPTION_VERBS_FUTURE_FRAGMENT = build_alternation(ADOPTION_VERBS_FUTURE)
ADOPTION_VERBS_GENERAL_FRAGMENT = build_alternation(ADOPTION_VERBS_GENERAL)
EFFECTIVE_DATE_PHRASES_FRAGMENT = build_alternation(EFFECTIVE_DATE_PHRASES)
IMPACT_PHRASES_FRAGMENT = build_alternation(IMPACT_PHRASES)
IMPACT_RESULT_PHRASES_FRAGMENT = build_alternation(IMPACT_RESULT_PHRASES)
ADOPTION_PERMISSION_PHRASES_FRAGMENT = build_alternation(ADOPTION_PERMISSION_PHRASES)
STANDALONE_PHRASES_FRAGMENT = build_alternation(STANDALONE_PHRASES)
GUIDANCE_OBJECT_TYPES_FRAGMENT = build_alternation(GUIDANCE_OBJECT_TYPES)

# --- STANDARD ID PATTERN ---
# Matches: "EITF Issue No. 06-6", "FASB Statement No. 133", "ASU 2014-09"
STANDARD_ID_PATTERN = rf"(?:{STANDARDS_FRAGMENT}|{GUIDANCE_OBJECT_TYPES_FRAGMENT})(?:\s+Issue)?(?:\s+No\.?)?\s+\d+(?:-\d+)*(?:[A-Z])?"
STANDARD_ID_REGEX = re.compile(STANDARD_ID_PATTERN)

CAPITALIZED_TITLE_PATTERN = (
    r"(?:,?\s*[\"“']?(?:[A-Z][\w\-']+\s+){2,}[A-Z][\w\-']+[\"”']?)?"
)
# =============================================================================
# ACCOUNTING STANDARDS: STRICT VS SOFT
# =============================================================================

# --- 1. STRICT (High Confidence) ---
# Triggers "Aggressive Mode" in Title Cleaner.
# These explicitly mention Regulators, Standard IDs, or Formal Adoption events.
ACCOUNTING_STANDARDS_STRICT = [
    # Dated Issuance ("In June 2022, the FASB issued...")
    rf"{MONTHS_FRAGMENT}\s+\d{{4}}.*{ISSUER_FRAGMENT}\s+{ISSUANCE_VERBS_FRAGMENT}",
    # Issuer + Issuance ("FASB issued...")
    rf"{ISSUER_FRAGMENT}\s+(?:in\s+{MONTHS_FRAGMENT}\s+\d{{4}}.*)?{ISSUANCE_VERBS_FRAGMENT}(?:\s+in\s+{MONTHS_FRAGMENT}\s+(?:\d{{4}})?)?",
    # Standard ID + Issuance ("ASU 2016-13 was issued...")
    rf"{STANDARD_ID_PATTERN}\s+(?:was|is)\s+{ISSUANCE_VERBS_FRAGMENT}",
    # Issuance Verb + Standard ID ("Adopted SFAS 157...")
    rf"{ISSUANCE_VERBS_FRAGMENT}(?:\s+\w+){{1,10}}\s+{STANDARD_ID_PATTERN}",
    # Standard Descriptions ("ASC 820 defines...")
    rf"{STANDARD_ID_PATTERN}\s+{DESCRIPTION_VERBS_FRAGMENT}",
    # Explicit Adoption ("Adoption of the new guidance")
    rf"{ADOPTION_VERBS_GENERAL_FRAGMENT}\s+{STANDARD_ID_PATTERN}",
    rf"{ADOPTION_VERBS_GENERAL_FRAGMENT}\s+(?:\S+\s+){{0,10}}{GUIDANCE_OBJECT_TYPES_FRAGMENT}",
    # Future Adoption ("We plan to adopt...")
    rf"{ADOPTION_VERBS_FUTURE_FRAGMENT}",
    # Effective Dates ("Effective for fiscal years...")
    rf"{STANDARD_ID_PATTERN}\s+should\s+be\s+applied",
    rf"{STANDARD_ID_PATTERN}\s+(?:is|was|becomes)\s+effective",
    EFFECTIVE_DATE_PHRASES_FRAGMENT,
    ADOPTION_PERMISSION_PHRASES_FRAGMENT,
    # Explicit "No Material Impact" statements (Classic boilerplate)
    IMPACT_RESULT_PHRASES_FRAGMENT,
    # Anchored Headers ("In March 2024...")
    rf"^{STANDARD_ID_PATTERN}\s+(?:{ISSUANCE_VERBS_FRAGMENT}|{DESCRIPTION_VERBS_FRAGMENT})",
    rf"^{ISSUER_FRAGMENT}\s+(?:{ISSUANCE_VERBS_FRAGMENT}|{DESCRIPTION_VERBS_FRAGMENT})",
    rf"^In\s+{MONTHS_FRAGMENT}.*{ISSUER_FRAGMENT}",
    # Specific Terms
    rf"(?:recently\s+)?(?:issued|updated|released|published|announced)\s+(?:accounting\s+)?{GUIDANCE_OBJECT_TYPES_FRAGMENT}(?:\s+updates?)?",
    r"accounting standards update",
    # Disclosures explicitly mandated by an ID
    rf"disclosures?\s+(?:required|mandated)\s+by\s+{STANDARD_ID_PATTERN}[^.?!]*",
    rf"derivatives\s+(?:instruments\s+)?and\s+hedging\s+activities",
]

# --- 2. SOFT (Lower Confidence) ---
# Used for general text filtering but NOT for aggressive title cleanup.
# These are more generic descriptions of disclosure improvements or impacts.
ACCOUNTING_STANDARDS_SOFT = [
    # Standalone accounting phrases (risk of collision with commercial terms)
    STANDALONE_PHRASES_FRAGMENT,
    # Generic impact assessment ("Evaluating the impact of...")
    IMPACT_PHRASES_FRAGMENT,
    # Disclosure improvement language (could be general)
    rf"improve\s+disclosures?\s+(?:about|regarding|on)[^.?!]*",
    rf"requiring\s+(?:more|additional)\s+information[^.?!]*",
    # Pure References ("Pursuant to ASC 815")
    rf"pursuant\s+to\s+{STANDARD_ID_PATTERN}",
    rf"defined\s+in\s+{STANDARD_ID_PATTERN}",
    rf"accordance\s+with\s+{STANDARD_ID_PATTERN}",
    # ID + Title ("ASC 815 Derivatives and Hedging")
    rf"{STANDARD_ID_PATTERN}(?:\s+,\s+)?{CAPITALIZED_TITLE_PATTERN}",
    # Indirect references
    rf"disclosures?\s+(?:about|regarding)\s+(?:the\s+)?(?:adoption|application|impact)\s+of[^.?!]*",
    rf"(?:intended|designed)\s+to\s+(?:improve|expand|enhance)\s+disclosures?[^.?!]*",
    rf"requiring\s+(?:more|additional|expanded)\s+information\s+about[^.?!]*",
]

# --- 3. COMBINED LIST (For General Filtering) ---
ACCOUNTING_STANDARDS_KEYWORDS = ACCOUNTING_STANDARDS_STRICT + ACCOUNTING_STANDARDS_SOFT
ACCOUNTING_STANDARDS_STRICT_REGEX = re.compile(
    r"|".join(ACCOUNTING_STANDARDS_STRICT), re.IGNORECASE
)

ACCOUNTING_STANDARDS_SOFT_REGEX = re.compile(
    r"|".join(ACCOUNTING_STANDARDS_SOFT), re.IGNORECASE
)


def build_capitalized_title_cleaner() -> re.Pattern:
    """
    Matches a sequence of Title Case words separated by common connectors.
    Updated to include 'regarding', 'about', 'as', etc.
    """
    # Expanded list of lowercase connectors found in accounting titles
    connectors = r"of|for|and|to|in|on|with|the|about|regarding|as|an"

    return re.compile(
        # 1. Start with optional chunks of "Word + Connector"
        # Matches: "Disclosures about ", "Amendment of "
        rf"(?!^)\b(?:[A-Z][a-z0-9-]*\s+(?:{connectors})\s+)*"
        # 2. Match the mandatory final Capitalized Word
        r"[A-Z][a-z0-9-]*"
        # 3. Allow trailing "Connector + Word" sequences (Greedy)
        # Matches: "...Derivative Instruments and Hedging Activities"
        rf"(?:\s+(?:[A-Z][a-z0-9-]*|{connectors}))*\b"
    )


TITLE_CLEANER_REGEX = build_capitalized_title_cleaner()

# =============================================================================
# FORWARD-LOOKING STATEMENT PATTERNS (NEW)
# =============================================================================
FORWARD_LOOKING_KEYWORDS = [
    # 1. The Headers/Titles
    r"cautionary\s+(?:note|statement|language)\s+(?:regarding|concerning|about)",
    r"forward[- ]looking\s+statements?",
    r"safe\s+harbor",
    # 2. Legal Acts/Sections (The smoking gun for boilerplate)
    r"private\s+securities\s+litigation\s+reform\s+act",
    r"section\s+27a\s+of\s+the\s+securities\s+act",
    r"section\s+21e\s+of\s+the\s+securities\s+exchange\s+act",
    # 3. Boilerplate Definitions
    r"statements\s+that\s+are\s+not\s+historical\s+facts",
    r"words\s+such\s+as\s+(?:expect|anticipate|intend|plan|believe|seek|see|will|would|target)",
    r"results\s+(?:could|may|might)\s+differ\s+materially",
    r"undertake\s+no\s+obligation\s+to\s+update",
    # 4. Specific Risk Factors boilerplate (careful not to delete actual risk mgmt)
    r"refer\s+to\s+(?:item|section)\s+1a\.?\s+risk\s+factors",
    r"risk\s+factors\s+described\s+in",
]

# --- HYPOTHETICAL SCORING COMPONENTS ---

# TIER 1: STRICT ARTIFACTS (The "Fake" Instruments)
# These do not exist in the real world. Finding one is almost certainly methodology.
# Weight: High (Immediate Kill or near-kill)
HYPOTHETICAL_STRICT = [
    r"hypothetical\s+derivatives?",
    r"hypothetical\s+positions?",
    r"hypothetical\s+trades?",
    r"hypothetical\s+instruments?",
    r"hypothetical\s+hedges?",
]

# TIER 2: METHODOLOGY PHRASES (The "Stats Class" Lingo)
# Strong indicators of modeling context.
# Weight: Medium (2 hits = Discard)
HYPOTHETICAL_PHRASES = [
    r"sensitivity\s+analysis",
    r"value[- ]at[- ]risk",
    r"confidence\s+(?:level|interval)",
    r"statistical\s+(?:measure|model|analysis)",
    r"parallel\s+shift",
    r"stress\s+testing",
    r"simulation\s+model",
    r"market\s+risk\s+measurement",
    # Matches "hypothetical" + (0-5 words) + "increase/decrease/change/shift"
    r"hypothetical(?:\s+\S+){0,5}\s+(?:increase|decrease|change|shift|loss|impact|effect)",
    r"rate\s+shocks?",
    r"yield\s+curve\s+shifts?",
    r"immediate\s+(?:and\s+sustained\s+)?shift",
    r"instantaneous\s+(?:parallel\s+)?shift",
    r"weakening\s+or\s+strengthening",
    r"regression\s+analysis",
    r"unobservable\s+inputs?",
    r"internally\s+developed\s+models?",
    r"prospective(?:ly)?\s+(?:basis|test|assessment)",
    r"retrospective(?:ly)?\s+(?:basis|test|assessment)",
    # Safe Basis Point Check
    r"\d+\s+basis\s+point\s+(?:increase|decrease|shift|shock|change)",
]

# TIER 3: LOOSE INDICATORS (The Context Fillers)
# Common words in sensitivity sections, but safe on their own.
# Accumulation (density) creates the signal.
# Weight: Low (Need 3-4 hits to Discard)
HYPOTHETICAL_SINGLES = [
    r"hypothetical",  # Standalone word
    r"simulation",
    r"statistical",
    r"probabilit(?:y|ies|istic)",
    r"assumption",
    r"parameter",
    r"holding\s+constant",
    r"baseline",
    r"variance",
    r"unobservable",
    r"estimate",
]

# --- BUILDERS ---
HYP_STRICT_REGEX = re.compile(
    r"\b" + build_alternation(HYPOTHETICAL_STRICT) + r"\b", re.IGNORECASE
)
HYP_PHRASE_REGEX = re.compile(
    r"\b" + build_alternation(HYPOTHETICAL_PHRASES) + r"\b", re.IGNORECASE
)
HYP_SINGLE_REGEX = re.compile(
    r"\b" + build_alternation(HYPOTHETICAL_SINGLES) + r"\b", re.IGNORECASE
)
COMPETITOR_KEYWORDS = [
    r"competitors?",
    r"competition",
    r"other\s+companies",
    r"other\s+entities",
    r"other\s+market\s+participants",
    r"industry\s+peers?",
    r"industry\s+practice",
    r"peer\s+group",
]
FILING_KEYWORDS = [
    "10-K",
    "10-KT",
    "20-F",
    "40-F",
    "10-K405",
    "10KSB",
    "10KSB40",
    "8-K",
    "Incorporated by",
    "filed on",
    r"(?:annual|quarterly)\s+report",
    r"\bSEC\b\s+File",
]
# =============================================================================
# REGULATORY NOISE LISTS (SPLIT)
# =============================================================================

# 1. STRICT: Specific Acts, Laws, & Banking Metrics
# Value: 2 Points Each
# Reasoning: Naming a specific Act usually implies a "Regulatory Environment" section.
REGULATORY_KEYWORDS_STRICT = [
    # Specific US Acts
    r"Dodd[- ]Frank",
    r"Volcker\s+Rule",
    r"Sarbanes[- ]Oxley",
    r"JOBS\s+Act",
    r"CARES\s+Act",
    r"Commodity\s+Exchange\s+Act",
    r"Securities\s+Exchange\s+Act",
    r"Regulation\s+AB",
    r"Federal\s+Reserve",
    # --- NEW: Energy & Environmental Acts ---
    r"Energy\s+Policy\s+Act",
    r"Clean\s+Air\s+Act",
    r"Clean\s+Water\s+Act",
    r"Oil\s+Pollution\s+Act",
    r"\bCERCLA\b",  # Superfund
    r"\bRCRA\b",  # Resource Conservation and Recovery Act
    r"\bNEPA\b",  # National Environmental Policy Act
    # International / Banking Standards
    r"Basel\s+(?:I|II|III|IV)",
    r"EMIR",  # European Market Infrastructure Regulation
    r"MiFID",  # Markets in Financial Instruments Directive
    r"Solvency\s+II",
    # Specific Banking Metrics (High likelihood of capital adequacy sections)
    r"capital\s+adequacy",
    r"liquidity\s+coverage\s+ratio",
    r"regulatory\s+(?:capital|environment)",
    r"risk[- ]weighted\s+assets?",  # RWA
    # --- Agencies (If not already caught by Entity Exclusion) ---
    r"\bEPA\b",  # Environmental Protection Agency
    r"\bFERC\b",  # Federal Energy Regulatory Commission
    r"\bDOT\b",  # Department of Transportation (Pipeline regs)
]

# 2. LOOSE: General Compliance Terminology
# Value: 1 Point Each
# Reasoning: "Regulations" or "SEC" can appear in valid context ("Filed with SEC").
# Requires density to trigger discard.
REGULATORY_KEYWORDS_LOOSE = [
    r"regulations?",
    r"regulatory\s+(?:requirements?|compliance|authorit(?:y|ies)|bod(?:y|ies)|agenc(?:y|ies)|frameworks?|matters?|reforms?)",
    r"subject\s+to\s+(?:regulation|oversight|regulatory)",
    r"governmental\s+regulations?",
    r"govern(?:ing|ed|s|ors?)?",
    r"penalt(?:y|ies)",
    r"(?:state|local|federal|international|government)\s+laws?",
    r"statutes?",
    r"oversight",
    r"\bSEC\b",  # Securities and Exchange Commission
    r"\bCFTC\b",  # Commodity Futures Trading Commission
    r"\bFCA\b",  # Financial Conduct Authority
    # --- NEW: Environmental Compliance ---
    r"civil\s+(?:penalt(?:y|ies)|fines?|sanctions?|actions?|proceedings?)",
    r"criminal\s+(?:penalt(?:y|ies)|fines?|sanctions?|actions?|proceedings?)",
    r"administrative\s+(?:penalt(?:y|ies)|fines?|sanctions?|proceedings?)",
    r"enforcement\s+(?:authority|actions?|proceedings?)",
    r"violations?\s+of",
    r"fines?\s+and\s+penalt(?:y|ies)",
    r"sanctions?",
    r"disgorgement",
    r"investigations?",
    r"anti[- ]market\s+manipulation",
    r"third\s+party\s+claims?",
    r"auditor",
    r"audits?",
    # --- NEW: Environmental Compliance ---
    r"environmental\s+(?:laws?|regulations?|matters?|compliance|protection|liabilit(?:y|ies))",
    r"greenhouse\s+gas(?:es)?",
    r"carbon\s+dioxide",
    r"emissions?",
    r"discharges?",
    r"hazardous\s+(?:substances?|wastes?|materials?)",
    r"remediat(?:ion|ing|e)",
    r"spill\s+prevention",
    r"contamination",
    r"pollutants?",
]


EXCLUDE_REGEX_EQUITY_COMP = build_regex(EQUITY_COMP_KEYWORDS)
EXCLUDE_REGEX_LEGAL_LITIGATION = build_regex(LEGAL_LITIGATION_KEYWORDS)
EXCLUDE_REGEX_ACCOUNTING_STD = build_regex(ACCOUNTING_STANDARDS_KEYWORDS)
EXCLUDE_PLAN_ASSETS_REGEX = build_regex(PLAN_ASSETS_KEYWORDS)
EXCLUDE_COMPETITOR_REGEX = build_regex(COMPETITOR_KEYWORDS)
EXCLUDE_REGEX_FORWARD_LOOKING = build_regex(FORWARD_LOOKING_KEYWORDS)
EXCLUDE_REGEX_FILING = build_regex(FILING_KEYWORDS)

EXCLUDE_REGEX_REGULATORY_STRICT = build_regex(
    REGULATORY_KEYWORDS_STRICT, ignore_case=True
)
EXCLUDE_REGEX_REGULATORY_LOOSE = build_regex(
    REGULATORY_KEYWORDS_LOOSE, ignore_case=True
)

EXCLUDE_REGEX_CONTRACTUAL_STRICT = build_regex(
    CONTRACTUAL_KEYWORDS_STRICT, ignore_case=False
)
EXCLUDE_REGEX_CONTRACTUAL_SINGLE = build_regex(
    CONTRACTUAL_KEYWORDS_SINGLE, ignore_case=True
)
EXCLUDE_REGEX_CONTRACTUAL_PHRASE = build_regex(
    CONTRACTUAL_KEYWORDS_PHRASE, ignore_case=True
)


def is_hypothetical_noise(text: str, threshold: int = 5) -> bool:
    # 1. Weights
    W_STRICT = 10  # KILL SHOT: "Hypothetical derivatives" (Instant >= 8)
    W_PHRASE = 2  # "Sensitivity analysis", "Value at Risk"
    W_SINGLE = 1  # "Statistical", "Probability"

    # 2. Count
    strict_hits = len(HYP_STRICT_REGEX.findall(text))
    phrase_hits = len(HYP_PHRASE_REGEX.findall(text))
    single_hits = len(HYP_SINGLE_REGEX.findall(text))

    # 3. Score
    score = (
        (strict_hits * W_STRICT) + (phrase_hits * W_PHRASE) + (single_hits * W_SINGLE)
    )

    return score >= threshold


def is_contractual_noise(text: str, threshold: int = 4) -> bool:
    """
    Determines if text is contractual boilerplate using a scoring system.

    Scoring Logic (Threshold = 4):
    - Strict Matches (Capitalized definitions): 2 points each (2 hits = Discard)
    - Phrases (Legal actions): 2 points each (2 hits = Discard)
    - Single Words (Archaic adverbs): 1 point each (4 hits = Discard)

    Combinations work automatically:
    - 1 Phrase (2pts) + 2 Singles (2pts) = 4pts -> Discard
    """

    # 1. DEFINE WEIGHTS
    W_STRICT = 2
    W_PHRASE = 2
    W_SINGLE = 1

    # 2. COUNT MATCHES
    # Note: We use findall to get the count of occurrences
    strict_hits = len(EXCLUDE_REGEX_CONTRACTUAL_STRICT.findall(text))
    phrase_hits = len(EXCLUDE_REGEX_CONTRACTUAL_PHRASE.findall(text))
    single_hits = len(EXCLUDE_REGEX_CONTRACTUAL_SINGLE.findall(text))

    # 3. CALCULATE SCORE
    score = (
        (strict_hits * W_STRICT) + (phrase_hits * W_PHRASE) + (single_hits * W_SINGLE)
    )

    return score >= threshold


def is_regulatory_noise(text: str, threshold: int = 4) -> bool:
    """
    Determines if text is regulatory boilerplate using a scoring system.

    Scoring Logic (Threshold = 4):
    - Strict Matches (Specific Acts like Dodd-Frank): 2 points
    - Loose Matches (General words like 'Regulation'): 1 point

    Examples:
    - "We comply with Dodd-Frank (2) and EMIR (2)." -> 4 pts -> Discard.
    - "Subject to regulation (1) by the SEC (1)." -> 2 pts -> Keep (Valid Context).
    - "Governmental regulations (1) governing (1) the SEC (1) oversight (1)." -> 4 pts -> Discard.
    """

    # 1. DEFINE WEIGHTS
    W_STRICT = 2
    W_LOOSE = 1

    # 2. COUNT MATCHES
    strict_hits = len(EXCLUDE_REGEX_REGULATORY_STRICT.findall(text))
    loose_hits = len(EXCLUDE_REGEX_REGULATORY_LOOSE.findall(text))

    # 3. CALCULATE SCORE
    score = (strict_hits * W_STRICT) + (loose_hits * W_LOOSE)

    return score >= threshold


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
    r"previous(?:ly)?",  # previous(ly)? rarely plural
    r"preced(?:e|es|ed|ing)",
    r"earlier",  # earlier/earliest already covered as comparative
    r"last",  # last/lasts/lasting → but usually adjective; add if needed
    r"past",  # past/pasts rarely plural in this context
    r"comparable",  # comparable/comparably
    r"correspond(?:s|ed|ing)",  # corresponding is very common
    r"historical(?:ly)?",  # historical/historically
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
        (?:accumulated\s+)?other\s+comprehensive\s+(?:income|loss)(?:es)?|
        (?:AOCI|O\.?C\.?I)\b|
        (?:reclassified?|reclassifi).{0,20}(?:AOCI|O\.?C\.?I|comprehensive)|
        deferred\s+(?:tax\s+)?(?:gain|loss)(?:es)?|
        realized\s+(?:gain|loss)(?:es)?|
        unrealized\s+(?:gain|loss)(?:es)?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Build alternations once
TIME_UNIT_PATTERN = build_alternation(TIME_UNITS)
PAST_TIME_PATTERN = build_alternation(PAST_TIME_INDICATORS)
CURRENT_TIME_PATTERN = build_alternation(CURRENT_TIME_INDICATORS)
COMPARISON_PATTERN = build_alternation(COMPARISON_PHRASES)
STRONG_VERB_PATTERN = build_alternation(STRONG_ACTION_VERBS)
STRONG_POSSESSION_REGEX = re.compile(rf"\b{STRONG_VERB_PATTERN}\b", re.IGNORECASE)
WEAK_VERB_PATTERN = build_alternation(PASSIVE_STATE_VERBS)
VERB_PATTERN = "|".join([STRONG_VERB_PATTERN, WEAK_VERB_PATTERN])
VERB_REGEX = re.compile(rf"\b(?:{VERB_PATTERN})\b", re.IGNORECASE)


def build_trading_denial_pattern() -> re.Pattern:
    """
    Build regex pattern for detecting trading denial statements.
    Detects: "We do not trade", "Derivatives are not used for trading", "No trading purposes".
    """

    # 1. Base Negation (Reuse global helper if available, or define here)
    # Matches: did not, will not, cannot, didn't, never
    active_negation = build_negation_prefix_pattern()

    # 2. Context-Specific Passive Negation
    passive_negators = [
        r"are\s+not", r"is\s+not", r"were\s+not", r"was\s+not",
        r"are\s+neither", r"is\s+neither", r"were\s+neither", r"was\s+neither",
        r"never", r"not"
    ]
    passive_negation = build_alternation(passive_negators)

    # Combined Negation Block
    _NEG = rf"(?:{active_negation}|{passive_negation})"

    # --- ACTIONS ---
    ACTIONS = [
        r"use(?:d|s)?", r"using", r"utiliz(?:e|es|ed|ing)",
        r"enter(?:ed|s)?\s+into", r"entering\s+into",
        r"engage(?:d|s)?\s+in", r"engaging\s+in",
        r"hold(?:s)?", r"have", r"held", r"holding",
        r"conduct(?:ed|s)?", r"conducting",
        r"undertake(?:n|s)?", r"undertaking",
        r"employ(?:ed|s)?", r"maintain(?:ed|s)?",
        r"designate(?:d|s)?", 
        r"intend\s+to", 
        r"expect\s+to",
    ]
    _ACT = build_alternation(ACTIONS)

    # --- OBJECTS & PURPOSES ---
    TRADING_WORDS = [
        r"trading", r"speculative", r"speculation", r"proprietary\s+trading",
    ]
    _TRAD = build_alternation(TRADING_WORDS)

    PURPOSE_WORDS = [
        r"purposes?", r"activities?", r"basis", r"transactions?", r"reasons?",
    ]
    _PURP = build_alternation(PURPOSE_WORDS)

    # --- HELPERS ---
    SUBJ_Or_OBJ = r"(?:[\w\s,]+)" 
    
    # GAP HANDLER
    _ADVERB_GAP = r"(?:\s+(?:currently|historically|primarily|solely|intend\s+to|expect\s+to))?"

    # --- NEW: AUTHORIZATION VERBS (For Clause 8) ---
    # Matches: "are not permitted", "is not authorized"
    _AUTH_VERBS = r"(?:permitted|authorized|allowed|condoned)"

    # --- CLAUSES ---

    # 1. Active: "We do not [currently] use [swaps] for trading"
    CLAUSE_1 = (
        rf"\b(?:{SUBJ_Or_OBJ})\s+(?:{_NEG}){_ADVERB_GAP}\s+(?:{_ACT})\s+"
        rf"(?:any\s+|such\s+)?\S+(?:\s+\S+){{0,10}}\s+" 
        rf"(?:for\s+)?(?:on\s+a\s+)?(?:{_TRAD})\s+(?:{_PURP})?\b"
    )

    # 2. Passive: "[Swaps] are not [currently] used for trading"
    CLAUSE_2 = (
        rf"\b\S+(?:\s+\S+){{0,7}}\s+"
        rf"(?:{_NEG}){_ADVERB_GAP}\s+(?:be\s+)?(?:{_ACT})\s+"
        rf"(?:for\s+)?(?:on\s+a\s+)?(?:{_TRAD})(?:\s+(?:{_PURP}))?\b"
    )

    # 3. Short Active: "Did not use for trading" (Implicit Subject)
    CLAUSE_3 = (
        rf"\b(?:{_NEG}){_ADVERB_GAP}\s+(?:be\s+)?(?:{_ACT})\s+"
        rf"(?:(?:any\s+|such\s+)?\S+(?:\s+\S+){{0,7}}\s+)?" 
        rf"(?:for\s+)?(?:on\s+a\s+)?(?:{_TRAD})(?:\s+(?:{_PURP}))?\b"
    )

    # 4. Speculation: "We do not speculate"
    CLAUSE_4 = rf"\b(?:{SUBJ_Or_OBJ})\s+(?:{_NEG}){_ADVERB_GAP}\s+(?:speculate|trade)\b"

    # 5. None Held: "None of [assets] are held for trading"
    CLAUSE_5 = (
        rf"\bnone\s+of\s+(?:the\s+|our\s+)?\S+(?:\s+\S+){{0,7}}\s+"
        rf"(?:are|is|were|was)\s+(?:{_ACT})\s+"
        rf"(?:for\s+)?(?:{_TRAD})(?:\s+(?:{_PURP}))?\b"
    )

    # 6. Strict Header: "No trading purposes"
    CLAUSE_6 = rf"""
        \b(?:no|not)\s+                
        (?:{_TRAD})(?:\s+\S+){{0,4}}    
        (?:\s+or\s+(?:{_TRAD}|{_PURP}))? 
        (?:\s+(?:{_PURP}))?     
        \b
    """

    # 7. Explicit Denial: "Derivatives are not used..."
    CLAUSE_7 = (
        rf"\b(?:{SUBJ_Or_OBJ}|derivatives?|instruments?|contracts?)\s+"
        rf"(?:are|is|were|was)\s+not\s+"
        rf"(?:used|held|entered|designated)\s+"
        rf"(?:for\s+)?(?:{_TRAD})(?:\s+(?:{_PURP}))?\b"
    )

    # 8. NEW: "Derivatives for speculation [is/are] not permitted"
    CLAUSE_8 = (
        rf"\b(?:{SUBJ_Or_OBJ}|derivatives?)\s+" # "Use of derivatives"
        rf"(?:for|in)\s+(?:the\s+purpose\s+of\s+)?(?:{_TRAD})\s+"           # "for speculation"
        rf"(?:are|is|were|was)\s+not\s+{_AUTH_VERBS}\b"                     # "are not permitted"
    )

    pattern = build_alternation([
        CLAUSE_1, CLAUSE_2, CLAUSE_3, CLAUSE_4, 
        CLAUSE_5, CLAUSE_6, CLAUSE_7, CLAUSE_8
    ])
    
    return re.compile(pattern, re.IGNORECASE | re.VERBOSE)

# =============================================================================
# DEFINITION DETECTION (Isolated boilerplate)
# =============================================================================


def build_definition_regex() -> re.Pattern:
    """
    Matches definition boilerplate safely.
    Consumes the full sentence tail to prevent debris.
    """

    # 1. Setup Components
    instr = f"(?:{CATEGORY_REGEX.pattern})"
    subject = SUBJ  # From derivative_regex.py
    SENTENCE_TAIL = r"[^.?!]*"

    # 2. Key Verbs Grouped by Safety

    # SAFE: Legal terms that rarely appear in narrative flow
    LEGAL_VERBS = r"(?:shall\s+mean|is\s+defined\s+as|definitions?\s+of)"

    # RISKY: Common verbs that need specific subjects (Quotes, "The term", Instrument names)
    COMMON_VERBS = (
        r"(?:means?|represents?|refers?\s+to|considered\s+as|\:)"  # Add colon
    )
    # Subject Groups
    # 1. Safe Accounting Nouns (Fair Value, Notional, etc.) - Can use "is the"
    SAFE_ACCT_SUBJ = (
        r"(?:notional\s+value|contractual\s+interest|fair\s+value|market\s+value|"
        r"hedge\s+effectiveness|credit\s+risk)"
    )
    
    # 2. Instrument Names (Swaps, Forwards) - NEED STRICTER VERBS
    INSTR_SUBJ = f"(?:{CATEGORY_REGEX.pattern})" # Your LOOSE_GEN_REGEX equivalent

    # 3. Generic Definitional Objects (To anchor "is the")
    DEF_OBJECTS = r"(?:agreement|contract|exchange|obligation|instrument|transaction|commitment|arrangement)"
    pattern_list = [
        # --- 1. The "Legal Hammer" (Safe to be broad) ---
        # Matches: "Swaps shall mean...", "Hedging is defined as..."
        # We allow broad subjects here because "shall mean" is distinct.
        rf".*?\s+{LEGAL_VERBS}\s+.*{SENTENCE_TAIL}",
        # --- 2. Anchored "Means/Refers" (Strict Subjects Only) ---
        # Matches: "The term 'Swap' means...", "'Derivatives' refers to..."
        # Logic: Must start with "The term", "This caption", or a Quoted String.
        rf"(?:[Tt]he\s+term\s+|[Tt]his\s+(?:caption|account)\s+|[\"“].*?[\"”]\s+){COMMON_VERBS}{SENTENCE_TAIL}",
        # --- 3. Instrument-Subject Definitions ---
        # Matches: "Interest Rate Swaps means...", "Options are considered as..."
        # Logic: Subject MUST be a detected instrument category.
        rf"(?:a\s+)?{instr}\s+(?:{COMMON_VERBS}){SENTENCE_TAIL}",
        # --- 4. Accounting Specifics ---
        # Matches: "Notional value represents..."
        rf"{SAFE_ACCT_SUBJ}\s+(?:represents?|means?){SENTENCE_TAIL}",
        # --- 5. Corporate Definitions ---
        # Matches: "The Company defines...", "Management considers..."
        rf"(?:{subject})\s+(?:consider|define)s?\s+(?:a\s+)?{instr}.*as{SENTENCE_TAIL}",
        # --- 6. Inverted Definitions ---
        # Matches: "...is the definition of..."
        rf".*?\s+is\s+the\s+definition\s+of{SENTENCE_TAIL}",
        # --- 4. Accounting Specifics (Safe with 'is the') ---
        # "Fair value is the price..."
        rf"{SAFE_ACCT_SUBJ}\s+(?:represents?|means?|is\s+the|are\s+the){SENTENCE_TAIL}",

        # --- 5. Instrument Definitions (Strict) ---
        # A. Strong Verbs: "Swaps mean..." (Safe)
        rf"{INSTR_SUBJ}\s+(?:means?|refers?\s+to|is\s+defined\s+as){SENTENCE_TAIL}",
        
        # B. "Is The" Anchor: Requires abstract subject ("A swap") AND generic object ("is a contract")
        # Matches: "A swap is the exchange...", "An option is a contract..."
        # Avoids: "The swap is the tool..."
        rf"(?:A|An)\s+{INSTR_SUBJ}\s+is\s+(?:the|an?)\s+{DEF_OBJECTS}{SENTENCE_TAIL}",
    ]

    combined = "|".join(f"(?:{p})" for p in pattern_list)

    return re.compile(combined, re.IGNORECASE | re.VERBOSE)


def build_non_derivative_classification_regex() -> re.Pattern:
    """
    Matches statements where instruments are explicitly NOT classified/considered derivatives.
    Targets: "are not considered derivatives", "is not classified as a derivative"
    """
    # Verbs that link the subject to the classification
    verbs = [
        r"considered",
        r"classified",
        r"accounted\s+for",
        r"designated",
        r"treated",
        r"defined",
        r"viewed",
    ]

    # The classification target (singular or plural)
    targets = [
        r"derivatives?",
        r"derivative\s+instruments?",
        r"financial\s+instruments?",  # optional, but common in this context
    ]

    verb_pat = build_alternation(verbs)
    target_pat = build_alternation(targets)

    # Structure: (Auxiliary Negation) + (Classification Verb) + (Optional 'as a') + (Target)
    return re.compile(
        rf"\b(?:are|is|were|was)\s+not\s+"
        rf"{verb_pat}\s+"
        rf"(?:as\s+)?(?:a\s+|an\s+)?"
        rf"{target_pat}\b",
        re.IGNORECASE,
    )


# Compile and Export
NON_DERIVATIVE_REGEX = build_non_derivative_classification_regex()

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
PRIOR_INDICATOR = build_prior_statement_pattern_2()

PRIOR_PATTERN = build_prior_statement_pattern()

# =============================================================================
# TABLE AND MISCELLANEOUS PATTERNS
# =============================================================================


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

NON_DERIVATIVE_COMMERCIAL_KEYWORDS = [
    # The "NPNS" Exemption (Physical Contracts)
    r"normal\s+purchases?\s+(?:and|&)\s+(?:normal\s+)?sales?",
    r"NPNS",
    r"own[- ]use\s+exemption",
    # Unconditional Obligations (ASC 440)
    r"unconditional\s+purchase\s+(?:obligations?|commitments?)",
    r"take[- ]or[- ]pay",
    r"throughput\s+agreements?",
    # General Supply Chain (If not caught by Physical Inventory)
    r"supply\s+arrangements?",
    r"procurement\s+contracts?",
]
EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX = build_regex(
    NON_DERIVATIVE_COMMERCIAL_KEYWORDS
)
# Regex to find years between 1980-2099, followed by a word boundary character
YEAR_REGEX = re.compile(r"\b(19[8-9]\d|20\d{2})\b")

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
_CLEAN_AND = re.compile(r"(?:\s{2,}and\b|\band\s{2,}|,\s*and\s{2,})")


def cleanup_fragment(sentence: str) -> str:
    """
    Clean up punctuation mess after surgically removing words
    """
    # 1. Remove dangling "and"
    sentence = _CLEAN_AND.sub("", sentence)

    # 2. Normalize punctuation spacing
    sentence = _CLEAN_SPACE_COMMA.sub(",", sentence)
    sentence = _CLEAN_COMMA_SPACE.sub(", ", sentence)
    sentence = _CLEAN_SPACE_SEMICOLON.sub(";", sentence)

    # 3. Remove leading/trailing junk
    sentence = _CLEAN_LEADING_JUNK.sub("", sentence)
    sentence = _CLEAN_TRAILING_JUNK.sub("", sentence)

    # 4. Collapse spaces and strip
    sentence = re.sub(r"\s+", " ", sentence).strip()

    return sentence if len(sentence) > 10 else ""


# =============================================================================
# LINGUISTIC INTENT & FILTERING PATTERNS
# =============================================================================

# Transaction verbs (Action)
_TRANSACTION_VERBS = [r"enter", r"engage", r"transact", r"perform", r"chooses?"]
_TRANSACTION_PATTERN = build_alternation(_TRANSACTION_VERBS)

# Combined intent verbs: standard (hold, use, hedge) + transaction (enter, engage)
INTENT_VERB_PATTERN = build_alternation([VERB_PATTERN, _TRANSACTION_PATTERN])

# Speculative / Uncertain Timing Phrases
SPECULATIVE_PHRASES = [
    r"from\s+time\s+to\s+time",
    r"periodically",
    r"historically",
    r"previously",
    r"occasionally",
    r"in\s+the\s+future",
    r"in\s+future\s+periods",
    r"upon\s+occurrence",
    r"believes?",
    r"(?:may|might)\s+consider",
    r"when\s+(?:deemed\s+)?necessary",
    r"when\s+(?:chosen|choosed)",
    r"expects?\s+that",
    r"(?!not )prevent",
]

# Potential / Hypothetical Modals & Phrases
POTENTIAL_INDICATORS = [
    r"may",
    r"might",
    r"could",
    r"would",
    r"will",
    r"seek\s+to",
    r"intend\s+to",
    r"plan(?:s|ned)?\s+to",
    r"if",
    r"whether",
    # FIX: Negative lookahead allows "expect to continue" (Active) while flagging "expect to use" (Potential)
    r"expect(?:s|ed)?\s+to\s+(?!continue)",
]

# Negative Intent Components
# Updated Negative Components

NEGATIVE_AUXILIARY = [
    # Active
    r"do", r"does", r"did", 
    r"will", r"would", 
    r"can", r"could", 
    r"shall", r"should", 
    r"have", r"has", "had", # Added 'had'
    r"must",
    # Passive (Crucial for "Derivatives were not held")
    r"are", r"is", r"were", r"was", r"be" 
]


NEGATIVE_INTENT_VERBS = [r"seek", r"intend", r"plan", r"expect", r"continue"]

# Absence Indicators
ABSENCE_INDICATORS = [r"no", r"none"]

# Absence/Termination Nouns (Abstract concepts not covered by instrument regexes)
_ABSENCE_NOUNS = [
    r"outstanding",  # "no such outstanding"
    r"positions?",
    r"exposures?",
    r"obligations?",
    r"hedges?",  # "no such hedge" (generic)
    r"activit(?:ies|y)",  # "no derivative activity"
    r"involvements?",  # "no involvement with derivatives"
    r"holdings?",  # "no holdings"
]

# Termination Verbs
# If these appear before "settled", it's likely a description of mechanics, not termination.
SETTLEMENT_MODIFIERS = [
    "cash",
    "net",
    "daily",
    "monthly",
    "physically",
    "final",
    "mandatory",
    "annually",
    "weekly",
]
_settle_lookbehind = "".join([rf"(?<!\b{word}\s)" for word in SETTLEMENT_MODIFIERS])
# In termination_filter.py

TERMINATION_VERBS = [
    # --- SAFE VERBS (Past/Present/Participle) ---
    # Regex note: We removed |ion, |ity, |ment, |y suffixes
    r"expir(?:e(?:d|s)?|ing)",  # Matches: expire, expired, expiring.  STOPS: expiration, expiry
    r"matur(?:e(?:d|s)?|ing)",  # Matches: mature, matured, maturing.  STOPS: maturity
    r"terminat(?:e(?:d|s)?|ing)",  # Matches: terminate, terminated.      STOPS: termination
    r"ceas(?:e(?:d|s)?|ing)",  # Matches: cease, ceased
    r"retir(?:e(?:d|s)?|ing)",  # Matches: retire, retired.
    r"clos(?:e(?:d|s)?|ing)(?!\s+(?:price|rate|date|balance|value))",
    r"liquidat(?:e(?:d|s)?|ing)",  # Matches: liquidate, liquidated.  STOPS: liquidation
    r"unwound",
    r"unwind",
    r"exercis(?:e(?:d|s)?|ing)",  # Matches: exercise, exercised.        STOPS: exercisable
    r"extinguish(?:e(?:d|s)?|ing)",  # Matches: extinguish, extinguished.   STOPS: extinguishment
    r"novat(?:e(?:d|s)?|ing)",  # Matches: novate, novated.            STOPS: novation
    r"cancel(?:l(?:ed|ing)|s)?",  # Matches: cancel, cancelled.          STOPS: cancellation
    r"rescind(?:e(?:d|s)?|ing)",  # Matches: rescind, rescinded.         STOPS: rescission
    r"void(?:ed)?",
    r"withdraw(?:n|s|ing)?",
    r"withdrew",
    r"discontinu(?:e(?:d|s)?|ing)",  # Matches: discontinued.               STOPS: discontinuation
    r"exit(?:ed|s|ing)?",
    r"redeem(?:e(?:d|s)?|ing)",  # Matches: redeem, redeemed.           STOPS: redemption
    r"repudiat(?:e(?:d|s)?|ing)",
    # --- SAFEGUARDED SETTLEMENT (From previous turn) ---
    rf"(?<!{_settle_lookbehind}\s)settl(?:e(?:d)|ing)",
    r"sold",
    r"wind(?:ing)?\s+down",
    r"dispos(?:e(?:d|s)?|ing)",
    r"derecogni[sz](?:e|ed|ing)",
    r"divest(?:ed|s|ing)?",
    r"preterminat(?:e(?:d|s)?|ing)",
    r"accelerat(?:e(?:d|s)?|ing)",
    r"relinquish(?:ed|es|ing)?",
    r"lapse(?:d|s|ing)?",
    r"forfeit(?:ed|s|ing)?",
]
TERMINATION_NOUNS = [
    # --- STATES (Strongest) ---
    r"expir(?:ation|y)",  # Matches: expiration, expiry
    r"maturit(?:y|ies)",  # Matches: maturity, maturities
    r"terminat(?:ion|or)",  # Matches: termination
    r"redemption",  # Matches: redemption
    # --- EVENTS (Transactional) ---
    r"extinguishment",  # Matches: extinguishment
    r"settlement",  # Matches: settlement
    r"cancellation",  # Matches: cancellation
    r"novation",  # Matches: novation
    r"rescission",  # Matches: rescission
    r"discontinu(?:ance|ation)",  # Matches: discontinuance, discontinuation
    r"withdrawal",  # Matches: withdrawal
    r"retirement",  # Matches: retirement
    r"unwinding",  # Matches: unwinding
    r"repudiation",  # Matches: repudiation
    r"cessation",  # Matches: cessation
    r"closure",  # Matches: closure
    r"exit",  # Matches: exit (noun form)
    r"liquidation",
    r"forfeiture",
    r"acceleration",
    r"close[- ]?out",
    r"lapse",
    r"forfeiture",
    r"derecognition",
    r"wind[- ]?down",
    r"sale",
    r"disposition",
    r"transfer",
    r"assignment",
    r"relinquishment",
    r"voiding",
    r"divestiture",
]

ALL_TERM_TERMS = TERMINATION_VERBS + TERMINATION_NOUNS
TERMINATION_ALL_REGEX = build_regex(ALL_TERM_TERMS)


# Active / Timing Indicators (New)
ACTIVE_INDICATORS = [
   "currently",
    "presently",
    "at present",
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
    "not zero",
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
        r"(?:\w+\s+){0,3}"
        rf"({INTENT_VERB_PATTERN})\b",
        re.IGNORECASE,
    )


def build_vague_timing_regex() -> re.Pattern:
    """Matches: "from time to time", "in the future" """
    return re.compile(rf"\b{build_alternation(SPECULATIVE_PHRASES)}\b", re.IGNORECASE)


# Add this alongside your other lists
NEGATIVE_CONTRACTIONS = [
    # Active
    r"do[nN]['’]?[tT]",  r"does[nN]['’]?[tT]", r"did[nN]['’]?[tT]",
    r"wo[nN]['’]?[tT]",  r"would[nN]['’]?[tT]",
    r"ca[nN]['’]?[tT]",  r"cannot", r"could[nN]['’]?[tT]",
    r"should[nN]['’]?[tT]", r"sha[nN]['’]?[tT]",
    r"have[nN]['’]?[tT]", r"has[nN]['’]?[tT]", r"had[nN]['’]?[tT]",
    # Passive
    r"are[nN]['’]?[tT]", r"is[nN]['’]?[tT]", 
    r"was[nN]['’]?[tT]", r"were[nN]['’]?[tT]"
]

def build_negation_prefix_pattern() -> str:
    """
    Returns a regex string matching:
    1. Standard Negation: "did not", "was not", "will not"
    2. Contractions: "didn't", "wasn't"
    3. Absolute Negation: "never"
    """
    # 1. Standard: Auxiliary + Not
    aux_full = build_alternation(NEGATIVE_AUXILIARY)
    pattern_full = rf"\b{aux_full}\s+not\b"

    # 2. Contractions
    pattern_contract = rf"\b{build_alternation(NEGATIVE_CONTRACTIONS)}\b"

    # 3. Absolute (The new addition)
    abs_neg = [
        "never",
        "neither"
    ]
    pattern_absolute = rf"\b{build_alternation(abs_neg)}\b"

    # Combine: (did not | didn't | never)
    return rf"(?:{pattern_full}|{pattern_contract}|{pattern_absolute})"


def build_negative_intent_regex() -> re.Pattern:
    """
    Matches: "does not intend", "doesn't intend", "won't seek", "couldn't plan"
    """
    _neg_verb = build_alternation(NEGATIVE_INTENT_VERBS)

    # Get the unified negation start (handles "could not" AND "couldn't")
    _neg_prefix = build_negation_prefix_pattern()

    _neg_pattern_standard = rf"{_neg_prefix}\s+(?:{ACTIVE_PATTERN}\s+)?{_neg_verb}\s+to"

    # "has no plans to" remains separate as it uses a noun structure
    _neg_pattern_plans = r"\b(?:had|has|have)\s+no\s+plans?\s+to"

    return re.compile(
        rf"(?:{_neg_pattern_standard}|{_neg_pattern_plans})\b", re.IGNORECASE
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
    
    # 1. Triggers
    triggers = build_alternation(ABSENCE_INDICATORS)

    # 2. Semantic Modifiers (The "Meat")
    # Expands your placeholders to cover standard list items
    modifiers = [
        "exchange", "rate", "currency", "interest", "foreign",
        "commodity", "equity", "credit", "market", "forward",
        "future", "option", "swap", "purchase", "sale",
        "cash", "fair", "value", "material", "significant",
        "hedging", "derivative", "financial"
    ]
    
    # Combine explicit placeholders with your LOOSE_GEN_REGEX
    # This allows "No [call] options" or "No [interest] rate"
    semantic_modifier = rf"(?:{build_alternation(modifiers)}|{LOOSE_GEN_REGEX.pattern})"

    # 3. Small Filler (The "Glue")
    # Matches 0-3 "garbage" tokens (punctuation, conjunctions, adjectives not in list)
    # e.g., "such", "any", "of the", ",", "or"
    small_filler = r"(?:\S+\s+){0,3}"

    # 4. The Gap Unit
    # A single link in the chain: [Filler] + [Semantic Word]
    # e.g., "such interest" or ", forward"
    gap_unit = rf"(?:{small_filler}{semantic_modifier})"

    # 5. The Chain
    # Allow 0 to 5 of these units to precede the final target
    # Matches: "[such interest] (rate), [forward] (exchange), [or commodity]"
    gap_chain = rf"(?:{gap_unit}\s+){{0,5}}"

    # 6. Target Instrument
    # The final noun must be a strong derivative term
    # (Reuse existing definitions)
    target = rf"(?:{STRICT_REGEX.pattern}|{LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"

    return re.compile(
        rf"\b{triggers}\b\s+"      # "No"
        rf"{gap_chain}"            # The Semantic Chain
        rf"{small_filler}"         # Final connector ("or")
        rf"{target}\b",            # "contracts"
        re.IGNORECASE
    )


def build_did_not_hold_regex() -> re.Pattern:
    """
    Matches: "did not hold", "didn't enter", "couldn't engage" in swaps, derivatives
    Note: if the sentence mentions that it can't do something, then we don't need the sentence anyways.
    """
    # Use the same unified prefix
    _neg_prefix = build_negation_prefix_pattern()

    _instrument_object = rf"(?:{STRICT_REGEX.pattern}|{LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"
    # _fillers = (
    #     r"(?:such\s+|any\s+|" rf"{MATERIAL_PATTERN}\s+|" rf"{ACTIVE_STATE_PATTERN}\s+)*"
    # )

    return re.compile(
        # Replace the hardcoded (did|does...) with the unified prefix
        # We do not currently have XXX instruments
        rf"{_neg_prefix}\s+(?:{ACTIVE_PATTERN}\s+)?(?:{INTENT_VERB_PATTERN})\s+(?:\S+\s+){{0,12}}"
        rf"{_instrument_object}\b",
        re.IGNORECASE,
    )


def build_termination_regex() -> re.Pattern:
    """Matches: "expired", "matured", "unwound" """
    return re.compile(rf"\b{build_alternation(TERMINATION_VERBS)}\b", re.IGNORECASE)


TRADING_STATEMENTS_REGEX = build_trading_denial_pattern()

def check_for_instrument(sentence: str, strict: bool = False) -> bool:
    from table_processor import TABLE_ANCHOR

    """
    Determines if the instrument name is still present in the paragraph/sentence.
    """
    # Check for length
    if len(sentence) < MIN_SENTENCE_LENGTH:
        return False
    if TABLE_ANCHOR in sentence:
        return True
    # 1. SPECIFIC MATCHES (The Only Safe Harbor for Orphans)
    # If it says "Interest Rate Swap", it survives ANY filter.
    if CATEGORY_REGEX.search(sentence):
        # Remove the phrase itself; there should still be something left
        remaining = CATEGORY_REGEX.sub("", sentence).strip()
        # Remove the period at the end
        if remaining.endswith("."):
            remaining = remaining[:-1]
        return True if len(remaining) > 5 else False

    # 1.5 If specfics failed, soft regex only (we trust the context anyways)
    if SOFT_CATEGORY_REGEX.search(sentence):
        return True

    # 2. STRICT GENERICS (Notionals, "Swap Agreements")
    # ONLY Valid if we have Context (Anchor) or Recency (Year Promotion).
    # If strict=True (Orphaned & Undated), these must die to prevent Zombies.
    if not strict:
        if STRICT_GEN_REGEX.search(sentence):
            return True

    # 3. LOOSE MATCHES (Weakest)
    # "Contracts", "Options", "Positions"
    # Requires Context (Anchor) AND Hedging Keywords.
    if not strict:
        if LOOSE_GEN_REGEX.search(sentence):
            if HEDGING_CONTEXT_REGEX.search(sentence) or SOFT_GEN_REGEX.search(
                sentence
            ):
                return True

    return False


def validate_instrument_retention(
    paragraphs: List[str],
    categories: List[str],
    url: str,
    strict: bool = False,
    year: Optional[int] = None,
) -> Tuple[List[str], List[str], List[Tuple[str, str, str]]]:
    """
    Final safety check with Dependency Anchoring and Year-Based Promotion.

    Logic:
    1. Anchor Present: Validate the whole block (Context survives).
    2. Anchor Missing (Orphans):
       - If 'year' is provided: Split into atomic sentences. Validating individually ensures
         a current-year sentence doesn't accidentally 'save' unrelated generic noise.
       - If 'year' is None: Validate the block strictly (Standard Phase 5/7 logic).
    """
    validated_paragraphs = []
    validated_categories = []
    discards = []

    for text, cat in zip(paragraphs, categories):
        has_anchor = ANCHOR_TAG in text

        # --- STRATEGY: SPLIT ORPHANS IF YEAR CHECKING IS ACTIVE ---
        # We only split if:
        # 1. We are in a Year-Check phase (year is not None)
        # 2. The Anchor is missing (If the Anchor is there, the context is valid, so keep the block)
        if year and not has_anchor:
            # Split the orphaned block back into atomic components
            sentences = [
                s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
            ]
        else:
            # Treat as a single unit (Standard behavior)
            sentences = [text]

        for unit in sentences:
            # Clean the tag for regex checking
            clean_unit = unit.replace(ANCHOR_TAG, " ")

            # Determine Mode
            effective_strict = strict
            promoted_to_anchor = False

            if not has_anchor:
                # Default: Kill orphans
                effective_strict = True

                # Salvation: Year-Based Promotion
                if year:
                    years_found = [int(y) for y in YEAR_REGEX.findall(clean_unit)]
                    # If this specific sentence is current, it stands alone
                    if any(y >= year for y in years_found):
                        effective_strict = False
                        promoted_to_anchor = True

            # Validate
            if check_for_instrument(clean_unit, strict=effective_strict):
                # Tagging: If promoted, it becomes a new Anchor
                if promoted_to_anchor and ANCHOR_TAG not in unit:
                    final_text = ANCHOR_TAG + unit.lstrip()
                else:
                    final_text = unit

                validated_paragraphs.append(final_text)
                validated_categories.append(cat)
            else:
                # Logging
                if has_anchor:
                    reason = "lost_instrument_reference"
                elif year and effective_strict is False:
                    reason = "orphaned_but_current_failed_check"
                else:
                    reason = "lost_anchor_context"

                discards.append((url, clean_unit, reason))

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

# Exhibit/Reference nouns
EXHIBIT_NOUNS = [
    "exhibit",
    "reference",
    "note",
    "appendix",
    "schedule",
    "article",
    "section",
    "subsection",
    "statement",
    "table",
    "page",
    "pp.",
    "p.",
    "figure",
    "chart",
]
EXHIBIT_FRAGMENT = build_alternation(EXHIBIT_NOUNS)
def build_reference_patterns() -> re.Pattern:
    """
    Builds a regex that catches navigational pointers (e.g., 'See Note X', 'Table below')
    WITHOUT consuming the rest of the sentence. This preserves context when the
    reference is embedded in a valid sentence (e.g., "The swaps shown in the table below are active").
    """

    patterns = [
        # --- 1. Explicit Note/Section References ---
        # Matches: "See Note 5", "Refer to Note 5", "In Note 5"
        r"(?:[Ss]ee|[Rr]efer(?:ence)?\s+(?:to|is\s+made\s+to)|[Ii]n)\s+(?:Note|NOTE|Section)\s+(?:No\.\s+)?\d+[A-Z]?(?:\s*\(s\))?",
        # --- 2. Descriptive Note References ---
        # Matches: "Note 5 provides...", "Note 10 discusses..."
        r"\b(?:Note|NOTE|Section)\s+(?:No\.\s+)?\d+[A-Z]?\s+(?:provides?|details?|discloses?|discusses?|presents?)",
        # --- 3. Table/Schedule Pointers (Directional) ---
        # Matches: "The table below", "The following schedule", "The accompanying exhibit"
        # Logic: Noun + Direction OR "Following" + Noun
        r"[Tt]he\s+(?:following\s+)?(?:table|schedule|exhibit|note|chart|graph)\s+(?:below|above|following|accompanying|herein)",
        r"[Tt]he\s+(?:following|accompanying)\s+(?:table|schedule|exhibit|note|chart|graph)",
        # --- 4. Passive Pointers ---
        # Matches: "As shown in the table", "As discussed below"
        r"[Aa]s\s+(?:shown|provided|detailed|presented|summarized|disclosed|set\s+forth|discussed|reflected)\s+(?:in\s+the\s+(?:table|schedule|exhibit|note)|below|above|herein)",
        # --- 5. Embedded Locators ---
        # Matches: "presented in the table below", "included in the following table"
        # This catches your specific example case.
        r"(?:presented|included|summarized|set\s+forth|reflected)\s+in\s+(?:the\s+)?(?:following\s+)?(?:table|schedule|exhibit|note)\s+(?:below|above|following)?",
        # --- 6. Trailing Identifiers ---
        # Matches: "...(Table 1)", "...- Schedule II"
        r"(?:[.,;:\-\s]|\s+and\s+)\s*(?:table|schedule|exhibit|note)\s+No\.\s+\d+",
    ]

    # No SENTENCE_TAIL. We rely on text cleaning to scrub the debris.
    return re.compile(r"|".join(patterns), re.IGNORECASE)

# Exhibit/Reference nouns
EXHIBIT_NOUNS = [
    "exhibits",
    "references",
    "note",
    "appendix",
    "schedule",
    "article",
    "section",
    "subsection",
    "statement",
    "table",
    "No.",
    "page",
    "pp.",
    "p.",
    "figure",
    "chart",
]
EXHIBIT_FRAGMENT = build_alternation(EXHIBIT_NOUNS)

def build_simple_reference_regex() -> re.Pattern:
    """
    Detects sentences that are primarily navigational pointers.
    Structure: [Pointer Verb] + [Exhibit Noun] OR [Exhibit Noun] + [Direction]
    """
    
    # 1. Pointer Anchors (Start of phrase usually)
    pointers = [
        r"see", 
        r"refer\s+to", 
        r"reference\s+is\s+made\s+to",
        r"included\s+in", 
        r"contained\s+in", 
        r"set\s+forth\s+in",
        r"discussed\s+in", 
        r"as\s+shown\s+in",
        r"as\s+presented\s+in",
        r"as\s+detailed\s+in"
    ]
    pointer_alt = build_alternation(pointers)

    # 2. Directions (for "Table below")
    directions = [
        "below", "above", "following", "accompanying", "attached", "herein"
    ]
    direction_alt = build_alternation(directions)

    # PATTERN A: "See Note 5", "Refer to the Table"
    # Matches: (Pointer) (Optional 'the') (Noun)
    pat_a = rf"\b(?:{pointer_alt})\s+(?:the\s+)?(?:{EXHIBIT_FRAGMENT})\b"

    # PATTERN B: "The table below", "The accompanying schedule"
    # Matches: (Noun) (Direction)
    pat_b = rf"\b(?:{EXHIBIT_FRAGMENT})\s+(?:{direction_alt})\b"
    
    pat_b2 = rf"\b(?:{direction_alt})\s+(?:{EXHIBIT_FRAGMENT})\b"

    # PATTERN C: "Note 5.", "Exhibit 10." (Explicit Numbering at sentence start/end)
    # Checks for Noun + Number (1-3 digits)
    pat_c = rf"\b(?:{EXHIBIT_FRAGMENT})\s+(?:No\.\s+)?\d{{1,3}}\b"

    return re.compile(rf"(?:{pat_a}|{pat_b}|{pat_b2}|{pat_c})", re.IGNORECASE)

# Compile once
IS_REFERENCE_REGEX = build_simple_reference_regex()


def build_information_reference_regex() -> re.Pattern:
    """
    Matches informational pointers like:
    - "For more information regarding..."
    - "For further details on..."
    - "For a complete discussion of..."
    """

    # Adjectives modifying the noun
    adjectives = [
        "more",
        "further",
        "additional",
        "extra",
        "detailed",
        "supplemental",
        "complete",
        "full",
    ]

    # The nouns themselves
    nouns = [
        "information",
        "details?",
        "discussions?",
        "disclosures?",
        "descriptions?",
    ]

    # Connectors to the subject (Optional)
    connectors = [
        "regarding",
        "concerning",
        "on",
        "about",
        r"related\s+to",
        r"with\s+respect\s+to",
    ]

    adj_pat = build_alternation(adjectives)
    noun_pat = build_alternation(nouns)
    conn_pat = build_alternation(connectors)

    # Structure: "For" + (Optional [Adjective]) + [Noun] + (Optional [Connector])
    pattern = (
        rf"([Ff]or)?\s+"
        rf"(?:(?:a\s+|an\s+)?(?:{adj_pat})\s+)?"  # <--- Added '?' at the end to make the whole block optional
        rf"(?:{noun_pat})"
        rf"(?:\s+(?:{conn_pat}))?"
    )

    return re.compile(pattern, re.IGNORECASE)


# Compile and Export
MORE_INFO_REGEX = build_information_reference_regex()
REFERENCE_CLEANUP_REGEX = build_reference_patterns()

# New Header and Structural Cleanup Patterns
# In main/database_filter/derivative_regex.py

# New Header and Structural Cleanup Patterns
HEADER_CLEANUP_PATTERNS = [
    # 1. Markdown Headers: Targets # Title # and similar structure
    (re.compile(r"\n\#+\s*.*?\#*\n", re.IGNORECASE), "\n\n"),
    # 2. Markdown Bold/Italics Emphasis: Targets **Title** or *Title* or _Title_
    # Replaces with space to separate merged text fragments
    (re.compile(r"\*{1,}.*?\*{1,}", re.IGNORECASE), " "),
    (re.compile(r"\_[^\s_].*?[^\s_]\_", re.IGNORECASE), " "),
    # 3. ALL-CAPS DERIVATIVE HEADER DELETION
    # Targets long, non-narrative all-caps sequences containing key terms
    (
        re.compile(
            r"^(?:[^a-z\n]*?(?:DERIVATIVES?|HEDGING)[^a-z\n]*?)(?=[A-Z][a-z])",
            re.MULTILINE,
        ),
        " ",
    ),
    (
        re.compile(r"^\s*[^a-z\n]*?(?:DERIVATIVES?|HEDGING)[^a-z\n]*?$", re.MULTILINE),
        "\n\n",
    ),
    # 4. QUOTED HEADER DELETION (NEW)
    # Targets lines like: "Hedging Activities", "Derivative Instruments"
    # Logic: Start of line + Quote + (Key Terms) + Quote + End of line
    (
        re.compile(
            r'^\s*["“][^"”\n]*?(?:Derivatives?|Hedging|Fair\s+Value|Financial\s+Instruments)[^"”\n]*?["”]\s*$',
            re.MULTILINE | re.IGNORECASE,
        ),
        "\n\n",
    ),
]
# =============================================================================
# BANK ENTITY LISTS (New)
# =============================================================================
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
BANK_SCORING_REGEX = re.compile(
    r"\b" + build_alternation(BANK_ENTITIES) + r"\b", re.IGNORECASE
)

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

# Compile
EXCLUDE_REGEX_LIBOR_TRANSITION = build_regex(LIBOR_TRANSITION_KEYWORDS)


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


def build_entity_exclusion_regex() -> Tuple[re.Pattern, str]:
    """
    Matches official entity names AND their acronyms that contain trigger words
    (Futures, Swaps, Options, Derivatives, Exchange) to prevent false positive classification.
    """
    entities = (
        [
            # --- 1. Regulators & Standard Setters ---
            r"\b(?:U\.?S\.?\s+)?Commodity\s+Futures\s+Trading\s+Commission\b",
            r"\bCFTC\b",
            r"\bNational\s+Futures\s+Association\b",
            r"\bNFA\b",
            r"\bSecurities\s+(?:[Aa]nd|&)\s+Exchange\s+Commission\b",
            r"\bSEC\b",
            r"\bPublic\s+Company\s+Accounting\s+Oversight\s+Board\b",
            r"\bPCAOB\b",
            r"\bFederal\s+Energy\s+Regulatory\s+Commission\b",
            r"\bFERC\b",
            r"\bPrudential\s+Regulators?\b",  # Generic but common in bank filings
            # --- 2. Associations (Master Agreements) ---
            r"\bInternational\s+Swaps\s+(?:[Aa]nd|&)\s+Derivatives\s+Association\b",
            r"\bISDA\b",
            r"\bFutures\s+Industry\s+Association\b",
            r"\bFIA\b",
            r"\bSecurities\s+Industry\s+(?:[Aa]nd|&)\s+Financial\s+Markets\s+Association\b",
            r"\bSIFMA\b",
            # --- 3. Exchanges (The "Option/Future/Swap" Triggers) ---
            # Chicago Group
            r"\bChicago\s+Board\s+Options\s+Exchange\b",
            r"\bCBOE\b",
            r"\bChicago\s+Mercantile\s+Exchange\b",
            r"\bCME\b",
            r"\bChicago\s+Board\s+of\s+Trade\b",
            r"\bCBOT\b",
            # New York / ICE Group
            r"\bNew\s+York\s+Stock\s+Exchange\b",
            r"\bNYSE\b",
            r"\bNew\s+York\s+Mercantile\s+Exchange\b",
            r"\bNYMEX\b",
            r"\bCommodity\s+Exchange(?:,?\s+Inc\.?)?\b",
            r"\bCOMEX\b",
            r"\bIntercontinental\s+Exchange\b",
            r"\bICE\b",
            # International / Other
            r"\bLondon\s+Metal\s+Exchange\b",
            r"\bLME\b",
            r"\bLondon\s+Stock\s+Exchange\b",
            r"\bLSE\b",
            r"\bPhiladelphia\s+Stock\s+Exchange\b",
            r"\bPHLX\b",
            r"\bEurex\b",
            # --- 4. Clearing Houses (Critical for "Cleared Swaps" noise) ---
            r"\bOptions\s+Clearing\s+Corporation\b",
            r"\bOCC\b",
            r"\bLondon\s+Clearing\s+House\b",
            r"\bLCH\b",
            r"\bCME\s+Clearing\b",
            r"\bICE\s+Clear\b",
            # --- 5. Generic / Investment Vehicles ---
            r"\bmutual\s+funds?\b",
            r"\bindex\s+funds?\b",
            r"\bexchange[- ]traded\s+funds?\b",
            r"\bETFs?\b",
            r"\bmoney\s+market\s+funds?\b",
            r"\bpension\s+funds?\b",  # Reinforces Plan Asset exclusion
            r"\bUniform\s+Commercial\s+Code\b",
            r"\bUCC\b",
            r"\b[hH]edge\s+(?:[fF]unds?|[bB]anks?|[Pp]roviders?)\b",
            r"\b[Ss]wap\s+(?:[dD]ealers?|[pP]articipants?)\b",  # <--- ADDED: Regulatory Entity Role
        ]
        + ISSUER_TERMS
        + BANK_ENTITIES
    )

    # --- 6. Dynamic Fund Pattern (Your existing logic) ---
    # Matches: "United States Commodity Index Fund", "Oil Derivatives Trust"
    triggers = r"(?:Commodity|Oil|Gas|Energy|Derivatives?|Futures?|Options?|Swaps?)"
    suffixes = r"(?:Fund|Trust|ETF|LP|L\.P\.|Holdings?|Portfolio|Group|Capital)"
    fund_pattern = rf"\b(?:[A-Z][a-z]+\s+)*{triggers}(?:\s+[A-Z][a-z]+)*\s+{suffixes}\b"

    all_patterns = entities + [fund_pattern]

    # Use build_alternation to ensure longest matches (e.g., full name) are prioritized
    # Note: We enforce word boundaries \b for short acronyms inside the list above
    pattern = build_alternation(all_patterns)
    return re.compile(pattern), " E_ "


# Compile and Export
ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN = build_entity_exclusion_regex()


def build_non_derivative_instrument_regex() -> re.Pattern:
    """
    Prevents loose_gen_regex from assuming that context still exists
    
    :return: Description
    :rtype: Pattern[Any]
    """
    placeholders = [
        # --- Existing ---
        "debt",
        "credit",
        # --- Explicit Exemptions (SEC Item 305) ---
        "lease",  #
        "insurance",  #
        "pension",  #
        "warranty",  #
        "purchase",  # Matches "Purchase contract"
        "trade",  # Matches "Trade agreement
        "deferred compensation",  #
        "stock option",  #
        "stock purchase",  #
        "equity method",  # Matches "Equity method contract"
    ]

    placeholder_alternation = build_alternation(placeholders)
    return re.compile(
        rf"\b{placeholder_alternation}\s+{suffix_alternation}\b", re.IGNORECASE
    )

NON_DERIVATIVE_REGEX = build_non_derivative_instrument_regex()


# Unique marker to identify the "Target" sentence that anchors a context window.
# Used to enforce dependency: if the anchor is deleted, loose dependents must die.
ANCHOR_TAG = " A_ "
# =============================================================================
# STRICT CONTEXT DEFINITIONS (The "High Value" Keywords)
# =============================================================================
# These terms are so specific to a category that if they appear in a generic sentence,
# we are 99% sure of the category without needing ML or historical lookback.

# 1. INTEREST RATE (Strict)
# Focus: Specific rates, benchmarks, and directional payment terms
# In derivative_regex.py

IR_STRICT_TERMS = [
    rf"(?<!foreign[- ])interest[- ]rate\s+{_RISK_ALTERNATION}",
    rf"(?<!currency[- ])interest[- ]rate\s+{_RISK_ALTERNATION}",
    r"(?:pay|receive)[- ](?:fixed|variable|floating)",
    r"interest\s+payments?",
    r"SOFR",
    "LIBOR",
    "EURIBOR",
    "SONIA",
    "TONAR",
    r"amortization\s+of\s+debt",
    # --- NEW ADDITIONS (The Safe Rates) ---
    # These imply Interest Rate mechanics specifically
    r"(?:floating|variable|fixed|prime|treasury|(?<!currency[- ])interest|(?<!foreign[- ])interest)[- ]rates?",
    r"fed(?:eral)?\s+funds\s+rates?",
    r"credit\s+agreements?"
]

# 2. FOREIGN EXCHANGE (Strict)
# Focus: Currency risk, translation, and remeasurement
FX_STRICT_TERMS = [
    rf"foreign\s+(?:currency|exchange)\s+{_RISK_ALTERNATION}",
    rf"currency\s+{_RISK_ALTERNATION}",
    rf"foreign interest[- ]rates?\s+{_RISK_ALTERNATION}",
    rf"foreign interest[- ]rates?",
    r"functional\s+currenc(?:y|ies)",
    r"remeasurement\s+(?:gain|loss)",
    r"foreign\s+operations?",
    r"denominated\s+in",
    r"cross[- ]currency",
    r"(?:forward|foreign|currency)\s+exchanges?",
    r"hedges?\s+of\s+(?:the\s+)?net\s+investments?",
    r"net\s+investment\s+hedges?",
] + build_currency_patterns()  # Specific currency names are strict context

# 3. COMMODITY (Strict)
# Focus: Physical assets and specific commodity names
# =============================================================================
# STRICT CONTEXT DEFINITIONS (Updated)
# =============================================================================

# 1. Helper: Build the commodity alternation once
_COMMODITY_NAMES = build_alternation(COMMON_COMMODITIES)

# 2. COMMODITY (Strict)
# FIX: Do NOT include raw commodity names.
# Only include them if attached to "price", "cost", "risk", "hedge", "volaitity"
venues = [
        r"\bNYMEX\b", r"\bNew\s+York\s+Mercantile\s+Exchange\b",
        r"\bCOMEX\b", r"\bCommodity\s+Exchange\b",
        r"\bCBOT\b",  r"\bChicago\s+Board\s+of\s+Trade\b",
        r"\bCME\b",   r"\bChicago\s+Mercantile\s+Exchange\b",
        r"\bICE\b",   r"\bIntercontinental\s+Exchange\b",
        r"\bLME\b",   r"\bLondon\s+Metal\s+Exchange\b",
        r"\bCBOE\b",  r"\bChicago\s+Board\s+Options\s+Exchange\b",
]
CP_STRICT_TERMS = [
    # General terms
    rf"{_COMMODITY_NAMES}(?:\s+\w+){0,3}{_RISK_ALTERNATION}"
    r"raw\s+material\s+costs?",
    r"fuel\s+surcharges?",
    # Financial Modifier + Specific Commodity
    # Matches: "Price of corn", "Hedging of oil", "Cost of gold"
    rf"{_RISK_ALTERNATION}(?:\s+\w+){0,3}{_COMMODITY_NAMES}",
    rf"{_COMMODITY_NAMES}\s+{PHYSICAL_DELIVERY_PATTERN}", # natural gas inventory, etc,
] + venues

# Focus: Convertibles, Warrants, Valuation Models, and Equity Risk
EQ_STRICT_TERMS = [
    # 1. Risk & Price Contexts (Expanded with _RISK_ALTERNATION)
    rf"equity\s+(?:price|{_RISK_ALTERNATION})",
    rf"stock\s+(?:price|appreciation|option|{_RISK_ALTERNATION})",
    rf"share\s+(?:price|{_RISK_ALTERNATION})",
    # 2. Convertible Instruments
    rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))",
    # 4. Specific Instruments
    r"accelerated\s+share\s+repurchases?",
    r"capped\s+calls?",
    # 5. Indices (Strict indicators of Equity category)
    r"S\&P\s+500",
    r"Nasdaq",
    r"Dow\s+Jones",
    # 6. Valuation & Metrics
    r"dividend\s+yield",
    r"Black[- ]Scholes",
    r"Monte[- ]Carlo",
    r"Lattice\s+model",
]
# Build Regexes
IR_STRICT_CONTEXT_REGEX = build_regex(IR_STRICT_TERMS)
FX_STRICT_CONTEXT_REGEX = build_regex(FX_STRICT_TERMS)
CP_STRICT_CONTEXT_REGEX = build_regex(CP_STRICT_TERMS)
EQ_STRICT_CONTEXT_REGEX = build_regex(EQ_STRICT_TERMS)


STRICT_CONTEXT_MAP = {
    "ir": IR_STRICT_CONTEXT_REGEX,
    "fx": FX_STRICT_CONTEXT_REGEX,
    "cp": CP_STRICT_CONTEXT_REGEX,
    "eq": EQ_STRICT_CONTEXT_REGEX,
    "cr": CR_CONTEXT_REGEX,
}


def aggregate_discards(
    discards: List[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    """
    Groups multiple discards with the same URL and reason into a single row.
    Concatenates the texts with a separator for auditing.

    Args:
        discards: List of (url, sentence, discard_reason)

    Returns:
        Aggregated list where multiple discards with same (url, reason) are combined
    """

    grouped = defaultdict(list)

    # Group by (url, reason)
    for url, sentence, reason in discards:
        grouped[(url, reason)].append(sentence)

    # Reconstruct as single rows with concatenated text
    result = []
    for (url, reason), sentences in grouped.items():
        # Join multiple sentences with a separator for readability
        combined_text = " ||| ".join(sentences)
        result.append((url, combined_text, reason))

    return result


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


# Export this
NON_DER_CAP_FLOOR_REGEX = build_embedded_cap_floor_regex()


def create_strict_fair_value_regex() -> re.Pattern:
    """
    Captures ONLY 'Sophisticated' Fair Value usage.
    Excludes standard 'Fair Value of Financial Instruments' disclosures.
    """

    # 1. Models (Unambiguous)
    model_pattern = r"Black[- ]Scholes|Monte[- ]Carlo|Binomial|Lattice"

    strict_terms = [
        # Actionable Fair Value (Implies Trading/Derivatives)
        r"mark[- ]to[- ]market",
        r"changes?\s+in\s+fair\s+value",  # "Change in" implies income statement recognition
        r"fair\s+value\s+option",  # Specific election (FVO)
        r"carried\s+at\s+fair\s+value",  # "Carried at" implies recurring measurement
        r"measured\s+at\s+fair\s+value",
        # Specific Complex Liabilities
        r"derivative\s+liability",
        r"warrant\s+liability",
        r"embedded\s+derivative",
        r"(?<!not\s)bifurcat(?:ed|ion|ing)",
        # Hierarchy (Strong signal of complex assets)
        r"Level\s+3",  # Level 1/2 are too common (Cash equivalents), Level 3 is rare/complex
        # Valuation Models
        model_pattern,
    ]

    pattern = "|".join(strict_terms)
    return re.compile(pattern, re.IGNORECASE)


# Export this
FV_REGEX = create_strict_fair_value_regex()

# =============================================================================
# NON-FINANCIAL DERIVATIVE EXCLUSIONS (NEW)
# =============================================================================
# Targets: "Derivative Works" (IP), "Plasma Derivatives" (Bio), "Chemical Derivatives"
NON_FINANCIAL_KEYWORDS = [
    # 1. Intellectual Property / Software
    r"derivative\s+works?",
    r"open\s+source",
    r"source\s+code",
    r"general\s+public\s+license",
    r"gpl",
    r"creative\s+commons",
    # 2. Biology / Pharma / Chemistry
    r"plasma",
    r"blood",
    r"fractionation",
    r"cellulose",
    r"fatty\s+acids?",
    r"proteins?",
    r"enzymes?",
    r"polymers?",
    r"molecules?",
    r"compounds?",
    r"substances?",
    r"isolates?",
    r"analogs?",
    r"homologs?",
    r"isomers?",
    r"metabolites?",
    r"synthesis",
    r"biosimilars?",
    # 3. Mathematics (Calculus context)
    r"integrals?",
    r"calculus",
    r"gradients?",
    # 4. The "And Its Derivatives" Trap (Generic)
    r"(?:and|or)\s+(?:their|its)\s+derivatives?",
]

# Compile
EXCLUDE_NON_FINANCIAL_REGEX = build_regex(NON_FINANCIAL_KEYWORDS)

# Export
TRADING_VENUE_REGEX = build_regex(venues, ignore_case=False)


# Use build_regex for consistency
AOCI_STRICT_TERMS = [
    r"accumulated\s+other\s+comprehensive", # Strict "Accumulated"
    r"AOCI\b",
    r"reclassifi.{0,20}(?:AOCI|O\.?C\.?I|comprehensive)", # Reclassification implies moving OUT (History)
]

AOCI_NOISE_REGEX = build_regex(AOCI_STRICT_TERMS)

CATEGORY_MAP = {
    "ir": (IR_REGEX, IR_SOFT_REGEX, IR_STRICT_CONTEXT_REGEX, IR_CONTEXT_REGEX),
    "fx": (FX_REGEX, FX_SOFT_REGEX, FX_STRICT_CONTEXT_REGEX, FX_CONTEXT_REGEX),
    "cp": (CP_REGEX, CP_SOFT_REGEX, CP_STRICT_CONTEXT_REGEX, CP_CONTEXT_REGEX),
    "eq": (EQ_REGEX, EQ_SOFT_REGEX, EQ_STRICT_CONTEXT_REGEX, EQ_CONTEXT_REGEX),
    "cr": (CR_REGEX, CR_SOFT_REGEX, CR_CONTEXT_REGEX, CR_CONTEXT_REGEX),
}
