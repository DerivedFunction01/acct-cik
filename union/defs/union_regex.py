"""
- collective + bargain
- bargaining + (agreement, contracts)
- union / unionized
- non-union(ized)
- unionization
- employees/workers + represented by
- labor + (agreements, contracts, organizations)
- organized labor


Use enums to build core terms, then use another enum or function to build out the phrases
"""

from enum import Enum

from union.defs.regex_lib import build_compound


class CORE(Enum):
    UNION = r"union(?:ized|i(?:z|s)ation|s)?"
    COLLECTIVE = r"collectives?"
    BARGAIN = r"bargain(?:ing|s)?"
    LABOR = r"labo(?:u)?rs?"
    ORGANIZED = r"organized"

class WORKER(Enum):
    terms = [
        r"workers?",
        r"employees?",
        r"laborers?",
        r"staff",
        r"personnel",
        r"workforce",
        r"associates",
    ]

class SUFFIX(Enum):
    AGREEMENT = r"agreements?"
    CONTRACT = r"contracts?"
    ORGANIZATION = r"organizations?"
    EFFORT = r"efforts?"
    


class REPRESENTATION(Enum):
    # [workers] + [gap] + [representation]
    terms = [
        r"represented\s+by",
        r"affliat(?:ed|ion)\s+with",
    ]
GAP = r"(?:\W+(?:\w+\W+){0,2}?)"
class LABOR_TERMS:
    SPECIFIC_PHRASES = [
        # collective bargaining
        build_compound([CORE.COLLECTIVE], [CORE.BARGAIN]),
        
    ]