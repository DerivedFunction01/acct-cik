import sqlite3
import pandas as pd
import json
import random
import re
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from collections import Counter, defaultdict
import sys
import os
import hashlib
import logging
from typing import Tuple, Set, List, Optional, Dict, Any
from tqdm import tqdm

# Ensure we can import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from derivative_regex import (
    CP_REGEX,
    EQ_REGEX,
    FX_REGEX,
    GEN_REGEX,
    IR_REGEX,
    SENTENCE_SPLIT_PATTERN,
    STRICT_REGEX,
    MIN_SENTENCE_LENGTH,
    CATEGORY_CONTEXT_MAP,
    UNAMBIGUOUS_BASE_TYPES,
    IR_CONTEXT_REGEX,
    FX_CONTEXT_REGEX,
    CP_CONTEXT_REGEX,
    EQ_CONTEXT_REGEX,
    HEDGING_CONTEXT_REGEX,
    EXCLUDE_REGEX_ACCOUNTING_STD,
    CATEGORY_DELETION_MAP,
    cleanup_fragment,
)
from filter_database import get_sentence_categories

# Setup logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "web_data.db"
OUTPUT_PATH = "roberta/classification_data_v17_scrubbed.parquet"

# THE SEPARATOR TOKEN
SEP_TOKEN = " [SEP] "

# DYNAMIC WINDOW SETTINGS
MIN_WINDOW_SIZE = 1
MAX_WINDOW_SIZE = 3

TARGET_SAMPLES_PER_CLASS = 1000
SATURATION_LIMIT = int(TARGET_SAMPLES_PER_CLASS * 1.5)
CHUNK_SIZE = 5000
MAX_WORKERS = max(1, mp.cpu_count() - 1)

# Scrubbing configuration
SCRUBBING_CONFIG = {
    "keep_same_category_bases": True,  # Keep multiple IR swaps/caps/locks
    "remove_category_context": True,  # Remove FX/CP/EQ context signals
    "min_instruments_per_sentence": 1,  # At least one instrument remains
    "aggressive_scrub": True,  # If True, remove ALL non-target instruments
}

LABEL_TO_CONFLICT_REGEX = {
    "ir": [
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        FX_REGEX,
        CP_REGEX,
        EQ_REGEX,
    ],
    "fx": [
        IR_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        IR_REGEX,
        CP_REGEX,
        EQ_REGEX,
    ],
    "cp": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        IR_REGEX,
        FX_REGEX,
        EQ_REGEX,
    ],
    "eq": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        IR_REGEX,
        FX_REGEX,
        CP_REGEX,
    ],
    "gen": [
        IR_CONTEXT_REGEX,
        FX_CONTEXT_REGEX,
        CP_CONTEXT_REGEX,
        EQ_CONTEXT_REGEX,
        IR_REGEX,
        FX_REGEX,
        CP_REGEX,
        EQ_REGEX
    ],
}

# =============================================================================
# HELPER CLASSES
# =============================================================================


class ContentDeduplicator:
    def __init__(self):
        self.seen_hashes = set()
        self.dupe_count = 0

    def is_duplicate(self, text: str) -> bool:
        norm = re.sub(r"\d+", "0", text.lower())
        norm = re.sub(r"[^\w]", "", norm)
        if len(norm) < 10:
            return False
        content_hash = hashlib.md5(norm.encode("utf-8")).hexdigest()
        if content_hash in self.seen_hashes:
            self.dupe_count += 1
            return True
        self.seen_hashes.add(content_hash)
        return False


