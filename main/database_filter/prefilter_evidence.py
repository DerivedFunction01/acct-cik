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
    SOFT_REGEX,
    STRICT_REGEX,
    TERMINATION_ALL_REGEX,
    VALUATION_MODELS_REGEX,
    YEAR_REGEX,
    build_alternation,
    build_regex,
)
from prefilter_database import is_sophisticated_content
from notional_filter import extract_values_and_years
from prefiltered_lib import (
    DEADWEIGHT_TOKEN,
    EVIDENCE_TOKEN,
    FLOW_EVIDENCE,
    FLOW_KILLERS,
    FLUFF_EVIDENCE,
    POLICY_KILLED_EVIDENCE,
    POLICY_KILLERS,
    SKIP_TOKEN,
    STRONG_EVIDENCE,
    TIME_KILLED_EVIDENCE,
    TIME_KILLERS,
    EvidenceReason,
    MinimalTextCleaner,
    NoiseReason,
    get_tag,
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
        r"hedg(?:e|es|ed|ing)",
        r"designat(?:e|es|ed|ing)",
        r"offset(?:s|ting)?",
        r"manag(?:e|es|ed|ing)",
        r"mitigat(?:e|es|ed|ing)",
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

PNL_TERMS = [
    r"(?:realized|unrealized)\s+(?:gains?|loss|losses)",
    r"(?:net\s+)?(?:gains?|loss|losses)\s+on",
    r"mark(?:\s+to)?[- ]market",
    r"change(?:s)?\s+in\s+fair\s+value",
    r"ineffective\s+portion",
    r"hedge\s+ineffectiveness",
    r"reclassifi(?:ed|cation).{0,20}earnings",
    r"results\s+of\s+operations",
    r"impact(?:ed)?\s+(?:net\s+)?income",
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

locs_escaped = [re.escape(x) for x in BALANCE_SHEET_LOCATIONS]
locs_pattern = build_alternation(locs_escaped)
verbs_pattern = build_alternation(FINANCIAL_OUTCOME_VERBS)
FLEX_SEP = r"(?:\s+\S+){0,5}\s+"
BS_LOC_REGEX = re.compile(f"{verbs_pattern}{FLEX_SEP}{locs_pattern}", re.IGNORECASE)

PNL_CONTEXT_REGEX = build_regex(PNL_TERMS)
REM_TERM_REGEX = build_regex(REM_TERM_PHRASES)

TAG_PARSER = re.compile(r"(_[SD])<([^>]+)>")

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
) -> Optional[EvidenceReason]:
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

    if is_notional or (is_strict_derivative and not is_fair_value):
        return EvidenceReason.NVY if has_relevant_year else EvidenceReason.NVNY

    if is_fair_value:
        if is_strict_derivative:
            return EvidenceReason.FVY if has_relevant_year else EvidenceReason.FVNY
        else:
            return EvidenceReason.FVAIY if has_relevant_year else EvidenceReason.FVAINY

    return None


def check_future_maturity(
    text: str, reporting_year: int, is_strict_derivative: bool
) -> Optional[EvidenceReason]:
    """Check for Future Maturity."""
    if not reporting_year:
        return None

    if not TERMINATION_ALL_REGEX.search(text):
        return None

    if not check_mention(text):
        return None

    years = [int(y) for y in YEAR_REGEX.findall(text)]

    if not any(y > reporting_year for y in years):
        return None

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
    has_use = bool(USAGE_VERB_REGEX.search(text))

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


def check_pnl_context(
    text: str, is_strict_derivative: bool
) -> Optional[EvidenceReason]:
    """Check for PnL Context."""
    if not PNL_CONTEXT_REGEX.search(text):
        return None

    if not is_strict_derivative:
        return None

    return EvidenceReason.PNL_REC


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


# =============================================================================
# MAIN EVIDENCE SCANNER
# =============================================================================


def scan_sentence_for_evidence(
    text: str, reporting_year: int, is_strict_derivative: bool
) -> Set[EvidenceReason]:
    """Scan a sentence and return all applicable evidence tags."""
    evidence = set()

    # TIER 1: STRONG
    if q := check_quantitative_evidence(text, reporting_year, is_strict_derivative):
        evidence.add(q)
    if as_year := check_active_state_year(text, reporting_year, is_strict_derivative):
        evidence.add(as_year)
    if mat := check_future_maturity(text, reporting_year, is_strict_derivative):
        evidence.add(mat)

    # TIER 1.5: FLOW
    if act := check_transaction_action(text, reporting_year, is_strict_derivative):
        evidence.add(act)

    # TIER 2: MEDIUM
    if loc := check_balance_sheet_location(text):
        evidence.add(loc)
    if val := check_valuation_context(text):
        evidence.add(val)
    if gen := check_active_state_general(text, is_strict_derivative):
        evidence.add(gen)

    # TIER 4: FLUFF
    if term := check_remaining_term(text):
        evidence.add(term)
    if pnl := check_pnl_context(text, is_strict_derivative):
        evidence.add(pnl)

    return evidence


# =============================================================================
# TAG APPLICATION LOGIC
# =============================================================================


def apply_tags(
    text: str, evidence_tags: Set[EvidenceReason], noise_tags: Set[NoiseReason]
) -> str:
    """Apply evidence and noise tags to text."""
    e_str = " ".join(
        [
            get_tag(EVIDENCE_TOKEN, t)
            for t in sorted(evidence_tags, key=lambda x: x.value)
        ]
    )
    n_str = " ".join(
        [get_tag(SKIP_TOKEN, t) for t in sorted(noise_tags, key=lambda x: x.value)]
    )

    prefix = f"{e_str} {n_str}".strip()

    if prefix:
        return f"{prefix} {text}"
    return text


def mark_as_deadweight(text: str, reason: NoiseReason) -> str:
    """Mark paragraph as deadweight."""
    return f"{get_tag(DEADWEIGHT_TOKEN, reason)} {text}"


def evaluate_dominance(text: str, evidence_tags: set, noise_tags: set) -> str:
    """Decide final fate based on Survival Hierarchy."""
    if not evidence_tags.isdisjoint(STRONG_EVIDENCE):
        return apply_tags(text, evidence_tags, noise_tags)

    if not evidence_tags.isdisjoint(FLOW_EVIDENCE):
        if noise_tags.isdisjoint(FLOW_KILLERS):
            return apply_tags(text, evidence_tags, noise_tags)

    if not evidence_tags.isdisjoint(TIME_KILLED_EVIDENCE):
        if noise_tags.isdisjoint(TIME_KILLERS):
            return apply_tags(text, evidence_tags, noise_tags)

    if not evidence_tags.isdisjoint(POLICY_KILLED_EVIDENCE):
        if noise_tags.isdisjoint(POLICY_KILLERS):
            return apply_tags(text, evidence_tags, noise_tags)

    if not evidence_tags.isdisjoint(FLUFF_EVIDENCE):
        if not noise_tags:
            return apply_tags(text, evidence_tags, set())

    return mark_as_deadweight(text, NoiseReason.ANLZ)


def parse_existing_tags(text: str) -> Tuple[str, Set[NoiseReason]]:
    """Extract existing noise tags from text."""
    noise_tags = set()

    matches = list(TAG_PARSER.finditer(text))
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

    text = TAG_PARSER.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)

    return text, noise_tags


