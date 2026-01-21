import re
from typing import List, Tuple
from defs.derivatives_core import (
    PHYSICAL_DELIVERY_PATTERN,
    build_smart_regex,
    expand_instruments,
)
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import (
    _RISK_ALTERNATION,
    build_risk_managment_phrase,
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


def build_energy_dynamic_pattern() -> str:
    prefixes = [
        "bio",
        "liquefied",
        "liquid",
    ]

    bases = [
        "fuels?",
        "oils?",
        "energy",
        "coal",
        "gas(?:oline)?",
        "propane",
        "power",
        "petroleum",
        "diesel",
        "butane",
        "electricity",
        "distillates",
        "ethane",
        "ethanol",
        "kerosene",
        "LNG",
        "LPG",
    ]

    modifiers = [
        "bunker",
        "marine",
        "jet",
        "(?:air|aero)plane",
        "helicopter",
        "plane",
        "aero",
        "aviation",
        "crude",
        "heating",
        "coking",
        "natural",
        "carbon",
        "solar",
        "wind",
        "renewable",
        "liquid",
    ]

    prefix_alt = build_alternation(prefixes, sort_longest_first=True)
    modifier_alt = build_alternation(modifiers, sort_longest_first=True)
    base_alt = build_alternation(bases, sort_longest_first=True)

    # Optional prefix, optional modifier, required base, optional second base
    return (
        rf"(?:(?:{prefix_alt})[- ])?"
        rf"(?:(?:{modifier_alt})[- ])?"
        rf"(?:{base_alt})"
        rf"(?:[- ](?:{base_alt}|liquids?))?"
    )


def build_metals_dynamic_pattern() -> str:
    """
    Dynamically build comprehensive Metals patterns.
    Allows:
        prefix? modifier? base (base)?
    """

    prefixes = [
        "precious",
        "rare earth",
        "base",
        "scrap",
        "silicon",
    ]

    # Optional: add more if you want "raw copper", "refined nickel", etc.
    modifiers = [
        "stainless",
        "refined",
        "raw",
        "unrefined",
        "high[- ]grade",
        "low[- ]grade",
    ]

    bases = [
        "aluminum",
        "copper",
        "iron",
        "gold",
        "silver",
        "metals?",
        "ores?",
        "(?:stainless[- ])?steel",
        "titanium",
        "uranium",
        "nickel",
        "zinc",
        "lead",
        "tin",
        "platinum",
        "palladium",
        "rhodium",
        "cobalt",
        "molybdenum",
        "chromium",
        "lithium",
        "magnesium",
        "vanadium",
        "alumina",
        "bauxite",
        "antimony",
        "arsenic",
        "bismuth",
        "indium",
        "gallium",
        "graphite",
        "potassium",
        "diamonds?",
        "gemstones?",
    ]

    prefix_alt = build_alternation(prefixes, sort_longest_first=True)
    modifier_alt = build_alternation(modifiers, sort_longest_first=True)
    base_alt = build_alternation(bases, sort_longest_first=True)

    # prefix? modifier? base base?
    return (
        rf"(?:(?:{prefix_alt})[- ])?"
        rf"(?:(?:{modifier_alt})[- ])?"
        rf"(?:{base_alt})"
        rf"(?:[- ](?:{base_alt}))?"
    )


COMMODITY_MAP = {
    "crops": [
        # --- Fruits ---
        "oranges?",
        "bananas?",
        "apples?",
        "grapes?",
        "avocados?",
        "mango(?:es)?",
        "pineapples?",
        "papayas?",
        "fruit",
        "kiwi(?:s)?",
        "lemon(?:s)?",
        "lime(?:s)?",
        "peach(?:es)?",
        "pear(?:s)?",
        "plum(?:s)?",
        "apricot(?:s)?",
        "fig(?:s)?",
        "olive(?:s)?",
        "coconut(?:s)?",
        # --- Berries ---
        "strawberr(?:y|ies)",
        "blueberr(?:y|ies)",
        "raspberr(?:y|ies)",
        "cherr(?:y|ies)",
        "berr(?:y|ies)",
        "cranberr(?:y|ies)",
        # --- Vegetables ---
        "tomato(?:es)?",
        "potato(?:es)?",
        "garlic",
        "pumpkins?",
        "peppers?",
        "peas?",
        "carrots?",
        "onions?",
        "cabbage",
        "lettuce",
        "spinach",
        "broccoli",
        "cauliflower",
        "vegetables?",
        "cucumber(?:s)?",
        "eggplant(?:s)?",
        "zucchini",
        "squash(?:es)?",
        "sweet potato(?:es)?",
        "turnip(?:s)?",
        "radish(?:es)?",
        "asparagus",
        "celery",
        # --- Grains / Cereals ---
        "corn",
        "grain",
        "wheat",
        "rice",
        "barley",
        "oats",
        "rye",
        "sorghum",
        "millet",
        "quinoa",
        "buckwheat",
        "triticale",
        "cereal",
        "oatmeal",
        # --- Oilseeds ---
        "soybeans?",
        "canola",
        "sunflower",
        "palm oil",
        "rapeseed",
        "flax",
        "hemp",
        "soy",
        # --- Legumes / Pulses ---
        "lentils?",
        "chickpeas?",
        "beans?",
        "peas?",
        "legumes?",
        "pulses?",
        # --- Nuts ---
        "almonds?",
        "walnuts?",
        "pecans?",
        "pistachios?",
        # --- Roots / Tubers ---
        "cassava",
        "yams?",
        "beets?",
        # --- Fungi ---
        "mushrooms?",
        # --- Specialty Crops ---
        "cocoa",
        "coffee",
        "cotton",
        "sugar",
        "tea",
        "tobacco",
        # --- General Crop Categories ---
        "(?:horticultural|row) crops?",
        # -- Other ---
        "honey",
        "beeswax",
        "spices?",
        "(?:(?:bell|spicy|sweet|green|red|chili|jalape[nñ]o|banana|ghost|cayenne)[- ])?peppers?",
        # Certain peppers
        "jalape[nñ]o?",
        "california reapers?",
        "paprika",
        "cinnamon",
        "cloves?",
        "nutmeg",
        "ginger",
        "turmeric",
        "vanilla",
        "saffron",
        "essential oils?",  # borderline but traded physically
        "(?:natural[- ])?rubber",
        "latex",
        "gum arabic",
    ],
    "livestock": [
        "dairy",
        "milk",
        "livestock",
        "eggs?",
        "cattle",
        "chicken",
        "pork",
        "turkey",
        "avian",
        "hogs?",
        "lean hogs?",
        "(?:feeder|live) cattle",
        "poultry",
        "beef",
        "meat",
        "lamb",
        "wool",
        "sheep",
        "goats?",
        "mutton",
        "veal",
        "bison",
        "buffalo",
        "ducks?",
        "geese?",
        "broilers?",
        "swine",
        "sows?",
        "boars?",
        "calves?",
        "heifers?",
        "ruminants?",
        "livestock feed",
        "feedlot",
        "feedstock",
        "turkeys?",
        "duck",
        "goose",
        "guinea fowl",
        "rabbit",
        "venison",
        "alpaca",
        "llama",
        "yak",
        "butter",
        "cheese",
        "whey",
        "milk powder",
        "nonfat dry milk",
        "dry whey",
    ],
    "seafood": [
        "salmon",
        "fish",
        "shrimp",
        "crab",
        "lobster",
        "tuna",
        "seafood",
        "aquaculture",
        "prawn",
        "scallop",
        "oyster",
        "clam",
        "mussel",
        "squid",
        "octopus",
        "halibut",
        "cod",
        "haddock",
        "tilapia",
        "snapper",
        "mackerel",
        "anchovy",
        "sardine",
        "trout",
        "bass",
        "catfish",
        "(?:king|snow|blue) crabs?",
        "shellfish",
        "bivalve",
        "crustacean",
        "sea bass",
        "yellowtail",
        "albacore",
        "eel",
        "uni",
        "roe",
        "caviar",
        "seaweed",
        "kelp",
        "mariculture",
        "pollock",
        "hake",
        "herring",
        "plaice",
        "flounder",
        "grouper",
        "mahi-mahi",
        "swordfish",
        "kingfish",
        "pomfret",
        "abalone",
        "sea urchin",
        "periwinkle",
        "shark",
        "whale",
        "dolphin",
    ],
    "energy": [
        "biodiesel",
        "biomass",
        build_energy_dynamic_pattern(),
        "condensate",
        "naphtha",
    ],
    "chemicals": [
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
        "salt",
        "silicon",
        "urea",
        "ammonia",
        "carbon",
    ],
    "metals": [build_metals_dynamic_pattern()],
    "construction": [
        "asphalt",
        "bitumen",
        "cement",
        "concrete",
        "gravel",
        "limestone",
        "sand",
        "clay",
        "slate",
        "granite",
        "marble",
        "gypsum",
        "plaster",
        "mortar",
        "bricks?",
        "ballast",
        "dolomite",
        "basalt",
        "quartzite",
        "pavers?",
        "tiles?",
        "drywall",
        "sheetrock",
        "insulation",
        "fiberglass",
        "roofing materials?",
        "shingles?",
        "precast panels?",
    ],
    "forestry": [
        "(?:hardwood|softwood) lumber",
        "log",
        "lumber",
        "(?:ply|hard|soft|sawn)wood",
        "timber",
        "wood",
        "wood (?:chips?|pellets?|fibers?|panels?|pulp)",
        r"(?<!commercial[ -])papers?",
        r"cardboard",
        r"cartons?",
        "pulp",
        # --- Added ---
        "veneer",
        "kraft paper",
        "newsprint",
        "cellulose",
        "(?:particle|fiber|oriented strand )board",
    ],
    "environmental": [
        "carbon credits?",
        "carbon offsets?",
        "emissions?",
        "emission allowances?",
    ],
    "general": [
        "raw materials?",
        "textile",
        "commodity",
        "commodities",
    ],
}

COMMON_COMMODITIES = [item for sublist in COMMODITY_MAP.values() for item in sublist]

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

NPNS_KEYWORDS = [
    # The "NPNS" Exemption (Physical Contracts)
    r"normal\s+purchases?\s+(?:and|&)\s+(?:normal\s+)?sales?",
    r"NPNS",
    r"own[- ]use\s+exemption",
]

COMMERCIAL_KEYWORDS = [
    # Unconditional Obligations (ASC 440)
    r"unconditional\s+purchase\s+(?:obligations?|commitments?)",
    r"take[- ]or[- ]pay",
    r"throughput\s+(?:agreements?|contracts?)",
    # General Supply Chain (If not caught by Physical Inventory)
    r"supply\s+(?:arrangements?|agreements?)",
    r"procurement\s+(?:agreements?|contracts?|arrangements)",
]

NON_DERIVATIVE_COMMERCIAL_KEYWORDS = NPNS_KEYWORDS + COMMERCIAL_KEYWORDS

def build_cp_context_terms() -> Tuple[List[str], List[str], List[str]]:
    # Context terms specific to commodity categories
    category_context = {
        "energy": [
            # Markets/Hubs
            "PJM", "ERCOT", "MISO", "SPP", "CAISO", "NYISO", "ISO-NE",
            "Henry Hub", "WTI", "West Texas Intermediate", "Cushing",
            "Mont Belvieu", "TTF", "JKM", "Dominion South", "Platts",
            "Argus", "OPIS", "Brent",
            # Terms
            "baseload", "peak load", "off-peak", "on-peak", "capacity",
            "power generation", "power assets", "fuel", "energy", "power",
            "(?:dark|crack|spark) spreads?"
        ],
        "crops": [
            "crops?", "harvest(?:s|ing)?", "yields?", "acreage", "plant(?:ing|ed)",
            "bushels?", "grains?",
        ],
        "livestock": [
            "livestock", "feed", "herd", "breeding", "heads?",
        ],
        "environmental": [
            "greenhouse", "carbon",
        ],
        "seafood": [
            "catch", "aquaculture", "fishery", "fisheries",
        ],
        "metals": [
            "mining", "mines?", "ores?", "smelt(?:ing|er)?", "refin(?:ing|ery|ed)",
            "bullion",
        ],
        "forestry": [
            "logging", "mills?", "pulp", "paper",
        ],
        "general": [
            "packaging", "manufactur(?:ing|ers?)", "raw materials?",
            "suppl(?:y|ies|iers?)", "containers?", "shipp(?:ing|ed)", "transportation",
            "inventor(?:y|ies)", "shipments?", "warehouses?", "storage",
            "logistic(?:s|al)?", "procurements?", "productions?", "wholesale",
            "factor(?:y|ies)", "deliver(?:y|ies)", "products?",
        ]
    }

    # Flatten context terms
    all_context_terms = [term for sublist in category_context.values() for term in sublist]

    # Glue for risk phrase: Commodities + Specific Context Terms
    # We exclude generic operational terms (packaging, shipping, etc.) from the risk phrase
    # to ensure we only capture market/price risk context.
    specific_context_terms = []
    for cat, terms in category_context.items():
        if cat != "general":
            specific_context_terms.extend(terms)
            
    # Selectively add safe general terms that imply market risk
    # Note: "raw materials" is already in COMMON_COMMODITIES
    safe_general_terms = ["procurements?", "wholesale"]
    
    cp_risk_glue = COMMON_COMMODITIES + specific_context_terms + safe_general_terms

    risk_terms = [build_risk_managment_phrase(cp_risk_glue)]

    strict_terms = [
        # General terms
        rf"{_COMMODITY_NAMES}(?:\s+\w+){{0,3}}{_RISK_ALTERNATION}",
        r"raw\s+material\s+costs?",
        r"fuel\s+surcharges?",
        # Financial Modifier + Specific Commodity
        # Matches: "Price of corn", "Hedging of oil", "Cost of gold"
        rf"{_RISK_ALTERNATION}(?:\s+\w+){{0,3}}{_COMMODITY_NAMES}",
    ] + TRADING_ENTITIES

    soft_terms = (
        all_context_terms +
        COMMON_COMMODITIES +
        CP_UNITS_STRICT +
        NON_DERIVATIVE_COMMERCIAL_KEYWORDS +
        [rf"{_COMMODITY_NAMES}\s+{PHYSICAL_DELIVERY_PATTERN}"]
    )

    return strict_terms, soft_terms, risk_terms


CP_STRICT_TERMS, CP_SOFT_TERMS, CP_RISK_TERMS = build_cp_context_terms()
CP_CONTEXT_TERMS = CP_STRICT_TERMS + CP_SOFT_TERMS + CP_RISK_TERMS


def build_cp_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
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
        r"fixed[- ]price(?: purchase)?",
    ]
    strict_core_alternation = build_alternation(
        strict_core_patterns, sort_longest_first=True
    )

    # 3. Unified Specific Phrases
    # These contain the max-munch phrases and apply to both strict and soft.
    specific_phrases = [
        r"weather derivatives?",  # raw string for regex
        r"power purchase agreements?",  # raw string for regex
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
    soft_instrument_fragment = expand_instruments(
        unsafe=True,
        exclude_standalone_suffixes=True,
        additional_standalone_suffixes=["contracts?", "options?"],
    )

    # Soft pattern combines simple prefixes ('commodity', 'CP') with the full range of instrument terms.
    soft_pattern = build_smart_regex(
        [strict_core_alternation],  # Simple prefixes
        soft_instrument_fragment,  # Full range of instruments (e.g., 'options', 'futures')
        sorted_specific_phrases,  # All high-priority explicit phrases
    )
    soft_cp_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)
    
    loose_instrument_fragment = expand_instruments(unsafe=True, exclude_standalone_suffixes=False, full_alternation=True)
    
    loose_pattern = build_smart_regex(
        [strict_core_alternation],
        loose_instrument_fragment,
        sorted_specific_phrases,
    )
    loose_cp_regex = re.compile(r"\b" + loose_pattern + r"\b", re.IGNORECASE)

    return strict_cp_regex, soft_cp_regex, loose_cp_regex


EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX = build_regex(NON_DERIVATIVE_COMMERCIAL_KEYWORDS)
NPNS_REGEX = build_regex(NPNS_KEYWORDS)
COMMERCIAL_CONTRACT_REGEX = build_regex(COMMERCIAL_KEYWORDS)
CP_STRICT_CONTEXT_REGEX = build_regex(CP_STRICT_TERMS + CP_RISK_TERMS)
CP_CONTEXT_REGEX = build_regex(CP_CONTEXT_TERMS)
CP_RISK_REGEX = build_regex(CP_RISK_TERMS)
CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX = build_cp_regex()
TRADING_VENUE_REGEX = build_regex(TRADING_ENTITIES)
from defs.verb_core import build_strict_do_not_mitigate_regex

CP_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(COMMON_COMMODITIES)


def run_tests():
    from defs.derivatives_core import MatchLevel, run_category_tests, run_category_tests_counter
    test_cases = [
        ("commodity swap", MatchLevel.STRICT),
        ("commodity swap agreement", MatchLevel.STRICT),
        ("crude oil swap", MatchLevel.STRICT),
        ("natural gas forward", MatchLevel.STRICT),
        ("natural gas derivative", MatchLevel.STRICT),
        ("fixed price swap", MatchLevel.STRICT),
        ("weather derivative", MatchLevel.STRICT),
        ("power purchase agreement", MatchLevel.STRICT),
        ("commodity contract", MatchLevel.SOFT),
        ("oil price contract", MatchLevel.SOFT),
        ("corn futures", MatchLevel.STRICT),
        ("commodity hedges", MatchLevel.LOOSE),
        ("oil hedging", MatchLevel.LOOSE),
        ("commodity arrangement", MatchLevel.LOOSE),
        ("commodity options", MatchLevel.SOFT),
    ]

    run_category_tests(test_cases, CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX)

    counter_cases = [
        ("commodity arrangement", MatchLevel.SOFT),
        ("commodity contracts", MatchLevel.STRICT),
        ("crude oil option", MatchLevel.STRICT),
        ("natural gas", MatchLevel.LOOSE),
    ]
    run_category_tests_counter(counter_cases, CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX)
