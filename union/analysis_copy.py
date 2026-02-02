from typing import List, Dict, Any, Optional, Tuple
import statistics
import re

from extraction import (
    UnionExtractor,
    SentenceAnalysis,
    MatchType,
    NEGATION_REGEX,
    REMAIN_REGEX,
    OF_REGEX,
    QUALITATIVE_MULTIPLIERS,
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
)


class SimpleCoverageAnalyzer:
    """
    Handles straightforward sentences where coverage is explicit and singular.
    Criteria:
    - Max 1 Percentage AND/OR Max 1 Worker Count
    - No conflicting Union vs Non-Union terms (mixed signals)
    - No Ratios
    """

    def analyze(self, analysis: SentenceAnalysis) -> Dict[str, Any]:
        data = {
            "percentage": None,
            "employee_count_covered": None,
            "employee_count_not_covered": None,
            "employee_count_total": None,
            "negated": False,
            "negation_type": None,
            "type": CoverageType.QUALITATIVE.value,
            "note": None,
        }

        notes = []

        # 0. Handle 1 Percentage + 1 Count (Combined)
        if len(analysis.percentages) == 1 and len(analysis.worker_counts) == 1:
            pct = analysis.percentages[0]
            count = analysis.worker_counts[0]

            data["percentage"] = pct
            data["type"] = CoverageType.EXPLICIT_PERCENT.value
            notes.append(f"Explicit percentage: {pct}%")

            # Determine if count is Total or Covered based on "of"
            # e.g. "10% of 100 employees" -> Total=100
            # e.g. "100 employees (10%)" -> Covered=100

            is_percent_of_total = False
            # Find matches to check text between
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
                    if m["type"] == MatchType.WORKER_COUNT and m["val"] == count
                ),
                None,
            )

            if pct_match and count_match:
                p_end = pct_match["span"][1]
                c_start = count_match["span"][0]
                if p_end < c_start:
                    between = analysis.text[p_end:c_start]
                    if OF_REGEX.search(between):
                        is_percent_of_total = True

            if is_percent_of_total:
                data["employee_count_total"] = count
                data["employee_count_covered"] = round((pct / 100.0) * count)
                notes.append(
                    f"Count (total): {count} (inferred covered: {data['employee_count_covered']})"
                )
            else:
                # Default: Count is Covered (or Not Covered)
                if analysis.negation_terms:
                    data["employee_count_not_covered"] = count
                    data["negated"] = True
                    data["negation_type"] = NegationType.NOT_COVERED.value
                    notes.append(f"Count (not covered): {count}")
                    # Calculate total if possible
                    if pct > 0:
                        data["employee_count_total"] = round(count / (pct / 100.0))
                else:
                    data["employee_count_covered"] = count
                    notes.append(f"Count (covered): {count}")
                    # Calculate total if possible
                    if pct > 0:
                        data["employee_count_total"] = round(count / (pct / 100.0))

        else:
            # 1. Explicit Percentage
            if analysis.percentages:
                pct = analysis.percentages[0]
                data["percentage"] = pct
                data["type"] = CoverageType.EXPLICIT_PERCENT.value
                notes.append(f"Explicit percentage: {pct}%")

            # 2. Explicit Count
            if analysis.worker_counts:
                count = analysis.worker_counts[0]
                if analysis.negation_terms:
                    data["employee_count_not_covered"] = count
                    data["negated"] = True
                    data["negation_type"] = NegationType.NOT_COVERED.value
                    notes.append(f"Count (not covered): {count}")
                else:
                    data["employee_count_covered"] = count
                    notes.append(f"Count (covered): {count}")

        # 3. Qualitative Zero ("None are represented")
        if (
            not analysis.percentages
            and not analysis.worker_counts
            and analysis.negation_terms
        ):
            if any(NEGATION_REGEX.search(t) for t in analysis.negation_terms):
                data["percentage"] = 0.0
                data["negated"] = True
                data["negation_type"] = NegationType.ZERO_COVERAGE.value
                data["type"] = CoverageType.EXPLICIT_PERCENT.value
                notes.append("Qualitative zero coverage detected")

        data["note"] = " | ".join(notes) if notes else "Simple Analysis (No Data)"
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


