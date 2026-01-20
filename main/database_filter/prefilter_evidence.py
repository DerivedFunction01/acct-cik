from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import re
import sqlite3
from typing import Optional, Set, NamedTuple, List, Tuple

from tqdm import tqdm
from defs.verb_regex import (
    ACCT_VERB_REGEX,
    POSS_VERB_REGEX,
    TERMINATION_ALL_REGEX,
    TRANS_VERB_REGEX,
    USAGE_VERB_REGEX,
    is_immaterial,
    ACTIVE_VERB_REGEX,
)
from defs.derivative_lib import SOFT_REGEX, STRICT_REGEX
from defs.fx_regex import FX_SOFT_REGEX
from defs.gen_regex import NOTIONAL_REGEX, PRECISE_LOOSE_GEN_REGEX
from defs.ir_regex import IR_SOFT_REGEX
from defs.shared_context import SETTLEMENT_MECHANICS_REGEX, VALUATION_MODELS_REGEX
from defs.exclusion_regex import AOCI_NOISE_REGEX
from table_processor import TABLE_ANCHOR
from defs.regex_lib import SENTENCE_SPLIT_PATTERN, build_alternation, build_regex
from defs.prefiltered_lib import (
    ACTIVE_STATE_REGEX,
    IMMATERIAL_KILLED_EVIDENCE,
    YEAR_REGEX,
    DEADWEIGHT_TOKEN,
    EVIDENCE_TOKEN,
    FLOW_EVIDENCE,
    FLOW_KILLERS,
    FLUFF_EVIDENCE,
    HEDGE_DOC_REGEX,
    POLICY_KILLED_EVIDENCE,
    POLICY_KILLERS,
    SKIP_TOKEN,
    STRONG_EVIDENCE,
    TIME_KILLED_EVIDENCE,
    TIME_KILLERS,
    EvidenceReason,
    MinimalTextCleaner,
    NoiseReason,
    Reason,
    Stage,
    convertible_ir,
    get_tag,
    is_pnl,
    is_sophisticated_content,
    mark_as_deadweight,
    mark_as_evidence,
    parse_noise_tags,
    HAD_CHANGE_REGEX,
    CHANGE_FV_REGEX,
)
import multiprocessing as mp

_cleaner = MinimalTextCleaner()


NOTIONAL_TERMS = [
    r"notional",
    r"(?:contract|face|par)\s+(?:amount|value|volume)",
]

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

ACTIVE_PREPOSITIONS = [
    r"as\s+of",
    r"at\s+year[- ]end",
    r"at\s+the\s+end\s+of",
    r"at\s+the\s+close\s+of",
    r"stood\s+at",
]

ACTIVE_ADJECTIVES = [
    r"outstanding",
    r"active",
    r"open\s+positions?",
    r"remaining",
    r"consist(?:s|ed)\s+of",
    r"compris(?:e|es|ed)\s+of",
    r"new",
    r"current",
]

FINANCIAL_OUTCOME_VERBS = [
    "recognized in",
    "recorded in",
    "reflected in",
    "reported in",
    "included in",
    "classified as",
    "component of",
]

BALANCE_SHEET_LOCATIONS = [
    "other income",
    "comprehensive income",
    "earnings",
    "net income",
    "statement of operations",
    "balance sheets",
    "equity",
    "profit and loss",
]


REM_TERM_PHRASES = [
    r"remaining\s+(?:contractual\s+)?terms?",
    r"weighted\s+average\s+(?:remaining\s+)?terms?",
    r"terms?\s+to\s+maturity",
    r"terms?\s+of\s+(?:the\s+)?(?:derivatives?|instruments?|swaps?|hedges?)",
    r"maximum\s+terms?",
    r"average\s+life",
]

# Compile all regexes once at module load
NOTIONAL_CONTEXT_REGEX = build_regex(NOTIONAL_TERMS)
FAIR_VALUE_CONTEXT_REGEX = build_regex(FAIR_VALUE_TERMS)
ACTIVE_PREP_REGEX = build_regex(ACTIVE_PREPOSITIONS)
ACTIVE_ADJ_REGEX = build_regex(ACTIVE_ADJECTIVES)


