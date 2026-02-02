from typing import List, Dict, Any, Optional, Tuple
import statistics

from extraction import (
    UnionExtractor, SentenceAnalysis, MatchType,
    NEGATION_REGEX, REMAIN_REGEX, RANGE_REGEX, OF_REGEX, QUALITATIVE_MULTIPLIERS
)
from defs.region_regex import REGION_CODES, Region, INT_LANGUAGE_MAP, GeoSource
from defs.output_enums import (
    Specificity, CoverageType, PercentageQualifier,
    NegationType, TemporalScope, RiskType, RelationshipStatus
)

from defs.union_regex import (
    NON_COVERAGE_REGEX, RELATIONSHIP_NEUTRAL_TERMS, RELATIONSHIP_QUALITY_TERMS, 
    RELATIONSHIP_NEGATIVE_TERMS, BOILERPLATE_REGEX,
    PERSONNEL_EVENT_REGEX
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
            "note": None
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
            pct_match = next((m for m in analysis._matches if m['type'] == MatchType.PERCENT and m['val'] == pct), None)
            count_match = next((m for m in analysis._matches if m['type'] == MatchType.WORKER_COUNT and m['val'] == count), None)
            
            if pct_match and count_match:
                p_end = pct_match['span'][1]
                c_start = count_match['span'][0]
                if p_end < c_start:
                    between = analysis.text[p_end:c_start]
                    if OF_REGEX.search(between):
                        is_percent_of_total = True

            if is_percent_of_total:
                data["employee_count_total"] = count
                data["employee_count_covered"] = round((pct / 100.0) * count)
                notes.append(f"Count (total): {count} (inferred covered: {data['employee_count_covered']})")
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
        if not analysis.percentages and not analysis.worker_counts and analysis.negation_terms:
             if any(NEGATION_REGEX.search(t) for t in analysis.negation_terms):
                 data["percentage"] = 0.0
                 data["negated"] = True
                 data["negation_type"] = NegationType.ZERO_COVERAGE.value
                 data["type"] = CoverageType.EXPLICIT_PERCENT.value
                 notes.append("Qualitative zero coverage detected")

        data["note"] = " | ".join(notes) if notes else "Simple Analysis (No Data)"
        return data


def get_external_worker_count(region: str, countries: List[Dict[str, str]]) -> Optional[float]:
    """
    Placeholder: Connect to external DB to get worker counts for a region/country.
    """
    return None

def create_risk_item(sentence: str, analysis: SentenceAnalysis, is_historical: bool = False) -> Dict[str, Any]:
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
        "type": RiskType.UNION_RISK.value if analysis.union_terms else RiskType.LABOR_RISK.value,
        "sentence": sentence,
        "labor_keywords": analysis.union_terms,
        "risk_keywords": analysis.risk_terms,
        "third_party": analysis.supplier_terms,
        "specific_to_unions": bool(analysis.union_terms),
        "union_mention": analysis.union_terms,
        "temporal_scope": temporal_scope,
        "conditional": is_conditional,
        "note": None
    }

def check_local_negation(match_span: Tuple[int, int], text: str) -> bool:
    """
    Check if a negation term appears within ~5 words before the matched pattern.
    """
    if not match_span:
        return False

    start_idx = match_span[0]
    # Look back window (approx 5 words ~ 40 chars)
    window = text[max(0, start_idx - 40):start_idx]
    
    return bool(NEGATION_REGEX.search(window))

def apply_qualitative_multipliers(raw_pct: float, span: Tuple[int, int], text: str, apply: bool = False) -> Tuple[float, Optional[str]]:
    """
    Applies qualitative multipliers (e.g. "almost", "nearly") to a percentage.
    """
    if not apply:
        return raw_pct, None

    start_idx = span[0]
    # Look back window (e.g. "almost 20%")
    window = text[max(0, start_idx - 30):start_idx]
    
    for pattern, mult in QUALITATIVE_MULTIPLIERS:
        if pattern.search(window):
            new_pct = raw_pct * mult
            # Cap at 100% if original was <= 100
            if new_pct > 100.0 and raw_pct <= 100.0:
                new_pct = 100.0
            return round(new_pct, 2), f"Adjusted from {raw_pct}% (x{mult}) via term matching '{pattern.pattern}'"
    
    return raw_pct, None

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