class ContextScorer:
    def score(self, text: str, label: str) -> int:
        if len(text) > 500: # penalize long text; it may be a table
            return 0
        regex = CATEGORY_CONTEXT_MAP.get(label)
        if not regex:
            return 0
        matches = regex.findall(text)
        unique_hits = set(m.lower() for m in matches)
        score = len(unique_hits) * 10
        if re.search(r"\b(hedg|mitigat|manag)(?:e|es|ed|ing)\b", text, re.I):
            score += 15
        if label == "ir" and re.search(
            r"\b(variable|floating|fixed)\s+rate\b", text, re.I
        ):
            score += 20
        if label == "fx" and re.search(r"\b(foreign rate|exchange rate|denominated)\b", text, re.I):
            score += 20
        if label == "cp" and re.search(r"\b(price|commodity|fuel|oil)\b", text, re.I):
            score += 20
        if label == "eq":
            text_lower = text.lower()
            is_comp_talk = any(
                x in text_lower
                for x in ["employee", "compensation", "vesting", "grant", "award"]
            )
            is_hedging_talk = re.search(
                r"\b(hedg|mitigat|manag|offset)(?:e|es|ed|ing)\b", text, re.I
            )
            if is_comp_talk and not is_hedging_talk:
                return -1
            if is_comp_talk and is_hedging_talk:
                score += 25
        return score

    def get_max_score_any_category(self, text: str) -> int:
        scores = [self.score(text, lbl) for lbl in ["ir", "fx", "cp", "eq"]]
        return max(scores)


class AugmentationEngine:
    def __init__(self):
        self.generic_terms = [
            "derivative",
            "instrument",
            "contract",
            "agreement",
            "hedging instrument",
            "hedge",
            "position",
        ]
        self.bases = [
            b.replace("?", "").replace("s", "") for b in UNAMBIGUOUS_BASE_TYPES
        ]

    def augment(self, text: str, span: tuple, match_text: str):
        start, end = span
        if random.random() < 0.3:
            replacement = random.choice(self.generic_terms)
            strategy = "Generic_Universal"
        else:
            found_base = "instrument"
            for base in self.bases:
                if base in match_text.lower():
                    found_base = base
                    break
            replacement = f"{found_base} {random.choice(['', 'contract'])}".strip()
            strategy = "Loose_Variant"
        augmented_text = text[:start] + replacement + text[end:]
        return augmented_text, strategy


class DynamicContextBank:
    def __init__(self):
        # Store valid sentences to use as "Noise" later
        self.noise_pool = []

    def add_noise_candidate(self, text):
        # Keep pool manageable
        if len(self.noise_pool) < 5000:
            self.noise_pool.append(text)
        elif random.random() < 0.1:  # Random replacement to keep fresh
            self.noise_pool[random.randint(0, 4999)] = text

    def get_noise(self):
        if not self.noise_pool:
            return "See Note X."
        return random.choice(self.noise_pool)


# =============================================================================
# SCRUBBING FUNCTIONS
# =============================================================================


