from enum import Enum
import re
from typing import Any, List, Optional

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


def add_restrictions(
    base: str,
    lookaheads: Optional[List[str]] = None,
    lookbehinds: Optional[List[str]] = None,
    lookahead_sep: Optional[str] = "[- ]"
) -> str:
    pattern = base
    if lookbehinds:
        for lb in lookbehinds:
            pattern = f"(?<!{lb}[- ]){pattern}"
    if lookaheads:
        la_pattern = build_alternation(lookaheads)
        pattern = f"{pattern}(?!{lookahead_sep}{la_pattern})"
    return pattern


def build_regex(keywords: list|set, ignore_case: bool = True, use_sep: bool = True) -> re.Pattern:
    """Build regex for that also builds the alternation."""
    # Add word boundaries (\b) around each keyword to prevent partial matches
    pattern = to_build_alternation(keywords)
    return re.compile(rf"\b{pattern}\b" if use_sep else pattern, re.IGNORECASE if ignore_case else 0)


def to_list(items: Any) -> List[str]:
    """Flattens a mix of Enums, strings, and lists into a list of strings."""
    if not isinstance(items, list):
        items = [items]

    out = []
    for item in items:
        if isinstance(item, Enum):
            out.append(item.value)
        elif isinstance(item, (list, tuple)):
            out.extend(to_list(list(item)))
        else:
            out.append(str(item))
    return out


def to_build_alternation(items: Any, sort_longest_first: bool = True) -> str:
    if not items:
        return ""
    return build_alternation(to_list(items), sort_longest_first=sort_longest_first)


def build_compound(
    prefix: Any,
    core: Any,
    suffix: Optional[Any] = None,
    sep_prefix: str = "[- ]",
    sep_suffix: str = "[- ]",
) -> str:
    prefix_part = f"{to_build_alternation(prefix)}{sep_prefix}" if prefix else ""
    core_part = to_build_alternation(core)
    suffix_part = f"{sep_suffix}{to_build_alternation(suffix)}" if suffix else ""
    return f"{prefix_part}{core_part}{suffix_part}"

def plural(string: str | Enum) -> str:
    if isinstance(string, Enum):
        string = string.value
    assert isinstance(string, str)
    # Removes '?' only if it is at the end of the string
    return string.removesuffix("?")


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
    r"(?<!\bSt\.)" # St. Petersburg
    r"\s+(?=[A-Z_<])"  # Must be followed by Whitespace + Uppercase <-- issue: doesn't consider tags
)


SENTENCE_SPLIT_PATTERN2 = re.compile(
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
    r"(?<!\bSt\.)"
    r"\s+(?=[A-Z0-9_<])"  # Must be followed by Whitespace + Uppercase <-- issue: doesn't consider tags
)

YEAR_REGEX = re.compile(r"\b(19\d{2}|20\d{2})\b")