locs_escaped = [re.escape(x) for x in BALANCE_SHEET_LOCATIONS]
locs_pattern = build_alternation(locs_escaped)
verbs_pattern = build_alternation(FINANCIAL_OUTCOME_VERBS)
FLEX_SEP = r"(?:\s+\S+){0,5}\s+"
BS_LOC_REGEX = re.compile(f"{verbs_pattern}{FLEX_SEP}{locs_pattern}", re.IGNORECASE)


REM_TERM_REGEX = build_regex(REM_TERM_PHRASES)


# =============================================================================
# VERB CHECK RESULTS (Cached at sentence level)
# =============================================================================


class VerbCheckResults(NamedTuple):
    """Cached results of all verb checks for a sentence."""

    has_active_verb: bool
    has_transaction: bool
    has_poss_or_use: bool
    has_poss_verb: bool
    has_usage_verb: bool
    is_specific: bool


def check_verbs(text: str) -> VerbCheckResults:
    """
    Perform all verb checks once per sentence.
    Returns cached results to avoid redundant regex calls.
    """
    has_poss = bool(POSS_VERB_REGEX.search(text))
    has_usage = bool(USAGE_VERB_REGEX.search(text))
    has_active = bool(ACTIVE_VERB_REGEX.search(text))
    is_specific = False
    if (STRICT_REGEX.search(text) or IR_SOFT_REGEX.search(text) or FX_SOFT_REGEX.search(text)): # avoid false positives for equity options, natural gas contracts
        is_specific = True
    return VerbCheckResults(
        has_active_verb=has_active,
        has_transaction=bool(TRANS_VERB_REGEX.search(text)),
        has_poss_verb=has_poss,
        has_usage_verb=has_usage,
        has_poss_or_use=has_poss or has_usage,
        is_specific= is_specific and has_active,
    )


# =============================================================================
# HELPER FUNCTIONS (Global checks - called once per paragraph)
# =============================================================================


def check_mention(text: str) -> bool:
    """Check if text mentions any derivative instrument."""
    return bool(SOFT_REGEX.search(text) or PRECISE_LOOSE_GEN_REGEX.search(text))


def check_derivative_global(text: str) -> bool:
    """Global check - returns True if text is a STRICT derivative mention."""
    return bool(
        STRICT_REGEX.search(text)
        or is_sophisticated_content(text)
        or NOTIONAL_REGEX.search(text)
    )


# =============================================================================
# EVIDENCE CHECKERS (Now take VerbCheckResults as parameter)
# =============================================================================


