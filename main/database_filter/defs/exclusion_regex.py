# Section 3: Accounting Standards
# === FASB ISSUANCE & ADOPTION ONLY ===
from collections import defaultdict
import re
from typing import List, Tuple

from defs.regex_lib import add_restrictions, build_alternation, build_compound, build_regex, to_build_alternation
from defs.derivatives_core import ALL_SUFFIXES, BASE, VERB_LOOKBEHIND
from defs.shared_context import TRADING_ENTITIES

def build_entity_exclusion_regex() -> Tuple[re.Pattern, str]:
    """
    Matches official entity names AND their acronyms that contain trigger words
    (Futures, Swaps, Options, Derivatives, Exchange) to prevent false positive classification.
    However, it allows Derivative context
    """

    # Use build_alternation to ensure longest matches (e.g., full name) are prioritized
    # Note: We enforce word boundaries \b for short acronyms inside the list above
    pattern = build_alternation(TRADING_ENTITIES)
    return re.compile(pattern), " ET_ "

# =============================================================================
# FORWARD-LOOKING STATEMENT PATTERNS
# =============================================================================
FORWARD_LOOKING_KEYWORDS = [
    # 1. The Headers/Titles
    r"cautionary\s+(?:note|statement|language)\s+(?:regarding|concerning|about)",
    r"forward[- ]looking\s+statements?",
    r"safe\s+harbor",
    # 2. Legal Acts/Sections (The smoking gun for boilerplate)
    r"private\s+securities\s+litigation\s+reform\s+act",
    r"section\s+27a\s+of\s+the\s+securities\s+act",
    r"section\s+21e\s+of\s+the\s+securities\s+exchange\s+act",
    # 3. Boilerplate Definitions
    r"statements\s+that\s+are\s+not\s+historical\s+facts",
    r"words\s+such\s+as\s+(?:expect|anticipate|intend|plan|believe|seek|see|will|would|target)",
    r"results\s+(?:could|may|might)\s+differ\s+materially",
    r"undertake\s+no\s+obligation\s+to\s+update",
    # 4. Specific Risk Factors boilerplate (careful not to delete actual risk mgmt)
    r"refer\s+to\s+(?:item|section)\s+1a\.?\s+risk\s+factors",
    r"risk\s+factors\s+described\s+in",
]

FILING_KEYWORDS = [
    "10-K",
    "10-KT",
    "20-F",
    "40-F",
    "10-K405",
    "10KSB",
    "10KSB40",
    "8-K",
    "Incorporated by",
    "filed on",
    r"(?:annual|quarterly)\s+report",
    r"\bSEC\b\s+File",
]

