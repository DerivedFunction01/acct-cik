import sqlite3
import pandas as pd
import json
import random
import re
import multiprocessing as mp
import os
import time
import hashlib
import logging
from typing import Tuple, List, Optional, Dict, Any, Set
from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
from tqdm import tqdm

# =============================================================================
# IMPORTS FROM YOUR REGEX MODULE
# =============================================================================
# Ensure derivative_regex.py is in the same directory or python path
from derivative_regex import (
    GEN_REGEX,
    SOFT_GEN_REGEX,
    SOFT_REGEX,
    STRICT_REGEX,
    POTENTIAL_REGEX,
    NEGATIVE_INTENT_REGEX,
    ABSENCE_REGEX,
    DID_NOT_HOLD_REGEX,
    TERMINATION_REGEX,
    TRADING_STATEMENTS_REGEX,
    SENTENCE_SPLIT_PATTERN,
    MIN_SENTENCE_LENGTH,
    all_currencies,  # Required for Currency Substitution
    Currency,  # Required for type hinting
)
from final_verification import QUANT_REGEX, COUNTERPARTY_REGEX

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "prefiltered_data.db"
OUTPUT_PATH = "../roberta/binary_classification_data.parquet"

# Data Balancing
TARGET_SAMPLES = 5000  # Total Desired (e.g. 2500 Active + 2500 Passive)
CHUNK_SIZE = 1000
MAX_WORKERS = max(1, mp.cpu_count() - 1)

# NLP Tokens
BOUNDARY = " <<>> "
SEP_TOKEN = " [SEP] "
# Augmentation Settings
NUMERIC_SUBSTITUTION_CONFIG = {
    "enabled": True,
    "apply_to_numbers": True,
    "number_perturbation": 0.05,  # ±5%
}

# =============================================================================
# 1. SUBSTITUTION CLASSES (Numeric, Entity, Currency)
# =============================================================================

# --- CONSTANTS FOR SUBSTITUTION ---
MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_ABBREVIATIONS = {k[:3]: v for k, v in MONTH_NAMES.items()}
MONTH_NUMBER_TO_NAME = {v: k for k, v in MONTH_NAMES.items()}
MONTH_NUMBER_TO_ABBREV = {v: k for k, v in MONTH_ABBREVIATIONS.items()}

MONTH_REGEX = re.compile(
    r"\b("
    + "|".join(list(MONTH_NAMES.keys()) + list(MONTH_ABBREVIATIONS.keys()))
    + r")\b",
    re.IGNORECASE,
)
YEAR_REGEX_COLLECTOR = re.compile(r"\b(19[0-9]{2}|20[0-9]{2})\b")
NON_YEAR_NUMBER_REGEX = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\b")


