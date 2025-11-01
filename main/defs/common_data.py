from dataclasses import dataclass
from typing import Dict, List

@dataclass
class Currency:
    code: str
    full_name: str
    symbol: str
    adjective: str
    location: str

months = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

quarters = ["first", "second", "third", "fourth", "last", "1st", "2nd", "3rd", "4th"]
frequencies = [
    "quarterly",
    "on a regular basis",
    "at least quarterly",
    "monthly",
    "semi-annually",
    "periodically",
    "annually",
    "from time to time",
]

major_currencies = [
    Currency("USD", "U.S. Dollar", "$", "U.S.", "United States"),
    Currency("EUR", "Euro", "€", "European", "Europe"),
    Currency("GBP", "British Pound", "£", "British", "U.K."),
    Currency("JPY", "Japanese Yen", "¥", "Japanese", "Japan"),
    Currency("CAD", "Canadian Dollar", "$", "Canadian", "Canada"),
    Currency("AUD", "Australian Dollar", "$", "Australian", "Australia"),
    Currency("CHF", "Swiss Franc", "CHF", "Swiss", "Switzerland"),
    Currency("CNY", "Chinese Yuan", "¥", "Chinese", "China"),
]

european_currencies = [
    Currency("NOK", "Norwegian Krone", "kr", "Norwegian", "Norway"),
    Currency("SEK", "Swedish Krona", "kr", "Swedish", "Sweden"),
    Currency("DKK", "Danish Krone", "kr", "Danish", "Denmark"),
    Currency("PLN", "Polish Zloty", "zł", "Polish", "Poland"),
    Currency("HUF", "Hungarian Forint", "Ft", "Hungarian", "Hungary"),
    Currency("CZK", "Czech Koruna", "Kč", "Czech", "Czech Republic"),
    Currency("TRY", "Turkish Lira", "₺", "Turkish", "Turkey"),
    Currency("RUB", "Russian Ruble", "₽", "Russian", "Russia"),
    Currency("BGN", "Bulgarian Lev", "лв", "Bulgarian", "Bulgaria"),
    Currency("RON", "Romanian Leu", "lei", "Romanian", "Romania"),
]

asian_currencies = [
    Currency("INR", "Indian Rupee", "₹", "Indian", "India"),
    Currency("KRW", "South Korean Won", "₩", "South Korean", "South Korea"),
    Currency("SGD", "Singapore Dollar", "$", "Singaporean", "Singapore"),
    Currency("HKD", "Hong Kong Dollar", "$", "Hong Kong", "Hong Kong"),
    Currency("THB", "Thai Baht", "฿", "Thai", "Thailand"),
    Currency("MYR", "Malaysian Ringgit", "RM", "Malaysian", "Malaysia"),
]

americas_currencies = [
    Currency("MXN", "Mexican Peso", "$", "Mexican", "Mexico"),
    Currency("BRL", "Brazilian Real", "R$", "Brazilian", "Brazil"),
    Currency("ARS", "Argentine Peso", "$", "Argentine", "Argentina"),
    Currency("CLP", "Chilean Peso", "$", "Chilean", "Chile"),
    Currency("COP", "Colombian Peso", "$", "Colombian", "Colombia"),
]

other_currencies = [
    Currency("NZD", "New Zealand Dollar", "$", "New Zealand", "Oceania"),
    Currency("ZAR", "South African Rand", "R", "South African", "African"),
    Currency("AED", "UAE Dirham", "د.إ", "Emirati", "United Arab Emirates"),
    Currency("SAR", "Saudi Riyal", "ر.س", "Saudi", "Saudi Arabia"),
]

all_currencies = (
    major_currencies
    + european_currencies
    + asian_currencies
    + americas_currencies
    + other_currencies
)
geo_locations = ["markets", "locations", "operations", "regions"]
transaction_types = ["purchase", "sale", "exchange", "transfer", "import", "export"]

# Verbs that can be used for both individual and aggregate contexts
shared_use_verbs = [
    "utilized",
    "employed",
    "used",
    "implemented",
]

# For entering into a new int
individual_use_verbs = [
    "entered into",
    "executed",
    "initiated",
    "put in place",
    "secured",
    "arranged",
    "committed to",
    "purchased",
    "established",
] + shared_use_verbs

# For aggregrate summary notional amounts
aggregate_use_verbs = [
    "held",
    "maintained",
    "had outstanding",
    "had in place",
    "were party to",
] + shared_use_verbs

future_adverbs = [
    "will",
    "is scheduled to",    
    "is expected to",
    "is anticipated to",
    "is projected to",
]

# Verbs for termination/expiration events
termination_verbs_present = [
    "expire",
    "settle",
    "mature",
    "terminate",
    "close out",
    "unwind",
    "liquidate",
    "reach their expiration date",
]

termination_verbs_past = [
    "expired",
    "settled",
    "matured",
    "terminated",
    "close out",
    "unwounded",
    "liquidated",
    "reach their expiration date",
]

# Comparison verbs phrases
comparison_phrases = ["compared to", "versus", "down from", "reduced from"]

# Verbs for expressing non-use or absence of instruments
non_use_verbs = [
    "hold",
    "utilize",
    "maintain",
    "have",
    "use",
    "employ",
    "carry",
    "possess",
    "be a party to",
]

