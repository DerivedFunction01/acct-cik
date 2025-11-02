from dataclasses import dataclass
from typing import Dict, List


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
    "is set to",
    "is slated to",
    "is due to",
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
    "conclude",
    "end",
    "be settled",
    "be terminated",
    "reach their expiration date",
]

termination_verbs_past = [
    "expired",
    "settled",
    "matured",
    "terminated",
    "close out",
    "unwound",
    "liquidated",
    "concluded",
    "ended",
]

termination_noun = [
    "expiration",
    "settlement",
    "maturity",
    "termination",
    "closing",
    "unwinding",
    "liquidation",
    "conclusion",
    "ending",
]

# Comparison verbs phrases
comparison_phrases = [
    "compared to",
    "versus",
    "down from",
    "up from",
    "an increase from",
    "reduced from",
    "as against",
    "in comparison with",
]

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

# Verbs for assessing hedge effectiveness
assessment_verbs = [
    "assesses",
    "evaluates",
    "reviews",
    "tests",
    "monitors",
    "analyzes",
]
# Adverbs for describing the timing or nature of an action.
time_adverbs = {
    "current": [  # For describing active, ongoing use
        "currently",
        "actively",
        "presently",
        "now",
        "also",
        "primarily",
        "expect to continue to",
        "",
    ],
    "historical": [  # For describing past, completed actions
        "in the past",
        "previously",
        "formerly",
    ],
    "speculative": [  # For describing potential or uncertain future actions
        "from time to time",
        "periodically",
        "occasionally",
        "in the future",
        "may", # For other adverbs in this category, we can still append "may", such as "from time to time, may use ..."
    ],
    "non_use": [  # For explicitly stating non-use
        "does not",
        "will not",
        "does not plan to",
        "does not intend to",
        "has no plans to",
        "will not seek to",
    ],
}

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
    "risks",
    "volatility",
    "changes",
    "exposure",
    "variability",
]

hedge_metrics = [
    "changes in cash flows",
    "changes in fair value",
    "variability",
    "exposure",
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

gain_loss_phrases = [
    "gains",
    "losses",
    "gains and losses",
    "increase",
    "decrease",
]

cost_metrics = [
    "cost of goods sold",
    "cost of sales",
    "operating expenses",
    "manufacturing costs",
]

inventory_methods = [
    "first-in, first-out (FIFO)",
    "last-in, first-out (LIFO)",
    "weighted-average cost",
    "specific identification",
    "standard cost",
    "moving average cost",
    "retail inventory method",
]

market_drivers = [
    "geopolitical tensions and supply chain disruptions",
    "changes in global supply and demand",
    "weather patterns and their impact on production",
    "speculative trading activity in the futures market",
    "fluctuations in currency exchange rates",
]
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
# Outstanding active state descriptors
state_descriptors = ["outstanding", "active", "remaining", "open"]

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

STANDALONE_TYPES = ["swap", "derivative", "cap"]
DEPENDENT_TYPES = [
    "floor",
    "collar",
    "swaption",
    "lock",
    "forward",
    "option",
    "future",
    "hedge",
    "hedging",
    "option",
    "call",
    "put",
]

BASE_TYPES = STANDALONE_TYPES + DEPENDENT_TYPES

# Types that should not have an alias
NO_ALIAS_TYPES_INDEPENDENT = [
    "derivative",
    "hedge",
    
]

# Types that should not have an alias
NO_ALIAS_TYPES = [
    "hedging",
] + NO_ALIAS_TYPES_INDEPENDENT

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
    "global_prefixes": GLOBAL_PREFIXES,
    "no_alias_types": NO_ALIAS_TYPES,
    "no_alias_independent": NO_ALIAS_TYPES_INDEPENDENT,
}

# --- NEW: Components for dynamically generating generic descriptions ---

# e.g., "various", "certain"
GENERIC_QUANTIFIERS = [
    "various", "certain", "a number of", "a series of", "multiple", "several", "",
]

# e.g., "derivative", "financial"
GENERIC_DESCRIPTORS = [
    "financial"
] + NO_ALIAS_TYPES
