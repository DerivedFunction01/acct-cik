# %%
import re
from typing import List, Dict, Optional, Set, Tuple

from derivative_regex import BASE_REGEX, CURRENCY_NAMES_REGEX, FX_SOFT_REGEX, IR_SOFT_REGEX, SOFT_GEN_REGEX, SOFT_REGEX, STRICT_REGEX, TABLE_REGEX, YEAR_REGEX

# --- REGEX DEFINITIONS ---

# Basic patterns
NUMERIC_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
NUMERIC_WITH_SYMBOLS = re.compile(r"[$€£¥,%()-]")
ACCOUNTING_NEGATIVE = re.compile(r"\(([^)]+)\)")  # Converts (100) to -100
WHITESPACE_REGEX = re.compile(r"\s+")
HTML_TAG_REGEX = re.compile(r"<[^>]+>")

# Table Structure Markers
CAPTION_REGEX = re.compile(
    r"<caption>\s*(.*?)(?=\n\n|:\n|\n[-=])", re.DOTALL | re.IGNORECASE
)
S_MARKER_REGEX = re.compile(r"<S>")
C_MARKER_REGEX = re.compile(r"<C>")

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
NOISE_HEADERS = re.compile(r"strike|exercise|shares|units|count|ratio|weighted", re.IGNORECASE)

DESIGNATION_REGEX = re.compile(r"designated|hedging|trading|fair value|cash flow|net investment|derivatives|aoci|income|earnings|gain|loss",re.IGNORECASE,)

SOPHISTICATED_TARGETS = re.compile(r"\b(?:convertibles?|warrants?|conversion)\b", re.IGNORECASE)
# Paragraph Detection
TABLE_OF_CONTENTS_REGEX = re.compile(r"\.{3,}")
PARAGRAPH_THRESHOLD = 250
TABLE_ANCHOR = " T_"
DEBUG = False


