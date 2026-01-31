import re
from typing import List, Dict, Any, Optional

from union.extraction import UnionExtractor, SentenceAnalysis, MatchType
from defs.region_regex import Region, INT_LANGUAGE_MAP, GeoSource
from defs.output_enums import (
    Specificity, CoverageType, PercentageQualifier, 
    NegationType, TemporalScope, RiskType
)


class UnionAnalyzer:
    def __init__(self):
        self.extractor = UnionExtractor()

    def _get_external_worker_count(self, region: str, countries: List[Dict[str, str]]) -> Optional[float]:
        """
        Placeholder: Connect to external DB to get worker counts for a region/country.
        Currently returns None as requested.
        """
        return None

    def analyze_paragraph(self, text: str, item_type: str = "item1") -> List[Dict[str, Any]]:
        """
        Process a paragraph of text, splitting it into sentences and 
        extracting details based on item_type (item1 or item1a).
        """
        sentences = self.extractor.split_sentences(text)

        if item_type == "item1a":
            return self._analyze_item1a(sentences)

        return self._analyze_item1(sentences)

    def _analyze_item1(self, sentences: List[str]) -> List[Dict[str, Any]]:
        """
        Analyzes sentences for Item 1 (Union Coverage) with context inheritance.
        """
        results = []

        # Pre-analyze all sentences to find global max (highest relevant number)
        # This helps establish a "Global Total" context (e.g. "We have 50,000 employees total")
        analyzed_sentences = [self.extractor.analyze_sentence(s) for s in sentences]
        
        global_max_workers = 0.0
        for ans in analyzed_sentences:
            if ans.worker_counts:
                global_max_workers = max(global_max_workers, max(ans.worker_counts))

        # Context inheritance state
        last_geo_context = None
        last_geo_sentence_idx = -1
        last_employee_count = None
        
        # Map specific regions/codes to their employee counts
        # Key: Region Name or Country Code -> Value: Count
        region_totals = {}

        for idx, analysis in enumerate(analyzed_sentences):
            sent = sentences[idx]

            # Skip if no relevant info (no union terms and no explicit coverage data)
            # We allow sentences without union terms IF they have coverage data AND we have inherited context
            has_coverage = bool(analysis.percentages or analysis.negation_terms)
            has_worker_context = bool(analysis.worker_terms or analysis.worker_counts)

            # Update sequential context (Employee Counts) even if sentence is skipped
            if analysis.worker_counts:
                last_employee_count = max(analysis.worker_counts) # Assume largest is total

            # Relevance Check:
            # 1. Union Terms: Always relevant.
            # 2. Geo Matches: Relevant for context updates.
            # 3. Coverage Data: Relevant ONLY if accompanied by Worker Context (to avoid "no debt" -> 0% coverage).
            is_relevant = False
            if analysis.union_terms or analysis.geo_matches:
                is_relevant = True
            elif has_coverage and has_worker_context:
                is_relevant = True

            if not is_relevant:
                continue

            # 1. Determine Geographic Context
            geo_context = self._determine_geo_context(
                analysis, last_geo_context, idx, last_geo_sentence_idx
            )

            # Update inheritance state if we found explicit or strong inferred context
            if geo_context["specificity"] in (
                Specificity.EXPLICIT.value,
                Specificity.EXPLICIT_INFERRED.value,
                Specificity.INFERRED_UNION.value,
            ):
                last_geo_context = geo_context
                last_geo_sentence_idx = idx

            # Update Region Totals if this sentence has a worker count
            # We assume if a sentence has a count and a specific region, that count applies to that region
            if analysis.worker_counts:
                current_max = max(analysis.worker_counts)
                
                # If context is explicit, map this count to the region/countries
                if geo_context["specificity"] in (Specificity.EXPLICIT.value, Specificity.EXPLICIT_INFERRED.value):
                    region_key = geo_context["region"]
                    region_totals[region_key] = current_max
                    
                    for c in geo_context.get("countries", []):
                        region_totals[c["code"]] = current_max

            # Determine best available total for calculation
            # Priority: 
            # 1. Region-specific total (if we are in that region)
            # 2. Global total (if we are in Global/Unknown/International region)
            # 3. Sequential fallback
            relevant_total = None
            current_region = geo_context["region"]
            
            if current_region in region_totals:
                relevant_total = region_totals[current_region]
            
            # Check external source if text didn't provide it
            if not relevant_total:
                relevant_total = self._get_external_worker_count(current_region, geo_context.get("countries", []))

            if not relevant_total:
                if current_region in (
                    Region.INTERNATIONAL.value,
                    Region.UNKNOWN.value,
                    Region.NORTH_AMERICA.value,
                ) and global_max_workers > 0:
                    relevant_total = global_max_workers
                else:
                    relevant_total = last_employee_count or global_max_workers

            # 2. Determine Coverage Data
            coverage_data = self._determine_coverage_data(analysis, relevant_total)

            # 3. Construct Item 1 JSON
            # Rule: Include if we have union terms OR (coverage data AND inherited context)
            should_include = False
            if analysis.union_terms:
                should_include = True
            elif (
                coverage_data
                and geo_context["specificity"] == Specificity.INHERITED.value
            ):
                should_include = True

            # Exclude if it looks like a risk statement (Item 1A) without concrete coverage data
            # (Simple heuristic: if risk terms exist and no percentage/numbers, it's likely 1A)
            if (
                analysis.risk_terms
                and not coverage_data["percentage"]
                and not coverage_data["negated"]
            ):
                should_include = False

            if should_include:
                item = {
                    "sentence": sent,
                    "keyword_matched": (
                        analysis.union_terms[0] if analysis.union_terms else None
                    ),
                    "geographic_context": geo_context,
                    "coverage_data": coverage_data,
                }
                results.append(item)

        return results

    def _determine_geo_context(
        self, analysis: SentenceAnalysis, last_context, current_idx, last_idx
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
            seen_codes = set()
            regions = set()

            unusual_combo = False
            conflict_notes = []

            for m in explicit_matches:
                if m.country and m.geo_code not in seen_codes:
                    countries.append({"name": m.country, "code": m.geo_code})
                    seen_codes.add(m.geo_code)
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

            # Handle "International" language matches (e.g. "Sindicato" -> INT_PT)
            # If we have explicit countries, check if they align with the language
            # e.g. Brazil (BR) + INT_PT (BR, PT) -> Consistent

            region_val = (
                Region.INTERNATIONAL.value
                if len(regions) > 1
                else (list(regions)[0].value if regions else Region.UNKNOWN.value)
            )

            return {
                "region": region_val,
                "countries": countries,
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
                    "region": "International",  # Broad region
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
            # Remove fields specific to the source sentence
            ctx.pop("union_names_mentioned", None)
            ctx.pop("explicit_countries", None)
            return ctx

        # 4. Fallback
        return {"region": Region.UNKNOWN.value,  "countries": [], "specificity": Specificity.IMPLICIT.value}

    def _determine_coverage_data(
        self, analysis: SentenceAnalysis, inherited_total_count: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Extracts percentage, negation, and count data.
        """
        data = {
            "percentage": None,
            "percentage_raw_stated": None,
            "calculated_percentage": None,
            "type": CoverageType.QUALITATIVE.value,
            "percentage_qualifier": None,
            "employee_count_covered": None,
            "employee_count_not_covered": None,
            "employee_count_total": None,
            "negated": False,
            "negation_type": None,
            "temporal_scope": TemporalScope.CURRENT.value,  # Default
            "effective_date": None,
            "expected_date": None,
            "ambiguity": None,
            "note": None,
            "extracted_numbers": [],
        }

        # NEW: Mixed Coverage Detection & Resolution
        # If we have multiple counts or percentages, try to disambiguate using proximity
        if len(analysis.worker_counts) > 1 or len(analysis.percentages) > 1:
             self._resolve_mixed_coverage(analysis, data)

        # Check for Negation
        is_negated = False
        negation_type = None

        # "No employees", "None of", "Not covered"
        if analysis.negation_terms:
            is_negated = True
            # Determine type by checking all terms
            # Default to NOT_COVERED (e.g. "not")
            negation_type = NegationType.NOT_COVERED.value

            for term in analysis.negation_terms:
                t_lower = term.lower()
                # Check for Zero Coverage indicators ("no", "none")
                if t_lower in ("no", "none", "neither", "nor", "never"):
                    negation_type = NegationType.ZERO_COVERAGE.value
                    # Zero coverage takes precedence (e.g. "no union employees" -> 0%)
                    break

                # Check for Non-Union specific terms (from NON_UNION_REGEX)
                # e.g. "non-union", "not-union"
                if "union" in t_lower:
                    negation_type = NegationType.NOT_COVERED.value

        # Extract Percentage
        if analysis.percentages and not data["percentage"]:
            raw_pct = analysis.percentages[0]
            data["type"] = CoverageType.EXPLICIT_PERCENT.value

            if is_negated and negation_type == NegationType.NOT_COVERED.value:
                # "12% are NOT covered" -> 88% covered
                data["percentage"] = 100.0 - raw_pct
                data["percentage_raw_stated"] = raw_pct
                data["negated"] = True
                data["negation_type"] = NegationType.NOT_COVERED.value
                data["note"] = f"Inverted from {raw_pct}% not covered"
            else:
                data["percentage"] = raw_pct
                if is_negated:
                    # "No employees (0%)" or similar redundancy
                    data["negated"] = True
                    data["negation_type"] = negation_type

        # Handle "No employees" / "None" -> 0%
        elif is_negated and negation_type == NegationType.ZERO_COVERAGE.value and not data["percentage"]:
            data["percentage"] = 0.0
            data["type"] = CoverageType.EXPLICIT_PERCENT.value  # Treated as explicit 0
            data["negated"] = True
            data["negation_type"] = NegationType.ZERO_COVERAGE.value
            data["employee_count_covered"] = 0

        # Handle "Non-union" -> 0% (if no other numbers)
        elif (
            is_negated
            and negation_type == NegationType.NOT_COVERED.value
            and not analysis.percentages
            and not data["percentage"]
        ):
            # "We are non-union" -> 0%
            data["percentage"] = 0.0
            data["type"] = CoverageType.QUALITATIVE.value
            data["negated"] = True
            data["negation_type"] = NegationType.QUALITATIVE_ZERO.value
            data["percentage_qualifier"] = PercentageQualifier.NONE.value

        # Handle Ratios (Calculated Percentage)
        elif not data["percentage"] and analysis.ratios:
            numerator, denominator = analysis.ratios[0]
            if denominator > 0:
                pct = (numerator / denominator) * 100
                data["percentage"] = round(pct, 2)
                data["calculated_percentage"] = round(pct, 2)
                data["type"] = CoverageType.CALCULATED.value
                data["employee_count_covered"] = numerator
                data["employee_count_total"] = denominator
                data["note"] = f"Calculated from ratio: {numerator} of {denominator}"

        # Handle Numbers (Basic mapping for now)
        if analysis.numbers and not data["employee_count_covered"]:
            # Store raw numbers for potential downstream analysis (e.g. Compustat merging)
            data["extracted_numbers"] = analysis.numbers

            # Heuristic: If we have negation "not covered" and a number, assume it's the count not covered
            if (
                is_negated
                and negation_type == NegationType.NOT_COVERED.value
                and not data["percentage"]
            ):
                val = analysis.numbers[0]
                data["employee_count_not_covered"] = val
                data["negated"] = True
                data["negation_type"] = NegationType.NOT_COVERED.value

                # Try to calculate percentage if we have a total
                total = inherited_total_count
                if analysis.worker_counts:
                    total = max(analysis.worker_counts)

                if total and total > val:
                    data["employee_count_total"] = total
                    pct_covered = ((total - val) / total) * 100
                    data["calculated_percentage"] = round(pct_covered, 2)
                    data["percentage"] = round(pct_covered, 2)
                    data["type"] = CoverageType.CALCULATED.value
                    
                    if pct_covered > 100.0:
                        data["ambiguity"] = "CALCULATION_ERROR_OVER_100"
                        data["note"] = f"Calculated percentage {pct_covered:.2f}% exceeds 100%"
                    else:
                        data["note"] = (
                            f"Calculated: ({total} total - {val} not covered) / {total}"
                        )

        return data

    def _resolve_mixed_coverage(self, analysis: SentenceAnalysis, data: Dict[str, Any]):
        """
        Resolves mixed coverage scenarios (e.g. "500 union, 200 non-union") by
        mapping counts/percentages to the nearest positive/negative keywords.
        Updates 'data' in-place.
        """
        # 1. Gather entities with spans
        counts = [m for m in analysis._matches if m['type'] == MatchType.WORKER_COUNT]
        percents = [m for m in analysis._matches if m['type'] == MatchType.PERCENT]
        
        # Positive indicators: Union terms
        positives = [m for m in analysis._matches if m['type'] in (MatchType.UNION_TERM, MatchType.SPECIFIC_UNION, MatchType.UNION_NAME)]
        
        # Negative indicators: Non-union terms or specific negation
        negatives = [m for m in analysis._matches if m['type'] in (MatchType.NON_UNION, MatchType.NEGATION, MatchType.NON_COVERAGE)]
        
        # Helper to find nearest indicator
        def get_nearest_type(target_span):
            t_start, t_end = target_span
            best_dist = float('inf')
            best_type = None # 'covered', 'not_covered'
            
            # Check positives
            for p in positives:
                p_start, p_end = p['span']
                # Check overlap (strongest signal)
                if p_start >= t_start and p_end <= t_end:
                    return 'covered'
                # Distance
                dist = min(abs(t_start - p_end), abs(p_start - t_end))
                if dist < best_dist:
                    best_dist = dist
                    best_type = 'covered'
            
            # Check negatives
            for n in negatives:
                n_start, n_end = n['span']
                if n_start >= t_start and n_end <= t_end:
                    return 'not_covered'
                dist = min(abs(t_start - n_end), abs(n_start - t_end))
                if dist < best_dist:
                    best_dist = dist
                    best_type = 'not_covered'
            
            return best_type

        # Process Counts
        if counts:
            # Sort counts descending to identify potential total (heuristic: largest is total)
            sorted_counts = sorted(counts, key=lambda x: x['val'], reverse=True)
            largest_val = sorted_counts[0]['val']
            
            # If we have 3+ counts, or 2 counts that sum to approx the largest, assume largest is total
            # For now, simple mapping
            for c in counts:
                val = c['val']
                ctype = get_nearest_type(c['span'])
                
                if ctype == 'covered':
                    data['employee_count_covered'] = val
                elif ctype == 'not_covered':
                    data['employee_count_not_covered'] = val
                elif val == largest_val and len(counts) > 1:
                    data['employee_count_total'] = val

            # Calculate total/percentage if missing
            if data['employee_count_covered'] and data['employee_count_not_covered']:
                if not data['employee_count_total']:
                    data['employee_count_total'] = data['employee_count_covered'] + data['employee_count_not_covered']
                
                # Calculate %
                pct = (data['employee_count_covered'] / data['employee_count_total']) * 100
                data['calculated_percentage'] = round(pct, 2)
                if not data['percentage']:
                    data['percentage'] = round(pct, 2)
                    data['type'] = CoverageType.CALCULATED.value
                    
                    if pct > 100.0:
                        data["ambiguity"] = "CALCULATION_ERROR_OVER_100"
                        data["note"] = f"Calculated percentage {pct:.2f}% exceeds 100%"
                    else:
                        data['note'] = f"Calculated from mixed counts: {data['employee_count_covered']} covered, {data['employee_count_not_covered']} not covered"

    def _analyze_item1a(self, sentences: List[str]) -> List[Dict[str, Any]]:
        """
        Analyzes sentences for Item 1A (Risk Factors).
        """
        results = []
        for sent in sentences:
            analysis = self.extractor.analyze_sentence(sent)

            # Item 1A logic: Look for risk terms
            if analysis.risk_terms:
                is_conditional = bool(re.search(r"\b(?:if|could|may|might|potential|possible|can)\b", sent, re.IGNORECASE))

                item = {
                    "type": RiskType.UNION_RISK.value if analysis.union_terms else RiskType.LABOR_RISK.value,
                    "sentence": sent,
                    "labor_keywords": analysis.union_terms,
                    "risk_keywords": analysis.risk_terms,
                    "specific_to_unions": bool(analysis.union_terms),
                    "union_mention": analysis.union_terms[0] if analysis.union_terms else None,
                    "temporal_scope": TemporalScope.CONDITIONAL.value if is_conditional else TemporalScope.CURRENT.value,
                    "conditional": is_conditional,
                    "note": None
                }
                results.append(item)
        return results

if __name__ == "__main__":
    import json

    analyzer = UnionAnalyzer()

    examples = [
        "Approximately 12% of our U.S. workforce is represented by labor unions.",
        "Our operations in Germany, France, and the UK have collective bargaining agreements covering approximately 55% of employees in those regions.",
        "Approximately 30% of our employees are represented by the UAW (United Auto Workers).",
        "We have no employees covered by collective bargaining agreements.",
        "Our international operations span Europe. Approximately 45% of our employees in these regions are covered.",
    ]

    print("Running Analysis on Examples:\n")
    for ex in examples:
        print(f"Input: {ex}")
        results = analyzer.analyze_paragraph(ex)
        print(json.dumps(results, indent=2))
        print("-" * 60)
