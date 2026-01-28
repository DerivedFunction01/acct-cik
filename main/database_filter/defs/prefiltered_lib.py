import re
from typing import List, Optional, Set, Tuple
from defs.cp_regex import COMMODITY_UNIT_PATTERN
from defs.refer import EXB_TOKEN, EXHIBIT_FRAGMENT
from defs.acct_std import STANDARD_ID_REGEX, STD_TOKEN
from defs.eq_regex import EQ_CONTEXT_REGEX, EQ_REGEX, EQ_SOFT_REGEX
from defs.exclusion_regex import ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN, NON_DERIVATIVE_REGEX
from defs.shared_context import (
    _DEBT_TERMS,
    CURRENCY_SYMBOL_PATTERN,
    VALUATION_MODELS,
)
from defs.regex_lib import SENTENCE_SPLIT_PATTERN, build_alternation, build_compound, build_regex, add_restrictions
from defs.gen_regex import GEN_HEDGES, NOTIONAL_REGEX
from defs.derivative_lib import create_target
from defs.ir_regex import CAP_FLOOR_REGEX, IR_SOFT_REGEX, DEBT_FT_REGEX, DEBT_EXP_REGEX, DEBT_TOKEN, IR_TOK

YEAR_REGEX = re.compile(r"\b(19[8-9]\d|20\d{2})\b")

# The token to append to deadweight paragraphs.
DEADWEIGHT_TOKEN = "_D"

# Token for sentence-level skips (Base string, will be formatted by get_tag)
SKIP_TOKEN = " _S"

