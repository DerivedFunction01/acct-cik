# %%
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
from defs.regex_lib import build_alternation, build_compound, build_regex, to_build_alternation
from defs.region_regex import INT_UNION_MAP


class CORE(Enum):
    UNION = r"Union(?:i(?:z|s)ed|i(?:z|s)ation|s)?"
    UNIONIZE = r"Unioni(?:z|s)(?:ation|ed)"
    ATWILL = r"At[- ]will"
    NONUNION = r"(?:non|un|not)[- ]?union(?:i(?:z|s)ed|s)?"
    REUNIONIZE = r"Re[- ]?unioni(?:z|s)(?:ations?|ed?)"
    COLLECTIVE = r"Collectives?"
    BARGAIN = r"Bargain(?:ing|s)?"
    NEGOTIATE = r"Negotiat(?:e|es|ed|ing|ions?)?"
    LABOR = r"Labo(?:u)?rs?"
    ORGANIZED = r"Organized?"
    STRIKE = r"Strikes?"
    DISPUTE = r"Disputes?"
    STOPPAGE = r"Stoppages?"
    DISAGREEMENT = r"Disagreements?"
    FEDERATION = r"(?:Con)?[Ff]ederations?"
    GUILD = r"Guilds?"
    AMALGAMATED = r"Amalgamated"
    BROTHERHOOD = r"Brotherhoods?"
    ASSOCIATION = r"Associations?"
    ALLIANCE = r"Alliances?"
    SOCIETY = r"Societ(?:y|ies)"
    UNITED = r"United"
    ORDER = r"Order\s+of"
    FRATERNAL = r"Fraternal"
    BENEVOLENT = r"Benevolent"
    LODGE = r"Lodges?"


WORKER_TERMS = [
    r"Workers?",
    r"Employees?",
    r"Labo(?:u)?rers?",
    r"Staff",
    r"Personnel",
    r"Workforces?",
    r"Associates",
    r"Miners?",
    build_compound(
        [
            r"Dock",
            r"Steel",
            r"Auto",
            r"Metal",
            r"Iron",
            r"Rail(?:road)?",
            r"Farm",
            r"Oil",
            r"Gas",
            r"Coal",
            r"Mill",
            r"Port",
            r"Plant",
            r"Warehouse",
            r"Postal",
        ],
        r"[Ww]orkers?",
        sep_prefix=r"\s*",
    ),
    r"Teachers?",
    r"Nurses?",
    r"Doctors?",
    r"Pilots?",
    r"Flight\s+Attendants?",
    r"Drivers?",
    r"Machinists?",
    r"Electricians?",
    r"Carpenters?",
    r"Plumbers?",
    r"Longshore(?:m[ae]n)",
    r"Patrolm[ae]n(?:'s)?",
    r"Sheriffs?(?:'s)?",
    r"Police",
    r"Teamsters?",
    r"Actors?",
    r"Writers?",
    r"Instructors?",
    r"Engineers?",
    r"Dispatchers?",
    r"Mechanics?",
    r"Technicians?",
    r"Operators?",
    r"Custodians?",
    r"Janitors?",
    r"(?:Security|Police)\s+(?:[Gg]uards?|[Oo]ficers?)",
    r"Fabricators?",
    r"Assemblers?",
    r"Welders?",
    r"Pipefitters?",
    r"Boilermakers?",
    r"Millwrights?",
    r"Labor\s+[Ff]orce",
    r"Chefs?",
    r"Cook(?:er)?s?",
]
NOUNS = [
    r"whom?",
    r"the(?:m|y)",
    r"th(?:e|o)se"
]
SUFFIX_AGREEMENTS = [r"agreements?", r"contracts?", r"arrangements?", r"memberships?", r"representations?"]

SUFFIX_ORGS = [
    r"organizations?",
]

REPRESENTATION_TERMS = [
    r"represented",  # removed by
    r"affiliat(?:ed|ion)",  # removed with
    r"covered",  # removed by
]

GAP = r"(?:'s?)?(?:\s+(?:of|the|for|&|[A-Z][\'\w-]*)){0,3}\s+"


