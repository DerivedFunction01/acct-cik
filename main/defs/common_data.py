from defs.class_definitions import Currency
months_full = [
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

months_abbr = [mon[0:3] for mon in months_full if len(mon) >= 4]
months = months_full + months_abbr
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

# Verbs for termination/expiration events (We {verb})
termination_verbs = [
    "terminated", "settled", "closed out", "ended", "unwounded", "liquidated",
]

# Verbs for termination/expiration events (The swap {verb})
swap_termination_verbs = [
    "expired",
    "matured",
    "reached maturity",
    "reached their expiration date",
    "settled",
    "terminated",
]

# Comparison verbs phrases
comparison_phrases = ["compared to", "versus", "down from", "reduced from"]

import random

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

STANDALONE_TYPES = ["swap", "derivative", "hedge", "cap"]
DEPENDENT_TYPES = [
    "floor",
    "collar",
    "swaption",
    "lock",
    "forward",
    "option",
    "future",
    "hedging",
]

BASE_TYPES = STANDALONE_TYPES + DEPENDENT_TYPES

DEFAULT_SUFFIXES = [
    "",
    "agreement",
    "contract",
    "arrangement",
    "instrument",
    "transaction",
    "commitment",
    "position",
    "program",
]

SPECIAL_EXPANSIONS = {
    "option": [
        "call option",
        "put option",
        "call contract",
        "put contract",
        "option contract",
    ],
}

CATEGORY_EXTRAS = {
    "ir": [],
    "fx": ["NDF"],
    "cp": [],
    "eq": ["index future"],
    "gen": [
        "over-the-counter contract",
        "collar strategies",
        "total return swap",
        "derivative financial instrument",
    ],
}

PLACEHOLDERS = {
    "ir": [
        "interest-rate",
        "single-currency",
        "Eurodollar",
        "SOFR",
        "SONIA",
        "LIBOR",
        "LIBOR-based",
        "EURIBOR",
        "treasury-rate",
        "treasury",
        "forward-rate",
        "fixed-rate",
        "floating-rate",
        "variable-rate",
        "benchmark-rate",
    ],
    "fx": [
        "foreign exchange",
        "forward exchange",
        "foreign currency",
        "currency",
        "cross-currency",
        "cross currency interest rate",
        "forward currency",
        "foreign currency",
        "forward exchange rate",
        "currency exchange",
        "exchange rate",
        "FX",
        "dollar call",
    ],
    "cp": [
        "commodity price",
        "commodity-related",
        "fixed commodity",
        "commodity-based",
    ],
    "eq": ["equity", "equity-related"],
    "gen": [""],
}


# =============================================================================
# EXPANSION FUNCTIONS
# =============================================================================


def expand_types(base_types, suffixes, special) -> list[str]:
    """Expand base types with suffixes and special overrides."""
    results = []
    for base in base_types:
        results.extend(f"{base} {s}".strip() for s in suffixes)
        if base in special:
            results.extend(special[base])
    return sorted(set(results))


def expand_derivative_terms(placeholders, types, extras) -> list[tuple[str, str, str]]:
    """Return (prefix, full term w/o prefix, base term) tuples."""
    results: list[tuple[str, str, str]]= []

    for ph in placeholders if placeholders else [""]:
        for t in types:
            # Skip dependent types without a placeholder
            if not ph and t in DEPENDENT_TYPES:
                continue

            full_term = " ".join(x for x in [ph, t] if x).strip()
            base_term = (
                " ".join(t.split()[-2:]) if len(t.split()) > 1 else t
            )  # keep "swap contract" not just "contract"

            # Always include base (no prefix)
            results.append(("", full_term, base_term))

            # Add global prefixes
            for pre in GLOBAL_PREFIXES:
                if pre:
                    results.append((pre, full_term, base_term))

            # Add swap prefixes only to swap-like instruments
            if any(x in t for x in ["swap", "swaption", "rate lock"]):
                for pre in SWAP_PREFIXES:
                    results.append((pre, full_term, base_term))

    # Add extras (no prefixes)
    for extra in extras:
        base_term = " ".join(extra.split()[-2:]) if len(extra.split()) > 1 else extra
        results.append(("", extra, base_term))

    # Deduplicate
    unique = []
    seen = set()
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    return sorted(unique, key=lambda x: (x[0], x[1]))


# =============================================================================
# BUILD FINAL DICTIONARY
# =============================================================================

SHARED_TYPES = expand_types(BASE_TYPES, DEFAULT_SUFFIXES, SPECIAL_EXPANSIONS)

derivative_keywords = {
    cat: expand_derivative_terms(
        PLACEHOLDERS[cat],
        SHARED_TYPES,
        CATEGORY_EXTRAS[cat],
    )
    for cat in PLACEHOLDERS
}