# 5. Date Exclusion Patterns
MONTHS_PATTERN = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
MD_PATTERN = rf"\b(?:{MONTHS_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,)?(?!\d)"
# Matches: "December 31", "Dec 31st"
DATE_MD_REGEX = re.compile(
    MD_PATTERN, re.IGNORECASE
)
DM_PATTERN = rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{MONTHS_PATTERN})\b"
# Matches: "31 December", "1st of Jan"
DATE_DM_REGEX = re.compile(
    DM_PATTERN, re.IGNORECASE
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
        # 1. Capture years/numbers with parentheses: (2023) -> STRIP
        r"\(\d+\)|"
        # 2. Capture numbers with period/colon ONLY if NOT a year: 1., 1: -> STRIP
        #    Uses negative lookahead to protect 19xx and 20xx
        r"(?!(?:19|20)\d{2})\d+(?:\.|\)|\:)|"
        # 3. Roman numerals and letters -> STRIP
        r"\([ivxlcdm]+\)|[ivxlcdm]+\.|"
        r"\([a-z]\)|[a-z]\.|"
        r"\([A-Z]\)|[A-Z]\."
        r")"
        r"(?=\s)",  # Followed by whitespace
        re.IGNORECASE,
    )

    # Dashed patterns: 1-2, 3-4 (range references)
    dashed_pattern = re.compile(r"\b\d+[-]\d+\b")

    exhibit_pattern = re.compile(
        rf"\b{EXHIBIT_FRAGMENT}\b" r"(?:\s*No\.?)?" r"\s*\d{1,3}(?:\.\d+)?\b",
        re.IGNORECASE,
    )

    warrant_pattern = re.compile(r"\b(?:warrants?)\b", re.IGNORECASE)
    convertible_pattern = re.compile(r"\b(?:convertibles?)\b", re.IGNORECASE)

    # Standard IDs: ASC 815-20, IFRS 9, etc.
    standard_id_pattern = STANDARD_ID_REGEX

    punct = re.compile(r"([.!?|:;])$")

    pnl_regex = None

    year_regex = None

    debt_regex = None

    title_regex = None

    maturity_regex = None

    newline = re.compile(r"\n{3,}")
    space = re.compile(r"[ \t]+")

    other_regexes = []
    def __init__(self):
        # 2. Define Removal Patterns (applied to masked text)
        self.initialize_regex()

    def initialize_regex(self):
        # A. PnL / Price Context (Preceding the quant)
        # Matches: "expense of <Q_0>", "earnings <Q_1>", "price of <Q_2>"
        # Excludes: "gain", "loss" (as requested)
        quant_token = r"<Q_\d+>"

        # IMPROVED: Allow comma, space, and/or word connectors in combination
        # This handles: ", ", " and ", ", and ", " or "
        sep_pattern = r"\s*(?:,|\band\b|\bor\b|&|to)\s*"

        # To handle the ", and" case specifically, we can make the separator
        # allow multiple units:
        flexible_sep = r"(?:[\s,]+(?:and|or|&|to)?\s*)"

        quant_chain = rf"{quant_token}(?:{flexible_sep}{quant_token})*"

        price_term = add_restrictions(r"prices?", lookbehinds=["strike", "exercise"])
        pnl_term_list = [
            r"income",
            r"expenses?",
            r"earnings?",
            price_term,
            r"costs?",
            r"revenues?",
            r"payments?",
            r"gains?",
            r"sales?",
            r"loss",
            r"losses",
        ]
        pnl_terms = build_alternation(pnl_term_list)
        pnl_connectors_list = [
            "of",
            "by",
            "was",
            "were",
            "is",
            "are",
            "aggregated",
            "totaling",
            "approximately",
            r"approx\.?",
            "to",
            "at",
        ]
        pnl_connectors = build_alternation(pnl_connectors_list)
        # 2. Define the Gap (0-2 words)
        # \s+\w+ matches a space followed by a word (e.g., " was increased")
        WORD_GAP = r"(?:\s+\w+){0,2}"

        # 3. Update the Regex
        # Structure: \b{term}{gap} {optional connector} {quant}
        self.pnl_regex = re.compile(
            rf"\b{pnl_terms}{WORD_GAP}\s+(?:{pnl_connectors}\s+)?(?P<token>{quant_chain})",
            re.IGNORECASE,
        )
        # Matches: "<Q_0> debt", "<Q_1> principal amount", "<Q_2> senior notes"
        debt_terms = rf"(?:aggregate\s+)?(?:principal|(?:convertible )?{_DEBT_TERMS})"
        self.debt_regex = re.compile(
            rf"(?P<token>{quant_chain})\s+{debt_terms}", re.IGNORECASE
        )

        # 2. Define Year Chain (Matches: <Y_0>, <Y_1> and <Y_2>)
        year_token = r"<Y_\d+>"
        sep_pattern = r"\s*(?:,|and|or|&)\s*"
        # Expanded to catch "December", "December 31", or "31 December"
        # We wrap them in optional groups to be used inside the year_chain
        DATE_PREFIX_PATTERN = rf"(?:(?:{MD_PATTERN}|{DM_PATTERN}|{MONTHS_PATTERN})\s*(?:,)?\s*)"
        # This now matches:
        # "2023"
        # "December 2023"
        # "December 31, 2023"
        # "December 2023, 2024 and 2025"
        year_chain = rf"(?:{DATE_PREFIX_PATTERN})?{year_token}(?:{sep_pattern}{year_token})*"

        # 3. Define Removal Patterns

        # A. Pre-Noun Modifiers (The "2024 Notes" / "2010 Plan" case)
        # STRICT ADJECTIVES: Excludes "Fiscal", "Annual"
        # Includes: Senior, Convertible, Secured, Incentive, Stock, Performance, Share
        adjectives_list = [
            "senior",
            "convertible",
            "secured",
            "unsecured",
            "guaranteed",
            "equity",
            "stock",
            "incentive",
            "share",
            "performance",
        ]
        opt_adjectives = rf"(?:{build_alternation(adjectives_list)}\s+){{0,3}}"

        # STRICT NOUNS: Excludes "Year", "Quarter", "Report"
        # Includes: Notes, Bonds, Loans, Facility, Plans, Programs, Schemes
        target_nouns_list = [
            _DEBT_TERMS,
            "facility",
            "plans?",
            "programs?",
            "schemes?",
            r"(?:net\s+)?(?:income|expenses?|sales?|revenues?|earnings?)",
        ]
        target_nouns = build_alternation(target_nouns_list)

        self.title_regex = re.compile(
            rf"(?P<token>{year_chain})\s+{opt_adjectives}{target_nouns}", re.IGNORECASE
        )

        # B. Post-Noun Maturities (The "Notes due 2025" case)
        # STRICT ANCHOR: Must be [Debt Noun] + "due" + [Year]
        # This prevents cleaning evidence like "The hedge is due 2025" or "Expires in 2025"
        debt_nouns = rf"(?:{_DEBT_TERMS}|facility)"
        maturity_triggers = r"(?:due|matur(?:e|ing)|expir(?:e|ing))\s+(?:on|in|at|during|through)?\s*"
        # Allow up to 3 words between the trigger and the date/year
        # This catches: "due in December 2023", "due approximately 2024", etc.
        GAP = r"(?:\W+\w+){0,4}?"

        self.maturity_regex = re.compile(
            rf"{debt_nouns}\s+{maturity_triggers}{GAP}\s+(?P<token>{year_chain})",
            re.IGNORECASE,
        )

    def clean_contextual_years(self, text: str) -> str:
        """
        Targeted cleaning of Years that act as Adjectives or Identifiers.

        Strict Rules:
        1. Removes: YEAR + [Adjectives] + [Debt/Plan Noun] (e.g. "2024 Senior Notes", "2010 Incentive Plan")
        2. Removes: [Debt Noun] + due + YEAR (e.g. "Notes due 2028")
        3. PROTECTS: "Fiscal Year", "Annual Report", and generic expirations (e.g. "Options expiring 2025")
        """
        # 1. Tokenize Years
        replacements = {}

        def token_sub(match):
            token = f"<Y_{len(replacements)}>"
            replacements[token] = match.group(0)
            return token

        # Uses the global YEAR_REGEX (e.g. \b20\d{2}\b)
        masked_text = YEAR_REGEX.sub(token_sub, text)
        # 4. Execute Removal
        def remove_token(match):
            # Replace the YEAR token chain with a space, keeping the context words.
            return match.group(0).replace(match.group("token"), " ")

        assert self.title_regex is not None and self.maturity_regex is not None
        masked_text = self.title_regex.sub(remove_token, masked_text)
        masked_text = self.maturity_regex.sub(remove_token, masked_text)

        # 5. Restore Remaining Years
        for token, original_text in replacements.items():
            masked_text = masked_text.replace(token, original_text)
        masked_text = DEBT_EXP_REGEX.sub(DEBT_TOKEN, masked_text) # replaces it with the word "debt"
        masked_text = self.normalize_whitespace(masked_text)
        return masked_text

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
        text = DATE_MD_REGEX.sub(" ", text)
        text = DATE_DM_REGEX.sub(" ", text)
        text = self.clean_contextual_quants(text)
        text = self.clean_contextual_years(text)
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
        text = self.standard_id_pattern.sub(STD_TOKEN, text)
        text = self.exhibit_pattern.sub(EXB_TOKEN, text)
        text = self.dashed_pattern.sub(" ", text)

        if remove_years:
            text = YEAR_REGEX.sub(" ", text)
        return text

    def normalize_whitespace(self, text: str) -> str:
        """Collapse multiple spaces and newlines."""
        text = self.space.sub(" ", text)
        text = self.newline.sub("\n\n", text)
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

    def clean_non_derivatives(self, text: str, is_nst_warr: bool = True, is_nst_conv: bool = True) -> str:
        # Step 1: Protect genuine Equity Derivatives (EQ_REGEX)
        # We move this to the top so we have a 'map' of what to never touch
        eq_matches = list(EQ_REGEX.finditer(text))
        protected_ranges = set()
        for match in eq_matches:
            for i in range(match.start(), match.end()):
                protected_ranges.add(i)

        # Step 2: Remove known non-derivative terms (e.g., "non-derivative")
        text = NON_DERIVATIVE_REGEX.sub(" ", text)

        # Step 3: Handle Sophisticated Term Stripping (is_nst=True)
        def safe_soph_sub(match):
            if any(
                i in protected_ranges for i in range(match.start(), match.end())
            ):
                return match.group(0)
            return " "

        if is_nst_warr:
            text = self.warrant_pattern.sub(safe_soph_sub, text)

        if is_nst_conv:
            text = self.convertible_pattern.sub(safe_soph_sub, text)

        # Step 4: Neutralize Fair Value of Debt
        # We use a protected sub to ensure we don't kill "FV of Convertible Debt"
        # when it's part of a protected hedge.
        def safe_debt_sub(match):
            if any(i in protected_ranges for i in range(match.start(), match.end())):
                return match.group(0)
            return DEBT_TOKEN  # " debt "

        text = DEBT_FT_REGEX.sub(safe_debt_sub, text)
        text = CAP_FLOOR_REGEX.sub(IR_TOK, text)
        text = self.normalize_whitespace(text)
        return text

    def clean_soph_targets(self, text: str) -> str:
        text = self.warrant_pattern.sub(" ", text)
        text = self.convertible_pattern.sub(" ", text)
        text = self.normalize_whitespace(text)
        return text

    def clean_gen_hedges(self, text: str) -> str:
        text = GEN_HEDGES.sub(" ", text)
        text = self.normalize_whitespace(text)
        return text

    def add_punctuation(self, text: str, punct: str) -> str:
        # Adds a period at the end of the sentence if it doesn't exist
        if not text.endswith(punct):
            text += punct
        return text

    def clean_other_regexes(self, text, regexes: List[re.Pattern]):
        for regex in regexes:
            text = regex.sub(" ", text)
        return text

    def clean(self, text: str, remove_years: bool = False, is_nst_warr: bool = True, is_nst_conv: bool = True) -> str:
        texts = []
        for sent in SENTENCE_SPLIT_PATTERN.split(text):
            if not sent.strip():
                continue

            # 1. Capture the original terminal punctuation reliably
            # Search for the last non-whitespace character that is punctuation
            match = self.punct.search(sent.strip())
            punctuation = match.group(1) if match else "."

            sent = self.clean_for_quant_analysis(sent, remove_years)
            sent = self.clean_entities(sent)
            sent = self.clean_non_derivatives(sent, is_nst_warr, is_nst_conv)
            sent = self.clean_other_regexes(sent, self.other_regexes)
            sent = self.add_punctuation(sent, punctuation)
            texts.append(sent)
        return " ".join(texts)

    def run_test(self):
        # --- 2. THE ULTIMATE TORTURE TEST PARAGRAPH ---
        test_paragraph = (
            "1) Context: During the 2023 Fiscal Year, per ASC 815-20 and ASU 2025-12, the Company held several "
            "interest rate swaps maturing in 2029, to lock in interest rates. The swap has a notional amount (from December 25, 2039) of $500 million, setting "
            "the cap interest rate to 10% and the floor interest rate to 5%. (2) These were "
            "used to fix the rate of our 2024 Convertible Senior Notes due December 31, 2029 and our 2025 Secured "
            "Debentures maturing in 2030. (ii) Quantitative: We recorded a gain of $42 million; however, the interest "
            "rate swap mechanics had an impact on 2023 earnings of $120 million, $80 million, and $15.5 million respectively. "
            "Furthermore, interest expense was increased by $5.2 million due to amortization. (iii) Equity: We also "
            "entered into convertible note hedge transactions to limit dilution, alongside separate warrant transactions "
            "which we bifurcated as embedded derivatives. (iv) Neutralization: The fair value of the facility "
            "and the change in fair value of debt were excluded. The agreement sets the interest rate cap and floor at "
            "10% and 5%, respectively. Note that the 2012 Stock Incentive Plan and "
            "the 2018 Performance Share Plan include options expiring 2026. (4) Distress: Due to liquidity issues, "
            "the Company filed a voluntary petition for relief under Chapter 11 of the Bankruptcy Code. "
            "See Exhibit 10.1 and Schedule 14A for additional 'fair value' hedges and debt documentation."
        )

        print("-" * 60)
        print("INPUT TEXT:")
        print("-" * 60)
        print(test_paragraph)
        print("\n" + "=" * 60 + "\n")

        cleaned_text = self.clean(test_paragraph, remove_years=False, is_nst_warr=True, is_nst_conv=True)

        print("-" * 60)
        print("CLEANED OUTPUT:")
        print("-" * 60)
        print(cleaned_text)
        print("-" * 60)

        # --- 4. UPDATED VERIFICATION CHECKLIST ---
        print("\nVISUAL CHECKLIST:")
        print(
            f"to lock in neutralized             {'SUCCESS' if 'to lock in' not in cleaned_text else 'FAIL'}"
        )
        print(
            f"cap interest rate neutralized             {'SUCCESS' if 'cap interest rate' not in cleaned_text else 'FAIL'}"
        )
        print(
            f"Date protected? 2039 still exists        {'SUCCESS' if '2039' in cleaned_text else 'FAIL'}"
        )
        # 1. Punctuation Restoration
        print(
            f"Terminal Punctuation restored?           {'SUCCESS' if cleaned_text.strip().endswith('.') else 'FAIL'}"
        )

        # 2. Accounting & Exhibit Stripping
        print(
            f"Accounting IDs (ASC/ASU) replaced?      {'SUCCESS' if '815' not in cleaned_text and STD_TOKEN in cleaned_text else 'FAIL'}"
        )
        print(
            f"Exhibits (Exhibit 10.1) replaced?        {'SUCCESS' if '10.1' not in cleaned_text and EXB_TOKEN in cleaned_text else 'FAIL'}"
        )

        # 3. Quant Contextual Removal (The 'Gap' & 'respectively' check)
        print(
            f"Notional [$500 million] Kept?            {'SUCCESS' if '$500 million' in cleaned_text else 'FAIL'}"
        )
        print(
            f"Gain [$42 million] Gone?                 {'SUCCESS' if '$42 million' not in cleaned_text else 'FAIL'}"
        )
        print(
            f"Oxford Quant Chain ($120M, $80M, $15.5M) Gone? {'SUCCESS' if '$120 million' not in cleaned_text and '$15.5 million' not in cleaned_text else 'FAIL'}"
        )
        print(
            f"PnL Gap (Expense increased by $5.2M) Gone? {'SUCCESS' if '$5.2 million' not in cleaned_text else 'FAIL'}"
        )

        # 4. Year Contextual Removal (Title & Maturity with Month/Day)
        print(
            f"ID Years (2024 Notes / 2025 Debentures) Gone? {'SUCCESS' if 'Notes' in cleaned_text and '2024' not in cleaned_text else 'FAIL'}"
        )
        print(
            f"Maturity (due December 31, 2029) Gone?   {'SUCCESS' if 'December 31, 2029' not in cleaned_text and 'December' not in cleaned_text else 'FAIL'}"
        )
        print(
            f"Incentive Plans (2012 / 2018) Gone?      {'SUCCESS' if 'Incentive Plan' in cleaned_text and '2012' not in cleaned_text else 'FAIL'}"
        )
        print(
            f"Fiscal Year (2023 Fiscal) Protected?     {'SUCCESS' if '2023 Fiscal' in cleaned_text else 'FAIL'}"
        )

        # 5. Sophisticated Logic & Equity Protection
        print(
            f"Protected (convertible note hedge)?      {'SUCCESS' if 'convertible note hedge' in cleaned_text.lower() else 'FAIL'}"
        )
        print(
            f"NST Stripped (warrant)?                  {'SUCCESS' if 'warrant' not in cleaned_text.lower() else 'FAIL'}"
        )

        # 5b. Split Logic Verification
        print("\nSPLIT LOGIC VERIFICATION:")
        split_text = "We issued warrants and convertible notes."

        # Case 1: Keep Warrants, Strip Convertibles
        clean_warr = self.clean(split_text, is_nst_warr=False, is_nst_conv=True)
        print(f"Keep Warrants Only:                      {'SUCCESS' if 'warrants' in clean_warr and 'convertible' not in clean_warr else 'FAIL'}")

        # Case 2: Strip Warrants, Keep Convertibles
        clean_conv = self.clean(split_text, is_nst_warr=True, is_nst_conv=False)
        print(f"Keep Convertibles Only:                  {'SUCCESS' if 'warrants' not in clean_conv and 'convertible' in clean_conv else 'FAIL'}")

        # 6. Neutralization & Expiration
        # Replaces 'Debentures maturing in 2030' -> 'debt'
        # Replaces 'fair value of the facility' -> 'debt'
        # Replaces 'change in fair value of debt' -> 'debt'
        print(
            f"Maturity neutralized (maturing in 2030 -> debt)? {'SUCCESS' if 'maturing in 2030' not in cleaned_text and 'debt' in cleaned_text.lower() else 'FAIL'}"
        )
        print(
            f"FV of Debt neutralized?                  {'SUCCESS' if 'fair value of the facility' not in cleaned_text.lower() else 'FAIL'}"
        )
        print(
            f"Interest Rate Cap neutralized?           {'SUCCESS' if 'sets the interest rate cap' not in cleaned_text else 'FAIL'}"
        )

        # 7. Bullet protection for years
        # (1) should be removed, but 2023. or 2023: should stay (if added to paragraph)
        print(
            f"Bullets ((1), (2), (ii), (iii)) Removed? {'SUCCESS' if '1)' not in cleaned_text and '(ii)' not in cleaned_text else 'FAIL'}"
        )


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
    DEBT = "DEBT" # All about debt
    RISK = "RISK" # Risk management text
    NON_DERIV = "NON_DERIV" # Non-derivative accounting
    STL_MECH = "STL_MECH" # Settlement mechanics

    # --- Business Logic / Signals ---
    NO_TRADING = "NO_TRADING"  # Trading Denial ("We do not trade")
    TRADING = "TRADING" # Trading activity ("We engage in limited trading activity")
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
    IMM = "IMMATERIAL" # The amounts were immaterial
    PLAN = "PLAN"  # Pension Plans or Hedge Funds

    # --- Paragraph Level ---
    HIST_BLOCK = "HIST_BLOCK" # The entire block was discard as history (legacy/unused)
    ANLZ = "ANLZ"  # Generic Deadweight: Requires scanning internal tags for attributes
    FILING = "FILING"  # 10-K Headers
    FORWARD = "FORWARD"  # Safe Harbor / Forward Looking
    LEGAL = "LEGAL"  # Litigation
    NON_FIN = "NON_FIN"  # Non-Financial (Plasma, Chemical)
    EQ_COMP = "EQ_COMP"  # Equity
    COMP = "COMPETE"  # Competitors
    ACCT_STD = "ACCT_STD"  # Accounting Standards
    BANKRUPTCY = "CH11"  # Bankruptcy
    CATALOGUE = "CATALOGUE" # We manufacture / product catelouge
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
    HEDGE_FAIL = "NON_USER"  # No indication of hedging (Fails stage 1 prefilter_database)
    NO_SOPH = "NO_SOPH"  # No indication of convertible/warrants as derivatives
    NO_HEDGE = "NO_HEDGE"


