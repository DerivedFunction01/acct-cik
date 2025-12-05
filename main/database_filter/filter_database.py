"""
DERIVATIVE CATEGORY DISAMBIGUATION MODULE
==========================================
Advanced filtering system for separating multi-category derivative disclosures
into distinct, single-category training examples through targeted text reduction.

Methodology:
1. Multi-category detection via instrument-specific and context-specific pattern matching
2. Iterative sentence duplication for each identified derivative category
3. Systematic removal of cross-category terminology using regex-based excision
4. Independent paragraph construction per category with contextual compatibility validation
5. Preservation of generic derivative references without category-specific terms

Academic Rationale:
This approach addresses the challenge of mixed-category financial disclosures where
companies discuss multiple derivative types in compound sentences. Traditional filtering
would either discard these sentences or introduce category ambiguity. Our duplication-
and-reduction strategy preserves information, so as all downstream targeted cleaning filters
rely on this category to be correct.

Note:
This is not used for training any classification model; but rather, provide binary flags
indicating firm usage. If the window survives throughout targeted rounds, then the firm
is classified as an active user for that category.

Example Transformation:
  Source: "The Company utilizes foreign currency forwards and interest rate swaps
           to manage exposure to market volatility."

  Output (2 distinct examples):
    - FX Instance: "The Company utilizes forwards to manage exposure to market volatility."
      (Removed: interest rate instruments and IR-specific context)

    - IR Instance: "The Company utilizes swaps to manage exposure to market volatility."
      (Removed: foreign currency instruments and FX-specific context)
"""

import json
import logging
from pathlib import Path
import re
from tqdm import tqdm
from typing import Dict, List, Tuple, Optional, Set, Any
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time
import sqlite3
from itertools import groupby
import uuid
from final_verification import QUANT_REGEX
from year_deletion import extract_years, has_current_year_mention
from notional_filter import DATE_DM_REGEX, DATE_MD_REGEX, check_is_quantitative_zero
from table_processor import TABLE_ANCHOR, TableToTextConverter

# Import all derivative regexes

from derivative_regex import (
    ABSENCE_REGEX,
    ACCOUNTING_STANDARDS_STRICT_REGEX,
    ACTIVE_STATE_REGEX,
    ALL_BASE_TYPES,
    ALL_REGEX,
    BASE_REGEX,
    BOTH_CATEGORY_REGEX,
    CP_SOFT_REGEX,
    CR_REGEX,
    CR_SOFT_REGEX,
    DEFINITION_INDICATORS,
    DER_STD_REGEX,
    DID_NOT_HOLD_REGEX,
    EMBEDDED_CAP_FLOOR_REGEX,
    ENTITY_TOKEN,
    EQ_SOFT_REGEX,
    EXCLUDE_COMPETITOR_REGEX,
    EXCLUDE_HYPOTHETICAL_REGEX,
    EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX,
    EXCLUDE_PLAN_ASSETS_REGEX,
    EXCLUDE_REGEX_ACCOUNTING_STD,
    EXCLUDE_REGEX_EQUITY_COMP,
    EXCLUDE_REGEX_FILING,
    EXCLUDE_REGEX_LEGAL_LITIGATION,
    EXCLUDE_REGULATION_REGEX,
    EXCLUDE_REGEX_FORWARD_LOOKING,
    FV_REGEX,
    FX_SOFT_REGEX,
    GEN_REGEX,
    HEADER_CLEANUP_PATTERNS,
    HEDGING_CONTEXT_REGEX,
    IR_REGEX,
    FX_REGEX,
    CP_REGEX,
    EQ_REGEX,
    IR_SOFT_REGEX,
    LOOSE_GEN_REGEX,
    MORE_INFO_REGEX,
    NEGATIVE_INTENT_REGEX,
    POSITION_CONTEXT_INDICATORS,
    POTENTIAL_REGEX,
    PRIOR_PATTERN,
    REFERENCE_CLEANUP_REGEX,
    SOFT_CATEGORY_REGEX,
    SOFT_GEN_REGEX,
    SOFT_REGEX,
    STANDARD_ID_REGEX,
    STRICT_GEN_REGEX,
    SENTENCE_SPLIT_PATTERN,
    MIN_SENTENCE_LENGTH,
    STRICT_NOTIONAL_REGEX,
    STRICT_REGEX,
    TERMINATION_REGEX,
    TITLE_CLEANER_REGEX,
    TRADING_STATEMENTS_REGEX,
    VERB_REGEX,
    YEAR_REGEX,
    check_for_instrument,
    cleanup_fragment,
    CATEGORY_CONTEXT_MAP,
    CATEGORY_DELETION_MAP,
    NON_POSITION_INDICATORS,
    PNL_ONLY_NO_POSITION,
    HIGH_PRECISION_SUFFIXES,
    is_contractual_noise,
    validate_instrument_retention,
    MAX_SENTENCE_LENGTH,
    ANCHOR_TAG,
    STRICT_CONTEXT_MAP,
    ENTITY_EXCLUSION_REGEX,
    aggregate_discards
)

# =============================================================================
# CONFIGURATION
# =============================================================================
PRIORTY = ["fx", "cp", "eq", "cr", "ir"]
from collections import defaultdict


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


# --- NEW: ML Resolver -------------------------------------------------
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

# Global resolver instance (initialized once at startup)
RESOLVER: Optional[NetworkDerivativeResolver] = None


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


