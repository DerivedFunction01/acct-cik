import random
from definitions.common_data import transaction_types
COMMODITY_COST_TYPES = {
    "energy": ["extraction", "drilling", "production", "generation", "refining"],
    "metals_minerals": ["mining", "extraction", "smelting", "processing"],
    "agriculture": ["farming", "harvesting", "planting", "processing", "feeding"],
    "lumber_wood": ["logging", "harvesting", "milling", "processing"],
    "chemicals_plastics": ["manufacturing", "production", "processing", "feedstock"],
    "generic": [
        "input",
        "selling",
        "procurement",
        "transportation",
        "storage",
        "hedging",
    ]
    + transaction_types,
}

COMMODITY_UNITS = {
    "energy": [
        "barrels",
        "bbl",
        "barrels per day",
        "bbl/d",
        "MMBtu",
        "MMBtu/h",
        "BTU",
        "Btu",
        "gigajoules",
        "GJ",
        "MWh",
        "megawatt-hour",
    ],
    "bulk_solids": [
        "metric tons",
        "tonne",
        "MT",
        "tons",
        "t",
        "long tons",
        "LT",
        "short tons",
        "ST",
        "hundredweights",
        "cwt",
        "pounds",
        "lb",
    ],
    "precious_metals": ["ounces", "oz", "carats", "ingots", "bars"],
    "agriculture": ["bushels", "bu", "sacks", "bales", "pecks", "head"],
    "liquids": [
        "gallons",
        "gal",
        "liters",
        "L",
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
    ],
    "lumber": ["board foot", "bf", "cubic meters", "m3", "cubic feet", "ft3"],
    "manufactured": ["sheets", "coils", "bundles", "pallets", "units"],
    "generic": ["units", "items", "packages", "containers", "loads"],
}

COMMODITIES = {
    "energy": [
        "crude oil",
        "diesel fuel",
        "electricity",
        "electric",
        "energy",
        "ethanol",
        "fuel",
        "gas",
        "gasoline",
        "natural gas",
        "petroleum",
        "biodiesel",
        "biomass",
    ],
    "metals_minerals": [
        "aluminum",
        "base metals",
        "copper",
        "iron ore",
        "limestone",
        "metals",
        "minerals",
        "potash",
        "precious metals",
        "salt",
        "sand",
        "steel",
        "titanium",
        "uranium",
        "gravel",
        "phosphate",
        "soda ash",
    ],
    "agriculture": [
        "agricultural products",
        "cocoa",
        "coffee",
        "corn",
        "cotton",
        "dairy",
        "grain",
        "livestock",
        "soybeans",
        "sugar",
        "wool",
        "rubber",
    ],
    "lumber_wood": [
        "hardwood lumber",
        "logs",
        "lumber",
        "plywood",
        "softwood lumber",
        "timber",
        "wood",
        "wood chips",
        "wood pellets",
        "pulp",
        "paper",
    ],
    "chemicals_plastics": [
        "asphalt",
        "bitumen",
        "cement",
        "chemicals",
        "concrete",
        "feedstock",
        "fertilizer",
        "nitrogen",
        "petrochemicals",
        "plastics",
        "polymers",
        "resin",
        "sulfur",
    ],
    "textiles": ["textiles", "cotton", "wool"],
    "generic": ["commodity", "raw materials"],
}

# Flattened lists for random selection when no category is specified
volume_units = [unit for sublist in COMMODITY_UNITS.values() for unit in sublist]
commodities = [item for sublist in COMMODITIES.values() for item in sublist]

# Flattened list for random selection or fallback
cost_types = list(
    set([cost for sublist in COMMODITY_COST_TYPES.values() for cost in sublist])
)


def get_units_for_commodity(commodity_name: str) -> list[str]:
    """
    Returns a list of appropriate volume units for a given commodity.
    """
    # This mapping connects commodity categories to their corresponding unit categories.
    CATEGORY_TO_UNITS_MAP = {
        "energy": ["energy", "liquids"],
        "metals_minerals": ["bulk_solids", "precious_metals", "manufactured"],
        "agriculture": ["agriculture", "bulk_solids"],
        "lumber_wood": ["lumber", "manufactured", "bulk_solids"],
        "chemicals_plastics": ["bulk_solids", "liquids"],
        "textiles": ["agriculture", "manufactured", "bulk_solids"],
        "generic": ["generic"],  # Can be anything
    }

    commodity_name = commodity_name.lower()

    # Find which category the commodity belongs to.
    for category, commodity_list in COMMODITIES.items():
        if commodity_name in commodity_list:
            # Get the corresponding unit categories from the map.
            unit_categories = CATEGORY_TO_UNITS_MAP.get(category, [])
            # Collect all units from those categories.
            units = []
            for unit_cat in unit_categories:
                units.extend(COMMODITY_UNITS.get(unit_cat, []))
            return list(
                set(units)
            )  # Use set to remove duplicates, then convert back to list.

    # Default fallback
    return volume_units


def get_random_commodity_and_unit() -> tuple[str, str, str]:
    """
    Selects a random commodity and a matching, appropriate unit and cost type for it.

    Returns:
        A tuple containing the commodity name, its unit, and an associated cost type.
    """
    # 1. Pick a random commodity from the flattened list
    commodity_name = random.choice(commodities)

    # 2. Get the list of appropriate units for that commodity
    appropriate_units = get_units_for_commodity(commodity_name)
    unit = random.choice(appropriate_units)

    # 3. Pick a random unit from that list
    cost_type = "purchase"  # Default
    for category, commodity_list in COMMODITIES.items():
        if commodity_name in commodity_list:
            # Get all costs for that category plus generic costs
            possible_costs = (
                COMMODITY_COST_TYPES.get(category, []) + COMMODITY_COST_TYPES["generic"]
            )
            if possible_costs:
                cost_type = random.choice(possible_costs)
            break  # Stop after finding the first category

    return commodity_name, unit, cost_type