class NumericSubstitutionEngine:
    def __init__(self, config=None, random_seed=None):
        self.config = config or NUMERIC_SUBSTITUTION_CONFIG
        self.rng = random.Random(random_seed) if random_seed else random
        self.year_mapping = {}
        self.month_mapping = {}
        self.base_year = None
        self.base_month = None

    def extract_and_map(self, text: str):
        # 1. Map Years
        years = [int(y) for y in YEAR_REGEX_COLLECTOR.findall(text)]
        if years:
            min_year = min(years)
            offsets = {year: year - min_year for year in years}
            self.base_year = self.rng.choice(years)  # Pick random existing year as base
            # Perturb base year slightly (e.g. -2 to +2)
            perturbation = self.rng.randint(-2, 2)
            self.base_year += perturbation

            for year, offset in offsets.items():
                self.year_mapping[year] = self.base_year + offset

        # 2. Map Months
        # (Simplified logic for brevity)
        months = []
        for m in MONTH_REGEX.finditer(text):
            raw = m.group(1).lower()
            if raw == "may" and not m.group(1)[0].isupper():
                continue  # Skip verb 'may'
            val = MONTH_NAMES.get(raw) or MONTH_ABBREVIATIONS.get(raw)
            if val:
                months.append(val)

        if months:
            min_month = min(months)
            offsets = {m: m - min_month for m in months}
            self.base_month = self.rng.randint(1, 12)
            for m, offset in offsets.items():
                new_val = ((self.base_month + offset - 1) % 12) + 1
                self.month_mapping[m] = new_val

    def substitute(self, text: str) -> str:
        # Years
        if self.year_mapping:
            text = YEAR_REGEX_COLLECTOR.sub(
                lambda m: str(self.year_mapping.get(int(m.group(0)), m.group(0))), text
            )

        # Numbers
        if self.config["apply_to_numbers"]:

            def replace_num(m):
                s = m.group(0)
                try:
                    # Don't replace years we just mapped
                    if int(float(s)) in self.year_mapping.values():
                        return s
                    val = float(s)
                    if val == 0:
                        return s
                    delta = self.rng.uniform(
                        -self.config["number_perturbation"],
                        self.config["number_perturbation"],
                    )
                    new_val = val * (1 + delta)
                    # Format preservation logic
                    if "." in s:
                        return f"{new_val:.2f}"
                    return str(int(new_val))
                except:
                    return s

            text = NON_YEAR_NUMBER_REGEX.sub(replace_num, text)

        # Months (Simplified replacement)
        if self.month_mapping:

            def replace_month(m):
                raw = m.group(1)
                lower = raw.lower()
                if lower == "may" and not raw[0].isupper():
                    return raw
                val = MONTH_NAMES.get(lower) or MONTH_ABBREVIATIONS.get(lower)
                if not val or val not in self.month_mapping:
                    return raw

                new_val = self.month_mapping[val]
                new_name = MONTH_NUMBER_TO_NAME[new_val]
                if raw in MONTH_ABBREVIATIONS:
                    new_name = MONTH_NUMBER_TO_ABBREV[new_val]

                return new_name.capitalize() if raw[0].isupper() else new_name

            text = MONTH_REGEX.sub(replace_month, text)

        return text


class DynamicEntitySubstitution:
    """Replaces specific entities (FASB, SEC) with generic terms."""

    def __init__(self):
        self.targets = ["FASB", "SEC", "IASB", "ASC", "IFRS", "GAAP"]
        self.replacements = [
            "The Board",
            "The Authority",
            "The Commission",
            "The Standard",
            "Guidance",
            "Regulation",
        ]
        self.pattern = re.compile(
            r"\b(" + "|".join(map(re.escape, self.targets)) + r")\b"
        )

    def substitute(self, text: str) -> str:
        if not self.pattern.search(text):
            return text
        mapping = {t: random.choice(self.replacements) for t in self.targets}
        return self.pattern.sub(lambda m: mapping.get(m.group(1), m.group(1)), text)


class DynamicCurrencySubstitution:
    """Replaces currencies to prevent regional overfitting."""

    def __init__(self):
        # Cache patterns to avoid rebuild
        self.codes = [c.code for c in all_currencies]
        self.names = [c.full_name for c in all_currencies]
        self.code_pattern = re.compile(r"\b(" + "|".join(self.codes) + r")\b")
        self.name_pattern = re.compile(
            r"\b(" + "|".join(map(re.escape, self.names)) + r")\b", re.IGNORECASE
        )

    def substitute(self, text: str) -> str:
        found_codes = set(self.code_pattern.findall(text))
        found_names = set(m.group(0).lower() for m in self.name_pattern.finditer(text))

        if not found_codes and not found_names:
            return text

        # Pick new random currencies
        needed = len(found_codes) + len(found_names)
        replacements = random.sample(
            all_currencies, min(needed + 2, len(all_currencies))
        )

        mapping = {}
        idx = 0

        for code in found_codes:
            mapping[code] = replacements[idx].code
            idx += 1

        for name in found_names:
            # Simple case match
            mapping[name] = replacements[idx].full_name.lower()
            mapping[name.title()] = replacements[idx].full_name.title()
            idx += 1

        # Apply
        text = self.code_pattern.sub(
            lambda m: mapping.get(m.group(1), m.group(1)), text
        )
        # Note: Name replacement is complex due to overlaps, simplified here
        return text


