from typing import List, Dict, Any, Optional, Callable
import re
from defs.table_processor import MAJOR_CURRENCIES, YEAR_REGEX

# Regex to remove footnote markers like (1), [a], *, †
FOOTNOTE_REGEX = re.compile(r'(\(\d+\)|\[\w+\]|[\*\†\‡]+)$')
CLEAN_NUM_REGEX = re.compile(r'[^\d\.\-]')
NUMBER_TOKEN_REGEX = re.compile(r'\d+(?:\.\d+)?')
# Pre-built at module level alongside your other regex constants
_ALL_CURRENCY_SYMBOLS = {
    s for props in MAJOR_CURRENCIES.values() for s in props["symbols"]
}
_UNIT_WORDS = re.compile(
    r"\b(hundred|thousand|million|billion|trillion)s?\b", re.IGNORECASE
)
# Strips everything that's "allowed" in a pure numeric/currency cell
_STRIP_ALLOWED = re.compile(
    r"[\d\s\.\,\(\)\-\%]"
    + r"|"
    + "|".join(
        re.escape(s) for s in sorted(_ALL_CURRENCY_SYMBOLS, key=len, reverse=True)
    )
)
def _clean_cell(text: str) -> str:
    """Removes footnote markers and extra whitespace."""
    if not text:
        return ""
    # Remove trailing footnote markers
    cleaned = FOOTNOTE_REGEX.sub('', text.strip())
    return cleaned.strip()


def _format_value(
    val: str, col_type: Optional[str], multiplier: float, currency: str
) -> str:
    val = _clean_cell(val)
    if not val:
        return ""

    # 1. Percentage (ignore multiplier)
    if col_type == "percentage" or "%" in val:
        if "%" not in val:
            return f"{val}%"
        return val

    # 2. Date (don't multiply)
    if col_type == "date":
        return val

    # 3. Multiple numeric tokens: try to sum if homogeneous, else preserve.
    number_tokens = NUMBER_TOKEN_REGEX.findall(val)
    if len(number_tokens) >= 2:
        # Detect which currencies are present in the cell
        symbols_found = {
            code
            for code, props in MAJOR_CURRENCIES.items()
            for s in props["symbols"]
            if s in val
        }

        # If multiple distinct currencies appear, preserve as-is
        if len(symbols_found) > 1:
            return val

        # If narrative text remains after stripping allowed chars + unit words,
        # preserve as-is (reuses the same scrub logic as guard #5)
        scrubbed = _UNIT_WORDS.sub("", val)
        scrubbed = _STRIP_ALLOWED.sub("", scrubbed)
        if scrubbed.strip():
            return val

        # Homogeneous: sum the tokens and let the rest of the function format it
        total = sum(float(t) for t in number_tokens)
        # Reconstruct a clean value string, preserving currency symbol if present
        sym = ""
        if symbols_found:
            code = next(iter(symbols_found))
            sym = MAJOR_CURRENCIES[code]["symbols"][0]
        elif "$" in val:
            sym = "$"

        is_negative = "(" in val and ")" in val
        val = f"({sym}{total})" if is_negative else f"{sym}{total}"
        # Re-run token detection so the rest of the function sees 1 token
        number_tokens = NUMBER_TOKEN_REGEX.findall(val)

    # 4. Guard: if there's no numeric token at all, it's pure text — skip.
    if len(number_tokens) == 0:
        return val

    # 5. Guard: only currency symbols and unit words are allowed as non-numeric text.
    #    Strip digits, punctuation, whitespace, currency symbols, and unit words.
    #    If anything remains, the cell is narrative text — preserve as-is.
    scrubbed = _UNIT_WORDS.sub("", val)  # remove "million", "billion", etc.
    scrubbed = _STRIP_ALLOWED.sub("", scrubbed)  # remove digits, symbols, currency
    if scrubbed.strip():  # letters remain → narrative text
        return val
    # 6. Numeric processing
    raw_num_str = CLEAN_NUM_REGEX.sub("", val)
    try:
        is_negative = "(" in val and ")" in val
        num = float(raw_num_str)
        num = num * multiplier

        if num >= 1000:
            num = int(num)
        elif int(num) != num:
            num = round(num, 2)
        else:
            num = int(num)
        num = f"{num:,}"

        if is_negative:
            num = f"({num})"

        has_symbol = any(s in val for s in _ALL_CURRENCY_SYMBOLS)
        has_currency = (
            has_symbol or col_type == "dollar"
        )

        if has_currency:
            curr_props = MAJOR_CURRENCIES.get(currency)
            sym = (
                curr_props["symbols"][0]
                if curr_props
                else ("$" if currency == "USD" else f"{currency} ")
            )
            return f"{sym}{num}"
        else:
            return f"{num}"

    except ValueError:
        return val

