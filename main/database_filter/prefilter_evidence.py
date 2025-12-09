import re
from typing import Optional, Set, Tuple
from derivative_regex import ACTIVE_STATE_REGEX, FX_SOFT_REGEX, IR_SOFT_REGEX, LOOSE_GEN_REGEX, SOFT_REGEX, STRICT_REGEX, TERMINATION_ALL_REGEX, YEAR_REGEX, build_regex
from notional_filter import extract_values_and_years
from prefiltered_lib import DEADWEIGHT_TOKEN, EVIDENCE_TOKEN, FLUFF_EVIDENCE, POLICY_KILLED_EVIDENCE, SKIP_TOKEN, STRONG_EVIDENCE, TIME_KILLED_EVIDENCE, EvidenceReason, MinimalTextCleaner, NoiseReason, get_tag

_cleaner = MinimalTextCleaner()

VERB_MAP = {
    # --- MEDIUM EVIDENCE (States / Possession) ---
    # These imply "Being" or "Having".
    # Logic: Present tense = Medium Evidence. Past tense = Weak/Historical.
    "POSS": [
        r"hold(?:s|ing)?|held",  # Irregular: hold/held
        r"hav(?:e|ing)|had",  # Irregular: have/had
        r"maintain(?:s|ed|ing)?",
        r"possess(?:e|es|ed|ing)?",
        r"carr(?:y|ies|ied|ying)",  # "Carried at fair value"
        r"retain(?:s|ed|ing)?",
        r"remained?\s+(?:open|outstanding|active)",  # Phrasal state
        r"(?:is|are|was|were)\s+a\s+party\s+to",  # Phrasal state
    ],
    # --- WEAK EVIDENCE (Generic Usage) ---
    # Generic "Doing" verbs.
    # Logic: Vulnerable to Policy (if Present) and History (if Past).
    "PRU": [
        r"use(?:s|d|ing)?",
        r"utiliz(?:e|es|ed|ing)",
        r"employ(?:s|ed|ing)?",
        r"apply(?:ies|ied|ying)?",  # "We apply hedge accounting"
    ],
    # --- WEAK EVIDENCE (Transactions) ---
    # Specific actions.
    # Logic: Usually describe a moment in time (Past) or intent (Present).
    "ACT": [
        r"enter(?:s|ed|ing)?(?:\s+into)?",
        r"engag(?:e|es|ed|ing)(?:\s+in)?",
        r"execut(?:e|es|ed|ing)",
        r"transact(?:s|ed|ing)?",
        r"purchas(?:e|es|ed|ing)",
        r"issu(?:e|es|ed|ing)?",  # "Issued warrants"
        r"convert(?:s|ed|ing)?",  # "Converted notes"
    ],
    # --- PASSIVE / ACCOUNTING STATES ---
    # Often found in Policy headers.
    "ACCT": [
        r"hedg(?:e|es|ed|ing)",
        r"designat(?:e|es|ed|ing)",
        r"offset(?:s|ting)?",
        r"manag(?:e|es|ed|ing)",  # "Manage risk"
        r"mitigat(?:e|es|ed|ing)",
    ],
}

AUXILIARY_REGEX = re.compile(r"\b(?:have|has)\s+$", re.IGNORECASE)