# =============================================================================
# TAGGING ENGINE
# =============================================================================


def tag_paragraph(text: str, reporting_year: int) -> str:
    """
    Tag a paragraph with evidence and evaluate dominance.

    Process:
    1. Mask text for logic checks
    2. Check if global strict derivative
    3. Split into sentences
    4. Scan each sentence for evidence
    5. Parse existing noise tags
    6. Evaluate dominance hierarchy
    """
    masked_text = _cleaner.clean(text)
    is_strict_derivative = check_derivative_global(masked_text)

    # Split into sentences
    original_sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()
    ]
    masked_sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", masked_text) if s.strip()
    ]

    # Align lengths (safety)
    if len(original_sentences) != len(masked_sentences):
        masked_sentences = original_sentences

    # Aggregate evidence and noise across all sentences
    all_evidence = set()
    all_noise = set()

    for orig, masked in zip(original_sentences, masked_sentences):
        # Parse existing noise tags from prefilter step
        _, existing_noise = parse_existing_tags(orig)
        all_noise.update(existing_noise)

        # Scan for evidence
        evidence = scan_sentence_for_evidence(
            masked, reporting_year, is_strict_derivative
        )
        all_evidence.update(evidence)

    # Evaluate dominance and return
    return evaluate_dominance(text, all_evidence, all_noise)


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
