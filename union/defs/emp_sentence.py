from typing import Any, Dict, List, Optional
from functools import lru_cache
import re
from defs.regex_lib import build_compound, build_regex
from defs.union_regex import (
    COVERAGE_REGEX,
    NON_COVERAGE_REGEX,
    CORE,
    DYNAMIC_UNION_REGEX,
    NON_UNION_REGEX,
    UNION_REGEX,
    WORKER_TERMS,
)
from defs.region_regex import RegionMatcher

SPACE_REGEX = re.compile(r"\s+")
NULL_HEADER_REGEX = re.compile(r"^(?:-|—|n/?a|na)$", re.IGNORECASE)
SPLIT_HINT_REGEX = re.compile(r"[|/;,]")
CONTRACT_CONTEXT_REGEX = build_regex(
    [
        build_compound([CORE.LABOR, CORE.UNION, CORE.BARGAIN], [r"agreements?", r"contracts?", r"arrangements?"]),
        r"collective\s+bargain(?:ing)?\s+agreements?",
        r"cba(?:s)?",
    ]
)
REGION_MATCHER = RegionMatcher()


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
    "union_name": build_regex([r"^unions?(?:\s+\(.*\))?$", r"labor\s+organizations?"]),
    "percent": build_regex([r"%", r"percent(?:ages?|s)?"]) # The data cell should be in percents anyways.
}

