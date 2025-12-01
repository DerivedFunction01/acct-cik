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
    "hedging?"
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
    r"hedg(?:e|es|ed|ing)",
    r"manag(?:e|es|ed|ing)",
    r"mitigat(?:e|es|ed|ing)",
    r"offset(?:s|ting)?",
    r"convert(?:s|ed|ing)?",
    r"continue\s+to",
]  # NEW: For embedded derivatives/warrants, but separate against "FASB issued"
VERB_USE_REGEX = re.compile(r"\b" + build_alternation(ACTION_VERBS) +r"\b", re.IGNORECASE)
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
MAX_SENTENCE_LENGTH = 800 # A very long sentence is probably a table that became a sentence

# 1. Complex Debt Term (Requires Lookbehind)
# Helper for the base terms to avoid repetition
_DEBT_TERMS = r"(?:debts?|loans?|borrow(?:ing|ed)?|bonds?|senior notes?|notes?|debentures?)"

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
        r"foreign\s+(?:debts?|loans?|borrowings?|bonds?|notes?)",
        r"foreign\s+currency\s+(?:debts?|loans?|borrowings?|bonds?|notes?)",
        # 1. Catch "Euro-denominated debt"
        r"(?:[a-z]+[- ])?denominated\s+(?:debts?|loans?|borrowings?|bonds?|notes?)",
        # 2. Catch "Debt denominated in..." (CRITICAL for preventing IR false positives)
        r"(?:debts?|loans?|borrowings?|bonds?|notes?)\s+denominated\s+(?:in|by)",
    ]

    return currency_specific_terms + generic_fx_terms

CURRENCY_SYMBOL_PATTERN = build_currency_symbol_pattern()
# Generic hedging context (required for generic matches)
HEDGING_CONTEXT_TERMS = [
    r"hedge(?:s|d|ing)?",
    r"mitigat(?:e|es|ed|ing)",
    r"protect(?:s|ed|ing)?",
    r"manage(?:s|d|ing)?",
    r"exposures?",
    r"risk\s+management",
    rf"economic\s+{_RISK_ALTERNATION}",
    # --- ADD THESE BACK (Safe for Phase 1 Contextual Capture) ---
    rf"(?:market|rate|currency|credit|counterparty|equity)[ -]{_RISK_ALTERNATION}",
    r"fluctuations?",  # e.g., "protect against fluctuations"
    r"volatility",  # e.g., "manage volatility"
    # ------------------------------------------------------------
    r"fair\s+value\s+hedges?",
    r"cash\s+flow\s+hedges?",
    r"designated\s+as\s+(?:a\s+)?hedge",
    r"hedge\s+effectiveness",
    r"hedge\s+accounting",
    r"(?:instruments?|contracts?) are designated",
    r"ineffective portion",
    r"hedging relationship",
    r"hedge accounting",
    r"change in fair value of derivatives?",
    r"derivative expense",
    r"designated as (?:a )?hedges?",
    r"(?:gain|loss) on derivatives?",
    r"derivative\s+asset|derivative\s+liabilit(?:y|ies)",
]

CP_CONTEXT_TERMS = (
    [
        # Physical quantity units
        "barrels",
        "bbl",
        "bbl/d",
        "btu",
        "gj",
        "mmbtu",
        "mmbtu/h",
        "mwh",
        "bushels",
        "cwt",
        "hundredweights",
        "pecks",
        "ounces",
        "pounds",
        "tons",
        "tonne",
        "long tons",
        "short tons",
        "joules",
        "gigajoules",
        "mcf",
        "mmcf",
        "bcf",  # thousand/million/billion cubic feet
        "therm",
        "therms",
        "dth",
        "dekatherms",
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
        "LME", "London Metal Exchange",
        "CBOT", "Chicago Board of Trade",
        "ICE Futures", "Intercontinental Exchange",
        "COMEX", "NYMEX",
    ]
    + COMMON_COMMODITIES
)
VALUATION_MODELS = [
    # The Gold Standard for Equity Options/Warrants
    r"Black[- ]Scholes(?:[- ]Merton)?",
    r"BSM",  # Abbreviation for Black-Scholes-Merton
    # Used for path-dependent equity features (e.g., Market conditions, TSR awards)
    r"Monte[- ]Carlo(?:[- ]simulations?)?",
    # Used for American options (exercisable early) and Convertibles
    r"Binomial(?:[- ]Lattice)?\s+models?",
    r"Lattice\s+models?",
    # General descriptive
    r"option[- ]pricing\s+models?",
]
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
    r"warrants?",
    r"(?:convertible\s+(?:debt|notes?|bonds?|securit(?:y|ies)))",
    r"initial\s+public\s+offering|IPO",
    r"primary\s+market|secondary\s+market",
    r"accelerated\s+share\s+repurchases?",  # ASR is a derivative
    # --- E. Risk Integration (Smart Expansion) ---
    rf"(?:stock|share|equity)\s+{_RISK_ALTERNATION}",
    # --- F. Fallback ---
    r"stock",  # Careful, but usually okay in context
]

EQ_CONTEXT_TERMS += VALUATION_MODELS

_CR_LINKED_DEBT = rf"credit[- ]linked\s+(?:{_DEBT_TERMS})"