# Example Usage Logic
def scan_verbs(text):
    found_signals = set()  # Use a set to avoid duplicates

    for category, patterns in VERB_MAP.items():
        # Combine patterns for this category
        full_regex = re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)

        for match in full_regex.finditer(text):
            verb_token = match.group(0)

            # 1. Default Detection (Base Logic)
            tense = detect_tense(verb_token)

            # 2. THE OVERRIDE: Check for "Have/Has"
            # Look at the text immediately preceding the match
            preceding_text = text[: match.start()]
            if AUXILIARY_REGEX.search(preceding_text):
                tense = "PRESENT"  # Force Present Tense (Present Perfect)

            # 3. Categorization Logic
            if category == "POSS":
                if tense == "PRESENT":
                    # "We hold" OR "We have held" -> Medium Evidence
                    found_signals.add(EvidenceReason.POSS)
                else:
                    # "We held" -> Weak Evidence
                    found_signals.add(EvidenceReason.PU)  # Past Usage

            elif category == "ACT":
                # "Entered" and "Have Entered" are both Actions.
                # In your hierarchy, ACT is WEAK regardless of tense,
                # but marking it as Present helps if you add logic later.
                found_signals.add(EvidenceReason.ACT)

            elif category == "PRU":
                if tense == "PRESENT":
                    found_signals.add(EvidenceReason.PRU)
                else:
                    found_signals.add(EvidenceReason.PU)  # Past Usage

    return found_signals


def detect_tense(verb: str) -> str:
    """
    Analyzes a specific verb token to detect if it is PAST or PRESENT/CONTINUOUS.

    Returns: 'PAST' | 'PRESENT'
    """
    verb = verb.lower().strip()

    # 1. Financial Irregulars (The "Strong" Past Tense)
    irregulars = {
        "held",
        "sold",
        "bought",
        "wrote",
        "took",
        "began",
        "became",
        "arose",
        "saw",
        "chose",
        "had",
        "withdrew",
        "stood",  # "Stood at"
    }

    if verb in irregulars:
        return "PAST"

    # 2. Standard Morphology
    # Ends in "ed" -> Past (entered, used, designated)
    if verb.endswith("ed"):
        return "PAST"

    # 3. Default to Present/Continuous
    # Covers: base form ("use"), third person ("uses"), participle ("using")
    # Note: "using" is technically continuous, which counts as Active/Present for our logic.
    return "PRESENT"


def evaluate_dominance(text: str, evidence_tags: set, noise_tags: set) -> str:
    """
    Decides the final fate of a paragraph based on the 4-Tier Survival Hierarchy.
    """

    # --- 1. STRONG CHECK (Immune) ---
    # Strong Evidence overrides EVERYTHING.
    # We exit immediately if found.
    if not evidence_tags.isdisjoint(STRONG_EVIDENCE):
        return apply_tags(text, evidence_tags, noise_tags)

    # =========================================================
    # DEFINE CUMULATIVE KILLERS
    # =========================================================

    # KILLER SET A: The "Reality Check" Killers
    # These kill everything except Strong Anchors.
    TIME_KILLERS = {
        NoiseReason.TIME,  # "In 2018..."
        NoiseReason.HIST_BLOCK,  # "History..."
        NoiseReason.TRADING,  # "We do not trade..."
        NoiseReason.TERM,  # "Terminated..."
        NoiseReason.NEG,  # "Did not hold..."
        NoiseReason.HYPO,  # "If we hold..." (Dangerous for states)
        NoiseReason.ZERO,  # "Notional was 0"
        NoiseReason.NPNS,  # "Normal purchase/sale exemption"
    }

    # KILLER SET B: The "Boilerplate" Killers (Cumulative)
    # Includes everything above + Policy definitions.
    POLICY_KILLERS = TIME_KILLERS | {
        NoiseReason.POLICY,  # "Our policy is to..."
        NoiseReason.DEF,  # "Swap shall mean..."
        NoiseReason.ACCT_STD,  # "FASB ASU 2017-12..."
    }

    # =========================================================
    # EVALUATE TIERS
    # =========================================================

    # --- 2. MEDIUM CHECK (Time-Killed) ---
    # Logic: Dies to TIME_KILLERS. Survives POLICY.
    if not evidence_tags.isdisjoint(TIME_KILLED_EVIDENCE):
        # Check against Set A
        if noise_tags.isdisjoint(TIME_KILLERS):
            return apply_tags(text, evidence_tags, noise_tags)

    # --- 3. WEAK CHECK (Policy-Killed) ---
    # Logic: Dies to POLICY_KILLERS (Time + Policy).
    if not evidence_tags.isdisjoint(POLICY_KILLED_EVIDENCE):
        # Check against Set B (The Superset)
        if noise_tags.isdisjoint(POLICY_KILLERS):
            return apply_tags(text, evidence_tags, noise_tags)

    # --- 4. FLUFF CHECK (Fragile) ---
    # Logic: Dies to ANY Noise.
    if not evidence_tags.isdisjoint(FLUFF_EVIDENCE):
        # Must be 100% clean
        if not noise_tags:
            return apply_tags(text, evidence_tags, [])

    # --- FALLBACK ---
    return mark_as_deadweight(text, NoiseReason.ANLZ)