class TextCleaner:
    MAX_CLEANUP_MATCH_LENGTH = 500
    TITLE_KEYWORDS_REPORTING = {
        "disclosure",
        "accounting",
        "reporting",
        "measurement",
        "recognition",
        "presentation",
        "guidance",
        "objective",
        "strategy",
        "policy",
        "activity",
        "summary",
        "information",
        "impact",
        "overview",
        "note",
        "table",
        "amendment",
        "deferral",
        "interpretation",
        "position",
        "adoption",
        "transition",
        "standard",
        "statement",
        "provision",
        "regulation",
        "abstract",
        "opinion",
        "codification",
        "bulletin",
        "release",
    }

    TITLE_KEYWORDS_DERIV = {
        "derivative",
        "hedging",
        "hedge",
        "swap",
        "option",
        "future",
        "forward",
        "instrument",
        "financial",
        "risk",
    }

    # Updated bullet_pattern definition inside TextCleaner class (or module level)

    bullet_pattern = re.compile(
        r"(?<![\$€£¥])"        # 1. Safety: Not preceded by currency symbols
        r"(?:(?<=^)|(?<=\s))"  # 2. Anchor: Start of line OR preceded by whitespace (Fixes \b bug)
        r"(?:"
            r"\(?\d+\)|"       # 3. Matches (1), 1), or 1 (if enclosed)
            r"\d+\."           # 4. Matches 1.
        r")"
        r"(?=\s)",             # 5. Safety: Must be followed by whitespace (Protects "Note 5.")
        re.IGNORECASE
    )

    dashed_pattern = re.compile(r"\b\d+[-]\d+\b")
    exhibit_pattern = re.compile(
        r"\b(?:exhibit|reference|note|appendix|schedule|article|section|subsection|statement)\b"   # keyword
        r"(?:\s*No\.?)?"                                      # optional "No." (with or without dot)
        r"\s*\d{1,3}\b",                                      # number (1–3 digits)
        re.IGNORECASE
    )

    loan_salvation_regex = [
        HEDGING_CONTEXT_REGEX,
        STRICT_NOTIONAL_REGEX,
        SOFT_GEN_REGEX,
        STANDARD_ID_REGEX,
    ]

    def __init__(
        self,
        max_match_length: int = MAX_CLEANUP_MATCH_LENGTH,
        track_discards: bool = False,
    ):
        """
        Args:
            max_match_length: The safety threshold for regex matches.
            track_discards: If True, track what content was removed and why.
        """
        self.max_match_length = max_match_length
        self.TITLE_KEYWORDS_REPORTING = set(self.TITLE_KEYWORDS_REPORTING)
        self.TITLE_KEYWORDS_DERIV = set(self.TITLE_KEYWORDS_DERIV)
        self.track_discards = track_discards
        self.discards = []  # List of (url, removed_text, reason)
        self.current_url = None

    def _record_discard(self, removed_text: str, reason: str):
        """Records removed content for auditing."""
        if self.track_discards and removed_text.strip():
            self.discards.append((self.current_url, removed_text, reason))

    def has_strict_quant(self, s: str) -> bool:
        s_no_year = YEAR_REGEX.sub("", s)
        s_no_year = STANDARD_ID_REGEX.sub(" ", s_no_year)
        s_no_year = DATE_MD_REGEX.sub(" ", s_no_year)
        s_no_year = DATE_DM_REGEX.sub(" ", s_no_year)
        s_no_year = self.bullet_pattern.sub(" ", s_no_year)
        s_no_year = self.dashed_pattern.sub(" ", s_no_year)
        return bool(QUANT_REGEX.search(s_no_year))

    def _safe_sub(self, pattern: re.Pattern, replacement: str, text: str) -> str:
        """
        Performs a regex substitution ONLY if the match length is within limits.
        """

        def replacement_callback(match):
            match_len = len(match.group(0))
            if match_len > self.max_match_length:
                return match.group(0)
            return replacement

        return pattern.sub(replacement_callback, text)

    def clean_entities(self, text: str) -> str:
        """
        Removes official entity names that contain derivative keywords.
        """
        return self._safe_sub(ENTITY_EXCLUSION_REGEX, f" {ENTITY_TOKEN} ", text)

    def clean_structure(self, text: str) -> str:
        """
        Cleans headers, markdown emphasis, and structural all-caps artifacts.
        """
        if TABLE_ANCHOR in text:
            return text
        cleaned_text = text
        for pattern, replacement in HEADER_CLEANUP_PATTERNS:
            cleaned_text = self._safe_sub(pattern, replacement, cleaned_text)
            cleaned_text = self._safe_sub(pattern, replacement, cleaned_text)
        return cleaned_text

    def _clean_text_per_sentence(
        self, text: str, trigger_regex: re.Pattern, reason: str, override_regex: Optional[List[re.Pattern]] = None
    ) -> str:
        """
        Generic per-sentence cleaner: if a sentence matches trigger_regex,
        remove from the match until the end of that sentence.

        Args:
            text: The input text
            trigger_regex: Pattern to search for within sentences
            reason: Reason for removal (for audit trail)

        Returns:
            Text with matching sentences cleaned from trigger point to end.
        """
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()]
        kept_sentences = []

        for sent in sentences:
            match = trigger_regex.search(sent)
            if match: 
                # Override prevents the match from getting cleaned
                if not (override_regex and any(regex.search(sent) for regex in override_regex)):
                    # Keep text before the match, remove from match to end of sentence
                    cleaned_sent = sent[: match.start()].strip()
                    removed_text = sent[match.start() :].strip()

                    self._record_discard(removed_text, reason)

                    if cleaned_sent:
                        kept_sentences.append(cleaned_sent)
                else:
                    kept_sentences.append(sent)
                    self._record_discard(sent, "overide_discarded_" + reason)
            else:
                kept_sentences.append(sent)

        return " ".join(kept_sentences)

    def clean_references(self, text: str) -> str:
        """
        Removes noise references like "See Note 5" or "Table below".
        Cleans from the trigger point to the end of the sentence.
        """
        if not REFERENCE_CLEANUP_REGEX.search(text):
            return text

        if self.has_strict_quant(text):
            return self._clean_text_per_sentence(
                text, REFERENCE_CLEANUP_REGEX, "reference_cleanup"
            )

        self._record_discard(text, "reference_entire_paragraph_no_quant")
        return ""  # The whole thing talks about a table

    def clean_information(self, text: str) -> str:
        """
        Remove "for further information" statements.
        Cleans from the trigger point to the end of the sentence.
        """
        return self._clean_text_per_sentence(
            text, MORE_INFO_REGEX, "information_cleanup"
        )

    def normalize_whitespace(self, text: str) -> str:
        """
        Collapses multiple spaces/newlines into single units.
        """
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _find_strict_context_endpoint(self, sentences: list[str]) -> int:
        """
        Finds the endpoint where strict regex context begins.

        Returns:
            Index of the first sentence containing strict context (endpoint).
            If no strict context is found, returns len(sentences) (keep all).
        """
        for idx, sent in enumerate(sentences):
            if ACCOUNTING_STANDARDS_STRICT_REGEX.search(sent):
                return idx
        return len(sentences)

    def _clean_kept_sentences(self, sentences: list[str], endpoint: int) -> str:
        """
        Cleans and filters sentences up to the endpoint.

        Processing includes:
        1. Detect accounting standard references
        2. Clean the standard IDs
        3. Apply quantitative filter (standard refs need numbers to survive)
        4. Apply title cleaning (aggressive vs conservative)

        Args:
            sentences: List of sentence strings
            endpoint: Index up to which to process (exclusive)

        Returns:
            Cleaned and joined text from kept sentences.
        """
        kept_sentences = []

        for idx in range(endpoint):
            sent = sentences[idx]

            # Detect standard reference
            has_std_ref = EXCLUDE_REGEX_ACCOUNTING_STD.search(sent)

            # Clean the IDs (unconditional cleanup)
            clean_sent = EXCLUDE_REGEX_ACCOUNTING_STD.sub(" ", sent)
            clean_sent = STANDARD_ID_REGEX.sub(" ", clean_sent)

            # QUANTITATIVE FILTER (Content Check)
            # If it's a standard ref, it needs numbers to survive.
            if has_std_ref:
                if not self.has_strict_quant(clean_sent):
                    self._record_discard(sent, "accounting_standard_no_quant")
                    continue  # Discard just this sentence, continue to next

            # Title Cleaning (Aggressive vs Conservative)
            def title_replacer(match):
                match_text = match.group(0)
                lower_text = match_text.lower()
                start_pos = match.start()

                if len(match_text.split()) < 2:
                    return match_text

                is_sentence_start = False
                if start_pos == 0:
                    is_sentence_start = True
                elif start_pos > 1:
                    preceding = clean_sent[start_pos - 2 : start_pos]
                    if any(p in preceding for p in [". ", "? ", "! "]):
                        is_sentence_start = True

                has_reporting = any(
                    kw in lower_text for kw in self.TITLE_KEYWORDS_REPORTING
                )
                has_deriv = any(kw in lower_text for kw in self.TITLE_KEYWORDS_DERIV)

                # Conservative mode (general context)
                if has_reporting and has_deriv:
                    return " " * len(match_text)

                return match_text

            final_sent = TITLE_CLEANER_REGEX.sub(title_replacer, clean_sent)

            if final_sent.strip():
                kept_sentences.append(final_sent)
            else:
                self._record_discard(
                    sent, "accounting_standard_title_cleaning_destroyed"
                )

        return " ".join(kept_sentences)

    def clean_standards(self, text: str) -> str:
        """
        Surgically removes accounting standard references.

        Pipeline:
        1. Find the endpoint where strict context begins
        2. Clean and filter sentences up to that endpoint
        3. Return the cleaned result
        """
        if TABLE_ANCHOR in text:
            return text

        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()]

        # Find where strict context starts (return point for discarded content)
        endpoint = self._find_strict_context_endpoint(sentences)

        # Record discarded sentences from endpoint onward
        for idx in range(endpoint, len(sentences)):
            self._record_discard(
                sentences[idx], "accounting_standard_strict_context_cutoff"
            )

        # Clean the kept sentences up to endpoint
        cleaned_text = self._clean_kept_sentences(sentences, endpoint)

        return cleaned_text

    def clean_numerics(self, text: str) -> str:
        """
        Removes numeric noise (bullets, dashed numerics, dates).
        Note: Does NOT track discards for numeric cleanup as these are minor artifacts.
        """
        text = self.bullet_pattern.sub(" ", text)
        text = self.dashed_pattern.sub(" ", text)
        text = DATE_DM_REGEX.sub(" ", text)
        text = DATE_MD_REGEX.sub(" ", text)
        text = self.exhibit_pattern.sub(" ", text)
        return text

    def clean_loan_features(self, text: str):

        return self._clean_text_per_sentence(text, EMBEDDED_CAP_FLOOR_REGEX, "loan_features", self.loan_salvation_regex)

    def process(self, text: str, url: Optional[str] = None) -> str:
        """
        Main pipeline execution.

        Args:
            text: The text to clean
            url: Optional URL to associate with discards (auto-clears previous URL's discards)
        """
        # Auto-clear when processing new URL
        if url is not None and url != self.current_url:
            self.clear_discards()
            self.current_url = url

        if not text:
            return ""
        text = self.clean_loan_features(text)
        text = self.clean_references(text)
        text = self.clean_information(text)
        text = self.clean_standards(text)
        text = self.clean_entities(text)
        text = self.clean_numerics(text)
        text = self.normalize_whitespace(text)
        text = self.clean_structure(text)
        text = cleanup_fragment(text)
        return text

    def get_discards(self) -> list[tuple[str, str, str]]:
        """
        Returns list of (url, removed_text, reason) tuples.
        Only populated if track_discards=True was set at initialization.
        """
        return self.discards

    def clear_discards(self):
        """Clears the discard history."""
        self.discards = []


CLEANER = TextCleaner(track_discards=True)

# ---------------------------------------------------------------------
def get_worker_count():
    """Auto-detects CPU cores to set worker count."""
    cpu_cores = mp.cpu_count()
    num_workers = max(1, cpu_cores - 1)
    print(
        f"🖥️  System Detected: {cpu_cores} CPU cores, setting NUM_WORKERS to {num_workers}"
    )
    return num_workers


NUM_WORKERS = get_worker_count()
BATCH_SIZE = 1000  # Optimal batch size for SQLite transactions
FLUSH_INTERVAL = 5.0  # Seconds — fallback flush if batch not full
CHUNK_SIZE = 50  # Larger chunks reduce task submission overhead — tune this
SOURCE_DB_PATH = "web_data.db"
CLEAN_DB_PATH = "prepared_data.db"
# How many sentences forward can we look?
MAX_FORWARD_EXPANSION = 5

