import re
from typing import Optional, Set, Tuple
from derivative_regex import ACTIVE_STATE_REGEX, FX_SOFT_REGEX, IR_SOFT_REGEX, LOOSE_GEN_REGEX, SOFT_REGEX, STRICT_REGEX, TERMINATION_ALL_REGEX, YEAR_REGEX, build_alternation, build_regex
from prefilter_database import is_sophisticated_content
from notional_filter import extract_values_and_years
from prefiltered_lib import DEADWEIGHT_TOKEN, EVIDENCE_TOKEN, FLOW_EVIDENCE, FLOW_KILLERS, FLUFF_EVIDENCE, POLICY_KILLED_EVIDENCE, POLICY_KILLERS, SKIP_TOKEN, STRONG_EVIDENCE, TIME_KILLED_EVIDENCE, TIME_KILLERS, EvidenceReason, MinimalTextCleaner, NoiseReason, get_tag

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
        r"secur(?:e|es|ed|ing)",
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


def evaluate_dominance(text: str, evidence_tags: set, noise_tags: set) -> str:
    """
    Decides the final fate of a paragraph based on the Survival Hierarchy.
    """

    # --- 1. STOCK CHECK (Titanium) ---
    if not evidence_tags.isdisjoint(STRONG_EVIDENCE):
        return apply_tags(text, evidence_tags, noise_tags)

    # --- 1.5. FLOW CHECK (Conditional Strong) ---
    # "Entered in 2024" - Ignores History, Dies to Termination
    if not evidence_tags.isdisjoint(FLOW_EVIDENCE):
        if noise_tags.isdisjoint(FLOW_KILLERS):
            return apply_tags(text, evidence_tags, noise_tags)

    # --- 2. MEDIUM CHECK (Standard) ---
    # "We hold swaps" - Dies to History AND Termination
    if not evidence_tags.isdisjoint(TIME_KILLED_EVIDENCE):
        if noise_tags.isdisjoint(TIME_KILLERS):
            return apply_tags(text, evidence_tags, noise_tags)

    # --- 3. WEAK CHECK (Policy) ---
    # "We enter into..." - Dies to Policy
    if not evidence_tags.isdisjoint(POLICY_KILLED_EVIDENCE):
        if noise_tags.isdisjoint(POLICY_KILLERS):
            return apply_tags(text, evidence_tags, noise_tags)

    # --- 4. FLUFF CHECK ---
    if not evidence_tags.isdisjoint(FLUFF_EVIDENCE):
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

    # 3. Time Gate
    clean_text = _cleaner.clean_numerics(text, remove_years=False)
    
    # 2. Subject Classification
    is_strict = check_derivative(clean_text)
    is_soft = check_mention(clean_text)

    if not (is_strict or is_soft):
        return None

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
    clean_text = _cleaner.clean_for_quant_analysis(text)  # Use your cleaning lib
    has_mention = check_mention(clean_text)

    # We bail out immediately.
    if not has_mention:
        return None

    is_strict = check_derivative(clean_text)
    # 2. Extract Data
    # (extract_values_and_years returns found years and values)
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

def check_mention(clean_text):
    return bool(
        SOFT_REGEX.search(clean_text) or LOOSE_GEN_REGEX.search(clean_text)
    )

def check_derivative(text):
    return bool(STRICT_REGEX.search(text) or IR_SOFT_REGEX.search(text) or FX_SOFT_REGEX.search(text) or is_sophisticated_content(text))

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


