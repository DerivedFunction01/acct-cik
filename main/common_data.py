from class_definitions import Currency

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

volume_units = [
    # Energy
    "barrels",
    "bbl",  # crude oil
    "barrels per day",
    "bbl/d",  # production rate
    "MMBtu",
    "MMBtu/h",  # natural gas, energy content
    "BTU",
    "Btu",  # single BTU
    "gigajoules",
    "GJ",  # energy content
    "MWh",
    "megawatt-hour",  # electricity
    # Bulk solids / metals / minerals
    "metric tons",
    "tonne",
    "MT",  # general bulk
    "tons",
    "t",  # alternative
    "long tons",
    "LT",
    "short tons",
    "ST",
    "hundredweights",
    "cwt",
    "pounds",
    "lb",
    "ounces",
    "oz",  # troy ounces for metals
    # Agriculture
    "bushels",
    "bu",
    "sacks",
    "bales",
    "pecks",
    # Liquids
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
    # Lumber / construction materials
    "board foot",
    "bf",
    "sheets",
    "coils",
    "bundles",
    "pallets",
]