def determine_geo_context(analysis: SentenceAnalysis, last_context: Optional[Dict[str, Any]], current_idx: int, last_idx: int) -> Dict[str, Any]:
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
        found_regions_map = {} # code -> (region_dict, region_enum)
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
                    r_obj = {
                        "name": m.country,
                        "code": m.geo_code,
                        "countries": []
                    }
                    regions_list.append(r_obj)
                    found_regions_map[m.geo_code] = (r_obj, m.region)
                else:
                    # It is a country
                    countries.append({
                        "name": m.country,
                        "code": m.geo_code,
                        "region_enum": m.region # Temporary for mapping
                    })
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
                        conflict_notes.append(f"Union '{um.text}' ({um.region.value}) mismatches explicit region ({', '.join(r.value for r in regions)})")

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
                Specificity.EXPLICIT.value if not union_matches else Specificity.EXPLICIT_INFERRED.value
            ),
            "explicit_countries": (
                [c["name"] for c in countries] if union_matches else None
            ),
            "unusual_union_region_combo": unusual_combo,
            "union_names_mentioned": (
                [m.text for m in union_matches] if union_matches else None
            ),
            "note": "; ".join(conflict_notes) if conflict_notes else None
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
    return {"region": Region.UNKNOWN.value,  "countries": [], "specificity": Specificity.IMPLICIT.value}

def check_is_total_context(analysis: SentenceAnalysis, match_span: Optional[Tuple[int, int]] = None) -> bool:
    """
    Checks if 'total', 'global', 'worldwide', etc. are present in the sentence,
    optionally near a specific match.
    """
    if not analysis.total_modifiers:
        return False
    
    # If no span provided, just return True if modifiers exist (sentence level)
    if not match_span:
        return True
        
    # If span provided, check proximity (e.g. within 50 chars)
    total_matches = [m for m in analysis._matches if m['type'] == MatchType.TOTAL_MODIFIER]
    start, end = match_span
    
    for tm in total_matches:
        t_start, t_end = tm['span']
        # Check distance
        dist = 0
        if t_end < start: dist = start - t_end
        elif end < t_start: dist = t_start - end
        
        if dist < 60: # Window to capture "total [approx] [number]" or "total of [number]"
            return True
            
    return False

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
    q_match = next((m for m in analysis._matches if m['type'] == MatchType.RELATIONSHIP_QUALITY), None)
    
    if q_match:
        q_start = q_match['span'][0]
        # Look for negation terms ending just before q_start
        negation_matches = [m for m in analysis._matches if m['type'] in (MatchType.NEGATION, MatchType.NON_COVERAGE)]
        for n_match in negation_matches:
            n_end = n_match['span'][1]
            # Check distance (approx 25 chars covers "are not", "is not")
            if 0 < (q_start - n_end) < 25:
                is_quality_negated = True
                break

    status = RelationshipStatus.UNKNOWN
    if quality_term in RELATIONSHIP_NEUTRAL_TERMS:
        status = RelationshipStatus.NEGATIVE if is_quality_negated else RelationshipStatus.NEUTRAL 
    elif quality_term in RELATIONSHIP_QUALITY_TERMS:
        status = RelationshipStatus.NEGATIVE if is_quality_negated else RelationshipStatus.POSITIVE
    elif quality_term in RELATIONSHIP_NEGATIVE_TERMS:
        status = RelationshipStatus.POSITIVE if is_quality_negated else RelationshipStatus.NEGATIVE
    
    return status.value if status != RelationshipStatus.UNKNOWN else None

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

    def update(self, count: float, geo_context: Dict[str, Any]):
        region = geo_context.get("region")
        countries = geo_context.get("countries", [])
        
        # 1. Global Update
        # Update if region is International/Unknown OR if explicit "Total" context implies global
        if region in (Region.INTERNATIONAL.value, Region.UNKNOWN.value) and not countries:
             if count > self.global_total:
                 self.global_total = count
        
        # 2. Regional Update
        if region and region not in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
            if count > self.region_totals.get(region, 0):
                self.region_totals[region] = count
            
            # Track hierarchy for resolution
            if region not in self.region_country_map:
                self.region_country_map[region] = set()
            for c in countries:
                self.region_country_map[region].add(c["code"])
                
        # 3. Country Update
        for c in countries:
            code = c["code"]
            if count > self.country_totals.get(code, 0):
                self.country_totals[code] = count

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
                known_countries, 
                key=lambda x: self.country_totals[x], 
                reverse=True
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

