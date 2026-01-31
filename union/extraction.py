#%%
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from defs.regex_lib import SENTENCE_SPLIT_PATTERN
from defs.union_regex import UNION_REGEX, RISK_REGEX, DYNAMIC_UNION_REGEX, CORE
from defs.region_regex import (
    Region, RegionMatcher, GeoSource)

# Regex for basic entities
PERCENT_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
NUMBER_REGEX = re.compile(r"\b\d+(?:\.\d+)?\b")
YEAR_TOKEN_REGEX = re.compile(r"<(\d{4})>")

# Negation patterns
NEGATION_REGEX = re.compile(r"\b(?:no|not|none|neither|nor|never)\b", re.IGNORECASE)
NON_UNION_REGEX = re.compile(CORE.NONUNION.value, re.IGNORECASE)

class MatchType(Enum):
    PERCENT = "PERCENT"
    YEAR = "YEAR"
    SPECIFIC_UNION = "SPECIFIC_UNION"
    UNION_NAME = "UNION_NAME"
    NON_UNION = "NON_UNION"
    RISK_TERM = "RISK_TERM"
    UNION_TERM = "UNION_TERM"
    GEO = "GEO"
    NEGATION = "NEGATION"
    NUMBER = "NUMBER"

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
    numbers: List[float] = field(default_factory=list)
    years: List[int] = field(default_factory=list)
    union_terms: List[str] = field(default_factory=list)
    risk_terms: List[str] = field(default_factory=list)
    negation_terms: List[str] = field(default_factory=list)
    geo_matches: List[GeoMatch] = field(default_factory=list)
    
    # Raw matches for debugging or precise location
    _matches: List[Dict[str, Any]] = field(default_factory=list)

class UnionExtractor:
    def __init__(self):
        # Use the centralized RegionMatcher for all geo/specific union logic
        self.matcher = RegionMatcher()

    def analyze_sentence(self, text: str) -> SentenceAnalysis:
        analysis = SentenceAnalysis(text=text)
        working_text = text  # Mutable text for masking
        
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

        # 9. Extract Negation Terms (General)
        process_matches(
            NEGATION_REGEX, MatchType.NEGATION,
            lambda m: m.group(0),
            lambda m, val: analysis.negation_terms.append(val)
        )

        # 10. Extract Numbers (Generic - lowest priority)
        process_matches(
            NUMBER_REGEX, MatchType.NUMBER,
            lambda m: float(m.group(0)),
            lambda m, val: analysis.numbers.append(val)
        )

        return analysis

    def split_sentences(self, text: str | List[str]) -> List[str]:
        parts = SENTENCE_SPLIT_PATTERN.split(text) if isinstance(text, str) else text
        return [p.strip() for p in parts if p.strip()]
#%%
if __name__ == "__main__":
    extractor = UnionExtractor()
    
    examples = [
        "Approximately 12% of our U.S. workforce is represented by labor unions.",
        "Our operations in Germany, France, and the UK have collective bargaining agreements covering approximately 55% of employees in those regions.",
        "Approximately 30% of our employees are represented by the UAW (United Auto Workers).",
        "We have no employees covered by collective bargaining agreements.",
        "Union organizing efforts in key markets could increase our labor expenses."
    ]
    
    for ex in examples:
        print(f"Input: {ex}")
        analysis = extractor.analyze_sentence(ex)
        print(f"  Percentages: {analysis.percentages}")
        print(f"  Numbers: {analysis.numbers}")
        print(f"  Union Terms: {analysis.union_terms}")
        print(f"  Risk Terms: {analysis.risk_terms}")
        print(f"  Negation Terms: {analysis.negation_terms}")
        print(f"  Geo Matches: {analysis.geo_matches}")
        print("-" * 40)