def scrub_non_target_instruments(
    text: str,
    target_category: str,
    all_detected_categories: Set[str],
    keep_same_category_bases: bool = True,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Remove all derivative instruments NOT matching the target category.
    Preserves target category instruments unless aggressive mode is enabled.

    Args:
        text: Original sentence
        target_category: Category to preserve ("ir", "fx", "cp", "eq")
        all_detected_categories: Set of all categories found in text
        keep_same_category_bases: If True, keep multiple same-category instruments
                                  (e.g., keep "caps" when masking "swap" for IR).
                                  If False, remove all but the first.

    Returns:
        Tuple of (cleaned_text, list_of_removed_info)

    Example:
        >>> text = "We use interest rate swaps and FX forwards."
        >>> scrub_non_target_instruments(text, "ir", {"ir", "fx"})
        # Returns: ("We use interest rate swaps and forwards.", [...])
        # Removed FX context but kept both instrument names
    """

    removed_info = []
    cleaned_text = text

    # Identify categories to scrub (all except target)
    categories_to_scrub = all_detected_categories - {target_category, "gen", "other"}

    if not categories_to_scrub:
        return cleaned_text, removed_info

    # For each non-target category, remove its instruments and context
    for scrub_cat in categories_to_scrub:
        if scrub_cat not in CATEGORY_DELETION_MAP:
            continue

        instrument_regex, context_regex = CATEGORY_DELETION_MAP[scrub_cat]

        # Track what we're removing
        instrument_matches = [
            m.group(0) for m in instrument_regex.finditer(cleaned_text)
        ]
        context_matches = [m.group(0) for m in context_regex.finditer(cleaned_text)]

        if instrument_matches or context_matches:
            removed_info.append(
                {
                    "category": scrub_cat,
                    "instruments": instrument_matches,
                    "context_terms": context_matches,
                }
            )

        # Remove cross-category instruments
        cleaned_text = instrument_regex.sub(" ", cleaned_text)

        # Remove cross-category context clues
        cleaned_text = context_regex.sub(" ", cleaned_text)

    # Normalize whitespace and punctuation
    cleaned_text = cleanup_fragment(cleaned_text)

    return cleaned_text, removed_info


def validate_scrubbed_example(
    scrubbed_text: str,
    target_category: str,
    removed_info: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """
    Validate that scrubbing produced a usable training example.

    Checks:
    1. Scrubbed text meets minimum length
    2. Target category instrument still present
    3. Text is non-empty after scrubbing

    Returns:
        Tuple of (is_valid, error_reason_or_none)
    """

    # Check 1: Minimum length
    if len(scrubbed_text) < MIN_SENTENCE_LENGTH:
        return (
            False,
            f"Scrubbed text too short: {len(scrubbed_text)} < {MIN_SENTENCE_LENGTH}",
        )

    # Check 2: Target instrument still present (if specific category)
    if target_category not in {"gen", "other"}:
        target_instrument_regex = CATEGORY_DELETION_MAP[target_category][0]

        if not target_instrument_regex.search(scrubbed_text):
            return (
                False,
                f"Target category {target_category} instrument lost after scrubbing",
            )

    # Check 3: Text not empty
    if not scrubbed_text.strip():
        return False, "Text became empty after scrubbing"

    return True, None


def prepare_training_example(
    sentence: str,
    target_category: str,
    all_detected_categories: Set[str],
    replacement_strategy: str = "stochastic",
) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """
    Convert a sentence into a training example by:
    1. Scrubbing non-target category instruments/context
    2. Masking the target category instrument
    3. Validating output quality

    Args:
        sentence: Source sentence
        target_category: Category for this training example
        all_detected_categories: All categories found in sentence
        replacement_strategy: "stochastic", "base", or "generic"

    Returns:
        Tuple of (masked_text, category, metadata) or None if validation fails

    Example:
        >>> sentence = "We use interest rate swaps to hedge."
        >>> prepare_training_example(sentence, "ir", {"ir"})
        # Returns: ("We use swaps to hedge.", "ir", {...})
    """

    # Step 1: Scrub non-target instruments/context
    scrubbed_text, removed = scrub_non_target_instruments(
        sentence,
        target_category,
        all_detected_categories,
        keep_same_category_bases=SCRUBBING_CONFIG["keep_same_category_bases"],
    )

    # Step 2: Validate scrubbed result
    is_valid, error_reason = validate_scrubbed_example(
        scrubbed_text, target_category, removed
    )

    if not is_valid:
        logger.debug(f"Scrubbed example invalid: {error_reason}")
        return None

    # Step 3: Mask the target instrument
    masked_text = scrubbed_text
    replacement_info = {}

    if target_category not in {"gen", "other"}:
        target_instrument_regex = CATEGORY_DELETION_MAP[target_category][0]

        # Find the match to determine what we're replacing
        match = target_instrument_regex.search(scrubbed_text)
        if not match:
            logger.warning(
                f"Target instrument not found after scrubbing: {target_category}"
            )
            return None

        matched_text = match.group(0)

        # Apply replacement strategy
        if replacement_strategy == "stochastic":
            # 30% base, 70% loose variant
            if random.random() < 0.3:
                replacement = _get_base_form(matched_text, target_category)
                strategy = "base"
            else:
                replacement = _get_loose_variant(matched_text, target_category)
                strategy = "loose_variant"
        elif replacement_strategy == "base":
            replacement = _get_base_form(matched_text, target_category)
            strategy = "base"
        elif replacement_strategy == "generic":
            replacement = _get_generic_form(target_category)
            strategy = "generic"
        else:
            replacement = matched_text
            strategy = "none"

        replacement_info = {
            "original_instrument": matched_text,
            "replacement": replacement,
            "strategy": strategy,
        }

        # Replace only the first occurrence to preserve other same-category bases
        masked_text = target_instrument_regex.sub(replacement, scrubbed_text, count=1)

    # Step 4: Final validation
    if len(masked_text) < MIN_SENTENCE_LENGTH:
        logger.debug(f"Masked text too short after replacement")
        return None

    metadata = {
        "removed_categories": removed,
        "replacement_info": replacement_info,
        "scrubbing_applied": bool(removed),
    }

    return (masked_text, target_category, metadata)


# =============================================================================
# REPLACEMENT STRATEGY HELPERS
# =============================================================================


def _get_base_form(matched_text: str, category: str) -> str:
    """
    Extract base instrument form using GEN_REGEX.
    E.g., "interest rate swap agreement" → "swap" or "swaps"
    """
    # GEN_REGEX captures the instrument portion
    match = GEN_REGEX.search(matched_text)
    if match:
        instrument = match.group("instrument")
        # Extract just the last word (typically the base)
        words = instrument.split()
        return words[-1] if words else instrument

    # Fallback: just use last word of original match
    words = matched_text.split()
    return words[-1] if len(words) > 1 else matched_text


def _get_loose_variant(matched_text: str, category: str) -> str:
    """
    Create a loose variant (e.g., "swap" → "swap agreement" or "swap instrument").
    """
    base = _get_base_form(matched_text, category)

    suffixes = ["agreement", "instrument", "contract"]
    chosen_suffix = random.choice(suffixes)

    return f"{base} {chosen_suffix}"


def _get_generic_form(category: str) -> str:
    """
    Use generic hedging language without category-specific signals.
    """
    generics = [
        "hedging instruments",
        "derivative contracts",
        "financial instruments",
        "hedging agreements",
        "derivative positions",
        "derivatives",
    ]

    return random.choice(generics)


# =============================================================================
# DYNAMIC WINDOW LOGIC
# =============================================================================


def get_dynamic_window(sentences, target_idx, override_target=None, context_bank=None):
    """
    Constructs a variable-width window.
    - Distance 1: Always kept clean.
    - Distance 2+: Chance to inject noise increases.
    """
    target_sent = (
        override_target if override_target is not None else sentences[target_idx]
    )

    current_width = random.randint(MIN_WINDOW_SIZE, MAX_WINDOW_SIZE)
    prev_parts = []
    next_parts = []

    for dist in range(1, current_width + 1):
        if target_idx - dist >= 0:
            sent = sentences[target_idx - dist]
            noise_prob = 0.0
            if dist == 2:
                noise_prob = 0.2
            if dist >= 3:
                noise_prob = 0.5

            if context_bank and random.random() < noise_prob:
                sent = context_bank.get_noise()

            prev_parts.insert(0, sent)

        if target_idx + dist < len(sentences):
            sent = sentences[target_idx + dist]
            noise_prob = 0.0
            if dist == 2:
                noise_prob = 0.2
            if dist >= 3:
                noise_prob = 0.5

            if context_bank and random.random() < noise_prob:
                sent = context_bank.get_noise()

            next_parts.append(sent)

    prev_block = " ".join(prev_parts)
    next_block = " ".join(next_parts)

    return f"{prev_block}{SEP_TOKEN}{target_sent}{SEP_TOKEN}{next_block}"


def has_conflict(text, label):
    for regex in LABEL_TO_CONFLICT_REGEX.get(label, []):
        if regex.search(text):
            return True
    return False


# =============================================================================
# ENHANCED PROCESSING WITH SCRUBBING
# =============================================================================


def process_chunk(chunk_data):
    scorer = ContextScorer()
    augmenter_dummy = AugmentationEngine()
    local_candidates = []
    local_noise = []

    for url, matches_json in chunk_data:
        try:
            paragraphs = json.loads(matches_json)
        except:
            continue
        if not isinstance(paragraphs, list):
            continue

        for para in paragraphs:
            if "<TABLE>" in para:
                continue

            if not (
                STRICT_REGEX.search(para)
                or HEDGING_CONTEXT_REGEX.search(para)
                or EXCLUDE_REGEX_ACCOUNTING_STD.search(para)
            ):
                continue

            sentences = [
                s.strip()
                for s in SENTENCE_SPLIT_PATTERN.split(para)
                if len(s.strip()) >= MIN_SENTENCE_LENGTH
            ]

            if len(sentences) > 2:
                local_noise.append(random.choice(sentences))

            for i, sentence in enumerate(sentences):
                match = STRICT_REGEX.search(sentence)

                # --- Branch A: Strict Match ---
                if match:
                    cats = get_sentence_categories(sentence)
                    specific_cats = cats - {"gen", "other"}

                    if len(specific_cats) == 1:
                        label = list(specific_cats)[0]

                        target_sent = sentences[i]
                        blanked_target = (
                            target_sent[: match.start()]
                            + "       "
                            + target_sent[match.end() :]
                        )
                        validation_text = get_dynamic_window(
                            sentences, i, override_target=blanked_target
                        )

                        score = (
                            -1
                            if has_conflict(validation_text, label)
                            else scorer.score(validation_text, label)
                        )

                        local_candidates.append(
                            {
                                "label": label,
                                "sentences": sentences,
                                "target_idx": i,
                                "match_span": match.span(),
                                "match_text": match.group(0),
                                "original_sent": sentence,
                                "score": score,
                                "url": url,
                                "detected_categories": cats,
                            }
                        )

                    elif len(specific_cats) == 0:
                        full_window = get_dynamic_window(sentences, i)
                        max_score = scorer.get_max_score_any_category(full_window)
                        if max_score < 10:
                            local_candidates.append(
                                {
                                    "label": "gen",
                                    "sentences": sentences,
                                    "target_idx": i,
                                    "match_span": match.span(),
                                    "match_text": match.group(0),
                                    "original_sent": sentence,
                                    "score": 0,
                                    "url": url,
                                    "subtype": "L0_Ambiguous_Instrument",
                                    "detected_categories": cats,
                                }
                            )

                # --- Branch B: No Strict Match ---
                else:
                    is_hedging_talk = bool(HEDGING_CONTEXT_REGEX.search(sentence))
                    is_accounting = bool(EXCLUDE_REGEX_ACCOUNTING_STD.search(sentence))

                    if is_hedging_talk or is_accounting:
                        cats = get_sentence_categories(sentence)
                        specific_cats = cats - {"gen", "other"}

                        if len(specific_cats) == 0:
                            full_window = get_dynamic_window(sentences, i)
                            max_score = scorer.get_max_score_any_category(full_window)

                            if max_score < 10:
                                subtype = (
                                    "L0_Accounting"
                                    if is_accounting
                                    else "L0_Risk_Policy"
                                )
                                local_candidates.append(
                                    {
                                        "label": "gen",
                                        "sentences": sentences,
                                        "target_idx": i,
                                        "match_span": None,
                                        "match_text": "None",
                                        "original_sent": sentence,
                                        "score": 0,
                                        "url": url,
                                        "subtype": subtype,
                                        "detected_categories": cats,
                                    }
                                )

    return local_candidates, local_noise


# =============================================================================
# MAIN GENERATION WITH SCRUBBING
# =============================================================================


def create_labeled_dataset():
    print(f"🚀 Starting Dataset Generation v17 (Scrubbing + Masking)")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT count(*) FROM webpage_result WHERE matches IS NOT NULL")
        total_rows = cursor.fetchone()[0]
    except:
        total_rows = 0
    print(f"   Source DB Rows: {total_rows:,}")

    df_iter = pd.read_sql_query(
        "SELECT url, matches FROM webpage_result WHERE matches IS NOT NULL",
        conn,
        chunksize=CHUNK_SIZE,
    )

    global_candidates = defaultdict(list)
    context_bank = DynamicContextBank()
    augmenter = AugmentationEngine()
    deduplicator = ContentDeduplicator()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        future_sizes = {}
        iterator = iter(df_iter)
        active = True

        with tqdm(total=total_rows, desc="Scanning DB", unit="rows") as pbar:
            while active or futures:
                while len(futures) < MAX_WORKERS * 2 and active:
                    try:
                        chunk = next(iterator)
                        chunk_data = list(zip(chunk["url"], chunk["matches"]))
                        ft = executor.submit(process_chunk, chunk_data)
                        futures.append(ft)
                        future_sizes[ft] = len(chunk)
                    except StopIteration:
                        active = False

                if not futures:
                    break

                import concurrent.futures

                done, _ = concurrent.futures.wait(
                    futures, return_when=concurrent.futures.FIRST_COMPLETED
                )

                for future in done:
                    futures.remove(future)
                    pbar.update(future_sizes.pop(future, 0))
                    try:
                        candidates, noise_samples = future.result()

                        for n in noise_samples:
                            context_bank.add_noise_candidate(n)

                        for c in candidates:
                            if not deduplicator.is_duplicate(c["original_sent"]):
                                global_candidates[c["label"]].append(c)

                        pbar.set_postfix(
                            {k: len(v) for k, v in global_candidates.items()}
                        )
                    except Exception as e:
                        pbar.write(f"Error: {e}")
    conn.close()
    print(f"   🚫 Deduped {deduplicator.dupe_count:,} redundant sentences.")

    # --- PHASE 2: GENERATION WITH SCRUBBING ---
    print("\n🏆 PASS 2: Generating Dataset with Scrubbing & Masking...")
    final_data = []
    stats = Counter()
    scrubbing_stats = Counter()

    for label, items in global_candidates.items():
        if label == "gen":
            random.shuffle(items)
        else:
            items.sort(key=lambda x: x["score"], reverse=True)

        for item in tqdm(items, desc=f"Generating {label}", leave=False):
            if stats[label] >= TARGET_SAMPLES_PER_CLASS:
                break

            sentences = item["sentences"]
            idx = item["target_idx"]
            orig = item["original_sent"]
            score = item.get("score", 0)
            url = item["url"]
            detected_cats = item.get("detected_categories", {label})

            row = {
                "text": "",
                "label": label,
                "difficulty": "",
                "debug_original": orig,
                "debug_score": score,
                "debug_hint": "None",
                "scrubbing_applied": False,
            }

            if label == "gen":
                row["text"] = get_dynamic_window(
                    sentences, idx, context_bank=context_bank
                )
                row["difficulty"] = item.get("subtype", "L0_Ambiguous")

            elif score == -1:
                row["text"] = get_dynamic_window(
                    sentences, idx, context_bank=context_bank
                )
                row["difficulty"] = "L4_Natural_Adverse"

            elif score >= 20:
                # Use scrubbing + masking approach
                prep_result = prepare_training_example(
                    orig, label, detected_cats, replacement_strategy="stochastic"
                )

                if prep_result:
                    masked_text, _, metadata = prep_result
                    row["text"] = get_dynamic_window(
                        sentences,
                        idx,
                        override_target=masked_text,
                        context_bank=context_bank,
                    )
                    row["difficulty"] = "L2_Masked_Scrubbed"
                    row["scrubbing_applied"] = metadata["scrubbing_applied"]
                    scrubbing_stats["L2_scrubbed"] += 1
                else:
                    # Fallback to old method if scrubbing fails
                    match_span = item["match_span"]
                    match_text = item["match_text"]
                    aug, _ = augmenter.augment(orig, match_span, match_text)
                    row["text"] = get_dynamic_window(
                        sentences, idx, override_target=aug, context_bank=context_bank
                    )
                    row["difficulty"] = "L2_Masked"
                    scrubbing_stats["L2_fallback"] += 1

            elif score > 0:
                # L1 Weak context
                prep_result = prepare_training_example(
                    orig, label, detected_cats, replacement_strategy="base"
                )

                if prep_result:
                    masked_text, _, metadata = prep_result
                    row["text"] = get_dynamic_window(
                        sentences,
                        idx,
                        override_target=masked_text,
                        context_bank=context_bank,
                    )
                    row["difficulty"] = "L1_WeakContext_Scrubbed"
                    row["scrubbing_applied"] = metadata["scrubbing_applied"]
                    scrubbing_stats["L1_scrubbed"] += 1
                else:
                    row["text"] = get_dynamic_window(
                        sentences, idx, context_bank=context_bank
                    )
                    row["difficulty"] = "L1_WeakContext"
                    scrubbing_stats["L1_unscrubbed"] += 1

            else:
                row["text"] = get_dynamic_window(
                    sentences, idx, context_bank=context_bank
                )
                row["difficulty"] = "L1_NoContext"

            final_data.append(row)
            stats[label] += 1

    df = pd.DataFrame(final_data)
    print("\n📊 Final Distribution:")
    print(df["label"].value_counts())
    print("\n🧹 Scrubbing Statistics:")
    print(dict(scrubbing_stats))
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    mp.freeze_support()
    create_labeled_dataset()
