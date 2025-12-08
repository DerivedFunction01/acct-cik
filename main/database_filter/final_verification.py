# final_verification.py (Note this was too aggresive, so it is skipped)
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
from typing import Tuple, List, Dict
from collections import defaultdict

from table_processor import TABLE_ANCHOR

# =============================================================================
# CONFIGURATION
# =============================================================================

NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "active_nonzero_data.db"
FINAL_DB_PATH = "verified_active_data.db"

# LLM Configuration
ENABLE_LLM_CHECK = False  # Set True to enable the salvage logic
LLM_MODEL = "gpt-4-turbo"

from derivative_regex import (
    ALL_REGEX,
    COMMODITY_UNIT_PATTERN,
    ENTITY_TOKEN,
    GEN_REGEX,
    MIN_SENTENCE_LENGTH,
    SENTENCE_SPLIT_PATTERN,
    CURRENCY_SYMBOL_PATTERN,
    STRONG_VERB_PATTERN,
    VALUATION_MODELS,
    aggregate_discards,
    build_alternation,
    ACTIVE_STATE_REGEX,
    validate_instrument_retention,
    CATEGORY_REGEX,
    HEDGING_CONTEXT_REGEX,
)

# =============================================================================
# 1. STRICT QUANTITATIVE DEFINITIONS
# =============================================================================

VALID_QUANT_TERMS = [
    r"notional",
    r"fair\s+value",
    r"carrying\s+(?:amount|value)",
    r"market\s+value",
    r"weighted\s+average",
    r"gains?",
    r"loss(?:es)?",
    r"earnings",
    r"income",
    r"assets?",
    r"liabilit(?:y|ies)",
    r"receivables?",
    r"payables?",
    r"net\s+investment",
    r"accumulated\s+other\s+comprehensive",
    r"AOCI",
    r"cash\s+flow",
]

VALID_QUANT_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(VALID_QUANT_TERMS) + r"\b", re.IGNORECASE
)
NUMBER_PATTERN = r"(?:0\.\d+|(?:[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)(?:\.\d+)?)"
SCALE_WORDS = r"(?:million|billion|trillion|thousand)"
QUANT_REGEX = re.compile(
    # Currency symbol + optional parens + number + optional parens
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*\(?\s*{NUMBER_PATTERN}\s*\)?|"
    # Number + optional parens + currency symbol
    rf"\(?\s*{NUMBER_PATTERN}\s*\)?\s*(?:{CURRENCY_SYMBOL_PATTERN})|"
    # Currency + number + scale word
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s+{NUMBER_PATTERN}\s+{SCALE_WORDS}|"
    # Number + optional scale word + commodity unit
    rf"{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?\s+{COMMODITY_UNIT_PATTERN}|"
    rf"{NUMBER_PATTERN}(?:\s+{SCALE_WORDS})?\s+shares",
    re.IGNORECASE,
)
VERB_REGEX = re.compile(rf"\b(?:{STRONG_VERB_PATTERN}|consists?\s+of)\b", re.IGNORECASE)
LEVEL_REGEX = re.compile(
    r"\b(?:Level\s+[123]|observable|record(?:s|ed)?|recogniz(?:ed?|ing|es))\b",
    re.IGNORECASE,
)
VALUATION_MODEL_REGEX = re.compile(
    r"\b" + build_alternation(VALUATION_MODELS) + r"\b", re.IGNORECASE
)

POLICY_TERMS = [
    r"formally\s+document",
    r"hedge\s+documentation",
    r"documentation",
    r"at\s+inception",
    r"effectiveness\s+(?:is|was)\s+assessed",
    r"highly\s+effective",
    r"qualif(?:y|ies|ied)\s+for\s+hedg(?:ing|e)\s+(?:accounting|relationship|documentation)",
    r"(?:dis)?continu(?:es?|ed|ing)\s+hedge\s+(?:accounting|relationship|documentation)",
    r"prospectively",
    r"retrospectively",
    r"economic\s+relationship",
]
POLICY_REGEX = re.compile(
    r"\b" + build_alternation(POLICY_TERMS + [ENTITY_TOKEN]) + r"\b", re.IGNORECASE
)

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
# 2. ANALYSIS LOGIC
# =============================================================================