def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


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
        lines = table_text.split("\n")

        # Find <S> marker line
        marker_line = None
        marker_line_idx = 0
        for i, line in enumerate(lines):
            if S_MARKER_REGEX.search(line):
                marker_line = line
                marker_line_idx = i
                break

        if not marker_line:
            return [], {}, {}

        # Find all <C> positions
        c_positions = [m.start() for m in C_MARKER_REGEX.finditer(marker_line)]
        debug_print(f"Found {len(c_positions)} <C> markers")
        if not c_positions:
            return [], {}, {}

        # Group adjacent <C> tags
        grouped_positions = []
        current_group = [c_positions[0]]
        for pos in c_positions[1:]:
            if pos - current_group[-1] <= 5:
                current_group.append(pos)
            else:
                grouped_positions.append(current_group)
                current_group = [pos]
        grouped_positions.append(current_group)

        # Define column boundaries
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

        # Extract raw data rows
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

        # STEP 1: Merge sparse columns
        merged_rows, col_mapping = self._merge_sparse_columns(
            raw_rows, single_width_col_indices
        )

        # STEP 2: Clean spacing & Strict Merge Symbols
        cleaned_rows = []
        for row in merged_rows:
            cleaned_row = self._clean_and_merge_symbols(row)
            cleaned_rows.append(cleaned_row)

        # STEP 3: Identify active columns
        active_col_indices = set()
        for row in cleaned_rows:
            for col_idx, cell in enumerate(row):
                if cell and len(cell) > 1:
                    active_col_indices.add(col_idx)
        active_col_indices = sorted(active_col_indices)

        # Filter rows
        filtered_rows = []
        for row in cleaned_rows:
            filtered_row = [row[i] if i < len(row) else "" for i in active_col_indices]
            if any(filtered_row):
                filtered_rows.append(filtered_row)

        # STEP 4: Extract headers
        col_headers = {}
        for local_idx, global_col_idx in enumerate(active_col_indices):
            sample_cells = [
                row[local_idx] for row in filtered_rows if local_idx < len(row)
            ]
            years_found = set()
            for cell in sample_cells:
                year_matches = YEAR_REGEX.findall(cell)
                years_found.update(year_matches)
            if years_found:
                col_headers[local_idx] = f"value_{max(years_found)}"
            else:
                col_headers[local_idx] = ""

        # STEP 5: Infer types
        col_map = {}
        for local_idx, global_col_idx in enumerate(active_col_indices):
            sample_cells = [
                row[local_idx] for row in filtered_rows if local_idx < len(row)
            ]
            has_dates = sum(1 for c in sample_cells if YEAR_REGEX.search(c)) > 0
            has_percentages = sum(1 for c in sample_cells if "%" in c) > 0
            has_large_numbers = (
                sum(1 for c in sample_cells if self._is_numeric_large(c)) > 0
            )

            col_type = None
            if local_idx == 0:
                col_type = "context_text"
            elif has_dates:
                col_type = "metadata_maturity"
            elif has_large_numbers:
                # Prioritize value if it has large numbers, even if it has percentages
                # This fixes tables with mixed data types (rates mixed with fair values)
                col_type = self.table_default_type or "value"
            elif has_percentages:
                col_type = None

            col_map[local_idx] = col_type

        return filtered_rows, col_map, col_headers

    # --- REMAINING METHODS (Unchanged but included for completeness) ---

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
            if not header or self.col_map.get(local_idx):
                continue
            header_lower = header.lower()
            if NOISE_HEADERS.search(header_lower):
                self.col_map[local_idx] = None
                continue
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
        return bool(NUMERIC_PATTERN.match(clean))

    def _is_numeric_large(self, val: str) -> bool:
        if not self._is_numeric(val):
            return False
        try:
            clean = NUMERIC_WITH_SYMBOLS.sub("", val).strip()
            return float(clean) > 1000
        except:
            return False
    def _has_any_value(self, val: str) -> bool:
        return bool(val)

    def _is_valid_value(self, val: str) -> bool:
        clean = NUMERIC_WITH_SYMBOLS.sub("", val).strip()
        if clean in ["-", "—", "0", "0.0", "", "0.00", "--"]:
            return False
        return bool(NUMERIC_PATTERN.match(clean))

    def normalize_value(self, clean_val: str, use_dollar: bool = True):
        # Detect whether the original value used a dollar sign
        had_dollar = "$" in clean_val

        # Convert accounting negatives: (100) → -100
        clean_val = ACCOUNTING_NEGATIVE.sub(r"-\1", clean_val)
        stripped = clean_val.strip("()").replace("%", "").replace("$", "")

        try:
            norm_num = float(stripped.replace(",", ""))
            num = abs(norm_num)

            # Zero case
            if num == 0:
                if use_dollar or had_dollar:
                    return "$0"
                return "0"

            # Format number
            num_str = "{:,.0f}".format(num) if num > 1000 else "{:,.2f}".format(num)

            # Determine whether to apply dollar formatting
            apply_dollar = use_dollar or had_dollar

            if apply_dollar:
                # Accounting-style negative formatting
                if norm_num < 0:
                    return f"$({num_str})"
                else:
                    return f"${num_str}"

            # No-dollar formatting
            if norm_num < 0:
                return f"-{num_str}"
            else:
                return num_str

        except ValueError:
            return clean_val

    def _is_subheader_row(self, row: List[str]) -> bool:
        if not row or not row[0].strip():
            return False
        if len(row) > 1 and all(not cell.strip() for cell in row[1:]):
            return True
        has_numeric_data = False
        for i, cell in enumerate(row[1:], start=1):
            if (
                i in self.col_map
                and self.col_map[i]
                and self.col_map[i] not in ["context_text", "metadata_maturity"]
                and self._has_any_value(cell)
            ):
                has_numeric_data = True
                break
        return not has_numeric_data

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
            caption_years = YEAR_REGEX.findall(self.caption)
            if caption_years:
                try:
                    caption_year_str = f"in {max(int(y) for y in caption_years)} "
                except:
                    caption_year_str = f"in {caption_years[-1]} "
        debug_print(f"Found {len(self.data)} rows")
        for row_idx, row in enumerate(self.data):
            if not row or not row[0].strip():
                continue
            if self._is_subheader_row(row):
                debug_print(f"Found subheader row: {row}")
                raw_header = row[0].strip().rstrip(":")
                header_years = YEAR_REGEX.findall(raw_header)
                if header_years:
                    y_val = max(int(y) for y in header_years)
                    section_year_str = f"in {y_val} "
                    raw_header = YEAR_REGEX.sub("", raw_header).strip(" (),")

                if raw_header:
                    is_designation = bool(DESIGNATION_REGEX.search(raw_header))
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
                if not should_keep and self.is_sophisticated or soph:
                    should_keep = True

            if not should_keep:
                debug_print(f"Discarded candidate row: {row}")
                continue
            debug_print(f"Found candidate row: {row}")
            expiration_str = ""
            for col_idx, col_type in self.col_map.items():
                if col_idx < len(row) and col_type == "metadata_maturity":
                    cell = row[col_idx]
                    years = YEAR_REGEX.findall(cell)
                    if years:
                        expiration_str = f" (expiring in {max(years)})"

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

                # Clean for display
                # Note: We don't strip symbols here anymore because they are attached correctly
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
                value = self.normalize_value(clean_val, actual_col_type != "value")
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
                else:
                    sentence = f"{anchor_text} {year_str}The Company held {display_instrument} with an amount of {value}."
                sentences.append(sentence)

        return (sentences, False)


if __name__ == "__main__":
    DEBUG = True
    string = """<TABLE>
    <CAPTION>
    The warrants issued in lieu of the financing were recorded as and valued using the Black-Scholes Option Pricing Model with the following weighted-average assumptions used.
    
                                                    11/30/05 Traunch  1/4/06 Traunch  1/30/06 Traunch  11/16/07 Traunch  4/22/08 Traunch
    ----------------------------------------------  ---------------  -------------  --------------  ---------------  --------------
    <S>                                             <C>              <C>            <C>             <C>              <C>
    Approximate risk free rate                                4.42%          4.28%           4.46%            3.88%           3.29%
    Average expected life                                   5 years        5 years         5 years          7 years         7 years
    Dividend yield                                               0%             0%              0%               0%              0%
    Volatility                                              356.33%        348.92%         342.77%          286.90%         325.91%
    Number of warrants granted                              375,000        625,000       1,500,000       15,000,000      10,000,000
    Estimated fair value of total warrants granted         $299,975       $493,692      $1,184,815          $59,995         $15,000
    
    </TABLE>"""
    table = TableToTextConverter(string, is_sophisticated=True)
    print(table.process())
# %%