# Section 2: Legal/Litigation
# === More specific legal/litigation patterns ===
LEGAL_LITIGATION_KEYWORDS = [
    # Core litigation terms
    r"\blawsuit\b",
    r"\blitigation\b",
    r"\barbitration\s+(?:proceeding|hearing|case)\b",
    r"\blegal\s+(?:action|proceeding|case|dispute)\b",
    # Types of legal actions (use full context)
    r"\bcivil\s+(?:action|suit|case|proceeding)\b",
    r"\bcriminal\s+(?:action|case|proceeding|charges?)\b",
    r"\badministrative\s+(?:action|proceeding|hearing)\b",
    # Parties in litigation (must be in litigation context)
    r"\b(?:named\s+as\s+)?(?:a\s+)?(?:plaintiff|defendant|respondent|claimant)\b",
    r"\b(?:co-)?defendants?\s+(?:in|include|are)\b",
    # Convictions and violations
    r"\bconvicted\s+of\b",
    r"\bpled\s+guilty\b",
    r"\bplea\s+(?:agreement|bargain|deal)\b",
    r"\bviolated\s+(?:securities|federal|state)\b",
    r"\balleges?\s+(?:that|violations?)\b",
    r"\bcharges?\s+(?:filed|brought|pending)\b",
    # Court proceedings
    r"\bcourt\s+(?:case|proceeding|order|judgment|ruling)\b",
    r"\bjudgme?nt\s+(?:against|in\s+favor|rendered)\b",  # Fixed typo
    # Officers/Directors in legal context (more specific)
    r"\b(?:former\s+)?(?:officer|director)s?\s+(?:was|were|are)\s+(?:charged|indicted|convicted|sued)\b",
    r"\bagainst\s+(?:former\s+)?(?:officer|director)s?\b",
    r"\b(?:officer|director)s?\s+(?:and|or)\s+(?:officer|director)s?\s+(?:were\s+)?(?:named|charged|sued)\b",
    # Securities litigation specific
    r"\bsecurities\s+(?:fraud|litigation|class\s+action)\b",
    r"\bclass\s+action\s+lawsuit\b",
    r"\bshareholder\s+(?:lawsuit|litigation|suit|derivative)\b",
    r"derivative\s+(?:action|lawsuit|suit|litigation|settlement|claim|proceeding)",
    r"courts?",
    r"petitions?",
    r"defenses?",
    r"corrections?",
    r"corrective\s+actions?",
]
COMPETITOR_KEYWORDS = [
    r"competitors?",
    r"competition",
    r"other\s+(?:entities|companies|market\s+participants)",
    r"industry\s+(?:practice|peers?)",
    r"peer\s+group",
]
# =============================================================================
# NON-FINANCIAL DERIVATIVE EXCLUSIONS (NEW)
# =============================================================================
# Targets: "Derivative Works" (IP), "Plasma Derivatives" (Bio), "Chemical Derivatives"
NON_FINANCIAL_KEYWORDS = [
    # 1. Intellectual Property / Software
    r"derivative\s+works?",
    r"open\s+source",
    r"source\s+code",
    r"general\s+public\s+license",
    r"gpl",
    r"creative\s+commons",
    # 2. Biology / Pharma / Chemistry
    r"plasma",
    r"blood",
    r"fractionation",
    r"cellulose",
    r"fatty\s+acids?",
    r"proteins?",
    r"enzymes?",
    r"polymers?",
    r"molecules?",
    r"compounds?",
    r"substances?",
    r"isolates?",
    r"analogs?",
    r"homologs?",
    r"isomers?",
    r"metabolites?",
    r"synthesis",
    r"biosimilars?",
    # 3. Mathematics (Calculus context)
    r"integrals?",
    r"calculus",
    r"gradients?",
    # 4. The "And Its Derivatives" Trap (Generic)
    r"(?:and|or)\s+(?:their|its)\s+derivatives?",
]

PLAN_ASSETS_KEYWORDS = [
    r"\bplan\s+assets\b",
    r"\bpension\s+(?:plans|funds?|trust|benefits?)",
    r"\bpost(?:\s|\-)?retirement\s+(?:benefits?|plans?)",
    r"\bdefined\s+benefit\s+(?:plans?|pensions?)",
    r"\bretirement\s+(?:plans?|system|benefits?)",
    r"\btrust\s+assets\b",
    r"\b401\(?k\)?\s+plan",
    r"\bVEBA\b",  # Voluntary Employees' Beneficiary Association
    r"hedge funds?",
]


