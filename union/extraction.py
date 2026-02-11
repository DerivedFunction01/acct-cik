# %%
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from defs.regex_lib import (
    SENTENCE_SPLIT_PATTERN2,
    build_alternation,
    build_regex,
    build_compound,
    to_build_alternation,
)
from defs.union_regex import (
    CORE,
    GAP,
    UNION_REGEX,
    RISK_REGEX,
    DYNAMIC_UNION_REGEX,
    WORKER_TERMS,
    NON_COVERAGE_REGEX,
    NON_UNION_REGEX,
    RELATIONSHIP_REGEX,
    RELATIONSHIP_QUALITY_REGEX,
    SUPPLIER_REGEX,
    COVERAGE_REGEX,
    BOILERPLATE_REGEX,
    PERSONNEL_EVENT_REGEX,
    FOREIGN_DYNAMIC_PATTERNS,
    LOOSE_TITLE_PREFIX_REGEX,
)
from defs.region_regex import Region, RegionMatcher, GeoSource

# Regex for basic entities
PERCENT_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
NUMBER_REGEX = re.compile(r"\b\d+(?:\.\d+)?\b")
YEAR_TOKEN_REGEX = re.compile(r"<(\d{4})>")
RATIO_REGEX = re.compile(
    r"\b(\d+(?:\.\d+)?)\s+(?:[\w-]+\s+){0,5}(?:(?:out\s+)?of)\s+(?:[\w-]+\s+){0,5}(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
RESPECTIVELY_REGEX = re.compile(r"\brespectively\b", re.IGNORECASE)

# --- Temporal Regexes ---
CONDITIONAL_REGEX = build_regex(
    [r"if", r"could", r"may", r"might", r"potential", r"possible", r"can"]
)

CURRENT_REGEX = build_regex(
    [
        r"currently",
        r"now",
        r"(?:this|current)\s+(?:fiscal\s+|reporting\s+)?(?:year|period)",
    ]
)

HISTORICAL_REGEX = build_regex(
    [
        r"historical(?:ly)?",
        r"previously",
        r"prior\s+to",
        r"(?:last|prior|past|previous|preceding)\s+(?:fiscal\s+|reporting\s+)?(?:years?|periods?)",
    ]
)

FUTURE_REGEX = build_regex(
    [
        r"in\s+the\s+future",
        r"(?:future|next|upcoming)\s+(?:fiscal\s+|reporting\s+)?(?:years?|periods?)",
    ]
)

NEGATION_REGEX = build_regex(
    [r"no", r"not", r"nor", r"without", r"neither", r"none", r"never"]
)

REMAIN_REGEX = build_regex([r"remaining", r"rest", r"other"])


OF_REGEX = build_regex([r"(?:out\s+)?of"])
OR_REGEX = build_regex([r"or"])

TOTAL_MODIFIER_REGEX = build_regex(
    [
        r"total",
        r"global",
        r"worldwide",
        r"aggregate",
        r"consolidated",
        r"entire",
        r"overall",
        r"combined",
        r"full",
        r"whole",
        r"employ(?:s|ed|ees?)?",
    ]
)

QUALITATIVE_MULTIPLIERS = [
    (build_regex([r"almost", r"nearly", r"virtually"]), 0.95),
    (build_regex([r"(?:slightly|just)\s+(?:under|below)", r"less\s+than"]), 0.90),
    (build_regex([r"materially\s+less\s+than"]), 0.80),
    (build_regex([r"(?:slightly|just)\s+(?:over|above)", r"more\s+than"]), 1.10),
]

# Worker Count Pattern: Number + (optional gap) + Worker Term
worker_term_pattern = build_alternation(WORKER_TERMS + [r"managers?", r"officers?"])
# Gap that avoids consuming numbers (words must start with non-digit)
non_numeric_gap = r"(?:[^\W\d][\w-]*\s+){0,3}"
WORKER_COUNT_REGEX = build_regex(
    [
        rf"employ(?:ed|s)?\s+{non_numeric_gap}(\d+(?:\.\d+)?)",
        rf"(\d+(?:\.\d+)?)\s+{non_numeric_gap}{worker_term_pattern}",
        rf"{worker_term_pattern}\s+{non_numeric_gap}(\d+(?:\.\d+)?)",
        rf"(\d+(?:\.\d+)?)\s+(?:in|are|were|have|had)",
    ]
)
WORKER_TERM_REGEX = re.compile(rf"\b{worker_term_pattern}\b", re.IGNORECASE)
WORKER_TYPE_REGEX = build_regex(
    [r"hourly", r"contracted", r"salar(?:y|ied)", r"(?:part|full)[- ]time", r"temporary", r"seasonal"]
)
DENOMINATOR_PREFIX = [r"(?:out\s+)?of"]
DENOMINATOR_ADJECTIVES = [
    CORE.UNION,
    r"represented",
    r"covered",
    r"bargaining",
    CORE.NONUNION,
    CORE.ATWILL,
    r"unrepresented",
]
DENOMINATOR_NOUNS = [worker_term_pattern, r"population", r"unit"]
DENOMINATOR_GAP = r"(?:[\w-]+\s+){0,2}"
DENOMINATOR_COVERAGE_TERMS = build_compound(
    [r"(?:currently?\s+)?", r"(?:not\s+)?"], # principally, primarily are stripped by the text cleaner
    [
        r"subject\s+to",
        r"covered",
        r"represented",
        r"under",
        r"affiliated",
    ],
    sep_prefix="",
)
PERCENT_PREFIX = r"\d+(?:\.\d+)?%\s+"
# Capture 18% of our unionized workers, 20% of the employees represented
UNION_DENOMINATOR_REGEX = build_regex(
    [
        PERCENT_PREFIX + build_compound(
            DENOMINATOR_PREFIX,
            DENOMINATOR_ADJECTIVES,
            DENOMINATOR_NOUNS,
            sep_prefix=r"\s+" + DENOMINATOR_GAP,
            sep_suffix=r"\s+" + DENOMINATOR_GAP,
        ),
        PERCENT_PREFIX + build_compound(
            DENOMINATOR_PREFIX,
            [r"union", r"bargaining\s+unit"],
            sep_prefix=r"\s+(?:our\s+|the\s+)?",
        ),
        # Strict: Do not match (18% of the workers are covered/represented)
        PERCENT_PREFIX + build_compound(
            DENOMINATOR_PREFIX,
            DENOMINATOR_NOUNS,
            DENOMINATOR_COVERAGE_TERMS,
            sep_prefix=r"\s+",
            sep_suffix=r"\s+",
        ),
    ]
)

DIVERSITY_REGEX = build_regex(
    [
        r"women",
        r"females?",
        r"males?",
        r"gender",
        r"diversity",
        r"inclusion",
        r"minorit(?:y|ies)",
        r"ethnic(?:ity)?",
        r"race",
        r"racial",
        r"veterans?",
        r"disabilit(?:y|ies)",
        r"disabled",
        r"sexual\s+orientation",
        r"people\s+of\s+color",
        r"african\s+american",
        r"hispanic",
        r"latino",
        r"asian",
        r"white",
        r"black",
        r"indigenous",
        r"lgbtq?",
        r"underrepresented",
    ]
)


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
    QUALITATIVE_MEMBERSHIP = "QUALITATIVE_MEMBERSHIP"
    TOTAL_MODIFIER = "TOTAL_MODIFIER"
    RESPECTIVELY = "RESPECTIVELY"
    REMAINING_OTHER = "REMAINING_OTHER"
    WORKER_TYPE = "WORKER_TYPE"
    DIVERSITY_TERM = "DIVERSITY_TERM"


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
    qualitative_membership_terms: List[str] = field(default_factory=list)
    total_modifiers: List[str] = field(default_factory=list)
    geo_matches: List[GeoMatch] = field(default_factory=list)
    worker_types: List[str] = field(default_factory=list)
    diversity_terms: List[str] = field(default_factory=list)

    # Temporal / Conditional flags
    has_conditional: bool = False
    has_current: bool = False
    has_historical: bool = False
    has_future: bool = False
    has_respectively: bool = False
    has_remaining_other: bool = False
    has_union_denominator: bool = False

    # Raw matches for debugging or precise location
    _matches: List[Dict[str, Any]] = field(default_factory=list)

    is_relevant: bool = False


@dataclass
class QualitativeTerm:
    """Represents a qualitative quantity term with its positive and negated percentages."""

    # Core term components
    core_terms: List[str]  # e.g., ["majority", "bulk"]

    # Percentage values
    positive_pct: Optional[float]  # When used positively: "majority" = 51%
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
    is_all: bool = False  # True if the meaning is 100%

    prefix_gap: Optional[str] = "[- ]"
    suffix_gap: Optional[str] = "[- ]"

    # Bounds for validation
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None

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


from defs.union_regex import MEMBERSHIP_PHRASES

QUALITATIVE_MEMBERSHIP = [
    # ===== 95% TIER (Mandatory/Widespread) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=["mandatory", "widespread", "comprehensive"],
        positive_pct=95.0,
        negated_pct=None,
        requires_suffix=False,
        lower_bound=90.0,
        upper_bound=100.0,
    ),
    # ===== 85% TIER (Substantial/Heavy) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=["substantial", "heavy", "predominant"],
        positive_pct=85.0,
        negated_pct=10.0,  # "not substantially" = minority (~10%)
        requires_suffix=False,
        lower_bound=75.0,
        upper_bound=100.0,
    ),
    # ===== 65% TIER (Significant/Major) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=["significant", "major", "considerable"],
        positive_pct=65.0,
        negated_pct=20.0,  # "not significant" = minor/small
        requires_suffix=False,
        lower_bound=50.0,
        upper_bound=85.0,
    ),
    # ===== 51% TIER (Majority/Most) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=["mostly"],
        positive_pct=51.0,
        negated_pct=10.0,  # "not majority" = minority
        requires_suffix=False,
        lower_bound=50.0,
        upper_bound=100.0,
    ),
    # ===== 40% TIER (Substantial Minority) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=["substantial", "fair"],
        positive_pct=40.0,
        negated_pct=None,
        requires_suffix=False,
        lower_bound=30.0,
        upper_bound=50.0,
    ),
    # ===== 25% TIER (Meaningful/Notable) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=["meaningful", "notable", "modest"],
        positive_pct=25.0,
        negated_pct=5.0,  # "not meaningful" = minimal
        requires_suffix=False,
        lower_bound=10.0,
        upper_bound=40.0,
    ),
    # ===== 5% TIER (Small/Minor) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=[
            "small",
            "minor",
        ],
        positive_pct=5.0,
        negated_pct=None,
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=15.0,
    ),
    # ===== 3% TIER (Minimal/Negligible) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=["minimal", "negligible", "token", "handful", "limited"],
        positive_pct=3.0,
        negated_pct=None,
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=10.0,
    ),
    # ===== 1% TIER (De Minimis/Immaterial) =====
    QualitativeTerm(
        core_terms=MEMBERSHIP_PHRASES,
        prefix_terms=["immaterial", "de minimis", "insignificant"],
        positive_pct=1.0,
        negated_pct=20.0,  # "not immaterial" = material/significant
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=5.0,
    ),
]

