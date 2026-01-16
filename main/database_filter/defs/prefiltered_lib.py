import re
from typing import List, Optional, Set, Tuple
from defs.cp_regex import COMMODITY_UNIT_PATTERN
from defs.refer import EXHIBIT_FRAGMENT
from defs.acct_std import STANDARD_ID_REGEX
from defs.eq_regex import EQ_CONTEXT_REGEX, EQ_REGEX, EQ_SOFT_REGEX
from defs.exclusion_regex import ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN, NON_DERIVATIVE_REGEX
from defs.ir_regex import IR_SOFT_REGEX
from defs.shared_context import _DEBT_TERMS, CURRENCY_SYMBOL_PATTERN, VALUATION_MODELS
from defs.regex_lib import SENTENCE_SPLIT_PATTERN, build_alternation, build_regex
from defs.gen_regex import GEN_HEDGES

YEAR_REGEX = re.compile(r"\b(19[8-9]\d|20\d{2})\b")

# The token to append to deadweight paragraphs.
DEADWEIGHT_TOKEN = "_D"

# Token for sentence-level skips (Base string, will be formatted by get_tag)
SKIP_TOKEN = " _S"

# 5. Date Exclusion Patterns
MONTHS_PATTERN = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"

# Matches: "December 31", "Dec 31st"
DATE_MD_REGEX = re.compile(
    rf"\b(?:{MONTHS_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,)?(?!\d)", re.IGNORECASE
)

