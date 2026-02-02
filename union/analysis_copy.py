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

class UnionAnalyzer:
    def __init__(self):
        self.extractor = UnionExtractor()

    def _get_external_worker_count(self, region: str, countries: List[Dict[str, str]]) -> Optional[float]:
        """
        Placeholder: Connect to external DB to get worker counts for a region/country.
        """
        return None

    def _create_risk_item(self, sentence: str, analysis: SentenceAnalysis, is_historical: bool = False) -> Dict[str, Any]:
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

    def _check_local_negation(self, analysis: SentenceAnalysis, match_span: Tuple[int, int], text: str) -> bool:
        """
        Check if a negation term appears within ~5 words before the matched pattern.
        """
        if not match_span:
            return False

        start_idx = match_span[0]
        # Look back window (approx 5 words ~ 40 chars)
        window = text[max(0, start_idx - 40):start_idx]
        
        return bool(NEGATION_REGEX.search(window))

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
        return [], {}, None

    def _determine_geo_context(
        self, analysis: SentenceAnalysis, last_context, current_idx, last_idx
    ) -> Dict[str, Any]:
        """
        Resolves geographic context based on explicit matches, union names,
        language inference, or inheritance.
        """
        return {"region": Region.UNKNOWN.value,  "countries": [], "specificity": Specificity.IMPLICIT.value}

    def _apply_qualitative_multipliers(self, raw_pct: float, span: Tuple[int, int], text: str, apply: bool = False) -> Tuple[float, Optional[str]]:
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

    def _determine_coverage_data(
        self, analysis: SentenceAnalysis, inherited_total_count: Optional[float] = None, reporting_year: Optional[int] = None, is_historical: bool = False
    ) -> Dict[str, Any]:
        """
        Extracts percentage, negation, and count data.
        """
        return {}

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
                result = self._create_risk_item(sent, analysis, is_historical=is_historical)
                if result:
                    results.append(result)
        return results

    def compute_weighted_coverage(self, results: List[Dict[str, Any]], global_workforce: float = 0.0, region_totals: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Computes a weighted average of union coverage percentages from analysis results.
        Then selects the BEST TEXT CANDIDATE that matches the calculation.
        """
        return {}