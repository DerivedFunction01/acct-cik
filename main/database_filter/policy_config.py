# policy_config.py

from typing import List, Dict, Any, Tuple

from derivative_regex import ACCOUNTING_STANDARDS_KEYWORDS, PNL_ONLY_NO_POSITION

# =============================================================================
# GLOBAL EXTRACTION CONFIGURATION
# =============================================================================

DEFAULT_EXTRACTION_CONFIG: Dict[str, Any] = {
    "DB_PATH": "web_data.db",
    "OUTPUT_PARQUET_PATH_BASE": "policy_extraction_batch",
    "TABLE_NAME": "webpage_result",
    "COLUMN_NAME": "matches",
    "MAX_SAMPLES_PER_FILING": 10,
    "MAX_FILINGS_TO_SAMPLE": 15000,
    "RANDOM_SEED": 82,
}

# =============================================================================
# POLICY KEYWORD DEFINITIONS (Stored as Tuples for Immutability)
# =============================================================================
RECLASSIF_TERM_OPTIONAL = r"(?:reclassif(?:y|ies|ied|ication))?"
AOCI_FULL_NAME = r"other\s+comprehensive\s+(?:income|loss)"
POLICY_KEYWORD_SETS: Dict[str, Tuple[str, List[str]]] = {
    # -------------------------------------------------------------------------
    # CATEGORY 1: VALUATION & FAIR VALUE HIERARCHY
    # Focus: Methodology and inputs (Excludes dollar signs/numbers in search)
    # -------------------------------------------------------------------------
    "fair_value_hierarchy": (
        "policy_fv",  # Short label prefix for the output
        [
            r"\bLevel\s+[123]\b",
            r"\bmark[- ]to[- ]market\b",
            r"\bvaluation\s+models?\b",
            r"\bobservable\s+inputs?\b",
            r"\bunobservable\s+inputs?\b",
            r"\bdiscounted\s+cash\s+flow\b",
            r"\bnet\s+asset\s+value\b",
            r"\bsignificant\s+judgment\b",
            r"\bmarket\s+quotations?\b",
            r"\bevaluated using\b",
        ],
    ),
    # -------------------------------------------------------------------------
    # CATEGORY 2: HEDGE DOCUMENTATION & EFFECTIVENESS
    # Focus: Compliance, testing, and qualifying status
    # -------------------------------------------------------------------------
    "hedge_documentation": (
        "policy_doc",
        [
            # Core Hedge Type & Criteria (Existing)
            r"\bhedge\s+effectiveness\b",
            r"\bprospective\s+assessment\b",
            r"\bretrospective\s+assessment\b",
            r"\bcritical\s+terms\b",
            r"\bdesignate(?:d|s|ing)\s+as\b",
            r"\bcash\s+flow\s+hedge\b",
            r"\bfair\s+value\s+hedge\b",
            r"\bnet\s+investment\s+hedge\b",
            # New Documentation & Strategy Terms
            r"\bformal(?:ly)?\s+document\b",
            r"\brisk\s+management\s+strateg(?:y|ies)?\b",
            r"\brisk\s+management\s+objective\b",
            r"\btest(?:s|ed|ing)?\s+of\s+effectiveness\b",
            r"\bassessment(?:s)?\s+of\s+effectiveness\b",
            # New Accounting & Outcome Terms
            r"\bineffective(?:ness)?\s+portion\b",
            r"\bdeferred\s+(?:gain|loss)\b",
            r"\bother\s+comprehensive\s+income\b",  # OCI
            r"\bAOCI\b",  # Common abbreviation
            # New Termination/Discontinuation Terms
            r"\bdiscontinu(?:e|ed|ation)\b",
            r"\bdedesignat(?:e|ed|ion)\b",
            r"\bno\s+longer\s+probable\b",
            r"\bceas(?:e|ed)\s+hedge\s+accounting\b",
        ],
    ),
    # -------------------------------------------------------------------------
    # CATEGORY 3: STANDARDS & ADOPTION BOILERPLATE
    # Focus: Regulatory guidance and future action (Non-use statements)
    # -------------------------------------------------------------------------
    "adoption_boilerplate": ("policy_adopt", ACCOUNTING_STANDARDS_KEYWORDS),
    # -------------------------------------------------------------------------
    # CATEGORY 4: STANDARDS & ADOPTION BOILERPLATE
    # Focus: Regulatory guidance and future action (Non-use statements)
    # -------------------------------------------------------------------------
    "aoci_reclassification": (
        "policy_aoci",
        [
            # 1. CORE AOCI MATCH (MANDATORY)
            r"\bAOCI\b",  # Match "AOCI" acronym
            rf"\b{AOCI_FULL_NAME}\b",  # Match "Other Comprehensive Income/Loss" full name
            # 2. OPTIONAL RECLASSIFICATION CONTEXT
            rf"\b{RECLASSIF_TERM_OPTIONAL}\b.*?(?:AOCI|{AOCI_FULL_NAME})\b",  # e.g., "reclassification...AOCI"
            rf"(?:AOCI|{AOCI_FULL_NAME})\b.*?\b{RECLASSIF_TERM_OPTIONAL}\b",  # e.g., "AOCI...reclassified"
            # 3. OTHER HIGH-PRECISION POLICY TERMS
            r"\bnet\s+deferred\s+tax\s+benefit\b",
            r"\bincluded\s+in.*AOCI\b",
            rf"\bdeferred\s+(?:gain|loss).*?(?:AOCI|{AOCI_FULL_NAME})\b",
            r"\bestimated\s+to\s+be\s+reclassified\b",
            r"\bumbrella\s+provisions\b",
        ],
    ),
    "references": (
        "reference_notes",
        [
            # --- NOTE REFERENCES ---
            # Variation 1: See Note X / See Note (X)
            r"[Ss]ee\s+(?:Note|NOTE)\s+(?:No\.\s+)?\d+[A-Z]?(?:\s*\(s\))?(?:\s*[,;:]\s+as\s+used\s+herein)?(?:\s*[,;:\.]?\s*\(?(?:of|and|in)\s+the\s+notes)?\b",
            # Variation 2: Refer to Note X / Reference is made to Note X
            r"(?:[Rr]efer(?:ence)?\s+(?:to|is\s+made\s+to|is\s+hereby\s+made\s+to))\s+(?:Note|NOTE)\s+(?:No\.\s+)?\d+[A-Z]?\b",
            # Variation 3: In Note X
            r"\b[Ii]n\s+(?:Note|NOTE)\s+(?:No\.\s+)?\d+[A-Z]?\b",
            # Variation 4: Note X provides... / Note X details...
            r"\b(?:Note|NOTE)\s+(?:No\.\s+)?\d+[A-Z]?\s+(?:provides?|details?|discloses?|discusses?)\b",
            # --- TABLE / SCHEDULE REFERENCES ---
            # Variation 1: The table/schedule refers to/shows/summarizes...
            r"[Tt]he\s+(?:table|schedule|exhibit|note)\s+(?:below|above|following|accompanying)?\s*(?:[Rr]efers\s+to|[Pp]rovides\s+details\s+on|[Pp]resents|[Ss]hows|[Ss]ummarizes|[Dd]etails|[Ii]s\s+presented)\b",
            # Variation 2: As shown/provided/detailed in the table/schedule
            r"(?:[Aa]s\s+(?:shown|provided|detailed|presented|summarized|disclosed|set\s+forth)?\s+in\s+the\s+(?:table|schedule|exhibit|note))\b",
            # Variation 3: In the table/schedule below/above
            r"[Ii]n\s+(?:the\s+)?(?:table|schedule|exhibit|note)\s+(?:below|above|following)\b",
            # Variation 4: Punctuation/Word separation followed by a table reference
            r"(?:[.,;:\-\s]|\s+and\s+)\s*(?:table|schedule|exhibit|note)\s+No\.\s+\d+\b",
        ],
    ),
}
