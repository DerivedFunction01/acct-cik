import re
from typing import Optional, Set, Tuple
from derivative_regex import COMMODITY_UNIT_PATTERN, CURRENCY_SYMBOL_PATTERN, ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN, EXHIBIT_FRAGMENT, SENTENCE_SPLIT_PATTERN, STANDARD_ID_REGEX, YEAR_REGEX, build_regex
from final_verification import QUANT_REGEX
from notional_filter import DATE_DM_REGEX, DATE_MD_REGEX

# The token to append to deadweight paragraphs.
DEADWEIGHT_TOKEN = "_D"

# Token for sentence-level skips (Base string, will be formatted by get_tag)
SKIP_TOKEN = " _S"

# Token for evidence
EVIDENCE_TOKEN = " _E"
class MinimalTextCleaner:
    """
    Lightweight cleaner that prepares text for quantitative analysis.
    Removes numeric noise that would confuse extract_values_and_years().
    """

    # Bullet/footnote pattern: matches (1), 1), 1., (i), (ii), etc at line/sentence start
    # Simplified since QUANT_REGEX will protect actual monetary values first
    bullet_pattern = re.compile(
        r"(?:(?<=^)|(?<=\s))"  # Start of line OR whitespace
        r"(?:"
        r"\(?\d+\)|\d+\.|\d+:|"  # (1), 1), 1., 1:   <-- added colon
        r"\([ivxlcdm]+\)|[ivxlcdm]+\.|"  # (i), (ii), i., ii. (roman numerals)
        r"\([a-z]\)|[a-z]\.|"  # (a), (b), a., b. (letters)
        r"\([A-Z]\)|[A-Z]\."  # (A), (B), A., B. (capitals)
        r")"
        r"(?=\s)",  # Followed by whitespace
        re.IGNORECASE,
    )

    # Dashed patterns: 1-2, 3-4 (range references)
    dashed_pattern = re.compile(r"\b\d+[-]\d+\b")

    exhibit_pattern = re.compile(
        rf"\b{EXHIBIT_FRAGMENT}\b" r"(?:\s*No\.?)?" r"\s*\d{1,3}\b",
        re.IGNORECASE,
    )

    # Standard IDs: ASC 815-20, IFRS 9, etc.
    standard_id_pattern = STANDARD_ID_REGEX

    def __init__(self):
        pass

    def clean_numerics(self, text: str, remove_years: bool = False) -> str:
        """
        Remove numeric noise that confuses quantitative parsing:
        - Bullet points (1), 1), 1.
        - Dashed ranges (1-2)
        - Dates (Dec 31, 31 December)
        - Exhibit/reference markers (Note 5, Table A)
        - Standard IDs (ASC 815, IFRS 9)

        Safety: QUANT_REGEX is applied FIRST to protect actual monetary values
        like "$ (100)" from being destroyed by the bullet pattern.
        """
        # Step 1: Identify and protect quantitative values
        quant_matches = list(QUANT_REGEX.finditer(text))
        protected_ranges = set()
        for match in quant_matches:
            for i in range(match.start(), match.end()):
                protected_ranges.add(i)

        # Step 2: Apply bullet pattern, but skip protected ranges
        def safe_bullet_sub(match):
            if any(i in protected_ranges for i in range(match.start(), match.end())):
                return match.group(0)  # Keep if protected
            return " "

        text = text.strip()
        text = self.bullet_pattern.sub(safe_bullet_sub, text)

        # Step 3: Apply POLICY cleanups (no quant conflict)
        text = self.dashed_pattern.sub(" ", text)
        text = DATE_MD_REGEX.sub(" ", text)
        text = DATE_DM_REGEX.sub(" ", text)
        text = self.exhibit_pattern.sub(" ", text)
        text = self.standard_id_pattern.sub(" ", text)
        if remove_years:
            text = YEAR_REGEX.sub(" ", text)
        return text

    def normalize_whitespace(self, text: str) -> str:
        """Collapse multiple spaces and newlines."""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def clean_for_quant_analysis(self, text: str, remove_years: bool = False) -> str:
        """
        Prepare text for quantitative zero checking.
        Removes noise that would interfere with extract_values_and_years().

        Pipeline:
        1. Clean numeric noise (bullets, dates, IDs, years if remove_years is true)
        2. Normalize whitespace
        3. Return cleaned text ready for QUANT_REGEX/value extraction
        """
        text = self.clean_numerics(text, remove_years)
        text = self.normalize_whitespace(text)
        return text

    def clean_entities(self, text: str) -> str:
        text = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, text)
        text = self.normalize_whitespace(text)
        return text

    def clean(self, text: str, remove_years: bool = False) -> str:
        texts = []
        for sent in SENTENCE_SPLIT_PATTERN.split(text):
            sent = self.clean_for_quant_analysis(sent, remove_years)
            sent = self.clean_entities(sent)
            texts.append(sent)
        return text

