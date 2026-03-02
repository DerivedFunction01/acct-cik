from typing import Any, Dict, List, Optional
import re
from regex_lib import build_compound, build_regex
from union_regex import COVERAGE_REGEX, NON_COVERAGE_REGEX, CORE, NON_UNION_REGEX, WORKER_TERMS

SPACE_REGEX = re.compile(r"\s+")
NULL_HEADER_REGEX = re.compile(r"^(?:-|—|n/?a|na)$", re.IGNORECASE)


"""
# Header Classification for Employment Tables

## 1. Numbers to Keep (Primary Data)
These are the core metrics we want to extract as quantitative data.
- **Union/Employee Counts** Note that it works with  | Union name| Number of Employees|:
    - "Employees", "Headcount", "Workforce", "Staff"
    - "Full-time", "Part-time", "Multi-year (ie 2018 vs 2019 -> Ignore the previous year)". 
    - Total vs Subset: 100 vs 200 total. This is much simplier if written as 100 of 200 to avoid having
        complex parsing strategies for the analyzer.
- **Bargaining Units**:
    - "Number of Bargaining Units" (Keep this count as it proxies for organizational complexity)
    -  Needs to be reordered so that the extraction.py sees it as XX bargaining units, rather than bargaining units is X.

## 2. Numbers to Strip or Reorder (Contextual/Metadata)
These numbers describe the structure but aren't the workforce counts themselves.
- **Contract Counts**:
    - "Number of Labor Contracts", "Number of CBAs", "Number of Unions"
    - *Action*: Generally ignore the number value to avoid confusing it with employee counts, but preserve the header context (implies union presence).
- **Dates/Years**:
    - "Expiration Date", "Amendable", "effective", "start"
    -  Drop this row, as the analyzer may see the wrong year, or the extractor will suppress "amendable"

## 3. Percentages (Coverage Rates)
- "% of Total", "% Unionized"
    - One count, one percent needs to know that if it was a count is total vs subset.

## 4. Text only cells:
    - Refering to geography, worker type, or union name.
    - If one data cell is a union, the rest of that column probably also is a union.

# Header simplication or categorization.
- Number of Employees -> Employees.

# Figure out the categorization to write natural sentences.
Ex. Employees = 500 -> We have 500 employees.
"""

# The table processor should have already set the year, we can probably have that dropped for multi-year data.
HEADER_PATTERNS = {
    "counts": build_regex(set(WORKER_TERMS + []) - {r"Teamsters?"}), # Or other rows that have numbers and not years.
    "bu": build_regex(
        [
            build_compound([CORE.BARGAIN], [r"units?"], sep_prefix=r"[\s-]+"),
        ]
    ),
    "union_contract_counts": build_regex(
        [
            build_compound(
                [CORE.LABOR, CORE.UNION, CORE.BARGAIN],
                [
                    r"agreements?",
                    r"contracts?",
                    r"arrangements?",
                ],
            ),
        ]
    ),
    "generic_contract_counts": build_regex(
        [
            r"agreements?",
            r"contracts?",
            r"arrangements?",
        ]
    ),
    "coverage": COVERAGE_REGEX,  # Bypasses contract counts -> covered by labor agreements = emp total, # covered by bu = emp count
    "non_coverage": NON_COVERAGE_REGEX, # Not covered
    "unionized": build_regex([r"unionized"]), # Unionized
    "nonunion": NON_UNION_REGEX, # Non-unionized
    "number": build_regex([r"number\s+of"]), # So we know if contract counts is explicity number of if needed.
    "percent": build_regex([r"%", r"percent(?:ages?|s)?"]) # The data cell should be in percents anyways.
}

DATE_META_REGEX = build_regex(
    [
        r"effective",
        r"expiration",
        r"expires?",
        r"amendable",
        r"start(?:ing)?\s+date",
        r"end(?:ing)?\s+date",
        r"ratification",
        r"year(?:s)?\s+ended",
        r"term",
        r"duration",
    ],
)
GENERIC_META_REGEX = build_regex(
    [
        r"notes?",
        r"description",
        r"comments?",
        r"status",
    ]
)
HEADER_CLASS_ORDER = [
    "date_meta",
    "union_contract_counts",
    "generic_contract_counts",
    "bu",
    "non_coverage",
    "coverage",
    "counts",
    "percent",
]


def render_employee_sentence(
    group: Dict[str, Any],
    row_info: Dict[str, Any],
    context: Dict[str, Any],
) -> Optional[str]:
    """
    Custom renderer skeleton for employment-focused table sentences.

    This is designed to be passed into:
        generate_primitive_sentences(processed_table, renderer=render_employee_sentence)
    """
    if not group or not row_info:
        return None

    items = group.get("items", [])
    if not items:
        return None

    year = _resolve_year(group=group, row_info=row_info, context=context)
    header_ctx = _digest_headers(items)
    value_ctx = _digest_values(items)

    # TODO: Replace with richer employment-specific templates.
    return _render_template(
        label=row_info.get("label", ""),
        year=year,
        header_ctx=header_ctx,
        value_ctx=value_ctx,
    )


