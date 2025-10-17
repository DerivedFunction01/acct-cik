money_unit_list = ["thousand", "million", "billion"]
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
]
volume_units = [
    "barrels",
    "MMBtu",
    "MWh",
    "metric tons",
    "bushels",
    "gallons",
    "ton",
    "pound",
    "bushel",
    "board foot",
]
balance_sheet_locations = [
    "other income (expense), net",
    "other comprehensive income",
    "earnings",
    "the consolidated statements of operations",
    "statement of operations",
]

geographies = [
    "North America, Europe, and Asia",
    "over 50 countries worldwide",
    "the United States and international markets",
    "global markets",
    "developed and emerging markets",
]

cities = [
    "San Francisco",
    "New York",
    "Boston",
    "Chicago",
    "Austin",
    "Seattle",
    "Atlanta",
]
states = [
    "California",
    "New York",
    "Massachusetts",
    "Illinois",
    "Texas",
    "Washington",
    "Georgia",
]
