# Exhibit/Reference nouns
import re
from defs.regex_lib import build_alternation, build_regex
from defs.derivatives_core import unsafe_standalone_alternation
from defs.shared_context import SUBJ

EXB_TOKEN = " E_XB "
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
    EXB_TOKEN
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
    # Checks for Noun + Number (1-3 digits) Exhbit 10.2
    pat_c = rf"\b(?:{EXHIBIT_FRAGMENT})\s+(?:No\.\s+)?\d{{1,3}}(?:\.d{{1,3}})?b"

    return re.compile(rf"(?:{pat_a}|{pat_b}|{pat_b2}|{pat_c}|{EXB_TOKEN})", re.IGNORECASE)


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
        r"shall\s+(?:mean|refer|represent)",
        r"(?:is|are)?\s+considered\s+as",
        rf"(?:{_COPULA}{_GAP})?"
        rf"(?:{_OPT_THE}{_GAP})?"
        rf"{_DEF_NOUN}{_GAP}"
        rf"{_DEF_PREP}",
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
        rf"\b{LEGAL_VERBS}\b",
        # Quoted subjects "X" refers to
        rf"\b(?:term|caption|account)(?:\s+[\"“\'].*?[\"”\'])?\s+{COMMON_VERBS}\b",
        rf"[\"“\'].*?[\"”\']\s+{COMMON_VERBS}\b",
        # Quoted definition with colon: "rate contracts": a/any...
        r"[\"“\'].*?[\"”\']\s*:\s*(?:a|an|any|the)\b",
        # --- 3. Instrument-Subject Definitions ---
        # Matches: "Interest Rate [Swaps means...]", "[Options are considered as...]"
        # Logic: Subject MUST be a detected instrument category.
        rf"\b{INSTR_SUBJ}\s+{COMMON_VERBS}\b",
        # --- 5. Corporate Definitions ---
        # Matches: "The Company defines...", "Management considers..."
        rf"\b(?:{subject})\s+(?:consider|define)s?\s+(?:a\s+)?{_GAP}{INSTR_SUBJ}.*as\b",
    
        # --- 4. Accounting Specifics (Safe with 'is the') ---
        # "Fair value is the price..."
        rf"\b{SAFE_ACCT_SUBJ}\s+(?:represents?|means?|is\s+the|are\s+the|{COMMON_VERBS})\b",
        # --- 5. Instrument Definitions (Strict) ---
        # B. "Is The" Anchor: Requires abstract subject ("A swap") AND generic object ("is a contract")
        # Matches: "A swap is the exchange...", "An option is a contract..."
        rf"\b{INSTR_SUBJ}\s+(?:is|are)\s+(?:the|an?)\s+{DEF_OBJECTS}\b",
    ]
    
    return re.compile(build_alternation(pattern_list), re.IGNORECASE)

# Compile and Export
MORE_INFO_REGEX = build_information_reference_regex()
IS_REFERENCE_REGEX = build_simple_reference_regex()
DEFINITION_INDICATORS = build_definition_regex()

def run_tests():
    print("Running tests for refer.py...")

    test_cases = [
        # --- IS_REFERENCE_REGEX ---
        ("REF: Easy - See Note", IS_REFERENCE_REGEX, "See Note 5.", True),
        ("REF: Easy - Refer to table", IS_REFERENCE_REGEX, "Refer to the above table.", True),
        ("REF: Med - As discussed in", IS_REFERENCE_REGEX, "As discussed in Note 12.", True),
        ("REF: Med - Accompanying schedule", IS_REFERENCE_REGEX, "The accompanying schedule.", True),
        ("REF: Hard - Included in table", IS_REFERENCE_REGEX, "included in the table below", True),
        ("REF: Hard - Exhibit No", IS_REFERENCE_REGEX, "set forth in Exhibit No. 99.1", True),
        ("REF: Neg - Verb note", IS_REFERENCE_REGEX, "We note that the value changed.", False),
        ("REF: Neg - Literal table", IS_REFERENCE_REGEX, "The table is large.", False),
        ("REF: Neg - See future", IS_REFERENCE_REGEX, "We will see the future.", False),

        # --- MORE_INFO_REGEX ---
        ("INFO: Easy - For more info", MORE_INFO_REGEX, "For more information", True),
        ("INFO: Easy - For further details", MORE_INFO_REGEX, "For further details", True),
        ("INFO: Med - Complete discussion", MORE_INFO_REGEX, "For a complete discussion of", True),
        ("INFO: Hard - Details on", MORE_INFO_REGEX, "For details on", True),
        ("INFO: Neg - For year ended", MORE_INFO_REGEX, "For the year ended December 31", False),

        # --- DEFINITION_INDICATORS ---
        ("DEF: Easy - Shall mean", DEFINITION_INDICATORS, "Swap shall mean an agreement.", True),
        ("DEF: Easy - Notional represents", DEFINITION_INDICATORS, "Notional value represents the face amount.", True),
        ("DEF: Med - Term refers to", DEFINITION_INDICATORS, "The term \"Derivative\" refers to financial instruments.", True),
        ("DEF: Med - IR Swaps means", DEFINITION_INDICATORS, "Interest Rate Swaps refers to a contract", True),
        ("DEF: Hard - Swap is contract", DEFINITION_INDICATORS, "Interest rate swap is a contract that exchanges cash flows.", True),
        ("DEF: Hard - Options considered", DEFINITION_INDICATORS, "Options are considered as derivatives.", True),
        ("DEF: Neg - Swap is effective", DEFINITION_INDICATORS, "The swap is effective.", False),
        ("DEF: Neg - Management considers", DEFINITION_INDICATORS, "Management considers the swap to be effective.", False),
        ("DEF: Neg - Generic means", DEFINITION_INDICATORS, "This means that we lost money.", False),
        ("DEF: Neg - Represents significant", DEFINITION_INDICATORS, "It represents a significant portion of assets.", False),
        ("DEF: Quoted Colon", DEFINITION_INDICATORS, '"Rate contracts": any agreement...', True),
    ]

    failures = 0
    for name, regex, text, expected in test_cases:
        match = regex.search(text)
        result = bool(match)
        if result != expected:
            print(f"FAIL [{name}]: '{text}' -> Expected {expected}, Got {result}")
            failures += 1

    if failures == 0:
        print(f"All {len(test_cases)} tests passed.")
    else:
        print(f"{failures} tests failed.")