# =============================================================================
# 2. CORE LOGIC: WINDOWING & LABELING
# =============================================================================


def get_active_passive_label(text: str) -> Optional[int]:
    """
    Heuristic Labeler.
    1 = Active (Positive)
    0 = Passive/Boilerplate (Negative)
    None = Ambiguous/Skip
    """
    # 1. GATE: Must mention a derivative
    if not (
        SOFT_GEN_REGEX.search(text)
        or SOFT_REGEX.search(text)
        or GEN_REGEX.search(text)
    ):
        if COUNTERPARTY_REGEX.search(text):
            return 0  # Explicit Risk Policy is Passive
        return None  # Irrelevant

    # 2. DETECT PASSIVE SIGNALS (Priority over Active)
    has_potential = bool(POTENTIAL_REGEX.search(text))
    has_absence = (
        bool(ABSENCE_REGEX.search(text))
        or bool(NEGATIVE_INTENT_REGEX.search(text))
        or bool(DID_NOT_HOLD_REGEX.search(text))
    )
    has_termination = bool(TERMINATION_REGEX.search(text))
    has_trading_denial = bool(TRADING_STATEMENTS_REGEX.search(text))

    # Truth Table for Discarding (Label 0)
    if has_potential and has_absence:
        return 0  # "May use... don't have"
    if has_termination and has_absence:
        return 0  # "Terminated... none left"
    if has_trading_denial and has_absence:
        return 0  # "Don't speculate... don't have"
    if has_absence and not has_potential:
        return 0  # "We have no contracts"
    if has_trading_denial and len(text) < 300:
        return 0  # Short trading denials

    # 3. DETECT ACTIVE SIGNALS (Label 1)
    has_strict = bool(STRICT_REGEX.search(text))
    has_quant = bool(QUANT_REGEX.search(text))

    if has_strict and has_quant:
        # Final Safety: Ensure no "Termination" or "Absence" overrides the numbers
        if not (has_termination or has_absence):
            return 1

    return None


def get_safe_window(sentences: list, target_idx: int, max_chars=2000) -> str:
    """
    Gets full paragraph context if safe, otherwise shrinks around target.
    Preserves Order.
    """
    target_sent = sentences[target_idx]

    # 1. Try taking the whole paragraph
    full_text = BOUNDARY.join(sentences)
    if len(full_text) <= max_chars:
        return full_text

    # 2. If too big, shrink window around the target
    current_window = [target_sent]
    left_ptr = target_idx - 1
    right_ptr = target_idx + 1
    current_len = len(target_sent)

    while True:
        added_something = False

        # Add Left
        if left_ptr >= 0:
            new_len = current_len + len(sentences[left_ptr]) + len(BOUNDARY)
            if new_len < max_chars:
                current_window.insert(0, sentences[left_ptr])
                current_len = new_len
                left_ptr -= 1
                added_something = True

        # Add Right
        if right_ptr < len(sentences):
            new_len = current_len + len(sentences[right_ptr]) + len(BOUNDARY)
            if new_len < max_chars:
                current_window.append(sentences[right_ptr])
                current_len = new_len
                right_ptr += 1
                added_something = True

        if not added_something:
            break

    return BOUNDARY.join(current_window)


def generalize_instrument(text: str) -> str:
    """
    Augmentation: Replaces specific instruments with generic terms
    to force model to focus on context/verbs.
    """
    match = STRICT_REGEX.search(text)
    if not match:
        return text

    generics = [
        "hedging instruments",
        "derivative contracts",
        "financial instruments",
        "hedging agreements",
        "hedge contracts",
        "derivative positions",
        "derivative financial instruments",
        "derivatives",
        "embedded derivatives",
        "financial agreements",
        "risk management instruments",
    ]
    replacement = random.choice(generics)

    span = match.span()
    return text[: span[0]] + replacement + text[span[1] :]


