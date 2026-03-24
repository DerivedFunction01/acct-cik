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
    WORKS_REGEX,
    WORKER_TERMS,
)
from defs.region_regex import RegionMatcher
from defs.table_processor import TABLE_TOK

SPACE_REGEX = re.compile(r"\s+")
NULL_HEADER_REGEX = re.compile(r"^(?:-|—|n/?a|na)$", re.IGNORECASE)
SPLIT_HINT_REGEX = re.compile(r"[|/;,]")
LOCAL_NUMBER_REGEX = re.compile(r"\bLocals?\s*#?\s*\d+(?:\s*[-–]\s*\d+)?\b", re.IGNORECASE)
PURE_NUMBER_REGEX = re.compile(r"^\(?-?\d[\d,]*(?:\.\d+)?\)?$")
CONTRACT_CONTEXT_REGEX = build_regex(
    [
        build_compound(
            [CORE.LABOR, CORE.UNION, CORE.BARGAIN],
            [r"agreements?", r"contracts?", r"arrangements?"],
        ),
        r"collective\s+bargain(?:ing)?\s+agreements?",
        build_compound([CORE.BARGAIN], [r"units?"], sep_prefix=r"[\s-]+"),
        r"cba(?:s)?",
    ]
)
EMPLOYEE_SCOPE_REGEX = build_regex(
    [
        r"employees?",
        r"workers?",
        r"workforce",
        r"staff",
        r"personnel",
        r"headcount",
    ]
)

REPRESENT_SCOPE_REGEX = build_regex([r"represent(?:ed|ation)?", r"represented\s+by"], ignore_case=True)
REGION_MATCHER = RegionMatcher()

