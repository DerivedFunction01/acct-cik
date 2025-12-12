# %%
import re
from typing import List, Dict, Optional, Set, Tuple

from derivative_regex import BASE_REGEX, CURRENCY_NAMES_REGEX, FX_SOFT_REGEX, IR_SOFT_REGEX, SOFT_GEN_REGEX, SOFT_REGEX, STRICT_REGEX, TABLE_REGEX, YEAR_REGEX

# --- REGEX DEFINITIONS ---

# Basic patterns
YEAR_SLASH_REGEX = re.compile(r"\b(?:\d{1,2}/)+(\d{2,4})\b")
NUMERIC_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
NUMERIC_WITH_SYMBOLS = re.compile(r"[$€£¥,%()-]")
ACCOUNTING_NEGATIVE = re.compile(r"\(([^)]+)\)")  # Converts (100) to -100
WHITESPACE_REGEX = re.compile(r"\s+")
HTML_TAG_REGEX = re.compile(r"<[^>]+>")

import re

CAPTION_REGEX = re.compile(
    r"""
    <caption[^>]*>        # Match start tag (case-insensitive via flags)
    
    (                     # --- GROUP 1: CAPTION CONTENT ---
        .*?               # Lazily match content (including newlines)
    )
    
    (?=                   # --- LOOKAHEAD: STOP CONDITIONS ---
                          # Stop matching content when we encounter:
        
        \n\s*\n           # 1. A BLANK LINE (Double newline). 
                          #    This prevents capturing table headers in Case 2.
        |
        \n\s*<S>          # 2. The <S> tag on a new line.
        |
        \n\s* # 3. A SEPARATOR LINE.
                          #    Must be a new line starting with dashes/equals.
        (?:[-=][ \t]*){3,} #    Matches "---", "- - -", or "------------"
        |
        \Z                # 4. End of String.
    )
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)
TABLE_TAG_REGEX = re.compile(r"<TABLE.*?>", re.DOTALL | re.IGNORECASE)
S_MARKER_REGEX = re.compile(r"<S>")
C_MARKER_REGEX = re.compile(r"<C>")
TABLE_TAG_REGEX = re.compile(r"<TABLE.*?>", re.DOTALL | re.IGNORECASE)

# Spacing & Cleaning
DOLLAR_SPACE_REGEX = re.compile(r"(\$|€|£|¥)\s+")
OPEN_PAREN_SPACE_REGEX = re.compile(r"\(\s+")
CLOSE_PAREN_SPACE_REGEX = re.compile(r"\s+\)")
PERCENT_SPACE_REGEX = re.compile(r"\s+%")
COMMA_SPACE_REGEX = re.compile(r",\s+")

# Classification Headers (Expanded)
CONTEXT_HEADERS = re.compile(
    r"purpose|risk|objective|hedged item|comments|description", re.IGNORECASE
)
PERCENT_HEADERS = re.compile(r"percent|percentage|rate", re.IGNORECASE)
VAR_HEADERS = re.compile(r"\bvar\b|value[- ]at[- ]risk", re.IGNORECASE)
STRONG_NOTIONAL_REGEX = re.compile(r"notional", re.IGNORECASE)
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
MATURITY_HEADERS = re.compile(r"maturity|expiration", re.IGNORECASE)
NOISE_HEADERS = re.compile(
    r"strike|exercise|shares|units|count|ratio|weighted", re.IGNORECASE
)

DESIGNATION_REGEX = re.compile(r"designated as|hedging|trading|fair value|cash flow hedg|net investment|derivatives|aoci|income|earnings|gain|loss",re.IGNORECASE,)

SOPHISTICATED_TARGETS = re.compile(r"\b(?:convertibles?|warrants?|conversion)\b", re.IGNORECASE)
YEAR_SLASH_REGEX = re.compile(r"\b(?:\d{1,2}/)+(\d{2,4})\b")
# Paragraph Detection
TABLE_OF_CONTENTS_REGEX = re.compile(r"\.{3,}")
PARAGRAPH_THRESHOLD = 250
TABLE_ANCHOR = " T_"
DEBUG = False

# Multipliers
THOUSAND_REGEX = re.compile(
    r"(?:in|dollars\s+in)\s+thousands|\(000(?:['\s]s)?\)", re.IGNORECASE
)
MILLION_REGEX = re.compile(
    r"(?:in|dollars\s+in)\s+millions|\(000(?:,000)?(?:['\s]s)?\)", re.IGNORECASE
)
BILLION_REGEX = re.compile(r"(?:in|dollars\s+in)\s+billions", re.IGNORECASE)
UNIT_REGEX = re.compile(
    r"(?i)\s*(?:thousands?|millions?|billions?|trillions?)", re.IGNORECASE
)


def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


def convert_slash_year_to_four_digit(year_str: str) -> List[int]:
    """
    Extract all 2-digit or 4-digit years from a string, convert each to 4-digit
    using the heuristic, and return the largest resulting year.

    Heuristic:
    - If year is already 4 digits (1900-2999), keep as-is
    - If year is 2 digits:
      - 00-30 → 2000–2030
      - 31-99 → 1931–1999
    """
    if not year_str:
        return []

    try:
        matches = YEAR_SLASH_REGEX.findall(year_str)
        if not matches:
            return []

        converted_years = []
        for m in matches:
            y = int(m)
            # Already 4-digit
            if y >= 1000:
                converted_years.append(y)
            else:
                # 2-digit conversion
                if y >= 80:  # 80-99 -> 1980-1999
                    converted_years.append(1900 + y)
                else:  # 00-79 -> 2000-2079
                    converted_years.append(2000 + y)
        return converted_years
    except (ValueError, TypeError):
        return []


class TableToTextConverter:
    def __init__(
        self,
        table_text: str,
        narrative_context: str = "",
        is_sophisticated: bool = False,
    ):
        self.raw_text = table_text
        self.narrative_context = narrative_context

        self.caption = self._extract_caption(table_text)
        debug_print(f"Caption: {self.caption}")
        full_context = f"{self.caption} {self.narrative_context}"
        self.global_multiplier = self._scan_for_multiplier(self.caption) or 1.0
        self.col_multipliers = {}

        self.caption_is_strong = self.is_implied_derivative(full_context)
        self.is_sophisticated = is_sophisticated or self.caption_is_strong
        debug_print(f"Caption is strong derivative: {self.caption_is_strong}")
        self.table_default_type = self._analyze_caption_context(full_context)

        # Data-driven extraction with improved sparsity detection
        self.data, self.col_map, self.col_headers = self._extract_data_driven(
            CAPTION_REGEX.sub("", table_text)
        )

        self.invalid_table = len(self.data) == 0
        debug_print(f"Data rows extracted: {len(self.data)}")

        if self._detect_paragraph_masquerading_as_table():
            self.invalid_table = True
            debug_print(f"DETECTED PARAGRAPH: Table flagged as invalid")

        # Apply classification and refinement heuristics
        if not self.invalid_table:
            self._classify_columns_from_headers()
            self._apply_column_heuristics()
            self._resolve_offsetting_conflicts()

    def _extract_caption(self, text: str) -> str:
        match = CAPTION_REGEX.search(text)
        if match:
            caption_text = match.group(1).strip()
            caption_text = WHITESPACE_REGEX.sub(" ", caption_text)
            return caption_text
        return ""

    def _analyze_caption_context(self, caption: str) -> Optional[str]:
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

    def is_implied_derivative(self, full_context):
        return bool(
            STRICT_REGEX.search(full_context)
            or SOFT_GEN_REGEX.search(full_context)
            or IR_SOFT_REGEX.search(full_context)
            or FX_SOFT_REGEX.search(full_context)
        )

    def _detect_merge_patterns(
        self, raw_rows: List[List[str]], sparse_columns: set
    ) -> Dict[int, str]:
        """
        Detects merge directions for sparse columns based on their content.

        IMPROVED LOGIC:
        - Groups currencies and opening parens as 'prefix' (Merge Right).
        - Groups percents and closing parens as 'suffix' (Merge Left).
        - Allows mixed content if they share the same directionality (e.g. $ and ( in same column).
        """
        merge_directions = {}

        for col_idx in sparse_columns:
            col_patterns = set()

            for row in raw_rows:
                if col_idx < len(row) and row[col_idx].strip():
                    val = row[col_idx].strip()
                    if val in ["$", "€", "£", "¥"]:
                        col_patterns.add("prefix_currency")
                    elif val == "(":
                        col_patterns.add("prefix_paren")
                    elif val == ")":
                        col_patterns.add("suffix_paren")
                    elif val == "%":
                        col_patterns.add("suffix_percent")
                    else:
                        col_patterns.add("other")

            if not col_patterns:
                continue

            # Check for dominant direction
            has_prefix = (
                "prefix_currency" in col_patterns or "prefix_paren" in col_patterns
            )
            has_suffix = (
                "suffix_paren" in col_patterns or "suffix_percent" in col_patterns
            )
            has_other = "other" in col_patterns

            # Strict Logic: Only merge if purely directional or directional + empty
            if has_prefix and not has_suffix and not has_other:
                merge_directions[col_idx] = "merge_right"
            elif has_suffix and not has_prefix and not has_other:
                merge_directions[col_idx] = "merge_left"
            else:
                merge_directions[col_idx] = "skip"

        return merge_directions

    def _merge_sparse_columns(
        self, raw_rows: List[List[str]], single_width_cols: Optional[Set] = None
    ) -> Tuple[List[List[str]], Dict[int, int]]:
        """
        Merges sparse columns based on detected patterns.
        """
        if not raw_rows:
            return [], {}

        if single_width_cols is None:
            single_width_cols = set()

        # Calculate sparsity
        num_rows = len(raw_rows)
        num_cols = max(len(row) for row in raw_rows) if raw_rows else 0
        col_sparsity = {}
        for col_idx in range(num_cols):
            empty_count = sum(
                1 for row in raw_rows if col_idx >= len(row) or not row[col_idx]
            )
            sparsity = empty_count / num_rows if num_rows > 0 else 0
            col_sparsity[col_idx] = sparsity

        # Columns to check for merging: High sparsity OR single-width markers
        sparse_columns = {idx for idx, s in col_sparsity.items() if s > 0.8}
        sparse_columns.update(single_width_cols)

        if not sparse_columns:
            return raw_rows, {i: i for i in range(num_cols)}

        merge_directions = self._detect_merge_patterns(raw_rows, sparse_columns)

        merged_rows = []
        col_mapping = {}

        for row in raw_rows:
            merged_row = []
            skip_next = False
            row_col_mapping = {}

            for col_idx in range(len(row)):
                if skip_next:
                    skip_next = False
                    continue

                cell = row[col_idx]
                strategy = merge_directions.get(col_idx, "keep")
                new_col_idx = len(merged_row)

                # --- MERGE RIGHT LOGIC ---
                if strategy == "merge_right":
                    # Look ahead
                    if col_idx + 1 < len(row):
                        next_cell = row[col_idx + 1]
                        # Concatenate
                        merged_row.append((cell + next_cell).strip())
                        skip_next = True

                        # Update mapping
                        row_col_mapping[col_idx] = new_col_idx
                        row_col_mapping[col_idx + 1] = new_col_idx
                    else:
                        # End of row, can't merge right
                        merged_row.append(cell)
                        row_col_mapping[col_idx] = new_col_idx

                # --- MERGE LEFT LOGIC ---
                elif strategy == "merge_left":
                    # Append to previous cell if exists
                    if merged_row:
                        merged_row[-1] = (merged_row[-1] + cell).strip()
                        row_col_mapping[col_idx] = len(merged_row) - 1
                    else:
                        # Start of row, can't merge left
                        merged_row.append(cell)
                        row_col_mapping[col_idx] = new_col_idx

                # --- NO MERGE ---
                else:
                    merged_row.append(cell)
                    row_col_mapping[col_idx] = new_col_idx

            if not col_mapping:
                col_mapping = row_col_mapping

            merged_rows.append(merged_row)

        return merged_rows, col_mapping

    def _clean_and_merge_symbols(self, row: List[str]) -> List[str]:
        """
        Robust post-processing to clean up split symbols ($ . 100) or ( 100 ).

        CONSTRAINTS:
        1. Currency ($) and Opening Paren (() must ONLY merge RIGHT.
        2. Percent (%) and Closing Paren ()) must ONLY merge LEFT.
        3. Merges only occur if the neighbor is numeric-like or complementary.
        """
        # Pass 1: Clean internal spacing (e.g. "$ 100" -> "$100")
        cleaned_row = []
        for cell in row:
            if not cell:
                cleaned_row.append("")
                continue
            c = DOLLAR_SPACE_REGEX.sub(r"\1", cell)
            c = OPEN_PAREN_SPACE_REGEX.sub("(", c)
            c = CLOSE_PAREN_SPACE_REGEX.sub(")", c)
            c = PERCENT_SPACE_REGEX.sub("%", c)
            c = COMMA_SPACE_REGEX.sub(",", c)
            cleaned_row.append(c)

        # Pass 2: Merge adjacent cells based on content constraints
        # We iterate and build a new row, merging where appropriate.
        final_row = []
        skip_idx = -1

        for i, cell in enumerate(cleaned_row):
            if i <= skip_idx:
                continue

            current_val = cell

            # Look ahead for potential merge
            if i + 1 < len(cleaned_row):
                next_val = cleaned_row[i + 1]

                # CASE A: Trailing Suffix (Merge LEFT into current)
                # Check if next_val is a suffix like ')' or '%' or '$' (Wait! $ is prefix)
                # FIXED: Removed '$' from left-merge candidates.
                if next_val in [")", "%"] and current_val:
                    # Constraint: Only merge ')' if current looks like a number or number-start
                    if self._is_numeric_start(current_val):
                        current_val = current_val + next_val
                        skip_idx = i + 1  # Consume next

                # CASE B: Leading Prefix (Merge RIGHT into next)
                # Check if current_val is a prefix like '$' or '('
                elif current_val in ["$", "€", "£", "¥", "("] and next_val:
                    # Constraint: Only merge if next_val looks like a number
                    if self._is_numeric_start(next_val):
                        # Merge current into next, effectively appending to final_row in next iteration?
                        # No, we combine now and append.

                        # Check if we have a chain (e.g. $ + ( + 100)
                        # This simple logic handles $ + 100.
                        # For $ + ( + 100, we need a second pass or recursion.
                        # Simpler: Just merge pairs. $ + ( becomes $(. Next pass $( + 100 becomes $(100.

                        current_val = current_val + next_val
                        skip_idx = i + 1  # Consume next

            # Handle existing 'final_row' for left-merges that might span
            # Actually, standardizing on a single pass is safer for indices.

            # Because we might have modified current_val by consuming next,
            # we need to check if we can merge *again* (e.g. $ + 100 + %).
            # But simpler to let the loop handle simple adjacent pairs.
            # Chains ($ -> ( -> 100) might require multi-pass.

            final_row.append(current_val)

        # Quick second pass to catch chains like "$ + ( + 100" which became "$( + 100"
        # or "100 + % + )" which became "100% + )"
        final_pass_row = []
        skip_idx_2 = -1

        for i, cell in enumerate(final_row):
            if i <= skip_idx_2:
                continue

            current_val = cell
            if i + 1 < len(final_row):
                next_val = final_row[i + 1]

                # Check Prefix again (e.g. $( + 100)
                if self._is_prefix_symbol(current_val) and self._is_numeric_start(
                    next_val
                ):
                    current_val = current_val + next_val
                    skip_idx_2 = i + 1
                # Check Suffix again (e.g. 100% + ))
                elif self._is_suffix_symbol(next_val) and self._is_numeric_start(
                    current_val
                ):
                    current_val = current_val + next_val
                    skip_idx_2 = i + 1

            final_pass_row.append(current_val)

        return final_pass_row

    def _is_prefix_symbol(self, val: str) -> bool:
        # Returns true for $, (, $(, etc.
        if not val:
            return False
        return all(c in "$€£¥(" for c in val)

    def _is_suffix_symbol(self, val: str) -> bool:
        # Returns true for %, ), %), etc.
        if not val:
            return False
        return all(c in "%)" for c in val)

    def _is_numeric_start(self, val: str) -> bool:
        # Helper to check if a value looks like the start of a number
        # e.g. "100", "(100", "4,000"
        if not val:
            return False
        clean = val.replace(",", "").replace("$", "").replace("(", "")
        if not clean:
            return False  # Was just symbol
        return clean[0].isdigit() or clean.startswith("-") or clean.startswith(".")

    def _extract_data_driven(
        self, table_text: str
    ) -> Tuple[List[List[str]], Dict[int, Optional[str]], Dict[int, str]]:
        table_text = TABLE_TAG_REGEX.sub("", table_text)
        lines = table_text.split("\n")

        # --- 1. DETECT TABLE STRUCTURE (<S> and <C>) ---
        marker_line = None
        marker_line_idx = 0
        for i, line in enumerate(lines):
            if S_MARKER_REGEX.search(line):
                marker_line = line
                marker_line_idx = i
                break

        if not marker_line:
            return [], {}, {}

        # Parse <C> tags into column boundaries
        c_positions = [m.start() for m in C_MARKER_REGEX.finditer(marker_line)]
        if not c_positions:
            return [], {}, {}

        grouped_positions = []
        current_group = [c_positions[0]]
        for pos in c_positions[1:]:
            if pos - current_group[-1] <= 5:
                current_group.append(pos)
            else:
                grouped_positions.append(current_group)
                current_group = [pos]
        grouped_positions.append(current_group)

        column_boundaries = []
        single_width_col_indices = set()
        first_c_pos = grouped_positions[0][0]
        column_boundaries.append((0, first_c_pos))

        for i, group in enumerate(grouped_positions):
            start = group[0]
            end = (
                grouped_positions[i + 1][0]
                if i + 1 < len(grouped_positions)
                else len(marker_line)
            )
            width = end - start
            col_idx = len(column_boundaries)
            if width < 2:
                single_width_col_indices.add(col_idx)
            column_boundaries.append((start, end))

        # --- 2. RAW EXTRACTION (Headers & Data) ---

        # A. Extract Raw Data Rows
        data_lines = lines[marker_line_idx + 1 :]
        raw_rows = []
        for line in data_lines:
            if not line.strip():
                continue
            row_cells = []
            for start, end in column_boundaries:
                if start < len(line):
                    cell = line[start : min(end, len(line))].strip()
                else:
                    cell = ""
                cell = HTML_TAG_REGEX.sub("", cell)
                row_cells.append(cell)
            if any(row_cells):
                raw_rows.append(row_cells)

        # B. Extract Raw Header Rows (Using the same boundaries)
        # We grab lines BEFORE the marker, but apply the EXACT same column slices
        header_lines = lines[:marker_line_idx]
        raw_header_rows = []
        for line in header_lines:
            clean_line = line.strip()
            # Skip noise lines
            if not clean_line or "<CAPTION>" in clean_line or "<TABLE>" in clean_line:
                continue
            # Skip separator lines (dashes/equals only)
            if all(c in "-= " for c in clean_line) and any(
                c in "-=" for c in clean_line
            ):
                continue

            h_cells = []
            for start, end in column_boundaries:
                if start < len(line):
                    h_cells.append(line[start : min(end, len(line))].strip())
                else:
                    h_cells.append("")

            if any(h_cells):
                raw_header_rows.append(h_cells)

        # --- 3. MERGE LOGIC (Strictly Data-Driven) ---

        # We pass ONLY raw_rows to the merge logic.
        # The empty/messy headers do not influence the decision.
        merged_rows, col_mapping = self._merge_sparse_columns(
            raw_rows, single_width_col_indices
        )

        # --- 4. APPLY MERGE TO HEADERS ---

        # Now we force the headers to follow the data's lead.
        merged_headers_map = {}
        for h_row in raw_header_rows:
            for old_idx, text in enumerate(h_row):
                if not text:
                    continue

                # Move header text to where the data went
                new_idx = col_mapping.get(old_idx, old_idx)
                if new_idx not in merged_headers_map:
                    merged_headers_map[new_idx] = []
                merged_headers_map[new_idx].append(text)

        # Flatten multi-line headers into single strings
        final_physical_headers = {}
        for idx, parts in merged_headers_map.items():
            final_physical_headers[idx] = " ".join(parts).strip()

        # --- 5. CLEANING & FILTERING ---

        # Clean symbols in data (post-merge)
        cleaned_rows = []
        for row in merged_rows:
            cleaned_row = self._clean_and_merge_symbols(row)
            cleaned_rows.append(cleaned_row)

        cleaned_rows = self._heal_data_rows(cleaned_rows)
        cleaned_rows = self._repair_split_numbers(cleaned_rows)
        cleaned_rows = self._repair_shifted_currency(cleaned_rows)

        # Identify active columns (columns that actually have data)
        active_col_indices = set()
        for row in cleaned_rows:
            for col_idx, cell in enumerate(row):
                if cell and len(cell) > 1:
                    active_col_indices.add(col_idx)
        active_col_indices = sorted(active_col_indices)

        # Create final filtered data rows
        filtered_rows = []
        for row in cleaned_rows:
            # Only keep active columns
            filtered_row = [row[i] if i < len(row) else "" for i in active_col_indices]
            if any(filtered_row):
                filtered_rows.append(filtered_row)

        # --- HEURISTIC: CARRY FORWARD YEARS IN HEADERS ---
        last_seen_year = None
        for global_col_idx in active_col_indices:
            header_text = final_physical_headers.get(global_col_idx, "")

            # Extract years (handle regex results or helper results)
            years_str = YEAR_REGEX.findall(header_text)
            years_int = convert_slash_year_to_four_digit(header_text)

            current_years = []
            if years_str:
                current_years.extend(int(y) for y in years_str)
            if years_int:
                current_years.extend(years_int)

            if current_years:
                last_seen_year = str(max(current_years))
            elif last_seen_year:
                if header_text:
                    final_physical_headers[global_col_idx] = (
                        f"{header_text} {last_seen_year}"
                    )
                else:
                    final_physical_headers[global_col_idx] = last_seen_year

        col_headers = {}
        col_map = {}

        for local_idx, global_col_idx in enumerate(active_col_indices):
            # 1. Get Header (Physical or Inferred)
            header_text = final_physical_headers.get(global_col_idx, "")

            # Fallback: If physical header is missing, try data inference
            if not header_text:
                sample_cells = [
                    row[local_idx] for row in filtered_rows if local_idx < len(row)
                ]
                years_found = set()
                for cell in sample_cells:
                    year_matches = YEAR_REGEX.findall(
                        cell
                    ) or convert_slash_year_to_four_digit(cell)
                    if year_matches:
                        # Normalize to string for set
                        for y in year_matches:
                            years_found.add(str(y))
                if years_found:
                    header_text = f"value_{max(years_found)}"

            col_headers[local_idx] = header_text

            # 2. Infer Type (UPDATED LOGIC)
            sample_cells = [
                row[local_idx] for row in filtered_rows if local_idx < len(row)
            ]

            # Metrics
            has_dates = (
                sum(
                    1
                    for c in sample_cells
                    if YEAR_REGEX.search(c) or convert_slash_year_to_four_digit(c)
                )
                > 0
            )
            has_percentages = sum(1 for c in sample_cells if "%" in c) > 0
            numeric_count = sum(1 for c in sample_cells if self._is_numeric(c))
            total_count = len([c for c in sample_cells if c])
            is_numeric_col = total_count > 0 and (numeric_count / total_count > 0.3)

            col_type = None
            if local_idx == 0:
                col_type = "context_text"
            elif has_dates:
                col_type = "metadata_maturity"
            elif is_numeric_col:
                col_type = self.table_default_type or "value"
            elif has_percentages:
                col_type = "rate"

            col_map[local_idx] = col_type

        return filtered_rows, col_map, col_headers
    def _repair_shifted_currency(self, rows):
        """
        Detects when a currency symbol for the NEXT column has been 
        wrongly concatenated to the end of the CURRENT column.
        
        Example: 
        ['$168 $', '17 $', '$'] -> ['$168', '$17', '$$']
        """
        cleaned_rows = []

        # Regex to find a value ending with a space and a dollar sign
        # Capture group 1: The real value
        # Capture group 2: The wrongly attached currency symbol
        pattern = re.compile(r"^(.*?)\s+(\$)$")

        for row in rows:
            # iterate backwards to safely push items forward?
            # Actually forward iteration is fine if we modify in place or use a carry.

            for i in range(len(row) - 1): # Stop at second to last col
                current_cell = row[i].strip()

                match = pattern.search(current_cell)
                if match:
                    real_value = match.group(1) # "$168"
                    symbol = match.group(2)     # "$"

                    # 1. Fix current cell
                    row[i] = real_value

                    # 2. Push symbol to next cell
                    # We check if next cell is empty or has content
                    next_cell = row[i+1].strip()
                    row[i+1] = f"{symbol}{next_cell}"

            # OPTIONAL: Clean up artifacts in the final pass
            # If we pushed a '$' onto a cell that was already '$', we might get '$$'
            # This handles the empty columns that are just placeholders.
            row = [x.replace('$$', '$').strip() for x in row]

            cleaned_rows.append(row)

        return cleaned_rows

    def _heal_data_rows(self, rows: List[List[str]]) -> List[List[str]]:
        """
        Fixes rows where the description text has shifted into the data columns
        due to indentation, or where text and data are split across lines.
        """
        healed_rows = []
        prev_text_row = None  # Buffer for vertical merging

        for i, row in enumerate(rows):
            if not row or not any(row):
                continue

            # --- 1. HORIZONTAL SHIFT (The "Shift It" Logic) ---
            # Scenario: ['', 'Accounts Payable', '100', '200']
            # Goal:     ['Accounts Payable', '', '100', '200']

            # If Col 0 is empty...
            if not row[0].strip() and len(row) > 1:
                # Find the first non-empty column index
                first_content_idx = -1
                for idx, cell in enumerate(row):
                    if cell.strip():
                        first_content_idx = idx
                        break

                # If we found content, and it is NOT a number (it's text), move it to Col 0
                if first_content_idx > 0:
                    val = row[first_content_idx]
                    # Check if it looks like a number/year (don't move data!)
                    # We treat specific keywords (Level 1, etc) as text, but dates/numbers as data
                    if not self._is_numeric(val) and not YEAR_REGEX.match(val):
                        row[0] = val
                        row[first_content_idx] = ""  # Clear the old spot

            # --- 2. VERTICAL MERGE (Hanging Indents) ---
            # Scenario:
            # Row A: ['Net Income', '', '']  <-- Text, No Data
            # Row B: ['', '100', '200']      <-- No Text, Data
            # Goal:  ['Net Income', '100', '200']

            has_text = bool(row[0].strip())

            # Check if the rest of the row has numeric data
            has_data = False
            for cell in row[1:]:
                if self._is_numeric(cell):
                    has_data = True
                    break

            if has_text and not has_data:
                # This might be a "Hanging Header". Buffer it.
                # If we already have a buffered header, flush it (it was a section header)
                if prev_text_row:
                    healed_rows.append(prev_text_row)
                prev_text_row = row
                continue

            elif not has_text and has_data:
                # This is a "Hanging Data" row.
                if prev_text_row:
                    # MERGE BACK!
                    row[0] = prev_text_row[0]
                    # If the previous row had other random text in other cols, arguably we could merge that too,
                    # but usually, we just want the description.
                    prev_text_row = None
                    healed_rows.append(row)
                else:
                    # No previous text to attach to. Just keep the row (orphaned data).
                    healed_rows.append(row)
                continue

            # Standard Case (Text AND Data, or neither)
            else:
                if prev_text_row:
                    healed_rows.append(prev_text_row)
                    prev_text_row = None
                healed_rows.append(row)

        # Flush any remaining buffer
        if prev_text_row:
            healed_rows.append(prev_text_row)

        return healed_rows

    def _repair_split_numbers(self, rows: List[List[str]]) -> List[List[str]]:
        """
        Stitches numbers that have been split across columns due to commas or formatting.
        Example: ['33', ',252'] -> ['', '33,252']
        """
        repaired_rows = []
        for row in rows:
            new_row = [x for x in row]  # Copy
            # Iterate backwards so we can merge left-to-right safely or right-to-left
            # Actually, standard split is [Num] [CommaNum]. We want to merge Right into Left.

            i = 0
            while i < len(new_row) - 1:
                curr = new_row[i].strip()
                next_val = new_row[i + 1].strip()

                # Check for the split pattern: "33" + ",252"
                # Current must end in digit, Next must start with comma + digit
                if (
                    curr
                    and next_val
                    and curr[-1].isdigit()
                    and next_val.startswith(",")
                    and len(next_val) > 1
                    and next_val[1].isdigit()
                ):

                    # Merge
                    new_row[i] = curr + next_val
                    new_row[i + 1] = ""  # Clear the fragment
                    i += 1  # Skip next

                # Check for the reverse split (sometimes happens): "33," + "252"
                elif curr and next_val and curr.endswith(",") and next_val[0].isdigit():

                    new_row[i] = curr + next_val
                    new_row[i + 1] = ""
                    i += 1
                i += 1

            repaired_rows.append(new_row)
        return repaired_rows

    def _detect_paragraph_masquerading_as_table(self) -> bool:
        if not self.data:
            return False
        raw_text = "\n".join([" ".join(row) for row in self.data])
        if TABLE_OF_CONTENTS_REGEX.search(raw_text):
            return True
        first_col_max_length = 0
        for row in self.data:
            if row and len(row) > 0:
                first_col_max_length = max(first_col_max_length, len(row[0]))
        if first_col_max_length > PARAGRAPH_THRESHOLD:
            return True
        return False

    def _classify_columns_from_headers(self):
        for local_idx, header in self.col_headers.items():
            if not header:
                continue
            h_mult = self._scan_for_multiplier(header)
            if h_mult:
                self.col_multipliers[local_idx] = h_mult

            years = YEAR_REGEX.findall(header) or convert_slash_year_to_four_digit(
                header
            )
            year_suffix = ""
            if years:
                y_val = max(str(y) for y in years)
                year_suffix = f"_{y_val}"

            header_lower = header.lower()
            current_type = self.col_map.get(local_idx)
            if current_type in ["context_text", "metadata_maturity"]:
                continue

            new_base_type = None
            if NOISE_HEADERS.search(header_lower):
                self.col_map[local_idx] = None
                continue
            elif CONTEXT_HEADERS.search(header_lower):
                new_base_type = "context_text"
                year_suffix = ""
            elif NOTIONAL_HEADERS.search(header_lower):
                new_base_type = "notional"
            elif VAR_HEADERS.search(header_lower):
                new_base_type = "fair_value"
            elif NET_HEADERS.search(header_lower):
                new_base_type = "net_fair_value"
            elif GROSS_HEADERS.search(header_lower):
                new_base_type = "gross_fair_value"
            elif LEVEL_HEADERS.search(header_lower):
                new_base_type = "fair_value"
            elif VALUE_HEADERS.search(header_lower):
                if ASSET_HEADERS.search(header_lower):
                    new_base_type = "asset_fair_value"
                elif LIABILITY_HEADERS.search(header_lower):
                    new_base_type = "liability_fair_value"
                else:
                    new_base_type = "fair_value"
            elif GAIN_LOSS_HEADERS.search(header_lower):
                new_base_type = "gain_loss"
            elif LOCATION_HEADERS.search(header_lower):
                new_base_type = "location"
                year_suffix = ""
            elif MATURITY_HEADERS.search(header_lower):
                new_base_type = "metadata_maturity"
                year_suffix = ""
            elif PERCENT_HEADERS.search(header_lower):
                self.col_map[local_idx] = "rate"

            if new_base_type:
                self.col_map[local_idx] = f"{new_base_type}{year_suffix}"
            elif year_suffix:
                if current_type and "value" in current_type:
                    base = current_type
                else:
                    base = "value"
                self.col_map[local_idx] = f"{base}{year_suffix}"

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
        has_net = any(
            col_type == "net_fair_value" for col_type in self.col_map.values()
        )
        if has_net:
            for idx, col_type in self.col_map.items():
                if col_type == "gross_fair_value":
                    self.col_map[idx] = None

    def _is_numeric(self, val: str) -> bool:
        clean = NUMERIC_WITH_SYMBOLS.sub("", val).strip()
        clean = self._strip_multipliers(clean)
        return bool(NUMERIC_PATTERN.match(clean))

    def _is_numeric_large(self, val: str) -> bool:
        if not self._is_numeric(val):
            return False
        try:
            clean = NUMERIC_WITH_SYMBOLS.sub("", val).strip()
            clean = self._strip_multipliers(clean)
            return float(clean) > 1000
        except:
            return False

    def _has_any_value(self, val: str) -> bool:
        return bool(len(val.strip()) > 1)

    def _strip_multipliers(self, val: str) -> str:
        val = val.lower()
        val = UNIT_REGEX.sub("", val)
        return val

    def _is_valid_value(self, val: str) -> bool:
        clean = NUMERIC_WITH_SYMBOLS.sub("", val).strip()
        clean = self._strip_multipliers(clean)
        if clean in ["-", "—", "0", "0.0", "", "0.00", "--"]:
            return False
        return bool(NUMERIC_PATTERN.match(clean))

    def _scan_for_multiplier(self, text: str) -> Optional[float]:
        if not text:
            return None
        if BILLION_REGEX.search(text):
            return 1_000_000_000.0
        if MILLION_REGEX.search(text):
            return 1_000_000.0
        if THOUSAND_REGEX.search(text):
            return 1_000.0
        return None

    def normalize_value(self, clean_val: str, multiplier: float = 1.0):
        clean_val = clean_val.strip()
        had_dollar = "$" in clean_val
        had_percent = "%" in clean_val
        if "(" in clean_val and ")" in clean_val:
            clean_val = clean_val.replace("(", "-").replace(")", "")

        text_multiplier = 1.0
        lower_val = clean_val.lower()
        if "trillion" in lower_val:
            text_multiplier = 1e12
        elif "billion" in lower_val:
            text_multiplier = 1e9
        elif "million" in lower_val:
            text_multiplier = 1e6
        elif "thousand" in lower_val:
            text_multiplier = 1e3

        clean_val = UNIT_REGEX.sub("", clean_val)
        stripped = NUMERIC_WITH_SYMBOLS.sub("", clean_val).strip()

        try:
            norm_num = float(stripped)
            final_multiplier = 1.0
            if not had_percent:
                if text_multiplier > 1.0:
                    final_multiplier = text_multiplier
                else:
                    final_multiplier = multiplier

            potential_val = norm_num * final_multiplier
            if abs(potential_val) < 1e14:
                norm_num = potential_val

            num = abs(norm_num)
            if num == 0:
                if had_dollar:
                    return "$0"
                if had_percent:
                    return "0%"
                return "0"

            if num >= 100:
                num_str = "{:,.0f}".format(num)
            else:
                num_str = "{:,.2f}".format(num)

            prefix = "$" if had_dollar else ""
            suffix = "%" if had_percent else ""

            if norm_num < 0:
                if had_dollar:
                    return f"{prefix}({num_str}){suffix}"
                else:
                    return f"-{prefix}{num_str}{suffix}"
            else:
                return f"{prefix}{num_str}{suffix}"
        except ValueError:
            return clean_val

    def _is_subheader_row(self, row: List[str]) -> bool:
        if not row or not row[0].strip():
            return False
        for cell in row[1:]:
            if cell and self._is_valid_value(cell):
                return False
        return True

    def _construct_instrument_name(self, row_text: str, context_text: str) -> str:
        name = row_text.strip().rstrip(":")
        ctx = context_text.strip().rstrip(":")
        if not ctx:
            return name
        is_designation = bool(DESIGNATION_REGEX.search(ctx))
        if is_designation:
            if ctx.lower() in name.lower():
                return name
            return f"{name} {ctx}"
        if ctx.lower() in name.lower():
            return name
        ctx_base_match = BASE_REGEX.search(ctx)
        row_base_match = BASE_REGEX.search(name)
        prefix = ctx
        if ctx_base_match and row_base_match:
            ctx_base = ctx_base_match.group(0)
            prefix = re.sub(re.escape(ctx_base), "", ctx, flags=re.IGNORECASE).strip()
        return f"{prefix} {name}".strip()

    def process(self) -> Tuple[List[str], bool]:
        if self.invalid_table or not self.data:
            return ([], False)
        sentences = []
        active_context = ""
        section_year_str = ""

        table_has_strong_notional_col = any(
            col_type and STRONG_NOTIONAL_REGEX.search(col_type)
            for col_type in self.col_map.values()
        )
        if self.table_default_type == "notional":
            table_has_strong_notional_col = True

        caption_year_str = ""
        if self.caption:
            caption_years = YEAR_REGEX.findall(
                self.caption
            ) or convert_slash_year_to_four_digit(self.caption)
            if caption_years:
                try:
                    caption_year_str = f"in {max(int(y) for y in caption_years)} "
                except:
                    caption_year_str = f"in {caption_years[-1]} "

        debug_print(f"Found {len(self.data)} rows")
        debug_print(f"Header: {self.col_headers}")

        for row_idx, row in enumerate(self.data):
            if not row or not row[0].strip():
                continue

            row_text = row[0].strip()
            row_specific_multiplier = self._scan_for_multiplier(row_text)
            row_years = YEAR_REGEX.findall(
                row_text
            ) or convert_slash_year_to_four_digit(row_text)
            if row_years:
                y_val = max(int(y) for y in row_years)
                section_year_str = f"in {y_val} "

            if self._is_subheader_row(row):
                debug_print(f"Found subheader row: {row}")
                raw_header = row_text.rstrip(":")
                if row_years:
                    raw_header = YEAR_REGEX.sub("", raw_header).strip(" (),")

                if raw_header:
                    is_designation = bool(DESIGNATION_REGEX.search(raw_header))
                    if "cash flow" in raw_header.lower() and len(raw_header) > 20:
                        is_designation = False
                    if len(raw_header) > 50:
                        is_designation = False
                    if is_designation and active_context:
                        active_context = f"{active_context} {raw_header}"
                    else:
                        active_context = raw_header
                continue

            instrument_name = row[0].strip()
            if "total" == instrument_name.lower():
                continue
            if active_context:
                instrument_name = self._construct_instrument_name(
                    instrument_name, active_context
                )

            is_strict = self.is_implied_derivative(instrument_name)
            is_table_safe = bool(TABLE_REGEX.search(instrument_name))
            is_soft = (
                bool(SOFT_REGEX.search(instrument_name)) if not is_strict else False
            )
            has_base = bool(BASE_REGEX.search(instrument_name))
            has_strong_notional = bool(STRONG_NOTIONAL_REGEX.search(instrument_name))
            has_currency_notional = bool(CURRENCY_NAMES_REGEX.search(instrument_name))
            is_ir = bool(IR_SOFT_REGEX.search(instrument_name))
            is_fx = bool(FX_SOFT_REGEX.search(instrument_name)) or has_currency_notional
            is_not_cp = is_ir or is_fx
            table_has_strong_row = (
                is_strict
                or is_table_safe
                or has_strong_notional
                or has_currency_notional
            )

            should_keep = False
            soph = False
            if (
                is_strict
                or is_table_safe
                or has_strong_notional
                or has_currency_notional
            ):
                should_keep = True
            elif is_soft:
                if is_not_cp:
                    if (
                        table_has_strong_row
                        or table_has_strong_notional_col
                        or self.caption_is_strong
                    ):
                        should_keep = True
                elif (
                    table_has_strong_row
                    or table_has_strong_notional_col
                    or self.caption_is_strong
                ):
                    if has_base:
                        should_keep = True
            if SOPHISTICATED_TARGETS.search(instrument_name):
                soph = True
                if not should_keep and (self.is_sophisticated or soph):
                    should_keep = True

            if not should_keep:
                continue

            expiration_str = ""
            for col_idx, col_type in self.col_map.items():
                if col_idx < len(row) and col_type == "metadata_maturity":
                    cell = row[col_idx]
                    yrs = YEAR_REGEX.findall(cell) or convert_slash_year_to_four_digit(
                        cell
                    )
                    if yrs:
                        expiration_str = f" (expiring in {max(yrs)})"

            for col_idx, col_type in self.col_map.items():
                if (
                    col_idx >= len(row)
                    or not col_type
                    or col_type in ["context_text", "metadata_maturity"]
                ):
                    continue
                cell = row[col_idx]
                if not cell or not self._is_valid_value(cell):
                    continue

                clean_val = cell.replace(",", "").strip()

                parts = col_type.split("_")
                year_str = ""
                if parts[-1].isdigit() and len(parts[-1]) == 4:
                    year_str = f"in {parts.pop()} "
                if not year_str and section_year_str:
                    year_str = section_year_str
                if not year_str and caption_year_str:
                    year_str = caption_year_str

                base_type = "_".join(parts)
                actual_col_type = base_type
                display_instrument = f"{instrument_name}{expiration_str}"

                if GAIN_LOSS_HEADERS.search(display_instrument):
                    actual_col_type = "gain_loss"
                elif VALUE_HEADERS.search(display_instrument):
                    actual_col_type = "fair_value"
                elif STRONG_NOTIONAL_REGEX.search(display_instrument):
                    actual_col_type = "notional"

                final_multiplier = row_specific_multiplier
                if not final_multiplier:
                    final_multiplier = self.col_multipliers.get(col_idx)
                if not final_multiplier:
                    final_multiplier = self.global_multiplier

                value = self.normalize_value(clean_val, multiplier=final_multiplier)
                if "%" in value:
                    actual_col_type = "rate"

                use_anchor = (
                    table_has_strong_row
                    or table_has_strong_notional_col
                    or self.caption_is_strong
                )
                anchor_text = TABLE_ANCHOR if use_anchor else ""

                if "notional" in actual_col_type:
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with a notional amount of {value}."
                elif "gain_loss" in actual_col_type:
                    sentence = f"{anchor_text} {year_str}The Company recorded {display_instrument} of {value}."
                elif "fair_value" in actual_col_type:
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with a fair value of {value}."
                elif actual_col_type == "value":
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with a value of {value}."
                elif actual_col_type == "rate":
                    continue
                else:
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with an amount of {value}."
                sentences.append(sentence)

        return (sentences, False)


if __name__ == "__main__":
    DEBUG = True
