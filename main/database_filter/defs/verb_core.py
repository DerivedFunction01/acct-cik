from defs.derivatives_core import LOOSE_GEN_REGEX
from defs.derivative_lib import STRICT_REGEX
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import (
    NUMBER_PATTERN,
    SUBJ,
)

# Add this alongside your other lists
NEGATIVE_CONTRACTIONS = [
    # Active
    r"do[nN]['’]?[tT]",
    r"does[nN]['’]?[tT]",
    r"did[nN]['’]?[tT]",
    r"wo[nN]['’]?[tT]",
    r"would[nN]['’]?[tT]",
    r"ca[nN]['’]?[tT]",
    r"cannot",
    r"could[nN]['’]?[tT]",
    r"should[nN]['’]?[tT]",
    r"sha[nN]['’]?[tT]",
    r"have[nN]['’]?[tT]",
    r"has[nN]['’]?[tT]",
    r"had[nN]['’]?[tT]",
    # Passive
    r"are[nN]['’]?[tT]",
    r"is[nN]['’]?[tT]",
    r"was[nN]['’]?[tT]",
    r"were[nN]['’]?[tT]",
]

NEGATIVE_AUXILIARY = [
    # Active
    r"do",
    r"does",
    r"did",
    r"will",
    r"would",
    r"can",
    r"could",
    r"shall",
    r"should",
    r"have",
    r"has",
    "had",  # Added 'had'
    r"must",
    # Passive (Crucial for "Derivatives were not held")
    r"are",
    r"is",
    r"were",
    r"was",
    r"be",
]

# Export
# Speculative / Uncertain Timing Phrases
SPECULATIVE_PHRASES = [
    r"from\s+time\s+to\s+time",
    r"periodically",
    r"in\s+future\s+periods",
    r"upon\s+occurrence",
    r"when\s+(?:deemed\s+)?necessary",
    r"when\s+(?:chosen|choosed)",
]

POTENTIAL_SUFFIX_ADVERBS = [
    r"occasionally",
    r"selectively",
    r"typically",
    r"generally",
    r"routinely",
    r"customarily",
    r"regularly",
    r"normally",
    r"often",
    r"frequently",
    r"sometimes",
    r"rarely",
]

# Potential / Hypothetical Modals & Phrases
POTENTIAL_INDICATORS = [
    r"may",
    r"might",
    r"(?:may|might|are|were)\s+(?:consider|plann?)(?:ing)?",
    r"could",
    r"would",
    r"will",
    r"seek\s+to",
    r"intend\s+to",
    r"plan(?:s|ned)?\s+to",
    r"if",
    r"whether",
    r"limited",  # limited use
    # FIX: Negative lookahead allows "expect to continue" (Active) while flagging "expect to use" (Potential)
    r"expect(?:s|ed)?\s+to(?![- ]continue)",
] + POTENTIAL_SUFFIX_ADVERBS

_ABSENCE_NOUNS = [
    r"positions?",
    r"obligations?",
    r"activit(?:ies|y)",  # "no derivative activity"
    r"involvements?",  # "no involvement with derivatives"
    r"holdings?",  # "no holdings"
]

VERB_MAP = {
    "POSS": [
        r"hold(?:s|ing)?|held",
        r"(?:hav(?:e|ing)|had)(?![- ]designat(?:e|es|ed|ing))",
        r"maintain(?:s|ed|ing)?",
        r"possess(?:e|es|ed|ing)?",
        r"carr(?:y|ies|ied|ying)",
        r"(?:remained|is|are|was|were)?\s+(?:open|outstanding|active)",
        r"(?:a\s+)?party\s+to",
    ],
    "PRU": [
        r"us(?:e(?:s|d)?|ing)",
        r"utiliz(?:e|es|ed|ing)",
        r"employ(?:s|ed|ing)?",
        r"appl(?:ies|ied|ying|y)",
        r"participat(?:es?|ed|ing)",
        r"designat(?:e|es|ed|ing)(?![- ]as)",
        r"hedg(?:e|es|ed|ing)\s+(?:with|using|by)",
        r"trad(?:e|es|ed|ing)",
    ],
    "ACT": [
        r"enter(?:s|ed|ing)?(?:\s+into)?",
        r"engag(?:e|es|ed|ing)(?:\s+in)?",
        r"execut(?:e|es|ed|ing)",
        r"transact(?:s|ed|ing)?",
        r"purchas(?:e|es|ed|ing)",
        r"issu(?:e|es|ed|ing)?",
        r"convert(?:s|ed|ing)?",
        r"secur(?:e|es|ed|ing)",
    ],
    "ACCT": [
        r"designat(?:e|es|ed|ing)",
        r"chose(?:\s+to)",
        r"choos(?:e|es|ing)(?:\s+to)",
        r"retain(?:s|ed|ing)?",
    ],
}

