from typing import List, Dict, Any

def generate_primitive_sentences(processed_table: Dict[str, Any]) -> List[str]:
    """
    Generates primitive sentences from a processed table dictionary.
    
    Args:
        processed_table: Dictionary containing 'data', 'headers', 'types', 'info'.
                         (Output from table_processor.process_table)
                         
    Returns:
        List of primitive sentences constructed from the table.
    """
    sentences = []
    data = processed_table.get("data", [])
    headers = processed_table.get("headers", {})
    info = processed_table.get("info", {})
    
    caption = info.get("caption", "")
    
    for row in data:
        if not row:
            continue
        
        # Assume first column is the row label (stub)
        row_label = row[0].strip()
        if not row_label:
            continue
        
        for col_idx, cell_value in enumerate(row):
            if col_idx == 0:
                continue
            
            val = cell_value.strip()
            if not val:
                continue
            
            header = headers.get(col_idx, "").strip()
            
            # Construct primitive sentence: "[Caption] | Row Label (Header) is Value."
            # Example: "Employees (Total) is 500."
            parts = []
            if caption:
                parts.append(f"{caption} |")
            
            parts.append(row_label)
            if header:
                parts.append(f"({header})")
            
            parts.append("is")
            parts.append(val)
            
            sentences.append(" ".join(parts) + ".")
    
    return sentences