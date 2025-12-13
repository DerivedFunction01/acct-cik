from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import re
import sqlite3
from typing import Optional, Set, Tuple

from tqdm import tqdm
from derivative_regex import (
    ACTIVE_STATE_REGEX,
    FX_SOFT_REGEX,
    IR_SOFT_REGEX,
    LOOSE_GEN_REGEX,
    SENTENCE_SPLIT_PATTERN,
    SOFT_REGEX,
    STRICT_REGEX,
    TERMINATION_ALL_REGEX,
    VALUATION_MODELS_REGEX,
    YEAR_REGEX,
    build_alternation,
    build_regex,
)

from table_processor import TABLE_ANCHOR
from prefilter_database import is_sophisticated_content
from prefiltered_lib import (
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
    get_tag,
    mark_as_deadweight,
    mark_as_evidence,
    parse_noise_tags,
    HAD_CHANGE_REGEX,
    CHANGE_FV_REGEX,
)
import multiprocessing as mp

_cleaner = MinimalTextCleaner()

# =============================================================================
# VERB MAPS & PRECOMPILED REGEXES
# =============================================================================
VERB_MAP = {
    "POSS": [
        r"hold(?:s|ing)?|held",
        r"hav(?:e|ing)|had",
        r"maintain(?:s|ed|ing)?",
        r"possess(?:e|es|ed|ing)?",
        r"carr(?:y|ies|ied|ying)",
        r"retain(?:s|ed|ing)?",
        r"remained?\s+(?:open|outstanding|active)",
        r"(?:is|are|was|were)\s+a\s+party\s+to",
    ],
    "PRU": [
        r"use(?:s|d|ing)?",
        r"utiliz(?:e|es|ed|ing)",
        r"employ(?:s|ed|ing)?",
        r"apply(?:ies|ied|ying)?",
    ],
    "ACT": [
        r"enter(?:s|ed|ing)?(?:\s+into)?",
        r"engag(?:e|es|ed|ing)(?:\s+in)?",
        r"execut(?:e|es|ed|ing)",
        r"transact(?:s|ed|ing)?",
        r"purchas(?:e|es|ed|ing)",
        r"issu(?:e|es|ed|ing)?",
        r"convert(?:s|ed|ing)?",
        r"secur(?:e|es|ed|ing)",
    ],
    "ACCT": [
        r"designat(?:e|es|ed|ing)",
    ],
}