# Regex to parse existing tags from the text
# Matches: _S<HIST> or _D<ANLZ>
TAG_PARSER = re.compile(r"(_[SD])<([^>]+)>")
def apply_tags(
    text: str, evidence_tags: Set[EvidenceReason], noise_tags: Set[NoiseReason]
) -> str:
    """
    Constructs the final tagged string.
    Format: _E<NVY> _S<HIST> Original text...
    """
    # 1. Convert Enums to Tag Strings
    e_str = " ".join(
        [
            get_tag(EVIDENCE_TOKEN, t)
            for t in sorted(evidence_tags, key=lambda x: x.value)
        ]
    )
    n_str = " ".join(
        [get_tag(SKIP_TOKEN, t) for t in sorted(noise_tags, key=lambda x: x.value)]
    )

    # 2. Combine Prefixes
    prefix = f"{e_str} {n_str}".strip()

    # 3. Attach to text
    if prefix:
        return f"{prefix} {text}"
    return text


def mark_as_deadweight(text: str, reason: NoiseReason) -> str:
    """
    Marks the paragraph as Deadweight (dropped).
    Format: _D<ANLZ> Original text...
    """
    # Note: We usually strip internal _S tags if marking as deadweight to save space,
    # but keeping them helps with debugging "Why was this dropped?".
    # Let's wrap the reason.
    return f"{get_tag(DEADWEIGHT_TOKEN, reason)} {text}"


def parse_existing_tags(text: str) -> Tuple[str, Set[NoiseReason]]:
    """
    Extracts existing _S<TAGS> from input text so we can process them logically.
    Returns: (clean_text, set_of_noise_reasons)
    """
    noise_tags = set()

    # 1. Find all tags
    matches = list(TAG_PARSER.finditer(text))

    if not matches:
        return text.strip(), noise_tags

    # 2. Extract Logic
    for m in matches:
        token_type = m.group(1)
        reason_str = m.group(2)

        if token_type == SKIP_TOKEN.strip():  # "_S"
            try:
                # Convert string "HIST" back to NoiseReason.HIST
                noise_tags.add(NoiseReason(reason_str))
            except ValueError:
                pass  # Ignore unknown tags

    # 3. Remove tags from text to get "Clean Text" for Regex scanning
    # (We don't want regexes matching on the tags themselves)
    clean_text = TAG_PARSER.sub("", text).strip()
    # Collapse extra spaces left by removal
    clean_text = re.sub(r"\s+", " ", clean_text)

    return clean_text, noise_tags


def check_future_maturity(text: str, reporting_year: int) -> Optional[EvidenceReason]:
    """
    Checks for Future Maturity.
    Splits into MAT_FUT (Strong) vs MAT_AMB_FUT (Medium).
    """
    if not reporting_year:
        return None

    # 1. Topic Gate: Must mention Termination/Maturity keywords
    if not TERMINATION_ALL_REGEX.search(text):
        return None

    # 2. Subject Classification
    is_strict = bool(
        STRICT_REGEX.search(text)
        or IR_SOFT_REGEX.search(text)
        or FX_SOFT_REGEX.search(text)
    )
    is_soft = bool(SOFT_REGEX.search(text) or LOOSE_GEN_REGEX.search(text))

    if not (is_strict or is_soft):
        return None

    # 3. Time Gate
    clean_text = _cleaner.clean_numerics(text, remove_years=False)
    years = [int(y) for y in YEAR_REGEX.findall(clean_text)]

    if not any(y > reporting_year for y in years):
        return None

    # 4. Decision
    # "Swap matures in 2026" -> Strong
    if is_strict:
        return EvidenceReason.MAT_FUT

    # "Agreement expires in 2026" -> Medium (Could be a lease, dies to Trading Denial)
    return EvidenceReason.MAT_AMB_FUT

