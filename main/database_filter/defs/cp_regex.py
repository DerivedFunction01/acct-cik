import random
import re
from typing import List, Tuple
from defs.derivatives_core import (
    ALL_SUFFIXES,
    BASE,
    DERIVATIVES,
    MULTI_BASE,
    DerivativeGenerator,
    SUFFIX,
    Groups,
)
from defs.regex_lib import (
    add_restrictions,
    build_alternation,
    build_compound,
    build_regex,
    plural,
    to_build_alternation,
)
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

PHYSICAL_COMMERCIAL_TERMS = [  # words against "oil forward shipment, or deliverable forward receipt" from being matched
    r"deliver(?:y|ies)",
    r"orders?",
    r"suppl(?:y|ies)",
    r"invoices?",
    r"shipments?",
    r"receipts?",
    r"inventor(?:y|ies)",
    r"purchases?",
]

FWD_LOOKAHEAD = PHYSICAL_COMMERCIAL_TERMS + [
    r"sales?",
    r"confirmation",
    r"stocks?",
    r"prices?",
]

COMM_SUFFIX = build_alternation(FWD_LOOKAHEAD, sort_longest_first=True)


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
        "corns",
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
    r"physical\s+(?:forward|delivery)\s+(?:contracts?|agreements?)",
]

# contract, instrument, arrangement, agreement, commitment, obligation
_SUFFIX = (
    Groups.AMBIGUOUS_SUFFIXES
    + Groups.UNAMBIGUOUS_SUFFIXES
    + [SUFFIX.COMMITMENT, SUFFIX.OBLIGATION]
)

_COMM_TERMS = build_compound(
    [
        # Unconditional Obligations (ASC 440)
        r"unconditional\s+purchases?",
        # Others
        r"supply",
        r"sales",
        r"capacity",
        r"delivery",
        r"requirements?",
        r"storage",
        r"off[- ]take",
        r"procurement",
        r"throughput",
    ],
    _SUFFIX,
)
_COMM_FORWARD = build_compound(
    PHYSICAL_COMMERCIAL_TERMS,
    BASE.FORWARD,
)

COMMERCIAL_KEYWORDS = [
    r"take[- ]or[- ]pay",
    r"purchase\s+orders?",
    r"master\s+supply",
    _COMM_TERMS,
    _COMM_FORWARD,
]

NON_DERIVATIVE_COMMERCIAL_KEYWORDS = NPNS_KEYWORDS + COMMERCIAL_KEYWORDS

# Targets "we manufacture steel/aluminum/copper/plastic instruments"
_NON_FINANCIAL_INSTRUMENT_TERMS = [
    # Medical / surgical / clinical
    "surgical",
    "medical",
    "dental",
    "veterinary",
    "optical",
    "scientific",
    "laboratory",
    "lab",
    "diagnostic",
    "therapeutic",
    "orthopedic",
    "prosthetic",
    "sterile",
    "clinical",
    "calipers",
    "forceps",
    "clamps",
    "microscope",
    # Musical / artistic
    "music(?:al)?",
    "woodwinds?",
    "percussions?",
    "string",
    "keyboards?",
    "acoustics?",
    "band",
    "orchestra",
    # Industrial / mechanical / tools
    "equipment",
    "components",
    "fittings",
    "fixtures",
    "hardware",
    "machinery",
    "appliances?",
    "fasteners",
    "screws",
    "bolts",
    "washers",
    "valves",
    "gaskets",
    "bearings",
    # Fabrication / materials
    "mold(?:ing)?",
    "extrusions?",
    "tub(?:e|es?|ing)",
    "pip(?:e|ing|es?)",
    # Containers
    "bottles?",
    "jars?",
    "cans",
    # Kitchen / household
    "utensils?",
    "cook(?:ing|ware)?",
    "furniture",
    # Navigation / surveying
    "navigation(?:al)?",
    "survey(?:ing)?",
    
    # Item 1A description
    "manufactur(?:e|es|ed|ing|er|ers)",
    "produc(?:e|es|ed|ing|tion)",
    "fabricat(?:e|es|ed|ing|ion)",
    "assembl(?:e|es|ed|ing|y)",
    "industrial",
]