# Matches: "31 December", "1st of Jan"
DATE_DM_REGEX = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{MONTHS_PATTERN})\b", re.IGNORECASE
)

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

    soph_pattern = re.compile(
        r"\b(?:convertibles?|warrants?)\b", re.IGNORECASE
    )

    # Standard IDs: ASC 815-20, IFRS 9, etc.
    standard_id_pattern = STANDARD_ID_REGEX

    pnl_regex = None

    # B. Debt Context (Following the quant)

    debt_regex = None

    def __init__(self):
        # 2. Define Removal Patterns (applied to masked text)
        self.initialize_regex()
        
    def initialize_regex(self):
        # A. PnL / Price Context (Preceding the quant)
        # Matches: "expense of <Q_0>", "earnings <Q_1>", "price of <Q_2>"
        # Excludes: "gain", "loss" (as requested)
        pnl_terms = r"(?:income|expenses?|earnings?|prices?|costs?|revenues?)"
        pnl_connectors = (
            r"(?:of|by|was|were|is|are|aggregated|totaling|approximately|approx\.?)"
        )
        self.pnl_regex = re.compile(
            rf"\b{pnl_terms}\s+(?:{pnl_connectors}\s+)?(?P<token><Q_\d+>)",
            re.IGNORECASE,
        )
        # Matches: "<Q_0> debt", "<Q_1> principal amount", "<Q_2> senior notes"
        debt_terms = rf"(?:aggregate\s+)?(?:principal|{_DEBT_TERMS})"
        self.debt_regex = re.compile(
            rf"(?P<token><Q_\d+>)\s+{debt_terms}", re.IGNORECASE
        )
        
    def clean_contextual_quants(self, text: str) -> str:
        """
        Targeted cleaning of quantitative values that act as noise.
        Specifically removes values associated with:
        - Income/Expense/Earnings/Price (e.g., "earnings of $10 million")
        - Debt Principals (e.g., "$500 million aggregate principal")

        Preserves:
        - Gains/Losses (e.g., "gain of $5 million")
        - Fair Values / Notionals (unless explicitly flagged as debt)
        """
        # 1. Tokenize Quants: Replace numbers with unique tokens <Q_i>
        # This prevents partial matching and simplifies context checks.
        replacements = {}

        def token_sub(match):
            token = f"<Q_{len(replacements)}>"
            replacements[token] = match.group(0)
            return token

        masked_text = QUANT_REGEX.sub(token_sub, text)

        # 3. Execute Removal
        # We replace the captured token group with a space, effectively "deleting" the number
        # while keeping the context word (e.g., "earnings") intact to be handled as text.

        def remove_token(match):
            # Replace the token part of the match with a space
            return match.group(0).replace(match.group("token"), " ")
        assert self.pnl_regex is not None and self.debt_regex is not None

        masked_text = self.pnl_regex.sub(remove_token, masked_text)
        masked_text = self.debt_regex.sub(remove_token, masked_text)

        # 4. Restore Remaining Tokens
        # Any token that wasn't removed gets swapped back to its original "$10 million" string.
        for token, original_text in replacements.items():
            masked_text = masked_text.replace(token, original_text)

        return masked_text

    def clean_numerics(self, text: str, remove_years: bool = False) -> str:
        """
        Remove numeric noise that confuses quantitative parsing.
        """
        # Step 0: Contextual Cleanup (NEW)
        # Remove "bad" quants (Debt/Earnings) BEFORE they can be protected.
        text = self.clean_contextual_quants(text)

        # Step 1: Identify and protect remaining quantitative values
        quant_matches = list(QUANT_REGEX.finditer(text))
        protected_ranges = set()
        for match in quant_matches:
            for i in range(match.start(), match.end()):
                protected_ranges.add(i)

        # Step 2: Identify and protect nil/zero values
        zero_matches = list(ZERO_QUANT_REGEX.finditer(text))
        for match in zero_matches:
            for i in range(match.start(), match.end()):
                protected_ranges.add(i)

        # Step 3: Apply bullet pattern, but skip protected ranges
        def safe_bullet_sub(match):
            if any(i in protected_ranges for i in range(match.start(), match.end())):
                return match.group(0)  # Keep if protected
            return " "

        text = text.strip()
        text = self.bullet_pattern.sub(safe_bullet_sub, text)

        # Step 4: Apply POLICY cleanups
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

    def clean_non_derivatives(self, text: str, is_nst: bool = True) -> str:
        """
        Modified to protect genuine equity derivatives (EQ_REGEX)
        from being mutilated by the sophisticated term stripper.
        """

        # Step 2: Remove known non-derivative terms
        text = NON_DERIVATIVE_REGEX.sub(" ", text)

        # Step 3: Handle Sophisticated Term Stripping (is_nst=True)
        if is_nst:
            # Step 1: Identify and protect genuine Equity Derivatives (e.g., "convertible note hedge")
            eq_matches = list(EQ_REGEX.finditer(text))
            protected_ranges = set()
            for match in eq_matches:
                for i in range(match.start(), match.end()):
                    protected_ranges.add(i)
            # Define a safe substitution that avoids protected ranges
            def safe_soph_sub(match):
                # If the match for "convertible" or "warrant" is inside a
                # protected EQ_REGEX match, keep it.
                if any(
                    i in protected_ranges for i in range(match.start(), match.end())
                ):
                    return match.group(0)
                return " "

            text = self.soph_pattern.sub(safe_soph_sub, text)

        text = self.normalize_whitespace(text)
        return text

    def clean_gen_hedges(self, text: str) -> str:
        text = GEN_HEDGES.sub(" ", text)
        text = self.normalize_whitespace(text)
        return text

    def clean(self, text: str, remove_years: bool = False, is_nst: bool = True) -> str:
        texts = []
        for sent in SENTENCE_SPLIT_PATTERN.split(text):
            sent = self.clean_for_quant_analysis(sent, remove_years)
            sent = self.clean_entities(sent)
            sent = self.clean_non_derivatives(sent, is_nst)
            texts.append(sent)
        return " ".join(texts)

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
    FLR_CAP = "FLR_CAP"  # Non derivative interest rate caps and floors on debt
    CTX = "CONTEXT" # Context text
    DEBT = "DEBT"
    OTHER = "OTHER"  # Has derivative mention but no Evidence -> Other
    RISK = "RISK" # Risk management text
    NON_DERIV = "NON_DERIV" # Non-derivative accounting

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
    TRANSACT = "TRANSACT" # Temporary: may not be noise

    # --- Paragraph Level ---
    HIST_BLOCK = "HIST_BLOCK" # The entire block was discard as history (legacy/unused)
    ANLZ = "ANLZ"  # Generic Deadweight: Requires scanning internal tags for attributes
    FILING = "FILING"  # 10-K Headers
    FORWARD = "FORWARD"  # Safe Harbor / Forward Looking
    LEGAL = "LEGAL"  # Litigation
    PLAN = "PLAN"  # Pension Plans or Hedge Funds
    NON_FIN = "NON_FIN"  # Non-Financial (Plasma, Chemical)
    EQ_COMP = "EQ_COMP"  # Equity
    COMP = "COMPETE"  # Competitors
    ACCT_STD = "ACCT_STD"  # Accounting Standards
    BANKRUPTCY = "CH11"  # Bankruptcy
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
    ACT_AMB_GEN = "TRANSACTION_AMB_GENERIC"
    REM_TERM = "REMAINING_TERM"
    UNCAT = "UNCATEGORIZED"

    # ========================================================
    # Paragraph level tags
    # ========================================================
    # 1. Valuation & Position (The "Balance Sheet" View)
    # Evidence: FVY, VY, AS_YEAR, TABLE, NVY (High Confidence)
    POSDQ = "POSITION_DERIVATIVE_QUANT"

    # 2. Risk Management Strategy (The "Intent" View)
    # Evidence: CONT_USE + Quant, or RISK (Noise) + Quant
    MGMTDQ = "MGMT_DERIVATIVE_QUANT"  # "We use swaps to hedge $10m debt."
    MGMTD = "MGMT_DERIVATIVE_GEN"  # "We use swaps to hedge risk." (No numbers)

    # 3. Flow & Activity (The "Income Statement" View)
    # Evidence: ACT_YEAR, PNL_REC + Quant
    FLOWDQ = (
        "FLOW_DERIVATIVE_QUANT"  # "We recognized $5m gain." / "Entered $10m new swaps."
    )

    # 4. Credit & Collateral (The "Counterparty" View)
    # Evidence: CREDIT (Noise) + Quant
    CREDITDQ = "CREDIT_DERIVATIVE_QUANT"  # "Posted $2m collateral."

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
    EvidenceReason.UNCAT,
    EvidenceReason.ACT_AMB_GEN,
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
    NoiseReason.NEG,  # "Did not enter"
    NoiseReason.ZERO,  # "Zero value"
    NoiseReason.AOCI,  # "Recorded in AOCI"
}

