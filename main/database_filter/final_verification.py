# final_verification.py
# =============================================================================
# PHASE 7: ACTIVE USAGE VERIFICATION
# =============================================================================
# The Final Gatekeeper.
# Ensures every remaining sentence contains a "Strong Signal" of activity.
#
# Filters out passive context like:
# - "The effectiveness is determined quarterly." (No action verb, no amount)
# - "Risk management policies are reviewed." (No instrument state)
#
# Keeps Strong Signals:
# - "We use swaps." (Action Verb)
# - "Notional was $100." (Quantitative)
# - "Positions remain outstanding." (State Descriptor)
#
# UPDATED LOGIC: "Paragraph-Level Immunity"
# If a paragraph contains a quantitative signal (e.g. "$50 million"),
# context sentences (Level 2, Policy) within that paragraph are PRESERVED
# if they mention an instrument, even if they lack a verb/number themselves.
# =============================================================================

import sqlite3
import json
import re
import multiprocessing as mp
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
from typing import Tuple

from table_processor import TABLE_ANCHOR

# =============================================================================
# CONFIGURATION
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "active_nonzero_data.db"
FINAL_DB_PATH = "verified_active_data.db"

from derivative_regex import (
    ALL_REGEX,
    ENTITY_TOKEN,
    GEN_REGEX,
    MIN_SENTENCE_LENGTH,
    SENTENCE_SPLIT_PATTERN,
    CURRENCY_SYMBOL_PATTERN,
    STRONG_VERB_PATTERN,
    VALUATION_MODELS,
    build_alternation,
    ACTIVE_STATE_REGEX,
    validate_instrument_retention,
    CATEGORY_REGEX,  # <--- NEW IMPORT for Safety Check
)

# =============================================================================
# VERIFICATION REGEXES
# =============================================================================

VERB_REGEX = re.compile(rf"\b(?:{STRONG_VERB_PATTERN}|consists?\s+of)\b", re.IGNORECASE)
LEVEL_REGEX = re.compile(r"\b(?:Level\s+[123]|observable)\b", re.IGNORECASE)
VALUATION_MODEL_REGEX = re.compile(
    r"\b" + build_alternation(VALUATION_MODELS) + r"\b", re.IGNORECASE
)

# 2. QUANTITATIVE INDICATORS (Money & Metrics)
# Matches: "$100", "5%", "Notional", "Fair Value"
# We assume if they give a number or mention "Fair Value", they have the instrument.
QUANT_TERMS = [
    r"notional",
    r"fair\s+value",
    r"carrying\s+(?:amount|value)",
    r"market\s+value",
    r"weighted\s+average",
]
# Looks for Currency Symbols or defined terms
QUANT_REGEX = re.compile(
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*(?:0\.\d+|[1-9]\d*(?:\.\d+)?)|"  # Prefix: $0.50, $100.00
    rf"(?:0\.\d+|[1-9]\d*(?:\.\d+)?)\s*(?:{CURRENCY_SYMBOL_PATTERN})|"  # Suffix: 0.50 USD, 100 USD
    r"\d+(?:\.\d+)?\s+(?:million|billion|trillion|thousand))",  # Magnitude: 0.5 million, 10.5 billion
    re.IGNORECASE,
)
ENTITY_TOKENS = [ENTITY_TOKEN]
POLICY_TERMS = [
    r"formally\s+document",
    r"hedge\s+documentation",
    r"documentation",
    r"at\s+inception",
    r"effectiveness\s+(?:is|was)\s+assessed",
    r"highly\s+effective",
    r"qualif(?:y|ies|ied)\s+for\s+hedge\s+accounting",
    r"prospectively",
    r"retrospectively",
    r"economic\s+relationship",
]
POLICY_REGEX = re.compile(
    r"\b" + build_alternation(POLICY_TERMS + ENTITY_TOKENS) + r"\b", re.IGNORECASE
)
# Targets: "We transact with highly rated institutions", "Subject to master netting
COUNTERPARTY_POLICY_TERMS = [
    r"credit\s+risk",
    r"counterpart(?:y|ies)",
    r"credit\s+quality",
    r"credit\s+worthiness",
    r"highly[- ]rated",
    r"investment[- ]grade",
    r"financial\s+institutions",
    r"master\s+netting",
    r"isda",
    r"collateral\s+requirements",
    r"concentration\s+of\s+credit",
    r"non[- ]performance",
    r"nonperformance",
]

