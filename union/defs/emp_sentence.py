from typing import Any, Dict, List, Optional
import re


AMENDABLE_TOKEN_REGEX = re.compile(r"\bamendable\b", re.IGNORECASE)
EMPLOYEE_HEADER_REGEX = re.compile(r"\bemployees?\b", re.IGNORECASE)
SPACE_REGEX = re.compile(r"\s+")


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
    """
    raw_headers = [i.get("header", "").strip() for i in items if i.get("header")]
    unique_headers: List[str] = []
    seen = set()
    for header in raw_headers:
        normalized = _normalize_header(header)
        if normalized and normalized not in seen:
            unique_headers.append(normalized)
            seen.add(normalized)

    return {
        "raw": raw_headers,
        "unique": unique_headers,
        "has_headers": bool(unique_headers),
        # TODO: Add parsed dimensions (region, workforce type, unit, etc.).
        "dimensions": {},
    }


def _normalize_header(header: str) -> str:
    """
    Lightweight normalization for employment-oriented header text.
    """
    if not header:
        return ""

    # Remove specific noisy token.
    header = AMENDABLE_TOKEN_REGEX.sub(" ", header)

    # Collapse long employee headers into a single stable label.
    if EMPLOYEE_HEADER_REGEX.search(header):
        return "employees"

    header = SPACE_REGEX.sub(" ", header).strip(" ,;:-")
    return header


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

    headers = header_ctx.get("unique", [])
    if headers:
        return f"{head}{label} ({', '.join(headers)}) was {' '.join(values)}."

    return f"{head}{label} was {' '.join(values)}."
