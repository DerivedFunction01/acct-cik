# --- STANDARD TYPES & ACRONYMS ---
import re
from typing import List, Optional, Union
from defs.regex_lib import build_alternation, build_regex
from defs.shared_context import MONTHS_FRAGMENT

ISSUER_TERMS = [
    r"\bFASB\b",
    r"\bFinancial Accounting Standards Board\b",
    r"\bF\.A\.S\.B\.\b",
    r"\bIASB\b",
    r"\bInternational Accounting Standards Board\b",
    r"\bI\.A\.S\.B\.\b",
    r"\bGASB\b",
    r"\bGovernmental Accounting Standards Board\b",
    r"\bG\.A\.S\.B\.\b",
    r"\bAICPA\b",
    r"\bAmerican Institute of Certified Public Accountants\b",
    r"\bA\.I\.C\.P\.A\.\b",
    r"\bPCAOB\b",
    r"\bPublic Company Accounting Oversight Board\b",
    r"\bP\.C\.A\.O\.B\.\b",
    r"\bFASAB\b",
    r"\bFederal Accounting Standards Advisory Board\b",
    r"\bF\.A\.S\.A\.B\.\b",
    r"\bSEC\b",
    r"\bSecurities\s+(?:[Aa]nd|&)\s+Exchange\s+Commission\b",
    r"\bS\.E\.C\.\b",
    r"\bAccounting Standards Board\b",
    r"\bEITF\b",
    r"\bE\.I\.T\.F\.\b",
    r"\bEmerging Issues Task Force\b",
    r"\bTask Force\b",
]

STANDARDS_TERMS = [
    r"\bSFAS\b",
    "Statement of Financial Accounting Standards?",
    r"\bFAS\b",
    "Financial Accounting Standards?",
    r"\bASU\b",
    "Accounting Standards Update",
    r"\bASC\b",
    "Accounting Standards Codification",
    r"\bIFRS\b",
    "International Financial Reporting Standards?",
    r"\bIAS\b",
    "International Accounting Standards?",
    r"\bIFRIC\b",
    "International Financial Reporting Interpretations Committee",
    r"\bSIC\b",
    "Standing Interpretations Committee",
    r"\bEITF\b",
    "Emerging Issues Task Force",
    r"\bSOP\b",
    "Statement of Position",
    r"\bFSP\b",
    "FASB Staff Position",
    r"\bFIN\b",
    "FASB Interpretation",
    r"\bTB\b",
    r"\bTechnical\s+Bulletin\b",
    r"\bSFAC\b",
    "Statement of Financial Accounting Concepts",
    r"\bConcept\s+Statement\b",
    r"\bAPB\s+Opinion\b",
    "Accounting Principles Board Opinion",
]


# --- ADOPTION TIMING TYPES ---
ADOPTION_TIMING_TYPES = [
    r"early",
    r"late",
    r"future",
    r"current",
    r"past",
    r"prospective",
    r"retrospective",
]
# --- ISSUANCE VERBS ---
ISSUANCE_VERBS = [
    # Core issuance verbs (Present/Past/Participle)
    r"issu(?:es?|ed|ing)",  # issue, issues, issued, issuing
    r"releas(?:es?|ed|ing)",  # release, releases, released...
    r"publish(?:es?|ed|ing)?",  # publish, publishes, published...
    r"ratif(?:y|ies|ied|ying)",  # ratify, ratifies, ratified...
    r"updat(?:es?|ed|ing)",  # update, updates, updated...
    r"announc(?:es?|ed|ing)",  # announce, announces, announced...
    r"expos(?:es?|ed|ing)",  # expose, exposes, exposed...
    r"propos(?:es?|ed|ing)",  # propose, proposes, proposed...
    r"approv(?:es?|ed|ing)",  # approve, approves, approved...
    r"finaliz(?:es?|ed|ing)",  # finalize, finalizes, finalized...
    r"adopt(?:s|ed|ing)?",  # adopt, adopts, adopted...
    r"re-?issu(?:es?|ed|ing)",  # reissue, re-issues, reissued...
    r"amend(?:s|ed|ing)?",  # amend, amends, amended...
    r"revis(?:es?|ed|ing)",  # revise, revises, revised...
    # Phrases
    r"reached?\s+a\s+(?:final\s+)?consensus",  # reach/reached a consensus
]

