# Section 3: Accounting Standards
# === FASB ISSUANCE & ADOPTION ONLY ===
from collections import defaultdict
import re
from typing import List, Tuple

from defs.regex_lib import build_alternation, build_regex
from defs.derivatives_core import ALL_SUFFIXES
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
    r"\bshareholder\s+(?:lawsuit|litigation|suit)\b",
    r"derivative\s+(?:action|lawsuit|suit|litigation|settlement|claim|proceeding)",
    r"shareholder\s+derivative",
    r"courts?",
    r"petitions?",
    r"defenses?",
    r"corrections?",
    r"corrective\s+actions?",
]
COMPETITOR_KEYWORDS = [
    r"competitors?",
    r"competition",
    r"other\s+companies",
    r"other\s+entities",
    r"other\s+market\s+participants",
    r"industry\s+peers?",
    r"industry\s+practice",
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
    r"\bpost[- ]?retirement\s+(?:benefits?|plans?)",
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
        # --- Explicit Exemptions (SEC Item 305) ---
        "lease",  #
        "insurance",  #
        "pension",  #
        "retirement",
        "warranty",  #
        r"(?<!power[- ])purchase",  # Matches "Purchase contract"
        "trade",  # Matches "Trade agreement
        "deferred compensation",  #
        "stock option",  #
        "stock purchase",  #
        "equity method",  # Matches "Equity method contract"
        "stock",
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
        "real estate",
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
        "sales",
    ]
    suffixes = ALL_SUFFIXES.copy()
    additional_suffixes = [
        r"positions?",
        r"obligations?",
        r"(?:activit|liabilit)(?:ies|y)", 
        r"involvements?",  
        r"holdings?",
        r"assets?",
    ]
    other_terms = [
        r"hedge\s+(?:funds?|banks?|providers?)",
        r"swap\s+(?:dealers?|participants?)",
        r"derivative\s+counterpart(?:y|ies)",
        r"(?:the|an)\s+options?\s+(?:to|for)",
        r"to\s+(?:swap|forward|call|put)",
        r"(?:look(?:ing|ed)?|br(?:ought|ing)|straight|fast|go(?:ing)?|step(?:ping|ped)?|carr(?:ing|y|ied)|puts?)\s+forward",
        r"(?:the|an)\s+options?\s+(?:to|for)",
        r"calls?\s+(?:for|upon)",
        r"puts?\s+(?:in|up|forward|off|out)",
    ]

    suffixes.extend(additional_suffixes)
    suffix_alternation = build_alternation(suffixes)
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
    neg = [
        "not",
        "no longer",
        "does not",
        "did not",
    ]
    verbs = [
        "qualif(?:ied|y)",
        "classif(?:ied|y)",
        "account(?:ed)?",
        "designate(?:d)?",
        "treat(?:ed)?",
        "elect(?:ed)?",
        "apply",
        "require(?:d)?",
        "meet",
    ]

    prepositions = [
        "for",
        "as",
        "under",
        "to",
    ]

    targets = [
        "derivatives?",
        "hedges?",
        "hedging",
        "bifurcation",
        r"derivative\s+accounting",
        "criteria",
    ]

    contexts = [
        "treatment",
        "accounting",
    ]
    neg_pat = build_alternation(neg)
    verb_pat = build_alternation(verbs)
    prep_pat = build_alternation(prepositions)
    target_pat = build_alternation(targets)
    context_pat = build_alternation(contexts)
    phrases = [
        rf"{neg_pat}\s+{verb_pat}\s+{prep_pat}\s+(?:an?\s+)?{target_pat}\s+{context_pat}",
        rf"{neg_pat}\s+a\s+derivative",
        r"derivative\s+accounting\s+(?:does|did)\s+not\s+apply",
        r"no\s+bifurcation\s+is\s+(?:required|needed)",
        r"accounted\s+for\s+as\s+debt",
        r"meet(?:s)?\s+the\s+criteria\s+for\s+classification\s+in\s+(?:stock|share)holders['’]?\s+equity",
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