# Expansion patterns for full name capture (e.g. "United" in "United Auto Workers")
TITLE_PREFIX = r"(?:[A-Z][\'\w-]*\s+)*"
TITLE_SUFFIX = r"(?:\s+[A-Z][\'\w-]*)*"

UNION_TERMS = [
    CORE.UNION,
    CORE.FEDERATION,
    CORE.GUILD,
    CORE.AMALGAMATED,
    CORE.BROTHERHOOD,
    CORE.ASSOCIATION,
    CORE.ALLIANCE,
    CORE.SOCIETY,
    CORE.UNITED,
    CORE.ORDER,
    CORE.FRATERNAL,
    CORE.BENEVOLENT,
    CORE.LODGE,
]

_foreign_dynamic = []
FOREIGN_DYNAMIC_PATTERNS = {}

for code, (workers, unions, gap) in INT_UNION_MAP.items():
    if workers and unions:
        # Build specific pattern for this language code
        p_workers = build_compound(unions, workers, sep_prefix=gap)
        p_unions = build_compound(unions, unions, sep_prefix=gap)
        _foreign_dynamic.extend([p_workers, p_unions])
        FOREIGN_DYNAMIC_PATTERNS[code] = build_regex([p_workers, p_unions], ignore_case=True)

_CORE_DYNAMIC_PATTERN = build_alternation(
    [
        build_compound(UNION_TERMS, WORKER_TERMS, sep_prefix=GAP),
        build_compound(WORKER_TERMS, UNION_TERMS, sep_prefix=GAP),
        build_compound(UNION_TERMS, CORE.UNION.value, sep_prefix=GAP),
    ] + _foreign_dynamic
)
DYNAMIC_UNION_PATTERN = f"{TITLE_PREFIX}{_CORE_DYNAMIC_PATTERN}{TITLE_SUFFIX}"

DYNAMIC_UNION_REGEX = build_regex([DYNAMIC_UNION_PATTERN], ignore_case=False)

# Regex to capture comma-separated worker titles preceding a union name
# e.g. "Teachers, Instructors and " before "Writers Association"
# Enforces that the terms are valid WORKER_TERMS to avoid capturing unrelated capitalized text.
_worker_term_alt = to_build_alternation(set(WORKER_TERMS) - {r"Teamsters?"})
_prefix_sep = r"(?:,\s*(?:(?:and|&)\s+)?|\s+(?:and|&)\s+|\s+)"
LOOSE_TITLE_PREFIX_REGEX = re.compile(rf"(?:{_worker_term_alt}{_prefix_sep})+$")

COLLECTIVE_BARGAIN = build_alternation(
    [
        build_compound(
            [CORE.COLLECTIVE, CORE.LABOR, CORE.UNION],
            [CORE.BARGAIN, CORE.LABOR, CORE.NEGOTIATE],
            sep_prefix=r"[\s-]+",
        ),
        build_compound(
            [CORE.BARGAIN, CORE.UNION], SUFFIX_AGREEMENTS, sep_prefix=r"[\s-]+"
        ),
        build_compound(
            [CORE.BARGAIN], [r"units?"], sep_prefix=r"[\s-]+"
        ),
        build_compound([r"industry(?:[- ]wide)?"], [CORE.BARGAIN])
    ]
)
UNION_PHRASES = [
    # collective + bargain + agreement
    COLLECTIVE_BARGAIN,
    # union / unionized / unionization
    CORE.UNION.value,
    # reunionize, re-unionization,
    CORE.REUNIONIZE.value,
    # employees/workers + represented by
    build_compound(WORKER_TERMS, REPRESENTATION_TERMS, sep_prefix=GAP),
    # labor + (agreements, contracts, organizations)
    build_compound(
        [CORE.LABOR],
        SUFFIX_AGREEMENTS + SUFFIX_ORGS + [CORE.UNION],
        sep_prefix=r"[\s-]+",
    ),
    # organized labor
    build_compound([CORE.ORGANIZED], [CORE.LABOR], sep_prefix=r"[\s-]+"),
]

