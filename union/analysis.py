from typing import List, Dict, Any, Optional, Tuple, Union
import statistics
import re
from dataclasses import dataclass, field

from extraction import (
    NEGATION_REGEX,
    OR_REGEX,
    QualitativeTerm,
    UnionExtractor,
    SentenceAnalysis,
    MatchType,
    REMAIN_REGEX,
    OF_REGEX,
    QUALITATIVE_MULTIPLIERS,
    TOTAL_MODIFIER_REGEX,
)
from defs.region_regex import REGION_CODES, Region, INT_LANGUAGE_MAP, GeoSource
from defs.output_enums import (
    Specificity,
    CoverageType,
    PercentageQualifier,
    NegationType,
    TemporalScope,
    RiskType,
    RelationshipStatus,
)

from defs.union_regex import (
    NON_COVERAGE_REGEX,
    NON_UNION_REGEX,
    RELATIONSHIP_NEUTRAL_TERMS,
    RELATIONSHIP_QUALITY_TERMS,
    RELATIONSHIP_NEGATIVE_TERMS,
    BOILERPLATE_REGEX,
    PERSONNEL_EVENT_REGEX,
    UNION_REGEX,
)


def get_effective_counts(analysis: SentenceAnalysis) -> List[float]:
    """Combines worker_counts and relevant numbers (heuristic filter)."""
    counts = list(analysis.worker_counts)
    for n in analysis.numbers:
        if n > 5 or n == 0:
            counts.append(n)
    return counts


UNION_MATCH_TYPES = [
    MatchType.UNION_TERM,
    MatchType.COVERAGE_TERM,
    MatchType.SPECIFIC_UNION,
    MatchType.UNION_NAME,
]


def get_min_distance_to_matches(
    target_span: Tuple[int, int],
    matches: List[Dict[str, Any]],
    match_types: List[MatchType],
) -> float:
    t_start, t_end = target_span
    min_dist = float("inf")

    for m in matches:
        if m["type"] in match_types:
            m_start, m_end = m["span"]
            dist = 0
            if m_end < t_start:
                dist = t_start - m_end
            elif t_end < m_start:
                dist = m_start - t_end

            if dist < min_dist:
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


def check_is_total_context(
    match_span: Tuple[int, int],
    text: str,
    backward: int = 60,
    forward: int = 60,
) -> bool:
    """
    Checks if 'total', 'global', 'worldwide', etc. are present near the match.
    """
    return check_local_regex(match_span, text, TOTAL_MODIFIER_REGEX, backward, forward)