def _extract_context(processed_table: Dict[str, Any]) -> Dict[str, Any]:
    info = processed_table.get("info", {})
    caption = _clean_cell(info.get("caption", ""))

    # Extract caption year
    caption_year = info.get("caption_year")

    # Build symbol map
    symbol_map = {}
    for code, props in MAJOR_CURRENCIES.items():
        for s in props["symbols"]:
            symbol_map[s] = code

    # Prefer root 'types', fallback to info 'column_types'
    col_types = processed_table.get("types")
    if not col_types:
        col_types = info.get("column_types", {})

    return {
        "data": processed_table.get("data", []),
        "headers": processed_table.get("headers", {}),
        "types": col_types,
        "col_years": processed_table.get("years", {}),
        "row_years": processed_table.get("row_years", {}),
        "caption": caption,
        "currency": info.get("currency", "USD"),
        "multiplier": info.get("global_multiplier", 1.0),
        "caption_year": caption_year,
        "symbol_map": symbol_map,
    }

def _extract_row_info(r_idx: int, row: List[str], context: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {"valid": False}
    
    label = _clean_cell(row[0])
    if not label:
        return {"valid": False}
        
    return {
        "valid": True,
        "label": label,
        "row_year": context["row_years"].get(r_idx)
    }

def _get_cell_info(c_idx: int, val: str, context: Dict[str, Any]) -> Dict[str, Any]:
    val = val.strip()
    if not val or val in ["-", "—", "N/A", "n/a"]:
        return {"valid": False}
    
    # Determine currency for this cell
    cell_currency = context["currency"]
    for sym in sorted(context["symbol_map"].keys(), key=len, reverse=True):
        if sym in val:
            cell_currency = context["symbol_map"][sym]
            break
            
    col_type = context["types"].get(c_idx)
    
    # Fallback for mixed or unknown types: infer from cell value
    if not col_type or col_type == "mixed":
        if YEAR_REGEX.search(val):
            col_type = "date"
        elif "%" in val:
            col_type = "percentage"
        elif any(s in val for s in context["symbol_map"]):
            col_type = "dollar"
        elif any(c.isdigit() for c in CLEAN_NUM_REGEX.sub("", val)):
            col_type = "value"
        else:
            col_type = "text"

    col_year = context["col_years"].get(c_idx)
    header = _clean_cell(context["headers"].get(c_idx, ""))
    
    # Resolve year (Column > Caption) - Row year handled in clustering
    year = col_year if col_year else context["caption_year"]
    
    return {
        "valid": True,
        "val": val,
        "type": col_type,
        "year": year,
        "header": header,
        "currency": cell_currency,
        "c_idx": c_idx
    }

def _can_merge(group: Dict[str, Any], cell: Dict[str, Any]) -> bool:
    if not group:
        return True
        
    # 1. Year Consistency
    if group.get("year") and cell.get("year") and group["year"] != cell["year"]:
        return False
    
    # 2. Type Compatibility
    g_types = group.get("types", set())
    c_type = cell["type"]
    
    # Text merges with everything
    if "text" in g_types or c_type == "text":
        return True
        
    # Value/Dollar merges with Percentage
    is_value_group = any(t in ["dollar", "value"] for t in g_types)
    is_percent_group = "percentage" in g_types
    
    is_value_cell = c_type in ["dollar", "value"]
    is_percent_cell = c_type == "percentage"
    
    if (is_value_group and is_percent_cell) or (is_percent_group and is_value_cell):
        return True
        
    return False

def _merge_cell(group: Dict[str, Any], cell: Dict[str, Any], context: Dict[str, Any]):
    if "items" not in group:
        group["items"] = []
        group["types"] = set()
        group["year"] = cell["year"]
        group["headers"] = []
    
    # Update year if not set
    if not group["year"] and cell["year"]:
        group["year"] = cell["year"]
        
    formatted = _format_value(cell["val"], cell["type"], context["multiplier"], cell["currency"])
    
    group["items"].append({
        "val": formatted,
        "type": cell["type"],
        "header": cell["header"]
    })
    group["types"].add(cell["type"])
    if cell["header"]:
        group["headers"].append(cell["header"])


def _find_next_valid_cell(
    row: List[str],
    start_idx: int,
    row_info: Dict[str, Any],
    context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Returns the next valid parsed cell after start_idx, or None.
    """
    for nxt_idx in range(start_idx + 1, len(row)):
        if nxt_idx == 0:
            continue
        nxt = _get_cell_info(nxt_idx, row[nxt_idx], context)
        if not nxt.get("valid"):
            continue
        if row_info["row_year"] and not nxt.get("year"):
            nxt["year"] = row_info["row_year"]
        return nxt
    return None


def _has_future_type(
    row: List[str],
    start_idx: int,
    target_type: str,
    row_info: Dict[str, Any],
    context: Dict[str, Any],
) -> bool:
    """Checks if any valid later cell is of target_type."""
    for nxt_idx in range(start_idx + 1, len(row)):
        if nxt_idx == 0:
            continue
        nxt = _get_cell_info(nxt_idx, row[nxt_idx], context)
        if not nxt.get("valid"):
            continue
        if row_info["row_year"] and not nxt.get("year"):
            nxt["year"] = row_info["row_year"]
        if nxt.get("type") == target_type:
            return True
    return False

def _cluster_cells(row: List[str], row_info: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups = []
    current_group = {}
    
    for c_idx, val in enumerate(row):
        if c_idx == 0: continue
        
        cell = _get_cell_info(c_idx, val, context)
        if not cell["valid"]:
            continue
            
        # Apply row year if cell lacks specific year
        if row_info["row_year"] and not cell["year"]:
            cell["year"] = row_info["row_year"]
            
        # If cell has year and row has year, and they differ, cell year takes precedence (already set)

        can_merge = _can_merge(current_group, cell)

        # Keep adjacent value columns together when a later percentage exists.
        # This avoids splitting rows like [covered_count, total_count, coverage_pct]
        # into two independent groups that later double-count semantics.
        if not can_merge and current_group:
            g_types = current_group.get("types", set())
            group_is_value_only = bool(g_types) and all(t in {"value", "dollar"} for t in g_types)
            cell_is_value = cell["type"] in {"value", "dollar"}
            if group_is_value_only and cell_is_value:
                if _has_future_type(row, c_idx, "percentage", row_info, context):
                    can_merge = True

        if can_merge:
            _merge_cell(current_group, cell, context)
        else:
            if current_group:
                groups.append(current_group)
            current_group = {}
            _merge_cell(current_group, cell, context)
            
    if current_group:
        groups.append(current_group)
        
    return groups

def _render_sentence(group: Dict[str, Any], row_info: Dict[str, Any], context: Dict[str, Any]) -> Optional[str]:
    if not group: return None
    
    year = group.get("year")
    items = group.get("items", [])
    if not items: return None

    verb = "was"

    # Helper to clean headers (deduplicated logic)
    def _clean_h(h):
        if not h: return ""
        if year and str(year) in h:
             clean_h = re.sub(r'[^a-zA-Z]', '', h)
             if len(clean_h) < 3:
                 return ""
        return h

    # Check for Value + Percentage pair (common case)
    values = [i for i in items if i["type"] in ["dollar", "value"]]
    percents = [i for i in items if i["type"] == "percentage"]
    
    # Strict check for simple pair: exactly 2 items, one value, one percent
    is_simple_pair = (len(items) == 2 and len(values) == 1 and len(percents) == 1)

    # --- New Logic for Complex/Merged Cells ---
    # If we have multiple items that aren't a simple Value/Percent pair, try verbose format
    if len(items) > 1 and not is_simple_pair:
        # Check if we have headers to make a descriptive sentence
        items_with_headers = [i for i in items if _clean_h(i["header"])]
        
        # If we have headers for at least one item, use the verbose format
        if items_with_headers:
            parts = []
            for i in items:
                val = i["val"]
                h = _clean_h(i["header"])
                if h:
                    parts.append(f"{h} {verb} {val}")
                else:
                    parts.append(val)
            
            intro_parts = []
            if year:
                intro_parts.append(f"In {year},")
            intro_parts.append(f"for {row_info['label']},")
            
            return f"{' '.join(intro_parts)} {', '.join(parts)}."

    
    # Construct Subject
    headers = [i["header"] for i in items if i["header"]]
    unique_headers = []
    seen = set()
    for h in headers:
        if h not in seen:
            unique_headers.append(h)
            seen.add(h)
            
    clean_headers = []
    for h in unique_headers:
        ch = _clean_h(h)
        if ch:
            clean_headers.append(ch)
        
    subject = row_info["label"]
    if clean_headers:
        subject += f" ({', '.join(clean_headers)})"
        
    # Construct Value String
    val_str = ""
    if is_simple_pair:
        val_str = f"{values[0]['val']} ({percents[0]['val']})"
    elif values and percents:
        # Fallback for mixed bag that isn't a simple pair but has both
        val_str = ", ".join([i["val"] for i in items])
    else:
        val_str = " ".join([i["val"] for i in items])
        
    parts = []
    if year:
        parts.append(f"In {year},")
    parts.append(subject)
    parts.append(verb)
    parts.append(val_str)
    
    return " ".join(parts) + "."

SentenceRenderer = Callable[[Dict[str, Any], Dict[str, Any], Dict[str, Any]], Optional[str]]


def generate_primitive_sentences(
    processed_table: Dict[str, Any],
    renderer: Optional[SentenceRenderer] = None,
) -> List[str]:
    """
    Generates primitive sentences from a processed table dictionary using heuristics.

    Args:
        processed_table: Output from table processing.
        renderer: Optional custom sentence renderer with signature
            (group, row_info, context) -> sentence or None.
            Defaults to this module's `_render_sentence`.
    """
    context = _extract_context(processed_table)
    sentences = []
    active_renderer = renderer or _render_sentence
    
    for r_idx, row in enumerate(context['data']):
        if not row: continue
        
        row_info = _extract_row_info(r_idx, row, context)
        if not row_info['valid']: continue
        
        groups = _cluster_cells(row, row_info, context)
        
        for group in groups:
            sent = active_renderer(group, row_info, context)
            if sent:
                sentences.append(sent)
                
    return sentences
