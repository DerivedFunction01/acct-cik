# policy_config.py

from typing import List, Dict, Any, Tuple

from derivative_regex import ACCOUNTING_STANDARDS_KEYWORDS

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
}
