# %%
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from defs.regex_lib import SENTENCE_SPLIT_PATTERN, build_alternation, build_regex, build_compound, to_build_alternation
from defs.union_regex import (
    UNION_REGEX, RISK_REGEX, DYNAMIC_UNION_REGEX, WORKER_TERMS, 
    NON_COVERAGE_REGEX, NON_UNION_REGEX, RELATIONSHIP_REGEX, RELATIONSHIP_QUALITY_REGEX
    , SUPPLIER_REGEX, COVERAGE_REGEX
)
from defs.region_regex import Region, RegionMatcher, GeoSource

# Regex for basic entities
PERCENT_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
NUMBER_REGEX = re.compile(r"\b\d+(?:\.\d+)?\b")
YEAR_TOKEN_REGEX = re.compile(r"<(\d{4})>")
RATIO_REGEX = re.compile(r"\b(\d+(?:\.\d+)?)\s+(?:[\w-]+\s+){0,5}(?:(?:out\s+)?of)\s+(?:[\w-]+\s+){0,5}(\d+(?:\.\d+)?)\b", re.IGNORECASE)

# --- Temporal Regexes ---
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

TOTAL_MODIFIER_REGEX = build_regex([
    r"total", r"global", r"worldwide", r"aggregate", r"consolidated", 
    r"entire", r"overall", r"combined", r"full", r"whole"
])

QUALITATIVE_MULTIPLIERS = [
    (build_regex([r"almost", r"nearly", r"virtually"]), 0.95),
    (build_regex([r"(?:slightly|just)\s+(?:under|below)", r"less\s+than"]), 0.90),
    (build_regex([r"materially\s+less\s+than"]), 0.80),
    (build_regex([r"(?:slightly|just)\s+(?:over|above)", r"more\s+than"]), 1.10),
]

# Worker Count Pattern: Number + (optional gap) + Worker Term
worker_term_pattern = build_alternation(WORKER_TERMS)
WORKER_COUNT_REGEX = build_regex(
    [
        rf"employ(?:ed|s)?\s+(?:[\w-]+\s+){{0,3}}(\d+(?:\.\d+)?)",
        rf"(\d+(?:\.\d+)?)\s+(?:[\w-]+\s+){{0,3}}{worker_term_pattern}",
        rf"{worker_term_pattern}\s+(?:[\w-]+\s+){{0,3}}(\d+(?:\.\d+)?)",
    ]
)
WORKER_TERM_REGEX = re.compile(rf"\b{worker_term_pattern}\b", re.IGNORECASE)

class MatchType(Enum):
    PERCENT = "PERCENT"
    RATIO = "RATIO"
    YEAR = "YEAR"
    WORKER_COUNT = "WORKER_COUNT"
    WORKER_TERM = "WORKER_TERM"
    SPECIFIC_UNION = "SPECIFIC_UNION"
    UNION_NAME = "UNION_NAME"
    NON_UNION = "NON_UNION"
    NON_COVERAGE = "NON_COVERAGE"
    RISK_TERM = "RISK_TERM"
    UNION_TERM = "UNION_TERM"
    GEO = "GEO"
    NEGATION = "NEGATION"
    NUMBER = "NUMBER"
    RELATIONSHIP_TERM = "RELATIONSHIP_TERM"
    RELATIONSHIP_QUALITY = "RELATIONSHIP_QUALITY"
    SUPPLIER_TERM = "SUPPLIER_TERM"
    COVERAGE_TERM = "COVERAGE_TERM"
    QUALITATIVE_TERM = "QUALITATIVE_TERM"
    TOTAL_MODIFIER = "TOTAL_MODIFIER"

@dataclass
class GeoMatch:
    text: str
    region: Region
    country: Optional[str] = None
    city: Optional[str] = None
    geo_code: Optional[str] = None
    source_type: GeoSource = GeoSource.EXPLICIT