def check_local_negation(match_span: Tuple[int, int], text: str) -> bool:
    """
    Check if a negation term appears within ~5 words before the matched pattern.
    """
    if not match_span:
        return False

    start_idx = match_span[0]
    # Look back window (approx 5 words ~ 40 chars)
    window = text[max(0, start_idx - 40) : start_idx]

    return bool(NEGATION_REGEX.search(window))


def apply_qualitative_multipliers(
    raw_pct: float, span: Tuple[int, int], text: str, apply: bool = False
) -> Tuple[float, Optional[str]]:
    """
    Applies qualitative multipliers (e.g. "almost", "nearly") to a percentage.
    """
    if not apply:
        return raw_pct, None

    start_idx = span[0]
    # Look back window (e.g. "almost 20%")
    window = text[max(0, start_idx - 30) : start_idx]

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
        pre_text = text[max(0, span1[0] - 15) : span1[0]]
        if _RANGE_BETWEEN.search(pre_text):
            return True

    return False


class ComplexCoverageAnalyzer:
    """
    Handles complex scenarios: mixed coverage, ratios, inferred totals, percent of percent.
    """

    # Delimiters: , ; or words like while, although, but, however
    delimiter_regex = re.compile(
        r"(?<!\d)[,;](?!\d)|\b(?:while|although|whereas|but|however)\b", re.IGNORECASE
    )

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
            "type": CoverageType.QUALITATIVE.value,
            "note": None,
        }

    def analyze(self) -> Dict[str, Any]:
        # 0. Ranges (High priority)
        if self._handle_ranges():
            return self.data

        # 1. Percent of Percent (High priority)
        if self._handle_percent_of_percent():
            return self.data

        # 2. Mixed Coverage (Resolves specific counts/percents)
        self._resolve_mixed_coverage()

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

    def _handle_ranges(self) -> bool:
        """
        Detects ranges like "20% to 25%" or "500 to 600 employees".
        Averages them and treats as explicit.
        """
        # 1. Percentage Ranges
        if len(self.analysis.percentages) == 2:
            matches = [m for m in self.analysis._matches if m['type'] == MatchType.PERCENT]
            if len(matches) == 2:
                matches.sort(key=lambda x: x['span'][0])
                if is_range_context(self.analysis.text, matches[0]['span'], matches[1]['span']):
                    p1 = matches[0]['val']
                    p2 = matches[1]['val']
                    avg = (p1 + p2) / 2
                    self.data["percentage"] = round(avg, 2)
                    self.data["type"] = CoverageType.EXPLICIT_PERCENT.value
                    self.data["percentage_qualifier"] = PercentageQualifier.RANGE.value
                    self.data["note"] = f"Averaged from range {p1}% to {p2}%"
                    return True

        # 2. Count Ranges
        if not self.data["percentage"] and len(self.analysis.worker_counts) == 2:
            matches = [m for m in self.analysis._matches if m['type'] == MatchType.WORKER_COUNT]
            if len(matches) == 2:
                matches.sort(key=lambda x: x['span'][0])
                if is_range_context(self.analysis.text, matches[0]['span'], matches[1]['span']):
                    c1 = matches[0]['val']
                    c2 = matches[1]['val']
                    avg = (c1 + c2) / 2
                    if self.analysis.negation_terms:
                        self.data["employee_count_not_covered"] = round(avg)
                        self.data["negated"] = True
                        self.data["negation_type"] = NegationType.NOT_COVERED.value
                        self.data["note"] = f"Averaged from range {c1} to {c2} (not covered)"
                    else:
                        self.data["employee_count_covered"] = round(avg)
                        self.data["note"] = f"Averaged from range {c1} to {c2} (covered)"
                    return True

        return False

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
                        p1 = m1["val"]
                        p2 = m2["val"]
                        combined = (p1 * p2) / 100.0
                        self.data["percentage"] = round(combined, 2)
                        self.data["calculated_percentage"] = round(combined, 2)
                        self.data["type"] = CoverageType.CALCULATED.value
                        self.data["note"] = f"Calculated from {p1}% of {p2}%"
                        return True
        return False

    def _resolve_mixed_coverage(self):
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
        counts = [
            m for m in self.analysis._matches if m["type"] == MatchType.WORKER_COUNT
        ]
        percents = [m for m in self.analysis._matches if m["type"] == MatchType.PERCENT]
        numbers = [m for m in self.analysis._matches if m["type"] == MatchType.NUMBER]

        count_spans = set(c["span"] for c in counts)
        all_values = counts + [n for n in numbers if n["span"] not in count_spans]

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
            sorted_values = sorted(all_values, key=lambda x: x["span"][0])
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
        for c in all_values:
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

    # 3. Max 1 Percentage, Max 1 Count (avoid ambiguity)
    if len(analysis.percentages) > 1:
        return False
    if len(analysis.worker_counts) > 1:
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
                # Special handling for Domestic -> US
                elif r_code == "DOMESTIC" and c["code"] == "US":
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
    is_quality_negated = False
    q_match = next(
        (m for m in analysis._matches if m["type"] == MatchType.RELATIONSHIP_QUALITY),
        None,
    )

    if q_match:
        q_start = q_match["span"][0]
        # Look for negation terms ending just before q_start
        negation_matches = [
            m
            for m in analysis._matches
            if m["type"] in (MatchType.NEGATION, MatchType.NON_COVERAGE)
        ]
        for n_match in negation_matches:
            n_end = n_match["span"][1]
            # Check distance (approx 25 chars covers "are not", "is not")
            if 0 < (q_start - n_end) < 25:
                is_quality_negated = True
                break

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