# Triggers only when needed as last resort, to avoid converting 100% x COUNT -> Qualitative.value
QUALITATIVE_ALL_TERMS = [
    QualitativeTerm(
        core_terms=["all"],
        suffix_terms=["of", "are", "were"],
        positive_pct=100.0,
        negated_pct=None,
        requires_suffix=True,
        lower_bound=100.0,
        upper_bound=100.0,
        is_all=True,
    ),
    QualitativeTerm(
        core_terms=["entirety"],
        positive_pct=100.0,
        negated_pct=None,
        requires_suffix=False,
        lower_bound=100.0,
        upper_bound=100.0,
        is_all=True,
    ),
    QualitativeTerm(
        core_terms=[r"every(?:[- ]?one)?", r"all"],
        suffix_terms=WORKER_TERMS,
        positive_pct=100.0,
        negated_pct=None,
        requires_suffix=True,
        suffix_gap=GAP,
        lower_bound=100.0,
        upper_bound=100.0,
        is_all=True,
    ),
]
QUALITATIVE_TERMS = [
    # ===== 95% TIER (Substantially All) =====
    QualitativeTerm(
        core_terms=["all", r"(?:the\s+)entire(?:ty)?", r"every"],
        prefix_terms=["substantially", "virtually", "almost", "nearly", "practically"],
        positive_pct=95.0,
        negated_pct=None,
        requires_suffix=False,
        lower_bound=90.0,
        upper_bound=99.9,
    ),
    # ===== 75% TIER (Vast Majority) =====
    QualitativeTerm(
        core_terms=["majority", "bulk"],
        prefix_terms=["vast", "substantial", "overwhelming"],
        positive_pct=75.0,
        negated_pct=None,  # "not vast majority" could be 51%, 30%, or 10%
        requires_suffix=False,
        lower_bound=70.0,
        upper_bound=100.0,
    ),
    # ===== 65% TIER (Predominant) =====
    QualitativeTerm(
        core_terms=["portion", "share", "number", "amount"],
        prefix_terms=["predominant", "vast", "substantial", "overwhelming"],
        positive_pct=65.0,
        negated_pct=None,  # Downgrade is unclear
        requires_suffix=False,
        lower_bound=55.0,
        upper_bound=90.0,
    ),
    QualitativeTerm(
        core_terms=["majority", "bulk"],
        prefix_terms=["considerable", "significant"],
        positive_pct=65.0,
        negated_pct=None,  # Could be modest, small, or minor
        requires_suffix=False,
        lower_bound=55.0,
        upper_bound=90.0,
    ),
    # ===== 60% TIER (Bulk) =====
    QualitativeTerm(
        core_terms=["bulk"],
        suffix_terms=["of"],
        positive_pct=60.0,
        negated_pct=None,  # Ambiguous downgrade
        requires_suffix=True,
        lower_bound=51.0,
        upper_bound=90.0,
    ),
    # ===== 51% TIER (Simple Majority) =====
    QualitativeTerm(
        core_terms=["majority"],
        positive_pct=51.0,
        negated_pct=10.0,  # ✓ CLEAR: "not majority" = "minority" (~10%)
        requires_suffix=False,
        lower_bound=50.0,
        upper_bound=100.0,
    ),
    QualitativeTerm(
        core_terms=["most"],
        suffix_terms=["of"],
        positive_pct=51.0,
        negated_pct=None,  # "not most of" is vague
        requires_suffix=True,
        lower_bound=50.0,
        upper_bound=100.0,
    ),
    # ===== 40% TIER (Major/Predominant Minority) =====
    QualitativeTerm(
        core_terms=["portion", "share", "number", "amount", "fraction"],
        prefix_terms=["major"],
        positive_pct=40.0,
        negated_pct=None,  # "not major" could be modest, small, or minor
        requires_suffix=False,
        lower_bound=30.0,
        upper_bound=49.9,
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
        lower_bound=30.0,
        upper_bound=49.9,
    ),
    # ===== 30% TIER (Considerable) =====
    QualitativeTerm(
        core_terms=["portion", "number", "amount", "share", "fraction"],
        prefix_terms=["considerable"],
        positive_pct=30.0,
        negated_pct=None,  # Could be modest or small
        requires_suffix=False,
        lower_bound=20.0,
        upper_bound=50.0,
    ),
    # ===== 25% TIER (Significant/Substantial) =====
    QualitativeTerm(
        core_terms=["portion", "share", "number", "amount", "fraction"],
        prefix_terms=["significant", "substantial", "large", "meaningful", "extensive"],
        positive_pct=25.0,
        negated_pct=None,  # Could be modest, small, or insignificant
        requires_suffix=False,
        lower_bound=10.0,
        upper_bound=50.0,
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
        lower_bound=10.0,
        upper_bound=50.0,
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
        lower_bound=10.0,
        upper_bound=50.0,
    ),
    # ===== 20% TIER (Good) =====
    QualitativeTerm(
        core_terms=["portion", "share", "number", "amount", "fraction"],
        prefix_terms=["good"],
        positive_pct=20.0,
        negated_pct=None,  # "not good" is vague
        requires_suffix=False,
        lower_bound=10.0,
        upper_bound=40.0,
    ),
    QualitativeTerm(
        core_terms=["many"],
        suffix_terms=["of"],
        positive_pct=20.0,
        negated_pct=None,
        requires_suffix=True,
        lower_bound=10.0,
        upper_bound=40.0,
    ),
    QualitativeTerm(
        core_terms=["numerous", "many"],
        suffix_terms=WORKER_TERMS,
        positive_pct=20.0,
        negated_pct=None,
        requires_suffix=True,
        suffix_gap=GAP,
        lower_bound=10.0,
        upper_bound=40.0,
    ),
    # ===== 15% TIER (Fair/Modest) =====
    QualitativeTerm(
        core_terms=["portion", "share", "number", "amount", "fraction"],
        prefix_terms=["fair", "modest"],
        positive_pct=15.0,
        negated_pct=None,  # Could be large or small
        requires_suffix=False,
        lower_bound=5.0,
        upper_bound=30.0,
    ),
    # ===== 10% TIER (Minority/Small) =====
    QualitativeTerm(
        core_terms=["minority"],
        positive_pct=10.0,
        negated_pct=51.0,  # ✓ CLEAR: "not minority" = "majority" (~51%)
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=50.0,
    ),
    QualitativeTerm(
        core_terms=["portion", "share", "amount", "fraction"],
        prefix_terms=["small", "minor", "little", "fractional"],
        positive_pct=10.0,
        negated_pct=None,  # "not small" could be modest, significant, or large
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=20.0,
    ),
    QualitativeTerm(
        core_terms=["minor", "small"],
        prefix_terms=["is", "are", "was", "were"],
        positive_pct=10.0,
        negated_pct=25.0,  # ✓ REASONABLE: "is not small/minor" → "is significant" (~25%)
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=20.0,
    ),
    QualitativeTerm(
        core_terms=["fraction"],
        suffix_terms=["of"],
        positive_pct=10.0,
        negated_pct=None,  # "not fraction of" is vague
        requires_suffix=True,
        lower_bound=0.0,
        upper_bound=20.0,
    ),
    # ===== 5% TIER (Handful/Few/Nominal/Limited) =====
    QualitativeTerm(
        core_terms=["handful", "few"],
        suffix_terms=["of"],
        positive_pct=5.0,
        negated_pct=None,  # "not handful" could be many things
        requires_suffix=True,
        lower_bound=0.0,
        upper_bound=10.0,
    ),
    QualitativeTerm(
        core_terms=["number"],
        prefix_terms=["small", "minor"],
        positive_pct=5.0,
        negated_pct=None,
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=15.0,
    ),
    QualitativeTerm(
        core_terms=["portion", "share", "number", "amount", "fraction"],
        prefix_terms=["nominal", "limited"],
        positive_pct=5.0,
        negated_pct=None,  # Could be modest or significant
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=15.0,
    ),
    QualitativeTerm(
        core_terms=["nominal", "limited"],
        prefix_terms=["is", "are", "was", "were"],
        positive_pct=5.0,
        negated_pct=25.0,  # ✓ REASONABLE: "is not limited/nominal" → "is significant" (~25%)
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=15.0,
    ),
    # ===== 1% TIER (Insignificant/Negligible) =====
    QualitativeTerm(
        core_terms=["portion", "share", "number", "amount", "fraction"],
        prefix_terms=["insignificant", "minimal", "tiny", "trivial", "token"],
        positive_pct=1.0,
        negated_pct=None,  # Could be modest, significant, or substantial
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=5.0,
    ),
    QualitativeTerm(
        core_terms=["immaterial", "negligible", "not material"],
        positive_pct=1.0,
        negated_pct=25.0,  # ✓ REASONABLE: "not immaterial/negligible" → "material/significant" (~25%)
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=5.0,
    ),
    QualitativeTerm(
        core_terms=[
            "insignificant",
            "immaterial",
            "negligible",
            "trivial",
            "de minimis",
            "minimal",
        ],
        prefix_terms=["is", "are", "was", "were"],
        positive_pct=1.0,
        negated_pct=25.0,  # ✓ REASONABLE: "is not insignificant" → "is significant" (~25%)
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=5.0,
    ),
    QualitativeTerm(
        core_terms=["de minimis"],
        positive_pct=1.0,
        negated_pct=None,  # Rare to negate, unclear meaning
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=5.0,
    ),
    QualitativeTerm(
        core_terms=["nominal", "token"],
        suffix_terms=["amount"],
        positive_pct=1.0,
        negated_pct=None,  # "not nominal amount" is vague
        requires_suffix=True,
        lower_bound=0.0,
        upper_bound=5.0,
    ),
    QualitativeTerm(
        core_terms=["nonexistent"],
        prefix_terms=["virtually", "substantially", "practically", "almost", "nearly"],
        positive_pct=0,
        negated_pct=None,  # "not nonexistent" is vague
        requires_suffix=False,
        lower_bound=0,
        upper_bound=1.0,
    ),
    QualitativeTerm(
        core_terms=["nonexistent", "zero", "none"],
        prefix_terms=[],
        positive_pct=0,
        negated_pct=None,  # "not nonexistent" is vague
        requires_suffix=False,
        lower_bound=0.0,
        upper_bound=0,
    ),
]

