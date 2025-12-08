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


# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "tagged_data.db"
TARGET_DB_PATH = "classified_data.db"

# Tag Parsing Regex: Captures _S<REASON> (Group 1) and Text (Group 2)
TAG_PARSER = re.compile(r" _[SD]<([^>]+)> (.*)")
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
        timeout: int = 60
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
                self.api_url.replace("/predict", "/info"),
                timeout=5
            )
            if response.ok:
                info = response.json()
                log.info(f"✅ Connected to RoBERTa server: {info.get('model')}")
                log.info(f" Device: {info.get('device')}, Labels: {info.get('labels')}")
            else:
                log.warning(f"⚠️ Server responded but not healthy: {response.status_code}")
        except Exception as e:
            log.error(f"❌ Could not connect to resolver API: {e}")
            log.error(f" Server must be running at {self.api_url}")
            raise ConnectionError(f"Resolver API unavailable: {e}")

    def build_context_window(
        self,
        target_sentence: str,
        prev_sentences: List[str],
        next_sentences: List[str]
    ) -> str:
        """
        Build formatted context window for RoBERTa.
        Format: "prev_context [SEP] target_sentence [SEP] next_context"
       
        Args:
            target_sentence: The generic sentence to classify
            prev_sentences: Previous sentences (most recent first)
            next_sentences: Following sentences
       
        Returns:
            Formatted string ready for tokenizer
        """
        # Take last N previous sentences (most recent context)
        prev_context = " ".join(prev_sentences[-self.context_window_size:])

        # Take first N next sentences
        next_context = " ".join(next_sentences[:self.context_window_size])

        # Format with [SEP] tokens (RoBERTa tokenizer handles these)
        parts = []
        if prev_context:
            parts.append(prev_context)
        parts.append(target_sentence)
        if next_context:
            parts.append(next_context)

        return " [SEP] ".join(parts)

    def resolve_batch(
        self,
        context_windows: List[str],
        fallback_labels: Optional[List[str]] = None
    ) -> List[Tuple[str, float]]:
        """
        Send batch of context windows to server for classification.
       
        Args:
            context_windows: List of formatted context strings
            fallback_labels: Optional list of fallback labels if API fails
       
        Returns:
            List of (label, confidence_score) tuples
        """
        if not context_windows:
            return []

        if fallback_labels and len(fallback_labels) != len(context_windows):
            raise ValueError("Fallback labels must match context_windows length")

        try:
            response = requests.post(
                self.api_url,
                json={"texts": context_windows},
                timeout=self.timeout
            )
            response.raise_for_status()

            predictions = response.json().get("predictions", [])

            if len(predictions) != len(context_windows):
                log.error(f"Server returned {len(predictions)} predictions for {len(context_windows)} inputs")
                return self._fallback_resolution(context_windows, fallback_labels)

            results = []
            for idx, pred in enumerate(predictions):
                if "error" in pred:
                    log.warning(f"Prediction error at index {idx}: {pred['error']}")
                    fallback = fallback_labels[idx] if fallback_labels else "gen"
                    results.append((fallback, 0.0))
                    continue

                # pred format: {'ir': 0.95, 'fx': 0.03, 'cp': 0.01, 'eq': 0.01, 'gen': 0.00}
                best_label = max(pred, key=pred.get)
                best_score = pred[best_label]

                # Apply confidence thresholding
                if best_score >= self.confidence_threshold:
                    results.append((best_label, best_score))
                else:
                    # Low confidence → use fallback or 'gen'
                    fallback = fallback_labels[idx] if fallback_labels else "gen"
                    results.append((fallback, best_score))
                    log.debug(f"Low confidence ({best_score:.3f}) → fallback to '{fallback}'")

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
        self,
        context_windows: List[str],
        fallback_labels: Optional[List[str]]
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
        fallback_label: str = "gen"
    ) -> Tuple[str, float]:
        """
        Convenience method for single sentence resolution.
        """
        context_window = self.build_context_window(
            target_sentence,
            prev_sentences or [],
            next_sentences or []
        )

        results = self.resolve_batch(
            [context_window],
            fallback_labels=[fallback_label]
        )

        return results[0] if results else (fallback_label, 0.0)