NOTIONAL_TERMS = [
    r"notional",
    r"face\s+(?:amount|value)",
    r"par\s+value",
    r"contract\s+(?:amount|value|volume)",
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
POSS_VERB_REGEX = build_regex(VERB_MAP["POSS"])
USAGE_VERB_REGEX = build_regex(VERB_MAP["PRU"])
TRANS_VERB_REGEX = build_regex(VERB_MAP["ACT"])
ACCT_VERB_REGEX = build_regex(VERB_MAP["ACCT"])

locs_escaped = [re.escape(x) for x in BALANCE_SHEET_LOCATIONS]
locs_pattern = build_alternation(locs_escaped)
verbs_pattern = build_alternation(FINANCIAL_OUTCOME_VERBS)
FLEX_SEP = r"(?:\s+\S+){0,5}\s+"
BS_LOC_REGEX = re.compile(f"{verbs_pattern}{FLEX_SEP}{locs_pattern}", re.IGNORECASE)


REM_TERM_REGEX = build_regex(REM_TERM_PHRASES)


# =============================================================================
# HELPER FUNCTIONS (Global checks - called once per paragraph)
# =============================================================================


def check_mention(text: str) -> bool:
    """Check if text mentions any derivative instrument."""
    return bool(SOFT_REGEX.search(text) or LOOSE_GEN_REGEX.search(text))


def check_derivative_global(text: str) -> bool:
    """Global check - returns True if text is a STRICT derivative mention."""
    return bool(
        STRICT_REGEX.search(text)
        or IR_SOFT_REGEX.search(text)
        or FX_SOFT_REGEX.search(text)
        or is_sophisticated_content(text)
    )


# =============================================================================
# EVIDENCE CHECKERS (Now take is_strict_derivative as parameter)
# =============================================================================


def check_quantitative_evidence(
    text: str, reporting_year: int, is_strict_derivative: bool
) -> Optional[Reason]:
    from prefilter_tagging import extract_values_and_years

    """Check for Quantitative Evidence (NVY/FVY)."""
    if not reporting_year:
        return None

    is_notional = bool(NOTIONAL_CONTEXT_REGEX.search(text))
    is_fair_value = bool(FAIR_VALUE_CONTEXT_REGEX.search(text))
    has_mention = check_mention(text)

    if not has_mention:
        return None

    years_found, values_found = extract_values_and_years(text)

    if not values_found:
        return None

    has_relevant_year = any(y >= reporting_year for y in years_found)
    # "We hold interest rate swaps... with value of XX in 2025"
    has_active_verb = (
        POSS_VERB_REGEX.search(text)
        or USAGE_VERB_REGEX.search(text)
        or TRANS_VERB_REGEX.search(text)
    )
    # 1. NOTIONAL SAFETY: Notional always overrides PnL context.
    # Logic: You don't have "Notional PnL". If "Notional" is there, it's a Position.
    if is_notional: # The notional value is... or we hold XX with notional of ...
        return EvidenceReason.NVY if has_relevant_year else EvidenceReason.NVNY

    # 2. FAIR VALUE LOGIC
    if is_fair_value:
        # 1. STRICT PNL CHECK (The Override)
        # Catches: "had a change", "has recorded a change", "have significant changes"
        # Logic: This specific proximity implies an event, not possession.
        if HAD_CHANGE_REGEX.search(text):
            return NoiseReason.PNL

        # 2. STANDARD PNL CHECK (The Rescue Logic)
        # Catches: "The change in fair value was..."
        if CHANGE_FV_REGEX.search(text):
            # ...UNLESS we see an Active Verb elsewhere in the sentence.
            # "We have swaps... to hedge the change in fair value."
            # Since "have... swaps... to... hedge... the..." is > 2 words,
            # HAD_CHANGE_REGEX failed, so we reach this rescue block.

            if not has_active_verb:
                return NoiseReason.PNL

        # 3. VALID EVIDENCE
        if is_strict_derivative:
            return EvidenceReason.FVY if has_relevant_year else EvidenceReason.FVNY
        else:
            return EvidenceReason.FVAIY if has_relevant_year else EvidenceReason.FVAINY

    # ...UNLESS we see an Active Verb elsewhere in the sentence.
    if has_active_verb:
        if STRICT_REGEX.search(text):
            return EvidenceReason.VY if has_relevant_year else EvidenceReason.VNY
    return None


def check_future_maturity(
    text: str, reporting_year: int, is_strict_derivative: bool
) -> Optional[Reason]:
    """Check for Future Maturity."""
    if not reporting_year:
        return None

    if not TERMINATION_ALL_REGEX.search(text):
        return None

    if not check_mention(text):
        return None

    years = [int(y) for y in YEAR_REGEX.findall(text)]

    if not any(y > reporting_year for y in years): # Termination noun without a year? probably termination amount/settlement
        return NoiseReason.PNL

    return (
        EvidenceReason.MAT_FUT if is_strict_derivative else EvidenceReason.MAT_AMB_FUT
    )


def check_active_state_year(
    text: str, reporting_year: int, is_strict_derivative: bool
) -> Optional[EvidenceReason]:
    """Check for Active State anchored to a year."""
    if not reporting_year:
        return None

    if not check_mention(text):
        return None

    has_prep = bool(ACTIVE_PREP_REGEX.search(text))
    has_adj = bool(ACTIVE_ADJ_REGEX.search(text))
    has_poss_verb = bool(POSS_VERB_REGEX.search(text))
    has_use = bool(USAGE_VERB_REGEX.search(text))
    has_current_state = ACTIVE_STATE_REGEX.search(text)

    if not (has_prep or has_adj or has_poss_verb or has_current_state or has_use):
        return None

    years = [int(y) for y in YEAR_REGEX.findall(text)]
    has_relevant_year = any(y >= reporting_year for y in years)

    if not has_relevant_year and not has_current_state:
        return None

    return EvidenceReason.AS_YEAR if is_strict_derivative else EvidenceReason.ASAIY


def check_active_state_general(
    text: str, is_strict_derivative: bool
) -> Optional[EvidenceReason]:
    """Check for General (Yearless) Possession or Usage."""

    if not check_mention(text):
        return None

    has_poss = bool(POSS_VERB_REGEX.search(text))
    has_use = bool(USAGE_VERB_REGEX.search(text) or ACCT_VERB_REGEX.search(text))

    if has_poss or has_use:
        return (
            EvidenceReason.CONT_USE
            if is_strict_derivative
            else EvidenceReason.CONT_USE_AMB
        )

    return None


def check_balance_sheet_location(text: str) -> Optional[EvidenceReason]:
    """Check for Balance Sheet Location (self-validating)."""
    

    if not check_mention(text):
        return None

    if BS_LOC_REGEX.search(text):
        return EvidenceReason.BS_LOC

    return None


def check_transaction_action(
    text: str, reporting_year: int, is_strict_derivative: bool
) -> Optional[EvidenceReason]:
    """Check for Transactional Events."""
    if not reporting_year:
        return None

    if not check_mention(text):
        return None

    if not TRANS_VERB_REGEX.search(text):
        return None

    years = [int(y) for y in YEAR_REGEX.findall(text)]

    if not years:
        return EvidenceReason.ACT_GEN

    if any(y >= reporting_year for y in years):
        return (
            EvidenceReason.ACT_YEAR
            if is_strict_derivative
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

def mark_sentence_as_other(text: str) -> Optional[Reason]:
    if TABLE_ANCHOR in text and not is_sophisticated_content(text): # Only for "normal" derivatives
        return EvidenceReason.TABLE
    if HEDGE_DOC_REGEX.search(text):
        return NoiseReason.DOC
    if not SOFT_REGEX.search(text): # Contracts, swaps, etc
        return NoiseReason.CTX
    return None # Remain uncategorized


# =============================================================================
# MAIN EVIDENCE SCANNER
# =============================================================================


def scan_sentence_for_evidence(
    text: str, reporting_year: int, is_strict_derivative: bool
) -> Optional[Reason]:
    """
    Scan a sentence and return the HIGHEST PRIORITY evidence tag.
    Returns only ONE tag per sentence based on the survival hierarchy.
    """
    if SKIP_TOKEN in text:
        return None

    # TIER 1: STRONG (highest priority)
    if mat := check_future_maturity(text, reporting_year, is_strict_derivative): # Overrides quant in case it is not relavant (ie termination amounts become PNL)
        return mat
    if q := check_quantitative_evidence(text, reporting_year, is_strict_derivative):
        return q
    if as_year := check_active_state_year(text, reporting_year, is_strict_derivative):
        return as_year

    # TIER 1.5: FLOW
    if act := check_transaction_action(text, reporting_year, is_strict_derivative):
        return act

    # TIER 2: MEDIUM
    if loc := check_balance_sheet_location(text):
        return loc
    if val := check_valuation_context(text):
        return val
    if gen := check_active_state_general(text, is_strict_derivative):
        return gen

    # TIER 3: FLUFF (lowest priority)
    if term := check_remaining_term(text):
        return term

    # TIER 4: OTHER (catch-all)
    other = mark_sentence_as_other(text)
    if other:
        return other

    return None


# =============================================================================
# TAG APPLICATION LOGIC
# =============================================================================


# In prefilter_evidence.py


def should_mark_deadweight(
    evidence_tags: set, noise_tags: set, sent_count: int = 0
) -> bool:
    """
    Determine if paragraph should be marked as deadweight.
    """

    # 1. ORPHAN KILL RULE (The "Anti-Clutter" Logic)
    # If it's a single sentence with NO evidence and NO noise, it's likely a
    # header, footer, or isolated bullet point. Kill it to prevent "Definition" counts.
    if sent_count == 1 and not evidence_tags and not noise_tags:
        return True

    # 2. Handle Remaining No-Evidence Cases (Multi-sentence clean text)
    # If we are here, and tags are empty, it must be > 1 sentence.
    # We treat this as "Uncategorized Context" (Fluff). 
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
    # This means multi-sentence clean text survives.
    if not evidence_tags.isdisjoint(FLUFF_EVIDENCE):
        return bool(noise_tags)

    return True


# =============================================================================
# TAGGING ENGINE
# =============================================================================


def tag_paragraph(text: str, reporting_year: int) -> str:
    """
    Tag untagged sentences with evidence and mark paragraph as deadweight if needed.

    Process:
    1. Check if paragraph is already deadweight - if so, return unchanged
    2. Parse existing noise tags from paragraph
    3. Split into sentences
    4. Tag ONLY untagged sentences with their evidence
    5. Collect evidence for dominance check
    6. Apply hierarchy to check if mixed signals should kill the paragraph
    """
    # If paragraph is already marked deadweight, leave it alone
    if text.startswith(DEADWEIGHT_TOKEN):
        return text

    # Parse any existing noise tags from the paragraph for dominance evaluation
    _, existing_paragraph_noise = parse_noise_tags(text)

    masked_text = _cleaner.clean(text)
    is_strict_derivative = check_derivative_global(masked_text)

    # Split into sentences
    original_sentences = [
        s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()
    ]
    masked_sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(masked_text) if s.strip()]

    # Align lengths (safety)
    if len(original_sentences) != len(masked_sentences):
        masked_sentences = original_sentences

    # Process sentences: tag untagged ones, collect evidence
    tagged_sentences = []
    all_evidence: Set[EvidenceReason] = set()

    for orig, masked in zip(original_sentences, masked_sentences):
        # Parse existing tags from this sentence
        clean_sent, existing_noise = parse_noise_tags(orig)

        # Only scan and tag sentences that have NO existing tags
        if not existing_noise:
            # Scan for evidence - returns single tag or None
            evidence = scan_sentence_for_evidence(
                masked, reporting_year, is_strict_derivative
            )
            if evidence:
                evidence_type = isinstance(evidence, EvidenceReason)
                if evidence_type:
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
    if should_mark_deadweight(all_evidence, existing_paragraph_noise, sent_count=len(original_sentences)):
        return mark_as_deadweight(tagged_paragraph, noise=existing_paragraph_noise)
    else:
        return mark_as_evidence(tagged_paragraph, evidence=all_evidence, noise=existing_paragraph_noise)


# =============================================================================
# CONFIGURATION & INFRASTRUCTURE
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "tagged_data.db"
TARGET_DB_PATH = "evidence_data.db"


def process_row(row):
    """Process a single row from source database."""
    url, matches_json, cik, year = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    new_paragraphs = []
    for p in paragraphs:
        if p.startswith(DEADWEIGHT_TOKEN):
            new_paragraphs.append(p)
            continue

        tagged_p = tag_paragraph(p, year)
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
