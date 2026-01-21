import re
from typing import List, Tuple
from defs.derivatives_core import SUFFIXES, build_smart_regex, expand_instruments, suffix_alternation
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION, build_currency_descriptor_pattern, all_currencies, build_risk_managment_phrase


def build_fx_dynamic_pattern() -> str:
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
            r"(?:cross|multi)[- ]currency",
            r"cross[- ]currency\s+interest[- ]rate",
            r"(?<!interest[- ])exchange[- ]rate",
        ],
        sort_longest_first=True,
    )
    word2_alt = build_alternation(
        [
            r"(?<!single[- ])currency",
            r"(?<!interest[- ])exchange",
            r"(?<!interest[- ])exchange[- ]rate",
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
        rf"(?:{compound})",  # cross currency, ccirs
        # Single-word descriptive terms (low priority, included for completeness)
        r"FX",
        r"forex",
    ]

    # CRITICAL: We let build_alternation sort this entire list by length/word count
    # to enforce Max Munch, ensuring "forward foreign currency" matches before "forward".
    return build_alternation(patterns, sort_longest_first=True)


def _replace_dynamic_placeholder(
    phrases: List[str], replacement_fragment: str
) -> List[str]:
    """Replaces the '__DYNAMIC__' placeholder in a list of phrase templates."""
    return [p.replace(r"__DYNAMIC__", replacement_fragment) for p in phrases]


def build_fx_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    # --- 1. Helper Definitions ---
    currency_name_alternation = build_currency_descriptor_pattern()
    fx_dynamic_pattern = build_fx_dynamic_pattern()

    forward_types = [
        "non[- ]deliverable",
        "deal[- ]contingent",
    ]
    forward_types_alternation = build_alternation(
        forward_types, sort_longest_first=True
    )

    # -------------------------------------------------------------------------
    # --- A. UNIFIED TEMPLATE PHRASES ---
    # -------------------------------------------------------------------------

    # Templates for phrases that attach instrument bases to currency context
    dynamic_templates = [
        rf"(?:{currency_name_alternation}[- ](?:denominated|linked|related|based))[- ](?:__DYNAMIC__)",
        rf"(?:{currency_name_alternation})[- ](?:__DYNAMIC__)",
        r"(?<!single[- ])currency[- ](?:__DYNAMIC__)", # dynamic currency includes swaps and options, but not contracts, agreements, or instruments
    ]

    # Fixed (non-dynamic) specific phrases
    fixed_phrases = [
        # Explicitly safe Forward Types
        rf"(?:{forward_types_alternation})\s+(?:forwards?|options?)\s+(?:{suffix_alternation})",
        rf"(?:{forward_types_alternation})\s+(?:forwards?|options?)",
        rf"(?<!single[- ])currency\s+contracts?", # currency contracts
    ]

    # -------------------------------------------------------------------------
    # --- B. STRICT Pattern Construction (High Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for dynamic replacement (e.g. "USD-denominated ...")
    # We use exclude_standalone_suffixes=True to strip generic suffixes,
    # then explicitly add back "options" to ensure precision.
    strict_dynamic_fragment = expand_instruments(
        unsafe=False,
        exclude_standalone_suffixes=True,
        additional_standalone_suffixes=["options?"], # only allow options
    )

    loose_dynamic_fragment = expand_instruments(
        unsafe=True,
        exclude_standalone_suffixes=False,
    )

    # 1. Substitute the dynamic fragment into the templates
    strict_dynamic_phrases = _replace_dynamic_placeholder(
        dynamic_templates, strict_dynamic_fragment
    )

    # 2. Combine and sort all specific phrases
    strict_specific_phrases = sorted(
        strict_dynamic_phrases + fixed_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:")),
    )

    # 3. Final pattern build
    # Fragment for Core Terms (e.g. "Foreign Exchange ...")
    # We use unsafe=False (Strict Mode), which includes UNAMBIGUOUS_SUFFIXES (like "contracts") by default.
    # We explicitly add "options" because it is normally ambiguous, but safe in FX context ("Foreign Exchange Option").
    strict_instrument_fragment = expand_instruments(
        unsafe=False, # unsafe bases excluded
        additional_standalone_suffixes=SUFFIXES, # but all the suffixes, due to our compound dynamic phrases
    )
    # --- 2. Build Core Terms (Prefixes) ---
    # Precise prefixes (e.g., 'forward foreign currency')

    strict_pattern = build_smart_regex(
        [fx_dynamic_pattern],  # Precise prefixes
        strict_instrument_fragment,  # Safe bases only
        strict_specific_phrases,  # Final list of specific phrases
    )

    strict_fx_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    # 3. Final pattern build
    soft_instrument_fragment = expand_instruments(
        unsafe=True, 
        additional_standalone_suffixes=["hedges?"]
    )

    soft_pattern = build_smart_regex(
        [fx_dynamic_pattern],  # Broad prefixes
        soft_instrument_fragment,  # Unsafe bases included
        strict_specific_phrases,  # Final list of specific phrases
    )
    soft_fx_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # --- C. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    # 1. Substitute the dynamic fragment into the templates
    loose_dynamic_phrases = _replace_dynamic_placeholder(
        dynamic_templates, loose_dynamic_fragment
    )

    loose_specific_phrases = sorted(
        loose_dynamic_phrases + fixed_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:")),
    )

    loose_instrument_fragment = expand_instruments(
        unsafe=True, exclude_standalone_suffixes=False, full_alternation=True
    )
    loose_pattern = build_smart_regex(
        [fx_dynamic_pattern, r"(?<!single[- ])currency"],
        loose_instrument_fragment,
        loose_specific_phrases,
    )
    loose_fx_regex = re.compile(r"\b" + loose_pattern + r"\b", re.IGNORECASE)

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
        rf"currenc(?:y|ies)\s+{_RISK_ALTERNATION}",
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
        r"foreign\s+currency",
        r"currency",
        r"exchange\s+rates?",
        r"(?:foreign|forward|currency|cross[- ]currency)\s+exchange",
        r"fx",
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
        ("currency swap agreement", MatchLevel.STRICT),
        ("FX forward", MatchLevel.STRICT),
        (
            "foreign exchange option",
            MatchLevel.STRICT,
        ),  # Option is explicitly added as safe suffix
        ("cross currency swap", MatchLevel.STRICT),
        ("forward foreign exchange contract", MatchLevel.STRICT),
        ("currency agreement", MatchLevel.LOOSE),
        ("foreign currency contract", MatchLevel.STRICT),
        ("foreign currency hedges", MatchLevel.SOFT),
        ("currency hedging", MatchLevel.LOOSE),
        ("foreign currency option", MatchLevel.STRICT),
        ("currency option", MatchLevel.STRICT),
        ("currency exchange rate arrangement", MatchLevel.STRICT),
        ("currency exchange agreement", MatchLevel.STRICT),
        ("foreign currency exchange swap", MatchLevel.STRICT),
        ("exchange rate contract", MatchLevel.STRICT),
        ("Japanese Yen option", MatchLevel.STRICT),
        ("exchange rate agreement", MatchLevel.STRICT),
        ("exchange rate hedge", MatchLevel.SOFT),
        ("foreign currency commitment", MatchLevel.LOOSE),
        ("currency transaction", MatchLevel.LOOSE),
        ("Japanese Yen contract", MatchLevel.LOOSE),
    ]
    run_category_tests(test_cases, FX_REGEX, FX_SOFT_REGEX, FX_LOOSE_REGEX)

    counter_cases = [
        ("foreign currency commitments", MatchLevel.SOFT),
        ("currency rate", MatchLevel.STRICT),
        ("exchange rate", MatchLevel.LOOSE),
        
        ("foreign currency transaction", MatchLevel.STRICT), # Transaction is not a derivative suffix
    ]
    run_category_tests_counter(counter_cases, FX_REGEX, FX_SOFT_REGEX, FX_LOOSE_REGEX)