DATE_META_REGEX = build_regex(
    [
        r"effective",
        r"expiration",
        r"expires?",
        r"amendments?",
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
    "union_name",
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
    non_date = [i.get("val", "") for i in items if i.get("type") != "date"]

    return {
        "all": [i.get("val", "") for i in items],
        "non_date": [v for v in non_date if v],
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

    values = value_ctx.get("non_date", []) or value_ctx.get("all", [])
    if not values:
        return None

    head = f"In {year}, " if year else ""

    metrics = _extract_metrics(header_ctx)
    hints = _extract_text_hints(label=label, header_ctx=header_ctx, value_ctx=value_ctx)
    context_suffix = _minimal_union_context_suffix(header_ctx, hints)
    union_name_segment = _union_name_segment(hints)

    metric_sentence = _render_metric_sentence(label, metrics)
    if metric_sentence:
        segments = [metric_sentence]
        for segment in [context_suffix, union_name_segment]:
            if segment and segment not in segments:
                segments.append(segment)
        return f"{head}{', '.join(segments)}."

    if header_ctx.get("has_only_meta_headers"):
        if context_suffix:
            tail = context_suffix
            if union_name_segment:
                tail = f"{tail}, {union_name_segment}"
            return f"{head}{label} reported {tail}."
        return None

    headers = [
        h["header"]
        for h in header_ctx.get("per_item", [])
        if h.get("header")
        and h.get("category") not in {"date_meta", "generic_meta", "generic_contract_counts", "union_name"}
    ]
    # Preserve order while de-duplicating
    deduped_headers: List[str] = []
    seen_headers = set()
    for h in headers:
        if h not in seen_headers:
            deduped_headers.append(h)
            seen_headers.add(h)

    if deduped_headers:
        base = f"{label} ({', '.join(deduped_headers)}) was {' '.join(values)}"
        for segment in [context_suffix, union_name_segment]:
            if segment and segment not in base:
                base = f"{base}, {segment}"
        return f"{head}{base}."

    base = f"{label} was {' '.join(values)}"
    for segment in [context_suffix, union_name_segment]:
        if segment and segment not in base:
            base = f"{base}, {segment}"
    return f"{head}{base}."


def _extract_metrics(header_ctx: Dict[str, Any]) -> Dict[str, Optional[str]]:
    per_item = header_ctx.get("per_item", [])
    metrics: Dict[str, Optional[str]] = {
        "covered": None,
        "non_covered": None,
        "total": None,
        "pct": None,
        "bu": None,
    }

    for item in per_item:
        val = (item.get("val") or "").strip()
        category = item.get("category")
        item_type = item.get("type")
        if not val or item_type == "date":
            continue

        is_percent = item_type == "percentage" or "%" in val
        is_numeric = item_type in {"value", "dollar"} or bool(re.search(r"\d", val))

        if category in {"coverage", "unionized"} and is_numeric and not is_percent and not metrics["covered"]:
            metrics["covered"] = val
            continue
        if category in {"non_coverage", "nonunion"} and is_numeric and not is_percent and not metrics["non_covered"]:
            metrics["non_covered"] = val
            continue
        if category == "counts" and is_numeric and not is_percent and not metrics["total"]:
            metrics["total"] = val
            continue
        if category == "bu" and is_numeric and not is_percent and not metrics["bu"]:
            metrics["bu"] = val
            continue

        if is_percent and not metrics["pct"]:
            if category in {"coverage", "non_coverage", "percent", "unionized", "nonunion"}:
                metrics["pct"] = val
                continue

    return metrics


def _render_metric_sentence(label: str, metrics: Dict[str, Optional[str]]) -> Optional[str]:
    covered = metrics.get("covered")
    non_covered = metrics.get("non_covered")
    total = metrics.get("total")
    pct = metrics.get("pct")
    bu = metrics.get("bu")

    base = None
    if covered and total and pct:
        base = f"{label} had {covered} ({pct}) out of {total} employees covered by unions"
    elif covered and total:
        base = f"{label} had {covered} out of {total} employees covered by unions"
    elif covered and pct:
        base = f"{label} had {covered} ({pct}) employees covered by unions"
    elif total and pct:
        base = f"{label} had {total} employees, of whom {pct} are covered by unions"
    elif non_covered and total:
        base = f"{label} had {non_covered} non-union employees out of {total}"
    elif covered:
        base = f"{label} had {covered} unionized employees"
    elif non_covered:
        base = f"{label} had {non_covered} non-union employees"
    elif total:
        base = f"{label} had {total} employees"
    elif pct:
        base = f"{label} had {pct} employees covered by unions"

    if not base:
        return None
    if bu:
        base = f"{base}, across {bu} bargaining units"
    return base


def _minimal_union_context_suffix(header_ctx: Dict[str, Any], hints: Dict[str, Optional[str]]) -> Optional[str]:
    headers = [
        (h.get("header") or "").strip()
        for h in header_ctx.get("per_item", [])
        if h.get("header")
    ]
    header_text = " | ".join(headers) if headers else ""
    categories = set(header_ctx.get("categories_present", []))
    if "union_contract_counts" in categories or CONTRACT_CONTEXT_REGEX.search(header_text):
        return "under labor contracts"
    if hints.get("has_non_union"):
        return "with non-union exposure"
    if hints.get("has_union_signal"):
        return "with union representation context"
    if any(c in categories for c in {"coverage", "non_coverage", "unionized", "nonunion", "bu"}):
        return "within a union context"
    return None


def _extract_text_hints(
    label: str,
    header_ctx: Dict[str, Any],
    value_ctx: Dict[str, Any],
) -> Dict[str, Optional[Any]]:
    headers = [h.get("header", "") for h in header_ctx.get("per_item", []) if h.get("header")]
    text_values = value_ctx.get("text", [])
    texts = [label] + headers + text_values
    compact_text = " | ".join([t for t in texts if t])

    union_names = _extract_union_mentions(text_values)
    if not union_names:
        union_match = DYNAMIC_UNION_REGEX.search(compact_text)
        if union_match:
            union_names = [union_match.group(0).strip(" ,.;:-")]

    has_union_signal = bool(UNION_REGEX.search(compact_text) or CONTRACT_CONTEXT_REGEX.search(compact_text))
    has_non_union = bool(NON_UNION_REGEX.search(compact_text))

    return {
        "union_name": union_names[0] if union_names else None,
        "union_names": union_names,
        "has_union_signal": has_union_signal,
        "has_non_union": has_non_union,
    }


def _extract_union_mentions(text_values: List[str]) -> List[str]:
    """
    Extract union names from text cells.
    If at least one text cell matches a union, treat other non-empty text cells
    in this group as union names as a fallback (same-column heuristic).
    """
    cleaned_texts = []
    for text in text_values:
        norm = SPACE_REGEX.sub(" ", (text or "")).strip(" ,.;:-")
        if norm:
            cleaned_texts.append(norm)

    if not cleaned_texts:
        return []

    matched = False
    explicit_unions: List[str] = []
    for text in cleaned_texts:
        parsed_terms, has_match = _cached_union_parse(text)
        if has_match:
            matched = True
            explicit_unions.extend(parsed_terms)

    # De-duplicate explicit matches.
    deduped_explicit: List[str] = []
    seen = set()
    for name in explicit_unions:
        key = name.lower()
        if key not in seen:
            deduped_explicit.append(name)
            seen.add(key)

    if matched:
        # Union-column heuristic: include all non-empty text values when any union is detected.
        out: List[str] = []
        seen_all = set()
        for text in cleaned_texts:
            key = text.lower()
            if key not in seen_all:
                out.append(text)
                seen_all.add(key)
        return out

    return deduped_explicit


@lru_cache(maxsize=4096)
def _cached_union_parse(text: str) -> tuple[tuple[str, ...], bool]:
    """
    Cached union parsing for repeated table cell text.
    Returns (union_terms, has_match).
    """
    norm = SPACE_REGEX.sub(" ", (text or "")).strip(" ,.;:-")
    if not norm:
        return tuple(), False

    names: List[str] = []
    hits = REGION_MATCHER.parse_unions(norm)
    for hit in hits:
        term = (hit.get("term") or "").strip(" ,.;:-")
        if term:
            names.append(term)

    if not names:
        dyn = DYNAMIC_UNION_REGEX.search(norm)
        if dyn:
            names.append(dyn.group(0).strip(" ,.;:-"))

    if not names:
        return tuple(), False

    deduped: List[str] = []
    seen = set()
    for name in names:
        key = name.lower()
        if key not in seen:
            deduped.append(name)
            seen.add(key)
    return tuple(deduped), True


def _union_name_segment(hints: Dict[str, Optional[str]]) -> Optional[str]:
    names = hints.get("union_names") or []
    if not names:
        name = hints.get("union_name")
        names = [name] if name else []
    names = [n for n in names if n]
    if not names:
        return None
    if len(names) == 1:
        return f"represented by {names[0]}"
    return f"represented by {', '.join(names)}"