from enum import Enum
class Reason(Enum):
    pass

def get_tag(token_type: str, reason: Reason | str) -> str:
    return f"{token_type}<{reason.value if isinstance(reason, Reason) else reason}>"

class NoiseReason(Reason):
    # --- Structural / Formatting --- (sentence level)
    REF = "REF"  # Navigational Reference ("See Note 5")
    DEF = "DEF"  # Definition ("Swap shall mean...")
    AOCI = "AOCI"  # AOCI ("recorded in AOCI")
    PNL = "PNL" # PNL (gains/losses, change in FV)
    NPNS = "NPNS"  # Normal Purchases / Sales
    LOAN = "LOAN"  # Non derivative interest rate caps and floors on debt
    CTX = "CONTEXT" # Context text
    OTHER = "OTHER"  # Has derivative mention but no Evidence -> Other
    RISK = "RISK" # Risk management text

    # --- Business Logic / Signals ---
    TRADING = "TRADING"  # Trading Denial ("We do not trade")
    DOC = "DOC"  # Hedge Documentation ("Formal Documentation of a hedge")
    CREDIT = "CREDIT"  # Counterparty Risk ("Credit exposure, counterparty risk")

    # --- Scoring ---
    CONTRACT = "CONTRACT"  # Contractual Boilerplate Score (includes certain definition indicators)
    REG = "REG"  # Regulatory Boilerplate Score
    HYP_SCORE = "HYP_SCORE"  # Hypothetical Simulation/Derivative Score
    BANK = "BANK"  # Banking
    LIBOR = "LIBOR"  # LIBOR Transition

    # --- Classification Killers --- (or sentence level indicators)
    TIME = "TIME"  # Historical / Temporal
    POT = "POTENTIAL"  # Hypothetical / Potential
    NEG = "NEG"  # Negative Intent
    TERM = "TERM"  # Termination / Expiration
    ZERO = "ZERO"  # Quantitative Zero

    # --- Paragraph Level ---
    HIST_BLOCK = "HIST_BLOCK" # The entire block was discard as history (legacy/unused)
    ANLZ = "ANLZ"  # Generic Deadweight: Requires scanning internal tags for attributes
    FILING = "FILING"  # 10-K Headers
    FORWARD = "FORWARD"  # Safe Harbor / Forward Looking
    LEGAL = "LEGAL"  # Litigation
    PLAN = "PLAN"  # Pension Plans or Hedge Funds
    NON_FIN = "NON_FIN"  # Non-Financial (Plasma, Chemical)
    COMP = "COMP"  # Competitors
    ACCT_STD = "ACCT_STD"  # Accounting Standards
    NC = "NC"  # Non derivative commodity contracts (No hedging context anywhere)

    # 1. Historical / Temporal
    DEAD_HIST_TERM = "DEAD_HISTORICAL_TERMINATION"  # "In 2019, we terminated..."
    DEAD_HIST_NEG = (
        "DEAD_HISTORICAL_ABSENCE"  # "At Dec 31, 2020, we had no derivatives."
    )

    # 2. Strategy / Non-Use
    DEAD_STRAT_VOID = (
        "DEAD_STRATEGY_VOID"  # "We may use... we do not hold." (Strategic Non-User)
    )
    DEAD_RISK_GEN = (
        "DEAD_RISK_GENERIC"  # "We manage risk via diversification." (No derivatives)
    )

    # 3. Accounting Boilerplate
    DEAD_POL_MECH = "DEAD_POLICY_MECHANICS"  # "Gains are recorded in OCI."
    DEAD_POL_DEF = "DEAD_POLICY_DEFINITION"  # "Swaps are defined as..."
    DEAD_POL_STD = "DEAD_POLICY_STANDARD"  # "ASC 815 requires..."

    # 4. Empty Flow
    DEAD_FLOW_NIL = "DEAD_FLOW_NIL"  # "The effect was nil."

    # --- Firm Level ---
    HEDGE_FAIL = "NO_HEDGE"  # No indication of hedging (Fails stage 1 prefilter_database)
    NO_SOPH = "NO_SOPH"  # No indication of convertible/warrants as derivatives