# --- DESCRIPTION VERBS ---
DESCRIPTION_VERBS = [
    r"address(?:es|ed|ing)",  # address, addresses, addressed
    r"provid(?:es?|ed|ing)\s+(?:guidance|standards|accounting\s+(?:for|treatment))",  # Focused phrase
    r"clarif(?:y|ies|ied|ying)",  # clarify, clarifies, clarified
    r"amend(?:s|ed|ing)?",  # amend, amends, amended
    r"requir(?:es?|ed|ing)",  # require, requires, required
    r"relat(?:es?|ed|ing)\s+to",  # relate/relates/related to
    r"appl(?:y|ies|ied|ying)\s+to",  # apply/applies/applied to
    r"establish(?:es|ed|ing)",  # establish, establishes, established
    r"prescrib(?:es?|ed|ing)",  # prescribe, prescribes, prescribed
    r"defin(?:es?|ed|ing)",  # define, defines, defined
    r"modif(?:y|ies|ied|ying)",  # modify, modifies, modified
    r"specif(?:y|ies|ied|ying)",  # specify, specifies, specified
    r"govern(?:s|ed|ing)?",  # govern, governs, governed
    r"affect(?:s|ed|ing)?",  # affect, affects, affected
    r"impact(?:s|ed|ing)?",  # impact, impacts, impacted
    r"cover(?:s|ed|ing)?",  # cover, covers, covered
    r"deal(?:s|t|ing)?\s+with",  # deal, deals, dealt with
    r"pertain(?:s|ed|ing)?\s+to",  # pertain, pertains, pertained to
    r"concern(?:s|ed|ing)?",  # concern, concerns, concerned
    r"prohibit(?:s|ed|ing)?",  # prohibit, prohibits, prohibited
    r"permit(?:s|ted|ting)?",  # permit, permits, permitted
    r"allow(?:s|ed|ing)?",  # allow, allows, allowed
    r"restrict(?:s|ed|ing)?",  # restrict, restricts, restricted
    r"mandat(?:es?|ed|ing)",  # mandate, mandates, mandated
    r"expand(?:s?|ed|ing)?",  # expand, expands (added per your previous request)
]

# --- ADOPTION VERBS: FUTURE INTENT ---
ADOPTION_VERBS_FUTURE = [
    r"will\s+adopt",
    r"plan(?:s|ned)?\s+to\s+adopt",
    r"expect(?:s|ed)?\s+to\s+adopt",
    r"required?\s+to\s+adopt",
    r"must\s+adopt",
    r"shall\s+adopt",
    r"intend(?:s|ed)?\s+to\s+adopt",
    r"anticipate(?:s|d)?\s+(?:adopting|adoption)",
    r"scheduled\s+to\s+adopt",
    r"targeted\s+to\s+adopt",
    r"is\s+required\s+to\s+adopt",
    r"will\s+be\s+required\s+to\s+adopt",
    r"(?:is|will\s+be)\s+(?:eligible|required)\s+for\s+(?:early\s+)?adoption",
    r"(?:adopted|adoption)\s+by",
]

# --- ADOPTION VERBS: GENERAL ACTION ---
ADOPTION_VERBS_GENERAL = [
    r"adopt(?:ing|ed)?",  # ✓ Direct adoption
    r"early\s+adopt(?:ed|ing|ion)?",  # ✓ Early adoption (accounting-specific)
    r"application\s+of",  # ✓ "Application of ASC 815" (accounting context)
    r"implement(?:ing|ed|ation)",  # ✓ Implementation (accounting standards)
    r"transition(?:ing|ed)?",  # ✓ Transition (accounting-specific in this context)
    r"compliance\s+with",
    r"conform(?:ing|ed|ity)\s+to",
    r"(?:early\s+)?application",
    r"retroactive\s+(?:application|adoption)",  # ✓ Retroactive adoption (accounting-specific)
    r"prospective\s+(?:application|adoption)",  # ✓ Prospective adoption (accounting-specific)
]

# --- EFFECTIVE DATE PHRASES ---
EFFECTIVE_DATE_PHRASES = [
    r"effective\s+for\s+(?:fiscal\s+years|annual\s+periods)",
    r"effective\s+(?:in|for|after)\s+(?:fiscal\s+)?(?:year\s+)?\d{4}",
    r"becomes\s+effective",
    r"will\s+be\s+effective",
    rf"(?:ending|beginning)\s+after\s+{MONTHS_FRAGMENT}",
]

