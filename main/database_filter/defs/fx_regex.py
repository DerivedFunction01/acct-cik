import re
from typing import List, Tuple
from defs.derivatives_core import (
    BASE,
    DERIVATIVES,
    DerivativeGenerator,
    Groups,
    MULTI_BASE,
    SUFFIX,
)
from defs.regex_lib import add_restrictions, build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION, build_currency_descriptor_pattern, all_currencies, build_risk_managment_phrase


CURRENCY_TERM = add_restrictions("currency", lookbehinds=["single", "crypto", "digital", "virtual"])
EXCHANGE_TERM = add_restrictions("exchange", lookbehinds=["interest"])

def build_fx_dynamic_pattern() -> List[str]:
    """
    Dynamically build comprehensive FX patterns with optional positions.

    This generates a single alternation pattern that covers almost all descriptive
    FX prefix combinations, allowing the external build_alternation function
    to sort them by length (Max Munch) automatically.
    """
    # Note: These components are simple alternations (no Max Munch needed here)
    word1 = build_alternation([r"forward", r"foreign", r"currency"], sort_longest_first=True)
    compound = build_alternation(
        [
            r"(?:cross|multi)[- ]currency(?:\s+interest[- ]rate)?",
            rf"(?:{EXCHANGE_TERM}|{CURRENCY_TERM})[- ]rate",
        ],
        sort_longest_first=True,
    )
    word2_alt = build_alternation(
        [
            rf"(?:{CURRENCY_TERM}|{EXCHANGE_TERM})(?:[- ]rate)?",
        ],
        sort_longest_first=True,
    )

    # List all necessary descriptive fragments/combinations
    patterns = [
        # Longest and most specific combinations
        rf"(?:{word1})[- ](?:{word1})[- ](?:{compound})[- ](?:{word2_alt})",  # forward foreign cross currency exchange rate?
        rf"(?:{word1})[- ](?:{word1})[- ](?:{word2_alt})",  # forward foreign exchange rate?
        # Shorter, common combinations
        rf"(?:{word1})[- ](?:{word2_alt})",  # forward/foreign/currency currency/exchange rate
        rf"(?:{compound})[- ](?:{word2_alt})",  # cross currency exchange rate
        rf"(?:{word1})[- ](?:{word1})[- ](?:{word2_alt})",  # forward foreign/currency exchange/currency
        rf"(?:{compound})[- ](?:{word2_alt})",  # cross currency exchange exchange
        rf"(?:{word2_alt})[- ](?:{word2_alt})",  # exchange currency, currency exchange
        # Two-word descriptive terms
        rf"(?:{word1})[- ](?:{word2_alt})",  # forward exchange, foreign currency, currency exchange rate, forward currency
        rf"(?:{compound})",  # cross currency, ccirs, exchange rate, currency rate
        # Single-word descriptive terms (low priority, included for completeness)
        r"FX",
        r"forex",
        add_restrictions(r"forward[- ]rates?", lookaheads=[r"agreements?"]),
    ]

    # CRITICAL: We let build_alternation sort this entire list by length/word count
    # to enforce Max Munch, ensuring "forward foreign currency" matches before "forward".
    return patterns


