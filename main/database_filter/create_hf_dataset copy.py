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
from tqdm import tqdm

# Ensure we can import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from derivative_regex import (
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
)
from filter_database import get_sentence_categories

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_PATH = "web_data.db"
OUTPUT_PATH = "roberta/classification_data_v16_dynamic_window.parquet"

# THE SEPARATOR TOKEN
SEP_TOKEN = " [SEP] "

# DYNAMIC WINDOW SETTINGS
# Min 1 (immediate neighbor), Max 3 (3 prev, 3 next)
MIN_WINDOW_SIZE = 1
MAX_WINDOW_SIZE = 3

TARGET_SAMPLES_PER_CLASS = 2500
SATURATION_LIMIT = int(TARGET_SAMPLES_PER_CLASS * 1.5)
CHUNK_SIZE = 5000
MAX_WORKERS = max(1, mp.cpu_count() - 1)

LABEL_TO_CONFLICT_REGEX = {
    "ir": [FX_CONTEXT_REGEX, CP_CONTEXT_REGEX, EQ_CONTEXT_REGEX],
    "fx": [IR_CONTEXT_REGEX, CP_CONTEXT_REGEX, EQ_CONTEXT_REGEX],
    "cp": [IR_CONTEXT_REGEX, FX_CONTEXT_REGEX, EQ_CONTEXT_REGEX],
    "eq": [IR_CONTEXT_REGEX, FX_CONTEXT_REGEX, CP_CONTEXT_REGEX],
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
        if label == "fx" and re.search(r"\b(foreign|exchange)\s+rate\b", text, re.I):
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
# DYNAMIC WINDOW LOGIC
# =============================================================================


def get_dynamic_window(sentences, target_idx, override_target=None, context_bank=None):
    """
    Constructs a variable-width window.
    - Distance 1: Always kept clean.
    - Distance 2+: Chance to inject noise increases.
    """

    # 1. Determine Target
    target_sent = (
        override_target if override_target is not None else sentences[target_idx]
    )

    # 2. Determine Window Width (Random between Min and Max)
    # This forces the model to handle both short and long contexts
    current_width = random.randint(MIN_WINDOW_SIZE, MAX_WINDOW_SIZE)

    prev_parts = []
    next_parts = []

    # 3. Build Outwards
    for dist in range(1, current_width + 1):

        # --- Previous Side ---
        if target_idx - dist >= 0:
            sent = sentences[target_idx - dist]
            # Noise Logic: Distance 2=20%, Distance 3=50%
            noise_prob = 0.0
            if dist == 2:
                noise_prob = 0.2
            if dist >= 3:
                noise_prob = 0.5

            if context_bank and random.random() < noise_prob:
                sent = context_bank.get_noise()  # Inject Noise

            # Prepend (so order is correct: Dist3, Dist2, Dist1)
            prev_parts.insert(0, sent)

        # --- Next Side ---
        if target_idx + dist < len(sentences):
            sent = sentences[target_idx + dist]
            # Same noise logic
            noise_prob = 0.0
            if dist == 2:
                noise_prob = 0.2
            if dist >= 3:
                noise_prob = 0.5

            if context_bank and random.random() < noise_prob:
                sent = context_bank.get_noise()

            next_parts.append(sent)

    # 4. Construct with Separators
    # Join neighbors with spaces first
    prev_block = " ".join(prev_parts)
    next_block = " ".join(next_parts)

    # Final Structure: PrevBlock [SEP] Target [SEP] NextBlock
    return f"{prev_block}{SEP_TOKEN}{target_sent}{SEP_TOKEN}{next_block}"


def has_conflict(text, label):
    for regex in LABEL_TO_CONFLICT_REGEX.get(label, []):
        if regex.search(text):
            return True
    return False


def process_chunk(chunk_data):
    scorer = ContextScorer()
    augmenter_dummy = AugmentationEngine()
    local_candidates = []
    # We return noise candidates to main process
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
            # Optimization
            if not (
                STRICT_REGEX.search(para)
                or HEDGING_CONTEXT_REGEX.search(para)
                or EXCLUDE_REGEX_ACCOUNTING_STD.search(para)
            ):
                # Even if skipped, maybe use as noise? (Optional, skipping for speed)
                continue

            sentences = [
                s.strip()
                for s in SENTENCE_SPLIT_PATTERN.split(para)
                if len(s.strip()) >= MIN_SENTENCE_LENGTH
            ]

            # Collect sentences for noise pool (generic financial text)
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

                        # Score using just immediate context (Distance 1) for reliability
                        # We don't want to score based on the noisy outer layers
                        target_sent = sentences[i]
                        blanked_target = (
                            target_sent[: match.start()]
                            + "       "
                            + target_sent[match.end() :]
                        )
                        # Use minimal window for scoring check
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
                            }
                        )

                    elif len(specific_cats) == 0:
                        # Generic Instrument
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
                                    }
                                )

    return local_candidates, local_noise


# =============================================================================
# MAIN
# =============================================================================


def create_labeled_dataset():
    print(f"🚀 Starting Dataset Generation v16 (Dynamic Window + Noise)")

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

                        # Feed the noise bank
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

    # --- PHASE 2: GENERATION ---
    print("\n🏆 PASS 2: Generating Dataset...")
    final_data = []
    stats = Counter()

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

            # DYNAMIC WINDOW GENERATION IS CALLED HERE
            # It uses the Noise Bank populated in Phase 1

            row = {
                "text": "",
                "label": label,
                "difficulty": "",
                "debug_original": orig,
                "debug_score": score,
                "debug_hint": "None",
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
                match_span = item["match_span"]
                match_text = item["match_text"]

                # We removed conflict injection for simplicity, but you can re-add it here
                # For now, focus on pure L2 Masking with Dynamic Context
                aug, _ = augmenter.augment(orig, match_span, match_text)
                row["text"] = get_dynamic_window(
                    sentences, idx, override_target=aug, context_bank=context_bank
                )
                row["difficulty"] = "L2_Masked"

            elif score > 0:
                # L1 Weak (We don't mask, but we widen the window to find help)
                row["text"] = get_dynamic_window(
                    sentences, idx, context_bank=context_bank
                )
                row["difficulty"] = "L1_WeakContext"

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
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    mp.freeze_support()
    create_labeled_dataset()
