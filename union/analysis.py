from enum import Enum
import math
from typing import List, Dict, Any, Optional, Set, Tuple, Union
import re
from dataclasses import dataclass, field
import csv
from pathlib import Path
import pandas as pd

from extraction import (
    CONSIST_REGEX,
    NEGATION_REGEX,
    OR_REGEX,
    SUBSET_REGEX,
    QualitativeTerm,
    UnionExtractor,
    SentenceAnalysis,
    MatchType,
    OF_REGEX, STRICT_OF_REGEX,
    QUALITATIVE_MULTIPLIERS,
    REMAIN_REGEX,
    EXCEPT_REGEX,
    SEGMENT_DELIMITER_REGEX,
    SPLIT_ADVERBS_REGEX,
    STRICT_LIST_CONNECTOR,
)
from defs.region_regex import (
    AGG_SET,
    DOMESTIC_SET,
    GLOBAL_SET,
    INT_SET,
    REGION_CODES,
    REGION_NAME_MAP,
    UNK_SET,
    GeoCode,
    Region,
    INT_LANGUAGE_MAP,
    GeoSource,
    _CODE_TO_REGION,
    is_region,
    weighted_division,
    _CODE_TO_LABOR_RATE,
    REGION_LABOR_RATES,
    _CODE_TO_WEIGHT,
    REGION_WEIGHTS,
    COMPOSITE_REGION_MAP,
    COMPOSITE_COUNTRIES,
    get_composite_constituents,
    is_contained,
    IGNORED_REGIONS,
    resolve_remaining_int,
    RegionMatcher,
    refine_generic_code,
)
from defs.region_regex import group_by_scope
from defs.output_enums import (
    Specificity,
    CoverageType,
    SourceType,
    PercentageSourceDetail,
    CountSourceDetail,
    TotalSourceDetail,
    DenominatorSourceDetail,
    DETAIL_TO_SOURCE_TYPE,
    PercentageQualifier,
    NegationType,
    TemporalScope,
    RiskType,
    RiskSignalType,
    RiskActivityClass,
    SuppressedCountType,
    RelationshipStatus,
)

from defs.union_regex import (
    NON_COVERAGE_REGEX,
    NON_UNION_REGEX,
    RELATIONSHIP_NEUTRAL_TERMS,
    RELATIONSHIP_QUALITY_TERMS,
    RELATIONSHIP_NEGATIVE_TERMS,
    UNION_REGEX,
)
from defs.table_processor import TABLE_TOK


def _normalize_domestic_country_code(code: Optional[str]) -> str:
    if not code:
        return "US"
    if code in INT_SET:
        return GeoCode.DOMESTIC.value
    return code



GENERIC_WORKER_TERMS = {
    "employee",
    "worker",
    "laborer",
    "personnel",
    "workforce",
    "associate",
    "staff",
    "employees",
    "workers",
    "laborers",
    "associates",
}

STRICT_EMPLOYMENT_ANCHOR_REGEX = re.compile(
    r"\b(?:employ(?:ee|ees|ed|ment|ing)?|workforce|personnel|headcount|staff)\b",
    re.IGNORECASE,
)


def get_effective_counts(analysis: SentenceAnalysis) -> List[float]:
    """Combines worker_counts and relevant numbers (heuristic filter)."""
    counts = list(analysis.worker_counts)
    for n in analysis.numbers:
        counts.append(n)
    return counts


UNION_MATCH_TYPES = [
    MatchType.UNION_TERM,
    MatchType.COVERAGE_TERM,
    MatchType.SPECIFIC_UNION,
    MatchType.UNION_NAME,
]
NEGATIVE_COVERAGE_MATCH_TYPES = (
    MatchType.NON_UNION,
    MatchType.NON_COVERAGE,
)


def has_status_negation_matches(matches: List[Dict[str, Any]]) -> bool:
    """True when extracted matches include explicit non-coverage/non-union status."""
    return any(m.get("type") in NEGATIVE_COVERAGE_MATCH_TYPES for m in matches)


FILLER = r"(?:,|;|&|[,;\s]?(?:and|or))"
SEP_PATTERN = rf"^(?:{FILLER})(?:\s+\w+){{0,1}}$"
LIST_REGEX = re.compile(SEP_PATTERN, re.IGNORECASE)


def get_text_segments(text: str) -> List[Tuple[int, int, str]]:
    delimiters = list(SEGMENT_DELIMITER_REGEX.finditer(text))
    delimiters.extend(list(SUBSET_REGEX.finditer(text)))
    delimiters.extend(list(EXCEPT_REGEX.finditer(text)))
    delimiters.sort(key=lambda x: x.start())

    # Filter overlaps
    unique_delimiters = []
    last_end = -1
    for m in delimiters:
        if m.start() >= last_end:
            unique_delimiters.append(m)
            last_end = m.end()

    segments = []
    current_start = 0
    for m in unique_delimiters:
        # Return start, end, and the delimiter text itself
        segments.append((current_start, m.end(), m.group(0)))
        current_start = m.end()
    segments.append((current_start, len(text), ""))
    return segments


def get_midpoint(span: Tuple[int, int]) -> float:
    return (span[0] + span[1]) / 2


def get_min_distance_to_matches(
    target_span: Tuple[int, int],
    matches: List[Dict[str, Any]],
    match_types: List[MatchType],
    look_backward: bool = True,
    look_forward: bool = True,
    text: Optional[str] = None,
) -> float:
    t_start, t_end = target_span
    min_dist = float("inf")

    def has_hard_delimiter_between(
        a_start: int, a_end: int, b_start: int, b_end: int
    ) -> bool:
        if text is None:
            return False
        lo = min(a_end, b_end)
        hi = max(a_start, b_start)
        if hi <= lo:
            return False
        return bool(SEGMENT_DELIMITER_REGEX.search(text[lo:hi]))

    for m in matches:
        if m["type"] in match_types:
            m_start, m_end = m["span"]
            dist = None
            if m_end < t_start:
                # Match is before target
                if look_backward:
                    if has_hard_delimiter_between(m_start, m_end, t_start, t_end):
                        continue
                    dist = t_start - m_end
            elif t_end < m_start:
                # Match is after target
                if look_forward:
                    if has_hard_delimiter_between(t_start, t_end, m_start, m_end):
                        continue
                    dist = m_start - t_end
            else:
                # Overlapping
                dist = 0

            if dist is not None and dist < min_dist:
                min_dist = dist
    return min_dist


def construct_window(
    match_span: Tuple[int, int],
    text: str,
    backward: int = 0,
    forward: int = 0,
) -> str:

    start_idx = match_span[0]
    window1 = ""
    window2 = ""
    # Look back window
    if backward:
        window1 = text[max(0, start_idx - backward) : start_idx]
    if forward:
        window2 = text[start_idx : start_idx + forward]

    window = window1 + " " + window2
    return window


def check_local_regex(
    match_span: Tuple[int, int],
    text: str,
    regex_patterns: Union[re.Pattern, List[re.Pattern]],
    backward: int = 40,
    forward: int = 40,
) -> bool:
    """
    Check if a regex pattern matches within distance of the match_span.
    """
    if not match_span:
        return False
    if not isinstance(regex_patterns, list):
        regex_patterns = [regex_patterns]
    window = construct_window(match_span, text, backward, forward)
    for pattern in regex_patterns:
        if bool(pattern.search(window)):
            return True
    return False


def check_local_negation(
    match_span: Tuple[int, int],
    text: str,
    backward: int = 40,
    forward: int = 0,
) -> bool:
    """
    Check if a negation term appears within distance before the matched pattern.
    """
    return check_local_regex(match_span, text, NEGATION_REGEX, backward, forward)


def check_local_union(
    match_span: Tuple[int, int],
    text: str,
    backward: int = 60,
    forward: int = 60,
    allow_non_union: bool = True,
) -> bool:
    """
    Check if a union term appears within distance before the matched pattern.
    """
    if not match_span:
        return False

    regexes = [UNION_REGEX]
    if allow_non_union:
        regexes.append(NON_UNION_REGEX)
    return check_local_regex(match_span, text, regexes, backward, forward)


def apply_coverage_logic(
    data: Dict[str, Any],
    total: float,
    subset: float,
    is_negated: bool,
    notes: Optional[List[str]] = None,
    note_fmt: str = "",
):
    """
    Helper to set covered/not_covered/total counts based on negation status.
    Calculates the 'other' portion (total - subset) and assigns fields.
    """
    other = total - subset
    data["employee_count_total"] = total

    if is_negated:
        data["employee_count_not_covered"] = subset
        data["employee_count_covered"] = other
        data["negated"] = True
        data["negation_type"] = NegationType.NOT_COVERED.value
        status = "not covered"
        other_status = "covered"
    else:
        data["employee_count_covered"] = subset
        data["employee_count_not_covered"] = other
        status = "covered"
        other_status = "not covered"

    if notes is not None and note_fmt:
        msg = note_fmt.format(
            status=status,
            subset=subset,
            total=total,
            other=other,
            other_status=other_status,
        )
        notes.append(msg)


def should_infer_complement(
    percentage: float,
    is_qualitative: bool,
    is_negated: Any,
    has_exceptions: bool = False,
) -> bool:
    """
    Determines if we should infer the complement count (e.g. Covered from Not Covered)
    based on the percentage value and type.

    For qualitative terms (e.g. "Majority"), we avoid inferring the inverse for
    ambiguous middle values when negated.
    e.g. "Majority are non-union" (51%) -> We know 510 are non-union, but we shouldn't
    assert 490 are union.

    If a negated qualitative is below majority-threshold (<49% not covered),
    we allow complement inference because covered is clearly majority.

    # If has_exceptions is True (e.g. "Majority non-union except US"), we NEVER infer
    # the complement, because the exception (US) likely occupies that remainder space.
    """
    # if has_exceptions: # Not using exceptions
    #     return False
    if is_negated and is_qualitative:
        # Clear-majority covered case (e.g., "minority non-union"): infer complement.
        if percentage < 49.0:
            return True
        # Ambiguous/non-extreme negated qualitative range: do not infer inverse.
        if 49.0 <= percentage < 90.0:
            return False
    return True


def split_ambiguous_entry(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Splits an ambiguous, qualitative, negated entry into two:
    1. Known Non-Covered (Explicit)
    2. Unknown Remainder (Eligible for dummy rates)
    """
    cov = item.get("coverage_data", {})

    # Criteria for splitting
    # 1. Must have a total to calculate the split
    total = cov.get("employee_count_total")
    if not total or total <= 0:
        return [item]

    # 2. Must be negated and qualitative
    if not (cov.get("negated") and cov.get("type") == CoverageType.QUALITATIVE.value):
        return [item]

    # 3. Check percentage range (Ambiguous or Exception-based)
    pct = cov.get("percentage")
    if pct is None:
        return [item]

    # If it has exceptions, we ALWAYS split to leave room for the exception
    # If no exceptions, only split if ambiguous (10% < pct < 90%)
    has_exceptions = cov.get("has_exceptions", False)
    is_ambiguous = 10.0 < pct < 90.0

    if not (has_exceptions or is_ambiguous):
        return [item]

    # Perform Split
    subset_count = round((pct / 100.0) * total)
    remainder_count = max(0, total - subset_count)

    # Item A: Known Non-Union
    item_a = item.copy()
    # Deep copy coverage data to avoid reference issues
    item_a["coverage_data"] = cov.copy()
    item_a["coverage_data"].update(
        {
            "employee_count_total": subset_count,  # Scope reduced to this group
            "employee_count_not_covered": subset_count,
            "employee_count_covered": 0,
            "percentage": 0.0,
            "note": (cov.get("note") or "") + " | Split Part A: Known non-union",
        }
    )

    # Item B: Unknown Remainder
    item_b = item.copy()
    item_b["coverage_data"] = cov.copy()
    item_b["coverage_data"].update(
        {
            "employee_count_total": remainder_count,
            "employee_count_not_covered": None,
            "employee_count_covered": None,
            "percentage": None,
            "negated": False,  # Reset negation so it's treated as a fresh unknown record
            "negation_type": None,
            "is_dummy_percent": False,  # Eligible for new dummy rate
            "note": (cov.get("note") or "") + " | Split Part B: Unknown remainder",
            "is_exception_remainder": has_exceptions,
        }
    )
    # Ensure it's marked as a union record so Tracker picks it up
    item_b["is_union"] = True

    return [item_a, item_b]


class SimpleCoverageAnalyzer:
    """
    Handles straightforward sentences where coverage is explicit and singular.
    Criteria:
    - Max 1 Percentage AND/OR Max 1 Worker Count
    - No conflicting Union vs Non-Union terms (mixed signals)
    - No Ratios
    """

    def _handle_qualitative_exception(
        self,
        analysis: SentenceAnalysis,
        effective_counts: List[float],
        data: Dict[str, Any],
        notes: List[str],
    ):
        """
        Handles qualitative statements with exceptions, e.g.
        "All employees are unionized except for those in North America."
        """
        # Only run if we haven't found data yet
        if (
            data.get("percentage") is not None
            or data.get("employee_count_covered") is not None
        ):
            return

        if not (analysis.except_terms or analysis.outside_terms):
            return

        # Check if any geography was actually excluded
        has_excluded_geo = any(m.is_excluded for m in analysis.geo_matches)
        if not has_excluded_geo:
            return

        # Must have union/coverage terms to be relevant
        if not analysis.is_union:
            return

        # Look for qualitative quantity terms (All, Majority, etc.)
        qual_match = next(
            (
                m
                for m in analysis._matches
                if m["type"]
                in (MatchType.QUALITATIVE_TERM, MatchType.QUALITATIVE_MEMBERSHIP)
            ),
            None,
        )

        # If no explicit qualitative term, check for "Global/Total" modifiers which imply "All"
        # e.g. "Our global workforce is unionized except..."
        implicit_all = False
        if not qual_match and analysis.total_modifiers:
            implicit_all = True

        pct = None
        amb_mult = None

        if qual_match:
            qinfo = interpret_qualitative_match(qual_match, analysis, prefer_note=False)
            pct = qinfo.get("percentage")
            amb_mult = qinfo.get("ambiguity_multiplier")
        elif implicit_all:
            pct = 100.0

        if pct is None and amb_mult is None:
            return

        # Check for status negation (e.g. "non-union", "not covered")
        has_status_negation = has_status_negation_matches(analysis._matches)

        if pct is not None:
            data["percentage"] = pct
        if amb_mult is not None:
            data["ambiguity_multiplier"] = amb_mult

        data["type"] = CoverageType.QUALITATIVE.value

        val_str = f"{pct}%" if pct is not None else f"(Ambiguous x{amb_mult})"

        if has_status_negation:
            data["negated"] = True
            data["negation_type"] = NegationType.NOT_COVERED.value
            notes.append(f"Qualitative Exception: {val_str} (Negated Status)")
        else:
            notes.append(f"Qualitative Exception: {val_str}")

    def _handle_one_percent_one_count(
        self,
        analysis: SentenceAnalysis,
        effective_counts: List[float],
        data: Dict[str, Any],
        notes: List[str],
        pct_override: Optional[float] = None,
        pct_match_override: Optional[Dict[str, Any]] = None,
        coverage_type: Optional[str] = None,
        note_prefix: str = "Explicit percentage",
    ):
        """Handles cases with exactly one percentage and one count. Follow standard grammatical flow
        COUNT BEFORE PCT
        NO OR:
            Case 1: For 10000 employees, 60% are unionized.  (Covered Count is PCT * COUNT)
            Case 2: 10000 are unionzied employees, representing 60% of the workforce. (Covered Count is COUNT)
        WITH OR:
            Case 3: We employ 10000 unionized employees, or 60% of out total workforce. (Covered Count is COUNT)

        PCT BEFORE CNT
        Case 4: 60% of our 1000 employees are unionized. (Covered Count is PCT * COUNT) [of]
        Case 4: 60% are unionized, for/from our 1000 employees. (Covered Count is PCT * COUNT) [for/from] (reverse)
        Case 5: 60% are unionized, representing 1000 employees. (Covered Count is COUNT)
        Case 6: 60% are 1000 union employees. (no of, etc) (Covered Count is COUNT)
        Case 7: 60% are unionized, consisting of 1000 union employees. (CONSIST OF) (Covered Count is COUNT)
        Case 8: 60% of employees are unionized, and/with employment of 10,000 people. (Covered Count is PCT * COUNT)

        """
        pct = pct_override if pct_override is not None else analysis.percentages[0]
        count = effective_counts[0]

        data["percentage"] = pct
        data["type"] = coverage_type or CoverageType.EXPLICIT_PERCENT.value
        notes.append(f"{note_prefix}: {pct}%")

        # Locate matches
        pct_match = pct_match_override
        if pct_match is None:
            pct_match = next(
                (
                    m
                    for m in analysis._matches
                    if m["type"] == MatchType.PERCENT and m["val"] == pct
                ),
                None,
            )
        count_match = next(
            (
                m
                for m in analysis._matches
                if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                and m["val"] == count
            ),
            None,
        )

        if not pct_match or not count_match:
            data["employee_count_total"] = count
            return
        pct_before_cnt = False
        # Analyze relationship between matches
        p_span, c_span = pct_match["span"], count_match["span"]
        if p_span[1] <= c_span[0]:
            pct_before_cnt = True
            between = analysis.text[p_span[1] : c_span[0]]
        else:
            between = analysis.text[c_span[1] : p_span[0]]

        # Determine if 'count' represents the Total population
        is_count_total = False

        # 0.1 X% ... consists 1000
        if CONSIST_REGEX.search(between) and pct_before_cnt:
            is_count_total = False
        # 0.2 "500 union ..., representing majority/60% ..." -> Count is covered subset
        elif re.search(r"\brepresent(?:s|ed|ing)?\b", between, re.IGNORECASE):
            is_count_total = False
            notes.append("Logic: REPRESENTING detected -> Count is Covered")
        # 1. Explicit "OR" relationship (Equivalence -> Count is Subset)
        elif OR_REGEX.search(between):
            is_count_total = False
            notes.append("Logic: OR/BY detected -> Count is Covered")
        # 2. Explicit "OF" relationship (Partitive -> Count is Total)
        elif OF_REGEX.search(between):
            is_count_total = True
            notes.append("Logic: OF detected -> Count is Total")
        elif pct_before_cnt:
            is_count_total = False
            notes.append(
                "Logic: PCT before Count (no subset indicator) -> Count is Covered"
            )
        # 3. Proximity to Union Term (Heuristic)
        else:
            dist_pct = get_min_distance_to_matches(
                pct_match["span"],
                analysis._matches,
                UNION_MATCH_TYPES,
                text=analysis.text,
            )
            dist_count = get_min_distance_to_matches(
                count_match["span"],
                analysis._matches,
                UNION_MATCH_TYPES,
                text=analysis.text,
            )
            # If union term is closer to Percentage -> Percentage describes coverage -> Count is Total
            if dist_pct < dist_count:
                is_count_total = True
                notes.append("Logic: Union term closer to PCT -> Count is Total")
            else:
                is_count_total = False
                notes.append("Logic: Union term closer to Count -> Count is Covered")

        # Check for negation on the percentage
        is_negated = False
        if analysis.negation_terms and check_local_negation(
            pct_match["span"], analysis.text, backward=50, forward=50
        ):
            is_negated = True

        if is_count_total:
            ratio = round((pct / 100.0) * count)

            apply_coverage_logic(
                data,
                total=count,
                subset=ratio,
                is_negated=is_negated,
                notes=notes,
                note_fmt="Count (total): {total}. {subset} {status}."
                + (" (negated)" if is_negated else ""),
            )
        else:
            # Count is the subset (Covered or Not Covered)
            total = round(count / (pct / 100.0)) if pct > 0 else count

            apply_coverage_logic(
                data,
                total=total,
                subset=count,
                is_negated=is_negated,
                notes=notes,
                note_fmt="Count ({status}): {subset}. Inferred total {total}.",
            )

    # def _handle_two_counts(
    #     self,
    #     analysis: SentenceAnalysis,
    #     effective_counts: List[float],
    #     data: Dict[str, Any],
    #     notes: List[str],
    # ):
    #     """Handles cases with exactly two counts and no percentages."""
    #     c1, c2 = effective_counts[0], effective_counts[1]

    #     m1 = next(
    #         (
    #             m
    #             for m in analysis._matches
    #             if (MatchType.WORKER_COUNT, MatchType.NUMBER) and m["val"] == c1
    #         ),
    #         None,
    #     )
    #     m2 = next(
    #         (
    #             m
    #             for m in analysis._matches
    #             if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
    #             and m["val"] == c2
    #             and m is not m1
    #         ),
    #         None,
    #     )

    #     is_subset = True
    #     is_exception = False
    #     if m1 and m2:
    #         if m1["span"][0] > m2["span"][0]:
    #             m1, m2 = m2, m1
    #         text_between = analysis.text[m1["span"][1] : m2["span"][0]]

    #         if OF_REGEX.search(text_between) or check_local_regex(
    #             m1["span"], analysis.text, OF_REGEX, backward=25, forward=0
    #         ):
    #             is_subset = True
    #         elif EXCEPT_REGEX.search(text_between):
    #             is_subset = True
    #             is_exception = True
    #             notes.append("Logic: Exception detected -> Subset with inverted status")
    #         elif re.search(r"\band\b", text_between, re.IGNORECASE):
    #             # Check for multiple specific unions to infer disjoint sets (Sum)
    #             union_matches = [
    #                 m
    #                 for m in analysis._matches
    #                 if m["type"] in (MatchType.SPECIFIC_UNION, MatchType.UNION_NAME)
    #             ]
    #             unique_unions = {m["val"].lower() for m in union_matches}

    #             if len(unique_unions) >= 2:
    #                 is_subset = False
    #                 notes.append("Logic: 'and' with multiple unions -> Sum")

    #     if is_subset:
    #         total, part = max(c1, c2), min(c1, c2)
    #         assert m1 and m2
    #         if is_exception:
    #             # Exception Logic: Status of Part is opposite of Total
    #             # 1. Determine status of Total (Main Clause)
    #             total_match = m1 if m1["val"] == total else m2

    #             # Check proximity to Union terms (Positive)
    #             dist_union = get_min_distance_to_matches(
    #                 total_match["span"], analysis._matches, UNION_MATCH_TYPES
    #             )

    #             # Check proximity to Non-Union terms (Negative)
    #             dist_non_union = get_min_distance_to_matches(
    #                 total_match["span"], analysis._matches, [MatchType.NON_UNION, MatchType.NON_COVERAGE]
    #             )

    #             # Default: If Total is near Union -> Part is Not Covered (Negated)
    #             part_is_negated = True

    #             if dist_non_union < dist_union and dist_non_union < 100:
    #                 # Total is Non-Union -> Part is Covered
    #                 part_is_negated = False

    #             apply_coverage_logic(
    #                 data,
    #                 total=total,
    #                 subset=part,
    #                 is_negated=part_is_negated,
    #                 notes=notes,
    #                 note_fmt="Exception ({status}): {subset} of {total}.",
    #             )
    #         else:
    #             # Standard Subset Logic
    #             # Check if 'part' is associated with union
    #             part_match = m1 if m1["val"] == part else m2
    #             if part_match:
    #                 dist = get_min_distance_to_matches(
    #                     part_match["span"], analysis._matches, UNION_MATCH_TYPES
    #                 )
    #                 if dist < 100:
    #                     is_negated = False
    #                     if analysis.negation_terms:
    #                         if check_local_negation(
    #                             part_match["span"], analysis.text, backward=50, forward=50
    #                         ):
    #                             is_negated = True

    #                     apply_coverage_logic(
    #                         data,
    #                         total=total,
    #                         subset=part,
    #                         is_negated=is_negated,
    #                         notes=notes,
    #                         note_fmt="Count ({status}): {subset} of {total}. Inferred {other} {other_status}.",
    #                     )
    #                 else:
    #                     # Part is not near union term -> Assume it's just a subset (e.g. "20 in marketing")
    #                     # Record total only
    #                     data["employee_count_total"] = total
    #                     notes.append(
    #                         f"Count (total): {total}. Subset {part} not associated with union."
    #                     )
    #     else:
    #         total = c1 + c2
    #         apply_coverage_logic(
    #             data,
    #             total=total,
    #             subset=total,
    #             is_negated=bool(analysis.negation_terms),
    #             notes=notes,
    #             note_fmt="Count ({status}): {subset} (Sum of {other} + {subset} is wrong here, logic handled sum)",
    #         )
    #         # Fix note for sum case
    #         notes[-1] = (
    #             f"Count ({'not covered' if analysis.negation_terms else 'covered'}): {c1} + {c2} = {total}"
    #         )

    #     if data.get("employee_count_total", 0) > 0:
    #         covered = data.get("employee_count_covered", 0) or 0
    #         pct = (covered / data["employee_count_total"]) * 100.0
    #         data["percentage"] = round(pct, 2)
    #         data["type"] = CoverageType.CALCULATED.value
    #         notes.append(f"Calculated percentage: {data['percentage']}%")

    def _handle_single_value(
        self,
        analysis: SentenceAnalysis,
        effective_counts: List[float],
        data: Dict[str, Any],
        notes: List[str],
    ):
        """Handles cases with one percentage OR one count."""
        if analysis.percentages:
            data["percentage"] = analysis.percentages[0]
            data["type"] = CoverageType.EXPLICIT_PERCENT.value
            notes.append(f"Explicit percentage: {data['percentage']}%")

        if effective_counts:
            count = effective_counts[0]
            count_match = next(
                (
                    m
                    for m in analysis._matches
                    if m["val"] == count
                    and m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                ),
                None,
            )

            is_associated = False
            if count_match:
                dist = get_min_distance_to_matches(
                    count_match["span"],
                    analysis._matches,
                    UNION_MATCH_TYPES,
                    text=analysis.text,
                )
                if dist < 100:
                    is_associated = True

            # Handle Exception Logic (High Priority)
            # "Except for 500, the rest are non-union" -> 500 is Covered
            if analysis.except_terms and count_match:
                # 1. Check local status of the count (Explicit)
                dist_neg = get_min_distance_to_matches(
                    count_match["span"],
                    analysis._matches,
                    list(NEGATIVE_COVERAGE_MATCH_TYPES),
                    text=analysis.text,
                )
                dist_pos = get_min_distance_to_matches(
                    count_match["span"],
                    analysis._matches,
                    UNION_MATCH_TYPES,
                    text=analysis.text,
                )

                is_exception_covered = None

                if dist_neg < 50 and dist_neg < dist_pos:
                    is_exception_covered = (
                        False  # Locally negated ("Except 500 non-union")
                    )
                elif dist_pos < 50:
                    is_exception_covered = True  # Locally union ("Except 500 union")
                else:
                    # 2. Infer from global context (Invert Main Clause)
                    # If sentence has negation, Main is Negative -> Exception is Positive
                    is_exception_covered = bool(analysis.negation_terms)

                apply_coverage_logic(
                    data,
                    total=count,
                    subset=count,
                    is_negated=not is_exception_covered,
                    notes=notes,
                    note_fmt="Exception count ({status}): {subset}",
                )
                data["type"] = CoverageType.CALCULATED.value
                return

            # Check for qualitative terms (e.g. "majority", "most")
            # If present, map to a percentage and run one-count/one-percent logic.
            qual_match = next(
                (
                    m
                    for m in analysis._matches
                    if m["type"]
                    in (MatchType.QUALITATIVE_TERM, MatchType.QUALITATIVE_MEMBERSHIP)
                ),
                None,
            )

            if qual_match:
                union_spans = [
                    m["span"]
                    for m in analysis._matches
                    if m["type"] in UNION_MATCH_TYPES
                ]
                qual_span = qual_match["span"]
                has_union_before = any(s[0] < qual_span[0] for s in union_spans)
                has_union_after = any(s[0] > qual_span[1] for s in union_spans)

                # If union indicators appear after the qualitative term (and not before),
                # treat it as a qualitative percentage over the count.
                if has_union_after and not has_union_before:
                    qinfo = interpret_qualitative_match(
                        qual_match, analysis, prefer_note=False
                    )
                    pct = qinfo.get("percentage")
                    amb_mult = qinfo.get("ambiguity_multiplier")
                    if pct is not None:
                        data["percentage"] = pct
                    if amb_mult is not None:
                        data["ambiguity_multiplier"] = amb_mult
                    data["employee_count_total"] = count
                    data["type"] = CoverageType.QUALITATIVE.value
                    val_str = f"{pct}%" if pct is not None else f"(Ambiguous x{amb_mult})"
                    notes.append(
                        f"Qualitative '{qual_match['text']}' after count -> Percent: {val_str}"
                    )
                    return

                # For qualitative+count cases (default), do not apply qualitative percentages.
                # Treat the raw count as the covered/not-covered subset, with total = count.
                has_status_negation = has_status_negation_matches(analysis._matches)
                data["percentage"] = None
                data["type"] = CoverageType.CALCULATED.value
                apply_coverage_logic(
                    data,
                    total=count,
                    subset=count,
                    is_negated=has_status_negation,
                    notes=notes,
                    note_fmt=f"Qualitative '{qual_match['text']}' with explicit count -> Count ({{status}}): {{subset}}",
                )

            elif analysis.has_remaining_other:
                data["employee_count_total"] = count
                data["type"] = CoverageType.REMAINING.value
                if analysis.negation_terms:
                    data["negated"] = True
                    data["negation_type"] = NegationType.NOT_COVERED.value
                notes.append(f"Count (total): {count} (remaining/rest detected)")

            elif is_associated:
                apply_coverage_logic(
                    data,
                    total=count,
                    subset=count,
                    is_negated=bool(analysis.negation_terms),
                    notes=notes,
                    note_fmt="Count ({status}): {subset}",
                )
                data["type"] = CoverageType.CALCULATED.value
            elif (
                analysis.negation_terms
            ):  # single count ..... are nonunion at this stage.
                apply_coverage_logic(
                    data,
                    total=count,
                    subset=count,
                    is_negated=True,
                    notes=notes,
                    note_fmt="Count ({status}): {subset}",
                )
            else:
                data["employee_count_total"] = count
                notes.append(f"Count (total): {count} (no union association)")

    def _handle_qualitative_zero(
        self,
        analysis: SentenceAnalysis,
        effective_counts: List[float],
        data: Dict[str, Any],
        notes: List[str],
    ):
        """Handles cases like 'None are represented'."""
        # Don't override if we have qualitative terms that will be handled later
        if analysis.qualitative_terms or analysis.qualitative_membership_terms:
            return

        if (
            not analysis.percentages
            and not effective_counts
            and analysis.negation_terms
        ):
            data.update(
                {
                    "percentage": 0.0,
                    "negated": True,
                    "negation_type": NegationType.ZERO_COVERAGE.value,
                    "type": CoverageType.QUALITATIVE.value,
                }
            )
            notes.append("Qualitative zero coverage detected")

    def _handle_remaining(
        self,
        analysis: SentenceAnalysis,
        effective_counts: List[float],
        data: Dict[str, Any],
        notes: List[str],
    ):
        """Handles cases like 'The remaining are represented'."""
        if (
            not analysis.percentages
            and not effective_counts
            and analysis.has_remaining_other
        ):
            data.update(
                {
                    "percentage": None,
                    "negated": True if analysis.negation_terms else False,
                    "negation_type": (
                        NegationType.ZERO_COVERAGE.value
                        if analysis.negation_terms
                        else None
                    ),
                    "type": CoverageType.REMAINING.value,
                }
            )
            if analysis.negation_terms:
                notes.append("Qualitative zero coverage detected")

    def analyze(self, analysis: SentenceAnalysis) -> Dict[str, Any]:
        data = {
            "percentage": None,
            "employee_count_covered": None,
            "employee_count_not_covered": None,
            "employee_count_total": None,
            "negated": False,
            "negation_type": None,
            "type": CoverageType.NONE.value,
            "note": None,
        }

        notes = []
        if not analysis.is_union:
            data["type"] = None
            return data

        effective_counts = get_effective_counts(analysis)

        if len(analysis.percentages) == 1 and len(effective_counts) == 1:
            self._handle_one_percent_one_count(analysis, effective_counts, data, notes)
        # elif not analysis.percentages and len(effective_counts) == 2:
        #     self._handle_two_counts(analysis, effective_counts, data, notes)
        else:
            self._handle_single_value(analysis, effective_counts, data, notes)

        # Try qualitative exception logic if still no data
        self._handle_qualitative_exception(analysis, effective_counts, data, notes)

        # Fallback to qualitative zero if no other data was found
        if (
            data.get("percentage") is None
            and data.get("employee_count_covered") is None
            and data.get("employee_count_not_covered") is None
        ):
            self._handle_remaining(analysis, effective_counts, data, notes)
            if not data.get("type") == CoverageType.REMAINING.value:
                self._handle_qualitative_zero(analysis, effective_counts, data, notes)

        data["note"] = " | ".join(notes) if notes else "Simple Analysis (No Data)"
        return data


class UnionExtraAnalyzer:
    """
    Analyzes sentences where the union population is the denominator.
    These are often contextual statements about negotiations or relationships
    rather than broad coverage data.
    """

    def analyze_denominator(self, analysis: SentenceAnalysis) -> Dict[str, Any]:
        """
        Creates a skeleton dictionary for union denominator sentences.
        This is treated as a special type of coverage data for context.
        """
        counts = get_effective_counts(analysis)
        # If counts exist in a denominator sentence (e.g. "Of our 500 unionized employees..."),
        # that count represents the unionized (covered) population.
        covered_count = max(counts) if counts else None

        return {
            "type": CoverageType.UNION_CONTEXT.value,
            "note": "Union is denominator. Parsed for context.",
            "percentages": analysis.percentages,
            "counts": counts,
            "relationship_status": determine_relationship_status(analysis),
            "risk_terms": analysis.risk_terms,
            # Standard coverage fields are null
            "percentage": None,
            "employee_count_covered": covered_count,
            "employee_count_not_covered": None,
            "employee_count_total": None,
            "negated": bool(analysis.negation_terms),
            "negation_type": None,
            "qualitative_bounds": None,
        }

    def create_risk_item(
        self,
        sentence: str,
        analysis: SentenceAnalysis,
        is_historical: bool = False,
        item1a_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Creates a risk item dictionary if relevant terms are found.
        """
        is_conditional = analysis.has_conditional
        is_future = analysis.has_future

        temporal_scope = TemporalScope.CURRENT.value
        if is_historical:
            temporal_scope = TemporalScope.HISTORICAL.value
        elif is_future:
            temporal_scope = TemporalScope.FUTURE.value
        elif is_conditional:
            temporal_scope = TemporalScope.CONDITIONAL.value

        has_legal_requirement = bool(analysis.legal_requirement_terms)
        has_boilerplate = bool(analysis.boilerplate_terms)
        has_relationship = bool(
            analysis.relationship_terms or analysis.relationship_quality_terms
        )
        has_explicit_risk = bool(analysis.risk_terms)
        has_generic_risk = bool(analysis.generic_risk_terms)
        has_labor_anchor = bool(
            analysis.union_terms
            or analysis.negation_terms
            or analysis.coverage_terms
            or analysis.works_councils
            or analysis.supplier_terms
        )
        has_negative_relationship_quality = any(
            q.lower() in RELATIONSHIP_NEGATIVE_TERMS
            for q in analysis.relationship_quality_terms
        )

        if item1a_mode:
            has_signal = bool(
                analysis.union_terms
                or analysis.negation_terms
                or has_explicit_risk
                or has_generic_risk
                or analysis.supplier_terms
                or has_relationship
                or has_legal_requirement
                or has_boilerplate
            )
        else:
            # Item 1 should be stricter: union mention alone is not a risk row.
            has_signal = bool(
                has_explicit_risk
                or (has_generic_risk and has_labor_anchor)
                or (has_negative_relationship_quality and has_labor_anchor)
                or has_legal_requirement
                or has_boilerplate
            )

        if not has_signal:
            return {}

        # Detect whether any explicit risk term is locally negated
        risk_matches = [
            m for m in analysis._matches if m.get("type") == MatchType.RISK_TERM
        ]
        risk_negated = any(
            check_local_negation(m["span"], analysis.text, backward=30, forward=10)
            for m in risk_matches
        )
        relationship_status = determine_relationship_status(analysis)
        labor_keywords = analysis.sentence_union_keywords or analysis.union_terms
        risk_keywords = analysis.risk_terms + analysis.generic_risk_terms

        if has_explicit_risk or (has_generic_risk and has_labor_anchor):
            risk_signal_type = RiskSignalType.RISK_EVENT.value
        elif has_legal_requirement:
            risk_signal_type = RiskSignalType.LEGAL_REQUIREMENT.value
        elif has_boilerplate:
            risk_signal_type = RiskSignalType.BOILERPLATE.value
        elif has_relationship:
            risk_signal_type = RiskSignalType.RELATIONSHIP_CONTEXT.value
        else:
            risk_signal_type = RiskSignalType.OTHER_CONTEXT.value

        activity_class = RiskActivityClass.ACTUAL.value
        if item1a_mode:
            has_quant_signal = bool(
                analysis.percentages
                or analysis.worker_counts
                or analysis.bargaining_unit_counts
            )
            has_union_activity = bool(analysis.union_terms or analysis.negation_terms)
            has_strong_actual = has_quant_signal and has_union_activity
            if not has_strong_actual and (
                is_historical or is_future or is_conditional or risk_negated
            ):
                activity_class = RiskActivityClass.POTENTIAL.value

        return {
            "type": (
                RiskType.UNION_RISK.value
                if analysis.union_terms or analysis.risk_terms
                else RiskType.LABOR_RISK.value
            ),
            "risk_signal_type": risk_signal_type,
            "activity_class": activity_class,
            "sentence": sentence,
            "labor_keywords": labor_keywords,
            "risk_keywords": risk_keywords,
            "relationship_keywords": analysis.relationship_terms,
            "relationship_quality_keywords": analysis.relationship_quality_terms,
            "relationship_status": relationship_status,
            "third_party": analysis.supplier_terms,
            "union_mention": analysis.union_terms,
            "temporal_scope": temporal_scope,
            "conditional": is_conditional,
            "risk_negated": risk_negated,
            "has_legal_requirement": has_legal_requirement,
            "has_boilerplate": has_boilerplate,
            "legal_requirement_keywords": analysis.legal_requirement_terms,
            "works_councils": analysis.works_councils,
            "boilerplate_keywords": analysis.boilerplate_terms,
            "note": None,
            "is_union": analysis.is_union,
        }


class RiskDigest:
    """
    Aggregates risk items into compact summaries for downstream reporting.
    """

    def summarize(self, risk_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        by_signal_type: Dict[str, int] = {}
        by_temporal_scope: Dict[str, int] = {}
        by_activity_class: Dict[str, int] = {}
        relationship_status_counts: Dict[str, int] = {}
        risk_term_counts: Dict[str, int] = {}
        works_councils: Dict[str, int] = {}
        labor_term_counts: Dict[str, int] = {}
        relationship_term_counts: Dict[str, int] = {}
        supplier_term_counts: Dict[str, int] = {}
        legal_requirement_term_counts: Dict[str, int] = {}
        boilerplate_term_counts: Dict[str, int] = {}
        global_keywords_seen: Set[str] = set()
        global_keywords: List[str] = []
        negated_count = 0
        risk_negated_count = 0
        conditional_count = 0
        coverage_totals = {
            "cov": 0.0,
            "not_cov": 0.0,
            "tot": 0.0,
            "bu": 0.0,
            "pct": 0.0,
        }
        coverage_has_signal = False
        cov_has_count = False
        tot_has_count = False
        pct_has_direct = False
        pct_has_explicit = False
        pct_has_qualitative = False

        def _register_keyword(term: str) -> None:
            if not term or term in global_keywords_seen:
                return
            global_keywords_seen.add(term)
            global_keywords.append(term)

        for item in risk_items:
            r_type = item.get("type")
            if r_type:
                by_type[r_type] = by_type.get(r_type, 0) + 1
            signal_type = item.get("risk_signal_type")
            if signal_type:
                by_signal_type[signal_type] = by_signal_type.get(signal_type, 0) + 1

            t_scope = item.get("temporal_scope")
            if t_scope:
                by_temporal_scope[t_scope] = by_temporal_scope.get(t_scope, 0) + 1
            activity_class = item.get("activity_class")
            if activity_class:
                by_activity_class[activity_class] = (
                    by_activity_class.get(activity_class, 0) + 1
                )

            rel_status = item.get("relationship_status")
            if rel_status:
                relationship_status_counts[rel_status] = (
                    relationship_status_counts.get(rel_status, 0) + 1
                )

            for t in item.get("risk_keywords", []) or []:
                risk_term_counts[t] = risk_term_counts.get(t, 0) + 1
                _register_keyword(t)
            for t in item.get("labor_keywords", []) or []:
                labor_term_counts[t] = labor_term_counts.get(t, 0) + 1
                _register_keyword(t)
            for t in item.get("relationship_keywords", []) or []:
                relationship_term_counts[t] = relationship_term_counts.get(t, 0) + 1
                _register_keyword(t)
            for t in item.get("relationship_quality_keywords", []) or []:
                _register_keyword(t)
            for t in item.get("third_party", []) or []:
                supplier_term_counts[t] = supplier_term_counts.get(t, 0) + 1
                _register_keyword(t)
            for t in item.get("works_councils", []) or []:
                works_councils[t] = works_councils.get(t, 0) + 1
                _register_keyword(t)

            for t in item.get("legal_requirement_keywords", []) or []:
                legal_requirement_term_counts[t] = (
                    legal_requirement_term_counts.get(t, 0) + 1
                )
                _register_keyword(t)
            for t in item.get("boilerplate_keywords", []) or []:
                boilerplate_term_counts[t] = boilerplate_term_counts.get(t, 0) + 1
                _register_keyword(t)

            if item.get("conditional"):
                conditional_count += 1
            if item.get("negated"):
                negated_count += 1
            if item.get("risk_negated"):
                risk_negated_count += 1

            coverage = item.get("coverage_data") or {}
            if coverage:
                if coverage.get("employee_count_covered") is not None:
                    cov_has_count = True
                if coverage.get("employee_count_total") is not None:
                    tot_has_count = True
                if coverage.get("percentage") is not None:
                    pct_has_direct = True
                if coverage.get("is_explicit_percent") or coverage.get("type") == CoverageType.EXPLICIT_PERCENT.value:
                    pct_has_explicit = True
                if coverage.get("type") == CoverageType.QUALITATIVE.value or coverage.get("qualitative_bounds"):
                    pct_has_qualitative = True
                for key, short_k in (
                    ("employee_count_covered", "cov"),
                    ("employee_count_not_covered", "not_cov"),
                    ("employee_count_total", "tot"),
                    ("bargaining_unit_counts", "bu"),
                    ("percentage", "pct"),
                ):
                    val = coverage.get(key)
                    if val is not None:
                        coverage_totals[short_k] += float(val)
                        coverage_has_signal = True

        out = {
            "n": len(risk_items),
            "typ": by_type,
            "sig": by_signal_type,
            "temp": by_temporal_scope,
            "act": by_activity_class,
            "rel": relationship_status_counts,
            "neg_n": negated_count,
            "r_neg_n": risk_negated_count,
            "cond_n": conditional_count,
            "kw_r": risk_term_counts,
            "kw_l": labor_term_counts,
            "kw_rel": relationship_term_counts,
            "kw_3p": supplier_term_counts,
            "kw_leg": legal_requirement_term_counts,
            "kw_bp": boilerplate_term_counts,
            "kw_g": global_keywords,
        }
        if coverage_has_signal:
            # Recalculate mathematically accurate percentage if counts exist
            if coverage_totals["tot"] > 0:
                coverage_totals["pct"] = round((coverage_totals["cov"] / coverage_totals["tot"]) * 100.0, 2)

            out["cov_t"] = {
                k: (v if v > 0 else None) for k, v in coverage_totals.items()
            }
            out["cov_t_meta"] = {
                "cov_has_count": cov_has_count,
                "tot_has_count": tot_has_count,
                "pct_from_counts": bool(coverage_totals["tot"] > 0 and cov_has_count),
                "pct_has_direct": pct_has_direct,
                "pct_has_explicit": pct_has_explicit,
                "pct_has_qualitative": pct_has_qualitative,
            }
            if (
                out["cov_t"].get("cov") is None
                and out["cov_t"].get("not_cov") is None
                and out["cov_t"].get("tot") is None
                and out["cov_t"].get("bu") is None
                and out["cov_t"].get("pct") is None
            ):
                out.pop("cov_t", None)
                out.pop("cov_t_meta", None)

        # Drop empty sections for compactness.
        compact = {"n": out.get("n", 0)}
        for key in (
            "typ",
            "sig",
            "temp",
            "act",
            "rel",
            "kw_r",
            "kw_l",
            "kw_rel",
            "kw_3p",
            "kw_leg",
            "kw_bp",
        ):
            if out.get(key):
                compact[key] = out[key]
        for key in ("neg_n", "r_neg_n", "cond_n"):
            if out.get(key):
                compact[key] = out[key]
        if out.get("kw_g"):
            compact["kw_g"] = out["kw_g"]
        if out.get("cov_t"):
            compact["cov_t"] = out["cov_t"]
        if out.get("cov_t_meta"):
            compact["cov_t_meta"] = out["cov_t_meta"]

        return compact


EXTERNAL_COUNTS: Dict[Tuple[int, int], float] = {}
DATA_LOADED = False

def load_external_counts(path="employee_processed.csv"):
    global DATA_LOADED
    if DATA_LOADED:
        return
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]

    if {"cik", "year", "emp"}.issubset(df.columns):
        df = df[["cik", "year", "emp"]].dropna()
        df["cik"] = pd.to_numeric(df["cik"], errors="coerce")
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df["emp"] = pd.to_numeric(df["emp"], errors="coerce")

        df = df.dropna()
        df["cik"] = df["cik"].astype(int)
        df["year"] = df["year"].astype(int)

        EXTERNAL_COUNTS.update(df.set_index(["cik", "year"])["emp"].to_dict())  # type: ignore

    DATA_LOADED = True


def get_external_global_count(
    cik: int, year: Optional[int]
) -> Optional[float]:
    """
    Prefer the exact year when available; otherwise fall back to any other year
    for the same CIK (closest year if reporting_year is provided).
    """
    load_external_counts()
    if year is not None:
        direct = EXTERNAL_COUNTS.get((cik, year))
        if direct:
            return direct

    candidates = [
        (y, v) for (c, y), v in EXTERNAL_COUNTS.items() if c == cik and v
    ]
    if not candidates:
        return None

    if year is None:
        # No target year: choose most recent available
        y, v = max(candidates, key=lambda t: t[0])
        return v

    # Closest year by absolute distance; tie-breaker = latest year
    candidates.sort(key=lambda t: (abs(t[0] - year), -t[0]))
    return candidates[0][1]


def apply_qualitative_multipliers(
    raw_pct: float, span: Tuple[int, int], text: str, apply: bool = False
) -> Tuple[float, Optional[str]]:
    """
    Applies qualitative multipliers (e.g. "almost", "nearly") to a percentage.
    """
    if not apply:
        return raw_pct, None

    # Look back window (e.g. "almost 20%")
    window = construct_window(span, text, backward=30)

    for pattern, mult in QUALITATIVE_MULTIPLIERS:
        if pattern.search(window):
            new_pct = raw_pct * mult
            # Cap at 100% if original was <= 100
            if new_pct > 100.0 and raw_pct <= 100.0:
                new_pct = 100.0
            return (
                round(new_pct, 2),
                f"Adjusted from {raw_pct}% (x{mult}) via term matching '{pattern.pattern}'",
            )

    return raw_pct, None


def interpret_qualitative_match(
    match: Dict[str, Any],
    analysis: SentenceAnalysis,
    backward: int = 40,
    prefer_note: bool = False,
) -> Dict[str, Any]:
    """
    Interpret a qualitative match and return a dictionary with keys:
      - percentage: Optional[float]
      - type: Optional[str] (CoverageType value)
      - qualitative_bounds: Optional[Tuple[float,float]]
      - note: Optional[str]
      - is_negated: bool
      - ambiguity_multiplier: Optional[float]

    """
    res: Dict[str, Any] = {
        "percentage": None,
        "type": None,
        "qualitative_bounds": None,
        "note": None,
        "is_negated": False,
        "ambiguity_multiplier": None,
    }

    # If match is provided, focus on it to avoid cross-contamination from other terms (e.g. "none")
    if match:
        qual_matches = [match]
    else:
        qual_matches = [
            m
            for m in analysis._matches
            if m["type"]
            in (MatchType.QUALITATIVE_TERM, MatchType.QUALITATIVE_MEMBERSHIP)
        ]

    best_pct = None
    best_is_neg = False
    best_pattern = None
    best_bounds = None

    for qm in qual_matches:
        term = qm.get("term_obj")
        if not term or not isinstance(term, QualitativeTerm):
            continue

        is_locally_negated = check_local_negation(
            qm["span"], analysis.text, backward=backward
        )

        # Absolute terms: treat as their positive_pct (but still consider for min)
        if term.is_absolute:
            pct = term.positive_pct
        else:
            pct = term.get_percentage(is_negated=is_locally_negated)

        if pct is None and term.ambiguity_multiplier is None:
            continue

        # Choose the lowest percentage
        if pct is not None:
            if best_pct is None or pct < best_pct:
                best_pct = pct
                best_is_neg = is_locally_negated
                best_pattern = qm.get("pattern_str", qm.get("text", ""))
                if term.lower_bound is not None and term.upper_bound is not None:
                    best_bounds = (term.lower_bound, term.upper_bound)

        if term.ambiguity_multiplier is not None:
            # Prioritize the lowest multiplier found (e.g. "few" 0.2 over "some" 1.0)
            if (
                res["ambiguity_multiplier"] is None
                or term.ambiguity_multiplier < res["ambiguity_multiplier"]
            ):
                res["ambiguity_multiplier"] = term.ambiguity_multiplier

    if best_pct is None and res["ambiguity_multiplier"] is None:
        return res

    res["percentage"] = best_pct
    res["is_negated"] = best_is_neg
    # Absolute terms are still qualitative in our schema
    res["type"] = CoverageType.QUALITATIVE.value

    if (not best_is_neg) and best_bounds is not None:
        res["qualitative_bounds"] = best_bounds

    if prefer_note:
        res["note"] = f"Qualitative: -> {best_pct}%"

    return res


# Pre‑compiled regexes
_RANGE_TO_THROUGH = re.compile(
    r"\b((?<!compared\s)to|through)(?:\s+\S+){0,2}$", re.IGNORECASE
)
_RANGE_AND = re.compile(r"\band\b", re.IGNORECASE)
_RANGE_BETWEEN = re.compile(r"\bbetween\b", re.IGNORECASE)


def is_range_context(text: str, span1: Tuple[int, int], span2: Tuple[int, int]) -> bool:
    """
    Checks if the text between two spans indicates a range (e.g. "10 to 20",
    "between 10 and 20").
    """
    # Overlapping or reversed spans → not a range
    if span1[1] >= span2[0]:
        return False

    text_between = text[span1[1] : span2[0]].strip()

    # Case 1: "10 to 20", "10 through 20"
    if _RANGE_TO_THROUGH.search(text_between):
        return True

    if len(text_between) > 20:
        return False

    # Case 2: "between 10 and 20"
    if _RANGE_AND.search(text_between):
        pre_text = construct_window(span1, text, backward=15)
        if _RANGE_BETWEEN.search(pre_text):
            return True

    return False


class ComplexCoverageAnalyzer:
    """
    Handles complex scenarios: mixed coverage, ratios, inferred totals, percent of percent.
    """

    # Uses a different subset regex made for percentage cases
    subset_regex = re.compile(
        r"\bof\s+(?:whom|which|these|those|them)\b", re.IGNORECASE
    )
    subgroup_breakdown_regex = re.compile(
        r"\b(?:represented|covered|affiliated)\s+by\b", re.IGNORECASE
    )

    def __init__(
        self,
        analysis: SentenceAnalysis,
        total_count: Optional[float],
        domestic_country_code: str = "US",
    ):
        self.analysis = analysis
        self.context_total = total_count
        self.domestic_country_code = domestic_country_code
        self.data = {
            "percentage": None,
            "employee_count_covered": None,
            "employee_count_not_covered": None,
            "employee_count_total": None,
            "negated": False,
            "negation_type": None,
            "type": CoverageType.NONE.value,
            "qualitative_bounds": None,
            "note": None,
            "_count_assignments": [],
        }
        self.local_assignments = []

    def analyze(self) -> Dict[str, Any]:
        if not self.analysis.is_union:
            return self.data

        counts = get_effective_counts(self.analysis)
        # 0. Ranges (High priority)
        if self._handle_ranges(counts=counts):
            return self.data

        # 1. Ratio Match (1 pct, 2 counts)
        if self._handle_ratio_match(counts=counts):
            return self.data

        # 1. Percent of Percent (High priority)
        if self._handle_percent_of_percent():
            return self.data

        # 1.5 Grouped Matches (from extraction grouping)
        excluded_ids = self._resolve_grouped_matches()

        # 2. Local Patterns (Sliding Window for "Count, Percent, Count")
        # Returns indices to exclude from generic processing, but queues assignments internally
        excluded_ids = self._resolve_local_patterns(excluded_ids)

        # Refresh counts to include any virtual matches injected by local patterns
        counts = get_effective_counts(self.analysis)

        # 3. Mixed Coverage (Resolves specific counts/percents)
        self._resolve_mixed_coverage(counts=counts, excluded_match_ids=excluded_ids)

        # 5. Calculate Percentage from Counts
        self._calculate_percentage_from_counts()

        # 6. Calculate Count from Percentage
        self._calculate_count_from_percentage()

        # 6.5 Fallback to context total if no total found
        if self.data["employee_count_total"] is None and self.context_total:
            self.data["employee_count_total"] = self.context_total

        # 7. Handle Negation (if no data yet)
        self._handle_negation()

        return self.data

    def _is_local_non_coverage_context(
        self, span: Tuple[int, int], backward: int = 30, forward: int = 30
    ) -> bool:
        """
        Detect local non-coverage context using both lexical negation and
        extracted NON_UNION/NON_COVERAGE match types.
        """
        if check_local_negation(
            span, self.analysis.text, backward=backward, forward=forward
        ):
            return True

        dist_non_cov = get_min_distance_to_matches(
            span,
            self.analysis._matches,
            list(NEGATIVE_COVERAGE_MATCH_TYPES),
            look_backward=False,
            look_forward=True,
            text=self.analysis.text,
        )
        return dist_non_cov < 50
    

    

    def _is_union_linked_count(self, match: Dict[str, Any]) -> bool:
        """
        Returns True if the count match is linked to union context directly
        or through its worker list chain.
        """

        def _nearest_union_like(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            m_start, m_end = m["span"]
            nearest = None
            best_dist = float("inf")
            for cand in self.analysis._matches:
                if (
                    cand["type"] not in UNION_MATCH_TYPES
                    and cand["type"] not in NEGATIVE_COVERAGE_MATCH_TYPES
                ):
                    continue
                c_start, c_end = cand["span"]
                dist = 0
                if c_end <= m_start:
                    dist = m_start - c_end
                elif m_end <= c_start:
                    dist = c_start - m_end
                else:
                    dist = 0
                if dist < best_dist:
                    best_dist = dist
                    nearest = cand
            if nearest is None or best_dist >= 80:
                return None
            return nearest

        def _has_intervening_numeric(
            m: Dict[str, Any], union_m: Dict[str, Any]
        ) -> bool:
            m_start, m_end = m["span"]
            u_start, _ = union_m["span"]
            if u_start < m_end:
                return False
            m_list_gid = m.get("worker_list_group_id")
            for cand in self.analysis._matches:
                if cand.get("type") not in (MatchType.WORKER_COUNT, MatchType.NUMBER):
                    continue
                if cand is m:
                    continue
                c_start, c_end = cand["span"]
                if m_end <= c_start and c_end <= u_start:
                    # Ignore same list-chain members when checking blockers.
                    if (
                        m_list_gid is not None
                        and cand.get("worker_list_group_id") == m_list_gid
                    ):
                        continue
                    # Exception: in "X of Y" patterns where X < Y, do not block
                    # (X is numerator, Y is denominator in subset relationship)
                    # But if X >= Y, the intervening number IS a blocker.
                    text_between = self.analysis.text[m_end:c_start]
                    if STRICT_OF_REGEX.search(text_between) and m["val"] < cand["val"]:
                        continue
                    return True
            return False

        nearest = _nearest_union_like(match)
        if nearest and not _has_intervening_numeric(match, nearest):
            return True

        list_gid = match.get("worker_list_group_id")
        if list_gid is None:
            return False

        for m in self.analysis._matches:
            if m.get("worker_list_group_id") != list_gid:
                continue
            if m.get("type") not in (MatchType.WORKER_COUNT, MatchType.NUMBER):
                continue
            nearest = _nearest_union_like(m)
            if nearest and not _has_intervening_numeric(m, nearest):
                return True
        return False

    def _handle_ranges(self, counts: List[float] = []) -> bool:
        """
        Detects ranges like "20% to 25%" or "500 to 600 employees".
        Averages them and treats as explicit.
        """
        # 1. Percentage Ranges
        if len(self.analysis.percentages) == 2:
            matches = [
                m for m in self.analysis._matches if m["type"] == MatchType.PERCENT
            ]
            if len(matches) == 2:
                matches.sort(key=lambda x: x["span"][0])
                if is_range_context(
                    self.analysis.text, matches[0]["span"], matches[1]["span"]
                ):
                    # Validate association
                    dist = get_min_distance_to_matches(
                        matches[0]["span"],
                        self.analysis._matches,
                        UNION_MATCH_TYPES,
                        text=self.analysis.text,
                    )
                    if dist > 100:
                        return False

                    p1 = matches[0]["val"]
                    p2 = matches[1]["val"]
                    avg = (p1 + p2) / 2
                    self.data["percentage"] = round(avg, 2)
                    self.data["type"] = CoverageType.EXPLICIT_PERCENT.value
                    self.data["percentage_qualifier"] = PercentageQualifier.RANGE.value
                    self.data["note"] = f"Averaged from range {p1}% to {p2}%"
                    return True

        # 2. Count Ranges
        if not self.data["percentage"] and len(counts) == 2:
            matches = matches = [
                m
                for m in self.analysis._matches
                if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                and m["val"] in counts
            ]
            if len(matches) == 2:
                matches.sort(key=lambda x: x["span"][0])
                if is_range_context(
                    self.analysis.text, matches[0]["span"], matches[1]["span"]
                ):
                    c1 = matches[0]["val"]
                    c2 = matches[1]["val"]
                    avg = (c1 + c2) / 2

                    # Validate association
                    dist = get_min_distance_to_matches(
                        matches[0]["span"],
                        self.analysis._matches,
                        UNION_MATCH_TYPES,
                        text=self.analysis.text,
                    )
                    is_associated = dist < 100

                    if is_associated:
                        is_negated = False
                        if self.analysis.negation_terms:
                            if check_local_negation(
                                matches[0]["span"], self.analysis.text, backward=50
                            ):
                                is_negated = True

                        apply_coverage_logic(
                            self.data,
                            total=round(avg),
                            subset=round(avg),
                            is_negated=is_negated,
                            notes=None,
                        )
                        self.data["note"] = (
                            f"Averaged from range {c1} to {c2} ({'not covered' if is_negated else 'covered'})"
                        )
                    else:
                        self.data["employee_count_total"] = round(avg)
                        self.data["note"] = (
                            f"Averaged from range {c1} to {c2} (total - no union association)"
                        )
                    return True

        return False

    def _handle_ratio_match(self, counts: List[float]) -> bool:
        """
        Checks if we have exactly 1 percentage and 2 counts, and if they mathematically align.
        """
        if len(self.analysis.percentages) != 1 or len(counts) != 2:
            return False

        pct = self.analysis.percentages[0]
        c1, c2 = counts[0], counts[1]

        # Sort counts
        s_counts = sorted([c1, c2])
        small, large = s_counts[0], s_counts[1]
        total_sum = small + large

        # Ratios
        ratio_subset_total = (small / large) * 100.0 if large > 0 else 0.0
        ratio_part_sum = (small / total_sum) * 100.0 if total_sum > 0 else 0.0
        ratio_large_sum = (large / total_sum) * 100.0 if total_sum > 0 else 0.0

        matched = False
        notes = []
        chosen_total = None
        chosen_subset = None
        note_fmt = None

        # Only enforce "ignore smaller ratio population" in single-geo context:
        # one explicit country/region reference with no competing entities.
        explicit_geo_codes = {
            gm.geo_code
            for gm in self.analysis.geo_matches
            if gm.source_type == GeoSource.EXPLICIT and gm.geo_code
        }
        single_geo_context = len(explicit_geo_codes) == 1
        baseline_total = max(
            (
                v
                for v in [
                    self.data.get("employee_count_total"),
                    self.context_total,
                ]
                if v is not None
            ),
            default=0.0,
        )

        # Helper to check negation
        is_negated = False
        pct_match = next(
            (
                m
                for m in self.analysis._matches
                if m["type"] == MatchType.PERCENT and m["val"] == pct
            ),
            None,
        )
        if pct_match and self.analysis.negation_terms:
            if check_local_negation(
                pct_match["span"], self.analysis.text, backward=50, forward=50
            ):
                is_negated = True

        # Check 1: small / large ~= pct
        if abs(ratio_subset_total - pct) < 2.0:
            chosen_total = large
            chosen_subset = small
            note_fmt = (
                "Match: {subset}/{total} ~= "
                + f"{pct}%"
                + (" (Negated)" if is_negated else "")
                + ". Total {total}."
            )
            matched = True

        # Check 2: small / (small+large) ~= pct
        elif abs(ratio_part_sum - pct) < 2.0:
            chosen_total = total_sum
            chosen_subset = small
            note_fmt = (
                "Match: {subset}/({subset}+{other}) ~= "
                + f"{pct}%"
                + (" (Negated)" if is_negated else "")
                + ". Total {total}."
            )
            matched = True

        # Check 3: large / (small+large) ~= pct
        elif abs(ratio_large_sum - pct) < 2.0:
            chosen_total = total_sum
            chosen_subset = large
            note_fmt = (
                "Match: {subset}/({other}+{subset}) ~= "
                + f"{pct}%"
                + (" (Negated)" if is_negated else "")
                + ". Total {total}."
            )
            matched = True

        if matched:
            assert chosen_total is not None
            assert chosen_subset is not None
            assert note_fmt is not None

            if (
                single_geo_context
                and baseline_total > 0
                and chosen_total < baseline_total
            ):
                self.data["note"] = (
                    (
                        self.data.get("note") or "" + " | "
                        if self.data.get("note")
                        else ""
                    )
                    + f"Ignored ratio population {chosen_total} (smaller than known {baseline_total}) in single-geo context"
                )
                return False

            apply_coverage_logic(
                self.data,
                total=chosen_total,
                subset=chosen_subset,
                is_negated=is_negated,
                notes=notes,
                note_fmt=note_fmt,
            )
            self.data["percentage"] = pct
            self.data["type"] = CoverageType.EXPLICIT_PERCENT.value
            self.data["note"] = " | ".join(notes)

        return matched

    def _handle_percent_of_percent(self) -> bool:
        """Handles '15% of the remaining 80%' logic."""
        if len(self.analysis.percentages) >= 2:
            matches = [
                m for m in self.analysis._matches if m["type"] == MatchType.PERCENT
            ]
            matches.sort(key=lambda x: x["span"][0])

            for i in range(len(matches) - 1):
                m1 = matches[i]
                m2 = matches[i + 1]

                span1 = m1["span"]
                span2 = m2["span"]

                if span1[1] < span2[0]:
                    text_between = self.analysis.text[span1[1] : span2[0]]
                    # Check for "of" and short distance
                    if OF_REGEX.search(text_between) and len(text_between.strip()) < 30:
                        # Validate association
                        dist = get_min_distance_to_matches(
                            span1,
                            self.analysis._matches,
                            UNION_MATCH_TYPES,
                            text=self.analysis.text,
                        )
                        if dist > 100:
                            continue

                        p1 = m1["val"]
                        p2 = m2["val"]
                        combined = (p1 * p2) / 100.0
                        self.data["percentage"] = round(combined, 2)
                        self.data["calculated_percentage"] = round(combined, 2)
                        self.data["type"] = CoverageType.CALCULATED.value
                        self.data["note"] = f"Calculated from {p1}% of {p2}%"
                        return True
        return False

    def _resolve_grouped_matches(self) -> Set[int]:
        """
        Resolves matches that were grouped during extraction (e.g. '200 of 300', '10% of 500').
        Uses numeric_group_id populated in extraction.py.
        """
        consumed_indices = set()

        def is_worker_breakdown_pct(pct_match: Dict[str, Any]) -> bool:
            dist_to_union = get_min_distance_to_matches(
                pct_match["span"],
                self.analysis._matches,
                UNION_MATCH_TYPES,
                text=self.analysis.text,
            )
            dist_to_worker_type = get_min_distance_to_matches(
                pct_match["span"],
                self.analysis._matches,
                [MatchType.WORKER_TYPE, MatchType.WORKER_TERM],
                text=self.analysis.text,
            )
            if dist_to_worker_type < dist_to_union and dist_to_worker_type < 30:
                return bool(self.analysis.has_subset_indicator)
            return False

        # Group matches by numeric_group_id
        groups = {}
        for m in self.analysis._matches:
            gid = m.get("numeric_group_id")
            if gid:
                if gid not in groups:
                    groups[gid] = []
                groups[gid].append(m)

        # Helper to propagate link id
        def make_virtual_match(val, span, source_match):
            vm = {"val": val, "span": span}
            if source_match.get("linked_geo_group_id"):
                vm["linked_geo_group_id"] = source_match["linked_geo_group_id"]
            return vm

        for gid, group in groups.items():
            # Sort by position
            group.sort(key=lambda x: x["span"][0])

            # Check composition
            counts = [
                m
                for m in group
                if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
            ]
            percents = [m for m in group if m["type"] == MatchType.PERCENT]

            # Find linked geo if any
            linked_geo_code = None
            linked_gid = group[0].get("linked_geo_group_id")
            if linked_gid:
                for gm in self.analysis.geo_matches:
                    if gm.list_group_id == linked_gid or id(gm) == linked_gid:
                        if gm.geo_code:
                            linked_geo_code = gm.geo_code
                            break

            geo_note = f" [{linked_geo_code}]" if linked_geo_code else ""

            # Case 1: Count of Count (200 of 300)
            if len(counts) == 2 and not percents:
                c1, c2 = counts[0]["val"], counts[1]["val"]
                total = max(c1, c2)
                part = min(c1, c2)

                # Determine negation from part
                part_match = counts[0] if counts[0]["val"] == part else counts[1]
                total_match = counts[0] if counts[0]["val"] == total else counts[1]

                # If this is a worker-list subset breakdown (e.g. "100 ... consisting of 20 pilots, ..."),
                # defer to mixed coverage assignment so the full list chain can be handled together.
                if (
                    self.analysis.has_subset_indicator
                    and part_match.get("worker_list_group_id") is not None
                ):
                    continue

                # Guard: role/demographic subsets (e.g. "consisting of 20 pilots of 100 workers")
                # should not be auto-interpreted as union coverage splits.
                if not self._is_union_linked_count(part_match):
                    self.local_assignments.append(
                        {"match": total_match, "type": "total"}
                    )
                    consumed_indices.update(id(m) for m in group)
                    continue

                is_negated = self._is_local_non_coverage_context(
                    part_match["span"], backward=30, forward=30
                )

                # Queue assignments
                self.local_assignments.append({"match": total_match, "type": "total"})

                if is_negated:
                    self.local_assignments.append(
                        {"match": part_match, "type": "not_covered"}
                    )
                    self.local_assignments.append(
                        {
                            "match": make_virtual_match(
                                max(0, total - part), total_match["span"], total_match
                            ),
                            "type": "covered",
                        }
                    )
                else:
                    self.local_assignments.append(
                        {"match": part_match, "type": "covered"}
                    )
                    self.local_assignments.append(
                        {
                            "match": make_virtual_match(
                                max(0, total - part), total_match["span"], total_match
                            ),
                            "type": "not_covered",
                        }
                    )

                consumed_indices.update(id(m) for m in group)
                self.data["note"] = (
                    self.data["note"] or ""
                ) + f" | Grouped subset: {part} of {total}{geo_note}"

            # Case 2: Percent of Count (10% of 500)
            elif len(counts) == 1 and len(percents) == 1:
                count_match = counts[0]
                pct_match = percents[0]

                if is_worker_breakdown_pct(pct_match):
                    consumed_indices.add(id(pct_match))
                    continue

                # Guard: skip if percent describes a worker type and a separate union count exists
                _dist_union = get_min_distance_to_matches(
                    pct_match["span"],
                    self.analysis._matches,
                    UNION_MATCH_TYPES,
                    text=self.analysis.text,
                )
                _dist_wtype = get_min_distance_to_matches(
                    pct_match["span"],
                    self.analysis._matches,
                    [MatchType.WORKER_TYPE, MatchType.WORKER_TERM],
                    text=self.analysis.text,
                )
                if _dist_wtype < _dist_union and _dist_wtype < 30:
                    has_separate_union_count = any(
                        m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                        and m is not count_match
                        and get_min_distance_to_matches(
                            m["span"],
                            self.analysis._matches,
                            UNION_MATCH_TYPES,
                            text=self.analysis.text,
                        )
                        < _dist_union
                        for m in self.analysis._matches
                    )
                    if has_separate_union_count:
                        consumed_indices.add(id(pct_match))
                        continue

                # Use _resolve_local_pair logic but for this specific group
                # We can reuse the logic by calling it directly or replicating it.
                # Replicating simplified version here for clarity and to ensure group usage.

                # Check for hard delimiters within the group (unlikely if grouped by extraction, but safe to check)
                text_between = self.analysis.text[
                    min(m["span"][1] for m in group) : max(m["span"][0] for m in group)
                ]
                if ";" in text_between:
                    continue
                self._resolve_local_pair(pct_match, count_match)
                consumed_indices.update(id(m) for m in group)
                self.data["note"] = (self.data["note"] or "") + f" (Grouped{geo_note})"

        return consumed_indices

    def _resolve_local_patterns(
        self, excluded_ids: Optional[Set[int]] = None
    ) -> Set[int]:
        """
        Scans for local arithmetic patterns (e.g. Total * Pct = Part) using a sliding window.
        Returns a set of match IDs that were consumed.
        """
        if not hasattr(self, "local_assignments"):
            self.local_assignments = []

        consumed_indices = set(excluded_ids) if excluded_ids else set()

        def is_worker_breakdown_pct(pct_match: Dict[str, Any]) -> bool:
            dist_to_union = get_min_distance_to_matches(
                pct_match["span"],
                self.analysis._matches,
                UNION_MATCH_TYPES,
                text=self.analysis.text,
            )
            dist_to_worker_type = get_min_distance_to_matches(
                pct_match["span"],
                self.analysis._matches,
                [MatchType.WORKER_TYPE, MatchType.WORKER_TERM],
                text=self.analysis.text,
            )
            if dist_to_worker_type < dist_to_union and dist_to_worker_type < 30:
                return bool(self.analysis.has_subset_indicator)
            return False

        # Gather all relevant matches sorted by position
        relevant_types = (MatchType.WORKER_COUNT, MatchType.NUMBER, MatchType.PERCENT)
        matches = [m for m in self.analysis._matches if m["type"] in relevant_types]
        matches.sort(key=lambda x: x["span"][0])

        if len(matches) < 2:
            return consumed_indices

        # Sliding window of size 3
        for i in range(len(matches) - 2):
            window = matches[i : i + 3]

            # Skip if any already consumed
            if any(id(m) in consumed_indices for m in window):
                continue

            # Identify components
            counts = [m for m in window if m["type"] != MatchType.PERCENT]
            percents = [m for m in window if m["type"] == MatchType.PERCENT]

            if len(counts) == 2 and len(percents) == 1:
                c1 = counts[0]["val"]
                c2 = counts[1]["val"]
                pct = percents[0]["val"]

                # Skip if this percent describes a worker type rather than union coverage,
                # but only when a separate union-linked count exists.
                _pct_m = percents[0]
                _dist_union = get_min_distance_to_matches(
                    _pct_m["span"],
                    self.analysis._matches,
                    UNION_MATCH_TYPES,
                    text=self.analysis.text,
                )
                _dist_wtype = get_min_distance_to_matches(
                    _pct_m["span"],
                    self.analysis._matches,
                    [MatchType.WORKER_TYPE, MatchType.WORKER_TERM],
                    text=self.analysis.text,
                )
                if is_worker_breakdown_pct(_pct_m):
                    consumed_indices.add(id(_pct_m))
                    continue
                if _dist_wtype < _dist_union and _dist_wtype < 30:
                    has_separate_union_count = any(
                        m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                        and get_min_distance_to_matches(
                            m["span"],
                            self.analysis._matches,
                            UNION_MATCH_TYPES,
                            text=self.analysis.text,
                        )
                        < _dist_union
                        for m in self.analysis._matches
                    )
                    if has_separate_union_count:
                        consumed_indices.add(id(_pct_m))
                        continue

                # Check math: Total * Pct = Part
                # Case A: c1 is Total, c2 is Part
                if c1 > 0 and abs(c1 * (pct / 100.0) - c2) < max(1.0, c1 * 0.01):
                    self._apply_local_pattern(
                        total_match=counts[0],
                        part_match=counts[1],
                        pct_match=percents[0],
                    )
                    consumed_indices.update(id(m) for m in window)
                    continue

                # Case B: c2 is Total, c1 is Part
                if c2 > 0 and abs(c2 * (pct / 100.0) - c1) < max(1.0, c2 * 0.01):
                    self._apply_local_pattern(
                        total_match=counts[1],
                        part_match=counts[0],
                        pct_match=percents[0],
                    )
                    consumed_indices.update(id(m) for m in window)
                    continue

        # 2. Pair Patterns (2 items)
        # Re-filter matches to exclude consumed ones
        original_matches = matches
        matches = [m for m in matches if id(m) not in consumed_indices]

        def has_consumed_between(m_left, m_right) -> bool:
            left_end = m_left["span"][1]
            right_start = m_right["span"][0]
            for m in original_matches:
                if m["span"][0] >= left_end and m["span"][1] <= right_start:
                    if id(m) in consumed_indices:
                        return True
            return False

        if len(matches) >= 2:
            for i in range(len(matches) - 1):
                m1 = matches[i]
                m2 = matches[i + 1]

                if id(m1) in consumed_indices or id(m2) in consumed_indices:
                    continue

                types = {m1["type"], m2["type"]}
                has_count = MatchType.WORKER_COUNT in types or MatchType.NUMBER in types
                has_percent = MatchType.PERCENT in types

                if has_count and has_percent:
                    if has_consumed_between(m1, m2):
                        continue
                    # Check distance (e.g. 50 chars)
                    dist = m2["span"][0] - m1["span"][1]
                    if dist < 50:
                        # Check for hard delimiters
                        text_between = self.analysis.text[m1["span"][1] : m2["span"][0]]
                        if ";" in text_between:
                            continue

                        pct_match = m1 if m1["type"] == MatchType.PERCENT else m2
                        count_match = m2 if pct_match is m1 else m1

                        # Skip if this percent describes a worker type rather than union coverage,
                        # but only when a separate union-linked count exists.
                        dist_to_union = get_min_distance_to_matches(
                            pct_match["span"],
                            self.analysis._matches,
                            UNION_MATCH_TYPES,
                            text=self.analysis.text,
                        )
                        dist_to_worker_type = get_min_distance_to_matches(
                            pct_match["span"],
                            self.analysis._matches,
                            [MatchType.WORKER_TYPE, MatchType.WORKER_TERM],
                            text=self.analysis.text,
                        )
                        if is_worker_breakdown_pct(pct_match):
                            consumed_indices.add(id(pct_match))
                            continue
                        if dist_to_worker_type < dist_to_union and dist_to_worker_type < 30:
                            has_separate_union_count = any(
                                m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                                and m is not count_match
                                and get_min_distance_to_matches(
                                    m["span"],
                                    self.analysis._matches,
                                    UNION_MATCH_TYPES,
                                    text=self.analysis.text,
                                )
                                < dist_to_union
                                for m in self.analysis._matches
                            )
                            if has_separate_union_count:
                                consumed_indices.add(id(pct_match))
                                continue

                        self._resolve_local_pair(m1, m2)
                        consumed_indices.add(id(m1))
                        consumed_indices.add(id(m2))
                        continue

                # Pattern B: Count + Count (Subset)
                is_count_1 = m1["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                is_count_2 = m2["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)

                if is_count_1 and is_count_2:
                    if has_consumed_between(m1, m2):
                        continue
                    dist = m2["span"][0] - m1["span"][1]
                    if dist < 50:
                        text_between = self.analysis.text[m1["span"][1] : m2["span"][0]]
                        if ";" in text_between:
                            continue

                        if SEGMENT_DELIMITER_REGEX.search(text_between):
                            continue

                        if self._resolve_local_two_counts(m1, m2, text_between):
                            consumed_indices.add(id(m1))
                            consumed_indices.add(id(m2))

        return consumed_indices

    def _resolve_local_pair(self, m1, m2):
        if m1["type"] == MatchType.PERCENT:
            pct_match, count_match = m1, m2
            pct_first = True
        else:
            pct_match, count_match = m2, m1
            pct_first = False

        pct = pct_match["val"]
        count = count_match["val"]

        if pct_first:
            between = self.analysis.text[pct_match["span"][1] : count_match["span"][0]]
            base_span = count_match["span"]
        else:
            between = self.analysis.text[count_match["span"][1] : pct_match["span"][0]]
            base_span = pct_match["span"]

        is_count_total = True  # Default assumption

        # Heuristics
        if OF_REGEX.search(between):
            is_count_total = True
        elif OR_REGEX.search(between):
            is_count_total = False
        elif CONSIST_REGEX.search(between) and pct_first:
            is_count_total = False
        elif pct_first:
            if "(" in between:
                is_count_total = False
            else:
                is_count_total = True
        else:
            is_count_total = True

        is_negated = self._is_local_non_coverage_context(
            pct_match["span"], backward=30, forward=30
        )

        # Helper to propagate link id
        def make_virtual_match(val, span, source_match):
            vm = {"val": val, "span": span}
            if source_match.get("linked_geo_group_id"):
                vm["linked_geo_group_id"] = source_match["linked_geo_group_id"]
            return vm

        # In subset clauses (e.g. "of which 200 of 300 ..."), avoid synthesizing
        # the complement remainder from local ratio math to prevent double counting.
        is_subset_clause = self._is_subset_breakdown_span(base_span)

        # Calculate values
        if is_count_total:
            total_val = count
            subset_val = round((pct / 100.0) * count)
            if is_negated:
                not_covered_val = subset_val
                covered_val = max(0, total_val - subset_val)
                self.local_assignments.append({"match": count_match, "type": "total"})
                self.local_assignments.append(
                    {
                        "match": make_virtual_match(
                            not_covered_val, base_span, count_match
                        ),
                        "type": "not_covered",
                    }
                )
                if not is_subset_clause:
                    self.local_assignments.append(
                        {
                            "match": make_virtual_match(
                                covered_val, base_span, count_match
                            ),
                            "type": "covered",
                        }
                    )
            else:
                covered_val = subset_val
                not_covered_val = max(0, total_val - subset_val)
                self.local_assignments.append({"match": count_match, "type": "total"})
                self.local_assignments.append(
                    {
                        "match": make_virtual_match(
                            covered_val, base_span, count_match
                        ),
                        "type": "covered",
                    }
                )
                if not is_subset_clause:
                    self.local_assignments.append(
                        {
                            "match": make_virtual_match(
                                not_covered_val, base_span, count_match
                            ),
                            "type": "not_covered",
                        }
                    )
            note_suffix = "(Total)"
        else:
            # Count is subset
            subset_val = count
            if pct > 0:
                total_val = round(count / (pct / 100.0))
            else:
                total_val = count  # Avoid div by zero

            note_suffix = "(Subset)"

            # For subset, we map the explicit count to its type, and the derived total to the same span
            if is_negated:
                self.local_assignments.append(
                    {"match": count_match, "type": "not_covered"}
                )
            else:
                self.local_assignments.append({"match": count_match, "type": "covered"})

            self.local_assignments.append(
                {
                    "match": make_virtual_match(
                        total_val, count_match["span"], count_match
                    ),
                    "type": "total",
                }
            )

        self.data["note"] = (
            self.data["note"] or ""
        ) + f" | Local pair: {pct}%/{count} {note_suffix}"

    def _apply_local_pattern(self, total_match, part_match, pct_match):
        # Determine if Part is Covered or Not Covered based on local context
        is_negated = self._is_local_non_coverage_context(
            pct_match["span"], backward=30, forward=30
        )

        total_val = total_match["val"]
        part_val = part_match["val"]
        pct_val = pct_match["val"]

        def make_virtual_match(val, span, source_match):
            vm = {"val": val, "span": span}
            if source_match.get("linked_geo_group_id"):
                vm["linked_geo_group_id"] = source_match["linked_geo_group_id"]
            return vm

        def ensure_linked_match(source_match):
            # Preserve existing link when present.
            if source_match.get("linked_geo_group_id"):
                return source_match

            # Backfill from strongest nearby context in this arithmetic trio.
            link_id = total_match.get("linked_geo_group_id") or pct_match.get(
                "linked_geo_group_id"
            )
            if not link_id:
                return source_match

            linked = {
                "val": source_match["val"],
                "span": source_match["span"],
                "linked_geo_group_id": link_id,
            }
            return linked

        is_subset_clause = self._is_subset_breakdown_span(total_match["span"])

        # Queue assignments instead of updating data directly
        self.local_assignments.append({"match": total_match, "type": "total"})

        if is_negated:
            self.local_assignments.append(
                {"match": ensure_linked_match(part_match), "type": "not_covered"}
            )
            # Add virtual remainder
            rem_val = max(0, total_val - part_val)
            if not is_subset_clause:
                self.local_assignments.append(
                    {
                        "match": make_virtual_match(
                            rem_val, total_match["span"], total_match
                        ),
                        "type": "covered",
                    }
                )
        else:
            self.local_assignments.append(
                {"match": ensure_linked_match(part_match), "type": "covered"}
            )
            # Add virtual remainder
            rem_val = max(0, total_val - part_val)
            if not is_subset_clause:
                self.local_assignments.append(
                    {
                        "match": make_virtual_match(
                            rem_val, total_match["span"], total_match
                        ),
                        "type": "not_covered",
                    }
                )

        self.data["note"] = (
            self.data["note"] or ""
        ) + f" | Local match: {part_val} is {pct_val}% of {total_val}"

    def _resolve_local_two_counts(self, m1, m2, text_between) -> bool:
        """
        Resolves 'Count of Count' patterns (e.g. '20 of 100').
        Returns True if resolved.
        """
        # Check for explicit subset relationship
        is_subset = False

        # 1. Partitive: "20 of 100"
        if OF_REGEX.search(text_between) and not "," in text_between:
            is_subset = True
        # 2. Subset Breakdown: "100 including 20" or "100 consisting of 20"
        elif (
            SUBSET_REGEX.search(text_between)
            or CONSIST_REGEX.search(text_between)
            or SPLIT_ADVERBS_REGEX.search(text_between)
        ):
            is_subset = True
        # 3. Introductory Total: "Of 100, 20..." or "For 100, 20..."
        elif check_local_regex(
            m1["span"], self.analysis.text, OF_REGEX, backward=25, forward=0
        ):
            if not SUBSET_REGEX.search(text_between):
                is_subset = True
        if not is_subset:
            return False

        # Do not cross worker list-chain boundaries when the connector is not a
        # strict list joiner. This keeps chained subsets bounded to the list.
        m1_list_gid = m1.get("worker_list_group_id")
        m2_list_gid = m2.get("worker_list_group_id")
        if m1_list_gid != m2_list_gid:
            one_side_is_list_member = (m1_list_gid is not None) or (
                m2_list_gid is not None
            )
            if one_side_is_list_member and not STRICT_LIST_CONNECTOR.match(
                text_between
            ):
                return False

        c1, c2 = m1["val"], m2["val"]
        total = max(c1, c2)
        part = min(c1, c2)

        # Determine which match is the part for negation checking
        part_match = m1 if m1["val"] == part else m2

        # Check if part is associated with union/coverage terms
        if not self._is_union_linked_count(part_match):
            # Just record total, ignore part as it's likely just a demographic/role subset
            total_match = m1 if m1["val"] == total else m2
            self.local_assignments.append({"match": total_match, "type": "total"})
            self.data["note"] = (
                self.data["note"] or ""
            ) + f" | Local subset: {part} of {total} (subset not union-linked)"
            return True

        is_negated = self._is_local_non_coverage_context(
            part_match["span"], backward=30, forward=30
        )

        def make_virtual_match(val, span, source_match):
            vm = {"val": val, "span": span}
            if source_match.get("linked_geo_group_id"):
                vm["linked_geo_group_id"] = source_match["linked_geo_group_id"]
            return vm

        # In subset clauses (e.g. "of which 200 of 300 ..."), avoid synthesizing
        # complement remainder to prevent parent + child double counting.
        is_subset_clause = self._is_subset_breakdown_span(part_match["span"])

        # Queue assignments
        # Total is the max value match
        total_match = m1 if m1["val"] == total else m2
        self.local_assignments.append({"match": total_match, "type": "total"})

        if is_negated:
            self.local_assignments.append({"match": part_match, "type": "not_covered"})
            if not is_subset_clause:
                self.local_assignments.append(
                    {
                        "match": make_virtual_match(
                            max(0, total - part), total_match["span"], total_match
                        ),
                        "type": "covered",
                    }
                )
        else:
            self.local_assignments.append({"match": part_match, "type": "covered"})
            if not is_subset_clause:
                self.local_assignments.append(
                    {
                        "match": make_virtual_match(
                            max(0, total - part), total_match["span"], total_match
                        ),
                        "type": "not_covered",
                    }
                )

        self.data["note"] = (
            self.data["note"] or ""
        ) + f" | Local subset: {part} of {total}"
        return True

    def _is_subset_breakdown_span(self, span: Tuple[int, int]) -> bool:
        """
        Returns True when the local numeric span appears in a subset clause
        (e.g. "of which/whom/those"), which should suppress synthetic remainders.
        """
        pre = construct_window(span, self.analysis.text, backward=80, forward=0)
        return bool(self.subset_regex.search(pre))

    def _is_subgroup_composition_percent(self, pct_match: Dict[str, Any]) -> bool:
        """
        True when a percentage appears to describe composition inside an already
        scoped union subgroup (e.g., "Of those represented, 95% ... represented by X").
        ONLY for these type of sentences: Of our unionized employees 80% are represented by UAW. 
        However, the true firm percentage is 20%; the 80% is the subgroup of the unionized percentage.
        """
        has_specific_union_targets = any(
            m["type"] in (MatchType.SPECIFIC_UNION, MatchType.UNION_NAME)
            for m in self.analysis._matches
        )
        if not has_specific_union_targets:
            return False

        p_start, p_end = pct_match["span"]
        pre = self.analysis.text[max(0, p_start - 140) : p_start]
        post = self.analysis.text[p_end : min(len(self.analysis.text), p_end + 100)]
        around = pre + " " + post

        has_subset_scope = bool(self.subset_regex.search(pre))
        has_breakdown_link = bool(self.subgroup_breakdown_regex.search(around))
        return has_subset_scope and has_breakdown_link

    def _resolve_mixed_coverage(
        self, counts: List[float] = [], excluded_match_ids: Set[int] = set()
    ):
        """
        Resolves mixed coverage by segmenting text on delimiters and mapping
        values to keywords within the same segment.
        """
        # 1. Identify Segments (Split by delimiters, avoiding numbers)
        # We capture delimiters to analyze list structure
        segments = get_text_segments(self.analysis.text)

        # Helper to find segment index
        def get_seg_idx(pos):
            return next((i for i, (s, e, _) in enumerate(segments) if s <= pos < e), 0)

        # 2. Gather entities
        _counts = [
            m
            for m in self.analysis._matches
            if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
            and m["val"] in counts
            and id(m) not in excluded_match_ids
        ]
        percents = [
            m
            for m in self.analysis._matches
            if m["type"] == MatchType.PERCENT and id(m) not in excluded_match_ids
        ]

        # Guardrail: percentages in subgroup composition clauses should not be
        # interpreted as top-level workforce coverage.
        subgroup_composition_pct_ids = {
            id(p) for p in percents if self._is_subgroup_composition_percent(p)
        }
        if subgroup_composition_pct_ids and len(percents) > 1:
            first_composition_start = min(
                p["span"][0] for p in percents if id(p) in subgroup_composition_pct_ids
            )
            has_breakdown_context = bool(
                self.subgroup_breakdown_regex.search(self.analysis.text)
            )
            if has_breakdown_context:
                for p in percents:
                    if p["span"][0] >= first_composition_start:
                        subgroup_composition_pct_ids.add(id(p))

        positives = [
            m
            for m in self.analysis._matches
            if m["type"]
            in (
                MatchType.UNION_TERM,
                MatchType.SPECIFIC_UNION,
                MatchType.UNION_NAME,
                MatchType.COVERAGE_TERM,
            )
        ]
        negatives = [
            m
            for m in self.analysis._matches
            if m["type"] in NEGATIVE_COVERAGE_MATCH_TYPES
        ]
        totals = [
            m
            for m in self.analysis._matches
            if m["type"] in (MatchType.WORKER_TERM, MatchType.TOTAL_MODIFIER)
        ]

        # Check which segments have coverage terms
        segments_with_context = set()
        for m in positives + negatives:
            mid = get_midpoint(m["span"])
            s_idx = get_seg_idx(mid)
            segments_with_context.add(s_idx)

        # If only one segment has union/coverage terms, apply them globally
        is_global_context = len(segments_with_context) <= 1

        logic_notes = []
        if is_global_context:
            logic_notes.append("Global Context")

        # 3. Respectively Logic
        if self.analysis.has_respectively:
            sorted_values = sorted(_counts, key=lambda x: x["span"][0])
            sorted_percents = sorted(percents, key=lambda x: x["span"][0])

            tagged_keywords = []
            for p in positives:
                tagged_keywords.append({"match": p, "type": "covered"})
            for n in negatives:
                tagged_keywords.append({"match": n, "type": "not_covered"})
            tagged_keywords.sort(key=lambda x: x["match"]["span"][0])

            # Map Counts
            if len(sorted_values) == len(tagged_keywords) and len(sorted_values) > 0:
                for val_match, kw_item in zip(sorted_values, tagged_keywords):
                    if kw_item["type"] == "covered":
                        current = self.data["employee_count_covered"] or 0
                        self.data["employee_count_covered"] = current + val_match["val"]
                        excluded_match_ids.add(id(val_match))
                    elif kw_item["type"] == "not_covered":
                        current = self.data["employee_count_not_covered"] or 0
                        self.data["employee_count_not_covered"] = (
                            current + val_match["val"]
                        )
                        excluded_match_ids.add(id(val_match))

                if (
                    self.data["employee_count_covered"] is not None
                    and self.data["employee_count_not_covered"] is not None
                ):
                    self.data["employee_count_total"] = (
                        self.data["employee_count_covered"]
                        + self.data["employee_count_not_covered"]
                    )
                return

            # Map Percentages
            if (
                len(sorted_percents) == len(tagged_keywords)
                and len(sorted_percents) > 0
            ):
                for pct_match, kw_item in zip(sorted_percents, tagged_keywords):
                    adj_val, note = apply_qualitative_multipliers(
                        pct_match["val"],
                        pct_match["span"],
                        self.analysis.text,
                        apply=True,
                    )
                    if kw_item["type"] == "covered":
                        self.data["percentage"] = adj_val
                        if note:
                            self.data["note"] = note
                        excluded_match_ids.add(id(pct_match))
                    elif (
                        kw_item["type"] == "not_covered"
                        and self.data["percentage"] is None
                    ):
                        self.data["percentage"] = 100.0 - adj_val
                        self.data["negated"] = True
                        self.data["negation_type"] = NegationType.NOT_COVERED.value
                        self.data["note"] = (
                            f"Inverted from {adj_val}% not covered (respectively)"
                        )
                        excluded_match_ids.add(id(pct_match))
                return

        # We'll check this dynamically during assignment
        def is_followed_by_subset_indicator(count_match):
            # Look ahead for "of whom", "of which" before the next count or end of sentence
            start = count_match["span"][1]
            window = self.analysis.text[start : start + 100]
            return bool(self.subset_regex.search(window))

        def get_segment_range(span):
            mid = get_midpoint(span)
            for start, end, _ in segments:
                if start <= mid < end:
                    return start, end
            return 0, len(self.analysis.text)

        def _is_total_anchor_for_count(
            count_match: Dict[str, Any], total_match: Dict[str, Any]
        ) -> bool:
            # Explicit total modifiers remain valid total anchors.
            if total_match["type"] == MatchType.TOTAL_MODIFIER:
                return True

            # WORKER_TERM is only a weak denominator cue and should not turn
            # typed/grouped counts (e.g. "6800 full-time employees") into totals.
            term_val = str(total_match.get("val", "")).lower()
            is_generic_worker_term = (
                term_val in GENERIC_WORKER_TERMS
                or term_val.rstrip("s") in GENERIC_WORKER_TERMS
            )
            if not is_generic_worker_term:
                return False

            c_gid = count_match.get("worker_group_id")
            t_gid = total_match.get("worker_group_id")
            if c_gid and t_gid and c_gid == t_gid:
                return False
            if c_gid:
                return False

            return True

        def get_nearest_type_in_segment(target_match):
            nonlocal logic_notes
            target_span = target_match["span"]
            seg_start, seg_end = get_segment_range(target_span)
            t_start, t_end = target_span

            # If this count is followed by "of whom", it is explicitly a TOTAL (denominator)
            if is_followed_by_subset_indicator(target_match):
                logic_notes.append("Subset Indicator -> Total")
                return "total"

            def has_hard_delimiter_between(
                a_start: int, a_end: int, b_start: int, b_end: int
            ) -> bool:
                lo = min(a_end, b_end)
                hi = max(a_start, b_start)
                if hi <= lo:
                    return False
                return bool(SEGMENT_DELIMITER_REGEX.search(self.analysis.text[lo:hi]))

            best_dist = float("inf")
            best_type = None

            candidates = []
            # If global context, use all matches. Else filter by segment.
            search_positives = (
                positives
                if is_global_context
                else [
                    p
                    for p in positives
                    if p["span"][0] >= seg_start and p["span"][1] <= seg_end
                ]
            )
            search_negatives = (
                negatives
                if is_global_context
                else [
                    n
                    for n in negatives
                    if n["span"][0] >= seg_start and n["span"][1] <= seg_end
                ]
            )
            search_totals = (
                totals
                if is_global_context
                else [
                    t
                    for t in totals
                    if t["span"][0] >= seg_start and t["span"][1] <= seg_end
                ]
            )

            for p in search_positives:
                candidates.append(("covered", p))
            for n in search_negatives:
                candidates.append(("not_covered", n))
            for t in search_totals:
                if not _is_total_anchor_for_count(target_match, t):
                    continue
                candidates.append(("total", t))

            for c_type, m in candidates:
                m_start, m_end = m["span"]
                dist = None
                if m_end < t_start:
                    # Match is before target
                    if has_hard_delimiter_between(m_start, m_end, t_start, t_end):
                        continue
                    dist = t_start - m_end
                elif t_end < m_start:
                    # Match is after target
                    if has_hard_delimiter_between(t_start, t_end, m_start, m_end):
                        continue
                    dist = m_start - t_end
                else:
                    # Overlapping
                    dist = 0

                if dist is not None:
                    eff_dist = dist + (20 if c_type == "total" else 0)
                    if eff_dist < best_dist:
                        best_dist = eff_dist
                        best_type = c_type

            return best_type if best_dist <= 150 else None

        # 4. Assign Initial Types to Counts
        count_assignments = []  # List of dicts: {match, type, segment_idx}

        for c in _counts:
            # Find segment index
            c_mid = get_midpoint(c["span"])
            seg_idx = get_seg_idx(c_mid)

            seg_text = ""
            if 0 <= seg_idx < len(segments):
                s_start, s_end, _ = segments[seg_idx]
                seg_text = self.analysis.text[s_start:s_end].strip()

            # Get local type
            ctype = get_nearest_type_in_segment(c)
            count_assignments.append(
                {"match": c, "type": ctype, "seg_idx": seg_idx, "seg_text": seg_text}
            )

        # 4b. Inject Local Assignments (from _resolve_local_patterns)
        if hasattr(self, "local_assignments") and self.local_assignments:
            for la in self.local_assignments:
                c = la["match"]
                # Calculate segment info for these too
                c_mid = get_midpoint(c["span"])
                seg_idx = get_seg_idx(c_mid)
                seg_text = ""
                if 0 <= seg_idx < len(segments):
                    s_start, s_end, _ = segments[seg_idx]
                    seg_text = self.analysis.text[s_start:s_end].strip()

                entry = {
                    "match": c,
                    "type": la["type"],
                    "seg_idx": seg_idx,
                    "seg_text": seg_text,
                    "is_local": True,
                }
                if "override_val" in la:
                    entry["override_val"] = la["override_val"]
                count_assignments.append(entry)

        # 4c. Positive worker-type propagation:
        # In purely positive union context, when one grouped worker-type count is
        # covered, propagate covered to other grouped worker-type counts that
        # remain untyped (prevents losing early list members due distance).
        if count_assignments:
            worker_type_count = len(self.analysis.worker_types or [])
            specific_worker_terms = {
                str(w).lower()
                for w in (self.analysis.worker_terms or [])
                if str(w).lower() not in GENERIC_WORKER_TERMS
                and str(w).lower().rstrip("s") not in GENERIC_WORKER_TERMS
            }
            has_multiple_worker_buckets = (
                worker_type_count >= 2 or len(specific_worker_terms) >= 2
            )
            is_positive_only = (
                bool(positives)
                and not bool(negatives)
                and not bool(self.analysis.negation_terms)
            )

            if has_multiple_worker_buckets and is_positive_only:
                covered_group_ids = {
                    item["match"].get("worker_group_id")
                    for item in count_assignments
                    if item.get("type") == "covered"
                    and item["match"].get("worker_group_id") is not None
                }
                covered_list_group_ids = {
                    item["match"].get("worker_list_group_id")
                    for item in count_assignments
                    if item.get("type") == "covered"
                    and item["match"].get("worker_list_group_id") is not None
                }
                if covered_group_ids or covered_list_group_ids:
                    for item in count_assignments:
                        if item.get("type") is not None:
                            continue
                        gid = item["match"].get("worker_group_id")
                        list_gid = item["match"].get("worker_list_group_id")

                        # Subset-list propagation: when subset indicators are present,
                        # keep all worker list members together (geo-style chain behavior).
                        if (
                            self.analysis.has_subset_indicator
                            and list_gid is not None
                            and list_gid in covered_list_group_ids
                        ):
                            item["type"] = "covered"
                            continue

                        # Generic propagation stays local to already-covered worker group ids.
                        if gid is not None and gid in covered_group_ids:
                            item["type"] = "covered"
                    logic_notes.append(
                        "Positive worker-type propagation -> covered for untyped grouped counts"
                    )

        # 5. Propagate Types (List Logic)
        # Sort by position
        count_assignments.sort(
            key=lambda x: (x["match"]["span"][0], 0 if x.get("is_local") else 1)
        )

        def is_connected(idx1, idx2):
            if is_global_context:
                return True

            s1 = count_assignments[idx1]["seg_idx"]
            s2 = count_assignments[idx2]["seg_idx"]
            if s1 == s2:
                return True

            # Allow connection across soft delimiters (commas) but not hard ones
            start, end = min(s1, s2), max(s1, s2)
            for i in range(start, end):
                delim = segments[i][2].strip()
                if delim != ",":
                    return False
            return True

        # Forward Propagation
        for i in range(len(count_assignments) - 1):
            if (
                count_assignments[i]["type"] is not None
                and count_assignments[i + 1]["type"] is None
            ):
                # Check for exception delimiter
                s1 = count_assignments[i]["seg_idx"]
                s2 = count_assignments[i + 1]["seg_idx"]
                is_exception = False
                if s2 > s1:
                    for k in range(s1, s2):
                        delim = segments[k][2]
                        if EXCEPT_REGEX.search(delim):
                            is_exception = True
                            break

                if is_exception:
                    prev_type = count_assignments[i]["type"]
                    if prev_type == "covered":
                        count_assignments[i + 1]["type"] = "not_covered"
                    elif prev_type == "not_covered":
                        count_assignments[i + 1]["type"] = "covered"
                elif is_connected(i, i + 1):
                    count_assignments[i + 1]["type"] = count_assignments[i]["type"]
                    logic_notes.append(
                        f"Propagated {count_assignments[i]['type']} Forward"
                    )

        # Backward Propagation
        for i in range(len(count_assignments) - 1, 0, -1):
            if (
                count_assignments[i]["type"] is not None
                and count_assignments[i - 1]["type"] is None
            ):
                if is_connected(i, i - 1):
                    count_assignments[i - 1]["type"] = count_assignments[i]["type"]
                    logic_notes.append(
                        f"Propagated {count_assignments[i]['type']} Backward"
                    )

        self.data["_count_assignments"] = count_assignments

        # Check if we have enough data to calculate percentage later
        has_covered = self.data["employee_count_covered"] is not None
        has_not_covered = self.data["employee_count_not_covered"] is not None
        has_total = self.data["employee_count_total"] is not None

        can_calculate_pct = (
            (has_covered and has_total)
            or (has_not_covered and has_total)
            or (has_covered and has_not_covered)
        )

        for p in percents:
            if can_calculate_pct:
                continue
            if id(p) in subgroup_composition_pct_ids:
                excluded_match_ids.add(id(p))
                continue

            ptype = get_nearest_type_in_segment(p)
            adj_val, note = apply_qualitative_multipliers(
                p["val"], p["span"], self.analysis.text, apply=True
            )

            if ptype == "not_covered":
                self.data["percentage"] = 100.0 - adj_val
                self.data["negated"] = True
                self.data["negation_type"] = NegationType.NOT_COVERED.value
                self.data["note"] = f"Inverted from {adj_val}% not covered" + (
                    f" ({note})" if note else ""
                )
                excluded_match_ids.add(id(p))
            elif ptype == "covered":
                self.data["percentage"] = adj_val
                if note:
                    self.data["note"] = note
                excluded_match_ids.add(id(p))

        total_candidates = []
        # Guardrail: a "total" should be strictly larger than the rest of local numeric assignments.
        assignment_values = [
            item.get("override_val", item["match"]["val"]) for item in count_assignments
        ]

        subset_matches = [
            m for m in self.analysis._matches if m.get("type") == MatchType.SUBSET
        ]

        def _is_subset_child_of_assigned_parent(
            item: Dict[str, Any],
            assigned_parent_values: List[float],
            assignment_type: str,
        ) -> bool:
            if not self.analysis.has_subset_indicator or not subset_matches:
                return False

            c_start, _ = item["match"]["span"]
            c_val = item.get("override_val", item["match"]["val"])
            c_span = item["match"]["span"]

            parenthetical_spans = list(
                getattr(self.analysis, "parenthetical_spans", []) or []
            )

            def _enclosing_parenthetical(
                span: Tuple[int, int],
            ) -> Optional[Tuple[int, int]]:
                for p_start, p_end in parenthetical_spans:
                    if p_start <= span[0] and span[1] <= p_end:
                        return (p_start, p_end)
                return None

            count_parenthetical = _enclosing_parenthetical(c_span)

            list_gid = item["match"].get("worker_list_group_id")

            # Require nearby preceding subset indicator with no hard delimiter in-between.
            nearest_subset = None
            nearest_dist = float("inf")
            for sm in subset_matches:
                s_start, s_end = sm["span"]
                if s_end > c_start:
                    continue
                dist = c_start - s_end
                if dist > 60:
                    continue
                subset_parenthetical = _enclosing_parenthetical(sm["span"])
                # Scope subset indicators to the same parenthetical phrase.
                # This prevents "including ..." inside () from suppressing counts outside ().
                if subset_parenthetical != count_parenthetical:
                    continue
                between = self.analysis.text[s_end:c_start]
                if SEGMENT_DELIMITER_REGEX.search(between):
                    continue
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_subset = sm

            if nearest_subset is None and list_gid is not None:
                # Chain-aware fallback: if this count belongs to a worker list chain,
                # allow a subset cue tied to the first list member (e.g. "consisting of
                # 20 ..., 10 ..., and 10 ...") to apply to all members.
                chain_starts = [
                    ca["match"]["span"][0]
                    for ca in count_assignments
                    if ca["match"].get("worker_list_group_id") == list_gid
                ]
                if chain_starts:
                    first_chain_start = min(chain_starts)
                    for sm in subset_matches:
                        _, s_end = sm["span"]
                        if s_end > first_chain_start:
                            continue
                        dist = first_chain_start - s_end
                        if dist > 120:
                            continue
                        between = self.analysis.text[s_end:first_chain_start]
                        if re.search(r"[;:\.]", between):
                            continue
                        nearest_subset = sm
                        break

            if nearest_subset is None:
                return False

            if list_gid is not None:
                # For chained worker lists in subset clauses (e.g. "including 20 pilots, 10 chefs ..."),
                # treat all list members as subset children when a larger parent count exists.
                larger_parent_exists = any(
                    parent_val > c_val for parent_val in assignment_values
                )
                chain_is_union_linked = self._is_union_linked_count(item["match"])
                if larger_parent_exists and not chain_is_union_linked:
                    logic_notes.append(
                        f"Skipped subset {assignment_type} {c_val} (worker list chain near '{nearest_subset.get('val', '')}')"
                    )
                    return True
                # If the worker list chain is union-linked (often by the last list member),
                # keep list members and do not apply generic parent-value suppression.
                if chain_is_union_linked:
                    return False

            # Only suppress when a parent value of same assignment type is already present.
            if any(parent_val >= c_val for parent_val in assigned_parent_values):
                logic_notes.append(
                    f"Skipped subset {assignment_type} {c_val} (subset indicator near '{nearest_subset.get('val', '')}')"
                )
                return True

            return False

        assigned_covered_values: List[float] = []
        assigned_not_covered_values: List[float] = []
        assigned_covered_items: List[Dict[str, Any]] = []
        skipped_subset_covered_values: List[float] = []
        consumed_covered_list_groups: Set[Any] = set()
        consumed_not_covered_list_groups: Set[Any] = set()

        for item in count_assignments:
            ctype = item["type"]
            match_obj = item["match"]
            if id(match_obj) in excluded_match_ids and not item.get("is_local"):
                continue
            list_gid = match_obj.get("worker_list_group_id")
            list_sum = match_obj.get("worker_list_group_sum")
            val = item.get("override_val", match_obj["val"])
            if ctype == "covered":
                if _is_subset_child_of_assigned_parent(
                    item, assigned_covered_values, "covered"
                ):
                    skipped_subset_covered_values.append(val)
                    excluded_match_ids.add(id(item["match"]))
                    continue

                if list_gid is not None and list_sum is not None:
                    if list_gid in consumed_covered_list_groups:
                        excluded_match_ids.add(id(item["match"]))
                        continue
                    val = float(list_sum)
                    consumed_covered_list_groups.add(list_gid)

                current = self.data["employee_count_covered"] or 0
                self.data["employee_count_covered"] = current + val
                assigned_covered_values.append(val)
                assigned_covered_items.append(item)
                excluded_match_ids.add(id(item["match"]))
                logic_notes.append(f"Assigned {val} to covered")
            elif ctype == "not_covered":
                if _is_subset_child_of_assigned_parent(
                    item, assigned_not_covered_values, "not covered"
                ):
                    excluded_match_ids.add(id(item["match"]))
                    continue

                if list_gid is not None and list_sum is not None:
                    if list_gid in consumed_not_covered_list_groups:
                        excluded_match_ids.add(id(item["match"]))
                        continue
                    val = float(list_sum)
                    consumed_not_covered_list_groups.add(list_gid)

                current = self.data["employee_count_not_covered"] or 0
                self.data["employee_count_not_covered"] = current + val
                assigned_not_covered_values.append(val)
                excluded_match_ids.add(id(item["match"]))
                logic_notes.append(f"Assigned {val} to not covered")
            elif ctype == "total":
                other_vals = [v for v in assignment_values if v != val]
                max_other = max(other_vals) if other_vals else None
                if max_other is None or val > max_other:
                    total_candidates.append(val)
                    logic_notes.append(f"Assigned {val} to total")
                else:
                    logic_notes.append(
                        f"Rejected total candidate {val} (not greater than other values; max_other={max_other})"
                    )
                    # Try fallback classification instead of discarding the value.
                    # Prefer the closer of explicit negative vs positive status cues.
                    neg_dist = get_min_distance_to_matches(
                        item["match"]["span"],
                        self.analysis._matches,
                        list(NEGATIVE_COVERAGE_MATCH_TYPES),
                        look_backward=True,
                        look_forward=True,
                        text=self.analysis.text,
                    )
                    pos_dist = get_min_distance_to_matches(
                        item["match"]["span"],
                        self.analysis._matches,
                        UNION_MATCH_TYPES,
                        look_backward=True,
                        look_forward=True,
                        text=self.analysis.text,
                    )
                    if neg_dist < 80 and neg_dist <= pos_dist:
                        current = self.data["employee_count_not_covered"] or 0
                        self.data["employee_count_not_covered"] = current + val
                        logic_notes.append(
                            f"Reassigned rejected total {val} to not covered (neg_dist={neg_dist}, pos_dist={pos_dist})"
                        )
                    elif pos_dist < 80:
                        current = self.data["employee_count_covered"] or 0
                        self.data["employee_count_covered"] = current + val
                        logic_notes.append(
                            f"Reassigned rejected total {val} to covered (pos_dist={pos_dist}, neg_dist={neg_dist})"
                        )
                    else:
                        logic_notes.append(
                            f"No fallback type found for rejected total {val}"
                        )
                excluded_match_ids.add(id(item["match"]))

        # Fallback for denominator-style openings where the largest introductory count
        # was misclassified as covered (e.g. "Of 300 employees, 200 are unionized").
        if (
            self.data["employee_count_total"] is None
            and not total_candidates
            and self.data["employee_count_not_covered"] is None
            and len(assigned_covered_items) >= 1
            and (
                len(assigned_covered_items) >= 2 or bool(skipped_subset_covered_values)
            )
        ):
            covered_sorted = sorted(
                assigned_covered_items, key=lambda x: x["match"]["span"][0]
            )
            first_item = covered_sorted[0]
            first_val = first_item.get("override_val", first_item["match"]["val"])
            max_val = max(
                x.get("override_val", x["match"]["val"]) for x in covered_sorted
            )
            other_cov_sum = (self.data["employee_count_covered"] or 0.0) - first_val
            if other_cov_sum <= 0 and skipped_subset_covered_values:
                other_cov_sum = max(skipped_subset_covered_values)

            first_span = first_item["match"]["span"]
            pre_text = construct_window(first_span, self.analysis.text, backward=25)
            first_end = first_span[1]
            if len(covered_sorted) >= 2:
                next_start = covered_sorted[1]["match"]["span"][0]
                between = self.analysis.text[first_end:next_start]
            else:
                between = self.analysis.text[first_end : first_end + 80]

            has_intro_denominator = bool(
                re.search(r"\b(of|for|among|out\s+of)\b", pre_text, re.IGNORECASE)
            )
            has_subset_bridge = bool(
                SUBSET_REGEX.search(between)
                or re.search(r"\bwith\b", between, re.IGNORECASE)
            )
            worker_term_near = (
                get_min_distance_to_matches(
                    first_span,
                    self.analysis._matches,
                    [MatchType.WORKER_TERM],
                    look_backward=True,
                    look_forward=True,
                    text=self.analysis.text,
                )
                < 30
            )

            if (
                first_val == max_val
                and other_cov_sum > 0
                and worker_term_near
                and (has_intro_denominator or has_subset_bridge)
            ):
                self.data["employee_count_total"] = first_val
                self.data["employee_count_covered"] = max(0.0, other_cov_sum)
                if self.data["employee_count_covered"] <= first_val:
                    self.data["employee_count_not_covered"] = max(
                        0.0, first_val - self.data["employee_count_covered"]
                    )
                logic_notes.append(
                    f"Promoted introductory covered {first_val} to total and removed from covered"
                )

        if total_candidates:
            # 0. Check for subset/overlap indicators in single-country context
            # Re-gather assignments to check text between
            total_assignments = [
                item for item in count_assignments if item["type"] == "total"
            ]
            total_assignments.sort(key=lambda x: x["match"]["span"][0])

            explicit_countries = {
                m.geo_code
                for m in self.analysis.geo_matches
                if m.source_type == GeoSource.EXPLICIT
                and m.geo_code not in REGION_CODES
                and m.geo_code not in IGNORED_REGIONS
            }
            is_single_country = len(explicit_countries) == 1

            if len(total_assignments) > 1 and is_single_country:
                has_overlap_indicator = False
                for i in range(len(total_assignments) - 1):
                    m1 = total_assignments[i]["match"]
                    m2 = total_assignments[i + 1]["match"]
                    text_between = self.analysis.text[m1["span"][1] : m2["span"][0]]

                    # Check for subset indicators
                    if SUBSET_REGEX.search(text_between):
                        has_overlap_indicator = True
                        break

                    # Check for unbalanced parentheses (m2 is inside m1)
                    if text_between.count("(") > text_between.count(")"):
                        has_overlap_indicator = True
                        break

                if has_overlap_indicator:
                    max_cand = max(total_candidates)
                    total_candidates = [max_cand]
                    logic_notes.append(
                        f"Collapsed total candidates to {max_cand} (single country, overlap indicator)"
                    )

            # 1. Check for internal hierarchy in total_candidates (e.g. [3100, 1800, 1300] -> 3100)
            if len(total_candidates) > 1:
                max_cand = max(total_candidates)
                others_sum = sum(total_candidates) - max_cand
                if others_sum > 0 and abs(max_cand - others_sum) / max_cand < 0.10:
                    total_candidates = [max_cand]
                    logic_notes.append(
                        f"Collapsed total candidates to {max_cand} (sum of others)"
                    )

            # 2. Check against existing data (Parent vs Disjoint)
            current_total = self.data["employee_count_total"] or 0
            max_cand = max(total_candidates)
            full_parts_sum = (self.data["employee_count_covered"] or 0) + (
                self.data["employee_count_not_covered"] or 0
            )

            is_parent = False
            if max_cand > 0:
                if (
                    full_parts_sum > 0
                    and abs(max_cand - full_parts_sum) / max_cand < 0.10
                ):
                    is_parent = True
                elif (current_total + full_parts_sum) > 0 and abs(
                    max_cand - (current_total + full_parts_sum)
                ) / max_cand < 0.10:
                    is_parent = True

            if is_parent:
                self.data["employee_count_total"] = max(current_total, max_cand)
                logic_notes.append(
                    f"Identified parent total {self.data['employee_count_total']} (matches parts)"
                )
            else:
                self.data["employee_count_total"] = current_total + sum(
                    total_candidates
                )
                if len(total_candidates) > 1:
                    logic_notes.append(f"Summed totals: {total_candidates}")

        # Inferred Total Logic (Parts > Total)
        parts_sum = (self.data["employee_count_covered"] or 0) + (
            self.data["employee_count_not_covered"] or 0
        )
        current_total = self.data["employee_count_total"] or 0

        # Only infer if we have at least one part and the sum exceeds current total
        if parts_sum > 0 and parts_sum > current_total:
            # Only infer if we have both parts OR if total is missing
            has_both = (
                self.data["employee_count_covered"] is not None
                and self.data["employee_count_not_covered"] is not None
            )
            if has_both or current_total == 0:
                self.data["employee_count_total"] = parts_sum
                logic_notes.append(f"Inferred total {parts_sum} from parts")

        if logic_notes:
            current_note = self.data["note"] or ""
            sep = " | " if current_note else ""
            unique_notes = []
            for n in logic_notes:
                if n not in unique_notes:
                    unique_notes.append(n)
            self.data["note"] = current_note + sep + "; ".join(unique_notes)

    # def _handle_ratios(self):
    #     if self.analysis.ratios:
    #         numerator, denominator = self.analysis.ratios[0]

    #         # Find match for context
    #         ratio_match = next(
    #             (
    #                 m
    #                 for m in self.analysis._matches
    #                 if m["type"] == MatchType.RATIO
    #                 and m["val"] == (numerator, denominator)
    #             ),
    #             None,
    #         )

    #         is_negated = False
    #         if ratio_match:
    #             if self.analysis.negation_terms:
    #                 if check_local_negation(
    #                     ratio_match["span"], self.analysis.text, backward=50
    #                 ):
    #                     is_negated = True
    #                 else:
    #                     dist = get_min_distance_to_matches(
    #                         ratio_match["span"],
    #                         self.analysis._matches,
    #                         [MatchType.NON_UNION, MatchType.NON_COVERAGE],
    #                     )
    #                     if dist < 50:
    #                         is_negated = True

    #         # Existing counts
    #         existing_cov = self.data["employee_count_covered"] or 0
    #         existing_not_cov = self.data["employee_count_not_covered"] or 0
    #         existing_total = self.data["employee_count_total"] or 0

    #         # If the ratio represents a population smaller than what we've already found, ignore it
    #         # if (
    #         #     denominator < existing_cov
    #         #     or denominator < existing_not_cov
    #         #     or (existing_total > 0 and denominator < existing_total)
    #         # ):
    #         #     self.data["note"] = f"Ignored ratio (likely breakdown)"
    #         #     return

    #         # Ratio components
    #         if is_negated:
    #             ratio_not_cov = numerator
    #             ratio_cov = denominator - numerator
    #         else:
    #             ratio_cov = numerator
    #             ratio_not_cov = denominator - numerator

    #         # Combine
    #         final_cov = existing_cov + ratio_cov
    #         final_not_cov = existing_not_cov + ratio_not_cov
    #         final_total = final_cov + final_not_cov

    #         if final_total > 0:
    #             self.data["employee_count_covered"] = final_cov
    #             self.data["employee_count_not_covered"] = final_not_cov
    #             self.data["employee_count_total"] = final_total

    #             pct = (final_cov / final_total) * 100.0
    #             self.data["percentage"] = round(pct, 2)
    #             self.data["type"] = CoverageType.CALCULATED.value

    #             neg_str = " (negated)" if is_negated else ""
    #             self.data["note"] = (
    #                 f"Calculated from ratio: {numerator}/{denominator}{neg_str} + existing counts"
    #             )
    #             if is_negated:
    #                 self.data["negated"] = True
    #                 self.data["negation_type"] = NegationType.NOT_COVERED.value

    def _calculate_percentage_from_counts(self):
        if (
            self.data["percentage"] is None
            and self.data["employee_count_covered"] is not None
            and self.data["employee_count_total"]
        ):
            total = self.data["employee_count_total"]
            covered = self.data["employee_count_covered"]
            if total >= covered and total > 0:
                pct = (covered / total) * 100
                self.data["percentage"] = round(pct, 2)
                self.data["type"] = CoverageType.CALCULATED.value
                self.data["note"] = (
                    self.data["note"] or ""
                ) + f" | Calculated from count {covered} / total {total}"

    def _calculate_count_from_percentage(self):
        if (
            self.data["employee_count_covered"] is None
            and self.data["percentage"] is not None
            and self.data["employee_count_total"]
        ):
            self.data["employee_count_covered"] = round(
                (self.data["percentage"] / 100) * self.data["employee_count_total"]
            )
            self.data["note"] = (
                (self.data["note"] or "")
                + f" | Inferred count from {self.data['percentage']}% of {self.data['employee_count_total']}"
            )

    def _handle_negation(self):
        if not self.data["percentage"] and not self.data["employee_count_covered"]:
            if self.analysis.negation_terms:
                if any(NEGATION_REGEX.search(t) for t in self.analysis.negation_terms):
                    self.data["percentage"] = 0.0
                    self.data["negated"] = True
                    self.data["negation_type"] = NegationType.ZERO_COVERAGE.value
                    self.data["type"] = CoverageType.EXPLICIT_PERCENT.value
                elif any(
                    NON_COVERAGE_REGEX.search(t) for t in self.analysis.negation_terms
                ):
                    self.data["negated"] = True
                    self.data["negation_type"] = NegationType.NOT_COVERED.value


def is_simple_scenario(analysis: SentenceAnalysis) -> bool:
    """
    Determines if the sentence is simple enough for the SimpleCoverageAnalyzer.
    """

    effective_counts = get_effective_counts(analysis)
    # # 2.5 Simple Counts of Counts
    # if len(analysis.percentages) == 0 and len(effective_counts) == 2:
    #     return True
    # 3. Max 1 Percentage, Max 1 Count (avoid ambiguity)
    if len(analysis.percentages) > 1:
        return False
    if len(effective_counts) > 1:
        return False

    return True


def determine_geo_context(
    analysis: SentenceAnalysis,
    last_context: Optional[Dict[str, Any]],
    current_idx: int,
    last_idx: int,
    domestic_country_code: str = "US",
) -> Dict[str, Any]:
    """
    Resolves geographic context based on explicit matches, union names,
    language inference, or inheritance.
    """
    explicit_matches = [
        m for m in analysis.geo_matches if m.source_type == GeoSource.EXPLICIT
    ]

    # If domestic is unresolved, infer it when "domestic" is adjacent to a single
    # explicit country in the same sentence (no other ambiguity).
    unknown_domestic_codes = (
        INT_SET | UNK_SET
    )
    if domestic_country_code in unknown_domestic_codes and explicit_matches:
        domestic_explicit = [
            m for m in explicit_matches if m.geo_code in DOMESTIC_SET
        ]
        specific_explicit = [
            m
            for m in explicit_matches
            if m.geo_code
            and m.geo_code not in DOMESTIC_SET
            and m.geo_code not in INT_SET
            and m.geo_code not in GLOBAL_SET
            and m.geo_code not in AGG_SET
            and m.geo_code not in UNK_SET
            and m.geo_code not in REGION_CODES
        ]

        inferred_domestic = None
        if domestic_explicit and len(specific_explicit) == 1:
            candidate = specific_explicit[0]
            ambiguous = any(
                m.geo_code not in DOMESTIC_SET
                and m.geo_code != candidate.geo_code
                and m.geo_code not in REGION_CODES
                for m in explicit_matches
                if m.geo_code
            )
            if not ambiguous:
                # Check proximity between "domestic" and explicit country span.
                geo_spans = [
                    (m.get("geo_obj"), m.get("span"))
                    for m in analysis._matches
                    if "geo_obj" in m and "span" in m
                ]
                dom_spans = [
                    span for obj, span in geo_spans if obj in domestic_explicit
                ]
                cand_spans = [
                    span for obj, span in geo_spans if obj == candidate
                ]
                is_adjacent = False
                if dom_spans and cand_spans:
                    for d_span in dom_spans:
                        if d_span:
                            min_dist = get_min_distance_to_matches(
                                target_span=d_span,
                                matches=[
                                    {"type": MatchType.GEO, "span": c_span}
                                    for c_span in cand_spans
                                ],
                                match_types=[MatchType.GEO],
                                text=analysis.text,
                            )
                            if min_dist <= 40:
                                is_adjacent = True
                                break
                else:
                    # If spans are missing, fall back to sentence-level inference.
                    is_adjacent = True

                if is_adjacent:
                    inferred_domestic = candidate

        if inferred_domestic:
            for m in domestic_explicit:
                m.geo_code = inferred_domestic.geo_code
                m.country = inferred_domestic.country
                m.region = inferred_domestic.region

    # Check if we have any VALID explicit matches (not excluded, or excluded but remapped to INT)
    has_valid_explicit = False
    for m in explicit_matches:
        if not m.is_excluded or analysis.has_remaining_other:
            has_valid_explicit = True
            break
        # Special case: "Outside US" -> International (Valid Context)
        if m.is_excluded and m.geo_code == domestic_country_code and m.is_strict:
            has_valid_explicit = True
            break

    union_matches = [
        m
        for m in analysis.geo_matches
        if m.source_type in (GeoSource.SPECIFIC_UNION, GeoSource.INFERRED_UNION)
    ]

    # 1. Explicit Geography (Highest Priority)
    if has_valid_explicit:
        countries = []
        regions_list = []
        found_regions_map = {}  # code -> (region_dict, region_enum)
        seen_codes = set()
        regions = set()
        locations_by_country = {}  # code -> set of locations

        # Pass 1: Identify strong (specific) codes in this sentence to filter redundant INT_ codes
        strong_codes = set()
        for m in explicit_matches:
            if (
                m.geo_code
                and not m.geo_code.startswith(GeoCode.INT_LANG.value)
                and m.geo_code
                not in [GeoCode.INTERNATIONAL.value, GeoCode.GLOBAL.value]
            ):
                strong_codes.add(m.geo_code)
        has_other_specific_codes = bool(
            {c for c in strong_codes if c and c != domestic_country_code}
        )

        unusual_combo = False
        conflict_notes = []
        domestic_negated = False

        for m in explicit_matches:
            if m.is_excluded and not analysis.has_remaining_other:
                if m.geo_code == domestic_country_code:
                    # If specific non-domestic countries are already present (e.g. "non-US Canada/Mexico"),
                    # do not inject generic INT.
                    if has_other_specific_codes:
                        continue
                    domestic_negated = True
                    # Map "Outside Domestic" -> International
                    m.geo_code = GeoCode.INTERNATIONAL.value
                    m.country = "International"
                    m.region = Region.INTERNATIONAL
                else:
                    # Skip other excluded regions for now to avoid false positives
                    continue

            if m.city:
                if m.geo_code not in locations_by_country:
                    locations_by_country[m.geo_code] = set()
                locations_by_country[m.geo_code].add(m.city)

            # Refine INT_ codes (e.g. INT_DE) using context
            if (
                m.geo_code
                and m.geo_code.startswith(GeoCode.INT_LANG.value)
                and m.geo_code in INT_LANGUAGE_MAP
            ):
                allowed = INT_LANGUAGE_MAP[m.geo_code]
                # 1. If a specific country from this group is already explicit in this sentence, skip the generic INT_ code
                if strong_codes.intersection(allowed):
                    continue

                # 2. If not, check if we can inherit a specific country from the previous context
                if last_context:
                    last_countries = last_context.get("countries", [])
                    refined_code, refined_name = refine_generic_code(
                        m.geo_code, last_countries, domestic_country_code
                    )
                    if refined_code != m.geo_code:
                        # Inherit specific country details
                        # We construct a synthetic match-like object for processing
                        m_code = refined_code
                        m_name = refined_name
                        # Update region based on the inherited country
                        m_region_name = _CODE_TO_REGION.get(
                            m_code, Region.UNKNOWN.value
                        )
                        # Find enum from value (inefficient but safe)
                        m_region = next(
                            (r for r in Region if r.value == m_region_name),
                            Region.UNKNOWN,
                        )

                        # Override current match properties for the loop
                        m.geo_code = m_code
                        m.country = m_name
                        m.region = m_region

            if m.country and m.geo_code not in seen_codes:
                seen_codes.add(m.geo_code)

                if m.geo_code in REGION_CODES:
                    # It is a region entity
                    # Use region enum value for consistency with Tracker keys
                    r_obj = {
                        "name": m.region.value,
                        "code": m.geo_code,
                        "countries": [],
                    }
                    regions_list.append(r_obj)
                    found_regions_map[m.geo_code] = (r_obj, m.region)
                else:
                    # It is a country
                    countries.append(
                        {
                            "name": m.country,
                            "code": m.geo_code,
                            "region_enum": m.region,  # Temporary for mapping
                        }
                    )
            regions.add(m.region)

        # Check for conflicts between Explicit Regions and Union Name Regions
        if union_matches:
            for um in union_matches:
                # If the union implies a specific region (e.g. UAW -> North America)
                # and that region is NOT in the explicit regions list (e.g. Europe)
                if um.region and um.region not in regions:
                    # Ignore if explicit is "International" (too broad to conflict)
                    if Region.INTERNATIONAL not in regions:
                        unusual_combo = True
                        conflict_notes.append(
                            f"Union '{um.text}' ({um.region.value}) mismatches explicit region ({', '.join(r.value for r in regions)})"
                        )

        # Map countries to regions
        for c in countries:
            c_enum = c.get("region_enum")
            # Attach locations
            if c["code"] in locations_by_country:
                c["locations"] = sorted(list(locations_by_country[c["code"]]))
            else:
                c["locations"] = []

            for r_code, (r_obj, r_enum) in found_regions_map.items():
                # Map if in same broad region
                if c_enum == r_enum:
                    r_obj["countries"].append(
                        {
                            "name": c["name"],
                            "code": c["code"],
                            "locations": c["locations"],
                        }
                    )

            # Remove temporary field
            c.pop("region_enum", None)

        region_val = (
            Region.AGGREGATE.value
            if len(regions) > 1
            else (list(regions)[0].value if regions else Region.UNKNOWN.value)
        )

        union_names_map = {}
        if union_matches and countries:
            for c in countries:
                c_code = c["code"]
                check_code = (
                    domestic_country_code
                    if c_code == GeoCode.DOMESTIC.value
                    else c_code
                )

                specifics = []
                for um in union_matches:
                    if um.geo_code == check_code:
                        specifics.append(um.text)
                    elif um.geo_code and is_contained(
                        container_key=um.geo_code,
                        item_key=check_code,
                        domestic_country_code=domestic_country_code,
                    ):
                        specifics.append(um.text)
                    elif um.geo_code and um.geo_code in INT_LANGUAGE_MAP:
                        if check_code in INT_LANGUAGE_MAP[um.geo_code]:
                            specifics.append(um.text)
                if specifics:
                    union_names_map[c["code"]] = sorted(list(set(specifics)))

        union_name_indicator = None
        if union_matches and len(countries) == 1:
            union_name_indicator = " | ".join([m.text for m in union_matches])

        return {
            "region": region_val,
            "countries": countries,
            "regions": regions_list,
            "specificity": (
                Specificity.EXPLICIT.value
                if not union_matches
                else Specificity.EXPLICIT_INFERRED.value
            ),
            "explicit_countries": (
                [c["name"] for c in countries] if union_matches else None
            ),
            "unusual_union_region_combo": unusual_combo,
            "union_names_mentioned": (
                [m.text for m in union_matches] if union_matches else None
            ),
            "union_name_indicator": union_name_indicator,
            "note": "; ".join(conflict_notes) if conflict_notes else None,
            "union_names_map": union_names_map,
            "domestic_negated": domestic_negated,
        }

    # 2. Inferred from Union Name (Medium Priority)
    if union_matches:
        # Check for specific union inference
        specific_unions = [m for m in union_matches if m.country]
        if specific_unions:
            # Use the first specific union found
            m = specific_unions[0]

            # Refine generic/container union code (e.g. NA) using previous context
            # and domestic fallback for simple single-country filers.
            if m.geo_code:
                ctx_candidates = (last_context or {}).get("countries", [])
                refined_code, refined_name = refine_generic_code(
                    m.geo_code,
                    ctx_candidates,
                    domestic_country_code,
                )
                if refined_code != m.geo_code:
                    m.geo_code = refined_code
                    m.country = refined_name or m.country
                    refined_region_name = _CODE_TO_REGION.get(
                        refined_code, Region.UNKNOWN.value
                    )
                    m.region = next(
                        (r for r in Region if r.value == refined_region_name),
                        Region.UNKNOWN,
                    )

            # If union is generic (INT/GLO), check if we should inherit specific context instead
            if (
                m.geo_code in [GeoCode.INTERNATIONAL.value, GeoCode.GLOBAL.value]
                and last_context
            ):
                last_region = last_context.get("region")
                last_countries = last_context.get("countries", [])

                is_specific_prev = last_region not in IGNORED_REGIONS or (
                    last_countries and last_countries[0]["code"] not in IGNORED_REGIONS
                )

                if is_specific_prev:
                    strong_global_modifiers = {"global", "international"}
                    has_global_mod = any(
                        mod.lower() in strong_global_modifiers
                        for mod in analysis.total_modifiers
                    )

                    if not has_global_mod:
                        ctx = last_context.copy()
                        ctx["specificity"] = Specificity.INHERITED.value
                        ctx["inherited_from_sentence_index"] = last_idx
                        ctx["union_name_indicator"] = m.text
                        ctx.pop("explicit_countries", None)
                        return ctx

            return {
                "region": m.region.value,
                "countries": [{"name": m.country, "code": m.geo_code}],
                "specificity": Specificity.INFERRED_UNION.value,
                "union_name_indicator": m.text,
            }

        # Check for language-based inference (INT_ES, INT_PT, etc.)
        lang_matches = [m for m in union_matches if m.geo_code in INT_LANGUAGE_MAP]
        if lang_matches:
            m = lang_matches[0]
            assert m.geo_code is not None
            allowed_codes = INT_LANGUAGE_MAP[m.geo_code]

            # Try to resolve against last_context if available
            if last_context and last_context.get("countries") and m.geo_code:
                refined_code, refined_name = refine_generic_code(
                    m.geo_code, last_context["countries"], domestic_country_code
                )
                if refined_code != m.geo_code:
                    region_name = _CODE_TO_REGION.get(
                        refined_code, Region.UNKNOWN.value
                    )
                    return {
                        "region": region_name,
                        "countries": [{"code": refined_code, "name": refined_name}],
                        "specificity": Specificity.INFERRED_LANG.value,
                        "union_name_indicator": m.text,
                        "union_name_code": m.geo_code,
                        "note": f"Resolved language term '{m.text}' to {refined_name} from context",
                    }

            return {
                "region": Region.INTERNATIONAL.value,  # Broad region
                "countries": [],  # No specific country known
                "specificity": Specificity.INFERRED_LANG.value,
                "union_name_indicator": m.text,
                "union_name_code": m.geo_code,
                "note": f"Inferred from language term '{m.text}' ({m.geo_code})",
            }

    # 2.5 Global Modifiers (Stop Inheritance)
    # If the sentence contains modifiers that imply a global/consolidated scope,
    # treat it as International and do NOT inherit from previous context.
    strong_global_modifiers = {"global", "international"}
    if any(m.lower() in strong_global_modifiers for m in analysis.total_modifiers):
        return {
            "region": Region.INTERNATIONAL.value,
            "countries": [{"code": GeoCode.GLOBAL.value, "name": "Global"}],
            "specificity": Specificity.IMPLICIT.value,
            "note": "Inferred from global modifier",
        }

    # 3. Inheritance (Lowest Priority)
    if last_context:
        # Create a copy of the last context but mark as inherited
        ctx = last_context.copy()
        ctx["specificity"] = Specificity.INHERITED.value
        ctx["inherited_from_sentence_index"] = last_idx
        # Remove source-specific metadata
        ctx.pop("union_name_indicator", None)
        ctx.pop("explicit_countries", None)

        # Apply exclusions from current sentence to inherited context
        excluded_codes = {
            m.geo_code for m in explicit_matches if m.is_excluded and m.geo_code
        }
        if excluded_codes:
            if "countries" in ctx:
                ctx["countries"] = [
                    c for c in ctx["countries"] if c["code"] not in excluded_codes
                ]
            if "regions" in ctx:
                ctx["regions"] = [
                    r for r in ctx["regions"] if r["code"] not in excluded_codes
                ]

        return ctx

    # 4. Fallback
    return {
        "region": Region.UNKNOWN.value,
        "countries": [],
        "specificity": Specificity.IMPLICIT.value,
    }


def determine_relationship_status(analysis: SentenceAnalysis) -> Optional[str]:
    """
    Determines the status of labor relationships (Positive, Negative, Neutral).
    """
    if not analysis.relationship_terms:
        return None

    if not analysis.relationship_quality_terms:
        # Fallback: infer quality from relationship phrase when quality term was masked.
        rel_text = " ".join(analysis.relationship_terms).lower()
        for term in RELATIONSHIP_QUALITY_TERMS:
            if term in rel_text:
                analysis.relationship_quality_terms.append(term)
                break
        if not analysis.relationship_quality_terms:
            for term in RELATIONSHIP_NEGATIVE_TERMS:
                if term in rel_text:
                    analysis.relationship_quality_terms.append(term)
                    break
        if not analysis.relationship_quality_terms:
            for term in RELATIONSHIP_NEUTRAL_TERMS:
                if term in rel_text:
                    analysis.relationship_quality_terms.append(term)
                    break

    if not analysis.relationship_quality_terms:
        return None

    # Find the quality term closest to the relationship term
    # For simplicity, we'll take the first quality term found if we have a relationship term
    quality_term = analysis.relationship_quality_terms[0].lower()

    # Check for local negation of the quality term (e.g. "not good")
    q_match = next(
        (m for m in analysis._matches if m["type"] == MatchType.RELATIONSHIP_QUALITY),
        None,
    )

    is_quality_negated = (
        check_local_negation(q_match["span"], analysis.text, backward=25)
        if q_match
        else False
    )

    status = RelationshipStatus.UNKNOWN
    if quality_term in RELATIONSHIP_NEUTRAL_TERMS:
        status = (
            RelationshipStatus.NEGATIVE
            if is_quality_negated
            else RelationshipStatus.NEUTRAL
        )
    elif quality_term in RELATIONSHIP_QUALITY_TERMS:
        status = (
            RelationshipStatus.NEGATIVE
            if is_quality_negated
            else RelationshipStatus.POSITIVE
        )
    elif quality_term in RELATIONSHIP_NEGATIVE_TERMS:
        status = (
            RelationshipStatus.POSITIVE
            if is_quality_negated
            else RelationshipStatus.NEGATIVE
        )

    return status.value if status != RelationshipStatus.UNKNOWN else None


class Scope(Enum):
    GLOBAL = "GLOBAL"  # the catch all "global workforce"
    REGION = "REGION"  # Should not be used for counts; only as placeholders
    COUNTRY = "COUNTRY"  # Should not be used for counts; only as placeholders
    AGGREGATE = "AGGREGATE"
    SEGMENT = "SEGMENT"  # Any mention is a segment
    UNKNOWN = "UNKNOWN"


def _infer_source_type_from_detail(source: Optional[str]) -> str:
    if not source:
        return SourceType.UNKNOWN.value
    return DETAIL_TO_SOURCE_TYPE.get(source, SourceType.UNKNOWN.value)


@dataclass
# The coverage statement.
class Entry:
    """
    Records one entry to later merge.
    One a paragraph level: a firm starts with the total and then breaks it down
    Assuming one region per paragraph:
    REGION? -> COUNTRY? -> SEGMENT
    At the SEGMENT level, no sentence forward can refer to this population (ex. We have 100 covered at Union X)

    """

    covered_count: Optional[float] = (
        None  # If null, do not derive from total - not covered. Internal sentence logic dictates this
    )
    not_covered_count: Optional[float] = None
    percentage: Optional[float] = None
    total_count: Optional[float] = None  # The sum of covered + not covered.
    key: Optional[str] = (
        "unknown"  # Union name or location. Else it belongs to the generic bucket
    )
    is_qualitative: bool = False
    is_explicit: bool = (
        False  # The firm plainly states that it is the total of something within that scope
    )
    qualitative_bounds: Optional[Tuple[float, float]] = None
    is_remaining: bool = False
    is_negated: bool = False
    is_union_record: bool = False
    scope: Scope = Scope.UNKNOWN
    sent_idx: int = -1  # The sentence index
    related_geo_codes: List[str] = field(default_factory=list)
    is_dummy_percent: bool = False
    ambiguity_multiplier: Optional[float] = None
    is_exception_entry: bool = False
    exception_limit_percent: Optional[float] = None
    is_exception_remainder: bool = False
    is_parent_breakdown: bool = False
    is_covered_breakdown: bool = False
    is_not_covered_breakdown: bool = False
    # Provenance for distinguishing explicit vs calculated vs inferred/fallback values
    percentage_source: Optional[str] = None
    covered_count_source: Optional[str] = None
    not_covered_count_source: Optional[str] = None
    total_count_source: Optional[str] = None
    denominator_source: Optional[str] = None
    percentage_source_type: Optional[str] = None
    covered_count_source_type: Optional[str] = None
    not_covered_count_source_type: Optional[str] = None
    total_count_source_type: Optional[str] = None
    denominator_source_type: Optional[str] = None
    source_notes: List[str] = field(default_factory=list)

    def __post_init__(self):
        for field_name in (
            "percentage_source",
            "covered_count_source",
            "not_covered_count_source",
            "total_count_source",
            "denominator_source",
        ):
            source_val = getattr(self, field_name)
            type_field = f"{field_name}_type"
            if source_val and getattr(self, type_field) is None:
                setattr(self, type_field, _infer_source_type_from_detail(source_val))

    # Hash
    def __hash__(self):
        key = "--".join(
            [
                str(self.sent_idx),
                self.key or "",
                self.scope.value,
                str(self.is_union_record),
                str(self.is_qualitative),
                str(self.covered_count),
                str(self.total_count),
                str(self.not_covered_count),
                str(self.percentage),
            ]
        )
        return hash(key)


@dataclass
class BargainingEntry:
    bargaining_unit_count: float
    key: str
    scope: Scope
    sent_idx: int
    related_geo_codes: List[str] = field(default_factory=list)
    bargaining_unit_count_source: str = (
        CountSourceDetail.EXPLICIT_BARGAINING_UNIT_COUNT.value
    )
    bargaining_unit_count_source_type: str = SourceType.EXPLICIT.value


@dataclass
class ExplicitPctEntry:
    geo_code: str
    percentage: float
    sent_idx: int
    scope: Scope = Scope.COUNTRY
    percentage_source: str = PercentageSourceDetail.EXPLICIT_PERCENTAGE.value
    percentage_source_type: str = SourceType.EXPLICIT.value
    derived_total: Optional[float] = None
    derived_covered: Optional[float] = None
    derived_not_covered: Optional[float] = None
    derived_source: Optional[str] = None
    note: Optional[str] = None


class Tracker:
    """
    Tracks the 'Whole Pie' (Total Employee Counts) across different geographic scopes.
    Used to provide the correct denominator for coverage calculations.
    """

    def __init__(self, domestic_country_code: str = "US"):
        self.global_total: float = 0.0
        self.region_totals: Dict[str, float] = {}
        self.country_totals: Dict[str, float] = {}
        self.resolution_log: List[str] = []
        self.entries: List[Entry] = []
        self.bargaining_entries: List[BargainingEntry] = []
        self.explicit_pct_entries: List[ExplicitPctEntry] = []
        self._seen_bargaining_records: Set[Tuple[int, str, float]] = set()
        self._seen_explicit_pct_entries: Set[Tuple[int, str, float]] = set()
        # Start empty; only populate from actual detected context.
        self.mentioned_countries: set[str] = set()
        self.domestic_country_code = _normalize_domestic_country_code(
            domestic_country_code
        )
        self.total_union_keywords: int = 0
        self.global_sentence_keywords: Set[Tuple[int, str]] = set()
        self.global_table_keywords: Set[str] = set()
        self.country_sentence_keywords: Dict[str, Set[Tuple[int, str]]] = {}
        self.country_keywords: Dict[str, Dict[str, int]] = {}
        self.country_table_keywords: Dict[str, Set[str]] = {}
        self._boosted_rate_cache: Dict[
            Tuple[float, Optional[str]], Tuple[float, float]
        ] = {}
        self._limiter_countries: Set = {"CN", "VN"}
        self.is_using_virtual: bool = False
        self.domestic_is_negated: bool = False
        # Countries created via INT_* fallback mapping without explicit mention.
        self.language_fallback_countries: Set[str] = set()
        self.census_log: List[str] = []

    @staticmethod
    def _source_type_from_detail(source: Optional[str]) -> str:
        return _infer_source_type_from_detail(source)

    @staticmethod
    def _mark_source(entry: Entry, field_name: str, source: Optional[str]):
        if source:
            setattr(entry, field_name, source)
            if field_name.endswith("_source"):
                type_field = f"{field_name}_type"
                if hasattr(entry, type_field):
                    setattr(entry, type_field, Tracker._source_type_from_detail(source))

    @staticmethod
    def _add_source_note(entry: Entry, note: Optional[str]):
        if note:
            entry.source_notes.append(note)

    @staticmethod
    def _derive_count_source_from_percentage(
        entry: Entry, *, denominator_is_fallback: bool = False, census: bool = False
    ) -> str:
        """
        Derive count provenance from percentage provenance.
        """
        if denominator_is_fallback:
            return (
                CountSourceDetail.CALCULATED_FROM_PERCENTAGE_AND_FALLBACK_DENOMINATOR.value
            )

        p_src_type = entry.percentage_source_type
        if p_src_type is None and entry.percentage_source:
            p_src_type = Tracker._source_type_from_detail(entry.percentage_source)

        if p_src_type == SourceType.INFERRED.value:
            # Covers qualitative inferred percentages (e.g., "immaterial" -> 1%)
            return CountSourceDetail.INFERRED_FROM_INFERRED_PERCENTAGE.value

        if entry.is_dummy_percent:
            return CountSourceDetail.INFERRED_FROM_DUMMY_PERCENTAGE.value

        if census:
            return CountSourceDetail.CALCULATED_FROM_PERCENTAGE_AND_CENSUS_TOTAL.value
        return CountSourceDetail.CALCULATED_FROM_PERCENTAGE_AND_TOTAL.value

    @staticmethod
    def _initial_percentage_source(
        coverage_type: Optional[str], is_qualitative: bool, is_explicit: bool
    ) -> Optional[str]:
        # Qualitative provenance should always win for inferred soft percentages
        # (e.g. "immaterial" -> 1%), even if upstream flags leak explicit context.
        if coverage_type == CoverageType.QUALITATIVE.value or is_qualitative:
            return PercentageSourceDetail.QUALITATIVE_INFERRED_PERCENTAGE.value
        if coverage_type == CoverageType.EXPLICIT_PERCENT.value or is_explicit:
            return PercentageSourceDetail.EXPLICIT_PERCENTAGE.value
        if coverage_type == CoverageType.CALCULATED.value:
            return PercentageSourceDetail.CALCULATED_PERCENTAGE.value
        if coverage_type == CoverageType.REMAINING.value:
            return PercentageSourceDetail.REMAINING_STATEMENT.value
        if coverage_type == CoverageType.UNION_CONTEXT.value:
            return PercentageSourceDetail.UNION_CONTEXT_ONLY.value
        return None

    def _calculate_boosted_rate(
        self, base_rate: float, key: Optional[str] = None
    ) -> Tuple[float, float]:
        """
        Dynamically boosts an inferred base unionization rate using:
        1. A logistic keyword multiplier (saturating growth)
        2. A continuous elasticity factor based on the base rate
        """
        cache_key = (base_rate, key)
        if cache_key in self._boosted_rate_cache:
            return self._boosted_rate_cache[cache_key]

        k = self.total_union_keywords  # e.g., 56 in your Autoliv case
        k_specific = 0
        if key:
            specific_key = key
            if isinstance(specific_key, str) and specific_key in INT_SET:
                specific_key = GeoCode.INTERNATIONAL.value
            elif isinstance(specific_key, str) and specific_key in DOMESTIC_SET:
                specific_key = self.domestic_country_code

            k_specific = len(self.country_sentence_keywords.get(specific_key, set()))
            if k_specific == 0 and isinstance(key, str) and "::" in key:
                country_code = key.split("::")[0]
                k_specific = len(
                    self.country_sentence_keywords.get(country_code, set())
                )

        # -----------------------------
        # 1. Logistic keyword multiplier
        # -----------------------------
        # L = max added multiplier (beyond 1.0)
        # s = steepness
        # m = midpoint
        L = 1.5
        s = 0.35
        m = 5

        global_multiplier = 1 + (L / (1 + math.exp(-s * (k - m))))

        # 2. Specific Multiplier (Logistic - smaller scale)
        # Max boost, steeper curve (kicks in at 1-2 keywords)
        L_spec = 1.25
        s_spec = 0.5
        m_spec = 2
        specific_multiplier = 1.0
        if k_specific > 0:
            specific_multiplier = 1 + (
                L_spec / (1 + math.exp(-s_spec * (k_specific - m_spec)))
            )

        keyword_multiplier = global_multiplier + (specific_multiplier - 1.0)

        # -----------------------------
        # 2. Base-rate elasticity
        # -----------------------------
        # Low base rates → high elasticity
        # High base rates → low elasticity
        elasticity = 1 / math.sqrt(base_rate + 1e-6)
        elasticity = min(elasticity, 5.0)  # safety cap

        # -----------------------------
        # 3. Combine signals
        # -----------------------------
        # Elasticity scales how much of the keyword multiplier applies.
        multiplier = 1 + (keyword_multiplier - 1) * (elasticity / 5.0)

        # Cap boost for (Nominal/State-controlled unions often have high keyword density but low effective bargaining variation)
        if key and (key.split("::")[0] in self._limiter_countries):
            multiplier = min(multiplier, 1.15)

        # -----------------------------
        # 4. Final boosted rate
        # -----------------------------
        boosted_rate = min(base_rate * multiplier, 0.95)

        self._boosted_rate_cache[cache_key] = (boosted_rate, multiplier)
        return boosted_rate, multiplier

    def update(self, count: float, geo_context: Dict[str, Any]):
        # 1. Update Lookups (Keep for analyze_block usage)
        # This logic is simplified to just maintain max values for lookups
        # The actual rate calculation will happen in calculate_metrics using self.entries
        self.census_log.append(
            f"update(count={count}, region={geo_context.get('region')}, "
            f"codes={[c.get('code') for c in geo_context.get('countries', [])]})"
        )
        region = geo_context.get("region")
        countries = geo_context.get("countries", [])
        regions = geo_context.get("regions", [])
        codes = {c.get("code") for c in countries}
        is_unknown_region = region in UNK_SET

        # 1. Global Update
        if GeoCode.GLOBAL.value in codes:
            self.global_total = max(self.global_total, count)
        elif is_unknown_region:
            # Unknown only contributes to lookup global when no single-country
            # attribution is possible.
            if not codes or len(countries) != 1:
                self.global_total = max(self.global_total, count)

        # 2. Regional Update
        if region and not is_unknown_region:
            # If International Region, only update if it's NOT Global code
            if region == Region.INTERNATIONAL.value and GeoCode.GLOBAL.value in codes:
                pass
            else:
                current = self.region_totals.get(region, 0)
                if count > current:
                    self.region_totals[region] = count

        # 3. Country Update
        if len(countries) == 1:
            c = countries[0]
            code = c["code"]

            # Check for disjoint regions (e.g. "US and Europe")
            is_disjoint = False
            if regions:
                country_region_name = _CODE_TO_REGION.get(code)
                for r in regions:
                    r_name = r.get("name")
                    if r_name and r_name != country_region_name:
                        is_disjoint = True
                        break

            if not is_disjoint:
                if code == GeoCode.DOMESTIC.value:
                    code = self.domestic_country_code
                # Route container/composite keys to region totals, not country totals.
                if self._is_container_geo_key(code):
                    target_region = _CODE_TO_REGION.get(code, code)
                    if count > self.region_totals.get(target_region, 0):
                        self.region_totals[target_region] = count
                else:
                    if count > self.country_totals.get(code, 0):
                        self.country_totals[code] = count

    def _is_container_geo_key(self, key: Optional[str]) -> bool:
        if not key:
            return False
        if isinstance(key, str) and key.startswith("SUB::"):
            return False
        base = str(key).split("::")[0]
        return (
            base in IGNORED_REGIONS
            or base in REGION_CODES
            or base in COMPOSITE_COUNTRIES
            or is_region(base)
        )

    def _is_subtraction_segment_key(self, key: Optional[str]) -> bool:
        return bool(isinstance(key, str) and key.startswith("SUB::"))

    def _subtraction_region_name(self, key: Optional[str]) -> Optional[str]:
        if not self._is_subtraction_segment_key(key):
            return None
        assert isinstance(key, str)
        region_token = key[len("SUB::") :]
        if not region_token:
            return None
        return _CODE_TO_REGION.get(region_token, region_token)

    def _segment_anchor_code(self, key: Optional[str]) -> Optional[str]:
        if not isinstance(key, str) or "::" not in key:
            return None
        if self._is_subtraction_segment_key(key):
            region_name = self._subtraction_region_name(key)
            if not region_name:
                return None
            return self._region_to_pseudo_country_code(region_name)
        return key.split("::")[0]

    def _segment_matches_country(
        self, seg_key: Optional[str], country_code: str
    ) -> bool:
        if not country_code:
            return False
        anchor = self._segment_anchor_code(seg_key)
        return bool(anchor and anchor == country_code)

    def _scope_bucket_for_denominator(self, entry: Entry) -> Optional[Tuple[str, str]]:
        """
        Normalize an entry to a denominator-dedup bucket:
        - Segments roll up to their anchor country
        - Countries keep their ISO key
        - Regions use canonical region names
        - Global aliases collapse to GLOBAL
        """
        if entry.total_count is None or entry.total_count <= 0:
            return None

        if entry.scope == Scope.SEGMENT:
            anchor = self._segment_anchor_code(entry.key)
            if not anchor or self._is_container_geo_key(anchor):
                return None
            return (Scope.COUNTRY.value, anchor)

        if entry.scope == Scope.COUNTRY:
            key = str(entry.key) if entry.key is not None else ""
            if not key or self._is_container_geo_key(key):
                return None
            return (Scope.COUNTRY.value, key)

        if entry.scope == Scope.REGION:
            key = str(entry.key) if entry.key is not None else ""
            if not key:
                return None
            if key in GLOBAL_SET or key in INT_SET:
                return (Scope.GLOBAL.value, Scope.GLOBAL.value)
            return (Scope.REGION.value, _CODE_TO_REGION.get(key, key))

        if entry.scope == Scope.GLOBAL:
            return (Scope.GLOBAL.value, Scope.GLOBAL.value)

        key = str(entry.key) if entry.key is not None else ""
        if key in GLOBAL_SET or key in INT_SET:
            return (Scope.GLOBAL.value, Scope.GLOBAL.value)
        return None

    def _expected_total_for_bucket(self, bucket: Tuple[str, str]) -> float:
        scope_type, scope_key = bucket
        if scope_type == Scope.COUNTRY.value:
            return float(self.country_totals.get(scope_key, 0.0) or 0.0)
        if scope_type == Scope.REGION.value:
            canonical = _CODE_TO_REGION.get(scope_key, scope_key)
            return float(
                self.region_totals.get(scope_key, 0.0)
                or self.region_totals.get(canonical, 0.0)
                or 0.0
            )
        if scope_type == Scope.GLOBAL.value:
            return float(self.global_total or 0.0)
        return 0.0

    def _pick_denominator_keeper(
        self, candidates: List[Entry], bucket: Tuple[str, str]
    ) -> Entry:
        scope_type, scope_key = bucket

        def _is_scope_anchor(e: Entry) -> int:
            if scope_type == Scope.COUNTRY.value:
                return int(e.scope == Scope.COUNTRY and str(e.key) == scope_key)
            if scope_type == Scope.REGION.value:
                key = _CODE_TO_REGION.get(str(e.key), str(e.key))
                return int(e.scope == Scope.REGION and key == scope_key)
            if scope_type == Scope.GLOBAL.value:
                key = str(e.key) if e.key is not None else ""
                return int(
                    e.scope == Scope.GLOBAL or key in GLOBAL_SET or key in INT_SET
                )
            return 0

        def _source_priority(e: Entry) -> int:
            src_type = e.total_count_source_type or SourceType.UNKNOWN.value
            if src_type == SourceType.EXPLICIT.value:
                return 4
            if src_type == SourceType.INHERITED.value:
                return 3
            if src_type == SourceType.CALCULATED.value:
                return 2
            if src_type == SourceType.INFERRED.value:
                return 1
            return 0

        def _score(e: Entry) -> Tuple[int, int, int, int, int, int]:
            return (
                _is_scope_anchor(e),
                _source_priority(e),
                int(e.is_explicit or False),
                int(e.covered_count is not None or e.not_covered_count is not None),
                int(e.percentage is not None),
                -abs(e.sent_idx) if e.sent_idx >= 0 else -10_000,
            )

        return max(candidates, key=_score)

    def _clear_duplicate_denominator(
        self,
        duplicate: Entry,
        keeper: Entry,
        bucket: Tuple[str, str],
        basis_total: float,
    ) -> None:
        old_total = duplicate.total_count
        duplicate.total_count = None
        duplicate.total_count_source = None
        duplicate.total_count_source_type = SourceType.UNKNOWN.value
        duplicate.denominator_source = None
        duplicate.denominator_source_type = SourceType.UNKNOWN.value
        self._add_source_note(
            duplicate,
            f"Removed duplicate denominator {old_total} in {bucket[0]}:{bucket[1]} (kept {keeper.key} total ~{basis_total}).",
        )
        self.resolution_log.append(
            f"Deduped denominator for {duplicate.key}: removed {old_total} in {bucket[0]}:{bucket[1]} (keeper={keeper.key}, basis~{basis_total})."
        )

    def _dedupe_redundant_scope_denominators(self) -> None:
        """
        De-duplicates repeated denominators within the same resolved scope.
        This prevents repeated references to the same population from inflating
        downstream summed totals.
        """
        buckets: Dict[Tuple[str, str], List[Entry]] = {}
        for e in self.entries:
            if e.is_parent_breakdown:
                continue
            bucket = self._scope_bucket_for_denominator(e)
            if not bucket:
                continue
            buckets.setdefault(bucket, []).append(e)

        for bucket, entries in buckets.items():
            if len(entries) < 2:
                continue

            expected_total = self._expected_total_for_bucket(bucket)
            tol = self._get_tolerance(entries, base_threshold=0.08)

            if expected_total > 0:
                expected_matches = [
                    e
                    for e in entries
                    if e.total_count is not None
                    and self._matches_census(
                        e.total_count, expected_total, threshold=tol
                    )
                ]
                if len(expected_matches) > 1:
                    keeper = self._pick_denominator_keeper(expected_matches, bucket)
                    for dup in expected_matches:
                        if dup is keeper:
                            continue
                        self._clear_duplicate_denominator(
                            duplicate=dup,
                            keeper=keeper,
                            bucket=bucket,
                            basis_total=expected_total,
                        )

            active = [
                e for e in entries if e.total_count is not None and e.total_count > 0
            ]
            if len(active) < 2:
                continue

            active.sort(key=lambda x: x.total_count or 0.0, reverse=True)
            seen: Set[int] = set()
            cluster_tol = self._get_tolerance(active, base_threshold=0.06)

            for i, base in enumerate(active):
                if id(base) in seen or base.total_count is None:
                    continue
                cluster = [base]
                seen.add(id(base))

                for j in range(i + 1, len(active)):
                    other = active[j]
                    if id(other) in seen or other.total_count is None:
                        continue
                    if self._matches_census(
                        base.total_count, other.total_count, threshold=cluster_tol
                    ):
                        cluster.append(other)
                        seen.add(id(other))

                if len(cluster) <= 1:
                    continue

                keeper = self._pick_denominator_keeper(cluster, bucket)
                basis = (
                    keeper.total_count
                    if keeper.total_count is not None
                    else (base.total_count or 0.0)
                )
                for dup in cluster:
                    if dup is keeper:
                        continue
                    self._clear_duplicate_denominator(
                        duplicate=dup,
                        keeper=keeper,
                        bucket=bucket,
                        basis_total=basis,
                    )

    def register_sentence_keywords(
        self,
        sentence_index: int,
        keywords: Optional[List[str]],
        is_table_generated: bool = False,
    ) -> None:
        if sentence_index < 0 or not keywords:
            return
        if is_table_generated:
            for kw in keywords:
                if not kw:
                    continue
                self.global_table_keywords.add(kw)
                # Collapse table keyword impact by keyword (not by row/sentence),
                # because generated table lines can repeat the same union terms.
                self.global_sentence_keywords.add((-1, kw))
        else:
            for kw in keywords:
                self.global_sentence_keywords.add((sentence_index, kw))
        self.total_union_keywords = len(self.global_sentence_keywords)

    def register_mentions(self, geo_context: Dict[str, Any]):
        if geo_context.get("domestic_negated"):
            self.domestic_is_negated = True

        countries = geo_context.get("countries", [])
        for c in countries:
            if c.get("code"):
                code = c["code"]
                if code == GeoCode.DOMESTIC.value:
                    code = self.domestic_country_code
                self.mentioned_countries.add(code)
        regions = geo_context.get("regions", [])
        for r in regions:
            if r.get("code"):
                self.mentioned_countries.add(r["code"])

    def record_context(self, geo_context: Dict[str, Any], note: str):
        """Records qualitative context that shouldn't affect calculations."""
        region = geo_context.get("region", "Unknown")
        self.resolution_log.append(f"Context ({region}): {note}")

    def resolve(self):
        """
        Resolves counts: If the location's sum > country, update country. If the country's sum > region, update region.
        If no region exists create a key and update.
        No updates to global here.
        """
        # Ensure all country_totals are in mentioned_countries
        for code in self.country_totals:
            self.mentioned_countries.add(code)

        # Build map of region -> mentioned countries
        mentioned_in_region = {}
        for code in self.mentioned_countries:
            r_name = _CODE_TO_REGION.get(code)
            if r_name:
                if r_name not in mentioned_in_region:
                    mentioned_in_region[r_name] = set()
                mentioned_in_region[r_name].add(code)

        # 0. Global -> Region (if singular)
        active_regions = set()
        for r in set(self.region_totals.keys()) | set(mentioned_in_region.keys()):
            if r not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
                active_regions.add(r)

        # If domestic is negated, treat International as an implicitly active region
        # This prevents distributing the entire Global total to the Domestic region
        if self.domestic_is_negated:
            active_regions.add(Region.INTERNATIONAL.value)

        if self.global_total > 0 and len(active_regions) == 1:
            target_region = list(active_regions)[0]
            current_r_total = self.region_totals.get(target_region, 0.0)
            if self.global_total > current_r_total:
                self.region_totals[target_region] = self.global_total
                self.resolution_log.append(
                    f"Updated region '{target_region}' from {current_r_total} to {self.global_total} based on global total (single region context)."
                )

        # Aggregate countries to regions
        region_aggs = {}
        # countries_in_region = {}
        for code, count in self.country_totals.items():
            region_name = _CODE_TO_REGION.get(code)
            if region_name:
                region_aggs[region_name] = region_aggs.get(region_name, 0.0) + count

        # Update region totals if sum of countries is greater
        for r_name, agg_count in region_aggs.items():
            current = self.region_totals.get(r_name, 0.0)
            if agg_count > current:
                self.region_totals[r_name] = agg_count
                self.resolution_log.append(
                    f"Updated region '{r_name}' from {current} to {agg_count} based on country sum."
                )

        # If only 1 country exists in a region, and the region total is larger than the country, update that country's total.
        for r_name, codes in mentioned_in_region.items():
            if len(codes) == 1:
                code = list(codes)[0]
                r_total = self.region_totals.get(r_name, 0.0)
                c_total = self.country_totals.get(code, 0.0)

                # Handle negated domestic country (Ambiguity Penalty)
                if self.domestic_is_negated and code == self.domestic_country_code:
                    if r_total > c_total:
                        dist, note = weighted_division(
                            r_total,
                            [{"key": code}],
                            domestic_country=self.domestic_country_code,
                            excluded_keys={code},
                        )
                        allocated = dist.get(code, 0.0)
                        if allocated > c_total:
                            self.country_totals[code] = allocated
                            self.resolution_log.append(
                                f"Updated country '{code}' from {c_total} to {allocated} (of {r_total}) using weighted division (Domestic Negated). {note}"
                            )
                    continue

                if r_total > c_total:
                    self.country_totals[code] = r_total
                    self.resolution_log.append(
                        f"Updated country '{code}' from {c_total} to {r_total} based on region '{r_name}' total (single country)."
                    )

    def record_coverage(
        self,
        percentage: Optional[float],
        covered_count: Optional[float],
        geo_context: Dict[str, Any],
        scope_total: Optional[float] = None,
        not_covered_count: Optional[float] = None,
        is_qualitative: bool = False,
        qualitative_bounds: Optional[Tuple[float, float]] = None,
        is_remaining: bool = False,
        is_explicit: bool = False,
        is_negated: bool = False,
        is_union_record: bool = False,
        sentence_index: int = -1,
        keywords: Optional[List[str]] = None,
        ambiguity_multiplier: Optional[float] = None,
        is_exception_entry: bool = False,
        exception_limit_percent: Optional[float] = None,
        is_exception_remainder: bool = False,
        coverage_type: Optional[str] = None,
        is_table_generated: bool = False,
    ):
        """
        Records coverage data (rate or count) for a specific geographic scope.
        """
        if sentence_index < 0:
            return

        keywords = keywords or []

        if geo_context.get("domestic_negated"):
            self.domestic_is_negated = True

        # Safe fallback in case pass-1 registration did not occur.
        self.register_sentence_keywords(
            sentence_index, keywords, is_table_generated=is_table_generated
        )

        countries = geo_context.get("countries", [])
        keyword_target_codes: List[str] = []

        for c in countries:
            code = c.get("code")
            if not code:
                continue
            if code == GeoCode.DOMESTIC.value:
                code = self.domestic_country_code
            keyword_target_codes.append(code)

        # If no explicit country is present, still route keyword signal to a
        # concrete key (domestic or region/composite pseudo-country).
        if not keyword_target_codes:
            region_key = geo_context.get("region")
            if region_key in DOMESTIC_SET:
                keyword_target_codes.append(self.domestic_country_code)
            elif region_key in INT_SET:
                keyword_target_codes.append(GeoCode.INTERNATIONAL.value)
            elif isinstance(region_key, str):
                pseudo = self._region_to_pseudo_country_code(region_key)
                if pseudo:
                    keyword_target_codes.append(pseudo)

            for r in geo_context.get("regions", []) or []:
                r_key = r.get("code") or r.get("name")
                if not r_key:
                    continue
                if r_key in DOMESTIC_SET:
                    keyword_target_codes.append(self.domestic_country_code)
                    continue
                if r_key in INT_SET:
                    keyword_target_codes.append(GeoCode.INTERNATIONAL.value)
                    continue
                pseudo = self._region_to_pseudo_country_code(str(r_key))
                if pseudo:
                    keyword_target_codes.append(pseudo)

            # "non-[domestic]" without specifics should still map to INT.
            if geo_context.get("domestic_negated") and not keyword_target_codes:
                keyword_target_codes.append(GeoCode.INTERNATIONAL.value)

        # Preserve insertion order while deduping.
        keyword_target_codes = list(dict.fromkeys(keyword_target_codes))

        for code in keyword_target_codes:
            if code not in self.country_keywords:
                self.country_keywords[code] = {}
            if code not in self.country_sentence_keywords:
                self.country_sentence_keywords[code] = set()
            if code not in self.country_table_keywords:
                self.country_table_keywords[code] = set()

            for kw in keywords:
                # Check if keyword implies a specific geography to avoid cross-contamination
                check_kw = kw
                if "::" in kw:
                    check_kw = kw.split("::")[1]

                union_info = RegionMatcher.get_union(check_kw)
                if union_info:
                    _, _, u_code = union_info

                    # Case 1: Union is specific to a concrete country (e.g. DE).
                    # Apply strict mismatch filtering only for country-scoped codes,
                    # not for container scopes such as NA/EU/composites.
                    if u_code in INT_LANGUAGE_MAP:
                        # Case 2: Union is language-specific (e.g. INT_ES)
                        allowed_countries = INT_LANGUAGE_MAP[u_code]
                        if len(code) == 2 and code not in allowed_countries:
                            continue
                    elif u_code:
                        is_concrete_country_union = (
                            len(u_code) == 2
                            and u_code not in DOMESTIC_SET
                            and u_code not in INT_SET
                            and u_code not in GLOBAL_SET
                            and not self._is_container_geo_key(u_code)
                        )
                        if is_concrete_country_union:
                            if len(code) == 2 and code != u_code:
                                continue
                        else:
                            # Container union code (e.g. NA): allow contained
                            # countries and block unrelated concrete countries.
                            if len(code) == 2 and (
                                not is_contained(
                                    container_key=u_code,
                                    item_key=code,
                                    domestic_country_code=self.domestic_country_code,
                                )
                            ):
                                continue

                if is_table_generated:
                    # For generated table rows, dedupe repeated keywords before
                    # assigning country/global keyword weight.
                    if kw in self.country_table_keywords[code]:
                        continue
                    self.country_table_keywords[code].add(kw)
                    self.country_sentence_keywords[code].add((-1, kw))
                else:
                    self.country_sentence_keywords[code].add((sentence_index, kw))

                self.country_keywords[code][kw] = (
                    self.country_keywords[code].get(kw, 0) + 1
                )

        region = geo_context.get("region")
        countries = geo_context.get("countries", [])
        union_name = geo_context.get("union_name_indicator")
        union_names_map = geo_context.get("union_names_map", {})

        # Determine scope
        scope = Scope.GLOBAL
        key = scope.value

        codes = [c.get("code") for c in countries]

        if region and region not in INT_SET | UNK_SET:
            scope = Scope.REGION
            key = region
        elif region in INT_SET:
            if GeoCode.GLOBAL.value in codes:
                scope = Scope.GLOBAL
                key = Scope.GLOBAL.value
            else:
                scope = Scope.REGION
                key = region
        elif region in AGG_SET:
            scope = Scope.AGGREGATE
            key = Region.AGGREGATE.value
        elif region in UNK_SET:
            # Unknown geography should only collapse to domestic when we have a
            # single-country context. Otherwise treat as global.
            if len(countries) == 1:
                c_code = countries[0].get("code")
                key = (
                    self.domestic_country_code
                    if c_code in DOMESTIC_SET | {GeoCode.DOMESTIC.value}
                    else c_code
                )
                scope = Scope.COUNTRY
            elif len(countries) > 1:
                key = Scope.GLOBAL.value
                scope = Scope.GLOBAL
            else:
                # Keep Unknown explicit; resolve later in _route_domestic based on
                # whether we have a domestic-only union context.
                key = Region.UNKNOWN.value
                scope = Scope.REGION

        if len(countries) == 1:
            country_code = countries[0]["code"]
            if country_code == GeoCode.DOMESTIC.value:
                country_code = self.domestic_country_code
            scope = Scope.SEGMENT
            key = f"{country_code}::Segment_{len(self.entries)}"

        elif len(countries) > 1:
            if region in UNK_SET:
                scope = Scope.GLOBAL
                key = Scope.GLOBAL.value
            else:
                scope = Scope.AGGREGATE
                key = region if region else Scope.AGGREGATE.value

        # Handle splitting of multiple countries if specific unions are mapped
        if len(countries) > 1 and union_names_map:
            pct_source = self._initial_percentage_source(
                coverage_type, is_qualitative, is_explicit
            )
            for c in countries:
                c_code = c["code"]
                real_code = (
                    self.domestic_country_code
                    if c_code == GeoCode.DOMESTIC.value
                    else c_code
                )

                u_names = union_names_map.get(c_code)
                if u_names:
                    key_suffix = " | ".join(u_names)
                    key = f"{real_code}::{key_suffix}"
                    scope = Scope.SEGMENT
                else:
                    key = f"{real_code}::Segment_{len(self.entries)}"
                    scope = Scope.SEGMENT

                # For split entries, we only propagate percentage if it applies to the group.
                # Counts are set to None to avoid double-counting the aggregate total,
                # unless we implement weighted division here (which is handled elsewhere).
                self.entries.append(
                    Entry(
                        covered_count=covered_count if percentage is not None else None,
                        not_covered_count=None,
                        percentage=percentage,
                        total_count=scope_total if percentage is not None else None,
                        key=key,
                        is_qualitative=is_qualitative,
                        qualitative_bounds=qualitative_bounds,
                        is_remaining=is_remaining,
                        is_explicit=is_explicit,
                        is_union_record=is_union_record,
                        is_negated=is_negated,
                        scope=scope,
                        sent_idx=sentence_index,
                        related_geo_codes=[real_code],
                        ambiguity_multiplier=ambiguity_multiplier,
                        is_exception_entry=is_exception_entry,
                        exception_limit_percent=exception_limit_percent,
                        is_exception_remainder=is_exception_remainder,
                        percentage_source=pct_source,
                        covered_count_source=(
                            CountSourceDetail.SPLIT_ALLOCATED_COVERED_COUNT.value
                            if (covered_count is not None and percentage is not None)
                            else None
                        ),
                        total_count_source=(
                            TotalSourceDetail.SPLIT_SCOPE_TOTAL.value
                            if percentage is not None
                            else None
                        ),
                        denominator_source=(
                            DenominatorSourceDetail.SPLIT_SCOPE_TOTAL.value
                            if percentage is not None
                            else None
                        ),
                    )
                )
            return

        if union_name:
            if countries and countries[0].get("code"):
                country_code = countries[0]["code"]
                if country_code == GeoCode.DOMESTIC.value:
                    country_code = self.domestic_country_code
                scope = Scope.SEGMENT
                key = f"{country_code}::{union_name}"
            else:
                # Language-only inferred unions (INT_*) may not resolve to a
                # concrete country yet; preserve code-tagged context safely.
                union_name_code = geo_context.get("union_name_code")
                if isinstance(union_name_code, str) and union_name_code.startswith(
                    GeoCode.INT_LANG.value
                ):
                    scope = Scope.SEGMENT
                    key = f"{union_name_code}::{union_name}"

        related_codes = [c["code"] for c in countries if c.get("code")]
        if "regions" in geo_context:
            related_codes.extend(
                [r["code"] for r in geo_context["regions"] if r.get("code")]
            )
            related_codes.extend(
                [r["name"] for r in geo_context["regions"] if r.get("name")]
            )

        pct_source = self._initial_percentage_source(
            coverage_type, is_qualitative, is_explicit
        )
        # Do not mark counts as explicit when the driving signal is qualitative.
        # Example: "immaterial" -> inferred 1% then derived counts from a total.
        if covered_count is not None:
            if coverage_type == CoverageType.QUALITATIVE.value or is_qualitative:
                covered_source = (
                    CountSourceDetail.INFERRED_FROM_INFERRED_PERCENTAGE.value
                )
            else:
                covered_source = CountSourceDetail.EXPLICIT_COVERED_COUNT.value
        else:
            covered_source = None

        if not_covered_count is not None:
            if coverage_type == CoverageType.QUALITATIVE.value or is_qualitative:
                not_covered_source = (
                    CountSourceDetail.INFERRED_FROM_INFERRED_PERCENTAGE.value
                )
            else:
                not_covered_source = CountSourceDetail.EXPLICIT_NOT_COVERED_COUNT.value
        else:
            not_covered_source = None

        total_source = (
            TotalSourceDetail.EXPLICIT_SCOPE_TOTAL.value
            if scope_total is not None
            else None
        )

        self.entries.append(
            Entry(
                covered_count=covered_count,
                not_covered_count=not_covered_count,
                percentage=percentage,
                total_count=scope_total,
                key=key,
                is_qualitative=is_qualitative,
                qualitative_bounds=qualitative_bounds,
                is_remaining=is_remaining,
                is_explicit=is_explicit,
                is_union_record=is_union_record,
                is_negated=is_negated,
                scope=scope,
                sent_idx=sentence_index,
                related_geo_codes=related_codes,
                ambiguity_multiplier=ambiguity_multiplier,
                is_exception_entry=is_exception_entry,
                exception_limit_percent=exception_limit_percent,
                is_exception_remainder=is_exception_remainder,
                percentage_source=pct_source,
                covered_count_source=covered_source,
                not_covered_count_source=not_covered_source,
                total_count_source=total_source,
                denominator_source=(
                    DenominatorSourceDetail.EXPLICIT_SCOPE_TOTAL.value
                    if scope_total is not None
                    else None
                ),
            )
        )

    def record_bargaining_units(
        self,
        bargaining_unit_count: Optional[float],
        geo_context: Dict[str, Any],
        sentence_index: int = -1,
    ) -> None:
        if sentence_index < 0 or bargaining_unit_count is None:
            return
        if bargaining_unit_count <= 0:
            return

        region = geo_context.get("region")
        countries = geo_context.get("countries", [])

        scope = Scope.GLOBAL
        key = scope.value

        codes = [c.get("code") for c in countries]

        if region and region not in INT_SET | UNK_SET:
            scope = Scope.REGION
            key = region
        elif region in INT_SET:
            if GeoCode.GLOBAL.value in codes:
                scope = Scope.GLOBAL
                key = Scope.GLOBAL.value
            else:
                scope = Scope.REGION
                key = region
        elif region in AGG_SET:
            scope = Scope.AGGREGATE
            key = Region.AGGREGATE.value
        elif region in UNK_SET:
            if len(countries) == 1:
                c_code = countries[0].get("code")
                key = self.domestic_country_code if c_code in DOMESTIC_SET else c_code
                scope = Scope.COUNTRY
            elif len(countries) > 1:
                key = Scope.GLOBAL.value
                scope = Scope.GLOBAL
            else:
                key = Region.UNKNOWN.value
                scope = Scope.REGION

        if len(countries) == 1:
            country_code = countries[0]["code"]
            if country_code == GeoCode.DOMESTIC.value:
                country_code = self.domestic_country_code
            scope = Scope.SEGMENT
            key = f"{country_code}::Segment_{len(self.bargaining_entries)}"
        elif len(countries) > 1:
            if region in UNK_SET:
                scope = Scope.GLOBAL
                key = Scope.GLOBAL.value
            else:
                scope = Scope.AGGREGATE
                key = region if region else Scope.AGGREGATE.value

        related_codes = [c["code"] for c in countries if c.get("code")]
        if "regions" in geo_context:
            related_codes.extend(
                [r["code"] for r in geo_context["regions"] if r.get("code")]
            )
            related_codes.extend(
                [r["name"] for r in geo_context["regions"] if r.get("name")]
            )

        normalized_related_codes: List[str] = []
        for code in related_codes:
            if code == GeoCode.DOMESTIC.value:
                code = self.domestic_country_code
            if code not in normalized_related_codes:
                normalized_related_codes.append(code)

        assert isinstance(key, str)
        dedupe_key = (sentence_index, key, float(bargaining_unit_count))
        if dedupe_key in self._seen_bargaining_records:
            return
        self._seen_bargaining_records.add(dedupe_key)

        self.bargaining_entries.append(
            BargainingEntry(
                bargaining_unit_count=float(bargaining_unit_count),
                key=key,
                scope=scope,
                sent_idx=sentence_index,
                related_geo_codes=normalized_related_codes,
            )
        )

    def record_explicit_pct_entries(
        self, entries: Optional[List[Dict[str, Any]]]
    ) -> None:
        if not entries:
            return

        for e in entries:
            code = e.get("geo_code")
            pct = e.get("percentage")
            sent_idx = e.get("sentence_index", -1)
            if not code or pct is None:
                continue
            dedupe_key = (int(sent_idx), str(code), float(pct))
            if dedupe_key in self._seen_explicit_pct_entries:
                continue
            self._seen_explicit_pct_entries.add(dedupe_key)
            self.explicit_pct_entries.append(
                ExplicitPctEntry(
                    geo_code=str(code),
                    percentage=float(pct),
                    sent_idx=int(sent_idx),
                    derived_total=e.get("derived_total"),
                    derived_covered=e.get("derived_covered"),
                    derived_not_covered=e.get("derived_not_covered"),
                    derived_source=e.get("derived_source"),
                    note=e.get("note"),
                )
            )

    def _get_tolerance(
        self, entries: List[Entry], base_threshold: float = 0.05
    ) -> float:
        """
        Returns a looser tolerance if any entry is qualitative.
        """
        if any(e.is_qualitative for e in entries):
            return max(base_threshold, 0.20)
        return base_threshold

    def _matches_census(
        self,
        val: Optional[float] = None,
        census: Optional[float] = None,
        threshold: float = 0.05,
    ) -> bool:
        """
        Checks if value matches census within threshold or rounding error.
        """
        if val is None or census is None:
            return False
        if census == 0:
            return val == 0

        diff = abs(val - census)
        # Relative error check
        if diff / census < threshold:
            return True

        # Absolute error check (for rounding issues, e.g. 100 vs 101)
        if diff <= 5:
            return True

        return False

    def _resolve_overlaps_list(self, name: str, entries: List[Entry]):
        """
        Generic overlap resolution for a list of entries.
        """

        def detect_breakdown(attr: str, flag_attr: str):
            # Only consider entries with a known value for the attribute
            candidates = [e for e in entries if getattr(e, attr) is not None]
            if len(candidates) < 2:
                return

            # 1. Sliding Window (Breakdowns within breakdowns)
            # Sort by sentence index to respect narrative flow
            by_sent = sorted(candidates, key=lambda x: x.sent_idx)

            for i in range(len(by_sent)):
                parent = by_sent[i]
                parent_val = getattr(parent, attr)
                if parent_val == 0:
                    continue

                current_sum = 0.0
                group: List[Entry] = []

                # Look ahead for children
                for j in range(i + 1, len(by_sent)):
                    child = by_sent[j]
                    child_val = getattr(child, attr)

                    # Skip if child is larger than parent (likely not a part)
                    if child_val >= parent_val:
                        continue

                    current_sum += child_val
                    group.append(child)

                    # Check match
                    # Dynamic tolerance for qualitative entries
                    tolerance = self._get_tolerance(
                        [parent] + group, base_threshold=0.05
                    )

                    if self._matches_census(
                        parent_val, current_sum, threshold=tolerance
                    ):
                        setattr(parent, flag_attr, True)
                        self.resolution_log.append(
                            f"Breakdown Detected {name} ({attr}): {parent_val} (sent {parent.sent_idx}) matches sum of {len(group)} items."
                        )
                        break

                    if current_sum > parent_val * 1.1:
                        break

            # 2. Global Parent vs All Children (Fallback)
            by_size = sorted(candidates, key=lambda x: getattr(x, attr), reverse=True)
            largest = by_size[0]
            largest_val = getattr(largest, attr)
            rest_total = sum(getattr(c, attr) for c in by_size[1:])

            tolerance = self._get_tolerance(by_size, base_threshold=0.10)
            if self._matches_census(largest_val, rest_total, threshold=tolerance):
                setattr(largest, flag_attr, True)
                self.resolution_log.append(
                    f"Global Hierarchy {name} ({attr}): {largest_val} matches sum of all other {len(by_size)-1} entries."
                )

        detect_breakdown("total_count", "is_parent_breakdown")
        detect_breakdown("covered_count", "is_covered_breakdown")
        detect_breakdown("not_covered_count", "is_not_covered_breakdown")

    def _resolve_single_entry_gap(self, name: str, census_total: float, e: Entry):
        """
        Helper to resolve gaps when there is only a single entry for a scope.
        Handles zero-total fixes and implicit total upgrades.
        """
        # 1. Fix zero-total entries for the main scope if census is known
        if e.key == name and e.total_count == 0 and census_total > 0:
            if e.not_covered_count == 0:
                e.total_count = census_total
                e.not_covered_count = census_total
                e.percentage = 0.0
                self._mark_source(
                    e, "total_count_source", TotalSourceDetail.CENSUS_GAP_FIX.value
                )
                self._mark_source(
                    e,
                    "not_covered_count_source",
                    CountSourceDetail.CALCULATED_FROM_TOTAL_MINUS_COVERED.value,
                )
                self._mark_source(
                    e,
                    "percentage_source",
                    PercentageSourceDetail.CALCULATED_ZERO_FROM_GAP_FIX.value,
                )
                self.resolution_log.append(
                    f"Fixed Zero-Total for {name}: 0 not covered implies 0% coverage."
                )

        # 2. Fix implicit total mismatch for single entry (e.g. "10 are union" vs Census 200)
        if census_total > 0 and e.total_count is not None and e.total_count > 0:
            # Check if entry is implicit and significantly smaller than census
            if (
                not e.is_explicit
                and not self._matches_census(e.total_count, census_total)
                and census_total > e.total_count
            ):
                # Check if it looks like a subset inference (covered ~= total OR not_covered ~= total)
                is_subset_inference = False
                if e.covered_count is not None and self._matches_census(
                    e.covered_count, e.total_count
                ):
                    is_subset_inference = True
                elif e.not_covered_count is not None and self._matches_census(
                    e.not_covered_count, e.total_count
                ):
                    is_subset_inference = True

                if is_subset_inference:
                    old_total = e.total_count
                    e.total_count = census_total

                    # Recalculate the other side
                    if e.covered_count is not None:
                        e.not_covered_count = census_total - e.covered_count
                        e.percentage = round(
                            (e.covered_count / census_total) * 100.0, 2
                        )
                        self._mark_source(
                            e,
                            "not_covered_count_source",
                            CountSourceDetail.CALCULATED_FROM_TOTAL_MINUS_COVERED.value,
                        )
                    elif e.not_covered_count is not None:
                        e.covered_count = census_total - e.not_covered_count
                        e.percentage = round(
                            (e.covered_count / census_total) * 100.0, 2
                        )
                        self._mark_source(
                            e,
                            "covered_count_source",
                            CountSourceDetail.CALCULATED_FROM_TOTAL_MINUS_NOT_COVERED.value,
                        )
                    self._mark_source(
                        e,
                        "total_count_source",
                        TotalSourceDetail.CENSUS_UPGRADE.value,
                    )
                    self._mark_source(
                        e,
                        "denominator_source",
                        DenominatorSourceDetail.CENSUS_UPGRADE.value,
                    )
                    self._mark_source(
                        e,
                        "percentage_source",
                        PercentageSourceDetail.CALCULATED_FROM_COUNTS.value,
                    )

                    self.resolution_log.append(
                        f"Upgraded implicit total for {name} ({e.key}) from {old_total} to {census_total} (Census Match)"
                    )

    def _resolve_gap_list(self, name: str, census_total: float, entries: List[Entry]):
        """
        Generic gap filling for a list of entries against a census total.
        """
        if len(entries) == 1:
            self._resolve_single_entry_gap(name, census_total, entries[0])

        # 1. Resolve entries with known percentages first (Independent resolution)
        # This handles qualitative percentages ("majority") or explicit percentages where total was unknown
        for e in entries:
            if e.covered_count is None and e.percentage is not None:
                # Apply if total is unknown OR matches the census (i.e. it's a country-wide rate)
                if e.total_count is None or self._matches_census(
                    e.total_count, census_total
                ):

                    # Safety: Don't assume a segment covers the entire census, unless we only have a single segment
                    if e.scope == Scope.SEGMENT and e.total_count is None:
                        segment_count = sum(
                            1 for entry in entries if entry.scope == Scope.SEGMENT
                        )
                        if segment_count > 1:
                            continue

                    # Also skip if census is missing (fallback handler will try broader scopes)
                    if census_total <= 0:
                        continue

                    # Respect negation: if negated, calculate not_covered, then derive covered
                    calculated_count = round((e.percentage / 100.0) * census_total)
                    if e.is_negated:
                        e.not_covered_count = calculated_count
                        e.covered_count = max(0, census_total - calculated_count)
                        derived_src = self._derive_count_source_from_percentage(
                            e, census=True
                        )
                        self._mark_source(
                            e,
                            "not_covered_count_source",
                            derived_src,
                        )
                        self._mark_source(
                            e,
                            "covered_count_source",
                            derived_src,
                        )
                    else:
                        e.covered_count = calculated_count
                        derived_src = self._derive_count_source_from_percentage(
                            e, census=True
                        )
                        self._mark_source(
                            e,
                            "covered_count_source",
                            derived_src,
                        )

                    e.total_count = census_total
                    self._mark_source(
                        e,
                        "total_count_source",
                        TotalSourceDetail.INHERITED_FROM_CENSUS_TOTAL.value,
                    )
                    self._mark_source(
                        e,
                        "denominator_source",
                        DenominatorSourceDetail.INHERITED_FROM_CENSUS_TOTAL.value,
                    )
                    self._add_source_note(
                        e,
                        "Denominator inherited from census context and used in calculation.",
                    )
                    self.resolution_log.append(
                        f"Resolved COUNT for {name} ({e.key}): {e.percentage}% of {census_total}"
                    )

        # 2. Backfill percentages for entries with counts but no percentage
        for e in entries:
            if e.covered_count is not None and e.percentage is None:
                if e.total_count is None or self._matches_census(
                    e.total_count, census_total
                ):
                    e.total_count = census_total
                    if census_total > 0:
                        raw_pct = (e.covered_count / census_total) * 100.0

                        # Validate/Adjust with bounds
                        if e.qualitative_bounds:
                            lower, upper = e.qualitative_bounds
                            if raw_pct < lower and (lower - raw_pct) < 2.0:
                                raw_pct = lower
                                self.resolution_log.append(
                                    f"Adjusted PCT for {name} ({e.key}) to lower bound {lower}% (was {raw_pct:.2f}%)"
                                )
                            elif raw_pct > upper and (raw_pct - upper) < 2.0:
                                raw_pct = upper
                                self.resolution_log.append(
                                    f"Adjusted PCT for {name} ({e.key}) to upper bound {upper}% (was {raw_pct:.2f}%)"
                                )
                            elif raw_pct < lower or raw_pct > upper:
                                self.resolution_log.append(
                                    f"Warning: Calculated PCT {raw_pct:.2f}% for {name} ({e.key}) is outside bounds [{lower}, {upper}]"
                                )

                        e.percentage = round(raw_pct, 2)
                        self._mark_source(
                            e,
                            "percentage_source",
                            PercentageSourceDetail.CALCULATED_FROM_COUNTS.value,
                        )
                        self.resolution_log.append(
                            f"Resolved PCT for {name} ({e.key}): {e.covered_count}/{census_total}"
                        )

        # 3. Identify remaining gaps (Dependent resolution)
        partials: List[Entry] = []
        others_sum = 0.0

        for e in entries:
            # CRITICAL: Only mark as partial if EXPLICITLY marked as remaining or negated
            # Don't assume unknown = "rest of population"
            is_partial = e.is_remaining or (e.is_negated and e.covered_count is None)

            if is_partial:
                partials.append(e)
            else:
                # Only sum entries that have explicit coverage data
                if e.covered_count is not None or e.not_covered_count is not None:
                    others_sum += (e.covered_count or 0.0) + (
                        e.not_covered_count or 0.0
                    )

        # Constraint: Only one partial entry and room to fill
        if len(partials) == 1 and others_sum < census_total:
            target = partials[0]
            # ONLY fill if explicitly marked as remainder
            if not (target.is_remaining or target.is_negated):
                self.resolution_log.append(
                    f"Skipped gap fill for {name} ({target.key}): "
                    f"Unknown coverage data (not marked as remainder)"
                )
                return
            gap = census_total - others_sum

            if target.is_remaining:
                target.total_count = census_total
                if target.is_negated:
                    target.not_covered_count = gap
                    target.covered_count = 0.0
                    self._mark_source(
                        target,
                        "not_covered_count_source",
                        CountSourceDetail.REMAINING_GAP_FILL.value,
                    )
                    self._mark_source(
                        target,
                        "covered_count_source",
                        CountSourceDetail.REMAINING_GAP_FILL_ZERO.value,
                    )
                else:
                    target.covered_count = gap
                    target.not_covered_count = 0.0
                    self._mark_source(
                        target,
                        "covered_count_source",
                        CountSourceDetail.REMAINING_GAP_FILL.value,
                    )
                    self._mark_source(
                        target,
                        "not_covered_count_source",
                        CountSourceDetail.REMAINING_GAP_FILL_ZERO.value,
                    )
                self._mark_source(
                    target,
                    "total_count_source",
                    TotalSourceDetail.REMAINING_GAP_FILL.value,
                )
                self._mark_source(
                    target,
                    "denominator_source",
                    DenominatorSourceDetail.REMAINING_GAP_FILL.value,
                )
                self.resolution_log.append(f"Resolved REMAINING for {name}: {gap}")

            elif target.covered_count is None and target.percentage is None:
                target.covered_count = gap
                target.total_count = census_total
                self._mark_source(
                    target,
                    "covered_count_source",
                    CountSourceDetail.REMAINING_GAP_FILL.value,
                )
                self._mark_source(
                    target,
                    "total_count_source",
                    TotalSourceDetail.REMAINING_GAP_FILL.value,
                )
                self._mark_source(
                    target,
                    "denominator_source",
                    DenominatorSourceDetail.REMAINING_GAP_FILL.value,
                )
                if census_total > 0:
                    raw_pct = (gap / census_total) * 100.0

                    # Validate/Adjust with bounds
                    if target.qualitative_bounds:
                        lower, upper = target.qualitative_bounds
                        if raw_pct < lower and (lower - raw_pct) < 5.0:
                            raw_pct = lower
                            self.resolution_log.append(
                                f"Adjusted Gap PCT for {name} ({target.key}) to lower bound {lower}% (was {raw_pct:.2f}%)"
                            )
                        elif raw_pct > upper and (raw_pct - upper) < 5.0:
                            raw_pct = upper
                            self.resolution_log.append(
                                f"Adjusted Gap PCT for {name} ({target.key}) to upper bound {upper}% (was {raw_pct:.2f}%)"
                            )
                        elif raw_pct < lower or raw_pct > upper:
                            self.resolution_log.append(
                                f"Warning: Inferred Gap PCT {raw_pct:.2f}% for {name} ({target.key}) is outside bounds [{lower}, {upper}]"
                            )

                    target.percentage = round(raw_pct, 2)
                    self._mark_source(
                        target,
                        "percentage_source",
                        PercentageSourceDetail.CALCULATED_FROM_REMAINING_GAP.value,
                    )
                self.resolution_log.append(
                    f"Resolved PCT for {name} ({target.key}): {gap}/{census_total}"
                )

    def _resolve_aggregates(self):
        """
        Propagates coverage from AGGREGATE entries to their constituent countries
        if those countries lack specific data.
        """
        for e in list(self.entries):
            if e.scope == Scope.AGGREGATE and e.related_geo_codes:
                pct = e.percentage
                related_codes = [
                    c for c in e.related_geo_codes if isinstance(c, str) and c
                ]
                effective_children: List[str] = []
                for c in related_codes:
                    if (
                        c in IGNORED_REGIONS
                        or c in AGG_SET
                        or c in DOMESTIC_SET
                    ):
                        continue
                    if is_region(c):
                        has_concrete_child = any(
                            other != c
                            and isinstance(other, str)
                            and is_contained(
                                c, other, self.domestic_country_code, excluded_keys=None
                            )
                            for other in related_codes
                        )
                        if has_concrete_child:
                            continue
                    if c not in effective_children:
                        effective_children.append(c)

                # Try to derive percentage from counts if missing
                if pct is None and e.covered_count is not None:
                    if e.covered_count == 0:
                        pct = 0.0
                    else:
                        denom = e.total_count
                        if not denom:
                            # Try summing known totals of constituents
                            denom = sum(
                                self.country_totals.get(c, 0)
                                for c in e.related_geo_codes
                            )

                        if denom and denom > 0:
                            pct = (e.covered_count / denom) * 100.0

                if pct is not None or e.is_union_record:

                    for code in e.related_geo_codes:
                        targets = [t for t in self.entries if t.key == code]

                        if not targets:
                            # Determine if key is a Region Name
                            _region = is_region(code)
                            scope = Scope.REGION if _region else Scope.COUNTRY

                            if scope == Scope.REGION:
                                known_total = self.region_totals.get(code)
                            else:
                                known_total = self.country_totals.get(code)

                            new_entry = Entry(
                                scope=scope,
                                key=code,
                                total_count=known_total,
                                is_explicit=False,
                                is_union_record=e.is_union_record,
                                is_qualitative=e.is_qualitative,
                                qualitative_bounds=e.qualitative_bounds,
                                is_remaining=e.is_remaining,
                                is_negated=e.is_negated,
                                is_dummy_percent=e.is_dummy_percent,
                            )
                            self.entries.append(new_entry)
                            targets = [new_entry]
                            self.resolution_log.append(
                                f"Injected placeholder for {code} ({scope.value}) during aggregate resolution"
                            )

                        for t in targets:
                            # If the country already has an explicit zero/negated segment,
                            # do not propagate aggregate percentages into the country entry.
                            has_zero_segment = False
                            if t.scope == Scope.COUNTRY and isinstance(t.key, str):
                                country_prefix = f"{t.key}::"
                                for s in self.entries:
                                    if (
                                        s.scope == Scope.SEGMENT
                                        and isinstance(s.key, str)
                                        and s.key.startswith(country_prefix)
                                        and s.sent_idx != -1
                                    ):
                                        has_zero = (
                                            s.is_negated
                                            or s.percentage == 0
                                            or s.covered_count == 0
                                        )
                                        if has_zero:
                                            has_zero_segment = True
                                            break

                            if has_zero_segment:
                                self.resolution_log.append(
                                    f"Skipped aggregate propagation to {t.key}: explicit zero/negated segment exists."
                                )
                                continue

                            # Special case: aggregate has a single child and explicit data.
                            # Treat it as a direct explicit report for that child (not weighted).
                            if (
                                len(effective_children) == 1
                                and code == effective_children[0]
                                and e.is_explicit
                                and t.covered_count is None
                                and t.percentage is None
                                and t.not_covered_count is None
                            ):
                                if e.covered_count is not None:
                                    t.covered_count = e.covered_count
                                    self._mark_source(
                                        t,
                                        "covered_count_source",
                                        CountSourceDetail.EXPLICIT_COVERED_COUNT.value,
                                    )
                                if e.not_covered_count is not None:
                                    t.not_covered_count = e.not_covered_count
                                    self._mark_source(
                                        t,
                                        "not_covered_count_source",
                                        CountSourceDetail.EXPLICIT_NOT_COVERED_COUNT.value,
                                    )
                                if e.percentage is not None:
                                    t.percentage = e.percentage
                                    self._mark_source(
                                        t,
                                        "percentage_source",
                                        PercentageSourceDetail.EXPLICIT_PERCENTAGE.value,
                                    )
                                t.is_explicit = True
                                # Flag aggregate for downstream reporting suppression.
                                e._single_child_explicit_applied = True  # type: ignore[attr-defined]
                                self.resolution_log.append(
                                    f"Applied explicit aggregate values to single child {t.key} from {e.key}."
                                )
                                continue

                            # Only overwrite if no specific data
                            if (
                                t.percentage is None
                                and t.covered_count is None
                                and (
                                    not t.is_negated or (pct is not None and pct == 0.0)
                                )
                            ):
                                if pct is not None and not e.is_dummy_percent:
                                    t.percentage = pct
                                    t.is_qualitative = e.is_qualitative
                                    self._mark_source(
                                        t,
                                        "percentage_source",
                                        PercentageSourceDetail.AGGREGATE_PROPAGATION.value,
                                    )
                                    self.resolution_log.append(
                                        f"Propagated {pct:.1f}% from Aggregate ({e.key}) to {t.key}"
                                    )

                                    # Calculate count if total is known
                                    if t.total_count:
                                        t.covered_count = round(
                                            (pct / 100.0) * t.total_count
                                        )
                                        denom_is_fallback = (
                                            t.total_count_source_type
                                            == SourceType.FALLBACK.value
                                            or t.denominator_source_type
                                            == SourceType.FALLBACK.value
                                        )
                                        self._mark_source(
                                            t,
                                            "covered_count_source",
                                            self._derive_count_source_from_percentage(
                                                t,
                                                denominator_is_fallback=denom_is_fallback,
                                            ),
                                        )
                                        if t.denominator_source is None:
                                            self._mark_source(
                                                t,
                                                "denominator_source",
                                                DenominatorSourceDetail.EXISTING_TOTAL_AFTER_AGGREGATE_PROPAGATION.value,
                                            )

                            if e.is_union_record:
                                t.is_union_record = True

    def get_child_stats(self, region_identifier: str) -> Tuple[bool, Dict[str, float]]:
        """
        Calculates aggregated statistics for child countries in a region.
        Returns (has_children, {covered, not_covered, total})
        """
        target_countries = None
        region_name = None

        if region_identifier in COMPOSITE_REGION_MAP:
            target_countries = set(COMPOSITE_REGION_MAP[region_identifier])
        else:
            # Resolve code to region name if possible (e.g. GeoCode.EUROPE.value -> "Europe")
            region_name = _CODE_TO_REGION.get(region_identifier, region_identifier)

        agg_covered = 0.0
        agg_not_covered = 0.0
        agg_total = 0.0

        # 1. Identify relevant country entries (Explicit or Implied by Segments)
        c_entries: List[Entry] = []
        for e in self.entries:
            if e.scope == Scope.COUNTRY:
                if target_countries:
                    if e.key in target_countries:
                        c_entries.append(e)
                elif region_name:
                    if _CODE_TO_REGION.get(e.key) == region_name:
                        c_entries.append(e)

        existing_codes = {e.key for e in c_entries}
        segment_entries = [e for e in self.entries if e.scope == Scope.SEGMENT]

        # Find implied countries from segments
        for s in segment_entries:
            code = self._segment_anchor_code(s.key)
            if code and code not in existing_codes:
                is_match = False
                if target_countries:
                    if code in target_countries:
                        is_match = True
                elif region_name:
                    if _CODE_TO_REGION.get(code) == region_name:
                        is_match = True

                if is_match:
                    dummy = Entry(scope=Scope.COUNTRY, key=code)
                    c_entries.append(dummy)
                    existing_codes.add(code)

        for c in c_entries:
            c_cov = 0.0
            c_not_cov = 0.0
            c_tot = 0.0
            c_has_local_data = False

            # A. Check Country Entry Data
            if c.covered_count is not None:
                c_cov = c.covered_count
                c_tot = c.total_count if c.total_count else 0.0
                c_not_cov = (
                    c.not_covered_count
                    if c.not_covered_count is not None
                    else max(0.0, c_tot - c_cov)
                )
                c_has_local_data = True
            elif c.percentage is not None and c.total_count:
                c_cov = (c.percentage / 100.0) * c.total_count
                c_tot = c.total_count
                c_not_cov = max(0.0, c_tot - c_cov)
                c_has_local_data = True
            elif c.not_covered_count is not None:
                c_not_cov = c.not_covered_count
                c_tot = c.total_count if c.total_count else c_not_cov
                c_cov = (
                    c.covered_count
                    if c.covered_count is not None
                    else max(0.0, c_tot - c_not_cov)
                )
                c_has_local_data = True

            # B. Check Segments (Override/Augment if segments provide better resolution)
            if not c_has_local_data:
                segs = [
                    s
                    for s in self.entries
                    if s.scope == Scope.SEGMENT
                    and self._segment_matches_country(s.key, str(c.key))
                ]
                if segs:
                    seg_cov = sum(s.covered_count for s in segs if s.covered_count)
                    seg_not_cov = sum(
                        s.not_covered_count for s in segs if s.not_covered_count
                    )
                    seg_tot = (
                        c.total_count
                        if c.total_count
                        else sum(s.total_count for s in segs if s.total_count)
                    )

                    if seg_cov > 0 or seg_not_cov > 0 or seg_tot > 0:
                        c_cov = seg_cov
                        c_not_cov = seg_not_cov
                        c_tot = seg_tot
                        if c_tot > 0:
                            if c_cov > 0 and c_not_cov == 0:
                                c_not_cov = max(0.0, c_tot - c_cov)
                            elif c_not_cov > 0 and c_cov == 0:
                                c_cov = max(0.0, c_tot - c_not_cov)
                        c_has_local_data = True

            if c_has_local_data:
                agg_covered += c_cov
                agg_not_covered += c_not_cov
                agg_total += c_tot

        return bool(c_entries), {
            "covered": agg_covered,
            "not_covered": agg_not_covered,
            "total": agg_total,
        }

    def _is_contained(
        self, container_key: Optional[str] = None, item_key: Optional[str] = None
    ):
        return is_contained(container_key, item_key, self.domestic_country_code)

    def _resolve_geographic_gaps(
        self, name: str, region_total: float, entries: List[Entry]
    ):
        """
        Resolves gaps for geographic constituents (e.g. Countries in a Region).
        Logic: Sum of Country Totals should equal Region Total.
        """
        # 1. Sum known totals
        known_sum = 0.0
        unknowns: List[Entry] = []

        # Filter out children if parent is present with total to avoid double counting
        entries_with_total = [e for e in entries if e.total_count is not None]
        ignored_entries = set()
        for e in entries_with_total:
            for potential_parent in entries_with_total:
                if e is potential_parent:
                    continue
                if self._is_contained(potential_parent.key, e.key):
                    ignored_entries.add(e)
                    break

        for e in entries:
            # Skip if ignored (contained in another present entry)
            if e in ignored_entries:
                continue

            # Use total_count if available
            if e.total_count is not None:
                known_sum += e.total_count
            # If not, maybe we can derive it from covered/pct?
            elif (
                e.covered_count is not None
                and e.percentage is not None
                and e.percentage > 0
            ):
                derived_total = round(e.covered_count / (e.percentage / 100.0))
                e.total_count = derived_total
                known_sum += derived_total
                self.resolution_log.append(
                    f"Derived TOTAL for {name} ({e.key}): {derived_total} from count/pct"
                )
            elif (
                e.not_covered_count is not None
                and e.percentage is None
                and e.covered_count is None
            ):
                e.total_count = e.not_covered_count
                known_sum += e.not_covered_count
                self.resolution_log.append(
                    f"Derived TOTAL for {name} ({e.key}): Filled total count from not covered: {e.not_covered_count}"
                )
            else:
                unknowns.append(e)

        # 2. Solve for single unknown
        if len(unknowns) == 1 and known_sum < region_total:
            target = unknowns[0]

            # Validation: Ensure we don't assign a regional gap to a segment
            if target.scope == Scope.SEGMENT:
                # Allow if this is the only explicit segment (excluding system placeholders)
                explicit_entries = [e for e in entries if e.sent_idx != -1]
                if len(explicit_entries) > 1:
                    self.resolution_log.append(
                        f"Skipped GEO GAP for {name}: Target {target.key} is a SEGMENT among multiple segments."
                    )
                    return

            gap = region_total - known_sum

            # Sanity check: Gap should be positive and reasonable
            if gap > 0:
                target.total_count = gap
                self.resolution_log.append(
                    f"Resolved GEO GAP for {name} ({target.key}): Total {gap} (derived from {region_total} - {known_sum})"
                )

                # If the target has a percentage, we can now derive covered_count
                if target.percentage is not None:
                    target.covered_count = round((target.percentage / 100.0) * gap)
                    self.resolution_log.append(
                        f"Resolved COUNT for {name} ({target.key}): {target.percentage}% of {gap}"
                    )
                # If target has covered_count, derive percentage
                elif target.covered_count is not None:
                    target.percentage = round((target.covered_count / gap) * 100.0, 2)
                    self.resolution_log.append(
                        f"Resolved PCT for {name} ({target.key}): {target.covered_count}/{gap}"
                    )

    def _get_region_entries(self, region_identifier: str) -> List[Entry]:
        """
        Collects entries contained by a region/container key.
        Supports canonical regions (e.g. Europe), generic aliases, and composites (e.g. EU_UNION, CIS).
        """
        container = _CODE_TO_REGION.get(region_identifier, region_identifier)
        relevant: List[Entry] = []
        seen_ids: Set[int] = set()
        is_international_agg = container == Region.INTERNATIONAL.value

        def add_entry(entry: Entry):
            marker = id(entry)
            if marker in seen_ids:
                return
            seen_ids.add(marker)
            relevant.append(entry)

        for e in self.entries:
            key = str(e.key) if e.key is not None else ""
            base = (
                self._segment_anchor_code(key)
                if e.scope == Scope.SEGMENT
                else (key.split("::")[0] if key else "")
            )

            if not base:
                continue

            # Direct region/container match
            if e.scope == Scope.REGION:
                e_region = _CODE_TO_REGION.get(base, base)
                if (
                    base == region_identifier
                    or base == container
                    or e_region == container
                ):
                    add_entry(e)
                    continue

            # Containment-based matching for countries/segments and composites.
            if e.scope in (Scope.COUNTRY, Scope.SEGMENT):
                if is_contained(
                    container_key=region_identifier,
                    item_key=base,
                    domestic_country_code=self.domestic_country_code,
                ) or is_contained(
                    container_key=container,
                    item_key=base,
                    domestic_country_code=self.domestic_country_code,
                ):
                    add_entry(e)
                    continue

                # Canonical region fallback (for plain region names like Europe).
                if _CODE_TO_REGION.get(
                    base
                ) == container and not self._is_container_geo_key(base):
                    add_entry(e)

        if is_international_agg:
            # International aggregates non-domestic geographies.
            for e in self.entries:
                if e.scope == Scope.SEGMENT:
                    base = self._segment_anchor_code(e.key) or ""
                else:
                    base = str(e.key).split("::")[0] if e.key is not None else ""
                if not base or base in IGNORED_REGIONS:
                    continue
                if is_contained(
                    container_key=Region.INTERNATIONAL.value,
                    item_key=base,
                    domestic_country_code=self.domestic_country_code,
                ):
                    add_entry(e)

        return relevant

    def _inject_placeholders(self, region_identifier: str):
        """
        Injects placeholder entries for countries mentioned in text but missing from entries.
        This allows gap filling to attribute remaining counts to these countries.
        Also backfills total_count from country_totals for all country entries in the region.
        """
        region_name = _CODE_TO_REGION.get(region_identifier, region_identifier)
        # 1. Inject missing mentioned countries
        existing_keys = {e.key for e in self.entries if e.scope == Scope.COUNTRY}

        for code in self.mentioned_countries:
            if code in existing_keys:
                continue

            if _CODE_TO_REGION.get(code) == region_name:
                self.entries.append(
                    Entry(
                        scope=Scope.COUNTRY,
                        key=code,
                        is_explicit=False,  # It's an inferred placeholder
                    )
                )
                self.resolution_log.append(
                    f"Injected placeholder for mentioned country: {code} in {region_name}"
                )
                existing_keys.add(code)

        # 1b. Mandatory Injections based on Region Logic

        # If resolving North America, always inject US (SEC filing context)
        if region_name == Region.NORTH_AMERICA.value:
            # Only add US if Canada is not present
            if "US" not in existing_keys and "CA" not in existing_keys:
                self.entries.append(
                    Entry(scope=Scope.COUNTRY, key="US", is_explicit=False)
                )
                self.resolution_log.append(
                    f"Injected placeholder for US in {region_name} (SEC Context)"
                )
                existing_keys.add("US")

        # If Domestic Country belongs to this region, inject it
        if self.domestic_country_code:
            dom_region = _CODE_TO_REGION.get(self.domestic_country_code)
            if (
                dom_region
                and dom_region == region_name
                and self.domestic_country_code not in existing_keys
            ):
                self.entries.append(
                    Entry(
                        scope=Scope.COUNTRY,
                        key=self.domestic_country_code,
                        is_explicit=False,
                    )
                )
                self.resolution_log.append(
                    f"Injected placeholder for domestic {self.domestic_country_code} in {region_name}"
                )
                existing_keys.add(self.domestic_country_code)

        # 2. Backfill totals from country_totals for ALL entries in this region
        region_entries = self._get_region_entries(region_name)

        for e in region_entries:
            if e.scope == Scope.COUNTRY and e.key in self.country_totals:
                known_total = self.country_totals[e.key]

                if e.total_count is None:
                    e.total_count = known_total
                    self.resolution_log.append(
                        f"Backfilled total for {e.key}: {known_total}"
                    )
                elif e.total_count < known_total:
                    old = e.total_count
                    e.total_count = known_total
                    self.resolution_log.append(
                        f"Updated total for {e.key} from {old} to {known_total} (census match)"
                    )

    def _drop_redundant_entries(self, entries: List[Entry]):
        """
        Drops entries that are restatements of other entries to avoid double counting.
        e.g. "80 not covered" when we already have "20 covered" out of 100.
        """
        to_remove = []

        # Group by normalized key (parent entity) to compare entries for the same entity or its segments
        by_parent: Dict[str, List[Entry]] = {}
        for e in entries:
            assert e.key is not None
            # Normalize key: US::Segment_0 -> US
            parent_key = e.key.split("::")[0]
            if parent_key not in by_parent:
                by_parent[parent_key] = []
            by_parent[parent_key].append(e)

        for parent, group in by_parent.items():
            if len(group) < 2:
                continue

            # 1. Check Not Covered vs (Total - Covered)
            # Find entries with Total and Covered (Source of Truth)
            sources: List[Entry] = [
                e
                for e in group
                if e.total_count is not None and e.covered_count is not None
            ]

            # Find entries with Not Covered (Candidates for removal)
            targets: List[Entry] = [e for e in group if e.not_covered_count is not None]

            for t in targets:
                if t in sources:  # Don't remove self if it has both
                    continue

                val = t.not_covered_count
                t_total = t.total_count

                for s in sources:
                    if s is t:
                        continue
                    implied_not_covered = (s.total_count or 0) - (s.covered_count or 0)

                    if self._matches_census(val, implied_not_covered):
                        # If keys differ (e.g. Segment_0 vs Segment_1), enforce stricter check:
                        # The target's Total must match the source's Implied Not Covered.
                        if s.key != t.key:
                            if t_total is not None and self._matches_census(
                                t_total, implied_not_covered
                            ):
                                to_remove.append(t)
                                self.resolution_log.append(
                                    f"Dropped redundant entry for {t.key}: {val} not covered (matches {s.total_count} - {s.covered_count} from {s.key})"
                                )
                                break
                        else:
                            # Same key: standard redundancy check
                            to_remove.append(t)
                            self.resolution_log.append(
                                f"Dropped redundant entry for {t.key}: {val} not covered (matches {s.total_count} - {s.covered_count} from another entry)"
                            )
                            break

            # 2. Check Covered vs Covered (with equal or larger Total)
            covered_entries: List[Entry] = [
                e for e in group if e.covered_count is not None
            ]

            for t in covered_entries:
                if t in to_remove:
                    continue

                val = t.covered_count
                t_total = t.total_count or 0

                for s in covered_entries:
                    if s is t:
                        continue
                    if s in to_remove:
                        continue

                    s_val = s.covered_count
                    s_total = s.total_count or 0

                    if self._matches_census(val, s_val):
                        # If keys are different and both are segments.
                        if (
                            s.key != t.key
                            and s.scope == Scope.SEGMENT
                            and t.scope == Scope.SEGMENT
                            # and one of the keys do not start with segment
                            and (
                                s.key and not s.key.startswith("Segment_")
                                or t.key and not t.key.startswith("Segment_")
                            )
                        ):
                           continue

                        should_remove_t = False
                        reason = ""

                        if s_total > t_total:
                            should_remove_t = True
                            reason = f"matches {s.covered_count} from {s.key} with larger total {s.total_count}"
                        elif s_total == t_total:
                            # Tie-breakers
                            if s.is_explicit and not t.is_explicit:
                                should_remove_t = True
                                reason = f"duplicate of {s.key}, preferring explicit"
                            elif not s.is_explicit and t.is_explicit:
                                pass
                            elif s.percentage is not None and t.percentage is None:
                                should_remove_t = True
                                reason = f"duplicate of {s.key}, preferring percentage"
                            elif s.percentage is None and t.percentage is not None:
                                pass
                            # Use index in 'entries' list as final tie-breaker (keep first)
                            elif entries.index(s) < entries.index(t):
                                should_remove_t = True
                                reason = f"duplicate of {s.key}"

                        if should_remove_t:
                            to_remove.append(t)
                            self.resolution_log.append(
                                f"Dropped redundant entry for {t.key}: {val} covered ({reason})"
                            )
                            break

                    # Case B: Covered Count matches Total Count (Misclassification)
                    if s_total > 0 and self._matches_census(val, s_total):
                        if s_val and s_val < s_total:
                            to_remove.append(t)
                            self.resolution_log.append(
                                f"Dropped redundant entry for {t.key}: {val} covered (matches total from {s.key}, likely misclassified total)"
                            )
                            break

        for e in to_remove:
            if e in self.entries:
                self.entries.remove(e)
            if e in entries:
                entries.remove(e)

    def _resolve_single_country(self, country_code: str, census_total: float):
        # Guardrail: container/composite geographies should not be resolved as countries.
        if self._is_container_geo_key(country_code):
            return

        relevant_entries = [
            e
            for e in self.entries
            if (e.scope == Scope.COUNTRY and e.key == country_code)
            or (
                e.scope == Scope.SEGMENT
                and self._segment_matches_country(e.key, country_code)
            )
        ]

        self._drop_redundant_entries(relevant_entries)

        # Backfill total for the country entry itself if it exists
        # This ensures placeholders get the distributed virtual total
        country_entry = next(
            (
                e
                for e in relevant_entries
                if e.scope == Scope.COUNTRY and e.key == country_code
            ),
            None,
        )
        if country_entry:
            if country_entry.total_count is None and census_total > 0:
                country_entry.total_count = census_total
                self._mark_source(
                    country_entry,
                    "total_count_source",
                    TotalSourceDetail.COUNTRY_CENSUS_BACKFILL.value,
                )
                self._mark_source(
                    country_entry,
                    "denominator_source",
                    DenominatorSourceDetail.COUNTRY_CENSUS_BACKFILL.value,
                )
                self.resolution_log.append(
                    f"Backfilled total for {country_code}: {census_total}"
                )
            elif (
                country_entry.total_count is not None
                and census_total > country_entry.total_count
            ):
                # Update if census is larger (e.g. from virtual pool)
                old = country_entry.total_count
                country_entry.total_count = census_total
                self._mark_source(
                    country_entry,
                    "total_count_source",
                    TotalSourceDetail.COUNTRY_CENSUS_UPDATE.value,
                )
                self._mark_source(
                    country_entry,
                    "denominator_source",
                    DenominatorSourceDetail.COUNTRY_CENSUS_UPDATE.value,
                )
                self.resolution_log.append(
                    f"Updated total for {country_code} from {old} to {census_total} (census match)"
                )

            # If we have a total but no coverage data, and it's not a union record (e.g. placeholder), infer 0%
            if (
                country_entry.total_count is not None
                and country_entry.total_count > 0
                and country_entry.covered_count is None
                and country_entry.percentage is None
                and not country_entry.is_union_record
            ):
                # Only infer 0% if no segments have data
                has_segment_data = any(
                    e.scope == Scope.SEGMENT
                    and (
                        e.covered_count is not None
                        or e.percentage is not None
                        or e.is_union_record
                    )
                    for e in relevant_entries
                )

                if not has_segment_data:
                    country_entry.covered_count = 0.0
                    country_entry.not_covered_count = country_entry.total_count
                    country_entry.percentage = 0.0
                    country_entry.is_negated = True
                    self._mark_source(
                        country_entry,
                        "covered_count_source",
                        CountSourceDetail.INFERRED_ZERO_FROM_PLACEHOLDER.value,
                    )
                    self._mark_source(
                        country_entry,
                        "not_covered_count_source",
                        CountSourceDetail.INFERRED_ZERO_FROM_PLACEHOLDER.value,
                    )
                    self._mark_source(
                        country_entry,
                        "percentage_source",
                        PercentageSourceDetail.INFERRED_ZERO_FROM_PLACEHOLDER.value,
                    )
                    self.resolution_log.append(
                        f"Inferred 0% coverage for {country_code} (Placeholder with Total)"
                    )

        if not relevant_entries:
            if census_total > 0:
                self.entries.append(
                    Entry(
                        scope=Scope.COUNTRY,
                        key=country_code,
                        total_count=census_total,
                        covered_count=0.0,
                        not_covered_count=census_total,
                        percentage=0.0,
                        is_explicit=False,
                        is_negated=True,
                        covered_count_source=CountSourceDetail.INFERRED_ZERO_FROM_CENSUS_ONLY.value,
                        not_covered_count_source=CountSourceDetail.INFERRED_ZERO_FROM_CENSUS_ONLY.value,
                        percentage_source=PercentageSourceDetail.INFERRED_ZERO_FROM_CENSUS_ONLY.value,
                        total_count_source=TotalSourceDetail.COUNTRY_CENSUS_ONLY.value,
                        denominator_source=DenominatorSourceDetail.COUNTRY_CENSUS_ONLY.value,
                    )
                )
                self.resolution_log.append(
                    f"Inferred 0% coverage for {country_code}: Census {census_total} exists but no union entries found."
                )
            return
        # Check if sum of segments exceeds census total (indicating census was just a large segment)
        segments = [
            e for e in relevant_entries if e.scope == Scope.SEGMENT and e.total_count
        ]
        if segments:
            sorted_segs: List[Entry] = sorted(segments, key=lambda x: x.total_count, reverse=True)  # type: ignore
            largest = sorted_segs[0].total_count or 0.0
            others_sum = sum(
                s.total_count for s in sorted_segs[1:] if s.total_count is not None
            )
            total_sum = largest + others_sum

            # Heuristic: If largest is roughly equal to sum of others, it's likely a hierarchy (Total vs Parts)
            # If not, and the sum is significantly larger than the census, assume disjoint segments and update total.
            is_hierarchy = False
            if others_sum > 0 and abs(largest - others_sum) / largest < 0.15:
                is_hierarchy = True
                sorted_segs[0].is_parent_breakdown = True

            if not is_hierarchy and total_sum > census_total * 1.05:
                self.country_totals[country_code] = total_sum
                self.resolution_log.append(
                    f"Updated Country Total for {country_code} from {census_total} to {total_sum} based on sum of disjoint segments."
                )
                census_total = total_sum
        self._resolve_overlaps_list(country_code, relevant_entries)

        # Filter for constituents (Segments) to avoid double counting the Country entry itself
        constituents = [e for e in relevant_entries if e.scope == Scope.SEGMENT]
        self._resolve_geographic_gaps(country_code, census_total, constituents)

    def _resolve_single_region(self, region_identifier: str, region_total: float):
        region_name = _CODE_TO_REGION.get(region_identifier, region_identifier)

        self._inject_placeholders(region_name)
        entries = self._get_region_entries(region_name)
        self._drop_redundant_entries(entries)
        if not entries:
            # Do not infer synthetic 0%-coverage region placeholders from census totals.
            # Region containers are often employment placeholders.
            return
        self._resolve_overlaps_list(region_name, entries)

        # Filter for constituents (Countries) to avoid double counting the Region entry itself
        constituents = [e for e in entries if e.scope == Scope.COUNTRY]
        self._resolve_geographic_gaps(region_name, region_total, constituents)

    def _region_to_pseudo_country_code(self, region_key: str) -> Optional[str]:
        canonical = _CODE_TO_REGION.get(region_key, region_key)

        if canonical in REGION_NAME_MAP:
            return REGION_NAME_MAP[canonical]
        # Composite categorizations are already code-like keys.
        if region_key in COMPOSITE_REGION_MAP:
            return region_key
        return None

    def _region_has_constituent_children(self, region_key: str) -> bool:
        canonical = _CODE_TO_REGION.get(region_key, region_key)

        if canonical in INT_SET:
            # International has children only when specific non-domestic entities
            # are present (countries/segments/regions/composites).
            for e in self.entries:
                if e.scope == Scope.SEGMENT:
                    base = self._segment_anchor_code(e.key) or ""
                else:
                    base = str(e.key).split("::")[0] if e.key is not None else ""
                if not base or base in IGNORED_REGIONS:
                    continue
                if base in INT_SET:
                    continue
                if e.scope in (Scope.COUNTRY, Scope.SEGMENT):
                    # Any explicit non-domestic country/composite indicates children.
                    if base not in DOMESTIC_SET and base != self.domestic_country_code:
                        return True
                elif e.scope == Scope.REGION and base not in INT_SET:
                    return True
            for c_code in self.country_totals:
                if c_code in IGNORED_REGIONS or c_code in INT_SET:
                    continue
                if c_code not in DOMESTIC_SET and c_code != self.domestic_country_code:
                    return True
            return False

        # Composite container: use its explicit constituents.
        if region_key in COMPOSITE_REGION_MAP:
            constituents = set(get_composite_constituents(region_key))
            if any(
                c in self.country_totals and self.country_totals[c] > 0
                for c in constituents
            ):
                return True
            for e in self.entries:
                if e.scope == Scope.SEGMENT:
                    base = self._segment_anchor_code(e.key) or ""
                else:
                    base = str(e.key).split("::")[0] if e.key is not None else ""
                if base in constituents and e.scope in (Scope.COUNTRY, Scope.SEGMENT):
                    return True
            return False

        # Canonical major-region children.
        for c_code, c_total in self.country_totals.items():
            if c_code in REGION_CODES or c_code in IGNORED_REGIONS:
                continue
            if c_total > 0 and _CODE_TO_REGION.get(c_code) == canonical:
                return True

        for e in self.entries:
            if e.scope not in (Scope.COUNTRY, Scope.SEGMENT):
                continue
            if e.scope == Scope.SEGMENT:
                base = self._segment_anchor_code(e.key) or ""
            else:
                base = str(e.key).split("::")[0] if e.key is not None else ""
            if (
                base
                and base not in REGION_CODES
                and base not in IGNORED_REGIONS
                and _CODE_TO_REGION.get(base) == canonical
            ):
                return True
        return False

    def _promote_region_entries_to_pseudo_countries(self) -> None:
        """
        Promote region-only entries into pseudo-country entities when no child
        constituents are present (e.g. Europe -> EU, CIS -> CIS).
        """
        promoted_region_keys: Set[str] = set()

        for e in self.entries:
            if e.scope != Scope.REGION or not isinstance(e.key, str):
                continue
            if e.key in IGNORED_REGIONS:
                continue

            pseudo_code = self._region_to_pseudo_country_code(e.key)
            if not pseudo_code:
                continue
            if self._region_has_constituent_children(e.key):
                continue

            original_key = e.key
            e.key = pseudo_code
            e.scope = Scope.COUNTRY
            promoted_region_keys.add(original_key)
            self.resolution_log.append(
                f"Promoted region '{original_key}' to pseudo-country '{pseudo_code}' (no child constituents)."
            )

        # Move region totals to country totals for promoted regions.
        for region_key in promoted_region_keys:
            pseudo_code = self._region_to_pseudo_country_code(region_key)
            if not pseudo_code:
                continue
            canonical = _CODE_TO_REGION.get(region_key, region_key)
            moved_total = 0.0
            if region_key in self.region_totals:
                moved_total = max(moved_total, self.region_totals.get(region_key, 0.0))
            if canonical in self.region_totals:
                moved_total = max(moved_total, self.region_totals.get(canonical, 0.0))
            if moved_total > 0:
                self.country_totals[pseudo_code] = max(
                    self.country_totals.get(pseudo_code, 0.0), moved_total
                )
                self.resolution_log.append(
                    f"Promoted region total '{region_key}' ({moved_total}) to pseudo-country '{pseudo_code}'."
                )

    def _synthesize_subtraction_segments(self) -> None:
        """
        Builds synthetic residual segments for region-minus-country structures.
        Example: Europe=1000 and Germany=200 -> SUB::Europe total=800.
        """
        region_entries = [
            e
            for e in self.entries
            if e.scope == Scope.REGION
            and isinstance(e.key, str)
            and e.key not in IGNORED_REGIONS
            and e.total_count is not None
            and e.total_count > 0
        ]
        if not region_entries:
            return

        for parent in region_entries:
            assert isinstance(parent.key, str)
            region_name = _CODE_TO_REGION.get(parent.key, parent.key)
            pseudo_code = self._region_to_pseudo_country_code(region_name)
            if not pseudo_code:
                continue

            # Avoid duplicate residual generation for the same region.
            if any(
                e.scope == Scope.SEGMENT
                and self._is_subtraction_segment_key(e.key)
                and self._subtraction_region_name(e.key) == region_name
                for e in self.entries
            ):
                continue

            has_children, stats = self.get_child_stats(region_name)
            if not has_children:
                continue

            parent_total = float(parent.total_count or 0.0)
            child_total = float(stats.get("total", 0.0) or 0.0)
            if child_total <= 0:
                continue

            residual_total = parent_total - child_total
            if residual_total <= 0:
                continue

            parent_cov = (
                float(parent.covered_count)
                if parent.covered_count is not None
                else (
                    (float(parent.percentage) / 100.0) * parent_total
                    if parent.percentage is not None and parent_total > 0
                    else None
                )
            )
            child_cov = float(stats.get("covered", 0.0) or 0.0)
            residual_cov = None
            if parent_cov is not None:
                residual_cov = max(0.0, parent_cov - child_cov)

            residual_not_cov = None
            residual_pct = None
            if residual_cov is not None:
                residual_not_cov = max(0.0, residual_total - residual_cov)
                if residual_total > 0:
                    residual_pct = round((residual_cov / residual_total) * 100.0, 2)
            elif parent.percentage is not None and residual_total > 0:
                residual_pct = float(parent.percentage)
                residual_cov = round((residual_pct / 100.0) * residual_total)
                residual_not_cov = max(0.0, residual_total - residual_cov)

            self.entries.append(
                Entry(
                    scope=Scope.SEGMENT,
                    key=f"SUB::{region_name}",
                    total_count=residual_total,
                    covered_count=residual_cov,
                    not_covered_count=residual_not_cov,
                    percentage=residual_pct,
                    is_explicit=False,
                    is_union_record=parent.is_union_record,
                    is_qualitative=parent.is_qualitative,
                    qualitative_bounds=parent.qualitative_bounds,
                    is_negated=parent.is_negated,
                    sent_idx=parent.sent_idx,
                    related_geo_codes=[pseudo_code],
                    total_count_source=TotalSourceDetail.REMAINING_GAP_FILL.value,
                    denominator_source=DenominatorSourceDetail.REMAINING_GAP_FILL.value,
                    covered_count_source=(
                        CountSourceDetail.REMAINING_GAP_FILL.value
                        if residual_cov is not None
                        else None
                    ),
                    not_covered_count_source=(
                        CountSourceDetail.REMAINING_GAP_FILL.value
                        if residual_not_cov is not None
                        else None
                    ),
                    percentage_source=(
                        PercentageSourceDetail.CALCULATED_FROM_COUNTS.value
                        if residual_pct is not None and parent_cov is not None
                        else (
                            PercentageSourceDetail.CALCULATED_PERCENTAGE.value
                            if residual_pct is not None
                            else None
                        )
                    ),
                )
            )
            self.resolution_log.append(
                f"Created subtraction segment SUB::{region_name}: {residual_total} (parent {parent_total} - child {child_total})."
            )

    def _route_domestic(self, target_country: Optional[str] = None):
        if target_country is None:
            target_country = self.domestic_country_code

        # Fallback for truly unknown domestic code
        if target_country in DOMESTIC_SET | {None}:
            target_country = "US"
            self.resolution_log.append(
                "Target country was DOM/Unknown, defaulted to US"
            )

        # Filter for valid country codes (2 letters usually)
        # Treat GeoCode.INTERNATIONAL.value as a valid country code for this logic if it is the target
        valid_countries = {
            c
            for c in self.mentioned_countries
            if c and (len(c) == 2 or c == target_country)
        }
        other_countries = valid_countries - {target_country}

        has_union_records = any(e.is_union_record for e in self.entries)
        has_non_domestic_mentions = any(
            c and len(c) == 2 and c != target_country for c in self.mentioned_countries
        )
        implicit_domestic_union_context = (
            not valid_countries and has_union_records and not has_non_domestic_mentions
        )
        single_country_context = (
            len(valid_countries) == 1 and target_country in valid_countries
        ) or implicit_domestic_union_context

        # Condition: No other countries mentioned
        if single_country_context:
            # Inherit global total if we are defaulting to target and have no specific data
            if (
                self.global_total > 0
                and self.country_totals.get(target_country, 0) == 0
            ):
                self.country_totals[target_country] = self.global_total
                self.resolution_log.append(
                    f"Inherited Global Total {self.global_total} to '{target_country}' (Default Domestic)"
                )

        for idx, e in enumerate(self.entries):
            if e.key in DOMESTIC_SET:
                e.key = target_country
                e.scope = Scope.COUNTRY
                self.resolution_log.append(f"Resolved 'Domestic' to '{target_country}'")
            elif e.key in UNK_SET:
                # Unknown scope defaults to domestic only in single-country context.
                # Otherwise route it to Global.
                if single_country_context:
                    e.key = target_country
                    e.scope = Scope.COUNTRY
                    self.resolution_log.append(
                        f"Resolved 'Unknown' to domestic country '{target_country}' (single-country context)"
                    )
                else:
                    e.key = Scope.GLOBAL.value
                    e.scope = Scope.GLOBAL
                    self.resolution_log.append(
                        "Resolved 'Unknown' to 'GLOBAL' (multi-country context)"
                    )
            elif (
                e.scope == Scope.SEGMENT
                and e.key
                and e.key.split("::")[0] in DOMESTIC_SET
            ):
                suffix = e.key.split("::", 1)[1]
                e.key = f"{target_country}::{suffix}"
                self.resolution_log.append(
                    f"Resolved Domestic Segment to '{target_country}::...'"
                )

        # Remap Totals
        if GeoCode.DOMESTIC.value in self.country_totals:
            val = self.country_totals.pop(GeoCode.DOMESTIC.value)
            self.country_totals[target_country] = max(
                self.country_totals.get(target_country, 0), val
            )
            self.resolution_log.append(
                f"Remapped country total DOM ({val}) to {target_country}"
            )

        # Remap Unknown Totals
        for unk_key in UNK_SET:
            if unk_key in self.country_totals:
                val = self.country_totals.pop(unk_key)
                if single_country_context:
                    self.country_totals[target_country] = max(
                        self.country_totals.get(target_country, 0), val
                    )
                    self.resolution_log.append(
                        f"Remapped country total '{unk_key}' ({val}) to '{target_country}' (single-country context)"
                    )
                else:
                    self.global_total = max(self.global_total, val)
                    self.resolution_log.append(
                        f"Remapped country total '{unk_key}' ({val}) to GLOBAL (multi-country context)"
                    )

        # Remap Region Totals for Domestic
        for key in DOMESTIC_SET:
            if key in self.region_totals:
                val = self.region_totals.pop(key)
                self.country_totals[target_country] = max(
                    self.country_totals.get(target_country, 0), val
                )
                self.resolution_log.append(
                    f"Remapped region total '{key}' ({val}) to country '{target_country}'"
                )

        # Remap Region Totals for Unknown
        for unk_key in UNK_SET:
            if unk_key in self.region_totals:
                val = self.region_totals.pop(unk_key)
                if single_country_context:
                    self.country_totals[target_country] = max(
                        self.country_totals.get(target_country, 0), val
                    )
                    self.resolution_log.append(
                        f"Remapped region total '{unk_key}' ({val}) to country '{target_country}' (single-country context)"
                    )
                else:
                    self.global_total = max(self.global_total, val)
                    self.resolution_log.append(
                        f"Remapped region total '{unk_key}' ({val}) to GLOBAL (multi-country context)"
                    )

    def _resolve_int_codes(self):
        """
        Resolves INT_* codes using the external resolver function.
        """
        int_codes = set()
        for e in self.entries:
            key = str(e.key)
            prefix = key.split("::")[0]
            if prefix.startswith(GeoCode.INT_LANG.value):
                int_codes.add(prefix)

        if not int_codes:
            return

        mapping = resolve_remaining_int(
            self.mentioned_countries,
            self.domestic_country_code,
            int_codes,
        )

        for e in self.entries:
            key = str(e.key)
            prefix = key
            suffix = ""
            if "::" in key:
                parts = key.split("::", 1)
                prefix = parts[0]
                suffix = "::" + parts[1]

            if prefix in mapping:
                new_code = mapping[prefix]
                if new_code != prefix:
                    if (
                        prefix.startswith(GeoCode.INT_LANG.value)
                        and isinstance(new_code, str)
                        and len(new_code) == 2
                        and new_code not in self.mentioned_countries
                    ):
                        self.language_fallback_countries.add(new_code)
                    new_key = new_code + suffix
                    self.resolution_log.append(f"Resolved {e.key} to {new_key}")
                    e.key = new_key

                    # Migrate sentence keywords from old prefix to new_code
                    if prefix in self.country_sentence_keywords:
                        keywords_to_move = {
                            kw
                            for sent_idx, kw in self.country_sentence_keywords[prefix]
                            if sent_idx == e.sent_idx
                        }
                        if keywords_to_move:
                            # Add to new code's sentence keywords
                            self.country_sentence_keywords.setdefault(new_code, set())
                            for kw in keywords_to_move:
                                self.country_sentence_keywords[new_code].add(
                                    (e.sent_idx, kw)
                                )

                            # Add to new code's summary keywords and remove from old
                            self.country_keywords.setdefault(new_code, {})
                            for kw in keywords_to_move:
                                self.country_keywords[new_code][kw] = (
                                    self.country_keywords[new_code].get(kw, 0) + 1
                                )
                                if prefix in self.country_keywords and kw in self.country_keywords[prefix]:
                                    self.country_keywords[prefix][kw] -= 1
                                    if self.country_keywords[prefix][kw] <= 0:
                                        del self.country_keywords[prefix][kw]
                            if prefix in self.country_keywords and not self.country_keywords[prefix]:
                                del self.country_keywords[prefix]

                            # Remove from old code's sentence keywords for this sentence
                            self.country_sentence_keywords[prefix] = {
                                (sent_idx, kw) for sent_idx, kw in self.country_sentence_keywords[prefix] if sent_idx != e.sent_idx
                            }
                            if not self.country_sentence_keywords[prefix]:
                                del self.country_sentence_keywords[prefix]

                    if e.scope != Scope.SEGMENT:
                        if is_region(new_code):
                            e.scope = Scope.REGION
                        elif len(new_code) == 2:
                            e.scope = Scope.COUNTRY

    def _resolve_international_gap(self):
        """
        Derives International total if Global Total is known and other regions are known.
        Global - (North America + Europe + ...) = International
        """
        if self.global_total <= 0:
            return

        # Find International Entry (Scope.REGION)
        intl_entry = next(
            (
                e
                for e in self.entries
                if e.scope == Scope.REGION and e.key == Region.INTERNATIONAL.value
            ),
            None,
        )

        # If we don't have an International entry to fill, or it already has a total, skip
        if not intl_entry or intl_entry.total_count is not None:
            return

        # Calculate sum of other regions
        resolved_region_totals = {}

        for r in Region:
            r_name = r.value
            if r_name in IGNORED_REGIONS:
                continue

            # 1. Check for Region Entry
            r_entry = next(
                (
                    e
                    for e in self.entries
                    if e.scope == Scope.REGION and e.key == r_name
                ),
                None,
            )
            if r_entry and r_entry.total_count:
                resolved_region_totals[r_name] = r_entry.total_count
                continue

            # 2. Sum Countries (using get_child_stats for comprehensive aggregation)
            has_children, stats = self.get_child_stats(r_name)
            if has_children and stats["total"] > 0:
                resolved_region_totals[r_name] = stats["total"]

        sum_others = sum(resolved_region_totals.values())

        if sum_others < self.global_total:
            gap = self.global_total - sum_others
            if gap > 0:
                intl_entry.total_count = gap
                self.resolution_log.append(
                    f"Resolved International Total: {gap} (Global {self.global_total} - Others {sum_others})"
                )

                if intl_entry.percentage is not None:
                    intl_entry.covered_count = round(
                        (intl_entry.percentage / 100.0) * gap
                    )
                    self.resolution_log.append(
                        f"Resolved International Count: {intl_entry.percentage}% of {gap}"
                    )
                elif intl_entry.covered_count is not None:
                    intl_entry.percentage = round(
                        (intl_entry.covered_count / gap) * 100.0, 2
                    )

    def _apply_dummy_union_percentage(self):
        """
        Applies a dummy percentage to union records that lack quantitative data,
        provided there are no negations for that country/region.
        """
        # Strict guard: if explicit percentages are present in this run,
        # do not synthesize dummy percentages. This prevents explicit table
        # percentages from being mixed with inferred dummy rates.
        has_any_explicit_percentage = any(
            e.percentage is not None and e.is_explicit and not e.is_dummy_percent
            for e in self.entries
        )
        if has_any_explicit_percentage:
            self.resolution_log.append(
                "Skipped dummy percentage inference: explicit percentage entries detected."
            )
            return

        # Build concrete-data maps so dummy percentages can be blocked per geo scope
        # (country/region), not globally.
        concrete_country_keys = set()
        concrete_region_keys = set()
        for c_entry in self.entries:
            if not (
                c_entry.is_union_record
                and not c_entry.is_dummy_percent
                and (
                    c_entry.covered_count is not None
                    or c_entry.not_covered_count is not None
                    or c_entry.total_count is not None
                )
            ):
                continue

            base_key = (
                str(c_entry.key).split("::")[0] if c_entry.key is not None else ""
            )
            if not base_key:
                continue

            if c_entry.scope == Scope.SEGMENT:
                concrete_country_keys.add(base_key)
                r_name = _CODE_TO_REGION.get(base_key)
                if r_name:
                    concrete_region_keys.add(r_name)
            elif c_entry.scope == Scope.COUNTRY:
                concrete_country_keys.add(base_key)
                r_name = _CODE_TO_REGION.get(base_key)
                if r_name:
                    concrete_region_keys.add(r_name)
            elif c_entry.scope == Scope.REGION:
                concrete_region_keys.add(_CODE_TO_REGION.get(base_key, base_key))

        if concrete_country_keys or concrete_region_keys:
            self.resolution_log.append(
                "Scoped dummy guards enabled (country/region concrete count data detected)."
            )

        # 1. Identify negated scopes
        negated_keys = set()
        negated_geos = set()

        for e in self.entries:
            if e.is_negated:
                negated_keys.add(e.key)
                if e.related_geo_codes:
                    negated_geos.update(e.related_geo_codes)

        # 2. Apply dummy to qualifying entries
        for e in self.entries:
            # Skip Aggregates from dummy percentage application
            if e.scope == Scope.AGGREGATE or e.key in AGG_SET:
                continue

            # Skip International if we have specific international countries
            # This prevents "International" dummy entries from diluting specific data
            if e.key in INT_SET:
                has_specific_intl = any(
                    c
                    for c in self.mentioned_countries
                    if c not in IGNORED_REGIONS and c != self.domestic_country_code
                )
                if has_specific_intl:
                    continue

            # Check basic criteria: Union record, no data, not already negated
            # Also allow if it's an existing dummy (1.0%) that needs a count calculated
            is_candidate = (
                e.is_union_record
                and (e.percentage is None or e.ambiguity_multiplier is not None)
                and e.covered_count is None
                and e.not_covered_count is None
                and not e.is_negated
            )
            is_existing_dummy = e.is_dummy_percent

            if is_candidate or is_existing_dummy:
                # Scoped guard: don't apply dummy if same country/region already has
                # concrete union count-based data.
                base_key = str(e.key).split("::")[0] if e.key is not None else ""
                scoped_country = None
                scoped_region = None
                if e.scope in (Scope.COUNTRY, Scope.SEGMENT) and len(base_key) == 2:
                    scoped_country = base_key
                if e.scope == Scope.REGION:
                    scoped_region = _CODE_TO_REGION.get(base_key, base_key)
                elif scoped_country:
                    scoped_region = _CODE_TO_REGION.get(scoped_country)

                if scoped_country and scoped_country in concrete_country_keys:
                    self.resolution_log.append(
                        f"Skipped dummy for {e.key}: concrete count data exists for country {scoped_country}."
                    )
                    continue
                if (
                    e.scope == Scope.REGION
                    and scoped_region
                    and scoped_region in concrete_region_keys
                ):
                    self.resolution_log.append(
                        f"Skipped dummy for {e.key}: concrete count data exists in region {scoped_region}."
                    )
                    continue

                # Check negation conflicts (Key or Related Geo)
                if e.key not in negated_keys and not any(
                    g in negated_geos for g in e.related_geo_codes
                ):
                    is_region_calc = False
                    if e.percentage is None:
                        # Try to find rate from external data
                        rate = None
                        # 2. Try calculating from mentioned countries in the region
                        if e.scope == Scope.REGION or is_region(e.key):
                            region_name = e.key
                            relevant_countries = []
                            for code in self.mentioned_countries:
                                if code not in REGION_CODES and _CODE_TO_REGION.get(
                                    code
                                ) in [region_name, e.key]:
                                    relevant_countries.append(code)

                            if relevant_countries:
                                total_weight = 0.0
                                weighted_rate_sum = 0.0
                                used_codes = []

                                for code in relevant_countries:
                                    if (
                                        code in _CODE_TO_LABOR_RATE
                                        and code in _CODE_TO_WEIGHT
                                    ):
                                        w = _CODE_TO_WEIGHT[code]
                                        r = _CODE_TO_LABOR_RATE[code]
                                        # Use boosted rate for weighted average
                                        boosted_r, _ = self._calculate_boosted_rate(
                                            r, key=code
                                        )
                                        weighted_rate_sum += boosted_r * w
                                        total_weight += w
                                        used_codes.append(code)

                                if total_weight > 0:
                                    rate = weighted_rate_sum / total_weight
                                    is_region_calc = True
                                    self.resolution_log.append(
                                        f"Calculated inferred rate {rate*100:.2f}% for {region_name} based on weighted sum of boosted rates: {', '.join(used_codes)}"
                                    )

                        # 3. Try Segment (Country::...)
                        if rate is None and isinstance(e.key, str):
                            code = e.key.split("::")[0]
                            if code in _CODE_TO_LABOR_RATE:
                                rate = _CODE_TO_LABOR_RATE[code]
                            elif code in REGION_LABOR_RATES:
                                rate = REGION_LABOR_RATES[code]

                        if is_region_calc and rate is not None:
                            e.percentage = round(rate * 100, 2)
                            e.is_qualitative = True
                            e.is_dummy_percent = True
                            self._mark_source(
                                e,
                                "percentage_source",
                                PercentageSourceDetail.DUMMY_INFERRED_REGION_WEIGHTED.value,
                            )
                            self._add_source_note(
                                e,
                                "Inferred from weighted sum of boosted constituent rates.",
                            )
                            self.resolution_log.append(
                                f"Applied inferred rate {e.percentage}% to {e.key} (Aggregated from boosted constituents)"
                            )
                        elif e.percentage is None or e.ambiguity_multiplier is not None:
                            base_rate = rate if rate is not None else 0.01

                            mult_note = ""
                            # Apply ambiguity multiplier if present (e.g. "some" = 1.0x, "few" = 0.5x)
                            if e.ambiguity_multiplier is not None:
                                original_base = base_rate
                                base_rate *= e.ambiguity_multiplier
                                mult_note = f" (adj from {original_base*100:.1f}% via {e.ambiguity_multiplier}x mult)"

                            boosted_rate, multiplier = self._calculate_boosted_rate(
                                base_rate, key=e.key
                            )
                            e.percentage = round(boosted_rate * 100, 2)
                            e.is_qualitative = True
                            e.is_dummy_percent = True
                            if rate is not None:
                                self._mark_source(
                                    e,
                                    "percentage_source",
                                    PercentageSourceDetail.DUMMY_INFERRED_EXTERNAL_DATA.value,
                                )
                            else:
                                self._mark_source(
                                    e,
                                    "percentage_source",
                                    PercentageSourceDetail.DUMMY_INFERRED_DEFAULT_RATE.value,
                                )
                            self._add_source_note(
                                e,
                                f"Applied keyword booster x{multiplier:.2f} (keywords={self.total_union_keywords}).",
                            )
                            source_desc = (
                                "External Data" if rate is not None else "Default"
                            )
                            self.resolution_log.append(
                                f"Applied inferred rate {e.percentage}% to {e.key} ({source_desc} {base_rate*100:.1f}%{mult_note} x {multiplier:.2f} booster from {self.total_union_keywords} keywords)"
                            )

    def _calculate_missing_covered_counts(self):
        """
        Calculates covered_count for entries that have both total_count and percentage
        but lack covered_count.
        """
        for e in self.entries:
            # Preserve explicit zero/negated country segments from being overridden by
            # inferred country-level percentages.
            if e.scope == Scope.COUNTRY and isinstance(e.key, str):
                has_zero_segment = False
                for s in self.entries:
                    if (
                        s.scope == Scope.SEGMENT
                        and self._segment_matches_country(s.key, e.key)
                        and s.sent_idx != -1
                    ):
                        has_zero = (
                            s.is_negated or s.percentage == 0 or s.covered_count == 0
                        )
                        if has_zero:
                            has_zero_segment = True
                            break
                if has_zero_segment:
                    self.resolution_log.append(
                        f"Skipped covered-count calc for {e.key}: explicit zero/negated segment exists."
                    )
                    continue

            if (
                e.total_count is not None
                and e.percentage is not None
                and e.covered_count is None
            ):
                e.covered_count = round((e.percentage / 100.0) * e.total_count)
                denom_is_fallback = (
                    e.total_count_source_type == SourceType.FALLBACK.value
                    or e.denominator_source_type == SourceType.FALLBACK.value
                )
                self._mark_source(
                    e,
                    "covered_count_source",
                    self._derive_count_source_from_percentage(
                        e, denominator_is_fallback=denom_is_fallback
                    ),
                )
                if e.denominator_source is None:
                    self._mark_source(
                        e,
                        "denominator_source",
                        DenominatorSourceDetail.EXISTING_TOTAL.value,
                    )
                self.resolution_log.append(
                    f"Calculated covered count for {e.key}: {e.percentage}% of {e.total_count} -> {e.covered_count}"
                )

    def _inject_virtual_global_pool(self):
        """
        Injects a virtual global total if no census data exists but union records are present.
        This allows weight-based distribution to function for 'union name only' scenarios.
        """
        # Check if we have any existing breakdown counts (census data)
        # If we have a global total (e.g. from external) but no breakdown, we still want to distribute it.
        has_breakdown = (
            any(v > 0 for v in self.region_totals.values())
            or any(v > 0 for v in self.country_totals.values())
            or any(
                e.total_count is not None and e.total_count > 0 for e in self.entries
            )
        )

        if has_breakdown:
            return

        has_unions = any(e.is_union_record for e in self.entries)

        # If no global total provided and no unions to infer from, abort
        if self.global_total <= 0 and not has_unions:
            return

        calculate_virtual = self.global_total <= 0
        if calculate_virtual:
            self.is_using_virtual = True

        # Ensure domestic entry exists so it gets populated with the distributed total
        # instead of defaulting to 0% coverage in _resolve_single_country
        dom_entry_exists = any(
            e.scope == Scope.COUNTRY and e.key == self.domestic_country_code
            for e in self.entries
        )

        # Base for home country
        virtual_total = 1000.0

        # Identify unique geographic entities mentioned
        unique_entities = set()
        for e in self.entries:
            if e.scope in (Scope.COUNTRY, Scope.REGION, Scope.SEGMENT):
                key = str(e.key)
                if e.scope == Scope.SEGMENT and "::" in key:
                    key = key.split("::")[0]

                if key and key not in IGNORED_REGIONS:
                    unique_entities.add(key)

        for code in self.mentioned_countries:
            if code and code not in IGNORED_REGIONS:
                unique_entities.add(code)

        # Remove domestic from set
        if self.domestic_country_code in unique_entities:
            unique_entities.remove(self.domestic_country_code)
        # Also remove "Domestic" aliases
        for d in DOMESTIC_SET:
            if d in unique_entities:
                unique_entities.remove(d)

        # Safeguard: If domestic is negated, ensure we have at least one external entity
        if self.domestic_is_negated and not unique_entities:
            unique_entities.add(GeoCode.INTERNATIONAL.value)

        # --- Filter duplicates/aliases/containers BEFORE calculation ---
        to_remove = set()

        # Pre-calculate region mapping
        entity_regions = {}
        for e in unique_entities:
            if is_region(e):
                entity_regions[e] = _CODE_TO_REGION.get(e, e)
            else:
                entity_regions[e] = _CODE_TO_REGION.get(e)

        if any(e.key != self.domestic_country_code for e in self.entries):
            # Remove international
            to_remove |= INT_SET

        sorted_unique = sorted(list(unique_entities))

        for r in sorted_unique:
            if r in to_remove:
                continue

            is_region_key = is_region(r)

            if is_region_key:
                r_canonical = entity_regions.get(r)

                # 1. Check for Aliases (e.g. EU vs Europe)
                for other in unique_entities:
                    if other == r or other in to_remove:
                        continue

                    if is_region(other):
                        other_canonical = entity_regions.get(other)
                        if other_canonical == r_canonical:
                            # Collision found. Prefer canonical name.
                            if r != r_canonical and other == r_canonical:
                                to_remove.add(r)
                                self.resolution_log.append(
                                    f"Virtual Pool: Removed alias '{r}' in favor of canonical '{other}'."
                                )
                                break
                            elif r != r_canonical and other != r_canonical:
                                if r > other:
                                    to_remove.add(r)
                                    self.resolution_log.append(
                                        f"Virtual Pool: Removed alias '{r}' in favor of '{other}'."
                                    )
                                    break

                if r in to_remove:
                    continue

                # 2. Check for Child Countries
                if r_canonical:
                    for other in unique_entities:
                        if other == r or other in to_remove:
                            continue

                        if (
                            not is_region(other)
                            and entity_regions.get(other) == r_canonical
                        ):
                            to_remove.add(r)
                            self.resolution_log.append(
                                f"Virtual Pool: Removed generic '{r}' in favor of specific countries."
                            )
                            break

            # Check for composite countries acting as containers (e.g. CIS containing RU)
            if r in COMPOSITE_COUNTRIES:
                constituents = set(get_composite_constituents(r))
                has_specifics = False
                for other in unique_entities:
                    if other == r or other in to_remove:
                        continue
                    if other in constituents:
                        has_specifics = True
                        break
                if has_specifics:
                    to_remove.add(r)
                    self.resolution_log.append(
                        f"Virtual Pool: Removed composite '{r}' in favor of specific constituents."
                    )

        unique_entities -= to_remove

        # Parameters
        UNIT_BASE = 100.0
        INTL_BOOSTER = 1.0
        BOOSTER_STEP = 0.01

        sorted_entities = sorted(list(unique_entities))
        log_details = []

        for entity in sorted_entities:
            weight = 0.005
            if entity in _CODE_TO_WEIGHT:
                weight = _CODE_TO_WEIGHT[entity]
            elif entity in REGION_WEIGHTS:
                weight = REGION_WEIGHTS[entity]

            # Dynamic contribution
            contribution = UNIT_BASE * (1 + (weight * 10)) * INTL_BOOSTER
            virtual_total += contribution

            log_details.append(f"{entity}")

            if calculate_virtual:
                INTL_BOOSTER += BOOSTER_STEP

        if calculate_virtual:
            self.global_total = round(virtual_total)
            log_msg = f"Injected Virtual Global Pool ({self.global_total}) based on {len(sorted_entities)} intl entities."
            log_msg += f" Details: {', '.join(log_details)}"
            self.resolution_log.append(log_msg)
        else:
            self.resolution_log.append(
                f"Using existing Global Total ({self.global_total}) for virtual distribution."
            )

        # Distribute to populate country/region totals for fallback
        # This distributes self.global_total (whether calculated or external)
        dist_entities = [{"key": self.domestic_country_code}]
        for entity in unique_entities:
            dist_entities.append({"key": entity})

        distribution, note = weighted_division(
            self.global_total,
            dist_entities,
            use_labor_weights=False,
            domestic_country=self.domestic_country_code,
        )

        for key, val in distribution.items():
            # Determine if region or country
            _region = is_region(key)

            if _region:
                if self.region_totals.get(key, 0) == 0:
                    self.region_totals[key] = val
            else:
                if self.country_totals.get(key, 0) == 0:
                    self.country_totals[key] = val
        if note:
            self.resolution_log.append(f"Distributed Virtual Pool: {note}")

        if not dom_entry_exists:
            self.entries.append(
                Entry(
                    scope=Scope.COUNTRY,
                    key=self.domestic_country_code,
                    is_explicit=False,
                    total_count=self.country_totals.get(self.domestic_country_code, 0),
                    sent_idx=0,
                    total_count_source=TotalSourceDetail.WEIGHTED_DIVISION_VIRTUAL_POOL.value,
                    denominator_source=DenominatorSourceDetail.WEIGHTED_DIVISION_VIRTUAL_POOL.value,
                )
            )
            self.resolution_log.append(
                f"Injected placeholder for domestic country: {self.domestic_country_code}"
            )

        # Restore totals for removed generic regions based on sum of constituents
        for removed_key in to_remove:
            # Normalize key
            key_str = (
                removed_key.value if isinstance(removed_key, Enum) else str(removed_key)
            )

            # Skip International/Global as they are aggregates of regions and handled elsewhere
            if key_str in IGNORED_REGIONS:
                continue

            # Special handling for Composite Countries (restore sum of constituents only)
            if key_str in COMPOSITE_COUNTRIES:
                constituents = set(get_composite_constituents(key_str))
                comp_sum = 0.0
                found_constituents = []
                for code, count in self.country_totals.items():
                    if code in constituents:
                        comp_sum += count
                        found_constituents.append(code)
                if comp_sum > 0:
                    self.country_totals[key_str] = comp_sum
                    self.resolution_log.append(
                        f"Restored total for composite '{key_str}': {comp_sum} (Sum of {', '.join(found_constituents)})"
                    )
                continue

            region_sum = 0.0
            constituents = []

            # Determine canonical region name
            target_region = _CODE_TO_REGION.get(key_str, key_str)

            for code, count in self.country_totals.items():
                if _CODE_TO_REGION.get(code) == target_region:
                    region_sum += count
                    constituents.append(code)

            if region_sum > 0:
                self.region_totals[key_str] = region_sum
                self.resolution_log.append(
                    f"Restored total for '{key_str}': {region_sum} (Sum of {', '.join(constituents)})"
                )

    def resolve_coverage(
        self, use_virtual_pool: bool = False, apply_dummy_percentages: bool = False, use_fallback: bool = False
    ):
        """
        Fills in missing info for countries and regions.
        """
        # 0. Inject Virtual Pool if empty (for Union Name only cases)
        # Must be done before resolving countries/regions so they have totals to work with
        if use_virtual_pool and self.global_total == 0:
            self._inject_virtual_global_pool()

        # 0. Resolve Domestic
        self._route_domestic()
        # 0.5 Resolve INT codes
        self._resolve_int_codes()
        # 0.1 Apply dummy percentages for union records with no data
        if apply_dummy_percentages:
            self._apply_dummy_union_percentage()
        # 0.5 Resolve Aggregates (Propagate down)
        self._resolve_aggregates()
        # 0.6 Promote region-only records to pseudo-country entities when
        # they have no resolved child constituents.
        self._promote_region_entries_to_pseudo_countries()
        # 1. Resolve Countries
        for country_code, census_total in self.country_totals.items():
            self._resolve_single_country(country_code, census_total)

        # 2. Resolve Regions (Specific First, then International)
        # We sort to ensure International comes last, so it can aggregate resolved children
        sorted_regions = sorted(
            self.region_totals.keys(),
            key=lambda r: 1 if r == Region.INTERNATIONAL.value else 0,
        )
        for region_name in sorted_regions:
            region_total = self.region_totals[region_name]
            self._resolve_single_region(region_name, region_total)

        # 2.5 Build residual region segments (e.g. Europe without Germany).
        self._synthesize_subtraction_segments()

        # 3. Resolve International Gap
        self._resolve_international_gap()

        # 4. Apply dummy percentages (Final fallback for backfilled totals)
        if apply_dummy_percentages:
            self._apply_dummy_union_percentage()

        # 4.5 Calculate missing covered counts (for entries with Total + Pct but no Covered)
        self._calculate_missing_covered_counts()

        # 4.8 Inject Virtual Pool if still empty (for Union Name only cases)
        if use_virtual_pool and self.global_total == 0:
            self._inject_virtual_global_pool()

        # 5. Apply fallback denominators (0.1%) for remaining percentage-only entries
        if use_fallback:
            self._apply_fallback_denominators()
        # 6. Final denominator dedup to prevent same-scope denominator inflation
        # from repeated references to the same population.
        self._dedupe_redundant_scope_denominators()

    def _apply_fallback_denominators(self):
        """
        Applies a conservative denominator to entries that have a percentage
        but lack a total count (usually due to safety checks preventing census inheritance).
        Uses weights to scale the population if inheriting from a broader scope.
        Distributes population if multiple segments map to the same scope.
        """
        global_weight = sum(
            REGION_WEIGHTS.get(r.value, 0.0)
            for r in [
                Region.NORTH_AMERICA,
                Region.EUROPE,
                Region.ASIA_PACIFIC,
                Region.LATIN_AMERICA,
                Region.MIDDLE_EAST_AFRICA,
            ]
        )

        # Group candidates by scope to distribute population
        candidates_by_scope = {}
        explicit_pct_only_by_scope: Dict[Tuple[str, Any], List[Entry]] = {}

        def _combine_explicit_percentages(
            vals: List[float], approx_tol: float = 2.0
        ) -> Optional[float]:
            nums = [float(v) for v in vals if v is not None]
            nums = [v for v in nums if 0.0 <= v <= 100.0]
            if not nums:
                return None
            if len(nums) == 1:
                return nums[0]
            nums_sorted = sorted(nums, reverse=True)
            largest = nums_sorted[0]
            smaller_sum = sum(nums_sorted[1:])
            total_sum = sum(nums_sorted)
            if abs(largest - smaller_sum) <= approx_tol:
                return largest
            if total_sum <= 100.0 + 1e-9:
                return total_sum
            return sum(nums) / len(nums)

        for e in self.entries:
            # Only target entries with percentage but no counts
            if (
                e.percentage is not None
                and e.total_count is None
                and e.covered_count is None
            ):
                # Determine target scope early (used by both explicit and inferred paths)
                country_code = None
                scope_key = None
                scope_type = None

                # 1. Country Level
                if e.scope == Scope.SEGMENT and e.key and "::" in str(e.key):
                    country_code = self._segment_anchor_code(str(e.key))
                    scope_key = country_code
                    scope_type = Scope.COUNTRY.value
                elif e.scope == Scope.COUNTRY:
                    country_code = e.key
                    scope_key = country_code
                    scope_type = Scope.COUNTRY.value
                elif e.scope == Scope.REGION and e.key:
                    scope_key = e.key
                    scope_type = Scope.REGION.value
                else:
                    scope_key = Scope.GLOBAL
                    scope_type = Scope.GLOBAL.value

                # Do not fabricate counts for explicit percentage-only statements
                # when no denominator is present. This avoids converting table
                # percentages (e.g., "% of Company's Employees") into arbitrary
                # fallback counts from virtual/distributed bases.
                if e.is_explicit and not e.is_dummy_percent:
                    key = (scope_type, scope_key)
                    explicit_pct_only_by_scope.setdefault(key, []).append(e)
                    self.resolution_log.append(
                        f"Skipped fallback for {e.key}: explicit percentage without denominator."
                    )
                    continue

                # Check for conflicting negations in the relevant scopes
                scopes_to_check = set()
                if country_code:
                    scopes_to_check.add(country_code)
                    # r_name = _CODE_TO_REGION.get(country_code)
                    # if r_name:
                    #     scopes_to_check.add(r_name)
                elif e.scope == Scope.REGION and e.key:
                    scopes_to_check.add(e.key)
                # scopes_to_check.add(GeoCode.GLOBAL.value)
                # scopes_to_check.add(Scope.GLOBAL.value)

                is_scope_negated = False
                for check_e in self.entries:
                    if check_e is e:
                        continue

                    # Ignore system-generated placeholders (sent_idx == -1) to avoid blocking based on inference
                    if check_e.sent_idx == -1:
                        continue

                    # Check for explicit negation OR zero coverage (count/pct) in the scope
                    has_zero = (check_e.covered_count == 0) or (check_e.percentage == 0)

                    # Determine whether check_e belongs to the same geographic scope
                    in_scope = False
                    # Direct key match (country/region/global keys)
                    if check_e.key in scopes_to_check:
                        in_scope = True
                    else:
                        # If we are targeting a country, include any segment entries like "CN::..."
                        if (
                            country_code
                            and isinstance(check_e.key, str)
                            and self._segment_matches_country(check_e.key, country_code)
                        ):
                            in_scope = True
                        # If check_e is a country whose region is in scopes_to_check, include it
                        if not in_scope and isinstance(check_e.key, str):
                            try:
                                region_of_check = _CODE_TO_REGION.get(check_e.key)
                            except Exception:
                                region_of_check = None
                            if region_of_check and region_of_check in scopes_to_check:
                                in_scope = True

                    if (check_e.is_negated or has_zero) and in_scope:
                        is_scope_negated = True
                        self.resolution_log.append(
                            f"Skipped fallback for {e.key}: Negation or zero found for {check_e.key}"
                        )
                        break

                if is_scope_negated:
                    e.covered_count = 0.0
                    e.percentage = 0.0
                    self._mark_source(
                        e,
                        "covered_count_source",
                        CountSourceDetail.FALLBACK_NEGATION_GUARD_ZERO.value,
                    )
                    self._mark_source(
                        e,
                        "percentage_source",
                        PercentageSourceDetail.FALLBACK_NEGATION_GUARD_ZERO.value,
                    )
                    self.resolution_log.append(
                        f"Zeroed out {e.key} as safety measure due to negation."
                    )
                    continue

                # Add to candidates
                key = (scope_type, scope_key)
                if key not in candidates_by_scope:
                    candidates_by_scope[key] = []
                candidates_by_scope[key].append(e)

        # Process groups
        for (scope_type, scope_key), group in candidates_by_scope.items():
            # If targeting a region, check if we already have child data.
            # If so, skip fallback to avoid conflicting with bottom-up aggregation.
            if scope_type == Scope.REGION.value:
                _, child_stats = self.get_child_stats(scope_key)
                if (
                    child_stats["total"] > 0
                    or child_stats["covered"] > 0
                    or child_stats["not_covered"] > 0
                ):
                    self.resolution_log.append(
                        f"Skipped fallback for {scope_key}: Child data exists (Total: {child_stats['total']})"
                    )
                    continue

            base_pop = 0.0
            source_total_pop = 0.0
            geo_name = "Unknown"
            target_weight = 0.0
            source_weight = 0.0
            pool_source = "Direct"
            prevent_global_fallback = False
            force_conservative = False

            # Determine Base Population & Weights
            if scope_type == Scope.COUNTRY.value:
                geo_name = scope_key
                target_weight = _CODE_TO_WEIGHT.get(scope_key, 0.0)
                base_pop = self.country_totals.get(scope_key, 0.0)
                if base_pop > 0:
                    source_total_pop = base_pop
                    source_weight = target_weight
                    pool_source = f"Country ({scope_key})"

                # Fallback to Region
                if base_pop <= 0:
                    r_name = _CODE_TO_REGION.get(scope_key)
                    if r_name:
                        region_total = self.region_totals.get(r_name, 0.0)

                        if region_total > 0:
                            source_total_pop = region_total
                            prevent_global_fallback = True
                            base_pop = region_total

                            # Subtract known siblings to avoid using exhausted pool
                            siblings_sum = sum(
                                c_total
                                for c_code, c_total in self.country_totals.items()
                                if c_code != scope_key
                                and _CODE_TO_REGION.get(c_code) == r_name
                            )
                            base_pop = max(0.0, base_pop - siblings_sum)

                            if base_pop > 0:
                                geo_name = r_name
                                source_weight = REGION_WEIGHTS.get(r_name, 0.0)
                                pool_source = f"Region ({r_name}) Fallback"
                            else:
                                base_pop = region_total
                                geo_name = r_name
                                source_weight = REGION_WEIGHTS.get(r_name, 0.0)
                                pool_source = f"Region ({r_name}) Exhausted"
                                force_conservative = True

            elif scope_type == Scope.REGION.value:
                geo_name = scope_key
                target_weight = REGION_WEIGHTS.get(scope_key, 0.0)
                base_pop = self.region_totals.get(scope_key, 0.0)
                if base_pop > 0:
                    source_total_pop = base_pop
                if base_pop > 0:
                    source_weight = target_weight
                    pool_source = f"Region ({scope_key})"

            # Fallback to Global
            if base_pop <= 0 and not prevent_global_fallback:
                base_pop = self.global_total
                source_total_pop = self.global_total
                geo_name = "Global"
                source_weight = global_weight
                pool_source = "Global Fallback"
                # If target weight wasn't set (e.g. Global scope target), set it
                if scope_type == Scope.GLOBAL.value:
                    target_weight = global_weight
                    pool_source = "Global"

            if base_pop > 0:
                # Scale population if source is broader than target
                estimated_pop = base_pop
                is_weighted_estimate = False
                if source_weight > 0 and target_weight > 0:
                    # If source is significantly larger (parent scope)
                    if source_weight > target_weight * 1.05:
                        estimated_pop = base_pop * (target_weight / source_weight)
                        is_weighted_estimate = True
                    elif source_weight >= target_weight * 0.95:
                        # Same scope (approx equal weights)
                        is_weighted_estimate = True

                # Filter out system placeholders if explicit entries exist in the group
                explicit_entries = [e for e in group if e.sent_idx != -1]
                if explicit_entries:
                    # If we have explicit entries, ignore the system placeholders for distribution
                    group = explicit_entries

                # Calculate consumed population to avoid double counting / inflation
                consumed_pop = 0.0
                if scope_type == Scope.COUNTRY.value:
                    for e in self.entries:
                        # Check if entry is a segment of this country and has a total count
                        if (
                            e.scope == Scope.SEGMENT
                            and e.key
                            and e.key.startswith(f"{scope_key}::")
                        ):
                            if e.total_count is not None:
                                consumed_pop += e.total_count
                elif scope_type == Scope.REGION.value:
                    country_entries = {}
                    for e in self.entries:
                        if e in group:
                            continue

                        c_code = None
                        if e.scope == Scope.COUNTRY:
                            c_code = e.key
                        elif e.scope == Scope.SEGMENT and e.key and "::" in str(e.key):
                            c_code = e.key.split("::")[0]

                        if c_code:
                            if _CODE_TO_REGION.get(c_code) == scope_key:
                                if c_code not in country_entries:
                                    country_entries[c_code] = []
                                country_entries[c_code].append(e)

                    for c_code, entries in country_entries.items():
                        c_total = 0.0
                        has_c_scope = False
                        for e in entries:
                            if e.scope == Scope.COUNTRY and e.total_count is not None:
                                if e.total_count > c_total:
                                    c_total = e.total_count
                                has_c_scope = True

                        if has_c_scope:
                            consumed_pop += c_total
                        else:
                            consumed_pop += sum(
                                e.total_count
                                for e in entries
                                if e.total_count is not None
                            )

                elif scope_type == Scope.GLOBAL.value:
                    region_entries = {}
                    for e in self.entries:
                        if e in group:
                            continue

                        key = None
                        if e.scope == Scope.REGION:
                            key = e.key
                        elif e.scope == Scope.COUNTRY:
                            r_name = _CODE_TO_REGION.get(e.key)
                            key = r_name if r_name else e.key
                        elif e.scope == Scope.SEGMENT and e.key and "::" in str(e.key):
                            c_code = e.key.split("::")[0]
                            r_name = _CODE_TO_REGION.get(c_code)
                            key = r_name if r_name else c_code

                        if key and key not in IGNORED_REGIONS:
                            if key not in region_entries:
                                region_entries[key] = []
                            region_entries[key].append(e)

                    for r_key, entries in region_entries.items():
                        r_total = 0.0
                        has_r_scope = False
                        for e in entries:
                            if e.scope == Scope.REGION and e.total_count is not None:
                                if e.total_count > r_total:
                                    r_total = e.total_count
                                has_r_scope = True

                        if has_r_scope:
                            consumed_pop += r_total
                        else:
                            # Sum Countries
                            c_entries_map = {}
                            for e in entries:
                                c_code = None
                                if e.scope == Scope.COUNTRY:
                                    c_code = e.key
                                elif (
                                    e.scope == Scope.SEGMENT
                                    and e.key
                                    and "::" in str(e.key)
                                ):
                                    c_code = e.key.split("::")[0]

                                if c_code:
                                    if c_code not in c_entries_map:
                                        c_entries_map[c_code] = []
                                    c_entries_map[c_code].append(e)

                            for c_code, c_list in c_entries_map.items():
                                c_total = 0.0
                                has_c_scope = False
                                for e in c_list:
                                    if (
                                        e.scope == Scope.COUNTRY
                                        and e.total_count is not None
                                    ):
                                        if e.total_count > c_total:
                                            c_total = e.total_count
                                        has_c_scope = True

                                if has_c_scope:
                                    consumed_pop += c_total
                                else:
                                    consumed_pop += sum(
                                        e.total_count
                                        for e in c_list
                                        if e.total_count is not None
                                    )

                # Determine available population
                available_pop = estimated_pop - consumed_pop

                # Decide whether to use the full available remainder or a conservative fallback
                use_conservative = False
                distributable_pop = 0.0

                # If we have very little room left (or negative), force conservative mode
                # We use 5% buffer or if consumed > estimated
                if force_conservative or available_pop < (estimated_pop * 0.05):
                    use_conservative = True
                    distributable_pop = estimated_pop  # Base for calc
                else:
                    distributable_pop = available_pop

                # Distribute among segments
                num_segments = len(group)
                if num_segments > 1:
                    distributable_pop /= num_segments

                # Determine final denominator
                # Use full estimate if weighted/scaled OR if scopes match explicitly
                scopes_match = (
                    scope_type == Scope.COUNTRY.value and geo_name == scope_key
                ) or (scope_type == Scope.REGION.value and geo_name == scope_key)

                base_rate = 0.0025  # 0.25%
                if (is_weighted_estimate or scopes_match) and not use_conservative:
                    small_denom = max(1.0, round(distributable_pop))
                else:
                    # Additive Logic: 0.25% of Source Total (Floor) + 0.25% of Distributable (Variable)
                    # Distribute source total share among segments
                    term1 = (source_total_pop * base_rate) / num_segments
                    term2 = distributable_pop * base_rate
                    small_denom = max(1.0, round(term1 + term2))

                for e in group:
                    assert isinstance(e, Entry)
                    e.total_count = small_denom
                    e.covered_count = round(((e.percentage or 0) / 100.0) * small_denom)
                    if scope_type == Scope.COUNTRY.value:
                        denom_source = (
                            TotalSourceDetail.FALLBACK_DENOMINATOR_COUNTRY.value
                        )
                    elif scope_type == Scope.REGION.value:
                        denom_source = (
                            TotalSourceDetail.FALLBACK_DENOMINATOR_REGION.value
                        )
                    else:
                        denom_source = (
                            TotalSourceDetail.FALLBACK_DENOMINATOR_GLOBAL.value
                        )
                    self._mark_source(e, "total_count_source", denom_source)
                    if (
                        denom_source
                        == TotalSourceDetail.FALLBACK_DENOMINATOR_COUNTRY.value
                    ):
                        den_detail = (
                            DenominatorSourceDetail.FALLBACK_DENOMINATOR_COUNTRY.value
                        )
                    elif (
                        denom_source
                        == TotalSourceDetail.FALLBACK_DENOMINATOR_REGION.value
                    ):
                        den_detail = (
                            DenominatorSourceDetail.FALLBACK_DENOMINATOR_REGION.value
                        )
                    else:
                        den_detail = (
                            DenominatorSourceDetail.FALLBACK_DENOMINATOR_GLOBAL.value
                        )
                    self._mark_source(e, "denominator_source", den_detail)
                    self._mark_source(
                        e,
                        "covered_count_source",
                        self._derive_count_source_from_percentage(
                            e, denominator_is_fallback=True
                        ),
                    )
                    self._add_source_note(
                        e, f"Fallback pool source: {pool_source}; base_geo={geo_name}."
                    )

                    log_msg = f"Resolved COUNT for {e.key} using fallback: {e.percentage}% of {small_denom}"
                    if num_segments > 1:
                        log_msg += f" (Distributed among {num_segments} segments)"

                    if use_conservative:
                        log_msg += f" (Conservative Additive: {base_rate:.2%} of {source_total_pop:.0f} Source + {base_rate:.2%} of {distributable_pop:.1f} Distributable)"

                    # Check if scaled (approx check due to float)
                    total_allocated = distributable_pop * num_segments

                    details = []
                    if abs(total_allocated - base_pop) > 1.0:
                        details.append(
                            f"Scaled from {base_pop} {geo_name} [{pool_source}] by weight {target_weight:.4f}/{source_weight:.4f}"
                        )
                    else:
                        details.append(
                            f"Base {base_pop} from {geo_name} [{pool_source}]"
                        )

                    if consumed_pop > 0:
                        details.append(f"Consumed {consumed_pop}")

                    if details:
                        log_msg += " (" + ", ".join(details) + ")"

                    self.resolution_log.append(log_msg)
            elif prevent_global_fallback:
                self.resolution_log.append(
                    f"Skipped fallback for {scope_key}: {pool_source}"
                )

        # Explicit percentage-only entries:
        # apply combined explicit pct once to the scope's remaining fallback pool
        # as an aggregate count anchor (do not fabricate per-segment denominators).
        for (scope_type, scope_key), group in explicit_pct_only_by_scope.items():
            if not group:
                continue

            combined_pct = _combine_explicit_percentages(
                [e.percentage for e in group if e.percentage is not None]
            )
            if combined_pct is None:
                continue

            base_pop = 0.0
            pool_source = "Direct"
            prevent_global_fallback = False

            if scope_type == Scope.COUNTRY.value:
                base_pop = float(self.country_totals.get(scope_key, 0.0) or 0.0)
                if base_pop > 0:
                    pool_source = f"Country ({scope_key})"
                if base_pop <= 0:
                    r_name = _CODE_TO_REGION.get(scope_key)
                    if r_name:
                        region_total = float(self.region_totals.get(r_name, 0.0) or 0.0)
                        if region_total > 0:
                            siblings_sum = sum(
                                float(c_total or 0.0)
                                for c_code, c_total in self.country_totals.items()
                                if c_code != scope_key
                                and _CODE_TO_REGION.get(c_code) == r_name
                            )
                            rem = max(0.0, region_total - siblings_sum)
                            base_pop = rem if rem > 0 else region_total
                            pool_source = f"Region ({r_name}) Fallback"
                            prevent_global_fallback = True
                if base_pop <= 0 and not prevent_global_fallback:
                    base_pop = float(self.global_total or 0.0)
                    pool_source = "Global Fallback"
            elif scope_type == Scope.REGION.value:
                base_pop = float(self.region_totals.get(scope_key, 0.0) or 0.0)
                pool_source = (
                    f"Region ({scope_key})" if base_pop > 0 else "Global Fallback"
                )
                if base_pop <= 0:
                    base_pop = float(self.global_total or 0.0)
            else:
                base_pop = float(self.global_total or 0.0)
                pool_source = "Global"

            if base_pop <= 0:
                self.resolution_log.append(
                    f"Skipped explicit-pct aggregate fallback for {scope_key}: no fallback pool available."
                )
                continue

            # Remaining unaccounted population in this scope.
            consumed_pop = 0.0
            if scope_type == Scope.COUNTRY.value:
                for e in self.entries:
                    if e in group:
                        continue
                    if e.total_count is None:
                        continue
                    if e.scope == Scope.COUNTRY and e.key == scope_key:
                        consumed_pop += float(e.total_count)
                    elif (
                        e.scope == Scope.SEGMENT
                        and isinstance(e.key, str)
                        and self._segment_matches_country(e.key, str(scope_key))
                    ):
                        consumed_pop += float(e.total_count)
            remaining_pop = max(0.0, base_pop - consumed_pop)
            if remaining_pop <= 0:
                remaining_pop = base_pop

            denom = max(1.0, round(remaining_pop))
            covered = round((combined_pct / 100.0) * denom)

            agg_scope = (
                Scope.COUNTRY
                if scope_type == Scope.COUNTRY.value
                else (
                    Scope.REGION if scope_type == Scope.REGION.value else Scope.GLOBAL
                )
            )
            agg_key = str(scope_key) if scope_key is not None else Scope.GLOBAL.value

            self.entries.append(
                Entry(
                    covered_count=float(covered),
                    not_covered_count=float(max(0.0, denom - covered)),
                    percentage=float(round(combined_pct, 2)),
                    total_count=float(denom),
                    key=agg_key,
                    is_qualitative=False,
                    is_explicit=False,
                    is_union_record=True,
                    scope=agg_scope,
                    sent_idx=-1,
                    percentage_source=PercentageSourceDetail.EXPLICIT_PERCENTAGE.value,
                    covered_count_source=CountSourceDetail.CALCULATED_FROM_PERCENTAGE_AND_FALLBACK_DENOMINATOR.value,
                    not_covered_count_source=CountSourceDetail.CALCULATED_FROM_TOTAL_MINUS_COVERED.value,
                    total_count_source=(
                        TotalSourceDetail.FALLBACK_DENOMINATOR_COUNTRY.value
                        if scope_type == Scope.COUNTRY.value
                        else (
                            TotalSourceDetail.FALLBACK_DENOMINATOR_REGION.value
                            if scope_type == Scope.REGION.value
                            else TotalSourceDetail.FALLBACK_DENOMINATOR_GLOBAL.value
                        )
                    ),
                    denominator_source=(
                        DenominatorSourceDetail.FALLBACK_DENOMINATOR_COUNTRY.value
                        if scope_type == Scope.COUNTRY.value
                        else (
                            DenominatorSourceDetail.FALLBACK_DENOMINATOR_REGION.value
                            if scope_type == Scope.REGION.value
                            else DenominatorSourceDetail.FALLBACK_DENOMINATOR_GLOBAL.value
                        )
                    ),
                )
            )

            self.resolution_log.append(
                f"Resolved aggregate COUNT for {agg_key} from explicit percentages: {combined_pct:.2f}% of {denom} (remaining fallback pool from {pool_source})."
            )

    def _check_contradictions(self):
        """
        Checks for logical contradictions in the tracked data.
        """
        # 1. Internal Arithmetic (Parts vs Total)
        for e in self.entries:
            if (
                e.total_count
                and e.covered_count is not None
                and e.not_covered_count is not None
            ):
                parts_sum = e.covered_count + e.not_covered_count
                if parts_sum > e.total_count * 1.05:  # 5% tolerance
                    self.resolution_log.append(
                        f"Contradiction (Arithmetic): {e.key} parts ({parts_sum}) exceed total ({e.total_count})"
                    )

            # Percentage vs Count consistency
            if (
                e.total_count
                and e.percentage is not None
                and e.covered_count is not None
            ):
                implied = (e.percentage / 100.0) * e.total_count
                # Check for deviation > 10% of total (for significant populations)
                if e.total_count > 50 and abs(implied - e.covered_count) > (
                    e.total_count * 0.10
                ):
                    self.resolution_log.append(
                        f"Contradiction (Math): {e.key} percentage ({e.percentage}%) implies {implied:.0f}, but count is {e.covered_count}"
                    )

        # 2. Hierarchical Mismatches (Countries > Region)
        for region_name, r_total in self.region_totals.items():
            c_sum = sum(
                c_total
                for c_code, c_total in self.country_totals.items()
                if _CODE_TO_REGION.get(c_code) == region_name
            )
            if c_sum > r_total * 1.05:
                self.resolution_log.append(
                    f"Contradiction (Hierarchy): Sum of countries in {region_name} ({c_sum}) exceeds region total ({r_total})"
                )

    def _dedupe_country_entries(self, entries: List[Entry]) -> List[Entry]:
        """
        Keep one strongest country entry per country key to avoid duplicate
        country-level processing in metrics/provenance.
        """
        by_key: Dict[str, Entry] = {}
        for e in entries:
            key = str(e.key)
            curr = by_key.get(key)
            if curr is None:
                by_key[key] = e
                continue

            def _score(x: Entry) -> Tuple[int, int, int, int, int, int, float]:
                return (
                    1 if x.covered_count is not None else 0,
                    1 if x.not_covered_count is not None else 0,
                    1 if x.percentage is not None else 0,
                    1 if x.total_count is not None else 0,
                    1 if x.is_explicit else 0,
                    1 if x.sent_idx != -1 else 0,
                    float(x.total_count or 0.0),
                )

            if _score(e) > _score(curr):
                by_key[key] = e

        return list(by_key.values())

    def validate(self):
        """
        Validates and repairs entries to ensure logical consistency.
        """
        for e in self.entries:
            if e.total_count is not None:
                # 1. Check Covered vs Total
                if e.covered_count is not None and e.covered_count > e.total_count:
                    self.resolution_log.append(
                        f"Validation: Bumped total for {e.key} from {e.total_count} to {e.covered_count} (Covered > Total)"
                    )
                    e.total_count = e.covered_count

                # 1. Check not Covered vs Total
                if (
                    e.not_covered_count is not None
                    and e.not_covered_count > e.total_count
                ):
                    self.resolution_log.append(
                        f"Validation: Bumped total for {e.key} from {e.total_count} to {e.not_covered_count} (Not Covered > Total)"
                    )
                    e.total_count = e.not_covered_count

                # 2. Check Sum of Parts vs Total
                parts_sum = (e.covered_count or 0.0) + (e.not_covered_count or 0.0)
                if parts_sum > e.total_count * 1.02:
                    self.resolution_log.append(
                        f"Validation: Bumped total for {e.key} from {e.total_count} to {parts_sum} (Parts > Total)"
                    )
                    e.total_count = parts_sum

    def calculate_metrics(self) -> Dict[str, Any]:
        # Keep a reporting baseline for domestic mention tracking without
        # seeding geography resolution.
        if self.domestic_country_code:
            self.country_keywords.setdefault(self.domestic_country_code, {})

        metrics = {
            "likely_percentage": None,
            "secondary_percentage": None,
            "derived_regional_coverage": {},
            "global_covered_count": 0.0,
            "global_total_count": 0.0,
            "measured_population_coverage": None,
            "country_keywords": self.country_keywords,
            "country_table_keywords": {
                code: sorted(list(terms))
                for code, terms in self.country_table_keywords.items()
                if terms
            },
            "global_table_keywords": sorted(list(self.global_table_keywords)),
            "domestic_country_code": self.domestic_country_code,
            "domestic_geo_explicitly_mentioned": (
                self.domestic_country_code in self.mentioned_countries
                if self.domestic_country_code
                else False
            ),
            "_logs": [],  # New key to store logs
            "resolution": self.resolution_log,
            "census": self.census_log,
        }

        # Ensure data consistency before calculation
        self.validate()

        def log(message: str):
            """Helper function to append logs to the metrics dict"""
            metrics["_logs"].append(message)

        def combine_pure_percentages(
            percentages: List[float], approx_tol: float = 2.0
        ) -> Tuple[Optional[float], str]:
            """
            Combine explicit standalone percentages with anti-double-count safeguards.
            Preference:
            1) If largest ~= sum(smaller), treat largest as roll-up total.
            2) Else if additive sum <= 100, use additive sum.
            3) Else fallback to unweighted average.
            """
            vals = [float(p) for p in percentages if p is not None]
            vals = [p for p in vals if 0.0 <= p <= 100.0]
            if not vals:
                return None, "none"
            if len(vals) == 1:
                return vals[0], "single"

            vals_sorted = sorted(vals, reverse=True)
            largest = vals_sorted[0]
            smaller_sum = sum(vals_sorted[1:])
            total_sum = sum(vals_sorted)

            if abs(largest - smaller_sum) <= approx_tol:
                return largest, "largest_matches_sum_smaller"
            if total_sum <= 100.0 + 1e-9:
                return total_sum, "additive_sum"
            return (sum(vals) / len(vals)), "average_fallback"

        log("=" * 80)
        log("STARTING METRICS CALCULATION (BOTTOM-UP PRIORITY)")
        log("=" * 80)

        # 1. Aggregate Regions
        log("\n[STEP 1] Aggregating Regions...")
        region_results = {}

        for region in Region:
            r_name = region.value
            if r_name in IGNORED_REGIONS:
                log(f"  ⊘ Skipping 'Unknown'/'Aggregate'/'Global' region")
                continue

            log(f"\n  Processing Region: {r_name}")

            # [A] Calculate Bottom-Up Aggregation (Countries)
            c_agg_covered = 0.0
            c_agg_total = 0.0
            c_has_data = False
            region_pure_pcts = []  # Store percentages found without counts

            log(f"    [A] Aggregating country-level entries for {r_name}...")
            c_entries = [
                e
                for e in self.entries
                if e.scope == Scope.COUNTRY and _CODE_TO_REGION.get(e.key) == r_name
            ]
            c_entries = self._dedupe_country_entries(c_entries)
            log(f"      Found {len(c_entries)} country entries")

            # Find countries implied by segments that don't have explicit entries
            existing_codes = {e.key for e in c_entries}
            segment_entries = [e for e in self.entries if e.scope == Scope.SEGMENT]
            for s in segment_entries:
                code = self._segment_anchor_code(s.key)
                if (
                    code
                    and code not in existing_codes
                    and _CODE_TO_REGION.get(code) == r_name
                ):
                    # Create a dummy entry for iteration
                    dummy = Entry(scope=Scope.COUNTRY, key=code)
                    c_entries.append(dummy)
                    existing_codes.add(code)

            # Filter out entries that are contained in other present entries to avoid double counting
            entries_to_skip = set()
            for e1 in c_entries:
                for e2 in c_entries:
                    if e1 is e2:
                        continue
                    if e2.key and e1.key and self._is_contained(e2.key, e1.key):
                        e2key = e2.key.split("::")[0]
                        e1key = e1.key.split("::")[0]
                        # Do not double count composites
                        if e2key in COMPOSITE_COUNTRIES and e1key in set(
                            get_composite_constituents(e2key)
                        ):
                            entries_to_skip.add(e2)
                        # Remove the region if composite is present
                        if e1key in COMPOSITE_COUNTRIES and e2key in REGION_CODES:
                            entries_to_skip.add(e2)
                        if e1key in REGION_CODES and e2key in COMPOSITE_COUNTRIES:
                            entries_to_skip.add(e1)
                        break
            for c in c_entries:
                if c in entries_to_skip:
                    log(
                        f"        ⊘ Skipping {c.key} (Contained in {next(e.key for e in c_entries if self._is_contained(e.key, c.key))})"
                    )
                    continue

                log(f"        Processing country: {c.key}")
                c_cov = 0.0
                c_tot = 0.0
                c_has_local_data = False
                c_pct_only = None
                segs = [
                    s
                    for s in self.entries
                    if s.scope == Scope.SEGMENT
                    and self._segment_matches_country(s.key, str(c.key))
                ]
                has_segment_counts = any(
                    (s.covered_count is not None) or (s.total_count is not None)
                    for s in segs
                )

                if c.covered_count is not None:
                    c_cov = c.covered_count
                    c_tot = c.total_count if c.total_count else 0.0
                    c_has_local_data = True
                    log(f"          → Using covered_count: {c_cov}/{c_tot}")
                elif c.percentage is not None and c.total_count:
                    c_cov = (c.percentage / 100.0) * c.total_count
                    c_tot = c.total_count
                    c_has_local_data = True
                    log(
                        f"          → Calculated from percentage: {c.percentage}% of {c_tot} = {c_cov}"
                    )

                # If country-level data looks like a zero/default placeholder but we have
                # segment-level quantitative data, prefer segments.
                if c_has_local_data and has_segment_counts:
                    seg_cov_preview = sum(
                        s.covered_count for s in segs if s.covered_count is not None
                    )
                    seg_tot_preview = sum(
                        s.total_count for s in segs if s.total_count is not None
                    )
                    if c_cov == 0 and (seg_cov_preview > 0 or seg_tot_preview > 0):
                        c_has_local_data = False
                        c_cov = 0.0
                        c_tot = 0.0
                        log(
                            "          → Country-level zero overridden by segment-level data"
                        )

                # Check Segments for this country
                if not c_has_local_data:
                    log(f"          → Checking segments for {c.key}...")
                    log(f"            Found {len(segs)} segments")
                    if segs:
                        seg_cov = sum(
                            s.covered_count for s in segs if s.covered_count is not None
                        )
                        seg_tot = (
                            c.total_count
                            if c.total_count
                            else sum(s.total_count for s in segs if s.total_count)
                        )

                        if seg_cov > 0 or seg_tot > 0:
                            c_cov = seg_cov
                            c_tot = seg_tot
                            c_has_local_data = True
                            log(
                                f"            → Aggregated segments: {seg_cov}/{seg_tot}"
                            )

                    # Fallback: Check for Segment Percentages if no counts
                    if not c_has_local_data and segs:
                        valid_seg_pcts = [
                            s.percentage for s in segs if s.percentage is not None
                        ]
                        if valid_seg_pcts:
                            c_pct_only, combine_mode = combine_pure_percentages(
                                valid_seg_pcts
                            )
                            if c_pct_only is not None:
                                if combine_mode == "single":
                                    log(
                                        f"            → Found segment percentage: {c_pct_only}%"
                                    )
                                elif combine_mode == "largest_matches_sum_smaller":
                                    log(
                                        f"            → Using largest segment percent as roll-up total: {c_pct_only:.2f}% (largest≈sum(smaller))"
                                    )
                                elif combine_mode == "additive_sum":
                                    log(
                                        f"            → Summed segment percentages: {c_pct_only:.2f}% (<=100 additive)"
                                    )
                                else:
                                    log(
                                        f"            → Found avg segment percentage: {c_pct_only:.2f}% (fallback)"
                                    )

                # If still no local data (counts), check if country itself has percentage
                if not c_has_local_data and c_pct_only is None:
                    if c.percentage is not None:
                        c_pct_only = c.percentage
                        log(f"          → Found country percentage: {c_pct_only}%")

                if c_has_local_data:
                    c_agg_covered += c_cov
                    c_agg_total += c_tot
                    c_has_data = True
                    log(
                        f"          ✓ Added to bottom-up total. Sum now: {c_agg_covered}/{c_agg_total}"
                    )
                elif c_pct_only is not None:
                    region_pure_pcts.append(c_pct_only)

            # [B] Check Region-Level Entry
            log(f"    [B] Checking region-level entry...")
            r_entry = next(
                (
                    e
                    for e in self.entries
                    if e.scope == Scope.REGION and e.key == r_name
                ),
                None,
            )

            r_covered = 0.0
            r_total = 0.0
            has_data = False

            # [C] Reconcile Bottom-Up vs Top-Down
            use_regional = False

            if r_entry and (
                r_entry.covered_count is not None or r_entry.percentage is not None
            ):
                log(f"      ✓ Found region entry: {r_entry.key}")

                # Extract Regional Data
                td_covered = 0.0
                td_total = 0.0
                td_has_data = False

                if r_entry.covered_count is not None:
                    td_covered = r_entry.covered_count
                    td_total = r_entry.total_count if r_entry.total_count else 0.0
                    td_has_data = True
                elif r_entry.percentage is not None and r_entry.total_count:
                    td_covered = (r_entry.percentage / 100.0) * r_entry.total_count
                    td_total = r_entry.total_count
                    td_has_data = True

                # Decision Logic
                if td_has_data:
                    # If Bottom-Up Total is significantly larger than Regional Total, prefer Bottom-Up
                    # (Implies Region entry is partial or outdated, while countries are specific)
                    if c_has_data and c_agg_total > td_total * 1.05:
                        log(
                            f"      ⚠ Contradiction: Sum of Countries ({c_agg_total}) > Region Total ({td_total}). Using Bottom-Up."
                        )
                        use_regional = False
                    else:
                        use_regional = True
                        r_covered = td_covered
                        r_total = td_total
                        has_data = True
                        log(
                            f"      → Using Regional Entry (Preferred): {r_covered}/{r_total}"
                        )
                elif r_entry.percentage is not None:
                    # Store percentage if we have no other data
                    metrics["derived_regional_coverage"][r_name] = r_entry.percentage
                    log(
                        f"      → Stored percentage only (no total): {r_entry.percentage}%"
                    )
            else:
                log(f"      ✗ No region-level entry found")

            # If not using regional (either didn't exist, or was contradicted), use Bottom-Up
            if not use_regional and c_has_data:
                r_covered = c_agg_covered
                r_total = c_agg_total
                has_data = True
                log(f"      → Using Bottom-Up Aggregation: {r_covered}/{r_total}")

            # Try to derive region percentage from pure percentages if no counts found
            if not has_data and region_pure_pcts:
                combined_pct, combine_mode = combine_pure_percentages(region_pure_pcts)
                if combined_pct is not None:
                    metrics["derived_regional_coverage"][r_name] = round(
                        combined_pct, 2
                    )
                    if combine_mode == "largest_matches_sum_smaller":
                        log(
                            f"    ✓ Derived region {r_name} percentage using largest roll-up percent: {combined_pct:.2f}% (largest≈sum(smaller))"
                        )
                    elif combine_mode == "additive_sum":
                        log(
                            f"    ✓ Derived region {r_name} percentage from additive sum of {len(region_pure_pcts)} entries: {combined_pct:.2f}%"
                        )
                    elif combine_mode == "single":
                        log(
                            f"    ✓ Derived region {r_name} percentage from single entry: {combined_pct:.2f}%"
                        )
                    else:
                        log(
                            f"    ✓ Derived region {r_name} percentage from unweighted average of {len(region_pure_pcts)} entries: {combined_pct:.2f}%"
                        )

            # C. Update Metrics
            if has_data:
                region_results[r_name] = {"covered": r_covered, "total": r_total}
                log(f"    ✓ Region {r_name} data: {r_covered}/{r_total}")

                if r_name not in metrics["derived_regional_coverage"] and r_total > 0:
                    regional_pct = round((r_covered / r_total) * 100.0, 2)
                    metrics["derived_regional_coverage"][r_name] = regional_pct
                    log(f"      → Stored in derived_regional_coverage: {regional_pct}%")
            else:
                log(f"    ✗ No data found for region {r_name}")

        # Resolve Overlaps (International vs Specific Regions)
        # 1. Identify Domestic Region
        domestic_region_name = None
        if self.domestic_country_code:
            domestic_region_name = _CODE_TO_REGION.get(self.domestic_country_code)

        # 2. Partition Regions
        dom_region_res = {"covered": 0.0, "total": 0.0}
        sum_rest_covered = 0.0
        sum_rest_total = 0.0
        sum_specific_total = 0.0
        sum_specific_covered = 0.0

        for r_name, res in region_results.items():
            if r_name in IGNORED_REGIONS:
                continue

            sum_specific_total += res["total"]
            sum_specific_covered += res["covered"]

            if r_name == domestic_region_name:
                dom_region_res = res
            else:
                sum_rest_total += res["total"]
                sum_rest_covered += res["covered"]

        intl_res = region_results.get(
            Region.INTERNATIONAL.value, {"covered": 0.0, "total": 0.0}
        )

        # 3. Determine if International is Global
        is_intl_global = False
        if intl_res["total"] > 0:
            # A. Matches explicit Global Total
            if self.global_total > 0 and self._matches_census(
                intl_res["total"], self.global_total, threshold=0.10
            ):
                is_intl_global = True
            # B. Heuristic: Much larger than Rest AND close to Total Specifics
            elif intl_res["total"] > (sum_rest_total * 1.5) and self._matches_census(
                intl_res["total"], sum_specific_total, threshold=0.20
            ):
                is_intl_global = True

        if is_intl_global:
            if intl_res["total"] >= sum_specific_total:
                bottom_up_total = intl_res["total"]
                bottom_up_covered = intl_res["covered"]
                log(
                    f"    ℹ International ({intl_res['total']}) identified as Global and >= Sum of Specifics ({sum_specific_total}). Using International."
                )
            else:
                bottom_up_total = sum_specific_total
                bottom_up_covered = sum_specific_covered
                log(
                    f"    ℹ International ({intl_res['total']}) identified as Global but < Sum of Specifics ({sum_specific_total}). Using Specifics."
                )
        else:
            # International is Non-Domestic
            if intl_res["total"] > sum_rest_total:
                non_dom_total = intl_res["total"]
                non_dom_covered = intl_res["covered"]
                log(
                    f"    ℹ International ({intl_res['total']}) > Sum of Rest ({sum_rest_total}). Using International as Non-Domestic."
                )
            else:
                non_dom_total = sum_rest_total
                non_dom_covered = sum_rest_covered
                if intl_res["total"] > 0:
                    log(
                        f"    ℹ Sum of Rest ({sum_rest_total}) >= International ({intl_res['total']}). Using Rest Specifics."
                    )
                    if (
                        Region.INTERNATIONAL.value
                        in metrics["derived_regional_coverage"]
                    ):
                        del metrics["derived_regional_coverage"][
                            Region.INTERNATIONAL.value
                        ]
                        log(
                            "      ⊘ Dropped International from derived metrics (Redundant)"
                        )

            bottom_up_total = dom_region_res["total"] + non_dom_total
            bottom_up_covered = dom_region_res["covered"] + non_dom_covered

        # Add Domestic (should be 0 if routed to US/NA, but add if present as distinct region)
        dom_res = region_results.get(
            Region.DOMESTIC.value, {"covered": 0.0, "total": 0.0}
        )
        bottom_up_total += dom_res["total"]
        bottom_up_covered += dom_res["covered"]

        # 2. Check for Explicit Global Entry (AFTER bottom-up)
        log("\n[STEP 2] Checking for Explicit Global Entry...")
        global_entry = next(
            (
                e
                for e in self.entries
                if e.scope == Scope.GLOBAL
                or (e.key and (e.key.split("::")[0] in GLOBAL_SET))
            ),
            None,
        )

        global_entry_percentage = None
        global_entry_counts = (None, None)

        if global_entry:
            log(f"  ✓ Found global entry: {global_entry}")
            if global_entry.percentage is not None:
                global_entry_percentage = global_entry.percentage
                log(f"    → Found explicit percentage: {global_entry.percentage}%")
            if global_entry.covered_count is not None and global_entry.total_count:
                global_entry_counts = (
                    global_entry.covered_count,
                    global_entry.total_count,
                )
                log(
                    f"    → Found explicit counts: {global_entry.covered_count}/{global_entry.total_count}"
                )
        else:
            log("  ✗ No global entry found")

        # 3. Finalize Global Metrics
        log("\n[STEP 3] Finalizing Global Metrics...")
        metrics["global_covered_count"] = bottom_up_covered
        metrics["global_total_count"] = bottom_up_total

        if self.global_total > 0:
            metrics["measured_population_coverage"] = round(
                (bottom_up_total / self.global_total) * 100.0, 2
            )
            log(
                f"  Measured population coverage: {metrics['measured_population_coverage']}% ({bottom_up_total}/{self.global_total})"
            )

        log(f"  Bottom-up aggregated totals: {bottom_up_covered}/{bottom_up_total}")

        # Priority: Bottom-up > Explicit Global Entry
        if bottom_up_total > 0:
            # We have bottom-up data, use it
            metrics["likely_percentage"] = round(
                (bottom_up_covered / bottom_up_total) * 100.0, 2
            )
            log(
                f"  ✓ Using bottom-up data: {metrics['likely_percentage']}% ({bottom_up_covered}/{bottom_up_total})"
            )

            # If explicit global provides different denominator, calculate alternative
            if global_entry_counts[1] and global_entry_counts[1] != bottom_up_total:
                metrics["secondary_percentage"] = round(
                    (bottom_up_covered / global_entry_counts[1]) * 100.0, 2
                )
                log(
                    f"    → Alternative calculation with explicit global total: {metrics['secondary_percentage']}% ({bottom_up_covered}/{global_entry_counts[1]})"
                )
        elif global_entry_percentage is not None:
            # Fall back to explicit global percentage if no bottom-up data
            metrics["likely_percentage"] = global_entry_percentage
            log(f"  ✓ Using explicit global percentage: {global_entry_percentage}%")
        elif global_entry_counts[0] is not None and global_entry_counts[1]:
            # Fall back to explicit global counts if no bottom-up data
            metrics["likely_percentage"] = round(
                (global_entry_counts[0] / global_entry_counts[1]) * 100.0, 2
            )
            log(
                f"  ✓ Using explicit global counts: {metrics['likely_percentage']}% ({global_entry_counts[0]}/{global_entry_counts[1]})"
            )
        else:
            log(f"  ✗ No data available (neither bottom-up nor explicit global)")

        if metrics["likely_percentage"] is None and self.global_total > 0:
            metrics["likely_percentage"] = round(
                (bottom_up_covered / self.global_total) * 100.0, 2
            )
            log(
                f"  ✓ Calculated using self.global_total: {metrics['likely_percentage']}%"
            )

        # 4. Fallback: No counts found, check derived regional data
        if metrics["likely_percentage"] is None and bottom_up_total == 0:
            # A. Prefer International/Global region if available
            if Region.INTERNATIONAL.value in metrics["derived_regional_coverage"]:
                metrics["likely_percentage"] = metrics["derived_regional_coverage"][
                    Region.INTERNATIONAL.value
                ]
                log(
                    f"  ✓ Fallback: Using International regional percentage: {metrics['likely_percentage']}%"
                )

            # B. If only one region exists (e.g. Domestic/US), assume it represents the whole
            elif len(metrics["derived_regional_coverage"]) == 1:
                r_name = list(metrics["derived_regional_coverage"].keys())[0]
                metrics["likely_percentage"] = metrics["derived_regional_coverage"][
                    r_name
                ]
                log(
                    f"  ✓ Fallback: Using single region ({r_name}) percentage: {metrics['likely_percentage']}%"
                )

        # [STEP 4] Derive International Coverage (Residual)
        # Calculate Domestic and derive International (Global - Domestic)
        intl_key = Region.INTERNATIONAL.value
        dom_key = Region.DOMESTIC.value

        if (
            intl_key not in metrics["derived_regional_coverage"]
            or dom_key not in metrics["derived_regional_coverage"]
        ):
            log("\n[STEP 4] Calculating Domestic & International Metrics...")

            # 1. Calculate Domestic Data (Aggregated)
            dom_covered = 0.0
            dom_total = 0.0
            dom_found = False
            target_dom_code = self.domestic_country_code

            # A. Check Country Entry
            c_entry = next(
                (
                    e
                    for e in self.entries
                    if e.scope == Scope.COUNTRY and e.key == target_dom_code
                ),
                None,
            )
            if c_entry and (
                c_entry.covered_count is not None or c_entry.percentage is not None
            ):
                if c_entry.covered_count is not None:
                    dom_covered = c_entry.covered_count
                    dom_total = c_entry.total_count or 0.0
                    dom_found = True
                elif c_entry.percentage is not None and c_entry.total_count:
                    dom_covered = (c_entry.percentage / 100.0) * c_entry.total_count
                    dom_total = c_entry.total_count
                    dom_found = True

            # B. Check Segments (if no country data found)
            if not dom_found:
                segs = [
                    s
                    for s in self.entries
                    if s.scope == Scope.SEGMENT
                    and s.key
                    and s.key.startswith(f"{target_dom_code}::")
                ]
                if segs:
                    seg_cov = sum(s.covered_count for s in segs if s.covered_count)
                    seg_tot = sum(s.total_count for s in segs if s.total_count)
                    # If country entry exists but has no coverage data, use its total if larger
                    if c_entry and c_entry.total_count:
                        seg_tot = max(seg_tot, c_entry.total_count)

                    if seg_cov > 0 or seg_tot > 0:
                        dom_covered = seg_cov
                        dom_total = seg_tot
                        dom_found = True

            # 2. Identify Global Data
            glob_covered = None
            glob_total = None

            if global_entry:
                if global_entry.covered_count is not None:
                    glob_covered = global_entry.covered_count
                elif global_entry.percentage is not None and global_entry.total_count:
                    glob_covered = (
                        global_entry.percentage / 100.0
                    ) * global_entry.total_count
                glob_total = global_entry.total_count

            # Fallback to bottom-up / census
            if glob_covered is None:
                glob_covered = bottom_up_covered
            if glob_total is None or glob_total == 0:
                glob_total = (
                    self.global_total if self.global_total > 0 else bottom_up_total
                )

            # 3. Store Domestic & Calculate Residual
            if dom_found and dom_total > 0:
                dom_pct = round((dom_covered / dom_total) * 100.0, 2)
                metrics["derived_regional_coverage"][dom_key] = dom_pct
                log(
                    f"  ✓ Domestic ({target_dom_code}): {dom_pct}% ({dom_covered:.0f}/{dom_total:.0f})"
                )

            if dom_found and glob_total > 0:
                intl_covered = max(0.0, (glob_covered or 0.0) - dom_covered)
                intl_total = max(0.0, glob_total - dom_total)

                # Only proceed if we have a meaningful international population
                if intl_key not in metrics["derived_regional_coverage"]:
                    if intl_total > 0 and intl_total > (glob_total * 0.01):
                        intl_pct = round((intl_covered / intl_total) * 100.0, 2)
                        metrics["derived_regional_coverage"][intl_key] = intl_pct
                        log(
                            f"  ✓ Derived International: {intl_pct}% ({intl_covered:.0f}/{intl_total:.0f}) [Global ({glob_covered:.0f}/{glob_total:.0f}) - Domestic ({dom_covered:.0f}/{dom_total:.0f})]"
                        )
            else:
                log(
                    "  ✗ Cannot derive International: Missing Domestic data or Global Total"
                )

        # Ensure Global is in derived_regional_coverage with the final likely_percentage
        if metrics["likely_percentage"] is not None:
            metrics["derived_regional_coverage"]["Global"] = metrics[
                "likely_percentage"
            ]

        log("\n" + "=" * 80)
        log("FINAL METRICS:")
        log(f"  likely_percentage: {metrics['likely_percentage']}")
        log(f"  secondary_percentage: {metrics['secondary_percentage']}")
        log(
            f"  measured_population_coverage: {metrics['measured_population_coverage']}"
        )
        log(f"  global_covered_count: {metrics['global_covered_count']}")
        log(f"  global_total_count: {metrics['global_total_count']}")
        log(f"  derived_regional_coverage: {metrics['derived_regional_coverage']}")
        log("=" * 80)

        return metrics

    def build_country_provenance_report(
        self,
        suppressed_clause_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Builds a country-array report focused on final country totals plus
        method/source-type breakdowns, plus top-level aggregate provenance.
        """
        method_keys = [
            SourceType.EXPLICIT.value,
            SourceType.CALCULATED.value,
            SourceType.INFERRED.value,
            SourceType.WEIGHTED_DIVISION.value,
            SourceType.VIRTUAL_POOL.value,
            SourceType.FALLBACK.value,
            SourceType.INHERITED.value,
        ]

        def empty_bucket() -> Dict[str, Any]:
            return {
                "tot": None,
                "cov": None,
                "not_cov": None,
                "pct_vals": [],
                "n": 0,
            }

        def add_nullable(
            acc: Optional[float], value: Optional[float]
        ) -> Optional[float]:
            if value is None:
                return acc
            if acc is None:
                return float(value)
            return float(acc + value)

        def alloc_map_by_weights(
            total_val: Optional[float], weights: Dict[str, float]
        ) -> Dict[str, Optional[float]]:
            if total_val is None:
                return {k: None for k in weights}
            if not weights:
                return {}

            total_weight = sum(max(0.0, float(v)) for v in weights.values())
            if total_weight <= 0:
                n = len(weights)
                if n == 0:
                    return {}
                equal = float(total_val) / n
                return {k: equal for k in weights}

            raw = {
                k: float(total_val) * (max(0.0, float(w)) / total_weight)
                for k, w in weights.items()
            }
            is_integer_total = abs(float(total_val) - round(float(total_val))) < 1e-9
            if not is_integer_total:
                return {k: round(v, 2) for k, v in raw.items()}

            floor_vals = {k: int(v) for k, v in raw.items()}
            remainder = int(round(float(total_val))) - sum(floor_vals.values())
            ranked = sorted(
                raw.keys(),
                key=lambda k: (raw[k] - floor_vals[k]),
                reverse=True,
            )
            for k in ranked[: max(0, remainder)]:
                floor_vals[k] += 1
            return {k: float(v) for k, v in floor_vals.items()}

        def normalize_geo_code(
            raw: Any, region_name_to_code: Dict[str, str]
        ) -> Optional[str]:
            if not isinstance(raw, str):
                return None
            code = raw.strip()
            if not code:
                return None
            if code in IGNORED_REGIONS:
                return None
            if code in region_name_to_code:
                return region_name_to_code[code]
            if is_region(code):
                return code
            if re.fullmatch(r"[A-Z0-9_]{2,12}", code):
                return code
            return None

        def reduce_child_codes(
            child_codes: List[str],
            *,
            aggregate_key: Optional[str],
            region_name_to_code: Dict[str, str],
        ) -> List[str]:
            # Remove aggregate self-reference first.
            if aggregate_key:
                child_codes = [c for c in child_codes if c != aggregate_key]

            def is_concrete_child(code: str) -> bool:
                return (
                    code not in IGNORED_REGIONS
                    and code not in AGG_SET
                    and code not in DOMESTIC_SET
                    and not is_region(code)
                )

            filtered_children: List[str] = []
            for c in child_codes:
                is_container_like = (
                    is_region(c)
                    or c in region_name_to_code.values()
                    or c in COMPOSITE_REGION_MAP
                )
                if is_container_like:
                    has_concrete_descendant = any(
                        other != c
                        and is_concrete_child(other)
                        and is_contained(
                            container_key=c,
                            item_key=other,
                            domestic_country_code=self.domestic_country_code,
                        )
                        for other in child_codes
                    )
                    if has_concrete_descendant:
                        continue
                filtered_children.append(c)
            return filtered_children

        region_name_to_code: Dict[str, str] = {
            region_name: code for region_name, code in REGION_NAME_MAP.items()
        }
        # Add any additional region aliases/codes known by matcher tables.
        for r_code in REGION_CODES:
            if not is_region(r_code):
                continue
            r_name = _CODE_TO_REGION.get(r_code, r_code)
            if isinstance(r_name, str):
                region_name_to_code.setdefault(r_name, r_code)

        explicit_pct_by_code: Dict[str, List[float]] = {}
        explicit_pct_counts_by_code: Dict[str, Dict[str, Optional[float]]] = {}
        for e in self.explicit_pct_entries:
            code = normalize_geo_code(e.geo_code, region_name_to_code)
            if not code:
                continue
            explicit_pct_by_code.setdefault(code, []).append(float(e.percentage))
            if (
                e.derived_total is not None
                or e.derived_covered is not None
                or e.derived_not_covered is not None
            ):
                existing = explicit_pct_counts_by_code.get(code)
                candidate = {
                    "tot": e.derived_total,
                    "cov": e.derived_covered,
                    "not_cov": e.derived_not_covered,
                    "source": e.derived_source,
                }
                if existing is None:
                    explicit_pct_counts_by_code[code] = candidate
                else:
                    # Prefer the entry with the largest total; fall back to larger covered.
                    existing_total = existing.get("tot")
                    candidate_total = candidate.get("tot")
                    if (
                        candidate_total is not None
                        and (
                            existing_total is None
                            or candidate_total > existing_total
                        )
                    ):
                        explicit_pct_counts_by_code[code] = candidate
                    elif (
                        candidate_total is None
                        and existing_total is None
                        and candidate.get("cov") is not None
                        and (
                            existing.get("cov") is None
                            or candidate.get("cov") > existing.get("cov") # type: ignore
                        )
                    ):
                        explicit_pct_counts_by_code[code] = candidate
        pseudo_region_name_by_code = {
            code: region_name for region_name, code in REGION_NAME_MAP.items()
        }
        promoted_region_codes = set(REGION_NAME_MAP.values()) | set(
            COMPOSITE_REGION_MAP.keys()
        )
        pseudo_region_by_code: Dict[str, str] = {}
        aggregate_weighted_by_code: Dict[str, Dict[str, Any]] = {}

        suppressed_by_code: Dict[str, Dict[str, Dict[str, Any]]] = {}
        if suppressed_clause_items:
            suppress_priority = [
                SuppressedCountType.CONTRACT_CLAUSE.value,
                SuppressedCountType.LEGAL_PROCESS.value,
                SuppressedCountType.LEGAL_REQUIREMENT.value,
                SuppressedCountType.BOILERPLATE.value,
            ]

            def _pick_suppress_type(types: Optional[List[str]]) -> Optional[str]:
                if not types:
                    return None
                for t in suppress_priority:
                    if t in types:
                        return t
                return types[0]

            for item in suppressed_clause_items:
                geo = item.get("geographic_context", {})
                target_codes: List[str] = []
                for c in geo.get("countries", []) or []:
                    code = c.get("code")
                    if not code:
                        continue
                    if code == GeoCode.DOMESTIC.value:
                        code = self.domestic_country_code
                    target_codes.append(code)
                if not target_codes:
                    region_key = geo.get("region")
                    if region_key in DOMESTIC_SET:
                        target_codes.append(self.domestic_country_code)
                    elif region_key in INT_SET:
                        target_codes.append(GeoCode.INTERNATIONAL.value)
                    elif isinstance(region_key, str):
                        pseudo = self._region_to_pseudo_country_code(region_key)
                        if pseudo:
                            target_codes.append(pseudo)
                    if geo.get("domestic_negated") and not target_codes:
                        target_codes.append(GeoCode.INTERNATIONAL.value)

                if not target_codes:
                    continue

                suppress_type = _pick_suppress_type(item.get("suppress_types"))
                if not suppress_type:
                    continue

                pct_vals = [float(p) for p in (item.get("percentages") or [])]
                counts = item.get("worker_counts") or item.get("numbers") or []
                count_total = sum(float(c) for c in counts) if counts else 0.0
                count_n = len(counts)
                bu_counts = item.get("bargaining_unit_counts") or []
                bu_total = sum(float(b) for b in bu_counts) if bu_counts else 0.0
                has_values = bool(count_total or pct_vals or bu_total)
                if not has_values:
                    continue

                for code in target_codes:
                    by_type = suppressed_by_code.setdefault(code, {})
                    bucket = by_type.setdefault(
                        suppress_type,
                        {
                            "tot": 0.0,
                            "pct_vals": [],
                            "bu": 0.0,
                            "n": 0,
                        },
                    )
                    if count_total:
                        bucket["tot"] += count_total
                    if pct_vals:
                        bucket["pct_vals"].extend(pct_vals)
                    if bu_total:
                        bucket["bu"] += bu_total
                    bucket["n"] += 1

        explicit_country_codes: set[str] = (
            set(self.country_totals.keys())
            | set(self.country_keywords.keys())
            | set(suppressed_by_code.keys())
        )
        for e in self.entries:
            if e.scope == Scope.COUNTRY and isinstance(e.key, str):
                if (
                    e.key not in REGION_CODES and e.key not in IGNORED_REGIONS
                ) or e.key in promoted_region_codes:
                    explicit_country_codes.add(e.key)
            elif e.scope == Scope.SEGMENT and isinstance(e.key, str) and "::" in e.key:
                c_code = self._segment_anchor_code(e.key)
                if not c_code:
                    continue
                if (
                    c_code not in REGION_CODES and c_code not in IGNORED_REGIONS
                ) or c_code in promoted_region_codes:
                    explicit_country_codes.add(c_code)

        def has_region_children(region_name: str) -> bool:
            region_code = region_name_to_code.get(region_name, region_name)
            candidate_codes: set[str] = set(explicit_country_codes) | set(
                self.country_totals.keys()
            )

            for c in candidate_codes:
                if (
                    c == region_code
                    or c in IGNORED_REGIONS
                    or c in AGG_SET
                    or c in DOMESTIC_SET
                ):
                    continue
                if is_contained(
                    container_key=region_code,
                    item_key=c,
                    domestic_country_code=self.domestic_country_code,
                ):
                    return True
            return False

        # Collect country codes from explicit country totals, keywords, and entries.
        country_codes: set[str] = set(explicit_country_codes)
        for e in self.entries:
            if e.scope != Scope.REGION or not isinstance(e.key, str):
                continue
            region_name = _CODE_TO_REGION.get(e.key, e.key)
            if region_name in REGION_NAME_MAP:
                # Always add region to country_codes if it has explicit data,
                # even if it has children. Subtraction logic will handle residuals.
                if e.total_count is not None or e.covered_count is not None or e.percentage is not None:
                    p_code = REGION_NAME_MAP[region_name]
                    country_codes.add(p_code)
                    pseudo_region_by_code[p_code] = region_name
                elif not has_region_children(region_name):
                    # Only add childless regions without explicit data
                    p_code = REGION_NAME_MAP[region_name]
                    country_codes.add(p_code)
                    pseudo_region_by_code[p_code] = region_name

        # Precompute weighted allocations from aggregate parents for country-level
        # method breakdown seeding/reclassification.
        for e in self.entries:
            is_aggregate_parent = e.scope == Scope.AGGREGATE or (
                e.scope == Scope.REGION and e.key in AGG_SET
            )
            if not is_aggregate_parent or not e.related_geo_codes:
                continue
            if getattr(e, "_single_child_explicit_applied", False):
                # Avoid weighted-division seeding when aggregate was collapsed
                # into a single explicit child.
                continue

            aggregate_key = e.key if isinstance(e.key, str) else None
            if isinstance(aggregate_key, str):
                if aggregate_key in AGG_SET:
                    aggregate_key = GeoCode.AGGREGATE.value
                elif aggregate_key in region_name_to_code:
                    aggregate_key = region_name_to_code[aggregate_key]
                elif is_region(aggregate_key):
                    aggregate_key = aggregate_key

            child_codes: List[str] = []
            for raw_code in e.related_geo_codes:
                normalized = normalize_geo_code(raw_code, region_name_to_code)
                if normalized and normalized not in child_codes:
                    child_codes.append(normalized)
            child_codes = reduce_child_codes(
                child_codes,
                aggregate_key=aggregate_key if isinstance(aggregate_key, str) else None,
                region_name_to_code=region_name_to_code,
            )
            if not child_codes:
                continue

            child_weights = {
                c: float(self.country_totals.get(c, 0.0) or 0.0) for c in child_codes
            }
            alloc_total = alloc_map_by_weights(e.total_count, child_weights)
            alloc_covered = alloc_map_by_weights(e.covered_count, child_weights)
            alloc_not_covered = alloc_map_by_weights(e.not_covered_count, child_weights)

            for c in child_codes:
                bucket = aggregate_weighted_by_code.setdefault(
                    c,
                    {
                        "tot": None,
                        "cov": None,
                        "not_cov": None,
                        "pct_vals": [],
                        "n": 0,
                    },
                )
                c_total = alloc_total.get(c)
                c_cov = alloc_covered.get(c)
                c_not = alloc_not_covered.get(c)
                bucket["tot"] = add_nullable(bucket["tot"], c_total)
                bucket["cov"] = add_nullable(bucket["cov"], c_cov)
                bucket["not_cov"] = add_nullable(bucket["not_cov"], c_not)
                if c_total is not None and c_cov is not None and c_total > 0:
                    bucket["pct_vals"].append(
                        round((float(c_cov) / float(c_total)) * 100.0, 2)
                    )
                elif e.percentage is not None:
                    bucket["pct_vals"].append(float(e.percentage))
                bucket["n"] += 1

        countries = []

        def entry_union_indicator(entry: Entry) -> Optional[int]:
            if entry.covered_count is not None and entry.covered_count > 0:
                return 1
            if (
                (entry.covered_count is not None and entry.covered_count == 0)
                or (entry.percentage is not None and entry.percentage == 0)
                or (
                    entry.not_covered_count is not None
                    and entry.not_covered_count > 0
                    and not entry.covered_count
                )
            ):
                return 0
            return None

        def fallback_union_indicator(code: str) -> Optional[int]:
            # 1) Region/composite/international containers
            container_indicators = []
            for e in self.entries:
                if not isinstance(e.key, str):
                    continue
                if e.scope not in (Scope.REGION, Scope.AGGREGATE, Scope.COUNTRY):
                    continue
                container_key = e.key.split("::")[0]
                if container_key in GLOBAL_SET:
                    continue
                if not is_contained(
                    container_key=container_key,
                    item_key=code,
                    domestic_country_code=self.domestic_country_code,
                ):
                    continue
                ind = entry_union_indicator(e)
                if ind is not None:
                    container_indicators.append(ind)

            if 0 in container_indicators:
                return 0
            if 1 in container_indicators:
                return 1

            # 2) Global fallback
            for e in self.entries:
                if e.scope == Scope.GLOBAL or (
                    isinstance(e.key, str) and e.key.split("::")[0] in GLOBAL_SET
                ):
                    ind = entry_union_indicator(e)
                    if ind is not None:
                        return ind
            return None

        def build_country_output(
            code: str,
            total_val: Optional[float],
            covered_val: Optional[float],
            not_covered_val: Optional[float],
            pct_val: Optional[float],
            country_entries: List[Entry],
            segment_entries: List[Entry],
            weighted_seed: Optional[Dict[str, Any]],
            country_keywords: Optional[Dict[str, Any]] = None,
            country_table_keywords: Optional[List[str]] = None,
            suppressed_items: Optional[Dict[str, Dict[str, Any]]] = None,
            language_fallback: bool = False,
            fallback_union_indicator: Optional[int] = None,
        ) -> Dict[str, Any]:
            method_breakdown = {k: empty_bucket() for k in method_keys}
            explicit_pct_present = False
            explicit_pct_vals = explicit_pct_by_code.get(code, [])
            if explicit_pct_vals:
                explicit_bucket = method_breakdown[SourceType.EXPLICIT.value]
                explicit_pct_present = True
            for e in country_entries + segment_entries:
                field_sources = [
                    ("tot", e.total_count, e.total_count_source_type),
                    ("cov", e.covered_count, e.covered_count_source_type),
                    ("not_cov", e.not_covered_count, e.not_covered_count_source_type),
                    ("pct_vals", e.percentage, e.percentage_source_type),
                ]

                used_bucket_keys = set()
                for field_name, val, stype in field_sources:
                    # Aggregate-propagated values are weighted split provenance.
                    if stype == SourceType.CALCULATED.value:
                        is_weighted_from_agg = False
                        if (
                            field_name == "pct_vals"
                            and e.percentage_source
                            == PercentageSourceDetail.AGGREGATE_PROPAGATION.value
                        ):
                            is_weighted_from_agg = True
                        elif (
                            field_name
                            in (
                                "cov",
                                "not_cov",
                            )
                            and e.percentage_source
                            == PercentageSourceDetail.AGGREGATE_PROPAGATION.value
                            and (
                                e.covered_count_source
                                == CountSourceDetail.CALCULATED_FROM_PERCENTAGE_AND_TOTAL.value
                                or e.not_covered_count_source
                                == CountSourceDetail.CALCULATED_FROM_TOTAL_MINUS_COVERED.value
                            )
                        ):
                            is_weighted_from_agg = True
                        if is_weighted_from_agg:
                            stype = SourceType.WEIGHTED_DIVISION.value
                        else:
                            # Reclassify calculated covered/not_covered parts as FALLBACK
                            # when their denominator provenance is fallback-based.
                            if field_name in ("cov", "not_cov"):
                                fallback_denom = (
                                    e.total_count_source_type
                                    == SourceType.FALLBACK.value
                                    or e.denominator_source_type
                                    == SourceType.FALLBACK.value
                                )
                                if fallback_denom:
                                    stype = SourceType.FALLBACK.value

                    # Virtual pool is a global-mode fallback. When active, reclassify
                    # downstream fallback/calculated derivatives to VIRTUAL_POOL.
                    if self.is_using_virtual and stype in (
                        SourceType.FALLBACK.value,
                        SourceType.CALCULATED.value,
                    ):
                        denom_linked = e.total_count_source_type in (
                            SourceType.VIRTUAL_POOL.value,
                            SourceType.FALLBACK.value,
                        ) or e.denominator_source_type in (
                            SourceType.VIRTUAL_POOL.value,
                            SourceType.FALLBACK.value,
                        )
                        if denom_linked:
                            stype = SourceType.VIRTUAL_POOL.value

                    if stype not in method_breakdown:
                        continue
                    bucket = method_breakdown[stype]
                    used_bucket_keys.add(stype)
                    if field_name == "pct_vals":
                        if val is not None:
                            bucket["pct_vals"].append(float(val))
                    else:
                        bucket[field_name] = add_nullable(bucket[field_name], val)
                for k in used_bucket_keys:
                    method_breakdown[k]["n"] += 1

            # Backfill weighted split method bucket from aggregate allocations
            # when this country/pseudo-country has no direct weighted entries.
            if weighted_seed:
                weighted_bucket = method_breakdown[SourceType.WEIGHTED_DIVISION.value]
                if weighted_bucket["n"] == 0:
                    for f in (
                        "tot",
                        "cov",
                        "not_cov",
                    ):
                        weighted_bucket[f] = add_nullable(
                            weighted_bucket[f], weighted_seed.get(f)
                        )
                    weighted_bucket["pct_vals"].extend(
                        weighted_seed.get("pct_vals", [])
                    )
                    weighted_bucket["n"] += int(weighted_seed.get("n") or 0)

            explicit_bucket = method_breakdown[SourceType.EXPLICIT.value]
            calculated_bucket = method_breakdown[SourceType.CALCULATED.value]
            explicit_pcts = explicit_bucket.get("pct_vals", [])
            reported_pct = None
            if explicit_pcts:
                vals = [float(p) for p in explicit_pcts if p is not None]
                vals = [p for p in vals if 0.0 <= p <= 100.0]
                if vals:
                    if len(vals) == 1:
                        reported_pct = vals[0]
                    else:
                        vals_sorted = sorted(vals, reverse=True)
                        largest = vals_sorted[0]
                        smaller_sum = sum(vals_sorted[1:])
                        total_sum = sum(vals_sorted)
                        if abs(largest - smaller_sum) <= 2.0:
                            reported_pct = largest
                        elif total_sum <= 100.0 + 1e-9:
                            reported_pct = total_sum
                        else:
                            reported_pct = sum(vals) / len(vals)
                    if reported_pct is not None:
                        reported_pct = round(reported_pct, 2)

            def _has_explicit_or_propagated_pct(entries: List[Entry]) -> bool:
                for ent in entries:
                    if ent.percentage is None:
                        continue
                    if ent.percentage_source in (
                        PercentageSourceDetail.EXPLICIT_PERCENTAGE.value,
                        PercentageSourceDetail.AGGREGATE_PROPAGATION.value,
                    ):
                        return True
                return False

            # If explicit pct exists for this code, avoid forcing a 0%/non-coverage
            # classification purely from inferred totals when no denominator-backed
            # covered/not-covered counts exist.
            if explicit_pct_present and total_val is not None:
                if (
                    (covered_val is None or covered_val == 0)
                    and not_covered_val is not None
                    and (pct_val is None or pct_val == 0)
                    and not_covered_val >= total_val
                ):
                    covered_val = None
                    not_covered_val = None
                    pct_val = None

            # Coverage-only indicator:
            # 1 => positive covered population
            # 0 => explicit non-coverage with no covered population
            if covered_val is not None and covered_val > 0:
                union_indicator = 1
            elif (
                (covered_val is not None and covered_val == 0)
                or (pct_val is not None and pct_val == 0)
                or (
                    not_covered_val is not None
                    and not_covered_val > 0
                    and not covered_val
                )
            ):
                union_indicator = 0
            else:
                has_pct_signal = (
                    (pct_val is not None and pct_val > 0) or explicit_pct_present
                )
                has_explicit_or_propagated = _has_explicit_or_propagated_pct(
                    country_entries + segment_entries
                )
                if explicit_pct_present:
                    has_explicit_or_propagated = True
                union_indicator = 1 if (has_pct_signal and has_explicit_or_propagated) else 0

            # If explicit pct exists but country pct is missing, surface the explicit pct
            # in country_totals without fabricating counts.
            if pct_val is None and explicit_pct_present and explicit_pct_vals:
                pct_val = max(explicit_pct_vals)

            explicit_non_coverage = (
                (covered_val is not None and covered_val == 0)
                or (pct_val is not None and pct_val == 0)
                or (
                    not_covered_val is not None
                    and not_covered_val > 0
                    and not covered_val
                )
            )

            has_country_keywords = False
            if country_keywords:
                has_country_keywords = any(
                    (v or 0) > 0 for v in country_keywords.values()
                )
            if country_table_keywords:
                has_country_keywords = True
            if has_country_keywords and not explicit_non_coverage:
                union_indicator = 1

            # Prune empty buckets to reduce verbosity
            def _bucket_has_signal(bucket: Dict[str, Any]) -> bool:
                return bool(
                    bucket.get("tot") is not None
                    or bucket.get("cov") is not None
                    or bucket.get("not_cov") is not None
                    or (bucket.get("pct_vals") or [])
                )

            for k in list(method_breakdown.keys()):
                bucket = method_breakdown.get(k)
                if not bucket:
                    continue
                if bucket.get("n", 0) == 0 or not _bucket_has_signal(bucket):
                    del method_breakdown[k]

            reported_totals = {
                "tot": add_nullable(explicit_bucket.get("tot"), calculated_bucket.get("tot")),
                "cov": add_nullable(explicit_bucket.get("cov"), calculated_bucket.get("cov")),
                "not_cov": add_nullable(explicit_bucket.get("not_cov"), calculated_bucket.get("not_cov")),
                "pct": reported_pct,
            }
            # If explicit pct entries carry derived counts (mixed-geo), surface them as reported totals
            # only when we otherwise have no reported totals.
            if (
                reported_totals.get("tot") is None
                and reported_totals.get("cov") is None
                and reported_totals.get("not_cov") is None
            ):
                derived_counts = explicit_pct_counts_by_code.get(code)
                if derived_counts:
                    reported_totals = {
                        "tot": derived_counts.get("tot"),
                        "cov": derived_counts.get("cov"),
                        "not_cov": derived_counts.get("not_cov"),
                        "pct": reported_pct,
                    }
            # Special case: Global (GLO) is treated as a parent "country".
            # If its pct is propagated, surface it as reported.
            if (
                code == GeoCode.GLOBAL.value
                and reported_totals.get("pct") is None
                and _has_explicit_or_propagated_pct(country_entries + segment_entries)
                and pct_val is not None
            ):
                reported_totals["pct"] = pct_val

            country = {
                "country_code": code,
                "union_indicator": union_indicator,
                "country_totals": {
                    "tot": total_val,
                    "cov": covered_val,
                    "not_cov": not_covered_val,
                    "pct": pct_val,
                },
            }
            if language_fallback:
                country["language_fallback_country"] = True
            if any(v is not None for v in reported_totals.values()):
                country["reported_totals"] = reported_totals
            if country_keywords:
                country["country_keywords"] = country_keywords
            if country_table_keywords:
                country["country_table_keywords"] = country_table_keywords
            if suppressed_items:
                country["suppressed_counts"] = suppressed_items
            source_sentence_indices = sorted(
                {
                    e.sent_idx
                    for e in country_entries + segment_entries
                    if e.sent_idx is not None and e.sent_idx >= 0
                }
            )
            if source_sentence_indices:
                country["source_sentence_indices"] = source_sentence_indices
            # For explicit non-coverage rows, omit breakdown noise to keep payload compact.
            if union_indicator != 0 and method_breakdown:
                country["method_breakdown"] = method_breakdown

            return country

        for code in sorted(country_codes):
            is_pseudo_region = code in pseudo_region_by_code
            is_promoted_pseudo_region = code in promoted_region_codes
            if (
                code in REGION_CODES
                and not is_pseudo_region
                and not is_promoted_pseudo_region
            ) or (
                code in IGNORED_REGIONS
                and not is_pseudo_region
                and not is_promoted_pseudo_region
            ):
                continue

            country_entries: List[Entry] = []
            segment_entries: List[Entry] = []
            if is_pseudo_region:
                region_name = pseudo_region_by_code[code]
                for e in self.entries:
                    if (
                        e.scope == Scope.REGION
                        and isinstance(e.key, str)
                        and _CODE_TO_REGION.get(e.key, e.key) == region_name
                    ):
                        country_entries.append(e)
            else:
                for e in self.entries:
                    if e.scope == Scope.COUNTRY and e.key == code:
                        country_entries.append(e)
                    elif e.scope == Scope.SEGMENT and self._segment_matches_country(
                        e.key, code
                    ):
                        segment_entries.append(e)
            if is_pseudo_region:
                for e in self.entries:
                    if e.scope == Scope.SEGMENT and self._segment_matches_country(
                        e.key, code
                    ):
                        segment_entries.append(e)
            country_entries = self._dedupe_country_entries(country_entries)

            # Prefer country-scope resolved entry as final snapshot.
            primary_country_entry = None
            if country_entries:
                primary_country_entry = max(
                    country_entries,
                    key=lambda x: ((x.total_count or 0.0), x.sent_idx),
                )

            total_val = None
            covered_val = None
            not_covered_val = None
            pct_val = None

            # Mirror calculate_metrics country aggregation semantics for parity.
            c_agg_covered = 0.0
            c_agg_total = 0.0
            c_has_data = False
            for c in country_entries:
                c_cov = 0.0
                c_tot = 0.0
                c_has_local_data = False
                segs = [
                    s
                    for s in segment_entries
                    if self._segment_matches_country(s.key, str(c.key))
                ]
                has_segment_counts = any(
                    (s.covered_count is not None) or (s.total_count is not None)
                    for s in segs
                )

                if c.covered_count is not None:
                    c_cov = c.covered_count
                    c_tot = c.total_count if c.total_count else 0.0
                    c_has_local_data = True
                elif c.percentage is not None and c.total_count:
                    c_cov = (c.percentage / 100.0) * c.total_count
                    c_tot = c.total_count
                    c_has_local_data = True

                if c_has_local_data and has_segment_counts:
                    seg_cov_preview = sum(
                        s.covered_count for s in segs if s.covered_count is not None
                    )
                    seg_tot_preview = sum(
                        s.total_count for s in segs if s.total_count is not None
                    )
                    if c_cov == 0 and (seg_cov_preview > 0 or seg_tot_preview > 0):
                        c_has_local_data = False
                        c_cov = 0.0
                        c_tot = 0.0

                if not c_has_local_data and segs:
                    seg_cov = sum(
                        s.covered_count for s in segs if s.covered_count is not None
                    )
                    seg_tot = (
                        c.total_count
                        if c.total_count
                        else sum(s.total_count for s in segs if s.total_count)
                    )
                    if seg_cov > 0 or seg_tot > 0:
                        c_cov = seg_cov
                        c_tot = seg_tot
                        c_has_local_data = True

                if c_has_local_data:
                    c_agg_covered += c_cov
                    c_agg_total += c_tot
                    c_has_data = True

            if c_has_data:
                total_val = c_agg_total
                covered_val = c_agg_covered
            else:
                if primary_country_entry:
                    total_val = primary_country_entry.total_count
                    covered_val = primary_country_entry.covered_count
                    not_covered_val = primary_country_entry.not_covered_count
                    pct_val = primary_country_entry.percentage
                if total_val is None and code in self.country_totals:
                    total_val = self.country_totals.get(code)
                if total_val is None and is_pseudo_region:
                    region_name = pseudo_region_by_code[code]
                    total_val = self.region_totals.get(region_name)

                if covered_val is None and segment_entries:
                    seg_cov = sum(
                        s.covered_count
                        for s in segment_entries
                        if s.covered_count is not None
                    )
                    covered_val = float(seg_cov) if seg_cov > 0 else None
                if not_covered_val is None and segment_entries:
                    seg_not = sum(
                        s.not_covered_count
                        for s in segment_entries
                        if s.not_covered_count is not None
                    )
                    not_covered_val = float(seg_not) if seg_not > 0 else None

            if (
                not_covered_val is None
                and total_val is not None
                and covered_val is not None
            ):
                residual = float(total_val) - float(covered_val)
                if residual >= 0:
                    not_covered_val = residual

            if (
                pct_val is None
                and total_val
                and covered_val is not None
                and total_val > 0
            ):
                pct_val = round((covered_val / total_val) * 100.0, 2)

            # NEW: also surface explicit pct when no count-derived pct exists
            if pct_val is None:
                explicit_vals = explicit_pct_by_code.get(code, [])
                if explicit_vals:
                    vals = [float(p) for p in explicit_vals if 0.0 <= float(p) <= 100.0]
                    if vals:
                        if len(vals) == 1:
                            pct_val = vals[0]
                        else:
                            vals_sorted = sorted(vals, reverse=True)
                            largest = vals_sorted[0]
                            smaller_sum = sum(vals_sorted[1:])
                            total_sum = sum(vals_sorted)
                            if abs(largest - smaller_sum) <= 2.0:
                                pct_val = largest
                            elif total_sum <= 100.0 + 1e-9:
                                pct_val = total_sum
                            else:
                                pct_val = sum(vals) / len(vals)
                        if pct_val is not None:
                            pct_val = round(pct_val, 2)

            country_keywords = self.country_keywords.get(code, {})
            country_table_keywords = sorted(
                list(self.country_table_keywords.get(code, set()))
            )
            suppressed_items = suppressed_by_code.get(code)
            weighted_seed = aggregate_weighted_by_code.get(code)

            country = build_country_output(
                code=code,
                total_val=total_val,
                covered_val=covered_val,
                not_covered_val=not_covered_val,
                pct_val=pct_val,
                country_entries=country_entries,
                segment_entries=segment_entries,
                weighted_seed=weighted_seed,
                country_keywords=country_keywords,
                country_table_keywords=country_table_keywords,
                suppressed_items=suppressed_items,
                language_fallback=code in self.language_fallback_countries,
                fallback_union_indicator=fallback_union_indicator(code),
            )

            countries.append(country)

        # Drop redundant pseudo-countries when child countries are present.
        # Keep pseudo-countries if:
        #   1. They represent subtraction residuals (SUB::Region)
        #   2. They have explicit reported data (don't drop if children are partial/empty)
        countries_by_code = {c.get("country_code"): c for c in countries}
        redundant_pseudo_codes: set[str] = set()

        def _country_has_signal(country_obj: Dict[str, Any]) -> bool:
            if not country_obj:
                return False
            reported = country_obj.get("reported_totals") or {}
            if any(v is not None for v in reported.values()):
                return True
            if country_obj.get("country_keywords"):
                return True
            if country_obj.get("country_table_keywords"):
                return True
            if country_obj.get("method_breakdown"):
                return True
            if country_obj.get("suppressed_counts"):
                return True
            return False

        for pseudo_code in pseudo_region_name_by_code:
            if pseudo_code not in countries_by_code:
                continue

            # Check if there are subtraction segments for this pseudo-country
            has_subtraction_segment = any(
                e.scope == Scope.SEGMENT
                and self._segment_matches_country(e.key, pseudo_code)
                and self._is_subtraction_segment_key(e.key)
                for e in self.entries
            )
            if has_subtraction_segment:
                continue

            # Check if this pseudo-country has explicit reported data
            # If it does, keep it even if children are present
            pseudo_entry = countries_by_code[pseudo_code]
            has_explicit_data = (
                (pseudo_entry.get("reported_totals") or {}).get("tot") is not None
                or (pseudo_entry.get("reported_totals") or {}).get("cov") is not None
            )
            if has_explicit_data:
                continue

            # Only mark as redundant if it has no explicit data and child countries exist
            has_child_country = any(
                c_code != pseudo_code
                and c_code not in IGNORED_REGIONS
                and c_code not in AGG_SET
                and c_code not in DOMESTIC_SET
                and is_contained(
                    container_key=pseudo_code,
                    item_key=c_code,
                    domestic_country_code=self.domestic_country_code,
                )
                and _country_has_signal(countries_by_code.get(c_code, {}))
                for c_code in countries_by_code.keys()
            )
            if has_child_country:
                redundant_pseudo_codes.add(pseudo_code)

        if redundant_pseudo_codes:
            countries = [
                c
                for c in countries
                if c.get("country_code") not in redundant_pseudo_codes
            ]

        agg = []
        seen_agg = set()
        for e in self.entries:
            is_aggregate_parent = e.scope == Scope.AGGREGATE or (
                e.scope == Scope.REGION and e.key in AGG_SET
            )
            if not is_aggregate_parent or not e.related_geo_codes:
                continue
            agg_id = (e.key, e.sent_idx)
            if agg_id in seen_agg:
                continue
            seen_agg.add(agg_id)

            aggregate_key = e.key
            if isinstance(aggregate_key, str):
                if aggregate_key in AGG_SET:
                    aggregate_key = GeoCode.AGGREGATE.value
                elif aggregate_key in region_name_to_code:
                    aggregate_key = region_name_to_code[aggregate_key]
                elif is_region(aggregate_key):
                    # Already code-like.
                    aggregate_key = aggregate_key

            child_codes: List[str] = []
            for raw_code in e.related_geo_codes:
                normalized = normalize_geo_code(raw_code, region_name_to_code)
                if normalized and normalized not in child_codes:
                    child_codes.append(normalized)
            if not child_codes:
                continue

            child_codes = reduce_child_codes(
                child_codes,
                aggregate_key=aggregate_key if isinstance(aggregate_key, str) else None,
                region_name_to_code=region_name_to_code,
            )

            if not child_codes:
                continue
            # Avoid double-counting: omit aggregates that already copied explicit
            # values directly to their single child.
            if getattr(e, "_single_child_explicit_applied", False):
                continue

            child_weights = {
                c: float(self.country_totals.get(c, 0.0) or 0.0) for c in child_codes
            }
            alloc_total = alloc_map_by_weights(e.total_count, child_weights)
            alloc_covered = alloc_map_by_weights(e.covered_count, child_weights)
            alloc_not_covered = alloc_map_by_weights(e.not_covered_count, child_weights)

            has_agg_counts = any(
                v is not None
                for v in (e.total_count, e.covered_count, e.not_covered_count)
            )
            if not has_agg_counts:
                continue
            if e.covered_count == 0:
                continue

            children = {}
            for c in child_codes:
                children[c] = {
                    "tot": alloc_total.get(c),
                    "cov": alloc_covered.get(c),
                    "not_cov": alloc_not_covered.get(c),
                    "w_tot": child_weights.get(c),
                }

            agg_source_type = SourceType.WEIGHTED_DIVISION.value
            if e.is_explicit and len(child_codes) == 1:
                agg_source_type = SourceType.EXPLICIT.value

            agg.append(
                {
                    "aggregate_key": aggregate_key,
                    "aggregate_scope": e.scope.value,
                    "tot": e.total_count,
                    "cov": e.covered_count,
                    "not_cov": e.not_covered_count,
                    "pct": e.percentage,
                    "source_type": agg_source_type,
                    "children": children,
                }
            )

        global_entry = next(
            (
                e
                for e in self.entries
                if e.scope == Scope.GLOBAL
                or (e.key and (e.key.split("::")[0] in GLOBAL_SET))
            ),
            None,
        )

        def _country_obj_has_quant_signal(country_obj: Optional[Dict[str, Any]]) -> bool:
            if not country_obj:
                return False
            totals = country_obj.get("country_totals") or {}
            reported = country_obj.get("reported_totals") or {}
            for bucket in (totals, reported):
                if any(bucket.get(k) is not None for k in ("tot", "cov", "not_cov", "pct")):
                    return True
            return False

        def _country_obj_is_explicit_non_coverage(country_obj: Optional[Dict[str, Any]]) -> bool:
            if not country_obj:
                return False
            if country_obj.get("union_indicator") == 0:
                return True
            totals = country_obj.get("country_totals") or {}
            reported = country_obj.get("reported_totals") or {}
            for bucket in (totals, reported):
                if bucket.get("pct") == 0:
                    return True
                if bucket.get("not_cov") is not None and bucket.get("cov") in (None, 0):
                    return True
            return False

        domestic_country_obj = next(
            (
                c
                for c in countries
                if c.get("country_code") == self.domestic_country_code
            ),
            None,
        )
        international_country_obj = next(
            (
                c
                for c in countries
                if c.get("country_code") in INT_SET
                and _country_obj_has_quant_signal(c)
                and not _country_obj_is_explicit_non_coverage(c)
            ),
            None,
        )

        global_obj = None
        if global_entry and any(
            v is not None
            for v in (
                global_entry.total_count,
                global_entry.covered_count,
                global_entry.not_covered_count,
                global_entry.percentage,
            )
        ):
            global_obj = build_country_output(
                code=GeoCode.GLOBAL.value,
                total_val=global_entry.total_count,
                covered_val=global_entry.covered_count,
                not_covered_val=global_entry.not_covered_count,
                pct_val=global_entry.percentage,
                country_entries=[global_entry],
                segment_entries=[],
                weighted_seed=None,
                country_keywords=None,
                country_table_keywords=None,
                suppressed_items=None,
                language_fallback=False,
            )
        elif (
            international_country_obj
            and not _country_obj_has_quant_signal(domestic_country_obj)
            and not _country_obj_is_explicit_non_coverage(domestic_country_obj)
        ):
            global_obj = dict(international_country_obj)
            global_obj["country_code"] = GeoCode.GLOBAL.value
            global_obj["global_source"] = "promoted_from_international"
            global_obj["global_source_code"] = international_country_obj.get(
                "country_code"
            )
            global_obj["global_source_note"] = (
                "International promoted to Global because domestic data was missing"
            )

        # If a North American union signal produces the same unsplittable signal
        # for both US and CA from the same sentence, keep only the domestic side
        # in the provenance report.
        if self.domestic_country_code in {"US", "CA"}:
            other_na_code = "CA" if self.domestic_country_code == "US" else "US"

            def _country_signal_signature(country_obj: Optional[Dict[str, Any]]) -> Tuple[Any, ...]:
                if not country_obj:
                    return tuple()
                totals = country_obj.get("country_totals") or {}
                reported = country_obj.get("reported_totals") or {}
                source_sentence_indices = tuple(
                    country_obj.get("source_sentence_indices") or []
                )
                return (
                    source_sentence_indices,
                    totals.get("tot"),
                    totals.get("cov"),
                    totals.get("not_cov"),
                    totals.get("pct"),
                    reported.get("tot"),
                    reported.get("cov"),
                    reported.get("not_cov"),
                    reported.get("pct"),
                    country_obj.get("union_indicator"),
                )

            domestic_country_obj = next(
                (
                    c
                    for c in countries
                    if c.get("country_code") == self.domestic_country_code
                ),
                None,
            )
            other_na_country_obj = next(
                (
                    c
                    for c in countries
                    if c.get("country_code") == other_na_code
                ),
                None,
            )
            if (
                domestic_country_obj
                and other_na_country_obj
                and _country_signal_signature(domestic_country_obj)
                == _country_signal_signature(other_na_country_obj)
            ):
                countries = [
                    c
                    for c in countries
                    if c.get("country_code") != other_na_code
                ]

        # Build Summary
        summary = {
            "cov": {code: [] for code in REGION_NAME_MAP.values()},
            "not_cov": {code: [] for code in REGION_NAME_MAP.values()},
            "dom_cov": False,
            "int_cov": False,
        }

        for c_obj in countries:
            code = c_obj["country_code"]
            union_indicator = c_obj.get("union_indicator")
            is_covered = union_indicator == 1

            if is_covered:
                if code == self.domestic_country_code:
                    summary["dom_cov"] = True
                else:
                    summary["int_cov"] = True

            r_name = _CODE_TO_REGION.get(code)
            if r_name:
                reg_key = REGION_NAME_MAP.get(r_name)
                if reg_key:
                    target_list = (
                        summary["cov"][reg_key]
                        if is_covered
                        else summary["not_cov"][reg_key]
                    )
                    target_list.append(code)

        # Sort lists
        for k in summary["cov"]:
            summary["cov"][k].sort()
            summary["not_cov"][k].sort()

        global_keywords = sorted(
            {kw for _, kw in self.global_sentence_keywords if kw}
            | {kw for kw in self.global_table_keywords if kw}
        )
        global_table_keywords = sorted(list(self.global_table_keywords))
        explicit_pct_entries = [
            {
                "geo_code": e.geo_code,
                "percentage": e.percentage,
                "sentence_index": e.sent_idx,
                "note": e.note,
            }
            for e in self.explicit_pct_entries
        ]

        return {
            "domestic_country_code": self.domestic_country_code,
            "countries": countries,
            "agg": agg,
            "global": global_obj,
            "summary": summary,
            "global_keywords": global_keywords,
            "global_keyword_count": len(global_keywords),
            "global_table_keywords": global_table_keywords,
            "notes": [],
        }

    def build_bargaining_provenance_report(self) -> Dict[str, Any]:
        entities: set[str] = set()
        total_units = 0.0
        total_entries = 0

        def _normalize_entity(val: str) -> str:
            if val in REGION_NAME_MAP:
                return REGION_NAME_MAP[val]
            return val

        def _is_code(val: str) -> bool:
            if not val:
                return False
            # Accept uppercase code-like tokens only (drop names).
            return val.isupper() and val.replace(" ", "").isalnum()

        for e in self.bargaining_entries:
            if e.key:
                base_key = str(e.key)
                main_key = base_key.split("::", 1)[0]
                norm = _normalize_entity(main_key)
                if _is_code(norm):
                    entities.add(norm)
            total_units += float(e.bargaining_unit_count or 0.0)
            total_entries += 1
            for code in e.related_geo_codes or []:
                if code:
                    norm = _normalize_entity(code)
                    if _is_code(norm):
                        entities.add(norm)

        entities_out = sorted(list(entities))

        if total_units == 0.0 and not entities_out:
            return {}

        return {
            "tot": total_units,
            "entities": entities_out,
        }


class GeoPopulationResolver:
    """
    Shared resolver for population-denominator updates by geography.
    Extracted from UnionAnalyzer pass-1 census logic so additional analyzers
    (e.g. employment distribution parsing) can reuse the same update path.
    """

    def __init__(self, analyzer: "UnionAnalyzer"):
        self.analyzer = analyzer

    def _is_strict_employment_distribution_sentence(
        self, analysis: SentenceAnalysis, allow_without_anchor: bool = False
    ) -> bool:
        text = analysis.text or ""
        if not STRICT_EMPLOYMENT_ANCHOR_REGEX.search(text) and not allow_without_anchor:
            return False
        if not analysis.percentages:
            return False

        # Strict exclusion: any union/coverage semantics disable this path.
        has_union_semantics = bool(
            analysis.is_union
            or analysis.union_terms
            or analysis.sentence_union_keywords
            or analysis.coverage_terms
            or analysis.negation_terms
            or analysis.works_councils
            or analysis.qualitative_terms
            or analysis.qualitative_membership_terms
            or analysis.relationship_terms
            or analysis.relationship_quality_terms
            or analysis.supplier_terms
            or analysis.risk_terms
            or analysis.generic_risk_terms
            or analysis.legal_requirement_terms
            or analysis.legal_process_terms
            or analysis.boilerplate_terms
        )
        if has_union_semantics:
            return False

        # Strict exclusion: typed worker buckets and hard exclusion language.
        if analysis.worker_types:
            return False
        if analysis.except_terms or analysis.outside_terms:
            return False

        explicit_geo = [
            g
            for g in analysis.geo_matches
            if g.source_type == GeoSource.EXPLICIT and g.geo_code
        ]
        return bool(explicit_geo)

    def _align_explicit_geo_spans(
        self, analysis: SentenceAnalysis
    ) -> List[Tuple[Tuple[int, int], str]]:
        geo_objs = [
            g
            for g in analysis.geo_matches
            if g.source_type == GeoSource.EXPLICIT and g.geo_code
        ]
        raw_geos = [m for m in analysis._matches if m.get("type") == MatchType.GEO]
        if not geo_objs or len(geo_objs) != len(raw_geos):
            return []

        aligned: List[Tuple[Tuple[int, int], str]] = []
        for g_obj, raw in zip(geo_objs, raw_geos):
            code = g_obj.geo_code
            if not code:
                continue
            if code == GeoCode.DOMESTIC.value:
                code = self.analyzer.domestic_country_code
            aligned.append((raw["span"], code))
        return aligned

    def _map_percentages_to_geo_codes(
        self, analysis: SentenceAnalysis, allow_sum: bool = True
    ) -> Dict[str, float]:
        aligned_geos = self._align_explicit_geo_spans(analysis)
        if not aligned_geos:
            return {}

        pct_matches = [
            m for m in analysis._matches if m.get("type") == MatchType.PERCENT
        ]
        if not pct_matches:
            return {}

        pct_to_geo: Dict[str, float] = {}
        for pct_m in pct_matches:
            p_span = pct_m["span"]
            p_mid = get_midpoint(p_span)

            best_code = None
            best_dist = float("inf")
            for g_span, code in aligned_geos:
                g_mid = get_midpoint(g_span)
                dist = abs(p_mid - g_mid)
                if dist > 120:
                    continue
                lo = min(p_span[1], g_span[1])
                hi = max(p_span[0], g_span[0])
                if hi > lo:
                    between = analysis.text[lo:hi]
                    if SEGMENT_DELIMITER_REGEX.search(between):
                        continue
                if dist < best_dist:
                    best_dist = dist
                    best_code = code

            if best_code is None:
                continue
            pct_val = float(pct_m.get("val", 0.0) or 0.0)
            if pct_val <= 0:
                continue
            if allow_sum:
                pct_to_geo[best_code] = pct_to_geo.get(best_code, 0.0) + pct_val
            else:
                # Keep closest match only; do not aggregate multiple percents into one geo.
                if best_code not in pct_to_geo:
                    pct_to_geo[best_code] = pct_val

        total_pct = sum(pct_to_geo.values())
        if total_pct > 100.0 + 2.0 and allow_sum:
            return {}
        return pct_to_geo

    def _apply_strict_employment_distribution(
        self,
        analysis: SentenceAnalysis,
        tracker: Tracker,
        total_population: float,
        allow_without_anchor: bool = False,
    ) -> bool:
        if total_population <= 0:
            return False
        if not self._is_strict_employment_distribution_sentence(
            analysis, allow_without_anchor=allow_without_anchor
        ):
            return False

        pct_to_geo = self._map_percentages_to_geo_codes(analysis)
        if not pct_to_geo:
            return False

        assigned_counts: Dict[str, float] = {}
        for code, pct in pct_to_geo.items():
            count = round((pct / 100.0) * total_population)
            if count <= 0:
                continue
            assigned_counts[code] = assigned_counts.get(code, 0.0) + float(count)
            r_name = _CODE_TO_REGION.get(code, Region.UNKNOWN.value)
            specific_ctx = {
                "region": r_name,
                "countries": [{"code": code, "name": code}],
            }
            tracker.update(count, specific_ctx)

        # Handle "remaining/balance" distribution:
        # e.g. "90% domestic, with the balance in China"
        if analysis.has_remaining_other:
            all_codes_in_sentence: List[str] = []
            for _, code in self._align_explicit_geo_spans(analysis):
                if code not in all_codes_in_sentence:
                    all_codes_in_sentence.append(code)

            residual_codes = [
                c for c in all_codes_in_sentence if c not in assigned_counts
            ]
            assigned_sum = sum(assigned_counts.values())
            residual_count = max(0.0, float(total_population) - float(assigned_sum))
            tracker.census_log.append(
                f"[REMAINDER] assigned_codes={list(assigned_counts.keys())} "
                f"all_codes={all_codes_in_sentence} "
                f"residual_codes={residual_codes} "
                f"residual_count={residual_count}"
            )
            if residual_count > 0 and residual_codes:
                if len(residual_codes) == 1:
                    code = residual_codes[0]
                    r_name = _CODE_TO_REGION.get(code, Region.UNKNOWN.value)
                    specific_ctx = {
                        "region": r_name,
                        "countries": [{"code": code, "name": code}],
                    }
                    tracker.update(round(residual_count), specific_ctx)
                else:
                    entities = [{"key": code} for code in residual_codes]
                    alloc, _ = weighted_division(
                        residual_count,
                        entities,
                        use_labor_weights=False,
                        domestic_country=self.analyzer.domestic_country_code,
                    )
                    for code, count in alloc.items():
                        if count <= 0:
                            continue
                        r_name = _CODE_TO_REGION.get(code, Region.UNKNOWN.value)
                        specific_ctx = {
                            "region": r_name,
                            "countries": [{"code": code, "name": code}],
                        }
                        tracker.update(float(count), specific_ctx)

        return bool(assigned_counts)

    def populate_tracker(
        self,
        sentences: List[str],
        tracker: Tracker,
        reporting_year: Optional[int] = None,
        initial_geo_context: Optional[Dict] = None,
        emp_count: Optional[float] = None,
    ) -> None:
        last_geo_context = initial_geo_context
        last_geo_sentence_idx = -1
        last_strict_total: Optional[float] = None
        last_strict_total_idx: int = -10_000

        for idx, s in enumerate(sentences):
            analysis = self.analyzer.extractor.analyze_sentence(s, emp_count=emp_count)

            # Skip historical counts
            is_historical = False
            if reporting_year and analysis.years:
                if all(y < reporting_year for y in analysis.years):
                    is_historical = True
            if (is_historical or analysis.has_historical) and not analysis.has_current:
                continue

            tracker.register_sentence_keywords(
                idx,
                self.analyzer._get_annotated_keywords(analysis),
                is_table_generated=self.analyzer._is_table_generated_sentence(s),
            )

            # Determine context (reusing logic to ensure consistency with Pass 2)
            geo_context = self.analyzer._determine_geo_context(
                analysis, last_geo_context, idx, last_geo_sentence_idx
            )

            if geo_context["specificity"] in (
                Specificity.EXPLICIT.value,
                Specificity.INFERRED_UNION.value,
                Specificity.EXPLICIT_INFERRED.value,
                Specificity.INFERRED_LANG.value,
            ):
                last_geo_context = geo_context
                last_geo_sentence_idx = idx
            tracker.register_mentions(geo_context)

            if analysis.suppress_coverage_counts:
                continue

            # Try to resolve specific counts to geography (e.g. "200 in China")
            mapped_counts, _, _ = self.analyzer._resolve_counts_to_geography(analysis)
            tracker.census_log.append(
                f"[PRE-MAPPED] mapped_counts={mapped_counts}"
            )
            if mapped_counts:
                for code, val in mapped_counts.items():
                    r_name = _CODE_TO_REGION.get(code, Region.UNKNOWN.value)
                    specific_ctx = {
                        "region": r_name,
                        "countries": [{"code": code, "name": code}],
                    }
                    tracker.update(val, specific_ctx)

            # Try to resolve counts to unions
            union_counts, _, _ = self.analyzer._resolve_counts_to_unions(analysis)
            if union_counts:
                for union_name, val in union_counts.items():
                    info = self.analyzer.matcher.get_union(union_name)
                    if not info:
                        continue
                    region, country, code = info

                    # Refine generic union code using context
                    if code:
                        ctx_countries = geo_context.get("countries", [])
                        refined_code, refined_name = refine_generic_code(
                            code, ctx_countries, self.analyzer.domestic_country_code
                        )
                        if refined_code != code:
                            code = refined_code
                            country = refined_name or country

                    r_val = region.value
                    if code != info[2]:
                        r_name = _CODE_TO_REGION.get(code)
                        if r_name:
                            r_val = r_name

                    specific_ctx = {
                        "region": r_val,
                        "countries": [{"code": code, "name": country}],
                    }
                    tracker.update(val, specific_ctx)

            effective_counts = get_effective_counts(analysis)
            allow_implicit_from_prior = (
                last_strict_total is not None and idx == last_strict_total_idx + 1
            )
            has_strict_pct_dist = self._is_strict_employment_distribution_sentence(
                analysis, allow_without_anchor=allow_implicit_from_prior
            )
            if not effective_counts:
                if (
                    has_strict_pct_dist
                    and last_strict_total is not None
                    and idx == last_strict_total_idx + 1
                ):
                    self._apply_strict_employment_distribution(
                        analysis=analysis,
                        tracker=tracker,
                        total_population=last_strict_total,
                        allow_without_anchor=True,
                    )
                continue

            max_count = max(effective_counts)
            range_avg = self.analyzer._detect_count_range(analysis, effective_counts)
            summation = None if analysis.is_union else self.analyzer._detect_summation(analysis, effective_counts)

            # Temporal Alignment (2 Years, 2 Counts)
            # "In 2009 we had 100, in 2010 we had 110"
            matched_temporal_count = None
            if (
                len(analysis.years) == len(effective_counts)
                and len(effective_counts) >= 2
            ):
                y_matches = sorted(
                    [m for m in analysis._matches if m["type"] == MatchType.YEAR],
                    key=lambda x: x["span"][0],
                )
                c_matches = sorted(
                    [
                        m
                        for m in analysis._matches
                        if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                        and m["val"] in effective_counts
                    ],
                    key=lambda x: x["span"][0],
                )

                if len(y_matches) == len(c_matches):
                    target_y = reporting_year if reporting_year else max(analysis.years)
                    for y_m, c_m in zip(y_matches, c_matches):
                        if not (target_y - 1 <= y_m["val"] <= target_y + 1):
                            continue
                        if y_m["val"] == target_y:
                            matched_temporal_count = c_m["val"]
                            break

            if matched_temporal_count is not None:
                final_count = matched_temporal_count
            elif range_avg:
                final_count = range_avg
            elif summation:
                final_count = summation
            else:
                final_count = max_count
            tracker.census_log.append(
                f"[CENSUS] sent={s[:60]!r} | effective_counts={effective_counts} | "
                f"range_avg={range_avg} | summation={summation} | final_count={final_count}"
            )
            tracker.update(final_count, geo_context)
            tracker.census_log.append(
                f"  -> after update: country_totals={dict(tracker.country_totals)} | "
                f"region_totals={dict(tracker.region_totals)}"
            )
            if STRICT_EMPLOYMENT_ANCHOR_REGEX.search(analysis.text or ""):
                last_strict_total = float(final_count)
                last_strict_total_idx = idx

            if has_strict_pct_dist:
                self._apply_strict_employment_distribution(
                    analysis=analysis,
                    tracker=tracker,
                    total_population=float(final_count),
                    allow_without_anchor=False,
                )


class UnionAnalyzer:
    def __init__(self, domestic_country_code: str = "US"):
        self.extractor = UnionExtractor()
        self.simple_analyzer = SimpleCoverageAnalyzer()
        self.extra_analyzer = UnionExtraAnalyzer()
        self.risk_digest = RiskDigest()
        self.complex_analyzer_cls = ComplexCoverageAnalyzer
        self.matcher = self.extractor.matcher  # Access shared matcher
        self.domestic_country_code = _normalize_domestic_country_code(
            domestic_country_code
        )
        self.geo_population_resolver = GeoPopulationResolver(self)

    def set_domestic_country_code(self, code: Optional[str]) -> None:
        self.domestic_country_code = _normalize_domestic_country_code(code)

    def _get_annotated_keywords(
        self, analysis: SentenceAnalysis
    ) -> Optional[List[str]]:
        keywords = analysis.sentence_union_keywords or analysis.union_terms
        if not keywords:
            return None

        annotated = []
        for term in keywords:
            related = next(
                (
                    m
                    for m in analysis.geo_matches
                    if m.text == term
                    and m.geo_code
                    and m.geo_code.startswith(GeoCode.INT_LANG.value)
                ),
                None,
            )
            if related:
                annotated.append(f"{related.geo_code}::{term}")
            else:
                annotated.append(term)
        return annotated

    @staticmethod
    def _is_table_generated_sentence(text: str) -> bool:
        return bool(text and TABLE_TOK in text)

    def _detect_count_range(
        self, analysis: SentenceAnalysis, counts: List[float]
    ) -> Optional[float]:
        """
        Detects if worker_counts form a range (e.g. 100 to 200).
        Returns average if range found, else None.
        """
        if len(counts) != 2:
            return None

        matches = [
            m
            for m in analysis._matches
            if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
            and m["val"] in counts
        ]
        if len(matches) != 2:
            return None

        matches.sort(key=lambda x: x["span"][0])
        m1, m2 = matches[0], matches[1]

        if is_range_context(analysis.text, m1["span"], m2["span"]):
            return (m1["val"] + m2["val"]) / 2

        return None

    def _detect_summation(
        self, analysis: SentenceAnalysis, counts: List[float]
    ) -> Optional[float]:
        """
        Detects if counts should be summed (e.g. "100 salaried and 50 hourly").
        """
        if not counts or len(counts) < 2:
            return None

        # 1. Check if one number is the sum of the others (Explicit Total)
        max_val = max(counts)
        total_sum = sum(counts)
        rest = total_sum - max_val

        # If max is roughly equal to the sum of the rest, then max is the total.
        if max_val > 0 and abs(max_val - rest) / max_val < 0.05:
            return None

        # 2. Check for "X and Y" pattern with worker types
        if len(counts) == 2:
            c1, c2 = counts[0], counts[1]
            m1 = next(
                (
                    m
                    for m in analysis._matches
                    if m["val"] == c1
                    and m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                ),
                None,
            )
            m2 = next(
                (
                    m
                    for m in analysis._matches
                    if m["val"] == c2
                    and m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                    and m is not m1
                ),
                None,
            )

            if m1 and m2:
                # Sort by position
                if m1["span"][0] > m2["span"][0]:
                    m1, m2 = m2, m1
                if len(analysis.worker_types) > 1 or len(analysis.worker_terms) > 1:
                    return c1 + c2

        return None

    def _build_clause_report(
        self,
        sentences: List[str],
        reporting_year: Optional[int] = None,
        allowed_sentence_indices: Optional[Set[int]] = None,
        only_suppressed: bool = False,
        emp_count: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Builds a separate report for legal/process/contract clause numerics.
        Intended as a last-resort quantitative signal, independent of coverage.
        """
        items: List[Dict[str, Any]] = []
        last_geo_context = None
        last_geo_sentence_idx = -1

        for idx, sent in enumerate(sentences):
            if (
                allowed_sentence_indices is not None
                and idx not in allowed_sentence_indices
            ):
                continue
            analysis = self.extractor.analyze_sentence(sent, emp_count=emp_count)

            is_historical = False
            if reporting_year and analysis.years:
                if all(y < reporting_year for y in analysis.years):
                    is_historical = True
            if (is_historical or analysis.has_historical) and not analysis.has_current:
                continue

            has_clause_terms = bool(
                analysis.legal_requirement_terms
                or analysis.legal_process_terms
                or analysis.boilerplate_terms
                or analysis.contract_clause_terms
            )
            if not has_clause_terms:
                continue
            if only_suppressed and not analysis.suppress_coverage_counts:
                continue

            has_quant = bool(
                analysis.percentages
                or analysis.worker_counts
                or analysis.bargaining_unit_counts
                or analysis.numbers
            )
            if not has_quant:
                continue

            geo_context = self._determine_geo_context(
                analysis, last_geo_context, idx, last_geo_sentence_idx
            )
            is_strong_geo = geo_context["specificity"] in (
                Specificity.EXPLICIT.value,
                Specificity.INFERRED_UNION.value,
                Specificity.EXPLICIT_INFERRED.value,
                Specificity.INFERRED_LANG.value,
            )
            effective_counts = get_effective_counts(analysis)
            has_counts = bool(effective_counts)
            if is_strong_geo or has_counts:
                last_geo_context = geo_context
                last_geo_sentence_idx = idx

            items.append(
                {
                    "sentence_index": idx,
                    "percentages": analysis.percentages,
                    "worker_counts": analysis.worker_counts,
                    "bargaining_unit_counts": analysis.bargaining_unit_counts,
                    "numbers": analysis.numbers,
                    "geographic_context": geo_context,
                    "suppress_types": [
                        t
                        for t, present in (
                            (
                                SuppressedCountType.LEGAL_REQUIREMENT.value,
                                bool(analysis.legal_requirement_terms),
                            ),
                            (
                                SuppressedCountType.LEGAL_PROCESS.value,
                                bool(analysis.legal_process_terms),
                            ),
                            (
                                SuppressedCountType.BOILERPLATE.value,
                                bool(analysis.boilerplate_terms),
                            ),
                            (
                                SuppressedCountType.CONTRACT_CLAUSE.value,
                                bool(analysis.contract_clause_terms),
                            ),
                        )
                        if present
                    ],
                    "temporal_scope": (
                        TemporalScope.HISTORICAL.value
                        if is_historical
                        else TemporalScope.CURRENT.value
                    ),
                }
            )
        return items

    def _determine_geo_context(
        self, analysis: SentenceAnalysis, last_context, current_idx, last_idx
    ) -> Dict[str, Any]:
        """
        Local wrapper for geographic context determination.
        """
        return determine_geo_context(
            analysis, last_context, current_idx, last_idx, self.domestic_country_code
        )

    def _create_exception_items(
        self,
        analysis: SentenceAnalysis,
        main_coverage: Dict[str, Any],
        sentence_index: int,
        sentence_text: str,
    ) -> List[Dict[str, Any]]:
        """
        Creates explicit coverage entries for excluded geographies based on the
        inverse of the main sentence's coverage status.
        e.g. "All unionized except Mexico" -> Mexico: 0% Unionized.
        """
        # If remaining is present, "except" is likely a breakdown delimiter, not a logical exception
        if analysis.has_remaining_other:
            return []

        items = []

        # 1. Check if we have excluded explicit geographies
        excluded_geos = [
            m
            for m in analysis.geo_matches
            if m.source_type == GeoSource.EXPLICIT and m.is_excluded
        ]
        if not excluded_geos:
            return []

        # Deduplicate by code to prevent double entries for the same country
        seen_codes = set()
        unique_excluded = []
        for m in excluded_geos:
            if m.geo_code and m.geo_code not in seen_codes:
                unique_excluded.append(m)
                seen_codes.add(m.geo_code)

        # 2. Determine Main Status
        main_type = main_coverage.get("type")
        main_pct = main_coverage.get("percentage")
        main_negated = main_coverage.get("negated", False)

        main_status = None  # 'covered' or 'not_covered'

        # Check for "All" / "Substantially All" (High %)
        if main_pct is not None and main_pct >= 90:
            main_status = "covered"
        # Check for "None" / "Minimal" (Low %)
        elif main_pct is not None and main_pct <= 10:
            main_status = "not_covered"
        # Check for Explicit Negation ("Non-union", "Not covered")
        elif main_negated:
            main_status = "not_covered"
        # Check for "Unionized" / "Covered" without specific % (Qualitative)
        elif main_type == CoverageType.QUALITATIVE.value and not main_negated:
            main_status = "covered"

        if not main_status:
            return []

        # 3. Create items for exceptions (Invert status)
        exception_status = "not_covered" if main_status == "covered" else "covered"

        for m in unique_excluded:
            # Skip if remapped to INT (e.g. "Outside US") - that's handled as main context
            if (
                m.geo_code == GeoCode.INTERNATIONAL.value
                and m.country == "International"
            ):
                continue

            geo_ctx = {
                "region": m.region.value,
                "countries": [{"name": m.country, "code": m.geo_code}],
                "specificity": Specificity.EXPLICIT.value,
                "explicit_countries": [m.country],
                "note": "Exception from main clause",
            }

            cov_data = {
                "percentage": None,
                "employee_count_covered": None,
                "employee_count_not_covered": None,
                "employee_count_total": None,
                "negated": False,
                "negation_type": None,
                "type": CoverageType.QUALITATIVE.value,
                "qualitative_bounds": None,
                "note": f"Inferred exception from '{main_status}' main clause",
                "temporal_scope": main_coverage.get("temporal_scope"),
                "ambiguity_multiplier": None,
            }

            if exception_status == "not_covered":
                cov_data["percentage"] = 0.0
                cov_data["negated"] = True
                cov_data["negation_type"] = NegationType.ZERO_COVERAGE.value
            else:
                # Covered (e.g. "Non-union except Canada")
                # Set ambiguity_multiplier to trigger dummy logic later if no counts found
                cov_data["ambiguity_multiplier"] = 1.0
                cov_data["note"] += " (Positive coverage implied)"

            cov_data["is_exception_entry"] = True
            if main_pct is not None:
                cov_data["exception_limit_percent"] = max(0.0, 100.0 - main_pct)

            item = {
                "sentence": sentence_text,
                "keyword_matched": self._get_annotated_keywords(analysis),
                "geographic_context": geo_ctx,
                "coverage_data": cov_data,
                "lookup_totals": {},
                "census_note": "Exception Inference",
                "sentence_index": sentence_index,
                "worker_type_map": {},
                "worker_types": [],
                "is_remaining": False,
                "is_union": True,
            }
            items.append(item)

        return items

    def analyze_paragraph(
        self,
        text: str,
        item_type: str = "item1",
        reporting_year: Optional[int] = None,
        cik: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process a paragraph of text, splitting it into sentences and
        extracting details based on item_type (item1 or item1a).
        """
        sentences = self.extractor.split_sentences(text)
        results = []
        risk_items = []
        summary = {}
        country_report: Dict[str, Any] = {}
        bargaining_report: Dict[str, Any] = {}

        # Inject external global total if available
        ext_total = None
        ext_total_log = None
        if cik and reporting_year:
            ext_total = get_external_global_count(cik, reporting_year)
            if ext_total:
                ext_total_log = f"Loaded external global total: {ext_total}"
        elif cik:
            ext_total = get_external_global_count(cik, None)
            if ext_total:
                ext_total_log = f"Loaded external global total (fallback year): {ext_total}"

        if item_type == "item1a":
            risk_items = self._analyze_item1a(sentences, reporting_year, ext_total)
            # Backward compatibility: keep risk rows under `items` for item1a callers.
            results = risk_items
        else:
            # 1. Split into paragraphs to handle local context
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [text]

            # 2. Pass 1: Census (Populate Tracker with Totals)
            tracker = Tracker(domestic_country_code=self.domestic_country_code)

            if ext_total and ext_total_log:
                tracker.global_total = ext_total
                tracker.resolution_log.append(ext_total_log)

            all_sentences = self.extractor.split_sentences(text)
            self._populate_tracker(all_sentences, tracker, reporting_year, emp_count=ext_total)
            tracker.resolve()
            # tracker.resolve_coverage() # Will be called after population

            suppressed_clause_items = self._build_clause_report(
                all_sentences, reporting_year=reporting_year, only_suppressed=True, emp_count=ext_total
            )

            # 3. Pass 2: Coverage Analysis (Process Paragraphs)
            results = []
            last_geo_context = None
            last_geo_sentence_idx = -1
            prev_paragraph_totals = {}
            all_region_totals = {}
            global_sentence_index = 0

            # Note: We can use tracker.global_total instead of recalculating global_max

            for p_text in paragraphs:
                p_sentences = self.extractor.split_sentences(p_text)

                # Analyze block with context from previous paragraph
                (
                    block_results,
                    block_risk_items,
                    local_totals,
                    last_geo_context,
                    last_geo_sentence_idx,
                ) = self._analyze_block(
                    p_sentences,
                    reporting_year=reporting_year,
                    global_max_workers=tracker.global_total,
                    external_total=ext_total,
                    initial_geo_context=last_geo_context,
                    initial_geo_sentence_idx=last_geo_sentence_idx,
                    previous_totals=prev_paragraph_totals,
                    start_index=global_sentence_index,
                    cik=cik,
                )

                global_sentence_index += len(p_sentences)

                # Update all_region_totals with max found across all blocks
                for reg, count in local_totals.items():
                    if count > all_region_totals.get(reg, 0):
                        all_region_totals[reg] = count

                results.extend(block_results)
                risk_items.extend(block_risk_items)

                # Handle Excluded Geographies (Implicit Coverage)
                for idx, analysis in enumerate(
                    [self.extractor.analyze_sentence(s, emp_count=ext_total) for s in p_sentences]
                ):
                    # We need to match the analysis to the result item to get coverage_data
                    # This is handled inside _analyze_block now to keep context aligned
                    pass

                # Update previous totals for the next iteration (Sliding window: only look back 1 paragraph)
                prev_paragraph_totals = local_totals

            # Populate tracker with coverage entries
            def _has_explicit_quant(cov_data: Dict[str, Any]) -> bool:
                if not cov_data:
                    return False
                if cov_data.get("type") == CoverageType.QUALITATIVE.value:
                    return False
                return any(
                    cov_data.get(k) is not None
                    for k in (
                        "percentage",
                        "employee_count_covered",
                        "employee_count_not_covered",
                        "employee_count_total",
                    )
                )

            explicit_non_table = any(
                (not item.get("is_table_generated"))
                and _has_explicit_quant(item.get("coverage_data", {}))
                for item in results
            )

            for item in results:
                cov: Dict[str, Any] = item.get("coverage_data", {})
                geo = item.get("geographic_context", {})
                # if (
                #     explicit_non_table
                #     and item.get("is_table_generated")
                #     and _has_explicit_quant(cov)
                # ):
                #     # Suppress tabular explicit values when narrative explicit values exist.
                #     for k in (
                #         "percentage",
                #         "employee_count_covered",
                #         "employee_count_not_covered",
                #         "employee_count_total",
                #     ):
                #         cov[k] = None
                #     cov["type"] = CoverageType.NONE.value
                #     cov["note"] = (
                #         ((cov.get("note") or "") + " | ")
                #         if cov.get("note")
                #         else ""
                #     ) + "Suppressed table explicit values (narrative explicit present)"

                #     # Still record keywords so table signals are retained.
                #     tracker.register_sentence_keywords(
                #         item.get("sentence_index", -1),
                #         item.get("keyword_matched"),
                #         is_table_generated=True,
                #     )
                #     continue
                tracker.record_bargaining_units(
                    bargaining_unit_count=cov.get("bargaining_unit_count"),
                    geo_context=geo,
                    sentence_index=item.get("sentence_index", -1),
                )

                tracker.record_explicit_pct_entries(
                    item.get("explicit_pct_entries")
                )

                if not item.get("is_split_item"):
                    item_countries = (item.get("geographic_context") or {}).get("countries") or []
                    item_codes = {c.get("code") for c in item_countries if c.get("code")}

                    for ep in (item.get("explicit_pct_entries") or []):
                        ep_code = ep.get("geo_code")
                        ep_pct = ep.get("percentage")
                        if not ep_code or ep_pct is None:
                            continue
                        if ep_code == GeoCode.DOMESTIC.value:
                            ep_code = self.domestic_country_code
                        r_name = _CODE_TO_REGION.get(ep_code, Region.UNKNOWN.value)
                        ep_geo = {
                            "region": r_name,
                            "countries": [{"code": ep_code, "name": ep_code}],
                            "specificity": Specificity.EXPLICIT.value,
                            "explicit_countries": [ep_code],
                            "regions": [],
                            "union_names_map": {},
                            "domestic_negated": False,
                        }

                        ep_total = ep.get("derived_total")
                        ep_covered = ep.get("derived_covered")
                        ep_not_covered = ep.get("derived_not_covered")
                        if ep_total is None and len(item_codes) == 1 and ep_code in item_codes:
                            ep_total = cov.get("employee_count_total")

                        tracker.record_coverage(
                            percentage=ep_pct,
                            covered_count=ep_covered,
                            geo_context=ep_geo,
                            scope_total=ep_total,
                            not_covered_count=ep_not_covered,
                            is_qualitative=False,
                            is_remaining=False,
                            is_explicit=True,
                            is_negated=False,
                            is_union_record=item.get("is_union", False),
                            sentence_index=item.get("sentence_index", -1),
                            keywords=item.get("keyword_matched"),
                            coverage_type=CoverageType.EXPLICIT_PERCENT.value,
                            is_table_generated=item.get("is_table_generated", False),
                        )

                # Handle Union Context (Denominator) items
                if cov.get("type") == CoverageType.UNION_CONTEXT.value:
                    # If it has a count, treat it as a Covered Count record
                    if cov.get("employee_count_covered"):
                        pass  # Proceed to record_coverage below
                    else:
                        # Otherwise, just log it as context and skip math
                        tracker.record_context(
                            geo, f"Union Denominator Statement: {item.get('sentence')}"
                        )
                        continue

                # Skip if no meaningful coverage data
                if (
                    cov.get("percentage") is None
                    and cov.get("employee_count_covered") is None
                    and cov.get("employee_count_total") is None
                    and not cov.get("negated")
                    and not item.get("is_union", False)
                ):
                    continue

                # Skip vacuous NONE entries whose data was already decomposed into explicit_pct_entries
                if (
                    item.get("explicit_pct_entries")
                    and cov.get("type") == CoverageType.NONE.value
                ):
                    continue

                tracker.record_coverage(
                    percentage=cov.get("percentage"),
                    covered_count=cov.get("employee_count_covered"),
                    geo_context=geo,
                    scope_total=cov.get("employee_count_total"),
                    not_covered_count=cov.get("employee_count_not_covered"),
                    is_qualitative=(cov.get("type") == CoverageType.QUALITATIVE.value),
                    qualitative_bounds=cov.get("qualitative_bounds"),
                    is_remaining=(cov.get("type") == CoverageType.REMAINING.value),
                    is_explicit=(
                        cov.get("type") == CoverageType.EXPLICIT_PERCENT.value
                        or cov.get("is_explicit_percent")
                    ), # type: ignore
                    is_negated=cov.get("negated", False),
                    is_union_record=item.get("is_union", False),
                    sentence_index=item.get("sentence_index", -1),
                    keywords=item.get("keyword_matched"),
                    ambiguity_multiplier=cov.get("ambiguity_multiplier"),
                    is_exception_entry=cov.get("is_exception_entry", False),
                    exception_limit_percent=cov.get("exception_limit_percent"),
                    is_exception_remainder=cov.get("is_exception_remainder", False),
                    coverage_type=cov.get("type"),
                    is_table_generated=item.get("is_table_generated", False),
                )

            # Resolve missing coverage data using collected totals
            tracker.resolve_coverage(
                use_virtual_pool=False, apply_dummy_percentages=False
            )

            summary = self.compute_weighted_coverage(
                results, tracker, all_region_totals
            )
            country_report = tracker.build_country_provenance_report(
                suppressed_clause_items=suppressed_clause_items
            )
            bargaining_report = tracker.build_bargaining_provenance_report()

        risk_summary = (
            self.risk_digest.summarize(risk_items) if risk_items else {}
        )
        if item_type == "item1a":
            country_report = {}

        return {
            "items": results,
            "risk_items": risk_items,
            "risk_summary": risk_summary,
            "summary": summary,
            "country_report": country_report,
            "bargaining_report": bargaining_report,
        }

    def _populate_tracker(
        self,
        sentences: List[str],
        tracker: Tracker,
        reporting_year: Optional[int] = None,
        initial_geo_context: Optional[Dict] = None,
        emp_count: Optional[float] = None,
    ):
        """
        Pass 1: Scans text specifically to find population totals (denominators)
        and populate the Tracker.
        """
        self.geo_population_resolver.populate_tracker(
            sentences=sentences,
            tracker=tracker,
            reporting_year=reporting_year,
            initial_geo_context=initial_geo_context,
            emp_count=emp_count,
        )

    def _prepare_counts(
        self,
        analysis: SentenceAnalysis,
        entities: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Optional[float], Dict[str, float]]:
        """
        Helper to prepare counts for mapping:
        1. Extracts counts
        2. Detects and removes Total (Sum of Parts)
        3. Adds Virtual Count for Balance/Remaining if applicable
        """
        sentence_total = None

        # 1. Extract Counts
        counts = [
            m
            for m in analysis._matches
            if (m["type"] == MatchType.WORKER_COUNT or m["type"] == MatchType.NUMBER)
        ]

        if not counts or not entities:
            return [], None, {}

        parts = counts[:]

        # 2. Detect Total (Sum of Parts / Explicit Total)
        if len(counts) > 1:
            vals = [c["val"] for c in counts]
            max_val = max(vals)
            sum_val = sum(vals)
            others_sum = sum_val - max_val

            # Logic A: Arithmetic Match (Sum of parts ~= Total)
            is_sum_match = others_sum > 0 and abs(max_val - others_sum) / max_val < 0.10

            # Logic B: Count Mismatch (N+1 counts for N entities -> 1 is likely total)
            is_len_mismatch = len(counts) == len(entities) + 1

            # Logic C: Remaining/Balance Indicator
            # If "remaining" is present but NOT associated with a specific count,
            # it implies a virtual remainder, which requires a Total to calculate from.
            is_virtual_remainder = analysis.has_remaining_other

            # Only remove total if we have more counts than entities (implying one is a container/total)
            # OR if we have a virtual remainder (which implies we need to split a Total)
            should_remove_total = False

            if is_virtual_remainder:
                should_remove_total = True
            elif len(counts) > len(entities):
                if is_len_mismatch or is_sum_match:
                    should_remove_total = True
                if analysis.has_subset_indicator:
                    # Check if the total count even exists before the subset indicator
                    subset_indictator = next(
                        (m for m in analysis._matches if m["type"] == MatchType.SUBSET),
                        None,
                    )
                    if subset_indictator:
                        # Find the total candidates that appear before the subset
                        total_candidates = [
                            c
                            for c in counts
                            if c["val"] == max_val
                            and c["span"][0] < subset_indictator["span"][0]
                        ]
                        if total_candidates:
                            should_remove_total = True

            if should_remove_total:
                sentence_total = max_val

                # Remove the total from parts to map the rest
                # We remove the *first* occurrence of max_val to be safe, though usually unique
                for i, c in enumerate(parts):
                    if c["val"] == max_val:
                        parts = parts[:i] + parts[i + 1 :]
                        break

        # 2.1 Handle Remaining/Balance (Virtual Count)
        if sentence_total is not None and analysis.has_remaining_other:
            current_sum = sum(c["val"] for c in parts)
            remainder = sentence_total - current_sum

            if remainder > 0:
                rem_match = next(
                    (
                        m
                        for m in analysis._matches
                        if m["type"] == MatchType.REMAINING_OTHER
                    ),
                    None,
                )
                if rem_match:
                    parts.append(
                        {
                            "val": remainder,
                            "span": rem_match["span"],
                            "type": MatchType.WORKER_COUNT,
                            "text": rem_match["text"],
                        }
                    )
                    # Re-sort parts by position
                    parts.sort(key=lambda x: x["span"][0])

        # 4. Pre-calculate Proximity Mapping
        # We do this early to detect if some entities are just descriptors (far from counts)
        # while others are targets (close to counts).
        proximity_map = {}
        if entities and parts:
            segments = get_text_segments(analysis.text)

            def get_seg_idx(pos):
                return next(
                    (i for i, (s, e, _) in enumerate(segments) if s <= pos < e), -1
                )

            # Pre-calculate counts per segment
            counts_in_segment = {}
            for c in parts:
                c_mid = get_midpoint(c["span"])
                s_idx = get_seg_idx(c_mid)
                counts_in_segment[s_idx] = counts_in_segment.get(s_idx, 0) + 1

            pairs = []
            for c in parts:
                c_mid = get_midpoint(c["span"])
                c_seg = get_seg_idx(c_mid)
                for e in entities:
                    e_mid = get_midpoint(e["span"])
                    e_seg = get_seg_idx(e_mid)
                    dist = abs(c_mid - e_mid)

                    # Penalize cross-segment matches
                    if c_seg != e_seg:
                        # Check for blocking counts in target or intermediate segments
                        # Also check if the separator is a "hard" separator (not a comma)
                        is_soft_boundary = True
                        start_seg, end_seg = sorted((c_seg, e_seg))
                        for i in range(start_seg, end_seg):
                            delim_text = segments[i][2]
                            if delim_text and delim_text != ",":
                                is_soft_boundary = False
                                break

                        has_blocking = False
                        if counts_in_segment.get(e_seg, 0) > 0:
                            has_blocking = True
                        else:
                            start, end = sorted((c_seg, e_seg))
                            for i in range(start + 1, end):
                                if counts_in_segment.get(i, 0) > 0:
                                    has_blocking = True
                                    break

                        if has_blocking or not is_soft_boundary:
                            dist += 1000
                        else:
                            dist *= 0.8

                    pairs.append((dist, c, e))

            pairs.sort(key=lambda x: x[0])
            used_c, used_e = set(), set()

            for dist, c, e in pairs:
                if dist < 150 and id(c) not in used_c and e["key"] not in used_e:
                    proximity_map[e["key"]] = c["val"]
                    used_c.add(id(c))
                    used_e.add(e["key"])

        return parts, sentence_total, proximity_map

    def _is_contained(
        self,
        container_key: str,
        item_key: str,
        excluded_keys: Optional[Set[str]] = None,
    ) -> bool:
        """
        Checks if item_key is geographically contained within container_key.
        """
        return is_contained(
            container_key, item_key, self.domestic_country_code, excluded_keys
        )

    def _remove_container_regions(
        self, entities: List[Dict[str, Any]], excluded_keys: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Removes entities that are containers of other entities in the list.
        Used to prevent double-counting in division operations.
        """
        if not entities:
            return []

        keep_indices = set()
        for i, e1 in enumerate(entities):
            is_container_of_others = False

            for j, e2 in enumerate(entities):
                if i == j:
                    continue

                if self._is_contained(e1["key"], e2["key"], excluded_keys):
                    is_container_of_others = True
                    break

            if not is_container_of_others:
                keep_indices.add(i)

        filtered = [entities[i] for i in sorted(keep_indices)]
        return filtered if filtered else entities

    def _preprocess_redundant_containers(
        self,
        entities: List[Dict[str, Any]],
        sentence_total: Optional[float],
        excluded_keys: Optional[Set[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        If no total was detected, and we have a region entity that contains all other
        entities in the list, it is likely a descriptor. Remove it to prevent it
        from absorbing counts meant for its constituents.
        """
        if sentence_total is None and len(entities) > 1:
            containers = []
            others = []

            # Identify potential containers
            for i, e in enumerate(entities):
                # Check if this entity contains ALL others
                contains_all = True
                for j, other in enumerate(entities):
                    if i == j:
                        continue
                    if not self._is_contained(e["key"], other["key"], excluded_keys):
                        contains_all = False
                        break

                if contains_all:
                    containers.append(i)

            if len(containers) == 1:
                c_idx = containers[0]
                return [
                    e for i, e in enumerate(entities) if i != c_idx
                ], "Removed Redundant Container"

        return entities, ""

    def _resolve_counts_generic(
        self,
        analysis: SentenceAnalysis,
        entities: List[Dict[str, Any]],
        total_key: Optional[str] = None,
        allow_naive_split: bool = False,
        use_labor_weights: bool = False,
        excluded_keys: Optional[Set[str]] = None,
        capacities: Optional[Dict[str, float]] = None,
    ) -> Tuple[Dict[str, float], Optional[float], List[str]]:
        """
        Refactored version of _resolve_counts_generic.
        """
        mapped_counts = {}

        # 1. Prepare Counts (Total detection + Virtual counts + Proximity Map)
        parts, sentence_total, proximity_map = self._prepare_counts(analysis, entities)

        if sentence_total is not None and total_key:
            # If we only have one entity, the "Total" likely belongs to it, not the generic scope
            if len(entities) == 1:
                entity_key = entities[0]["key"]
                mapped_counts[entity_key] = sentence_total
                # Return early to ignore subset parts for Census
                return (
                    mapped_counts,
                    sentence_total,
                    ["Inferred Total for Single Entity"],
                )
            else:
                mapped_counts[total_key] = sentence_total

        # --- Preprocess: Remove redundant container regions ---
        entities, preprocess_note = self._preprocess_redundant_containers(
            entities, sentence_total, excluded_keys
        )
        base_notes = [preprocess_note] if preprocess_note else []

        # --- Helper Strategies ---

        def try_exact_parallel(
            curr_parts, curr_entities
        ) -> Optional[Tuple[Dict[str, float], str]]:
            if len(curr_parts) == len(curr_entities):
                s_counts = sorted(curr_parts, key=lambda x: x["span"][0])
                s_entities = sorted(curr_entities, key=lambda x: x["span"][0])
                local_map = {}
                for c, e in zip(s_counts, s_entities):
                    local_map[e["key"]] = c["val"]
                return local_map, "Exact Parallel"
            return None

        def try_hierarchical_grouping(
            curr_parts, curr_entities, local_excluded_keys
        ) -> Optional[Tuple[Dict[str, float], str]]:
            if curr_entities:
                groups = group_by_scope(curr_entities, target_count=None)

                target_parts = curr_parts
                if groups and len(curr_parts) == len(groups) + 1:
                    vals = [c["val"] for c in curr_parts]
                    max_val = max(vals)
                    # Only remove if we don't have a global total
                    if sentence_total is None:
                        for i, c in enumerate(curr_parts):
                            if c["val"] == max_val:
                                target_parts = curr_parts[:i] + curr_parts[i + 1 :]
                                break

                if len(target_parts) == len(groups):
                    s_counts = sorted(target_parts, key=lambda x: x["span"][0])
                    local_map = {}
                    notes = ["Hierarchical Grouping"]
                    for c, group in zip(s_counts, groups):
                        head = group[0]
                        local_map[head["key"]] = c["val"]
                        children = group[1:]
                        if children:
                            # Filter out containers (e.g. CIS) if constituents (e.g. RU) are present
                            # This handles "Europe: CIS (Russia)" -> Distribute to Russia, ignore CIS container
                            valid_children = [
                                c
                                for c in self._remove_container_regions(
                                    children, local_excluded_keys
                                )
                                if not (
                                    local_excluded_keys
                                    and c["key"] in local_excluded_keys
                                )
                            ]

                            if not valid_children and children:
                                # If all children were excluded, skip weighted division
                                # so we don't force a single remaining entity to absorb counts.
                                if local_excluded_keys:
                                    continue
                                # Fallback only when no exclusions are active.
                                valid_children = children

                            if len(valid_children) == 1:
                                local_map[valid_children[0]["key"]] = c["val"]
                                continue

                            child_map, c_note = weighted_division(
                                c["val"],
                                valid_children,
                                use_labor_weights=use_labor_weights,
                                domestic_country=self.domestic_country_code,
                                excluded_keys=local_excluded_keys,
                                capacities=capacities,
                            )
                            local_map.update(child_map)
                            if c_note:
                                notes.append(c_note)
                    return local_map, " | ".join(notes)
            return None

        def try_list_grouping(
            curr_parts, curr_entities, local_excluded_keys
        ) -> Optional[Tuple[Dict[str, float], str]]:
            if curr_entities and curr_parts:
                s_entities = sorted(curr_entities, key=lambda x: x["span"][0])
                groups = []
                if s_entities:
                    current_group = [s_entities[0]]
                    for i in range(len(s_entities) - 1):
                        e1 = s_entities[i]
                        e2 = s_entities[i + 1]
                        start, end = e1["span"][1], e2["span"][0]

                        has_count_in_gap = any(
                            c["span"][0] >= start and c["span"][1] <= end
                            for c in curr_parts
                        )

                        is_connected = False
                        if not has_count_in_gap:
                            gid1 = e1.get("list_group_id")
                            gid2 = e2.get("list_group_id")
                            if gid1 is not None and gid1 == gid2:
                                is_connected = True
                            else:
                                text_between = analysis.text[start:end]
                                clean_text = re.sub(r"\s+", " ", text_between).strip()
                                is_sep = (
                                    bool(LIST_REGEX.search(clean_text))
                                    or not clean_text
                                )
                                if is_sep:
                                    is_connected = True

                        if is_connected:
                            current_group.append(e2)
                        else:
                            groups.append(current_group)
                            current_group = [e2]
                    groups.append(current_group)

                if len(groups) == len(curr_parts):
                    s_counts = sorted(curr_parts, key=lambda x: x["span"][0])
                    local_map = {}
                    filtered_note = ""
                    cluster_notes = []
                    for c, group in zip(s_counts, groups):
                        valid_group = self._remove_container_regions(
                            group, local_excluded_keys
                        )
                        valid_group = [
                            e
                            for e in valid_group
                            if not (
                                local_excluded_keys and e["key"] in local_excluded_keys
                            )
                        ]

                        if not valid_group and group:
                            # If all were excluded, skip weighted division
                            if local_excluded_keys:
                                continue
                            # Fallback only when no exclusions are active.
                            valid_group = group

                        if len(valid_group) == 1:
                            local_map[valid_group[0]["key"]] = c["val"]
                            continue

                        if len(valid_group) < len(group):
                            filtered_note = " (Filtered Containers)"
                        group_map, g_note = weighted_division(
                            c["val"],
                            valid_group,
                            use_labor_weights=use_labor_weights,
                            domestic_country=self.domestic_country_code,
                            excluded_keys=local_excluded_keys,
                            capacities=capacities,
                        )
                        local_map.update(group_map)
                        if g_note:
                            cluster_notes.append(g_note)

                    final_note = "List Grouping" + filtered_note
                    if cluster_notes:
                        final_note += " | " + "; ".join(cluster_notes)
                    return local_map, final_note
            return None

        def try_naive_split(
            curr_parts, curr_entities, local_excluded_keys
        ) -> Optional[Tuple[Dict[str, float], str]]:
            if allow_naive_split and len(curr_parts) == 1 and len(curr_entities) > 1:
                count_val = curr_parts[0]["val"]
                valid_entities = self._remove_container_regions(
                    curr_entities, local_excluded_keys
                )
                valid_entities = [
                    e
                    for e in valid_entities
                    if not (local_excluded_keys and e["key"] in local_excluded_keys)
                ]

                if not valid_entities and curr_entities:
                    # If all were excluded, skip weighted division
                    if local_excluded_keys:
                        return None
                    # Fallback only when no exclusions are active.
                    valid_entities = curr_entities

                if len(valid_entities) == 1:
                    return {valid_entities[0]["key"]: count_val}, "Naive Split (Single Entity)"

                filtered_note = ""
                if len(valid_entities) < len(curr_entities):
                    filtered_note = " (Filtered Containers)"
                local_map, w_note = weighted_division(
                    count_val,
                    valid_entities,
                    use_labor_weights=use_labor_weights,
                    domestic_country=self.domestic_country_code,
                    excluded_keys=local_excluded_keys,
                    capacities=capacities,
                )
                final_note = "Naive Split" + filtered_note
                if w_note:
                    final_note += f" | {w_note}"
                return local_map, final_note
            return None

        def resolve_subset(
            curr_parts, curr_entities, local_excluded_keys
        ) -> Tuple[Dict[str, float], str]:
            res = try_exact_parallel(curr_parts, curr_entities)
            if res:
                return res

            res = try_hierarchical_grouping(
                curr_parts, curr_entities, local_excluded_keys
            )
            if res:
                return res

            res = try_list_grouping(curr_parts, curr_entities, local_excluded_keys)
            if res:
                return res

            res = try_naive_split(curr_parts, curr_entities, local_excluded_keys)
            if res:
                return res

            # Fallback: Use global proximity map filtered for these entities
            local_map = {}
            for e in curr_entities:
                if e["key"] in proximity_map:
                    mapped_val = proximity_map[e["key"]]
                    if any(p["val"] == mapped_val for p in curr_parts):
                        local_map[e["key"]] = mapped_val
            return local_map, "Proximity Subset"

        def try_hard_boundary_split() -> Optional[Tuple[Dict[str, float], List[str]]]:
            if not parts or not entities:
                return None

            segments = get_text_segments(analysis.text)
            zones = []
            current_zone = [0]

            for i in range(len(segments) - 1):
                delim_text = segments[i][2]
                is_hard = True
                if delim_text == ",":
                    is_hard = False

                if is_hard:
                    zones.append(current_zone)
                    current_zone = [i + 1]
                else:
                    current_zone.append(i + 1)
            zones.append(current_zone)

            if len(zones) <= 1:
                return None

            combined_map = {}
            has_content = False
            notes = []

            for seg_indices in zones:
                z_start = segments[seg_indices[0]][0]
                z_end = segments[seg_indices[-1]][1]

                z_parts = [p for p in parts if z_start <= p["span"][0] < z_end]
                z_entities = [e for e in entities if z_start <= e["span"][0] < z_end]

                if z_parts or z_entities:
                    has_content = True
                    # Pass excluded_keys to allow filtering, relying on fallback logic if needed
                    zone_map, note = resolve_subset(z_parts, z_entities, excluded_keys)
                    combined_map.update(zone_map)
                    notes.append(note)

            if has_content:
                return combined_map, notes
            return None

        # --- Execution Flow ---

        # 1. Try Global Strategies
        res = try_exact_parallel(parts, entities)
        if res:
            return res[0], sentence_total, base_notes + [res[1]]

        res = try_hierarchical_grouping(parts, entities, excluded_keys)
        if res:
            return res[0], sentence_total, base_notes + [res[1]]

        res = try_list_grouping(parts, entities, excluded_keys)
        if res:
            return res[0], sentence_total, base_notes + [res[1]]

        # 2. Try Split & Retry
        res = try_hard_boundary_split()
        if res:
            return res[0], sentence_total, base_notes + ["Split by Boundary"] + res[1]

        # 3. Try Naive Split (Global)
        res = try_naive_split(parts, entities, excluded_keys)
        if res:
            return res[0], sentence_total, base_notes + [res[1]]

        # 4. Fallback to Proximity
        if not mapped_counts and proximity_map:
            return proximity_map, sentence_total, base_notes + ["Global Proximity"]

        return mapped_counts, sentence_total, base_notes

    def _resolve_counts_to_geography(
        self, analysis: SentenceAnalysis, capacities: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, float], Optional[float], List[str]]:
        """
        Refactored version of _resolve_counts_to_geography.
        """
        # Correlate GeoMatches with Spans (Explicit only)
        geo_entries = []
        excluded_codes = set()
        geo_match_objs = [
            m for m in analysis.geo_matches if m.source_type == GeoSource.EXPLICIT
        ]
        raw_geo_matches = [m for m in analysis._matches if m["type"] == MatchType.GEO]
        count_matches = [
            m
            for m in analysis._matches
            if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
        ]

        # Pre-calculate segments for exclusion refinement
        segments = get_text_segments(analysis.text)
        delimiter_spans = []
        for s_start, s_end, delim_text in segments:
            if delim_text:
                d_start = s_end - len(delim_text)
                delimiter_spans.append((d_start, s_end))

        def range_has_count(start, end):
            for m in analysis._matches:
                if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER):
                    if start <= m["span"][0] < end:
                        return True
            return False

        def range_has_remaining(start, end):
            for m in analysis._matches:
                if m["type"] == MatchType.REMAINING_OTHER:
                    if start <= m["span"][0] < end:
                        return True
            return False

        # Align matches (assuming order preservation in extraction)
        if len(geo_match_objs) == len(raw_geo_matches):
            # Pre-calculate strong codes for refinement
            strong_codes = {}
            for obj in geo_match_objs:
                if (
                    obj.geo_code
                    and not obj.geo_code.startswith(GeoCode.INT_LANG.value)
                    and obj.geo_code
                    not in [GeoCode.INTERNATIONAL.value, GeoCode.GLOBAL.value]
                ):
                    strong_codes[obj.geo_code] = obj

            for obj, raw in zip(geo_match_objs, raw_geo_matches):
                is_effectively_excluded = obj.is_excluded

                # Refine exclusion: If exclusion is a delimiter starting a segment with counts, treat as valid
                if is_effectively_excluded and obj.exclusion_group_id:
                    excl_match = next(
                        (
                            m
                            for m in analysis._matches
                            if id(m) == obj.exclusion_group_id
                        ),
                        None,
                    )
                    if excl_match:
                        e_start, e_end = excl_match["span"]
                        is_delimiter = False
                        for d_start, d_end in delimiter_spans:
                            if max(e_start, d_start) < min(e_end, d_end):
                                is_delimiter = True
                                break

                        if is_delimiter:
                            g_start = raw["span"][0]
                            for s_start, s_end, _ in segments:
                                if s_start <= g_start < s_end:
                                    if range_has_count(
                                        s_start, s_end
                                    ) and not range_has_remaining(s_start, s_end):
                                        is_effectively_excluded = False
                                    break

                if is_effectively_excluded:
                    should_exclude = True
                    if analysis.has_remaining_other:
                        should_exclude = False
                        # Targeted Patch: If exclusion is very close to "remaining", it modifies the remaining set
                        # e.g. "excluding Japan, the remaining..."
                        min_dist = get_min_distance_to_matches(
                            raw["span"],
                            analysis._matches,
                            [MatchType.REMAINING_OTHER],
                            text=analysis.text,
                        )
                        if min_dist < 40:
                            should_exclude = True

                    if should_exclude:
                        if obj.geo_code:
                            excluded_codes.add(obj.geo_code)
                    # Do not continue; allow mapping to specific counts, but exclude from distribution via excluded_keys

                # Refine INT_ codes
                if obj.geo_code:
                    candidates = [
                        {"code": o.geo_code, "name": o.country}
                        for o in strong_codes.values()
                    ]
                    refined_code, _ = refine_generic_code(obj.geo_code, candidates)
                    if refined_code != obj.geo_code:
                        obj = strong_codes[refined_code]

                # Use Region Name for generic accumulators, Code for countries
                key = obj.geo_code
                if obj.geo_code in REGION_CODES and obj.geo_code not in DOMESTIC_SET:
                    key = obj.region.value

                geo_entries.append(
                    {
                        "key": key,
                        "span": raw["span"],
                        "region_enum": obj.region,
                        "list_group_id": obj.list_group_id,
                    }
                )

        # Prefer explicitly linked geo counts over positional inference.
        linked_map: Dict[str, float] = {}
        if geo_entries and count_matches:
            geo_link_map: Dict[Any, List[str]] = {}

            def _add_geo_link(link_id: Any, key: str) -> None:
                if link_id is None:
                    return
                lst = geo_link_map.setdefault(link_id, [])
                if key not in lst:
                    lst.append(key)

            for obj, raw in zip(geo_match_objs, raw_geo_matches):
                key = obj.geo_code or ""
                if obj.geo_code in REGION_CODES and obj.geo_code not in DOMESTIC_SET:
                    key = obj.region.value
                if obj.list_group_id:
                    _add_geo_link(obj.list_group_id, key)
                _add_geo_link(id(obj), key)
                if raw.get("geo_obj") is not None:
                    _add_geo_link(id(raw["geo_obj"]), key)

            for c in count_matches:
                link_id = c.get("linked_geo_group_id")
                if not link_id:
                    continue
                keys = geo_link_map.get(link_id, [])
                if len(keys) != 1:
                    continue
                key = keys[0]
                linked_map[key] = max(linked_map.get(key, 0.0), float(c["val"]))

            # Only early-return with pure linked_map when there is NO remaining_other logic needed.
            # If we have a remaining clause, we MUST let _resolve_counts_generic handle total + virtual remainder.
            has_remaining = getattr(analysis, 'has_remaining_other', False)

            if linked_map and not has_remaining:
                unlinked_counts = [
                    c for c in count_matches if not c.get("linked_geo_group_id")
                ]
                if not unlinked_counts:
                    return linked_map, None, ["Linked Geo Counts"]

                first_geo_start = min(e["span"][0] for e in geo_entries)
                pre_geo_unlinked = [
                    c for c in unlinked_counts if c["span"][0] < first_geo_start
                ]
                # If all unlinked counts are pre-geo, treat the largest as a global total
                # and avoid naive remapping of linked counts to other geos.
                if len(pre_geo_unlinked) == len(unlinked_counts):
                    total_val = max(c["val"] for c in pre_geo_unlinked)
                    mapped_counts = dict(linked_map)
                    if total_val is not None:
                        mapped_counts[GeoCode.GLOBAL.value] = float(total_val)
                    return mapped_counts, float(total_val), [
                        "Linked Geo Counts",
                        "Pre-Geo Total",
                    ]

        # If we reach here, either:
        # - There was no clean linked_map, or
        # - has_remaining_other is True (critical for "remaining" cases)
        return self._resolve_counts_generic(
            analysis,
            geo_entries,
            total_key=GeoCode.GLOBAL.value,
            allow_naive_split=True,
            excluded_keys=excluded_codes,
            capacities=capacities,
        )

    def _map_assignments_to_geo(
        self,
        analysis: SentenceAnalysis,
        assignments: List[Dict],
        geo_capacities: Optional[Dict[str, float]] = None,
    ) -> List[Dict]:
        """
        Refactored version of _map_assignments_to_geo.
        """
        geo_match_objs = [
            m for m in analysis.geo_matches if m.source_type == GeoSource.EXPLICIT
        ]
        raw_geo_matches = [m for m in analysis._matches if m["type"] == MatchType.GEO]

        aligned_geos = []
        # Align matches (assuming order preservation)
        if len(geo_match_objs) == len(raw_geo_matches):
            # Pre-calculate strong codes for refinement
            strong_codes = {}
            for obj in geo_match_objs:
                if (
                    obj.geo_code
                    and not obj.geo_code.startswith(GeoCode.INT_LANG.value)
                    and obj.geo_code
                    not in [GeoCode.INTERNATIONAL.value, GeoCode.GLOBAL.value]
                ):
                    strong_codes[obj.geo_code] = obj

            for obj, raw in zip(geo_match_objs, raw_geo_matches):
                # Refine INT_ codes
                if obj.geo_code:
                    candidates = [
                        {"code": o.geo_code, "name": o.country}
                        for o in strong_codes.values()
                    ]
                    refined_code, _ = refine_generic_code(obj.geo_code, candidates)
                    if refined_code != obj.geo_code:
                        obj = strong_codes[refined_code]

                aligned_geos.append({"obj": obj, "span": raw["span"]})
        else:
            return []

        def _split_linked_value(
            total_val: float, country_codes: List[str]
        ) -> Dict[str, float]:
            """
            Split a linked assignment across multiple countries.
            Prefer capacity-weighted splits when lookup totals are available.
            """
            if not country_codes:
                return {}
            if len(country_codes) == 1:
                return {country_codes[0]: float(total_val)}

            caps = geo_capacities or {}
            weights = [
                max(0.0, float(caps.get(code, 0.0) or 0.0)) for code in country_codes
            ]
            total_weight = sum(weights)
            if total_weight <= 0:
                weights = [1.0] * len(country_codes)
                total_weight = float(len(country_codes))

            raw = [float(total_val) * (w / total_weight) for w in weights]
            is_integer_total = abs(float(total_val) - round(float(total_val))) < 1e-9

            if is_integer_total:
                floor_vals = [int(v) for v in raw]
                remainder = int(round(float(total_val))) - sum(floor_vals)
                fractional_order = sorted(
                    range(len(raw)),
                    key=lambda i: (raw[i] - floor_vals[i]),
                    reverse=True,
                )
                for i in fractional_order[: max(0, remainder)]:
                    floor_vals[i] += 1
                return {
                    code: float(val) for code, val in zip(country_codes, floor_vals)
                }

            rounded = [round(v, 2) for v in raw]
            drift = round(float(total_val) - sum(rounded), 2)
            if abs(drift) > 0:
                max_idx = max(range(len(rounded)), key=lambda i: rounded[i])
                rounded[max_idx] = round(rounded[max_idx] + drift, 2)
            return {code: val for code, val in zip(country_codes, rounded)}

        # NEW: Handle Linked Assignments First
        mapped_splits = []
        remaining_assignments = []
        used_geo_indices = set()

        # Create a map of geo_group_id/obj_id to indexes in aligned_geos.
        # A list group id can legitimately map to multiple geographies.
        geo_id_map: Dict[Any, List[int]] = {}
        for i, g in enumerate(aligned_geos):
            obj = g["obj"]
            if obj.list_group_id:
                geo_id_map.setdefault(obj.list_group_id, []).append(i)
            geo_id_map.setdefault(id(obj), []).append(i)

        for item in assignments:
            m = item["match"]
            link_id = m.get("linked_geo_group_id")

            if link_id and link_id in geo_id_map:
                geo_indices = geo_id_map[link_id]
                linked_geos = [aligned_geos[idx] for idx in geo_indices]

                # Prefer concrete country codes for linked list splits.
                concrete = []
                for g in linked_geos:
                    obj = g["obj"]
                    if (
                        obj.geo_code
                        and obj.geo_code not in REGION_CODES
                        and obj.geo_code not in IGNORED_REGIONS
                    ):
                        concrete.append(obj)
                split_targets = concrete or [g["obj"] for g in linked_geos]

                # Deduplicate while preserving order
                dedup_targets = []
                seen_codes = set()
                for obj in split_targets:
                    if obj.geo_code in seen_codes:
                        continue
                    seen_codes.add(obj.geo_code)
                    dedup_targets.append(obj)

                raw_val = float(item.get("override_val", item["match"]["val"]))
                target_codes = [obj.geo_code for obj in dedup_targets if obj.geo_code]
                split_vals = _split_linked_value(raw_val, target_codes)

                for obj in dedup_targets:
                    if not obj.geo_code:
                        continue
                    note = f"Mapped to {obj.country} (Linked)"
                    if len(dedup_targets) > 1:
                        note += " | Split across linked geos"
                    mapped_splits.append(
                        {
                            "val": split_vals.get(obj.geo_code, raw_val),
                            "type": item["type"],
                            "region": obj.region.value,
                            "countries": [
                                {
                                    "name": obj.country,
                                    "code": obj.geo_code,
                                    "locations": [],
                                }
                            ],
                            "note": note,
                        }
                    )

                used_geo_indices.update(geo_indices)
                continue

            remaining_assignments.append(item)

        # If we have mapped splits, check if we can return them
        if mapped_splits:
            # Allow return if remaining assignments are only totals (likely global/aggregate totals)
            # or if we have no remaining assignments
            if not remaining_assignments or all(
                a["type"] == "total" for a in remaining_assignments
            ):
                return mapped_splits

        # Filter aligned_geos for fallback logic
        remaining_geos = [
            g for i, g in enumerate(aligned_geos) if i not in used_geo_indices
        ]

        # 1. Respectively Logic (Explicit OR Implicit if counts == geos)
        # If we have equal number of remaining assignments and locations, assume 1-to-1 mapping in order
        if (
            len(remaining_assignments) == len(remaining_geos)
            and len(remaining_assignments) > 0
        ):
            # Sort both by position
            s_assign = sorted(
                remaining_assignments, key=lambda x: x["match"]["span"][0]
            )
            s_geos = sorted(remaining_geos, key=lambda x: x["span"][0])

            for item, g in zip(s_assign, s_geos):
                obj = g["obj"]

                note = f"Mapped to {obj.country}"
                mapped_splits.append(
                    {
                        "val": item.get("override_val", item["match"]["val"]),
                        "type": item["type"],
                        "region": obj.region.value,
                        "countries": [
                            {"name": obj.country, "code": obj.geo_code, "locations": []}
                        ],
                        "note": note,
                    }
                )
            return mapped_splits

        # If linked mapping produced usable splits but the fallback mapping couldn't
        # resolve the remainder, keep the linked splits instead of dropping all splits.
        if mapped_splits:
            return mapped_splits

        return []

    def _resolve_counts_to_unions(
        self, analysis: SentenceAnalysis
    ) -> Tuple[Dict[str, float], Optional[float], List[str]]:
        """
        Intelligently maps worker counts to union entities within the sentence.
        """
        # Identify Union Matches
        union_matches = [
            m
            for m in analysis._matches
            if m["type"] in (MatchType.SPECIFIC_UNION, MatchType.UNION_NAME)
        ]

        union_entries = [{"key": m["text"], "span": m["span"]} for m in union_matches]
        return self._resolve_counts_generic(
            analysis, union_entries, allow_naive_split=True, use_labor_weights=True
        )

    def _resolve_counts_to_types(self, analysis: SentenceAnalysis) -> Dict[str, float]:
        """Maps worker counts to worker types (e.g. '112' -> 'hourly')."""
        mapping: Dict[str, float] = {}
        counts = [
            m
            for m in analysis._matches
            if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
        ]

        worker_matches: List[Dict[str, Any]] = []

        # Include WORKER_TYPE and specific WORKER_TERM (e.g. pilots, teachers)
        for m in analysis._matches:
            m_type = m["type"]
            if m_type == MatchType.WORKER_TYPE:
                worker_matches.append(m)
            elif m_type == MatchType.WORKER_TERM:
                val_lower = m["val"].lower()
                if (
                    val_lower not in GENERIC_WORKER_TERMS
                    and val_lower.rstrip("s") not in GENERIC_WORKER_TERMS
                ):
                    worker_matches.append(m)

        if not counts or not worker_matches:
            return {}

        used_c = set()
        used_t = set()

        def _set_mapping(type_key: str, value: float) -> None:
            # Keep the larger value when duplicate terms are encountered.
            mapping[type_key] = max(mapping.get(type_key, 0.0), value)

        # 1. Link by worker_group_id (Strongest link, provided by extractor)
        for t in worker_matches:
            gid = t.get("worker_group_id")
            if not gid:
                continue

            candidates = [
                c
                for c in counts
                if c.get("worker_group_id") == gid and id(c) not in used_c
            ]
            if not candidates or id(t) in used_t:
                continue

            t_mid = get_midpoint(t["span"])
            c = min(candidates, key=lambda x: abs(get_midpoint(x["span"]) - t_mid))
            _set_mapping(t["val"].lower(), c["val"])
            used_c.add(id(c))
            used_t.add(id(t))

        pairs = []
        for c in counts:
            if id(c) in used_c:
                continue
            c_mid = get_midpoint(c["span"])
            for t in worker_matches:
                if id(t) in used_t:
                    continue
                t_mid = get_midpoint(t["span"])
                dist = abs(c_mid - t_mid)
                pairs.append((dist, c, t))

        pairs.sort(key=lambda x: x[0])

        for dist, c, t in pairs:
            if dist < 50 and id(c) not in used_c and id(t) not in used_t:
                _set_mapping(t["val"].lower(), c["val"])
                used_c.add(id(c))
                used_t.add(id(t))

        return mapping

    def _merge_continuation_items(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Post-processing: Merge continuation items (Fix for split sentences)
        e.g. "In Germany we have X employees." -> "They are covered by Y."
        """
        merged_results = []
        skip_indices = set()

        for i in range(len(results)):
            if i in skip_indices or "geographic_context" not in results[i]:
                continue
            current = results[i]
            anchor_sentence_indices = {
                sidx for sidx in [current.get("sentence_index")] if sidx is not None
            }
            j = i + 1
            while j < len(results):
                if j in skip_indices:
                    j += 1
                    continue

                next_item = results[j]
                # Stop merging when stream changes (e.g. risk rows or unrelated payloads)
                if "geographic_context" not in next_item:
                    break

                # Stop if one sentence is union related and the other isn't.
                cur_is_union = current.get("is_union", False)
                next_is_union = next_item.get("is_union", False)
                if cur_is_union and cur_is_union != next_is_union:
                    break

                # Criteria: next item inherits from one of the merged sentence anchors
                c_pct = current["coverage_data"].get("percentage")
                is_saturated = c_pct == 100.0
                is_empty = c_pct == 0.0
                inherited_from = next_item["geographic_context"].get(
                    "inherited_from_sentence_index"
                )
                if not (
                    next_item["geographic_context"]["specificity"]
                    == Specificity.INHERITED.value
                    and inherited_from in anchor_sentence_indices
                    and not is_saturated
                    and not is_empty
                    and not next_item.get("is_remaining", False)
                ):
                    break

                c_data = current["coverage_data"]
                n_data = next_item["coverage_data"]

                # Guard: do not convert a pure employment baseline sentence
                # (count only, no union signal) into a union block by merging
                # with adjacent no-data union-language continuations.
                current_is_employment_baseline = (
                    bool(current.get("potential_total"))
                    and not current.get("keyword_matched")
                    and not current.get("is_union", False)
                    and c_data.get("percentage") is None
                    and c_data.get("employee_count_covered") is None
                    and c_data.get("employee_count_not_covered") is None
                    and c_data.get("employee_count_total") is None
                )
                next_has_quantitative_data = any(
                    n_data.get(k) is not None
                    for k in (
                        "percentage",
                        "employee_count_covered",
                        "employee_count_not_covered",
                        "employee_count_total",
                    )
                )
                has_type_inference_signal = (
                    bool(next_item.get("keyword_matched"))
                    and bool(current.get("worker_type_map"))
                    and (
                        bool(next_item.get("worker_types"))
                        or bool(next_item.get("worker_terms"))
                    )
                )
                if (
                    current_is_employment_baseline
                    and not next_has_quantitative_data
                    and not has_type_inference_signal
                ):
                    break
                # Guard: avoid merging a global baseline + worker-type composition
                # with a subsequent union-coverage sentence scoped to that worker-type.
                # This prevents using a global total as the denominator for a subset.
                if (
                    current_is_employment_baseline
                    and next_has_quantitative_data
                    and (
                        bool(next_item.get("worker_types"))
                        or bool(next_item.get("worker_terms"))
                    )
                ):
                    break

                should_merge = True

                # 1. Data Collision Check
                # Do not merge if both items have data for the same field
                if (
                    c_data["percentage"] is not None
                    and n_data["percentage"] is not None
                ):
                    should_merge = False
                if (
                    c_data["employee_count_covered"] is not None
                    and n_data["employee_count_covered"] is not None
                ):
                    should_merge = False
                if (
                    c_data["employee_count_not_covered"] is not None
                    and n_data["employee_count_not_covered"] is not None
                ):
                    should_merge = False
                # If both have a total, don't merge
                if (
                    c_data["employee_count_total"] is not None
                    and n_data["employee_count_total"] is not None
                ):
                    should_merge = False

                # 2. Subject Conflict Check (Specific Unions)
                if should_merge:
                    k_curr = current.get("keyword_matched")
                    k_next = next_item.get("keyword_matched")
                    if k_curr and k_next:
                        specific_curr = {t for t in k_curr if self.matcher.get_union(t)}
                        specific_next = {t for t in k_next if self.matcher.get_union(t)}
                        if (
                            specific_curr
                            and specific_next
                            and specific_curr.isdisjoint(specific_next)
                        ):
                            should_merge = False

                # 3. Worker Term Conflict Check
                if should_merge:
                    w_curr = current.get("worker_terms", [])
                    w_next = next_item.get("worker_terms", [])

                    if w_curr and w_next:
                        spec_curr = {
                            w.lower()
                            for w in w_curr
                            if w.lower() not in GENERIC_WORKER_TERMS
                            and w.lower().rstrip("s") not in GENERIC_WORKER_TERMS
                        }
                        spec_next = {
                            w.lower()
                            for w in w_next
                            if w.lower() not in GENERIC_WORKER_TERMS
                            and w.lower().rstrip("s") not in GENERIC_WORKER_TERMS
                        }

                        if spec_curr and spec_next and spec_curr.isdisjoint(spec_next):
                            should_merge = False

                if not should_merge:
                    break

                # Merge Percentage
                if c_data["percentage"] is None and n_data["percentage"] is not None:
                    c_data["percentage"] = n_data["percentage"]
                    c_data["negated"] = n_data["negated"]
                    c_data["negation_type"] = n_data["negation_type"]
                    c_data["type"] = n_data["type"]
                    c_data["note"] = (
                        (c_data["note"] or "") + " | " + (n_data["note"] or "")
                    )

                # Merge Counts
                if (
                    not c_data["employee_count_covered"]
                    and n_data["employee_count_covered"]
                ):
                    c_data["employee_count_covered"] = n_data["employee_count_covered"]

                # Use potential total from current sentence if available, but only when neither entry provides a total.
                if (
                    not c_data.get("employee_count_total")
                    and not n_data.get("employee_count_total")
                    and current.get("potential_total")
                ):
                    c_data["employee_count_total"] = current["potential_total"]
                    c_data["note"] = (
                        c_data.get("note") or ""
                    ) + f" | Used local count {current['potential_total']}"

                if (
                    not c_data["employee_count_not_covered"]
                    and n_data["employee_count_not_covered"]
                ):
                    c_data["employee_count_not_covered"] = n_data[
                        "employee_count_not_covered"
                    ]

                # Recalculate missing values if percentage is present
                if c_data["percentage"] is not None:
                    pct = c_data["percentage"]
                    total = c_data.get("employee_count_total")
                    covered = c_data.get("employee_count_covered")
                    not_covered = c_data.get("employee_count_not_covered")
                    is_negated = c_data.get("negated")
                    neg_type = c_data.get("negation_type")

                    # Case 1: Have Total + Pct -> Calculate Parts
                    if total and (covered is None or not_covered is None):
                        subset = round((pct / 100.0) * total)
                        infer_complement = should_infer_complement(
                            pct,
                            c_data.get("type") == CoverageType.QUALITATIVE.value,
                            is_negated,
                            c_data.get("has_exceptions", False),
                        )

                        if c_data.get("has_exceptions") and pct >= 99.0:
                            pct = 95.0
                            c_data["note"] = (
                                c_data.get("note") or ""
                            ) + " | Downgraded 100%->95% (exception)"

                        if is_negated:
                            if neg_type == NegationType.ZERO_COVERAGE.value:
                                if covered is None:
                                    c_data["employee_count_covered"] = 0
                                if not_covered is None:
                                    c_data["employee_count_not_covered"] = total
                            else:
                                if not_covered is None:
                                    c_data["employee_count_not_covered"] = subset
                                if covered is None and infer_complement:
                                    c_data["employee_count_covered"] = total - subset
                        else:
                            if covered is None:
                                c_data["employee_count_covered"] = subset
                            if not_covered is None:
                                c_data["employee_count_not_covered"] = total - subset
                        c_data["note"] = (
                            c_data.get("note") or ""
                        ) + " | Derived counts from merged %"

                    # Case 2: Have Part + Pct -> Calculate Total (Denominator)
                    elif not total and pct > 0:
                        derived_total = None
                        if (
                            is_negated
                            and neg_type != NegationType.ZERO_COVERAGE.value
                            and not_covered is not None
                        ):
                            derived_total = round(not_covered / (pct / 100.0))
                            c_data["employee_count_covered"] = (
                                derived_total - not_covered
                            )
                        elif not is_negated and covered is not None:
                            derived_total = round(covered / (pct / 100.0))
                            c_data["employee_count_not_covered"] = (
                                derived_total - covered
                            )

                        if derived_total is not None:
                            c_data["employee_count_total"] = derived_total
                            c_data["note"] = (
                                c_data.get("note") or ""
                            ) + " | Derived total from merged %"

                    # Case 3: Refinement (Assumed 100% -> Actual %)
                    elif total and pct > 0 and pct < 100:
                        if covered == total:
                            derived_total = round(covered / (pct / 100.0))
                            c_data["employee_count_total"] = derived_total
                            c_data["employee_count_not_covered"] = (
                                derived_total - covered
                            )
                            c_data["note"] = (
                                (c_data.get("note") or "")
                                + f" | Refined Total from {total} to {derived_total} using {pct}%"
                            )
                        elif not_covered == total:
                            if is_negated:
                                derived_total = round(not_covered / (pct / 100.0))
                                c_data["employee_count_total"] = derived_total
                                c_data["employee_count_covered"] = (
                                    derived_total - not_covered
                                )
                                c_data["note"] = (
                                    (c_data.get("note") or "")
                                    + f" | Refined Total from {total} to {derived_total} using {pct}% (negated)"
                                )
                            else:
                                derived_total = round(
                                    not_covered / ((100 - pct) / 100.0)
                                )
                                c_data["employee_count_total"] = derived_total
                                c_data["employee_count_covered"] = (
                                    derived_total - not_covered
                                )
                                c_data["note"] = (
                                    (c_data.get("note") or "")
                                    + f" | Refined Total from {total} to {derived_total} using {pct}% (remainder)"
                                )

                # Type-based coverage inference
                targets = set(next_item.get("worker_types", []))
                for w in next_item.get("worker_terms", []):
                    if (
                        w.lower() not in GENERIC_WORKER_TERMS
                        and w.lower().rstrip("s") not in GENERIC_WORKER_TERMS
                    ):
                        targets.add(w)

                if next_item.get("keyword_matched") and targets:
                    c_map = current.get("worker_type_map", {})
                    matched_count = 0.0
                    found_match = False

                    for w_type in targets:
                        w_type_lower = w_type.lower()
                        if w_type_lower in c_map:
                            matched_count += c_map[w_type_lower]
                            found_match = True

                    if found_match:
                        target_field = (
                            "employee_count_not_covered"
                            if n_data.get("negated")
                            else "employee_count_covered"
                        )
                        current_val = c_data.get(target_field) or 0.0
                        c_data[target_field] = current_val + matched_count

                        if c_data.get("employee_count_total"):
                            cov = c_data.get("employee_count_covered") or 0.0
                            c_data["percentage"] = round(
                                (cov / c_data["employee_count_total"]) * 100, 2
                            )
                            c_data["type"] = CoverageType.CALCULATED.value
                            c_data["note"] = (
                                (c_data.get("note") or "")
                                + f" | Inferred coverage for {matched_count} (matched types)"
                            )

                merge_note = f" [Merged with next sentence: '{next_item.get('sentence', '')[:30]}...']"
                c_data["note"] = (c_data.get("note") or "") + merge_note
                current["merged_sentence_index"] = next_item.get("sentence_index")

                if next_item.get("is_union"):
                    current["is_union"] = True

                n_idx = next_item.get("sentence_index")
                if n_idx is not None:
                    anchor_sentence_indices.add(n_idx)

                skip_indices.add(j)
                j += 1

            merged_results.append(current)
        return merged_results

    def _apply_splitting_logic(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Applies split_ambiguous_entry to all items in the list.
        """
        final_results = []
        for item in results:
            split_items = split_ambiguous_entry(item)
            final_results.extend(split_items)
        return final_results

    def _analyze_block(
        self,
        sentences: List[str],
        reporting_year: Optional[int] = None,
        global_max_workers: float = 0.0,
        external_total: Optional[float] = None,
        initial_geo_context: Optional[Dict] = None,
        initial_geo_sentence_idx: int = -1,
        previous_totals: Optional[Dict[str, float]] = None,
        start_index: int = 0,
        cik: Optional[int] = None,
    ) -> Tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Dict[str, float],
        Optional[Dict],
        int,
    ]:
        """
        Analyzes a block of sentences (paragraph) for Item 1.
        Returns results, totals found in THIS block, and the final geo context.
        """
        # 0. Local Census (Pre-scan paragraph)
        local_tracker = Tracker(domestic_country_code=self.domestic_country_code)
        self._populate_tracker(
            sentences,
            local_tracker,
            reporting_year,
            initial_geo_context=initial_geo_context,
            emp_count=external_total,
        )
        local_tracker.resolve()

        results = []
        risk_items = []
        analyzed_sentences = [self.extractor.analyze_sentence(s, emp_count=external_total) for s in sentences]

        # Context inheritance state
        last_geo_context = initial_geo_context
        last_geo_sentence_idx = initial_geo_sentence_idx
        last_employee_count = None

        # Totals found strictly within this block (prevent double counting)
        local_totals = {}
        local_totals.update(local_tracker.region_totals)
        local_totals.update(local_tracker.country_totals)

        # Effective totals for lookup (Previous Paragraph + Local So Far)
        effective_totals = previous_totals.copy() if previous_totals else {}
        for k, v in local_totals.items():
            if v > effective_totals.get(k, 0):
                effective_totals[k] = v

        # Worker type lookup for cross-sentence inference
        worker_type_lookup: Dict[str, Dict[str, float]] = {}
        worker_type_total_lookup: Dict[str, float] = {}

        prev_sentence_geo_key: Optional[Tuple[str, ...]] = None
        prev_sentence_has_explicit = False

        def _normalize_country_code(code: Optional[str]) -> Optional[str]:
            if not code:
                return None
            return (
                self.domestic_country_code if code == GeoCode.DOMESTIC.value else code
            )

        def _geo_key(ctx: Dict[str, Any]) -> Optional[Tuple[str, ...]]:
            if not ctx:
                return None
            countries = ctx.get("countries") or []
            codes = sorted(
                c.get("code")
                for c in countries
                if c.get("code")
            )
            if codes:
                return tuple(f"C:{c}" for c in codes)
            region = ctx.get("region")
            if region and region not in UNK_SET:
                return (f"R:{region}",)
            return None

        def _worker_lookup_keys(ctx: Dict[str, Any]) -> List[str]:
            keys: List[str] = []
            countries = ctx.get("countries", []) or []
            for c in countries:
                c_code = _normalize_country_code(c.get("code"))
                if c_code:
                    keys.append(f"C:{c_code}")

            region_name = ctx.get("region")
            if region_name and region_name not in UNK_SET:
                keys.append(f"R:{region_name}")

            for r in ctx.get("regions", []) or []:
                r_code = r.get("code")
                r_name = r.get("name")
                if r_code:
                    keys.append(f"R:{r_code}")
                if r_name:
                    keys.append(f"R:{r_name}")

            # Preserve insertion order while removing duplicates
            return list(dict.fromkeys(keys))

        def _collect_explicit_pct_entries(
            analysis: SentenceAnalysis,
            geo_context: Dict[str, Any],
            cov_data: Dict[str, Any],
            sentence_index: int,
        ) -> List[Dict[str, Any]]:
            countries = geo_context.get("countries", []) or []
            if len(countries) <= 1:
                return []
            if not analysis.percentages:
                return []

            # Build geo list_group_id -> geo_code map from aligned explicit geos
            geo_match_objs = [
                m for m in analysis.geo_matches if m.source_type == GeoSource.EXPLICIT
            ]
            raw_geo_matches = [m for m in analysis._matches if m.get("type") == MatchType.GEO]
            geo_gid_to_code: Dict[Any, str] = {}
            def _add_geo_gid(gid: Any, code: str) -> None:
                if gid is None or not code:
                    return
                if gid not in geo_gid_to_code:
                    geo_gid_to_code[gid] = code
            if len(geo_match_objs) == len(raw_geo_matches):
                for obj, raw in zip(geo_match_objs, raw_geo_matches):
                    code = obj.geo_code
                    if not code:
                        continue
                    if code == GeoCode.DOMESTIC.value:
                        code = self.domestic_country_code
                    _add_geo_gid(obj.list_group_id or id(obj), code)
                    if raw.get("geo_obj") is not None:
                        _add_geo_gid(id(raw["geo_obj"]), code)

            # Try direct linking via linked_geo_group_id on percent matches
            pct_matches = [m for m in analysis._matches if m.get("type") == MatchType.PERCENT]
            linked_map: Dict[str, float] = {}
            derived_counts: Dict[str, Dict[str, float]] = {}
            for pm in pct_matches:
                link_id = pm.get("linked_geo_group_id")
                if link_id and link_id in geo_gid_to_code:
                    code = geo_gid_to_code[link_id]
                    linked_map[code] = float(pm["val"])

            # If percent is grouped with a count (e.g., "10% of 700") and linked to a geo,
            # carry derived counts for later reported_totals usage.
            groups: Dict[Any, List[Dict[str, Any]]] = {}
            for m in analysis._matches:
                gid = m.get("numeric_group_id")
                if gid:
                    groups.setdefault(gid, []).append(m)

            for group in groups.values():
                counts = [
                    m for m in group
                    if m.get("type") in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                ]
                percents = [m for m in group if m.get("type") == MatchType.PERCENT]
                if len(counts) != 1 or len(percents) != 1:
                    continue
                pct_match = percents[0]
                count_match = counts[0]
                link_id = (
                    pct_match.get("linked_geo_group_id")
                    or count_match.get("linked_geo_group_id")
                )
                if not link_id or link_id not in geo_gid_to_code:
                    continue
                code = geo_gid_to_code[link_id]
                total_val = float(count_match["val"])
                pct_val = float(pct_match["val"])
                covered_val = round((pct_val / 100.0) * total_val)
                not_covered_val = max(0.0, total_val - covered_val)
                existing = derived_counts.get(code)
                if existing is None or total_val > existing.get("total", 0.0):
                    derived_counts[code] = {
                        "total": total_val,
                        "covered": covered_val,
                        "not_covered": not_covered_val,
                    }

            explicit_geo_codes = [
                (obj.geo_code if obj.geo_code != GeoCode.DOMESTIC.value else self.domestic_country_code)
                for obj in geo_match_objs if obj.geo_code
            ]
            # Accept linked map only when it covers all explicit geos
            if linked_map and len(linked_map) == len(set(explicit_geo_codes)):
                return [
                    {
                        "geo_code": code,
                        "percentage": pct,
                        "sentence_index": sentence_index,
                        "note": "Explicit percent linked via geo proximity",
                        "derived_total": (derived_counts.get(code) or {}).get("total"),
                        "derived_covered": (derived_counts.get(code) or {}).get("covered"),
                        "derived_not_covered": (derived_counts.get(code) or {}).get("not_covered"),
                        "derived_source": "linked_group_calc" if code in derived_counts else None,
                    }
                    for code, pct in linked_map.items()
                ]

            # Fallback: require explicit-percent coverage signal
            if not (
                cov_data.get("is_explicit_percent")
                or cov_data.get("type") == CoverageType.EXPLICIT_PERCENT.value
            ):
                return []

            pct_map = self.geo_population_resolver._map_percentages_to_geo_codes(
                analysis, allow_sum=False
            )
            if not pct_map:
                return []
            if len(pct_map) < len(set(explicit_geo_codes)):
                return []

            return [
                {
                    "geo_code": code,
                    "percentage": float(pct),
                    "sentence_index": sentence_index,
                    "note": "Explicit percent in mixed-geo sentence",
                }
                for code, pct in pct_map.items()
            ]

        for idx, analysis in enumerate(analyzed_sentences):
            sent = sentences[idx]
            current_idx = start_index + idx
            suppress_clause_numbers = False

            # 1. Historical Check
            is_historical = False
            years_indicate_past = False
            if reporting_year and analysis.years:
                if all(y < reporting_year for y in analysis.years):
                    years_indicate_past = True

            if (
                years_indicate_past or analysis.has_historical
            ) and not analysis.has_current:
                is_historical = True
            if is_historical:
                for k in range(idx, len(analyzed_sentences)):
                    r_analysis = analyzed_sentences[k]
                    r_sent = sentences[k]
                    risk_item = self.extra_analyzer.create_risk_item(
                        r_sent,
                        r_analysis,
                        is_historical=True,
                        item1a_mode=False,
                    )
                    if risk_item:
                        risk_item["sentence_index"] = start_index + k
                        risk_items.append(risk_item)
                break

            risk_item = self.extra_analyzer.create_risk_item(
                sent,
                analysis,
                is_historical=False,
                item1a_mode=False,
            )
            if risk_item:
                risk_item["sentence_index"] = current_idx
                risk_items.append(risk_item)

            # 2. Update Context (Worker Counts)
            effective_counts = get_effective_counts(analysis)
            current_sentence_count = None
            if effective_counts and not is_historical:
                range_avg = self._detect_count_range(analysis, effective_counts)
                summation = self._detect_summation(analysis, effective_counts)
                if range_avg is not None:
                    current_sentence_count = range_avg
                elif summation is not None:
                    current_sentence_count = summation
                else:
                    current_sentence_count = max(effective_counts)

            # 3. Relevance Check
            if not analysis.is_relevant:
                # Allow geo-only sentences to update paragraph context
                # (e.g., "We operate in China." -> applies to following relevant sentences)
                if analysis.geo_matches:
                    geo_context = self._determine_geo_context(
                        analysis, last_geo_context, current_idx, last_geo_sentence_idx
                    )
                    is_strong_geo = geo_context["specificity"] in (
                        Specificity.EXPLICIT.value,
                        Specificity.INFERRED_UNION.value,
                        Specificity.EXPLICIT_INFERRED.value,
                        Specificity.INFERRED_LANG.value,
                    )
                    if is_strong_geo:
                        last_geo_context = geo_context
                        last_geo_sentence_idx = current_idx
                continue

            # Exclude procedural/risk boilerplate numerics from coverage math.
            if analysis.suppress_coverage_counts:
                continue

            # 4. Determine Geographic Context
            geo_context = self._determine_geo_context(
                analysis, last_geo_context, current_idx, last_geo_sentence_idx
            )
            current_geo_key = _geo_key(geo_context)

            # Suppress contract-clause numerics when the previous sentence
            # in the same geo already reported explicit coverage.
            has_quantitative = bool(
                analysis.percentages or analysis.worker_counts or analysis.numbers
            )
            if (
                analysis.contract_clause_terms
                and has_quantitative
                and prev_sentence_has_explicit
                and prev_sentence_geo_key
                and current_geo_key == prev_sentence_geo_key
            ):
                suppress_clause_numbers = True

            if suppress_clause_numbers:
                effective_counts = []
                current_sentence_count = None

            # Update context anchor if:
            # 1. Strong Geography (Explicit/Inferred)
            # 2. OR Strong Census (Has Counts) - allows inheriting from implicit totals
            is_strong_geo = geo_context["specificity"] in (
                Specificity.EXPLICIT.value,
                Specificity.INFERRED_UNION.value,
                Specificity.EXPLICIT_INFERRED.value,
                Specificity.INFERRED_LANG.value,
            )
            has_counts = bool(effective_counts)

            if is_strong_geo or has_counts:
                last_geo_context = geo_context
                last_geo_sentence_idx = current_idx

            # 5. Update Region Totals
            geo_notes, union_notes, census_update_note = None, None, None

            if effective_counts and not suppress_clause_numbers:
                # Check for range first
                range_avg = self._detect_count_range(analysis, effective_counts)

                if range_avg:
                    current_val = range_avg
                    mapped_counts = {}
                    union_counts = {}
                else:
                    # Try intelligent mapping first
                    mapped_counts, sent_total, geo_notes = (
                        self._resolve_counts_to_geography(analysis)
                    )
                    union_counts, _, union_notes = self._resolve_counts_to_unions(
                        analysis
                    )
                    current_val = max(effective_counts)

                updates_found = []
                update_sources = []

                if mapped_counts or union_counts:
                    # Use specific mappings
                    if mapped_counts:
                        for code, count in mapped_counts.items():
                            # Check if this is a source of the total (Update vs Previous)
                            prev_val = (
                                previous_totals.get(code, 0) if previous_totals else 0
                            )
                            curr_max = effective_totals.get(code, 0)
                            if count > prev_val and count >= curr_max:
                                updates_found.append(f"{code}: {count}")
                                update_sources.append(
                                    f"{code}: mapped_counts (prev={prev_val}, prior_max={curr_max})"
                                )

                            if count > local_totals.get(code, 0):
                                local_totals[code] = count
                            if count > effective_totals.get(code, 0):
                                effective_totals[code] = count

                    if union_counts:
                        for union_name, count in union_counts.items():
                            info = self.matcher.get_union(union_name)
                            if info:
                                region, country, code = info

                                # Refine generic union code using context
                                if code:
                                    ctx_countries = geo_context.get("countries", [])
                                    refined_code, _ = refine_generic_code(
                                        code, ctx_countries, self.domestic_country_code
                                    )
                                    if refined_code != code:
                                        code = refined_code

                                prev_val = (
                                    previous_totals.get(code, 0)
                                    if previous_totals
                                    else 0
                                )
                                curr_max = effective_totals.get(code, 0)
                                if count > prev_val and count >= curr_max:
                                    updates_found.append(
                                        f"{code} (via {union_name}): {count}"
                                    )
                                    update_sources.append(
                                        f"{code}: union_counts '{union_name}' (prev={prev_val}, prior_max={curr_max})"
                                    )

                                if count > local_totals.get(code, 0):
                                    local_totals[code] = count
                                if count > effective_totals.get(code, 0):
                                    effective_totals[code] = count
                else:
                    # Fallback to applying max count (or range avg) to context
                    if geo_context["specificity"] in (
                        Specificity.EXPLICIT.value,
                        Specificity.INHERITED.value,
                        Specificity.INFERRED_UNION.value,
                    ):
                        region_key = geo_context["region"]
                        fallback_countries = geo_context.get("countries", [])
                        if region_key in UNK_SET:
                            if len(fallback_countries) == 1:
                                c_code = fallback_countries[0].get("code")
                                region_key = (
                                    self.domestic_country_code
                                    if c_code == GeoCode.DOMESTIC.value
                                    else c_code
                                )
                            else:
                                region_key = Scope.GLOBAL.value

                        prev_val = (
                            previous_totals.get(region_key, 0) if previous_totals else 0
                        )
                        curr_max = effective_totals.get(region_key, 0)
                        if current_val > prev_val and current_val >= curr_max:
                            updates_found.append(f"{region_key}: {current_val}")
                            update_sources.append(
                                f"{region_key}: fallback_context (prev={prev_val}, prior_max={curr_max})"
                            )

                        if current_val > local_totals.get(region_key, 0):
                            local_totals[region_key] = current_val

                        if current_val > effective_totals.get(region_key, 0):
                            effective_totals[region_key] = current_val

                        for c in geo_context.get("countries", []):
                            c_code = c["code"]

                            prev_val = (
                                previous_totals.get(c_code, 0) if previous_totals else 0
                            )
                            curr_max = effective_totals.get(c_code, 0)
                            if current_val > prev_val and current_val >= curr_max:
                                updates_found.append(f"{c_code}: {current_val}")
                                update_sources.append(
                                    f"{c_code}: fallback_context (prev={prev_val}, prior_max={curr_max})"
                                )

                            # Only update if we didn't map it specifically above (though mapped_counts check covers this)
                            if current_val > local_totals.get(c_code, 0):
                                local_totals[c_code] = current_val
                            if current_val > effective_totals.get(c_code, 0):
                                effective_totals[c_code] = current_val

                if updates_found:
                    unique_updates = sorted(list(set(updates_found)))
                    census_update_note = f"Updates lookup: {', '.join(unique_updates)}"
                    if update_sources:
                        unique_sources = sorted(list(set(update_sources)))
                        census_update_note += (
                            " | Update sources: " + ", ".join(unique_sources)
                        )
                    if geo_notes:
                        census_update_note += f" | Geo Strategy: {', '.join(geo_notes)}"
                    if union_notes:
                        census_update_note += (
                            f" | Union Strategy: {', '.join(union_notes)}"
                        )

            # 6. Determine Relevant Total for Calculation
            relevant_total = None
            current_region = geo_context["region"]

            # Priority: Local > Effective (Previous) > Global
            if current_region in local_totals:
                relevant_total = local_totals[current_region]
            elif current_region in effective_totals:
                relevant_total = effective_totals[current_region]
            elif (
                current_region in (Region.INTERNATIONAL.value, Region.UNKNOWN.value)
                and global_max_workers > 0
            ):
                relevant_total = global_max_workers
            elif last_employee_count:
                relevant_total = last_employee_count

            # 7. Determine Coverage Data (Dispatch)
            coverage_data = self._determine_coverage_data(
                analysis, relevant_total, reporting_year, is_historical=is_historical
            )

            if suppress_clause_numbers:
                # Keep the sentence and keywords, but drop numeric coverage signals.
                coverage_data["percentage"] = None
                coverage_data["employee_count_covered"] = None
                coverage_data["employee_count_not_covered"] = None
                coverage_data["employee_count_total"] = None
                coverage_data["type"] = CoverageType.NONE.value
                coverage_data.pop("is_explicit_percent", None)
                coverage_data["note"] = (
                    ((coverage_data.get("note") or "") + " | ")
                    if coverage_data.get("note")
                    else ""
                ) + "Suppressed contract-clause numerics (prior explicit in same geo)"

            explicit_pct_entries = _collect_explicit_pct_entries(
                analysis, geo_context, coverage_data, current_idx
            )
            # Fire unconditionally when entries were collected
            if explicit_pct_entries:
                coverage_data.pop("is_explicit_percent", None)
                coverage_data["type"] = CoverageType.NONE.value
                coverage_data["percentage"] = None
                coverage_data["note"] = (
                    (coverage_data.get("note", "") + " | ")
                    if coverage_data.get("note")
                    else ""
                ) + "Explicit percent recorded separately for mixed-geo sentence"
                # Avoid double counting: if this is a mixed-geo sentence and we are not
                # splitting it into per-geo items, clear derived counts from the main entry.
                if len(geo_context.get("countries", [])) > 1:
                    coverage_data["employee_count_covered"] = None
                    coverage_data["employee_count_not_covered"] = None
                    coverage_data["employee_count_total"] = None
                    coverage_data["note"] = (
                        (coverage_data.get("note", "") + " | ")
                        if coverage_data.get("note")
                        else ""
                    ) + "Cleared counts to avoid mixed-geo double counting"

            # NEW: Resolve types
            type_map = self._resolve_counts_to_types(analysis)

            lookup_keys = _worker_lookup_keys(geo_context)
            if type_map and lookup_keys:
                type_total = sum(type_map.values())
                if current_sentence_count:
                    type_total = max(type_total, current_sentence_count)

                for lk in lookup_keys:
                    bucket = worker_type_lookup.setdefault(lk, {})
                    for t_name, t_count in type_map.items():
                        bucket[t_name.lower()] = max(
                            bucket.get(t_name.lower(), 0.0), t_count
                        )
                    worker_type_total_lookup[lk] = max(
                        worker_type_total_lookup.get(lk, 0.0), type_total
                    )

            has_quantitative_data = any(
                coverage_data.get(k) is not None
                for k in (
                    "percentage",
                    "employee_count_covered",
                    "employee_count_not_covered",
                    "employee_count_total",
                )
            )
            if not has_quantitative_data and analysis.is_union:
                targets: set[str] = set(
                    t.lower() for t in (analysis.worker_types or [])
                )
                for w in analysis.worker_terms or []:
                    w_low = w.lower()
                    if (
                        w_low not in GENERIC_WORKER_TERMS
                        and w_low.rstrip("s") not in GENERIC_WORKER_TERMS
                    ):
                        targets.add(w_low)

                if targets and lookup_keys:
                    matched_by_type: Dict[str, float] = {}
                    found_match = False
                    lookup_total = 0.0
                    for lk in lookup_keys:
                        bucket = worker_type_lookup.get(lk, {})
                        lookup_total = max(
                            lookup_total, worker_type_total_lookup.get(lk, 0.0)
                        )
                        for target in targets:
                            if target in bucket:
                                matched_by_type[target] = max(
                                    matched_by_type.get(target, 0.0), bucket[target]
                                )
                                found_match = True

                    matched_count = sum(matched_by_type.values())

                    if found_match and matched_count > 0:
                        if coverage_data.get("negated"):
                            coverage_data["employee_count_not_covered"] = (
                                coverage_data.get("employee_count_not_covered") or 0.0
                            ) + matched_count
                        else:
                            coverage_data["employee_count_covered"] = (
                                coverage_data.get("employee_count_covered") or 0.0
                            ) + matched_count

                        if (
                            coverage_data.get("employee_count_total") is None
                            and lookup_total >= matched_count
                            and lookup_total > 0
                        ):
                            coverage_data["employee_count_total"] = lookup_total

                        total_val = coverage_data.get("employee_count_total")
                        covered_val = coverage_data.get("employee_count_covered")
                        if total_val and covered_val is not None and total_val > 0:
                            coverage_data["percentage"] = round(
                                (covered_val / total_val) * 100.0, 2
                            )
                            coverage_data["type"] = CoverageType.CALCULATED.value

                        note = f"Inferred coverage for {matched_count} (worker type lookup)"
                        coverage_data["note"] = (
                            ((coverage_data.get("note") or "") + " | ")
                            if coverage_data.get("note")
                            else ""
                        ) + note

            # 8. Construct Result (Handle Splits)
            split_items = []
            # Remove internal key to prevent JSON serialization errors (contains MatchType)
            assignments = coverage_data.pop("_count_assignments", None)

            if assignments:
                relevant_assignments = [
                    a
                    for a in assignments
                    if a["type"] in ("covered", "not_covered", "total")
                ]

                # Only split if we have multiple relevant counts and multiple explicit geos
                if len(relevant_assignments) > 1:
                    splits = self._map_assignments_to_geo(
                        analysis, relevant_assignments, effective_totals
                    )

                    # Group splits by geography to merge Total + Covered for same country
                    grouped_splits = {}
                    for s in splits:
                        c_code = s["countries"][0]["code"]
                        key = (s["region"], c_code)
                        if key not in grouped_splits:
                            grouped_splits[key] = []
                        grouped_splits[key].append(s)

                    if len(grouped_splits) > 1:
                        for (region, c_code), group in grouped_splits.items():
                            # Merge group items into one coverage data
                            # Use the first item for context, then merge values
                            s = group[0]

                            new_geo_context = {
                                "region": s["region"],
                                "countries": s["countries"],
                                "specificity": Specificity.EXPLICIT.value,
                                "explicit_countries": [
                                    c["name"] for c in s["countries"]
                                ],
                                "regions": [],
                                "unusual_union_region_combo": False,
                                "union_names_mentioned": None,
                                "note": "Region split",
                            }

                            new_cov_data = {
                                "percentage": None,
                                "employee_count_covered": None,
                                "employee_count_not_covered": None,
                                "employee_count_total": None,
                                "negated": False,
                                "negation_type": None,
                                "type": CoverageType.CALCULATED.value,
                                "qualitative_bounds": None,
                                "note": f"Split from list | {s['note']}",
                                "temporal_scope": coverage_data.get(
                                    "temporal_scope", TemporalScope.CURRENT.value
                                ),
                            }

                            notes = []
                            for item in group:
                                if item.get("note"):
                                    notes.append(item["note"])

                                if item["type"] == "covered":
                                    new_cov_data["employee_count_covered"] = item["val"]
                                elif item["type"] == "not_covered":
                                    new_cov_data["employee_count_not_covered"] = item[
                                        "val"
                                    ]
                                    new_cov_data["negated"] = True
                                    new_cov_data["negation_type"] = (
                                        NegationType.NOT_COVERED.value
                                    )
                                elif item["type"] == "total":
                                    new_cov_data["employee_count_total"] = item["val"]

                            if notes:
                                dedup_notes = list(dict.fromkeys(notes))
                                extra_notes = [
                                    n
                                    for n in dedup_notes
                                    if n and n not in new_cov_data["note"]
                                ]
                                if extra_notes:
                                    new_cov_data["note"] += " | " + "; ".join(
                                        extra_notes
                                    )

                            # Try to find total from lookup if not present
                            if new_cov_data["employee_count_total"] is None:
                                c_total = effective_totals.get(c_code)
                                max_part = max(
                                    new_cov_data["employee_count_covered"] or 0,
                                    new_cov_data["employee_count_not_covered"] or 0,
                                )
                                if c_total and c_total >= max_part:
                                    new_cov_data["employee_count_total"] = c_total

                            # Normalize negation semantics for split rows:
                            # mixed covered + not_covered is not a negated-only statement.
                            cov_val = new_cov_data["employee_count_covered"]
                            not_cov_val = new_cov_data["employee_count_not_covered"]
                            total_val = new_cov_data["employee_count_total"]

                            if cov_val is not None and not_cov_val is not None:
                                if total_val and cov_val == 0 and not_cov_val > 0:
                                    new_cov_data["negated"] = True
                                    new_cov_data["negation_type"] = (
                                        NegationType.ZERO_COVERAGE.value
                                    )
                                else:
                                    new_cov_data["negated"] = False
                                    new_cov_data["negation_type"] = None
                            elif not_cov_val is not None and cov_val is None:
                                new_cov_data["negated"] = True
                                new_cov_data["negation_type"] = (
                                    NegationType.NOT_COVERED.value
                                )
                            elif cov_val is not None:
                                new_cov_data["negated"] = False
                                new_cov_data["negation_type"] = None

                            # Calculate percentage if possible
                            if (
                                new_cov_data["employee_count_total"]
                                and new_cov_data["employee_count_total"] > 0
                            ):
                                if new_cov_data["employee_count_covered"] is not None:
                                    new_cov_data["percentage"] = round(
                                        (
                                            new_cov_data["employee_count_covered"]
                                            / new_cov_data["employee_count_total"]
                                        )
                                        * 100,
                                        2,
                                    )
                                elif (
                                    new_cov_data["employee_count_not_covered"]
                                    is not None
                                ):
                                    new_cov_data["percentage"] = round(
                                        (
                                            (
                                                new_cov_data["employee_count_total"]
                                                - new_cov_data[
                                                    "employee_count_not_covered"
                                                ]
                                            )
                                            / new_cov_data["employee_count_total"]
                                        )
                                        * 100,
                                        2,
                                    )

                            split_item = {
                                "sentence": sent,
                                "keyword_matched": self._get_annotated_keywords(
                                    analysis
                                ),
                                "is_table_generated": self._is_table_generated_sentence(
                                    sent
                                ),
                                "geographic_context": new_geo_context,
                                "coverage_data": new_cov_data,
                                "lookup_totals": effective_totals.copy(),
                                "census_note": census_update_note,
                                "sentence_index": current_idx,
                                "worker_type_map": type_map,
                                "worker_types": analysis.worker_types,
                                "is_remaining": analysis.has_remaining_other,
                                "is_union": analysis.is_union,
                                "explicit_pct_entries": [
                                    ep for ep in explicit_pct_entries
                                    if ep.get("geo_code") == c_code
                                ] if explicit_pct_entries else [],
                                "is_split_item": True,
                            }
                            split_items.append(split_item)

            if split_items:
                results.extend(split_items)
            else:
                item = {
                    "sentence": sent,
                    "keyword_matched": self._get_annotated_keywords(analysis),
                    "is_table_generated": self._is_table_generated_sentence(sent),
                    "geographic_context": geo_context,
                    "coverage_data": coverage_data,
                    "lookup_totals": effective_totals.copy(),
                    "census_note": census_update_note,
                    "sentence_index": current_idx,
                    "worker_type_map": type_map,
                    "worker_types": analysis.worker_types,
                    "is_remaining": analysis.has_remaining_other,
                    "is_union": analysis.is_union,
                    "potential_total": current_sentence_count,
                    "explicit_pct_entries": explicit_pct_entries,
                }
                results.append(item)

            last_employee_count = current_sentence_count
            prev_sentence_geo_key = current_geo_key
            prev_sentence_has_explicit = bool(
                coverage_data.get("is_explicit_percent")
                or coverage_data.get("type") == CoverageType.EXPLICIT_PERCENT.value
            )

            # Exception-item synthesis is temporarily disabled (experimental/buggy).
            # Keep exclusion behavior from geo parsing, but do not emit synthetic items.
            # if analysis.is_relevant:
            #     exception_items = self._create_exception_items(
            #         analysis, coverage_data, current_idx, sent
            #     )
            #     results.extend(exception_items)

        merged_results = self._merge_continuation_items(results)

        # Apply splitting logic for ambiguous qualitative negations
        merged_results = self._apply_splitting_logic(merged_results)

        return (
            merged_results,
            risk_items,
            effective_totals,
            last_geo_context,
            last_geo_sentence_idx,
        )

    def _determine_coverage_data(
        self,
        analysis: SentenceAnalysis,
        inherited_total_count: Optional[float] = None,
        reporting_year: Optional[int] = None,
        is_historical: bool = False,
    ) -> Dict[str, Any]:
        """
        Dispatcher: Delegates to Simple or Complex analyzer based on sentence complexity.
        """
        data = {}

        # Capture explicit bargaining unit counts (summed per user instruction)
        bu_sum = sum(analysis.bargaining_unit_counts) if analysis.bargaining_unit_counts else None
        if bu_sum is not None:
            data["bargaining_unit_count"] = bu_sum

        if analysis.has_union_denominator:
            denom_data = self.extra_analyzer.analyze_denominator(analysis)
            if "bargaining_unit_count" in data:
                denom_data["bargaining_unit_count"] = data["bargaining_unit_count"]
            return denom_data
        elif is_simple_scenario(analysis):
            data = self.simple_analyzer.analyze(analysis)
        else:
            data = self._analyze_complex_coverage(analysis, inherited_total_count)

        if bu_sum is not None and data.get("bargaining_unit_count") is None:
            data["bargaining_unit_count"] = bu_sum

        # Common Post-Processing (Temporal Scope, etc.)
        data.setdefault("temporal_scope", TemporalScope.CURRENT.value)
        if is_historical:
            data["temporal_scope"] = TemporalScope.HISTORICAL.value

        # Relationship Status
        rel_status = determine_relationship_status(analysis)
        if rel_status:
            data["relationship_status"] = rel_status

        # Qualitative Quants (Soft Percent) - Fallback if no explicit data found
        # and no count-based coverage was already resolved.
        has_count_based_coverage = (
            data.get("employee_count_covered") is not None
            or data.get("employee_count_not_covered") is not None
        )
        if data["percentage"] is None and not has_count_based_coverage:
            qual_matches = [
                m
                for m in analysis._matches
                if m["type"]
                in (MatchType.QUALITATIVE_TERM, MatchType.QUALITATIVE_MEMBERSHIP)
            ]
            if qual_matches:
                match = qual_matches[0]

                # Ensure we have union context before applying generic qualitative terms
                if (
                    match["type"] == MatchType.QUALITATIVE_TERM
                    and not analysis.is_union
                ):
                    return data

                # Consolidated qualitative-term interpretation
                qinfo = interpret_qualitative_match(match, analysis, prefer_note=True)
                pct = qinfo.get("percentage")
                amb_mult = qinfo.get("ambiguity_multiplier")

                if pct is not None:
                    data["percentage"] = pct
                    if qinfo.get("type"):
                        data["type"] = qinfo.get("type")
                    else:
                        data["type"] = CoverageType.QUALITATIVE.value
                    if qinfo.get("qualitative_bounds") is not None:
                        data["qualitative_bounds"] = qinfo.get("qualitative_bounds")
                    if qinfo.get("note"):
                        data["note"] = qinfo.get("note")

                    # Check for status negation (e.g. "not represented", "non-union")
                    has_status_negation = has_status_negation_matches(analysis._matches)
                    if has_status_negation:
                        data["negated"] = True
                        data["negation_type"] = NegationType.NOT_COVERED.value
                        data["note"] = (data.get("note") or "") + " (Negated Status)"
                elif amb_mult is not None:
                    data["ambiguity_multiplier"] = amb_mult
                    data["type"] = CoverageType.QUALITATIVE.value
                    if qinfo.get("note"):
                        data["note"] = qinfo.get("note")
                    else:
                        data["note"] = f"Qualitative multiplier: {amb_mult}x"

                    has_status_negation = has_status_negation_matches(analysis._matches)
                    if has_status_negation:
                        data["negated"] = True
                        data["negation_type"] = NegationType.NOT_COVERED.value
                        data["note"] = (data.get("note") or "") + " (Negated Status)"

        # If the chosen percentage appears explicitly in the sentence, mark it explicit.
        if data.get("percentage") is not None and analysis.percentages:
            pct_val = float(data["percentage"])
            is_direct_pct = any(
                abs(float(p) - pct_val) < 1e-6 for p in analysis.percentages
            )
            if is_direct_pct and data.get("type") not in (
                CoverageType.CALCULATED.value,
                CoverageType.QUALITATIVE.value,
            ):
                data["is_explicit_percent"] = True

        return data

    def _analyze_complex_coverage(
        self, analysis: SentenceAnalysis, total_count: Optional[float]
    ) -> Dict[str, Any]:
        """
        Handles complex scenarios: mixed coverage, ratios, inferred totals, etc.
        (Placeholder for the complex logic to be re-added/refined)
        """
        analyzer = self.complex_analyzer_cls(
            analysis, total_count, self.domestic_country_code
        )
        return analyzer.analyze()

    def _analyze_item1a(
        self, sentences: List[str], reporting_year: Optional[int] = None, ext_total: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyzes sentences for Item 1A (Risk Factors).
        """
        results = []
        for idx, sent in enumerate(sentences):
            analysis = self.extractor.analyze_sentence(sent, emp_count=ext_total)

            is_historical = False
            # Historical Check for Risks
            years_indicate_past = False
            if reporting_year and analysis.years:
                if all(y < reporting_year for y in analysis.years):
                    years_indicate_past = True

            if (
                years_indicate_past or analysis.has_historical
            ) and not analysis.has_current:
                is_historical = True

            # Item 1A logic: Look for risk terms, union terms, supplier terms, or relationship terms
            if (
                analysis.risk_terms
                or analysis.union_terms
                or analysis.supplier_terms
                or analysis.relationship_quality_terms
                or analysis.relationship_terms
            ):
                result = self.extra_analyzer.create_risk_item(
                    sent,
                    analysis,
                    is_historical=is_historical,
                    item1a_mode=True,
                )
                if result:
                    result["sentence_index"] = idx
                    if result.get("activity_class") == RiskActivityClass.ACTUAL.value:
                        coverage_data = self._determine_coverage_data(
                            analysis,
                            inherited_total_count=None,
                            reporting_year=reporting_year,
                            is_historical=is_historical,
                        )
                        coverage_data.pop("_count_assignments", None)
                        has_signal = any(
                            coverage_data.get(k) is not None
                            for k in (
                                "percentage",
                                "employee_count_covered",
                                "employee_count_not_covered",
                                "employee_count_total",
                                "bargaining_unit_counts",
                            )
                        )
                        if has_signal:
                            result["coverage_data"] = coverage_data
                    results.append(result)
        return results

    def compute_weighted_coverage(
        self,
        results: List[Dict[str, Any]],
        tracker: Tracker,
        region_totals: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        output = tracker.calculate_metrics()

        entries_dump = []
        for e in tracker.entries:
            data = e.__dict__.copy()
            if isinstance(data.get("scope"), Enum):
                data["scope"] = data["scope"].value
            entries_dump.append(data)
        logs = output.get("_logs", [])

        output["entries"] = entries_dump
        return output