# In-memory buffers (protected by main process only)
result_buffer = []  # List of (url, matches, cik, year)
discard_buffer = []  # List of (url, sentence, reason)

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def create_clean_db():
    """Create unified clean database with parallel category tracking."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        # Main table for high-confidence matches
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS webpage_result (
                url TEXT PRIMARY KEY,
                matches TEXT NOT NULL  -- JSON array of paragraph texts
            )
            """
        )

        # CRITICAL: Category array synchronized with matches array
        # categories[i] corresponds to matches[i]
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS category (
                url TEXT PRIMARY KEY,
                categories TEXT NOT NULL,  -- JSON array of category labels ['ir', 'fx', 'gen', ...]
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
            """
        )

        # Metadata for high-confidence matches
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS report_data (
                url TEXT PRIMARY KEY,
                cik INTEGER,
                year INTEGER,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
            """
        )

        # Server result table: Roberta's results
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS server_result (
                url TEXT PRIMARY KEY,
                server_response TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url)
            )
        """
        )

        # Discard tracking table - stores discarded sentences for review
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discarded_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                sentence TEXT,
                discard_reason TEXT,
                FOREIGN KEY (url) REFERENCES webpage_result(url),
                FOREIGN KEY (discard_reason) REFERENCES discard_reasons(reason)
            )
            """
        )

        # Discard reasons: no_match, too_short, trading_statement
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS discard_reasons (
                reason TEXT PRIMARY KEY
            )
            """
        )

        c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS discard_reason_idx ON discarded_sentences (discard_reason)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS server_url_idx ON server_result (url)")
        c.execute("CREATE INDEX IF NOT EXISTS cat_url_idx ON category (url)")
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.IntegrityError as e:
        print(f"⚠️  Error creating clean database: {e}")
    finally:
        try:
            reasons = [
                "no_match",
                "too_short",
                "trading_statements",
                "aoci",
                "pnl_only_no_position",
                "pnl_only_removed",
                "definition_boilerplate",
                "reference_cleanup",
                "reference_entire_paragraph_no_quant",
                "information_cleanup",
                "accounting_standard_no_quant",
                "accounting_standard_strict_context_cutoff",
                "accounting_standard_title_cleaning_destroyed",
                "lost_instrument_reference",
                "regulation",
                "hypo",
                "planned_assets",
                "competitor",
                "contractual"
            ] + [
                f"disambiguation_excision_failed_{cat}"
                for cat in CATEGORY_CONTEXT_MAP.keys()
            ]
            c.executemany(
                "INSERT OR IGNORE INTO discard_reasons (reason) VALUES (?)",
                [(reason,) for reason in reasons],
            )
        except sqlite3.IntegrityError as e:
            print(f"⚠️  Error inserting discard reasons: {e}")
        conn.commit()
        conn.close()


def get_source_data() -> List[Tuple[str, str]]:
    """Fetch all URL and matches from source database."""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT url, matches FROM webpage_result WHERE url IS NOT NULL")
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"❌ Error reading source database: {e}")
        conn.close()
        return []


def get_all_report_data() -> dict:
    """Fetch all report data into a dictionary for fast lookups."""
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url, cik, year FROM report_data")
    report_map = {row[0]: (row[1], row[2]) for row in c.fetchall()}
    conn.close()
    return report_map


def get_processed_urls_from_clean_db() -> set:
    """Fetches all URLs that have already been processed and saved to the clean database."""
    if not Path(CLEAN_DB_PATH).exists():
        return set()
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT url FROM webpage_result")
        processed_urls = {row[0] for row in c.fetchall()}
        return processed_urls
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()


def flush_buffers(force: bool = False) -> bool:
    """
    Flush accumulated results and discards to database in batches.
    Ensures matches and categories arrays are synchronized.
    """
    global result_buffer, discard_buffer

    if (
        not force
        and len(result_buffer) < BATCH_SIZE
        and len(discard_buffer) < BATCH_SIZE * 10
    ):
        return False

    conn = sqlite3.connect(CLEAN_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA temp_store = MEMORY")
    c = conn.cursor()

    try:
        c.execute("BEGIN TRANSACTION")

        # 1. Flush main results with parallel category arrays
        if result_buffer:
            # result_buffer contains: (url, [(text, category), ...], cik, year)

            for url, paragraph_tuples, cik, year in result_buffer:
                # Separate texts and categories into parallel arrays
                texts = [text for text, cat in paragraph_tuples]
                categories = [cat for text, cat in paragraph_tuples]

                # Verify array synchronization
                assert len(texts) == len(categories), f"Array mismatch for {url}"

                # Insert matches
                c.execute(
                    "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                    (url, json.dumps(texts)),
                )

                # Insert parallel categories array
                c.execute(
                    "INSERT OR IGNORE INTO category (url, categories) VALUES (?, ?)",
                    (url, json.dumps(categories)),
                )

                # Insert metadata if available
                if cik is not None:
                    c.execute(
                        "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                        (url, cik, year),
                    )

            result_buffer.clear()

        # 2. Flush discarded sentences
        if discard_buffer:
            c.executemany(
                """
                INSERT INTO discarded_sentences (url, sentence, discard_reason)
                VALUES (?, ?, ?)
                """,
                discard_buffer,
            )
            discard_buffer.clear()

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Batch flush failed: {e}")
        raise
    finally:
        conn.close()


# =============================================================================
# CATEGORY DETECTION & VALIDATION
# =============================================================================
def scrub_unmatched_generics(text: str, category: str) -> str:
    """
    Removes generic derivative terms (e.g., 'options', 'swaps') UNLESS they are
    part of the specific category match.

    Strategy:
    1. Find specific category matches (e.g., 'interest rate swaps').
    2. Mask them with a unique placeholder.
    3. Aggressively remove loose generic terms from the remaining text.
    4. Restore the specific matches.
    """
    if category not in CATEGORY_DELETION_MAP:
        return text

    # 1. Get the regex for the category we want to KEEP (e.g., IR_REGEX)
    keep_regex = CATEGORY_DELETION_MAP[category][0]
    keep_soft_regex =  CATEGORY_DELETION_MAP[category][1]

    # 2. Mask specific matches
    # We use a unique ID to avoid accidental partial replacement collisions
    protections = {}

    def mask_match(match):
        token = f"__PROTECTED_{uuid.uuid4().hex}__"
        protections[token] = match.group(0)
        return token

    masked_text = keep_regex.sub(mask_match, text) # Max munch
    masked_text = keep_soft_regex.sub(mask_match, text) # fallback if the strict match doesn't have it
    # 3. Scrub generics from the REST of the text
    # remove "swaps", "options", "contracts" that weren't protected
    from derivative_regex import LOOSE_GEN_REGEX

    scrubbed_text = LOOSE_GEN_REGEX.sub(" ", masked_text)

    # 4. Restore the specific matches
    for token, original_phrase in protections.items():
        scrubbed_text = scrubbed_text.replace(token, original_phrase)

    # 5. Cleanup whitespace
    return cleanup_fragment(scrubbed_text)

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


def get_primary_category(categories: set) -> str:
    """Get the primary category, preferring specific over generic."""
    specific = categories - {"gen", "other"}
    if specific:
        priority = PRIORTY
        for cat in priority:
            if cat in specific:
                return cat
        return list(specific)[0]
    return "gen" if "gen" in categories else "other"


# =============================================================================
# CATEGORY-SPECIFIC TERM EXCISION ENGINE
# =============================================================================

# Mapping of derivative categories to their respective deletion patterns
# Each category maps to (instrument_pattern, context_pattern) for comprehensive removal


def excise_category_terminology(text: str, category: str) -> str:
    """
    Systematically remove all lexical markers associated with a specific derivative category.
    Applies both instrument-specific and contextual terminology removal.

    Args:
        text: Source text containing derivative references
        category: Target category for removal ('ir', 'fx', 'cp', or 'eq')

    Returns:
        Text with all specified category terminology removed

    Example:
        Input:  "foreign currency forwards hedge exposure"
        Call:   excise_category_terminology(text, "fx")
        Output: "hedge exposure"

        Rationale: Removes "foreign currency forwards" (FX instrument + context)
    """
    if category not in CATEGORY_DELETION_MAP:
        return text

    instrument_regex, instrument_soft_regex, context_regex = CATEGORY_DELETION_MAP[category]

    # Phase 1: Remove instrument-specific terminology
    text = instrument_regex.sub(" ", text)

    text = instrument_soft_regex.sub(" ", text)

    # Phase 2: Remove contextual terminology
    text = context_regex.sub(" ", text)

    # Phase 3: Normalize whitespace and punctuation artifacts
    text = cleanup_fragment(text)

    return text


def protect_category_phrases(text: str, category: str) -> Tuple[str, Dict[str, str]]:
    """
    Masks specific phrases belonging to the target category to prevent them
    from being deleted by subsequent excision steps (Friendly Fire Protection).
    """
    if category not in CATEGORY_DELETION_MAP:
        return text, {}

    # Get the regexes for the category we want to KEEP
    # Tuple is (Strict, Soft, Context)
    keep_regex, keep_soft_regex, _ = CATEGORY_DELETION_MAP[category]

    protections = {}

    def mask_match(match):
        token = f"__PROTECTED_{uuid.uuid4().hex}__"
        protections[token] = match.group(0)
        return token

    # Apply masking (Max Munch priority is handled by the regex structure)
    # Mask strict first, then soft to ensure we catch the best matches
    masked_text = keep_regex.sub(mask_match, text)
    masked_text = keep_soft_regex.sub(mask_match, masked_text)

    return masked_text, protections


def restore_placeholders(text: str, protections: Dict[str, str]) -> str:
    """Restores masked phrases after excision is complete."""
    for token, original_phrase in protections.items():
        text = text.replace(token, original_phrase)
    return text


def generate_single_category_variant(
    sentence: str, preserve_category: str, detected_categories: Set[str]
) -> Optional[str]:
    """
    Generate a category-pure variant of a multi-category sentence through
    systematic excision of conflicting category terminology.

    Args:
        sentence: Original multi-category sentence
        preserve_category: Category to retain in output
        detected_categories: Complete set of categories identified in source

    Returns:
        Category-pure sentence variant, or None if excision results in
        insufficient content or loss of preserved category
    """
    # Identify categories requiring excision (all except preserved category)
    excision_targets = detected_categories - {preserve_category, "gen", "other"}

    # 1. PROTECT: Mask the specific matches for the category we want to KEEP
    #    e.g., Turn "equity swap" into "__PROTECTED_...__" so CP regex doesn't see "swap"
    cleaned, protections = protect_category_phrases(sentence, preserve_category)

    # 2. EXCISE: Iteratively excise each conflicting category
    #    Now safe to run broad regexes because our target is hidden
    for target_category in excision_targets:
        cleaned = excise_category_terminology(cleaned, target_category)

    # 3. RESTORE: Put the protected phrases back
    cleaned = restore_placeholders(cleaned, protections)

    # 4. SCRUB: Remove unmatched generics (Existing Step)
    #    Removes "swaps" that weren't part of "equity swaps" or other protected phrases
    if preserve_category in PRIORTY:
        cleaned = scrub_unmatched_generics(cleaned, preserve_category)

    # Validation 1: Minimum length requirement
    if len(cleaned) < MIN_SENTENCE_LENGTH:
        return None

    # Final cleanup before regex check
    cleaned = cleanup_fragment(cleaned)
    if not cleaned:
        return None

    # Validation 2: Verify preserved category remains detectable
    if preserve_category not in {"gen", "other"}:
        _, instrument_soft_regex, _ = CATEGORY_DELETION_MAP[preserve_category]
        if not instrument_soft_regex.search(cleaned):
            return None  # Over-excision removed target category

    return cleaned


# =============================================================================
# ENHANCED FILTER_MATCHES WITH CATEGORY DISAMBIGUATION
# =============================================================================

def expand_forward_context(
    sentences: List[str],
    start_idx: int,
    target_cat: str,
    used_indices: Set[int],
    excision_mode: bool = False,
) -> Tuple[List[str], Set[int]]:
    """
    Greedily consumes subsequent sentences if they are contextually compatible.

    Args:
        sentences: All sentences in the paragraph.
        start_idx: The index of the *Target* sentence (we look at start_idx + 1).
        target_cat: The category we are building the paragraph for.
        used_indices: Global set of indices already processed.
        excision_mode: If True, applies 'generate_single_category_variant' to context.

    Returns:
        (list_of_context_strings, set_of_consumed_indices)
    """
    # ---------------------------------------------------------
    # NEW: TABULAR ISOLATION
    # ---------------------------------------------------------
    # If the current sentence is a table row, we MUST NOT expand.
    # The TableToTextConverter has already injected full context into this row.
    # Merging it with the next row creates a dependency that risks data loss
    # if this specific row (the anchor) is filtered out (e.g. due to year).
    if TABLE_ANCHOR in sentences[start_idx]:
        return [], set()
    context_parts = []
    newly_used_indices = set()

    current_lookahead = 1

    while current_lookahead <= MAX_FORWARD_EXPANSION:
        next_idx = start_idx + current_lookahead

        # 1. Boundary Checks
        if next_idx >= len(sentences) or next_idx in used_indices:
            break

        nxt = sentences[next_idx]
        if TABLE_ANCHOR in nxt:
            break

        # 2. Length/Quality Check
        if len(nxt) < MIN_SENTENCE_LENGTH:
            break

        # 3. Category Compatibility Check
        # We perform category detection on the *next* sentence.
        nxt_cats = get_sentence_categories(nxt)

        # STOP if we hit a different STRICT category (e.g. IR paragraph hits FX sentence)
        # Compatible if:
        # a) It contains our target category
        # b) OR it is purely Generic/Other (ambiguous context)
        is_compatible = target_cat in nxt_cats or not (nxt_cats - {"gen", "other"})

        if not is_compatible:
            break

        # 4. Processing & Accumulation
        final_text = nxt

        if excision_mode:
            # If we are splitting a multi-category paragraph, we must also
            # scrub the context sentences to ensure purity.
            clean_nxt = generate_single_category_variant(nxt, target_cat, nxt_cats)
            if clean_nxt:
                final_text = clean_nxt
            else:
                # If excision failed (e.g. sentence destroyed), stop expansion
                break

        context_parts.append(final_text)
        newly_used_indices.add(next_idx)
        current_lookahead += 1

    return context_parts, newly_used_indices


def process_resolved_sentence(
    meta: Dict[str, Any],
    sentences: List[str],
    used_indices: Set[int],
    url: str,
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, str]]]:

    paragraphs = []
    discards = []

    final_cat = meta["final_category"]
    sent_idx = meta["sent_idx"]

    # Skip if already processed
    if sent_idx in used_indices:
        return [], []

    # ════════════════════════════════════════════════════════════════
    # CASE 1: Single-category sentence
    # ════════════════════════════════════════════════════════════════
    if len(meta["specific_cats"]) <= 1 and final_cat not in {"gen", "other"}:

        # 1. Prepare Target (Anchor)
        target_sent = meta["sentence"]
        if ANCHOR_TAG not in target_sent:
            target_sent = ANCHOR_TAG + target_sent

        parts = [target_sent]
        context_indices = {sent_idx}

        # 2. Commented out, do not look back, it may lead to false positives.
        # if sent_idx > 0 and (sent_idx - 1) not in used_indices:
        #     prev = sentences[sent_idx - 1]
        #     is_curr_table = TABLE_ANCHOR in target_sent
        #     is_prev_table = TABLE_ANCHOR in prev
        #     if not (is_curr_table or is_prev_table) and len(prev) >= MIN_SENTENCE_LENGTH:
        #         prev_cats = get_sentence_categories(prev)
        #         # Compatible?
        #         if final_cat in prev_cats or not (prev_cats - {"gen", "other"}):
        #             parts.insert(0, prev)
        #             context_indices.add(sent_idx - 1)

        # 3. Look Forward (Expand)
        fwd_parts, fwd_indices = expand_forward_context(
            sentences, sent_idx, final_cat, used_indices, excision_mode=False
        )
        parts.extend(fwd_parts)
        context_indices.update(fwd_indices)

        # 4. Finalize
        paragraph = " ".join(parts)

        # Validation: Check strictly if anchor lost, loosely if anchor present
        # (check_for_instrument handles this logic if called via validate_instrument_retention later,
        # but here we do a quick check to ensure we didn't build a ghost)
        if check_for_instrument(paragraph.replace(ANCHOR_TAG, " "), strict=False):
            paragraphs.append((paragraph, final_cat))
            used_indices.update(context_indices)
        else:
            discards.append((url, paragraph, "lost_instrument_reference"))

    # ════════════════════════════════════════════════════════════════
    # CASE 2: Multi-category sentence → Generate variants
    # ════════════════════════════════════════════════════════════════
    elif len(meta["specific_cats"]) > 1:
        any_variant_succeeded = False

        for target_cat in meta["specific_cats"]:
            # Excise all other categories' terminology
            pure_variant = generate_single_category_variant(
                meta["sentence"],
                target_cat,
                meta["categories"],
            )

            if pure_variant:
                # 1. Prepare Anchor
                if ANCHOR_TAG not in pure_variant:
                    pure_variant = ANCHOR_TAG + pure_variant
                parts = [pure_variant]
                current_variant_indices = {
                    sent_idx
                }  # Track local indices for this variant

                # 2. Look Backward (1 Step with Excision)
                if sent_idx > 0 and (sent_idx - 1) not in used_indices:
                    prev = sentences[sent_idx - 1]
                    if len(prev) >= MIN_SENTENCE_LENGTH and TABLE_ANCHOR not in prev:
                        prev_cats = get_sentence_categories(prev)
                        if target_cat in prev_cats or not (
                            prev_cats - {"gen", "other"}
                        ):
                            clean_prev = generate_single_category_variant(
                                prev, target_cat, prev_cats
                            )
                            if clean_prev:
                                parts.insert(0, clean_prev)
                                # Note: We don't mark backward as used yet,
                                # as other variants might need it too.

                # 3. Look Forward (Expand with Excision)
                fwd_parts, fwd_indices = expand_forward_context(
                    sentences, sent_idx, target_cat, used_indices, excision_mode=True
                )
                parts.extend(fwd_parts)
                current_variant_indices.update(fwd_indices)

                # 4. Finalize
                paragraph = " ".join(parts)

                if check_for_instrument(
                    paragraph.replace(ANCHOR_TAG, " "), strict=False
                ):
                    paragraphs.append((paragraph, target_cat))
                    any_variant_succeeded = True
            else:
                # 1. Re-calculate what we TRIED to remove
                debug_targets = meta["categories"] - {target_cat, "gen", "other"}

                # 2. Re-run the cleaning steps to see the result
                debug_clean = meta["sentence"]
                for t_cat in debug_targets:
                    debug_clean = excise_category_terminology(debug_clean, t_cat)

                if target_cat in PRIORTY:
                    debug_clean = scrub_unmatched_generics(debug_clean, target_cat)

                # 3. Diagnose the exact failure reason
                fail_reason = "Unknown"
                if len(debug_clean) < MIN_SENTENCE_LENGTH:
                    fail_reason = f"Result too short ({len(debug_clean)} chars < {MIN_SENTENCE_LENGTH})"
                else:
                    # Check if we accidentally deleted the category we wanted to keep
                    # (Accessing the regex map directly to verify)
                    instrument_regex = CATEGORY_DELETION_MAP[target_cat][1]
                    if not instrument_regex.search(debug_clean):
                        fail_reason = (
                            f"Preserved category '{target_cat}' lost during excision"
                        )

                # 4. Pack it all into one string for the 'sentence' column
                combined_log = (
                    f"ORIGINAL: {meta['sentence']} "
                    f"||| AFTER: {debug_clean} "
                    f"||| EXCISED: {debug_targets} "
                    f"||| REASON: {fail_reason}"
                )
                discards.append(
                    (
                        url,
                        combined_log,
                        f"disambiguation_excision_failed_{target_cat}",
                    )
                )

        if any_variant_succeeded:
            # We mark the anchor as used.
            # Note regarding context: In multi-category split scenarios,
            # strictly marking context as "used" prevents the 2nd variant from grabbing it.
            # However, reusing context for both variants (e.g. IR and FX sharing the same
            # generic description sentence) is usually desirable.
            # Strategy: Only mark the ANCHOR index as globally used.
            # Context indices can be reused by other variants in this specific loop if logic allows,
            # but usually `used_indices` prevents double processing across the main loop.
            used_indices.add(sent_idx)

    # ════════════════════════════════════════════════════════════════
    # CASE 3: Unresolved generic
    # ════════════════════════════════════════════════════════════════
    else:
        # 1. Active State ("outstanding", "open")
        has_active_state = bool(ACTIVE_STATE_REGEX.search(meta["sentence"]))
        # 2. Quantitative ("$50M", "Notional")
        has_quant = (
            bool(QUANT_REGEX.search(meta["sentence"]))
            or TABLE_ANCHOR in meta["sentence"]
        )
        # 3. Action Verb ("use", "hold")
        has_verb = bool(VERB_REGEX.search(meta["sentence"]))

        if has_active_state or has_quant or has_verb:
            # RESURRECT: Keep as 'gen'
            # We don't build context here to avoid noise, just keep the anchor
            target_sent = meta["sentence"]
            if ANCHOR_TAG not in target_sent:
                target_sent = ANCHOR_TAG + target_sent

            paragraphs.append((target_sent, "gen"))
            used_indices.add(sent_idx)
        else:
            # DISCARD (Original Logic)
            resolution_method = meta.get("resolution_method", "unknown")
            confidence = meta.get("confidence", 0.0)
            discard_reason = f"unresolved_generic_{resolution_method}"
            if confidence is not None and confidence < 0.5:
                discard_reason += "_low_conf"
            # If it failed signal check, append new reason
            discard_reason = "discarded_generic_no_signal"

            discards.append((url, meta["sentence"], discard_reason))
            used_indices.add(sent_idx)

    return paragraphs, discards

def get_global_sophistication_flag(matches: List[str]) -> bool:
    """
    Scans the document for 'Sophisticated' derivative terminology (FAS 133, Hedge Accounting).
    CRITICAL: Validates that the signal is NOT inside noise (Litigation, Risk Factors, Forward-Looking).
    Meant for BioTech like firms that only uses equity derivatives (convertible debt, warrants).
    Not a need for 100% accuracy or edge cases just good enough for most firms that only ever mention 
    a convertible debt once and no other mentions
    """
    # We must iterate to see if there is a mention, but have to ignore accounting standards or else there is a false flag
    for match in matches:
        # 1. Quick Check: Does this paragraph even contain a sophistication signal?
        # (This is fast; filters out 90% of paragraphs immediately)
        if ACCOUNTING_STANDARDS_STRICT_REGEX.search(match): # Filter out issuance
            continue
        if EXCLUDE_REGEX_FILING.search(match):
            continue
        # 2. Safety Check: Is this signal actually just noise?
        # We reuse the exclusion regexes from derivative_regex.py
        if EXCLUDE_REGEX_FORWARD_LOOKING.search(match):
            continue
        if EXCLUDE_REGEX_LEGAL_LITIGATION.search(match):
            continue
        if EXCLUDE_COMPETITOR_REGEX.search(match):
            continue

        has_signal = SOFT_GEN_REGEX.search(match) or STRICT_REGEX.search(match) # embedded derivative, hedge accounting, swaps, etc. 
        # Note: eq_regex strict doesn't have barebones convertible debt, needs "derivative or hedge after it"
        
        if not has_signal:
            if FV_REGEX.search(match):
                return True
            continue
        # Note: We don't check "Contractual" here because "FAS 133" in a contract
        # definition still implies they know what they are doing.

        # 3. If we survived the checks, this is a VALID sophistication signal.
        # We trust this filer.
        return True

    # If we scanned everything and found no valid signal, we will manually check
    return False


# def is_paragraph_salvageable(paragraph: str, year: Optional[int]) -> bool:
#     """
#     'Speedruns' the late-stage checks (Phase 6/7) to see if a paragraph
#     marked for aggressive deletion actually contains hard evidence we must keep. Doesn't work as intended.
#     """
#     # 0. Clean the paragraph locally to ensure accurate regex matching
#     paragraph = CLEANER.process(paragraph)

