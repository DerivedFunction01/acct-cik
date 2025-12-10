import re
from derivative_regex import ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN, EXHIBIT_FRAGMENT, STANDARD_ID_REGEX, YEAR_REGEX, build_regex
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

        # Step 3: Apply other cleanups (no quant conflict)
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
        text = self.clean_for_quant_analysis(text, remove_years)
        text = self.clean_entities(text)
        return text

from enum import Enum
class Reason(Enum):
    # --- Nothing here
    pass

def get_tag(token_type: str, reason: Reason | str) -> str:
    return f"{token_type}<{reason.value if isinstance(reason, Reason) else reason}>"

class NoiseReason(Reason):
    # --- Structural / Formatting --- (sentence level)
    REF = "REF"  # Navigational Reference ("See Note 5")
    DEF = "DEF"  # Definition ("Swap shall mean...")
    AOCI = "AOCI"  # AOCI ("recorded in AOCI") (Note: AOCI + Termination is an instant killer)
    PNL = "PNL" # PNL, but no quantitaive action. Probably fair valuation inputs
    NPNS = "NPNS"  # Normal Purchases / Sales
    NC = "NC" # Non derivative commodity contracts
    LOAN = "LOAN"  # Embedded Loan Features

    # --- Business Logic / Signals ---
    TRADING = "TRADING"  # Trading Denial ("We do not trade")
    POLICY = "POLICY"  # Accounting Policy ("Formal Documentation of a hedge")
    CREDIT = "CREDIT"  # Counterparty Risk ("Credit exposure, counterparty risk")

    # --- Scoring ---
    CONTRACT = "CONTRACT"  # Contractual Boilerplate Score
    REG = "REG"  # Regulatory Boilerplate Score
    HYP_SCORE = "HYP_SCORE"  # Hypothetical Simulation/Derivative Score
    BANK = "BANK"  # Banking
    LIBOR = "LIBOR"  # LIBOR Transition

    # --- Classification Killers --- (or sentence level indicators)
    TIME = "TIME"  # Historical / Temporal
    HYPO = "HYPO"  # Hypothetical / Potential
    NEG = "NEG"  # Negative Intent
    TERM = "TERM"  # Termination / Expiration
    ZERO = "ZERO"  # Quantitative Zero

    # --- Paragraph Level ---
    HIST_BLOCK = "HIST_BLOCK" # The entire block was discard as history
    ANLZ = "ANLZ"  # Generic Deadweight: Requires scanning internal tags for attributes
    FILING = "FILING"  # 10-K Headers
    FORWARD = "FORWARD"  # Safe Harbor / Forward Looking
    LEGAL = "LEGAL"  # Litigation
    PLAN = "PLAN"  # Pension Plans
    NON_FIN = "NON_FIN"  # Non-Financial (Plasma, Chemical)
    COMP = "COMP"  # Competitors
    ACCT_STD = "ACCT_STD"  # Accounting Standards

    # --- Firm Level ---
    HEDGE_FAIL = "NO_HEDGE"  # No indication of hedging
    NO_SOPH = "NO_SOPH"  # No indication of convertible/warrants as derivatives


class EvidenceReason(Reason):
    # =========================================================
    # TIER 1: STRONG (The "Smoking Gun")
    # Criteria: Strict Subject ("Swap") + Hard Anchor (Year/Value)
    # Survival: Overrides ALL Noise.
    # =========================================================
    AS_YEAR = "ACTIVE_STATE_YEAR"  # "Swaps outstanding at Dec 31, 2024"
    MAT_FUT = "MATURITY_FUTURE"  # "Swaps mature in 2026"
    NVY = "NOTIONAL_VALUE_YEAR"  # "Notional was $100M in 2024"
    FVY = "FAIR_VALUE_YEAR"  # "Fair Value of Swaps was $5M in 2024"

    # Special Survives history but dies to termination only
    ACT_YEAR = "TRANSACTION_YEAR"  # "Entered into Swaps in 2024" 

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

# --- LOGIC SETS ---

# TIER 1: STOCK EVIDENCE (Titanium)
# Immune to: History, Termination, Policy, Negation.
# Logic: If I have it at Year-End 2024, it doesn't matter if I terminated others or had old ones.
STRONG_EVIDENCE = {
    EvidenceReason.AS_YEAR,  # "Outstanding at Dec 31, 2024"
    EvidenceReason.MAT_FUT,  # "Matures in 2026"
    EvidenceReason.NVY,  # "Notional was $100M at Dec 31, 2024"
    EvidenceReason.FVY,  # "Fair Value was $5M at Dec 31, 2024"
}

