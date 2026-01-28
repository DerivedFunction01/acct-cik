from dataclasses import dataclass
import re
from typing import List, Optional
from defs.regex_lib import add_restrictions, build_alternation, build_regex

_DEBT_TERMS = r"(?:debts?|loans?|borrowings?|bonds?|senior\s+notes?|notes?|debentures?)"
RISK_TERMS = [
    "risks?",
    "fluctuations?",
    "volatilit(?:y|ies)",
    "exposures?",
    "movements?",
    "variabilit(?:y|ies)",
    "changes?",
    "managements?",
    "transactions?",
    "costs?",
    "prices?",
    "rising",
    "falling",
    "increas(?:ing|es?)",
    "decreas(?:ing|es?)",
]
_RISK_ALTERNATION = build_alternation(RISK_TERMS)


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
    Currency("GBP", "British Pound", "£", "British", "United Kingdom"),
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
    Currency(
        "VND", "Vietnamese Dong", "₫", "Vietnamese", "Vietnam", symbol_first=False
    ),
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
    Currency(
        "ZAR", "South African Rand", "R", "South African", "South Africa"
    ),  # added _ to prevent R from matching
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


def build_currency_iso_pattern() -> str:
    """
    Returns a regex alternation of all ISO 4217 currency codes.
    Sorted by length descending to prevent partial matches (e.g., 'NOK' before 'OK').
    """
    codes = {c.code for c in all_currencies if c.code}
    sorted_codes = sorted(codes, key=len, reverse=True)
    escaped = [re.escape(code) for code in sorted_codes]
    return build_alternation(escaped)