def check_is_total_context(
    analysis: SentenceAnalysis, match_span: Optional[Tuple[int, int]] = None
) -> bool:
    """
    Checks if 'total', 'global', 'worldwide', etc. are present near the match.
    """
    if not analysis.total_modifiers:
        return False
    if not match_span:
        return True

    total_matches = [
        m for m in analysis._matches if m["type"] == MatchType.TOTAL_MODIFIER
    ]
    start, end = match_span

    for tm in total_matches:
        t_start, t_end = tm["span"]
        # Check distance (approx 60 chars covers "total of approximately [number]")
        dist = 0
        if t_end < start:
            dist = start - t_end
        elif end < t_start:
            dist = t_start - end

        if dist < 60:
            return True
    return False


class Tracker:
    """
    Tracks the 'Whole Pie' (Total Employee Counts) across different geographic scopes.
    Used to provide the correct denominator for coverage calculations.
    """

    def __init__(self):
        self.global_total: float = 0.0
        self.region_totals: Dict[str, float] = {}
        self.country_totals: Dict[str, float] = {}
        self.region_country_map: Dict[str, set] = {}
        self.candidates: List[Dict[str, Any]] = []
        self.explicit_global = False
        self.explicit_regions = set()
        
        # Coverage Tracking
        self.global_rate: Optional[float] = None
        self.region_rates: Dict[str, float] = {}
        self.country_rates: Dict[str, float] = {}
        
        self.global_covered: float = 0.0
        self.region_covered: Dict[str, float] = {}
        self.country_covered: Dict[str, float] = {}

    def update(
        self, count: float, geo_context: Dict[str, Any], is_explicit_total: bool = False
    ):
        self.candidates.append(
            {"count": count, "context": geo_context, "explicit": is_explicit_total}
        )
        region = geo_context.get("region")
        countries = geo_context.get("countries", [])

        # 1. Global Update
        if (
            region in (Region.INTERNATIONAL.value, Region.UNKNOWN.value)
            and not countries
        ):
            if is_explicit_total:
                # Explicit total always takes precedence (or max of explicits)
                self.global_total = max(self.global_total, count)
                self.explicit_global = True
            elif not self.explicit_global:
                # Only update implicit if we don't have an explicit lock
                if count > self.global_total:
                    self.global_total = count

        # 2. Regional Update
        if region and region not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
            current = self.region_totals.get(region, 0)
            if is_explicit_total:
                self.region_totals[region] = max(current, count)
                self.explicit_regions.add(region)
            elif region not in self.explicit_regions:
                # Only update implicit if region is not locked by explicit total
                if count > current:
                    self.region_totals[region] = count

            # Track hierarchy for resolution
            if region not in self.region_country_map:
                self.region_country_map[region] = set()
            for c in countries:
                self.region_country_map[region].add(c["code"])

        # 3. Country Update
        # Only update specific country totals if the count is associated with a SINGLE country.
        # If multiple countries are listed (e.g. "5000 in X, Y, and Z"), the count is an aggregate.
        if len(countries) == 1:
            c = countries[0]
            code = c["code"]
            if count > self.country_totals.get(code, 0):
                self.country_totals[code] = count

        self.reconcile()

    def resolve(self):
        """
        Enforces hierarchy constraints using a greedy algorithm.
        Constraint: Sum of children (countries) cannot exceed parent (region).
        If violated, we assume double-counting and prioritize larger entities until full.
        """
        for region, countries in self.region_country_map.items():
            region_total = self.region_totals.get(region, 0)
            if region_total <= 0:
                continue

            # Filter to known countries and sort by size (Greedy approach)
            known_countries = [c for c in countries if c in self.country_totals]
            sorted_countries = sorted(
                known_countries, key=lambda x: self.country_totals[x], reverse=True
            )

            running_sum = 0.0
            accepted_countries = set()

            for c in sorted_countries:
                val = self.country_totals[c]
                if running_sum + val <= region_total:
                    running_sum += val
                    accepted_countries.add(c)

            # Update the map to only include the 'accepted' disjoint children
            self.region_country_map[region] = accepted_countries

        self.reconcile()

    def reconcile(self):
        """
        Reconciles Global vs. Regional totals.
        1. Updates Global if Sum(Regions) > Global.
        2. Attempts to fill gaps if Global > Sum(Regions).
        """
        specific_regions_sum = sum(
            count
            for region, count in self.region_totals.items()
            if region not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value)
        )

        # Scenario 2: Global Max missing or too low -> Update from Regions
        if specific_regions_sum > self.global_total:
            self.global_total = specific_regions_sum

        # Scenario 1: Global Max exists, but regions are missing -> Fill Gap
        elif self.global_total > specific_regions_sum:
            gap = self.global_total - specific_regions_sum
            if gap > self.global_total * 0.10:
                self._fill_region_gap(gap)

    def _fill_region_gap(self, gap: float):
        """
        Greedy approach to 'fill' in a region using unassigned numbers.
        Skeleton implementation.
        """
        # Strategy:
        # 1. Iterate through self.candidates to find a count close to 'gap'
        # 2. Verify candidate is not already used in region_totals
        # 3. If found, promote to region_totals (e.g. "Rest of World")
        pass

    def record_coverage(self, percentage: Optional[float], covered_count: Optional[float], geo_context: Dict[str, Any]):
        """
        Records coverage data (rate or count) for a specific geographic scope.
        """
        region = geo_context.get("region")
        countries = geo_context.get("countries", [])
        
        # Determine scope
        scope = "global"
        target_code = None
        
        if region and region not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
            scope = "region"
        
        if len(countries) == 1:
            scope = "country"
            target_code = countries[0]["code"]
            
        # 1. Handle Rates (Percentages)
        if percentage is not None:
            if scope == "global":
                self.global_rate = percentage
            elif scope == "region":
                self.region_rates[region] = percentage
            elif scope == "country" and target_code:
                self.country_rates[target_code] = percentage
                
        # 2. Handle Counts
        if covered_count is not None:
            if scope == "global":
                self.global_covered = max(self.global_covered, covered_count)
            elif scope == "region":
                self.region_covered[region] = max(self.region_covered.get(region, 0), covered_count)
            elif scope == "country" and target_code:
                self.country_covered[target_code] = max(self.country_covered.get(target_code, 0), covered_count)

    def calculate_metrics(self) -> Dict[str, Any]:
        """
        Performs top-down calculation of coverage rates.
        """
        # 1. Resolve Countries (Rate -> Count)
        for code in self.country_totals:
            total = self.country_totals[code]
            if code in self.country_rates:
                # Explicit rate overrides count
                self.country_covered[code] = (self.country_rates[code] / 100.0) * total
        
        # 2. Resolve Regions
        final_region_stats = {}
        for region in self.region_totals:
            total = self.region_totals[region]
            if total <= 0: continue
            
            covered = 0.0
            rate = 0.0
            
            # Priority 1: Explicit Region Rate
            if region in self.region_rates:
                rate = self.region_rates[region]
                covered = (rate / 100.0) * total
            else:
                # Priority 2: Sum of Children vs Explicit Region Count
                children_sum = 0.0
                if region in self.region_country_map:
                    for code in self.region_country_map[region]:
                        children_sum += self.country_covered.get(code, 0.0)
                
                explicit_val = self.region_covered.get(region, 0.0)
                covered = max(explicit_val, children_sum)
                rate = (covered / total) * 100.0 if total > 0 else 0.0
            
            final_region_stats[region] = {"covered": covered, "total": total, "rate": rate}
            
        # 3. Resolve Global
        if self.global_rate is not None:
            global_rate = self.global_rate
        else:
            regions_sum = sum(stat["covered"] for stat in final_region_stats.values())
            final_global_covered = max(self.global_covered, regions_sum)
            global_rate = (final_global_covered / self.global_total * 100.0) if self.global_total > 0 else 0.0
            
        return {"global_rate": round(global_rate, 2), "region_stats": final_region_stats}


