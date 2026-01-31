import re
from typing import List, Dict, Any

from union.extraction import UnionExtractor, SentenceAnalysis
from defs.region_regex import Region, INT_LANGUAGE_MAP, GeoSource
from defs.output_enums import (
    Specificity, CoverageType, PercentageQualifier, 
    NegationType, TemporalScope, RiskType
)


class UnionAnalyzer:
    def __init__(self):
        self.extractor = UnionExtractor()

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

        # Context inheritance state

        self.extractor = UnionExtractor()

        sentences = self.extractor.split_sentences(sentences)

        # Context inheritance state
        last_geo_context = None
        last_geo_sentence_idx = -1

        for idx, sent in enumerate(sentences):
            analysis = self.extractor.analyze_sentence(sent)

            # Skip if no relevant info (no union terms and no explicit coverage data)
            # We allow sentences without union terms IF they have coverage data AND we have inherited context
            has_coverage = bool(analysis.percentages or analysis.negation_terms)
            if (
                not analysis.union_terms
                and not analysis.geo_matches
                and not has_coverage
            ):
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

            # 2. Determine Coverage Data
            coverage_data = self._determine_coverage_data(analysis)

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
                "MIXED"
                if len(regions) > 1
                else (list(regions)[0].value if regions else "UNKNOWN")
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

    def _determine_coverage_data(self, analysis: SentenceAnalysis) -> Dict[str, Any]:
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
        if analysis.percentages:
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
        elif is_negated and negation_type == NegationType.ZERO_COVERAGE.value:
            data["percentage"] = 0.0
            data["type"] = CoverageType.EXPLICIT_PERCENT.value  # Treated as explicit 0
            data["negated"] = True
            data["negation_type"] = NegationType.ZERO_COVERAGE.value
            data["employee_count_covered"] = 0

        # Handle "Non-union" -> 0% (if no other numbers)
        elif is_negated and negation_type == NegationType.NOT_COVERED.value and not analysis.percentages:
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
        if analysis.numbers:
            # Store raw numbers for potential downstream analysis (e.g. Compustat merging)
            data["extracted_numbers"] = analysis.numbers

        return data

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