#     # 1. Must have Quantitative Evidence (Phase 6)
#     quant_matches = list(QUANT_REGEX.finditer(paragraph))
#     if not quant_matches:
#         return False

#     # ZERO CHECK: Discard if the only numbers found are "0", "0.0", etc.
#     has_nonzero_quant = any(re.search(r"[1-9]", m.group()) for m in quant_matches)
#     if not has_nonzero_quant:
#         return False

#     # 2. PARAGRAPH TIME CHECK (The Gatekeeper)
#     # The paragraph MUST mention the reporting year (or future).
#     if not has_current_year_mention(paragraph, year):
#         return False

#     # 3. SENTENCE VALIDATION
#     sentences = SENTENCE_SPLIT_PATTERN.split(paragraph)

#     for sentence in sentences:
#         # A. Filter out "Prior Year" clauses ("In the prior period...")
#         if PRIOR_PATTERN.search(sentence):
#             continue

#         # B. Filter out explicit past years (The "Mixed Year" Fix)
#         # If the sentence mentions "2004" but not "2005", skip it.
#         # (If it mentions NO years, we assume it refers to the paragraph context)
#         sent_years = extract_years(sentence)
#         if year and sent_years:
#             if max(sent_years) < year:
#                 continue

#         # C. Check for Non-Zero Quant (Phase 6 Logic)
#         # If this returns False (Keep), it means we found a valid non-zero amount.
#         if not check_is_quantitative_zero(sentence, year if year else 0):
#             return True

