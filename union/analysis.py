import re
from typing import List, Dict, Any, Optional, Tuple

from extraction import UnionExtractor, SentenceAnalysis, MatchType
from defs.region_regex import REGION_CODES, Region, INT_LANGUAGE_MAP, GeoSource
from defs.output_enums import (
    Specificity, CoverageType, PercentageQualifier,
    NegationType, TemporalScope, RiskType, RelationshipStatus
)

from defs.union_regex import (
    NON_COVERAGE_REGEX, RELATIONSHIP_NEUTRAL_TERMS, RELATIONSHIP_QUALITY_TERMS, 
    RELATIONSHIP_NEGATIVE_TERMS, BOILERPLATE_REGEX
)
from defs.regex_lib import build_regex

CONDITIONAL_REGEX = build_regex([
    r"if",
    r"could",
    r"may",
    r"might",
    r"potential",
    r"possible",
    r"can"
])

CURRENT_REGEX = build_regex([
    r"current(?:ly)?",
    r"present",
    r"now",
    r"today",
    r"this\s+(?:fiscal|reporting)\s+(?:year|period)"
])

HISTORICAL_REGEX = build_regex([
    r"historical(?:ly)?",
    r"previously",
    r"prior\s+to",
    r"(?:last|prior|past|previous)\s+(?:fiscal\s+|reporting\s+)?(?:years?|periods?)"
])

FUTURE_REGEX = build_regex([
    r"in\s+the\s+future",
    r"(?:future|next|upcoming)\s+(?:fiscal\s+|reporting\s+)?(?:years?|periods?)"
])

NEGATION_REGEX = build_regex([
    r"no",
    r"without",
    r"neither",
    r"none",
    r"never"
])

REMAIN_REGEX = build_regex([
    r"remaining",
    r"rest",
    r"balance",
    r"other"
])

RANGE_REGEX = build_regex([
    r"to",
    r"-",
    r"through",
    r"and"
])