def build_currency_descriptor_pattern() -> str:
    """
    FX-optimized currency fragment generator. for iso code, iso-pairs, names
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

CURRENCY_SYMBOL_PATTERN = build_currency_symbol_pattern()


def build_currency_names_regex() -> re.Pattern:
    terms = []
    for currency in all_currencies:
        terms.append(re.escape(currency.full_name))
    return build_regex(terms)


CURRENCY_NAMES_REGEX = build_currency_names_regex()

VALUATION_MODELS = [
    # The Gold Standard for Equity Options/Warrants
    r"Black[- ]Scholes(?:[- ]Merton)?",
    r"\bBSM\b",  # Abbreviation for Black-Scholes-Merton
    # Used for path-dependent equity features (e.g., Market conditions, TSR awards)
    r"Monte[- ]Carlo(?:[- ][sS]imulations?)?",
    # Used for American options (exercisable early) and Convertibles
    r"[Bb]inomial(?:[- ][Ll]attice)?\s+[mM]odels?",
    r"[Ll]attice\s+[mM]odels?",
    # General descriptive
    r"[Oo]ption[- ][Pp]ricing\s+[Mm]odels?",
]
VALUATION_MODELS_REGEX = build_regex(VALUATION_MODELS, ignore_case=False)

MITIGATION_STRICT_VERBS = [
    r"mitigat(?:e|es|ed|ing)",
    r"hedg(?:e|es|ed|ing)",
    r"manag(?:e|es|ed|ing)",
]

MITIGATION_VERBS = MITIGATION_STRICT_VERBS + [
    r"offset(?:s|ting)?",
    r"reduc(?:e|es|ed|ing)",
    r"limit(?:s|ed|ing)?",
    r"control(?:s|led|ling)?",
    r"minimiz(?:e|es|ed|ing)",
    r"neutraliz(?:e|es|ed|ing)",
    r"protect(?:s|ed|ing)?",
    r"stabiliz(?:e|es|ed|ing)",
    r"counter(?:act)?(?:s|ed|ing)?",
    r"guard(?:s|ed|ing)?\s+(?:against)?",
    r"shield(?:s|ed|ing)?",
    r"safeguard(?:s|ed|ing)?",
    r"defend(?:s|ed|ing)?",
    r"prevent(?:s|ed|ing)?",
    r"avoid(?:s|ed|ing)?",
    r"alleviat(?:e|es|ed|ing)",
    r"lessen(?:s|ed|ing)?",
    r"curtail(?:s|ed|ing)?",
    r"contain(?:s|ed|ing)?",
    r"address(?:es|ed|ing)?",
    r"respond(?:s|ed|ing)?\s+to",
    r"to\s+(?:deal|cope)\s+with",
    r"(?:lock|capp?)(?:s|ed|ing)?\s+(?:in|the)", # required verb + article/prep
]

GENERIC_RISK_GLUE = [
    # --- Core risk/change verbs & stems ---
    r"(?:ris|aris|declin|increas|decreas)(?:es?|ed|ing)?",
    r"result(?:ed|ing)?",
    r"falling",
    r"drops?\s+in",
    r"movements?",
    r"chang(?:e|es|ing)?",
    r"fluctuat(?:ions?|ing)?",
    r"(?:in|de)creas(?:e|es|ed|ing)?",
    # --- Macro / market environment ---
    r"econom(?:ic|y)",
    r"inflation(?:ary)?",
    r"volatil(?:ity|e|ities)?",
    r"(?:up|down)ward(?:s)?",
    r"markets?",
    r"values?",
    r"(?<!raw\s)material(?:s)?",
    # --- Risk nouns ---
    r"risks?",
    r"expos(?:ures?|ed?|es)",
    r"hypothetical",
    r"sensitiv(?:it(?:y|ies)|e)",
    r"vulnerab(?:ilit(?:y|ies)|le)",
    r"susceptib(?:ilit(?:y|ies)|le)",
    # --- Adjectival risk qualifiers ---
    r"adverse",
    r"(?:negative|detrimental)",
    r"(?:un)?(?:favorable|anticipated|expected|foreseen)",
    r"(?:significant|substantial|severe|considerable)",
    r"(?:elevated|heightened)",
    r"(?:in|un)stab(?:ilit(?:y|ies)|le)",
    # --- Stress / shock / disruption ---
    r"disrupt(?:ions?|ive|ing)?",
    r"turmoil",
    r"stress(?:es|ful)?",
    r"shocks?",
    # --- Generic event/factor nouns ---
    r"(?:events?|factors?|developments?|trends?|scenarios?|circumstances?|situations?|conditions?)",
    r"(?:consequences?|outcomes?|effects?|impacts?)",
    # --- Relationship / association language ---
    r"(?:associat|relat)(?:ed|ing|es?|ion(?:s|ships?)?)?",
    r"inherent",
    # --- Directional / causal glue ---
    r"pressure",
    r"potential",
    r"future",
    r"against",
    r"from",
    r"impact(?:s)?",
    r"effect(?:s)?",
    r"conditions?",
    r"uncertaint(?:y|ies)",
    r"management",
] + RISK_TERMS


def build_risk_managment_phrase(
    required_glue: Optional[List[str]] = None,
    strict_verbs: bool = False,
) -> str:
    verbs = build_alternation(MITIGATION_STRICT_VERBS if strict_verbs else MITIGATION_VERBS)
    glue = build_alternation(GENERIC_RISK_GLUE, sort_longest_first=True)
    filler = r"(?:\S+\s+){0,3}"
    
    if required_glue:
        req_alt = build_alternation(required_glue)
        glue_unit = rf"(?:{filler}{glue})"
        req_unit = rf"(?:{filler}{req_alt})"
        pre_chain = rf"(?:{glue_unit}\s+){{0,3}}"
        post_chain = rf"(?:{glue_unit}\s+){{0,3}}"
        gap = rf"{pre_chain}{req_unit}\s+{post_chain}"
    else:
        glue_unit = rf"(?:{filler}{glue})"
        gap = rf"(?:{glue_unit}\s+){{0,6}}"

    # Original pattern: [verbs] [gap] [final_filler] [_RISK_ALTERNATION]
    final_filler = r"(?:\S+\s+){0,3}" # Allows a few words before the final risk term
    original_pattern_str = rf"{verbs}\s+{gap}{final_filler}{_RISK_ALTERNATION}"

    # New requested pattern: [verbs] [risk_alternation] [required qlue]?
    new_pattern_parts = []
    # Allow a very small gap (e.g. "the", "its", "our") between verb and risk
    tiny_gap = r"(?:\S+\s+){0,3}"
    if required_glue:
        req_alt = build_alternation(required_glue, sort_longest_first=True)
        new_pattern_parts.append(rf"{verbs}\s+{tiny_gap}{_RISK_ALTERNATION}(?:\s+{tiny_gap}{req_alt})")
    else:
        new_pattern_parts.append(rf"{verbs}\s+{tiny_gap}{_RISK_ALTERNATION}")

    new_pattern_str = build_alternation(new_pattern_parts, sort_longest_first=True)

    # Combine both patterns, ensuring longest matches are tried first
    return build_alternation([original_pattern_str, new_pattern_str], sort_longest_first=True)


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

NUMBERS = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "thousand",
    "millions?",
    "billions?",
    "trillions?",
]

def build_number_alternation() -> str:
    # allow two numbers, first one optional
    numbers = build_alternation(NUMBERS, sort_longest_first=True)
    pattern = rf"(?:(?:{numbers}[- ])?{numbers})"
    return pattern

NUMBER_PATTERN = build_number_alternation()

DET_OPT = r"(?:the\s+|our\s+)?"
SUBJECTS = [
    # Simple pronouns
    r"we",
    r"us",
    # Generic entity terms
    rf"{DET_OPT}(?:company|firm|partnership|group|trust|entity|issuer|registrant|organization|association|co\.?|management)",
    # LLC / LP / GP structures
    rf"{DET_OPT}(?:llc|l\.l\.c\.|lp|l\.p\.|gp|g\.p\.)",
    # Partnership (general/limited)
    rf"{DET_OPT}(?:general\s+partner|limited\s+partner|partnership)",
    # Corporate forms
    rf"{DET_OPT}(?:corporation|corp\.|co\.|inc\.|incorporated)",
    # Parent entity
    rf"{DET_OPT}parent(?:\s+company)?",
    # Subsidiaries
    rf"{DET_OPT}(?:wholly[-\s]+owned\s+)?(?:subsidiar(?:y|ies))",
]

SUBJ = build_alternation(SUBJECTS)


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
SETTLEMENT_MODIFIERS = [
    "cash",
    "net",
    "daily",
    "monthly",
    "physically",
    "quarterly",
    "final",
    "mandatory",
    "annually",
    "weekly",
    "annual",
]
SETTLEMENT_MECHANICS_REGEX = build_regex(SETTLEMENT_MODIFIERS)
TERM_LOOKAHEADS = ["price", "rate", "balance", "value"]
TERMINATION_VERBS = [
    # --- SAFE VERBS (Past/Present/Participle) ---
    # Regex note: We removed |ion, |ity, |ment, |y suffixes
    r"expir(?:e(?:d|s)?)",  # Matches: expire, expired.  STOPS: expiration, expiry
    r"matur(?:e(?:d|s)?)",  # Matches: mature, matured.  STOPS: maturity
    r"terminat(?:e(?:d|s)?)",  # Matches: terminate, terminated.      STOPS: termination
    r"ceas(?:e(?:d|s)?|ing)",  # Matches: cease, ceased
    r"retir(?:e(?:d|s)?|ing)",  # Matches: retire, retired.
    add_restrictions(r"clos(?:e(?:d|s)?|ing)", lookaheads=TERM_LOOKAHEADS, lookahead_sep=r"\s+"),
    r"liquidat(?:e(?:d|s)?|ing)",  # Matches: liquidate, liquidated.  STOPS: liquidation
    r"unwound",
    r"unwind",
    add_restrictions(r"exercis(?:e(?:d|s)?|ing)", lookaheads=TERM_LOOKAHEADS, lookahead_sep=r"\s+"),
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
    # --- SAFEGUARDED SETTLEMENT (From previous turn) --- (settles annually, etc)
    add_restrictions(r"settl(?:es?|ed)", lookbehinds=SETTLEMENT_MODIFIERS, lookaheads=TERM_LOOKAHEADS + SETTLEMENT_MODIFIERS, lookahead_sep=r"\s+"),
    r"sold",
    r"wind(?:ing)?\s+down",
    r"dispos(?:e(?:d|s)?|ing)",
    r"derecogni[sz](?:e|ed|ing)",
    r"divest(?:ed|s|ing)?",
    r"preterminat(?:e(?:d|s)?|ing)",
    r"relinquish(?:ed|es|ing)?",
]
TERMINATION_NOUNS = [
    # --- STATES (Strongest) ---
    r"expir(?:ation|y|ing)",  # Matches: expiration, expiry
    r"maturit(?:y|ies)",  # Matches: maturity, maturities
    r"maturing",  # Matches: maturing
    r"terminat(?:ion|ing)",  # Matches: termination
    r"redemption",  # Matches: redemption
    # --- EVENTS (Transactional) ---
    r"extinguishment",  # Matches: extinguishment
    add_restrictions(r"settl(?:ement|ing)", lookbehinds=SETTLEMENT_MODIFIERS, lookaheads=TERM_LOOKAHEADS + SETTLEMENT_MODIFIERS + [r"every"], lookahead_sep=r"\s+"),  # Matches: settlement
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
    r"close(?:\s|\-)?out",
    r"lapse",
    r"forfeiture",
    r"derecognition",
    r"wind(?:\s|\-)?down",
    r"sale",
    r"disposition",
    r"transfer",
    r"assignment",
    r"relinquishment",
    r"voiding",
    r"divestiture",
]

ALL_TERM_TERMS = TERMINATION_VERBS + TERMINATION_NOUNS


EXCHANGE_ACRONYMS = [
    "NYMEX", "COMEX", "CBOT", "CME", "ICE", "LME", "CBOE", "NYBOT", "KCBT", "MGEX",
    "LIFFE", "TOCOM", "MX", "BM&F", "DME", "BIFFEX", "Eurex"
]

EXCHANGE_PREFIXES = [
    r"New\s+York\s+Mercantile",
    r"Chicago\s+Mercantile",
    r"Intercontinental",
    r"London\s+Metal",
    r"Chicago\s+Board\s+Options",
    r"Minneapolis\s+Grain",
    r"London\s+International\s+Financial\s+Futures\s+and\s+Options",
    r"Tokyo\s+Commodity",
    r"Montreal",
    r"Dubai\s+Mercantile",
    r"Baltic",
]

BOARD_OF_TRADE_PREFIXES = [
    r"Chicago",
    r"New\s+York",
    r"Kansas\s+City",
]

OTHER_EXCHANGES = [
    r"ICE\s+Futures",
    r"[Dd]erivative\s+[Mm]arkets?",
    r"Commodity\s+Exchange(?!\s+Act)",
]

DERIVATIVE_EXCHANGES = [
    build_alternation(EXCHANGE_ACRONYMS),
    rf"{build_alternation(EXCHANGE_PREFIXES)}\s+Exchange",
    rf"{build_alternation(BOARD_OF_TRADE_PREFIXES)}\s+Board\s+of\s+Trade",
] + OTHER_EXCHANGES

DERIVATIVE_ENTITIES = [
    r"\bCFTC\b",
    r"\bCommodity\s+Futures\s+Trading\s+Commission\b",
    r"\bISDA\b",
    r"\bInternational\s+Swaps\s+(?:[Aa]nd|&)\s+Derivatives\s+Association\b",
    r"\bNFA\b",
    r"\bNational\s+Futures\s+Association\b",
    r"\bFIA\b",
    r"\bFutures\s+Industry\s+Association\b",
    r"\bOptions\s+Clearing\s+Corporation\b",
    r"\bSIFMA\b",
    r"\bSecurities\s+Industry\s+and\s+Financial\s+Markets\s+Association\b",
    r"\bLCH\b",
    r"\bLondon\s+Clearing\s+House\b",
]


def dynamic_exchange() -> str:
    triggers = [
        "Derivatives?",
        "Futures",
        "Options",
        "Swaps",
        "Forwards",
        "Warrants",
        "Equities",
        "Board",
        "Mercantile",
        "Commodity",
        "Securities",
        "Financial",
        "Intercontinental",
        "Stock",
        "International",
        "National",
    ]
    trigger_pat = build_alternation(triggers)

    suffixes = [
        "Exchange",
        "Trade",
        "Market",
    ]
    suffix_pat = build_alternation(suffixes)

    cap_word = r"[A-Z][\w\'-]*"
    connector = r"(?:[oO]f|[aA]nd|&|[fF]or)"

    return rf"\b(?:{cap_word}\s+)*{trigger_pat}(?:\s+(?:{cap_word}|{connector}))*\s+{suffix_pat}\b"

def dynamic_clearing() -> str:
    triggers = [
        "Derivatives?",
        "Futures",
        "Options",
        "Swaps",
        "Forwards",
        "Warrants",
        "Equities",
        "Clearing",
        "International",
        "National",
        "Commodity",
        "Securities",
        "Financial",
    ]
    trigger_pat = build_alternation(triggers)
    
    suffixes = [
        "Association",
        "Commission",
        "Corporation",
        "Authority",
        "Council",
        "House",
        "Registry",
    ]
    suffix_pat = build_alternation(suffixes)
    
    cap_word = r"[A-Z][\w\'-]*"
    connector = r"(?:[oO]f|[aA]nd|&|[fF]or)"
    
    return rf"\b(?:{cap_word}\s+)*{trigger_pat}(?:\s+(?:{cap_word}|{connector}))*\s+{suffix_pat}\b"

TRADING_ENTITIES = DERIVATIVE_EXCHANGES + DERIVATIVE_ENTITIES + [dynamic_exchange(), dynamic_clearing()]
TRADING_VENUE_REGEX = build_regex(DERIVATIVE_EXCHANGES + [dynamic_exchange()], ignore_case=False)
DERIVATIVE_CLEARING_REGEX = build_regex(DERIVATIVE_ENTITIES + [dynamic_clearing()], ignore_case=False)
FULL_ENTITY_REGEX = build_regex(TRADING_ENTITIES, ignore_case=False)