class SimpleCoverageAnalyzer:
    """
    Handles straightforward sentences where coverage is explicit and singular.
    Criteria:
    - Max 1 Percentage AND/OR Max 1 Worker Count
    - No conflicting Union vs Non-Union terms (mixed signals)
    - No Ratios
    """

    def _handle_one_percent_one_count(
        self,
        analysis: SentenceAnalysis,
        effective_counts: List[float],
        data: Dict[str, Any],
        notes: List[str],
    ):
        """Handles cases with exactly one percentage and one count."""
        pct = analysis.percentages[0]
        count = effective_counts[0]

        data["percentage"] = pct
        data["type"] = CoverageType.EXPLICIT_PERCENT.value
        notes.append(f"Explicit percentage: {pct}%")

        is_percent_of_total = False
        count_total = False
        # Ensure matches are found
        if not analysis._matches:
            return

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

        if pct_match and count_match:
            if pct_match["span"][1] <= count_match["span"][0]:
                start, end = pct_match["span"][1], count_match["span"][0]
            else:
                start, end = count_match["span"][1], pct_match["span"][0]
            between = analysis.text[start:end]

            if OF_REGEX.search(between):
                is_percent_of_total = True
            if OR_REGEX.search(between):
                count_total = True

        if is_percent_of_total:
            data["employee_count_total"] = count
            ratio = round((pct / 100.0) * count)
            other = count - ratio

            # Check for local negation to decide if we assume the opposite
            is_negated = False
            if analysis.negation_terms:
                if pct_match and check_local_negation(
                    pct_match["span"], analysis.text, backward=50, forward=50
                ):
                    is_negated = True

            if is_negated:
                data["employee_count_not_covered"] = ratio
                data["employee_count_covered"] = other
                data["negated"] = True
                notes.append(
                    f"Count (total): {count}. {ratio} not covered (negated). Inferred {other} covered."
                )
            else:
                data["employee_count_covered"] = ratio
                data["employee_count_not_covered"] = other
                notes.append(
                    f"Count (total): {count}. {ratio} covered. Inferred {other} not covered."
                )

        else:
            # Determine if count is Total or Covered based on proximity to union terms
            is_count_total = True  # Default to Total if ambiguous

            if pct_match and count_match:
                if not count_total:
                    dist_to_pct = get_min_distance_to_matches(
                        pct_match["span"], analysis._matches, UNION_MATCH_TYPES
                    )
                    dist_to_count = get_min_distance_to_matches(
                        count_match["span"], analysis._matches, UNION_MATCH_TYPES
                    )

                    # If both are far, ignore (likely unrelated numbers)
                    if dist_to_pct > 100 and dist_to_count > 100:
                        notes.append(
                            "Ignored: Percentage and Count too far from union terms"
                        )
                        return

                    # If union term is closer to Percentage, then Percentage describes coverage -> Count is Total
                    if dist_to_pct < dist_to_count:
                        is_count_total = True
                    # If union term is closer to Count, then Count is Covered
                    elif dist_to_count < dist_to_pct:
                        is_count_total = False

                    # Only override to Total if we don't have a strong signal that it is Covered
                    is_strongly_covered = (dist_to_count < dist_to_pct) and (
                        dist_to_count < 50
                    )
                    if not is_strongly_covered:
                        if check_is_total_context(count_match["span"], analysis.text):
                            is_count_total = True

            if is_count_total or count_total:
                data["employee_count_total"] = count
                ratio = round((pct / 100.0) * count)
                other = count - ratio

                is_negated = False
                if analysis.negation_terms:
                    if pct_match and check_local_negation(
                        pct_match["span"], analysis.text, backward=50, forward=50
                    ):
                        is_negated = True

                if is_negated:
                    data["employee_count_not_covered"] = ratio
                    data["employee_count_covered"] = other
                    data["negated"] = True
                    notes.append(
                        f"Count (total): {count}. {ratio} not covered (negated). Inferred {other} covered."
                    )
                else:
                    data["employee_count_covered"] = ratio
                    data["employee_count_not_covered"] = other
                    notes.append(
                        f"Count (total): {count}. {ratio} covered. Inferred {other} not covered."
                    )
            else:
                total = round(count / (pct / 100.0)) if pct > 0 else None
                other = total - count if total else None
                data["employee_count_total"] = total

                is_negated = False
                if analysis.negation_terms:
                    if pct_match and check_local_negation(
                        pct_match["span"], analysis.text, backward=50, forward=50
                    ):
                        is_negated = True

                if is_negated:
                    data["employee_count_not_covered"] = count
                    data["employee_count_covered"] = other
                    data["negated"] = True
                    data["negation_type"] = NegationType.NOT_COVERED.value
                    notes.append(
                        f"Count (not covered): {count}, inferred total: {total}. Inferred {other} covered."
                    )
                else:
                    data["employee_count_covered"] = count
                    data["employee_count_not_covered"] = other
                    notes.append(
                        f"Count (covered): {count}, inferred total: {total}. Inferred {other} not covered."
                    )

    def _handle_two_counts(
        self,
        analysis: SentenceAnalysis,
        effective_counts: List[float],
        data: Dict[str, Any],
        notes: List[str],
    ):
        """Handles cases with exactly two counts and no percentages."""
        c1, c2 = effective_counts[0], effective_counts[1]

        m1 = next(
            (
                m
                for m in analysis._matches
                if m["type"] == MatchType.WORKER_COUNT and m["val"] == c1
            )
            or (
                m
                for m in analysis._matches
                if m["type"] == MatchType.NUMBER and m["val"] == c1
            ),
            None,
        )
        m2 = next(
            (
                m
                for m in analysis._matches
                if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                and m["val"] == c2
                and m is not m1
            ),
            None,
        )

        is_subset = True
        if m1 and m2:
            if m1["span"][0] > m2["span"][0]:
                m1, m2 = m2, m1
            text_between = analysis.text[m1["span"][1] : m2["span"][0]]

            if OF_REGEX.search(text_between) or check_local_regex(
                m1["span"], analysis.text, OF_REGEX, backward=25, forward=0
            ):
                is_subset = True
            elif re.search(r"\band\b", text_between, re.IGNORECASE):
                is_subset = False

        if is_subset:
            total, part = max(c1, c2), min(c1, c2)
            data["employee_count_total"] = total
            other = total - part
            assert m1 and m2
            # Check if 'part' is associated with union
            part_match = m1 if m1["val"] == part else m2
            if part_match:
                dist = get_min_distance_to_matches(
                    part_match["span"], analysis._matches, UNION_MATCH_TYPES
                )
                if dist < 100:
                    is_negated = False
                    if analysis.negation_terms:
                        if check_local_negation(
                            part_match["span"], analysis.text, backward=50, forward=50
                        ):
                            is_negated = True

                    if is_negated:
                        data["employee_count_not_covered"] = part
                        data["employee_count_covered"] = other
                        data["negated"] = True
                        data["negation_type"] = NegationType.NOT_COVERED.value
                        notes.append(
                            f"Count (not covered): {part} of {total}. Inferred {other} covered."
                        )
                    else:
                        data["employee_count_covered"] = part
                        data["employee_count_not_covered"] = other
                        notes.append(
                            f"Count (covered): {part} of {total}. Inferred {other} not covered."
                        )
                else:
                    # Part is not near union term -> Assume it's just a subset (e.g. "20 in marketing")
                    # Record total only
                    notes.append(
                        f"Count (total): {total}. Subset {part} not associated with union."
                    )
        else:
            total = c1 + c2
            data["employee_count_total"] = total
            if analysis.negation_terms:
                data.update(
                    {
                        "employee_count_not_covered": total,
                        "negated": True,
                        "negation_type": NegationType.NOT_COVERED.value,
                    }
                )
                notes.append(f"Count (not covered): {c1} + {c2} = {total}")
            else:
                data["employee_count_covered"] = total
                notes.append(f"Count (covered): {c1} + {c2} = {total}")

        if data.get("employee_count_total", 0) > 0:
            covered = data.get("employee_count_covered", 0) or 0
            pct = (covered / data["employee_count_total"]) * 100.0
            data["percentage"] = round(pct, 2)
            data["type"] = CoverageType.CALCULATED.value
            notes.append(f"Calculated percentage: {data['percentage']}%")

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
                    count_match["span"], analysis._matches, UNION_MATCH_TYPES
                )
                if dist < 100:
                    is_associated = True

            # Check for qualitative terms (e.g. "majority", "most")
            # If present, we assume the count is the Total, and the term describes the subset.
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
                data["employee_count_total"] = count
                term = qual_match.get("term_obj")
                if term:
                    assert isinstance(term, QualitativeTerm)
                    is_term_negated = check_local_negation(
                        qual_match["span"], analysis.text, backward=40
                    )
                    pct = term.get_percentage(is_negated=is_term_negated)
                    if pct is not None:
                        data["percentage"] = pct
                        data["type"] = CoverageType.QUALITATIVE.value

                        has_status_negation = any(
                            m["type"] in (MatchType.NON_UNION, MatchType.NON_COVERAGE)
                            for m in analysis._matches
                        )

                        ratio = round((pct / 100.0) * count)
                        if has_status_negation:
                            data["employee_count_not_covered"] = ratio
                            data["employee_count_covered"] = count - ratio
                            data["negated"] = True
                            data["negation_type"] = NegationType.NOT_COVERED.value
                            data["note"] = (
                                f"Qualitative '{qual_match['text']}' of {count} total -> {ratio} not covered (negated)"
                            )
                        else:
                            data["employee_count_covered"] = ratio
                            data["note"] = (
                                f"Qualitative '{qual_match['text']}' of {count} total -> {ratio} covered"
                            )
                else:
                    data["type"] = CoverageType.CALCULATED.value
                    notes.append(f"Count (total): {count} (qualitative term present)")

            elif is_associated:
                if analysis.negation_terms:
                    data.update(
                        {
                            "employee_count_not_covered": count,
                            "negated": True,
                            "negation_type": NegationType.NOT_COVERED.value,
                        }
                    )
                    notes.append(f"Count (not covered): {count}")
                else:
                    data["employee_count_covered"] = count
                    notes.append(f"Count (covered): {count}")
                data["type"] = CoverageType.CALCULATED.value
                data["employee_count_total"] = count
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

    def analyze(self, analysis: SentenceAnalysis) -> Dict[str, Any]:
        data = {
            "percentage": None,
            "employee_count_covered": None,
            "employee_count_not_covered": 0,
            "employee_count_total": None,
            "negated": False,
            "negation_type": None,
            "type": CoverageType.NONE.value,
            "note": None,
        }

        notes = []
        has_union_context = (
            bool(analysis.union_terms)
            or bool(analysis.coverage_terms)
            or bool(analysis.negation_terms)
            or any(
                m.source_type in (GeoSource.SPECIFIC_UNION, GeoSource.INFERRED_UNION)
                for m in analysis.geo_matches
            )
        )
        if not has_union_context:
            data["type"] = None
            return data

        effective_counts = get_effective_counts(analysis)

        if len(analysis.percentages) == 1 and len(effective_counts) == 1:
            self._handle_one_percent_one_count(analysis, effective_counts, data, notes)
        elif not analysis.percentages and len(effective_counts) == 2:
            self._handle_two_counts(analysis, effective_counts, data, notes)
        else:
            self._handle_single_value(analysis, effective_counts, data, notes)

        # Fallback to qualitative zero if no other data was found
        if (
            data.get("percentage") is None
            and data.get("employee_count_covered") is None
            and data.get("employee_count_not_covered") is None
        ):
            self._handle_qualitative_zero(analysis, effective_counts, data, notes)

        data["note"] = " | ".join(notes) if notes else "Simple Analysis (No Data)"
        data["employee_count_total"]
        return data


