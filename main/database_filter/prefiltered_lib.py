import re
from derivative_regex import ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN, EXHIBIT_FRAGMENT, STANDARD_ID_REGEX, YEAR_REGEX
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
class NoiseReason(Reason):
    # --- Structural / Formatting ---
    REF = "REF"  # Navigational Reference ("See Note 5")
    DEF = "DEF"  # Definition ("Swap shall mean...")
    PNL = "PNL"  # PnL/AOCI ("Gain of $5M")
    NPNS = "NPNS"  # Normal Purchases / Sales
    LOAN = "LOAN"  # Embedded Loan Features

    # --- Business Logic / Signals ---
    TRADING = "TRADING"  # Trading Denial ("We do not trade")
    POLICY = "POLICY"  # Accounting Policy ("Designated as hedge")
    CREDIT = "CREDIT"  # Counterparty Risk ("Credit exposure")

    # --- Scoring ---
    CONTRACT = "CONTRACT"  # Contractual Boilerplate Score
    REG = "REG"  # Regulatory Boilerplate Score
    HYP_SCORE = "HYP_SCORE"  # Hypothetical Score
    BANK = "BANK"  # Banking
    LIBOR = "LIBOR"  # LIBOR Transition

    # --- Classification Killers ---
    TIME = "TIME"  # Historical / Temporal
    HYPO = "HYPO"  # Hypothetical / Potential
    NEG = "NEG"  # Negative Intent
    TERM = "TERM"  # Termination / Expiration
    ZERO = "ZERO"  # Quantitative Zero

    # --- Paragraph Level ---
    HIST_BLOCK = "HIST_BLOCK"
    BOILER_BLOCK = "BOILER_BLOCK"
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
    # --- QUANTITATIVE (The Gold Standard) ---
    NVY = "NOTIONAL_VALUE_YEAR"  # "Notional was $100M in 2024"
    FVY = "FAIR_VALUE_YEAR"  # "Fair value was $5M in 2024"
    NVNY = "NOTIONAL_VALUE_NO_YEAR"  # "Notional amount of $100M" (Context dependent)
    FVNY = "FAIR_VALUE_NO_YEAR"  # "Fair value of $5M"

    # --- HARD LINGUISTIC (State of Being) ---
    MAT_FUT = "MATURITY_FUTURE"  # "Matures in 2026" (Year > Reporting Year)
    AS_YEAR = "ACTIVE_STATE_YEAR"  # "Outstanding at December 31, 2024"
    BS_LOC = "BALANCE_SHEET_LOC"  # "Are recorded in Other Assets" (Present Tense)
    CONT_USE = "CONTINUOUS_USAGE"  # "Currently hedges", "Is hedging"
    REM_TERM = "REMAINING_TERM"  # "Weighted average maturity of 2 years"

    # --- SOFT LINGUISTIC (Action/Activity) ---
    PRU = "PRESENT_USAGE"  # "We use swaps" (Simple Present - Risk of Policy)
    PRY = "PRESENT_YEAR_ACTION"  # "In 2024, we used..."
    ACT_DUR = "ACTIVITY_DURING"  # "During 2024, we entered..."
    PNL_REC = "PNL_RECOGNITION"  # "Recognized a gain of..."

    # --- HISTORICAL / WEAK (Lower Confidence) ---
    PU = "PAST_USAGE"  # "We held" (Simple Past)
    PW = "PAST_WEAK"  # "We entered into" (Transactional Past)
    ASNY = "ACTIVE_STATE_NO_YEAR"  # "Outstanding" (No date anchor)


def get_tag(token_type: str, reason: Reason | str) -> str:
    return (
        f"{token_type}<{reason.value if isinstance(reason, Reason) else reason}>"
    )