EFFECT_NOUNS = [
    r"impacts?",
    r"effects?",
    r"implications?",
    r"outcomes?",
    r"results?",
    r"consequences?",
    r"repercussions?",
    r"ramifications?",
    r"influences?",
    r"significance",
    r"aftermath",
    r"corollaries?",
    r"byproducts?",
]
ASSESSMENT_VERBS = [
    r"assess(?:es|ed|ing)?",
    r"(?:re)?evaluate(?:s|d|ing)?",
    r"review(?:s|ed|ing)?",
    r"test(?:s|ed|ing)?",
    r"monitor(?:s|ed|ing)?",
    r"analyz(?:e|es|ed|ing)",
    r"apprais(?:e|es|ed|ing)",
    r"audit(?:s|ed|ing)?",
    r"examin(?:e|es|ed|ing)",
    r"inspect(?:s|ed|ing)?",
    r"scrutiniz(?:e|es|ed|ing)",
    r"stud(?:y|ies|ied|ying)",
    r"investigat(?:e|es|ed|ing)",
    r"consider(?:s|ed|ing)?",
    r"validat(?:e|es|ed|ing)",
    r"verif(?:y|ies|ied|ying)",
    r"check(?:s|ed|ing)?",
    r"measur(?:e|es|ed|ing)",
    r"weigh(?:s|ed|ing)?",
]


EFFECT_FRAGMENT = build_alternation(EFFECT_NOUNS)
ASSESSMENT_FRAGMENT = build_alternation(ASSESSMENT_VERBS)

# --- IMPACT ASSESSMENT PHRASES ---
IMPACT_PHRASES = [
    # Generic evaluation/assessment of effects
    rf"{ASSESSMENT_FRAGMENT}\s+(?:the\s+)?{EFFECT_FRAGMENT}\s+of",
    # Ongoing evaluation/assessment
    rf"currently\s+{ASSESSMENT_FRAGMENT}",
    rf"continu(?:ing|es)\s+to\s+{ASSESSMENT_FRAGMENT}",
    # Specific financial reporting context
]

# --- IMPACT RESULT PHRASES ---
IMPACT_RESULT_PHRASES = [
    # Expected materiality with up to 3 intervening words
    rf"(?:not\s+)?expected\s+to\s+have\s+a\s+material(?:\s+\w+){{0,3}}\s+{EFFECT_FRAGMENT}",
    # Explicit immateriality with flexibility
    rf"no\s+material(?:\s+\w+){{0,3}}\s+{EFFECT_FRAGMENT}",
    rf"immaterial(?:\s+\w+){{0,3}}\s+{EFFECT_FRAGMENT}",
    rf"{EFFECT_FRAGMENT}\s+on(?:\s+\w+){{0,3}}\s+statements",
]

# --- ADOPTION PERMISSIBILITY PHRASES ---
ADOPTION_PERMISSION_PHRASES = [
    r"early\s+application\s+(?:is\s+)?permitted",
    r"early\s+adoption\s+(?:is\s+)?permitted",
    rf"(?:{build_alternation(ADOPTION_TIMING_TYPES)})\s+(?:adoption|application)",
    r"(?:adoption|application)\s+(?:is\s+)?(?:permitted|allowed|optional)",
    r"(?:adoption|application)\s+(?:is\s+)?(?:required|mandatory)",
    r"optional\s+(?:adoption|application)",
    r"permitted\s+(?:adoption|application)",
    r"voluntary\s+(?:adoption|application)",
]

# --- GUIDANCE OBJECT TYPES ---
GUIDANCE_OBJECT_TYPES = [
    r"Guidance",
    r"Standards?",
    r"Amendments?",
    r"Statements?",
    r"Provisions?",
    r"Regulations?",
    r"Abstracts?",
    r"Opinions?",
    r"Codifications?",
    r"Pronouncements?",
    r"Interpretations?",
    r"Bulletins?",
    r"Frameworks?",
    r"Concept\s+Statements?",
    r"Clarifications?",
    r"Rules?",
    r"Principals?",
    r"Principles?",
]

