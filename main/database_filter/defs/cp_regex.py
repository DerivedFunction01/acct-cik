import re
from typing import List, Tuple
from defs.derivatives_core import (
    ALL_SUFFIXES,
    BASE,
    COMMODITY_COMMERICIAL_PATTERN,
    DERIVATIVES,
    MULTI_BASE,
    PHYSICAL_COMMERCIAL_TERMS,
    DerivativeGenerator,
    SUFFIX,
    Groups,
)
from defs.regex_lib import add_restrictions, build_alternation, build_regex, plural, to_build_alternation
from defs.shared_context import (
    _RISK_ALTERNATION,
    DERIVATIVE_EXCHANGES,
    build_risk_managment_phrase,
)


# 3. COMMODITY (Strict)
# Focus: Physical assets and specific commodity names
# =============================================================================
# STRICT CONTEXT DEFINITIONS (Updated)
# =============================================================================


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
        "solar",
        "wind",
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
        rf"(?:[- ](?:{base_alt}|liquids?|power))?"
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

    # Allows natural gas contracts, etc
    suffix_alternation = to_build_alternation(ALL_SUFFIXES)

    strict_terms = [
        # General terms (natural gas contracts, natural gas price risks)
        rf"{_COMMODITY_NAMES}(?:(?:\s+\w+){{0,3}}{_RISK_ALTERNATION}|{suffix_alternation})",
        r"raw\s+material\s+costs?",
        r"fuel\s+surcharges?",
        # Financial Modifier + Specific Commodity
        # Matches: "Price of corn", "Hedging of oil", "Cost of gold"
        rf"{_RISK_ALTERNATION}(?:\s+\w+){{0,3}}{_COMMODITY_NAMES}",
    ] + DERIVATIVE_EXCHANGES

    soft_terms = (
        all_context_terms +
        COMMON_COMMODITIES +
        CP_UNITS_STRICT +
        NON_DERIVATIVE_COMMERCIAL_KEYWORDS +
        [rf"{_COMMODITY_NAMES}\s+{COMMODITY_COMMERICIAL_PATTERN}"]
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

    # Optimized modifiers (Max Munch applied internally)
    modifier_terms = [
        "costs?",
        "related",
        "based",
        "linked",
        "index",
        "capacity",
        "purchase",
        "price",
    ]
    modifier_alternation = build_alternation(modifier_terms, sort_longest_first=True)

    fixed_modifier_terms = [
        "costs?",
        "purchase",
        "price",
    ]
    fixed_modifier_alternation = build_alternation(fixed_modifier_terms, sort_longest_first=True)

    # --- OPTIMIZED PATTERNS ---

    # 1. Fixed Commodity Prefix (Strict)
    # Matches: "fixed corn contract", "fixed oil agreement"
    # Structure: fixed [commodity] [filler] [suffix]
    _FIXED_PRICE = add_restrictions(
        plural(BASE.FIXED_PRICE.value),
        lookaheads=[BASE.OPTION.value], # prevent fixed price purchase options
    )
    fixed_commodity_prefix = [
        rf"fixed[- ](?:{commodity_alternation})(?:[- ](?:{fixed_modifier_alternation}))?",
        _FIXED_PRICE,
    ]

    _FIXED_COMMODITY_CONFIG = DERIVATIVES(
        PREFIX=fixed_commodity_prefix,
        # fixed price purchase contract, fixed price purchase commitment, 
        STANDALONE_SUFFIXES=[BASE.OPTION, SUFFIX.COMMITMENT, SUFFIX.CONTRACT],
        SUFFIXES=[],
        _BASES=[],
        MULTI_BASE=[],
        _AMB_BASES=[],
    )
    _FIXED_COMMODITY_PATTERN = DerivativeGenerator(config=_FIXED_COMMODITY_CONFIG).generate()

    # 2. General Commodity + Base (Strict Base)
    # Matches: "corn swap", "oil future", "corn fixed price", "corn forward purchase"
    # Structure: [optional fixed] [commodity] [base] [suffix]

    general_commodity_prefix = [
        rf"(?:fixed[- ])?{commodity_alternation}(?:[- ](?:{modifier_alternation}))?",
    ]

    _BASES = Groups.CORE_UNAMBIGUOUS_BASES.copy()
    if BASE.FORWARD in _BASES:
        _BASES.remove(BASE.FORWARD)

    # naked forward requires restrictions to avoid natural gas forward sales/delivery
    _FWD = add_restrictions(BASE.FORWARD.value, lookaheads=PHYSICAL_COMMERCIAL_TERMS)

    # Allows natural gas derivatives
    _COMMODITY_BASE_CONFIG = DERIVATIVES(
        PREFIX=general_commodity_prefix,
        # Require a specific base (including fixed price/forward purchase)
        ADDITIONAL_BASES=[BASE.FIXED_PRICE, BASE.FORWARD_PURCHASE, BASE.FORWARD], # forward contracts without complex lookahead
        _BASES=_BASES,
        # DISALLOW standalone suffixes to prevent "corn contract"
        STANDALONE_SUFFIXES=[BASE.OPTION, _FWD], # Standalone forward and options
        MULTI_BASE=[] # leave empty
    )

    _COMMODITY_BASE_PATTERN = DerivativeGenerator(config=_COMMODITY_BASE_CONFIG).generate()

    _FREIGHT = r"(?:container[- ])?freight(?!\s+forward)"

    _FREIGHT_BASES = Groups.CORE_UNAMBIGUOUS_BASES.copy()
    # prevent freight forward contracts (in case)
    if BASE.FORWARD in _FREIGHT_BASES:
        _FREIGHT_BASES.remove(BASE.FORWARD)
    if BASE.SWAP in _FREIGHT_BASES:
        _FREIGHT_BASES.remove(BASE.SWAP)

    # Create a new specific derivative
    _FREIGHT_DERIVATIVES = DERIVATIVES(
        PREFIX=[_FREIGHT],
        _BASES=_FREIGHT_BASES,
        ADDITIONAL_BASES=[BASE.SWAP],  # Force swap to have a suffix
        STANDALONE_SUFFIXES=[],
        MULTI_BASE=[],
    )
    _FREIGHT_PATTERN = DerivativeGenerator(config=_FREIGHT_DERIVATIVES).generate()

    # 3. Unified Specific Phrases
    # These contain the max-munch phrases and apply to both strict and soft.
    _SPECIFIC_PHRASES = [
        _FIXED_COMMODITY_PATTERN,
        _COMMODITY_BASE_PATTERN,
        _FREIGHT_PATTERN,
        r"power purchase agreements?",  # raw string for regex
        r"forward\s+freight\s+agreements?",
        r"fixed[- ]price\s+swaps?"
    ]
    _SOFT_SPECIFIC_PHRASES = _SPECIFIC_PHRASES + [ r"commodity\s+contracts?"]

    _UNIFIED_MULTI_BASE = DERIVATIVES(
        PREFIX=[_FREIGHT] + general_commodity_prefix,
        _BASES=[],
        ADDITIONAL_BASES=[],
        STANDALONE_SUFFIXES=[],
        MULTI_BASE=[MULTI_BASE.DOUBLE_BASE],
    )
    _UNIFIED_MULTI_BASE_PATTERN = DerivativeGenerator(config=_UNIFIED_MULTI_BASE).generate()

    strict_cp_regex = build_regex([_UNIFIED_MULTI_BASE_PATTERN, _SPECIFIC_PHRASES])
    soft_cp_regex = build_regex([_UNIFIED_MULTI_BASE_PATTERN, _SOFT_SPECIFIC_PHRASES])

    return strict_cp_regex, soft_cp_regex, build_regex([_COMMODITY_NAMES])


EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX = build_regex(NON_DERIVATIVE_COMMERCIAL_KEYWORDS)
NPNS_REGEX = build_regex(NPNS_KEYWORDS)
COMMERCIAL_CONTRACT_REGEX = build_regex(COMMERCIAL_KEYWORDS)
CP_STRICT_CONTEXT_REGEX = build_regex(CP_STRICT_TERMS + CP_RISK_TERMS)
CP_CONTEXT_REGEX = build_regex(CP_CONTEXT_TERMS)
CP_RISK_REGEX = build_regex(CP_RISK_TERMS)
CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX = build_cp_regex()

from defs.verb_core import build_strict_do_not_mitigate_regex

CP_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(COMMON_COMMODITIES+ ["freight"])


def run_tests():
    from defs.derivatives_core import MatchLevel, run_category_tests, run_category_tests_counter
    test_cases = [
        ("commodity swap", MatchLevel.STRICT),
        ("commodity swap agreement", MatchLevel.STRICT),
        ("crude oil options", MatchLevel.STRICT),
        ("natural gas forward", MatchLevel.STRICT),
        ("natural gas derivative", MatchLevel.STRICT),
        ("natural gas contracts such as caps", MatchLevel.STRICT),
        ("fixed price swap", MatchLevel.STRICT),
        ("power purchase agreement", MatchLevel.STRICT),
        (
            "commodity contract",
            MatchLevel.SOFT,
        ),  # Note all cp contracts are derivatives
        ("oil price contract", MatchLevel.LOOSE),
        ("corn futures", MatchLevel.STRICT),
        ("commodity hedges", MatchLevel.LOOSE),
        ("oil hedging", MatchLevel.LOOSE),
        ("commodity arrangement", MatchLevel.LOOSE),
        ("commodity options", MatchLevel.STRICT),
        ("commodity options, swaps and futures", MatchLevel.STRICT),  # TRIPLE_BASE
        ("freight swap", MatchLevel.LOOSE),
        ("freight swap agreement", MatchLevel.STRICT),
        ("container freight derivative", MatchLevel.STRICT),
        ("freight forward", MatchLevel.NONE),
        ("freight forward agreement", MatchLevel.NONE),
    ]

    run_category_tests(test_cases, CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX)

    counter_cases = [
        ("commodity arrangement", MatchLevel.SOFT),
        ("commodity contracts", MatchLevel.STRICT),
        ("natural gas", MatchLevel.LOOSE),
    ]
    run_category_tests_counter(counter_cases, CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX)