class EvidenceReason(Reason):
    MGMTD = "MGMT_DER"  # Risk managment paragraph with intent of using derivatives (no quant)
    MGMTDQ = "MGMT_DER_QUANT"  # Risk managment paragraph with intent of using derivatives (with quant)
    POSDQ = "DER_QUANT" # Standard valuation of derivative paragraph (quant, have strong evidence)
    # =========================================================
    # TIER 1: STRONG (The "Smoking Gun")
    # Criteria: Strict Subject ("Swap") + Hard Anchor (Year/Value)
    # Survival: Overrides ALL Noise.
    # =========================================================
    AS_YEAR = "ACTIVE_STATE_YEAR"  # "Swaps outstanding at Dec 31, 2024"
    MAT_FUT = "MATURITY_FUTURE"  # "Swaps mature in 2026"
    NVY = "NOTIONAL_VALUE_YEAR"  # "Notional was $100M in 2024"
    FVY = "FAIR_VALUE_YEAR"  # "Fair Value of Swaps was $5M in 2024"
    VY = "VALUE_YEAR"  # "Value of Swaps was $5M in 2024

    # Special Survives history but dies to termination only
    ACT_YEAR = "TRANSACTION_YEAR"  # "Entered into Swaps in 2024" 
    TABLE = "TABLE" # Table usually refers to current usage

    # =========================================================
    # TIER 2: MEDIUM (The "Solid State")
    # Criteria:
    #   A. Strict Subject + General State ("We hold Swaps")
    #   B. Weak Subject + Hard Anchor ("Contracts outstanding in 2024")
    #   C. Self-Validating ("Recorded in Earnings")
    # Survival: Dies to TIME, NEG, TRADING. Survives POLICY.
    # =========================================================

    # Group A: Strict Subject / General State
    CONT_USE = "CONTINUOUS_USAGE"  # "We use Swaps to hedge" (Strict)
    NVNY = "NOTIONAL_NO_YEAR"  # "Notional is $100M"
    FVNY = "FAIR_VALUE_NO_YEAR"  # "Fair Value of Swaps is $5M"
    VNY = "VALUE_NO_YEAR"  # "Value of Swaps was $5M
    VAL_MODEL = "VALUATION_MODEL" # Black Scholes, etc

    # Group B: Weak Subject / Hard Anchor (The "Ambiguous" Duals)
    ASAIY = "ACTIVE_STATE_AMB_YEAR"  # "Contracts outstanding at Dec 31, 2024"
    MAT_AMB_FUT = "MAT_AMB_FUTURE"  # "Agreements mature in 2026"
    FVAIY = "FAIR_VALUE_AMB_YEAR"  # "Fair Value of Contracts was $5M in 2024"
    ACT_AMB_YEAR = "TRANSACTION_AMB_YEAR"  # "Entered into Contracts in 2024"

    # Group C: Self-Validating
    BS_LOC = "BALANCE_SHEET_LOC"  # "Recorded in Earnings" (Implies existence)

    # =========================================================
    # TIER 3: WEAK (The "Policy Prone")
    # Criteria: Weak Subject ("Contracts") OR Generic Actions
    # Survival: Dies to POLICY, DEFINITIONS, BOILERPLATE.
    # =========================================================
    ACT_GEN = "TRANSACTION_GENERIC"  # "We enter into Swaps" (No year)
    CONT_USE_AMB = "CONTINUOUS_USAGE_AMB"  # "We use Contracts" (Weak Subject)
    FVAINY = "FAIR_VALUE_AMB_NO_YEAR"  # "Fair Value of Contracts is $5M"

    # =========================================================
    # TIER 4: FLUFF (Context Only)
    # Criteria: PnL descriptions, Terms
    # Survival: Dies to ANY Noise.
    # =========================================================
    PNL_REC = "PNL_RECOGNITION"
    REM_TERM = "REMAINING_TERM"
    UNCAT = "UNCATEGORIZED"

# --- LOGIC SETS ---

