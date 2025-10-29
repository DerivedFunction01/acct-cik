money_unit_list = ["thousand", "million", "billion", ""]
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
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

quarters = ["first", "second", "third", "fourth", "last", "1st", "2nd", "3rd", "4th"]
# Currency codes for international flavor
currency_codes = [
    "$",
    "USD ",
    "€",
    "EUR ",
    "£",
    "GBP ",
    "¥",
    "JPY ",
    "CHF ",  # Swiss Franc
    "CNY ",  # Chinese Yuan
    "HKD ",  # Hong Kong Dollar
    "SGD ",  # Singapore Dollar
    "CAD ",  # Canadian Dollar
    "AUD ",  # Australian Dollar
    "NZD ",  # New Zealand Dollar
    "SEK ",  # Swedish Krona
    "NOK ",  # Norwegian Krone
    "DKK ",  # Danish Krone
    "ZAR ",  # South African Rand
    "BRL ",  # Brazilian Real
    "MXN ",  # Mexican Peso
    "INR ",  # Indian Rupee
    "KRW ",  # South Korean Won
    "TRY ",  # Turkish Lira
]
currency_pairs = [
    # Major USD crosses
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "USD/CAD",
    "AUD/USD",
    "NZD/USD",
    "USD/CNY",
    "USD/HKD",
    "USD/SGD",
    "USD/INR",
    "USD/KRW",
    "USD/MXN",
    "USD/BRL",
    "USD/TRY",
    "USD/ZAR",
    # Euro crosses
    "EUR/GBP",
    "EUR/JPY",
    "EUR/CHF",
    "EUR/CAD",
    "EUR/AUD",
    "EUR/NZD",
    "EUR/SEK",
    "EUR/NOK",
    "EUR/DKK",
    "EUR/PLN",
    "EUR/HUF",
    "EUR/CZK",
    # Asia-Pacific crosses
    "AUD/JPY",
    "AUD/NZD",
    "AUD/CAD",
    "NZD/JPY",
    "SGD/JPY",
    "CNY/JPY",
    # Pound crosses
    "GBP/JPY",
    "GBP/CHF",
    "GBP/CAD",
    "GBP/AUD",
    "GBP/NZD",
]


major_currencies = [
    "the Euro",
    "the British pound",
    "the Swiss franc",
    "the Japanese yen",
    "the Canadian dollar",
    "the Australian dollar",
    "the Chinese yuan",
    "the U.S. Dollar",
]

european_currencies = [
    "the Euro",
    "the British pound",
    "the Swiss franc",
    "the Norwegian krone",
    "the Swedish krona",
    "the Polish zloty",
    "the Czech koruna",
    "the Hungarian forint",
]

asian_currencies = [
    "the Japanese yen",
    "the Chinese yuan",
    "the Indian rupee",
    "the South Korean won",
    "the Singapore dollar",
    "the Thai baht",
    "the Malaysian ringgit",
]

americas_currencies = [
    "the Canadian dollar",
    "the Mexican peso",
    "the Brazilian real",
    "the Argentine peso",
    "the Chilean peso",
    "the Colombian peso",
]
all_currencies = (
    set(major_currencies)
    | set(european_currencies)
    | set(asian_currencies)
    | set(americas_currencies)
)
all_currencies = list(all_currencies)
frequencies = [
    "quarterly",
    "on a regular basis",
    "at least quarterly",
    "monthly",
    "periodically",    
    "annually",
]
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
    # Precious stones / metals
    "carats",
    "ingots",
    "bars",
    # Lumber / construction materials
    "board foot",
    "bf",
    "sheets",
    "coils",
    "bundles",
    "pallets",
    # Land / area (sometimes in agricultural contracts)
    "acres",
    "hectares",
    "square meters",
    "square feet",
    # Countable units for livestock or manufactured goods
    "units",
    "head",
    "crates",
    "boxes",
    "cartons",
    "totes",
    "drums",
    "rolls",
    "loaves",
]


balance_sheet_locations = [
    "other income (expense), net",
    "other comprehensive income",
    "earnings",
    "the consolidated statements of operations",
    "statement of operations",    
    "the consolidated balance sheets",
    "the consolidated statements of cash flows",
    
]

