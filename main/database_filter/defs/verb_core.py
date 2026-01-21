import re
from typing import List, Optional
from defs.regex_lib import build_alternation
from defs.shared_context import (
    MITIGATION_STRICT_VERBS,
    GENERIC_RISK_GLUE,
    _RISK_ALTERNATION,
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

def build_strict_do_not_mitigate_regex(required_glue: Optional[List[str]] = None) -> re.Pattern:
    """
    Matches: "do not hedge [risk]", "did not mitigate [exposure]"
    Inspired by build_risk_managment_phrase but negated.
    """
    neg_prefix = build_negation_prefix_pattern()
    mitigation_verbs = build_alternation(MITIGATION_STRICT_VERBS)

    # Gap logic from build_risk_managment_phrase
    glue = build_alternation(GENERIC_RISK_GLUE)
    filler = r"(?:\S+\s+){0,3}"

    tiny_gap = r"(?:\S+\s+){0,3}"
    if required_glue:
        req_alt = build_alternation(required_glue)
        glue_unit = rf"(?:{filler}{glue})"
        req_unit = rf"(?:{filler}{req_alt})"
        pre_chain = rf"(?:{glue_unit}\s+){{0,3}}"
        post_chain = rf"(?:{glue_unit}\s+){{0,3}}"
        gap = rf"{pre_chain}{req_unit}\s+{post_chain}"
        # Pattern B: Verb ... Risk ... [Required Glue]? (New)
        pattern_b = rf"{tiny_gap}{_RISK_ALTERNATION}(?:\s+{tiny_gap}{req_alt})?"
    else:
        glue_unit = rf"(?:{filler}{glue})"
        gap = rf"(?:{glue_unit}\s+){{0,6}}"
        # Pattern B: Verb ... Risk ... [Required Glue]? (New)
        pattern_b = rf"{tiny_gap}{_RISK_ALTERNATION}"

    final_filler = r"(?:\S+\s+){0,3}"

    # Allow adverbs between negation and verb
    _pre_verb_gap = (
        r"[, ]"  # Mandatory space or comma after "not"
        r"(?:"
        rf"{ACTIVE_PATTERN}\s+|"  # "currently "
        r"\s*[^,]{1,50}\s*,\s+"  # ", as a routine matter, " (Greedy but bounded)
        r")?"
    )

    # Pattern A: Verb ... Gap ... Risk (Existing)
    pattern_a = rf"{gap}{final_filler}{_RISK_ALTERNATION}"

    combined_suffix = build_alternation([pattern_a, pattern_b], sort_longest_first=True)

    return re.compile(
        rf"{neg_prefix}"
        rf"{_pre_verb_gap}"
        rf"{mitigation_verbs}\s+"
        rf"{combined_suffix}\b",
        re.IGNORECASE
    )
