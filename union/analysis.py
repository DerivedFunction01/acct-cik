from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Union
import re
from dataclasses import dataclass, field

from extraction import (
    NEGATION_REGEX,
    OR_REGEX,
    QualitativeTerm,
    UnionExtractor,
    SentenceAnalysis,
    MatchType,
    OF_REGEX,
    QUALITATIVE_MULTIPLIERS,
    REMAIN_REGEX,
)
from defs.region_regex import (
    REGION_CODES, Region, INT_LANGUAGE_MAP, GeoSource, _CODE_TO_REGION
)
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
    UNION_REGEX,
)

GENERIC_WORKER_TERMS = {
    "employee", "worker", "laborer", "personnel", "workforce", 
    "associate", "staff", "employees", "workers", "laborers", "associates"
}


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

# Delimiters: , ; or words like while, although, but, however
SEGMENT_DELIMITER_REGEX = re.compile(
    r"(?<!\d)[:;](?!\d)|\b(?:while|although|whereas|but|however|except|yet)|(?:,)(?!(?:\s+or))\b", re.IGNORECASE
)

def get_text_segments(text: str) -> List[Tuple[int, int]]:
    delimiters = list(SEGMENT_DELIMITER_REGEX.finditer(text))
    boundaries = [0] + [m.end() for m in delimiters] + [len(text)]
    segments = []
    for i in range(len(boundaries) - 1):
        segments.append((boundaries[i], boundaries[i + 1]))
    return segments

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
            other_status=other_status
        )
        notes.append(msg)


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
        """Handles cases with exactly one percentage and one count.
        NO OR:
            Case 1: We employ 10000 employees, 60% are unionized.  (Covered Count is PCT * COUNT)
            Case 2: We employ 10000 unionzied employees, presenting 60% of the workforce. (Covered Count is COUNT)
        WITH OR:
            Case 3: We employ 10000 unionized employees, or 60% of out total workforce. (Covered Count is COUNT)
        OF COUNT/ FALLBACK
        Case 4: 60% of our 1000 employees are unionized. (Covered Count is PCT * COUNT)

        """
        pct = analysis.percentages[0]
        count = effective_counts[0]

        data["percentage"] = pct
        data["type"] = CoverageType.EXPLICIT_PERCENT.value
        notes.append(f"Explicit percentage: {pct}%")

        # Locate matches
        pct_match = next((m for m in analysis._matches if m["type"] == MatchType.PERCENT and m["val"] == pct), None)
        count_match = next((m for m in analysis._matches if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER) and m["val"] == count), None)

        if not pct_match or not count_match:
            data["employee_count_total"] = count
            return

        # Analyze relationship between matches
        p_span, c_span = pct_match["span"], count_match["span"]
        if p_span[1] <= c_span[0]:
            between = analysis.text[p_span[1]:c_span[0]]
        else:
            between = analysis.text[c_span[1]:p_span[0]]

        # Determine if 'count' represents the Total population
        is_count_total = False

        # 1. Explicit "OR" relationship (Equivalence -> Count is Subset)
        if OR_REGEX.search(between):
            is_count_total = False
            notes.append("Logic: OR detected -> Count is Covered")
        # 2. Explicit "OF" relationship (Partitive -> Count is Total)
        elif OF_REGEX.search(between):
            is_count_total = True
            notes.append("Logic: OF detected -> Count is Total")
        # 3. Proximity to Union Term (Heuristic)
        else:
            dist_pct = get_min_distance_to_matches(pct_match["span"], analysis._matches, UNION_MATCH_TYPES)
            dist_count = get_min_distance_to_matches(count_match["span"], analysis._matches, UNION_MATCH_TYPES)
            # If union term is closer to Percentage -> Percentage describes coverage -> Count is Total
            if dist_pct < dist_count:
                is_count_total = True
                notes.append("Logic: Union term closer to PCT -> Count is Total")
            else:
                is_count_total = False
                notes.append("Logic: Union term closer to Count -> Count is Covered")

        # Check for negation on the percentage
        is_negated = False
        if analysis.negation_terms and check_local_negation(pct_match["span"], analysis.text, backward=50, forward=50):
            is_negated = True

        if is_count_total:
            ratio = round((pct / 100.0) * count)
            
            apply_coverage_logic(
                data,
                total=count,
                subset=ratio,
                is_negated=is_negated,
                notes=notes,
                note_fmt="Count (total): {total}. {subset} {status}." + (" (negated)" if is_negated else "")
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
                note_fmt="Count ({status}): {subset}. Inferred total {total}."
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
                if (MatchType.WORKER_COUNT, MatchType.NUMBER) and m["val"] == c1
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
                # Check for multiple specific unions to infer disjoint sets (Sum)
                union_matches = [
                    m for m in analysis._matches 
                    if m["type"] in (MatchType.SPECIFIC_UNION, MatchType.UNION_NAME)
                ]
                unique_unions = {m["val"].lower() for m in union_matches}
                
                if len(unique_unions) >= 2:
                    is_subset = False
                    notes.append("Logic: 'and' with multiple unions -> Sum")

        if is_subset:
            total, part = max(c1, c2), min(c1, c2)
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

                    apply_coverage_logic(
                        data,
                        total=total,
                        subset=part,
                        is_negated=is_negated,
                        notes=notes,
                        note_fmt="Count ({status}): {subset} of {total}. Inferred {other} {other_status}."
                    )
                else:
                    # Part is not near union term -> Assume it's just a subset (e.g. "20 in marketing")
                    # Record total only
                    data["employee_count_total"] = total
                    notes.append(
                        f"Count (total): {total}. Subset {part} not associated with union."
                    )
        else:
            total = c1 + c2
            apply_coverage_logic(
                data,
                total=total,
                subset=total,
                is_negated=bool(analysis.negation_terms),
                notes=notes,
                note_fmt="Count ({status}): {subset} (Sum of {other} + {subset} is wrong here, logic handled sum)"
            )
            # Fix note for sum case
            notes[-1] = f"Count ({'not covered' if analysis.negation_terms else 'covered'}): {c1} + {c2} = {total}"

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
                        if term.is_all and not is_term_negated:
                            data["type"] = CoverageType.EXPLICIT_PERCENT.value
                        else:
                            data["type"] = CoverageType.QUALITATIVE.value
                        if term.lower_bound is not None and term.upper_bound is not None and (term.is_absolute or not is_term_negated):
                            data["qualitative_bounds"] = (term.lower_bound, term.upper_bound)

                        has_status_negation = any(
                            m["type"] in (MatchType.NON_UNION, MatchType.NON_COVERAGE)
                            for m in analysis._matches
                        )

                        ratio = round((pct / 100.0) * count)
                        apply_coverage_logic(
                            data,
                            total=count,
                            subset=ratio,
                            is_negated=has_status_negation,
                            notes=notes,
                            note_fmt=f"Qualitative '{qual_match['text']}' of {{total}} total -> {{subset}} {{status}}" + (" (negated)" if has_status_negation else "")
                        )
                else:
                    data["type"] = CoverageType.CALCULATED.value
                    data["employee_count_total"] = count
                    notes.append(f"Count (total): {count} (qualitative term present)")

            elif is_associated:
                apply_coverage_logic(
                    data,
                    total=count,
                    subset=count,
                    is_negated=bool(analysis.negation_terms),
                    notes=notes,
                    note_fmt="Count ({status}): {subset}"
                )
                data["type"] = CoverageType.CALCULATED.value
            elif analysis.negation_terms: # single count ..... are nonunion at this stage.
                apply_coverage_logic(
                    data,
                    total=count,
                    subset=count,
                    is_negated=True,
                    notes=notes,
                    note_fmt="Count ({status}): {subset}"
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
        notes: List[str]):
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
                    "negation_type": NegationType.ZERO_COVERAGE.value if analysis.negation_terms else None,
                    "type": CoverageType.REMAINING.value,
                }
            )
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
            self._handle_remaining(analysis, effective_counts, data, notes)
            if not data.get("type") == CoverageType.REMAINING.value:
                self._handle_qualitative_zero(analysis, effective_counts, data, notes)
            

        data["note"] = " | ".join(notes) if notes else "Simple Analysis (No Data)"
        data["employee_count_total"]
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
    def create_risk_item(self, sentence: str, analysis: SentenceAnalysis, is_historical: bool = False
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


def get_external_worker_count(
    region: str, countries: List[Dict[str, str]]
) -> Optional[float]:
    """
    Placeholder: Connect to external DB to get worker counts for a region/country.
    """
    return None

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
_RANGE_TO_THROUGH = re.compile(r"\b((?<!compared\s)to|through)(?:\s+\S+){0,2}$", re.IGNORECASE)
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

    subset_regex = re.compile(r"\bof\s+(?:whom|which|these|those)\b", re.IGNORECASE)

    def __init__(self, analysis: SentenceAnalysis, total_count: Optional[float]):
        self.analysis = analysis
        self.total_count = total_count
        self.data = {
            "percentage": None,
            "employee_count_covered": None,
            "employee_count_not_covered": None,
            "employee_count_total": total_count,
            "negated": False,
            "negation_type": None,
            "type": CoverageType.NONE.value,
            "qualitative_bounds": None,
            "note": None,
        }

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

                        apply_coverage_logic(
                            self.data,
                            total=round(avg),
                            subset=round(avg),
                            is_negated=is_negated,
                            notes=None
                        )
                        self.data["note"] = f"Averaged from range {c1} to {c2} ({'not covered' if is_negated else 'covered'})"
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
            apply_coverage_logic(
                self.data,
                total=large,
                subset=small,
                is_negated=is_negated,
                notes=notes,
                note_fmt="Match: {subset}/{total} ~= " + f"{pct}%" + (" (Negated)" if is_negated else "") + ". Total {total}."
            )
            matched = True

        # Check 2: small / (small+large) ~= pct
        elif abs(ratio_part_sum - pct) < 2.0:
            apply_coverage_logic(
                self.data,
                total=total_sum,
                subset=small,
                is_negated=is_negated,
                notes=notes,
                note_fmt="Match: {subset}/({subset}+{other}) ~= " + f"{pct}%" + (" (Negated)" if is_negated else "") + ". Total {total}."
            )
            matched = True

        # Check 3: large / (small+large) ~= pct
        elif abs(ratio_large_sum - pct) < 2.0:
            apply_coverage_logic(
                self.data,
                total=total_sum,
                subset=large,
                is_negated=is_negated,
                notes=notes,
                note_fmt="Match: {subset}/({other}+{subset}) ~= " + f"{pct}%" + (" (Negated)" if is_negated else "") + ". Total {total}."
            )
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
        # We capture delimiters to analyze list structure
        segments = get_text_segments(self.analysis.text)

        # Helper to find segment index
        def get_seg_idx(pos):
            return next((i for i, (s, e) in enumerate(segments) if s <= pos < e), -1)

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

        # Check which segments have coverage terms
        segments_with_context = set()
        for m in positives + negatives:
             mid = (m["span"][0] + m["span"][1]) / 2
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

        # 3b. "Of Whom" / "Of Which" Logic (Subset Indicator)
        # If we have counts followed by "of whom/which ... union", the counts are TOTAL.
        # e.g. "10 employees, 0% of whom are union" -> 10 is Total.
        subset_indicator_spans = []
        for m in self.analysis._matches:
            # Check for "of whom", "of which", "of these"
            if m["type"] == MatchType.PERCENT:
                # Look immediately before the percent for "of whom" pattern isn't captured by regex usually
                # But we can check text between last count and this percent
                pass
        
        # We'll check this dynamically during assignment
        def is_followed_by_subset_indicator(count_match):
            # Look ahead for "of whom", "of which" before the next count or end of sentence
            start = count_match["span"][1]
            window = self.analysis.text[start : start + 100]
            return bool(self.subset_regex.search(window))

        def get_segment_range(span):
            mid = (span[0] + span[1]) / 2
            for start, end in segments:
                if start <= mid < end:
                    return start, end
            return 0, len(self.analysis.text)

        def get_nearest_type_in_segment(target_span):
            nonlocal logic_notes
            seg_start, seg_end = get_segment_range(target_span)
            t_start, t_end = target_span

            # If this count is followed by "of whom", it is explicitly a TOTAL (denominator)
            if is_followed_by_subset_indicator({"span": target_span}):
                logic_notes.append("Subset Indicator -> Total")
                return "total"

            best_dist = float("inf")
            best_type = None

            candidates = []
            # If global context, use all matches. Else filter by segment.
            search_positives = positives if is_global_context else [p for p in positives if p["span"][0] >= seg_start and p["span"][1] <= seg_end]
            search_negatives = negatives if is_global_context else [n for n in negatives if n["span"][0] >= seg_start and n["span"][1] <= seg_end]
            search_totals = totals if is_global_context else [t for t in totals if t["span"][0] >= seg_start and t["span"][1] <= seg_end]

            for p in search_positives:
                    candidates.append(("covered", p))
            for n in search_negatives:
                    candidates.append(("not_covered", n))
            for t in search_totals:
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

        # 4. Assign Initial Types to Counts
        count_assignments = []  # List of dicts: {match, type, segment_idx}

        for c in _counts:
            # Find segment index
            c_mid = (c["span"][0] + c["span"][1]) / 2
            seg_idx = get_seg_idx(c_mid)

            # Get local type
            ctype = get_nearest_type_in_segment(c["span"])
            count_assignments.append({"match": c, "type": ctype, "seg_idx": seg_idx})

        # 5. Propagate Types (List Logic)
        # Sort by position
        count_assignments.sort(key=lambda x: x["match"]["span"][0])

        def is_connected(idx1, idx2):
            if is_global_context:
                return True
            if count_assignments[idx1]["seg_idx"] == count_assignments[idx2]["seg_idx"]:
                return True
            return False

        # Forward Propagation
        for i in range(len(count_assignments) - 1):
            if count_assignments[i]["type"] is not None and count_assignments[i + 1]["type"] is None:
                if is_connected(i, i + 1):
                    count_assignments[i + 1]["type"] = count_assignments[i]["type"]
                    logic_notes.append("Propagated Forward")

        # Backward Propagation
        for i in range(len(count_assignments) - 1, 0, -1):
            if count_assignments[i]["type"] is not None and count_assignments[i - 1]["type"] is None:
                if is_connected(i, i - 1):
                    count_assignments[i - 1]["type"] = count_assignments[i]["type"]
                    logic_notes.append("Propagated Backward")
                    
        self.data["_count_assignments"] = count_assignments
        
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
        for item in count_assignments:
            ctype = item["type"]
            val = item["match"]["val"]
            if ctype == "covered":
                current = self.data["employee_count_covered"] or 0
                self.data["employee_count_covered"] = current + val
            elif ctype == "not_covered":
                current = self.data["employee_count_not_covered"] or 0
                self.data["employee_count_not_covered"] = current + val
            elif ctype == "total":
                total_candidates.append(val)

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
            
        if logic_notes:
            current_note = self.data["note"] or ""
            sep = " | " if current_note else ""
            unique_notes = []
            for n in logic_notes:
                if n not in unique_notes:
                    unique_notes.append(n)
            self.data["note"] = current_note + sep + "; ".join(unique_notes)

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
                    # Use region enum value for consistency with Tracker keys
                    r_obj = {"name": m.region.value, "code": m.geo_code, "countries": []}
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

            # Try to resolve against last_context if available
            if last_context and last_context.get("countries") and m.geo_code:
                allowed_codes = INT_LANGUAGE_MAP[m.geo_code]
                # Find first country in last_context that matches the language
                matching_country = next(
                    (c for c in last_context["countries"] if c["code"] in allowed_codes),
                    None,
                )
                if matching_country:
                    region_name = _CODE_TO_REGION.get(matching_country["code"], Region.UNKNOWN.value)
                    return {
                        "region": region_name,
                        "countries": [matching_country],
                        "specificity": Specificity.INFERRED_LANG.value,
                        "union_name_indicator": m.text,
                        "note": f"Resolved language term '{m.text}' to {matching_country['name']} from context",
                    }

            return {
                "region": Region.INTERNATIONAL.value,  # Broad region
                "countries": [],  # No specific country known
                "specificity": Specificity.INFERRED_LANG.value,
                "union_name_indicator": m.text,
                "note": f"Inferred from language term '{m.text}' ({m.geo_code})",
            }

    # 2.5 Global Modifiers (Stop Inheritance)
    # If the sentence contains modifiers that imply a global/consolidated scope,
    # treat it as International and do NOT inherit from previous context.
    strong_global_modifiers = {"global", "international"}
    if any(m.lower() in strong_global_modifiers for m in analysis.total_modifiers):
        return {
            "region": Region.INTERNATIONAL.value,
            "countries": [{"code": "GLO", "name": "Global"}],
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


class Scope(Enum):
    GLOBAL = "GLOBAL" # the catch all "global workforce"
    REGION = "REGION" # Should not be used for counts; only as placeholders
    COUNTRY = "COUNTRY" # Should not be used for counts; only as placeholders
    AGGREGATE = "AGGREGATE"
    SEGMENT = "SEGMENT" # Any mention is a segment
    UNKNOWN = "UNKNOWN"

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
    covered_count: Optional[float] = None # If null, do not derive from total - not covered. Internal sentence logic dictates this
    not_covered_count: Optional[float] = None
    percentage: Optional[float] = None
    total_count: Optional[float] = None # The sum of covered + not covered.
    key: Optional[str] = "unknown" # Union name or location. Else it belongs to the generic bucket
    is_qualitative: bool = False
    is_explicit: bool = False # The firm plainly states that it is the total of something within that scope
    qualitative_bounds: Optional[Tuple[float, float]] = None
    is_remaining: bool = False
    is_negated: bool = False
    is_union_record: bool = False
    scope: Scope = Scope.UNKNOWN
    sent_idx: int = -1 # The sentence index
    related_geo_codes: List[str] = field(default_factory=list)


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
        self.mentioned_countries: set[str] = set()
        self.domestic_country_code = domestic_country_code

    def update(
        self, count: float, geo_context: Dict[str, Any]
    ):
        # 1. Update Lookups (Keep for analyze_block usage)
        # This logic is simplified to just maintain max values for lookups
        # The actual rate calculation will happen in calculate_metrics using self.entries

        region = geo_context.get("region")
        countries = geo_context.get("countries", [])
        codes = {c.get("code") for c in countries}

        # 1. Global Update
        if "GLO" in codes or (region == Region.UNKNOWN.value and not codes):
            self.global_total = max(self.global_total, count)

        # 2. Regional Update
        if region and region not in (Region.UNKNOWN.value,):
            # If International Region, only update if it's NOT Global code
            if region == Region.INTERNATIONAL.value and "GLO" in codes:
                pass
            else:
                current = self.region_totals.get(region, 0)
                if count > current:
                    self.region_totals[region] = count

        # 3. Country Update
        if len(countries) == 1:
            c = countries[0]
            code = c["code"]
            if code == "DOM":
                code = self.domestic_country_code
            if count > self.country_totals.get(code, 0):
                self.country_totals[code] = count

    def register_mentions(self, geo_context: Dict[str, Any]):
        countries = geo_context.get("countries", [])
        for c in countries:
            if c.get("code"):
                code = c["code"]
                if code == "DOM":
                    code = self.domestic_country_code
                self.mentioned_countries.add(code)

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
        sentence_index: int = -1
    ):
        """
        Records coverage data (rate or count) for a specific geographic scope.
        """
        if sentence_index < 0:
            return

        region = geo_context.get("region")
        countries = geo_context.get("countries", [])
        union_name = geo_context.get("union_name_indicator")

        # Determine scope
        scope = Scope.GLOBAL
        key = scope.value

        codes = [c.get("code") for c in countries]

        if region and region not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
            scope = Scope.REGION
            key = region
        elif region == Region.INTERNATIONAL.value:
            if "GLO" in codes:
                scope = Scope.GLOBAL
                key = Scope.GLOBAL.value
            else:
                scope = Scope.REGION
                key = region
        elif region == Region.UNKNOWN.value:
            if "DOM" in codes:
                key = self.domestic_country_code
                scope = Scope.COUNTRY
            else:
                key = Region.DOMESTIC.value
                scope = Scope.REGION

        if len(countries) == 1:
            country_code = countries[0]["code"]
            if country_code == "DOM":
                country_code = self.domestic_country_code
            scope = Scope.SEGMENT
            key = f"{country_code}::Segment_{len(self.entries)}"

        elif len(countries) > 1:
            scope = Scope.AGGREGATE
            key = region if region else Scope.AGGREGATE.value

        if union_name:
            country_code = countries[0]["code"]
            if country_code == "DOM":
                country_code = self.domestic_country_code
            scope = Scope.SEGMENT
            key = f"{country_code}::{union_name}"

        related_codes = [c["code"] for c in countries if c.get("code")]
        if "regions" in geo_context:
            related_codes.extend([r["name"] for r in geo_context["regions"] if r.get("name")])

        self.entries.append(Entry(
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
            related_geo_codes=related_codes
        ))

    def _get_tolerance(self, entries: List[Entry], base_threshold: float = 0.05) -> float:
        """
        Returns a looser tolerance if any entry is qualitative.
        """
        if any(e.is_qualitative for e in entries):
            return max(base_threshold, 0.20)
        return base_threshold

    def _matches_census(self, val: float, census: float, threshold: float = 0.05) -> bool:
        """
        Checks if value matches census within threshold or rounding error.
        """
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
        # Only consider entries with a known total population
        candidates = [e for e in entries if e.total_count is not None]
        if len(candidates) < 2:
            return

        # 1. Sliding Window (Breakdowns within breakdowns)
        # Sort by sentence index to respect narrative flow
        by_sent = sorted(candidates, key=lambda x: x.sent_idx)

        for i in range(len(by_sent)):
            parent = by_sent[i]
            current_sum = 0.0
            group: List[Entry] = []

            # Look ahead for children
            for j in range(i + 1, len(by_sent)):
                child = by_sent[j]

                # Skip if child is larger than parent (likely not a part)
                if child.total_count >= parent.total_count: # type: ignore
                    continue

                current_sum += child.total_count # type: ignore
                group.append(child)

                # Check match
                if self._matches_census(parent.total_count, current_sum, threshold=0.05): # type: ignore
                    # Check coverage consistency
                    p_cov = parent.covered_count
                    c_cov_sum = sum(g.covered_count or 0.0 for g in group)

                    msg = f"Breakdown Detected {name}: {parent.total_count} (sent {parent.sent_idx}) matches sum of {len(group)} items."

                    if p_cov is not None:
                        # Dynamic tolerance for qualitative entries
                        tolerance = self._get_tolerance([parent] + group, base_threshold=0.10)
                        if self._matches_census(p_cov, c_cov_sum, threshold=tolerance):
                            msg += f" Covered counts also match ({p_cov})."
                        else:
                            msg += f" BUT Covered counts mismatch ({p_cov} vs {c_cov_sum})."

                    self.resolution_log.append(msg)
                    break

                if current_sum > parent.total_count * 1.1: # type: ignore
                    break

        # 2. Global Parent vs All Children (Fallback)
        by_size = sorted(candidates, key=lambda x: x.total_count, reverse=True) # type: ignore
        largest = by_size[0]
        rest_total = sum(c.total_count for c in by_size[1:]) # type: ignore

        if self._matches_census(largest.total_count, rest_total, threshold=0.10): # type: ignore
            self.resolution_log.append(
                f"Global Hierarchy {name}: {largest.total_count} matches sum of all other {len(by_size)-1} entries."
            )

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
                self.resolution_log.append(f"Fixed Zero-Total for {name}: 0 not covered implies 0% coverage.")

        # 2. Fix implicit total mismatch for single entry (e.g. "10 are union" vs Census 200)
        if census_total > 0 and e.total_count is not None and e.total_count > 0:
            # Check if entry is implicit and significantly smaller than census
            if not e.is_explicit and not self._matches_census(e.total_count, census_total) and census_total > e.total_count:
                # Check if it looks like a subset inference (covered ~= total OR not_covered ~= total)
                is_subset_inference = False
                if e.covered_count is not None and self._matches_census(e.covered_count, e.total_count):
                    is_subset_inference = True
                elif e.not_covered_count is not None and self._matches_census(e.not_covered_count, e.total_count):
                    is_subset_inference = True

                if is_subset_inference:
                    old_total = e.total_count
                    e.total_count = census_total

                    # Recalculate the other side
                    if e.covered_count is not None:
                        e.not_covered_count = census_total - e.covered_count
                        e.percentage = round((e.covered_count / census_total) * 100.0, 2)
                    elif e.not_covered_count is not None:
                        e.covered_count = census_total - e.not_covered_count
                        e.percentage = round((e.covered_count / census_total) * 100.0, 2)

                    self.resolution_log.append(f"Upgraded implicit total for {name} ({e.key}) from {old_total} to {census_total} (Census Match)")

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
                if e.total_count is None or self._matches_census(e.total_count, census_total):
                    # Safety: Don't assume a segment covers the entire census, unless we only have a single segment (and generic Entry for that specific country, since we inject a placeholder entry for mentioned countries).
                    if e.scope == Scope.SEGMENT and e.total_count is None:
                        segment_count = sum(
                            1 for entry in entries if entry.scope == Scope.SEGMENT
                        )
                        if segment_count > 1:
                            continue
                    e.covered_count = round((e.percentage / 100.0) * census_total)
                    e.total_count = census_total
                    self.resolution_log.append(f"Resolved COUNT for {name} ({e.key}): {e.percentage}% of {census_total}")

        # 2. Backfill percentages for entries with counts but no percentage
        for e in entries:
            if e.covered_count is not None and e.percentage is None:
                if e.total_count is None or self._matches_census(e.total_count, census_total):
                    e.total_count = census_total
                    if census_total > 0:
                        raw_pct = (e.covered_count / census_total) * 100.0

                        # Validate/Adjust with bounds
                        if e.qualitative_bounds:
                            lower, upper = e.qualitative_bounds
                            if raw_pct < lower and (lower - raw_pct) < 2.0:
                                raw_pct = lower
                                self.resolution_log.append(f"Adjusted PCT for {name} ({e.key}) to lower bound {lower}% (was {raw_pct:.2f}%)")
                            elif raw_pct > upper and (raw_pct - upper) < 2.0:
                                raw_pct = upper
                                self.resolution_log.append(f"Adjusted PCT for {name} ({e.key}) to upper bound {upper}% (was {raw_pct:.2f}%)")
                            elif raw_pct < lower or raw_pct > upper:
                                self.resolution_log.append(f"Warning: Calculated PCT {raw_pct:.2f}% for {name} ({e.key}) is outside bounds [{lower}, {upper}]")

                        e.percentage = round(raw_pct, 2)
                        self.resolution_log.append(f"Resolved PCT for {name} ({e.key}): {e.covered_count}/{census_total}")

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
                    others_sum += (e.covered_count or 0.0) + (e.not_covered_count or 0.0)

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
                else:
                    target.covered_count = gap
                    target.not_covered_count = 0.0
                self.resolution_log.append(f"Resolved REMAINING for {name}: {gap}")

            elif target.covered_count is None and target.percentage is None:
                target.covered_count = gap
                target.total_count = census_total
                if census_total > 0:
                    raw_pct = (gap / census_total) * 100.0

                    # Validate/Adjust with bounds
                    if target.qualitative_bounds:
                        lower, upper = target.qualitative_bounds
                        if raw_pct < lower and (lower - raw_pct) < 5.0:
                            raw_pct = lower
                            self.resolution_log.append(f"Adjusted Gap PCT for {name} ({target.key}) to lower bound {lower}% (was {raw_pct:.2f}%)")
                        elif raw_pct > upper and (raw_pct - upper) < 5.0:
                            raw_pct = upper
                            self.resolution_log.append(f"Adjusted Gap PCT for {name} ({target.key}) to upper bound {upper}% (was {raw_pct:.2f}%)")
                        elif raw_pct < lower or raw_pct > upper:
                            self.resolution_log.append(f"Warning: Inferred Gap PCT {raw_pct:.2f}% for {name} ({target.key}) is outside bounds [{lower}, {upper}]")

                    target.percentage = round(raw_pct, 2)
                self.resolution_log.append(f"Resolved PCT for {name} ({target.key}): {gap}/{census_total}")

    def _resolve_aggregates(self):
        """
        Propagates coverage from AGGREGATE entries to their constituent countries
        if those countries lack specific data.
        """
        for e in list(self.entries):
            if e.scope == Scope.AGGREGATE and e.related_geo_codes:
                pct = e.percentage

                # Try to derive percentage from counts if missing
                if pct is None and e.covered_count is not None:
                    denom = e.total_count
                    if not denom:
                        # Try summing known totals of constituents
                        denom = sum(self.country_totals.get(c, 0) for c in e.related_geo_codes)

                    if denom and denom > 0:
                        pct = (e.covered_count / denom) * 100.0

                if pct is not None:
                    for code in e.related_geo_codes:
                        targets = [t for t in self.entries if t.key == code]

                        if not targets:
                            # Determine if key is a Region Name
                            is_region = any(r.value == code for r in Region)
                            scope = Scope.REGION if is_region else Scope.COUNTRY

                            if scope == Scope.REGION:
                                known_total = self.region_totals.get(code)
                            else:
                                known_total = self.country_totals.get(code)

                            new_entry = Entry(
                                scope=scope,
                                key=code,
                                total_count=known_total,
                                is_explicit=False
                            )
                            self.entries.append(new_entry)
                            targets = [new_entry]
                            self.resolution_log.append(f"Injected placeholder for {code} ({scope.value}) during aggregate resolution")

                        for t in targets:
                            # Only overwrite if no specific data
                            if t.percentage is None and t.covered_count is None and not t.is_negated:
                                t.percentage = pct
                                t.is_qualitative = e.is_qualitative
                                self.resolution_log.append(f"Propagated {pct:.1f}% from Aggregate ({e.key}) to {t.key}")

                                # Calculate count if total is known
                                if t.total_count:
                                    t.covered_count = round((pct / 100.0) * t.total_count)

    def _resolve_geographic_gaps(self, name: str, region_total: float, entries: List[Entry]):
        """
        Resolves gaps for geographic constituents (e.g. Countries in a Region).
        Logic: Sum of Country Totals should equal Region Total.
        """
        # 1. Sum known totals
        known_sum = 0.0
        unknowns: List[Entry] = []

        for e in entries:
            # Use total_count if available
            if e.total_count is not None:
                known_sum += e.total_count
            # If not, maybe we can derive it from covered/pct?
            elif e.covered_count is not None and e.percentage is not None and e.percentage > 0:
                derived_total = round(e.covered_count / (e.percentage / 100.0))
                e.total_count = derived_total
                known_sum += derived_total
                self.resolution_log.append(f"Derived TOTAL for {name} ({e.key}): {derived_total} from count/pct")
            else:
                unknowns.append(e)

        # 2. Solve for single unknown
        if len(unknowns) == 1 and known_sum < region_total:
            target = unknowns[0]

            # Validation: Ensure we don't assign a regional gap to a segment
            if target.scope == Scope.SEGMENT:
                self.resolution_log.append(f"Skipped GEO GAP for {name}: Target {target.key} is a SEGMENT.")
                return

            gap = region_total - known_sum

            # Sanity check: Gap should be positive and reasonable
            if gap > 0:
                target.total_count = gap
                self.resolution_log.append(f"Resolved GEO GAP for {name} ({target.key}): Total {gap} (derived from {region_total} - {known_sum})")

                # If the target has a percentage, we can now derive covered_count
                if target.percentage is not None:
                    target.covered_count = round((target.percentage / 100.0) * gap)
                    self.resolution_log.append(f"Resolved COUNT for {name} ({target.key}): {target.percentage}% of {gap}")
                # If target has covered_count, derive percentage
                elif target.covered_count is not None:
                    target.percentage = round((target.covered_count / gap) * 100.0, 2)
                    self.resolution_log.append(f"Resolved PCT for {name} ({target.key}): {target.covered_count}/{gap}")

    def _get_region_entries(self, region_name: str) -> List[Entry]:
        relevant = []
        for e in self.entries:
            # 1. Direct Region Match
            if e.scope == Scope.REGION and e.key == region_name:
                relevant.append(e)
                continue

            # 2. Child Country Match
            code = None
            if e.scope == Scope.COUNTRY:
                code = e.key
            elif e.scope == Scope.SEGMENT:
                # Try to extract code from "US::UAW" or "North America::Pilots"
                if e.key:
                    parts = e.key.split("::")
                    if parts[0] == region_name:
                        relevant.append(e)
                        continue
                    code = parts[0]

            if code:
                # Check mapping
                if _CODE_TO_REGION.get(code) == region_name:
                    relevant.append(e)
        return relevant

    def _inject_placeholders(self, region_name: str):
        """
        Injects placeholder entries for countries mentioned in text but missing from entries.
        This allows gap filling to attribute remaining counts to these countries.
        Also backfills total_count from country_totals for all country entries in the region.
        """
        # 1. Inject missing mentioned countries
        existing_keys = {e.key for e in self.entries if e.scope == Scope.COUNTRY}

        for code in self.mentioned_countries:
            if code in existing_keys:
                continue

            if _CODE_TO_REGION.get(code) == region_name:
                self.entries.append(Entry(
                    scope=Scope.COUNTRY,
                    key=code,
                    is_explicit=False # It's an inferred placeholder
                ))
                self.resolution_log.append(f"Injected placeholder for mentioned country: {code} in {region_name}")
                existing_keys.add(code)

        # 2. Backfill totals from country_totals for ALL entries in this region
        region_entries = self._get_region_entries(region_name)

        for e in region_entries:
            if e.scope == Scope.COUNTRY and e.key in self.country_totals:
                known_total = self.country_totals[e.key]

                if e.total_count is None:
                    e.total_count = known_total
                    self.resolution_log.append(f"Backfilled total for {e.key}: {known_total}")
                elif e.total_count < known_total:
                    old = e.total_count
                    e.total_count = known_total
                    self.resolution_log.append(f"Updated total for {e.key} from {old} to {known_total} (census match)")

    def _resolve_single_country(self, country_code: str, census_total: float):
        relevant_entries = [
            e for e in self.entries 
            if (e.scope == Scope.COUNTRY and e.key == country_code) or 
               (e.scope == Scope.SEGMENT and e.key and e.key.startswith(f"{country_code}::"))
        ]
        if not relevant_entries:
            return
        # Check if sum of segments exceeds census total (indicating census was just a large segment)
        segments = [
            e for e in relevant_entries if e.scope == Scope.SEGMENT and e.total_count
        ]
        if segments:
            sorted_segs: List[Entry] = sorted(segments, key=lambda x: x.total_count, reverse=True) # type: ignore
            largest = sorted_segs[0].total_count or 0.0
            others_sum = sum(s.total_count for s in sorted_segs[1:] if s.total_count is not None)
            total_sum = largest + others_sum

            # Heuristic: If largest is roughly equal to sum of others, it's likely a hierarchy (Total vs Parts)
            # If not, and the sum is significantly larger than the census, assume disjoint segments and update total.
            is_hierarchy = False
            if others_sum > 0 and abs(largest - others_sum) / largest < 0.15:
                is_hierarchy = True

            if not is_hierarchy and total_sum > census_total * 1.05:
                self.country_totals[country_code] = total_sum
                self.resolution_log.append(
                    f"Updated Country Total for {country_code} from {census_total} to {total_sum} based on sum of disjoint segments."
                )
                census_total = total_sum
        self._resolve_overlaps_list(country_code, relevant_entries)
        self._resolve_gap_list(country_code, census_total, relevant_entries)

    def _resolve_single_region(self, region_name: str, region_total: float):
        self._inject_placeholders(region_name)
        entries = self._get_region_entries(region_name)
        if not entries:
            return
        self._resolve_overlaps_list(region_name, entries)
        self._resolve_geographic_gaps(region_name, region_total, entries)

    def _route_domestic(self, target_country: Optional[str] = None):
        if target_country is None:
            target_country = self.domestic_country_code
            
        # Fallback for truly unknown domestic code
        if target_country in ["DOM", "Domestic", "Unknown", None]:
            target_country = "US"
            self.resolution_log.append("Target country was DOM/Unknown, defaulted to US")

        # Filter for valid country codes (2 letters usually)
        # Treat "INT" as a valid country code for this logic if it is the target
        valid_countries = {c for c in self.mentioned_countries if c and (len(c) == 2 or c == target_country)}
        other_countries = valid_countries - {target_country}

        # Condition: No other countries mentioned
        if not other_countries:
            # Inherit global total if we are defaulting to target and have no specific data
            if self.global_total > 0 and self.country_totals.get(target_country, 0) == 0:
                self.country_totals[target_country] = self.global_total
                self.resolution_log.append(f"Inherited Global Total {self.global_total} to '{target_country}' (Default Domestic)")

        for idx, e in enumerate(self.entries):
            if e.key in [Region.DOMESTIC.value, Region.UNKNOWN.value, "DOM", "Domestic"]:
                e.key = target_country
                e.scope = Scope.COUNTRY
                self.resolution_log.append(f"Resolved 'Domestic'/'Unknown' to '{target_country}'")
            elif e.scope == Scope.SEGMENT and e.key and (e.key.startswith("DOM::") or e.key.startswith("Domestic::")):
                suffix = e.key.split("::", 1)[1]
                e.key = f"{target_country}::{suffix}"
                self.resolution_log.append(f"Resolved Domestic Segment to '{target_country}::...'")

        # Remap Totals
        if "DOM" in self.country_totals:
            val = self.country_totals.pop("DOM")
            self.country_totals[target_country] = max(self.country_totals.get(target_country, 0), val)
            self.resolution_log.append(f"Remapped country total DOM ({val}) to {target_country}")

    def _resolve_international_gap(self):
        """
        Derives International total if Global Total is known and other regions are known.
        Global - (North America + Europe + ...) = International
        """
        if self.global_total <= 0:
            return

        # Find International Entry (Scope.REGION)
        intl_entry = next((e for e in self.entries if e.scope == Scope.REGION and e.key == Region.INTERNATIONAL.value), None)
        
        # If we don't have an International entry to fill, or it already has a total, skip
        if not intl_entry or intl_entry.total_count is not None:
            return

        # Calculate sum of other regions
        resolved_region_totals = {}
        
        for r in Region:
            r_name = r.value
            if r_name in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
                continue
                
            # 1. Check for Region Entry
            r_entry = next((e for e in self.entries if e.scope == Scope.REGION and e.key == r_name), None)
            if r_entry and r_entry.total_count:
                resolved_region_totals[r_name] = r_entry.total_count
                continue
                
            # 2. Sum Countries (using max per country code to avoid duplicates)
            c_entries = [e for e in self.entries if e.scope == Scope.COUNTRY and _CODE_TO_REGION.get(e.key) == r_name]
            
            c_totals = {}
            for e in c_entries:
                if e.total_count:
                    c_totals[e.key] = max(c_totals.get(e.key, 0), e.total_count)
            
            if c_totals:
                resolved_region_totals[r_name] = sum(c_totals.values())

        sum_others = sum(resolved_region_totals.values())
        
        if sum_others < self.global_total:
            gap = self.global_total - sum_others
            if gap > 0:
                intl_entry.total_count = gap
                self.resolution_log.append(f"Resolved International Total: {gap} (Global {self.global_total} - Others {sum_others})")
                
                if intl_entry.percentage is not None:
                    intl_entry.covered_count = round((intl_entry.percentage / 100.0) * gap)
                    self.resolution_log.append(f"Resolved International Count: {intl_entry.percentage}% of {gap}")
                elif intl_entry.covered_count is not None:
                    intl_entry.percentage = round((intl_entry.covered_count / gap) * 100.0, 2)

    def resolve_coverage(self):
        """
        Fills in missing info for countries and regions.
        """
        # 0. Resolve Domestic
        self._route_domestic()
        # 0.5 Resolve Aggregates (Propagate down)
        self._resolve_aggregates()
        # 1. Resolve Countries
        for country_code, census_total in self.country_totals.items():
            self._resolve_single_country(country_code, census_total)

        # 2. Resolve Regions
        for region_name, region_total in self.region_totals.items():
            self._resolve_single_region(region_name, region_total)
            
        # 3. Resolve International Gap
        self._resolve_international_gap()
    
    def _check_contradictions(self):
        """
        Checks for logical contradictions in the tracked data.
        """
        # 1. Internal Arithmetic (Parts vs Total)
        for e in self.entries:
            if e.total_count and e.covered_count is not None and e.not_covered_count is not None:
                parts_sum = e.covered_count + e.not_covered_count
                if parts_sum > e.total_count * 1.05: # 5% tolerance
                    self.resolution_log.append(f"Contradiction (Arithmetic): {e.key} parts ({parts_sum}) exceed total ({e.total_count})")
            
            # Percentage vs Count consistency
            if e.total_count and e.percentage is not None and e.covered_count is not None:
                implied = (e.percentage / 100.0) * e.total_count
                # Check for deviation > 10% of total (for significant populations)
                if e.total_count > 50 and abs(implied - e.covered_count) > (e.total_count * 0.10):
                    self.resolution_log.append(f"Contradiction (Math): {e.key} percentage ({e.percentage}%) implies {implied:.0f}, but count is {e.covered_count}")

        # 2. Hierarchical Mismatches (Countries > Region)
        for region_name, r_total in self.region_totals.items():
            c_sum = sum(
                c_total for c_code, c_total in self.country_totals.items()
                if _CODE_TO_REGION.get(c_code) == region_name
            )
            if c_sum > r_total * 1.05:
                 self.resolution_log.append(f"Contradiction (Hierarchy): Sum of countries in {region_name} ({c_sum}) exceeds region total ({r_total})")

    def validate(self):
        """
        Validates and repairs entries to ensure logical consistency.
        """
        for e in self.entries:
            if e.total_count is not None:
                # 1. Check Covered vs Total
                if e.covered_count is not None and e.covered_count > e.total_count:
                    self.resolution_log.append(f"Validation: Reduced covered for {e.key} from {e.covered_count} to {e.total_count} (Covered > Total)")
                    e.covered_count = e.total_count
                
                # 1. Check not Covered vs Total
                if e.not_covered_count is not None and e.not_covered_count > e.total_count:
                    self.resolution_log.append(f"Validation: Reduced not covered for {e.key} from {e.not_covered_count} to {e.total_count} (Not Covered > Total)")
                    e.not_covered_count = e.total_count
                
                # 2. Check Sum of Parts vs Total
                parts_sum = (e.covered_count or 0.0) + (e.not_covered_count or 0.0)
                if parts_sum > e.total_count * 1.02:
                    self.resolution_log.append(f"Validation: Bumped total for {e.key} from {e.total_count} to {parts_sum} (Parts > Total)")
                    e.total_count = parts_sum

    def calculate_metrics(self) -> Dict[str, Any]:
        metrics = {
            "likely_percentage": None,
            "secondary_percentage": None,
            "derived_regional_coverage": {},
            "global_covered_count": 0.0,
            "global_total_count": 0.0,
            "measured_population_coverage": None,
            "_logs": [],  # New key to store logs
            "resolution": self.resolution_log,
        }

        # Ensure data consistency before calculation
        self.validate()

        def log(message: str):
            """Helper function to append logs to the metrics dict"""
            metrics["_logs"].append(message)

        log("=" * 80)
        log("STARTING METRICS CALCULATION (BOTTOM-UP PRIORITY)")
        log("=" * 80)

        # 1. Aggregate Regions (Bottom-Up FIRST)
        log("\n[STEP 1] Aggregating Regions (Bottom-Up Priority)...")
        bottom_up_covered = 0.0
        bottom_up_total = 0.0

        for region in Region:
            r_name = region.value
            if r_name == "Unknown":
                log(f"  ⊘ Skipping 'Unknown' region")
                continue

            log(f"\n  Processing Region: {r_name}")
            r_covered = 0.0
            r_total = 0.0
            region_pure_pcts = []  # Store percentages found without counts
            has_data = False

            # A. Check Region-Level Entry
            log(f"    [A] Checking region-level entry...")
            r_entry = next(
                (e for e in self.entries if e.scope == Scope.REGION and e.key == r_name),
                None,
            )

            if r_entry and (
                r_entry.covered_count is not None or r_entry.percentage is not None
            ):
                log(f"      ✓ Found region entry: {r_entry.key}")
                if r_entry.covered_count is not None:
                    r_covered = r_entry.covered_count
                    r_total = r_entry.total_count if r_entry.total_count else 0.0
                    has_data = True
                    log(f"        → Using covered_count: {r_covered}/{r_total}")
                elif r_entry.percentage is not None and r_entry.total_count:
                    r_covered = (r_entry.percentage / 100.0) * r_entry.total_count
                    r_total = r_entry.total_count
                    has_data = True
                    log(
                        f"        → Calculated from percentage: {r_entry.percentage}% of {r_total} = {r_covered}"
                    )
                elif r_entry.percentage is not None:
                    metrics["derived_regional_coverage"][r_name] = r_entry.percentage
                    log(
                        f"        → Stored percentage only (no total): {r_entry.percentage}%"
                    )
            else:
                log(f"      ✗ No region-level entry found")

            # B. If no region-level data, sum Country-Level Entries
            if not has_data:
                log(f"    [B] Aggregating country-level entries for {r_name}...")
                c_entries = [
                    e
                    for e in self.entries
                    if e.scope == Scope.COUNTRY and _CODE_TO_REGION.get(e.key) == r_name
                ]
                log(f"      Found {len(c_entries)} country entries")

                # NEW: Find countries implied by segments that don't have explicit entries
                existing_codes = {e.key for e in c_entries}
                segment_entries = [e for e in self.entries if e.scope == Scope.SEGMENT]
                for s in segment_entries:
                    if s.key and "::" in s.key:
                        code = s.key.split("::")[0]
                        if code not in existing_codes and _CODE_TO_REGION.get(code) == r_name:
                            # Create a dummy entry for iteration
                            dummy = Entry(scope=Scope.COUNTRY, key=code)
                            c_entries.append(dummy)
                            existing_codes.add(code)

                for c in c_entries:
                    log(f"        Processing country: {c.key}")
                    c_cov = 0.0
                    c_tot = 0.0
                    c_has_local_data = False
                    c_pct_only = None

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

                    # Check Segments for this country
                    if not c_has_local_data:
                        log(f"          → Checking segments for {c.key}...")
                        segs = [
                            s
                            for s in self.entries
                            if s.scope == Scope.SEGMENT
                            and s.key
                            and s.key.startswith(f"{c.key}::")
                        ]
                        log(f"            Found {len(segs)} segments")
                        if segs:
                            seg_cov = sum(s.covered_count for s in segs if s.covered_count)
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
                            valid_seg_pcts = [s.percentage for s in segs if s.percentage is not None]
                            if valid_seg_pcts:
                                # If single segment or multiple, use the first/avg. 
                                # For single segment (common case), this is accurate.
                                if len(valid_seg_pcts) == 1:
                                    c_pct_only = valid_seg_pcts[0]
                                    log(f"            → Found segment percentage: {c_pct_only}%")
                                else:
                                    # Simple average for multiple unweighted segments
                                    c_pct_only = sum(valid_seg_pcts) / len(valid_seg_pcts)
                                    log(f"            → Found avg segment percentage: {c_pct_only:.2f}%")

                    # If still no local data (counts), check if country itself has percentage
                    if not c_has_local_data and c_pct_only is None:
                        if c.percentage is not None:
                            c_pct_only = c.percentage
                            log(f"          → Found country percentage: {c_pct_only}%")

                    if c_has_local_data:
                        r_covered += c_cov
                        r_total += c_tot
                        has_data = True
                        log(
                            f"          ✓ Added to region total. Region now: {r_covered}/{r_total}"
                        )
                    elif c_pct_only is not None:
                        region_pure_pcts.append(c_pct_only)

            # Try to derive region percentage from pure percentages if no counts found
            if not has_data and region_pure_pcts:
                # Average the percentages found in this region
                avg_pct = sum(region_pure_pcts) / len(region_pure_pcts)
                metrics["derived_regional_coverage"][r_name] = round(avg_pct, 2)
                log(f"    ✓ Derived region {r_name} percentage from unweighted average of {len(region_pure_pcts)} entries: {avg_pct:.2f}%")

            # C. Update Metrics
            if has_data:
                bottom_up_covered += r_covered
                bottom_up_total += r_total
                log(f"    ✓ Region {r_name} data: {r_covered}/{r_total}")

                if r_name not in metrics["derived_regional_coverage"] and r_total > 0:
                    regional_pct = round((r_covered / r_total) * 100.0, 2)
                    metrics["derived_regional_coverage"][r_name] = regional_pct
                    log(f"      → Stored in derived_regional_coverage: {regional_pct}%")
            else:
                log(f"    ✗ No data found for region {r_name}")

        # 2. Check for Explicit Global Entry (AFTER bottom-up)
        log("\n[STEP 2] Checking for Explicit Global Entry...")
        global_entry = next((e for e in self.entries if e.scope == Scope.GLOBAL), None)
        global_entry_percentage = None
        global_entry_counts = (None, None)

        if global_entry:
            log(f"  ✓ Found global entry: {global_entry}")
            if global_entry.percentage is not None:
                global_entry_percentage = global_entry.percentage
                log(f"    → Found explicit percentage: {global_entry.percentage}%")
            if global_entry.covered_count is not None and global_entry.total_count:
                global_entry_counts = (global_entry.covered_count, global_entry.total_count)
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
            metrics["measured_population_coverage"] = round((bottom_up_total / self.global_total) * 100.0, 2)
            log(f"  Measured population coverage: {metrics['measured_population_coverage']}% ({bottom_up_total}/{self.global_total})")

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
            log(f"  ✓ Calculated using self.global_total: {metrics['likely_percentage']}%")

        # 4. Fallback: No counts found, check derived regional data
        if metrics["likely_percentage"] is None and bottom_up_total == 0:
            # A. Prefer International/Global region if available
            if Region.INTERNATIONAL.value in metrics["derived_regional_coverage"]:
                metrics["likely_percentage"] = metrics["derived_regional_coverage"][Region.INTERNATIONAL.value]
                log(f"  ✓ Fallback: Using International regional percentage: {metrics['likely_percentage']}%")
            
            # B. If only one region exists (e.g. Domestic/US), assume it represents the whole
            elif len(metrics["derived_regional_coverage"]) == 1:
                r_name = list(metrics["derived_regional_coverage"].keys())[0]
                metrics["likely_percentage"] = metrics["derived_regional_coverage"][r_name]
                log(f"  ✓ Fallback: Using single region ({r_name}) percentage: {metrics['likely_percentage']}%")

        # [STEP 4] Derive International Coverage (Residual)
        # If International is not explicitly calculated, derive it as Global - Domestic
        intl_key = Region.INTERNATIONAL.value
        if intl_key not in metrics["derived_regional_coverage"]:
            log("\n[STEP 4] Attempting to derive International coverage (Residual)...")
            
            # 1. Identify Domestic Data
            dom_covered = 0.0
            dom_total = 0.0
            dom_found = False
            
            # Check for Domestic Country or Region
            dom_entries = [
                e for e in self.entries 
                if e.key and (e.key.startswith(self.domestic_country_code)
                or e.key.startswith(Region.DOMESTIC.value))
            ]
            
            for e in dom_entries:
                if e.covered_count is not None:
                    dom_covered += e.covered_count
                    dom_total += (e.total_count or 0.0)
                    dom_found = True
                elif e.percentage is not None and e.total_count:
                    dom_covered += (e.percentage / 100.0) * e.total_count
                    dom_total += e.total_count
                    dom_found = True
            
            # 2. Identify Global Data
            # Prefer explicit global entry for coverage
            glob_covered = None
            glob_total = None
            
            if global_entry:
                if global_entry.covered_count is not None:
                    glob_covered = global_entry.covered_count
                elif global_entry.percentage is not None and global_entry.total_count:
                    glob_covered = (global_entry.percentage / 100.0) * global_entry.total_count
                glob_total = global_entry.total_count
            
            # Fallback to bottom-up / census
            if glob_covered is None: glob_covered = bottom_up_covered
            if glob_total is None or glob_total == 0: glob_total = self.global_total
                
            # 3. Calculate Residual
            if dom_found and glob_total > 0:
                intl_covered = max(0.0, (glob_covered or 0.0) - dom_covered)
                intl_total = max(0.0, glob_total - dom_total)
                
                # Only proceed if we have a meaningful international population
                if intl_total > 0 and intl_total > (glob_total * 0.01):
                    intl_pct = round((intl_covered / intl_total) * 100.0, 2)
                    metrics["derived_regional_coverage"][intl_key] = intl_pct
                    log(f"  ✓ Derived International: {intl_pct}% ({intl_covered:.0f}/{intl_total:.0f}) [Global ({glob_covered:.0f}/{glob_total:.0f}) - Domestic ({dom_covered:.0f}/{dom_total:.0f})]")
            else:
                log("  ✗ Cannot derive International: Missing Domestic data or Global Total")

        log("\n" + "=" * 80)
        log("FINAL METRICS:")
        log(f"  likely_percentage: {metrics['likely_percentage']}")
        log(f"  secondary_percentage: {metrics['secondary_percentage']}")
        log(f"  measured_population_coverage: {metrics['measured_population_coverage']}")
        log(f"  global_covered_count: {metrics['global_covered_count']}")
        log(f"  global_total_count: {metrics['global_total_count']}")
        log(f"  derived_regional_coverage: {metrics['derived_regional_coverage']}")
        log("=" * 80)

        return metrics


class UnionAnalyzer:
    def __init__(self, domestic_country_code: str = "US"):
        self.extractor = UnionExtractor()
        self.simple_analyzer = SimpleCoverageAnalyzer()
        self.extra_analyzer = UnionExtraAnalyzer()
        self.complex_analyzer_cls = ComplexCoverageAnalyzer
        self.matcher = self.extractor.matcher  # Access shared matcher
        self.domestic_country_code = domestic_country_code

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

    def _detect_summation(self, analysis: SentenceAnalysis, counts: List[float]) -> Optional[float]:
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
            m1 = next((m for m in analysis._matches if m["val"] == c1 and m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)), None)
            m2 = next((m for m in analysis._matches if m["val"] == c2 and m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER) and m is not m1), None)

            if m1 and m2:
                # Sort by position
                if m1["span"][0] > m2["span"][0]:
                    m1, m2 = m2, m1
                if len(analysis.worker_types) > 1 or len(analysis.worker_terms) > 1:
                    return c1 + c2

        return None

    def _determine_geo_context(
        self, analysis: SentenceAnalysis, last_context, current_idx, last_idx
    ) -> Dict[str, Any]:
        """
        Local wrapper for geographic context determination.
        """
        return determine_geo_context(analysis, last_context, current_idx, last_idx)

    def _map_assignments_to_geo(self, analysis: SentenceAnalysis, assignments: List[Dict]) -> List[Dict]:
        """
        Maps count assignments to explicit geographic entities in the sentence.
        """
        geo_match_objs = [m for m in analysis.geo_matches if m.source_type == GeoSource.EXPLICIT]
        raw_geo_matches = [m for m in analysis._matches if m["type"] == MatchType.GEO]

        aligned_geos = []
        # Align matches (assuming order preservation)
        if len(geo_match_objs) == len(raw_geo_matches):
            for obj, raw in zip(geo_match_objs, raw_geo_matches):
                aligned_geos.append({"obj": obj, "span": raw["span"]})
        else:
            return []

        # 1. Respectively Logic (Explicit OR Implicit if counts == geos)
        # If we have equal number of assignments and locations, assume 1-to-1 mapping in order
        if len(assignments) == len(aligned_geos):
            # Sort both by position
            s_assign = sorted(assignments, key=lambda x: x["match"]["span"][0])
            s_geos = sorted(aligned_geos, key=lambda x: x["span"][0])
            splits = []
            for item, g in zip(s_assign, s_geos):
                obj = g["obj"]
                splits.append({
                    "val": item["match"]["val"],
                    "type": item["type"],
                    "region": obj.region.value,
                    "countries": [{"name": obj.country, "code": obj.geo_code, "locations": []}],
                    "note": f"Mapped to {obj.country}"
                })
            return splits

        # 1.5 Shared Assignment Split (1 count, multiple locations)
        if len(assignments) == 1 and len(aligned_geos) > 1:
            item = assignments[0]
            c_span = item["match"]["span"]

            s_geos = sorted(aligned_geos, key=lambda x: x["span"][0])

            is_list = True
            for i in range(len(s_geos) - 1):
                e1 = s_geos[i]
                e2 = s_geos[i+1]
                gap_text = analysis.text[e1["span"][1]:e2["span"][0]]
                clean_gap = re.sub(r"[,\s]|and|&|or", "", gap_text, flags=re.IGNORECASE)
                if clean_gap and len(gap_text) > 15:
                    is_list = False
                    break

            if is_list:
                split_val = item["match"]["val"] / len(aligned_geos)
                splits = []
                for g in s_geos:
                    obj = g["obj"]
                    splits.append({
                        "val": split_val,
                        "type": item["type"],
                        "region": obj.region.value,
                        "countries": [{"name": obj.country, "code": obj.geo_code, "locations": []}],
                        "note": f"Split from list to {obj.country}"
                    })
                return splits

        # 2. Greedy Proximity Mapping (Fallback)
        pairs = []
        for i, item in enumerate(assignments):
            c_span = item["match"]["span"]
            c_mid = (c_span[0] + c_span[1]) / 2

            for j, g in enumerate(aligned_geos):
                g_mid = (g["span"][0] + g["span"][1]) / 2
                dist = abs(c_mid - g_mid)
                pairs.append({
                    "dist": dist,
                    "assign_idx": i,
                    "geo_idx": j
                })

        pairs.sort(key=lambda x: x["dist"])

        used_assign = set()
        used_geo = set()
        mapping = {} # assign_idx -> geo_idx

        # Allow reuse if we have more assignments than locations (e.g. "20 union, 30 non-union in China")
        allow_reuse = len(assignments) > len(aligned_geos)

        for p in pairs:
            if p["assign_idx"] not in used_assign:
                if allow_reuse or p["geo_idx"] not in used_geo:
                    if p["dist"] < 150:
                        mapping[p["assign_idx"]] = p["geo_idx"]
                        used_assign.add(p["assign_idx"])
                        used_geo.add(p["geo_idx"])

        splits = []
        # Process assignments in original order to preserve logic
        for i, item in enumerate(assignments):
            if i in mapping:
                g = aligned_geos[mapping[i]]
                obj = g["obj"]
                splits.append({
                    "val": item["match"]["val"],
                    "type": item["type"],
                    "region": obj.region.value,
                    "countries": [{"name": obj.country, "code": obj.geo_code, "locations": []}],
                    "note": f"Mapped to {obj.country}"
                })

        return splits

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
            tracker = Tracker(domestic_country_code=self.domestic_country_code)
            all_sentences = self.extractor.split_sentences(text)
            self._populate_tracker(all_sentences, tracker, reporting_year)
            tracker.resolve()
            # tracker.resolve_coverage() # Will be called after population

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
                block_results, local_totals, last_geo_context, last_geo_sentence_idx = self._analyze_block(
                    p_sentences,
                    reporting_year=reporting_year,
                    global_max_workers=tracker.global_total,
                    initial_geo_context=last_geo_context,
                    initial_geo_sentence_idx=last_geo_sentence_idx,
                    previous_totals=prev_paragraph_totals,
                    start_index=global_sentence_index,
                )

                global_sentence_index += len(p_sentences)

                # Update all_region_totals with max found across all blocks
                for reg, count in local_totals.items():
                    if count > all_region_totals.get(reg, 0):
                        all_region_totals[reg] = count

                results.extend(block_results)
                # Update previous totals for the next iteration (Sliding window: only look back 1 paragraph)
                prev_paragraph_totals = local_totals

            # Populate tracker with coverage entries
            for item in results:
                cov: Dict[str, Any] = item.get("coverage_data", {})
                geo = item.get("geographic_context", {})

                # Handle Union Context (Denominator) items
                if cov.get("type") == CoverageType.UNION_CONTEXT.value:
                    # If it has a count, treat it as a Covered Count record
                    if cov.get("employee_count_covered"):
                        pass # Proceed to record_coverage below
                    else:
                        # Otherwise, just log it as context and skip math
                        tracker.record_context(geo, f"Union Denominator Statement: {item.get('sentence')}")
                        continue

                # Skip if no meaningful coverage data
                if (
                    cov.get("percentage") is None 
                    and cov.get("employee_count_covered") is None 
                    and not cov.get("negated")
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
                    is_explicit=(cov.get("type") == CoverageType.EXPLICIT_PERCENT.value),
                    is_negated=cov.get("negated", False),
                    is_union_record=item.get("is_union", False),
                    sentence_index=item.get("sentence_index", -1)
                )

            # Resolve missing coverage data using collected totals
            tracker.resolve_coverage()

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
                tracker.register_mentions(geo_context)

            # Try to resolve specific counts to geography (e.g. "200 in China")
            mapped_counts, _ = self._resolve_counts_to_geography(analysis)
            if mapped_counts:
                for code, val in mapped_counts.items():
                    r_name = _CODE_TO_REGION.get(code, Region.UNKNOWN.value)
                    specific_ctx = {
                        "region": r_name,
                        "countries": [{"code": code, "name": code}]
                    }
                    tracker.update(val, specific_ctx)

            # Try to resolve counts to unions
            union_counts, _ = self._resolve_counts_to_unions(analysis)
            if union_counts:
                for union_name, val in union_counts.items():
                    lower_name = union_name.lower()
                    if lower_name in self.matcher.union_map:
                        region, country, code = self.matcher.union_map[lower_name]
                        specific_ctx = {
                            "region": region.value,
                            "countries": [{"code": code, "name": country}]
                        }
                        tracker.update(val, specific_ctx)

            effective_counts = get_effective_counts(analysis)
            if effective_counts:
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

                range_avg = self._detect_count_range(analysis, effective_counts)
                summation = self._detect_summation(analysis, effective_counts)

                # 1. Temporal Alignment (2 Years, 2 Counts)
                # "In 2009 we had 100, in 2010 we had 110"
                matched_temporal_count = None
                if len(analysis.years) == len(effective_counts) and len(effective_counts) >= 2:
                    # Get matches to sort by position
                    y_matches = sorted([m for m in analysis._matches if m["type"] == MatchType.YEAR], key=lambda x: x["span"][0])
                    c_matches = sorted([m for m in analysis._matches if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER) and m["val"] in effective_counts], key=lambda x: x["span"][0])

                    if len(y_matches) == len(c_matches):
                        # Determine target year
                        target_y = reporting_year if reporting_year else max(analysis.years)

                        for y_m, c_m in zip(y_matches, c_matches):
                            # Check is Valid: The year must be related or within bounds!
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

                tracker.update(final_count, geo_context)

    def _resolve_counts_generic(
        self, 
        analysis: SentenceAnalysis, 
        entities: List[Dict[str, Any]],
        total_key: Optional[str] = None
    ) -> Tuple[Dict[str, float], Optional[float]]:
        """
        Generic helper to map worker counts to a list of entities (regions or unions).
        entities: List of dicts with keys 'key' (identifier), 'span' (tuple), and optional 'region_enum'.
        """
        mapped_counts = {}
        sentence_total = None

        counts = [
            m
            for m in analysis._matches
            if (m["type"] == MatchType.WORKER_COUNT
            or m["type"] == MatchType.NUMBER)
        ]
        if not counts or not entities:
            return {}, None

        parts = counts

        # 1. Identify Total (Denominator)
        if len(counts) > 1:
            vals = [c["val"] for c in counts]
            max_val = max(vals)
            sum_val = sum(vals)
            others_sum = sum_val - max_val

            is_sum_match = others_sum > 0 and abs(max_val - others_sum) / max_val < 0.10
            is_len_mismatch = len(counts) == len(entities) + 1

            has_subset_indicator = bool(re.search(r"(?:of\s+which|includ(?:ing|es)|compris(?:ing|es))", analysis.text, re.IGNORECASE))

            if is_len_mismatch or (is_sum_match and len(counts) != len(entities)) or has_subset_indicator:
                sentence_total = max_val

                if total_key:
                    mapped_counts[total_key] = sentence_total

                for i, c in enumerate(parts):
                    if c["val"] == max_val:
                        parts = parts[:i] + parts[i+1:]
                        break

        # 1.1 Handle Remaining/Balance (Virtual Count)
        if sentence_total is not None and analysis.has_remaining_other:
            current_sum = sum(c["val"] for c in parts)
            remainder = sentence_total - current_sum

            if remainder > 0:
                rem_match = REMAIN_REGEX.search(analysis.text)
                if rem_match:
                    parts.append({
                        "val": remainder,
                        "span": rem_match.span(),
                        "type": MatchType.WORKER_COUNT,
                        "text": rem_match.group(0)
                    })
                    parts.sort(key=lambda x: x["span"][0])

        # 1.5 Filter Generic Regions if Mismatch (Specific to Geography)
        if len(parts) < len(entities):
            generics = (Region.INTERNATIONAL, Region.DOMESTIC, Region.UNKNOWN)
            if any("region_enum" in e for e in entities):
                non_generic_entries = [g for g in entities if g.get("region_enum") not in generics]

                # Only filter if we have non-generics to prefer. If all are generic, keep them for proximity matching.
                if non_generic_entries:
                    if len(parts) == len(non_generic_entries):
                        entities = non_generic_entries
                    elif len(parts) == len(entities) - 1:
                        for i, g in enumerate(entities):
                            if g.get("region_enum") in generics:
                                entities = entities[:i] + entities[i+1:]
                                break

        # 1.6 Check for Shared Count (1 count, multiple entities) -> Split Evenly
        if len(parts) == 1 and len(entities) > 1:
            count_val = parts[0]["val"]

            sorted_entities = sorted(entities, key=lambda x: x["span"][0])

            # Identify chains (lists of entities)
            chains = []
            if sorted_entities:
                current_chain = [sorted_entities[0]]
                for i in range(len(sorted_entities) - 1):
                    e1 = sorted_entities[i]
                    e2 = sorted_entities[i+1]
                    gap_text = analysis.text[e1["span"][1]:e2["span"][0]]

                    # Check for list separators (comma, and, or) and short length
                    is_list_gap = False
                    clean_gap = re.sub(r"[,\s]|and|&|or", "", gap_text, flags=re.IGNORECASE)
                    if not clean_gap and len(gap_text) <= 25:
                        is_list_gap = True

                    if is_list_gap:
                        current_chain.append(e2)
                    else:
                        chains.append(current_chain)
                        current_chain = [e2]
                chains.append(current_chain)

            target_list = None
            multi_item_chains = [c for c in chains if len(c) > 1]

            if len(multi_item_chains) == 1:
                candidate = multi_item_chains[0]

                # Check if excluded items are Broad Containers (INT, GLO, DOM)
                all_in_chain = set(id(x) for x in candidate)
                others = [x for x in sorted_entities if id(x) not in all_in_chain]

                broad_keys = {"INT", "GLO", "DOM", Region.INTERNATIONAL.value, Region.GLOBAL.value, Region.DOMESTIC.value}
                others_are_broad = all(x["key"] in broad_keys for x in others)

                if others_are_broad:
                    target_list = candidate

            if target_list:
                split_val = int(count_val / len(target_list))
                for e in target_list:
                    mapped_counts[e["key"]] = split_val
                return mapped_counts, sentence_total

        # 2. Parallel Structure
        if len(parts) == len(entities):
            s_counts = sorted(parts, key=lambda x: x["span"][0])
            s_entities = sorted(entities, key=lambda x: x["span"][0])
            for c, e in zip(s_counts, s_entities):
                mapped_counts[e["key"]] = c["val"]
            return mapped_counts, sentence_total

        # 3. Proximity Mapping
        if entities:
            segments = get_text_segments(analysis.text)

            def get_seg_idx(pos):
                return next((i for i, (s, e) in enumerate(segments) if s <= pos < e), -1)

            pairs = []
            for c in parts:
                c_mid = (c["span"][0] + c["span"][1]) / 2
                c_seg = get_seg_idx(c_mid)
                for e in entities:
                    e_mid = (e["span"][0] + e["span"][1]) / 2
                    e_seg = get_seg_idx(e_mid)
                    dist = abs(c_mid - e_mid)

                    # Penalize cross-segment matches
                    if c_seg != e_seg:
                        dist += 1000

                    pairs.append((dist, c, e))

            pairs.sort(key=lambda x: x[0])
            used_c, used_e = set(), set()

            for dist, c, e in pairs:
                if dist < 150 and id(c) not in used_c and e["key"] not in used_e:
                    mapped_counts[e["key"]] = c["val"]
                    used_c.add(id(c))
                    used_e.add(e["key"])

        return mapped_counts, sentence_total

    def _resolve_counts_to_geography(
        self, analysis: SentenceAnalysis
    ) -> Tuple[Dict[str, float], Optional[float]]:
        """
        Intelligently maps worker counts to geographic entities within the sentence.
        """
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
                if obj.geo_code in REGION_CODES and obj.geo_code != "DOM":
                    key = obj.region.value
                geo_entries.append({"key": key, "span": raw["span"], "region_enum": obj.region})

        return self._resolve_counts_generic(analysis, geo_entries, total_key="GLO")

    def _resolve_counts_to_unions(
        self, analysis: SentenceAnalysis
    ) -> Tuple[Dict[str, float], Optional[float]]:
        """
        Intelligently maps worker counts to union entities within the sentence.
        """
        # Identify Union Matches
        union_matches = [
            m for m in analysis._matches 
            if m["type"] in (MatchType.SPECIFIC_UNION, MatchType.UNION_NAME)
        ]

        union_entries = [{"key": m["text"], "span": m["span"]} for m in union_matches]
        return self._resolve_counts_generic(analysis, union_entries)

    def _resolve_counts_to_types(self, analysis: SentenceAnalysis) -> Dict[str, float]:
        """Maps worker counts to worker types (e.g. '112' -> 'hourly')."""
        mapping = {}
        counts = [m for m in analysis._matches if m["type"] in (MatchType.WORKER_COUNT, MatchType.NUMBER)]

        # Include WORKER_TYPE
        types = [m for m in analysis._matches if m["type"] == MatchType.WORKER_TYPE]

        # Include specific WORKER_TERM (e.g. pilots, teachers)
        terms = [m for m in analysis._matches if m["type"] == MatchType.WORKER_TERM]
        for t in terms:
            val_lower = t["val"].lower()
            if val_lower not in GENERIC_WORKER_TERMS and val_lower.rstrip("s") not in GENERIC_WORKER_TERMS:
                types.append(t)

        if not counts or not types:
            return {}

        used_c = set()
        used_t = set()
        pairs = []
        for c in counts:
            c_mid = (c["span"][0] + c["span"][1]) / 2
            for t in types:
                t_mid = (t["span"][0] + t["span"][1]) / 2
                dist = abs(c_mid - t_mid)
                pairs.append((dist, c, t))

        pairs.sort(key=lambda x: x[0])

        for dist, c, t in pairs:
            if dist < 50 and id(c) not in used_c and id(t) not in used_t:
                mapping[t["val"].lower()] = c["val"]
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

            if i + 1 < len(results):
                next_item = results[i + 1]
                if "geographic_context" not in next_item:
                    merged_results.append(current)
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
                    and not next_item.get("is_remaining", False)
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
                    # If both have a total, don't merge
                    if c_data["employee_count_total"] is not None and n_data["employee_count_total"] is not None:
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
                            spec_curr = {
                                w.lower()
                                for w in w_curr
                                if w.lower() not in GENERIC_WORKER_TERMS and w.lower().rstrip("s") not in GENERIC_WORKER_TERMS
                            }
                            spec_next = {
                                w.lower()
                                for w in w_next
                                if w.lower() not in GENERIC_WORKER_TERMS and w.lower().rstrip("s") not in GENERIC_WORKER_TERMS
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

                        # Recalculate missing values if percentage is present
                        if c_data["percentage"] is not None:
                            pct = c_data["percentage"]
                            total = c_data.get("employee_count_total")
                            covered = c_data.get("employee_count_covered")
                            not_covered = c_data.get("employee_count_not_covered")
                            is_negated = c_data.get("negated")

                            # Case 1: Have Total + Pct -> Calculate Parts
                            if total and (covered is None or not_covered is None):
                                subset = round((pct / 100.0) * total)
                                if is_negated:
                                    if not_covered is None:
                                        c_data["employee_count_not_covered"] = subset
                                    if covered is None:
                                        c_data["employee_count_covered"] = (
                                            total - subset
                                        )
                                else:
                                    if covered is None:
                                        c_data["employee_count_covered"] = subset
                                    if not_covered is None:
                                        c_data["employee_count_not_covered"] = (
                                            total - subset
                                        )
                                c_data["note"] = (
                                    c_data.get("note") or ""
                                ) + " | Derived counts from merged %"

                            # Case 2: Have Part + Pct -> Calculate Total (Denominator)
                            elif not total and pct > 0:
                                derived_total = None
                                if is_negated and not_covered is not None:
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
                                        derived_total = round(
                                            not_covered / (pct / 100.0)
                                        )
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

                        # NEW: Type-based coverage inference
                        # If next item indicates coverage (union terms) and specifies worker types

                        # Gather targets from types and specific terms
                        targets = set(next_item.get("worker_types", []))
                        for w in next_item.get("worker_terms", []):
                            if w.lower() not in GENERIC_WORKER_TERMS and w.lower().rstrip("s") not in GENERIC_WORKER_TERMS:
                                targets.add(w)

                        if next_item.get("keyword_matched") and targets:
                            # Check if current item has counts for these types
                            c_map = current.get("worker_type_map", {})

                            matched_count = 0.0
                            found_match = False

                            for w_type in targets:
                                w_type_lower = w_type.lower()
                                if w_type_lower in c_map:
                                    matched_count += c_map[w_type_lower]
                                    found_match = True

                            if found_match:
                                target_field = "employee_count_not_covered" if n_data.get("negated") else "employee_count_covered"
                                current_val = c_data.get(target_field) or 0.0
                                c_data[target_field] = current_val + matched_count

                                # Recalculate percentage if total exists
                                if c_data.get("employee_count_total"):
                                    cov = c_data.get("employee_count_covered") or 0.0
                                    c_data["percentage"] = round((cov / c_data["employee_count_total"]) * 100, 2)
                                    c_data["type"] = CoverageType.CALCULATED.value
                                    c_data["note"] = (c_data.get("note") or "") + f" | Inferred coverage for {matched_count} (matched types)"

                        # Add merge hint
                        merge_note = f" [Merged with next sentence: '{next_item.get('sentence', '')[:30]}...']"
                        c_data["note"] = (c_data.get("note") or "") + merge_note
                        current["merged_sentence_index"] = next_item.get("sentence_index")

                        # Merge is_union flag (if continuation is union-specific, the whole item is)
                        if next_item.get("is_union"):
                            current["is_union"] = True
                        skip_indices.add(i + 1)

            merged_results.append(current)
        return merged_results

    def _analyze_block(
        self,
        sentences: List[str],
        reporting_year: Optional[int] = None,
        global_max_workers: float = 0.0,
        initial_geo_context: Optional[Dict] = None,
        initial_geo_sentence_idx: int = -1,
        previous_totals: Optional[Dict[str, float]] = None,
        start_index: int = 0,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], Optional[Dict], int]:
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
        )
        local_tracker.resolve()

        results = []
        analyzed_sentences = [self.extractor.analyze_sentence(s) for s in sentences]

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

        for idx, analysis in enumerate(analyzed_sentences):
            sent = sentences[idx]
            current_idx = start_index + idx

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
                        r_sent, r_analysis, is_historical=True
                    )
                    if risk_item:
                        risk_item["sentence_index"] = start_index + k
                        results.append(risk_item)
                break

            # 2. Update Context (Worker Counts)
            effective_counts = get_effective_counts(analysis)
            if effective_counts and not is_historical:
                last_employee_count = max(effective_counts)

            # 3. Relevance Check
            if not analysis.is_relevant:
                continue

            # 4. Determine Geographic Context
            geo_context = self._determine_geo_context(
                analysis, last_geo_context, current_idx, last_geo_sentence_idx
            )

            # Update context anchor if:
            # 1. Strong Geography (Explicit/Inferred)
            # 2. OR Strong Census (Has Counts) - allows inheriting from implicit totals
            is_strong_geo = geo_context["specificity"] in (Specificity.EXPLICIT.value, Specificity.INFERRED_UNION.value)
            has_counts = bool(effective_counts)

            if is_strong_geo or has_counts:
                last_geo_context = geo_context
                last_geo_sentence_idx = current_idx

            # 5. Update Region Totals
            census_update_note = None
            if effective_counts:
                # Check for range first
                range_avg = self._detect_count_range(analysis, effective_counts)

                if range_avg:
                    current_val = range_avg
                    mapped_counts = {}
                    union_counts = {}
                else:
                    # Try intelligent mapping first
                    mapped_counts, sent_total = self._resolve_counts_to_geography(
                        analysis
                    )
                    union_counts, _ = self._resolve_counts_to_unions(analysis)
                    current_val = max(effective_counts)

                updates_found = []

                if mapped_counts or union_counts:
                    # Use specific mappings
                    if mapped_counts:
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

                    if union_counts:
                        for union_name, count in union_counts.items():
                            lower_name = union_name.lower()
                            if lower_name in self.matcher.union_map:
                                region, country, code = self.matcher.union_map[lower_name]

                                prev_val = previous_totals.get(code, 0) if previous_totals else 0
                                curr_max = effective_totals.get(code, 0)
                                if count > prev_val and count >= curr_max:
                                    updates_found.append(f"{code} (via {union_name}): {count}")

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

            # NEW: Resolve types
            type_map = self._resolve_counts_to_types(analysis)

            # 8. Construct Result (Handle Splits)
            split_items = []
            # Remove internal key to prevent JSON serialization errors (contains MatchType)
            assignments = coverage_data.pop("_count_assignments", None)

            if assignments:
                relevant_assignments = [a for a in assignments if a["type"] in ("covered", "not_covered")]

                # Only split if we have multiple relevant counts and multiple explicit geos
                if len(relevant_assignments) > 1:
                    splits = self._map_assignments_to_geo(analysis, relevant_assignments)
                    if len(splits) > 1:
                        for s in splits:
                            new_geo_context = {
                                "region": s["region"],
                                "countries": s["countries"],
                                "specificity": Specificity.EXPLICIT.value,
                                "explicit_countries": [c["name"] for c in s["countries"]],
                                "regions": [],
                                "unusual_union_region_combo": False,
                                "union_names_mentioned": None,
                                "note": "Region split"
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
                                "temporal_scope": coverage_data.get("temporal_scope", "CURRENT")
                            }

                            if s["type"] == "covered":
                                new_cov_data["employee_count_covered"] = s["val"]
                            elif s["type"] == "not_covered":
                                new_cov_data["employee_count_not_covered"] = s["val"]
                                new_cov_data["negated"] = True
                                new_cov_data["negation_type"] = NegationType.NOT_COVERED.value

                            # Try to find total
                            c_code = s["countries"][0]["code"]
                            c_total = effective_totals.get(c_code)
                            if c_total and c_total >= s["val"]:
                                new_cov_data["employee_count_total"] = c_total
                                if s["type"] == "covered":
                                    new_cov_data["percentage"] = round((s["val"]/c_total)*100, 2)

                            split_item = {
                                "sentence": sent,
                                "keyword_matched": analysis.union_terms or None,
                                "geographic_context": new_geo_context,
                                "coverage_data": new_cov_data,
                                "lookup_totals": effective_totals.copy(),
                                "census_note": census_update_note,
                                "sentence_index": current_idx,
                                "worker_type_map": type_map,
                                "worker_types": analysis.worker_types,
                                "is_remaining": analysis.has_remaining_other,
                            }
                            split_items.append(split_item)

            if split_items:
                results.extend(split_items)
            else:
                item = {
                    "sentence": sent,
                    "keyword_matched": analysis.union_terms or None,
                    "geographic_context": geo_context,
                    "coverage_data": coverage_data,
                    "lookup_totals": effective_totals.copy(),
                    "census_note": census_update_note,
                    "sentence_index": current_idx,
                    "worker_type_map": type_map,
                    "worker_types": analysis.worker_types,
                    "is_remaining": analysis.has_remaining_other,
                }
                results.append(item)

        merged_results = self._merge_continuation_items(results)

        return merged_results, effective_totals, last_geo_context, last_geo_sentence_idx

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

        if analysis.has_union_denominator:
            return self.extra_analyzer.analyze_denominator(analysis)
        elif is_simple_scenario(analysis):
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

                # Ensure we have union context before applying generic qualitative terms
                if match["type"] == MatchType.QUALITATIVE_TERM and not analysis.is_union:
                    return data

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
                        if term.lower_bound is not None and term.upper_bound is not None:
                            data["qualitative_bounds"] = (term.lower_bound, term.upper_bound)
                        data["note"] = f"Absolute qualitative: '{pattern_str}'"
                    else:
                        pct = term.get_percentage(is_negated=is_locally_negated)
                        if pct is not None:
                            data["percentage"] = pct
                            if term.is_all and not is_locally_negated:
                                data["type"] = CoverageType.EXPLICIT_PERCENT.value
                            else:
                                data["type"] = CoverageType.QUALITATIVE.value
                            data["note"] = f"Qualitative: '{pattern_str}' -> {pct}%"
                            if not is_locally_negated and term.lower_bound is not None and term.upper_bound is not None:
                                data["qualitative_bounds"] = (term.lower_bound, term.upper_bound)

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
                result = self.extra_analyzer.create_risk_item(sent, analysis, is_historical=is_historical)
                if result:
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