CR_CONTEXT_TERMS = [
    # --- A. Explicit Instruments (Broad Match) ---
    r"credit[- ]default",          # Matches "credit default swap/option/risk"
    r"total[- ]return",            # Matches "total return swap" (predominantly credit)
    _CR_LINKED_DEBT,               # Use the variable!
    r"basket[- ]default",
    r"first[- ]to[- ]default",
    rf"credit[- ]{_RISK_ALTERNATION}"
    
    # --- B. Indices (Highly Specific) ---
    r"CDX",
    r"iTraxx",
    r"Markit\s+CDX",
    r"credit\s+indices",
    r"credit\s+index",
    
    # --- C. Mechanics & Roles (The "Smoking Gun" terms) ---
    # These imply a derivative contract structure, not just a loan.
    r"reference\s+(?:entit(?:y|ies)|obligations?|assets?)",
    r"protection\s+(?:buyer|seller|sold|bought)",
    r"credit\s+protection\s+(?:sold|bought|held)",
    r"credit\s+events?",          # Specific ISDA term (bankruptcy, restructuring)
    r"recovery\s+rates?",
    r"credit\s+spreads?",         # "Spreads" usually implies trading/hedging context
    r"spread\s+duration",
    r"par\s+value",               # Common in CDS context
    
    # --- D. General (Use with caution, but usually safe in this regex) ---
    r"credit\s+derivatives?",
    r"credit\s+linked",           # Catch-all for "Credit linked deposits", etc.
]

# Compile the Regex
CR_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(CR_CONTEXT_TERMS) + r"\b", re.IGNORECASE
)

IR_CONTEXT_REGEX = re.compile(
    r"\b" + IR_CONTEXT + r"\b", re.IGNORECASE
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
    "stock",
    "looking", # Just added it here against forward-looking
]
PHYSICAL_DELIVERY_PATTERN = build_alternation(
    PHYSICAL_COMMERCIAL_TERMS, sort_longest_first=True
)

PHYSICAL_INVENTORY_TERMS = [ # "capacity forward contract?"
    
]

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
    'exotic options?',
]
UNAMBIGUOUS_BASE_TYPES = [
    "swaps?",
    rf"forwards?{FORWARD_NOT_PHYSICAL_AHEAD}",
    "caps?",
    "floors?",
    "collars?",
    "derivatives?",
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
    "puts?",
    "calls?",
    "straddles?"
    "strangles?"
]

ALL_BASE_TYPES = UNAMBIGUOUS_BASE_TYPES + AMBIGUOUS_BASE_TYPES
HIGH_PRECISION_SUFFIXES = re.compile(r"\b" + build_alternation(UNAMBIGUOUS_BASE_TYPES) + r"\b", re.IGNORECASE)
ALL_SUFFIXES = [
    "agreements?",
    "contracts?",
    "commitments?",
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
    cln_pattern = rf"credit[- ]linked\s+(?:{_DEBT_TERMS})"
    specific_phrases = [ # None for this one
        cln_pattern,
        "credit swaps?"
    ]

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
        r"(?<!currency[- ])interest",
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
    soft_pattern = build_smart_regex(
        core_terms,
        expand_instruments(unsafe=True, additional_bases=["protection"]), # IR is highly unambiguous
        specific_phrases,
    )
    regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)
    return regex, regex # return the same thing as a tuple for consistency


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
        rf"(?:{word1})[- ](?:{word1})[- ](?:{compound})[- ](?:{word2_alt})[- ]{word3}", # forward foreign cross currency exchange rate
        rf"(?:{word1})[- ](?:{word1})[- ](?:{word2_alt})[- ]{word3}",  # forward foreign exchange rate
        # Shorter, common combinations
        rf"(?:{word1})[- ](?:{word2_alt})[- ]{word3}", # forward exchange rate
        rf"(?:{compound})[- ](?:{word2_alt})[- ]{word3}",  # cross currency exchange rate
        rf"(?:{word1})[- ](?:{word1})[- ](?:{word2_alt})",  # forward foreign exchange
        rf"(?:{word1})[- ](?:{word2_alt})",
        rf"(?:{compound})[- ](?:{word2_alt})",
        # Two-word descriptive terms
        rf"(?:{word1})[- ](?:{word2_alt})",
        rf"(?:{compound})",
        # Single-word descriptive terms (low priority, included for completeness)
        compound,
        r"FX",
        r"forex",
    ]

    # CRITICAL: We let build_alternation sort this entire list by length/word count
    # to enforce Max Munch, ensuring "forward foreign currency" matches before "forward".
    return build_alternation(patterns, sort_longest_first=True)