def resolve_generic_with_ml(
    target_sentence: str, context_window: List[str], prev_valid_cat: Optional[str]
) -> Optional[str]:
    global RESOLVER
    """
    Optional: Attempts to resolve a generic sentence using RoBERTa.
    Only runs if RESOLVER is initialized.
    """
    if not RESOLVER:
        return None

    # Build window: Last 3 sentences (even if they were noise/skipped)
    # to give RoBERTa the full linguistic flow.
    label, conf = RESOLVER.resolve_single(
        target_sentence,
        prev_sentences=context_window[-3:],
        next_sentences=[],  # Sequential processing only
    )

    if conf > 0.85 and label != "gen":
        return label

    return None


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
        print("ML resolver initialized successfully")
    except Exception as e:
        print(
            f"ML resolver unavailable ({e}) – will fall back to regex-only resolution"
        )
        RESOLVER = None

# Global resolver instance (initialized once at startup)
RESOLVER: Optional[NetworkDerivativeResolver] = None

class GlobalInstrumentTracker:
    def __init__(self):
        self.instrument_map = defaultdict(set)
        self.embedded_regex = re.compile(r"\bembedded\b", re.IGNORECASE)

    def register_paragraph(self, paragraph: str, category: str):
        """
        Registers high-confidence instruments to build the global map.
        """
        # 0. Highly specfic: embedded features. If the word embedded appears
        # in that same sentence as the paragraph, we should register it for easier lookup
        if self.embedded_regex.search(paragraph):
            self.instrument_map["embedded"].add(category)

        # 1. Try to find Specific Instruments first (High Confidence)
        # Use finditer to avoid tuple issues with capturing groups
        specific_matches = [m.group(0) for m in ALL_REGEX.finditer(paragraph)]

        if specific_matches:
            for instr in specific_matches:
                # Search for the base term INSIDE the specific string
                match = BASE_REGEX.search(instr)
                if match:
                    token = match.group(0).lower().rstrip("s")
                    self.instrument_map[token].add(category)
        else:
            # 2. Fallback: Implicit/Soft Context (Medium Confidence)
            base_matches = BASE_REGEX.findall(paragraph)
            for instr in base_matches:
                instr = instr.lower()
                # Safety: Enforce plurality for common words (e.g. "futures", "options")
                # but allow "swap" as it is rarely a non-financial verb here.
                if not instr.endswith("s") and instr != "swap":
                    continue

                token = instr.rstrip("s")
                self.instrument_map[token].add(category)

    def resolve_instrument(self, sentence: str):
        """
        Returns a category if the sentence contains an unambiguous global instrument.
        """
        # Find potential instruments in the generic sentence
        matches = BASE_REGEX.findall(sentence)
        # If the sentence contains the word "embedded", add it
        if self.embedded_regex.search(sentence):
            matches.append("embedded")
        candidates = set()
        for m in matches:
            token = m.lower().rstrip("s")
            if token in self.instrument_map:
                candidates.update(self.instrument_map[token])

        # Decision Logic
        if len(candidates) == 1:
            return list(candidates)[0]  # Unambiguous (e.g., "Swap" -> IR)

        return None  # Collision or Unknown -> Fallback to neighbor logic


