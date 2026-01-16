import re
from typing import List

def build_alternation(items: List[str], sort_longest_first: bool = True) -> str:
    """
    Build regex alternation pattern, optionally sorting by length (longest first).

    Critical for masking and safe span detection: ensures longer, more specific
    patterns like "interest rate swap" match before shorter ones like "swap".

    Args:
        items: List of regex patterns/terms to combine
        sort_longest_first: If True, sort by (word_count DESC, char_length DESC)

    Returns:
        Alternation pattern string ready for re.compile()

    Example:
        >>> build_alternation(["swap", "interest rate swap", "swap agreement"])
        # Returns: '(?:interest rate swap|swap agreement|swap)'  ✓ Correct order
        # NOT: '(?:swap|interest rate swap|swap agreement)'  ✗ Wrong order
    """
    if not items:
        return ""
    if len(items) == 1:
        return items[0]

    if sort_longest_first:
        # Remove duplicates while preserving order (for tiebreaker)
        unique_items = []
        seen = set()
        for item in items:
            if item not in seen:
                unique_items.append(item)
                seen.add(item)

        # Sort by: (word_count DESC, then char_length DESC)
        unique_items = sorted(
            unique_items,
            key=lambda x: (
                -len(x.split()),  # Primary: word count (descending)
                -len(x),  # Secondary: character length (descending)
            ),
        )
        items = unique_items

    return f'(?:{"|".join(items)})'


def build_regex(keywords: list, ignore_case: bool = True, use_sep: bool = True) -> re.Pattern:
    """Build regex for that also builds the alternation."""
    # Add word boundaries (\b) around each keyword to prevent partial matches
    pattern = build_alternation(keywords)
    return re.compile(rf"\b{pattern}\b" if use_sep else pattern, re.IGNORECASE if ignore_case else 0)


SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<=[.!?])"  # Positive lookbehind for punctuation
    # 1. Protect Initials (e.g., "John H. Smith") -> Capital + Dot
    r"(?<!\b[A-Z]\.)"
    # 2. Protect 2-letter Acronyms (e.g., "U.S.", "U.K.", "N.Y.") -> Cap.Cap.
    r"(?<!\b[A-Z]\.[A-Z]\.)"
    # 3. Protect 3-letter and 4-letter Acronyms (e.g., "U.S.A.", "S.E.C.", "F.A.S.B.") -> Cap.Cap.Cap.Cap. 4-letter acronyms are rare
    r"(?<!\b[A-Z]\.[A-Z]\.[A-Z]\.)"
    r"(?<!\b[A-Z]\.[A-Z]\.[A-Z]\.[A-Z]\.)"
    # 4. Protect common Title/Corp abbreviations (Mixed Case)
    r"(?<!\bInc\.)"
    r"(?<!\bCorp\.)"
    r"(?<!\bLtd\.)"
    r"(?<!\bLlc\.)"
    r"(?<!\bNo\.)"  # "Note No. 5"
    r"(?<!\bNos\.)"  # Plural numbers
    r"(?<!\bVol\.)"  # Volume
    r"(?<!\bvs\.)"  # versus
    r"(?<!\bp\.)"  # p. (page) - FIXED (Separated)
    r"(?<!\bpp\.)"  # pp. (pages) - FIXED (Separated)
    r"(?<!\b[Ee]tc\.)"  # etc.
    r"\s+(?=[A-Z_])"  # Must be followed by Whitespace + Uppercase <-- issue: doesn't consider tags
    r"|"
    r"(?<=[a-z])(?=[A-Z])"  # camelCase boundaries (unchanged)
)