# Assuming you construct this regex from VERB_MAP["POSS"]
# Example verbs: held, hold, holding, maintain, maintained, carry, carried, possess
POSS_VERB_REGEX = build_regex(VERB_MAP["POSS"])
USAGE_VERB_REGEX = build_regex(VERB_MAP["PRU"])
def check_active_state_year(text: str, reporting_year: int) -> Optional[EvidenceReason]:
    """
    Determines if text represents Active State anchored to a date.
    
    Now Consolidates:
    1. Prepositions ("As of")
    2. Adjectives ("Outstanding", "Open")
    3. Possession Verbs ("Held", "Maintained") -> NEW
    """
    if not reporting_year:
        return None

    # Use existing cleaner to allow year regex to work
    clean_text = _cleaner.clean_numerics(text, remove_years=False)

    # --- 1. Subject Gate & Classification ---
    # Does it mention any instrument at all?
    if not check_mention(clean_text):
        return None

    # Is it a specific derivative (Swap/Option) or generic (Contract/Agreement)?
    has_strict = check_derivative(clean_text)

    # --- 2. Anchor Gate (Consolidated) ---
    # We now accept three types of anchors to prove the state exists:
    # A. Preposition: "As of 2024..."
    # B. Adjective: "Swaps outstanding..."
    # C. Possession Verb: "We held swaps..."

    has_prep = bool(ACTIVE_PREP_REGEX.search(text))
    has_adj = bool(ACTIVE_ADJ_REGEX.search(text))
    has_poss_verb = bool(POSS_VERB_REGEX.search(text))
    has_use = bool(USAGE_VERB_REGEX.search(text)) # In 20XX we are using
    has_current_state = ACTIVE_STATE_REGEX.search(text)

    # If it lacks all three anchors, it's just a mention (e.g., "We discuss swaps..."), not a state.
    if not (has_prep or has_adj or has_poss_verb or has_current_state or has_use):
        return None

    # --- 3. Time Gate ---
    years = [int(y) for y in YEAR_REGEX.findall(clean_text)]
    has_relevant_year = any(y >= reporting_year for y in years)

    if not has_relevant_year and not has_current_state:
        return None

    # --- 4. Decision ---
    # If Strict Instrument ("Held Swaps in 2024") -> Tier 1 (Strong)
    if has_strict:
        return EvidenceReason.AS_YEAR

    # If Soft Instrument ("Held Contracts in 2024") -> Tier 2 (Medium)
    return EvidenceReason.ASAIY


def check_active_state_general(text: str) -> Optional[EvidenceReason]:
    """
    Checks for General (Yearless) statements of Possession or Usage.

    Assumption:
    - Input text has already passed 'NEG', 'HYPO', 'ZERO' noise filters.

    Logic:
    1. Gate: Must mention an instrument.
    2. Action: Must use a Possession verb ("hold") or Usage verb ("utilize").
    """
    # Use existing cleaner
    clean_text = _cleaner.clean_numerics(text)

    # --- 1. Subject Gate ---
    if not check_mention(clean_text):
        return None

    # --- 2. Verb Gate ---
    # We combine both Possession and Usage here.
    # "We maintain a portfolio" (Possession) OR "We use swaps to hedge" (Usage)
    has_poss = bool(POSS_VERB_REGEX.search(clean_text))
    has_use = bool(USAGE_VERB_REGEX.search(clean_text))

    if has_poss or has_use:
        has_strict = check_derivative(clean_text)
        if has_strict:
            return EvidenceReason.CONT_USE
        else:
            return EvidenceReason.CONT_USE_AMB

    return None


# 1. Flexible Separator (Adjust '5' to allow for more/fewer intervening words)
# Matches 0 to 5 non-whitespace tokens/words
FLEX_SEP = r"(?:\s+\S+){0,5}\s+"

FINANCIAL_OUTCOME_VERBS = [
    "recognized in",
    "recorded in",
    "reflected in",
    "reported in",
    "included in",
    "classified as",
    "component of",
]

# 2. Simplified Locations (Core Nouns Only)
# removed "AOCI" and "consolidated" adjectives
BALANCE_SHEET_LOCATIONS = [
    "other income",  # Catches "Other income (expense)" via partial match if strictness is low
    "comprehensive income",
    "earnings",
    "net income",
    "statement of operations",
    "balance sheets",
    "equity",
    "profit and loss",
]

# --- Regex Construction ---

# Escape locations automatically so you don't have to type "income \(expense\)"
# We sort by length (descending) so "statement of operations" matches before "operations" (if you had it)
locs_escaped = [re.escape(x) for x in BALANCE_SHEET_LOCATIONS]
locs_pattern = build_alternation(locs_escaped)
verbs_pattern = build_alternation(FINANCIAL_OUTCOME_VERBS)

# Pattern: (Verb Phrase) + (0-5 Words) + (Location)
# Example matches:
# "recorded in earnings"
# "recorded in consolidated earnings"
# "recorded in the company's consolidated earnings"
BS_LOC_REGEX = re.compile(f"{verbs_pattern}{FLEX_SEP}{locs_pattern}", re.IGNORECASE)