# --- QUANTITATIVE CONTEXT GATES ---

# 1. Notional (Volume of the bet)
NOTIONAL_TERMS = [
    r"notional",
    r"face\s+(?:amount|value)",
    r"par\s+value",
    r"contract\s+(?:amount|value|volume)",  # "Contract amount of $10M"
]

# 2. Fair Value (Value of the bet)
FAIR_VALUE_TERMS = [
    r"fair\s+value",
    r"carrying\s+(?:amount|value)",
    r"mark(?:ed)?\s+to\s+market",
    r"market\s+value",
    r"asset\s+value",
    r"liability\s+value",
    r"instrument\s+value",
    r"valuation",
]

# Compile for speed
NOTIONAL_CONTEXT_REGEX = build_regex(NOTIONAL_TERMS)
FAIR_VALUE_CONTEXT_REGEX = build_regex(FAIR_VALUE_TERMS)

def check_quantitative_evidence(
    text: str, reporting_year: int
) -> Optional[EvidenceReason]:
    """
    Checks for Quantitative Evidence (NVY/FVY/QUANT_NY).

    CRITICAL: Validates that the number refers to Notional or Fair Value,
    excluding generic PnL/Income statements.
    """

    # 1. Determine Context (The Gatekeeper)
    is_notional = bool(NOTIONAL_CONTEXT_REGEX.search(text))
    is_fair_value = bool(FAIR_VALUE_CONTEXT_REGEX.search(text))
    has_mention = bool(SOFT_REGEX.search(text) or LOOSE_GEN_REGEX.search(text))

    # We bail out immediately.
    if not has_mention:
        return None

    is_strict = bool(STRICT_REGEX.search(text))

    # 2. Extract Data
    # (extract_values_and_years returns found years and values)
    clean_text = _cleaner.clean_for_quant_analysis(text)  # Use your cleaning lib
    years_found, values_found = extract_values_and_years(clean_text)

    if not values_found:
        return None

    # 3. Classify based on Year Presence
    # (Any value > 0 is valid here, as long as context matches)

    has_relevant_year = any(y >= reporting_year for y in years_found)

    if is_notional or (is_strict and not is_fair_value):
        return EvidenceReason.NVY if has_relevant_year else EvidenceReason.NVNY

    if is_fair_value:
        if is_strict:
            return EvidenceReason.FVY if has_relevant_year else EvidenceReason.FVNY
        else:
            return EvidenceReason.FVAIY if has_relevant_year else EvidenceReason.FVAINY

    return None

# GROUP A: PREPOSITIONS (Sentence-Wide Scope)
# These apply to the entire sentence. If found, we just need a Subject + Year anywhere.
ACTIVE_PREPOSITIONS = [
    r"as\s+of",  # "As of Dec 31..."
    r"at\s+year[- ]end",  # "At year-end..."
    r"at\s+the\s+end\s+of",  # "At the end of 2024"
    r"at\s+the\s+close\s+of",  # "At the close of 2024"
    r"stood\s+at",  # "Stood at $10M"
]

# GROUP B: ADJECTIVES (Noun-Modifying Scope)
# These modify the noun. Ideally, they should be "near" the instrument,
# but in a single sentence, co-occurrence is usually 99% safe.
ACTIVE_ADJECTIVES = [
    r"outstanding",
    r"active",
    r"open\s+positions?",
    r"remaining",
    r"consist(?:s|ed)\s+of",  # "Portfolio consists of..."
    r"compris(?:e|es|ed)\s+of",
]