COUNTERPARTY_REGEX = re.compile(
    r"\b" + build_alternation(COUNTERPARTY_POLICY_TERMS) + r"\b", re.IGNORECASE
)

# =============================================================================
# LOGIC
# =============================================================================


def check_signal_status(sentence: str, has_quant: bool = False) -> Tuple[bool, str]:
    """
    Analyzes sentence for evidence of active usage.
    Returns: (is_kept: bool, reason_code: str)
    """
    # Sub out phrases
    sentence = ALL_REGEX.sub(" ", sentence)
    # 1. QUANTITATIVE CHECK (The Ultimate Salvager)
    if QUANT_REGEX.search(sentence):
        return True, "kept_quantitative_indicator"

    # -----------------------------------------------------------
    # TRAP 1: THE LEVEL TRAP
    # "Fair value determined using Level 2 inputs" -> No position evidence
    # -----------------------------------------------------------
    if LEVEL_REGEX.search(sentence):
        # FIX: Only discard if NO global signal AND no instrument name.
        # If the paragraph has a number, and this sentence says "Interest Rate Swaps are Level 2", keep it.
        if has_quant and CATEGORY_REGEX.search(sentence):
            return True, "kept_context_via_global_quant"
        return False, "discarded_fair_value_hierarchy_boilerplate"

    # -----------------------------------------------------------
    # TRAP 2: THE MODEL TRAP
    # "Valued using Black-Scholes model" -> Methodology, not holding
    # -----------------------------------------------------------
    if VALUATION_MODEL_REGEX.search(sentence):
        if has_quant and CATEGORY_REGEX.search(sentence):
            return True, "kept_context_via_global_quant"
        return False, "discarded_valuation_methodology"

    # -----------------------------------------------------------
    # TRAP 3: THE POLICY TRAP
    # "We formally document all hedges" -> Accounting policy, not holding
    # -----------------------------------------------------------
    if POLICY_REGEX.search(sentence):
        if has_quant and CATEGORY_REGEX.search(sentence):
            return True, "kept_context_via_global_quant"
        return False, "discarded_accounting_policy_boilerplate"

    if COUNTERPARTY_REGEX.search(sentence):
        if has_quant and CATEGORY_REGEX.search(sentence):
            return True, "kept_context_via_global_quant"
        return False, "discarded_counterparty_risk_boilerplate"

    # -----------------------------------------------------------
    # STANDARD CHECKS (If survived traps)
    # -----------------------------------------------------------

    # Action Verbs ("We use", "We hold")
    if VERB_REGEX.search(sentence):
        return True, "kept_action_verb"

    # Active State ("Outstanding", "Open")
    if ACTIVE_STATE_REGEX.search(sentence):
        return True, "kept_active_state_descriptor"

    # Weak Evidence / Passive Voice fallback
    # If we have a global quant signal, we are more lenient with passive sentences
    # provided they mention the instrument name.
    if has_quant and CATEGORY_REGEX.search(sentence) or GEN_REGEX.search(sentence):
        return True, "kept_passive_context_via_global_quant"

    # If we get here, the sentence lacks any verb, number, or state to prove it exists.
    return False, "discarded_weak_evidence_no_verb_or_quant"