# Expanded Killers for TIER 3 (Weak)
# Includes everything above + Policy/Definitions
POLICY_KILLERS = TIME_KILLERS | {
    NoiseReason.POT,  # "We periodically use..."
    NoiseReason.DOC,  # "Hedge documentation is..."
    NoiseReason.DEF,  # "Swap shall mean..."
    NoiseReason.ACCT_STD,  # "FASB ASU..."
    NoiseReason.REF,  # "See Note 5"
    NoiseReason.TRADING,  # "We do not trade"
    NoiseReason.PNL,  # An unrealized gain
}


NOISE_TAG_PARSER = re.compile(r"(_[SD])<([^>]+)>")

def mark_as_evidence(
    text: str,
    evidence: Optional[Set[EvidenceReason]] = None,
    noise: Optional[Set[NoiseReason]] = None,
) -> str:
    """
    Marks paragraph as evidence with a specific semantic reason derived from its tags.
    """
    final_reason = EvidenceReason.UNCAT  # Default fallback

    if evidence is None:
        evidence = set()
    if noise is None:
        noise = set()

    # --- HELPER: CHECK FOR QUANT ---
    # Many sentence tags imply quant (FVY, NVY), but some don't (CONT_USE).
    # We check if *any* strong quant tag exists in the evidence set.
    has_quant = not evidence.isdisjoint(
        {
            EvidenceReason.FVY,
            EvidenceReason.NVY,
            EvidenceReason.VY,
            EvidenceReason.AS_YEAR,
            EvidenceReason.ACT_YEAR,
            EvidenceReason.TABLE,
            EvidenceReason.FVNY,
            EvidenceReason.NVNY,
            EvidenceReason.VNY,
        }
    )

    # Note: You might also want to pass a raw 'has_quant' boolean if you rely on
    # extract_values_and_years() at the paragraph level, but checking tags is usually sufficient.

    # --- TIER 1: HARD VALUATION (The Strongest Signal) ---
    # If it's a Table or Explicit Year-End Value, it's a Position disclosure.
    if not evidence.isdisjoint(
        {
            EvidenceReason.TABLE,
            EvidenceReason.FVY,
            EvidenceReason.VY,
            EvidenceReason.AS_YEAR,
            EvidenceReason.FVNY,
            EvidenceReason.VNY,
            EvidenceReason.NVNY,
        }
    ):
        final_reason = EvidenceReason.POSDQ

    # --- TIER 2: FLOW & ACTIVITY ---
    # Transaction years or PnL recognition (with numbers)
    elif not evidence.isdisjoint({EvidenceReason.ACT_YEAR, EvidenceReason.ACT_GEN}) or (
        EvidenceReason.PNL_REC in evidence and has_quant
    ):
        final_reason = EvidenceReason.FLOWDQ

    # --- TIER 3: CREDIT / COLLATERAL ---
    # If "CREDIT" noise survived, it means it was saved by Strong Evidence.
    # Usually implies collateral posting or netting agreements with values.
    elif NoiseReason.CREDIT in noise and has_quant:
        final_reason = EvidenceReason.CREDITDQ

    # --- TIER 4: RISK MANAGEMENT STRATEGY ---
    # Check for Strategy indicators (CONT_USE) or Risk Context (RISK tag)
    elif (
        not evidence.isdisjoint({EvidenceReason.CONT_USE, EvidenceReason.CONT_USE_AMB})
        or NoiseReason.RISK in noise
    ):
        if has_quant:
            final_reason = EvidenceReason.MGMTDQ  # "We hedge $100m of debt"
        else:
            final_reason = EvidenceReason.MGMTD  # "We hedge debt"

    # --- TIER 5: REMAINING QUANT (Catch-all) ---
    # E.g. "Notional amount was $50m" (NVY) - fits loosely into Valuation or Strategy
    elif EvidenceReason.NVY in evidence:
        final_reason = EvidenceReason.POSDQ

    # Apply the tag
    return f"{get_tag(EVIDENCE_TOKEN, final_reason)} {text}"


