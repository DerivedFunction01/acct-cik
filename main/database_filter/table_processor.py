import re
from typing import List, Dict, Optional, Tuple

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

# --- HEADER DEFINITIONS ---
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
MATURITY_HEADERS = re.compile(r"maturity|expiration", re.IGNORECASE)

SECTION_KEYWORDS = re.compile(
    r"designated as|hedging instruments|underlying risk|derivatives not designated|"
    r"cash flow|fair value|net investment|assets|liabilities|equity contracts|warrants|"
    r"embedded|offsetting|trading|non[- ]?trading|held for|financial instruments",
    re.IGNORECASE,
)
SOPHISTICATED_TARGETS = re.compile(
    r"\b(?:convertibles?|warrants?|conversion)\b", re.IGNORECASE
)

TABLE_ANCHOR = " T_ "
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
        self.data, self.col_map = self._extract_data_driven(
            caption_regex.sub("", table_text)
        )
        self.invalid_table = len(self.data) == 0

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

    def _merge_sparse_columns(self, raw_rows: List[List[str]]) -> List[List[str]]:
        """
        Merge very sparse columns (mostly empty) with adjacent columns.
        This handles cases where <C> markers create phantom columns.
        """
        if not raw_rows:
            return raw_rows

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

        # Columns with > 80% empty cells are candidates for merging
        sparse_columns = {
            idx for idx, sparsity in col_sparsity.items() if sparsity > 0.8
        }

        if not sparse_columns:
            return raw_rows

        # Merge sparse columns with their neighbors
        merged_rows = []
        for row in raw_rows:
            merged_row = []
            skip_next = False

            for col_idx in range(len(row)):
                if skip_next:
                    skip_next = False
                    continue

                cell = row[col_idx]

                # If this column is sparse, try to merge with next column
                if col_idx in sparse_columns and col_idx + 1 < len(row):
                    next_cell = row[col_idx + 1]
                    # Merge non-empty cells, skip if both empty
                    if cell or next_cell:
                        merged_row.append((cell + next_cell).strip())
                        skip_next = True
                    else:
                        skip_next = True
                else:
                    if col_idx not in sparse_columns:
                        merged_row.append(cell)

            if merged_row:
                merged_rows.append(merged_row)

        return merged_rows

    def _extract_data_driven(
        self, table_text: str
    ) -> Tuple[List[List[str]], Dict[int, str]]:
        """
        Extract table using data rows to guide structure.

        Steps:
        1. Find <S> and <C> markers for column boundaries
        2. Extract raw data rows
        3. Merge sparse columns (>80% empty)
        4. Clean spacing (merge $, %, parentheses, etc.)
        5. Identify active columns (drop single-char noise)
        6. Infer column types from content
        """
        lines = table_text.split("\n")

        # Find <S> marker line
        marker_line = None
        marker_line_idx = 0
        for i, line in enumerate(lines):
            if "<S>" in line:
                marker_line = line
                marker_line_idx = i
                break

        if not marker_line:
            return [], {}

        # Find all <C> positions
        c_positions = [m.start() for m in re.finditer(r"<C>", marker_line)]
        if not c_positions:
            return [], {}

        # Group adjacent <C> tags (within 5 chars)
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
        column_boundaries = []
        first_c_pos = grouped_positions[0][0]
        column_boundaries.append((0, first_c_pos))

        for i, group in enumerate(grouped_positions):
            start = group[0]
            end = (
                grouped_positions[i + 1][0]
                if i + 1 < len(grouped_positions)
                else len(marker_line)
            )
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
                cell = re.sub(r"<[^>]+>", "", cell)
                row_cells.append(cell)

            if any(row_cells):
                raw_rows.append(row_cells)

        # STEP 1: Merge sparse columns based on data patterns
        raw_rows = self._merge_sparse_columns(raw_rows)

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

        # STEP 4: Infer column types from content
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
                col_type = self.table_default_type or "notional"
            else:
                col_type = None

            col_map[local_idx] = col_type

        return filtered_rows, col_map

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

    def process(self) -> Tuple[List[str], bool]:
        if self.invalid_table or not self.data:
            return ([], False)

        sentences = []

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

            instrument_name = row[0].strip()
            if "total" in instrument_name.lower():
                continue

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
