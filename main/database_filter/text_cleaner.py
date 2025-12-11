import re
from typing import List, Optional
from derivative_regex import ACCOUNTING_STANDARDS_STRICT_REGEX, NON_DER_CAP_FLOOR_REGEX, ENTITY_EXCLUSION_REGEX, ENTITY_TOKEN, EXCLUDE_REGEX_ACCOUNTING_STD, HEADER_CLEANUP_PATTERNS, HEDGING_CONTEXT_REGEX, MORE_INFO_REGEX, REFERENCE_CLEANUP_REGEX, SENTENCE_SPLIT_PATTERN, SOFT_GEN_REGEX, STANDARD_ID_REGEX, STRICT_NOTIONAL_REGEX, TITLE_CLEANER_REGEX, YEAR_REGEX, cleanup_fragment
from final_verification import QUANT_REGEX
from notional_filter import DATE_DM_REGEX, DATE_MD_REGEX
from table_processor import TABLE_ANCHOR


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
        r"(?<![\$€£¥])"  # 1. Safety: Not preceded by currency symbols
        r"(?:(?<=^)|(?<=\s))"  # 2. Anchor: Start of line OR preceded by whitespace (Fixes \b bug)
        r"(?:"
        r"\(?\d+\)|"  # 3. Matches (1), 1), or 1 (if enclosed)
        r"\d+\."  # 4. Matches 1.
        r")"
        r"(?=\s)",  # 5. Safety: Must be followed by whitespace (Protects "Note 5.")
        re.IGNORECASE,
    )

    dashed_pattern = re.compile(r"\b\d+[-]\d+\b")
    exhibit_pattern = re.compile(
        r"\b(?:exhibit|reference|note|appendix|schedule|article|section|subsection|statement)\b"  # keyword
        r"(?:\s*No\.?)?"  # optional "No." (with or without dot)
        r"\s*\d{1,3}\b",  # number (1–3 digits)
        re.IGNORECASE,
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
        self,
        text: str,
        trigger_regex: re.Pattern,
        reason: str,
        override_regex: Optional[List[re.Pattern]] = None,
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
                if not (
                    override_regex
                    and any(regex.search(sent) for regex in override_regex)
                ):
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

        return self._clean_text_per_sentence(
            text, NON_DER_CAP_FLOOR_REGEX, "loan_features", self.loan_salvation_regex
        )

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