# =============================================================================
# 3. WORKER & MAIN
# =============================================================================


def process_chunk(chunk_data):
    # Initialize Substitution Engines per process
    import time

    random.seed(os.getpid() + time.time())

    entity_sub = DynamicEntitySubstitution()
    currency_sub = DynamicCurrencySubstitution()

    active_rows = []
    passive_rows = []

    for url, matches_json in chunk_data:
        try:
            paragraphs = json.loads(matches_json)
        except:
            continue

        for para in paragraphs:
            if "<TABLE>" in para:
                continue  # Skip tables for training

            sentences = [
                s.strip()
                for s in SENTENCE_SPLIT_PATTERN.split(para)
                if len(s) > MIN_SENTENCE_LENGTH
            ]

            for i, sent in enumerate(sentences):

                # 1. Get Label
                label = get_active_passive_label(sent)
                if label is None:
                    continue

                # 2. Get Context Window
                window_text = get_safe_window(sentences, i)

                # 3. Apply Substitutions to Window (Crucial: Apply to whole window)
                # Numeric
                num_sub = NumericSubstitutionEngine()
                num_sub.extract_and_map(window_text)
                window_text = num_sub.substitute(window_text)

                # Entity & Currency
                window_text = entity_sub.substitute(window_text)
                window_text = currency_sub.substitute(window_text)
                window_text = re.sub(BOUNDARY, SEP_TOKEN, window_text)
                # 4. Instrument Generalization (Augmentation)
                # Apply 50% of the time to Active samples to prevent overfitting "Swap"
                if label == 1 and random.random() < 0.5:
                    window_text = generalize_instrument(window_text)

                row = {
                    "text": window_text,
                    "label": label,
                    "original_target": sent,
                    "url": url,
                }

                if label == 1:
                    active_rows.append(row)
                else:
                    passive_rows.append(row)

    return active_rows, passive_rows


def generate_dataset():
    print(f"🚀 Generating Binary Dataset (Active vs Passive)...")

    conn = sqlite3.connect(DB_PATH)
    # Get total count for progress bar
    try:
        total_rows = conn.execute(
            "SELECT count(*) FROM webpage_result WHERE matches IS NOT NULL"
        ).fetchone()[0]
    except:
        total_rows = 0

    df_iter = pd.read_sql_query(
        "SELECT url, matches FROM webpage_result WHERE matches IS NOT NULL",
        conn,
        chunksize=CHUNK_SIZE,
    )

    all_active = []
    all_passive = []

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for chunk in tqdm(
            df_iter, total=(total_rows // CHUNK_SIZE), desc="Processing DB"
        ):
            chunk_data = list(zip(chunk["url"], chunk["matches"]))
            futures = [executor.submit(process_chunk, chunk_data)]

            for f in futures:
                actives, passives = f.result()
                all_active.extend(actives)
                all_passive.extend(passives)

            # Memory Management / Early Stop
            if (
                len(all_active) > TARGET_SAMPLES * 1.5
                and len(all_passive) > TARGET_SAMPLES * 1.5
            ):
                print("⚡ Hit target sample count, stopping early.")
                break

    # Balance
    min_count = min(len(all_active), len(all_passive))
    print(f"\n📊 Found: {len(all_active)} Active | {len(all_passive)} Passive")

    if min_count == 0:
        print("❌ Error: One class has 0 samples. Check Regexes.")
        return

    print(f"⚖️ Balancing to {min_count} per class...")
    final_active = random.sample(all_active, min_count)
    final_passive = random.sample(all_passive, min_count)

    df = pd.DataFrame(final_active + final_passive)
    df = df.sample(frac=1).reset_index(drop=True)  # Shuffle rows

    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Saved {len(df)} samples to {OUTPUT_PATH}")


if __name__ == "__main__":
    generate_dataset()
