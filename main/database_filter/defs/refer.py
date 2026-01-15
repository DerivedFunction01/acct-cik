# Exhibit/Reference nouns
import re
from defs.regex_lib import build_alternation
from defs.derivative_lib import CATEGORY_REGEX
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
    instr = f"(?:{CATEGORY_REGEX.pattern})"
    subject = SUBJ  # From derivative_regex.py
    SENTENCE_TAIL = r"[^.?!]*"

    # 2. Key Verbs Grouped by Safety

    # SAFE: Legal terms that rarely appear in narrative flow
    LEGAL_VERBS = r"(?:shall\s+mean|is\s+defined\s+as|definitions?\s+of)"

    # RISKY: Common verbs that need specific subjects (Quotes, "The term", Instrument names)
    COMMON_VERBS = (
        r"(?:means?|represents?|refers?\s+to|considered\s+as|\:)"  # Add colon
    )
    # Subject Groups
    # 1. Safe Accounting Nouns (Fair Value, Notional, etc.) - Can use "is the"
    SAFE_ACCT_SUBJ = (
        r"(?:notional\s+value|contractual\s+interest|fair\s+value|market\s+value|"
        r"hedge\s+effectiveness|credit\s+risk)"
    )

    # 2. Instrument Names (Swaps, Forwards) - NEED STRICTER VERBS
    INSTR_SUBJ = f"(?:{CATEGORY_REGEX.pattern})"  # Your LOOSE_GEN_REGEX equivalent

    # 3. Generic Definitional Objects (To anchor "is the")
    DEF_OBJECTS = r"(?:agreement|contract|exchange|obligation|instrument|transaction|commitment|arrangement)"
    pattern_list = [
        # --- 1. The "Legal Hammer" (Safe to be broad) ---
        # Matches: "Swaps shall mean...", "Hedging is defined as..."
        # We allow broad subjects here because "shall mean" is distinct.
        rf".*?\s+{LEGAL_VERBS}\s+.*{SENTENCE_TAIL}",
        # --- 2. Anchored "Means/Refers" (Strict Subjects Only) ---
        # Matches: "The term 'Swap' means...", "'Derivatives' refers to..."
        # Logic: Must start with "The term", "This caption", or a Quoted String.
        rf"(?:[Tt]he\s+term\s+|[Tt]his\s+(?:caption|account)\s+|[\"“].*?[\"”]\s+){COMMON_VERBS}{SENTENCE_TAIL}",
        # --- 3. Instrument-Subject Definitions ---
        # Matches: "Interest Rate Swaps means...", "Options are considered as..."
        # Logic: Subject MUST be a detected instrument category.
        rf"(?:a\s+)?{instr}\s+(?:{COMMON_VERBS}){SENTENCE_TAIL}",
        # --- 4. Accounting Specifics ---
        # Matches: "Notional value represents..."
        rf"{SAFE_ACCT_SUBJ}\s+(?:represents?|means?){SENTENCE_TAIL}",
        # --- 5. Corporate Definitions ---
        # Matches: "The Company defines...", "Management considers..."
        rf"(?:{subject})\s+(?:consider|define)s?\s+(?:a\s+)?{instr}.*as{SENTENCE_TAIL}",
        # --- 6. Inverted Definitions ---
        # Matches: "...is the definition of..."
        rf".*?\s+is\s+the\s+definition\s+of{SENTENCE_TAIL}",
        # --- 4. Accounting Specifics (Safe with 'is the') ---
        # "Fair value is the price..."
        rf"{SAFE_ACCT_SUBJ}\s+(?:represents?|means?|is\s+the|are\s+the){SENTENCE_TAIL}",
        # --- 5. Instrument Definitions (Strict) ---
        # A. Strong Verbs: "Swaps mean..." (Safe)
        rf"{INSTR_SUBJ}\s+(?:means?|refers?\s+to|is\s+defined\s+as){SENTENCE_TAIL}",
        # B. "Is The" Anchor: Requires abstract subject ("A swap") AND generic object ("is a contract")
        # Matches: "A swap is the exchange...", "An option is a contract..."
        # Avoids: "The swap is the tool..."
        rf"(?:A|An)\s+{INSTR_SUBJ}\s+is\s+(?:the|an?)\s+{DEF_OBJECTS}{SENTENCE_TAIL}",
    ]

    combined = "|".join(f"(?:{p})" for p in pattern_list)

    return re.compile(combined, re.IGNORECASE | re.VERBOSE)


# Compile and Export
MORE_INFO_REGEX = build_information_reference_regex()
IS_REFERENCE_REGEX = build_simple_reference_regex()
DEFINITION_INDICATORS = build_definition_regex()
