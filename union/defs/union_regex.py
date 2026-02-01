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
import re
from defs.regex_lib import build_alternation, build_compound, build_regex


class CORE(Enum):
    UNION = r"(?:re[- ])?Union(?:ized|i(?:z|s)ation|s)?"
    NONUNION = r"(?:non|un|not)[- ]?union(?:ized)?s?"
    REUNIONIZE = r"Re[- ]?unioni(?:z|s)(?:ations?|ed?)"
    COLLECTIVE = r"Collectives?"
    BARGAIN = r"Bargain(?:ing|s)?"
    LABOR = r"Labo(?:u)?rs?"
    ORGANIZED = r"Organized?"
    FEDERATION = r"(?:Con)?[Ff]ederations?"
    GUILD = r"Guilds?"
    AMALGAMATED = r"Amalgamated"
    BROTHERHOOD = r"Brotherhoods?"
    STRIKE = r"Strikes?"
    DISPUTE = r"Disputes?"
    STOPPAGE = r"Stoppages?"
    DISAGREEMENT = r"Disagreements?"
    ASSOCIATION = r"Associations?"
    ALLIANCE = r"Alliances?"
    SOCIETY = r"Societ(?:y|ies)"

WORKER_TERMS = [
    r"Workers?",
    r"Employees?",
    r"Laborers?",
    r"Staff",
    r"Personnel",
    r"Workforces?",
    r"Associates",
    r"Miners?",
    r"(?:Dock|Steel|Auto|Metal|Iron|Auto)\s*[Ww]orkers?",
    r"Teachers?",
    r"Nurses?",
    r"Pilots?",
    r"Flight\s+Attendants?",
    r"Drivers?",
    r"Machinists?",
    r"Electricians?",
    r"Carpenters?",
    r"Plumbers?",
    r"Longshore(?:m[ae]n)",
    r"Teamsters?",
    r"Actors?",
    r"Writers?",
    r"Instructors?",
    r"Engineers?",
    r"Dispatchers?",
    r"Mechanics?"
    r"Technicians?",
    r"Operators?",
    r"Custodians?",
    r"Janitors?",
    r"Security\s+(?:[Gg]uards?|[Oo]ficers?)",
    r"Warehouse\s+Workers?",
    r"Fabricators?",
    r"Assemblers?",
    r"Welders?",
    r"Pipefitters?",
    r"Boilermakers?",
    r"Millwrights?",
    r"Labor\s+Force"
]
NOUNS = [
    r"whom?",
    r"the(?:m|y)",
    CORE.UNION.value
]
SUFFIX_AGREEMENTS = [
    r"agreements?",
    r"contracts?",
    r"arrangements?"
]

SUFFIX_ORGS = [
    r"organizations?",
]

REPRESENTATION_TERMS = [
    r"represented\s+by",
    r"affliat(?:ed|ion)\s+with",
    r"covered\s+by",
]

GAP = r"(?:\s+(?:of|the|for|&|[A-Z][\w-]*)){0,3}\s+"


# Expansion patterns for full name capture (e.g. "United" in "United Auto Workers")
TITLE_PREFIX = r"(?:[A-Z][\w-]*\s+)*"
TITLE_SUFFIX = r"(?:\s+[A-Z][\w-]*)*"

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

_CORE_DYNAMIC_PATTERN = build_alternation([
    build_compound(UNION_TERMS, WORKER_TERMS, sep_prefix=GAP),
    build_compound(WORKER_TERMS, UNION_TERMS, sep_prefix=GAP),
])
DYNAMIC_UNION_PATTERN = f"{TITLE_PREFIX}{_CORE_DYNAMIC_PATTERN}{TITLE_SUFFIX}"

DYNAMIC_UNION_REGEX = build_regex([DYNAMIC_UNION_PATTERN], ignore_case=False)

class LABOR_TERMS:
    SPECIFIC_PHRASES = [
        # collective + bargain
        build_compound([CORE.COLLECTIVE], [CORE.BARGAIN]),
        # bargaining + (agreement, contracts)
        build_compound([CORE.BARGAIN], SUFFIX_AGREEMENTS),
        # union / unionized / unionization
        CORE.UNION.value,
        # reunionize, re-unionization, 
        CORE.REUNIONIZE.value,
        # non-union(ized)
        CORE.UNION.value, 
        # employees/workers + represented by
        build_compound(WORKER_TERMS, REPRESENTATION_TERMS, sep_prefix=GAP),
        # labor + (agreements, contracts, organizations)
        build_compound([CORE.LABOR], SUFFIX_AGREEMENTS + SUFFIX_ORGS + [CORE.UNION]),
        # organized labor
        build_compound([CORE.ORGANIZED], [CORE.LABOR]),
    ]


class RISK_TERMS:
    PHRASES = [
        # Union disputes, campaigns, disagreements
        build_compound([CORE.UNION, CORE.REUNIONIZE], [CORE.DISPUTE, r"campaigns?", CORE.DISAGREEMENT, r"drives?", r"efforts?", r"strikes?", r"walkouts?", r"work\s+stoppages?"]),
        # Collective bargaining disputes
        build_compound(
            [CORE.COLLECTIVE, CORE.BARGAIN], [CORE.DISPUTE, CORE.DISAGREEMENT]
        ),
    ]