@dataclass
class SentenceAnalysis:
    text: str
    percentages: List[float] = field(default_factory=list)
    ratios: List[Tuple[float, float]] = field(default_factory=list)
    worker_counts: List[float] = field(default_factory=list)
    worker_terms: List[str] = field(default_factory=list)
    numbers: List[float] = field(default_factory=list)
    years: List[int] = field(default_factory=list)
    union_terms: List[str] = field(default_factory=list)
    risk_terms: List[str] = field(default_factory=list)
    negation_terms: List[str] = field(default_factory=list)
    relationship_terms: List[str] = field(default_factory=list)
    relationship_quality_terms: List[str] = field(default_factory=list)
    supplier_terms: List[str] = field(default_factory=list)
    coverage_terms: List[str] = field(default_factory=list)
    qualitative_terms: List[str] = field(default_factory=list)
    total_modifiers: List[str] = field(default_factory=list)
    geo_matches: List[GeoMatch] = field(default_factory=list)
    
    # Temporal / Conditional flags
    has_conditional: bool = False
    has_current: bool = False
    has_historical: bool = False
    has_future: bool = False

    # Raw matches for debugging or precise location
    _matches: List[Dict[str, Any]] = field(default_factory=list)
# %%
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from defs.regex_lib import build_compound, build_regex, to_build_alternation


@dataclass
class QualitativeTerm:
    """Represents a qualitative quantity term with its positive and negated percentages."""

    # Core term components
    core_terms: List[str]  # e.g., ["majority", "bulk"]

    # Percentage values
    positive_pct: float  # When used positively: "majority" = 51%
    negated_pct: Optional[float]  # When negated: "not majority" = 10%

    # Optional modifiers
    prefix_terms: Optional[List[str]] = None  # e.g., ["vast", "substantial"]
    suffix_terms: Optional[List[str]] = None  # e.g., ["portion", "share"]

    # Metadata
    is_absolute: bool = (
        False  # True for terms like "not insignificant" that have fixed meaning
    )
    requires_suffix: bool = (
        False  # True if suffix is mandatory (e.g., "portion" needed)
    )

    def build_pattern(self) -> str:
        """Build regex pattern using build_compound."""
        if self.prefix_terms and self.suffix_terms:
            return build_compound(self.prefix_terms, self.core_terms, self.suffix_terms)
        elif self.prefix_terms:
            return build_compound(self.prefix_terms, self.core_terms)
        elif self.suffix_terms:
            return build_compound(self.core_terms, self.suffix_terms)
        else:
            # Just core terms with optional word boundary
            return to_build_alternation(self.core_terms)

    def get_percentage(self, is_negated: bool = False) -> Optional[float]:
        """Get the appropriate percentage based on negation."""
        return self.negated_pct if is_negated else self.positive_pct