class Stage(Enum):
    PF_DB = "PF_DB"  # Phase 0
    PF_TG = "PF_TG"  # Phase 1
    PF_EV = "PF_EV"  # Phase 2


def mark_as_deadweight(
    text: str,
    noise: Optional[Set[NoiseReason]] = None,
    stage: Optional[Stage] = None,
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
    return f"{get_tag(DEADWEIGHT_TOKEN, final_reason)} {stage}: {text}"


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

# Zero specifically: 0, 0.0, 0.00
ZERO_NUM = r"0(?:\.0+)?"
NUMBER_PATTERN = (
    r"(?:0\.(0[1-9]|[1-9][0-9]{0,3})|(?:[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)(?:\.\d+)?)"
)
SCALE_WORDS = r"(?:million|billion|trillion|thousand)"
QUANT_REGEX = re.compile(
    # Currency symbol + optional parens + number + optional parens
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*\(?\s*{NUMBER_PATTERN}\s*\)?|"
    # Number + optional parens + currency symbol
    rf"\(?\s*{NUMBER_PATTERN}\s*\)?\s*(?:{CURRENCY_SYMBOL_PATTERN})|"
    # Number + optional scale word + commodity unit
    rf"{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?\s+(?:{COMMODITY_UNIT_PATTERN}|shares)|"
    # Custom Tabular data (custom and consistent)
    rf"(?:amount|value)\s+of\s+{NUMBER_PATTERN}", # we do not do ignore case here
)


# Needs to match $0, $ 0, $ (0), or $(0), 0 USD, USD 0, or 0 million units/shares
ZERO_QUANT_REGEX = re.compile(
    # The value was nil
    r"\b(?:nil)\b|"
    # 2. Currency Prefix: $0, $ 0, $ (0), or $(0) or USD 0
    # Matches: Symbol + Optional Parens + Zero + Optional Scale
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*\(?\s*{ZERO_NUM}\s*\)?\b|"
    # 3. Currency Suffix: 0 USD, 0 EUR
    rf"\b{ZERO_NUM}\s*(?:{CURRENCY_SYMBOL_PATTERN})|"
    # 4. Commodity / Shares / Units: 0 barrels, 0 shares
    rf"\b{ZERO_NUM}(?:\s+{SCALE_WORDS})?\s+(?:{COMMODITY_UNIT_PATTERN}|shares)\b"
    # Custom Tabular data (custom and consistent)
    rf"(?:amount|value)\s+of\s+\b{ZERO_NUM}\b",  # we do not do ignore case here
)


G = r"(?:\W+\w+){0,5}"  # up to 5 intermediate words

HEDGE_DOC_TERMS = [
    # 1. Documentation & Designation (Existing)
    rf"\bformally\s+document\b",
    r"\bdocumentation\b",
    rf"\bat\s+inception\b",
    rf"\b(?:in)?effectiveness\s+(?:portion)?\b",
    rf"\bhighly\s+effective\b",
    rf"\bqualif(?:y|ies|ied){G}hedg(?:ing|es?)\b",
    rf"\b(?:not)?\s+designated\s+as\b",
    rf"\bhedge\s+(?:accounting|relationship|documentation|designation|treatment)?\b",
    rf"\beconomic\s+relationship\b",
    rf"\bnature\s+of\b",
    r"\bearnings\s+impact\b",
    # 2. ASC 815 / FAS 133 Specifics (New & Tightened)
    # Matches: "Hedges of forecasted transactions\b", "Hedge of a recognized asset"
    r"\bhedges?\s+of\s+(?:(?:a|the|these|those|any)\s+)?(?:forecasted|recognized)\b",
    # Matches: "Changes in the fair value of a derivative"
    r"\bchanges?\s+in\s+(?:the\s+)?fair\s+values?\s+of\s+(?:a|the|these|those|any)\s+derivatives?\b",
    # Matches: "Derivatives are recognized\b", "The derivative is recognized"
    r"\b(?:the\s+|these\s+|those\s+|a\s+)?derivatives?\s+(?:are|is)\s+recognized\b",
    # Matches: "Variability of cash flows" (Safe if inside derivative/hedging paragraphs)
    r"\bvariabilit(?:y|ies)\s+of\s+cash\s+flows?\b",
    # Matches: "Hedge of net investment in foreign operation"
    r"\bhedges?\s+of\s+(?:the\s+)?net\s+investment\b",
    # Matches: "Recorded in OCI\b", "Recorded in earnings" (Standard mechanics)
    r"\b(?:recognized|recorded)\s+in\s+(?:other\s+comprehensive|earnings|oci)\b",
    r"\b(?:[\"“\'])?(?:net investment|fair\s+value|cash\s+flow)(?:[\"“\'])?\s+hedges?\b",
]


HEDGE_DOC_REGEX = build_regex(HEDGE_DOC_TERMS, use_sep=False)

def pnl_regex() -> re.Pattern:
    # 1. The Financial Targets (The "What")
    # Captures: "net income", "interest expense", "2024 earnings", "revenues"
    # Structure handles optional prefixes: "the", "net", "2024", "interest"
    pnl_target_bases = r"(?:earnings|incomes?|revenues?|expenses?|operations|results)"
    pnl_targets = rf"(?:the\s+)?(?:net\s+)?(?:\d{{4}}\s+)?(?:interest\s+)?(?:net\s+)?{pnl_target_bases}"

    # 2. The Prepositions (The "Connector")
    preps = r"(?:on|to|in|at|of|from)"

    # 3. The Action Words (The "How")
    # Nouns: "an impact", "an increase"
    impact_nouns = r"(?:impact|effect|increase|decrease|gain|loss(?:es)?)"
    # Verbs: "increased", "reducing"
    change_verbs = r"(?:increas|decreas|reduc)(?:ed?|es|ing)"

    pnl_terms = [
        # 1. Explicit Gains/Losses (Anchored to avoid "Total Gains")
        r"(?:realized|unrealized)\s+(?:net\s+)?(?:gains?|loss(?:es)?)",
        # 2. "On" Construction (e.g., "Gain on derivatives")
        rf"(?:net\s+)?(?:gains?|loss(?:es)?)\s+{preps}",
        # 3. Fair Value CHANGES (Strictly Flow)
        # 4. Ineffectiveness (Strictly PnL context)
        r"ineffective\s+portion",
        r"hedge\s+ineffectiveness",
        # 6. Mark-to-Market (Action/Result, usually implies flow)
        # Distinguishes from "Fair Value" measurement policy
        r"mark(?:ed)?[- ]to[- ]market",
        # A. Unambiguous Gains/Losses (Stand-alone)
        # Matches: "resulted in a gain", "recognized a loss"
        r"(?:had|have|has|recognized|recorded|resulted\s+in)(?:\W+\w+){0,3}\s+(?:gain|loss(?:es)?)",
        # B. "Noun" Impact (Impact/Effect ON Target)
        # Matches: "impact on net income", "increase in 2024 earnings"
        # Logic: Noun + Prep + Target
        rf"{impact_nouns}\s+{preps}\s+{pnl_targets}",
        # C. "Verb" Change (Directly Changed Target)
        # Matches: "increased interest expense", "reducing net income"
        # Logic: Verb + (optional 3 words) + Target
        rf"{change_verbs}(?:\W+\w+){{0,3}}\s+{pnl_targets}",
        # D. "Auxiliary" Impact (Had ... Impact ON Target)
        # Matches: "had a material impact on earnings", "has no effect on results"
        # Logic: Had/Have + (optional words) + Noun + Prep + Target
        rf"(?:had|have|has)(?:\W+\w+){{0,3}}\s+{impact_nouns}\s+{preps}\s+{pnl_targets}",
    ]

    return build_regex(pnl_terms)


PNL_CONTEXT_REGEX = pnl_regex()

_prep_pattern = build_alternation([r"in", r"of", r"on"])
CHANGE_FV_REGEX = build_regex(
    [
        # LOGIC:
        # 1. Match "Change in fair value"
        rf"\bchange(?:s)?\s+{_prep_pattern}\s+(?:the\s+)?fair\s+value"
    ]
)

# 1. Match auxiliary verbs: have, having, had, has
# 2. Allow 0-2 filler words (e.g., "recorded a", "significant", "no", "a")
# 3. Match target: "change(s) in fair value"
# --- 1. Core components -------------------------------------------------------

# Change verbs: change / changes / increased / decreases / etc.
_change_verbs = [
    r"change(?:s)?",
    r"increase(?:d|s)?",
    r"decrease(?:d|s)?",
    r"adjustments?"
]

change_verb_pattern = build_alternation(_change_verbs)


# --- 2. Fair value targets ----------------------------------------------------

_fv_targets = [
    # e.g., "change in fair value", "increase of fair value"
    rf"{change_verb_pattern}\s+{_prep_pattern}\s+(?:the\s+)?fair\s+value",
    # e.g., "fair value changes"
    rf"fair\s+value\s+{change_verb_pattern}",
]

fv_target_pattern = build_alternation(_fv_targets)

# --- 3. Auxiliary verb anchor -------------------------------------------------
_aux_verbs = [
    r"hav(?:e|ing)",
    r"had",
    r"has",
]

aux_verb_pattern = build_alternation(_aux_verbs)

# --- 4. Final regex -----------------------------------------------------------

HAD_CHANGE_REGEX = re.compile(
    rf"\b{aux_verb_pattern}"  # have / having / had / has
    rf"(?:\s+\S+){{0,2}}"  # 0–2 filler words
    rf"\s+{fv_target_pattern}",  # fair value change target
    re.IGNORECASE,
)

def is_pnl(text, context_only = True):
    if context_only:
        return bool(PNL_CONTEXT_REGEX.search(text))
    return bool(HAD_CHANGE_REGEX.search(text)) or bool(PNL_CONTEXT_REGEX.search(text))

# =============================================================================
# SOPHISTICATED CONTEXT DEFINITIONS
# =============================================================================

def is_sophisticated_content(text: str) -> bool:
    """
    Returns True if text is sophisticated derivative content.
    Checks: (Target + EQ context) OR (Sophisticated context terms)

    Used throughout to gate sophisticated buffer routing.
    """
    return is_sophisticated_target(text) or bool(
        SOPHISTICATED_CONTEXT_REGEX.search(text)
    )


# 1. Target Instruments (The "What") - NOW REQUIRES EQ CONTEXT
# Instead of just matching "convertible" or "warrant" standalone,
# we require them to co-occur with equity derivative signals
CONVERSION = (
    r"(?<!currency[ -])"
    r"(?<!foreign[ -])"
    r"(?<!exchange[ -])"
    r"(?<!forex[ -])"
    r"(?<!spot[ -])"
    r"(?<!forward[ -])"
    r"(?<!rate[ -])"
    r"(?<!interest[ -])"
    r"(?<!yield[ -])"
    r"(?<!coupon[ -])"
    r"(?<!principal[ -])"
    r"(?<!debt[ -])"
    r"(?<!loan[- ])"
    r"conversion"
)

SOPHISTICATED_TARGETS = re.compile(
    rf"\b(?:convertibles?|warrants?|{CONVERSION})\b",
    re.IGNORECASE,
)

# 2. Sophisticated Context (The "Why/How")
# Used to validate the sophisticated buffer.
SOPHISTICATED_CONTEXT_TERMS = [
    # REFINED: "embedded" must be followed by a relevant noun to be a self-validating signal
    r"embedded\s+derivatives?",
    r"bifurcat(?:e|ion|ed)",
    r"derivative\s+(?:liabilit(?:y|ies)|assets?)",
    r"host\s+contracts?",
    r"conversion\s+(?:options?|features?)",
    r"fair\s+value\s+options?",
    r"warrants?.*not indexed to.*stock",
    r"warrants?.*(?:accounted|classified).*liability",
] + VALUATION_MODELS  # Black-Scholes, Monte Carlo, etc.

SOPHISTICATED_CONTEXT_REGEX = build_regex(SOPHISTICATED_CONTEXT_TERMS)


def is_sophisticated_target(text: str) -> bool:
    """
    Returns True if text contains a sophisticated target (convertible/warrant/conversion)
    AND has equity derivative context (EQ_REGEX or EQ_SOFT_REGEX).

    This prevents false positives from unrelated mentions of "warrant" or "convertible".
    """
    # Quick exit: no target word present
    if not SOPHISTICATED_TARGETS.search(text):
        return False

    # Quick exit 2: refer to interest rate category
    if IR_SOFT_REGEX.search(text):
        return False

    # Required: target must have equity context
    if EQ_SOFT_REGEX.search(text):
        return True

    return False

def convertible_ir(p):
    local_is_nst = False
    if SOPHISTICATED_TARGETS.search(p) and IR_SOFT_REGEX.search(
        p
    ):  # Discussions of ir cap, swap, etc
        if not (
            SOPHISTICATED_CONTEXT_REGEX.search(p)
            or EQ_CONTEXT_REGEX.search(p)
        ):
            local_is_nst = True
    return local_is_nst

ACTIVE_STATE_DESCRIPTORS = [
    "outstanding",
    "active",
    "remaining",
    "open",
    "current(?:ly)?",
]

ACTIVE_STATE_PATTERN = build_alternation(ACTIVE_STATE_DESCRIPTORS)
ACTIVE_STATE_REGEX = build_regex(ACTIVE_STATE_DESCRIPTORS)