# TIER 1.5: FLOW EVIDENCE (Conditional Strong)
# Immune to: History (TIME), Policy (POLICY).
# Dies to: Termination (TERM)
# Logic: "Entered in 2024" overrides "2019 history" or no other "oustanding positions", but dies if "Terminated" in same breath.
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
    EvidenceReason.FVNY,  # "Fair Value is $5M"
    EvidenceReason.BS_LOC,  # "Recorded in Earnings"
    # Weak Subject / Anchored (The "Ambiguous" Duals)
    EvidenceReason.ASAIY,  # "Contracts outstanding 2024"
    EvidenceReason.MAT_AMB_FUT,  # "Agreements mature in 2026"
    EvidenceReason.FVAIY,  # "FV of Contracts was $5M in 2024"
    EvidenceReason.ACT_AMB_YEAR,  # "Entered contracts in 2024"
    EvidenceReason.VAL_MODEL,  # Black Scholes, etc
}

# TIER 3: WEAK EVIDENCE (Policy Prone)
# Dies to: Policy (POLICY), Definitions (DEF), Boilerplate.
POLICY_KILLED_EVIDENCE = {
    EvidenceReason.ACT_GEN,  # "We enter into..." (No year)
    EvidenceReason.CONT_USE_AMB,  # "We use contracts..." (No year, Weak Subject)
    EvidenceReason.FVAINY,  # "FV of Contract is..."
}

# TIER 4: FLUFF (Context Only)
# Dies to: Any Noise.
FLUFF_EVIDENCE = {
    EvidenceReason.PNL_REC,
    EvidenceReason.REM_TERM,
}

# --- KILLER SETS ---
FLOW_KILLERS = {
    NoiseReason.TERM,  # "Terminated"
}

# Standard Killers for TIER 2 (Medium)
# Includes everything in Flow Killers + Time/History
TIME_KILLERS = FLOW_KILLERS | {
    NoiseReason.TIME,  # "In 2019..."
    NoiseReason.HIST_BLOCK,  # "Historically..."
    NoiseReason.HYPO,  # "Hypothetical..."
    NoiseReason.NEG,  # "Did not enter"
    NoiseReason.ZERO,  # "Zero value"
}

# Expanded Killers for TIER 3 (Weak)
# Includes everything above + Policy/Definitions
POLICY_KILLERS = TIME_KILLERS | {
    NoiseReason.POLICY,  # "Our policy is..."
    NoiseReason.DEF,  # "Swap shall mean..."
    NoiseReason.ACCT_STD,  # "FASB ASU..."
    NoiseReason.REF,  # "See Note 5"
    NoiseReason.TRADING,  # "We do not trade"
}

class DerivativeAttribute(Enum):
    # --- DESIGNATIONS (ASC 815 & SEC Portfolios) ---
    # The text distinguishes explicitly between "Trading" and "Other than Trading"[cite: 347, 355].
    # Within "Other than Trading," firms designate specific accounting hedges (CFH, FVH).
    TRADING = "TRD"  # "Instruments entered into for trading purposes"
    CASH_FLOW_HEDGE = "CFH"  # Hedging variability in cash flows 
    FAIR_VALUE_HEDGE = "FVH"  # Hedging changes in fair value 
    NET_INVESTMENT_HEDGE = "NIH"  # Hedging foreign currency exposure of net investment (implied by translation risk discussions )
    UNDESIGNATED = (
        "UND"  # Economic hedges not designated for hedge accounting 
    )

    # --- ACCOUNTING METHODS ---
    # The text notes that FASB 133 (ASC 815) largely superseded Deferral/Accrual,
    # but firms must still disclose these policies if material.
    FAIR_VALUE_ACCOUNTING = "FVA"  # "Derivatives are carried on the balance sheet at fair value" 
    DEFERRAL_METHOD = (
        "DFM"  # Gains/losses deferred and recognized with hedged item 
    )
    ACCRUAL_METHOD = (
        "ACM"  # Net payment/receipt recognized in earnings (e.g., swaps) 
    )

    # --- SEC DISCLOSURE ALTERNATIVES (Item 305) ---
    # The SEC mandates three specific quantitative disclosure formats.
    TABULAR_PRESENTATION = (
        "TAB"  # "Tabular presentation of fair value information" # Any fair value matches with table anchor
    )
    SENSITIVITY_ANALYSIS = (
        "SEN"  # "Sensitivity analysis... hypothetical changes"
    )
    VALUE_AT_RISK = (
        "VAR"  # "Value at risk analysis estimating potential loss" 
    )

    # --- VALUATION MODELS (For VaR & Fair Value) ---
    # The text explicitly lists these three methods for calculating Value at Risk.
    VARIANCE_COVARIANCE = "VCOV"  # "Variance/Covariance approach" 
    HISTORICAL_SIMULATION = "HSIM"  # "Historical Simulation method" 
    MONTE_CARLO = "MCS"  # "Monte Carlo simulation" 

    # Generic valuation (if needed for non-VaR Fair Value)
    BLACK_SCHOLES = "BSM"  # implied by "probabilistic models" 
    LATTICE_MODEL = (
        "LAT"  # (Binomial) - distinct from BSM, often used for complex options
    )