def get_external_worker_count(
    region: str, countries: List[Dict[str, str]]
) -> Optional[float]:
    """
    Placeholder: Connect to external DB to get worker counts for a region/country.
    """
    return None


def create_risk_item(
    sentence: str, analysis: SentenceAnalysis, is_historical: bool = False
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

    # Return something if there is something to return (Union terms OR Risk terms)
    if not (analysis.union_terms or analysis.risk_terms):
        return {}

    return {
        "type": (
            RiskType.UNION_RISK.value
            if analysis.union_terms
            else RiskType.LABOR_RISK.value
        ),
        "sentence": sentence,
        "labor_keywords": analysis.union_terms,
        "risk_keywords": analysis.risk_terms,
        "third_party": analysis.supplier_terms,
        "specific_to_unions": bool(analysis.union_terms),
        "union_mention": analysis.union_terms,
        "temporal_scope": temporal_scope,
        "conditional": is_conditional,
        "note": None,
    }


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


# Pre‑compiled regexes
_RANGE_TO_THROUGH = re.compile(r"\b(to|through)(?:\s+\S+){0,2}$", re.IGNORECASE)
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

    # Delimiters: , ; or words like while, although, but, however
    delimiter_regex = re.compile(
        r"(?<!\d)[:;](?!\d)|\b(?:while|although|whereas|but|however|except|yet)|(?:,)(?!(?:\s+or))\b", re.IGNORECASE
    )

    def __init__(self, analysis: SentenceAnalysis, total_count: Optional[float]):
        self.analysis = analysis
        self.total_count = total_count
        self.data = {
            "percentage": None,
            "employee_count_covered": None,
            "employee_count_not_covered": 0,
            "employee_count_total": total_count,
            "negated": False,
            "negation_type": None,
            "type": CoverageType.NONE.value,
            "note": None,
        }

    def analyze(self) -> Dict[str, Any]:
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

        # 2. Mixed Coverage (Resolves specific counts/percents)
        self._resolve_mixed_coverage(counts=counts)

        # 3. Ratios
        if not self.data["percentage"]:
            self._handle_ratios()

        # 4. Calculate Percentage from Counts
        self._calculate_percentage_from_counts()

        # 5. Calculate Count from Percentage
        self._calculate_count_from_percentage()

        # 6. Handle Negation (if no data yet)
        self._handle_negation()

        return self.data

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
                        matches[0]["span"], self.analysis._matches, UNION_MATCH_TYPES
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
                        matches[0]["span"], self.analysis._matches, UNION_MATCH_TYPES
                    )
                    is_associated = dist < 100

                    if is_associated:
                        is_negated = False
                        if self.analysis.negation_terms:
                            if check_local_negation(
                                matches[0]["span"], self.analysis.text, backward=50
                            ):
                                is_negated = True

                        if is_negated:
                            self.data["employee_count_not_covered"] = round(avg)
                            self.data["negated"] = True
                            self.data["negation_type"] = NegationType.NOT_COVERED.value
                            self.data["note"] = (
                                f"Averaged from range {c1} to {c2} (not covered)"
                            )
                        else:
                            self.data["employee_count_covered"] = round(avg)
                            self.data["note"] = (
                                f"Averaged from range {c1} to {c2} (covered)"
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

        # Helper to check negation
        is_negated = False
        pct_match = next((m for m in self.analysis._matches if m["type"] == MatchType.PERCENT and m["val"] == pct), None)
        if pct_match and self.analysis.negation_terms:
             if check_local_negation(pct_match["span"], self.analysis.text, backward=50, forward=50):
                 is_negated = True

        # Check 1: small / large ~= pct
        if abs(ratio_subset_total - pct) < 2.0:
            self.data["employee_count_total"] = large
            if is_negated:
                self.data["employee_count_not_covered"] = small
                self.data["employee_count_covered"] = large - small
                self.data["negated"] = True
                self.data["negation_type"] = NegationType.NOT_COVERED.value
                notes.append(f"Match: {small}/{large} ~= {pct}% (Negated). Total {large}.")
            else:
                self.data["employee_count_covered"] = small
                self.data["employee_count_not_covered"] = large - small
                notes.append(f"Match: {small}/{large} ~= {pct}%. Total {large}.")
            matched = True

        # Check 2: small / (small+large) ~= pct
        elif abs(ratio_part_sum - pct) < 2.0:
            self.data["employee_count_total"] = total_sum
            if is_negated:
                self.data["employee_count_not_covered"] = small
                self.data["employee_count_covered"] = large
                self.data["negated"] = True
                self.data["negation_type"] = NegationType.NOT_COVERED.value
                notes.append(f"Match: {small}/({small}+{large}) ~= {pct}% (Negated). Total {total_sum}.")
            else:
                self.data["employee_count_covered"] = small
                self.data["employee_count_not_covered"] = large
                notes.append(f"Match: {small}/({small}+{large}) ~= {pct}%. Total {total_sum}.")
            matched = True

        # Check 3: large / (small+large) ~= pct
        elif abs(ratio_large_sum - pct) < 2.0:
            self.data["employee_count_total"] = total_sum
            if is_negated:
                self.data["employee_count_not_covered"] = large
                self.data["employee_count_covered"] = small
                self.data["negated"] = True
                self.data["negation_type"] = NegationType.NOT_COVERED.value
                notes.append(f"Match: {large}/({small}+{large}) ~= {pct}% (Negated). Total {total_sum}.")
            else:
                self.data["employee_count_covered"] = large
                self.data["employee_count_not_covered"] = small
                notes.append(f"Match: {large}/({small}+{large}) ~= {pct}%. Total {total_sum}.")
            matched = True

        if matched:
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
                            span1, self.analysis._matches, UNION_MATCH_TYPES
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

    def _resolve_mixed_coverage(self, counts: List[float] = []):
        """
        Resolves mixed coverage by segmenting text on delimiters and mapping
        values to keywords within the same segment.
        """
        # 1. Identify Segments (Split by delimiters, avoiding numbers)
        delimiters = list(self.delimiter_regex.finditer(self.analysis.text))

        boundaries = [0] + [m.end() for m in delimiters] + [len(self.analysis.text)]
        segments = []
        for i in range(len(boundaries) - 1):
            segments.append((boundaries[i], boundaries[i + 1]))

        # 2. Gather entities
        _counts = [
            m
            for m in self.analysis._matches
            if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
            and m["val"] in counts
        ]
        percents = [m for m in self.analysis._matches if m["type"] == MatchType.PERCENT]

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
            if m["type"]
            in (MatchType.NON_UNION, MatchType.NEGATION, MatchType.NON_COVERAGE)
        ]
        totals = [
            m
            for m in self.analysis._matches
            if m["type"] in (MatchType.WORKER_TERM, MatchType.TOTAL_MODIFIER)
        ]

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
                    elif kw_item["type"] == "not_covered":
                        current = self.data["employee_count_not_covered"] or 0
                        self.data["employee_count_not_covered"] = (
                            current + val_match["val"]
                        )

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
                return

        def get_segment_range(span):
            mid = (span[0] + span[1]) / 2
            for start, end in segments:
                if start <= mid < end:
                    return start, end
            return 0, len(self.analysis.text)

        def get_nearest_type_in_segment(target_span):
            seg_start, seg_end = get_segment_range(target_span)
            t_start, t_end = target_span

            best_dist = float("inf")
            best_type = None

            candidates = []
            # Filter candidates by segment
            for p in positives:
                if p["span"][0] >= seg_start and p["span"][1] <= seg_end:
                    candidates.append(("covered", p))
            for n in negatives:
                if n["span"][0] >= seg_start and n["span"][1] <= seg_end:
                    candidates.append(("not_covered", n))
            for t in totals:
                if t["span"][0] >= seg_start and t["span"][1] <= seg_end:
                    candidates.append(("total", t))

            for c_type, m in candidates:
                m_start, m_end = m["span"]
                dist = 0
                if m_end < t_start:
                    dist = t_start - m_end
                elif t_end < m_start:
                    dist = m_start - t_end

                eff_dist = dist + (20 if c_type == "total" else 0)
                if eff_dist < best_dist:
                    best_dist = eff_dist
                    best_type = c_type

            return best_type if best_dist <= 150 else None

        for p in percents:
            ptype = get_nearest_type_in_segment(p["span"])
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
            elif ptype == "covered":
                self.data["percentage"] = adj_val
                if note:
                    self.data["note"] = note

        total_candidates = []
        for c in _counts:
            ctype = get_nearest_type_in_segment(c["span"])
            if ctype == "covered":
                self.data["employee_count_covered"] = c["val"]
            elif ctype == "not_covered":
                self.data["employee_count_not_covered"] = c["val"]
            elif ctype == "total":
                total_candidates.append(c["val"])

        if total_candidates:
            self.data["employee_count_total"] = sum(total_candidates)

        if (
            self.data["employee_count_covered"]
            and self.data["employee_count_not_covered"]
            and not self.data["employee_count_total"]
        ):
            self.data["employee_count_total"] = (
                self.data["employee_count_covered"]
                + self.data["employee_count_not_covered"]
            )

    def _handle_ratios(self):
        if self.analysis.ratios:
            numerator, denominator = self.analysis.ratios[0]
            if denominator > 0:
                pct = (numerator / denominator) * 100
                self.data["percentage"] = round(pct, 2)
                self.data["type"] = CoverageType.CALCULATED.value
                self.data["employee_count_covered"] = numerator
                self.data["employee_count_total"] = denominator
                self.data["note"] = f"Calculated from ratio: {numerator}/{denominator}"

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
    # 1. No mixed signals (Union AND Non-Union/Negation)
    has_union = bool(analysis.union_terms or analysis.coverage_terms)
    has_negation = bool(analysis.negation_terms)
    if has_union and has_negation:
        return False

    # 2. No Ratios (implies calculation)
    if analysis.ratios:
        return False

    effective_counts = get_effective_counts(analysis)
    # 2.5 Simple Counts of Counts
    if len(analysis.percentages) == 0 and len(effective_counts) == 2:
        return True
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
) -> Dict[str, Any]:
    """
    Resolves geographic context based on explicit matches, union names,
    language inference, or inheritance.
    """
    explicit_matches = [
        m for m in analysis.geo_matches if m.source_type == GeoSource.EXPLICIT
    ]
    union_matches = [
        m
        for m in analysis.geo_matches
        if m.source_type in (GeoSource.SPECIFIC_UNION, GeoSource.INFERRED_UNION)
    ]

    # 1. Explicit Geography (Highest Priority)
    if explicit_matches:
        countries = []
        regions_list = []
        found_regions_map = {}  # code -> (region_dict, region_enum)
        seen_codes = set()
        regions = set()
        locations_by_country = {}  # code -> set of locations

        unusual_combo = False
        conflict_notes = []

        for m in explicit_matches:
            if m.city:
                if m.geo_code not in locations_by_country:
                    locations_by_country[m.geo_code] = set()
                locations_by_country[m.geo_code].add(m.city)
            if m.country and m.geo_code not in seen_codes:
                seen_codes.add(m.geo_code)

                if m.geo_code in REGION_CODES:
                    # It is a region entity
                    r_obj = {"name": m.country, "code": m.geo_code, "countries": []}
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
            Region.INTERNATIONAL.value
            if len(regions) > 1
            else (list(regions)[0].value if regions else Region.UNKNOWN.value)
        )

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
            "note": "; ".join(conflict_notes) if conflict_notes else None,
        }

    # 2. Inferred from Union Name (Medium Priority)
    if union_matches:
        # Check for specific union inference
        specific_unions = [m for m in union_matches if m.country]
        if specific_unions:
            # Use the first specific union found
            m = specific_unions[0]
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
            return {
                "region": Region.INTERNATIONAL.value,  # Broad region
                "countries": [],  # No specific country known
                "specificity": Specificity.INFERRED_LANG.value,
                "union_name_indicator": m.text,
                "note": f"Inferred from language term '{m.text}' ({m.geo_code})",
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
    if not (analysis.relationship_terms and analysis.relationship_quality_terms):
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


@dataclass
class CoverageEntry:
    scope: str
    key: str
    total: float
    covered: float = 0.0
    not_covered: float = 0.0
    percentage: Optional[float] = None
    is_explicit_total: bool = False
    is_qualitative: bool = False
    sentence_index: int = -1
    union_name: Optional[str] = None
    children: List["CoverageEntry"] = field(default_factory=list)

class Tracker:
    """
    Tracks the 'Whole Pie' (Total Employee Counts) across different geographic scopes.
    Used to provide the correct denominator for coverage calculations.
    """

    def __init__(self):
        self.global_total: float = 0.0
        self.region_totals: Dict[str, float] = {}
        self.country_totals: Dict[str, float] = {}

        # Unified storage for all statements (Census + Coverage)
        # Key: sentence_index
        self.entries: Dict[int, CoverageEntry] = {}
        self.resolution_log: List[str] = []

    def update(
        self, count: float, geo_context: Dict[str, Any], is_explicit_total: bool = False, sentence_index: int = -1
    ):
        # 1. Update Lookups (Keep for analyze_block usage)
        # This logic is simplified to just maintain max values for lookups
        # The actual rate calculation will happen in calculate_metrics using self.entries

        region = geo_context.get("region")
        countries = geo_context.get("countries", [])
        # 1. Global Update
        if (
            region in (Region.INTERNATIONAL.value, Region.UNKNOWN.value)
            and not countries
        ):
            self.global_total = max(self.global_total, count)

        # 2. Regional Update
        if region and region not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
            current = self.region_totals.get(region, 0)
            if count > current:
                self.region_totals[region] = count

        # 3. Country Update
        if len(countries) == 1:
            c = countries[0]
            code = c["code"]
            if count > self.country_totals.get(code, 0):
                self.country_totals[code] = count

        # 4. Record Entry for Hierarchy
        if sentence_index >= 0:
            key = region
            if len(countries) == 1:
                key = countries[0]["code"]

            if sentence_index not in self.entries:
                self.entries[sentence_index] = CoverageEntry(
                    scope="region" if not countries else "country",
                    key=key or "global",
                    total=count,
                    is_explicit_total=is_explicit_total,
                    sentence_index=sentence_index
                )
            else:
                # Update existing (if we found a better total in Pass 1?)
                # Usually Pass 1 is the authority on Totals.
                self.entries[sentence_index].total = max(self.entries[sentence_index].total, count)

    def resolve(self):
        # No-op for simplified tracker, logic moved to calculate_metrics
        pass

    def record_coverage(
        self,
        percentage: Optional[float],
        covered_count: Optional[float],
        geo_context: Dict[str, Any],
        scope_total: Optional[float] = None,
        not_covered_count: Optional[float] = None,
        is_qualitative: bool = False,
        sentence_index: int = -1
    ):
        """
        Records coverage data (rate or count) for a specific geographic scope.
        """
        if sentence_index < 0:
            return

        region = geo_context.get("region")
        countries = geo_context.get("countries", [])

        # Determine scope
        scope = "global"
        key = "global"

        if region and region not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
            scope = "region"
            key = region

        if len(countries) == 1:
            scope = "country"
            key = countries[0]["code"]
        elif len(countries) > 1:
            scope = "aggregate"
            key = region or "aggregate"

        union_name = geo_context.get("union_name_indicator")

        # Create or Update Entry
        if sentence_index not in self.entries:
            self.entries[sentence_index] = CoverageEntry(
                scope=scope,
                key=key,
                total=scope_total or 0.0,
                sentence_index=sentence_index
            )

        entry = self.entries[sentence_index]
        if percentage is not None:
            entry.percentage = percentage
        if covered_count is not None:
            entry.covered = covered_count
        if not_covered_count is not None:
            entry.not_covered = not_covered_count
        if scope_total is not None:
            entry.total = max(entry.total, scope_total)

        entry.is_qualitative = is_qualitative
        entry.union_name = union_name

    def calculate_metrics(self) -> Dict[str, Any]:
        """
        Performs calculation of coverage rates using Parent-Sibling hierarchy logic.
        """
        from collections import defaultdict

        def is_refinement(child_total: float, parent_total: float) -> bool:
            """
            Determines if 'child_total' is a refinement (child) of 'parent_total'.
            Allows for rough approximation where child might be slightly larger due to
            rounding, contractors, or estimation differences.
            """
            # Standard case: Child is smaller
            if child_total < parent_total:
                return True

            # Edge case: Rounding/Estimates (Child slightly larger)
            # Allow up to 5% variance where child > parent
            # e.g. Parent 100k, Child 101k -> Treated as child/refinement
            if child_total <= parent_total * 1.05:
                return True

            return False

        # 1. Group entries by Key (Region/Country)
        grouped_entries = defaultdict(list)
        for e in self.entries.values():
            if e.total > 0: # Only consider entries with totals
                grouped_entries[e.key].append(e)

        region_stats = {}
        global_covered_sum = 0.0
        global_total_sum = 0.0

        for key, group in grouped_entries.items():
            # Sort by sentence index (order of appearance)
            group.sort(key=lambda x: x.sentence_index)

            # Build Hierarchy (Stack-based)
            roots = []
            stack = [] # List of CoverageEntry (parents)

            for entry in group:
                # Logic:
                # If entry.total < stack.top.total -> Child (Refinement)
                # If entry.total >= stack.top.total -> Sibling (Different Segment)

                # Pop parents that are smaller or equal (siblings/finished blocks)
                while stack and not is_refinement(entry.total, stack[-1].total):
                    stack.pop()

                if stack:
                    # entry is child of stack[-1]
                    stack[-1].children.append(entry)
                else:
                    # entry is a new root
                    roots.append(entry)

                stack.append(entry)

            # Calculate Metrics for this Key
            key_covered = 0.0
            key_total = 0.0

            def process_node(node: CoverageEntry) -> Tuple[float, float]:
                # Calculate children stats
                children_covered = 0.0
                children_total = 0.0
                for child in node.children:
                    c_cov, c_tot = process_node(child)
                    children_covered += c_cov
                    children_total += c_tot

                # Determine node stats
                node_covered = node.covered

                # If percentage exists, calculate covered
                if node.percentage is not None and node.covered == 0:
                    node_covered = (node.percentage / 100.0) * node.total

                # If not_covered exists, infer covered
                if node.not_covered > 0 and node_covered == 0:
                    node_covered = max(0, node.total - node.not_covered)

                # Enforce constraint: Parent covered >= Sum(Children covered)
                effective_covered = max(node_covered, children_covered)

                # Enforce constraint: Parent total >= Sum(Children total)
                # (Though we trust the parent total if explicit)
                effective_total = max(node.total, children_total)

                return effective_covered, effective_total

            for root in roots:
                r_cov, r_tot = process_node(root)
                key_covered += r_cov
                key_total += r_tot

            # Store stats
            if key_total > 0:
                rate = (key_covered / key_total) * 100.0
                region_stats[key] = {
                    "rate": rate,
                    "covered": key_covered,
                    "total": key_total
                }

                # Accumulate to Global (if this is a top-level region or country)
                # Note: This simple summation assumes keys are disjoint.
                # In reality, "France" is inside "Europe".
                # We should probably only sum up Regions + Independent Countries.
                # For now, we rely on the fact that usually companies report EITHER by Region OR by Country.
                # Or we can just sum everything and assume the user wants the breakdown.
                # But for the "Global Rate", we should be careful.
                # Let's assume "Global" key handles the global total if present.

                if key == "global":
                    global_covered_sum = key_covered
                    global_total_sum = key_total

        # If no explicit global key, sum up the parts?
        # This is risky if regions overlap.
        # But let's provide the "Sum of Regions" as secondary.

        sum_regions_covered = sum(s["covered"] for k, s in region_stats.items() if k != "global")
        sum_regions_total = sum(s["total"] for k, s in region_stats.items() if k != "global")

        sum_regions_rate = 0.0
        if sum_regions_total > 0:
            sum_regions_rate = (sum_regions_covered / sum_regions_total) * 100.0

        global_rate = 0.0
        if global_total_sum > 0:
            global_rate = (global_covered_sum / global_total_sum) * 100.0
        elif sum_regions_total > 0:
            global_rate = sum_regions_rate

        return {
            "global_rate": global_rate,
            "sum_of_regions_rate": sum_regions_rate,
            "region_stats": region_stats,
            "log": [],
        }


class UnionAnalyzer:
    def __init__(self):
        self.extractor = UnionExtractor()
        self.simple_analyzer = SimpleCoverageAnalyzer()
        self.complex_analyzer_cls = ComplexCoverageAnalyzer
        self.matcher = self.extractor.matcher  # Access shared matcher

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

    def _determine_geo_context(
        self, analysis: SentenceAnalysis, last_context, current_idx, last_idx
    ) -> Dict[str, Any]:
        """
        Local wrapper for geographic context determination.
        """
        return determine_geo_context(analysis, last_context, current_idx, last_idx)

    def analyze_paragraph(
        self, text: str, item_type: str = "item1", reporting_year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process a paragraph of text, splitting it into sentences and
        extracting details based on item_type (item1 or item1a).
        """
        sentences = self.extractor.split_sentences(text)
        results = []
        summary = {}

        if item_type == "item1a":
            results = self._analyze_item1a(sentences, reporting_year)
        else:
            # 1. Split into paragraphs to handle local context
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [text]

            # 2. Pass 1: Census (Populate Tracker with Totals)
            tracker = Tracker()
            all_sentences = self.extractor.split_sentences(text)
            self._populate_tracker(all_sentences, tracker, reporting_year)
            tracker.resolve()

            # 3. Pass 2: Coverage Analysis (Process Paragraphs)
            results = []
            last_geo_context = None
            prev_paragraph_totals = {}
            all_region_totals = {}

            # Note: We can use tracker.global_total instead of recalculating global_max

            for p_text in paragraphs:
                p_sentences = self.extractor.split_sentences(p_text)

                # Analyze block with context from previous paragraph
                block_results, local_totals, last_geo_context = self._analyze_block(
                    p_sentences,
                    reporting_year=reporting_year,
                    global_max_workers=tracker.global_total,
                    initial_geo_context=last_geo_context,
                    previous_totals=prev_paragraph_totals,
                )

                # Update all_region_totals with max found across all blocks
                for reg, count in local_totals.items():
                    if count > all_region_totals.get(reg, 0):
                        all_region_totals[reg] = count

                results.extend(block_results)
                # Update previous totals for the next iteration (Sliding window: only look back 1 paragraph)
                prev_paragraph_totals = local_totals

            summary = self.compute_weighted_coverage(
                results, tracker, all_region_totals
            )

        return {"items": results, "summary": summary}

    def _populate_tracker(
        self,
        sentences: List[str],
        tracker: Tracker,
        reporting_year: Optional[int] = None,
        initial_geo_context: Optional[Dict] = None,
    ):
        """
        Pass 1: Scans text specifically to find population totals (denominators)
        and populate the Tracker.
        """
        last_geo_context = initial_geo_context
        last_geo_sentence_idx = -1

        for idx, s in enumerate(sentences):
            analysis = self.extractor.analyze_sentence(s)

            # Skip historical counts
            is_historical = False
            if reporting_year and analysis.years:
                if all(y < reporting_year for y in analysis.years):
                    is_historical = True
            if (is_historical or analysis.has_historical) and not analysis.has_current:
                continue

            effective_counts = get_effective_counts(analysis)
            if effective_counts:
                # Determine context (reusing logic to ensure consistency with Pass 2)
                geo_context = self._determine_geo_context(
                    analysis, last_geo_context, idx, last_geo_sentence_idx
                )

                if geo_context["specificity"] in (
                    Specificity.EXPLICIT.value,
                    Specificity.INFERRED_UNION.value,
                ):
                    last_geo_context = geo_context
                    last_geo_sentence_idx = idx

                # Determine if this count is an explicit total
                max_count = max(effective_counts)
                count_match = next(
                    (
                        m
                        for m in analysis._matches
                        if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)
                        and m["val"] == max_count
                    ),
                    None,
                )
                span = count_match["span"] if count_match else None
                is_explicit = (
                    check_is_total_context(span, analysis.text) if span else False
                )

                range_avg = self._detect_count_range(analysis, effective_counts)
                final_count = range_avg if range_avg else max_count

                tracker.update(final_count, geo_context, is_explicit_total=is_explicit, sentence_index=idx)

    def _resolve_counts_to_geography(
        self, analysis: SentenceAnalysis
    ) -> Tuple[Dict[str, float], Optional[float]]:
        """
        Intelligently maps worker counts to geographic entities within the sentence.
        """
        mapped_counts = {}
        sentence_total = None

        # Include numbers > 5 to catch cases like "1000" (number) -> "Germany" (geo)
        counts = [
            m
            for m in analysis._matches
            if m["type"] == MatchType.WORKER_COUNT
            or (m["type"] == MatchType.NUMBER and m["val"] > 5)
        ]
        if not counts:
            return {}, None

        # Correlate GeoMatches with Spans (Explicit only)
        geo_entries = []
        geo_match_objs = [
            m for m in analysis.geo_matches if m.source_type == GeoSource.EXPLICIT
        ]
        raw_geo_matches = [m for m in analysis._matches if m["type"] == MatchType.GEO]

        # Align matches (assuming order preservation in extraction)
        if len(geo_match_objs) == len(raw_geo_matches):
            for obj, raw in zip(geo_match_objs, raw_geo_matches):
                # Use Region Name for generic accumulators, Code for countries
                key = obj.geo_code
                if obj.geo_code in REGION_CODES:
                    key = obj.region.value
                geo_entries.append({"code": key, "span": raw["span"]})

        # 1. "Respectively" Logic
        if analysis.has_respectively and len(counts) == len(geo_entries):
            # Sort both by position
            s_counts = sorted(counts, key=lambda x: x["span"][0])
            s_geos = sorted(geo_entries, key=lambda x: x["span"][0])
            for c, g in zip(s_counts, s_geos):
                mapped_counts[g["code"]] = c["val"]
            return mapped_counts, None

        # 2. Summation Check (Total vs Parts)
        vals = [c["val"] for c in counts]
        max_val = max(vals)
        sum_val = sum(vals)
        others_sum = sum_val - max_val

        parts = counts
        if len(counts) > 1 and others_sum > 0:
            # If sum of others is close to max (within 10%), treat max as total
            if abs(max_val - others_sum) / max_val < 0.10:
                sentence_total = max_val
                parts = [c for c in counts if c["val"] != max_val]

        # 3. Proximity Mapping (Greedy)
        if geo_entries:
            pairs = []
            for c in parts:
                c_mid = (c["span"][0] + c["span"][1]) / 2
                for g in geo_entries:
                    g_mid = (g["span"][0] + g["span"][1]) / 2
                    dist = abs(c_mid - g_mid)
                    pairs.append((dist, c, g))

            pairs.sort(key=lambda x: x[0])
            used_c, used_g = set(), set()

            for dist, c, g in pairs:
                if dist < 150 and id(c) not in used_c and g["code"] not in used_g:
                    mapped_counts[g["code"]] = c["val"]
                    used_c.add(id(c))
                    used_g.add(g["code"])

        return mapped_counts, sentence_total

    
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

            if i + 1 < len(results):
                next_item = results[i + 1]
                if "geographic_context" not in next_item:
                    continue

                # Criteria: Next item inherits from Current, and Current has data
                c_pct = current["coverage_data"].get("percentage")
                is_saturated = c_pct == 100.0
                is_empty = c_pct == 0.0

                if (
                    next_item["geographic_context"]["specificity"]
                    == Specificity.INHERITED.value
                    and next_item["geographic_context"].get(
                        "inherited_from_sentence_index"
                    )
                    == current.get("sentence_index")
                    and not is_saturated
                    and not is_empty
                ):

                    c_data = current["coverage_data"]
                    n_data = next_item["coverage_data"]

                    should_merge = True

                    # 1. Data Collision Check
                    # Do not merge if both items have data for the same field
                    if c_data["percentage"] is not None and n_data["percentage"] is not None:
                        should_merge = False
                    if c_data["employee_count_covered"] is not None and n_data["employee_count_covered"] is not None:
                        should_merge = False
                    if c_data["employee_count_not_covered"] is not None and n_data["employee_count_not_covered"] is not None:
                        should_merge = False

                    # 2. Subject Conflict Check (Specific Unions)
                    # Do not merge if both items mention different specific unions (e.g. UAW vs Teamsters)
                    if should_merge:
                        k_curr = current.get("keyword_matched")
                        k_next = next_item.get("keyword_matched")
                        if k_curr and k_next:
                            specific_curr = {t for t in k_curr if t.lower() in self.matcher.union_map}
                            specific_next = {t for t in k_next if t.lower() in self.matcher.union_map}

                            if specific_curr and specific_next and specific_curr.isdisjoint(specific_next):
                                should_merge = False
                    # 3. Worker Term Conflict Check
                    if should_merge:
                        w_curr = current.get("worker_terms", [])
                        w_next = next_item.get("worker_terms", [])

                        if w_curr and w_next:
                            generic_terms = {
                                "employee",
                                "employees",
                                "worker",
                                "workers",
                                "laborer",
                                "laborers",
                                "staff",
                                "personnel",
                                "workforce",
                                "workforces",
                                "associate",
                                "associates",
                            }

                            spec_curr = {
                                w.lower()
                                for w in w_curr
                                if w.lower() not in generic_terms
                            }
                            spec_next = {
                                w.lower()
                                for w in w_next
                                if w.lower() not in generic_terms
                            }

                            if (
                                spec_curr
                                and spec_next
                                and spec_curr.isdisjoint(spec_next)
                            ):
                                should_merge = False

                    if should_merge:
                        # Merge Percentage
                        if (
                            c_data["percentage"] is None
                            and n_data["percentage"] is not None
                        ):
                            c_data["percentage"] = n_data["percentage"]
                            c_data["negated"] = n_data["negated"]
                            c_data["negation_type"] = n_data["negation_type"]
                            c_data["type"] = n_data["type"]
                            c_data["note"] = (
                                (c_data["note"] or "") + " | " + (n_data["note"] or "")
                            )

                        # Merge Counts
                        if not c_data["employee_count_covered"] and n_data["employee_count_covered"]:
                            c_data["employee_count_covered"] = n_data["employee_count_covered"]

                        if not c_data["employee_count_not_covered"] and n_data["employee_count_not_covered"]:
                            c_data["employee_count_not_covered"] = n_data["employee_count_not_covered"]

                    skip_indices.add(i + 1)

            merged_results.append(current)
        return merged_results

    def _analyze_block(
        self,
        sentences: List[str],
        reporting_year: Optional[int] = None,
        global_max_workers: float = 0.0,
        initial_geo_context: Optional[Dict] = None,
        previous_totals: Optional[Dict[str, float]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], Optional[Dict]]:
        """
        Analyzes a block of sentences (paragraph) for Item 1.
        Returns results, totals found in THIS block, and the final geo context.
        """
        # 0. Local Census (Pre-scan paragraph)
        local_tracker = Tracker()
        self._populate_tracker(
            sentences,
            local_tracker,
            reporting_year,
            initial_geo_context=initial_geo_context,
        )
        local_tracker.resolve()

        results = []
        analyzed_sentences = [self.extractor.analyze_sentence(s) for s in sentences]

        # Context inheritance state
        last_geo_context = initial_geo_context
        last_geo_sentence_idx = -1
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

        for idx, analysis in enumerate(analyzed_sentences):
            sent = sentences[idx]

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

            # 2. Update Context (Worker Counts)
            effective_counts = get_effective_counts(analysis)
            if effective_counts and not is_historical:
                last_employee_count = max(effective_counts)

            # 3. Relevance Check
            has_coverage = bool(analysis.percentages or analysis.negation_terms)
            has_worker_context = bool(analysis.worker_terms or effective_counts)
            is_relevant = (
                bool(
                    analysis.union_terms
                    or analysis.geo_matches
                    or analysis.negation_terms
                    or analysis.qualitative_membership_terms
                )
                or (has_coverage and has_worker_context)
                or bool(effective_counts)
            )

            if not is_relevant:
                continue

            # 4. Determine Geographic Context
            geo_context = self._determine_geo_context(
                analysis, last_geo_context, idx, last_geo_sentence_idx
            )

            if geo_context["specificity"] in (
                Specificity.EXPLICIT.value,
                Specificity.INFERRED_UNION.value,
            ):
                last_geo_context = geo_context
                last_geo_sentence_idx = idx

            # 5. Update Region Totals
            census_update_note = None
            if effective_counts:
                # Check for range first
                range_avg = self._detect_count_range(analysis, effective_counts)

                if range_avg:
                    current_val = range_avg
                    mapped_counts = {}
                else:
                    # Try intelligent mapping first
                    mapped_counts, sent_total = self._resolve_counts_to_geography(
                        analysis
                    )
                    current_val = max(effective_counts)

                updates_found = []

                if mapped_counts:
                    # Use specific mappings
                    for code, count in mapped_counts.items():
                        # Check if this is a source of the total (Update vs Previous)
                        prev_val = previous_totals.get(code, 0) if previous_totals else 0
                        curr_max = effective_totals.get(code, 0)
                        if count > prev_val and count >= curr_max:
                            updates_found.append(f"{code}: {count}")

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

                        prev_val = previous_totals.get(region_key, 0) if previous_totals else 0
                        curr_max = effective_totals.get(region_key, 0)
                        if current_val > prev_val and current_val >= curr_max:
                            updates_found.append(f"{region_key}: {current_val}")

                        if current_val > local_totals.get(region_key, 0):
                            local_totals[region_key] = current_val

                        if current_val > effective_totals.get(region_key, 0):
                            effective_totals[region_key] = current_val

                        for c in geo_context.get("countries", []):
                            c_code = c["code"]
                            
                            prev_val = previous_totals.get(c_code, 0) if previous_totals else 0
                            curr_max = effective_totals.get(c_code, 0)
                            if current_val > prev_val and current_val >= curr_max:
                                updates_found.append(f"{c_code}: {current_val}")

                            # Only update if we didn't map it specifically above (though mapped_counts check covers this)
                            if current_val > local_totals.get(c_code, 0):
                                local_totals[c_code] = current_val
                            if current_val > effective_totals.get(c_code, 0):
                                effective_totals[c_code] = current_val
                
                if updates_found:
                    unique_updates = sorted(list(set(updates_found)))
                    census_update_note = f"Updates lookup: {', '.join(unique_updates)}"

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

            # 8. External Source Fallback
            if not relevant_total:
                relevant_total = get_external_worker_count(
                    current_region, geo_context.get("countries", [])
                )

            # 7. Determine Coverage Data (Dispatch)
            coverage_data = self._determine_coverage_data(
                analysis, relevant_total, reporting_year, is_historical=is_historical
            )

            # 8. Construct Result
            should_include = False
            has_data = (
                coverage_data.get("percentage") is not None
                or coverage_data.get("employee_count_covered") is not None
                or coverage_data.get("negated")
            )

            if analysis.union_terms:
                should_include = True
            elif has_data and geo_context["specificity"] != Specificity.IMPLICIT.value:
                should_include = True

            # Exclude "monitoring" statements with no data (Statement Only)
            # e.g. "We are committed to constructive engagement..."
            if (
                should_include
                and (not has_data or analysis.relationship_terms)
                and BOILERPLATE_REGEX.search(sent)
            ):
                should_include = False

            # Exclude personnel events (layoffs, hiring) if no union keywords are present
            # e.g. "We laid off 500 employees." (Avoids treating 500 as a workforce total)
            if (
                should_include
                and not analysis.union_terms
                and PERSONNEL_EVENT_REGEX.search(sent)
            ):
                should_include = False

            # Filter out Risk Items embedded in Item 1 (Use boilerplate block)
            if (analysis.risk_terms and not has_data) or BOILERPLATE_REGEX.search(sent):
                risk_item = create_risk_item(
                    sent, analysis, is_historical=is_historical
                )
                if risk_item:
                    results.append(risk_item)
                should_include = False

            if should_include:
                item = {
                    "sentence": sent,
                    "keyword_matched": analysis.union_terms or None,
                    "geographic_context": geo_context,
                    "coverage_data": coverage_data,
                    "lookup_totals": effective_totals.copy(),
                    "census_note": census_update_note,
                    "sentence_index": idx,
                }
                results.append(item)

        merged_results = self._merge_continuation_items(results)

        return merged_results, effective_totals, last_geo_context

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

        if is_simple_scenario(analysis):
            data = self.simple_analyzer.analyze(analysis)
        else:
            data = self._analyze_complex_coverage(analysis, inherited_total_count)

        # Common Post-Processing (Temporal Scope, etc.)
        data.setdefault("temporal_scope", TemporalScope.CURRENT.value)
        if is_historical:
            data["temporal_scope"] = TemporalScope.HISTORICAL.value

        # Relationship Status
        rel_status = determine_relationship_status(analysis)
        if rel_status:
            data["relationship_status"] = rel_status

        # Qualitative Quants (Soft Percent) - Fallback if no explicit data found
        if data["percentage"] is None:
            qual_matches = [
                m
                for m in analysis._matches
                if m["type"]
                in (MatchType.QUALITATIVE_TERM, MatchType.QUALITATIVE_MEMBERSHIP)
            ]
            if qual_matches:
                match = qual_matches[0]
                term = match.get("term_obj")
                pattern_str = match.get("pattern_str", "")

                if term:
                    assert isinstance(term, QualitativeTerm)
                    is_locally_negated = check_local_negation(
                        match["span"], analysis.text
                    )
                    if term.is_absolute:
                        data["percentage"] = term.positive_pct
                        data["type"] = CoverageType.QUALITATIVE.value
                        data["note"] = f"Absolute qualitative: '{pattern_str}'"
                    else:
                        pct = term.get_percentage(is_negated=is_locally_negated)
                        if pct is not None:
                            data["percentage"] = pct
                            data["type"] = CoverageType.QUALITATIVE.value
                            data["note"] = f"Qualitative: '{pattern_str}' -> {pct}%"

        return data

    def _analyze_complex_coverage(
        self, analysis: SentenceAnalysis, total_count: Optional[float]
    ) -> Dict[str, Any]:
        """
        Handles complex scenarios: mixed coverage, ratios, inferred totals, etc.
        (Placeholder for the complex logic to be re-added/refined)
        """
        analyzer = self.complex_analyzer_cls(analysis, total_count)
        return analyzer.analyze()

    def _analyze_item1a(
        self, sentences: List[str], reporting_year: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyzes sentences for Item 1A (Risk Factors).
        """
        results = []
        for sent in sentences:
            analysis = self.extractor.analyze_sentence(sent)

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
                result = create_risk_item(sent, analysis, is_historical=is_historical)
                if result:
                    results.append(result)
        return results

    def compute_weighted_coverage(
        self,
        results: List[Dict[str, Any]],
        tracker: Tracker,
        region_totals: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Computes weighted average coverage and derived regional stats using Tracker data.
        """
        # Populate Tracker with Coverage Data from Results
        for item in results:
            data = item.get("coverage_data", {})
            geo = item.get("geographic_context", {})

            # Skip non-current
            if data.get("temporal_scope") != TemporalScope.CURRENT.value:
                continue

            pct = data.get("percentage")
            covered = data.get("employee_count_covered")
            not_covered = data.get("employee_count_not_covered")
            total = data.get("employee_count_total")

            # Try to resolve not_covered to covered
            if covered is None and not_covered is not None:
                if total and total >= not_covered:
                    covered = total - not_covered
                else:
                    # Try to find total from Tracker if not in item
                    scope_total = None
                    region = geo.get("region")
                    countries = geo.get("countries", [])

                    if len(countries) == 1:
                        code = countries[0]["code"]
                        scope_total = tracker.country_totals.get(code)
                    elif region and region not in (
                        Region.INTERNATIONAL.value,
                        Region.UNKNOWN.value,
                    ):
                        scope_total = tracker.region_totals.get(region)
                    elif region in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
                        scope_total = tracker.global_total

                    if scope_total and scope_total >= not_covered:
                        covered = scope_total - not_covered

            is_qual = data.get("type") == CoverageType.QUALITATIVE.value

            tracker.record_coverage(
                pct,
                covered,
                geo,
                scope_total=total,
                not_covered_count=not_covered,
                is_qualitative=is_qual,
                sentence_index=item.get("sentence_index", -1)
            )

        # Calculate Metrics
        metrics = tracker.calculate_metrics()
        region_stats = metrics.get("region_stats", {})

        return {
            "weighted_average_percentage": metrics["global_rate"],
            "likely_percentage": metrics["global_rate"],
            "secondary_percentage": metrics["sum_of_regions_rate"],
            "derived_regional_coverage": {
                r: m["rate"] for r, m in region_stats.items()
            },
            "derived_regional_covered_counts": {
                r: m["covered"] for r, m in region_stats.items()
            },
            "derived_regional_not_covered_counts": {
                r: m["total"] - m["covered"] for r, m in region_stats.items()
            },
            "derived_regional_total_counts": {
                r: m["total"] for r, m in region_stats.items()
            },
            "census_global_total": tracker.global_total,
            "census_region_totals": tracker.region_totals,
            "census_country_totals": tracker.country_totals,
            "resolution_log": metrics.get("log", []),
        }