#     return False


def filter_matches_with_disambiguation(
    matches_json: str, url: str = "", year: Optional[int] = None
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, str]]]:
    """
    Advanced filtering system implementing category-based sentence disambiguation
    through duplication and targeted terminology excision.
    
    Returns: (list_of_(paragraph, category), list_of_discards)
    """
    try:
        matches = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return [], []

    if not isinstance(matches, list):
        return [], []

    final_paragraphs = []
    all_discarded = []

    # Metadata collection for all sentences across all paragraphs
    sentence_metadata = []
    generic_buffer = []
    tracker = GlobalInstrumentTracker()
    is_derivative = get_global_sophistication_flag(matches)

    # ═════════════════════════════════════════════════════════════════
    # PASS 1: SEGMENTATION, VALIDATION, NOISE REDUCTION
    # ═════════════════════════════════════════════════════════════════

    for para_idx, match in enumerate(matches):
        # Skip tables
        is_table_content = False
        if '<TABLE>' in match.upper():
            # 1. Attempt to convert valid numeric tables into "Active User" sentences
            # e.g. "Table Disclosure: The Company held IR Swaps with fair value of $50."
            try:
                # CONTEXT EXTRACTION FOR TABLE PROCESSING
                # We check previous and next paragraphs for pointers like "The table below presents..."
                table_context = ""

                # Check Previous Paragraph
                if para_idx > 0:
                    prev_text = matches[para_idx - 1]
                    # We use REFERENCE_CLEANUP_REGEX to detect the structure,
                    # and explicit keywords to ensure it refers to a table/schedule (not just a Note)
                    if REFERENCE_CLEANUP_REGEX.search(prev_text):
                        if any(
                            kw in prev_text.lower()
                            for kw in ["table", "schedule", "exhibit"]
                        ):
                            table_context += " " + prev_text

                # Check Next Paragraph (e.g. "The table above shows...")
                if para_idx < len(matches) - 1:
                    next_text = matches[para_idx + 1]
                    if REFERENCE_CLEANUP_REGEX.search(next_text):
                        if any(
                            kw in next_text.lower()
                            for kw in ["table", "schedule", "exhibit"]
                        ):
                            table_context += " " + next_text

                converter = TableToTextConverter(match, narrative_context=table_context, is_sophisticated=is_derivative)
                extracted_sentences = converter.process()

                if extracted_sentences:
                    # Success: We extracted data. Treat these sentences as a single paragraph.
                    # This allows standard regex filtering (Phase 1) and intent checks (Phase 4)
                    # to work on the table data just like narrative text.
                    match = " ".join(extracted_sentences)
                    is_table_content = True
                else:
                    # Failure: Table was numeric but had no recognized active columns.
                    # Keep as is (tagged 'table') or discard depending on preference.
                    # Currently keeping for manual review if needed.
                    final_paragraphs.append((match, 'table'))
                    continue
            except Exception as e:
                # Fallback for parsing errors
                # logging.warning(f"Table parsing failed for {url}: {e}")
                final_paragraphs.append((match, 'table'))
                continue

        # Skip litigation (if a "commodity swap") was involved in the case, we don't want it anyways.
        if EXCLUDE_REGEX_LEGAL_LITIGATION.search(match):
            all_discarded.append((url, match, "legal"))
            continue
        # Don't care how competitors uses swaps
        if EXCLUDE_COMPETITOR_REGEX.search(match):
            all_discarded.append((url, match, "competitor"))
            continue
        # Skip regulatory paragraphs, they say how "swaps" are regulated, not a firm uses it
        if EXCLUDE_REGULATION_REGEX.search(match):
            all_discarded.append((url, match, "regulation"))
            continue

        if EXCLUDE_PLAN_ASSETS_REGEX.search(match):
            all_discarded.append((url, match, "planned_assets"))
            continue

        if EXCLUDE_HYPOTHETICAL_REGEX.search(match):
            all_discarded.append((url, match, "hypo"))
            continue
        if EXCLUDE_REGEX_FORWARD_LOOKING.search(match):
            all_discarded.append((url, match, "forward_looking"))
            continue
        if EXCLUDE_REGEX_FILING.search(match):
            all_discarded.append((url, match, "filing"))
            continue
        if is_contractual_noise(match):
            sentences_temp = SENTENCE_SPLIT_PATTERN.split(match)
            kept_text = []
            discarded_parts = []

            for sentence in sentences_temp:
                # SALVATION LOGIC:
                # 1. Must mention a derivative (SOFT_REGEX)
                # 2. Must have Hedging Context (e.g. "hedge", "manage risk", "exposure")
                # This distinguishes "We use swaps to hedge..." (Keep)
                # from "Swap Agreement shall mean..." (Discard)
                if STRICT_REGEX.search(sentence):
                    kept_text.append(sentence)
                elif SOFT_REGEX.search(sentence) and HEDGING_CONTEXT_REGEX.search(
                    sentence
                ):
                    kept_text.append(sentence)
                else:
                    discarded_parts.append(sentence)

            # 1. Log the discards
            discarded_str = " ".join(discarded_parts)
            if discarded_str.strip():
                all_discarded.append((url, discarded_str, "contractual"))

            # 2. Check if anything survived
            match = " ".join(kept_text).strip()

            # 3. If the whole paragraph was definitions, kill it.
            if not match:
                continue

        # Split into sentences
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(match)]

        # ═══════════════════════════════════════════════════════════
        # PRE-SCAN: PARAGRAPH INTENT ANALYSIS
        # ═══════════════════════════════════════════════════════════
        # We check specific sentences for "Potential", "Absence", or "Termination" flags.
        # If the paragraph is overwhelmingly "Risk Management" (Non-use/Hypothetical),
        # we discard the WHOLE thing to prevent leaving behind orphan sentences.

        para_potential = False
        para_absence = False

        for s in sentences:
            # OPTIMIZATION: Only check intent in sentences that actually discuss derivatives.
            # This prevents "We may acquire new companies" (Potential) from triggering the filter.
            if BOTH_CATEGORY_REGEX.search(s) or GEN_REGEX.search(s):

                # 1. Potential ("May use", "Expect to enter")
                if POTENTIAL_REGEX.search(s):
                    para_potential = True

                # 2. Absence ("Do not hold", "No outstanding")
                if (NEGATIVE_INTENT_REGEX.search(s) 
                    or ABSENCE_REGEX.search(s) 
                    or DID_NOT_HOLD_REGEX.search(s)):
                    para_absence = True
            if para_potential and para_absence:
                break               
        # ═══════════════════════════════════════════════════════════
        # DECISION: KEEP OR KILL PARAGRAPH
        # ═══════════════════════════════════════════════════════════

        # CASE 1: Contradiction (Potential + Absence) -> "We may use... we do not have."
        # This is classic boilerplate. Kill it.
        if para_potential and para_absence:
            all_discarded.append((url, match, "aggressive_paragraph_contradiction"))
            continue

        # Remove equity compensation boilerplate (salvage derivative mentions)
        if EXCLUDE_REGEX_EQUITY_COMP.search(match):
            sentences_temp = SENTENCE_SPLIT_PATTERN.split(match)
            text = []
            discard = []
            # Inside the EXCLUDE_REGEX_EQUITY_COMP block

            for sentence in sentences_temp:
                # 1. SAFE INSTRUMENTS (IR, FX, CP)
                # These are distinct enough from "Stock Options" that we can trust
                # Broad Context ("manage risk", "exposure").
                if (
                    IR_SOFT_REGEX.search(sentence)
                    or FX_SOFT_REGEX.search(sentence)
                    or CP_SOFT_REGEX.search(sentence)
                    or CR_SOFT_REGEX.search(sentence)
                ):

                    if HEDGING_CONTEXT_REGEX.search(sentence):
                        text.append(sentence)

                # 2. DANGEROUS INSTRUMENTS (EQ, Generics)
                elif EQ_REGEX.search(sentence):
                    text.append(sentence)
                # "Stock Options" or "Swaps" could be compensation.
                # We require Strict Accounting proof ("hedge accounting", "derivative liability").
                elif EQ_SOFT_REGEX.search(sentence):
                    if SOFT_GEN_REGEX.search(sentence) or DER_STD_REGEX.search(sentence):
                        text.append(sentence)
                else:
                    discard.append(sentence)
            discarded_text = " ".join(discard)
            if discarded_text.strip():
                all_discarded.append((url, discarded_text, "comp"))
            match = " ".join(text)
            if not match.strip():
                continue
        # Run the text cleaner
        match = CLEANER.process(match, url=url)

        if not match:
            continue
        # Split into sentences
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(match)]
        used_indices = set()

        for sent_idx, sentence in enumerate(sentences):
            if sent_idx in used_indices:
                continue

            # ═══════════════════════════════════════════════════════════
            # VALIDATION: Length, definition, trading denials, AOCI, PnL
            # ═══════════════════════════════════════════════════════════

            if len(sentence) < MIN_SENTENCE_LENGTH:
                all_discarded.append((url, sentence, "too_short"))
                used_indices.add(sent_idx)
                continue
            if len(sentence) > MAX_SENTENCE_LENGTH and ALL_REGEX.search(sentence): # an unwrapped table: convert it back
                sentence = "<TABLE>" +  sentence + "</TABLE>"
                final_paragraphs.append((sentence, 'table'))
                used_indices.add(sent_idx)
                continue

            if DEFINITION_INDICATORS.search(sentence):
                all_discarded.append((url, sentence, "definition_boilerplate"))
                used_indices.add(sent_idx)
                continue

            # Trading denial removal
            if TRADING_STATEMENTS_REGEX.search(sentence):
                deleted_text = " ".join(m.group(0) for m in TRADING_STATEMENTS_REGEX.finditer(sentence))
                all_discarded.append((url, sentence, "trading_statements_full_delete"))
                used_indices.add(sent_idx)
                continue

            # AOCI removal
            if NON_POSITION_INDICATORS.search(sentence):
                all_discarded.append((url, sentence, "aoci_or_pnl_only"))
                used_indices.add(sent_idx)
                continue

            # PnL-only removal (with partial salvage)
            if PNL_ONLY_NO_POSITION.search(sentence):
                has_instrument = bool(STRICT_REGEX.search(sentence))
                has_position_context = bool(POSITION_CONTEXT_INDICATORS.search(sentence))

                if has_instrument or has_position_context:
                    deleted_text = " ".join(m.group(0) for m in PNL_ONLY_NO_POSITION.finditer(sentence))
                    all_discarded.append((url, deleted_text.strip(), "pnl_only_removed"))
                    sentence = PNL_ONLY_NO_POSITION.sub("", sentence)
                    sentence = cleanup_fragment(sentence)

                    if not sentence:
                        used_indices.add(sent_idx)
                        continue
                else:
                    all_discarded.append((url, sentence, "pnl_only_no_position"))
                    used_indices.add(sent_idx)
                    continue

            # No derivative match
            if not SOFT_REGEX.search(sentence) or SOFT_GEN_REGEX.search(sentence):
                if not (QUANT_REGEX.search(sentence) and LOOSE_GEN_REGEX.search(sentence)) or FV_REGEX.search(sentence):
                    all_discarded.append((url, sentence, "no_match"))
                    used_indices.add(sent_idx)
                continue
            if CP_REGEX.search(sentence):
                # Check for NPNS / Commercial Exemptions
                if EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX.search(sentence):    
                    # This is a physical supply contract, not a financial derivative
                    all_discarded.append((url, sentence, "commercial_contract_exemption"))
                    used_indices.add(sent_idx)
                    continue

            if EQ_SOFT_REGEX.search(sentence) and not EQ_REGEX.search(sentence):
                if "convertible" in sentence.lower() or "warrants" in sentence.lower():
                    if not is_derivative:
                        used_indices.add(sent_idx)
                        continue
            # ═══════════════════════════════════════════════════════════
            # CATEGORY DETECTION
            # ═══════════════════════════════════════════════════════════

            core_categories = get_sentence_categories(sentence)
            specific_cats = core_categories - {"gen", "other"}

            current_instrument = None
            instrument_match = STRICT_REGEX.search(sentence)
            soft_instrument_match = SOFT_REGEX.search(sentence) # Should be safe, since it should've passed the first stage
            if instrument_match:
                current_instrument = instrument_match.group(0)
            elif soft_instrument_match:
                current_instrument = soft_instrument_match.group(0)

            # ═══════════════════════════════════════════════════════════
            # METADATA STAGING
            # ═══════════════════════════════════════════════════════════

            meta = {
                "para_idx": para_idx,
                "sent_idx": sent_idx,
                "sentence": sentence,
                "categories": core_categories,
                "specific_cats": specific_cats,
                "instrument": current_instrument,
                "prev_sentences": sentences[:sent_idx],
                "next_sentences": sentences[sent_idx + 1:],
                "all_sentences": sentences,  # Store for later processing
                "final_category": None,
                "confidence": None,
                "resolution_method": None,
            }

            if not specific_cats:
                if is_table_content:
                    meta["final_category"] = "gen"
                    meta["resolution_method"] = "table_default"
                    continue
                # Generic sentence → defer to ML
                generic_buffer.append(len(sentence_metadata))
                meta["resolution_method"] = "ml_pending"
            else:
                # Direct match → assign immediately
                primary = get_primary_category(core_categories)
                meta["final_category"] = primary
                meta["confidence"] = 1.0
                meta["resolution_method"] = "specific"
                tracker.register_paragraph(sentence, primary)

            sentence_metadata.append(meta)

    # ═════════════════════════════════════════════════════════════════
    # PASS 2: ML BATCH RESOLUTION (for generics)
    # ═════════════════════════════════════════════════════════════════

    if generic_buffer and RESOLVER:
        context_windows = []
        fallback_labels = []

        for idx in generic_buffer:
            m = sentence_metadata[idx]
            ctx = RESOLVER.build_context_window(
                target_sentence=m["sentence"],
                prev_sentences=m["prev_sentences"],
                next_sentences=m["next_sentences"],
            )
            context_windows.append(ctx)

            fb = resolve_generic_reference(
                sentence=m["sentence"],
                paragraph_history=[],
                global_history=[],
                current_para_idx=m["para_idx"],
            ) or "gen"
            fallback_labels.append(fb)

        results = RESOLVER.resolve_batch(context_windows, fallback_labels)

        for pos, (label, conf) in enumerate(results):
            idx = generic_buffer[pos]
            sentence_metadata[idx].update({
                "final_category": label,
                "confidence": conf,
                "resolution_method": "ml" if conf > 0.5 else "fallback",
            })
    # ═════════════════════════════════════════════════════════════════
    # PASS 2.1: GLOBAL INSTRUMENT RESOLUTION (Tracker)
    # ═════════════════════════════════════════════════════════════════
    # Check if we can resolve "gen" sentences using the map we built in Pass 1

    for meta in sentence_metadata:
        # Only check unresolved or generic items
        if meta["final_category"] in {"gen", "other"}:

            resolved_cat = tracker.resolve_instrument(meta["sentence"])

            if resolved_cat:
                meta["final_category"] = resolved_cat
                meta["resolution_method"] = "global_tracker_resolution"
                # Note: We set confidence high so it sticks
                meta["confidence"] = 0.95

    # ═════════════════════════════════════════════════════════════════
    # PASS 2.2: SEQUENTIAL INHERITANCE (Text Extraction Repair)
    # ═════════════════════════════════════════════════════════════════
    # If a generic sentence follows a specific one (skipping intervening tables),
    # it inherits the specific category. This heals paragraphs split by data tables.

    for i in range(1, len(sentence_metadata)):
        curr = sentence_metadata[i]

        # 1. Identify if current sentence is a Table Row
        #    (We check both the resolution method AND the anchor tag for safety)
        is_curr_table = (
            curr.get("resolution_method") == "table_default"
            or TABLE_ANCHOR in curr["sentence"]
        )

        # 2. Target Condition: Current must be Generic/Other AND NOT a table
        #    "If a table row is gen, we don't do any resolving"
        if curr["final_category"] in {"gen", "other"} and not is_curr_table:

            # 3. Lookback Logic: Find nearest NON-TABLE predecessor
            #    "Look back only at non-tabular sentences"
            prev = None
            for j in range(i - 1, -1, -1):
                cand = sentence_metadata[j]

                # Check if candidate is a table row
                is_cand_table = (
                    cand.get("resolution_method") == "table_default"
                    or TABLE_ANCHOR in cand["sentence"]
                )

                if not is_cand_table:
                    prev = cand
                    break

            # 4. Inheritance Logic
            if prev:
                prev_cat = prev["final_category"]
                # If the nearest narrative ancestor was specific, inherit
                if prev_cat and prev_cat not in {"gen", "other"}:
                    curr["final_category"] = prev_cat
                    curr["resolution_method"] = "sequential_inheritance"
    # ═════════════════════════════════════════════════════════════════
    # PASS 2.5: CATEGORY INHERITANCE
    # ═════════════════════════════════════════════════════════════════
    # 1. Collect all SPECIFIC categories found in this document
    doc_specific_cats = set()
    for meta in sentence_metadata:
        if meta["specific_cats"]:
            doc_specific_cats.update(meta["specific_cats"])

    # Remove 'gen' and 'other' just in case
    doc_specific_cats.discard("gen")
    doc_specific_cats.discard("other")

    # 2. Apply Inheritance to remaining "gen" items
    # Only if the document has EXACTLY ONE specific category
    if len(doc_specific_cats) == 1:
        single_cat = list(doc_specific_cats)[0]
        for meta in sentence_metadata:
            # If it is currently "gen" (from ML or Fallback)
            if meta["final_category"] in {"gen", "other"}:
                meta["final_category"] = single_cat
                meta["resolution_method"] = "inheritance"

    # ═════════════════════════════════════════════════════════════════
    # PASS 3: POST-RESOLUTION PROCESSING
    # ═════════════════════════════════════════════════════════════════
    all_discarded.extend(CLEANER.get_discards())
    final_paragraphs_all = []
    all_discarded_final = all_discarded
    used_indices_global = set()

    by_paragraph = {}
    for meta in sentence_metadata:
        para_idx = meta["para_idx"]
        if para_idx not in by_paragraph: by_paragraph[para_idx] = []
        by_paragraph[para_idx].append(meta)

    for para_idx in sorted(by_paragraph.keys()):
        para_metadata = by_paragraph[para_idx]
        used_indices_para = set()
        if not para_metadata: continue
        sentences = para_metadata[0]["all_sentences"]

        for meta in para_metadata:
            # Pass to processor which now handles Resurrection in Case 3
            paras, discs = process_resolved_sentence(
                meta, sentences, used_indices_para, url
            )
            final_paragraphs_all.extend(paras)
            all_discarded_final.extend(discs)

    # ═════════════════════════════════════════════════════════════════
    # SAFETY CHECK: Instrument retention validation
    # ═════════════════════════════════════════════════════════════════

    if final_paragraphs_all:
        validated_paragraphs, validated_categories, validation_discards = validate_instrument_retention(
            [p[0] for p in final_paragraphs_all],
            [p[1] for p in final_paragraphs_all],
            url,
            strict=False,
        )

        # Reconstruct (text, category) tuples with validated texts
        final_paragraphs_all = list(zip(
            validated_paragraphs,
            validated_categories,
        ))

        all_discarded_final.extend(validation_discards)

    return final_paragraphs_all, aggregate_discards(all_discarded_final)