def check_quantitative_evidence(
    text: str,
    reporting_year: int,
    is_strict_derivative: bool,
    verbs: VerbCheckResults,
    skip_year: bool = False,
    has_active_context: bool = False,
    force_transaction_context: bool = False,
) -> Optional[Reason]:
    """Check for Quantitative Evidence (NVY/FVY)."""
    from prefilter_tagging import extract_values_and_years

    if not reporting_year and not skip_year:
        return None

    is_notional = bool(NOTIONAL_CONTEXT_REGEX.search(text))
    is_fair_value = bool(FAIR_VALUE_CONTEXT_REGEX.search(text))
    has_mention = check_mention(text)

    if not has_mention and not (is_notional or is_fair_value):
        return None

    years_found, values_found = extract_values_and_years(text)

    if not values_found:
        return None

    has_relevant_year = (
        any(y >= reporting_year for y in years_found) if not skip_year else True
    )
    
    if not has_relevant_year and has_active_context:
        has_relevant_year = True

    # 1. NOTIONAL SAFETY: Notional always overrides PnL context.
    if is_notional:
        if not verbs.has_transaction and not force_transaction_context:
            return EvidenceReason.NVY if has_relevant_year else EvidenceReason.NVNY
        else:
            return EvidenceReason.ACT_NV_YEAR if has_relevant_year else EvidenceReason.NVNY

    # 2. FAIR VALUE LOGIC
    if is_fair_value:
        # 1. STRICT PNL CHECK (The Override)
        if HAD_CHANGE_REGEX.search(text):
            return NoiseReason.PNL

        # 2. STANDARD PNL CHECK (The Rescue Logic)
        if CHANGE_FV_REGEX.search(text):
            if not verbs.has_active_verb:
                return NoiseReason.PNL

        # 3. VALID EVIDENCE
        # Upgrade to Strict Evidence if we have a specific soft mention (e.g. "interest rate agreement")
        if is_strict_derivative or verbs.is_specific:
            if not verbs.has_transaction and not force_transaction_context:
                return EvidenceReason.FVY if has_relevant_year else EvidenceReason.FVNY
            else:
                return EvidenceReason.ACT_FV_YEAR if has_relevant_year else EvidenceReason.FVNY
        else:
            return EvidenceReason.FVAIY if has_relevant_year else EvidenceReason.FVAINY

    # ...UNLESS we see an Active Verb elsewhere in the sentence.
    if verbs.has_active_verb:
        # But we need more restrictions: This interest swap agreement had a positive impact on 2003 earnings, reducing interest expense by $0.3 million.
        # Maybe perform a quant sub -> $10 = _Q, then check sub out earnings/expense/income/ (of/by) _Q: if _Q still exists, next step
        # Check if it is _Q {debt_terms} and sub that out. if _Q still exists next step
        if verbs.is_specific:
            if not verbs.has_transaction and not force_transaction_context:
                return (
                    EvidenceReason.VY if has_relevant_year else EvidenceReason.VNY
                )
            else:
                return EvidenceReason.ACT_V_YEAR if has_relevant_year else EvidenceReason.VNY

    return None


def check_future_maturity(
    text: str,
    reporting_year: int,
    is_strict_derivative: bool,
    verbs: VerbCheckResults,
) -> Optional[Reason]:
    """Check for Future Maturity."""
    if not reporting_year:
        return None

    if not TERMINATION_ALL_REGEX.search(text):
        return None

    if not check_mention(text):
        return None

    years = [int(y) for y in YEAR_REGEX.findall(text)]

    if not any(y > reporting_year for y in years):
        is_notional = bool(NOTIONAL_CONTEXT_REGEX.search(text))
        if is_notional:
            return None
        if SETTLEMENT_MECHANICS_REGEX.search(text):
            return NoiseReason.STL_MECH
        return NoiseReason.PNL

    if verbs.has_transaction:
        # Skip
        return None
    else:
        evidence = check_quantitative_evidence(
            text, reporting_year, is_strict_derivative, verbs, skip_year=True
        )
        
        if is_strict_derivative and evidence:
            if evidence in {EvidenceReason.NVY, EvidenceReason.NVNY, EvidenceReason.ACT_NV_YEAR}:
                return EvidenceReason.MAT_FUT_NV
            if evidence in {EvidenceReason.FVY, EvidenceReason.FVNY, EvidenceReason.ACT_FV_YEAR, EvidenceReason.FVAIY, EvidenceReason.FVAINY}:
                return EvidenceReason.MAT_FUT_FV
            if evidence in {EvidenceReason.VY, EvidenceReason.VNY, EvidenceReason.ACT_V_YEAR}:
                return EvidenceReason.MAT_FUT_V

        return (
            EvidenceReason.MAT_FUT
            if is_strict_derivative
            else EvidenceReason.MAT_AMB_FUT
        )


def check_active_state_year(
    text: str,
    reporting_year: int,
    is_strict_derivative: bool,
    verbs: VerbCheckResults,
) -> Optional[EvidenceReason]:
    """Check for Active State anchored to a year."""
    if not reporting_year:
        return None

    if not check_mention(text):
        return None

    has_prep = bool(ACTIVE_PREP_REGEX.search(text))
    has_adj = bool(ACTIVE_ADJ_REGEX.search(text))
    has_current_state = ACTIVE_STATE_REGEX.search(text)

    # Tightened Verb Check: Must have Possession/Usage verb AND Active Connection
    has_valid_verb = verbs.has_poss_or_use and verbs.has_active_verb

    if not (has_prep or has_adj or has_current_state or has_valid_verb):
        return None

    years = [int(y) for y in YEAR_REGEX.findall(text)]

    if not years:
        return None

    has_relevant_year = any(y >= reporting_year for y in years)

    if not has_relevant_year and not has_current_state:
        return None

    is_specific = is_strict_derivative or verbs.is_specific
    return EvidenceReason.AS_YEAR if is_specific else EvidenceReason.ASAIY


