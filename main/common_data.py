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

months_abbr = [mon for mon in months_full if len(mon) <= 4]
months = months_full + months_abbr
quarters = ["first", "second", "third", "fourth", "last", "1st", "2nd", "3rd", "4th"]
major_currencies = [
    ("USD", "U.S. Dollar", "$", "U.S.", "United States"),
    ("EUR", "Euro", "€", "European", "Europe"),
    ("GBP", "British Pound", "£", "British", "U.K."),
    ("JPY", "Japanese Yen", "¥", "Japanese", "Japan"),
    ("CAD", "Canadian Dollar", "$", "Canadian", "Canada"),
    ("AUD", "Australian Dollar", "$", "Australian", "Australia"),
    ("CHF", "Swiss Franc", "CHF", "Swiss", "Switzerland"),
    ("CNY", "Chinese Yuan", "¥", "Chinese", "China"),
]

european_currencies = [
    ("NOK", "Norwegian Krone", "kr", "Norwegian", "Norway"),
    ("SEK", "Swedish Krona", "kr", "Swedish", "Sweden"),
    ("DKK", "Danish Krone", "kr", "Danish", "Denmark"),
    ("PLN", "Polish Zloty", "zł", "Polish", "Poland"),
    ("HUF", "Hungarian Forint", "Ft", "Hungarian", "Hungary"),
    ("CZK", "Czech Koruna", "Kč", "Czech", "Czech Republic"),
    ("TRY", "Turkish Lira", "₺", "Turkish", "Turkey"),
    ("RUB", "Russian Ruble", "₽", "Russian", "Russia"),
    ("BGN", "Bulgarian Lev", "лв", "Bulgarian", "Bulgaria"),
    ("RON", "Romanian Leu", "lei", "Romanian", "Romania"),
]

asian_currencies = [
    ("INR", "Indian Rupee", "₹", "Indian", "India"),
    ("KRW", "South Korean Won", "₩", "South Korean", "South Korea"),
    ("SGD", "Singapore Dollar", "$", "Singaporean", "Singapore"),
    ("HKD", "Hong Kong Dollar", "$", "Hong Kong", "Hong Kong"),
    ("THB", "Thai Baht", "฿", "Thai", "Thailand"),
    ("MYR", "Malaysian Ringgit", "RM", "Malaysian", "Malaysia"),
]

americas_currencies = [
    ("MXN", "Mexican Peso", "$", "Mexican", "Mexico"),
    ("BRL", "Brazilian Real", "R$", "Brazilian", "Brazil"),
    ("ARS", "Argentine Peso", "$", "Argentine", "Argentina"),
    ("CLP", "Chilean Peso", "$", "Chilean", "Chile"),
    ("COP", "Colombian Peso", "$", "Colombian", "Colombia"),
]

other_currencies = [
    ("NZD", "New Zealand Dollar", "$", "New Zealand", "Oceania"),
    ("ZAR", "South African Rand", "R", "South African", "African"),
    ("AED", "UAE Dirham", "د.إ", "Emirati", "United Arab Emirates"),
    ("SAR", "Saudi Riyal", "ر.س", "Saudi", "Saudi Arabia"),

]

all_currencies = (
    major_currencies
    + european_currencies
    + asian_currencies
    + americas_currencies
    + other_currencies
)