# TIER 1: STOCK EVIDENCE (Titanium)
# Immune to: History, Termination, Policy, Negation.
# Logic: If I have it at Year-End 2024, it doesn't matter if I terminated POLICYs or had old ones.
STRONG_EVIDENCE = {
    EvidenceReason.AS_YEAR,  # "Outstanding at Dec 31, 2024"
    EvidenceReason.MAT_FUT,  # "Matures in 2026"
    EvidenceReason.NVY,  # "Notional was $100M at Dec 31, 2024"
    EvidenceReason.FVY,  # "Fair Value was $5M at Dec 31, 2024"
    EvidenceReason.VY  # "Value was $5M at Dec 31, 2024"
}

# TIER 1.5: FLOW EVIDENCE (Conditional Strong)
# Immune to: History (TIME), Policy (POLICY).
# Dies to: Termination (TERM)
# Logic: "Entered in 2024" overrides "2019 history" or no POLICY "oustanding positions", but dies if "Terminated" in same breath.
FLOW_EVIDENCE = {
    EvidenceReason.ACT_YEAR,  # "Entered into Swaps in 2024"
}

# TIER 2: MEDIUM EVIDENCE (Standard State)
# Dies to: History (TIME) AND Termination (TERM).
# Logic: Without a specific year, any mention of "History" or "Termination" poisons the well.
TIME_KILLED_EVIDENCE = {
    # Strict Subject / Yearless
    EvidenceReason.CONT_USE,  # "We hold/use Swaps" (No year)
    EvidenceReason.NVNY,  # "Notional is $100M"
    EvidenceReason.VNY,  # " Value is $5M"
    EvidenceReason.FVNY,  # "Fair Value is $5M"
    EvidenceReason.BS_LOC,  # "Recorded in Earnings"
    # Weak Subject / Anchored (The "Ambiguous" Duals): There is no derivative mention within the same paragraph.
    EvidenceReason.ASAIY,  # "Contracts outstanding 2024"
    EvidenceReason.MAT_AMB_FUT,  # "Agreements mature in 2026"
    EvidenceReason.FVAIY,  # "FV of Contracts was $5M in 2024"
    EvidenceReason.ACT_AMB_YEAR,  # "Entered contracts in 2024"
    EvidenceReason.VAL_MODEL,  # Black Scholes, etc
}

# TIER 3: WEAK EVIDENCE (Policy Prone)
# Dies to: Policy (POLICY), Definitions (DEF), Boilerplate.
POLICY_KILLED_EVIDENCE = {
    EvidenceReason.CONT_USE_AMB,  # "We use contracts..." (No year, Weak Subject)
    EvidenceReason.FVAINY,  # "FV of Contract is..."
    EvidenceReason.ACT_GEN,  # "We enter into..." (No year)
}

# TIER 4: FLUFF (Context Only)
# Dies to: Any Noise.
FLUFF_EVIDENCE = {
    EvidenceReason.PNL_REC,
    EvidenceReason.REM_TERM,
    EvidenceReason.UNCAT
}

# --- KILLER SETS ---
FLOW_KILLERS = {
    NoiseReason.TERM,  # "Terminated"
}

# Standard Killers for TIER 2 (Medium)
# Includes everything in Flow Killers + Time/History
TIME_KILLERS = FLOW_KILLERS | {
    NoiseReason.TIME,  # "In 2019..."
    NoiseReason.HIST_BLOCK,  # Entire paragraph is marked as historical (legacy)
    NoiseReason.POT,  # "We periodically use..."
    NoiseReason.NEG,  # "Did not enter"
    NoiseReason.ZERO,  # "Zero value"
}

# Expanded Killers for TIER 3 (Weak)
# Includes everything above + Policy/Definitions
POLICY_KILLERS = TIME_KILLERS | {
    NoiseReason.DOC,  # "Hedge documentation is..."
    NoiseReason.DEF,  # "Swap shall mean..."
    NoiseReason.ACCT_STD,  # "FASB ASU..."
    NoiseReason.REF,  # "See Note 5"
    NoiseReason.TRADING,  # "We do not trade"
    NoiseReason.PNL,  # An unrealized gain
    NoiseReason.AOCI,  # "Recorded in AOCI"
}


NOISE_TAG_PARSER = re.compile(r"(_[SD])<([^>]+)>")

