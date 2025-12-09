from pathlib import Path
import sqlite3
import json
import re
import logging
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from tqdm import tqdm
from typing import List, Optional, Tuple

# --- IMPORTS ---
from derivative_regex import (
    ALL_REGEX,
    BASE_REGEX,
    CATEGORY_CONTEXT_MAP,
    HIGH_PRECISION_SUFFIXES,
    LOOSE_GEN_REGEX,
    SENTENCE_SPLIT_PATTERN,
    # Strict Regexes (The Anchors)
    IR_REGEX,
    FX_REGEX,
    CP_REGEX,
    EQ_REGEX,
    CR_REGEX,
    # Soft Regexes (The Piggybackers)
    IR_SOFT_REGEX,
    FX_SOFT_REGEX,
    CP_SOFT_REGEX,
    EQ_SOFT_REGEX,
    CR_SOFT_REGEX,
    STRICT_CONTEXT_MAP,
    TRADING_VENUE_REGEX,
    NoiseReason,
)
from table_processor import TABLE_ANCHOR
from prefilter_database import find_hedging_context, is_sophisticated_content
from prefiltered_lib import MinimalTextCleaner


# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "tagged_data.db"
TARGET_DB_PATH = "classified_data.db"

# Tag Parsing Regex: Captures _S or _D (Group 1), REASON (Group 2), Text (Group 3)
TAG_PARSER_STRICT = re.compile(r"^\s*(_[SD])<([^>]+)>\s+(.*)", re.DOTALL)
PRIORTY = ["fx", "cp", "eq", "cr", "ir"]

import requests

log = logging.getLogger(__name__)


