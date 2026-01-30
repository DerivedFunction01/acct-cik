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
from defs.regex_lib import build_alternation, build_compound, build_regex


class CORE(Enum):
    UNION = r"Union(?:ized|i(?:z|s)ation|s)?"
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
    r"Workforce",
    r"Associates",
    r"Miners?",
    r"(?:Dock|Steel|Auto|Metal)\s*[Ww]orkers?",
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
        # non-union(ized)
        r"non[- ]union(?:ized)?",
        # employees/workers + represented by
        build_compound(WORKER_TERMS, REPRESENTATION_TERMS, sep_prefix=GAP),
        # labor + (agreements, contracts, organizations)
        build_compound([CORE.LABOR], SUFFIX_AGREEMENTS + SUFFIX_ORGS),
        # organized labor
        build_compound([CORE.ORGANIZED], [CORE.LABOR]),
    ]


class RISK_TERMS:
    PHRASES = [
        # Union disputes, campaigns, disagreements
        build_compound([CORE.UNION], [CORE.DISPUTE, r"campaigns?", CORE.DISAGREEMENT, r"drives?", r"efforts?", r"strikes?", r"walkouts?", r"work\s+stoppages?"]),
        # Collective bargaining disputes
        build_compound(
            [CORE.COLLECTIVE, CORE.BARGAIN], [CORE.DISPUTE, CORE.DISAGREEMENT]
        ),
    ]


UNION_REGEX = build_regex(LABOR_TERMS.SPECIFIC_PHRASES)
RISK_REGEX = build_regex(RISK_TERMS.PHRASES)

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