def mark_as_deadweight(
    text: str,
    noise: Optional[Set[NoiseReason]] = None,
) -> str:
    """
    Marks paragraph as deadweight with a specific semantic reason derived from its tags.
    """
    final_reason = NoiseReason.ANLZ  # Default fallback
    if not noise:
        # If dead but no noise tags (rare, implies Orphan Kill rule), use ANLZ
        return f"{get_tag(DEADWEIGHT_TOKEN, final_reason)} {text}"

    # --- TIER 1: TEMPORAL NUANCE (The "Timeline") ---
    # Distinguish "Former User" (Terminated) from "Former Non-User" (Absence)
    if not noise.isdisjoint({NoiseReason.TIME, NoiseReason.HIST_BLOCK}):
        if NoiseReason.TERM in noise:
            final_reason = NoiseReason.DEAD_HIST_TERM  # "In 2019, we terminated..."
        elif NoiseReason.NEG in noise:
            final_reason = NoiseReason.DEAD_HIST_NEG  # "In 2019, we had none."
        else:
            final_reason = NoiseReason.HIST_BLOCK  # Generic history

    elif NoiseReason.NEG in noise:
        # Check for the "Strategic Non-Use" combo (Potential + Absence)
        # "We may enter... we currently do not hold."
        if NoiseReason.POT in noise:
            final_reason = NoiseReason.DEAD_STRAT_VOID
        else:
            final_reason = NoiseReason.NEG  # Simple Absence

    # --- TIER 3: SPECIFIC EVENTS ---
    elif NoiseReason.TERM in noise:
        final_reason = NoiseReason.TERM  # Current year termination

    # --- TIER 4: RISK MANAGEMENT CONTEXT ---
    # Removed MGMTND from input check. Now relies on RISK (generic) and POT (potential).
    elif not noise.isdisjoint({NoiseReason.RISK, NoiseReason.POT}):
        # "We manage risk via cash reserves" OR "We may hedge in the future"
        final_reason = NoiseReason.DEAD_RISK_GEN
    # --- TIER 2: EXPLICIT FIRM STATUS ---
    elif NoiseReason.TRADING in noise:
        final_reason = NoiseReason.TRADING  # "We do not trade"
    # --- TIER 5: FINANCIAL MECHANICS (Policy without Numbers) ---
    elif NoiseReason.ZERO in noise:
        final_reason = NoiseReason.DEAD_FLOW_NIL  # "Immaterial amount"

    # Check for PnL/AOCI policy (Mechanics)
    elif not noise.isdisjoint({NoiseReason.PNL, NoiseReason.AOCI}):
        final_reason = NoiseReason.DEAD_POL_MECH  # "Changes are recorded in..."

    # --- TIER 6: PURE BOILERPLATE ---
    elif not noise.isdisjoint({NoiseReason.DEF, NoiseReason.DOC}):
        final_reason = NoiseReason.DEAD_POL_DEF  # "Swaps are defined as..."

    elif NoiseReason.ACCT_STD in noise:
        final_reason = NoiseReason.DEAD_POL_STD  # "ASC 815 requires..."

    elif NoiseReason.REF in noise:
        final_reason = NoiseReason.REF

    # Apply the specific tag
    return f"{get_tag(DEADWEIGHT_TOKEN, final_reason)} {text}"


def parse_noise_tags(text: str) -> Tuple[str, Set[NoiseReason]]:
    """Extract existing noise tags from text."""
    noise_tags = set()

    matches = list(NOISE_TAG_PARSER.finditer(text))
    if not matches:
        return text.strip(), noise_tags

    for m in matches:
        token_type = m.group(1)
        reason_str = m.group(2)

        if token_type == SKIP_TOKEN.strip():
            try:
                noise_tags.add(NoiseReason(reason_str))
            except ValueError:
                pass

    text = NOISE_TAG_PARSER.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)

    return text, noise_tags


NUMBER_PATTERN = r"(?:0\.\d+|(?:[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)(?:\.\d+)?)"
SCALE_WORDS = r"(?:million|billion|trillion|thousand)"
QUANT_REGEX = re.compile(
    # Currency symbol + optional parens + number + optional parens
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*\(?\s*{NUMBER_PATTERN}\s*\)?|"
    # Number + optional parens + currency symbol
    rf"\(?\s*{NUMBER_PATTERN}\s*\)?\s*(?:{CURRENCY_SYMBOL_PATTERN})|"
    # Currency + number + scale word
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s+{NUMBER_PATTERN}\s+{SCALE_WORDS}|"
    # Number + optional scale word + commodity unit
    rf"{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?\s+{COMMODITY_UNIT_PATTERN}|"
    rf"{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?\s+shares|"
    # Tabular data
    rf"(?:amount|value)\s+of\s+{NUMBER_PATTERN}",
    re.IGNORECASE,
)