class UnionAnalyzer:
    def __init__(self):
        self.extractor = UnionExtractor()

    def _get_external_worker_count(self, region: str, countries: List[Dict[str, str]]) -> Optional[float]:
        """
        Placeholder: Connect to external DB to get worker counts for a region/country.
        Currently returns None.
        """
        return None

    def _create_risk_item(self, sentence: str, analysis: SentenceAnalysis, is_historical: bool = False) -> Dict[str, Any]:
        is_conditional = bool(CONDITIONAL_REGEX.search(sentence))
        is_future = bool(FUTURE_REGEX.search(sentence))
        temporal_scope = TemporalScope.CURRENT.value
        if is_historical:
            temporal_scope = TemporalScope.HISTORICAL.value
        elif is_future:
            temporal_scope = TemporalScope.FUTURE.value
        elif is_conditional:
            temporal_scope = TemporalScope.CONDITIONAL.value

        return {
            "type": RiskType.UNION_RISK.value if analysis.union_terms else RiskType.LABOR_RISK.value,
            "sentence": sentence,
            "labor_keywords": analysis.union_terms,
            "risk_keywords": analysis.risk_terms,
            "third_party": analysis.supplier_terms,
            "specific_to_unions": bool(analysis.union_terms),
            "union_mention": analysis.union_terms[0] if analysis.union_terms else None,
            "temporal_scope": temporal_scope,
            "conditional": is_conditional,
            "note": None
        }

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
            summary = self.compute_weighted_coverage(results)
        else:
            # 1. Split into paragraphs to handle local context
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            if not paragraphs:
                paragraphs = [text]

            # 2. Calculate Global Max (scan all text)
            all_sentences_flat = self.extractor.split_sentences(text)
            global_max = self._get_global_max(all_sentences_flat)

            # 3. Process Paragraphs
            results = []
            last_geo_context = None
            prev_paragraph_totals = {}

            for p_text in paragraphs:
                p_sentences = self.extractor.split_sentences(p_text)
                
                # Analyze block with context from previous paragraph
                block_results, local_totals, last_geo_context = self._analyze_block(
                    p_sentences, 
                    reporting_year=reporting_year, 
                    global_max_workers=global_max, 
                    initial_geo_context=last_geo_context,
                    previous_totals=prev_paragraph_totals
                )
                
                results.extend(block_results)
                # Update previous totals for the next iteration (Sliding window: only look back 1 paragraph)
                prev_paragraph_totals = local_totals

            summary = self.compute_weighted_coverage(results, global_max)

        return {"items": results, "summary": summary}

    def _get_global_max(self, sentences: List[str]) -> float:
        global_max_workers = 0.0
        for s in sentences:
            ans = self.extractor.analyze_sentence(s)
            if ans.worker_counts:
                global_max_workers = max(global_max_workers, max(ans.worker_counts))
        return global_max_workers

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

            is_historical = False
            # Historical Check: If reporting_year is provided, skip purely historical sentences
            if reporting_year and analysis.years:
                if all(y < reporting_year for y in analysis.years) or HISTORICAL_REGEX.search(sent):
                    # Check for explicit current indicators to override exclusion
                    if not CURRENT_REGEX.search(sent):
                        is_historical = True

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
            
            # Determine effective worker counts (explicit or inferred from raw numbers)
            current_counts = analysis.worker_counts
            if not current_counts and analysis.numbers:
                # Fallback: Use raw numbers if they look like worker counts
                # Years are protected in text, so we assume remaining large numbers are counts
                potential_counts = []
                for n in analysis.numbers:
                    if n > 10:
                        potential_counts.append(n)
                if potential_counts:
                    current_counts = potential_counts
            # Update Region Totals if this sentence has a worker count
            # We assume if a sentence has a count and a specific region, that count applies to that region
            if current_counts:
                current_max = max(current_counts)
                
                # If context is explicit, map this count to the region/countries
                if geo_context["specificity"] in (Specificity.EXPLICIT.value, Specificity.EXPLICIT_INFERRED.value):
                    region_key = geo_context["region"]
                    local_totals[region_key] = current_max
                    effective_totals[region_key] = current_max
                    
                    for c in geo_context.get("countries", []):
                        local_totals[c["code"]] = current_max
                        effective_totals[c["code"]] = current_max

            # Determine best available total for calculation
            # Priority: 
            # 1. Region-specific total (if we are in that region)
            # 2. Global total (if we are in Global/Unknown/International region)
            # 3. Sequential fallback
            relevant_total = None
            current_region = geo_context["region"]
            
            if current_region in effective_totals:
                relevant_total = effective_totals[current_region]
            
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
            coverage_data = self._determine_coverage_data(analysis, relevant_total, reporting_year, is_historical=is_historical)

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
                # It is a risk statement embedded in Item 1 (common in older filings)
                results.append(self._create_risk_item(sent, analysis, is_historical=is_historical))
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
                    "lookup_totals": effective_totals.copy(), # Snapshot for summary calculation
                    "last_seen_count": last_employee_count,
                    "sentence_index": idx
                }
                results.append(item)

        # Post-processing: Merge continuation items (Fix for Germany split)
        # If an item inherits context and looks like a breakdown of the previous item, merge them.
        merged_results = []
        skip_indices = set()
        
        for i in range(len(results)):
            # Skip if processed or if it's a Risk Item (no geographic_context)
            if i in skip_indices or "geographic_context" not in results[i]:
                continue
                
            current = results[i]
            
            # Check if next item is a candidate for merging
            if i + 1 < len(results):
                next_item = results[i+1]
                
                # Skip merging if next item is a Risk Item
                if "geographic_context" not in next_item:
                    continue
                
                # Criteria: Next item inherits from Current, and Current has data
                if (next_item["geographic_context"]["specificity"] == Specificity.INHERITED.value and
                    next_item["geographic_context"].get("inherited_from_sentence_index") == current.get("sentence_index")):
                    
                    # Merge Data
                    c_data = current["coverage_data"]
                    n_data = next_item["coverage_data"]
                    
                    # 1. Fill in missing Percentage
                    if c_data["percentage"] is None and n_data["percentage"] is not None:
                        c_data["percentage"] = n_data["percentage"]
                        c_data["negated"] = n_data["negated"]
                        c_data["negation_type"] = n_data["negation_type"]
                        c_data["type"] = n_data["type"]
                        c_data["note"] = (c_data["note"] or "") + " | " + (n_data["note"] or "")

                    # 2. Fill in missing Counts
                    if not c_data["employee_count_covered"] and n_data["employee_count_covered"]:
                        c_data["employee_count_covered"] = n_data["employee_count_covered"]
                    if not c_data["employee_count_not_covered"] and n_data["employee_count_not_covered"]:
                        c_data["employee_count_not_covered"] = n_data["employee_count_not_covered"]
                    
                    skip_indices.add(i+1)
            
            merged_results.append(current)

        return merged_results, local_totals, last_geo_context

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
            regions_list = []
            found_regions_map = {} # code -> (region_dict, region_enum)
            seen_codes = set()
            regions = set()

            unusual_combo = False
            conflict_notes = []

            # Codes that identify a Region entity rather than a Country
            

            for m in explicit_matches:
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
                for r_code, (r_obj, r_enum) in found_regions_map.items():
                    # Map if in same broad region
                    if c_enum == r_enum:
                        r_obj["countries"].append({"name": c["name"], "code": c["code"]})
                    # Special handling for Domestic -> US
                    elif r_code == "DOMESTIC" and c["code"] == "US":
                        r_obj["countries"].append({"name": c["name"], "code": c["code"]})
                
                # Remove temporary field
                c.pop("region_enum", None)

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
            # Remove fields specific to the source sentence
            ctx.pop("union_names_mentioned", None)
            ctx.pop("explicit_countries", None)
            return ctx

        # 4. Fallback
        return {"region": Region.UNKNOWN.value,  "countries": [], "specificity": Specificity.IMPLICIT.value}

    def _determine_coverage_data(
        self, analysis: SentenceAnalysis, inherited_total_count: Optional[float] = None, reporting_year: Optional[int] = None, is_historical: bool = False
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
                # Check for Zero Coverage indicators (Absolute negation)
                if NEGATION_REGEX.search(term):
                    negation_type = NegationType.ZERO_COVERAGE.value
                    # Zero coverage takes precedence (e.g. "no union employees" -> 0%)
                    break

                # Check for Not Covered indicators (Status negation)
                if NON_COVERAGE_REGEX.search(term):
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
                if RANGE_REGEX.search( text_between):
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

        # Handle explicit "0" count in positive context -> 0%
        # Only if it's the only number to avoid ambiguity (e.g. "0 union, 500 total")
        elif (
            not data["percentage"]
            and analysis.union_terms
            and len(analysis.numbers) == 1
            and (0 in analysis.numbers or 0.0 in analysis.numbers)
        ):
             data["percentage"] = 0.0
             data["type"] = CoverageType.EXPLICIT_PERCENT.value
             data["employee_count_covered"] = 0.0 if not is_negated else 100.0
             data["note"] = "Inferred 0% from explicit '0' count (100% if negated)"

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
            if quality_term in RELATIONSHIP_NEUTRAL_TERMS:
                status = RelationshipStatus.NEGATIVE if is_quality_negated else RelationshipStatus.NEUTRAL 
            elif quality_term in RELATIONSHIP_QUALITY_TERMS:
                status = RelationshipStatus.NEGATIVE if is_quality_negated else RelationshipStatus.POSITIVE
            elif quality_term in RELATIONSHIP_NEGATIVE_TERMS:
                status = RelationshipStatus.POSITIVE if is_quality_negated else RelationshipStatus.NEGATIVE
            
            if status != RelationshipStatus.UNKNOWN:
                data["relationship_status"] = status.value

        # Determine Temporal Scope based on reporting year
        if is_historical:
            data["temporal_scope"] = TemporalScope.HISTORICAL.value
        elif reporting_year and analysis.years:
            future_years = [y for y in analysis.years if y > reporting_year]
            if future_years:
                data["temporal_scope"] = TemporalScope.FUTURE.value
                data["expected_date"] = str(min(future_years))
        
        if data["temporal_scope"] == TemporalScope.CURRENT.value and FUTURE_REGEX.search(analysis.text):
            data["temporal_scope"] = TemporalScope.FUTURE.value

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

    def _analyze_item1a(self, sentences: List[str], reporting_year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Analyzes sentences for Item 1A (Risk Factors).
        """
        results = []
        for sent in sentences:
            analysis = self.extractor.analyze_sentence(sent)

            is_historical = False
            # Historical Check for Risks
            if reporting_year and analysis.years:
                if all(y < reporting_year for y in analysis.years) or HISTORICAL_REGEX.search(sent):
                    if not CURRENT_REGEX.search(sent):
                        is_historical = True

            # Item 1A logic: Look for risk terms
            if analysis.risk_terms:
                results.append(self._create_risk_item(sent, analysis, is_historical=is_historical))
        return results

    def compute_weighted_coverage(self, results: List[Dict[str, Any]], global_workforce: float = 0.0, region_totals: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Computes a weighted average of union coverage percentages from the analysis results.
        Weights are based on the total employee count associated with each percentage.
        """
        if region_totals is None:
            region_totals = {}

        total_weighted_pct = 0.0
        total_employees = 0.0
        calculation_log = []

        for item in results:
            log_entry = {
                "sentence_snippet": item.get("sentence", "")[:60] + "...",
                "status": "skipped",
                "percentage": None,
                "weight_used": None,
                "weight_source": None,
                "reason": None
            }
            data = item.get("coverage_data", {})
            
            # Filter out historical data
            if data.get("temporal_scope") != TemporalScope.CURRENT.value:
                log_entry["reason"] = f"Temporal scope: {data.get('temporal_scope')}"
                calculation_log.append(log_entry)
                continue

            pct = data.get("percentage")
            covered_count = data.get("employee_count_covered")

            # Handle implicit 0% (e.g. "0 employees covered") even if pct is None
            if pct is None:
                if covered_count == 0:
                    pct = 0.0
                else:
                    log_entry["reason"] = "No percentage or zero-covered count found"
                    calculation_log.append(log_entry)
                    continue
            
            log_entry["percentage"] = pct

            # Determine weight (Total Employees)
            weight = data.get("employee_count_total")
            weight_source = "Explicit in item"
            
            # Get context-aware totals if available
            item_totals = item.get("lookup_totals", region_totals)

            # If total is missing, try to derive it from covered/not_covered
            if not weight:
                not_covered = data.get("employee_count_not_covered")

                if covered_count is not None and not_covered is not None:
                    weight = covered_count + not_covered
                    weight_source = "Derived (Covered + Not Covered)"
                elif covered_count is not None and pct > 0:
                    weight = covered_count / (pct / 100.0)
                    weight_source = "Derived (Covered / Pct)"
                elif not_covered is not None and pct < 100:
                    weight = not_covered / (1.0 - (pct / 100.0))
                    weight_source = "Derived (Not Covered / Inverse Pct)"

                # If still no weight, try to look it up from extracted raw numbers
                if not weight:
                    geo = item.get("geographic_context", {})
                    region = geo.get("region")
                    
                    # 1. Try specific region lookup
                    if region and region in item_totals:
                        weight = item_totals[region]
                        weight_source = f"Lookup Region: {region}"
                    
                    # 2. Try country lookup
                    elif geo.get("countries"):
                        for c in geo["countries"]:
                            if c["code"] in item_totals:
                                weight = item_totals[c["code"]]
                                weight_source = f"Lookup Country: {c['code']}"
                                break
                    
                    # 3. Fallback to global workforce if item is global/international
                    if not weight and global_workforce > 0:
                        if region in (Region.INTERNATIONAL.value, Region.UNKNOWN.value):
                            weight = global_workforce
                            weight_source = "Global Fallback"
            
            # 4. Fallback to last seen count in block (for cases where region lookup failed but number was in previous sentence)
            if not weight and item.get("last_seen_count"):
                weight = item.get("last_seen_count")
                weight_source = "Fallback: Last Seen Count"

            if weight and weight > 0:
                total_weighted_pct += (pct * weight)
                total_employees += weight
                log_entry["status"] = "included"
                log_entry["weight_used"] = weight
                log_entry["weight_source"] = weight_source
            else:
                log_entry["reason"] = "No valid weight (total employees) found"
            
            calculation_log.append(log_entry)

        weighted_avg = 0.0
        if total_employees > 0:
            weighted_avg = total_weighted_pct / total_employees

        return {
            "weighted_average_percentage": round(weighted_avg, 2),
            "total_employees_analyzed": round(total_employees, 2),
            "calculation_log": calculation_log
        }