# Centralized fallback/hint phrases for easy tuning.
PHRASE_MAP = {
    "context_contract": "under labor contracts",
    "context_non_union": "with non-union exposure",
    "report_verb": "reported",
    "represented": "represented by",
    "coverage_union": "covered by unions",
    "coverage_neutral": "covered",
    "coverage_represented": "represented",
    "coverage_works": "covered by works councils",
    "context_works": "under works councils",
}


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
    "counts": build_regex(
        list(set(WORKER_TERMS + []) - {r"Teamsters?"}) + [
            r"Headcount"
        ]
    ), # Or other rows that have numbers and not years.
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
    "works_council": WORKS_REGEX,
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
    "works_council",
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
    sentence = _render_template(
        label=row_info.get("label", ""),
        year=year,
        header_ctx=header_ctx,
        value_ctx=value_ctx,
    )
    if not sentence:
        return None
    if TABLE_TOK not in sentence:
        return f"{sentence} {TABLE_TOK}"
    return sentence


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
        "works_council",
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

    # Promote overlap headers to coverage when both concepts appear.
    # Example: "Employees covered by labor agreements" should be treated as
    # coverage (count/percent), not as a contract-count metadata column.
    has_union_contract = bool(HEADER_PATTERNS["union_contract_counts"].search(header))
    has_bu = bool(HEADER_PATTERNS["bu"].search(header))
    has_works = bool(HEADER_PATTERNS["works_council"].search(header))
    has_coverage = bool(HEADER_PATTERNS["coverage"].search(header))
    has_non_coverage = bool(HEADER_PATTERNS["non_coverage"].search(header))

    has_employee_scope = bool(EMPLOYEE_SCOPE_REGEX.search(header))

    # Only promote contract/BU headers to coverage when they are explicitly scoped
    # to employees/workforce; otherwise keep them as metadata/count context.
    if has_works and has_employee_scope:
        return "works_council"
    if (has_union_contract or has_bu) and has_non_coverage and has_employee_scope:
        return "non_coverage"
    if (has_union_contract or has_bu) and has_coverage and has_employee_scope:
        return "coverage"

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

    # Get raw values
    raw_values = value_ctx.get("non_date", []) or value_ctx.get("all", [])
    
    metrics = _extract_metrics(header_ctx)
    hints = _extract_text_hints(label=label, header_ctx=header_ctx, value_ctx=value_ctx)
    has_core_metric = any(metrics.get(k) for k in ["covered", "non_covered", "total", "pct", "bu", "workforce_pct"])
    coverage_basis = _coverage_basis_phrase(metrics, header_ctx, hints)
    
    # Filter values: Remove text that is used as a union name
    union_names_set = set(hints.get("union_names", []) or [])
    values = [v for v in raw_values if v not in union_names_set]
    
    head = f"In {year}, " if year else ""

    context_suffix = _minimal_union_context_suffix(header_ctx, hints)
    union_name_segment = _union_name_segment(hints)

    # If we have a specific union name segment, suppress the generic context suffix
    if union_name_segment and context_suffix == PHRASE_MAP["context_contract"]:
        context_suffix = None

    metric_sentence = _render_metric_sentence(
        label,
        metrics,
        has_specific_union=bool(union_name_segment),
        coverage_basis=coverage_basis,
    )
    if metric_sentence:
        # Construct workforce_pct segment (moved from _render_metric_sentence to control order)
        # Only add if it wasn't used as the primary base metric and not handled by mixed-coverage logic
        workforce_pct_segment = None
        has_primary_metric = any(metrics.get(k) for k in ["covered", "non_covered", "total", "pct", "bu"])
        is_mixed_works_case = bool(metrics.get("covered") and metrics.get("works_covered"))
        
        if metrics.get("workforce_pct") and not metrics.get("pct") and has_primary_metric and not is_mixed_works_case:
            workforce_pct_segment = f"which was {metrics['workforce_pct']} of the total workforce"

        # Special handling for "Union + Workforce %" scenario (no count, just % and union name)
        # Reorder to: "Label was represented by Union, which was X% of total workforce"
        has_other_metrics = any(metrics.get(k) for k in ["covered", "non_covered", "total", "pct", "bu", "works_covered"])
        if metrics.get("workforce_pct") and not has_other_metrics and union_name_segment:
            base = f"{label} was {union_name_segment}"
            pct_segment = f"which was {metrics['workforce_pct']} of the total workforce"
            
            if context_suffix and _is_redundant_suffix(base, context_suffix):
                context_suffix = None
            
            segments = [base]
            if context_suffix:
                segments.append(context_suffix)
            segments.append(pct_segment)
            return f"{head}{', '.join(segments)}."

        # Avoid mixing explicit covered-by-union phrasing with extra
        # non-union hint suffixes unless the metric itself is non-union.
        if context_suffix == PHRASE_MAP["context_non_union"] and (metrics.get("covered") or metrics.get("pct")):
            context_suffix = None
        # If coverage is already stated in the metric sentence, suppress
        # redundant contract-context phrasing.
        if context_suffix == PHRASE_MAP["context_contract"] and (
            metrics.get("covered") or metrics.get("pct") or metrics.get("bu") or metrics.get("non_covered")
        ):
            context_suffix = None
        # Drop suffix if its core phrase already appears in metric text
        # (e.g., "covered by labor agreements, under labor agreements").
        if context_suffix and _is_redundant_suffix(metric_sentence, context_suffix):
            context_suffix = None

        # Merge union_name_segment into metric_sentence to remove comma if simple sentence
        if union_name_segment and not context_suffix and "." not in metric_sentence:
            metric_sentence = f"{metric_sentence} {union_name_segment}"
            union_name_segment = None

        segments = [metric_sentence]
        for segment in [context_suffix, union_name_segment, workforce_pct_segment]:
            if segment and segment not in segments:
                segments.append(segment)
        return f"{head}{', '.join(segments)}."

    # Drop contract/meta-only rows with no usable workforce metrics.
    if not has_core_metric:
        cats = {
            i.get("category", "unknown")
            for i in header_ctx.get("per_item", [])
            if i.get("category")
        }
        if cats and cats.issubset(
            {
                "union_contract_counts",
                "generic_contract_counts",
                "date_meta",
                "generic_meta",
                "union_name",
                "number",
                "unknown",
            }
        ):
            if context_suffix or union_name_segment:
                tail = context_suffix or ""
                if union_name_segment:
                    tail = f"{tail}, {union_name_segment}".strip(", ")
                if tail:
                    return f"{head}{label} {PHRASE_MAP['report_verb']} {tail}."
            return None

    if header_ctx.get("has_only_meta_headers"):
        if context_suffix:
            tail = context_suffix
            if union_name_segment:
                tail = f"{tail}, {union_name_segment}"
            return f"{head}{label} {PHRASE_MAP['report_verb']} {tail}."
        return None

    if not values:
        if context_suffix or union_name_segment:
            tail = context_suffix or ""
            if union_name_segment:
                tail = f"{tail}, {union_name_segment}".strip(", ")
            if tail:
                return f"{head}{label} {PHRASE_MAP['report_verb']} {tail}."
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
    return f"{head}{base}. {TABLE_TOK}"