def check_balance_sheet_location(text: str) -> Optional[EvidenceReason]:
    """
    Checks for accounting location descriptions (BS_LOC).

    Why Single Tier?
    The specificity of the location ("OCI", "Earnings") validates generic terms
    like "Contracts." If a "Contract" is "Recorded in OCI", it is a financial instrument.
    """
    clean_text = _cleaner.clean_numerics(text)

    # --- 1. Subject Gate ---
    # We still need this to ensure we aren't picking up "Revenue is recorded in..."
    if not check_mention(clean_text):
        return None

    # --- 2. Pattern Gate ---
    # Matches: "Natural gas contracts ... recorded in ... earnings"
    if BS_LOC_REGEX.search(clean_text):
        return EvidenceReason.BS_LOC

    return None

TRANS_VERB_REGEX = build_regex(VERB_MAP["ACT"])

def check_transaction_action(
    text: str, reporting_year: int
) -> Optional[EvidenceReason]:
    """
    Checks for Transactional Events (Flow).

    Logic:
    1. Gate: Must mention an instrument.
    2. Time Check:
       - If Year < Reporting Year -> DISCARD (Historical noise).
       - If Year >= Reporting Year -> ACT_YEAR (Fresh Transaction).
       - If No Year -> ACT_GEN (General Policy).
    """
    if not reporting_year:
        return None

    # Keep years for validation
    clean_text = _cleaner.clean_numerics(text, remove_years=False)

    # --- 1. Subject Gate ---
    if not check_mention(clean_text):
        return None

    # --- 2. Verb Gate ---
    if not TRANS_VERB_REGEX.search(clean_text):
        return None

    # --- 3. Time Gate ---
    # Find all years in the text
    years = [int(y) for y in YEAR_REGEX.findall(clean_text)]
    is_strict = check_derivative(clean_text)
    # CASE A: No years found -> General Policy ("We enter into swaps")
    if not years:
        return EvidenceReason.ACT_GEN

    # CASE B: Years found -> Must be current or future
    # If ANY year in the text is valid (>= reporting_year), we accept it.
    if any(y >= reporting_year for y in years):
        return (
            EvidenceReason.ACT_YEAR if is_strict else EvidenceReason.ACT_AMB_YEAR
        ) 

    # CASE C: Years found, but all are old -> Historical Noise ("Entered in 2019")
    return None

# --- PnL / Performance Context ---
# We strip the complex lookaheads. We just want to know:
# "Is this sentence talking about gains, losses, or income?"

PNL_TERMS = [
    r"(?:realized|unrealized)\s+(?:gains?|loss|losses)",  # "Unrealized loss"
    r"(?:net\s+)?(?:gains?|loss|losses)\s+on",  # "Net gain on...", "Loss on..."
    r"mark(?:\s+to)?[- ]market",  # "Mark-to-market"
    r"change(?:s)?\s+in\s+fair\s+value",  # "Changes in fair value"
    r"ineffective\s+portion",  # "Ineffective portion"
    r"hedge\s+ineffectiveness",  # "Hedge ineffectiveness"
    r"reclassifi(?:ed|cation).{0,20}earnings",  # "Reclassified into earnings" (Limited wildcards)
    r"results\s+of\s+operations",  # "Results of operations"
    r"impact(?:ed)?\s+(?:net\s+)?income",  # "Impacted net income"
]


# Build the simple regex
PNL_CONTEXT_REGEX = build_regex(PNL_TERMS)
def check_pnl_context(text: str) -> Optional[EvidenceReason]:
    """
    Checks for PnL / Performance context.

    Logic:
    1. Topic Gate: Must match PnL keywords (Gains/Losses).
    2. Subject Gate: Must be STRICT (Swaps/Options).
       We ignore "Gain on Contracts" to avoid physical commodity noise.

    Returns:
    Tier 4 (FLUFF) - This is context, not proof of holding.
    """
    # 1. Topic Gate (Fastest check)
    if not PNL_CONTEXT_REGEX.search(text):
        return None

    clean_text = _cleaner.clean_numerics(text)

    # 2. Subject Gate (Strict Only)
    # We bail out if it's just "Gain on contracts" (Soft)
    if not check_derivative(clean_text):
        return None

    # 3. Tag it
    return EvidenceReason.PNL_REC


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