def check_signal_status(sentence: str, has_quant: bool = False) -> Tuple[bool, str]:
    """
    Analyzes sentence for evidence of active usage.
    Returns: (is_kept, reason_code)
    """
    # 1. QUANTITATIVE CHECK (Strongest Signal)
    if QUANT_REGEX.search(sentence):
        if VALID_QUANT_CONTEXT_REGEX.search(sentence) or TABLE_ANCHOR in sentence:
            return True, "kept_quantitative_indicator"

    # 2. TRAPS (Boilerplate Removal)
    if LEVEL_REGEX.search(sentence):
        if has_quant and CATEGORY_REGEX.search(sentence):
            return True, "kept_context_via_global_quant"
        return False, "discarded_fair_value_hierarchy_boilerplate"

    if VALUATION_MODEL_REGEX.search(sentence):
        if has_quant and CATEGORY_REGEX.search(sentence):
            return True, "kept_context_via_global_quant"
        return False, "discarded_valuation_methodology"

    if POLICY_REGEX.search(sentence):
        if has_quant and CATEGORY_REGEX.search(sentence):
            return True, "kept_context_via_global_quant"
        return False, "discarded_accounting_policy_boilerplate"

    if COUNTERPARTY_REGEX.search(sentence):
        if has_quant and CATEGORY_REGEX.search(sentence):
            return True, "kept_context_via_global_quant"
        return False, "discarded_counterparty_risk_boilerplate"

    # 3. ACTION / STATE CHECKS (Strong Signals)
    if VERB_REGEX.search(sentence):
        return True, "kept_action_verb"

    if ACTIVE_STATE_REGEX.search(sentence):
        return True, "kept_active_state_descriptor"

    # 4. WEAK EVIDENCE FALLBACK (Requires Validation)
    if has_quant and (CATEGORY_REGEX.search(sentence) or GEN_REGEX.search(sentence)):
        return True, "kept_passive_context_via_global_quant"

    return False, "discarded_weak_evidence_no_verb_or_valid_quant"


def process_company(item):
    url, matches_json, cats_json, cik, year = item

    try:
        paragraphs = json.loads(matches_json)
        categories = json.loads(cats_json)
    except:
        return None

    # -- AGGREGATION & METADATA STRUCTURE --
    # category_signals: Tracks if the block has a "Golden Ticket" (Strong Signal)
    category_blocks = defaultdict(list)
    category_signals = defaultdict(bool)
    discards = []

    # 1. PROCESS SENTENCES (Filtering)
    for paragraph, category in zip(paragraphs, categories):
        has_quant = bool(QUANT_REGEX.search(paragraph)) or TABLE_ANCHOR in paragraph
        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]

        for sent in atomic_sentences:
            is_kept, reason = check_signal_status(sent, has_quant=has_quant)

            if is_kept:
                category_blocks[category].append(sent)

                # CHECK FOR GOLDEN TICKETS (Bypass LLM)
                if reason in {
                    "kept_quantitative_indicator",
                    "kept_action_verb",
                    "kept_active_state_descriptor",
                }:
                    category_signals[category] = True
            else:
                discards.append((url, sent, reason))

    # 2. GROUP DECISION LOGIC
    final_paragraphs = []
    final_categories = []

    for category, sentences in category_blocks.items():
        if not sentences:
            continue

        mega_window = " ".join(sentences)

        # --- PATH A: FAST PASS (Strong Signal) ---
        if category_signals[category]:
            final_paragraphs.append(mega_window)
            final_categories.append(category)
            continue

        # --- PATH B: AMBIGUOUS (Weak Signal + Context Check) ---
        # If we are here, we only have passive context or weak indicators.
        # We perform a group-level check for Hedging Context.
        has_group_context = HEDGING_CONTEXT_REGEX.search(mega_window)

        if has_group_context:
            # CANDIDATE FOR LLM SALVAGE
            if ENABLE_LLM_CHECK:
                # Stub for LLM Call
                # is_valid = call_llm_active_check(mega_window, category)
                # if is_valid:
                #     final_paragraphs.append(mega_window)
                #     final_categories.append(category)
                pass
            else:
                # If LLM disabled, we might have to discard or keep based on risk appetite.
                # Currently: Discard because previous logic proved too weak without LLM validation.
                discards.append(
                    (url, mega_window, "discarded_weak_signal_requires_llm")
                )
        else:
            discards.append((url, mega_window, "discarded_no_signal_no_context"))

    # 3. DB FORMATTING
    if final_paragraphs:
        return (
            url,
            json.dumps(final_paragraphs),
            json.dumps(final_categories),
            cik,
            year,
            aggregate_discards(discards),
        )

    return (url, "[]", "[]", cik, year, discards) if discards else None

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