MEMBERSHIP_PHRASES = [
    CORE.UNIONIZE,
    COLLECTIVE_BARGAIN,
    build_compound([CORE.LABOR, CORE.UNION], [r"representations?", r"affiliations?"]),
    build_compound([r"worker", r"employee"], [r"representations?"]),
    r"(?:union\s+)?memberships?",
    r"affiliations?",
]

DIVERSITY_TERMS = [
    r"(?:wo)?m(?:e|a)n",
    r"females?",
    r"males?",
    r"gender",
    r"diversity",
    r"inclusion",
    r"minorit(?:y|ies)",
    r"ethnic(?:ity|ally)?",
    r"races?",
    r"racial(?:ly)",
    r"veterans?",
    r"disabilit(?:y|ies)",
    r"disabled",
    r"sexual\s+orientation",
    r"people\s+of\s+color",
    r"african\s+american",
    r"hispanics?",
    r"latin(?:o|a|x)?s?",
    r"asians?",
    r"whites?",
    r"blacks?",
    r"indigenous",
    r"lgbtq?",
    r"underrepresented",
    build_compound(r"gen(?:eration|\.)?", [r"Z", r"X", r"Y", r"W"]),
    r"Millennials?",
    r"Baby\s+Boomers?",
    r"Traditionalists?",
]

class LABOR_TERMS:
    SPECIFIC_PHRASES = UNION_PHRASES + [CORE.NONUNION.value]