def _extract_metrics(header_ctx: Dict[str, Any]) -> Dict[str, Optional[str]]:
    per_item = header_ctx.get("per_item", [])
    metrics: Dict[str, Optional[Any]] = {
        "covered": None,
        "non_covered": None,
        "total": None,
        "pct": None,
        "bu": None,
        "works_covered": None,
        "works_pct": None,
        "workforce_pct": None,
        "covered_header": None,
        "pct_header": None,
        "works_header": None,
        "workforce_pct_header": None,
    }
    # assert arrays
    metrics["coverage_counts"] = []
    metrics["coverage_headers"] = []
    
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
            metrics["covered_header"] = item.get("header")
            metrics["coverage_counts"].append(val)
            if item.get("header"):
                metrics["coverage_headers"].append(item.get("header"))
            continue
        if category in {"coverage", "unionized"} and is_numeric and not is_percent:
            metrics["coverage_counts"].append(val)
            if item.get("header"):
                metrics["coverage_headers"].append(item.get("header"))
            continue
        if category in {"non_coverage", "nonunion"} and is_numeric and not is_percent and not metrics["non_covered"]:
            metrics["non_covered"] = val
            continue
        if category == "counts" and is_numeric and not is_percent and not metrics["total"]:
            metrics["total"] = val
            continue
        if category == "bu" and is_numeric and not is_percent and not metrics["bu"]:
            if not _looks_like_pure_number(val):
                continue
            metrics["bu"] = val
            continue
        if category == "works_council" and is_numeric and not is_percent and not metrics["works_covered"]:
            metrics["works_covered"] = val
            if item.get("header"):
                metrics["works_header"] = item.get("header")
            continue

        if is_percent:
            header_text = (item.get("header") or "").strip()
            
            is_coverage_related = (
                HEADER_PATTERNS["coverage"].search(header_text)
                or HEADER_PATTERNS["non_coverage"].search(header_text)
                or HEADER_PATTERNS["works_council"].search(header_text)
                or category in {"coverage", "non_coverage", "unionized", "nonunion", "works_council"}
            )

            if category in {"percent", "counts"} and not is_coverage_related and not metrics["workforce_pct"]:
                metrics["workforce_pct"] = val
                metrics["workforce_pct_header"] = header_text
                continue

        if is_percent and not metrics["pct"]:
            if category in {"coverage", "non_coverage", "unionized", "nonunion"}:
                metrics["pct"] = val
                metrics["pct_header"] = item.get("header")
                continue
        if is_percent and category == "works_council" and not metrics["works_pct"]:
            metrics["works_pct"] = val
            if item.get("header"):
                metrics["works_header"] = item.get("header")
            continue

    return metrics


def _parse_number_token(value: str) -> Optional[float]:
    if not value:
        return None
    raw = value.strip()
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", raw)
    if not cleaned:
        return None
    try:
        num = float(cleaned)
    except ValueError:
        return None
    if negative:
        num = -num
    return num


