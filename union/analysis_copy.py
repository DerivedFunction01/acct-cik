from typing import List, Dict, Any, Optional, Tuple
import statistics

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

# --- Regex Definitions ---
CONDITIONAL_REGEX = build_regex([
    r"if", r"could", r"may", r"might", r"potential", r"possible", r"can"
])

CURRENT_REGEX = build_regex([
    r"current(?:ly)?", r"present", r"now", r"today",
    r"this\s+(?:fiscal|reporting)\s+(?:year|period)"
])

HISTORICAL_REGEX = build_regex([
    r"historical(?:ly)?", r"previously", r"prior\s+to",
    r"(?:last|prior|past|previous|preceding)\s+(?:fiscal\s+|reporting\s+)?(?:years?|periods?)"
])

FUTURE_REGEX = build_regex([
    r"in\s+the\s+future",
    r"(?:future|next|upcoming)\s+(?:fiscal\s+|reporting\s+)?(?:years?|periods?)"
])

NEGATION_REGEX = build_regex([
    r"no", r"not", r"nor", r"without", r"neither", r"none", r"never"
])

REMAIN_REGEX = build_regex([
    r"remaining", r"rest", r"balance", r"other"
])

RANGE_REGEX = build_regex([
    r"to", r"-", r"through", r"and"
])

OF_REGEX = build_regex([
    r"(?:out\s+)?of"
])

QUALITATIVE_MULTIPLIERS = [
    (build_regex([r"almost", r"nearly", r"virtually"]), 0.95),
    (build_regex([r"(?:slightly|just)\s+(?:under|below)", r"less\s+than"]), 0.90),
    (build_regex([r"materially\s+less\s+than"]), 0.80),
    (build_regex([r"(?:slightly|just)\s+(?:over|above)", r"more\s+than"]), 1.10),
]

QUANT_SUFFIX = [r"portion", r"number", r"amount", r"share"]
COPULA = [r"is", r"are", r"was", r"were"]


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
        return {}

    def _check_local_negation(self, analysis: SentenceAnalysis, match_span: Tuple[int, int], text: str) -> bool:
        """
        Check if a negation term appears within ~5 words before the matched pattern.
        """
        return False

    def analyze_paragraph(self, text: str, item_type: str = "item1", reporting_year: Optional[int] = None) -> Dict[str, Any]:
        """
        Process a paragraph of text, splitting it into sentences and 
        extracting details based on item_type (item1 or item1a).
        """
        return {"items": [], "summary": {}}

    def _get_global_max(self, sentences: List[str], reporting_year: Optional[int] = None) -> float:
        """
        Scans all sentences to find the maximum worker count mentioned, 
        serving as a potential global denominator.
        """
        return 0.0

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
        return []

    def compute_weighted_coverage(self, results: List[Dict[str, Any]], global_workforce: float = 0.0, region_totals: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Computes a weighted average of union coverage percentages from analysis results.
        Then selects the BEST TEXT CANDIDATE that matches the calculation.
        """
        return {}