def check_active_state_general(
    text: str,
    is_strict_derivative: bool,
    verbs: VerbCheckResults,
) -> Optional[Reason]:
    """Check for General (Yearless) Possession or Usage."""

    if not check_mention(text):
        return None

    if verbs.has_active_verb:
        is_specific = is_strict_derivative or verbs.is_specific
        return (
            EvidenceReason.CONT_USE
            if is_specific
            else EvidenceReason.CONT_USE_AMB
        )

    if CHANGE_FV_REGEX.search(text):
        return NoiseReason.PNL
    return None


def check_balance_sheet_location(text: str) -> Optional[Reason]:
    """Check for Balance Sheet Location (self-validating)."""

    if not check_mention(text):
        return None
    if CHANGE_FV_REGEX.search(text):
        return NoiseReason.PNL
    if BS_LOC_REGEX.search(text):
        return EvidenceReason.BS_LOC

    return None


def check_transaction_action(
    text: str,
    reporting_year: int,
    is_strict_derivative: bool,
    verbs: VerbCheckResults,
) -> Optional[EvidenceReason]:
    """Check for Transactional Events."""
    if not reporting_year:
        return None

    if not check_mention(text):
        return None

    if not verbs.has_transaction:
        return None

    if not verbs.has_active_verb:
        return None

    years = [int(y) for y in YEAR_REGEX.findall(text)]

    is_specific = is_strict_derivative or verbs.is_specific

    if not years:
        return (
            EvidenceReason.ACT_GEN
            if is_specific
            else EvidenceReason.ACT_AMB_GEN
        )

    if any(y >= reporting_year for y in years):
        return (
            EvidenceReason.ACT_YEAR
            if is_specific
            else EvidenceReason.ACT_AMB_YEAR
        )

    return None


def check_remaining_term(text: str) -> Optional[EvidenceReason]:
    """Check for Remaining Term descriptions."""

    if not check_mention(text):
        return None

    if REM_TERM_REGEX.search(text):
        return EvidenceReason.REM_TERM

    return None


def check_valuation_context(text: str) -> Optional[EvidenceReason]:
    """Check for Valuation Models (self-validating)."""

    if not check_mention(text):
        return None

    if VALUATION_MODELS_REGEX.search(text):
        return EvidenceReason.VAL_MODEL

    return None


def mark_sentence_as_other(text: str, verbs: VerbCheckResults) -> Optional[Reason]:
    """Determine if sentence is noise/other category."""
    if AOCI_NOISE_REGEX.search(text):
        return NoiseReason.AOCI
    if is_pnl(text, False):
        return NoiseReason.PNL
    if TABLE_ANCHOR in text and not is_sophisticated_content(text):
        return EvidenceReason.TABLE
    if HEDGE_DOC_REGEX.search(text):
        return NoiseReason.DOC
    if not SOFT_REGEX.search(text):
        return NoiseReason.CTX
    return None


# =============================================================================
# MAIN EVIDENCE SCANNER
# =============================================================================


def scan_sentence_for_evidence(
    text: str,
    reporting_year: int,
    is_strict_derivative: bool,
    verbs: VerbCheckResults,
    has_active_context: bool = False,
    force_transaction_context: bool = False,
) -> Optional[Reason]:
    """
    Scan a sentence and return the HIGHEST PRIORITY evidence tag.
    Accepts pre-computed verb check results to avoid redundant regex calls.
    """
    if SKIP_TOKEN in text:
        return None

    # TIER 1: STRONG (highest priority)
    if mat := check_future_maturity(text, reporting_year, is_strict_derivative, verbs):
        return mat
    if q := check_quantitative_evidence(
        text, reporting_year, is_strict_derivative, verbs, has_active_context=has_active_context, force_transaction_context=force_transaction_context
    ):
        return q
    if as_year := check_active_state_year(
        text, reporting_year, is_strict_derivative, verbs
    ):
        return as_year

    # TIER 1.5: FLOW
    if act := check_transaction_action(
        text, reporting_year, is_strict_derivative, verbs
    ):
        return act

    # TIER 2: MEDIUM
    if loc := check_balance_sheet_location(text):
        return loc
    if val := check_valuation_context(text):
        return val
    if gen := check_active_state_general(text, is_strict_derivative, verbs):
        return gen

    # TIER 3: FLUFF (lowest priority)
    if term := check_remaining_term(text):
        return term

    # TIER 4: OTHER (catch-all)
    other = mark_sentence_as_other(text, verbs)
    if other:
        return other

    return None


