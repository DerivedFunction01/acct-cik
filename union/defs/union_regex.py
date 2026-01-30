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
from defs.regex_lib import build_compound, build_regex


class CORE(Enum):
    UNION = r"union(?:ized|i(?:z|s)ation|s)?"
    COLLECTIVE = r"collectives?"
    BARGAIN = r"bargain(?:ing|s)?"
    LABOR = r"labo(?:u)?rs?"
    ORGANIZED = r"organized?"
    FEDERATION = r"(?:con)?federations?"
    GUILD = r"guilds?"

WORKER_TERMS = [
    r"workers?",
    r"employees?",
    r"laborers?",
    r"staff",
    r"personnel",
    r"workforce",
    r"associates",
    r"miners?",
    r"auto\s*workers?",
    r"steel\s*workers?",
    r"teachers?",
    r"nurses?",
    r"pilots?",
    r"flight\s+attendants?",
    r"drivers?",
    r"machinists?",
    r"electricians?",
    r"carpenters?",
    r"plumbers?",
    r"dock\s*workers?",
    r"longshore(?:m[ae]n)",
    r"teamsters?",
    r"actors?",
    r"writers?",
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
    r"covered\s+by",
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
        # Federation + worker terms (e.g. Federation of Workers)
        build_compound([CORE.FEDERATION], WORKER_TERMS, sep_prefix=GAP),
        # Worker terms + Federation (e.g. Workers Federation)
        build_compound(WORKER_TERMS, [CORE.FEDERATION], sep_prefix=GAP),
        # Guild + worker terms (e.g. Guild of Actors)
        build_compound([CORE.GUILD], WORKER_TERMS, sep_prefix=GAP),
        # Worker terms + Guild (e.g. Actors Guild)
        build_compound(WORKER_TERMS, [CORE.GUILD], sep_prefix=GAP),
    ]

UNION_REGEX = build_regex(LABOR_TERMS.SPECIFIC_PHRASES)