class RISK_TERMS:
    PHRASES = [
        # Union disputes, campaigns, disagreements
        build_compound(
            [CORE.UNION, CORE.REUNIONIZE],
            [
                CORE.DISPUTE,
                r"campaigns?",
                CORE.DISAGREEMENT,
                CORE.NEGOTIATE,
                r"drives?",
                r"efforts?",
                r"strikes?",
                r"walkouts?",
                r"work\s+stoppages?",
            ],
        ),
        # Collective bargaining disputes
        build_compound(
            [CORE.BARGAIN], [CORE.DISPUTE, CORE.DISAGREEMENT]
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
    r"stances?\b",
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
RELATIONSHIP_QUALITY_REGEX = build_regex(
    RELATIONSHIP_QUALITY_TERMS
    + RELATIONSHIP_NEGATIVE_TERMS
    + RELATIONSHIP_NEUTRAL_TERMS
)

BOILERPLATE_TERMS = ["monitor", "committed", "constructive", "engagement", "relations", "closely", "publically", "disclose", "disclosure", "believe(?:s|d)?"]
BOILERPLATE_REGEX = build_regex(BOILERPLATE_TERMS)

UNION_REGEX = build_regex(LABOR_TERMS.SPECIFIC_PHRASES)
RISK_REGEX = build_regex(RISK_TERMS.PHRASES)

NEGATION_TERMS = [
    r"no",
    r"not",
    r"non",
    r"un",
    r"neither",
    r"nor",
    r"never",
    r"without",
    r"none",
]

COVERAGE_TERMS = [
    r"represent(?:ed|tion)",
    r"covered",
    r"affiliat(?:ed|ion)",
    r"union(?:ized)?",
    r"subject\s+to",
    r"(?:are|were)\s+under",
    r"members?\s+of",
] + SUFFIX_AGREEMENTS
COVERAGE_REGEX = build_regex(COVERAGE_TERMS)

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
    CORE.ATWILL,
    r"operate(?:s|d)?\s+outside",
    r"decertif(?:ied|y|ications?)",
    r"not\s+under",
    build_compound(
        NEGATION_TERMS, COVERAGE_TERMS + WORKER_TERMS + UNION_PHRASES, sep_prefix=GAP
    ),
]
NON_COVERAGE_REGEX = build_regex(NON_COVERAGE_PHRASES)

# Negation patterns
NON_UNION_REGEX = build_regex([CORE.NONUNION])

# Exclusion patterns to discard entire paragraphs
EXCLUSION_MAP = {
    "MONETARY": [
        r"monetary\s+unions?",
        r"currency\s+unions?",
        r"customs\s+unions?",
    ],

    "MEDICAL": [
        r"fractures?",
        r"clinical",
        r"bones?",
        r"bacterial?",
        r"phages?",
        r"viral",
        r"patients?",
        r"surg(?:er(?:y|ies)|ical)"
        r"spinal",
        r"bleeding",
        r"blood",
        r"pain",
        r"infections?",
        r"muscles?",
        r"injur(?:y|ies)",
        r"knee",
        r"hips?",
        r"elbows?",
        r"shoulders?",
        r"wrists?",
        r"ankles?",
        r"marrow",
        r"cancers?",
        r"genetics?",
        r"tissues?",
        r"strokes?"
        r"heart",
        r"diseases?",
    ],
    "COMPENSATION": [
        r"stock\s+options?",
        r"restricted\s+stock\s+units?",
        r"performance\s+shares?",
        r"executive\s+officers?",
        r"equity\s+incentive\s+plans?",
        r"strike\s+prices?",
        r"exercise\s+prices?",
        r"board\s+of\s+directors?"
    ]
}

_exclusion_patterns = []
for terms in EXCLUSION_MAP.values():
    _exclusion_patterns.extend(terms)

EXCLUSION_REGEX = build_regex(_exclusion_patterns)

# %%
def run_test():
    print(f"Testing DYNAMIC_UNION_REGEX pattern...")
    examples = [
        # Should Match
        "International Brotherhood of Teamsters",
        "Screen Actors Guild",
        "American Federation of Teachers",
        "United Steelworkers Union",
        "United Air Alliance",
        "Air Line Pilots Association",
        "National Ironworkers Alliance",
        # Boundary / Punctuation Checks
        "The workers. Union officials said no.",  # Sentence boundary
        "The workers, Union officials said no.",  # Comma boundary
        "The workers and Union officials.",  # 'and' boundary
        # Tricky / Negative cases (should be good via cleaner)
        "State of the Union",
        "Credit Union",
    ]

    for ex in examples:
        matches = DYNAMIC_UNION_REGEX.findall(ex)
        print(f"Input:  {ex}")
        print(f"Match:  {matches}")
        print("-" * 20)

    # 3. Personnel Events (Hiring, Firing, Furlough)
PERSONNEL_EVENT_TERMS = [
    r"furlough(?:s|ed|ing)?",
    r"recall(?:s|ed|ing)?",
    r"hir(?:es?|ed|ing)",
    r"fir(?:es?|ed|ing)",
    r"layoffs?",
    r"lay(?:ing)?\s+off",
    r"laid\s+off",
    r"terminat(?:es?|ed|ing|ions?)",
    r"recruit(?:s|ed|ing|ment)?",
    r"redundanc(?:y|ies)",
    r"severance",
    r"retention",
    r"turnover",
    r"attritions?",
    r"headcount\s+reductions?",
    r"job\s+cuts?",
    r"eliminat(?:es?|ed|ing|ions?)",
    r"downsiz(?:es?|ed|ing)",
    r"separat(?:es?|ed|ing|ions?)",
    r"reduc(?:es?|ed|ing|tions?)",
]

CHANGE_TERMS = [
    # Increase / Growth
    r"increase(?:s|d|ing)?",
    r"growth",  # noun only
    r"grow(?:s|n|ing)?",
    r"rise(?:s|r|n|ing|d)?",
    r"gain(?:s|ed|ing)?",
    r"improv(?:es?|ed|ing|ements?)",
    # Decrease / Decline
    r"decrease(?:s|d|ing)?",
    r"declin(?:e|es|ed|ing)?",
    r"drop(?:s|ped|ping)?",
    r"loss(?:es)?",
    r"reduc(?:es?|ed|ing|tions?)",
    # Appreciation / Depreciation
    r"appreciat(?:es?|ed|ing|ions?)",
    r"depreciat(?:es?|ed|ing|ions?)",
    # Offset
    r"offset(?:s|ted|ting)?",
    # Higher / Lower (comparatives)
    r"higher",
    r"lower",
    # Change (generic)
    r"chang(?:es?|ed|ing)",
    # Transition
    r"transition(?:s|ed|ing)?",
]

PERSONNEL_EVENT_REGEX = build_regex(PERSONNEL_EVENT_TERMS)
