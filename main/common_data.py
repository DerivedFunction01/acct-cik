from class_definitions import Currency
import random

cost_types = ["input", "extraction", "storage"]
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


COMMODITY_UNITS = {
    "energy": [
        "barrels", "bbl", "barrels per day", "bbl/d", "MMBtu", "MMBtu/h",
        "BTU", "Btu", "gigajoules", "GJ", "MWh", "megawatt-hour",
    ],
    "bulk_solids": [
        "metric tons", "tonne", "MT", "tons", "t", "long tons", "LT",
        "short tons", "ST", "hundredweights", "cwt", "pounds", "lb",
    ],
    "precious_metals": ["ounces", "oz", "carats", "ingots", "bars"],
    "agriculture": ["bushels", "bu", "sacks", "bales", "pecks", "head"],
    "liquids": [
        "gallons", "gal", "liters", "L", "ltr", "cubic meters", "m3",
        "cubic feet", "ft3", "hectoliters", "hL", "kiloliters", "kL",
        "megaliters", "ML", "gigaliters", "GL",
    ],
    "lumber": ["board foot", "bf", "cubic meters", "m3", "cubic feet", "ft3"],
    "manufactured": ["sheets", "coils", "bundles", "pallets", "units"],
}

COMMODITIES = {
    "energy": [
        "crude oil", "diesel fuel", "electricity", "electric", "energy",
        "ethanol", "fuel", "gas", "gasoline", "natural gas", "petroleum",
        "biodiesel", "biomass",
    ],
    "metals_minerals": [
        "aluminum", "base metals", "copper", "iron ore", "limestone", "metals",
        "minerals", "potash", "precious metals", "salt", "sand", "steel",
        "titanium", "uranium", "gravel", "phosphate", "soda ash",
    ],
    "agriculture": [
        "agricultural products", "cocoa", "coffee", "corn", "cotton", "dairy",
        "grain", "livestock", "soybeans", "sugar", "wool", "rubber",
    ],
    "lumber_wood": [
        "hardwood lumber", "logs", "lumber", "plywood", "softwood lumber",
        "timber", "wood", "wood chips", "wood pellets", "pulp", "paper",
    ],
    "chemicals_plastics": [
        "asphalt", "bitumen", "cement", "chemicals", "concrete", "feedstock",
        "fertilizer", "nitrogen", "petrochemicals", "plastics", "polymers",
        "resin", "sulfur",
    ],
    "textiles": ["textiles", "cotton", "wool"],
    "generic": ["commodity", "raw materials"],
}

# Flattened lists for random selection when no category is specified
volume_units = [unit for sublist in COMMODITY_UNITS.values() for unit in sublist]
commodities = [item for sublist in COMMODITIES.values() for item in sublist]


def get_units_for_commodity(commodity_name: str) -> list[str]:
    """
    Returns a list of appropriate volume units for a given commodity.
    """
    # This mapping connects commodity categories to their corresponding unit categories.
    CATEGORY_TO_UNITS_MAP = {
        "energy": ["energy", "liquids"],
        "metals_minerals": ["bulk_solids", "precious_metals"],
        "agriculture": ["agriculture", "bulk_solids"],
        "lumber_wood": ["lumber", "manufactured", "bulk_solids"],
        "chemicals_plastics": ["bulk_solids", "liquids"],
        "textiles": ["agriculture", "manufactured"],
        "generic": list(COMMODITY_UNITS.keys()), # Can be anything
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
            return list(set(units)) # Use set to remove duplicates, then convert back to list.

    # Default fallback
    return volume_units


def get_random_commodity_and_unit() -> tuple[str, str]:
    """
    Selects a random commodity and a matching, appropriate unit for it.

    Returns:
        A tuple containing the commodity name and its unit.
    """
    # 1. Pick a random commodity from the flattened list
    commodity_name = random.choice(commodities)
    # 2. Get the list of appropriate units for that commodity
    appropriate_units = get_units_for_commodity(commodity_name)
    # 3. Pick a random unit from that list
    unit = random.choice(appropriate_units)
    return commodity_name, unit