# Verbs for policy/strategy sentences (e.g., "The company {verb} derivatives...")
policy_verbs = [
    "utilizes",
    "employs",
    "uses",
    "maintains",
    "applies",
]

time_adverbs = {
    "current": [
        "currently",
        "actively",
        "presently",
        "now",
        "also",
        "primarily",
        "only",
        "expect to continue to",
        "",
    ],
    "past": [
        "in the past",
        "from time to time",
        "periodically",
        "occasionally",
        "in the future", 
        "",
    ],
}

not_adverbs = [
    "does not",
    "will not",
    "does not plan to",
    "does not intend to",
    "has no plans to",
    "will not seek to",
]

# Verbs for describing risk management actions (e.g., "...to {verb} exposure")
risk_management_verbs = [
    "manage",
    "mitigate",
    "reduce",
    "hedge",
    "offset",
    "stabilize",
    "limit",
    "protect against",
    "control",
    "mitigating",
    "hedging",
    "offsetting",
    "protecting against",
    "reducing",
    "managing",
    "stabilizing",
]

# --- New Placeholder Lists for Result Phrases ---

risk_exposure_terms = [
    "fluctuations",
    "movements",
    "risk",
    "volatility",
    "changes",
    "exposure",
    "variability",
]

general_interest_terms = [
    "interest rate",
    "borrowing cost",
    "financing cost",
    "interest cost",
    "rate of interest",
]

specific_rate_terms = [
    "variable rate",
    "fixed rate",
    "floating rate",
]
interest_rate_terms = general_interest_terms + specific_rate_terms

financial_outcome_verbs = [
    "recognized in",
    "recorded in",
    "reflected in",
    "reported in",
]

balance_sheet_locations = [
    "other income (expense), net",
    "other comprehensive income",
    "accumulated other comprehensive income (OCI)",
    "earnings",
    "net income",
    "the consolidated statements of operations",
    "the statement of operations",
    "the consolidated balance sheets",
    "equity",
]

gain_loss_phrases = ["gains", "losses", "increase", "decrease"]

# Optional / Immaterial terms
immaterial = [
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
    "small-scale",
    "marginal",
    "petty",
    "nominal",
    "slight",
    "unimportant",
    "zero",
    "none",
]

# Material / Significant terms
material = [
    "material",
    "significant",
    "substantial",
    "considerable",
    "important",
    "consequential",
    "critical",
    "major",
    "notable",
    "relevant",
    "weighty",
    "meaningful",
    "prominent",
    "pivotal",
    "essential",
]

# =============================================================================
# DERIVATIVES
# =============================================================================

GLOBAL_PREFIXES = ["forward-starting", ""]

SWAP_PREFIXES = [
    "pay-fixed, receive-floating",
    "pay-floating, receive-fixed",
    "pay variable, receive fixed",
    "pay fixed, receive variable",
]

PAY_PREFIX_RATIO = 0.05  # ~5% of total swap-like combinations


# =============================================================================
# BASE TYPES
# =============================================================================

STANDALONE_TYPES = ["swap", "derivative" "cap"]
DEPENDENT_TYPES = [
    "floor",
    "collar",
    "swaption",
    "lock",
    "forward",
    "option",
    "future",
    "hedge",
    "option",
    "call",
    "put",
]

BASE_TYPES = STANDALONE_TYPES + DEPENDENT_TYPES

DEFAULT_SUFFIXES = [
    "agreement",
    "contract",
    "arrangement",
    "instrument",
    "transaction",
    "commitment",
    "position",
    "program",
]

SPECIAL_SUFFIX = [
    "call option",
    "put option",
]

CATEGORY_EXTRAS = {
    "IR": [],
    "FX": ["NDF"],
    "CP": [],
    "EQ": ["index future"],
    "GEN": [
        "over-the-counter contract",
        "collar strategies",
        "total return swap",
        "derivative financial instrument",
    ],
}

PLACEHOLDERS = {
    "IR": [
        "interest-rate",
        "single-currency",
        "forward-rate",
        "benchmark-rate",
    ],
    "FX": [
        "foreign exchange",
        "forward exchange",
        "foreign currency",
        "currency",
        "cross-currency",
        "forward currency",
        "foreign currency",
        "forward exchange rate",
        "currency exchange",
        "exchange rate",
        "FX",
    ],
    "CP": [
        "commodity price",
        "commodity-related",
        "fixed commodity",
        "commodity-based",
    ],
    "EQ": ["equity", "equity-related"],
    "GEN": [""],
}

# =============================================================================
# NEW: Component-based structure for dynamic generation
# =============================================================================

DERIVATIVE_COMPONENTS = {
    "placeholders": PLACEHOLDERS,
    "base_types": BASE_TYPES,
    "dependent_types": DEPENDENT_TYPES,
    "suffixes": DEFAULT_SUFFIXES,
    "special_suffixes": SPECIAL_SUFFIX,
    "category_extras": CATEGORY_EXTRAS,
    "swap_prefixes": SWAP_PREFIXES,
    "global_prefixes": GLOBAL_PREFIXES
}