def build_fx_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    # --- 1. Helper Definitions ---
    currency_name_alternation = build_currency_descriptor_pattern()

    forward_types = [
        "non[- ]deliverable",
        "deal[- ]contingent",
    ]

    # --- 1. Define Prefixes ---
    fx_prefixes = build_fx_dynamic_pattern()
    currency_name_prefixes = [currency_name_alternation]
    naked_prefixes = [CURRENCY_TERM] # Weak prefix ("currency")

    all_prefixes = fx_prefixes + naked_prefixes + currency_name_prefixes

    # --- 2. Specific Phrases ---
    fixed_phrases = [
        r"(?<!to\s)hedges?\s+of\s+(?:the\s+)?net\s+investments?(?!\s+(?:in|for|to))",
        r"net\s+investment\s+hedges?",
    ]

    # Forward types (non-deliverable, etc.) + Forward/Option
    # These are specific enough to be strict
    # Nonderivatible forward, non deliverable option
    _FWD_CONFIG = DERIVATIVES(
        PREFIX=forward_types,
        _BASES=[BASE.FORWARD, BASE.OPTION, BASE.SWAP],
        _AMB_BASES=[],
        ADDITIONAL_BASES=[],
        MULTI_BASE=[],
    )
    _FWD_PATTERN = DerivativeGenerator(config=_FWD_CONFIG).generate()

    _CURR_NAME_CONFIG = DERIVATIVES(
        PREFIX=currency_name_prefixes,
        STANDALONE_BASES=[BASE.OPTION],
        MULTI_BASE=[],
    )
    _CURR_NAME_PATTERN = DerivativeGenerator(config=_CURR_NAME_CONFIG).generate()
    # --- 3. Strict Generator ---
    # Option is strict in FX context (Foreign Exchange Option)
    # Split into Strong (allows Agreements) and Weak (allows only Contracts)
    _STRICT_CONFIG_STRONG = DERIVATIVES(
        PREFIX=fx_prefixes,
        STANDALONE_BASES=[BASE.OPTION, BASE.CAP, BASE.PUT, BASE.CALL, BASE.LOCK, BASE.FLOOR],
        STANDALONE_SUFFIXES=Groups.AMBIGUOUS_SUFFIXES + Groups.UNAMBIGUOUS_SUFFIXES,
        ADDITIONAL_BASES=[],
        MULTI_BASE=[], # Add separately to avoid redundancy/complexity in one regex
    )
    _STRICT_MAIN_STRONG = DerivativeGenerator(config=_STRICT_CONFIG_STRONG).generate()

    # Barebones "currency" -> Currency contract, currency option, currency swap
    _STRICT_CONFIG_WEAK = DERIVATIVES(
        PREFIX=naked_prefixes,
        STANDALONE_BASES=[BASE.OPTION, BASE.CAP, BASE.PUT, BASE.CALL, BASE.LOCK, BASE.FLOOR, BASE.HEDGE],
        ADDITIONAL_BASES=[],
        STANDALONE_SUFFIXES=Groups.UNAMBIGUOUS_SUFFIXES,
        MULTI_BASE=[],
    )
    _STRICT_MAIN_WEAK = DerivativeGenerator(config=_STRICT_CONFIG_WEAK).generate()

    # Multi-Base (Caps and Floors, etc.) attached to prefixes
    _MULTI_CONFIG = DERIVATIVES(
        PREFIX=all_prefixes,
        _BASES=[],
        _AMB_BASES=[],
        ADDITIONAL_BASES=[],
        SUFFIXES=[],
        MULTI_BASE=[MULTI_BASE.DOUBLE_BASE]
    )
    _STRICT_MULTI = DerivativeGenerator(config=_MULTI_CONFIG).generate()

    strict_fx_regex = build_regex([_STRICT_MAIN_STRONG, _STRICT_MAIN_WEAK, _STRICT_MULTI, _CURR_NAME_PATTERN, _FWD_PATTERN] + fixed_phrases)

    # --- 4. Soft Generator ---
    # Allows ambiguous bases (Caps, Floors) and Hedges
    _SOFT_CONFIG_STRONG = DERIVATIVES(
        PREFIX=fx_prefixes,
        ADDITIONAL_BASES=[],
        STANDALONE_BASES=Groups.AMBIGUOUS_BASES,
        MULTI_BASE=[],
        STANDALONE_SUFFIXES=Groups.UNAMBIGUOUS_SUFFIXES + Groups.AMBIGUOUS_SUFFIXES
    )
    _SOFT_MAIN_STRONG = DerivativeGenerator(config=_SOFT_CONFIG_STRONG).generate()

    # Bare Currency agreement, currency hedges, currency contracts, etc
    _SOFT_CONFIG_WEAK = DERIVATIVES(
        PREFIX=naked_prefixes,
        ADDITIONAL_BASES=[],
        STANDALONE_BASES=Groups.AMBIGUOUS_BASES,
        MULTI_BASE=[],
        STANDALONE_SUFFIXES=Groups.UNAMBIGUOUS_SUFFIXES + Groups.AMBIGUOUS_SUFFIXES,
    )
    _SOFT_MAIN_WEAK = DerivativeGenerator(config=_SOFT_CONFIG_WEAK).generate()

    soft_fx_regex = build_regex([_SOFT_MAIN_STRONG, _SOFT_MAIN_WEAK, _STRICT_MULTI, _CURR_NAME_PATTERN, _FWD_PATTERN] + fixed_phrases)

    # --- 5. Loose Generator ---
    _LOOSE_CONFIG = DERIVATIVES(PREFIX=all_prefixes, ADDITIONAL_BASES=[], LOOSE=True)
    _LOOSE_MAIN = DerivativeGenerator(config=_LOOSE_CONFIG).generate()
    loose_fx_regex = build_regex([_LOOSE_MAIN] + fixed_phrases)

    return strict_fx_regex, soft_fx_regex, loose_fx_regex