def _looks_like_pure_number(value: str) -> bool:
    if not value:
        return False
    raw = value.strip()
    return bool(PURE_NUMBER_REGEX.match(raw))


def _format_int_like(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _derive_pct_from_counts(numerator: Optional[str], denominator: Optional[str]) -> Optional[str]:
    num = _parse_number_token(numerator or "")
    den = _parse_number_token(denominator or "")
    if num is None or den is None or den == 0:
        return None
    pct = (num / den) * 100.0
    # Keep compact output while stable for extractor.
    out = f"{pct:.1f}".rstrip("0").rstrip(".")
    return f"{out}%"


def _derive_pct_from_mixed_components(
    component_count: Optional[str],
    other_component_count: Optional[str],
    overall_pct: Optional[str],
) -> Optional[str]:
    """
    Estimate component-specific percent when we only have:
      - two component counts (e.g., labor-covered and works-covered)
      - one overall coverage percent
      - no explicit total.
    Assumption: overall_pct applies to combined covered population.
    """
    comp = _parse_number_token(component_count or "")
    other = _parse_number_token(other_component_count or "")
    overall = _parse_number_token(overall_pct or "")
    if comp is None or other is None or overall is None:
        return None
    combined = comp + other
    if combined <= 0:
        return None
    est = overall * (comp / combined)
    out = f"{est:.1f}".rstrip("0").rstrip(".")
    return f"{out}%"


def _render_metric_sentence(
    label: str,
    metrics: Dict[str, Optional[str]],
    has_specific_union: bool = False,
    coverage_basis: str = PHRASE_MAP["coverage_union"],
) -> Optional[str]:
    covered = metrics.get("covered")
    non_covered = metrics.get("non_covered")
    total = metrics.get("total")
    pct = metrics.get("pct")
    bu = metrics.get("bu")
    works_covered = metrics.get("works_covered")
    works_pct = metrics.get("works_pct")
    workforce_pct = metrics.get("workforce_pct")

    # Works-council dominant rows should be rendered as one coherent statement.
    # This avoids "X% are covered; separately ... covered by works councils".
    if works_covered and total and (works_pct or pct) and coverage_basis == PHRASE_MAP["coverage_neutral"]:
        pct_val = works_pct or pct
        return f"{label} had {works_covered} ({pct_val}) out of {total} employees covered by works councils"

    # Keep labor/union coverage and works-council coverage separate when both exist.
    # Do not blend them into one combined covered count sentence.
    if covered and works_covered:
        base = f"{label} had {covered} employees {coverage_basis}"
        if total:
            base = f"{label} had {covered} of {total} employees {coverage_basis}"
        derived_union_pct = _derive_pct_from_counts(covered, total)
        if not derived_union_pct and pct and not total:
            derived_union_pct = _derive_pct_from_mixed_components(
                covered,
                works_covered,
                pct,
            )
        if derived_union_pct:
            base = f"{base} ({derived_union_pct})"
        elif pct:
            # Keep provided percentage only when we cannot derive a union/CBA-specific one.
            base = f"{base}, with overall coverage of {pct}"
        works_clause = f"{works_covered} employees were covered by works councils"
        if workforce_pct and not pct and not covered:
            base = f"{base}, which was {workforce_pct} of the total workforce"
        return f"{base}. Separately, {works_clause}"

    coverage_counts = metrics.get("coverage_counts") or []
    if coverage_counts and len(coverage_counts) > 1:
        nums = [_parse_number_token(v) for v in coverage_counts]
        nums = [n for n in nums if n is not None]
        if nums:
            covered = _format_int_like(sum(nums))
    covered_phrase = "employees" if has_specific_union else f"employees {coverage_basis}"
    pct_phrase = "covered" if has_specific_union else coverage_basis

    base = None
    if covered and total and pct:
        base = f"{label} had {covered} ({pct}) out of {total} {covered_phrase}"
    elif covered and total:
        base = f"{label} had {covered} of {total} {covered_phrase}"
    elif covered and pct:
        base = f"{label} had {covered} ({pct}) {covered_phrase}"
    elif total and pct:
        base = f"{label} had {pct} of {total} employees {pct_phrase}"
    elif non_covered and total:
        base = f"{label} had {non_covered} non-union employees out of {total}"
    elif covered:
        base = f"{label} had {covered} {covered_phrase}"
    elif non_covered:
        base = f"{label} had {non_covered} non-union employees"
    elif total:
        base = f"{label} had {total} employees"
    elif pct:
        base = f"{label} had {pct} employees {pct_phrase}"
    elif bu:
        base = f"{label} had {bu} bargaining units"
    elif workforce_pct:
        base = f"{label} was {workforce_pct} of the total workforce"

    if not base:
        if works_covered and works_pct:
            return f"{label} had {works_covered} employees covered by works councils ({works_pct})"
        if works_covered:
            return f"{label} had {works_covered} employees covered by works councils"
        if works_pct:
            return f"{label} had {works_pct} employees covered by works councils"
        return None
    if bu and "bargaining units" not in base:
        base = f"{base}, across {bu} bargaining units"
    if works_covered and works_pct:
        base = f"{base}. Separately, {works_covered} ({works_pct}) employees were covered by works councils"
    elif works_covered:
        base = f"{base}. Separately, {works_covered} employees were covered by works councils"
    elif works_pct:
        base = f"{base}. Separately, {works_pct} were covered by works councils"
    return base


def _coverage_basis_phrase(
    metrics: Dict[str, Optional[str]],
    header_ctx: Dict[str, Any],
    hints: Dict[str, Optional[str]],
) -> str:
    """
    Choose coverage wording from the actual matched coverage headers first,
    then fallback to broader table context.
    """
    coverage_headers = metrics.get("coverage_headers") or []
    if coverage_headers:
        basis_parts: List[str] = []
        seen_basis = set()
        for hdr in coverage_headers:
            basis = _coverage_basis_from_header((hdr or "").strip())
            if not basis:
                continue
            key = basis.lower()
            if key not in seen_basis:
                basis_parts.append(basis)
                seen_basis.add(key)
        if len(basis_parts) > 1:
            joined = " and ".join(basis_parts)
            return joined
        if len(basis_parts) == 1:
            return basis_parts[0]

    for hdr_key in ("covered_header", "pct_header", "works_header"):
        header = (metrics.get(hdr_key) or "").strip()
        basis = _coverage_basis_from_header(header)
        if basis:
            return basis

    headers = [
        (h.get("header") or "").strip()
        for h in header_ctx.get("per_item", [])
        if h.get("header")
    ]
    for header in headers:
        basis = _coverage_basis_from_header(header)
        if basis:
            return basis

    categories = set(header_ctx.get("categories_present", []))
    if "works_council" in categories:
        return PHRASE_MAP["coverage_neutral"]
    if hints.get("union_names"):
        return PHRASE_MAP["coverage_represented"]
    return PHRASE_MAP["coverage_union"]


def _coverage_basis_from_header(header: str) -> Optional[str]:
    if not header:
        return None
    if HEADER_PATTERNS["works_council"].search(header):
        return PHRASE_MAP["coverage_works"]
    contract_match = CONTRACT_CONTEXT_REGEX.search(header)
    if contract_match:
        phrase = SPACE_REGEX.sub(" ", contract_match.group(0)).strip().lower()
        if phrase:
            return f"covered by {phrase}"
    coverage_match = HEADER_PATTERNS["coverage"].search(header)
    if coverage_match:
        phrase = SPACE_REGEX.sub(" ", coverage_match.group(0)).strip().lower()
        if phrase:
            # If the matched snippet already encodes "covered/represented", keep it.
            if "cover" in phrase or "represent" in phrase:
                # Keep specific union-bearing phrases, but avoid downgrading to bare
                # "covered"/"represented" because extraction relies on union context.
                if any(tok in phrase for tok in ("union", "labor", "bargain", "cba")):
                    return phrase
                return PHRASE_MAP["coverage_neutral"]
            return f"covered by {phrase}"
    if REPRESENT_SCOPE_REGEX.search(header):
        return PHRASE_MAP["coverage_represented"]
    if HEADER_PATTERNS["unionized"].search(header) or HEADER_PATTERNS["coverage"].search(header):
        return PHRASE_MAP["coverage_union"]
    return None


def _minimal_union_context_suffix(header_ctx: Dict[str, Any], hints: Dict[str, Optional[str]]) -> Optional[str]:
    headers = [
        (h.get("header") or "").strip()
        for h in header_ctx.get("per_item", [])
        if h.get("header")
    ]
    header_text = " | ".join(headers) if headers else ""
    categories = set(header_ctx.get("categories_present", []))
    if "works_council" in categories:
        return PHRASE_MAP["context_works"]
    if "union_contract_counts" in categories or CONTRACT_CONTEXT_REGEX.search(header_text):
        contract_phrase = _header_contract_phrase(headers)
        if contract_phrase:
            return f"under {contract_phrase}"
        return PHRASE_MAP["context_contract"]
    if hints.get("has_non_union"):
        non_union_header = _first_header_for_category(header_ctx, {"non_coverage", "nonunion"})
        if non_union_header:
            return f"with {non_union_header.lower()}"
        return PHRASE_MAP["context_non_union"]
    return None


def _is_redundant_suffix(metric_sentence: str, suffix: str) -> bool:
    metric_l = metric_sentence.lower()
    suffix_l = suffix.lower().strip()
    if not suffix_l:
        return True
    if suffix_l in metric_l:
        return True

    for lead in ("under ", "with ", "in "):
        if suffix_l.startswith(lead):
            core = suffix_l[len(lead):].strip()
            if core and core in metric_l:
                return True
    return False


def _first_header_for_category(header_ctx: Dict[str, Any], categories: set[str]) -> Optional[str]:
    for item in header_ctx.get("per_item", []):
        category = item.get("category")
        header = (item.get("header") or "").strip()
        if category in categories and header:
            return header
    return None


def _header_contract_phrase(headers: List[str]) -> Optional[str]:
    for header in headers:
        if not header:
            continue
        match = CONTRACT_CONTEXT_REGEX.search(header)
        if not match:
            continue
        phrase = SPACE_REGEX.sub(" ", match.group(0)).strip().lower()
        if phrase:
            return phrase
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

    # Fallback: Check if any text values are in a column explicitly labeled as 'union_name'
    # This catches acronyms like "AFA", "PAFCA" that aren't in the regex dictionary but are under a "Union" header.
    for item in header_ctx.get("per_item", []):
        if item.get("category") == "union_name" and item.get("val"):
            val = item["val"].strip()
            if val and val not in union_names:
                union_names.append(val)

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
        return _clean_union_names(out)

    return _clean_union_names(deduped_explicit)


def _strip_local_numbers(text: str) -> str:
    if not text:
        return ""
    cleaned = LOCAL_NUMBER_REGEX.sub("", text)
    cleaned = SPACE_REGEX.sub(" ", cleaned).strip(" ,;:-")
    # Remove dangling conjunctions caused by stripping locals.
    cleaned = re.sub(r"^(?:and|&)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:and|&)$", "", cleaned, flags=re.IGNORECASE)
    # Drop bare "Local(s)" tokens that no longer carry meaning.
    if cleaned.lower() in {"local", "locals"}:
        return ""
    return cleaned


def _clean_union_names(names: List[str]) -> List[str]:
    if not names:
        return []
    cleaned: List[str] = []
    seen = set()
    for name in names:
        stripped = _strip_local_numbers(name)
        if not stripped:
            continue
        key = stripped.lower()
        if key in seen:
            continue
        cleaned.append(stripped)
        seen.add(key)
    return cleaned


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
        return f"{PHRASE_MAP['represented']} {names[0]}"
    return f"{PHRASE_MAP['represented']} {', '.join(names)}"
