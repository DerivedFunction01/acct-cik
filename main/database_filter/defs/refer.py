# Exhibit/Reference nouns
from defs.regex_lib import build_alternation

EXHIBIT_NOUNS = [
    "exhibits",
    "references",
    "note",
    "appendix",
    "schedule",
    "article",
    "section",
    "subsection",
    "statement",
    "table",
    "No.",
    "page",
    "pp.",
    "p.",
    "figure",
    "chart",
]
EXHIBIT_FRAGMENT = build_alternation(EXHIBIT_NOUNS)