def process_company(item):
    url, matches_json, cats_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
        categories = json.loads(cats_json)
    except:
        return None

    final_paragraphs = []
    final_categories = []
    discards = []

    for paragraph, category in zip(paragraphs, categories):
        # Atomic split is crucial here - we validate sentence by sentence
        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]
        kept_atomic = []

        # 1. Calculate Global Signal for Paragraph
        # If this flag is True, we activate "Immunity Mode" for context sentences
        has_quant = bool(QUANT_REGEX.search(paragraph)) or TABLE_ANCHOR in paragraph

        for sent in atomic_sentences:
            # --- VERIFICATION CHECK ---
            is_kept, reason = check_signal_status(sent, has_quant=has_quant)

            if is_kept:
                kept_atomic.append(sent)
            else:
                discards.append((url, sent, reason))

        if kept_atomic:
            final_paragraphs.append(
                " ".join([k for k in kept_atomic if len(k) > MIN_SENTENCE_LENGTH])
            )
            final_categories.append(category)

    # 4. Final Validation Helper (Anchor Check)
    final_paragraphs, final_categories, validation_discards = (
        validate_instrument_retention(
            final_paragraphs, final_categories, url, strict=False
        )
    )

    discards.extend(validation_discards)

    if final_paragraphs:
        return (
            url,
            json.dumps(final_paragraphs),
            json.dumps(final_categories),
            cik,
            year,
            discards,
        )

    return (url, "[]", "[]", cik, year, discards) if discards else None


# =============================================================================
# DB HELPERS (Unchanged)
# =============================================================================


def setup_db():
    if Path(FINAL_DB_PATH).exists():
        Path(FINAL_DB_PATH).unlink()
    conn = sqlite3.connect(FINAL_DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE webpage_result (url TEXT PRIMARY KEY, matches TEXT)")
    c.execute(
        "CREATE TABLE category (url TEXT PRIMARY KEY, categories TEXT, FOREIGN KEY(url) REFERENCES webpage_result(url))"
    )
    c.execute(
        "CREATE TABLE report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER)"
    )
    c.execute(
        "CREATE TABLE discarded_sentences (id INTEGER PRIMARY KEY, url TEXT, sentence TEXT, discard_reason TEXT)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_url ON webpage_result (url)")
    c.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()


def get_source_data():
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT wr.url, wr.matches, c.categories, rd.cik, rd.year
        FROM webpage_result wr
        JOIN category c ON wr.url = c.url
        JOIN report_data rd ON wr.url = rd.url
    """
    )
    data = c.fetchall()
    conn.close()
    return data


def write_batch(batch):
    if not batch:
        return
    conn = sqlite3.connect(FINAL_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        webpage_rows = [(b[0], b[1]) for b in batch]
        cat_rows = [(b[0], b[2]) for b in batch]
        meta_rows = [(b[0], b[3], b[4]) for b in batch]
        c.executemany("INSERT INTO webpage_result VALUES (?, ?)", webpage_rows)
        c.executemany("INSERT INTO category VALUES (?, ?)", cat_rows)
        c.executemany("INSERT INTO report_data VALUES (?, ?, ?)", meta_rows)

        all_discards = []
        for b in batch:
            if b[5]:
                all_discards.extend(b[5])
        if all_discards:
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                all_discards,
            )
        conn.commit()
    except Exception as e:
        print(f"Write error: {e}")
        conn.rollback()
    finally:
        conn.close()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 90)
    print("PHASE 7: FINAL VERIFICATION (Action/Quant Check)")
    print("=" * 90)

    setup_db()
    data = get_source_data()

    if not data:
        print("❌ No data found in source database.")
    else:
        print(f"Processing {len(data):,} records...")
        batch = []
        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            results = executor.map(process_company, data)
            for result in tqdm(results, total=len(data)):
                if not result:
                    continue
                batch.append(result)
                if len(batch) >= BATCH_SIZE:
                    write_batch(batch)
                    batch = []
        if batch:
            write_batch(batch)

    print("\n✅ Done.")
    print(f"Final Verified Data: {FINAL_DB_PATH}")