class NetworkDerivativeResolver:
    """
    Client for RoBERTa-based derivative category resolution.
    Handles batching, context window construction, and fallback logic.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:5000/predict",
        confidence_threshold: float = 0.85,
        context_window_size: int = 2,
        timeout: int = 60,
    ):
        self.api_url = api_url
        self.confidence_threshold = confidence_threshold
        self.context_window_size = context_window_size
        self.timeout = timeout
        self._verify_connection()

    def _verify_connection(self):
        """Verify server is reachable at startup."""
        try:
            response = requests.get(
                self.api_url.replace("/predict", "/info"), timeout=5
            )
            if response.ok:
                info = response.json()
                log.info(f"✅ Connected to RoBERTa server: {info.get('model')}")
            else:
                log.warning(
                    f"⚠️ Server responded but not healthy: {response.status_code}"
                )
        except Exception as e:
            log.error(f"❌ Could not connect to resolver API: {e}")
            raise ConnectionError(f"Resolver API unavailable: {e}")

    def build_context_window(
        self, target_sentence: str, prev_sentences: List[str], next_sentences: List[str]
    ) -> str:
        """Build formatted context window for RoBERTa."""
        prev_context = " ".join(prev_sentences[-self.context_window_size :])
        next_context = " ".join(next_sentences[: self.context_window_size])

        parts = []
        if prev_context:
            parts.append(prev_context)
        parts.append(target_sentence)
        if next_context:
            parts.append(next_context)

        return " [SEP] ".join(parts)

    def resolve_batch(
        self, context_windows: List[str], fallback_labels: Optional[List[str]] = None
    ) -> List[Tuple[str, float]]:
        """Send batch of context windows to server for classification."""
        if not context_windows:
            return []

        if fallback_labels and len(fallback_labels) != len(context_windows):
            raise ValueError("Fallback labels must match context_windows length")

        try:
            response = requests.post(
                self.api_url, json={"texts": context_windows}, timeout=self.timeout
            )
            response.raise_for_status()
            predictions = response.json().get("predictions", [])

            if len(predictions) != len(context_windows):
                log.error(
                    f"Server returned {len(predictions)} predictions for {len(context_windows)} inputs"
                )
                return self._fallback_resolution(context_windows, fallback_labels)

            results = []
            for idx, pred in enumerate(predictions):
                if "error" in pred:
                    log.warning(f"Prediction error at index {idx}: {pred['error']}")
                    fallback = fallback_labels[idx] if fallback_labels else "gen"
                    results.append((fallback, 0.0))
                    continue

                best_label = max(pred, key=pred.get)
                best_score = pred[best_label]

                if best_score >= self.confidence_threshold:
                    results.append((best_label, best_score))
                else:
                    fallback = fallback_labels[idx] if fallback_labels else "gen"
                    results.append((fallback, best_score))

            return results

        except requests.exceptions.Timeout:
            log.error(f"⏱️ API timeout after {self.timeout}s")
            return self._fallback_resolution(context_windows, fallback_labels)
        except requests.exceptions.RequestException as e:
            log.error(f"❌ API request failed: {e}")
            return self._fallback_resolution(context_windows, fallback_labels)
        except Exception as e:
            log.error(f"❌ Unexpected error in resolve_batch: {e}")
            return self._fallback_resolution(context_windows, fallback_labels)

    def _fallback_resolution(
        self, context_windows: List[str], fallback_labels: Optional[List[str]]
    ) -> List[Tuple[str, float]]:
        """Return fallback labels with 0.0 confidence."""
        if fallback_labels:
            return [(label, 0.0) for label in fallback_labels]
        return [("gen", 0.0) for _ in context_windows]

    def resolve_single(
        self,
        target_sentence: str,
        prev_sentences: List[str] = [],
        next_sentences: List[str] = [],
        fallback_label: str = "gen",
    ) -> Tuple[str, float]:
        """Convenience method for single sentence resolution."""
        context_window = self.build_context_window(
            target_sentence, prev_sentences or [], next_sentences or []
        )
        results = self.resolve_batch([context_window], fallback_labels=[fallback_label])
        return results[0] if results else (fallback_label, 0.0)


def initialize_resolver(api_url: str = "http://localhost:5000/predict"):
    """Initialize the RoBERTa resolver – called once at program start."""
    global RESOLVER
    try:
        RESOLVER = NetworkDerivativeResolver(
            api_url=api_url,
            confidence_threshold=0.85,
            context_window_size=3,
            timeout=60,
        )
        print("🧠 ML Resolver Initialized")
    except Exception as e:
        print(
            f"⚠️ ML resolver unavailable ({e}) – will fall back to regex-only resolution"
        )
        RESOLVER = None


RESOLVER: Optional[NetworkDerivativeResolver] = None


class GlobalInstrumentTracker:
    """Tracks instrument → category mappings for resolving generic references."""

    def __init__(self):
        self.instrument_map = defaultdict(set)
        self.embedded_regex = re.compile(r"\bembedded\b", re.IGNORECASE)

    def register_paragraph(self, paragraph: str, category: str):
        """Register instruments found in paragraph to category."""
        if self.embedded_regex.search(paragraph):
            self.instrument_map["embedded"].add(category)

        # Specific matches (high confidence)
        specific_matches = [m.group(0) for m in ALL_REGEX.finditer(paragraph)]

        if specific_matches:
            for instr in specific_matches:
                match = BASE_REGEX.search(instr)
                if match:
                    token = match.group(0).lower().rstrip("s")
                    if token.startswith("hedg"):  # ignore hedge, it is too generic
                        continue
                    self.instrument_map[token].add(category)
        else:
            # Fallback: implicit context
            base_matches = BASE_REGEX.findall(paragraph)
            for instr in base_matches:
                instr = instr.lower()
                if instr.startswith("hedg"): #ignore hedge, it is too generic
                    continue
                if not instr.endswith("s") and instr != "swap":
                    continue
                token = instr.rstrip("s")
                self.instrument_map[token].add(category)

    def resolve_instrument(self, sentence: str) -> Optional[str]:
        """Returns category if sentence contains unambiguous global instrument."""
        matches = BASE_REGEX.findall(sentence)
        if self.embedded_regex.search(sentence):
            matches.append("embedded")

        candidates = set()
        for m in matches:
            token = m.lower().rstrip("s")
            if token in self.instrument_map:
                candidates.update(self.instrument_map[token])

        if len(candidates) == 1:
            return list(candidates)[0]
        return None


def get_sentence_categories(
    sentence: str, context_sentences: Optional[List[str]] = None
) -> set:
    """
    Determines category using multi-phase approach:
    1. Strict Context Bypass (highest confidence)
    2. Direct Instrument Detection
    3. Priority Consumption (soft context)
    4. Context Window (tie-breaker)
    """
    if context_sentences is None:
        context_sentences = []

    full_text = (
        sentence + " " + " ".join(context_sentences) if context_sentences else sentence
    )
    scores = {"ir": 0, "fx": 0, "cp": 0, "eq": 0, "cr": 0, "warr": 0, "gen": 0}

    # PHASE 0: Strict Context Bypass
    strict_hits = set()
    for cat, regex in STRICT_CONTEXT_MAP.items():
        if regex.search(sentence):
            strict_hits.add(cat)

    if strict_hits:
        if "fx" in strict_hits:
            scores["fx"] += 2000
        elif "eq" in strict_hits:
            scores["eq"] += 2000
            if is_sophisticated_content(sentence):
                scores["warr"] += 5000 # Bypasses eq
        elif "cp" in strict_hits:
            scores["cp"] += 2000
        elif "cr" in strict_hits:
            scores["cr"] += 2000
        elif "ir" in strict_hits:
            scores["ir"] += 2000

    # PHASE 1: Direct Instrument Detection
    for cat, regex in [
        ("fx", FX_REGEX),
        ("cp", CP_REGEX),
        ("eq", EQ_REGEX),
        ("cr", CR_REGEX),
        ("ir", IR_REGEX),
    ]:
        matches = regex.findall(sentence)
        for match in matches:
            if is_sophisticated_content(sentence) and cat == "eq":
                scores["warr"] = max(scores[cat], 5000)
            if HIGH_PRECISION_SUFFIXES.search(match):
                scores[cat] = max(scores[cat], 1000)
            else:
                scores[cat] = max(scores[cat], 100)

    # PHASE 2: Priority Consumption (Soft Context)
    if LOOSE_GEN_REGEX.search(sentence) or max(scores.values()) < 1000:
        scores["gen"] = max(scores["gen"], 50)
        priority_order = PRIORTY
        remaining_text = sentence

        for cat in priority_order:
            ctx_regex = CATEGORY_CONTEXT_MAP.get(cat)
            if ctx_regex:
                matches = list(ctx_regex.finditer(remaining_text))
                if matches:
                    scores[cat] += 50 * len(matches)
                    remaining_text = ctx_regex.sub(" ", remaining_text)

    # PHASE 3: Context Window (Tie-Breaker)
    if context_sentences and max(scores.values()) < 1000:
        for cat in PRIORTY:
            context_regex = CATEGORY_CONTEXT_MAP.get(cat)
            if context_regex and context_regex.search(full_text):
                scores[cat] += 10

    # Winner Determination
    active_scores = {cat: score for cat, score in scores.items() if score > 0}
    if not active_scores:
        return {"other"}

    max_score = max(active_scores.values())
    threshold = 50
    if max_score >= 2000:
        threshold = 1000
    if max_score >= 1000:
        threshold = 500

    top_cats = {cat for cat, score in active_scores.items() if score >= threshold}
    specific = top_cats - {"gen"}

    return specific if specific else top_cats


_cleaner = MinimalTextCleaner()


def remove_outlier_categories(
    evidence_map, promoted_cats, threshold_pct=0.10, min_mentions=3
):
    """
    Remove categories with stray mentions (outliers).

    A category is removed if EITHER:
    1. Has < min_mentions (absolute floor)
    2. Has < threshold_pct * max_mentions (relative to largest category)

    Args:
        evidence_map: dict of category -> [sentences]
        promoted_cats: set of categories just added via soft promotion
        threshold_pct: what % of max to use as threshold (default 0.10 = 10%)
        min_mentions: minimum absolute mentions to keep (default 3)

    Returns:
        dict of removed categories with reasoning
    """

    # Count mentions per category
    cat_counts = {cat: len(sents) for cat, sents in evidence_map.items() if sents}

    if not cat_counts:
        return {}  # No evidence to check

    # Get the highest mention count
    max_count = max(cat_counts.values())

    # Calculate threshold: use whichever is higher (absolute or relative)
    threshold = max(min_mentions, max_count * threshold_pct)

    # Find outliers ONLY among newly promoted categories
    # Don't remove hard evidence that was already there
    removed = {}

    for cat in promoted_cats:
        if cat not in cat_counts:
            continue  # No mentions (shouldn't happen)

        count = cat_counts[cat]

        if count < threshold:
            # This is an outlier
            removed[cat] = {
                "count": count,
                "threshold": threshold,
                "max_count": max_count,
                "reason": f"Stray mention ({count} < {threshold:.1f})",
            }
            del evidence_map[cat]

    return removed

def _process_paragraphs_and_sentences(paragraphs, attributes, doc_tracker):
    """
    PASS 0: Iterate through paragraphs and sentences.
    - Parse paragraph-level (_D) and sentence-level (_S) tags.
    - Extract attributes from tags (is_hedger, uses_hedge_accounting, etc.).
    - Generate initial strict and soft category matches.
    - Register to GlobalInstrumentTracker and collect initial evidence.

    Returns: evidence_map, potential_map, context_buffer
    """
    evidence_map = defaultdict(list)
    potential_map = defaultdict(list)
    context_buffer = []

    for p in paragraphs:
        original_p = p # Keep the original paragraph for context
        is_paragraph_deadweight = False

        # VENUE CHECK: Run on original text
        if TRADING_VENUE_REGEX.search(p):
            attributes["mentions_venue"] = True

        # --- A. Check for Paragraph-Level Tag (_D) ---
        para_match = TAG_PARSER_STRICT.match(p)
        if para_match:
            tag_type = para_match.group(1)
            tag_reason = para_match.group(2)
            content = para_match.group(3)

            if tag_type == "_D":
                is_paragraph_deadweight = True
                # Mine attributes from deadweight tag (TRADING, POLICY, HIST)
                if tag_reason == NoiseReason.TRADING.value: attributes["is_hedger"] = True
                elif tag_reason == NoiseReason.POLICY.value: attributes["uses_hedge_accounting"] = True
                elif tag_reason == NoiseReason.PNL.value: attributes["has_pnl_activity"] = True
                elif tag_reason in {NoiseReason.HIST_BLOCK.value, NoiseReason.TERM.value}: attributes["is_historical"] = True
                p = content # UNWRAP: Process the content

        # --- B. Sentence Processing ---
        sentences_original = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(p) if s.strip()]

        for original_s in sentences_original:
            clean_s = original_s
            is_sentence_deadweight = is_paragraph_deadweight # Inherit paragraph deadweight

            # --- 1. Parse Sentence-Level Tags ---
            sent_match = TAG_PARSER_STRICT.match(original_s)
            if sent_match:
                tag_type = sent_match.group(1)
                tag_reason = sent_match.group(2)
                clean_s = sent_match.group(3)

                if tag_type == "_S":
                    is_sentence_deadweight = True
                    # Mine attributes from sentence tag (TRADING, POLICY, PNL, CREDIT, TIME)
                    if tag_reason == NoiseReason.TRADING.value: attributes["is_hedger"] = True
                    elif tag_reason == NoiseReason.POLICY.value: attributes["uses_hedge_accounting"] = True
                    elif tag_reason == NoiseReason.PNL.value: attributes["has_pnl_activity"] = True
                    elif tag_reason == NoiseReason.CREDIT.value: attributes["manages_credit_risk"] = True
                    elif tag_reason in {NoiseReason.TIME.value, NoiseReason.TERM.value}: attributes["is_historical"] = True

            # --- 2. Clean text for tracking (remove entities) ---
            clean_s = _cleaner.clean_entities(clean_s)

            # --- 3. Update context buffer (use clean) ---
            context_buffer.append(clean_s)
            if len(context_buffer) > 5:
                context_buffer.pop(0)

            # --- 4. Register to Global Tracker (use clean) ---
            strict_cats = set()
            if IR_REGEX.search(clean_s): strict_cats.add("ir")
            if FX_REGEX.search(clean_s): strict_cats.add("fx")
            if CP_REGEX.search(clean_s): strict_cats.add("cp")
            if CR_REGEX.search(clean_s): strict_cats.add("cr")
            if EQ_REGEX.search(clean_s):
                if is_sophisticated_content(clean_s): strict_cats.add("warr")
                else: strict_cats.add("eq")

            for cat in strict_cats:
                doc_tracker.register_paragraph(clean_s, cat)

            # --- 5. Collect Evidence (only if NOT deadweight) ---
            if is_paragraph_deadweight or is_sentence_deadweight:
                continue

            # A. Strict Matches
            if strict_cats:
                attributes["is_hedging_sophisticated"] = True
                if "warr" in strict_cats:
                    attributes["is_financing_sophisticated"] = True
                for cat in strict_cats:
                    evidence_map[cat].append(original_s)

            # B. Soft Matches
            else:
                soft_cats = set()
                if IR_SOFT_REGEX.search(clean_s): soft_cats.add("ir")
                if FX_SOFT_REGEX.search(clean_s): soft_cats.add("fx")
                if CP_SOFT_REGEX.search(clean_s) and find_hedging_context(clean_s): soft_cats.add("cp")
                if CR_SOFT_REGEX.search(clean_s): soft_cats.add("cr")
                if EQ_SOFT_REGEX.search(clean_s):
                    if is_sophisticated_content(clean_s): soft_cats.add("warr")
                    else: soft_cats.add("eq")

                if soft_cats:
                    for cat in soft_cats:
                        potential_map[cat].append(original_s)

                # C. Generic Resolution
                else:
                    cats = get_sentence_categories(clean_s)
                    if "gen" in cats:
                        potential_map["_generic"].append({
                            "original": original_s,
                            "clean": clean_s,
                            "categories": cats,
                            "sentence_index": len(context_buffer) - 1,
                        })

    return evidence_map, potential_map, context_buffer

def _resolve_generic_passes(paragraphs, evidence_map, potential_map, attributes, doc_tracker):
    """
    Execute three passes for resolving generic (unclassified) sentences:
    1. Global Instrument Tracker Resolution (using doc_tracker).
    2. Sequential Inheritance (from nearest non-table predecessor).
    3. Document-Level Category Inheritance (if only one category found).

    Updates evidence_map and attributes in place.
    """
    if "_generic" not in potential_map:
        return

    generic_sentences_to_resolve = potential_map.pop("_generic")
    unresolved_generics = []

    # --- PASS 1: Global Instrument Tracker Resolution ---
    for gen_item in generic_sentences_to_resolve:
        resolved = doc_tracker.resolve_instrument(gen_item["clean"])

        if resolved and resolved not in {"gen", "other"}:
            # Upgrade EQ to WARR if sophisticated
            if resolved == "eq" and is_sophisticated_content(gen_item["clean"]):
                resolved = "warr"
                attributes["is_financing_sophisticated"] = True
            else:
                attributes["is_hedging_sophisticated"] = True
            evidence_map[resolved].append(gen_item["original"])
        else:
            unresolved_generics.append(gen_item)

    # --- PASS 2: Sequential Inheritance ---
    sentence_list = []
    for p in paragraphs:
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(p) if s.strip()]
        for s in sentences:
            is_table = TABLE_ANCHOR in s or "<TABLE>" in s.upper()
            sentence_list.append({"text": s, "from_table": is_table})

    resolved_in_pass2 = []
    generic_originals = {g["original"] for g in unresolved_generics}

    for i in range(1, len(sentence_list)):
        curr = sentence_list[i]
        # Only process sentences that were generic AND unresolved in Pass 1 AND not from tables
        if not curr["from_table"] and curr["text"] in generic_originals:
            prev_cat = None
            # Find nearest non-table predecessor with evidence
            for j in range(i - 1, -1, -1):
                if not sentence_list[j]["from_table"]:
                    for cat, sentences in evidence_map.items():
                        if sentence_list[j]["text"] in sentences:
                            prev_cat = cat
                            break
                    if prev_cat:
                        break

            # If we found a specific predecessor category, inherit
            if prev_cat and prev_cat not in {"gen", "other"}:
                evidence_map[prev_cat].append(curr["text"])
                resolved_in_pass2.append(curr["text"])

    # Update unresolved_generics list for Pass 3
    remaining_generics = [
        g for g in unresolved_generics if g["original"] not in resolved_in_pass2
    ]

    # --- PASS 3: Document-Level Category Inheritance ---
    all_cats_in_evidence = {
        cat
        for cat, sents in evidence_map.items()
        if sents and cat not in {"gen", "other"}
    }

    if len(all_cats_in_evidence) == 1:
        single_cat = list(all_cats_in_evidence)[0]
        # Assign remaining generics to the single-category
        for gen_item in remaining_generics:
            evidence_map[single_cat].append(gen_item["original"])
            attributes["is_hedging_sophisticated"] = True

    # If any generics remain, put them back for potential further processing (or logging)
    if remaining_generics:
        potential_map["_generic"] = remaining_generics


def _promotion_and_cleanup(evidence_map, potential_map, attributes):
    """
    Execute the final promotion of soft matches to evidence, removal of outliers,
    and determination of the final is_trader attribute.

    Returns: removed_outliers (set)
    """
    removed_outliers = set()

    # --- 1. PROMOTION PASS ---
    is_valid_user = (
        attributes["is_hedging_sophisticated"]
        or attributes["uses_hedge_accounting"]
        or attributes["is_financing_sophisticated"]
    )

    if is_valid_user:
        promoted_cats = set()

        # First: Promote soft matches to evidence
        for cat, sentences in potential_map.items():
            if cat not in evidence_map and cat != "_generic":
                evidence_map[cat].extend(sentences)
                promoted_cats.add(cat)

        # Second: Remove outliers among promoted categories
        removed_outliers = remove_outlier_categories(
            evidence_map, promoted_cats, threshold_pct=0.10, min_mentions=2
        )

    # --- 2. TRADER LOGIC ---
    if attributes.get("mentions_venue") and not attributes["is_hedger"]:
        attributes["is_trader"] = True
    else:
        attributes["is_trader"] = False

    # Clean up internal flags
    attributes.pop("mentions_venue", None)

    return removed_outliers


def _compute_final_categories(evidence_map: dict) -> List[str]:
    """
    Final authoritative category list.
    If a key exists in evidence_map and has ≥1 sentence → it's real.
    'eq' and 'warr' coexist happily.
    'gen' only if that's literally all we have.
    """
    cats = set()

    for cat, sentences in evidence_map.items():
        if sentences:  # non-empty list
            if cat not in {"other", "_generic"}:
                cats.add(cat)

    # If absolutely nothing specific → check if we at least had generic hedging
    if not cats and evidence_map.get("gen"):
        cats.add("gen")

    return sorted(list(cats))


def process_row(row):
    """
    Orchestrates the multi-pass classification process for a single company document.
    """
    url, matches_json, cik, year = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    # Initialize state
    attributes = {
        "is_hedger": False,
        "uses_hedge_accounting": False,
        "has_pnl_activity": False,
        "manages_credit_risk": False,
        "is_hedging_sophisticated": False,
        "is_financing_sophisticated": False,
        "is_historical": False,
    }
    doc_tracker = GlobalInstrumentTracker()

    # --- STEP 1: Initial Processing (Pass 0) ---
    evidence_map, potential_map, context_buffer = _process_paragraphs_and_sentences(
        paragraphs, attributes, doc_tracker
    )

    # --- STEP 2: Generic Resolution Passes (Passes 1, 2, 3) ---
    _resolve_generic_passes(
        paragraphs, evidence_map, potential_map, attributes, doc_tracker
    )

    # --- STEP 3: Promotion and Cleanup ---
    removed_outliers = _promotion_and_cleanup(evidence_map, potential_map, attributes)

    # --- STEP 4: Final Output ---
    # Check if anything was found (attributes or evidence)
    if not evidence_map and not any(attributes.values()):
        return (url, "{}", cik, year, removed_outliers)
    final_categories = _compute_final_categories(evidence_map)
    output_data = {
        "evidence": evidence_map,
        "attributes": attributes,
        "categories": final_categories,
    }

    # Return with outlier log
    return (url, json.dumps(output_data), cik, year, removed_outliers)


# =============================================================================
# INFRASTRUCTURE
# =============================================================================


def setup_target_db(path):
    """Create target database with logging table for outlier removals."""
    conn = sqlite3.connect(path)
    c = conn.cursor()

    # Existing tables
    c.execute(
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, matches TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES webpage_result(url))"
    )
    
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS category (
            url TEXT PRIMARY KEY,
            categories TEXT NOT NULL,  -- JSON array of category labels ['ir', 'fx', 'gen', ...]
            FOREIGN KEY (url) REFERENCES webpage_result(url)
        )
        """
    )
    # NEW: Outlier removal log
    c.execute(
        """CREATE TABLE IF NOT EXISTS outlier_removals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            category TEXT NOT NULL,
            mention_count INTEGER NOT NULL,
            threshold REAL NOT NULL,
            max_count INTEGER NOT NULL,
            reason TEXT,
            FOREIGN KEY (url) REFERENCES webpage_result(url)
        )"""
    )

    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
    c.execute("CREATE INDEX IF NOT EXISTS outlier_url_idx ON outlier_removals (url)")
    c.execute(
        "CREATE INDEX IF NOT EXISTS outlier_cat_idx ON outlier_removals (category)"
    )

    c.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    conn.close()