ALL_VERBS = list(
    VERB_MAP["POSS"] + VERB_MAP["PRU"] + VERB_MAP["ACT"] + VERB_MAP["ACCT"]
)

INTENT_VERB_PATTERN = build_alternation(ALL_VERBS)
VERB_REGEX = build_regex(VERB_MAP["POSS"] + VERB_MAP["PRU"] + VERB_MAP["ACT"])
# The "Meat": Keywords that define what is being denied

_DENIAL_MODIFIERS = [
    "exchange",
    "rate",
    "currency",
    "interest",
    "foreign",
    "commodity",
    "equity",
    "credit",
    "market",
    "forward",
    "future",
    "option",
    "swap",
    "purchase",
    "sale",
    "cash",
    "fair",
    "value",
    "material",
    "significant",
    "hedging",
    "derivative",
    "financial",
    "trading",
    "proprietary",
    "contracted",
    "volume",
    "price",
    "speculative",
    NUMBER_PATTERN,
    "forward[- ]starting",
    "months?",
    "years?",
    "net",
    "aggregated?",
    "total",
    "notional",
    "amounts?",
    "new",
    "open",
    "active",
    "outstanding",
    "separate",
    "more",
]

# The "Glue": Small filler words that appear between modifiers
_DENIAL_FILLER = r"(?:\S+\s+){0,3}"

# The "Chain": A single unit of [Filler] + [Modifier]
# Supports lists like "interest rate, foreign exchange, or commodity..."
_DENIAL_SEMANTIC_MOD = (
    rf"(?:{build_alternation(_DENIAL_MODIFIERS)}|{LOOSE_GEN_REGEX.pattern})"
)
_DENIAL_GAP_UNIT = rf"(?:{_DENIAL_FILLER}{_DENIAL_SEMANTIC_MOD})"
GAP_CHAIN = rf"(?:{_DENIAL_GAP_UNIT}\s+){{0,5}}"
# The "Target": The final noun in the sequence
_DENIAL_TARGET = rf"(?:{STRICT_REGEX.pattern}|{LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"

POSS_VERB_REGEX = build_regex(VERB_MAP["POSS"])
USAGE_VERB_REGEX = build_regex(VERB_MAP["PRU"])
TRANS_VERB_REGEX = build_regex(VERB_MAP["ACT"])
ACCT_VERB_REGEX = build_regex(VERB_MAP["ACCT"])
ALL_VERB_REGEX = build_alternation(ALL_VERBS)

def build_negation_prefix_pattern() -> str:
    """
    Returns a regex string matching:
    1. Standard Negation: "did not", "was not", "will not"
    2. Contractions: "didn't", "wasn't"
    3. Absolute Negation: "never"
    """
    # 1. Standard: Auxiliary + Not
    aux_full = build_alternation(NEGATIVE_AUXILIARY)
    pattern_full = rf"\b{aux_full}\s+not\b"

    # 2. Contractions
    pattern_contract = rf"\b{build_alternation(NEGATIVE_CONTRACTIONS)}\b"

    # 3. Absolute (The new addition)
    abs_neg = ["never", "neither", "nor"]
    pattern_absolute = rf"\b{build_alternation(abs_neg)}\b"

    # Combine: (did not | didn't | never)
    return rf"(?:{pattern_full}|{pattern_contract}|{pattern_absolute})"

# Active / Timing Indicators (New)
ACTIVE_INDICATORS = [
    "currently",
    "presently",
    "at present",
]
ACTIVE_PATTERN = build_alternation(ACTIVE_INDICATORS)
# Allow adverbs between negation and verb
aux = build_alternation(NEGATIVE_AUXILIARY)
PRE_VERB_GAP = (
    r"(?:"
    rf"\s+(?:{aux})\s+{SUBJ}\s+|"  # Inversion: " did the company "
    r"[, ](?:"  # Mandatory space or comma after "not"
    rf"{_DENIAL_FILLER}\s+|"  # "currently, occasionally "
    r"\s*[^,]{1,50}\s*,\s+"  # ", as a routine matter, " (Greedy but bounded)
    r")?)"
)
