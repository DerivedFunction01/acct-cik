import re
from typing import List, Dict, Any, Optional

from extraction import UnionExtractor, SentenceAnalysis, MatchType
from defs.region_regex import Region, INT_LANGUAGE_MAP, GeoSource
from defs.output_enums import (
    Specificity, CoverageType, PercentageQualifier,
    NegationType, TemporalScope, RiskType, RelationshipStatus
)
from defs.text_cleaner import MinimalTextCleaner
from defs.union_regex import (
    NON_COVERAGE_REGEX, RELATIONSHIP_QUALITY_TERMS, 
    RELATIONSHIP_NEGATIVE_TERMS, BOILERPLATE_REGEX
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

            # Exclude "monitoring" statements with no data (Statement Only)
            if (
                should_include
                and not coverage_data["percentage"]
                and not coverage_data["extracted_numbers"]
                and not coverage_data["negated"]
                and BOILERPLATE_REGEX.search(sent)
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

        # Post-processing: Merge continuation items (Fix for Germany split)
        # If an item inherits context and looks like a breakdown of the previous item, merge them.
        merged_results = []
        skip_indices = set()
        
        for i in range(len(results)):
            if i in skip_indices:
                continue
                
            current = results[i]
            
            # Check if next item is a candidate for merging
            if i + 1 < len(results):
                next_item = results[i+1]
                
                # Criteria: Next item inherits from Current, and Current has data
                if (next_item["geographic_context"]["specificity"] == Specificity.INHERITED.value and
                    next_item["geographic_context"].get("inherited_from_sentence_index") == i and # Approximation since we don't store original index in result, but sequential usually implies it
                    current["coverage_data"]["type"] != CoverageType.QUALITATIVE.value):
                    
                    # Check for "remaining", "rest" in sentence
                    if re.search(r"\b(?:remaining|rest|balance|other)\b", next_item["sentence"], re.IGNORECASE):
                        # Merge Data
                        c_data = current["coverage_data"]
                        n_data = next_item["coverage_data"]
                        
                        # Fill in missing pieces
                        if not c_data["employee_count_not_covered"] and n_data["employee_count_not_covered"]:
                            c_data["employee_count_not_covered"] = n_data["employee_count_not_covered"]
                        
                        skip_indices.add(i+1)
            
            merged_results.append(current)

        return merged_results

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

            # Filter out invalid codes (Regions masquerading as countries)
            valid_countries = []
            for c in countries:
                if c["code"]: # and c["code"] not in ["", "AFRICA", "INT", "APAC", "LATAM", "EU", "MEA"]:
                     valid_countries.append(c)
            countries = valid_countries

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
            "relationship_status": None,
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
                # Check for Zero Coverage indicators (Absolute negation)
                if re.search(r"\b(?:no|none|neither|nor|never|without)\b", t_lower):
                    negation_type = NegationType.ZERO_COVERAGE.value
                    # Zero coverage takes precedence (e.g. "no union employees" -> 0%)
                    break

                # Check for Not Covered indicators (Status negation)
                if NON_COVERAGE_REGEX.search(t_lower):
                    negation_type = NegationType.NOT_COVERED.value

        # Check for Percentage Range (e.g. "33% to 37%")
        if len(analysis.percentages) >= 2:
            p1 = analysis.percentages[0]
            p2 = analysis.percentages[1]
            # Find spans to check text between
            matches = [m for m in analysis._matches if m['type'] == MatchType.PERCENT]
            if len(matches) >= 2:
                span1 = matches[0]['span']
                span2 = matches[1]['span']
                text_between = analysis.text[span1[1]:span2[0]]
                if re.search(r'\b(?:to|-|and)\b', text_between):
                    data["percentage"] = p1
                    data["ambiguity"] = f"RANGE_{p1}_TO_{p2}_PERCENT"
                    data["percentage_qualifier"] = PercentageQualifier.RANGE.value

        # Extract Percentage
        if analysis.percentages and not data["percentage"]:
            raw_pct = analysis.percentages[0]
            data["type"] = CoverageType.EXPLICIT_PERCENT.value

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
            and not analysis.numbers # Don't zero out if we have numbers to process
            and not analysis.ratios
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
                # Check if negation applies to the ratio (e.g. "8500 of 15000 operate outside")
                if is_negated and negation_type in (NegationType.NOT_COVERED.value, NegationType.ZERO_COVERAGE.value):
                    data["employee_count_not_covered"] = numerator
                    data["employee_count_total"] = denominator
                    data["employee_count_covered"] = denominator - numerator
                    
                    pct_covered = (data["employee_count_covered"] / denominator) * 100
                    data["percentage"] = round(pct_covered, 2)
                    data["calculated_percentage"] = round(pct_covered, 2)
                    data["type"] = CoverageType.CALCULATED.value
                    data["negated"] = True
                    data["negation_type"] = negation_type
                    data["note"] = f"Calculated from ratio (negated): {numerator} not covered out of {denominator}"
                else:
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
            
            # Check for "Percent OF Number" pattern (Global Aggregate case)
            # If we have a percentage and a number, and "of" is between them, the number is Total
            if data["percentage"] is not None and not data["employee_count_total"]:
                # Simple check: is there a number that is larger than covered count?
                # Or check text proximity?
                # For now, if we have a percentage, and a large number, assume it's total
                if analysis.numbers[0] > 1000 and (not data["employee_count_covered"] or analysis.numbers[0] > data["employee_count_covered"]):
                     data["employee_count_total"] = analysis.numbers[0]

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
                        data["ambiguity"] = PercentageQualifier.CALC_ERROR.value
                        data["note"] = f"Calculated percentage {pct_covered:.2f}% exceeds 100%"
                    else:
                        data["note"] = (
                            f"Calculated: ({total} total - {val} not covered) / {total}"
                        )

        # Calculate missing counts if we have percentage and total (e.g. USA: 18% of 45000)
        if data["percentage"] is not None and data["employee_count_total"] and not data["employee_count_covered"]:
             # Use round to avoid float precision issues
             data["employee_count_covered"] = round((data["percentage"] / 100) * data["employee_count_total"])

        # Determine Relationship Status
        if analysis.relationship_terms and analysis.relationship_quality_terms:
            # Find the quality term closest to the relationship term
            # For simplicity, we'll take the first quality term found if we have a relationship term
            # A more robust approach would be distance-based, but this covers the templates provided.
            
            quality_term = analysis.relationship_quality_terms[0].lower()
            
            # Check for local negation of the quality term (e.g. "not good")
            # We check if a negation term is within 3 words before the quality term
            is_quality_negated = False
            q_match = next((m for m in analysis._matches if m['type'] == MatchType.RELATIONSHIP_QUALITY), None)
            
            if q_match:
                q_start = q_match['span'][0]
                # Look for negation terms ending just before q_start
                for n_match in [m for m in analysis._matches if m['type'] in (MatchType.NEGATION, MatchType.NON_COVERAGE)]:
                    n_end = n_match['span'][1]
                    # Check distance (approx 20 chars covers "are not", "is not")
                    if 0 < (q_start - n_end) < 25:
                        is_quality_negated = True
                        break

            status = RelationshipStatus.UNKNOWN
            if quality_term in RELATIONSHIP_QUALITY_TERMS:
                status = RelationshipStatus.NEGATIVE if is_quality_negated else RelationshipStatus.POSITIVE
            elif quality_term in RELATIONSHIP_NEGATIVE_TERMS:
                status = RelationshipStatus.POSITIVE if is_quality_negated else RelationshipStatus.NEGATIVE
            
            if status != RelationshipStatus.UNKNOWN:
                data["relationship_status"] = status.value

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
        positives = [m for m in analysis._matches if m['type'] in (MatchType.UNION_TERM, MatchType.SPECIFIC_UNION, MatchType.UNION_NAME)]
        negatives = [m for m in analysis._matches if m['type'] in (MatchType.NON_UNION, MatchType.NEGATION, MatchType.NON_COVERAGE)]
        totals = [m for m in analysis._matches if m['type'] in (MatchType.WORKER_TERM,)]
        
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
            if ptype == 'not_covered':
                # Invert
                val = p['val']
                data['percentage'] = 100.0 - val
                data['percentage_raw_stated'] = val
                data['negated'] = True
                data['negation_type'] = NegationType.NOT_COVERED.value
                data['note'] = f"Inverted from {val}% not covered"
            elif ptype == 'covered':
                data['percentage'] = p['val']

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
            # If multiple totals found (e.g. Spain 920, NL 680), sum them?
            # Or if one is clearly larger, take it?
            # For now, sum them if they seem to be distinct parts (heuristic)
            # But usually we just want the max if it's a "Total" mention
            data['employee_count_total'] = sum(total_candidates)

        # Calculate missing values
        if data['employee_count_covered'] and data['employee_count_not_covered'] and not data['employee_count_total']:
            data['employee_count_total'] = data['employee_count_covered'] + data['employee_count_not_covered']
            
        if data['employee_count_total'] and data['employee_count_covered'] and not data['percentage']:
             pct = (data['employee_count_covered'] / data['employee_count_total']) * 100
             data['percentage'] = round(pct, 2)
             data['calculated_percentage'] = round(pct, 2)
             data['type'] = CoverageType.CALCULATED.value

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
    cleaner = MinimalTextCleaner()

    stress_test_text = """
Our labor relations landscape is highly complex given our truly global footprint. In the United States, approximately 18% of our 45,000 domestic employees are represented by various unions including the UAW, which covers 2,340 of our automotive manufacturing workers in Michigan, and the International Brotherhood of Teamsters, whose members represent 3,150 of our logistics workforce across our distribution centers. We have a cordial relationship with our unions. We also have non-union segments, particularly in our corporate headquarters where 8,500 of our 15,000 white-collar staff operate outside any collective bargaining framework. In Canada, our operations in Toronto and Vancouver include 1,200 employees, of which Unifor represents approximately 55%, or 660 workers. Elsewhere in North America, our Mexican manufacturing facilities in Monterrey and Guadalajara employ 5,600 workers, 80% of whom (4,480 workers) are affiliated with the Confederación de Trabajadores de México (CTM); however, we maintain a smaller non-union management tier of 1,120 employees in those locations.
Moving to Europe, our operations span multiple jurisdictions with vastly different labor frameworks. Germany, where we operate three major plants, employs 8,200 workers, with IG Metall representing approximately 72% (5,904 workers); the remaining 28% (2,296 workers) are management or non-union technical staff. In France, our Paris headquarters and regional offices employ 3,400 staff, of which the CFDT and CGT together represent approximately 40% (1,360 workers), while 2,040 remain unrepresented. The United Kingdom operations, centered in Birmingham and London, employ 4,100 workers; roughly one-third (1,367 workers) are members of Unite the Union, while the remaining two-thirds (2,733 workers) operate under non-union arrangements. We note that in our smaller European footprint—specifically our operations in Spain (Madrid facility: 920 employees) and Netherlands (Rotterdam: 680 employees)—union representation is minimal; we have no specific data on unionization rates in these locations. Sweden and Norway, combined, employ 2,100 workers, and given the national labor frameworks in these countries, we estimate that approximately 85% (1,785 workers) operate under collective agreements, though specific union membership is not separately tracked.
In Asia-Pacific, our operations are more fragmented. Japan, our largest Asian manufacturing hub, employs 12,000 workers, but union activity is concentrated in our automotive division where the Japanese Association of Metal and Allied Workers (JAM) represents approximately 30% (3,600 workers); the broader manufacturing base outside this agreement remains largely non-unionized (8,400 workers). China, despite rapid growth, presents challenges in labor organization; our facilities in Shanghai and Shenzhen employ 7,500 workers, but we have no formal unionization data and do not separately track union membership in these locations. We anticipate increased labor organizing in China in 2025. In Australia, our Sydney and Melbourne operations employ 2,800 workers, with the Australian Manufacturing Workers' Union (AMWU) representing approximately 45% (1,260 workers), while the remainder operate as non-union staff (1,540 workers). Singapore's operations are smaller—450 employees—and remain entirely non-unionized.
In Latin America outside Mexico, we maintain a limited footprint. Our Brazil operations in São Paulo and Rio de Janeiro employ 1,800 workers, of which approximately 50% (900 workers) are covered by collective bargaining agreements through various local unions, though we do not track individual union names in this region. Argentina, with 420 employees, has a smaller unionized portion at roughly 33% (139 workers). Our operations in Chile and Colombia are nascent; Chile employs 280 workers with no current union representation, while Colombia, with 350 employees, has informal union representation that we estimate at 20% (70 workers), though exact figures are unavailable.
In the Middle East and Africa, our presence is minimal. Our UAE operations in Dubai and Abu Dhabi employ 650 staff, all non-union. South Africa, our only significant African footprint with 980 employees in Johannesburg and Cape Town, has approximately 40% union representation (392 workers) through the National Union of Metalworkers of South Africa (NUMSA), though we note labor relations in this region remain volatile.
In aggregate, we estimate that approximately 33% to 37% of our global workforce of approximately 120,000 employees operates under some form of union representation or collective bargaining coverage, though precise global metrics are challenging given regional variations in data availability and labor law definitions. Certain regions—particularly the Nordics and Germany—have implicit union coverage through national frameworks that exceed explicit unionization percentages. We continue to monitor labor relations across all geographies and remain committed to constructive engagement with union partners where they are present.
"""

    print("Running Stress Test Analysis:\n")
    results = analyzer.analyze_paragraph(cleaner.clean(stress_test_text))
    print(json.dumps(results, indent=2))