RELATIONSHIP_QUALITY_TERMS = [
    "good",
    "satisfactory",
    "positive",
    "strong",
    "excellent",
    "favorable",
    "constructive",
    "cooperative",
    "harmonious",
    "cordial",
    "mutually beneficial",
    "beneficial",
    "productive",
    "stable",
    "respectful",
]

RELATIONSHIP_NEGATIVE_TERMS = [
    "poor",
    "strained",
    "difficult",
    "tense",
    "adversarial",
    "hostile",
    "challenging",
    "volatile",
    "unstable",
    "disruptive",
    "uncooperative",
]
RELATIONSHIP_NEUTRAL_TERMS = [
    r"neutral",
    r"mutual",    
    r"normal",
    r"standard",
    r"ordinary",
]

RELATIONSHIP_SUBJECTS = [
    r"relations\b",
    r"relationships?\b",
    r"communications?\b",
    r"engagement\b",
    r"dialogue\b",
    r"stances?\b"
]

RELATIONSHIP_PHRASES = [
    # "Employee relations", "Labor relations", "Union relations"
    build_compound(
        WORKER_TERMS + [CORE.LABOR, CORE.UNION], RELATIONSHIP_SUBJECTS, sep_prefix=GAP
    ),
    # "Relations with employees", "Relationship with the union"
    build_compound(
        RELATIONSHIP_SUBJECTS,
        [r"with"] + WORKER_TERMS + [CORE.LABOR, CORE.UNION],
        sep_prefix=GAP,
    ),
    # cordial relationship
    build_compound(
        RELATIONSHIP_QUALITY_TERMS
        + RELATIONSHIP_NEGATIVE_TERMS
        + RELATIONSHIP_NEUTRAL_TERMS,
        RELATIONSHIP_SUBJECTS,
        sep_prefix=GAP,
    ),
    # "Working relationship"
    r"working\s+relationships?",
]

RELATIONSHIP_REGEX = build_regex(RELATIONSHIP_PHRASES)
# Match both positive and negative terms; analysis will distinguish them
RELATIONSHIP_QUALITY_REGEX = build_regex(RELATIONSHIP_QUALITY_TERMS + RELATIONSHIP_NEGATIVE_TERMS + RELATIONSHIP_NEUTRAL_TERMS)

BOILERPLATE_TERMS = [
    "monitor", "committed", "constructive", "engagement", "relations"
]
BOILERPLATE_REGEX = build_regex(BOILERPLATE_TERMS)


UNION_REGEX = build_regex(LABOR_TERMS.SPECIFIC_PHRASES)
RISK_REGEX = build_regex(RISK_TERMS.PHRASES)

NEGATION_TERMS = [
    r"no", r"not", r"non", r"un", r"neither", r"nor", r"never", r"without", r"none"
]

COVERAGE_TERMS = [
    r"represented",
    r"covered",
    r"affiliat(?:ed|ion)",
    r"union(?:ized)?",
    r"collective\s+bargaining",
    r"agreements?",
    r"contracts?",
    r"arrangements?",
]

SUPPLIER_TERMS = [
    r"suppliers?",
    r"vendors?",
    r"third\s+part(?:y|ies)",
    r"contractors?",
    r"sub[- ]?contractors?",
    r"supply\s+chain",
    r"outsourc(?:e|ed|ing|es)",
    r"service\s+providers?",
    r"customers?",
]
SUPPLIER_REGEX = build_regex(SUPPLIER_TERMS)

NON_COVERAGE_PHRASES = [
    r"at[- ]will",
    r"operate(?:s|d)?\s+outside",
    r"decertif(?:ied|y|ications?)",
    build_compound(NEGATION_TERMS, COVERAGE_TERMS + WORKER_TERMS, sep_prefix=r"[- ]?"),
]
NON_COVERAGE_REGEX = build_regex(NON_COVERAGE_PHRASES)

# Negation patterns
NON_UNION_REGEX = build_regex([CORE.NONUNION])

def run_test():
    print(f"Testing DYNAMIC_UNION_REGEX pattern...")
    
    examples = [
        # Should Match
        "International Brotherhood of Teamsters",
        "Screen Actors Guild",
        "American Federation of Teachers",
        "United Steelworkers Union",
        "Air Line Pilots Association",
        
        # Boundary / Punctuation Checks
        "The workers. Union officials said no.",  # Sentence boundary
        "The workers, Union officials said no.",  # Comma boundary
        "The workers and Union officials.",       # 'and' boundary
        
        # Tricky / Negative cases (should be good via cleaner)
        "State of the Union",
        "Credit Union",
    ]
    
    for ex in examples:
        matches = DYNAMIC_UNION_REGEX.findall(ex)
        print(f"Input:  {ex}")
        print(f"Match:  {matches}")
        print("-" * 20)