class EvidenceReason(Reason):
    # =========================================================
    # TIER 1: STRONG (The "Smoking Gun")
    # Criteria: Strict Subject ("Swap") + Hard Anchor (Year/Value)
    # Survival: Overrides ALL Noise.
    # =========================================================
    AS_YEAR = "ACTIVE_STATE_YEAR"  # "Swaps outstanding at Dec 31, 2024"
    MAT_FUT = "MATURITY_FUTURE"  # "Swaps mature in 2026"
    MAT_FUT_NV = "MATURITY_FUTURE_NOTIONAL"
    MAT_FUT_FV = "MATURITY_FUTURE_FAIR_VALUE"
    MAT_FUT_V = "MATURITY_FUTURE_VALUE"
    NVY = "NOTIONAL_VALUE_YEAR"  # "Notional was $100M in 2024"
    FVY = "FAIR_VALUE_YEAR"  # "Fair Value of Swaps was $5M in 2024"
    VY = "VALUE_YEAR"  # "Value of Swaps was $5M in 2024

    # Special Survives history but dies to termination only
    ACT_YEAR = "TRANSACTION_YEAR"  # "Entered into Swaps in 2024" 
    ACT_NV_YEAR = "TRANSACTION_NOTIONAL_YEAR"  # "Entered into Swaps in with notional 2024
    ACT_FV_YEAR = "TRANSACTION_FAIR_VALUE_YEAR" 
    ACT_V_YEAR = "TRANSACTION_VALUE_YEAR"
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
    EvidenceReason.MAT_FUT_NV,
    EvidenceReason.MAT_FUT_FV,
    EvidenceReason.MAT_FUT_V,
    EvidenceReason.NVY,  # "Notional was $100M at Dec 31, 2024"
    EvidenceReason.FVY,  # "Fair Value was $5M at Dec 31, 2024"
    EvidenceReason.VY  # "We hold $5M of swaps at Dec 31, 2024"
}