def _resolve_year(
    group: Dict[str, Any],
    row_info: Dict[str, Any],
    context: Dict[str, Any],
) -> Optional[int]:
    """
    Priority can be adjusted later if needed.
    """
    return group.get("year") or row_info.get("row_year") or context.get("caption_year")


def _digest_headers(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse/normalize headers and expose structured metadata for templates.
    Input shape is aligned with table_sentences items:
      {"val": "...", "type": "value|percentage|text|...", "header": "..."}
    """
    raw_headers = [i.get("header", "").strip() for i in items if i.get("header")]
    unique_headers: List[str] = []
    seen = set()
    for header in raw_headers:
        normalized = _normalize_header(header)
        if normalized and normalized not in seen:
            unique_headers.append(normalized)
            seen.add(normalized)

    per_item: List[Dict[str, Any]] = []
    class_counts: Dict[str, int] = {}
    for i in items:
        raw = i.get("header", "")
        normalized = _normalize_header(raw)
        category = _classify_header(normalized, i.get("type"))

        if category:
            class_counts[category] = class_counts.get(category, 0) + 1

        per_item.append(
            {
                "header": normalized,
                "category": category,
                "type": i.get("type"),
                "val": i.get("val", ""),
            }
        )

    categories_present = sorted(class_counts.keys())
    informative_categories = {
        "counts",
        "coverage",
        "non_coverage",
        "bu",
        "percent",
    }
    dropped_categories = {"date_meta", "generic_meta"}

    return {
        "raw": raw_headers,
        "unique": unique_headers,
        "has_headers": bool(unique_headers),
        "per_item": per_item,
        "class_counts": class_counts,
        "categories_present": categories_present,
        "has_informative_headers": any(c in informative_categories for c in categories_present),
        "has_only_meta_headers": bool(categories_present) and all(c in dropped_categories for c in categories_present),
        "dimensions": {},
    }


def _normalize_header(header: str) -> str:
    """
    Lightweight normalization for employment-oriented header text.
    """
    if not header:
        return ""

    header = SPACE_REGEX.sub(" ", header).strip(" ,;:-")
    return header


def _classify_header(header: str, item_type: Optional[str]) -> str:
    """
    Categorize one header for sentence rendering.
    """
    if not header or NULL_HEADER_REGEX.match(header):
        return "unknown"

    if DATE_META_REGEX.search(header):
        return "date_meta"
    if GENERIC_META_REGEX.search(header):
        return "generic_meta"

    for klass in HEADER_CLASS_ORDER:
        pattern = HEADER_PATTERNS.get(klass)
        if pattern and pattern.search(header):
            return klass

    # If column type is percentage and no explicit header class matched,
    # keep a lightweight category so templates can still reason about it.
    if item_type == "percentage":
        return "percent"

    return "unknown"


def _digest_values(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Split values by type for downstream template logic.
    """
    values = [i.get("val", "") for i in items if i.get("type") in {"value", "dollar"}]
    percents = [i.get("val", "") for i in items if i.get("type") == "percentage"]
    text_values = [i.get("val", "") for i in items if i.get("type") == "text"]

    return {
        "all": [i.get("val", "") for i in items],
        "values": [v for v in values if v],
        "percents": [p for p in percents if p],
        "text": [t for t in text_values if t],
        # TODO: Add numeric normalization if needed (int/float extraction).
    }


def _render_template(
    label: str,
    year: Optional[int],
    header_ctx: Dict[str, Any],
    value_ctx: Dict[str, Any],
) -> Optional[str]:
    """
    Temporary baseline template.
    """
    if not label:
        return None

    values = value_ctx.get("all", [])
    if not values:
        return None

    head = f"In {year}, " if year else ""

    if header_ctx.get("has_only_meta_headers"):
        return None

    headers = [
        h["header"]
        for h in header_ctx.get("per_item", [])
        if h.get("header")
        and h.get("category") not in {"date_meta", "generic_meta", "generic_contract_counts"}
    ]
    # Preserve order while de-duplicating
    deduped_headers: List[str] = []
    seen_headers = set()
    for h in headers:
        if h not in seen_headers:
            deduped_headers.append(h)
            seen_headers.add(h)

    if deduped_headers:
        return f"{head}{label} ({', '.join(deduped_headers)}) was {' '.join(values)}."

    return f"{head}{label} was {' '.join(values)}."
