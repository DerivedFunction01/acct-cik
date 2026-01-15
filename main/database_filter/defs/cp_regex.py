import re
from typing import List, Tuple
from defs.derivatives_core import (
    PHYSICAL_DELIVERY_PATTERN,
    build_smart_regex,
    expand_instruments,
    standalone_alternation
)
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import (
    _RISK_ALTERNATION,

)

# 3. COMMODITY (Strict)
# Focus: Physical assets and specific commodity names
# =============================================================================
# STRICT CONTEXT DEFINITIONS (Updated)
# =============================================================================

TRADING_ENTITIES = [
    r"\bNYMEX\b",
    r"\bNew\s+York\s+Mercantile\s+Exchange\b",
    r"\bCOMEX\b",
    r"\bCommodity\s+Exchange\b",
    r"\bCBOT\b",
    r"\bChicago\s+Board\s+of\s+Trade\b",
    r"\bCME\b",
    r"\bChicago\s+Mercantile\s+Exchange\b",
    r"\bICE\b",
    r"\bIntercontinental\s+Exchange\b",
    r"\bLME\b",
    r"\bLondon\s+Metal\s+Exchange\b",
    r"\bCBOE\b",
    r"\bChicago\s+Board\s+Options\s+Exchange\b",
]
COMMON_COMMODITIES = [
    # 🌾 Agriculture & Food
    "cocoa",
    "coffee",
    "corn",
    "cotton",
    "dairy",
    "milk",
    "grain",
    "livestock",
    "soybeans?",
    "sugar",
    "wool",
    "oranges?",
    "bananas?",
    "apples?",
    "grapes?",
    "tomato(?:es)?",
    "potato(?:es)?",
    "wheat",
    "rice",
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
    r"(?<!commericial[ -])paper",
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

# 1. Helper: Build the commodity alternation once
_COMMODITY_NAMES = build_alternation(COMMON_COMMODITIES)
COMMODITY_REGEX = build_regex(COMMON_COMMODITIES)
# 2. COMMODITY (Strict)
# FIX: Do NOT include raw commodity names.
# Only include them if attached to "price", "cost", "risk", "hedge", "volaitity"

# Strict commodity units (high confidence)
CP_UNITS_STRICT = [
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
    "bcf",
    "therm",
    "therms",
    "dth",
    "dekatherms",
]
CP_UNITS = [
    "units",
    "items",
    "packages",
    "containers",
    "loads",
    "gallons",
    "gal",
    "liters",
    "ltr",
    "cubic meters",
    "m3",
    "cubic feet",
    "ft3",
    "hectoliters",
    "hL",
    "kiloliters",
    "kL",
    "megaliters",
    "ML",
    "gigaliters",
    "GL",
    "board foot",
    "bf",
    "sheets",
    "coils",
    "bundles",
    "pallets",
    "sacks",
    "bales",
    "heads",
    "carats",
    "ingots",
    "bars",
] + CP_UNITS_STRICT
COMMODITY_UNIT_PATTERN = build_alternation(CP_UNITS)
CP_CONTEXT_TERMS = (
    [
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
    ]
    + COMMON_COMMODITIES
    + CP_UNITS_STRICT
    + TRADING_ENTITIES
)


CP_STRICT_TERMS = [
    # General terms
    rf"{_COMMODITY_NAMES}(?:\s+\w+){0,3}{_RISK_ALTERNATION}",
    r"raw\s+material\s+costs?",
    r"fuel\s+surcharges?",
    # Financial Modifier + Specific Commodity
    # Matches: "Price of corn", "Hedging of oil", "Cost of gold"
    rf"{_RISK_ALTERNATION}(?:\s+\w+){0,3}{_COMMODITY_NAMES}",
    rf"{_COMMODITY_NAMES}\s+{PHYSICAL_DELIVERY_PATTERN}",  # natural gas inventory, etc,
] + TRADING_ENTITIES


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
        "purchase"
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
        r"fixed[- ]price swaps?",
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

EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX = build_regex(NON_DERIVATIVE_COMMERCIAL_KEYWORDS)
CP_STRICT_CONTEXT_REGEX = build_regex(CP_STRICT_TERMS)
CP_CONTEXT_REGEX = build_regex(CP_CONTEXT_TERMS)
CP_REGEX, CP_SOFT_REGEX = build_cp_regex()
TRADING_VENUE_REGEX = build_regex(TRADING_ENTITIES)