QUALITATIVE_TERMS_AMB = [
    QualitativeTerm(
        core_terms=[
            "some",
            "part",
            "portion",
            "segment",
            "fraction",
            "percentage",
            "proportion",
            "remainder",
            "balance",
        ],
        suffix_terms=["of"],
        positive_pct=None,
        negated_pct=None,
        requires_suffix=True,
    ),
    QualitativeTerm(
        core_terms=["certain"],
        suffix_terms=["of", "number", "amount", "fraction"],
        positive_pct=None,
        negated_pct=None,
        requires_suffix=True,
    ),
    QualitativeTerm(
        core_terms=["certain", "several", "some", "few", "multiple", "various"],
        suffix_terms=WORKER_TERMS,  # certain employees, several employees
        positive_pct=None,
        negated_pct=None,
        requires_suffix=True,
        suffix_gap=GAP,  # Gap
    ),
    QualitativeTerm(
        core_terms=["number", "quantity"],
        prefix_terms=["a"],
        suffix_terms=["of"],
        positive_pct=None,
        negated_pct=None,
        requires_suffix=True,
    ),
]

COMPILED_QUALITATIVE_PATTERNS = []
for term in QUALITATIVE_TERMS + QUALITATIVE_TERMS_AMB + QUALITATIVE_ALL_TERMS:
    pattern_str = term.build_pattern()
    regex = build_regex([pattern_str])
    COMPILED_QUALITATIVE_PATTERNS.append(
        {"regex": regex, "term": term, "pattern_str": pattern_str}
    )