EXCLUDE_PRODUCT_CATALOGUE_REGEX = build_regex(_NON_FINANCIAL_INSTRUMENT_TERMS)


def build_cp_context_terms() -> Tuple[List[str], List[str], List[str]]:
    # Context terms specific to commodity categories
    category_context = {
        "energy": [
            # Markets/Hubs
            "PJM",
            "ERCOT",
            "MISO",
            "SPP",
            "CAISO",
            "NYISO",
            "ISO-NE",
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
            "OPIS",
            "Brent",
            # Terms
            "baseload",
            "peak load",
            "off-peak",
            "on-peak",
            "capacity",
            "power (?:assets|generation|supply)",
            "fuel",
            "energy",
            "(?:dark|crack|spark) spreads?",
        ],
        "crops": [
            "crops?",
            "harvest(?:s|ing)?",
            "yields?",
            "acreage",
            "plant(?:ing|ed)",
            "bushels?",
            "grains?",
        ],
        "livestock": [
            "livestock",
            "feed",
            "herd",
            "breeding",
            "heads?",
        ],
        "environmental": [
            "greenhouse",
            "carbon",
        ],
        "seafood": [
            "catch",
            "aquaculture",
            "fishery",
            "fisheries",
        ],
        "metals": [
            "mining",
            "mines?",
            "ores?",
            "smelt(?:ing|er)?",
            "refin(?:ing|ery|ed)",
            "bullion",
        ],
        "forestry": [
            "logging",
            "mills?",
            "pulp",
            "paper",
        ],
        "general": [
            "packaging",
            "manufactur(?:ing|ers?)",
            "raw materials?",
            "suppl(?:y|ies|iers?)",
            "containers?",
            "shipp(?:ing|ed)",
            "transportation",
            "inventor(?:y|ies)",
            "shipments?",
            "warehouses?",
            "storage",
            "logistic(?:s|al)?",
            "procurements?",
            "productions?",
            "wholesale",
            "factor(?:y|ies)",
            "deliver(?:y|ies)",
            "products?",
        ],
    }

    # Flatten context terms
    all_context_terms = [
        term for sublist in category_context.values() for term in sublist
    ]

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
        all_context_terms
        + COMMON_COMMODITIES
        + CP_UNITS_STRICT
        + NON_DERIVATIVE_COMMERCIAL_KEYWORDS
        + [rf"{_COMMODITY_NAMES}\s+{COMM_SUFFIX}"]
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
        r"(?:fixed[- ])?price(?: purchase)?",
    ]
    modifier_alternation = build_alternation(modifier_terms, sort_longest_first=True)

    # 2. General Commodity + Base (Strict Base)
    # Matches: "corn swap", "oil futures", "corn fixed price", "corn forward purchase"
    # Structure: [optional fixed] [commodity] [base] [suffix]

    general_commodity_prefix = [
        rf"(?:fixed[- ])?{commodity_alternation}(?:[- ](?:{modifier_alternation}))?",
    ]

    _BASES = Groups.CORE_UNAMBIGUOUS_BASES.copy()
    if BASE.FORWARD in _BASES:
        _BASES.remove(BASE.FORWARD)

    # naked forward requires restrictions to avoid natural gas forward sales/delivery
    _FWD = add_restrictions(BASE.FORWARD.value, lookaheads=FWD_LOOKAHEAD)

    # Allows natural gas derivatives, commodity derivatives, commodity forward, etc
    _COMMODITY_BASE_CONFIG = DERIVATIVES(
        PREFIX=general_commodity_prefix,
        # Require a specific base (forward purchase)
        ADDITIONAL_BASES=[
            BASE.FORWARD,
            BASE.FORWARD_PRICE,
        ],  # forward (price) contracts without complex lookahead
        _BASES=_BASES,
        ADDITIONAL_SUFFIXES=[],
        STANDALONE_SUFFIXES=[
            BASE.OPTION,
            _FWD,
            SUFFIX.INSTRUMENT,
        ],  # Standalone forward and options
        MULTI_BASE=[MULTI_BASE.MIXED_DOUBLE],
    )

    _COMMODITY_BASE_PATTERN = DerivativeGenerator(
        config=_COMMODITY_BASE_CONFIG
    ).generate()

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

    _GEN_COMMODITY = [
        rf"(?:fixed[- ])?commodity(?:[- ](?:{modifier_alternation}))?",
    ]
    _GEN_CONFIG = DERIVATIVES(
        PREFIX=_GEN_COMMODITY,
        _BASES=[],
        _AMB_BASES=[],
        ADDITIONAL_BASES=[],
        STANDALONE_SUFFIXES=Groups.AMBIGUOUS_BASES,  # Instrument already in base config
        MULTI_BASE=[],  # Leave empty, mixed double captures it.
    )
    _GEN_PATTERN = DerivativeGenerator(config=_GEN_CONFIG).generate()

    _FIXED_PRICE = [
        r"fixed[- ]price purchase",
    ]

    # Fixed price purchase commitment/contracts/arrangements, etc
    _FIXED_PRICE_CONFIG = DERIVATIVES(
        PREFIX=_FIXED_PRICE,
        _BASES=[],
        _AMB_BASES=[],
        ADDITIONAL_BASES=[],
        STANDALONE_SUFFIXES=Groups.UNAMBIGUOUS_SUFFIXES
        + Groups.AMBIGUOUS_SUFFIXES
        + [SUFFIX.COMMITMENT],
        MULTI_BASE=[],
    )
    _FIXED_PRICE_PATTERN = DerivativeGenerator(config=_FIXED_PRICE_CONFIG).generate()

    # 3. Unified Specific Phrases
    # These contain the max-munch phrases and apply to both strict and soft.
    _SPECIFIC_PHRASES = [
        _COMMODITY_BASE_PATTERN,
        _FREIGHT_PATTERN,
        _GEN_PATTERN,
        r"power purchase agreements?",  # raw string for regex
        r"forward\s+freight\s+agreements?",
        r"(?:fixed|open)[- ]price\s+swaps?",  # Only swaps, the rest
    ]
    # make commodity contracts, fixed price purchase commitments soft
    _SOFT_SPECIFIC_PHRASES = _SPECIFIC_PHRASES + [
        r"(?:fixed[- ])?commodity(?:[- ]price)?\s+contracts?",
        _FIXED_PRICE_PATTERN,
    ]

    # _UNIFIED_MULTI_BASE = DERIVATIVES(
    #     PREFIX=[_FREIGHT] + general_commodity_prefix,
    #     _BASES=[],
    #     ADDITIONAL_BASES=[],
    #     STANDALONE_SUFFIXES=[],
    #     MULTI_BASE=[MULTI_BASE.DOUBLE_BASE],
    # )
    # _UNIFIED_MULTI_BASE_PATTERN = DerivativeGenerator(config=_UNIFIED_MULTI_BASE).generate()

    strict_cp_regex = build_regex([_SPECIFIC_PHRASES])
    soft_cp_regex = build_regex([_SOFT_SPECIFIC_PHRASES])
    return strict_cp_regex, soft_cp_regex, build_regex([_COMMODITY_NAMES, "freight"])


EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX = build_regex(
    NON_DERIVATIVE_COMMERCIAL_KEYWORDS
)
NPNS_REGEX = build_regex(NPNS_KEYWORDS)
COMMERCIAL_CONTRACT_REGEX = build_regex(COMMERCIAL_KEYWORDS)
CP_STRICT_CONTEXT_REGEX = build_regex(CP_STRICT_TERMS + CP_RISK_TERMS)
CP_CONTEXT_REGEX = build_regex(CP_CONTEXT_TERMS)
CP_RISK_REGEX = build_regex(CP_RISK_TERMS)
CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX = build_cp_regex()

from defs.verb_core import build_strict_do_not_mitigate_regex

CP_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(
    COMMON_COMMODITIES + ["freight"]
)


def run_tests():
    from defs.derivatives_core import (
        MatchLevel,
        run_category_tests,
        run_category_tests_counter,
    )

    # Filter commodities for test generation (remove regex patterns)
    safe_commodities = [
        c
        for c in COMMON_COMMODITIES
        if re.match(r"^[a-zA-Z\s]+$", c)
        and c not in COMMODITY_MAP["chemicals"]
        and c not in COMMODITY_MAP["metals"]
    ]

    # Base phrases provided
    base_phrases = [
        "commodity contract",
        "commodity price contract",
        "commodity derivative",
        "commodity price derivative",
        "commodity instrument",
        "commodity price instrument",
        "commodity forward",
        "commodity price forward",
        "commodity futures",
        "commodity price futures",
        "commodity option",
        "commodity price option",
        "commodity cap",
        "commodity price cap",
        "commodity floor",
        "commodity price floor",
        "commodity collar",
        "commodity price collar",
        "commodity swap",
        "commodity price swap",
    ]

    # Configuration for expectations
    # Keys are lowercased keywords from the phrases
    # Default is STRICT if not specified
    expectations = {
        "contract": MatchLevel.SOFT,
        "instrument": MatchLevel.STRICT,
        "cap": MatchLevel.STRICT,  # Generic only
        "floor": MatchLevel.STRICT,  # Generic only
        "derivative": MatchLevel.STRICT,
        "forward": MatchLevel.STRICT,
        "futures": MatchLevel.STRICT,
        "option": MatchLevel.STRICT,
        "collar": MatchLevel.STRICT,
        "swap": MatchLevel.STRICT,
    }

    # Specific commodity expectations (Overrides generic if different)
    specific_overrides = {
        "cap": MatchLevel.LOOSE,  # Specific caps are not strict
        "floor": MatchLevel.LOOSE,
        "contract": MatchLevel.LOOSE,  # Specific contracts are not soft (only generic "commodity contract" is)
        "instrument": MatchLevel.STRICT,
    }

    test_cases = [
        ("power purchase agreement", MatchLevel.STRICT),
        ("freight swap", MatchLevel.LOOSE),
        ("freight swap agreement", MatchLevel.STRICT),
        ("container freight derivative", MatchLevel.STRICT),
        ("forward freight contract", MatchLevel.LOOSE),
        ("freight forward contract", MatchLevel.LOOSE),
        ("freight forward agreement", MatchLevel.LOOSE),
        ("marble floor", MatchLevel.LOOSE),  # Should be loose (matches marble)
        ("natural gas cap", MatchLevel.LOOSE),  # Should be loose (matches natural gas)
        ("fixed-price swap", MatchLevel.STRICT),
        ("fixed-price purchase commitment", MatchLevel.SOFT),
        ("commodity hedges", MatchLevel.STRICT),
        ("oil hedge", MatchLevel.LOOSE)
    ]

    # Generate dynamic test cases
    for phrase in base_phrases:
        lower_phrase = phrase.lower()
        keyword = next((k for k in expectations.keys() if k in lower_phrase), "swap")

        # 1. Add Original Phrase
        expected = expectations.get(keyword, MatchLevel.STRICT)
        test_cases.append((phrase, expected))

        # 2. Create 2 Duplicates with Random Commodities
        for _ in range(random.randint(1, 2)):
            specific_comm = "commodity"
            while specific_comm == "commodity":
                specific_comm = random.choice(safe_commodities)

            new_phrase = lower_phrase.replace("commodity", specific_comm)

            # Variation: price -> cost (50% chance)
            if "price" in new_phrase and random.random() > 0.5:
                new_phrase = new_phrase.replace("price", "cost")

            # Determine Expected for Specific
            spec_expected = specific_overrides.get(keyword, expected)
            test_cases.append((new_phrase, spec_expected))

    print("Commodity Derivatives tests:")
    print("(Assume that steel instruments refer to commodity derivatives and not manufactured goods)")
    run_category_tests(test_cases, CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX)

    counter_cases = [
        ("commodity arrangement", MatchLevel.SOFT),
        ("natural gas", MatchLevel.STRICT),  # Should NOT be strict
        (
            "natural gas forward sale",
            MatchLevel.STRICT,
        ),  # Forward lookahead blocks strict
        ("fixed-price contract", MatchLevel.SOFT),
    ]
    run_category_tests_counter(counter_cases, CP_REGEX, CP_SOFT_REGEX, CP_LOOSE_REGEX)