geographies = [
    "North America, Europe, and Asia",
    "over 50 countries worldwide",
    "the United States and international markets",
    "global markets",
    "developed and emerging markets",    
    "the United States, Canada, and Mexico",
    "Europe, the Middle East, and Africa (EMEA)",
    "Asia-Pacific (APAC) region",
    "Latin America",
    "North America",
    "South America",
    "Europe",
    "Asia",
    "Africa",
    "Australia",
    "Oceania",
    "the United States",
    "Canada",
    "Mexico",
    "Brazil",
    "Argentina",
    "the United Kingdom",
    "Germany",
    "France",
    "Italy",
    "Spain",
    "China",
    "India",
    "Japan",
    "South Korea",
    "Australia",
    "New Zealand",
    "Southeast Asia",
    "the Nordic countries",
    "Eastern Europe",
    "Western Europe",
    "Central America",
    "the Caribbean",
    "the Middle East",
    "North Africa",
    "Sub-Saharan Africa",
    "Russia and CIS countries",
    "the European Union",
    "the Eurozone",
    "the ASEAN region",
]

cities = [
    "San Francisco",
    "New York",
    "Boston",
    "Chicago",
    "Austin",
    "Seattle",
    "Atlanta",    
    "Houston",
    "Dallas",
    "Los Angeles",
    "Philadelphia",
    "Phoenix",
    "San Antonio",
    "San Diego",
    "Denver",
    "Portland",
    "Las Vegas",
    "Miami",
    "Orlando",
    "Detroit",
    "Minneapolis",
    "St. Louis",
    "Charlotte",
    "Raleigh",
    "Nashville",
    "Kansas City",
    "New Orleans",
    "Salt Lake City",
    "Albuquerque",
    "Richmond",
    "Baltimore",
    "Cleveland",
    "Columbus",
    "Cincinnati",
    "Pittsburgh",
    "Milwaukee",
    "Indianapolis",
    "Louisville",
    "Memphis",
    "Birmingham",
    "Jacksonville",
    "Tampa",
    "Orlando",
    "Fort Lauderdale",
    "West Palm Beach",
    "Sacramento",
    "San Jose",
    "Oakland",
    "Long Beach",
    "Anaheim",
    "Santa Ana",
    "Riverside",
    "Irvine",
    "Stockton",
    "Fremont",
    "Baton Rouge",
    "Shreveport",
    "Lexington",
    "Boise",
    "Omaha",
    "Lincoln",
    "Des Moines",
    "Wichita",
    "Springfield",
    "Little Rock",
    "Honolulu",
    "Anchorage",
    "Burlington",
    "Manchester",
    "Providence",
    "Hartford",
    "New Haven",
    "Stamford",
    "Bridgeport",
    "Augusta",
    "Portland",
    "Concord",
    "Dover",
    "Nashua",
    "Missoula",
    "Billings",
    "Fargo",
    "Sioux Falls",
    "Rapid City",
    "Cheyenne",
    "Casper",
    "Charleston",
    "Columbia",
    "Greenville",
    "Myrtle Beach",
    "Knoxville",
    "Chattanooga",
    "Huntsville",
    "Mobile",
    "Montgomery"
]
states = [
    "California",
    "New York",
    "Massachusetts",
    "Illinois",
    "Texas",
    "Washington",
    "Georgia",    
    "Florida",
    "Pennsylvania",
    "Ohio",
    "Michigan",
    "North Carolina",
    "New Jersey",
    "Virginia",
    "Arizona",
    "Colorado",
    "Maryland",
    "Missouri",
    "Indiana",
    "Tennessee",
    "Wisconsin",
    "Minnesota",
    "Louisiana",
    "Alabama",
    "Kentucky",
    "Oregon",
    "Oklahoma",
    "Connecticut",
    "Iowa",
    "Mississippi",
    "Arkansas",
    "Kansas",
    "Utah",
    "Nevada",
    "New Mexico",
    "Nebraska",
    "West Virginia",
    "Idaho",
    "Hawaii",
    "New Hampshire",
    "Maine",
    "Montana",
    "Rhode Island",
    "Delaware",
    "South Dakota",
    "North Dakota",
    "Alaska",
    "Vermont",
    "Wyoming",
    
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
    "none",
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

current_adverbs = [
    "currently",
    "actively",
    "presently",
    "now",
    "also",
    "primarily",
    "only",
    "",
]

past_adverbs = [
    "in the past",
    ", from time to time, ",
    "periodically",
    "occasionally",
    ", in the future,",
    "",
]

not_adverbs = [
    "does not",
    "will not",
    "does not plan to",
    "does not intend to",
    "has no plans to",
    "will not seek to",
    "can not",
    "could not",
]
