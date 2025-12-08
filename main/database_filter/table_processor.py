import re
from typing import List, Dict, Optional, Tuple

from derivative_regex import (
    SOFT_REGEX,
    TABLE_REGEX,
    YEAR_REGEX,
    STRICT_REGEX,
    SOFT_GEN_REGEX,  # Imported for caption analysis
)

# --- 1. EXPANDED HEADER DEFINITIONS ---
CONTEXT_HEADERS = re.compile(
    r"purpose|risk|objective|hedged item|comments|description", re.IGNORECASE
)
VAR_HEADERS = re.compile(r"\bvar\b|value[- ]at[- ]risk", re.IGNORECASE)
NOTIONAL_HEADERS = re.compile(
    r"notional|principal|contract\s+(?:amount|volume|value)", re.IGNORECASE
)
NET_HEADERS = re.compile(r"net\s+amount|net\s+presented|total\s+net", re.IGNORECASE)
GROSS_HEADERS = re.compile(r"gross\s+amount|gross\s+recognized", re.IGNORECASE)
LEVEL_HEADERS = re.compile(r"level\s*[123]", re.IGNORECASE)
VALUE_HEADERS = re.compile(r"(?:fair|market|carrying)\s+value|balance", re.IGNORECASE)
ASSET_HEADERS = re.compile(r"asset", re.IGNORECASE)
LIABILITY_HEADERS = re.compile(r"liabilit", re.IGNORECASE)
GAIN_LOSS_HEADERS = re.compile(
    r"gain|loss|income|earnings|oci|comprehensive", re.IGNORECASE
)
LOCATION_HEADERS = re.compile(r"location|sheet|line item", re.IGNORECASE)
NOISE_HEADERS = re.compile(
    r"strike|exercise|shares|units|count|ratio|rate|maturity|date|weighted",
    re.IGNORECASE,
)
SECTION_KEYWORDS = re.compile(
    r"designated as|hedging instruments|underlying risk|derivatives not designated|"
    r"cash flow|fair value|net investment|assets|liabilities|equity contracts|warrants|"
    r"embedded|offsetting|trading|non[- ]?trading|held for|financial instruments",
    re.IGNORECASE,
)
# NEW: Specific regex for the sophisticated exception
SOPHISTICATED_TARGETS = re.compile(
    r"\b(?:convertibles?|warrants?|conversion)\b", re.IGNORECASE
)

TABLE_ANCHOR = " T_ "


