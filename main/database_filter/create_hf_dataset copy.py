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

# Import tqdm for progress bars
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
OUTPUT_PATH = "roberta/classification_data_v11_tqdm.parquet"
TARGET_SAMPLES_PER_CLASS = 6000
SATURATION_LIMIT = int(TARGET_SAMPLES_PER_CLASS * 1.5)
CONTEXT_WINDOW_SIZE = 1
CHUNK_SIZE = 5000
MAX_WORKERS = max(1, mp.cpu_count() - 1)

LABEL_TO_CONFLICT_REGEX = {
    "ir": [FX_CONTEXT_REGEX, CP_CONTEXT_REGEX, EQ_CONTEXT_REGEX],
    "fx": [IR_CONTEXT_REGEX, CP_CONTEXT_REGEX, EQ_CONTEXT_REGEX],
    "cp": [IR_CONTEXT_REGEX, FX_CONTEXT_REGEX, EQ_CONTEXT_REGEX],
    "eq": [IR_CONTEXT_REGEX, FX_CONTEXT_REGEX, CP_CONTEXT_REGEX],
}

CONFLICT_CATEGORY_MAP = {
    "ir": ["fx", "cp", "eq"],
    "fx": ["ir", "cp", "eq"],
    "cp": ["ir", "fx", "eq"],
    "eq": ["ir", "fx", "cp"],
}

# =============================================================================
# HELPER CLASSES
# =============================================================================


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
        self.global_bank = defaultdict(list)
        self.firm_bank = defaultdict(lambda: defaultdict(list))

    def add_teacher(self, label, url, text):
        self.global_bank[label].append(text)
        self.firm_bank[label][url].append(text)

    def get_hint(self, label, url):
        firm_hints = self.firm_bank[label].get(url)
        if firm_hints:
            return random.choice(firm_hints)
        global_hints = self.global_bank.get(label)
        if global_hints:
            return random.choice(global_hints)
        return ""


# =============================================================================
# WORKER FUNCTIONS
# =============================================================================


def get_context_window(
    sentences, target_idx, window_size=1, override_target=None, injected_hint=None
):
    start = max(0, target_idx - window_size)
    end = min(len(sentences), target_idx + window_size + 1)
    parts = []
    if injected_hint:
        parts.append(f"[Context: {injected_hint}]")
    for i in range(start, end):
        if i == target_idx and override_target is not None:
            parts.append(override_target)
        else:
            parts.append(sentences[i])
    return " ".join(parts)


def has_conflict(text, label):
    for regex in LABEL_TO_CONFLICT_REGEX.get(label, []):
        if regex.search(text):
            return True
    return False


