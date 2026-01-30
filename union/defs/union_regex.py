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
from union.defs.regex_lib import build_compound, build_regex


class CORE(Enum):
    UNION = r"union(?:ized|i(?:z|s)ation|s)?"
    COLLECTIVE = r"collectives?"
    BARGAIN = r"bargain(?:ing|s)?"
    LABOR = r"labo(?:u)?rs?"
    ORGANIZED = r"organized?"

WORKER_TERMS = [
    r"workers?",
    r"employees?",
    r"laborers?",
    r"staff",
    r"personnel",
    r"workforce",
    r"associates",
]

SUFFIX_AGREEMENTS = [
    r"agreements?",
    r"contracts?",
]

SUFFIX_ORGS = [
    r"organizations?",
]

REPRESENTATION_TERMS = [
    r"represented\s+by",
    r"affliat(?:ed|ion)\s+with",
]

GAP = r"(?:\W+(?:\w+\W+){0,3}?)"

class LABOR_TERMS:
    SPECIFIC_PHRASES = [
        # collective + bargain
        build_compound([CORE.COLLECTIVE], [CORE.BARGAIN]),
        # bargaining + (agreement, contracts)
        build_compound([CORE.BARGAIN], SUFFIX_AGREEMENTS),
        # union / unionized / unionization
        CORE.UNION.value,
        # non-union(ized)
        r"non[- ]union(?:ized)?",
        # employees/workers + represented by
        build_compound(WORKER_TERMS, REPRESENTATION_TERMS, sep_prefix=GAP),
        # labor + (agreements, contracts, organizations)
        build_compound([CORE.LABOR], SUFFIX_AGREEMENTS + SUFFIX_ORGS),
        # organized labor
        build_compound([CORE.ORGANIZED], [CORE.LABOR]),
        # Efforts to organize
        r"efforts?\s+to\s+organize",
    ]

UNION_REGEX = build_regex(LABOR_TERMS.SPECIFIC_PHRASES)