class TableToTextConverter:

    def __init__(
        self,
        table_text: str,
        narrative_context: str = "",
        is_sophisticated: bool = False,
    ):
        self.raw_text = table_text
        self.narrative_context = narrative_context
        self.is_sophisticated = is_sophisticated

        # 1. Extract & Analyze Caption
        self.caption = self._extract_caption(table_text)

        # NEW: Check Caption for Strong Signal immediately
        full_context = f"{self.caption} {self.narrative_context}"
        
        # If caption says "Derivative Instruments" or "Hedging Activities", the whole table is safe.
        self.caption_is_strong = bool(
            STRICT_REGEX.search(full_context) or SOFT_GEN_REGEX.search(full_context)
        )
        
        self.table_default_type = self._analyze_caption_context(full_context)

        # 2. Extract Data
        self.headers, self.data = self.extract_table_content(table_text)
        self.flattened_headers = self._flatten_headers()

        # 3. Classify Columns
        self.col_map = {
            i: self._classify_column(h) for i, h in enumerate(self.flattened_headers)
        }

        self._apply_column_heuristics()
        self._resolve_offsetting_conflicts()
        
    def extract_table_content(self, table_text: str) -> Tuple[List[List[str]], List[List[str]]]:
        """
        Parses a raw <TABLE> string into headers and data rows.
        Uses <S> and <C> tags (present in older SEC filings) to identify where data starts.
        Falls back to first row as header if no tags found (artificial tables).
        """
        lines = table_text.split("\n")
        content_rows = []

        # 1. Extract content rows (skip TABLE/CAPTION tags and separator rows)
        for line in lines:
            line = line.strip()
            if "<TABLE>" in line or "<CAPTION>" in line or "</TABLE>" in line:
                continue
            if not line:  # Empty lines
                continue
            # Skip separator rows (dashes or equal signs)
            if all(c in "- =" for c in line) and any(c in "-=" for c in line):
                continue
            content_rows.append(line)

        # 2. Find first row with <S> or <C> tags (marks data start in older filings)
        data_start_idx = None
        for i, row in enumerate(content_rows):
            if "<S>" in row or "<C>" in row:
                data_start_idx = i
                break

        # 3. Split headers and data based on tag markers
        if data_start_idx is not None:
            headers = content_rows[:data_start_idx]
            data = content_rows[data_start_idx:]
        else:
            # No tags found - use first row as header (artificial tables)
            if content_rows:
                headers = [content_rows[0]]
                data = content_rows[1:]
            else:
                headers = []
                data = []

        # 4. Cell Parsing (Split by 2+ spaces)
        def parse_row(row: str) -> List[str]:
            row = row.replace("<S>", "").replace("<C>", "")  # Remove tags
            cells = re.split(r"\s{2,}", row.strip())
            return [c.strip() for c in cells if c.strip()]

        header_cells = [parse_row(h) for h in headers]
        data_cells = [parse_row(d) for d in data]

        return header_cells, data_cells

    def _extract_caption(self, text: str) -> str:
        """Extracts text following the <caption> tag."""
        match = re.search(r"<caption>\s*(.*)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def _analyze_caption_context(self, caption: str) -> Optional[str]:
        """Determines default value type from caption."""
        if not caption:
            return None

        caption_lower = caption.lower()

        if NOTIONAL_HEADERS.search(caption_lower):
            return "notional"
        if VAR_HEADERS.search(caption_lower):
            return "fair_value"
        if VALUE_HEADERS.search(caption_lower):
            return "fair_value"
        if GAIN_LOSS_HEADERS.search(caption_lower):
            return "gain_loss"

        return None

    def _flatten_headers(self) -> List[str]:
        if not self.headers:
            return []
        num_cols = max(len(h) for h in self.headers)
        flat_headers = []
        for col_idx in range(num_cols):
            col_parts = []
            for row in self.headers:
                if col_idx < len(row) and row[col_idx].strip():
                    part = row[col_idx].strip()
                    if not set(part).issubset(set("-= ")):
                        col_parts.append(part)
            flat_headers.append(" ".join(col_parts))
        return flat_headers

    def _classify_column(self, header: str) -> Optional[str]:
        header = header.lower()
        if NOISE_HEADERS.search(header):
            return None

        year_match = YEAR_REGEX.search(header)
        year_suffix = f"_{year_match.group(0)}" if year_match else ""

        col_type = None
        if CONTEXT_HEADERS.search(header):
            return "context_text"
        elif VAR_HEADERS.search(header):
            col_type = "fair_value"
        elif NOTIONAL_HEADERS.search(header):
            col_type = "notional"
        elif NET_HEADERS.search(header):
            col_type = "net_fair_value"
        elif GROSS_HEADERS.search(header):
            col_type = "gross_fair_value"
        elif LEVEL_HEADERS.search(header):
            col_type = "fair_value"
        elif VALUE_HEADERS.search(header):
            if ASSET_HEADERS.search(header):
                col_type = "asset_fair_value"
            elif LIABILITY_HEADERS.search(header):
                col_type = "liability_fair_value"
            else:
                col_type = "fair_value"

        if not col_type and year_suffix:
            if self.table_default_type:
                col_type = self.table_default_type
            else:
                col_type = "value"

        if col_type:
            return f"{col_type}{year_suffix}"

        return None

    def _cleanup_spaced_value(self, val: str) -> str:
        val = re.sub(r"(\d)\s+([().,])", r"\1\2", val)
        val = re.sub(r"([().,])\s+(\d)", r"\1\2", val)
        val = re.sub(r"\s+", "", val)
        return val

    def _is_valid_value(self, val: str) -> bool:
        clean = self._cleanup_spaced_value(val)
        clean = re.sub(r"[(),$€£¥%]", "", clean).strip()
        if clean in ["-", "—", "0", "0.0", "", "0.00", "--"]:
            return False
        return bool(re.match(r"^-?\d+(?:\.\d+)?$", clean))

    def _apply_column_heuristics(self):
        TARGET_IDX = 1
        if TARGET_IDX not in self.col_map or self.col_map[TARGET_IDX] is not None:
            return
        text_rows = 0
        numeric_rows = 0
        for row in self.data[:5]:
            if len(row) > TARGET_IDX:
                cell = row[TARGET_IDX].strip()
                if not cell or set(cell).issubset(set("- ")):
                    continue
                if self._is_valid_value(cell):
                    numeric_rows += 1
                else:
                    text_rows += 1
        if text_rows > 0 and numeric_rows == 0:
            self.col_map[TARGET_IDX] = "context_text"

    def _resolve_offsetting_conflicts(self):
        has_net = any(t == "net_fair_value" for t in self.col_map.values())
        if has_net:
            for idx, col_type in self.col_map.items():
                if col_type == "gross_fair_value":
                    self.col_map[idx] = None

    def _is_subheader_row(self, row: List[str]) -> bool:
        if not row or not row[0].strip():
            return False
        if SECTION_KEYWORDS.search(row[0]):
            return True
        has_data = False
        for i, cell in enumerate(row[1:], start=1):
            if (
                i in self.col_map
                and self.col_map[i]
                and self.col_map[i] != "context_text"
                and self._is_valid_value(cell)
            ):
                has_data = True
                break
        return not has_data

    def _merge_row_values(self, row: List[str]) -> List[str]:
        merged = row[:]
        fragment_pattern = re.compile(r"^[()$€£¥%—\-\s]+$")
        value_pattern = re.compile(r"\d")

        i = 0
        while i < len(merged):
            cell = merged[i].strip()
            if cell and fragment_pattern.match(cell):
                j = i + 1
                while j < len(merged) and j < i + 3:
                    next_cell = merged[j].strip()
                    if value_pattern.search(next_cell):
                        merged[j] = cell + merged[j]
                        merged[i] = ""
                        break
                    elif fragment_pattern.match(next_cell):
                        j += 1
                    else:
                        break
            i += 1

        for i in range(len(merged)):
            cell = merged[i].strip()
            if value_pattern.search(cell) and not fragment_pattern.match(cell):
                for offset in [1, 2]:
                    if i - offset >= 0:
                        left = merged[i - offset].strip()
                        if left and fragment_pattern.match(left):
                            merged[i] = left + merged[i]
                            merged[i - offset] = ""
                        else:
                            break
                if i + 1 < len(merged):
                    right = merged[i + 1].strip()
                    if right and fragment_pattern.match(right):
                        merged[i] = merged[i] + right
                        merged[i + 1] = ""
        return merged

    def normalize_value(self, clean_val: str):
        stripped = clean_val.strip("()")
        try:
            norm_num = float(stripped.replace(",", ""))
            num = abs(norm_num)
            if num == 0:
                return "$0"
            else:
                formatted = "$(__)" if norm_num < 0 else "$__"
                if num > 1000:
                    num_str = "{:,.0f}".format(num)
                else:
                    num_str = "{:,.2f}".format(num)
                return formatted.replace("__", num_str)
        except ValueError:
            return clean_val

    def process(self) -> List[str]:
        sentences = []

        # --- PASS 1: SCAN FOR STRONG SIGNALS ---
        table_has_notional_col = any(
            "notional" in str(v) for v in self.col_map.values()
        ) or (self.table_default_type == "notional")

        candidate_rows = []
        active_context = []
        table_has_strong_row = False

        for row in self.data:
            if not row:
                continue

            if self._is_subheader_row(row):
                active_context = [row[0].strip().rstrip(":")]
                continue

            row_label = row[0].strip()
            if not row_label or "total" in row_label.lower():
                continue

            row = self._merge_row_values(row)

            row_context_str = ""
            for i, cell_val in enumerate(row[1:], start=1):
                if self.col_map.get(i) == "context_text":
                    clean_text = re.sub(r"\s+", " ", cell_val).strip()
                    if clean_text and len(clean_text) > 2:
                        row_context_str = f" ({clean_text})"

            full_instrument_name = (
                f"{' '.join(active_context)} {row_label}{row_context_str}"
            )

            row_implies_notional = bool(NOTIONAL_HEADERS.search(full_instrument_name))
            is_strict = bool(STRICT_REGEX.search(full_instrument_name))
            is_table_safe = bool(TABLE_REGEX.search(full_instrument_name))
            is_soft = bool(SOFT_REGEX.search(full_instrument_name))

            if is_strict or is_table_safe or row_implies_notional:
                table_has_strong_row = True

            candidate_rows.append(
                {
                    "row": row,
                    "name": full_instrument_name,
                    "is_strong": is_strict or is_table_safe or row_implies_notional,
                    "is_soft": is_soft,
                    "implies_notional": row_implies_notional,
                }
            )

        # --- GLOBAL SIGNAL CHECK ---
        # 1. Row/Column Anchors
        # 2. Caption Anchor (NEW: If caption says "Derivatives", the table is safe)
        table_is_anchored = (
            table_has_strong_row or table_has_notional_col or self.caption_is_strong
        )

        # --- PASS 2: GENERATE SENTENCES ---
        for cand in candidate_rows:

            # Exception Logic (Convertibles/Warrants for sophisticated firms)
            is_sophisticated_exception = (
                self.is_sophisticated and SOPHISTICATED_TARGETS.search(cand["name"])
            )

            # FILTER LOGIC
            should_keep = False

            if cand["is_strong"]:
                should_keep = True
            elif cand["is_soft"]:
                if table_is_anchored:
                    should_keep = True
                elif is_sophisticated_exception:
                    should_keep = True

            if not should_keep:
                continue

            # Extract Values & Generate Sentences
            row = cand["row"]
            full_instrument_name = cand["name"]
            row_implies_notional = cand["implies_notional"]

            for i, cell_val in enumerate(row[1:], start=1):
                col_type = self.col_map.get(i)
                if (
                    not col_type
                    or col_type == "context_text"
                    or not self._is_valid_value(cell_val)
                ):
                    continue

                clean_val = self._cleanup_spaced_value(cell_val)
                if "(" in clean_val and ")" in clean_val:
                    clean_val = "-" + clean_val.replace("(", "").replace(")", "")
                clean_val = clean_val.replace("$", "").replace(",", "").strip()

                parts = col_type.split("_")
                year_str = ""
                if parts[-1].isdigit() and len(parts[-1]) == 4:
                    year_str = f"in {parts.pop()} "

                base_type = "_".join(parts)
                value = self.normalize_value(clean_val)

                if "notional" in base_type or row_implies_notional:
                    sentences.append(
                        f"{TABLE_ANCHOR} {year_str}The Company held {full_instrument_name} with a notional amount of {value}."
                    )
                elif "fair_value" in base_type:
                    sentences.append(
                        f"{TABLE_ANCHOR} {year_str}The Company held {full_instrument_name} with a fair value of {value}."
                    )
                elif base_type == "value":
                    sentences.append(
                        f"{TABLE_ANCHOR} {year_str}The Company held {full_instrument_name} with a value of {value}."
                    )
                else:
                    # Fallback: use generic "amount"
                    sentences.append(
                        f"{TABLE_ANCHOR} {year_str}The Company held {full_instrument_name} with an amount of {value}."
                    )

        return sentences
    
    def is_valid_table(self) -> Tuple[bool, bool]:
        """
        Determines if this is a valid table and whether it should be unwrapped.
        
        Returns: (is_derivative_table, should_unwrap)
        
        Cases:
        1. (True, False)   - Valid derivative table → KEEP as <TABLE>
        2. (False, False)  - Valid non-derivative table (has numerical cells) → DISCARD
        3. (False, True)   - Invalid/container table (no numerical cells) → UNWRAP to text
        """
        
        # 1. Check if table has any numerical financial cells
        has_numerical_cells = False
        
        for row in self.data:
            if not row:
                continue
            
            if self._is_subheader_row(row):
                continue
            
            row_label = row[0].strip()
            if not row_label or "total" in row_label.lower():
                continue
            
            # Check if any cell in this row is a valid numerical value
            for i, cell_val in enumerate(row[1:], start=1):
                col_type = self.col_map.get(i)
                if col_type and col_type != "context_text" and self._is_valid_value(cell_val):
                    has_numerical_cells = True
                    break
            
            if has_numerical_cells:
                break
        
        # If no numerical cells found → invalid/container table, should unwrap
        if not has_numerical_cells:
            return (False, True)
        
        # 2. Now check if it's a derivative table (has derivative signals)
        
        # Caption Check - Strong Signal
        if self.caption_is_strong:
            return (True, False)
        
        # Column Check - Has notional or fair value columns
        has_notional_col = any(
            "notional" in str(v) for v in self.col_map.values()
        ) or (self.table_default_type == "notional")
        
        has_value_col = any(
            "fair_value" in str(v) or "value" in str(v) 
            for v in self.col_map.values()
        )
        
        if has_notional_col or has_value_col:
            return (True, False)
        
        # Row Check - Scan for derivative signals
        for row in self.data:
            if not row:
                continue
            
            if self._is_subheader_row(row):
                continue
            
            row_label = row[0].strip()
            if not row_label or "total" in row_label.lower():
                continue
            
            # Build full instrument name
            row = self._merge_row_values(row)
            row_context_str = ""
            for i, cell_val in enumerate(row[1:], start=1):
                if self.col_map.get(i) == "context_text":
                    clean_text = re.sub(r"\s+", " ", cell_val).strip()
                    if clean_text and len(clean_text) > 2:
                        row_context_str = f" ({clean_text})"
            
            full_instrument_name = f"{row_label}{row_context_str}"
            
            # Check derivative signals
            is_strict = bool(STRICT_REGEX.search(full_instrument_name))
            is_table_safe = bool(TABLE_REGEX.search(full_instrument_name))
            row_implies_notional = bool(NOTIONAL_HEADERS.search(full_instrument_name))
            
            if is_strict or is_table_safe or row_implies_notional:
                return (True, False)
        
        # 3. Has numerical cells but no derivative signals
        # → Valid non-derivative table (income statement, balance sheet, etc.)
        return (False, False)
