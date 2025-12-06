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
ENABLE_LLM_CHECK = False  # Set to True to enable actual API calls
LLM_MODEL = "gpt-4-turbo"  # or local model

from derivative_regex import (
    ALL_REGEX,
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
    HEDGING_CONTEXT_REGEX,  # Import the Group Checker
)

# =============================================================================
# 1. STRICT QUANTITATIVE DEFINITIONS
# =============================================================================

# Valid financial metrics that justify keeping a number
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

# Excluded indicators (If these are the ONLY context for a number, discard)
# e.g. "Spot price was $50" -> Discard. "Spot price was $50 used for fair value" -> Keep (caught by above).
INVALID_QUANT_CONTEXT = [
    r"spot\s+(?:price|rate)",
    r"exchange\s+rates?",
    r"market\s+(?:price|rate)",
    r"strike\s+(?:price|rate)",
    r"exercise\s+price",
]

VALID_QUANT_CONTEXT_REGEX = re.compile(
    r"\b" + build_alternation(VALID_QUANT_TERMS) + r"\b", re.IGNORECASE
)

# Reuse existing regexes
QUANT_REGEX = re.compile(
    rf"(?:{CURRENCY_SYMBOL_PATTERN})\s*(?:0\.\d+|[1-9]\d*(?:\.\d+)?)|"
    rf"(?:0\.\d+|[1-9]\d*(?:\.\d+)?)\s*(?:{CURRENCY_SYMBOL_PATTERN})|"
    r"\d+(?:\.\d+)?\s+(?:million|billion|trillion|thousand)",
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
    r"qualif(?:y|ies|ied)\s+for\s+hedge\s+accounting",
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
    """
    # 1. QUANTITATIVE CHECK (STRICTER NOW)
    # Must have a number AND a valid financial metric (Fair Value, Notional, etc.)
    # This filters out "Spot price was $50" or "Stock price is $10".
    if QUANT_REGEX.search(sentence):
        if VALID_QUANT_CONTEXT_REGEX.search(sentence) or TABLE_ANCHOR in sentence:
            return True, "kept_quantitative_indicator"
        else:
            # It has a number, but no valid context (likely spot price/exchange rate noise)
            # We treat this as "No Signal" and let it fall through to other checks
            pass

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

    # 3. ACTION / STATE CHECKS
    if VERB_REGEX.search(sentence):
        return True, "kept_action_verb"

    if ACTIVE_STATE_REGEX.search(sentence):
        return True, "kept_active_state_descriptor"

    # 4. WEAK EVIDENCE FALLBACK
    # If we have global quant signal, we are lenient with passive sentences containing the instrument
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

    # -- AGGREGATION STRUCTURE --
    # Group sentences by category to create "Mega Windows"
    # Key: Category (e.g., 'ir'), Value: List of sentences
    category_blocks = defaultdict(list)
    discards = []

    # 1. PROCESS SENTENCES (Filtering)
    for paragraph, category in zip(paragraphs, categories):
        # Paragraph-level flag for immunity
        has_quant = bool(QUANT_REGEX.search(paragraph)) or TABLE_ANCHOR in paragraph

        atomic_sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(paragraph) if s.strip()
        ]

        for sent in atomic_sentences:
            is_kept, reason = check_signal_status(sent, has_quant=has_quant)
            if is_kept:
                # Add to the category bucket
                category_blocks[category].append(sent)
            else:
                discards.append((url, sent, reason))

    # 2. GROUP CHECK & LLM PREP
    final_paragraphs = []
    final_categories = []

    for category, sentences in category_blocks.items():
        if not sentences:
            continue

        # Create the Mega Window
        mega_window = " ".join(sentences)

        # -- CHECK A: GROUP HEDGING CONTEXT --
        # Does the *combined* text mention hedging/risk management/designation?
        # This saves "We hold swaps." (No hedge mentioned) if another sentence says "to hedge risk".
        has_group_context = HEDGING_CONTEXT_REGEX.search(mega_window)

        # Exception: Tables usually imply context by existence, or simple "Active User" statements
        is_strong_usage = VERB_REGEX.search(mega_window) or TABLE_ANCHOR in mega_window

        if has_group_context or is_strong_usage:

            # -- CHECK B: LLM VERIFICATION (Optional/Stub) --
            # Currently disabled by flag, but this is where you insert the call.
            if ENABLE_LLM_CHECK:
                # llm_decision = call_llm_active_check(mega_window, category)
                # if not llm_decision: continue
                pass

            # If passed checks, reconstruct paragraphs (or keep as one big block)
            # For DB consistency, we usually store the block.
            final_paragraphs.append(mega_window)
            final_categories.append(category)

        else:
            discards.append(
                (url, mega_window, "discarded_group_check_no_hedging_context")
            )

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


# ... (Rest of DB Helpers and Main block remain unchanged) ...


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
