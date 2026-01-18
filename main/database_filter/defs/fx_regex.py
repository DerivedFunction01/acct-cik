import re
from typing import List, Tuple
from defs.derivatives_core import build_smart_regex, expand_instruments, suffix_alternation
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION, build_currency_descriptor_pattern, all_currencies


def build_fx_dynamic_pattern() -> str:
    """
    Dynamically build comprehensive FX patterns with optional positions.

    This generates a single alternation pattern that covers almost all descriptive
    FX prefix combinations, allowing the external build_alternation function
    to sort them by length (Max Munch) automatically.
    """
    # Note: These components are simple alternations (no Max Munch needed here)
    word1 = build_alternation([r"forward", r"foreign"], sort_longest_first=True)
    compound = build_alternation(
        [r"cross[- ]currency", r"multi[- ]currency"], sort_longest_first=True
    )
    word2_alt = build_alternation([r"currency", r"exchange"], sort_longest_first=True)
    word3 = r"rate"

    # List all necessary descriptive fragments/combinations
    patterns = [
        # Longest and most specific combinations
        rf"(?:{word1})[- ](?:{word1})[- ](?:{compound})[- ](?:{word2_alt})[- ]{word3}",  # forward foreign cross currency exchange rate
        rf"(?:{word1})[- ](?:{word1})[- ](?:{word2_alt})[- ]{word3}",  # forward foreign exchange rate
        # Shorter, common combinations
        rf"(?:{word1})[- ](?:{word2_alt})[- ]{word3}",  # forward/foreign currency/exchange rate
        rf"(?:{compound})[- ](?:{word2_alt})[- ]{word3}",  # cross currency exchange rate
        rf"(?:{word1})[- ](?:{word1})[- ](?:{word2_alt})",  # forward foreign exchange/currency
        rf"(?:{compound})[- ](?:{word2_alt})",  # cross currency exchange
        # Two-word descriptive terms
        rf"(?:{word1})[- ](?:{word2_alt})",  # forward exchange, foreign currency
        rf"(?:{compound})",  # cross currency
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


def build_fx_regex() -> Tuple[re.Pattern, re.Pattern]:
    # --- 1. Helper Definitions ---
    currency_name_alternation = build_currency_descriptor_pattern()
    fx_dynamic_pattern = build_fx_dynamic_pattern()

    # --- 2. Build Core Terms (Prefixes) ---
    # Precise prefixes (e.g., 'forward foreign currency')
    strict_core_terms = [
        rf"(?:{fx_dynamic_pattern})",
        r"cross[- ]currency\s+interest\s+rate",
        r"cross[- ]currency\s+interest",
    ]
    # Broad prefixes (e.g., 'currency', 'fx')
    soft_core_terms = [
        r"foreign\s+exchange",
        r"(?<!single[- ])currency",
        r"fx",
        r"forex",
    ]
    soft_core_alternation = build_alternation(soft_core_terms, sort_longest_first=True)

    forward_types = [
        "non[- ]deliverable",
        "deliverable",
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
        rf"(?<!single[- ])currency[- ](?:__DYNAMIC__)",
    ]

    # Fixed (non-dynamic) specific phrases
    fixed_phrases = [
        # Explicitly safe Forward Types
        rf"(?:{forward_types_alternation})\s+(?:forwards?|options?)\s+(?:{suffix_alternation})",
        rf"(?:{forward_types_alternation})\s+(?:forwards?|options?)",
    ]

    # -------------------------------------------------------------------------
    # --- B. STRICT Pattern Construction (High Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for dynamic replacement: safe bases only (no suffixes as standalones, but include safe ones)
    strict_dynamic_fragment = expand_instruments(
        unsafe=False,
        exclude_standalone_suffixes=True,
        additional_standalone_suffixes=["contracts?", "options?", "forwards?"],
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
    strict_instrument_fragment = expand_instruments(
        unsafe=False
    )  # Safe standalone bases allowed here
    strict_pattern = build_smart_regex(
        strict_core_terms,  # Precise prefixes
        strict_instrument_fragment,  # Safe bases only
        strict_specific_phrases,  # Final list of specific phrases
    )
    strict_fx_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # --- C. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for dynamic replacement: includes all instrument bases (unsafe=True, exclude standalones)
    soft_dynamic_fragment = expand_instruments(
        unsafe=True,
        exclude_standalone_suffixes=True,
        additional_standalone_suffixes=["contracts?", "options?", "forwards?"],
    )

    # 1. Substitute the dynamic fragment into the templates
    soft_dynamic_phrases = _replace_dynamic_placeholder(
        dynamic_templates, soft_dynamic_fragment
    )

    # 2. Combine and sort all specific phrases
    soft_specific_phrases = sorted(
        soft_dynamic_phrases + fixed_phrases,
        key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:")),
    )

    # 3. Final pattern build
    soft_instrument_fragment = expand_instruments(
        unsafe=True
    )  # Unsafe standalone bases allowed here
    soft_pattern = build_smart_regex(
        [soft_core_alternation],  # Broad prefixes
        soft_instrument_fragment,  # Unsafe bases included
        soft_specific_phrases,  # Final list of specific phrases
    )
    soft_fx_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)

    # Return the tuple of (strict, soft)
    return strict_fx_regex, soft_fx_regex


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


def build_fx_context_terms_advanced() -> Tuple[List[str], List[str]]:
    """Generate comprehensive FX context terms combining currency-specific and generic patterns."""

    # 1. Get patterns dynamically generated from Currency objects
    currency_specific_terms = build_currency_patterns()

    # 2. Define static generic FX terms
    strict_fx_terms = [
        rf"exchange\s+rate\s+{_RISK_ALTERNATION}",
        rf"foreign\s+interest[- ]rate\s+{_RISK_ALTERNATION}",
        rf"currenc(?:y|ies)\s+{_RISK_ALTERNATION}",
        rf"foreign\s+(?:currency|exchange)\s+{_RISK_ALTERNATION}",
        rf"currency\s+{_RISK_ALTERNATION}",
        # Transactional Context
        r"cross[- ]border",
        r"repatriation",
        r"intercompany",  # Strong signal for FX swaps
        r"denominated\s+in",
        # Specific FX Instruments Keywords
        r"spot\s+rate",
        r"non[- ]deliverable",
        rf"foreign\s+{_DEBT_TERMS}",
        rf"foreign\s+currency\s+{_DEBT_TERMS}",
        # 1. Catch "Euro-denominated debt"
        rf"(?:[a-z]+[- ])?denominated\s+{_DEBT_TERMS}",
        # 2. Catch "Debt denominated in..." (CRITICAL for preventing IR false positives)
        rf"{_DEBT_TERMS}\s+denominated\s+(?:in|by)",
        r"cross[- ]currency",
    ]

    soft_fx_terms = [
        r"translations?",  # Be careful, "translation of documents" exists, but usually accounting
        r"foreign\s+(?:currenc(?:y|ies)|exchanges?|operations?|subsidiar(?:y|ies)|sales?|revenues?)",
        # 1. Operations & Accounting
        r"(?:functional|reporting|local|foreign)\s+currenc(?:y|ies)",
        r"remeasurements?",
        r"(?:currency|foreign)\s+exchanges?",
        r"exchange\s+rates?",
        r"translation\s+adjustments?",
        r"foreign\s+interest\s+rates?",
        r"currenc(?:y|ies)\s+exchange\s+rates?",
        r"remeasurement\s+(?:gain|loss)",
        r"(?:forward|foreign|currency)\s+exchanges?",
        r"hedges?\s+of\s+(?:the\s+)?net\s+investments?",
        r"net\s+investment\s+hedges?",
    ] + currency_specific_terms

    return strict_fx_terms, soft_fx_terms

FX_STRICT_TERMS, FX_SOFT_TERMS = build_fx_context_terms_advanced()
FX_CONTEXT_TERMS = FX_STRICT_TERMS + FX_SOFT_TERMS
FX_CONTEXT_REGEX = build_regex(FX_CONTEXT_TERMS)
FX_STRICT_CONTEXT_REGEX = build_regex(FX_STRICT_TERMS)
FX_REGEX, FX_SOFT_REGEX = build_fx_regex()
