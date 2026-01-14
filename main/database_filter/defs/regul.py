# =============================================================================
# REGULATORY NOISE LISTS (SPLIT)
# =============================================================================

# 1. STRICT: Specific Acts, Laws, & Banking Metrics
# Value: 2 Points Each
# Reasoning: Naming a specific Act usually implies a "Regulatory Environment" section.
from defs.regex_lib import build_regex


REGULATORY_KEYWORDS_STRICT = [
    # Specific US Acts
    r"Dodd[- ]Frank",
    r"Volcker\s+Rule",
    r"Sarbanes[- ]Oxley",
    r"JOBS\s+Act",
    r"CARES\s+Act",
    r"Commodity\s+Exchange\s+Act",
    r"Securities\s+Exchange\s+Act",
    r"Regulation\s+AB",
    r"Federal\s+Reserve",
    # --- NEW: Energy & Environmental Acts ---
    r"Energy\s+Policy\s+Act",
    r"Clean\s+Air\s+Act",
    r"Clean\s+Water\s+Act",
    r"Oil\s+Pollution\s+Act",
    r"\bCERCLA\b",  # Superfund
    r"\bRCRA\b",  # Resource Conservation and Recovery Act
    r"\bNEPA\b",  # National Environmental Policy Act
    # International / Banking Standards
    r"Basel\s+(?:I|II|III|IV)",
    r"EMIR",  # European Market Infrastructure Regulation
    r"MiFID",  # Markets in Financial Instruments Directive
    r"Solvency\s+II",
    # Specific Banking Metrics (High likelihood of capital adequacy sections)
    r"capital\s+adequacy",
    r"liquidity\s+coverage\s+ratio",
    r"regulatory\s+(?:capital|environment)",
    r"risk[- ]weighted\s+assets?",  # RWA
    # --- Agencies (If not already caught by Entity Exclusion) ---
    r"\bEPA\b",  # Environmental Protection Agency
    r"\bFERC\b",  # Federal Energy Regulatory Commission
    r"\bDOT\b",  # Department of Transportation (Pipeline regs)
]

# 2. LOOSE: General Compliance Terminology
# Value: 1 Point Each
# Reasoning: "Regulations" or "SEC" can appear in valid context ("Filed with SEC").
# Requires density to trigger discard.
REGULATORY_KEYWORDS_LOOSE = [
    r"regulations?",
    r"regulatory\s+(?:requirements?|compliance|authorit(?:y|ies)|bod(?:y|ies)|agenc(?:y|ies)|frameworks?|matters?|reforms?)",
    r"subject\s+to\s+(?:regulation|oversight|regulatory)",
    r"governmental\s+regulations?",
    r"govern(?:ing|ed|s|ors?)?",
    r"penalt(?:y|ies)",
    r"(?:state|local|federal|international|government)\s+laws?",
    r"statutes?",
    r"oversight",
    r"\bSEC\b",  # Securities and Exchange Commission
    r"\bCFTC\b",  # Commodity Futures Trading Commission
    r"\bFCA\b",  # Financial Conduct Authority
    # --- NEW: Environmental Compliance ---
    r"civil\s+(?:penalt(?:y|ies)|fines?|sanctions?|actions?|proceedings?)",
    r"criminal\s+(?:penalt(?:y|ies)|fines?|sanctions?|actions?|proceedings?)",
    r"administrative\s+(?:penalt(?:y|ies)|fines?|sanctions?|proceedings?)",
    r"enforcement\s+(?:authority|actions?|proceedings?)",
    r"violations?\s+of",
    r"fines?\s+and\s+penalt(?:y|ies)",
    r"sanctions?",
    r"disgorgement",
    r"investigations?",
    r"anti[- ]market\s+manipulation",
    r"third\s+party\s+claims?",
    r"auditor",
    r"audits?",
    # --- NEW: Environmental Compliance ---
    r"environmental\s+(?:laws?|regulations?|matters?|compliance|protection|liabilit(?:y|ies))",
    r"greenhouse\s+gas(?:es)?",
    r"carbon\s+dioxide",
    r"emissions?",
    r"discharges?",
    r"hazardous\s+(?:substances?|wastes?|materials?)",
    r"remediat(?:ion|ing|e)",
    r"spill\s+prevention",
    r"contamination",
    r"pollutants?",
]
EXCLUDE_REGEX_REGULATORY_STRICT = build_regex(REGULATORY_KEYWORDS_STRICT)
EXCLUDE_REGEX_REGULATORY_LOOSE = build_regex(REGULATORY_KEYWORDS_LOOSE)

def is_regulatory_noise(text: str, threshold: int = 4) -> bool:
    """
    Determines if text is regulatory boilerplate using a scoring system.

    Scoring Logic (Threshold = 4):
    - Strict Matches (Specific Acts like Dodd-Frank): 2 points
    - Loose Matches (General words like 'Regulation'): 1 point

    Examples:
    - "We comply with Dodd-Frank (2) and EMIR (2)." -> 4 pts -> Discard.
    - "Subject to regulation (1) by the SEC (1)." -> 2 pts -> Keep (Valid Context).
    - "Governmental regulations (1) governing (1) the SEC (1) oversight (1)." -> 4 pts -> Discard.
    """

    # 1. DEFINE WEIGHTS
    W_STRICT = 2
    W_LOOSE = 1

    # 2. COUNT MATCHES
    strict_hits = len(EXCLUDE_REGEX_REGULATORY_STRICT.findall(text))
    loose_hits = len(EXCLUDE_REGEX_REGULATORY_LOOSE.findall(text))

    # 3. CALCULATE SCORE
    score = (strict_hits * W_STRICT) + (loose_hits * W_LOOSE)

    return score >= threshold