class UnionAnalyzer:
    def __init__(self):
        self.extractor = UnionExtractor()
        self.simple_analyzer = SimpleCoverageAnalyzer()

    def _determine_geo_context(self, analysis: SentenceAnalysis, last_context, current_idx, last_idx) -> Dict[str, Any]:
        """
        Local wrapper for geographic context determination.
        """
        return determine_geo_context(analysis, last_context, current_idx, last_idx)

    def analyze_paragraph(self, text: str, item_type: str = "item1", reporting_year: Optional[int] = None) -> Dict[str, Any]:
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
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
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
                    previous_totals=prev_paragraph_totals
                )
                
                # Update all_region_totals with max found across all blocks
                for reg, count in local_totals.items():
                    if count > all_region_totals.get(reg, 0):
                        all_region_totals[reg] = count

                results.extend(block_results)
                # Update previous totals for the next iteration (Sliding window: only look back 1 paragraph)
                prev_paragraph_totals = local_totals

            summary = self.compute_weighted_coverage(results, tracker, all_region_totals)

        return {"items": results, "summary": summary}

    def _populate_tracker(self, sentences: List[str], tracker: Tracker, reporting_year: Optional[int] = None):
        """
        Pass 1: Scans text specifically to find population totals (denominators)
        and populate the Tracker.
        """
        last_geo_context = None
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
                geo_context = self._determine_geo_context(analysis, last_geo_context, idx, last_geo_sentence_idx)
                
                if geo_context["specificity"] in (Specificity.EXPLICIT.value, Specificity.INFERRED_UNION.value):
                    last_geo_context = geo_context
                    last_geo_sentence_idx = idx
                    
                tracker.update(max(analysis.worker_counts), geo_context)

    def _analyze_block(
        self, 
        sentences: List[str], 
        reporting_year: Optional[int] = None,
        global_max_workers: float = 0.0,
        initial_geo_context: Optional[Dict] = None,
        previous_totals: Optional[Dict[str, float]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], Optional[Dict]]:
        """
        Analyzes a block of sentences (paragraph) for Item 1.
        Returns results, totals found in THIS block, and the final geo context.
        """
        results = []
        analyzed_sentences = [self.extractor.analyze_sentence(s) for s in sentences]

        # Context inheritance state
        last_geo_context = initial_geo_context
        last_geo_sentence_idx = -1
        last_employee_count = None
        
        # Totals found strictly within this block
        local_totals = {}
        # Effective totals for lookup (Previous Paragraph + Local So Far)
        effective_totals = previous_totals.copy() if previous_totals else {}

        for idx, analysis in enumerate(analyzed_sentences):
            sent = sentences[idx]

            # 1. Historical Check
            is_historical = False
            years_indicate_past = False
            if reporting_year and analysis.years:
                if all(y < reporting_year for y in analysis.years):
                    years_indicate_past = True
            
            if (years_indicate_past or analysis.has_historical) and not analysis.has_current:
                is_historical = True

            # 2. Update Context (Worker Counts)
            if analysis.worker_counts and not is_historical:
                last_employee_count = max(analysis.worker_counts)

            # 3. Relevance Check
            has_coverage = bool(analysis.percentages or analysis.negation_terms)
            has_worker_context = bool(analysis.worker_terms or analysis.worker_counts)
            is_relevant = (
                bool(analysis.union_terms or analysis.geo_matches or analysis.negation_terms) or
                (has_coverage and has_worker_context) or
                bool(analysis.worker_counts)
            )

            if not is_relevant:
                continue

            # 4. Determine Geographic Context
            geo_context = self._determine_geo_context(
                analysis, last_geo_context, idx, last_geo_sentence_idx
            )

            if geo_context["specificity"] in (Specificity.EXPLICIT.value, Specificity.INFERRED_UNION.value):
                last_geo_context = geo_context
                last_geo_sentence_idx = idx

            # 5. Update Region Totals
            if analysis.worker_counts:
                current_max = max(analysis.worker_counts)
                if geo_context["specificity"] in (Specificity.EXPLICIT.value, Specificity.INHERITED.value, Specificity.INFERRED_UNION.value):
                    region_key = geo_context["region"]
                    
                    # Update local totals (max seen in this block for this region)
                    if current_max > local_totals.get(region_key, 0):
                        local_totals[region_key] = current_max
                    
                    # Update effective totals (best available info)
                    # We update effective totals if the current local count provides better info
                    if current_max > effective_totals.get(region_key, 0):
                        effective_totals[region_key] = current_max

                    # Also update specific countries if present
                    for c in geo_context.get("countries", []):
                        c_code = c["code"]
                        if current_max > local_totals.get(c_code, 0):
                            local_totals[c_code] = current_max
                        if current_max > effective_totals.get(c_code, 0):
                            effective_totals[c_code] = current_max

            # 6. Determine Relevant Total for Calculation
            relevant_total = None
            current_region = geo_context["region"]
            
            # Priority: Local > Effective (Previous) > Global
            if current_region in local_totals:
                relevant_total = local_totals[current_region]
            elif current_region in effective_totals:
                relevant_total = effective_totals[current_region]
            elif current_region in (Region.INTERNATIONAL.value, Region.UNKNOWN.value) and global_max_workers > 0:
                relevant_total = global_max_workers
            elif last_employee_count:
                relevant_total = last_employee_count

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
                and not has_data
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

            # Filter out Risk Items embedded in Item 1
            if analysis.risk_terms and not has_data:
                risk_item = create_risk_item(sent, analysis, is_historical=is_historical)
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
                    "sentence_index": idx
                }
                results.append(item)

        return results, local_totals, last_geo_context

    def _determine_coverage_data(
        self, analysis: SentenceAnalysis, inherited_total_count: Optional[float] = None, reporting_year: Optional[int] = None, is_historical: bool = False
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
        
        return data

    def _analyze_complex_coverage(self, analysis: SentenceAnalysis, total_count: Optional[float]) -> Dict[str, Any]:
        """
        Handles complex scenarios: mixed coverage, ratios, inferred totals, etc.
        (Placeholder for the complex logic to be re-added/refined)
        """
        data = {
            "percentage": None,
            "employee_count_covered": None,
            "employee_count_not_covered": None,
            "employee_count_total": total_count,
            "negated": False,
            "negation_type": None,
            "type": CoverageType.QUALITATIVE.value,
            "note": None
        }

        # 1. Resolve Mixed Coverage (e.g. "500 union, 200 non-union")
        self._resolve_mixed_coverage(analysis, data)

        # 2. Handle Ratios (e.g. "500 out of 2000")
        if not data["percentage"] and analysis.ratios:
            numerator, denominator = analysis.ratios[0]
            if denominator > 0:
                pct = (numerator / denominator) * 100
                data["percentage"] = round(pct, 2)
                data["type"] = CoverageType.CALCULATED.value
                data["employee_count_covered"] = numerator
                data["employee_count_total"] = denominator
                data["note"] = f"Calculated from ratio: {numerator}/{denominator}"

        # 3. Calculate Percentage from Counts
        if data["percentage"] is None and data["employee_count_covered"] is not None and total_count:
            if total_count >= data["employee_count_covered"] and total_count > 0:
                pct = (data["employee_count_covered"] / total_count) * 100
                data["percentage"] = round(pct, 2)
                data["type"] = CoverageType.CALCULATED.value
                data["note"] = f"Calculated from count {data['employee_count_covered']} / total {total_count}"

        # 4. Calculate Count from Percentage
        if data["employee_count_covered"] is None and data["percentage"] is not None and total_count:
            data["employee_count_covered"] = round((data["percentage"] / 100) * total_count)
            data["note"] = f"Inferred count from {data['percentage']}% of {total_count}"

        # 5. Handle Negation without specific counts
        if not data["percentage"] and not data["employee_count_covered"]:
            if analysis.negation_terms:
                # Check for "None" or "No employees"
                if any(NEGATION_REGEX.search(t) for t in analysis.negation_terms):
                    data["percentage"] = 0.0
                    data["negated"] = True
                    data["negation_type"] = NegationType.ZERO_COVERAGE.value
                    data["type"] = CoverageType.EXPLICIT_PERCENT.value
                elif any(NON_COVERAGE_REGEX.search(t) for t in analysis.negation_terms):
                    data["negated"] = True
                    data["negation_type"] = NegationType.NOT_COVERED.value

        return data

    def _resolve_mixed_coverage(self, analysis: SentenceAnalysis, data: Dict[str, Any]):
        """
        Resolves mixed coverage scenarios (e.g. "500 union, 200 non-union") by
        mapping counts/percentages to the nearest positive/negative keywords.
        Updates 'data' in-place.
        """
        # 1. Gather entities
        counts = [m for m in analysis._matches if m['type'] == MatchType.WORKER_COUNT]
        percents = [m for m in analysis._matches if m['type'] == MatchType.PERCENT]
        numbers = [m for m in analysis._matches if m['type'] == MatchType.NUMBER]
        
        # Combine counts and numbers (prefer counts, but use numbers if needed)
        count_spans = set(c['span'] for c in counts)
        all_values = counts + [n for n in numbers if n['span'] not in count_spans]

        # Indicators
        positives = [m for m in analysis._matches if m['type'] in (MatchType.UNION_TERM, MatchType.SPECIFIC_UNION, MatchType.UNION_NAME, MatchType.COVERAGE_TERM)]
        negatives = [m for m in analysis._matches if m['type'] in (MatchType.NON_UNION, MatchType.NEGATION, MatchType.NON_COVERAGE)]
        totals = [m for m in analysis._matches if m['type'] in (MatchType.WORKER_TERM, MatchType.TOTAL_MODIFIER)]
        
        # Helper to find nearest indicator
        def get_nearest_type(target_span):
            t_start, t_end = target_span
            best_dist = float('inf')
            best_type = None # 'covered', 'not_covered', 'total'
            
            candidates = []
            for p in positives: candidates.append(('covered', p))
            for n in negatives: candidates.append(('not_covered', n))
            for t in totals: candidates.append(('total', t))
            
            for c_type, m in candidates:
                m_start, m_end = m['span']
                
                # Distance calculation
                dist = 0
                if m_end < t_start: dist = t_start - m_end
                elif t_end < m_start: dist = m_start - t_end
                
                # Weighting: Negatives/Positives are stronger signals than Totals
                eff_dist = dist
                if c_type == 'total':
                    eff_dist += 20 # Penalty to prefer specific union/non-union terms
                
                if eff_dist < best_dist:
                    best_dist = eff_dist
                    best_type = c_type
            
            if best_dist > 150: return None # Threshold
            return best_type

        # Map Percentages
        for p in percents:
            ptype = get_nearest_type(p['span'])
            
            # Use standalone function
            adj_val, note = apply_qualitative_multipliers(p['val'], p['span'], analysis.text, apply=True)
            
            if ptype == 'not_covered':
                # Invert
                val = adj_val
                data['percentage'] = 100.0 - val
                data['negated'] = True
                data['negation_type'] = NegationType.NOT_COVERED.value
                data['note'] = f"Inverted from {val}% not covered"
                if note:
                    data['note'] += f" ({note})"
            elif ptype == 'covered':
                data['percentage'] = adj_val
                if note:
                    data['note'] = note

        # Map Counts
        total_candidates = []
        for c in all_values:
            val = c['val']
            ctype = get_nearest_type(c['span'])
            
            if ctype == 'covered':
                data['employee_count_covered'] = val
            elif ctype == 'not_covered':
                data['employee_count_not_covered'] = val
            elif ctype == 'total':
                total_candidates.append(val)
        
        # Handle Totals
        if total_candidates:
            data['employee_count_total'] = sum(total_candidates)

        # Calculate missing values
        if data['employee_count_covered'] and data['employee_count_not_covered']:
             if not data['employee_count_total']:
                 data['employee_count_total'] = data['employee_count_covered'] + data['employee_count_not_covered']
             
             # Recalculate percentage based on the aggregate counts
             pct = (data['employee_count_covered'] / data['employee_count_total']) * 100
             data['percentage'] = round(pct, 2)
             data['type'] = CoverageType.CALCULATED.value
             data['note'] = (data['note'] or "") + f" | Recalculated % from counts: {data['employee_count_covered']}/{data['employee_count_total']}"

        elif data['employee_count_total'] and data['employee_count_covered'] and not data['percentage']:
             pct = (data['employee_count_covered'] / data['employee_count_total']) * 100
             data['percentage'] = round(pct, 2)
             data['type'] = CoverageType.CALCULATED.value

    def _analyze_item1a(self, sentences: List[str], reporting_year: Optional[int] = None) -> List[Dict[str, Any]]:
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
            
            if (years_indicate_past or analysis.has_historical) and not analysis.has_current:
                is_historical = True

            # Item 1A logic: Look for risk terms, union terms, supplier terms, or relationship terms
            if (analysis.risk_terms or analysis.union_terms or analysis.supplier_terms or 
                analysis.relationship_quality_terms or analysis.relationship_terms):
                result = create_risk_item(sent, analysis, is_historical=is_historical)
                if result:
                    results.append(result)
        return results

    def compute_weighted_coverage(self, results: List[Dict[str, Any]], tracker: Tracker, region_totals: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        New summary function that currently just returns the Tracker's census data.
        """
        return {
            "census_global_total": tracker.global_total,
            "census_region_totals": tracker.region_totals,
            "census_country_totals": tracker.country_totals
        }

    def compute_weighted_coverage_legacy(self, results: List[Dict[str, Any]], global_workforce: float = 0.0, region_totals: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Computes a weighted average of union coverage percentages from analysis results.
        Then selects the BEST TEXT CANDIDATE that matches the calculation.
        """
        if region_totals is None:
            region_totals = {}

        total_weighted_pct = 0.0
        total_employees = 0.0
        
        valid_percentages = []
        grouped_items = {} # (weight, region_key) -> list of percentages

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
                if geo.get("region") in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
                    weight = global_workforce

            # Determine Percentage if missing
            if pct is None:
                covered = data.get("employee_count_covered")
                if covered is not None and weight and weight > 0:
                    pct = (covered / weight) * 100.0
                elif data.get("negated") and data.get("negation_type") in (NegationType.ZERO_COVERAGE.value, NegationType.QUALITATIVE_ZERO.value):
                    pct = 0.0

            if pct is not None:
                valid_percentages.append(pct)
                
                if weight and weight > 0:
                    # Group by weight and region to avoid double counting identical statements
                    region_key = (
                        geo.get("region", "UNKNOWN"),
                        tuple(sorted(c["code"] for c in geo.get("countries", [])))
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
            "all_percentages": sorted(valid_percentages)
        }