def resolve_generic_reference(
    sentence: str,
    paragraph_history: List[Tuple[int, str, Optional[str]]],
    global_history: List[Tuple[int, int, str, Optional[str], str]],
    current_para_idx: int,
) -> Optional[str]:
    """
    Resolve generic derivative references using hierarchical context.

    Resolution Strategy (in priority order):
    1. Current sentence context signals (debt → IR, currency → FX)
    2. Within-paragraph lookback (previous sentences in same paragraph)
    3. Cross-paragraph lookback (sentence-by-sentence from previous paragraphs)

    Args:
        sentence: Current generic sentence
        paragraph_history: List of (sent_idx, category, instrument) from current paragraph
        global_history: List of (para_idx, sent_idx, category, instrument, text) from all paragraphs
        current_para_idx: Index of current paragraph

    Returns:
        Resolved category or None
    """

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 1: Check for context signals in current sentence
    # ═══════════════════════════════════════════════════════════
    context_scores = {}
    for cat, ctx_regex in CATEGORY_CONTEXT_MAP.items():
        if cat == "gen":
            continue
        matches = ctx_regex.findall(sentence)
        if matches:
            context_scores[cat] = len(matches)

    if context_scores:
        # Found strong context in current sentence
        return max(context_scores.items(), key=lambda x: x[1])[0]

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 2: Within-paragraph lookback (HIGHEST PRIORITY)
    # ═══════════════════════════════════════════════════════════
    # Check if sentence has anaphoric references
    has_anaphoric = bool(LOOSE_GEN_REGEX.search(sentence))

    if has_anaphoric and paragraph_history:
        # Use the most recent category from this paragraph
        last_cat_in_para = paragraph_history[-1][1]
        if last_cat_in_para not in {"gen", "other"}:
            return last_cat_in_para

    # Even without anaphoric references, if we're in same paragraph and
    # haven't seen a category change, inherit previous category
    if paragraph_history:
        last_cat_in_para = paragraph_history[-1][1]
        last_instrument_in_para = paragraph_history[-1][2]

        # Check if the last instrument is still relevant
        if last_instrument_in_para:
            # Very weak check: if last instrument was mentioned recently, inherit
            if last_cat_in_para not in {"gen", "other"}:
                return last_cat_in_para

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 3: Cross-paragraph lookback (SENTENCE-BY-SENTENCE)
    # ═══════════════════════════════════════════════════════════
    if has_anaphoric and global_history:
        # Look backwards through ALL previous sentences across ALL paragraphs
        # Start from most recent and work backwards
        for para_idx, sent_idx, category, instrument, text in reversed(global_history):
            # Only consider sentences from previous paragraphs
            if para_idx >= current_para_idx:
                continue

            # Found a specific category in a previous sentence
            if category not in {"gen", "other"}:
                # Optional: Add proximity check - only look back N sentences
                # For now, we take the most recent specific category
                return category

        # Alternative strategy: look for the most common category in recent history
        # This handles cases where categories alternate
        recent_categories = []
        lookback_limit = min(5, len(global_history))  # Look back max 5 sentences

        for para_idx, sent_idx, category, instrument, text in reversed(
            global_history[-lookback_limit:]
        ):
            if para_idx >= current_para_idx:
                continue
            if category not in {"gen", "other"}:
                recent_categories.append(category)

        if recent_categories:
            # Use most frequent category in recent history
            from collections import Counter

            most_common = Counter(recent_categories).most_common(1)
            if most_common:
                return most_common[0][0]

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 4: Instrument-based inference (WEAKEST)
    # ═══════════════════════════════════════════════════════════
    # Look for any recent instrument mention in global history
    if global_history:
        for para_idx, sent_idx, category, instrument, text in reversed(global_history):
            if para_idx >= current_para_idx:
                continue

            if instrument:
                for cat in PRIORTY:
                    cat_regex = {
                        "ir": IR_REGEX,
                        "fx": FX_REGEX,
                        "cp": CP_REGEX,
                        "eq": EQ_REGEX,
                        "cr": CR_REGEX,
                    
                    }[cat]
                    if cat_regex.search(instrument):
                        return cat

    # Could not resolve
    return None


