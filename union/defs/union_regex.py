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
    AMALGAMATED = r"amalgamated"
    BROTHERHOOD = r"brotherhoods?"
    STRIKE = r"strikes?"
    DISPUTE = r"disputes?"
    STOPPAGE = r"stoppages?"
    DISAGREEMENT = r"disagreements?"
    ASSOCIATION = r"associations?"
    ALLIANCE = r"alliances?"
    SOCIETY = r"societ(?:y|ies)"

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

UNION_TERMS = [
    CORE.UNION,
    CORE.FEDERATION,
    CORE.GUILD,
    CORE.AMALGAMATED,
    CORE.BROTHERHOOD,
    CORE.ASSOCIATION,
    CORE.ALLIANCE,
    CORE.SOCIETY,
]

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
        # Dynamic Union + Worker terms (e.g. Federation of Workers, Workers Union)
        build_compound(UNION_TERMS, WORKER_TERMS, sep_prefix=GAP),
        build_compound(WORKER_TERMS, UNION_TERMS, sep_prefix=GAP),
    ]

class RISK_TERMS:
    PHRASES = [
        r"labor\s+risks?",
        build_compound([CORE.LABOR, CORE.UNION], [CORE.DISPUTE, r"campaigns?", CORE.DISAGREEMENT]),
        build_compound([r"work", CORE.LABOR], [CORE.STOPPAGE, CORE.STRIKE, r"unrest"]),
        r"slowdowns?",
        r"walkouts?",
        r"union\s+organizing",
        r"efforts?\s+to\s+organize",
    ]

UNION_REGEX = build_regex(LABOR_TERMS.SPECIFIC_PHRASES)
RISK_REGEX = build_regex(RISK_TERMS.PHRASES)