COMPILED_QUALITATIVE_MEMBERSHIP_PATTERNS = []
for term in QUALITATIVE_MEMBERSHIP:
    pattern_str = term.build_pattern()
    regex = build_regex([pattern_str])
    COMPILED_QUALITATIVE_MEMBERSHIP_PATTERNS.append(
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
        analysis.has_respectively = bool(RESPECTIVELY_REGEX.search(text))
        analysis.has_remaining_other = bool(REMAIN_REGEX.search(text))
        analysis.has_union_denominator = bool(UNION_DENOMINATOR_REGEX.search(text))
        analysis.is_relevant = False

        def process_matches(pattern, type_name, extractor_func=None, side_effect=None, update_working_text=False):
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
                        res = extractor_func(m)
                        if isinstance(res, tuple) and len(res) == 3:
                            extracted, new_start, new_end = res
                            start, end = new_start, new_end
                        else:
                            extracted = res
                    except (ValueError, IndexError):
                        continue

                # Record match
                analysis._matches.append(
                    {
                        "type": type_name,
                        "val": extracted,
                        "span": (start, end),
                        "text": val,
                    }
                )

                if side_effect:
                    side_effect(m, extracted)

                # Mask with spaces
                for i in range(start, end):
                    chars[i] = " "
                
                if update_working_text:
                    working_text = "".join(chars)

            if not update_working_text:
                working_text = "".join(chars)

        # 1. Extract Percentages
        process_matches(
            PERCENT_REGEX,
            MatchType.PERCENT,
            lambda m: float(m.group(1)),
            lambda m, val: analysis.percentages.append(val),
        )

        # 2. Extract Years
        process_matches(
            YEAR_TOKEN_REGEX,
            MatchType.YEAR,
            lambda m: int(m.group(1)),
            lambda m, val: analysis.years.append(val),
        )

        # 3. Extract Specific Unions (Highest Priority for Unions)
        # These are explicit names like "UAW", "IG Metall" defined in region_regex
        if self.matcher.specific_union_regex:

            def specific_union_side_effect(m, val):
                analysis.union_terms.append(val)
                lower_term = val.lower()
                if lower_term in self.matcher.union_map:
                    region, country, code = self.matcher.union_map[lower_term]
                    analysis.geo_matches.append(
                        GeoMatch(
                            text=val,
                            region=region,
                            country=country,
                            geo_code=code,
                            source_type=GeoSource.SPECIFIC_UNION,
                        )
                    )

            process_matches(
                self.matcher.specific_union_regex,
                MatchType.SPECIFIC_UNION,
                lambda m: m.group(0),
                specific_union_side_effect,
            )

        # 4. Extract Dynamic Union Names (Pattern-based)
        def expand_dynamic_match(m):
            val = m.group(0)
            start, end = m.span()

            # Look behind for loose prefix (e.g. "International Teachers, Instructors and ")
            # We look at working_text which has previous matches masked, so we won't merge separate unions
            lookbehind_limit = 150
            search_start = max(0, start - lookbehind_limit)
            pre_text = working_text[search_start:start]

            prefix_match = LOOSE_TITLE_PREFIX_REGEX.search(pre_text)
            if prefix_match:
                prefix = prefix_match.group(0)
                return prefix + val, start - len(prefix), end
            
            return val

        def dynamic_union_side_effect(m, val):
            analysis.union_terms.append(val)
            lower_term = val.lower()
            if lower_term in self.matcher.union_map:
                region, country, code = self.matcher.union_map[lower_term]
                analysis.geo_matches.append(
                    GeoMatch(
                        text=val,
                        region=region,
                        country=country,
                        geo_code=code,
                        source_type=GeoSource.INFERRED_UNION,
                    )
                )
            else:
                # Fallback: Check if it matches a known foreign dynamic pattern
                # This maps "Sindicato de..." back to "INT_IBERIA", etc.
                for code, pattern in FOREIGN_DYNAMIC_PATTERNS.items():
                    if pattern.fullmatch(val):
                        # We found the language origin.
                        # We don't know the specific country yet, but we have the language code.
                        analysis.geo_matches.append(
                            GeoMatch(
                                text=val,
                                region=Region.INTERNATIONAL, # Broad region, refined by analysis.py using code
                                geo_code=code,
                                source_type=GeoSource.INFERRED_UNION,
                            )
                        )
                        break

        process_matches(
            DYNAMIC_UNION_REGEX,
            MatchType.UNION_NAME,
            expand_dynamic_match,
            dynamic_union_side_effect,
            update_working_text=True,
        )

        # 4.5 Check for Union Denominator with specific/dynamic union names replaced
        if not analysis.has_union_denominator:
            # Gather all union matches found so far (SPECIFIC_UNION and UNION_NAME)
            union_matches = [
                m
                for m in analysis._matches
                if m["type"] in (MatchType.SPECIFIC_UNION, MatchType.UNION_NAME)
            ]

            if union_matches:
                # Sort by start index descending to replace from end to start
                union_matches.sort(key=lambda x: x["span"][0], reverse=True)
                temp_text = text
                for m in union_matches:
                    start, end = m["span"]
                    temp_text = temp_text[:start] + "union" + temp_text[end:]

                if UNION_DENOMINATOR_REGEX.search(temp_text):
                    analysis.has_union_denominator = True

        # 5. Extract Non-Union Terms (Specific negation)
        process_matches(
            NON_UNION_REGEX,
            MatchType.NON_UNION,
            lambda m: m.group(0),
            lambda m, val: analysis.negation_terms.append(val),
        )

        # 5b. Extract Non-Coverage Terms (at-will, unrepresented, non-union)
        process_matches(
            NON_COVERAGE_REGEX,
            MatchType.NON_COVERAGE,
            lambda m: m.group(0),
            lambda m, val: analysis.negation_terms.append(
                val
            ),  # Treat as negation term for general logic
        )

        # 6. Extract Risk Terms
        process_matches(
            RISK_REGEX,
            MatchType.RISK_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.risk_terms.append(val),
        )

        # 7. Extract Union Terms (Generic)
        process_matches(
            UNION_REGEX,
            MatchType.UNION_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.union_terms.append(val),
        )

        # 8. Extract Geography (Explicit)
        if self.matcher.location_regex:

            def geo_side_effect(m, val):
                phrase = val.lower()
                if phrase in self.matcher.location_map:
                    region, country, city, code = self.matcher.location_map[phrase]
                    analysis.geo_matches.append(
                        GeoMatch(
                            text=val,
                            region=region,
                            country=country,
                            city=city,
                            geo_code=code,
                            source_type=GeoSource.EXPLICIT,
                        )
                    )

            process_matches(
                self.matcher.location_regex,
                MatchType.GEO,
                lambda m: m.group(0),
                geo_side_effect,
            )

        # 10. Extract Ratios (Before Numbers)
        process_matches(
            RATIO_REGEX,
            MatchType.RATIO,
            lambda m: (float(m.group(1)), float(m.group(2))),
            lambda m, val: analysis.ratios.append(val),
        )

        # 11A: Extract Worker type
        process_matches(
            WORKER_TYPE_REGEX,
            MatchType.WORKER_TYPE,
            lambda m: m.group(0),
            lambda m, val: analysis.worker_types.append(val),
        )

        # 11B: Extract Diversity Terms
        process_matches(
            DIVERSITY_REGEX,
            MatchType.DIVERSITY_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.diversity_terms.append(val),
        )

        # 11. Extract Worker Counts (Specific Numbers)
        process_matches(
            WORKER_COUNT_REGEX,
            MatchType.WORKER_COUNT,
            lambda m: float(next(g for g in m.groups() if g is not None)),
            lambda m, val: analysis.worker_counts.append(val),
        )

        # 12. Extract Worker Terms (Generic)
        process_matches(
            WORKER_TERM_REGEX,
            MatchType.WORKER_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.worker_terms.append(val),
        )

        # 13. Extract Numbers (Generic - lowest priority)
        process_matches(
            NUMBER_REGEX,
            MatchType.NUMBER,
            lambda m: float(m.group(0)),
            lambda m, val: analysis.numbers.append(val),
        )

        # 14. Extract Relationship Terms (e.g. "employee relations")
        process_matches(
            RELATIONSHIP_REGEX,
            MatchType.RELATIONSHIP_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.relationship_terms.append(val),
        )

        # 15. Extract Relationship Quality (e.g. "good", "strained")
        process_matches(
            RELATIONSHIP_QUALITY_REGEX,
            MatchType.RELATIONSHIP_QUALITY,
            lambda m: m.group(0),
            lambda m, val: analysis.relationship_quality_terms.append(val),
        )

        # 16. Extract Supplier Terms (Third Party Risk)
        process_matches(
            SUPPLIER_REGEX,
            MatchType.SUPPLIER_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.supplier_terms.append(val),
        )

        # 17. Extract Coverage Terms (e.g. "represented", "covered")
        process_matches(
            COVERAGE_REGEX,
            MatchType.COVERAGE_TERM,
            lambda m: m.group(0),
            lambda m, val: analysis.coverage_terms.append(val),
        )

        # 18. Extract Qualitative Terms
        for item in COMPILED_QUALITATIVE_PATTERNS:

            def qual_side_effect(m, val):
                analysis.qualitative_terms.append(val)
                if analysis._matches:
                    analysis._matches[-1]["term_obj"] = item["term"]
                    analysis._matches[-1]["pattern_str"] = item["pattern_str"]

            process_matches(
                item["regex"],
                MatchType.QUALITATIVE_TERM,
                lambda m: m.group(0),
                qual_side_effect,
            )

        # 18b. Extract Qualitative Membership Terms
        for item in COMPILED_QUALITATIVE_MEMBERSHIP_PATTERNS:

            def qual_mem_side_effect(m, val):
                analysis.qualitative_membership_terms.append(val)
                if analysis._matches:
                    analysis._matches[-1]["term_obj"] = item["term"]
                    analysis._matches[-1]["pattern_str"] = item["pattern_str"]

            process_matches(
                item["regex"],
                MatchType.QUALITATIVE_MEMBERSHIP,
                lambda m: m.group(0),
                qual_mem_side_effect,
            )

        # 19. Extract Total Modifiers
        process_matches(
            TOTAL_MODIFIER_REGEX,
            MatchType.TOTAL_MODIFIER,
            lambda m: m.group(0),
            lambda m, val: analysis.total_modifiers.append(val),
        )

        # 20. Extract Respectively
        process_matches(
            RESPECTIVELY_REGEX, MatchType.RESPECTIVELY, lambda m: m.group(0), None
        )

        # Determine relevancy
        # 1. Explicit Union/Labor/Coverage/Risk terms
        has_union_keywords = bool(
            analysis.union_terms
            or analysis.coverage_terms
            or analysis.risk_terms
            or analysis.qualitative_membership_terms
            or analysis.relationship_terms
        )

        # 2. Geographic matches derived from Union names
        has_union_geo = any(
            m.source_type in (GeoSource.SPECIFIC_UNION, GeoSource.INFERRED_UNION)
            for m in analysis.geo_matches
        )

        # 3. Negation (often used for "non-union", "not covered")
        has_negation = bool(analysis.negation_terms)

        # 4. Quantitative Coverage (Percentage/Ratio + Worker Context)
        # We check if there's a percentage/ratio AND (worker terms OR worker counts)
        has_quant = bool(analysis.percentages or analysis.ratios or analysis.numbers or analysis.qualitative_terms)
        has_worker_context = bool(analysis.worker_terms or analysis.worker_counts)

        analysis.is_relevant = (
            has_union_keywords
            or has_union_geo
            or has_negation
            or (has_quant and has_worker_context)
            or bool(analysis.worker_counts)
        )

        # 5. Exclusions (Boilerplate / Personnel)
        if analysis.is_relevant:
            # Personnel: Exclude if no union terms and matches personnel event
            if not analysis.union_terms and PERSONNEL_EVENT_REGEX.search(text):
                analysis.is_relevant = False

            # Diversity: Exclude if diversity terms are present and no explicit union indicators
            elif analysis.diversity_terms:
                has_union_negation = any(
                    m["type"] in (MatchType.NON_UNION, MatchType.NON_COVERAGE)
                    for m in analysis._matches
                )
                if not (
                    analysis.union_terms
                    or analysis.coverage_terms
                    or has_union_geo
                    or has_union_negation
                ):
                    analysis.is_relevant = False

            # Boilerplate: Exclude if no quantitative data and matches boilerplate
            elif BOILERPLATE_REGEX.search(text):
                has_data = bool(
                    analysis.percentages
                    or analysis.ratios
                    or analysis.worker_counts
                    or analysis.numbers
                    or analysis.qualitative_terms
                )
                if not has_data:
                    analysis.is_relevant = False
        # print(analysis)
        return analysis

    def split_sentences(self, text: str | List[str]) -> List[str]:
        parts = SENTENCE_SPLIT_PATTERN2.split(text) if isinstance(text, str) else text
        final_parts = []
        for p in parts:
            # Secondary split by semicolon to handle compound sentences like "Chile...; Colombia..."
            sub_parts = p.split(";")
            for sp in sub_parts:
                if sp.strip():
                    final_parts.append(sp.strip())
        return final_parts

# %%
