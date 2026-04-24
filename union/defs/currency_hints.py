from defs.regex_lib import build_regex


# Currency hints that can help webpage-level home-country detection without
# polluting the geographic matcher itself.
CURRENCY_COUNTRY_HINTS = [
    (build_regex([r"sterling", r"gbp"]), "GB"),
    (build_regex([r"yen", r"jpy"]), "JP"),
    (build_regex([r"yuan", r"renminbi", r"rmb", r"cny"]), "CN"),
    (build_regex([r"rupee", r"rupees", r"inr"]), "IN"),
    (build_regex([r"dirham", r"dirhams", r"aed"]), "AE"),
    (build_regex([r"riyal", r"riyals", r"sar"]), "SA"),
    (build_regex([r"shekel", r"shekels", r"new shekel", r"ils"]), "IL"),
    (build_regex([r"rand", r"zar"]), "ZA"),
    (build_regex([r"lira", r"liras", r"try"]), "TR"),
    (build_regex([r"ruble", r"rubles", r"rouble", r"roubles", r"rub"]), "RU"),
    (build_regex([r"won", r"krw"]), "KR"),
]