def _replace_dynamic_placeholder(phrases: List[str], replacement_fragment: str) -> List[str]:
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
    ]
    soft_core_alternation = build_alternation(soft_core_terms, sort_longest_first=True)

    forward_types = [
        "non[- ]deliverable",
        "deliverable",
        "deal[- ]contingent",
    ]
    forward_types_alternation = build_alternation(forward_types, sort_longest_first=True)

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
    strict_dynamic_fragment = expand_instruments(unsafe=False, exclude_standalone_suffixes=True, additional_standalone_suffixes=["contracts?", "options?"])

    # 1. Substitute the dynamic fragment into the templates
    strict_dynamic_phrases = _replace_dynamic_placeholder(dynamic_templates, strict_dynamic_fragment)

    # 2. Combine and sort all specific phrases
    strict_specific_phrases = sorted(
        strict_dynamic_phrases + fixed_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:"))
    )

    # 3. Final pattern build
    strict_instrument_fragment = expand_instruments(unsafe=False) # Safe standalone bases allowed here
    strict_pattern = build_smart_regex(
        strict_core_terms,                   # Precise prefixes
        strict_instrument_fragment,          # Safe bases only
        strict_specific_phrases,             # Final list of specific phrases
    )
    strict_fx_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # --- C. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for dynamic replacement: includes all instrument bases (unsafe=True, exclude standalones)
    soft_dynamic_fragment = expand_instruments(unsafe=True, exclude_standalone_suffixes=True)

    # 1. Substitute the dynamic fragment into the templates
    soft_dynamic_phrases = _replace_dynamic_placeholder(dynamic_templates, soft_dynamic_fragment)

    # 2. Combine and sort all specific phrases
    soft_specific_phrases = sorted(
        soft_dynamic_phrases + fixed_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:"))
    )

    # 3. Final pattern build
    soft_instrument_fragment = expand_instruments(unsafe=True) # Unsafe standalone bases allowed here
    soft_pattern = build_smart_regex(
        [soft_core_alternation],             # Broad prefixes
        soft_instrument_fragment,            # Unsafe bases included
        soft_specific_phrases,               # Final list of specific phrases
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
    strict_core_alternation = build_alternation(strict_core_patterns, sort_longest_first=True)

    # 3. Unified Specific Phrases
    # These contain the max-munch phrases and apply to both strict and soft.
    specific_phrases = [
        r"weather derivatives?", # raw string for regex
        r"power purchase agreements?",               # raw string for regex
        # LONGEST FIRST: spreads with suffix (uses standalone_alternation for bases/suffixes)
        rf"(?:{spread_types_alternation})\s+spreads?\s+(?:{standalone_alternation})",
        # SHORTER: spreads alone
        rf"(?:{spread_types_alternation})\s+spreads?",
        r"virtual power purchase agreements?",       # raw string for regex
        r"virtual PPA",
    ]

    # Pre-sort longest-first for Max Munch precedence
    sorted_specific_phrases = sorted(
        specific_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:" ))
    )

    # -------------------------------------------------------------------------
    # --- A. STRICT Pattern Construction (High Precision) ---
    # -------------------------------------------------------------------------

    # Fragment used for attachment to core terms: Requires an instrument base, excludes standalones.
    # This maintains the high precision of the original function's core logic.
    strict_attachment_fragment = expand_instruments(unsafe=True, exclude_standalone_suffixes=True)

    strict_pattern = build_smart_regex(
        [strict_core_alternation],               # Highly precise core prefixes
        strict_attachment_fragment,              # Must attach a derivative base (e.g., 'swap' or 'future')
        sorted_specific_phrases,                 # All high-priority explicit phrases
    )
    strict_cp_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # --- B. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    # Fragment used for general pattern combination: Includes all derivative terminology.
    soft_instrument_fragment = expand_instruments(unsafe=True)

    # Soft pattern combines simple prefixes ('commodity', 'CP') with the full range of instrument terms.
    soft_pattern = build_smart_regex(
        [strict_core_alternation],                 # Simple prefixes
        soft_instrument_fragment,                # Full range of instruments (e.g., 'options', 'futures')
        sorted_specific_phrases,                 # All high-priority explicit phrases
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
        r"share\s+price",
        r"stock\s+price",
        r"market\s+index",
        r"S&P\s+500",
        r"Nasdaq",
        r"Dow\s+Jones",
    ]
    strict_core_alternation = build_alternation(strict_core_terms, True)


    # 2. Build Specific Phrases (Max Munch) - UNIFIED LIST
    # Convertible phrases (Structural Embedded Derivatives)
    convertible_phrases = [
        rf"embedded\s+conversion\s+(?:{option}|features?|{derivative})",
        rf"conversion\s+option\s+{liability}",
        rf"bifurcated\s+conversion\s+{option}",
        rf"{derivative}\s+{liability}\s+\S*convertible\s+notes?",
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
        sorted_specific_phrases,  # All high-priority explicit phrases
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
    safe_bases = ["swaps", "derivatives"]

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
    specific_phrases = [
        "cash flow hedges?",
        "fair value hedges?",
        "embedded derivatives?",
        "over[- ]the[- ]counter derivatives?",
        "derivative financial instruments?",
        "financial derivatives?",
        "derivative assets?",
        "derivative liabilit(?:y|ies)",
        "forward contracts",
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
    # 1. Phrases explicitly related to derivative accounting treatment (PNL/Classification)
    accounting_phrases = [
        r"(?:instruments?|contracts?) are designated",
        r"ineffective portion",
        r"hedging relationship",
        r"hedge accounting",
        r"change in fair value of derivatives?",
        r"derivative expense",
        r"designated as (?:a )?hedges?",
        r"(?:gain|loss) on derivatives?",
        r"derivative\s+asset|derivative\s+liabilit(?:y|ies)",
    ]

    all_patterns = accounting_phrases

    # Combine and prioritize based on length/specificity
    pattern = build_alternation(all_patterns)

    return re.compile(r"\b" + pattern + r"\b", re.IGNORECASE)


def build_loose_gen_regex() -> re.Pattern:
    pattern = build_alternation(ALL_BASE_TYPES + ALL_SUFFIXES)
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
            CR_REGEX.pattern
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
    r"|".join([IR_SOFT_REGEX.pattern,
            FX_SOFT_REGEX.pattern,
            CP_SOFT_REGEX.pattern,
            EQ_SOFT_REGEX.pattern,
            CR_SOFT_REGEX.pattern,
            IR_REGEX.pattern,
            FX_REGEX.pattern,
            CP_REGEX.pattern,
            EQ_REGEX.pattern,
            SOFT_GEN_REGEX.pattern,
            GEN_REGEX.pattern,
            STRICT_NOTIONAL_REGEX.pattern,
            CR_REGEX.pattern,
            ]), re.IGNORECASE
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
    "phantom stock",
    "employee stock",
    # 2. Plan/HR Terminology
    "compensation",
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
]

METHODOLOGY_KEYWORDS = [
    r"is\s+defined\s+as",
    r"value[- ]at[- ]risk\s+(?:model|methodology|measurement|analysis)",
    r"sensitivity\s+analysis\s+(?:model|methodology)",
    r"confidence\s+(?:level|interval)",
    r"statistical\s+(?:measure|model)",
    r"hypothetical\s+(?:change|loss|shift|scenario)",
    r"parallel\s+shift",
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
    r"court",
    r"petition",
]

# Section 3: Accounting Standards
# === FASB ISSUANCE & ADOPTION ONLY ===

# --- ISSUING BODIES ---
ISSUER_TERMS = [
    r"FASB",
    r"Financial Accounting Standards Board",
    r"F\.A\.S\.B\.",
    r"IASB",
    r"International Accounting Standards Board",
    r"I\.A\.S\.B\.",
    r"GASB",
    r"Governmental Accounting Standards Board",
    r"G\.A\.S\.B\.",
    r"AICPA",
    r"American Institute of Certified Public Accountants",
    r"A\.I\.C\.P\.A\.",
    r"PCAOB",
    r"Public Company Accounting Oversight Board",
    r"P\.C\.A\.O\.B\.",
    r"FASAB",
    r"Federal Accounting Standards Advisory Board",
    r"F\.A\.S\.A\.B\.",
    r"SEC",
    r"Securities and Exchange Commission",
    r"Accounting Standards Board",
    r"EITF",
    r"E\.I\.T\.F\.",
    r"Emerging Issues Task Force",
    r"Task Force",
]

# --- STANDARD TYPES & ACRONYMS ---
STANDARDS_TERMS = [
    r"SFAS",
    r"FAS",
    r"ASU",
    r"ASC",
    r"IFRS",
    r"IAS",
    r"IFRIC",
    r"SIC",
    r"EITF",
    r"SOP",
    r"FSP",
    r"FIN",
    r"Technical\s+Bulletin",
    r"TB",
    r"SFAC",
    r"Concept\s+Statement",
    r"APB\s+Opinion",
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
    r"expand(?s?|ed|ing)?",  # expand, expands (added per your previous request)
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
]

# --- ADOPTION VERBS: GENERAL ACTION ---
ADOPTION_VERBS_GENERAL = [
    r"adopt(?:ing|ed)?",
    r"early\s+adopt(?:ed|ing|ion)?",
    r"application\s+of",
    r"implement(?:ing|ed|ation)",
    r"transition(?:ing|ed)?",
    r"compliance\s+with",
    r"conform(?:ing|ed|ity)\s+to",
    r"following",
    r"(?:early\s+)?application",
    r"effective\s+(?:upon|date)",
    r"retroactive\s+(?:application|adoption)",
    r"prospective\s+(?:application|adoption)",
]

# --- EFFECTIVE DATE PHRASES ---
EFFECTIVE_DATE_PHRASES = [
    r"effective\s+for\s+(?:fiscal\s+years|annual\s+periods)",
    r"effective\s+(?:in|for|after)\s+(?:fiscal\s+)?(?:year\s+)?\d{4}",
    r"becomes\s+effective",
    r"will\s+be\s+effective",
    rf"(?:ending|beginning)\s+after\s+{MONTHS_FRAGMENT}",
]

# --- IMPACT ASSESSMENT PHRASES ---
IMPACT_PHRASES = [
    r"evaluat(?:ing|ed|e|es)\s+(?:the\s+)?(?:impact|effect)\s+of",
    r"assess(?:ing|ed|es)\s+the\s+(?:impact|effect)\s+of",
    r"currently\s+(?:evaluating|assessing)",
    r"continu(?:ing|es)\s+to\s+evaluate",
    r"impact\s+on\s+(?:our|the)\s+consolidated\s+financial\s+statements",
]

# --- IMPACT RESULT PHRASES ---
IMPACT_RESULT_PHRASES = [
    r"(?:not\s+)?expected\s+to\s+have\s+a\s+material\s+(?:impact|effect)",
    r"no\s+material\s+impact",
    r"immaterial\s+impact",
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
    r"Abstract",
    r"Opinions?",
    r"Codifications?",
    r"Pronouncements?",
    r"Interpretations?",
    r"Bulletins?",
    r"Frameworks?",
    r"Concept\s+Statements?",
    r"Clarifications?",
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
ISSUER_FRAGMENT = build_alternation(ISSUER_TERMS)
STANDARDS_FRAGMENT = build_alternation(STANDARDS_TERMS)

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
STANDARD_ID_PATTERN = rf"(?:{STANDARDS_FRAGMENT}|{GUIDANCE_OBJECT_TYPES_FRAGMENT})(?:\s+Issue)?(?:\s+No\.?)?\s+\d+(?:-\d+)*"
CAPITALIZED_TITLE_PATTERN = (
    r"(?:,?\s*[\"“']?(?:[A-Z][\w\-']+\s+){2,}[A-Z][\w\-']+[\"”']?)?"
)
# --- FINAL KEYWORD LIST ---
ACCOUNTING_STANDARDS_KEYWORDS = [
    # Issuer + Issuance
    rf"{ISSUER_FRAGMENT}\s+(?:in\s+{STANDARD_ID_PATTERN}\s+)?{ISSUANCE_VERBS_FRAGMENT}",
    # Standard ID + Issuance
    rf"{STANDARD_ID_PATTERN}\s+(?:was|is)\s+{ISSUANCE_VERBS_FRAGMENT}",
    # Issuance Verb + Standard ID
    rf"{ISSUANCE_VERBS_FRAGMENT}(?:\s+\w+){{1,10}}\s+{STANDARD_ID_PATTERN}",
    
    rf"{STANDARD_ID_PATTERN}{CAPITALIZED_TITLE_PATTERN}",
    # Dated Issuance
    rf"in\s+{MONTHS_FRAGMENT}\s+\d{{4}}.*{ISSUANCE_VERBS_FRAGMENT}",
    # Standard Descriptions
    rf"{STANDARD_ID_PATTERN}\s+{DESCRIPTION_VERBS_FRAGMENT}",
    # Pure References/Citations
    rf"pursuant\s+to\s+{STANDARD_ID_PATTERN}",
    rf"defined\s+in\s+{STANDARD_ID_PATTERN}",
    rf"accordance\s+with\s+{STANDARD_ID_PATTERN}",
    # Future Adoption Intent
    rf"{ADOPTION_VERBS_FUTURE_FRAGMENT}",
    # General Adoption Actions
    rf"{ADOPTION_VERBS_GENERAL_FRAGMENT}\s+{STANDARD_ID_PATTERN}",
    rf"{ADOPTION_VERBS_GENERAL_FRAGMENT}\s+(?:the\s+)?(?:new\s+)?{GUIDANCE_OBJECT_TYPES_FRAGMENT}",
    # Effective Dates & Application
    rf"{STANDARD_ID_PATTERN}\s+should\s+be\s+applied",
    rf"{STANDARD_ID_PATTERN}\s+(?:is|was|becomes)\s+effective",
    EFFECTIVE_DATE_PHRASES_FRAGMENT,
    ADOPTION_PERMISSION_PHRASES_FRAGMENT,
    # Standalone Phrases
    STANDALONE_PHRASES_FRAGMENT,
    # Impact Assessment
    IMPACT_PHRASES_FRAGMENT,
    IMPACT_RESULT_PHRASES_FRAGMENT,
    # Anchor-based patterns (start of line)
    rf"^{STANDARD_ID_PATTERN}\s+(?:{ISSUANCE_VERBS_FRAGMENT}|{DESCRIPTION_VERBS_FRAGMENT})",
    rf"^{ISSUER_FRAGMENT}\s+(?:{ISSUANCE_VERBS_FRAGMENT}|{DESCRIPTION_VERBS_FRAGMENT})",
    rf"^In\s+{MONTHS_FRAGMENT}.*{ISSUER_FRAGMENT}",
    
    rf"improve\s+disclosures?\s+(?:about|regarding|on)[^.?!]*",
    rf"requiring\s+(?:more|additional)\s+information[^.?!]*",
    rf"disclosures?\s+(?:required|mandated)\s+by\s+{STANDARD_ID_PATTERN}[^.?!]*",
    rf"disclosures?\s+(?:about|regarding)\s+(?:the\s+)?(?:adoption|application|impact)\s+of[^.?!]*",
    rf"(?:intended|designed)\s+to\s+(?:improve|expand|enhance)\s+disclosures?[^.?!]*",
    rf"requiring\s+(?:more|additional|expanded)\s+information\s+about[^.?!]*",
    r"accounting\s+standards?\s+update",
    rf"recently\s+(?:issued|updated|released|published|announced)\s+(?:accounting\s+)?{GUIDANCE_OBJECT_TYPES_FRAGMENT}",
]


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
    r"safe\s+harbor\s+statement",
    
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


# Section 4: Regulatory & Compliance (New)
REGULATORY_KEYWORDS = [
    # 1. General Regulatory Terms
    r"regulations?",
    r"regulatory\s+(?:requirements?|compliance|authorit(?:y|ies)|bod(?:y|ies)|agenc(?:y|ies)|frameworks?|matters?|reforms?)",
    r"compliance\s+with",
    r"subject\s+to\s+(?:regulation|oversight|regulatory)",
    r"governmental\s+regulations?",
    # 2. Specific Laws & Acts (The big noise makers)
    r"Dodd[- ]Frank",
    r"Volcker\s+Rule",
    r"Basel\s+(?:I|II|III|IV)",
    r"EMIR",  # European Market Infrastructure Regulation
    r"MiFID",  # Markets in Financial Instruments Directive
    r"Commodity\s+Exchange\s+Act",
    r"Securities\s+Exchange\s+Act",
    r"SEC",
    r"Sarbanes[- ]Oxley",
    r"JOBS\s+Act",
    r"CARES\s+Act",
    r"Regulation\s+AB",
    # 3. Capital & Liquidity (Banking Regs)
    r"capital\s+adequacy",
    r"liquidity\s+coverage\s+ratio",
    r"regulatory\s+capital",
]

HYPOTHETICAL_KEYWORDS = [
    r"measure(?:s|d|ment)\s+of\s+market\s+risk",
    r"confidence\s+(?:level|interval)",
    r"statistical\s+(?:measure|model)",
    r"hypothetical\s+(?:change|loss|shift|scenario|stress)", # Added 'stress'
    r"parallel\s+shift",
    r"simulation\s+model\s+that\s+estimates",
    r"sensitivity\s+analysis",
]
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

def build_exclude_regex(keywords: list) -> re.Pattern:
    """Build regex for excluding noise keywords."""
    escaped_keywords = [re.escape(kw) for kw in keywords]
    pattern = r"|".join(escaped_keywords)
    return re.compile(pattern, re.IGNORECASE)


EXCLUDE_REGEX_EQUITY_COMP = build_exclude_regex(EQUITY_COMP_KEYWORDS)
EXCLUDE_REGEX_LEGAL_LITIGATION = build_exclude_regex(LEGAL_LITIGATION_KEYWORDS)
EXCLUDE_REGEX_ACCOUNTING_STD = build_exclude_regex(ACCOUNTING_STANDARDS_KEYWORDS)
EXCLUDE_REGULATION_REGEX = build_exclude_regex(REGULATORY_KEYWORDS)
EXCLUDE_PLAN_ASSETS_REGEX = build_exclude_regex(PLAN_ASSETS_KEYWORDS)
EXCLUDE_HYPOTHETICAL_REGEX = build_exclude_regex(HYPOTHETICAL_KEYWORDS)
EXCLUDE_COMPETITOR_REGEX = build_exclude_regex(COMPETITOR_KEYWORDS)
EXCLUDE_REGEX_FORWARD_LOOKING = build_exclude_regex(FORWARD_LOOKING_KEYWORDS)

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
    CLAUSE_4 = rf"\b(?:{SUBJ})\s+(?:{NEG})\s+(?:speculate|trade)\b"

    # Clause 5: "None of [anything]..."
    CLAUSE_5 = (
        rf"\bnone\s+of\s+(?:the\s+|our\s+)?\S+(?:\s+\S+){{0,7}}\s+"
        rf"(?:are|is|were|was)\s+(?:{ACT})\s+"
        rf"(?:for\s+)?(?:{TRAD})(?:\s+(?:{PURP}))?\b"
    )

    # Clause 6: "No trading or speculative purposes"
    CLAUSE_6 = (
        rf"\b(?:no|for)\s+(?:{TRAD})(?:\s+or\s+(?:{TRAD}))?(?:\s+(?:{PURP}))?\b"
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
    COMMON_VERBS = r"(?:means?|represents?|refers?\s+to|considered\s+as)"
    
    # SPECIFIC: Accounting nouns allowed for "represents"
    ACCT_NOUNS = r"(?:notional\s+value|contractual\s+interest|fair\s+value|market\s+value)"

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
        rf"{ACCT_NOUNS}\s+(?:represents?|means?){SENTENCE_TAIL}",
        
        # --- 5. Corporate Definitions ---
        # Matches: "The Company defines...", "Management considers..."
        rf"(?:{subject})\s+(?:consider|define)s?\s+(?:a\s+)?{instr}.*as{SENTENCE_TAIL}",
        
        # --- 6. Inverted Definitions ---
        # Matches: "...is the definition of..."
        rf".*?\s+is\s+the\s+definition\s+of{SENTENCE_TAIL}",
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
        r"financial\s+instruments?", # optional, but common in this context
    ]

    verb_pat = build_alternation(verbs)
    target_pat = build_alternation(targets)

    # Structure: (Auxiliary Negation) + (Classification Verb) + (Optional 'as a') + (Target)
    return re.compile(
        rf"\b(?:are|is|were|was)\s+not\s+"
        rf"{verb_pat}\s+"
        rf"(?:as\s+)?(?:a\s+|an\s+)?"
        rf"{target_pat}\b",
        re.IGNORECASE
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
EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX = build_exclude_regex(
    NON_DERIVATIVE_COMMERCIAL_KEYWORDS
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
    r"historically",
    r"previously",
    r"occasionally",
    r"in\s+the\s+future",
    r"upon\s+occurrence",
    r"believes?",
    r"(?:may|might)\s+consider",
    r"when\s+(?:deemed\s+)?necessary",
]

# Potential / Hypothetical Modals & Phrases
POTENTIAL_INDICATORS = [
    r"may",
    r"might",
    r"could",
    r"seek\s+to",
    r"intend\s+to",
    r"plans?\s+to",
    r"if",
    # FIX: Negative lookahead allows "expect to continue" (Active) while flagging "expect to use" (Potential)
    r"expect\s+to\s+(?!continue)",
]

# Negative Intent Components
NEGATIVE_AUXILIARY = [r"do", r"does", r"did", r"will", r"would", r"can", r"could", r"shall", r"should"]
NEGATIVE_INTENT_VERBS = [r"seek", r"intend", r"plan", r"expect", r"continue"]

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
# In termination_filter.py (or wherever you define this list)

# 1. DEFINE SAFEGUARDS (Words that make "Settlement/Closing" active)
# If these appear before "settled", it's likely a description of mechanics, not termination.
SETTLEMENT_MODIFIERS = [
    "cash", "net", "daily", "monthly", "physically", "final", "mandatory", "annually", "weekly"
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
    r"clos(?:e(?:d|s)?|ing)(?!\s+(?:price|rate|date|balance|value))",
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
    r"do[nN]['’]?[tT]",  # don't
    r"does[nN]['’]?[tT]",  # doesn't
    r"did[nN]['’]?[tT]",  # didn't
    r"wo[nN]['’]?[tT]",  # won't (handles 'will' negation)
    r"would[nN]['’]?[tT]",  # wouldn't
    r"ca[nN]['’]?[tT]",  # can't
    r"cannot",  # cannot (special case, one word)
    r"could[nN]['’]?[tT]",  # couldn't
    r"should[nN]['’]?[tT]",  # shouldn't
    r"sha[nN]['’]?[tT]",  # shan't
]
def build_negation_prefix_pattern() -> str:
    """
    Returns a regex string matching:
    1. "did not", "could not" (Aux + space + not)
    2. "didn't", "couldn't"   (Contractions)
    """
    # 1. Full forms: \b(do|will|could)\s+not\b
    aux_full = build_alternation(NEGATIVE_AUXILIARY)
    pattern_full = rf"\b{aux_full}\s+not\b"

    # 2. Contractions: \b(don't|won't|couldn't)\b
    # Note: build_alternation automatically handles sorting by length
    aux_contract = build_alternation(NEGATIVE_CONTRACTIONS)
    pattern_contract = rf"\b{aux_contract}\b"

    # Combine: (Full | Contraction)
    return rf"(?:{pattern_full}|{pattern_contract})"


def build_negative_intent_regex() -> re.Pattern:
    """
    Matches: "does not intend", "doesn't intend", "won't seek", "couldn't plan"
    """
    _neg_verb = build_alternation(NEGATIVE_INTENT_VERBS)

    # Get the unified negation start (handles "could not" AND "couldn't")
    _neg_prefix = build_negation_prefix_pattern()

    _neg_pattern_standard = rf"{_neg_prefix}\s+(?:{ACTIVE_PATTERN}\s+)?{_neg_verb}\s+to"

    # "has no plans to" remains separate as it uses a noun structure
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
    Matches: "did not hold", "didn't enter", "couldn't engage"
    """
    # Use the same unified prefix
    _neg_prefix = build_negation_prefix_pattern()
    
    _instrument_object = rf"(?:{STRICT_REGEX.pattern}|{LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"
    _fillers = (
        r"(?:such\s+|any\s+|" rf"{MATERIAL_PATTERN}\s+|" rf"{ACTIVE_STATE_PATTERN}\s+)*"
    )

    return re.compile(
        # Replace the hardcoded (did|does...) with the unified prefix
        rf"{_neg_prefix}\s+(?:{ACTIVE_PATTERN}\s+)?(?:{INTENT_VERB_PATTERN})\s+"
        rf"{_fillers}"
        rf"{_instrument_object}\b",
        re.IGNORECASE,
    )


def build_termination_regex() -> re.Pattern:
    """Matches: "expired", "matured", "unwound" """
    return re.compile(rf"\b{build_alternation(TERMINATION_VERBS)}\b", re.IGNORECASE)
# Ensure you have HEDGING_CONTEXT_REGEX available in the function's scope
# (It is likely already imported or defined in derivative_regex.py)

def check_for_instrument(sentence: str, strict: bool = False) -> bool:
    """
    Determines if the instrument name is still present in the paragraph/sentence.
    """
    # Check for length 
    if len(sentence) < MIN_SENTENCE_LENGTH: return False
    # 1. SPECIFIC MATCHES (The Only Safe Harbor for Orphans)
    # If it says "Interest Rate Swap", it survives ANY filter.
    if CATEGORY_REGEX.search(sentence):
        # Remove the phrase itself; there should still be something left
        remaining = CATEGORY_REGEX.sub("", sentence).strip()
        # Remove the period at the end
        if remaining.endswith("."):
            remaining = remaining[:-1]
        return True if len(remaining) > 5 else False

    # 1.5 If specfics failed, soft regex only if there is hedging context
    if SOFT_CATEGORY_REGEX.search(sentence):
        if HEDGING_CONTEXT_REGEX.search(sentence):
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
            if HEDGING_CONTEXT_REGEX.search(sentence):
                return True

    return False

def validate_instrument_retention(
    paragraphs: List[str], 
    categories: List[str], 
    url: str, 
    strict: bool = False, 
    year: Optional[int] = None
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
            sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()]
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


def build_reference_patterns() -> re.Pattern:
    """
    Builds a regex that catches 'See Note X' references and consumes
    the rest of the sentence to clean up tail noise.
    """

    # The "Tail" - Consumes everything until a sentence boundary or end of string
    # We use non-greedy lookahead or simply a negated character class
    # [^.?!]* matches anything that isn't a period, question mark, or exclamation.
    SENTENCE_TAIL = r"[^.?!:]*"

    # Base patterns (from your list)
    patterns = [
        # --- NOTE REFERENCES ---
        # 1. See Note X
        r"[Ss]ee\s+(?:Note|NOTE)\s+(?:No\.\s+)?\d+[A-Z]?(?:\s*\(s\))?",
        # 2. Refer to Note X
        r"(?:[Rr]efer(?:ence)?\s+(?:to|is\s+made\s+to|is\s+hereby\s+made\s+to))\s+(?:Note|NOTE)\s+(?:No\.\s+)?\d+[A-Z]?",
        # 3. In Note X (Start of fragment or sentence)
        r"\b[Ii]n\s+(?:Note|NOTE)\s+(?:No\.\s+)?\d+[A-Z]?",
        # 4. Note X provides/details...
        r"\b(?:Note|NOTE)\s+(?:No\.\s+)?\d+[A-Z]?\s+(?:provides?|details?|discloses?|discusses?)",
        # --- TABLE / SCHEDULE REFERENCES ---
        # 5. The table/schedule below/above...
        r"[Tt]he\s+(?:following\s+)?(?:table|schedule|exhibit|note)\s+(?:below|above|following|accompanying)?\s*(?:[Rr]efers\s+to|[Pp]rovides\s+details\s+on|[Pp]resents|[Ss]hows|[Ss]ummarizes|[Dd]etails|[Ii]s\s+presented)",
        # 6. As shown in the table...
        r"(?:[Aa]s\s+(?:shown|provided|detailed|presented|summarized|disclosed|set\s+forth)?\s+in\s+the\s+(?:table|schedule|exhibit|note))",
        # 7. In the table below...
        r"[Ii]n\s+(?:the\s+)?(?:table|schedule|exhibit|note)\s+(?:below|above|following)",
        # 8. Punctuation + Table No. X (Very specific tail noise)
        r"(?:[.,;:\-\s]|\s+and\s+)\s*(?:table|schedule|exhibit|note)\s+No\.\s+\d+",
    ]

    # Combine: (Pattern) + (Tail)
    # We allow the regex to consume the rest of the sentence.
    combined = [f"(?:{p}){SENTENCE_TAIL}" for p in patterns]

    return re.compile(r"|".join(combined), re.IGNORECASE | re.DOTALL)


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
        "discussion",
        "analysis",
        "disclosure",
        "description",
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

    # Structure: "For" + [Adjective] + [Noun] + (Optional [Connector])
    pattern = (
        rf"([Ff]or)?\s+"
        rf"(?:a\s+|an\s+)?(?:{adj_pat})\s+"
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
            re.MULTILINE | re.IGNORECASE
        ),
        "\n\n"
    ),
]


def build_entity_exclusion_regex() -> Tuple[re.Pattern, str]:
    """
    Matches official entity names AND their acronyms that contain trigger words
    (Futures, Swaps, Options, Derivatives, Exchange) to prevent false positive classification.
    """
    entities = [
        # --- 1. Regulators & Standard Setters ---
        r"(?:U\.?S\.?\s+)?Commodity\s+Futures\s+Trading\s+Commission",
        r"\bCFTC\b",
        r"National\s+Futures\s+Association",
        r"\bNFA\b",
        r"Securities\s+(?:and|&)\s+Exchange\s+Commission",
        r"\bSEC\b",
        r"Public\s+Company\s+Accounting\s+Oversight\s+Board",
        r"\bPCAOB\b",
        r"Federal\s+Energy\s+Regulatory\s+Commission",
        r"\bFERC\b",
        r"Prudential\s+Regulators?",  # Generic but common in bank filings
        # --- 2. Associations (Master Agreements) ---
        r"International\s+Swaps\s+(?:and|&)\s+Derivatives\s+Association",
        r"\bISDA\b",
        r"Futures\s+Industry\s+Association",
        r"\bFIA\b",
        r"Securities\s+Industry\s+(?:and|&)\s+Financial\s+Markets\s+Association",
        r"\bSIFMA\b",
        # --- 3. Exchanges (The "Option/Future/Swap" Triggers) ---
        # Chicago Group
        r"Chicago\s+Board\s+Options\s+Exchange",
        r"\bCBOE\b",
        r"Chicago\s+Mercantile\s+Exchange",
        r"\bCME\b",
        r"Chicago\s+Board\s+of\s+Trade",
        r"\bCBOT\b",
        # New York / ICE Group
        r"New\s+York\s+Stock\s+Exchange",
        r"\bNYSE\b",
        r"New\s+York\s+Mercantile\s+Exchange",
        r"\bNYMEX\b",
        r"Commodity\s+Exchange(?:,?\s+Inc\.?)?",
        r"\bCOMEX\b",
        r"Intercontinental\s+Exchange",
        r"\bICE\b",
        # International / Other
        r"London\s+Metal\s+Exchange",
        r"\bLME\b",
        r"London\s+Stock\s+Exchange",
        r"\bLSE\b",
        r"Philadelphia\s+Stock\s+Exchange",
        r"\bPHLX\b",
        r"Eurex",
        # --- 4. Clearing Houses (Critical for "Cleared Swaps" noise) ---
        r"Options\s+Clearing\s+Corporation",
        r"\bOCC\b",
        r"London\s+Clearing\s+House",
        r"\bLCH\b",
        r"CME\s+Clearing",
        r"ICE\s+Clear",
        # --- 5. Generic / Investment Vehicles ---
        r"hedge\s+funds?",
        r"mutual\s+funds?",
        r"index\s+funds?",
        r"exchange[- ]traded\s+funds?",
        r"\bETFs?\b",
        r"money\s+market\s+funds?",
        r"pension\s+funds?",  # Reinforces Plan Asset exclusion
    ] + ISSUER_TERMS

    # --- 6. Dynamic Fund Pattern (Your existing logic) ---
    # Matches: "United States Commodity Index Fund", "Oil Derivatives Trust"
    triggers = r"(?:Commodity|Oil|Gas|Energy|Derivatives?|Futures?|Options?|Swaps?)"
    suffixes = r"(?:Fund|Trust|ETF|LP|L\.P\.|Holdings?|Portfolio|Group|Capital)"
    fund_pattern = rf"(?:[A-Z][a-z]+\s+)*{triggers}(?:\s+[A-Z][a-z]+)*\s+{suffixes}"

    all_patterns = entities + [fund_pattern]

    # Use build_alternation to ensure longest matches (e.g., full name) are prioritized
    # Note: We enforce word boundaries \b for short acronyms inside the list above
    pattern = build_alternation(all_patterns)
    return re.compile(rf"\b{pattern}\b"), "_E"


# Compile and Export
ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN = build_entity_exclusion_regex()

# Unique marker to identify the "Target" sentence that anchors a context window.
# Used to enforce dependency: if the anchor is deleted, loose dependents must die.
ANCHOR_TAG = " _A^ "
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
# Only include them if attached to "price", "cost", "risk", "hedge", or "swap".
CP_STRICT_TERMS = [
    # General terms
    rf"(?:cost|price)\s+{_RISK_ALTERNATION}",
    r"raw\s+material\s+costs?",
    r"fuel\s+surcharges?",
    # Specific Commodity + Financial Modifier
    # Matches: "Corn prices", "Oil hedging",
    rf"(?:{_COMMODITY_NAMES})\s+{_RISK_ALTERNATION}",
    # Financial Modifier + Specific Commodity
    # Matches: "Price of corn", "Hedging of oil", "Cost of gold"
    rf"{_RISK_ALTERNATION}\s+of\s+(?:{_COMMODITY_NAMES})",
]

# ... (IR_STRICT_TERMS, FX_STRICT_TERMS, etc. remain the same) ...

# 4. EQUITY (Strict)
# Focus: Convertibles, Warrants, and Valuation Models
# 4. EQUITY (Strict)
# Focus: Convertibles, Warrants, Valuation Models, and Equity Risk
EQ_STRICT_TERMS = [
    # 1. Risk & Price Contexts (Expanded with _RISK_ALTERNATION)
    rf"equity\s+(?:price|{_RISK_ALTERNATION})",
    rf"stock\s+(?:price|appreciation|option|{_RISK_ALTERNATION})",
    rf"share\s+(?:price|{_RISK_ALTERNATION})",
    # 2. Convertible Instruments
    r"convertible\s+(?:debt|notes?|bonds?|debentures?)",
    # 3. Embedded Features (REMOVED: "derivative" as requested)
    # Only matches specific features now, reducing noise.
    r"embedded\s+(?:conversion|option)",
    # 4. Specific Instruments
    r"warrants?",
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
STRICT_CONTEXT_MAP = {
    "ir": re.compile(r"\b" + build_alternation(IR_STRICT_TERMS) + r"\b", re.IGNORECASE),
    "fx": re.compile(r"\b" + build_alternation(FX_STRICT_TERMS) + r"\b", re.IGNORECASE),
    "cp": re.compile(r"\b" + build_alternation(CP_STRICT_TERMS) + r"\b", re.IGNORECASE),
    "eq": re.compile(r"\b" + build_alternation(EQ_STRICT_TERMS) + r"\b", re.IGNORECASE),
    "cr": CR_CONTEXT_REGEX
}

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
    "TRADING_STATEMENTS_REGEX",
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
    "BASE_REGEX",
    "VERB_USE_REGEX",
    "NON_DERIVATIVE_REGEX",
    "ENTITY_EXCLUSION_REGEX",
    "HEADER_CLEANUP_PATTERNS",
    "STRICT_CONTEXT_MAP"
]
