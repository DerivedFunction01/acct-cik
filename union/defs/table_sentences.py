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

def _build_context(processed_table: Dict[str, Any]) -> Dict[str, Any]:
    info = processed_table.get("info", {})
    caption = _clean_cell(info.get("caption", ""))
    
    # Heuristic: Extract year from caption if available
    caption_year = None
    m = YEAR_REGEX.search(caption)
    if m:
        caption_year = int(m.group(0))

    symbol_map = {}
    for code, props in MAJOR_CURRENCIES.items():
        for s in props["symbols"]:
            symbol_map[s] = code

    return {
        "data": processed_table.get("data", []),
        "headers": processed_table.get("headers", {}),
        "types": processed_table.get("types", {}),
        "col_years": processed_table.get("years", {}),
        "row_years": processed_table.get("row_years", {}),
        "caption": caption,
        "caption_year": caption_year,
        "default_currency": info.get("currency", "USD"),
        "multiplier": info.get("global_multiplier", 1.0),
        "symbol_map": symbol_map,
        "col_currencies": {} 
    }

def _resolve_year(col_year: Optional[int], row_year: Optional[int], caption_year: Optional[int]) -> Optional[int]:
    return col_year if col_year else (row_year if row_year else caption_year)

def _update_col_currency(val: str, c_idx: int, ctx: Dict[str, Any]):
    symbol_map = ctx["symbol_map"]
    # Update currency if symbol found (longest match first)
    for sym in sorted(symbol_map.keys(), key=len, reverse=True):
        if sym in val:
            ctx["col_currencies"][c_idx] = symbol_map[sym]
            break

def _construct_subject(row_label: str, header: str, year: Optional[int]) -> str:
    is_year_header = False
    if year and str(year) in header:
        # Check if header has other meaningful text
        clean_header = re.sub(r'[^a-zA-Z]', '', header)
        if len(clean_header) < 3: # e.g. "FY" or empty
            is_year_header = True
            
    if header and not is_year_header:
        # Heuristic: "Employees (North America)"
        return f"{row_label} ({header})"
    return row_label

def _construct_verb(year: Optional[int]) -> str:
    return "was" if year and year < 2025 else "is"

def _construct_sentence_string(year: Optional[int], subject: str, verb: str, val_str: str, caption: str) -> str:
    parts = []
    if year:
        parts.append(f"In {year},")
    parts.append(subject)
    parts.append(verb)
    parts.append(val_str)
    if caption:
        clean_caption = caption.replace('\n', ' ')
        parts.append(f"[{clean_caption}]")
    return " ".join(parts) + "."

def _process_cell(c_idx: int, val: str, row_label: str, row_year: Optional[int], ctx: Dict[str, Any]) -> Optional[str]:
    val = val.strip()
    if not val or val in ["-", "—", "N/A", "n/a"]:
        return None

    _update_col_currency(val, c_idx, ctx)
    
    header = _clean_cell(ctx["headers"].get(c_idx, ""))
    col_type = ctx["types"].get(c_idx)
    col_year = ctx["col_years"].get(c_idx)
    
    year = _resolve_year(col_year, row_year, ctx["caption_year"])
    
    subject = _construct_subject(row_label, header, year)
    verb = _construct_verb(year)
    
    effective_currency = ctx["col_currencies"].get(c_idx, ctx["default_currency"])
    formatted_val = _format_value(val, col_type, ctx["multiplier"], effective_currency)
    
    return _construct_sentence_string(year, subject, verb, formatted_val, ctx["caption"])

def _process_row(r_idx: int, row: List[str], ctx: Dict[str, Any]) -> List[str]:
    if not row:
        return []
    
    row_label = _clean_cell(row[0])
    if not row_label:
        return []
        
    row_year = ctx["row_years"].get(r_idx)
    sentences = []
    
    for c_idx, cell_value in enumerate(row):
        if c_idx == 0: continue
        sent = _process_cell(c_idx, cell_value, row_label, row_year, ctx)
        if sent:
            sentences.append(sent)
            
    return sentences

def generate_primitive_sentences(processed_table: Dict[str, Any]) -> List[str]:
    """
    Generates primitive sentences from a processed table dictionary using heuristics.
    """
    ctx = _build_context(processed_table)
    sentences = []
    
    for r_idx, row in enumerate(ctx["data"]):
        sentences.extend(_process_row(r_idx, row, ctx))
    
    return sentences