# =============================================================================
# WORKER FUNCTION (NO DB ACCESS)
# =============================================================================


def process_item_buffered(
    item: Tuple[str, str], report_data_map: dict
) -> Optional[Tuple]:
    url, matches_json = item
    try:
        cik, year = report_data_map.get(url, (None, None))
        # NEW: use ML-enhanced version
        strict_matches, discarded = filter_matches_with_disambiguation(matches_json, url, year)

        return (url, strict_matches, cik, year, discarded)
    except Exception as e:
        logging.error(f"Error processing {url}: {e}")
        return None 


# =============================================================================
# MAIN PROCESSING FUNCTION
# =============================================================================


def process_and_filter_database():
    """Main function to filter database with buffered batch writes."""
    print("=" * 80)
    print("🔧 DATABASE NOISE REDUCTION WITH BATCHED BUFFERED WRITES")
    print("=" * 80)

    # Initialize database
    print("\n📦 Initializing clean database...")
    create_clean_db()

    # Get already processed URLs
    print(f"🔍 Checking for previously processed URLs in {CLEAN_DB_PATH}...")
    processed_urls = get_processed_urls_from_clean_db()
    if processed_urls:
        print(
            f"  • Found {len(processed_urls):,} already processed URLs. They will be skipped."
        )

    # Fetch source data
    print(f"📖 Reading from {SOURCE_DB_PATH}...")
    source_data = get_source_data()

    if not source_data:
        print("❌ No data found in source database.")
        return

    # Filter out already processed URLs
    unprocessed_data = [item for item in source_data if item[0] not in processed_urls]
    if not unprocessed_data:
        print("✅ All URLs have already been processed. Nothing to do.")
        return

    print("🧠 Loading report metadata into memory...")
    report_data_map = get_all_report_data()
    print(f"  • Loaded metadata for {len(report_data_map)} reports.")

    print(f"📊 Found {len(unprocessed_data)} new URLs to process\n")

    global result_buffer, discard_buffer
    result_buffer = []
    discard_buffer = []

    last_flush = time.time()

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Use map() with chunksize for better task batching
        results_iter = executor.map(
            process_item_buffered,
            unprocessed_data,
            [report_data_map] * len(unprocessed_data),
            chunksize=CHUNK_SIZE,
        )

        for result in tqdm(
            results_iter, total=len(unprocessed_data), desc="Filtering URLs"
        ):
            if result is None:
                continue

            url, matches, cik, year, discarded = result
            result_buffer.append((url, matches, cik, year))
            discard_buffer.extend(discarded)

            # Periodic flush
            if len(result_buffer) >= BATCH_SIZE or (
                time.time() - last_flush > FLUSH_INTERVAL
            ):
                flush_buffers()
                last_flush = time.time()

    # Final flush
    if result_buffer or discard_buffer:
        print("\n💾 Final buffer flush...")
        flush_buffers(force=True)

    print_discard_summary()


def print_discard_summary():
    """Print summary of discarded sentences by category."""
    conn = sqlite3.connect(CLEAN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "SELECT discard_reason, COUNT(*) as count FROM discarded_sentences GROUP BY discard_reason ORDER BY count DESC"
        )
        stats = c.fetchall()

        print("\n" + "=" * 80)
        print("📊 DISCARDED SENTENCES SUMMARY")
        print("=" * 80)

        total_discarded = sum(count for _, count in stats)

        for reason, count in stats:
            reason_display = reason.replace("_", " ").title()
            print(f"  • {reason_display}: {count:,}")

        print(f"\n  Total Discarded: {total_discarded:,}")
        print(f"  View details in 'discarded_sentences' table")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"⚠️  Error reading discard summary: {e}")
    finally:
        conn.close()


# =============================================================================
# MAIN EXECUTION
# =============================================================================
# %%
if __name__ == "__main__":
    initialize_resolver(api_url="http://localhost:5000/predict")
    # Run the filtering process
    process_and_filter_database()

# %%
