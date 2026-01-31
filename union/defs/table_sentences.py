from typing import List, Dict, Any, Optional
import re
from defs.table_processor import MAJOR_CURRENCIES, YEAR_REGEX

# Regex to remove footnote markers like (1), [a], *, †
FOOTNOTE_REGEX = re.compile(r'(\(\d+\)|\[\w+\]|[\*\†\‡]+)$')
CLEAN_NUM_REGEX = re.compile(r'[^\d\.\-]')

def _clean_cell(text: str) -> str:
    """Removes footnote markers and extra whitespace."""
    if not text:
        return ""
    # Remove trailing footnote markers
    cleaned = FOOTNOTE_REGEX.sub('', text.strip())
    return cleaned.strip()

def _format_value(val: str, col_type: Optional[str], multiplier: float, currency: str) -> str:
    """
    Formats the value with currency, multipliers, and type awareness.
    Example: 1.5 with multiplier 1,000,000 -> 1,500,000 (with commas, else the cleaner will think it is a year)
    """
    val = _clean_cell(val)
    if not val:
        return ""
    
    # 1. Check for Percentage
    # If explicitly typed as percentage or contains %, treat as percent (ignore multiplier)
    if col_type == 'percentage' or '%' in val:
        if '%' not in val:
            return f"{val}%"
        return val

    # 2. Check for Date (don't multiply dates)
    if col_type == 'date':
        return val

    # 3. Numeric Processing
    # Try to parse as number to apply multiplier
    # We strip currency symbols and commas for parsing
    raw_num_str = CLEAN_NUM_REGEX.sub('', val)
    
    try:
        # Handle parentheses for negative numbers if present in original string (e.g. "(500)")
        is_negative = "(" in val and ")" in val
        
        if not raw_num_str:
            return val
            
        num = float(raw_num_str)
            
        # Apply Multiplier Logic
        num = num * multiplier
        # If the number >=1000, then remove the decimals, 
        # else keep two decimals only if it is not an integer
        if num >= 1000:
            num = int(num)
        elif int(num) != num:
            num = round(num, 2)
        else:
            num = int(num)
        # Convert it to a string with commas
        num = f"{num:,}"
          
        if is_negative:
            # Convert it back to parenthesis
            num = f"({num})"
        
        # Determine Currency Symbol
        has_symbol = False
        for props in MAJOR_CURRENCIES.values():
            if any(s in val for s in props["symbols"]):
                has_symbol = True
                break

        has_currency = has_symbol or '$' in val or col_type == 'dollar'
        
        if has_currency:
            curr_props = MAJOR_CURRENCIES.get(currency)
            if curr_props:
                sym = curr_props["symbols"][0]
            else:
                sym = "$" if currency == "USD" else f"{currency} "
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

        if _can_merge(current_group, cell):
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
        # Filter out headers that are just the year
        if year and str(year) in h:
             clean_h = re.sub(r'[^a-zA-Z]', '', h)
             if len(clean_h) < 3:
                 continue
        clean_headers.append(h)
        
    subject = row_info["label"]
    if clean_headers:
        subject += f" ({', '.join(clean_headers)})"
        
    # Construct Value String
    values = [i["val"] for i in items if i["type"] in ["dollar", "value"]]
    percents = [i["val"] for i in items if i["type"] == "percentage"]
    
    val_str = ""
    if values and percents:
        val_str = f"{values[0]} ({percents[0]})"
        if len(values) > 1 or len(percents) > 1:
             val_str = ", ".join([i["val"] for i in items])
    else:
        val_str = " ".join([i["val"] for i in items])
        
    verb = "was" if year and year < 2025 else "is"
    
    parts = []
    if year:
        parts.append(f"In {year},")
    parts.append(subject)
    parts.append(verb)
    parts.append(val_str)
    
    return " ".join(parts) + "."

def generate_primitive_sentences(processed_table: Dict[str, Any]) -> List[str]:
    """
    Generates primitive sentences from a processed table dictionary using heuristics.
    """
    context = _extract_context(processed_table)
    sentences = []
    
    for r_idx, row in enumerate(context['data']):
        if not row: continue
        
        row_info = _extract_row_info(r_idx, row, context)
        if not row_info['valid']: continue
        
        groups = _cluster_cells(row, row_info, context)
        
        for group in groups:
            sent = _render_sentence(group, row_info, context)
            if sent:
                sentences.append(sent)
                
    return sentences
