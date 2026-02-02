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
    RELATIONSHIP_NEGATIVE_TERMS, BOILERPLATE_REGEX
)

class SimpleCoverageAnalyzer:
    """
    Handles straightforward sentences where coverage is explicit and singular.
    Criteria:
    - Max 1 Percentage OR Max 1 Worker Count
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
    # 1. Explicit Geography (Highest Priority)
    explicit_matches = [m for m in analysis.geo_matches if m.source_type == GeoSource.EXPLICIT]
    if explicit_matches:
        countries = []
        regions = set()
        
        for m in explicit_matches:
            if m.country:
                countries.append({"name": m.country, "code": m.geo_code})
            if m.region:
                regions.add(m.region.value)
        
        # Resolve Region
        if len(regions) == 1:
            region_val = list(regions)[0]
        elif len(regions) > 1:
            region_val = Region.INTERNATIONAL.value
        else:
            region_val = Region.UNKNOWN.value

        return {
            "region": region_val,
            "countries": countries,
            "specificity": Specificity.EXPLICIT.value,
            "explicit_countries": [c["name"] for c in countries]
        }

    # 2. Inferred from Union Name (Medium Priority)
    union_matches = [m for m in analysis.geo_matches if m.source_type in (GeoSource.SPECIFIC_UNION, GeoSource.INFERRED_UNION)]
    if union_matches:
        # Use the first specific union found
        m = union_matches[0]
        return {
            "region": m.region.value if m.region else Region.UNKNOWN.value,
            "countries": [{"name": m.country, "code": m.geo_code}] if m.country else [],
            "specificity": Specificity.INFERRED_UNION.value,
            "union_name_indicator": m.text,
        }

    # 3. Inheritance (Lowest Priority)
    if last_context:
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
        "specificity": Specificity.IMPLICIT.value
    }


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

            # 2. Calculate Global Max (scan all text)
            all_sentences_flat = self.extractor.split_sentences(text)
            global_max = self._get_global_max(all_sentences_flat, reporting_year)

            # 3. Process Paragraphs
            results = []
            last_geo_context = None
            prev_paragraph_totals = {}
            all_region_totals = {}

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
                
                # Update all_region_totals with max found across all blocks
                for reg, count in local_totals.items():
                    if count > all_region_totals.get(reg, 0):
                        all_region_totals[reg] = count

                results.extend(block_results)
                # Update previous totals for the next iteration (Sliding window: only look back 1 paragraph)
                prev_paragraph_totals = local_totals

            summary = self.compute_weighted_coverage(results, global_max, all_region_totals)

        return {"items": results, "summary": summary}

    def _get_global_max(self, sentences: List[str], reporting_year: Optional[int] = None) -> float:
        """
        Scans all sentences to find the maximum worker count mentioned, 
        serving as a potential global denominator.
        """
        global_max_workers = 0.0
        for s in sentences:
            ans = self.extractor.analyze_sentence(s)

            # Check for historical context
            is_historical = False
            years_indicate_past = False
            if reporting_year and ans.years:
                if all(y < reporting_year for y in ans.years):
                    years_indicate_past = True

            if (years_indicate_past or ans.has_historical) and not ans.has_current:
                is_historical = True

            # Determine counts (Explicit Worker Counts or Fallback to Numbers)
            counts = ans.worker_counts or [n for n in ans.numbers if n > 10]

            if counts:
                local_max = max(counts)
                if not is_historical and local_max > global_max_workers:
                    global_max_workers = local_max
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
                if geo_context["specificity"] in (Specificity.EXPLICIT.value, Specificity.INHERITED.value):
                    region_key = geo_context["region"]
                    if current_max > local_totals.get(region_key, 0):
                        local_totals[region_key] = current_max
                        effective_totals[region_key] = current_max

            # 6. Determine Relevant Total for Calculation
            relevant_total = None
            current_region = geo_context["region"]
            if current_region in effective_totals:
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
        
        return data

    def _analyze_complex_coverage(self, analysis: SentenceAnalysis, total_count: Optional[float]) -> Dict[str, Any]:
        """
        Handles complex scenarios: mixed coverage, ratios, inferred totals, etc.
        (Placeholder for the complex logic to be re-added/refined)
        """
        data = {
            "type": CoverageType.QUALITATIVE.value,
            "note": "Complex Analysis (Placeholder)"
        }
        # TODO: Re-implement the complex logic (ratios, mixed resolution, proximity checks) here
        return data

    def _resolve_mixed_coverage(self, analysis: SentenceAnalysis, data: Dict[str, Any]):
        """
        Resolves mixed coverage scenarios (e.g. "500 union, 200 non-union") by
        mapping counts/percentages to the nearest positive/negative keywords.
        Updates 'data' in-place.
        """
        pass

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

    def compute_weighted_coverage(self, results: List[Dict[str, Any]], global_workforce: float = 0.0, region_totals: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Computes a weighted average of union coverage percentages from analysis results.
        Then selects the BEST TEXT CANDIDATE that matches the calculation.
        """
        return {}