def get_sentence_categories(
    sentence: str, context_sentences: Optional[List[str]] = None
) -> set:
    """
    Determines category using:
    1. Strict Context (The Bypass) -> FX > CP > EQ > CR > IR
    2. Instrument Detection
    3. Priority Consumption
    4. Soft Context Tie-Breaking
    """
    if context_sentences is None:
        context_sentences = []

    full_text = (
        sentence + " " + " ".join(context_sentences) if context_sentences else sentence
    )
    scores = {"ir": 0, "fx": 0, "cp": 0, "eq": 0, "cr": 0, "gen": 0}

    # ═══════════════════════════════════════════════════════════
    # PHASE 0: STRICT CONTEXT BYPASS (New)
    # ═══════════════════════════════════════════════════════════
    # If we find "Convertible Debt" or "Currency Risk", we know the category.
    # We assign a massive score to skip ML.

    # Check current sentence ONLY for strict context (context window is too noisy for strictness)
    strict_hits = set()
    for cat, regex in STRICT_CONTEXT_MAP.items():
        if regex.search(sentence):
            strict_hits.add(cat)

    if strict_hits:
        # COLLISION LOGIC: Define the Hierarchy
        # 1. FX overrides CP/IR (e.g. "Currency risk of corn")
        # 2. EQ overrides IR (e.g. "Convertible debt" - debt is IR, but feature is EQ)

        if "fx" in strict_hits:
            scores["fx"] += 2000
        elif "eq" in strict_hits:
            scores["eq"] += 2000
        elif "cp" in strict_hits:
            scores["cp"] += 2000
        elif "cr" in strict_hits:
            scores["cr"] += 2000
        elif "ir" in strict_hits:
            scores["ir"] += 2000

        # If we found a strict context, we can often stop here for classification purposes,
        # BUT we still run instrument detection to capture specific headers/suffixes.

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: DIRECT INSTRUMENT DETECTION
    # ═══════════════════════════════════════════════════════════
    for cat, regex in [
        ("fx", FX_REGEX),
        ("cp", CP_REGEX),
        ("eq", EQ_REGEX),
        ("cr", CR_REGEX),
        ("ir", IR_REGEX),
    ]:
        matches = regex.findall(sentence)
        for match in matches:
            if HIGH_PRECISION_SUFFIXES.search(match):
                scores[cat] = max(scores[cat], 1000)
            else:
                scores[cat] = max(scores[cat], 100)

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: PRIORITY CONSUMPTION (For Soft Context)
    # ═══════════════════════════════════════════════════════════
    # Only run if we have generic instrument OR no strong signals yet
    if LOOSE_GEN_REGEX.search(sentence) or max(scores.values()) < 1000:
        scores["gen"] = max(scores["gen"], 50)

        # Priority: FX -> EQ -> CP -> CR -> IR
        # This removes "Currency" before IR sees "Rate", etc.
        priority_order = PRIORTY
        remaining_text = sentence

        for cat in priority_order:
            ctx_regex = CATEGORY_CONTEXT_MAP.get(cat)  # Soft Regex
            if ctx_regex:
                matches = list(ctx_regex.finditer(remaining_text))
                if matches:
                    scores[cat] += 50 * len(matches)
                    remaining_text = ctx_regex.sub(" ", remaining_text)

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: CONTEXT WINDOW (Tie-Breaker)
    # ═══════════════════════════════════════════════════════════
    if context_sentences and max(scores.values()) < 1000:
        for cat in PRIORTY:
            context_regex = CATEGORY_CONTEXT_MAP.get(cat)
            if context_regex and context_regex.search(full_text):
                scores[cat] += 10  # Low weight

    # ═══════════════════════════════════════════════════════════
    # WINNER DETERMINATION
    # ═══════════════════════════════════════════════════════════
    active_scores = {cat: score for cat, score in scores.items() if score > 0}
    if not active_scores:
        return {"other"}

    max_score = max(active_scores.values())

    # If Strict Context (2000) or Strict Instrument (1000) found,
    # filter out the noise.
    threshold = 50
    if max_score >= 1000:
        threshold = 500  # Kill soft context noise

    top_cats = {cat for cat, score in active_scores.items() if score >= threshold}
    specific = top_cats - {"gen"}

    return specific if specific else top_cats