def build_non_derivative_instrument_regex() -> re.Pattern:
    """
    Prevents loose_gen_regex from assuming that context still exists

    :return: Description
    :rtype: Pattern[Any]
    """
    placeholders = [
        # --- Existing ---
        "debt",
        "credit",
        "equity",
        # --- Explicit Exemptions (SEC Item 305) ---
        "lease",  #
        "insurance",  #
        "pension",  #
        "retirement",
        "warranty",  #
        "trad(?:e|ing)",  # Matches "Trade agreement
        "compensation",  #
        "stock option",  #
        "stock purchase",  #
        "equity method",  # Matches "Equity method contract"
        "stock",
        "dividend",
        # --- Common Non-Derivative Contracts ---
        "loan",
        "mortgage",
        "guarantee",
        "indemnification",
        "reinsurance",
        "service",
        "employment",
        "license",
        "construction",
        "franchise",
        "royalty",
        "trust",
        "partnership",
        "subscription",
        "underwriting",
        "custody",
        "management",
        "consulting",
        "marketing",
        "distribution",
        "development",
        "research",
        "collaboration",
        "settlement",
        "escrow",
        "pledge",
        "security",
        "deposit",
        "investment",
        "executory",
        "operating",
        "maintenance",
        "support",
        "hosting",
        "software",
        "hardware",
        "equipment",
        "real-estate",
        "land",
        "building",
        "property",
        "vehicle",
        "vessel",
        "aircraft",
        "inventory",
        "receivable",
        "payable",
        "tax",
        "intercompany",
        "joint venture",
        "merger",
        "acquisition",
        "divestiture",
        "restructuring",
        "separation",
        "transition",
        "standstill",
        "voting",
        "registration rights",
        "lock-up",
        "non-compete",
        "non-disclosure",
        "confidentiality",
        "sales?",
    ]
    suffixes = ALL_SUFFIXES.copy() + [BASE.OPTION]
    
    other_terms = [
        r"hedge\s+(?:funds?|banks?|providers?)",
        r"swap\s+(?:dealers?|participants?)",
        r"(?<!the\s)(?<!an\s)(?<!a\s)(?:swap|forward|call|put|lock|cap)s?\s+(?:the|a|an|out|off|up)",
        build_compound(VERB_LOOKBEHIND, r"(?:swap|forward|call|put|lock|cap)s?"),
        r"(?:look(?:ing|ed)?|br(?:ought|ing)|straight|fast|go(?:ing)?|step(?:ping|ped)?|carr(?:ing|y|ied)|puts?)\s+forward",
        r"(?:debt|equity)[- ](?:to|for)[- ](?:equity|debt)",
        r"(?:stock|share|debt|loan|bond|note)s?\s+swaps?",
        r"economic\s+hedg(?:es?|ing)(?!\s+(?:instruments?|contracts?))",
    ]

    suffix_alternation = to_build_alternation(suffixes)
    placeholder_alternation = build_alternation(placeholders)
    other_alternation = build_alternation(other_terms)
    return re.compile(
        rf"\b(?:{placeholder_alternation}\s+{suffix_alternation}|{other_alternation})\b",
        re.IGNORECASE,
    )


# Use build_regex for consistency
AOCI_STRICT_TERMS = [
    r"accumulated\s+other\s+comprehensive",  # Strict "Accumulated"
    r"AOCI\b",
    r"reclassifi.{0,20}(?:AOCI|O\.?C\.?I|comprehensive)",  # Reclassification implies moving OUT (History)
]
def build_non_derivative_treatment_regex() -> re.Pattern:
    # Negation cues
    neg = [
        r"not",
        r"no\s+longer",
        r"does\s+not",
        r"did\s+not",
        r"exception\s+from",
    ]

    # Verbs describing classification/treatment
    verbs = [
        r"qualif(?:ied|y|ication)",
        r"classif(?:ied|y|ication)",
        r"account(?:ed)?",
        r"designate(?:d)?",  # we will explicitly exclude "not designated as a hedging instrument"
        r"treat(?:ed)?",
        r"elect(?:ed)?",
        r"apply|application",
        r"require(?:d)?",
        r"meet",
        r"met",
        r"subject(?:ed)?",
        r"consider(?:ed)?",
    ]

    prepositions = [
        r"for",
        r"as",
        r"under",
        r"to",
        r"to\s+be",
        r"the",
    ]

    targets = [
        r"derivatives?",
        r"hedges?",
        r"hedging",
        r"bifurcation",
        r"criteria",
    ]

    contexts = [
        r"treatment",
        r"accounting",
        r"criteria",
        r"for",
    ]

    neg_pat = build_alternation(neg)
    verb_pat = build_alternation(verbs)
    prep_pat = build_alternation(prepositions)
    target_pat = build_alternation(targets)
    context_pat = build_alternation(contexts)

    phrases = [
        # 1. General negation template
        rf"{neg_pat}\s+{verb_pat}\s+{prep_pat}\s+(?:an?\s+)?{target_pat}\s+{context_pat}",
        # 2. Simple "not a derivative"
        rf"{neg_pat}\s+a\s+derivative",
        # 3. Hedge/derivative classification not applying
        r"(?:hedge|derivative)\s+(?:classification|accounting)\s+(?:does|did)\s+not\s+apply",
        # 4. No bifurcation required
        r"no\s+bifurcation\s+(?:is\s+)?(?:required|needed)",
        # 5. Accounted for as debt/equity
        r"(?<!not\s)accounted\s+for\s+as\s+(?:debt|equity|permanent\s+equity)",
        # 6. Meets criteria for equity classification (positive form)
        r"(?<!not\s)(?<!whether\sit\s)(?<!if\sit\s)meet(?:s)?\s+(?:the\s+)?criteria(?:\s+for)?(?:\s+\b\w+\b){0,2}?\s*classification(?:\s+in)?\s+(?:stock|share)holders['’]?\s+equity",
        # 7. Not considered derivative financial instruments
        r"not\s+considered\s+(?:to\s+be\s+)?derivative\s+financial\s+instruments?",
        # 8. Does not meet definition of a derivative
        r"(?<!if\sit\s)(?:do|does|did)\s+not\s+meet\s+the\s+definition\s+of\s+a\s+derivative",
        # 9. Indexed to own stock (positive form only)
        r"(?<!not\s)indexed\s+to(?:\s+\w+){0,3}\s+own\s+stock",
        # 10. Exception from derivative accounting
        r"exception\s+from\s+derivative\s+accounting",
        # 11. Regular-way security trades
        r"regular[- ]way\s+security\s+trades?",
    ]

    return build_regex(phrases)


