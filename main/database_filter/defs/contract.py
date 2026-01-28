# =============================================================================
# CONTRACTUAL NOISE LISTS (SPLIT)
# =============================================================================

# 1. STRICT: Capitalized Definitions & Structural Headers (High Confidence)
# Single match is usually sufficient to identify a contract/indenture.
from defs.regex_lib import build_regex


CONTRACTUAL_KEYWORDS_STRICT = [
    # ROLES
    r"\bAgents?\b",
    r"\b(?:Co-)?Lenders?\b",
    r"\b(?:Co-)?Borrowers?\b",
    r"\bGuarantors?\b",
    r"\bPersons?\b",
    r"\bIssuing\s+Banks?\b",
    r"\bSwingline\s+Lenders?\b",
    r"\bNoteholders?\b",
    r"\bGrantors?\b",
    r"\bPledgors?\b",
    r"\bTrustees?\b",
    r"\bRegistrars?\b",
    r"\bCustodians?\b",
    r"\bDepositaries?\b",
    r"\bAssignees?\b",
    r"\bIndemnitees?\b",
    r"\bLiquidators?\b",
    r"\bReceivers?\b",
    r"\bSuccessors?(?:\s+and\s+Assigns?)?\b",
    # IDIOMS
    r"\b(?:any|such|no|each|another)\s+Person\b",
    r"\bSurviving\s+Person\b",
    r"\bSuccessor\s+Person\b",
    # DOCUMENTS
    r"\bGlobal\s+Notes?\b",
    r"\bDefinitive\s+Notes?\b",
    r"\bSupplemental\s+Indenture\b",
    r"\bOfficer['’]s\s+Certificate\b",
    # STRUCTURE
    r"\bArticles?\s+(?:[IVXLCDM]+|\d+)\s+(?:hereof|thereof|of\s+the\s+(?:Credit|Loan|Indenture|Agreement))\b",
    r"\bArticles?\s+[IVXLCDM]+\b",
    r"\bSections?\s+\d+\.\d+(?:\([a-z]\))?\b",
    r"\bRecitals?\b",
    r"\bSchedules?\s+(?:\d+|[A-Z])\b",
    r"\bExhibits?\s+(?:\d+|[A-Z])\b",
    r"\bAnnex(?:es)?\s+(?:\d+|[A-Z])\b",
]

# 2. LOOSE SINGLE: Archaic Adverbs (High Risk of False Positive)
# These require high density (>3) or combination with phrases to trigger discard.
CONTRACTUAL_KEYWORDS_SINGLE = [
    r"\bhereby\b",
    r"\bhereof\b",
    r"\bthereof\b",
    r"\bthereunder\b",
    r"\bhereunder\b",
    r"\bwitnesseth\b",
    r"\bwhereas\b",
    r"\bhereto\b",
]

# 3. LOOSE PHRASE: Legal Actions & Boilerplate (Medium Confidence)
CONTRACTUAL_KEYWORDS_PHRASE = [
    # Latin/Legal Idioms
    r"\bmutatis\s+mutandis\b",
    r"\binter\s+alia\b",
    r"\binure\s+to\s+the\s+benefit\b",
    r"\bnow\s*,?\s*therefore\b",
    # Actions
    r"acknowledge(?:s|d)?\s+and\s+agree(?:s|d)?",
    r"reaffirm(?:s|ed|ing)?\s+(?:its|their|the)\s+obligations",
    r"ratif(?:y|ies|ied)\s+and\s+confirm(?:s|ed)?",
    r"constitute\s+valid\s+and\s+subsisting\s+obligations",
    r"waive(?:s|d)?\s+any\s+(?:defense|claim|offset)",
    r"operat(?:e|es|ed)\s+to\s+reduce\s+or\s+discharge",
    # Consent/Evidence
    r"prior\s+written\s+consent",
    r"consent\s+of\s+the\s+(?:Administrative\s+Agent|Lenders?|Banks?)",
    r"without\s+the\s+consent\s+of",
    r"evidenced\s+(?:or\s+represented\s+)?by\s+(?:a|an|the|any)\s+(?:Note|Certificate|Instrument|Agreement|Contract)",
    # Pointers
    r"the\s+foregoing\s+(?:recitals|definitions|provisions|conditions|covenants)",
    r"under\s+the\s+Credit\s+Agreement",
    r"under\s+the\s+Loan\s+Documents",
    r"under\s+the\s+Guarantee",
    r"terms\s+defined\s+in\s+the\s+Credit\s+Agreement",
    # Governance
    r"certificate\s+of\s+incorporation",
    r"articles\s+of\s+incorporation",
    r"certificate\s+of\s+designation",
    r"by(?:\s|\-)?laws",
    r"organizational\s+documents",
    r"delaware\s+law",
    r"general\s+corporation\s+law",
    r"DGCL",
    r"anti[- ]takeover",
    r"change\s+of\s+control\s+provisions?",
    r"stockholder\s+rights\s+plan",
    r"poison\s+pill",
    # Definition indicators
    # 1. "Shall mean" (The classic legal definition)
    r"shall\s+(?:mean|refers?|have|has|do|give|get|expire|mature|settle|terminate|be)",
    # 2. "Have the meaning ascribed"
    r"have\s+the\s+meanings?\s+(?:ascribed|assigned|given|set\s+forth)",
    # 3. "As defined in/under" (Pointer to definition)
    r"(?:as|is|are|were|was)\s+defined\s+(?:in|under|by|as)",
    # 5. Anchored Term Definition: "The term 'X' means"
    # This is safe because it requires "The term" anchor.
    r"[Tt]he\s+term\s+[\"“].*?[\"”]\s+(?:means?|refers?)",
]
EXCLUDE_REGEX_CONTRACTUAL_STRICT = build_regex(CONTRACTUAL_KEYWORDS_STRICT)
EXCLUDE_REGEX_CONTRACTUAL_PHRASE = build_regex(CONTRACTUAL_KEYWORDS_PHRASE)
EXCLUDE_REGEX_CONTRACTUAL_SINGLE = build_regex(CONTRACTUAL_KEYWORDS_SINGLE)

def is_contractual_noise(text: str, threshold: int = 4) -> bool:
    """
    Determines if text is contractual boilerplate using a scoring system.

    Scoring Logic (Threshold = 4):
    - Strict Matches (Capitalized definitions): 2 points each (2 hits = Discard)
    - Phrases (Legal actions): 2 points each (2 hits = Discard)
    - Single Words (Archaic adverbs): 1 point each (4 hits = Discard)

    Combinations work automatically:
    - 1 Phrase (2pts) + 2 Singles (2pts) = 4pts -> Discard
    """

    # 1. DEFINE WEIGHTS
    W_STRICT = 2
    W_PHRASE = 2
    W_SINGLE = 1

    # 2. COUNT MATCHES
    # Note: We use findall to get the count of occurrences
    strict_hits = len(EXCLUDE_REGEX_CONTRACTUAL_STRICT.findall(text))
    phrase_hits = len(EXCLUDE_REGEX_CONTRACTUAL_PHRASE.findall(text))
    single_hits = len(EXCLUDE_REGEX_CONTRACTUAL_SINGLE.findall(text))

    # 3. CALCULATE SCORE
    score = (
        (strict_hits * W_STRICT) + (phrase_hits * W_PHRASE) + (single_hits * W_SINGLE)
    )

    return score >= threshold
