from dataclasses import dataclass
import re
from defs.regex_lib import build_alternation, build_regex

_DEBT_TERMS = r"(?:debts?|loans?|borrowings?|bonds?|senior notes?|notes?|debentures?)"
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
    r"Monte[- ]Carlo(?:[- ]simulations?)?",
    # Used for American options (exercisable early) and Convertibles
    r"Binomial(?:[- ]Lattice)?\s+models?",
    r"Lattice\s+models?",
    # General descriptive
    r"option[- ]pricing\s+models?",
]
VALUATION_MODELS_REGEX = build_regex(VALUATION_MODELS)

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
    "final",
    "mandatory",
    "annually",
    "weekly",
]
_settle_lookbehind = "".join([rf"(?<!\b{word}\s)" for word in SETTLEMENT_MODIFIERS])
TERMINATION_VERBS = [
    # --- SAFE VERBS (Past/Present/Participle) ---
    # Regex note: We removed |ion, |ity, |ment, |y suffixes
    r"expir(?:e(?:d|s)?)",  # Matches: expire, expired.  STOPS: expiration, expiry
    r"matur(?:e(?:d|s)?)",  # Matches: mature, matured.  STOPS: maturity
    r"terminat(?:e(?:d|s)?)",  # Matches: terminate, terminated.      STOPS: termination
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
    r"relinquish(?:ed|es|ing)?",
]
TERMINATION_NOUNS = [
    # --- STATES (Strongest) ---
    r"expir(?:ation|y|ing)",  # Matches: expiration, expiry
    r"maturit(?:y|ies)",  # Matches: maturity, maturities
    r"maturing",  # Matches: maturing
    r"terminat(?:ion|or|ing)",  # Matches: termination
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

def debt_expiration_regex() -> re.Pattern:
    # 1. We use a non-greedy gap (?:\s+\S+){0,3}? 
    # 2. We ensure the termination verb is checked at every step
    WORD_GAP = r"(?:\s+\S+){0,3}?" 
    
    # We strip the \b from the alternation to allow it to match 
    # immediately after the gap
    verbs = build_alternation(ALL_TERM_TERMS)
    
    pattern = rf"\b(?:{_DEBT_TERMS}|facility)(?:,)?{WORD_GAP}\s+{verbs}\b"
    return re.compile(pattern, re.IGNORECASE)


DEBT_TOKEN = " debt "
DEBT_EXP_REGEX = debt_expiration_regex()