# =============================================================================
# TAG APPLICATION LOGIC
# =============================================================================


def should_mark_deadweight(
    evidence_tags: set, noise_tags: set, sent_count: int = 0
) -> bool:
    """
    Determine if paragraph should be marked as deadweight.
    """

    # 1. ORPHAN KILL RULE
    if sent_count == 1 and not evidence_tags and not noise_tags:
        return True
    if len(evidence_tags) == 1:
        if not noise_tags.isdisjoint({NoiseReason.IMM}):
            if not evidence_tags.isdisjoint(IMMATERIAL_KILLED_EVIDENCE):
                return True

    # Handle ambiguous evidence
    if not evidence_tags.isdisjoint(
        {
            EvidenceReason.ASAIY,
            EvidenceReason.MAT_AMB_FUT,
            EvidenceReason.FVAIY,
            EvidenceReason.ACT_AMB_YEAR,
            EvidenceReason.ACT_AMB_GEN,
            EvidenceReason.CONT_USE_AMB,
            EvidenceReason.FVAINY,
        }
    ):
        return True

    # 2. Handle Remaining No-Evidence Cases
    if not evidence_tags:
        evidence_tags.add(EvidenceReason.UNCAT)

    # 3. Hierarchy Checks (Standard)

    if not evidence_tags.isdisjoint(STRONG_EVIDENCE):
        return False

    if not evidence_tags.isdisjoint(FLOW_EVIDENCE):
        return not noise_tags.isdisjoint(FLOW_KILLERS)

    if not evidence_tags.isdisjoint(TIME_KILLED_EVIDENCE):
        return not noise_tags.isdisjoint(TIME_KILLERS)

    if not evidence_tags.isdisjoint(POLICY_KILLED_EVIDENCE):
        return not noise_tags.isdisjoint(POLICY_KILLERS)

    # FLUFF (including UNCAT) survives ONLY if there are no noise tags
    if not evidence_tags.isdisjoint(FLUFF_EVIDENCE):
        return bool(noise_tags)

    return True


# =============================================================================
# TAGGING ENGINE
# =============================================================================
active_context_reasons = {
        EvidenceReason.MAT_FUT, EvidenceReason.MAT_AMB_FUT, 
        EvidenceReason.MAT_FUT_NV, EvidenceReason.MAT_FUT_FV, EvidenceReason.MAT_FUT_V,
        EvidenceReason.AS_YEAR,
        EvidenceReason.ACT_YEAR, EvidenceReason.ACT_NV_YEAR, EvidenceReason.ACT_FV_YEAR, EvidenceReason.ACT_V_YEAR,
        EvidenceReason.NVY, EvidenceReason.FVY, EvidenceReason.VY
}

transaction_reasons = {
    EvidenceReason.ACT_YEAR, EvidenceReason.ACT_NV_YEAR, EvidenceReason.ACT_FV_YEAR, EvidenceReason.ACT_V_YEAR,
    EvidenceReason.ACT_GEN, EvidenceReason.ACT_AMB_YEAR, EvidenceReason.ACT_AMB_GEN
}

possession_reasons = {
    EvidenceReason.AS_YEAR, EvidenceReason.ASAIY,
    EvidenceReason.CONT_USE, EvidenceReason.CONT_USE_AMB,
    EvidenceReason.BS_LOC,
    EvidenceReason.MAT_FUT, EvidenceReason.MAT_AMB_FUT,
    EvidenceReason.MAT_FUT_NV, EvidenceReason.MAT_FUT_FV, EvidenceReason.MAT_FUT_V
}