def process_chunk(chunk_data):
    scorer = ContextScorer()
    augmenter_dummy = AugmentationEngine()

    local_candidates = []
    local_teachers = []

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

            sentences = [
                s.strip()
                for s in SENTENCE_SPLIT_PATTERN.split(para)
                if len(s.strip()) >= MIN_SENTENCE_LENGTH
            ]

            for i, sentence in enumerate(sentences):
                match = STRICT_REGEX.search(sentence)
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
                        validation_text = get_context_window(
                            sentences,
                            i,
                            CONTEXT_WINDOW_SIZE,
                            override_target=blanked_target,
                        )

                        if has_conflict(validation_text, label):
                            score = -1
                        else:
                            score = scorer.score(validation_text, label)

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

                        if score >= 20:
                            aug_text, _ = augmenter_dummy.augment(
                                sentence, match.span(), match.group(0)
                            )
                            teacher_text = get_context_window(
                                sentences,
                                i,
                                CONTEXT_WINDOW_SIZE,
                                override_target=aug_text,
                            )
                            local_teachers.append((label, url, teacher_text))

                    elif len(specific_cats) == 0:
                        full_window = get_context_window(
                            sentences, i, CONTEXT_WINDOW_SIZE
                        )
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

                else:
                    is_hedging_talk = bool(HEDGING_CONTEXT_REGEX.search(sentence))
                    is_accounting = bool(EXCLUDE_REGEX_ACCOUNTING_STD.search(sentence))

                    if is_hedging_talk or is_accounting:
                        cats = get_sentence_categories(sentence)
                        specific_cats = cats - {"gen", "other"}

                        if len(specific_cats) == 0:
                            subtype = (
                                "L0_Accounting" if is_accounting else "L0_Risk_Policy"
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

    return local_candidates, local_teachers


# =============================================================================
# MAIN PROCESS
# =============================================================================


def create_labeled_dataset():
    print(f"🚀 Starting Dataset Generation v11 (Progress Tracking Enabled)")

    conn = sqlite3.connect(DB_PATH)
    # 1. Count total rows for progress bar
    print("📊 Counting total rows in database...")
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM webpage_result WHERE matches IS NOT NULL")
    total_rows = cursor.fetchone()[0]
    print(f"   -> Total Rows: {total_rows:,}")

    df_iter = pd.read_sql_query(
        "SELECT url, matches FROM webpage_result WHERE matches IS NOT NULL",
        conn,
        chunksize=CHUNK_SIZE,
    )

    global_candidates = defaultdict(list)
    context_bank = DynamicContextBank()
    augmenter = AugmentationEngine()

    # --- PHASE 1: PARALLEL SCAN ---
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        future_sizes = {}  # Map future -> number of rows in chunk
        iterator = iter(df_iter)
        active = True

        # Initialize Phase 1 Progress Bar
        with tqdm(total=total_rows, desc="Phase 1: Scanning", unit="rows") as pbar:
            while active or futures:
                # Fill queue
                while len(futures) < MAX_WORKERS * 2 and active:
                    try:
                        chunk = next(iterator)
                        chunk_len = len(chunk)
                        chunk_data = list(zip(chunk["url"], chunk["matches"]))

                        ft = executor.submit(process_chunk, chunk_data)
                        futures.append(ft)
                        future_sizes[ft] = chunk_len
                    except StopIteration:
                        active = False

                if not futures:
                    break

                # Wait for results
                import concurrent.futures

                done, _ = concurrent.futures.wait(
                    futures, return_when=concurrent.futures.FIRST_COMPLETED
                )

                for future in done:
                    futures.remove(future)
                    nrows = future_sizes.pop(future, 0)
                    pbar.update(nrows)  # Update progress bar

                    try:
                        candidates, teachers = future.result()
                        for label, url, text in teachers:
                            context_bank.add_teacher(label, url, text)
                        for c in candidates:
                            global_candidates[c["label"]].append(c)

                        # Update status text with counts
                        counts = {k: len(v) for k, v in global_candidates.items()}
                        pbar.set_postfix(counts)

                        if all(
                            len(global_candidates.get(l, [])) >= SATURATION_LIMIT
                            for l in ["ir", "fx", "cp", "eq", "gen"]
                        ):
                            # pbar.write("🛑 All classes saturated. Stopping scan.")
                            active = False
                            futures = []
                            break
                    except Exception as e:
                        pbar.write(f"Worker error: {e}")
    conn.close()

    # --- PHASE 2: GENERATION ---
    print("\n\n🏆 PASS 2: Generating Dataset...")
    final_data = []
    stats = Counter()

    for label, items in global_candidates.items():
        if label == "gen":
            random.shuffle(items)
        else:
            items.sort(key=lambda x: x["score"], reverse=True)

        # Phase 2 Progress Bar (Per Class)
        limit = min(len(items), TARGET_SAMPLES_PER_CLASS)

        for item in tqdm(
            items, desc=f"  Generating {label:>3}", total=limit, leave=False
        ):
            if stats[label] >= TARGET_SAMPLES_PER_CLASS:
                break

            sentences = item["sentences"]
            idx = item["target_idx"]
            orig_sent = item["original_sent"]
            score = item["score"]
            match_span = item["match_span"]
            match_text = item["match_text"]
            url = item["url"]
            subtype = item.get("subtype", "")

            row = {
                "text": "",
                "label": label,
                "difficulty": "",
                "debug_original": orig_sent,
                "debug_match": match_text,
                "debug_score": score,
                "debug_hint": "None",
            }

            if label == "gen":
                row["text"] = get_context_window(sentences, idx, CONTEXT_WINDOW_SIZE)
                row["difficulty"] = subtype if subtype else "L0_Ambiguous_Instrument"
                stats[f"gen_{row['difficulty']}"] += 1

            elif score == -1:
                row["text"] = get_context_window(sentences, idx, CONTEXT_WINDOW_SIZE)
                row["difficulty"] = "L4_Natural_Adverse"
                stats[f"{label}_L4_Natural"] += 1

            elif score >= 20:
                if random.random() < 0.2:
                    conflict_cat = random.choice(CONFLICT_CATEGORY_MAP[label])
                    fake_hint = context_bank.get_hint(conflict_cat, url)
                    if fake_hint:
                        row["text"] = get_context_window(
                            sentences,
                            idx,
                            CONTEXT_WINDOW_SIZE,
                            override_target=orig_sent,
                            injected_hint=fake_hint,
                        )
                        row["difficulty"] = "L4_Synthetic_Adverse"
                        row["debug_hint"] = f"FAKE({conflict_cat})"
                        stats[f"{label}_L4_Synthetic"] += 1
                    else:
                        aug_text, _ = augmenter.augment(
                            orig_sent, match_span, match_text
                        )
                        row["text"] = get_context_window(
                            sentences,
                            idx,
                            CONTEXT_WINDOW_SIZE,
                            override_target=aug_text,
                        )
                        row["difficulty"] = "L2_Masked"
                        stats[f"{label}_L2_Masked"] += 1
                else:
                    aug_text, _ = augmenter.augment(orig_sent, match_span, match_text)
                    row["text"] = get_context_window(
                        sentences, idx, CONTEXT_WINDOW_SIZE, override_target=aug_text
                    )
                    row["difficulty"] = "L2_Masked"
                    stats[f"{label}_L2_Masked"] += 1

            elif score > 0:
                if random.random() < 0.5:
                    aug_text, _ = augmenter.augment(orig_sent, match_span, match_text)
                    hint = context_bank.get_hint(label, url)
                    if hint:
                        row["text"] = get_context_window(
                            sentences,
                            idx,
                            CONTEXT_WINDOW_SIZE,
                            override_target=aug_text,
                            injected_hint=hint,
                        )
                        row["difficulty"] = "L3_Injected"
                        row["debug_hint"] = hint[:30]
                        stats[f"{label}_L3_Injected"] += 1
                    else:
                        row["text"] = get_context_window(
                            sentences, idx, CONTEXT_WINDOW_SIZE
                        )
                        row["difficulty"] = "L1_WeakContext"
                        stats[f"{label}_L1_WeakContext"] += 1
                else:
                    row["text"] = get_context_window(
                        sentences, idx, CONTEXT_WINDOW_SIZE
                    )
                    row["difficulty"] = "L1_WeakContext"
                    stats[f"{label}_L1_WeakContext"] += 1

            else:
                row["text"] = get_context_window(sentences, idx, CONTEXT_WINDOW_SIZE)
                row["difficulty"] = "L1_NoContext"
                stats[f"{label}_L1_NoContext"] += 1

            final_data.append(row)
            stats[label] += 1

    df = pd.DataFrame(final_data)
    print("\n📊 Final Distribution:")
    print(df["label"].value_counts())
    print("\n", df["difficulty"].value_counts())

    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    mp.freeze_support()
    create_labeled_dataset()
