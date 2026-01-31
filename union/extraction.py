import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from defs.regex_lib import SENTENCE_SPLIT_PATTERN
from defs.union_regex import UNION_REGEX, RISK_REGEX, DYNAMIC_UNION_REGEX, CORE
from defs.region_regex import (
    NORTH_AMERICA, EUROPE, ASIA_PACIFIC, LATIN_AMERICA, 
    MIDDLE_EAST_AFRICA, INTERNATIONAL, Region
)

# Regex for basic entities
PERCENT_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
NUMBER_REGEX = re.compile(r"\b\d+(?:\.\d+)?\b")
YEAR_TOKEN_REGEX = re.compile(r"<(\d{4})>")

# Negation patterns
NEGATION_REGEX = re.compile(r"\b(?:no|not|none|neither|nor|never)\b", re.IGNORECASE)
NON_UNION_REGEX = re.compile(CORE.NONUNION.value, re.IGNORECASE)

@dataclass
class GeoMatch:
    text: str
    region: Region
    country: Optional[str] = None
    city: Optional[str] = None
    source_type: str = "explicit"  # explicit, inferred_union

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
        self.geo_map: Dict[str, Tuple[Region, str, Optional[str]]] = {}
        self.union_geo_map: Dict[str, Tuple[Region, str]] = {}
        self.geo_regex: Optional[re.Pattern] = None
        self._compile_geo_data()

    def _compile_geo_data(self):
        """Builds mapping and regex for geographic terms."""
        all_regions = [
            NORTH_AMERICA, EUROPE, ASIA_PACIFIC, LATIN_AMERICA, 
            MIDDLE_EAST_AFRICA, INTERNATIONAL
        ]
        
        geo_phrases = set()

        for region_set in all_regions:
            for nation in region_set:
                # Map Nation phrases
                for phrase in nation.phrases:
                    p_lower = phrase.lower()
                    self.geo_map[p_lower] = (nation.region, nation.name, None)
                    geo_phrases.add(phrase)
                
                # Map Nation name
                n_lower = nation.name.lower()
                self.geo_map[n_lower] = (nation.region, nation.name, None)
                geo_phrases.add(nation.name)
                
                # Map Locations
                for loc in nation.locations:
                    for phrase in loc.phrases:
                        p_lower = phrase.lower()
                        self.geo_map[p_lower] = (nation.region, nation.name, loc.name)
                        geo_phrases.add(phrase)
                    
                    l_lower = loc.name.lower()
                    self.geo_map[l_lower] = (nation.region, nation.name, loc.name)
                    geo_phrases.add(loc.name)
                    
                    for sub in loc.cities:
                        for phrase in sub.phrases:
                            p_lower = phrase.lower()
                            self.geo_map[p_lower] = (nation.region, nation.name, sub.name)
                            geo_phrases.add(phrase)
                        
                        s_lower = sub.name.lower()
                        self.geo_map[s_lower] = (nation.region, nation.name, sub.name)
                        geo_phrases.add(sub.name)

                # Map Unions
                for union_name in nation.unions:
                    self.union_geo_map[union_name.lower()] = (nation.region, nation.name)

        # Build a single regex for all geo phrases
        # Sort by length descending to match longest phrases first
        if geo_phrases:
            sorted_phrases = sorted(list(geo_phrases), key=len, reverse=True)
            escaped_phrases = [re.escape(p) for p in sorted_phrases]
            pattern_str = r"\b(?:" + "|".join(escaped_phrases) + r")\b"
            self.geo_regex = re.compile(pattern_str, re.IGNORECASE)

    def analyze_sentence(self, text: str) -> SentenceAnalysis:
        analysis = SentenceAnalysis(text=text)
        
        # 1. Extract Percentages
        for m in PERCENT_REGEX.finditer(text):
            try:
                val = float(m.group(1))
                analysis.percentages.append(val)
                analysis._matches.append({
                    'type': 'PERCENT', 'val': val, 'span': m.span(), 'text': m.group(0)
                })
            except ValueError:
                pass

        # 2. Extract Years
        for m in YEAR_TOKEN_REGEX.finditer(text):
            try:
                val = int(m.group(1))
                analysis.years.append(val)
                analysis._matches.append({
                    'type': 'YEAR', 'val': val, 'span': m.span(), 'text': m.group(0)
                })
            except ValueError:
                pass

        # 3. Extract Numbers (avoid overlaps)
        for m in NUMBER_REGEX.finditer(text):
            start, end = m.span()
            # Check overlap with PERCENT or YEAR
            is_overlap = False
            for existing in analysis._matches:
                if existing['type'] in ('PERCENT', 'YEAR'):
                    e_start, e_end = existing['span']
                    if start < e_end and end > e_start:
                        is_overlap = True
                        break
            
            if not is_overlap:
                try:
                    val = float(m.group(0))
                    analysis.numbers.append(val)
                    analysis._matches.append({
                        'type': 'NUMBER', 'val': val, 'span': m.span(), 'text': m.group(0)
                    })
                except ValueError:
                    pass

        # 4. Extract Union Terms
        for m in UNION_REGEX.finditer(text):
            analysis.union_terms.append(m.group(0))
            analysis._matches.append({
                'type': 'UNION_TERM', 'val': m.group(0), 'span': m.span()
            })
        
        for m in DYNAMIC_UNION_REGEX.finditer(text):
            term = m.group(0)
            analysis.union_terms.append(term)
            analysis._matches.append({
                'type': 'UNION_NAME', 'val': term, 'span': m.span()
            })
            
            lower_term = term.lower()
            if lower_term in self.union_geo_map:
                region, country = self.union_geo_map[lower_term]
                analysis.geo_matches.append(GeoMatch(
                    text=term, region=region, country=country, source_type="inferred_union"
                ))

        # 5. Extract Risk Terms
        for m in RISK_REGEX.finditer(text):
            analysis.risk_terms.append(m.group(0))
            analysis._matches.append({
                'type': 'RISK_TERM', 'val': m.group(0), 'span': m.span()
            })

        # 6. Extract Negation Terms
        for m in NEGATION_REGEX.finditer(text):
            analysis.negation_terms.append(m.group(0))
            analysis._matches.append({
                'type': 'NEGATION', 'val': m.group(0), 'span': m.span()
            })
            
        # 7. Extract Non-Union Terms (Specific negation)
        for m in NON_UNION_REGEX.finditer(text):
            analysis.negation_terms.append(m.group(0))
            analysis._matches.append({
                'type': 'NON_UNION', 'val': m.group(0), 'span': m.span()
            })

        # 8. Extract Geography (Explicit)
        if self.geo_regex:
            for m in self.geo_regex.finditer(text):
                phrase = m.group(0).lower()
                if phrase in self.geo_map:
                    region, country, city = self.geo_map[phrase]
                    analysis.geo_matches.append(GeoMatch(
                        text=m.group(0), region=region, country=country, city=city, source_type="explicit"
                    ))

        return analysis

    def split_sentences(self, text: str) -> List[str]:
        parts = SENTENCE_SPLIT_PATTERN.split(text)
        return [p.strip() for p in parts if p.strip()]

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