def tag_paragraph(text: str, reporting_year: int, is_nst: bool = True) -> Tuple[str, List[str]]:
    """
    Tag untagged sentences with evidence and mark paragraph as deadweight if needed.
    """
    # If paragraph is already marked deadweight, leave it alone
    if text.startswith(DEADWEIGHT_TOKEN):
        return text, []

    # Parse any existing noise tags from the paragraph for dominance evaluation
    _, existing_paragraph_noise = parse_noise_tags(text)

    # Split into sentences FIRST to ensure alignment
    original_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
    ]

    # Mask each sentence individually
    masked_sentences = [_cleaner.clean(s, is_nst=is_nst) for s in original_sentences]

    # Pre-compute verb checks for all sentences
    sentence_verbs = [check_verbs(s) for s in masked_sentences]

    # Reconstruct masked text for global check
    masked_text = " ".join(masked_sentences)
    is_strict_derivative = check_derivative_global(masked_text)

    # === PRE-SCAN: Identify if paragraph contains an Active Context signal ===
    has_active_context = False
    has_transaction_context = False
    has_possession_context = False

    pre_scan_results = []
    for i, s in enumerate(masked_sentences):
        verbs = sentence_verbs[i]
        # Pass False to avoid circular dependency during scan
        res = scan_sentence_for_evidence(s, reporting_year, is_strict_derivative, verbs, has_active_context=False)
        pre_scan_results.append(res)
        if res in active_context_reasons:
            has_active_context = True
        if res in transaction_reasons:
            has_transaction_context = True
        if res in possession_reasons:
            has_possession_context = True

    # Force transaction context for quants if we have transactions but NO possession signals
    # This ensures "Entered... Notional... Terminated" dies, but "Held... Notional... Terminated" survives.
    force_transaction_for_quants = has_transaction_context and not has_possession_context

    # Process sentences: tag untagged ones, collect evidence
    tagged_sentences = []
    all_evidence: Set[EvidenceReason] = set()
    debug_events = []

    for i, (orig, masked) in enumerate(zip(original_sentences, masked_sentences)):
        # Parse existing tags from this sentence
        clean_sent, existing_noise = parse_noise_tags(orig)
        verbs = sentence_verbs[i]

        # === PROMOTION LOGIC: Reclaim Historical Inception ===
        if has_active_context and (
            NoiseReason.TRANSACT in existing_noise
        ):
            if verbs.has_transaction:
                # Promote to Active Transaction Evidence
                evidence = (
                    EvidenceReason.ACT_YEAR
                    if is_strict_derivative
                    else EvidenceReason.ACT_AMB_YEAR
                )
                # Promote to Active Transaction Quant
                evidence2 = check_quantitative_evidence(
                    masked, reporting_year, is_strict_derivative, verbs, skip_year=True, force_transaction_context=True
                )

                if evidence2:
                    evidence = evidence2.value

                all_evidence.add(evidence)

                # Debug info for upgrade
                debug_tag = f"UPGRADE_{NoiseReason.TRANSACT}"
                debug_events.append(debug_tag)

                tagged_sent = f"{get_tag(EVIDENCE_TOKEN, evidence)} _M<{debug_tag}> {clean_sent} "
                tagged_sentences.append(tagged_sent)
                continue

        # Only scan and tag sentences that have NO existing tags
        if not existing_noise:
            # Scan for evidence - returns single tag or None
            evidence = pre_scan_results[i]

            needs_rescan = False
            if has_active_context and evidence not in active_context_reasons:
                needs_rescan = True
            if force_transaction_for_quants and evidence in {EvidenceReason.NVY, EvidenceReason.FVY, EvidenceReason.VY}:
                needs_rescan = True

            if needs_rescan:
                evidence = scan_sentence_for_evidence(
                    masked, reporting_year, is_strict_derivative, verbs, has_active_context=True, force_transaction_context=force_transaction_for_quants
                )

            if evidence:
                evidence_type = isinstance(evidence, EvidenceReason)
                if isinstance(evidence, EvidenceReason):
                    all_evidence.add(evidence)
                elif isinstance(evidence, NoiseReason):
                    existing_paragraph_noise.add(evidence)
                # Tag this sentence with the evidence
                tagged_sent = f"{get_tag(EVIDENCE_TOKEN if evidence_type else SKIP_TOKEN, evidence)} {orig}"
                tagged_sentences.append(tagged_sent)
            else:
                tagged_sentences.append(orig)
        else:
            # Already tagged, keep as-is
            tagged_sentences.append(orig)

    # Reconstruct paragraph with tagged sentences
    tagged_paragraph = " ".join(tagged_sentences)

    # Apply hierarchy: check if mixed signals kill the paragraph
    if should_mark_deadweight(
        all_evidence, existing_paragraph_noise, sent_count=len(original_sentences)
    ):
        return mark_as_deadweight(
            tagged_paragraph, noise=existing_paragraph_noise, stage=Stage.PF_EV
        ), debug_events
    else:
        return mark_as_evidence(
            tagged_paragraph, evidence=all_evidence, noise=existing_paragraph_noise
        ), debug_events


