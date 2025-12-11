import re
from typing import List, Dict, Optional, Set, Tuple

from derivative_regex import (
    BASE_REGEX,
    FX_SOFT_REGEX,
    IR_SOFT_REGEX,
    SOFT_REGEX,
    TABLE_REGEX,
    YEAR_REGEX,
    STRICT_REGEX,
    SOFT_GEN_REGEX,
    CURRENCY_NAMES_REGEX,
)

# --- EXPANDED HEADER DEFINITIONS ---

# Context/Purpose Headers
CONTEXT_HEADERS = re.compile(
    r"purpose|risk|objective|hedged item|comments|description", re.IGNORECASE
)

# Value at Risk (Strong Signal)
VAR_HEADERS = re.compile(r"\bvar\b|value[- ]at[- ]risk", re.IGNORECASE)

# Strong Notional Indicator
STRONG_NOTIONAL_REGEX = re.compile(r"notional", re.IGNORECASE)

# Expanded Notional
NOTIONAL_HEADERS = re.compile(
    r"notional|principal|contract\s+(?:amount|volume|value)", re.IGNORECASE
)

# Netting / Offsetting (ASC 210-20)
NET_HEADERS = re.compile(r"net\s+amount|net\s+presented|total\s+net", re.IGNORECASE)
GROSS_HEADERS = re.compile(r"gross\s+amount|gross\s+recognized", re.IGNORECASE)

# Standard Values
LEVEL_HEADERS = re.compile(r"level\s*[123]", re.IGNORECASE)
VALUE_HEADERS = re.compile(r"(?:fair|market|carrying)\s+value|balance", re.IGNORECASE)
ASSET_HEADERS = re.compile(r"asset", re.IGNORECASE)
LIABILITY_HEADERS = re.compile(r"liabilit", re.IGNORECASE)
GAIN_LOSS_HEADERS = re.compile(
    r"gain|loss|income|earnings|oci|comprehensive", re.IGNORECASE
)

# Location (line item reference)
LOCATION_HEADERS = re.compile(r"location|sheet|line item", re.IGNORECASE)

# Maturity
MATURITY_HEADERS = re.compile(r"maturity|expiration", re.IGNORECASE)

# Noise to Ignore (metadata columns that shouldn't generate sentences)
NOISE_HEADERS = re.compile(
    r"strike|exercise|shares|units|count|ratio|weighted",
    re.IGNORECASE,
)

# Context Row Keywords
SECTION_KEYWORDS = re.compile(
    r"designated as|hedging instruments|underlying risk|derivatives not designated|"
    r"cash flow|fair value|net investment|assets|liabilities|equity contracts|warrants|"
    r"embedded|offsetting|trading|non[- ]?trading|held for|financial instruments|"
    r"(?:interest\s+rate|equity|foreign\s+exchange|commodity|credit|"
    r"FX|IR|commodity|currency)\s+(?:contracts?|derivatives?|instruments?)",
    re.IGNORECASE,
)

SOPHISTICATED_TARGETS = re.compile(
    r"\b(?:convertibles?|warrants?|conversion)\b", re.IGNORECASE
)

TABLE_ANCHOR = " T_"

