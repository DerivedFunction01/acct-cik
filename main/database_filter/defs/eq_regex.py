import re
from typing import Tuple

from defs.derivatives_core import build_smart_regex, expand_instruments, suffix_alternation
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import _DEBT_TERMS, _RISK_ALTERNATION, VALUATION_MODELS

def build_eq_regex() -> Tuple[re.Pattern, re.Pattern]:
    # --- 1. Build Core Terms (Prefixes) ---
    liability = r"liabilit(?:y|ies)"
    option = r"options?"
    warrant = r"warrants?"
    derivative = r"derivatives?"
    # Strict Core Terms (Precise market/price references)
    strict_core_terms = [
        r"equity",
        r"equity[- ](?:based|related|linked|index)",
        r"market\s+index",
    ]
    strict_core_alternation = build_alternation(strict_core_terms, True)

    # 2. Build Specific Phrases (Max Munch) - UNIFIED LIST
    # Convertible phrases (Structural Embedded Derivatives)
    convertible_phrases = [
        rf"embedded\s+conversion\s+(?:{option}|features?|{derivative})",
        rf"conversion\s+option\s+{liability}",
        rf"bifurcated\s+conversion\s+{option}",
        rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))\s+(?:hedges?|derivatives?)",
    ]

    # Warrant liabilities (Financial Warrants only)
    warrant_phrases = [
        # Direct warrant + (liability OR derivative)
        rf"{warrant}\s+(?:{derivative}[- ]{liability}|{liability}|{derivative})",
        # Inverted: liability/derivative + warrant
        rf"(?:{liability}|{derivative})[- ]classified\s+{warrant}",
        # Classified context: warrant...classified as (liability|derivative)
        rf"(?:{derivative}\s+)?{warrant}.*classified\s+as\s+(?:a\s+)?(?:{derivative}[- ]{liability}|{derivative}|{liability})",
        rf"(?:{derivative}[- ]{liability}|{derivative}|{liability})[- ]{warrant}",
    ]

    # Other Explicitly Safe Phrases
    explicit_phrases = [
        r"call spreads?",
        r"capped calls?",
        r"accelerated\s+share\s+repurchases?",
        r"(?:forward|prepaid)\s+contracts?\s+on\s+(?:own\s+)?shares?",
        r"margin\s+loans?",
    ]

    # Combine and pre-sort all high-confidence specific phrases
    all_specifics = explicit_phrases + convertible_phrases + warrant_phrases
    sorted_specific_phrases = sorted(
        all_specifics, key=lambda x: (-len(x), -x.count(r"\s+"), -x.count(r"(?:"))
    )

    # -------------------------------------------------------------------------
    # --- A. STRICT Pattern Construction (High Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for attachment: Must exclude standalones to ensure precision in core matches
    strict_attachment_fragment = expand_instruments(
        unsafe=False, exclude_standalone_suffixes=True
    )

    strict_pattern = build_smart_regex(
        [strict_core_alternation],  # Precise prefixes (share price, S&P 500, etc.)
        strict_attachment_fragment,  # Must attach a derivative base (e.g., 'swap' or 'future')
        sorted_specific_phrases,  # All high-priority explicit phrases
    )
    strict_eq_regex = re.compile(r"\b" + strict_pattern + r"\b", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # --- B. SOFT Pattern Construction (Contextual Precision) ---
    # -------------------------------------------------------------------------

    # Fragment for general pattern combination: Includes all derivative terminology, including standalones.
    soft_instrument_fragment = expand_instruments(unsafe=True)

    soft_pattern = build_smart_regex(
        [strict_core_alternation],
        soft_instrument_fragment,  # Full range of instruments (e.g., 'options', 'warrants' standalones)
        sorted_specific_phrases
        + [
            rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))",
        ],
    )
    soft_eq_regex = re.compile(r"\b" + soft_pattern + r"\b", re.IGNORECASE)

    # Return the tuple of (strict, soft)
    return strict_eq_regex, soft_eq_regex


EQ_CONTEXT_TERMS = [
    # --- A. Core Prices & Markets ---
    r"(?:stock|share|equity)\s+(prices?|markets?|warrants?|indices?|awards?|grants?|compensation|appreciation|options?|derivatives?|capital|securit(?:y|ies))",
    r"market\s+index(?:es)?",
    # --- B. Specific Indices ---
    r"S\&P\s+500",
    r"Nasdaq(?:\s+Composite|\s+Index)?",
    r"Dow\s+Jones(?:\s+Industrial\s+Average|\s+Index)?",
    r"Russell\s+2000",
    # --- C. Equity Components ---
    r"(?:preferred|common|treasury|outstanding)\s+(?:stocks?|shares)",
    # --- D. Structures & Events ---
    r"initial\s+public\s+offering|IPO",
    r"(?:primary|secondary)\s+markets?",
    r"accelerated\s+share\s+repurchases?",  # ASR is a derivative
    # --- E. Risk Integration (Smart Expansion) ---
    rf"(?:stock|share|equity)\s+{_RISK_ALTERNATION}",
    r"capped\s+calls?",
]

EQ_CONTEXT_TERMS += VALUATION_MODELS
EQ_CONTEXT_REGEX = build_regex(EQ_CONTEXT_TERMS)
EQ_STRICT_CONTEXT_REGEX = build_regex(EQ_CONTEXT_TERMS)
EQ_REGEX, EQ_SOFT_REGEX = build_eq_regex()