# --- STANDALONE PHRASES (context-specific, non-generic) ---
STANDALONE_PHRASES = [
    r"adoption\s+of",
    r"prior\s+to\s+adoption",
    r"transition\s+period",
    r"cumulative\s+effect\s+adjustment",
    r"transition\s+method",
    r"adoption\s+method",
    r"retrospective\s+restatement",
    r"prospective\s+application\s+only",
    r"no\s+restatement\s+(?:of\s+)?(?:prior\s+)?periods",
    r"grandfathering",
    r"grandfather\s+provision",
    r"deemed\s+cost\s+(?:option|election)",
    r"first-?time\s+adoption",
    r"adoption\s+date",
    r"adoption\s+guidance",
    r"implementation\s+guidance",
    r"transition\s+guidance",
    r"effective\s+date\s+(?:of\s+adoption|guidance)",
    r"safe\s+harbor",
    r"optional\s+expedient",
    r"practical\s+expedient",
]

# --- BUILD REGEX FRAGMENTS ---
# Matches: FASB, "FASB", (FASB), ("FASB"), ('FASB')
# We allow any combination of opening parens/quotes and closing parens/quotes
ISSUER_FRAGMENT = rf"(?:[\(\"\'\s]+)?{build_alternation(ISSUER_TERMS)}(?:[\)\"\'\s]+)?"
STANDARDS_FRAGMENT = (
    rf"(?:[\(\"\'\s]+)?{build_alternation(STANDARDS_TERMS)}(?:[\)\"\'\s]+)?"
)

ISSUANCE_VERBS_FRAGMENT = build_alternation(ISSUANCE_VERBS)
DESCRIPTION_VERBS_FRAGMENT = build_alternation(DESCRIPTION_VERBS)
ADOPTION_VERBS_FUTURE_FRAGMENT = build_alternation(ADOPTION_VERBS_FUTURE)
ADOPTION_VERBS_GENERAL_FRAGMENT = build_alternation(ADOPTION_VERBS_GENERAL)
EFFECTIVE_DATE_PHRASES_FRAGMENT = build_alternation(EFFECTIVE_DATE_PHRASES)
IMPACT_PHRASES_FRAGMENT = build_alternation(IMPACT_PHRASES)
IMPACT_RESULT_PHRASES_FRAGMENT = build_alternation(IMPACT_RESULT_PHRASES)
ADOPTION_PERMISSION_PHRASES_FRAGMENT = build_alternation(ADOPTION_PERMISSION_PHRASES)
STANDALONE_PHRASES_FRAGMENT = build_alternation(STANDALONE_PHRASES)
GUIDANCE_OBJECT_TYPES_FRAGMENT = build_alternation(GUIDANCE_OBJECT_TYPES)

# --- STANDARD ID PATTERN ---
# Matches: "EITF Issue No. 06-6", "FASB Statement No. 133", "ASU 2014-09"
STANDARD_ID_PATTERN = rf"(?:{STANDARDS_FRAGMENT}|{GUIDANCE_OBJECT_TYPES_FRAGMENT})(?:\s+Issue)?(?:\s+No\.?)?\s+\d+(?:-\d+)*(?:[A-Z])?"
STANDARD_ID_REGEX = re.compile(r"\b" + STANDARD_ID_PATTERN, re.IGNORECASE)

CAPITALIZED_TITLE_PATTERN = (
    r"(?:,?\s*[\"“']?(?:[A-Z][\w\-']+\s+){2,}[A-Z][\w\-']+[\"”']?)?"
)
# =============================================================================
# ACCOUNTING STANDARDS: STRICT VS SOFT
# =============================================================================

