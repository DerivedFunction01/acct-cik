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

def generate_primitive_sentences(processed_table: Dict[str, Any]) -> List[str]:
    """
    Generates primitive sentences from a processed table dictionary using heuristics.
    """
    sentences = []
    data = processed_table.get("data", [])
    headers = processed_table.get("headers", {})
    types = processed_table.get("types", {})
    col_years = processed_table.get("years", {})
    row_years = processed_table.get("row_years", {})
    info = processed_table.get("info", {})
    
    caption = _clean_cell(info.get("caption", ""))
    currency = info.get("currency", "USD")
    col_currencies = {}
    
    symbol_map = {}
    for code, props in MAJOR_CURRENCIES.items():
        for s in props["symbols"]:
            symbol_map[s] = code

    multiplier = info.get("global_multiplier", 1.0)
    
    # Heuristic: Extract year from caption if available
    caption_year = None
    m = YEAR_REGEX.search(caption)
    
    if m:
        caption_year = int(m.group(0))
    
    for r_idx, row in enumerate(data):
        if not row:
            continue
        
        # 1. Row Label
        row_label = _clean_cell(row[0])
        if not row_label:
            continue
            
        # 2. Row Context (Year from section header)
        row_year = row_years.get(r_idx)
        
        for c_idx, cell_value in enumerate(row):
            if c_idx == 0: # Skip label column
                continue
            
            val = cell_value.strip()
            if not val or val in ["-", "—", "N/A", "n/a"]:
                continue
            
            # Update currency if symbol found (longest match first)
            for sym in sorted(symbol_map.keys(), key=len, reverse=True):
                if sym in val:
                    col_currencies[c_idx] = symbol_map[sym]
                    break

            # 3. Column Context
            header = _clean_cell(headers.get(c_idx, ""))
            col_type = types.get(c_idx)
            col_year = col_years.get(c_idx)
            
            # 4. Resolve Year (Column > Row > Caption)
            year = col_year if col_year else (row_year if row_year else caption_year)
            
            # 5. Construct Sentence
            parts = []
            
            # [Time]
            if year:
                parts.append(f"In {year},")
            
            # [Subject]
            # Combine Row Label and Header
            # If header is essentially just the year, don't repeat it in subject
            is_year_header = False
            if year and str(year) in header:
                # Check if header has other meaningful text
                clean_header = re.sub(r'[^a-zA-Z]', '', header)
                if len(clean_header) < 3: # e.g. "FY" or empty
                    is_year_header = True
            
            if header and not is_year_header:
                # Heuristic: "Employees (North America)"
                subject = f"{row_label} ({header})"
            else:
                subject = row_label
            
            parts.append(subject)
            
            # [Verb]
            # "was" for past, "is" for present/future/unknown
            verb = "was" if year and year < 2025 else "is"
            parts.append(verb)
            
            # [Value]
            effective_currency = col_currencies.get(c_idx, currency)
            formatted_val = _format_value(val, col_type, multiplier, effective_currency)
            parts.append(formatted_val)
            
            # [Context/Caption]
            if caption:
                # Clean caption of newlines
                clean_caption = caption.replace('\n', ' ')
                parts.append(f"[{clean_caption}]")
            
            # Finalize
            sentences.append(" ".join(parts) + ".")
    
    return sentences