def get_processed_urls(path):
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
    conn = sqlite3.connect(source_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT w.url, w.matches, r.cik, r.year FROM webpage_result w LEFT JOIN report_data r ON w.url = r.url WHERE w.matches IS NOT NULL"
    )
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            if row[0] not in processed_urls:
                yield row
    conn.close()


def write_batch(conn, buffer):
    """Write classification results, report data, categories, and outlier logs."""
    if not buffer:
        return

    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")

        # 1. Main classification results
        webpage_data = [(r[0], r[1]) for r in buffer]  # url, json_string
        report_data = [(r[0], r[2], r[3]) for r in buffer]  # url, cik, year

        c.executemany(
            "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
            webpage_data,
        )
        c.executemany(
            "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            report_data,
        )

        # 2. Extract and save final categories
        category_data = []
        for r in buffer:
            url = r[0]
            json_str = r[1]
            try:
                data = json.loads(json_str)
                cats = data.get("categories", [])
                if cats:  # only insert if not empty
                    category_data.append((url, json.dumps(cats)))
            except json.JSONDecodeError:
                continue  # skip malformed

        if category_data:
            c.executemany(
                "INSERT OR REPLACE INTO category (url, categories) VALUES (?, ?)",
                category_data,
            )

        # 3. Outlier logs (unchanged)
        outlier_logs = []
        for r in buffer:
            url = r[0]
            removed_outliers = r[4]  # dict from _promotion_and_cleanup
            for cat, details in removed_outliers.items():
                outlier_logs.append(
                    (
                        url,
                        cat,
                        details.get("count", 0),
                        details.get("threshold", 0),
                        details.get("max_count", 0),
                        details.get("reason", "outlier"),
                    )
                )

        if outlier_logs:
            c.executemany(
                """INSERT INTO outlier_removals 
                   (url, category, mention_count, threshold, max_count, reason)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                outlier_logs,
            )

        conn.commit()

    except Exception as e:
        print(f"Write Error: {e}")
        conn.rollback()


if __name__ == "__main__":
    try:
        initialize_resolver()
    except:
        print("⚠️ ML Server skipped (Regex Only Mode)")

    print(f"🚀 Starting Final Classifier ({NUM_WORKERS} workers)")
    setup_target_db(TARGET_DB_PATH)
    processed = get_processed_urls(TARGET_DB_PATH)

    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")

    buffer = []
    total_removed = 0

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        source = list(data_generator(SOURCE_DB_PATH, processed))
        for result in tqdm(
            executor.map(process_row, source, chunksize=10), total=len(source)
        ):
            if result:
                buffer.append(result)
                # Track removals for summary
                if result[4]:  # removed_outliers dict
                    total_removed += len(result[4])

                if len(buffer) >= BATCH_SIZE:
                    write_batch(conn, buffer)
                    buffer = []

    if buffer:
        write_batch(conn, buffer)

    conn.close()

    print("✅ Classification Complete.")
    print(f"   Total outlier categories removed: {total_removed}")