caption_regex = re.compile(
    r"<caption>\s*(.*?)(?=\n\n|:\n|\n[-=])", re.DOTALL | re.IGNORECASE
)


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

        self.caption = self._extract_caption(table_text)
        full_context = f"{self.caption} {self.narrative_context}"
        self.caption_is_strong = self.is_implied_derivative(full_context)
        self.table_default_type = self._analyze_caption_context(full_context)

        # Data-driven extraction with sparsity detection
        self.data, self.col_map, self.col_headers = self._extract_data_driven(
            caption_regex.sub("", table_text)
        )
        self.invalid_table = len(self.data) == 0

        # Apply classification and refinement heuristics
        if not self.invalid_table:
            self._classify_columns_from_headers()
            self._apply_column_heuristics()
            self._resolve_offsetting_conflicts()

    def _extract_caption(self, text: str) -> str:
        match = caption_regex.search(text)
        if match:
            caption_text = match.group(1).strip()
            caption_text = re.sub(r"\s+", " ", caption_text)
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

    def _detect_merge_patterns(self, raw_rows: List[List[str]], sparse_columns: set) -> Dict[int, str]:
        """
        Pre-analysis pass: detect semantic patterns for how sparse columns should merge.
        Returns mapping of column_idx -> merge_strategy.
        
        Strategies:
        - "merge_right": currency symbols, opening parens (merge with following column)
        - "merge_left": closing parens, percents (merge with preceding column)
        - "skip": ambiguous or mixed content (don't merge)
        """
        merge_directions = {}

        for col_idx in sparse_columns:
            # Collect all non-empty values in this column
            col_values = []
            col_patterns = set()

            for row in raw_rows:
                if col_idx < len(row) and row[col_idx].strip():
                    val = row[col_idx].strip()
                    col_values.append(val)
                    # Classify pattern
                    if val in ["$", "€", "£", "¥"]:
                        col_patterns.add("currency")
                    elif val == ")":
                        col_patterns.add("closing_paren")
                    elif val == "%":
                        col_patterns.add("percent")
                    elif val == "(":
                        col_patterns.add("opening_paren")
                    else:
                        col_patterns.add("other")

            if not col_values:
                continue

            # Determine merge strategy
            # Pure currency: merge RIGHT
            if col_patterns == {"currency"}:
                merge_directions[col_idx] = "merge_right"
            # Pure closing paren: merge LEFT
            elif col_patterns == {"closing_paren"}:
                merge_directions[col_idx] = "merge_left"
            # Pure percent: merge LEFT
            elif col_patterns == {"percent"}:
                merge_directions[col_idx] = "merge_left"
            # Pure opening paren: merge RIGHT
            elif col_patterns == {"opening_paren"}:
                merge_directions[col_idx] = "merge_right"
            # Mixed currency symbols: merge RIGHT
            elif col_patterns.issubset({"currency"}):
                merge_directions[col_idx] = "merge_right"
            # Ambiguous or mixed: skip to be safe
            else:
                merge_directions[col_idx] = "skip"

        return merge_directions

    def _merge_sparse_columns(self, raw_rows: List[List[str]], single_width_cols: Optional[Set] = None) -> Tuple[List[List[str]], Dict[int, int]]:
        """
        Merge very sparse columns (mostly empty) with adjacent columns.
        Combines two heuristics:
        1. Single-width <C> tag heuristic: columns with width <= 2 chars are almost certainly separators
        2. Data sparsity: columns with > 80% empty cells
        
        Semantic rules (via pre-analysis):
        - $ (currency) merges RIGHT with numbers
        - ) (closing paren) merges LEFT with numbers
        - % (percent) merges LEFT with numbers
        - ( (opening paren) merges RIGHT with numbers
        
        Returns:
        - merged_rows: data rows after merging
        - col_mapping: dict mapping old column indices to new indices (for header alignment)
        """
        if not raw_rows:
            return [], {}

        if single_width_cols is None:
            single_width_cols = set()

        # Calculate sparsity (% empty cells) for each column
        num_rows = len(raw_rows)
        num_cols = max(len(row) for row in raw_rows) if raw_rows else 0

        col_sparsity = {}
        for col_idx in range(num_cols):
            empty_count = sum(
                1 for row in raw_rows if col_idx >= len(row) or not row[col_idx]
            )
            sparsity = empty_count / num_rows if num_rows > 0 else 0
            col_sparsity[col_idx] = sparsity

        # Combine both heuristics: single-width columns OR > 80% empty cells
        sparse_columns = {idx for idx, sparsity in col_sparsity.items() if sparsity > 0.8}
        sparse_columns.update(single_width_cols)

        if not sparse_columns:
            # No merging needed: identity mapping
            col_mapping = {i: i for i in range(num_cols)}
            return raw_rows, col_mapping

        # PASS 1: Detect merge patterns (pre-aware system)
        merge_directions = self._detect_merge_patterns(raw_rows, sparse_columns)

        # PASS 2: Apply merges based on detected strategies and track column mapping
        merged_rows = []
        col_mapping = {}  # old_col_idx -> new_col_idx

        for row in raw_rows:
            merged_row = []
            skip_indices = set()
            row_col_mapping = {}  # Track mapping for this row

            for col_idx in range(len(row)):
                if col_idx in skip_indices:
                    continue

                cell = row[col_idx]
                strategy = merge_directions.get(col_idx, "keep")
                new_col_idx = len(merged_row)

                # Merge RIGHT: currency, opening paren
                if strategy == "merge_right":
                    if col_idx + 1 < len(row):
                        next_cell = row[col_idx + 1]
                        merged_row.append((cell + next_cell).strip())
                        skip_indices.add(col_idx + 1)
                        # Both old columns map to new column
                        row_col_mapping[col_idx] = new_col_idx
                        row_col_mapping[col_idx + 1] = new_col_idx
                    else:
                        merged_row.append(cell)
                        row_col_mapping[col_idx] = new_col_idx

                # Merge LEFT: closing paren, percent
                elif strategy == "merge_left":
                    if merged_row:  # Append to previous cell
                        merged_row[-1] = (merged_row[-1] + cell).strip()
                        # This column maps to the previous column
                        row_col_mapping[col_idx] = len(merged_row) - 1
                    else:
                        merged_row.append(cell)
                        row_col_mapping[col_idx] = new_col_idx

                # Skip (ambiguous): don't merge
                elif strategy == "skip":
                    merged_row.append(cell)
                    row_col_mapping[col_idx] = new_col_idx

                # Normal column or unclassified sparse column: keep as-is
                else:
                    merged_row.append(cell)
                    row_col_mapping[col_idx] = new_col_idx

            # Aggregate column mappings (use first row as reference)
            if not col_mapping:
                col_mapping = row_col_mapping

            if merged_row:
                merged_rows.append(merged_row)

        return merged_rows, col_mapping

    def _sync_headers_after_merge(self, col_mapping: Dict[int, int]) -> Dict[int, str]:
        """
        Align headers with merged columns using the column mapping.
        
        If column 2 merged with column 3, the new column 2 should have a combined header.
        """
        if not col_mapping or not self.col_headers:
            return self.col_headers

        synced_headers = {}
        processed_old_cols = set()

        for old_col_idx, new_col_idx in sorted(col_mapping.items()):
            if old_col_idx in processed_old_cols:
                continue

            # Check if this column merged with the next
            if (old_col_idx + 1 in col_mapping and 
                col_mapping[old_col_idx + 1] == new_col_idx):
                # Merged pair: combine headers
                h1 = self.col_headers.get(old_col_idx, "")
                h2 = self.col_headers.get(old_col_idx + 1, "")
                combined = f"{h1} {h2}".strip()
                synced_headers[new_col_idx] = combined
                processed_old_cols.add(old_col_idx)
                processed_old_cols.add(old_col_idx + 1)
            else:
                # Single column (no merge)
                synced_headers[new_col_idx] = self.col_headers.get(old_col_idx, "")
                processed_old_cols.add(old_col_idx)

        return synced_headers

    def _extract_data_driven(self, table_text: str) -> Tuple[List[List[str]], Dict[int, Optional[str]], Dict[int, str]]:
        """
        Extract table using data rows to guide structure.

        Steps:
        1. Find <S> and <C> markers for column boundaries
        2. Extract raw data rows
        3. Merge sparse columns (>80% empty) with semantic awareness
        4. Sync headers to merged column structure
        5. Clean spacing (merge $, %, parentheses, etc.)
        6. Identify active columns (drop single-char noise)
        7. Infer column types from content
        
        Returns: (data_rows, col_map, col_headers)
        """
        lines = table_text.split("\n")

        # Find <S> marker line (column structure marker)
        marker_line = None
        marker_line_idx = 0
        for i, line in enumerate(lines):
            if "<S>" in line:
                marker_line = line
                marker_line_idx = i
                break

        if not marker_line:
            return [], {}, {}

        # Find all <C> positions
        c_positions = [m.start() for m in re.finditer(r"<C>", marker_line)]
        if not c_positions:
            return [], {}, {}

        # Group adjacent <C> tags (within 5 chars) and filter single-width candidates
        grouped_positions = []
        current_group = [c_positions[0]]
        for pos in c_positions[1:]:
            if pos - current_group[-1] <= 5:
                current_group.append(pos)
            else:
                grouped_positions.append(current_group)
                current_group = [pos]
        grouped_positions.append(current_group)

        # Define column boundaries (start from position 0)
        # Mark single-width <C> groups as candidates for merging
        column_boundaries = []
        single_width_col_indices = set()  # Track which columns are single-width candidates
        first_c_pos = grouped_positions[0][0]
        column_boundaries.append((0, first_c_pos))

        for i, group in enumerate(grouped_positions):
            start = group[0]
            end = (
                grouped_positions[i + 1][0]
                if i + 1 < len(grouped_positions)
                else len(marker_line)
            )

            # Heuristic: if <C> group spans only 1 characters, it's likely a separator
            width = end - start
            col_idx = len(column_boundaries)
            if width < 2:
                single_width_col_indices.add(col_idx)

            column_boundaries.append((start, end))

        # Extract raw data rows (everything after <S>)
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
                cell = re.sub(r"<[^>]+>", "", cell)
                row_cells.append(cell)

            if any(row_cells):
                raw_rows.append(row_cells)

        # STEP 1: Merge sparse columns based on data patterns AND single-width heuristic
        raw_rows, col_mapping = self._merge_sparse_columns(raw_rows, single_width_col_indices)

        # STEP 2: Clean spacing in data cells
        cleaned_rows = []
        for row in raw_rows:
            cleaned_row = []
            for cell in row:
                # Merge $ with following numbers
                cell = re.sub(r"\$\s+", "$", cell)
                # Merge parentheses with numbers
                cell = re.sub(r"\(\s+", "(", cell)
                cell = re.sub(r"\s+\)", ")", cell)
                # Merge % with preceding numbers
                cell = re.sub(r"\s+%", "%", cell)
                # Merge comma-separated digits
                cell = re.sub(r",\s+", ",", cell)
                cleaned_row.append(cell)

            # POST-PROCESS: Merge trailing single-char symbols with preceding cells
            # and leading symbols with following cells
            final_row = []

            # First pass: merge trailing symbols
            merged_once = []
            for i, cell in enumerate(cleaned_row):
                if (
                    cell in ["%", "$", "€", "£", "¥", ")"]
                    and merged_once
                    and merged_once[-1]
                    and not any(c in merged_once[-1] for c in ["%", "$", "€", "£", "¥"])
                ):
                    merged_once[-1] = merged_once[-1] + cell
                else:
                    merged_once.append(cell)

            # Second pass: merge leading symbols
            for i, cell in enumerate(merged_once):
                if cell in ["$", "€", "£", "¥", "("] and i + 1 < len(merged_once):
                    next_cell = merged_once[i + 1]
                    if next_cell and (
                        next_cell[0].isdigit() or next_cell.startswith("(")
                    ):
                        final_row.append(cell + next_cell)
                        merged_once[i + 1] = None
                    else:
                        final_row.append(cell)
                elif cell is not None:
                    final_row.append(cell)

            final_row = [c for c in final_row if c is not None]
            cleaned_rows.append(final_row)

        # STEP 3: Identify active columns (non-empty, not single-char noise)
        active_col_indices = set()
        for row in cleaned_rows:
            for col_idx, cell in enumerate(row):
                if cell and len(cell) > 1:
                    active_col_indices.add(col_idx)

        active_col_indices = sorted(active_col_indices)

        # Filter rows to active columns only
        filtered_rows = []
        for row in cleaned_rows:
            filtered_row = [row[i] if i < len(row) else "" for i in active_col_indices]
            if any(filtered_row):
                filtered_rows.append(filtered_row)

        # STEP 4: Extract column headers (infer from data patterns + look for year indicators)
        col_headers = {}
        for local_idx, global_col_idx in enumerate(active_col_indices):
            sample_cells = [
                row[local_idx] for row in filtered_rows if local_idx < len(row)
            ]

            # Try to infer year from cell content
            years_found = set()
            for cell in sample_cells:
                year_matches = YEAR_REGEX.findall(cell)
                years_found.update(year_matches)

            # If year found in cells, use it as header
            if years_found:
                col_headers[local_idx] = f"value_{max(years_found)}"
            else:
                col_headers[local_idx] = ""

        # STEP 5: Infer column types from content
        col_map = {}

        for local_idx, global_col_idx in enumerate(active_col_indices):
            sample_cells = [
                row[local_idx] for row in filtered_rows if local_idx < len(row)
            ]

            has_dates = (
                sum(1 for c in sample_cells if re.search(r"\d{1,2}/\d{1,2}/\d{4}", c))
                > 0
            )
            has_percentages = sum(1 for c in sample_cells if "%" in c) > 0
            has_large_numbers = (
                sum(1 for c in sample_cells if self._is_numeric_large(c)) > 0
            )
            text_count = sum(1 for c in sample_cells if c and not self._is_numeric(c))
            numeric_count = sum(1 for c in sample_cells if c and self._is_numeric(c))

            col_type = None

            # First column is always instrument/label
            if local_idx == 0:
                col_type = "context_text"

            # Detect by content
            elif has_dates:
                col_type = "metadata_maturity"
            elif has_percentages:
                col_type = None  # Rate column, skip
            elif has_large_numbers:
                col_type = self.table_default_type or "value"
            else:
                col_type = None

            col_map[local_idx] = col_type

        return filtered_rows, col_map, col_headers

    def _classify_columns_from_headers(self):
        """
        Refine column classification using header analysis.
        Maps detected headers to semantic types (notional, fair_value, gain_loss, etc.)
        """
        for local_idx, header in self.col_headers.items():
            if not header or self.col_map.get(local_idx):
                continue

            header_lower = header.lower()

            # Skip noise columns
            if NOISE_HEADERS.search(header_lower):
                self.col_map[local_idx] = None
                continue

            # Classify by header patterns
            if CONTEXT_HEADERS.search(header_lower):
                self.col_map[local_idx] = "context_text"
            elif VAR_HEADERS.search(header_lower):
                self.col_map[local_idx] = "fair_value"
            elif NOTIONAL_HEADERS.search(header_lower):
                self.col_map[local_idx] = "notional"
            elif NET_HEADERS.search(header_lower):
                self.col_map[local_idx] = "net_fair_value"
            elif GROSS_HEADERS.search(header_lower):
                self.col_map[local_idx] = "gross_fair_value"
            elif LEVEL_HEADERS.search(header_lower):
                self.col_map[local_idx] = "fair_value"
            elif VALUE_HEADERS.search(header_lower):
                if ASSET_HEADERS.search(header_lower):
                    self.col_map[local_idx] = "asset_fair_value"
                elif LIABILITY_HEADERS.search(header_lower):
                    self.col_map[local_idx] = "liability_fair_value"
                else:
                    self.col_map[local_idx] = "fair_value"
            elif GAIN_LOSS_HEADERS.search(header_lower):
                self.col_map[local_idx] = "gain_loss"
            elif LOCATION_HEADERS.search(header_lower):
                self.col_map[local_idx] = "location"
            elif MATURITY_HEADERS.search(header_lower):
                self.col_map[local_idx] = "metadata_maturity"

    def _apply_column_heuristics(self):
        """
        Applies data-driven heuristics to classify ambiguous columns.
        Specific Rule: If Column 2 (Index 1) is unclassified AND contains text (not numbers),
        treat it as a Context/Purpose column.
        """
        TARGET_IDX = 1

        # Only run if column exists and is currently unclassified
        if TARGET_IDX not in self.col_map or self.col_map[TARGET_IDX] is not None:
            return

        # Scan the first 5 data rows to check content type
        text_rows = 0
        numeric_rows = 0

        for row in self.data[:5]:
            if len(row) > TARGET_IDX:
                cell = row[TARGET_IDX].strip()
                if not cell or set(cell).issubset(set("- ")):
                    continue  # Skip empty/dash

                if self._is_valid_value(cell):
                    numeric_rows += 1
                else:
                    # It has content but isn't a number -> Text
                    text_rows += 1

        # Logic: If we see text and NO numbers, it's a Purpose column
        if text_rows > 0 and numeric_rows == 0:
            self.col_map[TARGET_IDX] = "context_text"

    def _resolve_offsetting_conflicts(self):
        """
        Handle ASC 210-20 netting conflicts: if both net and gross fair values exist,
        deprioritize gross amounts in favor of net amounts.
        """
        has_net = any(
            col_type == "net_fair_value" for col_type in self.col_map.values()
        )

        if has_net:
            for idx, col_type in self.col_map.items():
                if col_type == "gross_fair_value":
                    self.col_map[idx] = None

    def _is_numeric(self, val: str) -> bool:
        """Check if value is numeric (with currency/percent symbols)."""
        clean = re.sub(r"[$€£¥,%()-]", "", val).strip()
        return bool(re.match(r"^-?\d+(?:\.\d+)?$", clean))

    def _is_numeric_large(self, val: str) -> bool:
        """Check if value is a large number (> 1000)."""
        if not self._is_numeric(val):
            return False
        try:
            clean = re.sub(r"[$€£¥,%()-]", "", val).strip()
            return float(clean) > 1000
        except:
            return False

    def _is_valid_value(self, val: str) -> bool:
        """Check if value is valid for sentence generation."""
        clean = re.sub(r"[$€£¥,%()-]", "", val).strip()
        if clean in ["-", "—", "0", "0.0", "", "0.00", "--"]:
            return False
        return bool(re.match(r"^-?\d+(?:\.\d+)?$", clean))

    def _cleanup_spaced_value(self, val: str) -> str:
        val = re.sub(r"(\d)\s+([().,])", r"\1\2", val)
        val = re.sub(r"([().,])\s+(\d)", r"\1\2", val)
        val = re.sub(r"\s+", "", val)
        return val

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

    def _is_subheader_row(self, row: List[str]) -> bool:
        """
        Determines if a row is likely a section header rather than a data row.
        
        Simple rule: A row is a subheader if:
        1. Only column 0 is populated (all other columns are empty), OR
        2. It has no valid numeric data in any value columns (after we've started seeing data)
        
        This naturally catches:
        - "Interest rate contracts:"
        - "swaps options collars"
        - "Not designated as hedging instruments:"
        - Any row with just a label and no numbers
        """
        if not row or not row[0].strip():
            return False

        # Check if ONLY column 0 has content (all others empty)
        if len(row) > 1:
            rest_is_empty = all(not cell.strip() for cell in row[1:])
            if rest_is_empty:
                return True

        # Check if this row has any valid numeric data
        has_numeric_data = False
        for i, cell in enumerate(row[1:], start=1):
            if (
                i in self.col_map
                and self.col_map[i]
                and self.col_map[i] not in ["context_text", "metadata_maturity"]
                and self._is_valid_value(cell)
            ):
                has_numeric_data = True
                break

        # If no numeric data, it's a subheader
        return not has_numeric_data

    def process(self) -> Tuple[List[str], bool]:
        if self.invalid_table or not self.data:
            return ([], False)

        sentences = []
        active_context = ""
        # Check for table anchoring
        table_has_strong_notional_col = any(
            col_type and STRONG_NOTIONAL_REGEX.search(col_type)
            for col_type in self.col_map.values()
        )

        if self.table_default_type == "notional":
            table_has_strong_notional_col = True

        # Get caption year
        caption_year_str = ""
        if self.caption:
            caption_years = YEAR_REGEX.findall(self.caption)
            if caption_years:
                try:
                    caption_year_str = f"in {max(int(y) for y in caption_years)} "
                except:
                    caption_year_str = f"in {caption_years[-1]} "

        # Process data rows
        table_has_strong_row = False

        for row_idx, row in enumerate(self.data):
            if not row or not row[0].strip():
                continue

            if self._is_subheader_row(row):
                # Update the active context (e.g., "Interest Rate Contracts")
                # We strip colons/whitespace to keep it clean.
                active_context = row[0].strip().rstrip(":")
                continue

            instrument_name = row[0].strip()
            if "total" in instrument_name.lower():
                continue
            if active_context:
                instrument_name = f"{active_context} {instrument_name}"

            # Check derivative signals
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

            # Anchoring check
            if (
                is_strict
                or is_table_safe
                or has_strong_notional
                or has_currency_notional
            ):
                table_has_strong_row = True

            # Keep/drop decision
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

            # Sophisticated exception
            if SOPHISTICATED_TARGETS.search(instrument_name):
                soph = True
                if not should_keep and self.is_sophisticated:
                    should_keep = True

            if not should_keep:
                continue

            # Extract expiration
            expiration_str = ""
            for col_idx, col_type in self.col_map.items():
                if col_idx < len(row) and col_type == "metadata_maturity":
                    cell = row[col_idx]
                    years = YEAR_REGEX.findall(cell)
                    if years:
                        expiration_str = f" (expiring in {max(years)})"

            # Generate sentences
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

                clean_val = self._cleanup_spaced_value(cell)
                if "(" in clean_val and ")" in clean_val:
                    clean_val = "-" + clean_val.replace("(", "").replace(")", "")
                clean_val = clean_val.replace("$", "").replace(",", "").strip()

                parts = col_type.split("_")
                year_str = ""
                if parts[-1].isdigit() and len(parts[-1]) == 4:
                    year_str = f"in {parts.pop()} "

                if not year_str and caption_year_str:
                    year_str = caption_year_str

                base_type = "_".join(parts)
                value = self.normalize_value(clean_val)
                display_instrument = f"{instrument_name}{expiration_str}"

                # SMART SEMANTICS: Detect value type from instrument name
                actual_col_type = base_type

                # If instrument mentions "gain" or "loss", it's OCI/income, not notional
                if GAIN_LOSS_HEADERS.search(display_instrument):
                    actual_col_type = "gain_loss"

                # If it mentions "fair value", force fair_value type
                elif VALUE_HEADERS.search(display_instrument):
                    actual_col_type = "fair_value"

                # If it mentions "notional", keep as notional
                elif STRONG_NOTIONAL_REGEX.search(display_instrument):
                    actual_col_type = "notional"

                use_anchor = (
                    table_has_strong_row
                    or table_has_strong_notional_col
                    or self.caption_is_strong
                ) and not soph
                anchor_text = TABLE_ANCHOR if use_anchor else ""

                # Generate sentence based on actual type
                if "notional" in actual_col_type:
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with a notional amount of {value}."
                elif "gain_loss" in actual_col_type:
                    sentence = f"{anchor_text} {year_str}The Company recorded {display_instrument} of {value}."
                    continue
                elif "fair_value" in actual_col_type:
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with a fair value of {value}."
                elif actual_col_type == "value":
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with a value of {value}."
                else:
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with an amount of {value}."

                sentences.append(sentence)

        return (sentences, False)