# --- 1. STRICT (High Confidence) ---
# Triggers "Aggressive Mode" in Title Cleaner.
# These explicitly mention Regulators, Standard IDs, or Formal Adoption events.
ACCOUNTING_STANDARDS_STRICT = [
    # Dated Issuance ("In June 2022, the FASB issued...")
    rf"{MONTHS_FRAGMENT}\s+\d{{4}}.*{ISSUER_FRAGMENT}\s+{ISSUANCE_VERBS_FRAGMENT}",
    # Issuer + Issuance ("FASB issued...")
    rf"{ISSUER_FRAGMENT}\s+(?:in\s+{MONTHS_FRAGMENT}\s+\d{{4}}.*)?{ISSUANCE_VERBS_FRAGMENT}(?:\s+in\s+{MONTHS_FRAGMENT}\s+(?:\d{{4}})?)?",
    # Standard ID + Issuance ("ASU 2016-13 was issued...")
    rf"{STANDARD_ID_PATTERN}\s+(?:was|is)\s+{ISSUANCE_VERBS_FRAGMENT}",
    # Issuance Verb + Standard ID ("Adopted SFAS 157...")
    rf"{ISSUANCE_VERBS_FRAGMENT}(?:\s+\w+){{1,10}}\s+{STANDARD_ID_PATTERN}",
    # Standard Descriptions ("ASC 820 defines...")
    rf"{STANDARD_ID_PATTERN}\s+{DESCRIPTION_VERBS_FRAGMENT}",
    # Explicit Adoption ("Adoption of the new guidance")
    rf"{ADOPTION_VERBS_GENERAL_FRAGMENT}\s+{STANDARD_ID_PATTERN}",
    rf"{ADOPTION_VERBS_GENERAL_FRAGMENT}\s+(?:\S+\s+){{0,10}}{GUIDANCE_OBJECT_TYPES_FRAGMENT}",
    # Future Adoption ("We plan to adopt...")
    rf"{ADOPTION_VERBS_FUTURE_FRAGMENT}",
    # Effective Dates ("Effective for fiscal years...")
    rf"{STANDARD_ID_PATTERN}\s+should\s+be\s+applied",
    rf"{STANDARD_ID_PATTERN}\s+(?:is|was|becomes)\s+effective",
    EFFECTIVE_DATE_PHRASES_FRAGMENT,
    ADOPTION_PERMISSION_PHRASES_FRAGMENT,
    # Explicit "No Material Impact" statements (Classic boilerplate)
    IMPACT_RESULT_PHRASES_FRAGMENT,
    # Anchored Headers ("In March 2024...")
    rf"^{STANDARD_ID_PATTERN}\s+(?:{ISSUANCE_VERBS_FRAGMENT}|{DESCRIPTION_VERBS_FRAGMENT})",
    rf"^{ISSUER_FRAGMENT}\s+(?:{ISSUANCE_VERBS_FRAGMENT}|{DESCRIPTION_VERBS_FRAGMENT})",
    rf"^In\s+{MONTHS_FRAGMENT}.*{ISSUER_FRAGMENT}",
    # Specific Terms
    rf"(?:recently\s+)?(?:issued|updated|released|published|announced)\s+(?:accounting\s+)?{GUIDANCE_OBJECT_TYPES_FRAGMENT}(?:\s+updates?)?",
    r"accounting standards update",
    # Disclosures explicitly mandated by an ID
    rf"disclosures?\s+(?:required|mandated)\s+by\s+{STANDARD_ID_PATTERN}[^.?!]*",
    rf"derivatives\s+(?:instruments\s+)?and\s+hedging\s+activities",
]

# --- 2. SOFT (Lower Confidence) ---
# Used for general text filtering but NOT for aggressive title cleanup.
# These are more generic descriptions of disclosure improvements or impacts.
ACCOUNTING_STANDARDS_SOFT = [
    # Standalone accounting phrases (risk of collision with commercial terms)
    STANDALONE_PHRASES_FRAGMENT,
    # Generic impact assessment ("Evaluating the impact of...")
    IMPACT_PHRASES_FRAGMENT,
    # Disclosure improvement language (could be general)
    rf"improve\s+disclosures?\s+(?:about|regarding|on)[^.?!]*",
    rf"requiring\s+(?:more|additional)\s+information[^.?!]*",
    # Pure References ("Pursuant to ASC 815")
    rf"pursuant\s+to\s+{STANDARD_ID_PATTERN}",
    rf"defined\s+in\s+{STANDARD_ID_PATTERN}",
    rf"accordance\s+with\s+{STANDARD_ID_PATTERN}",
    # ID + Title ("ASC 815 Derivatives and Hedging")
    rf"{STANDARD_ID_PATTERN}(?:\s+,\s+)?{CAPITALIZED_TITLE_PATTERN}",
    # Indirect references
    rf"disclosures?\s+(?:about|regarding)\s+(?:the\s+)?(?:adoption|application|impact)\s+of[^.?!]*",
    rf"(?:intended|designed)\s+to\s+(?:improve|expand|enhance)\s+disclosures?[^.?!]*",
    rf"requiring\s+(?:more|additional|expanded)\s+information\s+about[^.?!]*",
]