# =============================================================================
# CONFIGURATION & INFRASTRUCTURE
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "tagged_data.db"
TARGET_DB_PATH = "evidence_data.db"


def process_row(row):
    url, matches_json, cik, year = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    new_paragraphs = []
    is_nst = False

    # 1. Extract and Handle Metadata
    if paragraphs and paragraphs[0].startswith('{"type": "metadata"'):
        try:
            metadata_str = paragraphs.pop(0)
            metadata = json.loads(metadata_str)
            is_nst = metadata.get("NST", False)
            new_paragraphs.append(metadata_str)
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. Process remaining actual text paragraphs
    for p in paragraphs:
        if DEADWEIGHT_TOKEN in p:
            new_paragraphs.append(p)
            continue

        local_is_nst = convertible_ir(p)
        tagged_p, _ = tag_paragraph(p, year, is_nst=is_nst or local_is_nst)
        new_paragraphs.append(tagged_p)

    return (url, json.dumps(new_paragraphs), cik, year)


def setup_target_db(path):
    """Create target database schema."""
    if Path(path).exists():
        pass
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, matches TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES webpage_result(url))"
    )
    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
    conn.commit()
    conn.close()


def get_processed_urls(path):
    """Get set of already-processed URLs."""
    if not Path(path).exists():
        return set()
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT url FROM webpage_result")}
    except:
        return set()
    finally:
        conn.close()


def data_generator(source_db, processed_urls, batch_size=BATCH_SIZE):
    """Stream data from source database."""
    conn = sqlite3.connect(source_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT w.url, w.matches, r.cik, r.year
        FROM webpage_result w 
        LEFT JOIN report_data r ON w.url = r.url
        WHERE w.matches IS NOT NULL
        """
    )
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            if row[0] not in processed_urls:
                yield row
    conn.close()


def flush_buffers(conn, buffer):
    """Write buffer to database."""
    if not buffer:
        return
    c = conn.cursor()
    try:
        c.executemany(
            "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
            [(r[0], r[1]) for r in buffer],
        )
        c.executemany(
            "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(r[0], r[2], r[3]) for r in buffer],
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Write Error: {e}")
        conn.rollback()


if __name__ == "__main__":
    print(f"🚀 Starting Evidence Tagger ({NUM_WORKERS} workers)")
    setup_target_db(TARGET_DB_PATH)
    processed = get_processed_urls(TARGET_DB_PATH)

    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    buffer = []
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        source = list(data_generator(SOURCE_DB_PATH, processed))
        for result in tqdm(
            executor.map(process_row, source, chunksize=CHUNK_SIZE),
            total=len(source),
            desc="Tagging",
        ):
            if result:
                buffer.append(result)
                if len(buffer) >= BATCH_SIZE:
                    flush_buffers(conn, buffer)
                    buffer = []

    if buffer:
        flush_buffers(conn, buffer)
    conn.close()
    print("✅ Complete.")
