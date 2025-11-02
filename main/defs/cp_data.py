import random
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from defs.common_data import (
    transaction_types,
    risk_exposure_terms,
    gain_loss_phrases,
    financial_outcome_verbs,
    balance_sheet_locations,
    comparison_phrases,
)
from defs.function_definitions import _get_company_reference
from defs.template_definitions import _cleanup_sentence, _format_single_notional
from defs.instrument_definitions import HedgedItem, NotionalInstrument


@dataclass
class CommodityHedgedItem(HedgedItem):
    """Represents a commodity being hedged (for CP derivatives).

    Args:
        commodity_type: str - The type of commodity being hedged.
        quantity: int - The quantity of the commodity.
        unit_of_volume: str - The unit of volume of the commodity.
        price_per_unit: float - The price per unit of the commodity.
        cost_type: str - The cost type of the commodity (e.g., "input").
        transaction_type: Literal["purchase", "sale"] - The transaction type (e.g., "purchase").
        supplier: Optional[str] - The supplier of the commodity if purchased.
    """

    commodity_type: str
    quantity: int
    unit_of_volume: str
    price_per_unit: float
    cost_type: str
    transaction_type: str
    supplier: Optional[str]


class CPInstrument(NotionalInstrument[CommodityHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="CP", **kwargs)

COMMODITY_COST_TYPES = {
    "energy": ["extraction", "drilling", "production", "generation", "refining"],
    "metals_minerals": ["mining", "extraction", "smelting", "refining"],
    "agriculture": ["farming", "harvesting", "planting", "feeding"],
    "lumber_wood": ["logging", "harvesting", "milling"],
    "chemicals_plastics": ["manufacturing", "production", "synthesis"],
    "generic": [
        "input",
        "selling",
        "procurement",
        "transportation",
        "storage",
        "hedging",
        "processing"
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
    "generic": ["commodity", "raw materials", "energy"],
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


def get_cost_types_for_commodity(commodity_name: Optional[str] = "commodity") -> list[str]:
    """
    Returns a list of appropriate cost types for a given commodity by finding
    its category and combining specific and generic cost types.
    """
    
    commodity_name = commodity_name.lower() if commodity_name else "commodity"

    # Find which category the commodity belongs to.
    for category, commodity_list in COMMODITIES.items():
        if commodity_name in commodity_list:
            # Get all costs for that category plus generic costs.
            possible_costs = (
                COMMODITY_COST_TYPES.get(category, []) + COMMODITY_COST_TYPES["generic"]
            )
            return list(set(possible_costs))  # Use set to remove duplicates.

    # Default fallback to generic costs if no specific category is found.
    return COMMODITY_COST_TYPES["generic"]


def get_random_commodity_and_unit(selected_types: Optional[list[str]] = None) -> tuple[str, str, str]:
    """
    Selects a random commodity and a matching, appropriate unit and cost type for it.

    Returns:
        A tuple containing the commodity name, its unit, and an associated cost type.
    """
    # 1. Pick a random commodity from the flattened list, if we don't have selected types
    commodity_name = "commodity"
    if not selected_types or len(selected_types) == 0:
        commodity_name = random.choice(commodities)
    else:
        # Filter out any empty strings from the list before choosing
        valid_types = [t for t in selected_types if t]
        if valid_types:
            types_to_pick_from = random.choice(valid_types)
        else: # If the list is empty or only contained empty strings, fall back to generic
            types_to_pick_from = "generic"
        # Now pick a random one for that type
        commodities_for_type = COMMODITIES.get(types_to_pick_from, [])
        if commodities_for_type:
            commodity_name = random.choice(commodities_for_type)
        else: # Fallback if the selected type has no commodities
            commodity_name = random.choice(commodities)

    # 2. Get the list of appropriate units for that commodity
    appropriate_units = get_units_for_commodity(commodity_name)
    unit = random.choice(appropriate_units)

    # 3. Get the list of appropriate cost types and pick one.
    possible_costs = get_cost_types_for_commodity(commodity_name)
    cost_type = random.choice(possible_costs) if possible_costs else "purchase"

    return commodity_name, unit, cost_type


@dataclass
class CPContextSentence:
    """Generates contextual sentences about commodity exposure without mentioning derivatives."""

    company_name: str
    reporting_year: int
    reporting_month: str
    reporting_day: int
    hedged_item: Optional[CommodityHedgedItem]
    prefer_abbreviated: bool
    currency_symbol: str

    def build(self) -> str:
        """Builds a single contextual sentence for CP."""
        # This method is a placeholder for now.
        # The actual implementation will be done in a subsequent step.
        return ""


# =============================================================================
# CP Contextual "Noise" Templates
# Ported from old/template/other.py
# These describe CP-related business activities without mentioning derivatives.
# =============================================================================

cp_context_templates = {
    "exposure": [
        "{company}'s operating results are subject to {risk_term} in the price of {commodities}.",
        "Our primary raw material is {commodity}, and changes in its price can significantly {impact_verb} our {cost_metric}.",
        "{company} is exposed to price {risk_term} for {commodities} used in our production processes.",
        "The market for {commodity} is subject to significant price {risk_term}, which can affect our profitability.",
        "Our {cost_type} costs are directly impacted by the market price of {commodity}.",
    ],
    "procurement": [
        "{company} sources {commodity} from various suppliers to ensure a stable supply chain.",
        "We have long-term supply {supply_agreements} with {company2} and {company3} for the procurement of {commodity}.",
        "The cost of {commodity} purchased from suppliers is a significant component of our {cost_metric}.",
        "Our procurement strategy for {commodity} involves a mix of spot market purchases and long-term contracts.",
        "We rely on a limited number of suppliers for our {commodity} needs, which exposes us to supply chain {risk_term}.",
    ],
    "inventory": [
        "Inventories of {commodity} are stated at the lower of cost or net realizable value, with cost being determined using the {inventory_method} method.",
        "As of {month} {end_day}, {year}, our inventory of {commodity} was valued at {amount_str}.",
        "We maintain a {small_int}-day supply of {commodity} to support our production schedule.",
        "The value of our {commodity} inventory {impact_verb_past} by {amount_str} during {year} due to price {risk_term} in the market.",
        "Write-downs of {commodity} inventory to net realizable value totaled {amount_str} in {year}.",
    ],
    "impact": [
        "An increase of {pct}% in the price of {commodity} would have {impact_adverb} impacted our {income_statement_item} by approximately {amount_str} in {year}.",
        "Changes in {commodity} prices {impact_adverb} affected our {cost_metric} by {pct}% during the last fiscal quarter.",
        "Our {cost_metric} {impact_verb_past} by {amount_str} in {year}, primarily due to higher {commodity} prices.",
        "The {strength_weakness} of {commodity} prices had an {impact_adjective} impact on our operating results for {year}.",
        "We estimate that a {pct}% change in the average price of {commodity} would result in a {amount_str} change in annual {income_statement_item}.",
    ],
}