# TIER 1.5: FLOW EVIDENCE (Conditional Strong)
# Immune to: History (TIME), Policy (POLICY).
# Dies to: Termination (TERM)
# Logic: "Entered in 2024" overrides "2019 history" or no POLICY "oustanding positions", but dies if "Terminated" in same breath.
FLOW_EVIDENCE = {
    EvidenceReason.ACT_YEAR,  # "Entered into Swaps in 2024"
    EvidenceReason.ACT_NV_YEAR,  # "Entered into Swaps in with notional 2024"
    EvidenceReason.ACT_FV_YEAR,  # "Entered into Swaps in with fair value 2024"
    EvidenceReason.ACT_V_YEAR,  # "Entered into Swaps in with value 2024"
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

# TIER 3.5: WEAK EVIDENCE (Immaterial Prone)
# For very short 1 evidence sentence paragraphs, Dies to Immaterial
IMMATERIAL_KILLED_EVIDENCE = FLUFF_EVIDENCE | {
    EvidenceReason.CONT_USE,
    EvidenceReason.CONT_USE_AMB,
    EvidenceReason.BS_LOC,
    EvidenceReason.VAL_MODEL,
    EvidenceReason.ACT_GEN,
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
    NoiseReason.POT,  # "We periodically use..."
}

# Expanded Killers for TIER 3 (Weak)
# Includes everything above + Policy/Definitions
POLICY_KILLERS = TIME_KILLERS | {
    NoiseReason.DOC,  # "Hedge documentation is..."
    NoiseReason.DEF,  # "Swap shall mean..."
    NoiseReason.ACCT_STD,  # "FASB ASU..."
    NoiseReason.REF,  # "See Note 5"
    NoiseReason.NO_TRADING,  # "We do not trade"
    NoiseReason.TRADING,  # "We engage in limited trading activity"
    NoiseReason.PNL,  # An unrealized gain
    NoiseReason.TRANSACT,  # Entered into a derivative in the past
    NoiseReason.IMM,
    NoiseReason.CREDIT,
    NoiseReason.NON_DERIV,
    NoiseReason.STL_MECH,
    NoiseReason.FLR_CAP,
    NoiseReason.CTX,
    NoiseReason.DEBT,
    NoiseReason.RISK,
    NoiseReason.NPNS,
    NoiseReason.REG,
    NoiseReason.HYP_SCORE,
    NoiseReason.CONTRACT,
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
            EvidenceReason.MAT_FUT_NV,
            EvidenceReason.MAT_FUT_FV,
            EvidenceReason.MAT_FUT_V,
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
    elif NoiseReason.NO_TRADING in noise:
        final_reason = NoiseReason.NO_TRADING  # "We do not trade"
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
    # 1. Currency Symbol + Number + Optional Scale (e.g., "$ 500 million")
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*\(?\s*{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?\s*\)?|"
    
    # 2. Number + Scale + Currency Symbol (e.g., "500 million $")
    rf"\(?\s*{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?\s*\)?\s*(?:{CURRENCY_SYMBOL_PATTERN})|"
    
    # 3. Number + Scale + Commodity/Shares (e.g., "10 million barrels", "500 shares")
    rf"{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?\s+(?:{COMMODITY_UNIT_PATTERN}|shares)|"
    
    # 4. Tabular Context (e.g., "amount of 500 million")
    rf"(?:amount|value|volume|strike\s+price)\s+of\s+{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?",
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
    rf"(?:amount|value|volume|strike\s+price)\s+of\s+\b{ZERO_NUM}\b",  # we do not do ignore case here
)


G = r"(?:\W+\w+){0,5}"  # up to 5 intermediate words

HEDGE_DOC_TERMS = [
    # 1. Documentation & Designation (Existing)
    rf"\bformally\s+document\b",
    r"\bdocumentation\b",
    rf"\bat\s+inception\b",
    rf"\b(?:in)?effectiveness\s+(?:portion)?\b",
    rf"\bhighly\s+effective\b",
    rf"\bqualif(?:y|ies|ied|ying){G}hedg(?:ing|es?)\b",
    rf"\b(?:not)?\s+designated\s+as\b",
    rf"\bhedg(?:e|ing)\s+(?:accounting|relationship|documentation|designation|treatment)\b",
    rf"\beconomic\s+relationship\b",
    rf"\bnature\s+of\b",
    r"\bearnings\s+impact\b",
    # 2. ASC 815 / FAS 133 Specifics (New & Tightened)
    # Matches: "Hedges of forecasted transactions\b", "Hedge of a recognized asset"
    r"\bhedges?\s+of\s+(?:(?:a|the|these|those|any)\s+)?(?:forecasted|recognized)\b",
    # Matches: "Changes in the fair value of a derivative"
    r"\bchanges?\s+in\s+(?:the\s+)?fair\s+values?\s+of\s+(?:a|the|these|those|any)\s+(?:derivatives?|hedging instruments?|hedges?)\b",
    # Matches: "Derivatives are recognized\b", "The derivative is recognized"
    r"\b(?:the\s+|these\s+|those\s+|a\s+)?(?:derivatives?|hedging instruments?|hedges?)\s+(?:are|is)\s+recognized\b",
    # Matches: "Variability of cash flows" (Safe if inside derivative/hedging paragraphs)
    r"\bvariabilit(?:y|ies)\s+of\s+cash\s+flows?\b",
    # Matches: "Hedge of net investment in foreign operation"
    r"\bhedges?\s+of\s+(?:the\s+)?net\s+investment\b",
    # Matches: "Recorded in OCI\b", "Recorded in earnings" (Standard mechanics)
    r"\b(?:recognized|recorded)\s+in\s+(?:other\s+comprehensive|earnings|oci)\b",
    r"\b(?:[\"“\'])?(?:net investment|fair\s+value|cash\s+flow)(?:[\"“\'])?\s+hedges?\b",
]


HEDGE_DOC_REGEX = build_regex(HEDGE_DOC_TERMS, use_sep=False)

def pnl_regex() -> Tuple[re.Pattern, re.Pattern, re.Pattern]:
    # 1. The Financial Targets (The "What")
    # Captures: "net income", "interest expense", "2024 earnings", "revenues"
    # Structure handles optional prefixes: "the", "net", "2024", "interest"
    pnl_target_bases = r"(?:earnings|incomes?|revenues?|expenses?|operations|results)"
    pnl_targets = rf"(?:the\s+)?(?:net\s+)?(?:\d{{4}}\s+)?(?:interest\s+)?(?:net\s+)?{pnl_target_bases}"

    # 2. The Prepositions (The "Connector")
    preps = r"(?:on|to|in|at|of|from)"

    # 3. The Action Words (The "How")
    # Nouns: "an impact", "an increase"
    impact_nouns = r"(?:impact|effect|increase|decrease|gain|loss(?:es)?|adjustments?|changes?)"
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
        # D. "Auxiliary" Impact (Had ... Impact ON Target)
        # Matches: "had a material impact on earnings", "has no effect on results"
        # Logic: Had/Have + (optional words) + Noun + Prep + Target
        rf"(?:had|have|has)(?:\W+\w+){{0,3}}\s+{impact_nouns}\s+{preps}\s+{pnl_targets}",
        rf"fair[- ]value {impact_nouns}",
        rf"unamortized debt discounts?",
        rf"write[- ]?offs?",
    ]

    pnl_terms2 = [
        # B. "Noun" Impact (Impact/Effect ON Target)
        # Matches: "impact on net income", "increase in 2024 earnings"
        # Logic: Noun + Prep + Target
        rf"{impact_nouns}\s+{preps}\s+{pnl_targets}",
        # C. "Verb" Change (Directly Changed Target)
        # Matches: "increased interest expense", "reducing net income"
        # Logic: Verb + (optional 3 words) + Target
        rf"{change_verbs}(?:\W+\w+){{0,3}}\s+{pnl_targets}",
        
    ]
    connectors = r"(?:the\s+|our\s+|a\s+|an\s+|these\s+|those\s+|any\s+|such\s+)?"
    # Extended prepositions for this specific context
    preps_extended = r"(?:of|on|from|related\s+to|associated\s+with|in)"
    target = create_target()
    ending = rf"{preps_extended}\s+{connectors}{target}"

    pnl_terms3 = [
        # "Changes in (the) fair value of (the) [Swap]"
        rf"{impact_nouns}\s+in\s+(?:{connectors})",
        # "Fair value changes of (the) [Swap]"
        rf"fair\s+value\s+{impact_nouns}",
        # "Gain/Loss on (the) [Swap]"
        rf"(?:realized|unrealized\s+)?(?:net\s+)?(?:gains?|loss(?:es)?)",
        # "Impact of (the) [Swap]"
        rf"{impact_nouns}",
        # "Ineffectiveness of (the) [Swap]"
        rf"(?:hedge\s+)?ineffectiveness",
        # "Amortization of (the) [Swap]"
        rf"amortization",
        # "Settlements on (the) [Swap]"
        rf"(?:cash\s+)?settlements?",
    ]

    return (
        build_regex(pnl_terms),
        build_regex(pnl_terms2),
        build_regex([build_compound(pnl_terms3, ending)]),
    )


PNL_CONTEXT_REGEX, PNL_CONTEXT_REGEX2, PNL_CONTEXT_REGEX3 = pnl_regex()

_prep_pattern = build_alternation([r"in", r"of", r"on"])


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

CHANGE_FV_REGEX = build_regex(
    [
        # LOGIC:
        # 1. Match "Change/ADJUSTments/etc in fair value"
        rf"{change_verb_pattern}\s+{_prep_pattern}\s+(?:the\s+)?fair\s+value",
    ]
)

def is_pnl(text, context_only = True):
    if NOTIONAL_REGEX.search(text):
        return False
    if context_only:
        return bool(PNL_CONTEXT_REGEX.search(text) or PNL_CONTEXT_REGEX3.search(text))
    return bool(PNL_CONTEXT_REGEX2.search(text) or 
                PNL_CONTEXT_REGEX.search(text) or 
                PNL_CONTEXT_REGEX3.search(text) or 
                HAD_CHANGE_REGEX.search(text) or 
                CHANGE_FV_REGEX.search(text))


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

WARRANT_TERMS = r"warrants?"
CONVERTIBLE_TERMS = rf"(?:convertibles?|{CONVERSION})"

SOPHISTICATED_TARGETS = re.compile(
    rf"\b(?:{WARRANT_TERMS}|{CONVERTIBLE_TERMS})\b",
    re.IGNORECASE,
)
WARRANT_TARGETS = re.compile(rf"\b{WARRANT_TERMS}\b", re.IGNORECASE)
CONVERTIBLE_TARGETS = re.compile(rf"\b{CONVERTIBLE_TERMS}\b", re.IGNORECASE)

# 2. Sophisticated Context (The "Why/How")
# Used to validate the sophisticated buffer.
SOPHISTICATED_CONTEXT_TERMS = [
    # REFINED: "embedded" must be followed by a relevant noun to be a self-validating signal
    r"embedded\s+derivatives?",
    r"bifurcat(?:e|ion|ed|ing)",
    r"derivative\s+(?:liabilit(?:y|ies)|assets?)",
    r"host\s+contracts?",
    r"conversion\s+(?:options?|features?)",
    r"fair\s+value\s+options?",
    r"warrants?.*not indexed to.*stock",
    r"warrants?(?:(?!\bnot\b).)*(?:accounted|classified)(?:(?!\bnot\b).)*(?:liability|derivative)",
    r"down[- ]round\s+protections?",
    r"fixed[- ]for[- ]fixed",
    r"anti[- ]dilution",
    r"ratchet",
    r"price\s+reset",
    r"net\s+cash\s+settl(?:e|ement|ed|ing)",
    r"fundamental\s+transactions?",
] + VALUATION_MODELS  # Black-Scholes, Monte Carlo, etc.

SOPHISTICATED_CONTEXT_REGEX = build_regex(SOPHISTICATED_CONTEXT_TERMS)

CONV = rf"convertible\s+(?:{_DEBT_TERMS}|securit(?:y|ies))" 
CONV_REGEX = re.compile(rf"\b{CONV}\b", re.IGNORECASE)
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

    # Required: target must have conv context
    if CONV_REGEX.search(text):
        return True

    return False

def is_warrant_target(text: str) -> bool:
    if not WARRANT_TARGETS.search(text):
        return False
    if IR_SOFT_REGEX.search(text):
        return False
    if EQ_SOFT_REGEX.search(text):
        return True
    return False

def is_convertible_target(text: str) -> bool:
    if not CONVERTIBLE_TARGETS.search(text):
        return False
    if IR_SOFT_REGEX.search(text):
        return False
    if CONV_REGEX.search(text):
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