QUALITATIVE_TERMS = [
    # ===== 75% TIER (Vast Majority) =====
    QualitativeTerm(
        core_terms=["majority", "bulk"],
        prefix_terms=["vast", "substantial", "overwhelming"],
        positive_pct=75.0,
        negated_pct=None,  # "not vast majority" could be 51%, 30%, or 10%
        requires_suffix=False,
    ),
    # ===== 65% TIER (Predominant) =====
    QualitativeTerm(
        core_terms=["portion", "share"],
        prefix_terms=["predominant", "vast", "substantial", "overwhelming"],
        positive_pct=65.0,
        negated_pct=None,  # Downgrade is unclear
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["majority", "bulk"],
        prefix_terms=["considerable", "significant"],
        positive_pct=65.0,
        negated_pct=None,  # Could be modest, small, or minor
        requires_suffix=False,
    ),
    # ===== 60% TIER (Bulk) =====
    QualitativeTerm(
        core_terms=["bulk"],
        suffix_terms=["of"],
        positive_pct=60.0,
        negated_pct=None,  # Ambiguous downgrade
        requires_suffix=True,
    ),
    # ===== 51% TIER (Simple Majority) =====
    QualitativeTerm(
        core_terms=["majority"],
        positive_pct=51.0,
        negated_pct=10.0,  # ✓ CLEAR: "not majority" = "minority" (~10%)
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["most"],
        suffix_terms=["of"],
        positive_pct=51.0,
        negated_pct=None,  # "not most of" is vague
        requires_suffix=True,
    ),
    # ===== 40% TIER (Major/Predominant Minority) =====
    QualitativeTerm(
        core_terms=["portion", "share"],
        prefix_terms=["major"],
        positive_pct=40.0,
        negated_pct=None,  # "not major" could be modest, small, or minor
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["minority"],
        prefix_terms=[
            "predominant",
            "vast",
            "substantial",
            "overwhelming",
            "considerable",
        ],
        positive_pct=40.0,
        negated_pct=None,  # Downgrade unclear
        requires_suffix=False,
    ),
    # ===== 30% TIER (Considerable) =====
    QualitativeTerm(
        core_terms=["portion", "number", "amount", "share"],
        prefix_terms=["considerable"],
        positive_pct=30.0,
        negated_pct=None,  # Could be modest or small
        requires_suffix=False,
    ),
    # ===== 25% TIER (Significant/Substantial) =====
    QualitativeTerm(
        core_terms=["portion"],
        prefix_terms=["significant", "substantial", "large", "meaningful"],
        positive_pct=25.0,
        negated_pct=None,  # Could be modest, small, or insignificant
        requires_suffix=False,
    ),
    # "is/are/was/were significant/material/etc."
    QualitativeTerm(
        core_terms=[
            "significant",
            "material",
            "substantial",
            "meaningful",
            "large",
            "considerable",
        ],
        prefix_terms=["is", "are", "was", "were"],
        positive_pct=25.0,
        negated_pct=1.0,  # ✓ CLEARER: "is not significant" = "is insignificant" (~1%)
        requires_suffix=False,
    ),
    # ===== DOUBLE NEGATIVES (Absolute meaning) =====
    # "not insignificant" = significant (25%)
    QualitativeTerm(
        core_terms=[
            "minor",
            "insignificant",
            "immaterial",
            "negligible",
            "trivial",
            "small",
            "limited",
            "nominal",
        ],
        prefix_terms=["is", "are", "was", "were"],
        suffix_terms=["not"],
        positive_pct=25.0,
        negated_pct=25.0,  # ✓ ABSOLUTE: meaning doesn't flip
        is_absolute=True,
        requires_suffix=False,
    ),
    # ===== 20% TIER (Good) =====
    QualitativeTerm(
        core_terms=["portion", "share"],
        prefix_terms=["good"],
        positive_pct=20.0,
        negated_pct=None,  # "not good" is vague
        requires_suffix=False,
    ),
    # ===== 15% TIER (Fair/Modest) =====
    QualitativeTerm(
        core_terms=["portion", "share"],
        prefix_terms=["fair", "modest"],
        positive_pct=15.0,
        negated_pct=None,  # Could be large or small
        requires_suffix=False,
    ),
    # ===== 10% TIER (Minority/Small) =====
    QualitativeTerm(
        core_terms=["minority"],
        positive_pct=10.0,
        negated_pct=51.0,  # ✓ CLEAR: "not minority" = "majority" (~51%)
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["portion"],
        prefix_terms=["small", "minor", "little", "fractional"],
        positive_pct=10.0,
        negated_pct=None,  # "not small" could be modest, significant, or large
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["minor", "small"],
        prefix_terms=["is", "are", "was", "were"],
        positive_pct=10.0,
        negated_pct=25.0,  # ✓ REASONABLE: "is not small/minor" → "is significant" (~25%)
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["fraction"],
        suffix_terms=["of"],
        positive_pct=10.0,
        negated_pct=None,  # "not fraction of" is vague
        requires_suffix=True,
    ),
    # ===== 5% TIER (Handful/Few/Nominal/Limited) =====
    QualitativeTerm(
        core_terms=["handful", "few"],
        suffix_terms=["of"],
        positive_pct=5.0,
        negated_pct=None,  # "not handful" could be many things
        requires_suffix=True,
    ),
    QualitativeTerm(
        core_terms=["portion", "share", "number"],
        prefix_terms=["nominal", "limited"],
        positive_pct=5.0,
        negated_pct=None,  # Could be modest or significant
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["nominal", "limited"],
        prefix_terms=["is", "are", "was", "were"],
        positive_pct=5.0,
        negated_pct=25.0,  # ✓ REASONABLE: "is not limited/nominal" → "is significant" (~25%)
        requires_suffix=False,
    ),
    # ===== 1% TIER (Insignificant/Negligible) =====
    QualitativeTerm(
        core_terms=["portion"],
        prefix_terms=["insignificant", "minimal", "tiny", "trivial", "token"],
        positive_pct=1.0,
        negated_pct=None,  # Could be modest, significant, or substantial
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["immaterial", "negligible"],
        positive_pct=1.0,
        negated_pct=25.0,  # ✓ REASONABLE: "not immaterial/negligible" → "material/significant" (~25%)
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=[
            "insignificant",
            "immaterial",
            "negligible",
            "trivial",
            "de minimis",
        ],
        prefix_terms=["is", "are", "was", "were"],
        positive_pct=1.0,
        negated_pct=25.0,  # ✓ REASONABLE: "is not insignificant" → "is significant" (~25%)
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["de minimis"],
        positive_pct=1.0,
        negated_pct=None,  # Rare to negate, unclear meaning
        requires_suffix=False,
    ),
    QualitativeTerm(
        core_terms=["nominal"],
        suffix_terms=["amount"],
        positive_pct=1.0,
        negated_pct=None,  # "not nominal amount" is vague
        requires_suffix=True,
    ),
]