# --- 3. COMBINED LIST (For General Filtering) ---
ACCOUNTING_STANDARDS_KEYWORDS = ACCOUNTING_STANDARDS_STRICT + ACCOUNTING_STANDARDS_SOFT
EXCLUDE_REGEX_ACCOUNTING_STD = build_regex(ACCOUNTING_STANDARDS_KEYWORDS)
STD_TOKEN = " S_TD "

def register_standard(
    issuers: Union[List[str], str],
    number: str,
    sub: Optional[str] = None,
) -> str:
    if isinstance(issuers, str):
        issuers = [issuers]

    issuer_alt = build_alternation(issuers, sort_longest_first=True)

    # Optional filler: "Statement", "No.", "Issue", "Standard"
    # e.g. "FASB Statement No. 133", "EITF Issue 00-19"
    filler = r"(?:\s+(?:Statement|Standard|Issue|No\.?))*"

    # Separator for sub-part (e.g. 815-40)
    # Matches: "-", "–", "—", " ", "."
    sub_sep = r"[-–—\s\.]?"

    if sub:
        return rf"{issuer_alt}{filler}\s+{number}{sub_sep}{sub}"

    return rf"{issuer_alt}{filler}\s+{number}"


DERIVATIVE_STDS = [
    # US GAAP - Derivatives & Hedging
    register_standard("ASC", "815"),  # The big one (Derivatives and Hedging)
    register_standard(["SFAS", "FAS", "Statement"], "133"),  # The legacy big one
    # US GAAP - Fair Value (Strong signal when combined with "Option/Warrant")
    register_standard("ASC", "820"),
    register_standard(["SFAS", "FAS", "Statement"], "157"),
    # US GAAP - Distinguishing Liabilities from Equity (Crucial for Warrants)
    register_standard("ASC", "480"),  # Distinguishing Liabilities from Equity
    register_standard(["SFAS", "FAS", "Statement"], "150"),
    # International (IFRS)
    register_standard("IFRS", "9"),  # Financial Instruments
    register_standard("IAS", "39"),  # Legacy Financial Instruments
    register_standard("IAS", "32"),  # Presentation (Liability vs Equity)
    # --- NEW: EITF 00-19 (The "Warrant Liability" Key) ---
    # Matches: "EITF 00-19", "EITF Issue No. 00-19", "EITF 0019"
    # Note: We allow flexible separators between '00' and '19'
    register_standard("EITF", "00", "19"),
    # --- NEW: The Codified Version (ASC 815-40) ---
    # EITF 00-19 was codified into ASC 815-40 "Contracts in Entity's Own Equity"
    register_standard("ASC", "815", "40"),
    # Masked standards token
    STD_TOKEN.strip(),
]

DER_STD_REGEX = build_regex(DERIVATIVE_STDS)

def run_test():
    ids = [
        # --- FASB Standards & Updates ---
        "ASU 2025-12",  # Standard Year-Sequence
        "ASC 815-40",  # Codification with sub-topic
        "ASC 815",  # Broad Topic
        "ASU No. 2024-04",  # With optional "No."
        "FASB Statement No. 133",  # Full name + No.
        # --- Legacy & Unofficial IDs ---
        "SFAS 133",  # Acronym only
        "EITF 00-19",  # Legacy format
        "EITF Issue No. 06-6",  # Complex "Issue No." format
        "FIN 48",  # Interpretation
        "FSP 133-1",  # Staff Position
        # --- International Standards ---
        "IFRS 9",  # International standard
        "IAS 39",  # Legacy international
        "IFRIC 12",  # International interpretation
        # --- Fictional/Generic "Debris" IDs ---
        "Guidance No. 123",  # Generic Guidance object
        "Standard 999-A",  # Generic Standard with letter suffix
        "Opinion No. 45-B",  # Accounting Board Opinion style
        "Bulletin 2025",  # Bulletin style
        "Codification 815-10-05",  # Deep sub-topic mapping
    ]

    for id in ids:
        # sub() returns an empty string if the ID matches the pattern perfectly
        stripped = STANDARD_ID_REGEX.sub("", id).strip()
        if stripped:
            print(f"FAILED TO STRIP: '{id}' (Remaining: '{stripped}')")
        else:
            print(f"SUCCESSFULLY STRIPPED: '{id}'")