def build_currency_patterns() -> List[str]:
    """
    Generates regex patterns derived specifically from the Currency class objects.
    Includes codes, adjectives, locations, and specific denominating phrases.
    """
    terms = []
    for currency in all_currencies:
        # Basic terms
        terms.append(currency.code)
        terms.append(re.escape(currency.adjective))
        terms.append(re.escape(currency.location))

        # Currency name patterns
        # "U.S. Dollar", "Euro", "Japanese Yen"
        terms.append(re.escape(currency.full_name))

        # Adjective + common words
        adj_esc = re.escape(currency.adjective)
        phrases = [
            r"operations?",
            r"subsidiar(?:y|ies)",
            r"sales?",
            r"revenues?",
            r"income",
            r"earnings",
            r"assets?",
            r"entit(?:y|ies)",
            r"liabilit(?:y|ies)",
            r"markets?",
            r"econom(?:y|ies)",
            r"busine(?:ss|sses)",
            rf"{_RISK_ALTERNATION}",
        ]
        full_phrase = rf"{adj_esc}[- ]{build_alternation(phrases, sort_longest_first=True)}"
        terms.append(full_phrase)

        # Code + patterns
        code = currency.code
        terms.extend(
            [
                code + r"[- ]denominated",
                code + r"[/]" + r"[A-Z]{3}",  # USD/EUR, GBP/JPY
                r"[A-Z]{3}" + r"[/]" + code,  # EUR/USD, JPY/GBP
            ]
        )
    terms.extend(["foreign[- ]denominated"])
    return terms


def build_fx_context_terms_advanced() -> Tuple[List[str], List[str], List[str]]:
    """Generate comprehensive FX context terms combining currency-specific and generic patterns."""

    # 1. Get patterns dynamically generated from Currency objects
    currency_specific_terms = build_currency_patterns()

    # Shared FX Terms
    fx_core = [
        r"(?:foreign|forward|currency|cross[- ]currency)\s+exchange",
        r"exchange\s+rates?",
        r"forex",
        r"fx",
        r"foreign\s+(?:sales?|revenues?|costs?|expenses?|earnings?|income)",
    ]

    fx_accounting = [
        r"translations?",
        r"remeasurements?",
        r"(?:functional|reporting|local|foreign)\s+currenc(?:y|ies)",
        r"net\s+investments?",
        r"foreign\s+(?:operations?|subsidiar(?:y|ies))",
    ]

    fx_transaction = [
        r"cross[- ]border",
        r"repatriation",
        r"intercompany",
        r"denominated",
        r"non[- ]deliverable",
        r"spot\s+rates?",
        r"cross[- ]currency",
    ]

    fx_risk = [
        rf"exchange\s+rate\s+{_RISK_ALTERNATION}",
        rf"foreign\s+interest[- ]rate\s+{_RISK_ALTERNATION}",
        rf"{CURRENCY_TERM}\s+{_RISK_ALTERNATION}",
        rf"foreign\s+(?:currency|exchange)\s+{_RISK_ALTERNATION}",
    ]

    fx_debt = [
        rf"foreign\s+{_DEBT_TERMS}",
        rf"foreign\s+currency\s+{_DEBT_TERMS}",
        rf"(?:[a-z]+[- ])?denominated\s+{_DEBT_TERMS}",
        rf"{_DEBT_TERMS}\s+denominated\s+(?:in|by)",
        rf"denominated\s+in",
        r"foreign\s+interest\s+rates?",
    ]

    # 2. Define static generic FX terms
    strict_fx_terms = fx_risk + fx_debt + fx_transaction

    soft_fx_terms = fx_core + fx_accounting + currency_specific_terms + strict_fx_terms

    fx_glue = fx_core + fx_accounting + fx_transaction

    for curr in all_currencies:
        fx_glue.append(re.escape(curr.code))
        fx_glue.append(re.escape(curr.adjective))
        fx_glue.append(re.escape(curr.full_name))

    risk_terms = [build_risk_managment_phrase(fx_glue)]

    return strict_fx_terms, soft_fx_terms, risk_terms

FX_STRICT_TERMS, FX_SOFT_TERMS, FX_RISK_TERMS = build_fx_context_terms_advanced()
FX_CONTEXT_TERMS = FX_STRICT_TERMS + FX_SOFT_TERMS + FX_RISK_TERMS
FX_CONTEXT_REGEX = build_regex(FX_CONTEXT_TERMS)
FX_STRICT_CONTEXT_REGEX = build_regex(FX_STRICT_TERMS + FX_RISK_TERMS)
FX_RISK_REGEX = build_regex(FX_RISK_TERMS)
FX_REGEX, FX_SOFT_REGEX, FX_LOOSE_REGEX = build_fx_regex()
from defs.verb_core import build_strict_do_not_mitigate_regex

FX_DO_NOT_MITIGATE_REGEX = build_strict_do_not_mitigate_regex(
    [
        r"(?:foreign|cross|multi)[- ]currency",
        CURRENCY_TERM,
        r"exchange\s+rates?",
        r"(?:foreign|forward|currency|cross[- ]currency)\s+exchange",
        r"fx",
        r"forex",
    ]
)