# Compile them
ACTIVE_PREP_REGEX = re.compile(
    r"\b(?:" + "|".join(ACTIVE_PREPOSITIONS) + r")\b", re.IGNORECASE
)


ACTIVE_ADJ_REGEX = re.compile(
    r"\b(?:" + "|".join(ACTIVE_ADJECTIVES) + r")\b", re.IGNORECASE
)


def check_active_state_year(text: str, reporting_year: int) -> Optional[EvidenceReason]:
    """
    Determines if text represents Active State anchored to a date (AS_YEAR).
    Crucial for distinguishing 'As of 2024' (Strong) from 'In 2024' (Weak).
    """
    if not reporting_year:
        return None

    # 1. Subject Gate (Must mention instrument)
    if not (SOFT_REGEX.search(text) or LOOSE_GEN_REGEX.search(text)):
        return None

    # 2. Anchor Gate (Prepositions OR Adjectives)
    # We NEED 'Active Prepositions' to catch cases like "As of 2024..."
    # where no other adjective ("outstanding") exists.
    has_prep = bool(ACTIVE_PREP_REGEX.search(text))
    has_adj = bool(ACTIVE_ADJ_REGEX.search(text))

    if not (has_prep or has_adj):
        return None

    # 3. Time Gate
    # Use existing cleaner to allow year regex to work
    clean_text = _cleaner.clean_numerics(text, remove_years=False)
    years = [int(y) for y in YEAR_REGEX.findall(clean_text)]

    if any(y >= reporting_year for y in years):
        return EvidenceReason.AS_YEAR

    return None


def check_possession(text: str) -> Optional[EvidenceReason]:
    """
    Checks for explicit possession verbs (POSS).

    Logic:
    1. Matches POSS_REGEX (e.g., "We hold", "We maintain").
    2. Must NOT be negated (handled by regex lookbehind).
    """
    pass


def check_balance_sheet_location(text: str) -> Optional[EvidenceReason]:
    """
    Checks for accounting location descriptions (BS_LOC).

    Logic:
    1. Matches BS_LOC_REGEX (e.g., "Recorded in Other Assets").
    2. Implies standard practice/current state.
    """
    pass


def check_continuous_usage(text: str) -> Optional[EvidenceReason]:
    """
    Checks for continuous/participle usage (CONT_USE).

    Logic:
    1. Matches CONT_USE_REGEX (e.g., "is hedging", "are designating").
    """
    pass


def check_generic_usage(text: str) -> Optional[EvidenceReason]:
    """
    Checks for generic present tense usage (PRU).

    Logic:
    1. Matches PRU_REGEX (e.g., "We use", "We derivative").
    2. Highly vulnerable to Policy noise.
    """
    pass


def check_transaction_action(text: str) -> Optional[EvidenceReason]:
    """
    Checks for transactional verbs (ACT).

    Logic:
    1. Matches ACT_REGEX (e.g., "Entered into", "Purchased").
    2. Can be historical or generic.
    """
    pass


def check_pnl_recognition(text: str) -> Optional[EvidenceReason]:
    """
    Checks for PnL recognition statements (PNL_REC).

    Logic:
    1. Matches PNL_REGEX (Focus on 'Recognized', 'Recorded gain').
    """
    pass


def check_remaining_term(text: str) -> Optional[EvidenceReason]:
    """
    Checks for relative duration (REM_TERM).

    Logic:
    1. Matches REM_TERM_REGEX (e.g., "Remaining term of 2 years").
    """
    pass


def scan_sentence_for_evidence(text: str, reporting_year: int) -> Set[EvidenceReason]:
    """
    Runs all checkers on a single sentence and aggregates the Evidence Enums.
    """
    evidence = set()

    return evidence