def process_row(row):
    url, matches_json, cik, year = row
    try:
        paragraphs = json.loads(matches_json)
    except:
        return None

    # --- OUTPUT STRUCTURES ---
    # Evidence: Confirmed sentences proving active use
    evidence_map = defaultdict(list)
    # Potential: Soft matches waiting for sophistication confirmation
    potential_map = defaultdict(list)

    attributes = {
        "is_hedger": False,  # Found _S<TRADING>
        "uses_hedge_accounting": False,  # Found _S<POLICY>
        "has_pnl_activity": False,  # Found _S<PNL>
        "manages_credit_risk": False,  # Found _S<CREDIT>
        "is_sophisticated": False,  # Found STRICT match
        "mentions_venue": False, # temp flag for commodity traders
    }

    doc_tracker = GlobalInstrumentTracker()
    context_buffer = []

    # 1. SCANNING PASS
    for p in paragraphs:
        # --- A. Paragraph Level Tags (_D) ---
        para_match = TAG_PARSER.match(p)
        if para_match:
            tag_str = para_match.group(1)
            content = para_match.group(2)

            # Mining Attributes from Deadweight
            if tag_str == NoiseReason.TRADING.value:
                attributes["is_hedger"] = True
            elif tag_str == NoiseReason.POLICY.value:
                attributes["uses_hedge_accounting"] = True

            # Add stripped content to context buffer for flow
            for s in SENTENCE_SPLIT_PATTERN.split(content):
                context_buffer.append(s)
                if len(context_buffer) > 5:
                    context_buffer.pop(0)
            continue

        # --- B. Sentence Level Processing ---
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(p) if s.strip()]

        for s in sentences:
            if TRADING_VENUE_REGEX.search(s):
                attributes["mentions_venue"] = True
            # Check Sentence Tags (_S)
            tag_match = TAG_PARSER.match(s)

            if tag_match:
                tag_str = tag_match.group(1)
                clean_text = tag_match.group(2)

                # Attribute Mining
                if tag_str == NoiseReason.TRADING.value:
                    attributes["is_hedger"] = True
                elif tag_str == NoiseReason.POLICY.value:
                    attributes["uses_hedge_accounting"] = True
                elif tag_str == NoiseReason.PNL.value:
                    attributes["has_pnl_activity"] = True
                elif tag_str == NoiseReason.CREDIT.value:
                    attributes["manages_credit_risk"] = True

                elif tag_str == NoiseReason.DEF.value:
                    # Definitions help the Tracker know "Swaps" = IR
                    cats = get_sentence_categories(clean_text)
                    specific = cats - {"gen", "other"}
                    if specific:
                        doc_tracker.register_paragraph(clean_text, list(specific)[0])

                # Add to context
                context_buffer.append(clean_text)
                if len(context_buffer) > 5:
                    context_buffer.pop(0)
                continue

            # --- C. CLASSIFICATION (Clean Sentences) ---
            # This sentence survived all filters. It is a candidate.

            context_buffer.append(s)
            if len(context_buffer) > 5:
                context_buffer.pop(0)

            # 1. Check STRICT Matches (Anchors)
            strict_cats = set()
            if IR_REGEX.search(s):
                strict_cats.add("ir")
            if FX_REGEX.search(s):
                strict_cats.add("fx")
            if CP_REGEX.search(s):
                strict_cats.add("cp")
            if EQ_REGEX.search(s):
                strict_cats.add("eq")
            if CR_REGEX.search(s):
                strict_cats.add("cr")

            if strict_cats:
                attributes["is_sophisticated"] = True
                for cat in strict_cats:
                    evidence_map[cat].append(s)
                    doc_tracker.register_paragraph(s, cat)

            # 2. Check SOFT Matches (Piggybackers)
            else:
                soft_cats = set()
                if IR_SOFT_REGEX.search(s):
                    soft_cats.add("ir")
                if FX_SOFT_REGEX.search(s):
                    soft_cats.add("fx")
                if CP_SOFT_REGEX.search(s):
                    soft_cats.add("cp")
                if EQ_SOFT_REGEX.search(s):
                    soft_cats.add("eq")
                if CR_SOFT_REGEX.search(s):
                    soft_cats.add("cr")

                if soft_cats:
                    for cat in soft_cats:
                        potential_map[cat].append(s)
                else:
                    # 3. Check Generic Resolution
                    cats = get_sentence_categories(s)
                    if "gen" in cats:
                        # Try Global Tracker (Fast & Accurate)
                        resolved = doc_tracker.resolve_instrument(s)

                        # Try ML (Optional Backup)
                        if not resolved and RESOLVER:
                            resolved = resolve_generic_with_ml(
                                s, context_buffer[:-1], None
                            )

                        if resolved and resolved not in {"gen", "other"}:
                            evidence_map[resolved].append(s)
                            attributes["is_sophisticated"] = True

    # 2. PROMOTION PASS (Piggybacking)
    # If firm is Sophisticated OR uses Hedge Accounting, we trust the Soft matches.
    is_valid_user = (
        attributes["is_sophisticated"] or attributes["uses_hedge_accounting"]
    )

    if is_valid_user:
        for cat, sentences in potential_map.items():
            if cat not in evidence_map:
                evidence_map[cat].extend(sentences)
    # 2.5: Trading attributes: if it is not a hedger, then it is a trader
    if attributes["mentions_venue"] and not attributes["is_hedger"]:
        attributes["is_trader"] = True
    else:
        attributes["is_trader"] = False
    del attributes["mentions_venue"]
    
    # 3. FINAL OUTPUT
    if not evidence_map and not any(attributes.values()):
        return (url, "{}", cik, year)

    output_data = {"evidence": evidence_map, "attributes": attributes}

    return (url, json.dumps(output_data), cik, year)


# =============================================================================
# INFRASTRUCTURE
# =============================================================================


def setup_target_db(path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, matches TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES webpage_result(url))"
    )
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
    if not buffer:
        return
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
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
    try:
        initialize_resolver()
        print("🧠 ML Resolver Initialized")
    except:
        print("⚠️ ML Server skipped (Regex Only Mode)")
    print(f"🚀 Starting Final Classifier ({NUM_WORKERS} workers)")
    setup_target_db(TARGET_DB_PATH)
    processed = get_processed_urls(TARGET_DB_PATH)

    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")

    buffer = []
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        source = list(data_generator(SOURCE_DB_PATH, processed))
        for result in tqdm(
            executor.map(process_row, source, chunksize=10), total=len(source)
        ):
            if result:
                buffer.append(result)
                if len(buffer) >= BATCH_SIZE:
                    write_batch(conn, buffer)
                    buffer = []

    if buffer:
        write_batch(conn, buffer)
    conn.close()
    print("✅ Classification Complete.")