def run_tests():
    from defs.derivatives_core import (
        MatchLevel,
        run_category_tests,
        run_category_tests_counter,
    )

    test_cases = [
        ("foreign currency forward", MatchLevel.STRICT),
        ("foreign currency exchange rate contract", MatchLevel.STRICT),
        ("currency contract", MatchLevel.STRICT),
        ("currency cap agreement", MatchLevel.STRICT),
        ("FX forward", MatchLevel.STRICT),
        ("crypto currency swaps", MatchLevel.NONE),
        ("vitrual currency contract", MatchLevel.NONE),
        (
            "foreign exchange option",
            MatchLevel.STRICT,
        ),  # Option is explicitly added as safe suffix
        ("cross currency swap", MatchLevel.STRICT),
        ("forward foreign exchange contract", MatchLevel.STRICT),
        ("currency agreement", MatchLevel.SOFT),
        ("foreign currency contract", MatchLevel.STRICT),
        ("foreign currency hedges", MatchLevel.SOFT),
        ("currency hedging", MatchLevel.SOFT),
        ("foreign currency option", MatchLevel.STRICT),
        ("currency option", MatchLevel.STRICT),
        ("currency exchange rate arrangement", MatchLevel.STRICT),
        ("currency exchange agreement", MatchLevel.STRICT),
        ("foreign currency exchange swap", MatchLevel.STRICT),
        ("exchange rate contract", MatchLevel.STRICT),
        ("Japanese Yen option", MatchLevel.STRICT),
        ("Euro forward", MatchLevel.STRICT),
        ("exchange rate agreement", MatchLevel.STRICT),
        ("exchange rate hedge", MatchLevel.SOFT),
        ("foreign currency commitment", MatchLevel.LOOSE),
        ("currency transaction", MatchLevel.LOOSE),
        (
            "Japanese Yen contract",
            MatchLevel.LOOSE,
        ),  # Only options along with other bases
        ("currency assets", MatchLevel.LOOSE),
        ("foreign currency liability", MatchLevel.LOOSE),
        ("forward rate agreement (IR)", MatchLevel.NONE),
        ("forward rate contract", MatchLevel.STRICT),
        ("forward rate option", MatchLevel.STRICT),
        ("foreign exchange agreement", MatchLevel.STRICT),
        ("foreign exchange rate contract", MatchLevel.STRICT),
        ("single-currency contract (IR)", MatchLevel.NONE),
        ("currency rate contract", MatchLevel.STRICT),
        ("foreign exchange derivative", MatchLevel.STRICT),
        ("foreign exchange rate derivative", MatchLevel.STRICT),
        ("foreign exchange instrument", MatchLevel.STRICT),
        ("currency instrument", MatchLevel.STRICT),
        ("foreign exchange forward", MatchLevel.STRICT),
        ("foreign exchange rate forward", MatchLevel.STRICT),
        ("currency forward", MatchLevel.STRICT),
        ("foreign exchange futures", MatchLevel.STRICT),
        ("currency futures", MatchLevel.STRICT),
        ("currency rate put options", MatchLevel.STRICT),
        ("foreign exchange swap", MatchLevel.STRICT),
        ("foreign exchange rate swap", MatchLevel.STRICT),
        ("currency rate swap", MatchLevel.STRICT),
        ("currency swap", MatchLevel.STRICT),
        ("foreign exchange option", MatchLevel.STRICT),
        ("currency option", MatchLevel.STRICT),
        ("foreign exchange cap", MatchLevel.STRICT),
        ("currency cap", MatchLevel.STRICT),
        ("foreign exchange rate put", MatchLevel.STRICT),
        ("crypto currency floor", MatchLevel.NONE),
        ("virtual currency forward", MatchLevel.NONE),
        ("foreign exchange collar", MatchLevel.STRICT),
        ("foreign exchange rate collar", MatchLevel.STRICT),
        ("digital currency collar", MatchLevel.NONE),
    ]
    print("FX Derivatives tests:")
    run_category_tests(test_cases, FX_REGEX, FX_SOFT_REGEX, FX_LOOSE_REGEX)

    counter_cases = [
        ("foreign currency commitments", MatchLevel.SOFT),
        ("digital currency swaps", MatchLevel.SOFT),
        ("currency rate", MatchLevel.LOOSE),
        ("exchange rate", MatchLevel.LOOSE),
        ("cap contract", MatchLevel.LOOSE),
        ("foreign currency transaction", MatchLevel.SOFT), # Transaction is not a derivative suffix
    ]
    run_category_tests_counter(counter_cases, FX_REGEX, FX_SOFT_REGEX, FX_LOOSE_REGEX)