COMPILED_QUALITATIVE_PATTERNS = []
for term in QUALITATIVE_TERMS:
    pattern_str = term.build_pattern()
    regex = build_regex([pattern_str])
    COMPILED_QUALITATIVE_PATTERNS.append(
        {"regex": regex, "term": term, "pattern_str": pattern_str}
    )

class UnionExtractor:
    def __init__(self):
        # Use the centralized RegionMatcher for all geo/specific union logic
        self.matcher = RegionMatcher()

    def analyze_sentence(self, text: str) -> SentenceAnalysis:
        analysis = SentenceAnalysis(text=text)
        working_text = text  # Mutable text for masking
        
        # Pre-compute temporal flags
        analysis.has_conditional = bool(CONDITIONAL_REGEX.search(text))
        analysis.has_current = bool(CURRENT_REGEX.search(text))
        analysis.has_historical = bool(HISTORICAL_REGEX.search(text))
        analysis.has_future = bool(FUTURE_REGEX.search(text))
        
        def process_matches(pattern, type_name, extractor_func=None, side_effect=None):
            nonlocal working_text
            current_iter_matches = list(pattern.finditer(working_text))
            if not current_iter_matches:
                return

            # Apply masking to working_text
            chars = list(working_text)
            
            for m in current_iter_matches:
                start, end = m.span()
                val = m.group(0)
                extracted = val
                
                if extractor_func:
                    try:
                        extracted = extractor_func(m)
                    except (ValueError, IndexError):
                        continue
                
                # Record match
                analysis._matches.append({
                    'type': type_name,
                    'val': extracted,
                    'span': (start, end),
                    'text': val
                })
                
                if side_effect:
                    side_effect(m, extracted)
                
                # Mask with spaces
                for i in range(start, end):
                    chars[i] = ' '
            
            working_text = "".join(chars)

        # 1. Extract Percentages
        process_matches(
            PERCENT_REGEX, MatchType.PERCENT,
            lambda m: float(m.group(1)),
            lambda m, val: analysis.percentages.append(val)
        )

        # 2. Extract Years
        process_matches(
            YEAR_TOKEN_REGEX, MatchType.YEAR,
            lambda m: int(m.group(1)),
            lambda m, val: analysis.years.append(val)
        )

        # 3. Extract Specific Unions (Highest Priority for Unions)
        # These are explicit names like "UAW", "IG Metall" defined in region_regex
        if self.matcher.specific_union_regex:
            def specific_union_side_effect(m, val):
                analysis.union_terms.append(val)
                lower_term = val.lower()
                if lower_term in self.matcher.union_map:
                    region, country, code = self.matcher.union_map[lower_term]
                    analysis.geo_matches.append(GeoMatch(
                        text=val, region=region, country=country, geo_code=code, source_type=GeoSource.SPECIFIC_UNION
                    ))

            process_matches(
                self.matcher.specific_union_regex, MatchType.SPECIFIC_UNION,
                lambda m: m.group(0),
                specific_union_side_effect
            )

        # 4. Extract Dynamic Union Names (Pattern-based)
        def dynamic_union_side_effect(m, val):
            analysis.union_terms.append(val)
            lower_term = val.lower()
            if lower_term in self.matcher.union_map:
                region, country, code = self.matcher.union_map[lower_term]
                analysis.geo_matches.append(GeoMatch(
                    text=val, region=region, country=country, geo_code=code, source_type=GeoSource.INFERRED_UNION
                ))

        process_matches(
            DYNAMIC_UNION_REGEX, MatchType.UNION_NAME,
            lambda m: m.group(0),
            dynamic_union_side_effect
        )

        # 5. Extract Non-Union Terms (Specific negation)
        process_matches(
            NON_UNION_REGEX, MatchType.NON_UNION,
            lambda m: m.group(0),
            lambda m, val: analysis.negation_terms.append(val)
        )
        
        # 5b. Extract Non-Coverage Terms (at-will, unrepresented)
        process_matches(
            NON_COVERAGE_REGEX, MatchType.NON_COVERAGE,
            lambda m: m.group(0),
            lambda m, val: analysis.negation_terms.append(val) # Treat as negation term for general logic
        )

        # 6. Extract Risk Terms
        process_matches(
            RISK_REGEX, MatchType.RISK_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.risk_terms.append(val)
        )

        # 7. Extract Union Terms (Generic)
        process_matches(
            UNION_REGEX, MatchType.UNION_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.union_terms.append(val)
        )

        # 8. Extract Geography (Explicit)
        if self.matcher.location_regex:
            def geo_side_effect(m, val):
                phrase = val.lower()
                if phrase in self.matcher.location_map:
                    region, country, city, code = self.matcher.location_map[phrase]
                    analysis.geo_matches.append(GeoMatch(
                        text=val, region=region, country=country, city=city, geo_code=code, source_type=GeoSource.EXPLICIT
                    ))
            
            process_matches(
                self.matcher.location_regex, MatchType.GEO,
                lambda m: m.group(0),
                geo_side_effect
            )

        # 10. Extract Ratios (Before Numbers)
        process_matches(
            RATIO_REGEX, MatchType.RATIO,
            lambda m: (float(m.group(1)), float(m.group(2))),
            lambda m, val: analysis.ratios.append(val)
        )

        # 11. Extract Worker Counts (Specific Numbers)
        process_matches(
            WORKER_COUNT_REGEX, MatchType.WORKER_COUNT,
            lambda m: float(next(g for g in m.groups() if g is not None)),
            lambda m, val: analysis.worker_counts.append(val)
        )

        # 12. Extract Worker Terms (Generic)
        process_matches(
            WORKER_TERM_REGEX, MatchType.WORKER_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.worker_terms.append(val)
        )
        
        # 13. Extract Numbers (Generic - lowest priority)
        process_matches(
            NUMBER_REGEX, MatchType.NUMBER,
            lambda m: float(m.group(0)),
            lambda m, val: analysis.numbers.append(val)
        )

        # 14. Extract Relationship Terms (e.g. "employee relations")
        process_matches(
            RELATIONSHIP_REGEX, MatchType.RELATIONSHIP_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.relationship_terms.append(val)
        )

        # 15. Extract Relationship Quality (e.g. "good", "strained")
        process_matches(
            RELATIONSHIP_QUALITY_REGEX, MatchType.RELATIONSHIP_QUALITY,
            lambda m: m.group(0),
            lambda m, val: analysis.relationship_quality_terms.append(val)
        )

        # 16. Extract Supplier Terms (Third Party Risk)
        process_matches(
            SUPPLIER_REGEX, MatchType.SUPPLIER_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.supplier_terms.append(val)
        )
        
        # 17. Extract Coverage Terms (e.g. "represented", "covered")
        process_matches(
            COVERAGE_REGEX, MatchType.COVERAGE_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.coverage_terms.append(val)
        )
        
        # 18. Extract Qualitative Terms
        for item in COMPILED_QUALITATIVE_PATTERNS:
            def qual_side_effect(m, val):
                analysis.qualitative_terms.append(val)
                if analysis._matches:
                    analysis._matches[-1]['term_obj'] = item['term']
                    analysis._matches[-1]['pattern_str'] = item['pattern_str']

            process_matches(
                item['regex'], MatchType.QUALITATIVE_TERM,
                lambda m: m.group(0),
                qual_side_effect
            )

        # 19. Extract Total Modifiers
        process_matches(
            TOTAL_MODIFIER_REGEX, MatchType.TOTAL_MODIFIER,
            lambda m: m.group(0),
            lambda m, val: analysis.total_modifiers.append(val)
        )
        print(analysis)
        return analysis

    def split_sentences(self, text: str | List[str]) -> List[str]:
        parts = SENTENCE_SPLIT_PATTERN.split(text) if isinstance(text, str) else text
        final_parts = []
        for p in parts:
            # Secondary split by semicolon to handle compound sentences like "Chile...; Colombia..."
            sub_parts = p.split(';')
            for sp in sub_parts:
                if sp.strip():
                    final_parts.append(sp.strip())
        return final_parts
