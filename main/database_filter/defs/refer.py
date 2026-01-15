# Exhibit/Reference nouns
import re
from defs.regex_lib import build_alternation, build_regex
from defs.derivatives_core import unsafe_standalone_alternation
from defs.shared_context import SUBJ

EXHIBIT_NOUNS = [
    "exhibits",
    "references",
    "note",
    "appendix",
    "schedule",
    "article",
    "section",
    "subsection",
    "statement",
    "table",
    "No.",
    "page",
    "pp.",
    "p.",
    "figure",
    "chart",
]
EXHIBIT_FRAGMENT = build_alternation(EXHIBIT_NOUNS)


def build_simple_reference_regex() -> re.Pattern:
    """
    Detects sentences that are primarily navigational pointers.
    Structure: [Pointer Verb] + [Exhibit Noun] OR [Exhibit Noun] + [Direction]
    """

    # 1. Pointer Anchors (Start of phrase usually)
    pointers = [
        r"see",
        r"refer\s+to",
        r"reference\s+is\s+made\s+to",
        r"included\s+in",
        r"contained\s+in",
        r"set\s+forth\s+in",
        r"discussed\s+in",
        r"as\s+shown\s+in",
        r"as\s+presented\s+in",
        r"as\s+detailed\s+in",
    ]
    pointer_alt = build_alternation(pointers)

    # 2. Directions (for "Table below")
    directions = ["below", "above", "following", "accompanying", "attached", "herein"]
    direction_alt = build_alternation(directions)

    # PATTERN A: "See Note 5", "Refer to the Table"
    # Matches: (Pointer) (Optional 'the') (Noun)
    pat_a = rf"\b(?:{pointer_alt})\s+(?:the\s+)?(?:{EXHIBIT_FRAGMENT})\b"

    # PATTERN B: "The table below", "The accompanying schedule"
    # Matches: (Noun) (Direction)
    pat_b = rf"\b(?:{EXHIBIT_FRAGMENT})\s+(?:{direction_alt})\b"

    pat_b2 = rf"\b(?:{direction_alt})\s+(?:{EXHIBIT_FRAGMENT})\b"

    # PATTERN C: "Note 5.", "Exhibit 10." (Explicit Numbering at sentence start/end)
    # Checks for Noun + Number (1-3 digits)
    pat_c = rf"\b(?:{EXHIBIT_FRAGMENT})\s+(?:No\.\s+)?\d{{1,3}}\b"

    return re.compile(rf"(?:{pat_a}|{pat_b}|{pat_b2}|{pat_c})", re.IGNORECASE)


def build_information_reference_regex() -> re.Pattern:
    """
    Matches informational pointers like:
    - "For more information regarding..."
    - "For further details on..."
    - "For a complete discussion of..."
    """

    # Adjectives modifying the noun
    adjectives = [
        "more",
        "further",
        "additional",
        "extra",
        "detailed",
        "supplemental",
        "complete",
        "full",
    ]

    # The nouns themselves
    nouns = [
        "information",
        "details?",
        "discussions?",
        "disclosures?",
        "descriptions?",
    ]

    # Connectors to the subject (Optional)
    connectors = [
        "regarding",
        "concerning",
        "on",
        "about",
        r"related\s+to",
        r"with\s+respect\s+to",
    ]

    adj_pat = build_alternation(adjectives)
    noun_pat = build_alternation(nouns)
    conn_pat = build_alternation(connectors)

    # Structure: "For" + (Optional [Adjective]) + [Noun] + (Optional [Connector])
    pattern = (
        rf"([Ff]or)?\s+"
        rf"(?:(?:a\s+|an\s+)?(?:{adj_pat})\s+)?"  # <--- Added '?' at the end to make the whole block optional
        rf"(?:{noun_pat})"
        rf"(?:\s+(?:{conn_pat}))?"
    )

    return re.compile(pattern, re.IGNORECASE)

# =============================================================================
# DEFINITION DETECTION (Isolated boilerplate)
# =============================================================================


def build_definition_regex() -> re.Pattern:
    """
    Matches definition boilerplate safely.
    Consumes the full sentence tail to prevent debris.
    """

    # 1. Setup Components
    subject = SUBJ 
    
    # 2. Key Verbs Grouped by Safety
    # Optional copula
    _GAP = r"(?:\s+\S+){0,2}"

    _COPULA = r"(?:is|are)"

    # Optional "the"
    _OPT_THE = r"(?:the)"

    # Definition noun
    _DEF_NOUN = r"defin(?:ed|itions?)"

    # Prepositions
    _DEF_PREP = r"(?:as|of)"

    # SAFE: Legal terms that rarely appear in narrative flow
    LEGAL_VERBS_LIST = [
        r"shall\s+mean",
        r"(?:(?:is|are)\s+)?considered\s+as"
        rf"(?:{_COPULA}{_GAP})?"
        rf"(?:{_OPT_THE}{_GAP})?"
        rf"{_DEF_NOUN}{_GAP}"
        rf"{_DEF_PREP}\b",
    ]

    COMMON_VERBS_LIST = [
        r"means?",
        r"refers?\s+to",
        r"represents?",
        
    ] + LEGAL_VERBS_LIST

    # RISKY: Common verbs that need specific subjects (Quotes, "The term", Instrument names)
    COMMON_VERBS = build_alternation(COMMON_VERBS_LIST)
    LEGAL_VERBS = build_alternation(LEGAL_VERBS_LIST)
    # Subject Groups
    # 1. Safe Accounting Nouns (Fair Value, Notional, etc.) - Can use "is the"
    SAFE_ACCT_SUBJ = (
        r"(?:notional\s+value|contractual\s+interest|fair\s+value|market\s+value|"
        r"hedge\s+effectiveness|credit\s+risk)"
    )

    INSTR_SUBJ = unsafe_standalone_alternation  # swap, future, collar, contract, etc

    # 3. Generic Definitional Objects (To anchor "is the")
    DEF_OBJECTS = r"(?:agreement|contract|exchange|obligation|instrument|transaction|commitment|arrangement)"
    pattern_list = [
        LEGAL_VERBS,
        # Quoted subjects "X" refers to
        rf"[\"“].*?[\"”]\s+{COMMON_VERBS}",
        # --- 3. Instrument-Subject Definitions ---
        # Matches: "Interest Rate [Swaps means...]", "[Options are considered as...]"
        # Logic: Subject MUST be a detected instrument category.
        rf"{INSTR_SUBJ}\s+(?:{COMMON_VERBS})",
        # --- 5. Corporate Definitions ---
        # Matches: "The Company defines...", "Management considers..."
        rf"(?:{subject})\s+(?:consider|define)s?\s+(?:a\s+)?{_GAP}{INSTR_SUBJ}.*as",
    
        # --- 4. Accounting Specifics (Safe with 'is the') ---
        # "Fair value is the price..."
        rf"{SAFE_ACCT_SUBJ}\s+(?:represents?|means?|is\s+the|are\s+the)",
        # --- 5. Instrument Definitions (Strict) ---
        # B. "Is The" Anchor: Requires abstract subject ("A swap") AND generic object ("is a contract")
        # Matches: "A swap is the exchange...", "An option is a contract..."
        rf"{INSTR_SUBJ}\s+(?:is|are)\s+(?:the|an?)\s+{DEF_OBJECTS}",
    ]

    return build_regex(pattern_list)

# Compile and Export
MORE_INFO_REGEX = build_information_reference_regex()
IS_REFERENCE_REGEX = build_simple_reference_regex()
DEFINITION_INDICATORS = build_definition_regex()