class UnionAnalyzer:
    def __init__(self):
        self.extractor = UnionExtractor()
        self.simple_analyzer = SimpleCoverageAnalyzer()
        self.complex_analyzer_cls = ComplexCoverageAnalyzer
        self.matcher = self.extractor.matcher  # Access shared matcher

    def _detect_count_range(self, analysis: SentenceAnalysis) -> Optional[float]:
        """
        Detects if worker_counts form a range (e.g. 100 to 200).
        Returns average if range found, else None.
        """
        if len(analysis.worker_counts) != 2:
            return None
            
        matches = [m for m in analysis._matches if m['type'] == MatchType.WORKER_COUNT]
        if len(matches) != 2:
            return None
            
        matches.sort(key=lambda x: x['span'][0])
        m1, m2 = matches[0], matches[1]
        
        if is_range_context(analysis.text, m1['span'], m2['span']):
            return (m1['val'] + m2['val']) / 2
                
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

            if analysis.worker_counts:
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
                max_count = max(analysis.worker_counts)
                count_match = next(
                    (
                        m
                        for m in analysis._matches
                        if m["type"] == MatchType.WORKER_COUNT and m["val"] == max_count
                    ),
                    None,
                )
                span = count_match["span"] if count_match else None
                is_explicit = check_is_total_context(analysis, span)

                range_avg = self._detect_count_range(analysis)
                final_count = range_avg if range_avg else max_count

                tracker.update(final_count, geo_context, is_explicit_total=is_explicit)

    def _resolve_counts_to_geography(
        self, analysis: SentenceAnalysis
    ) -> Tuple[Dict[str, float], Optional[float]]:
        """
        Intelligently maps worker counts to geographic entities within the sentence.
        """
        mapped_counts = {}
        sentence_total = None

        counts = [m for m in analysis._matches if m["type"] == MatchType.WORKER_COUNT]
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
                geo_entries.append({"code": obj.geo_code, "span": raw["span"]})

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

    def _apply_remaining_logic(
        self,
        analysis: SentenceAnalysis,
        coverage_data: Dict[str, Any],
        results: List[Dict[str, Any]],
    ):
        """
        Handles 'Remaining/Rest/Other' logic linking to previous sentence.
        e.g. '80% are unionized. The remaining employees are not.' -> 20%
        """
        if (
            analysis.has_remaining_other
            and coverage_data["percentage"] is None
            and coverage_data["employee_count_covered"] is None
            and coverage_data["employee_count_not_covered"] is None
            and results
        ):
            prev_item = results[-1]
            if "coverage_data" in prev_item:
                prev_data = prev_item["coverage_data"]

                # Case 1: Previous had percentage
                if prev_data.get("percentage") is not None:
                    prev_pct = prev_data["percentage"]
                    remaining_pct = max(0.0, 100.0 - prev_pct)

                    coverage_data["percentage"] = round(remaining_pct, 2)
                    coverage_data["type"] = CoverageType.CALCULATED.value
                    coverage_data["note"] = f"Calculated from remaining of {prev_pct}%"

                    # Infer negation status if not explicit
                    if not coverage_data.get("negated") and not analysis.union_terms:
                        # Flip previous status
                        if not prev_data.get("negated"):
                            coverage_data["negated"] = True
                            coverage_data["negation_type"] = NegationType.NOT_COVERED.value
                        else:
                            coverage_data["negated"] = False

                # Case 2: Previous had counts
                elif prev_data.get("employee_count_total"):
                    total = prev_data["employee_count_total"]
                    prev_val = (
                        prev_data.get("employee_count_covered")
                        if prev_data.get("employee_count_covered") is not None
                        else prev_data.get("employee_count_not_covered")
                    )

                    if prev_val is not None:
                        remaining_count = max(0, total - prev_val)
                        coverage_data["employee_count_total"] = total
                        coverage_data["note"] = f"Calculated remaining count (Total {total} - Prev {prev_val})"

                        if coverage_data.get("negated") or (analysis.negation_terms and not analysis.union_terms):
                            coverage_data["employee_count_not_covered"] = remaining_count
                            coverage_data["negated"] = True
                            coverage_data["negation_type"] = NegationType.NOT_COVERED.value
                        else:
                            coverage_data["employee_count_covered"] = remaining_count

    def _merge_continuation_items(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                next_item = results[i+1]
                if "geographic_context" not in next_item:
                    continue

                # Criteria: Next item inherits from Current, and Current has data
                c_pct = current["coverage_data"].get("percentage")
                is_saturated = (c_pct == 100.0)
                is_empty = (c_pct == 0.0)

                if (next_item["geographic_context"]["specificity"] == Specificity.INHERITED.value and
                    next_item["geographic_context"].get("inherited_from_sentence_index") == current.get("sentence_index") and
                    not is_saturated and not is_empty):

                    c_data = current["coverage_data"]
                    n_data = next_item["coverage_data"]

                    # Merge Percentage
                    if c_data["percentage"] is None and n_data["percentage"] is not None:
                        c_data["percentage"] = n_data["percentage"]
                        c_data["negated"] = n_data["negated"]
                        c_data["negation_type"] = n_data["negation_type"]
                        c_data["type"] = n_data["type"]
                        c_data["note"] = (c_data["note"] or "") + " | " + (n_data["note"] or "")

                    # Merge Counts
                    if not c_data["employee_count_covered"] and n_data["employee_count_covered"]:
                        c_data["employee_count_covered"] = n_data["employee_count_covered"]
                    if not c_data["employee_count_not_covered"] and n_data["employee_count_not_covered"]:
                        c_data["employee_count_not_covered"] = n_data["employee_count_not_covered"]

                    skip_indices.add(i+1)

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
        effective_totals.update(local_totals)

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
            if analysis.worker_counts and not is_historical:
                last_employee_count = max(analysis.worker_counts)

            # 3. Relevance Check
            has_coverage = bool(analysis.percentages or analysis.negation_terms)
            has_worker_context = bool(analysis.worker_terms or analysis.worker_counts)
            is_relevant = (
                bool(
                    analysis.union_terms
                    or analysis.geo_matches
                    or analysis.negation_terms
                )
                or (has_coverage and has_worker_context)
                or bool(analysis.worker_counts)
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
            if analysis.worker_counts:
                # Check for range first
                range_avg = self._detect_count_range(analysis)
                
                if range_avg:
                    current_val = range_avg
                    mapped_counts = {}
                else:
                    # Try intelligent mapping first
                    mapped_counts, sent_total = self._resolve_counts_to_geography(analysis)
                    current_val = max(analysis.worker_counts)

                if mapped_counts:
                    # Use specific mappings
                    for code, count in mapped_counts.items():
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

                        if current_val > local_totals.get(region_key, 0):
                            local_totals[region_key] = current_val

                        if current_val > effective_totals.get(region_key, 0):
                            effective_totals[region_key] = current_val

                        for c in geo_context.get("countries", []):
                            c_code = c["code"]
                            # Only update if we didn't map it specifically above (though mapped_counts check covers this)
                            if current_val > local_totals.get(c_code, 0):
                                local_totals[c_code] = current_val
                            if current_val > effective_totals.get(c_code, 0):
                                effective_totals[c_code] = current_val

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
                relevant_total = get_external_worker_count(current_region, geo_context.get("countries", []))

            # 7. Determine Coverage Data (Dispatch)
            coverage_data = self._determine_coverage_data(
                analysis, relevant_total, reporting_year, is_historical=is_historical
            )

            self._apply_remaining_logic(analysis, coverage_data, results)

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
            if should_include and not has_data and BOILERPLATE_REGEX.search(sent):
                should_include = False

            # Exclude personnel events (layoffs, hiring) if no union keywords are present
            # e.g. "We laid off 500 employees." (Avoids treating 500 as a workforce total)
            if (
                should_include
                and not analysis.union_terms
                and PERSONNEL_EVENT_REGEX.search(sent)
            ):
                should_include = False

            # Filter out Risk Items embedded in Item 1
            if analysis.risk_terms and not has_data:
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
                    "sentence_index": idx,
                }
                results.append(item)

        merged_results = self._merge_continuation_items(results)

        return merged_results, local_totals, last_geo_context

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
            qual_matches = [m for m in analysis._matches if m['type'] == MatchType.QUALITATIVE_TERM]
            if qual_matches:
                match = qual_matches[0]
                term = match.get('term_obj')
                pattern_str = match.get('pattern_str', '')

                if term:
                    is_locally_negated = check_local_negation(match['span'], analysis.text)
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
            
            # Try to resolve not_covered to covered using Tracker's totals
            if covered is None and not_covered is not None:
                scope_total = None
                region = geo.get("region")
                countries = geo.get("countries", [])
                
                if len(countries) == 1:
                    code = countries[0]["code"]
                    scope_total = tracker.country_totals.get(code)
                elif region and region not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
                    scope_total = tracker.region_totals.get(region)
                elif region in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
                    scope_total = tracker.global_total
                
                if scope_total and scope_total >= not_covered:
                    covered = scope_total - not_covered
            
            tracker.record_coverage(pct, covered, geo)
            
        # Calculate Metrics
        metrics = tracker.calculate_metrics()
        
        return {
            "weighted_average_percentage": metrics["global_rate"],
            "likely_percentage": metrics["global_rate"],
            "derived_regional_coverage": {r: m["rate"] for r, m in metrics["region_stats"].items()},
            "census_global_total": tracker.global_total,
            "census_region_totals": tracker.region_totals,
            "census_country_totals": tracker.country_totals,
        }

    def compute_weighted_coverage_legacy(
        self,
        results: List[Dict[str, Any]],
        global_workforce: float = 0.0,
        region_totals: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Computes a weighted average of union coverage percentages from analysis results.
        Then selects the BEST TEXT CANDIDATE that matches the calculation.
        """
        if region_totals is None:
            region_totals = {}

        total_weighted_pct = 0.0
        total_employees = 0.0

        valid_percentages = []
        grouped_items = {}  # (weight, region_key) -> list of percentages

        for item in results:
            data = item.get("coverage_data", {})
            geo = item.get("geographic_context", {})

            # Skip non-current
            if data.get("temporal_scope") != TemporalScope.CURRENT.value:
                continue

            pct = data.get("percentage")

            # Determine Weight (Total Employees)
            weight = data.get("employee_count_total")

            # Fallback Weight Logic
            if not weight:
                covered = data.get("employee_count_covered")
                not_covered = data.get("employee_count_not_covered")
                if covered is not None and not_covered is not None:
                    weight = covered + not_covered
                elif not_covered is not None and (pct == 0 or data.get("negated")):
                    weight = not_covered

            if not weight:
                region = geo.get("region")
                if region and region in region_totals:
                    weight = region_totals[region]
                elif geo.get("countries"):
                    for c in geo["countries"]:
                        if c["code"] in region_totals:
                            weight = region_totals[c["code"]]
                            break

            if not weight and global_workforce > 0:
                if geo.get("region") in (
                    Region.INTERNATIONAL.value,
                    Region.UNKNOWN.value,
                ):
                    weight = global_workforce

            # Determine Percentage if missing
            if pct is None:
                covered = data.get("employee_count_covered")
                if covered is not None and weight and weight > 0:
                    pct = (covered / weight) * 100.0
                elif data.get("negated") and data.get("negation_type") in (
                    NegationType.ZERO_COVERAGE.value,
                    NegationType.QUALITATIVE_ZERO.value,
                ):
                    pct = 0.0

            if pct is not None:
                valid_percentages.append(pct)

                if weight and weight > 0:
                    # Group by weight and region to avoid double counting identical statements
                    region_key = (
                        geo.get("region", "UNKNOWN"),
                        tuple(sorted(c["code"] for c in geo.get("countries", []))),
                    )
                    key = (weight, region_key)

                    if key not in grouped_items:
                        grouped_items[key] = []
                    grouped_items[key].append(pct)

        # --- LOGIC TO PREVENT DOUBLE COUNTING (Global vs Regional) ---
        global_candidates = []
        regional_candidates = []

        for (weight, region_key), pcts in grouped_items.items():
            avg_pct = sum(pcts) / len(pcts)

            # Check if this group represents the Global workforce
            is_global = False
            region_name = region_key[0]

            # 1. Explicit Global Region
            if region_name in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
                if global_workforce > 0:
                    # If we know global max, require this to be significant (e.g. > 70%)
                    if weight >= 0.7 * global_workforce:
                        is_global = True
                else:
                    # If no global max known, assume International is global
                    is_global = True

            # 2. Weight matches Global Max (regardless of region label)
            if global_workforce > 0 and weight >= 0.95 * global_workforce:
                is_global = True

            if is_global:
                global_candidates.append((weight, avg_pct))
            else:
                regional_candidates.append((weight, avg_pct))

        # Decision: Use Global if available (most accurate), otherwise sum regions
        items_to_use = global_candidates if global_candidates else regional_candidates

        # Calculate Weighted Average
        for weight, avg_pct in items_to_use:
            total_weighted_pct += avg_pct * weight
            total_employees += weight

        weighted_avg = 0.0
        if total_employees > 0:
            weighted_avg = total_weighted_pct / total_employees

        # Find closest text candidate
        closest_pct = None
        if valid_percentages:
            closest_pct = min(valid_percentages, key=lambda x: abs(x - weighted_avg))

        return {
            "weighted_average_percentage": round(weighted_avg, 2),
            "total_employees_analyzed": total_employees,
            "likely_percentage": closest_pct,
            "all_percentages": sorted(valid_percentages),
        }