def bankruptcy_regex() -> re.Pattern:
    bankruptcy_terms = [
        # 1. Statutory Chapters (US Code)
        # Matches: Chapter 11, Chapter 7, Chapter 15 (Cross-border)
        r"chapter\s+(?:7|11|15)",
        # 2. Core Legal Status
        r"bankruptcy",
        r"insolvency",
        r"receivership",
        r"conservatorship",  # Common for banks (e.g., FDIC takeover)
        # 3. The Process / Legal Actions
        r"debtor[- ]in[- ]possession",  # DIP financing
        r"voluntary\s+petition",
        r"involuntary\s+petition",
        r"petition\s+for\s+relief",  # "filed a petition for relief under Chapter 11"
        r"automatic\s+stay",  # The legal halt on creditors
        # 4. Reorganization & Emergence
        r"plan\s+of\s+reorganization",
        r"emergence\s+from\s+bankruptcy",
        r"fresh[- ]start\s+(?:accounting|reporting)",  # Specific accounting treatment upon emergence
        # 5. Liquidation (Guarded)
        # GUARD: "Liquidation" alone is dangerous (e.g. "liquidation of hedges").
        # We target the accounting basis or the corporate plan.
        r"liquidation\s+basis",
        r"plan\s+of\s+liquidation",
    ]

    return build_regex(bankruptcy_terms)


# Compile and Export
ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN = build_entity_exclusion_regex()
EXCLUDE_REGEX_FORWARD_LOOKING = build_regex(FORWARD_LOOKING_KEYWORDS)
EXCLUDE_REGEX_FILING = build_regex(FILING_KEYWORDS)
EXCLUDE_REGEX_LEGAL_LITIGATION = build_regex(LEGAL_LITIGATION_KEYWORDS)
EXCLUDE_COMPETITOR_REGEX = build_regex(COMPETITOR_KEYWORDS)
EXCLUDE_NON_FINANCIAL_REGEX = build_regex(NON_FINANCIAL_KEYWORDS, use_sep=False)
EXCLUDE_PLAN_ASSETS_REGEX = build_regex(PLAN_ASSETS_KEYWORDS)
EXCLUDE_BANKRUPTCY_REGEX = bankruptcy_regex()
NON_DERIVATIVE_REGEX = build_non_derivative_instrument_regex()
NON_DERIVATIVE_TREATMENT_REGEX = build_non_derivative_treatment_regex()
AOCI_NOISE_REGEX = build_regex(AOCI_STRICT_TERMS)

def aggregate_discards(
    discards: List[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    """
    Groups multiple discards with the same URL and reason into a single row.
    Concatenates the texts with a separator for auditing.

    Args:
        discards: List of (url, sentence, discard_reason)

    Returns:
        Aggregated list where multiple discards with same (url, reason) are combined
    """

    grouped = defaultdict(list)

    # Group by (url, reason)
    for url, sentence, reason in discards:
        grouped[(url, reason)].append(sentence)

    # Reconstruct as single rows with concatenated text
    result = []
    for (url, reason), sentences in grouped.items():
        # Join multiple sentences with a separator for readability
        combined_text = " ||| ".join(sentences)
        result.append((url, combined_text, reason))

    return result
