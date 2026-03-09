import re
from typing import List, Dict, Optional, Set, Tuple
from defs.regex_lib import build_regex
from defs.region_regex import MAJOR_CURRENCIES

# --- BASIC REGEX PATTERNS ---
CAPTION_REGEX = re.compile(
    r"<caption[^>]*>(.*?)(?=\n\s*\n|\n\s*<S>|\n\s*[-=]{3,}|\Z)",
    re.IGNORECASE | re.DOTALL,
)
TABLE_TAG_REGEX = re.compile(r"<TABLE.*?>", re.DOTALL | re.IGNORECASE)
S_MARKER_REGEX = re.compile(r"<S>")
C_MARKER_REGEX = re.compile(r"<C>")
HTML_TAG_REGEX = re.compile(r"<[^>]+>")
WHITESPACE_REGEX = re.compile(r"\s+")
NUMERIC_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
NUMERIC_WITH_SYMBOLS = re.compile(r"[$€£¥₹%\(\)\-,]")
PERCENT_HEADER_REGEX = re.compile(r"\b(?:%|percent(?:age)?)\b", re.IGNORECASE)

# safe patterns for years in tables
YEAR_REGEX = build_regex([r"(?:\d{1,2}/)+(\d{2,4})", r"(19[8-9]\d|20\d{2})"])
TABLE_TOK = "TABLE_"
# Header detection
LAST_HEADER_PATTERN = build_regex([
    "notional",
    "fair",
    "location",
    "carrying",
    "level",
    "maturity",
    "rate",
    "yield",
    "weighted",
    "amount",
    "value",
    "balance",
    "principal",
    "gain",
    "loss",
    "income",
    "asset",
    "liability",
    "status",
    "date",
    ]
)

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

# Symbol cleaning
DOLLAR_SPACE_REGEX = re.compile(r"(\$)\s+")
OPEN_PAREN_SPACE_REGEX = re.compile(r"\(\s+")
CLOSE_PAREN_SPACE_REGEX = re.compile(r"\s+\)")
PERCENT_SPACE_REGEX = re.compile(r"\s+%")
COMMA_SPACE_REGEX = re.compile(r",\s+")

# Paragraph detection
TABLE_OF_CONTENTS_REGEX = re.compile(r"\.{3,}")
PARAGRAPH_THRESHOLD = 250


PREFIX_SYMBOLS = set()
SUFFIX_SYMBOLS = set()

for code, data in MAJOR_CURRENCIES.items():
    symbols = data.get("symbols", [])
    if data.get("prefix"):
        PREFIX_SYMBOLS.update(symbols)
    if data.get("suffix"):
        SUFFIX_SYMBOLS.update(symbols)


class SimpleTableProcessor:
    """
    Process tables: repair invalid ones, merge sparse columns, heal data rows.
    No derivative/finance-specific logic.
    """

    def __init__(self, table_text: str):
        self.raw_text = table_text
        self.caption = self._extract_caption(table_text)
        self.table_currency = self._detect_table_currency(self.caption)
        self.global_multiplier = self._scan_for_multiplier(self.caption) or 1.0
        self.col_multipliers = {}

        # Extract data
        self.data, self.col_map, self.col_headers = self._extract_data_driven(
            CAPTION_REGEX.sub("", table_text)
        )

        self.invalid_table = len(self.data) == 0
        if self.invalid_table:
            self._repair_invalid_table()

        if self._detect_paragraph_masquerading_as_table():
            self.invalid_table = True

    def _extract_caption(self, text: str) -> str:
        """Extract caption from <caption> tags"""
        match = CAPTION_REGEX.search(text)
        if match:
            caption_text = match.group(1).strip()
            caption_text = WHITESPACE_REGEX.sub(" ", caption_text)
            return caption_text
        return ""

    def _detect_table_currency(self, context: str) -> str:
        """
        Detect primary currency from context (simplified to major currencies).
        Returns ISO code like 'USD', 'EUR', etc. Defaults to 'USD'.
        """
        if not context:
            return "USD"

        context_lower = context.lower()

        # Check currency names
        for currency_code, currency_data in MAJOR_CURRENCIES.items():
            for name in currency_data.get("names", []):
                if name in context_lower:
                    return currency_code

        # Check currency symbols
        for currency_code, currency_data in MAJOR_CURRENCIES.items():
            for symbol in currency_data.get("symbols", []):
                if symbol in context:
                    return currency_code

        # Default to USD
        return "USD"

    def _scan_for_multiplier(self, text: str) -> Optional[float]:
        """Detect thousand/million/billion multipliers"""
        if not text:
            return None
        if BILLION_REGEX.search(text):
            return 1_000_000_000.0
        if MILLION_REGEX.search(text):
            return 1_000_000.0
        if THOUSAND_REGEX.search(text):
            return 1_000.0
        return None

    def _repair_invalid_table(self):
        """
        Repair table by relocating <S> marker to actual header row.
        Scores lines by header keyword count.
        """
        table_text = CAPTION_REGEX.sub("", self.raw_text)
        table_text = TABLE_TAG_REGEX.sub("", table_text)
        lines = table_text.split("\n")

        # Find current marker
        old_marker_idx = None
        old_marker_line = None
        for i, line in enumerate(lines):
            if S_MARKER_REGEX.search(line):
                old_marker_idx = i
                old_marker_line = line
                break

        if old_marker_idx is None:
            return

        # Score lines before marker
        best_header_idx = old_marker_idx
        best_score = 0

        for i in range(old_marker_idx):
            line = lines[i].strip()
            if not line or line.startswith("<"):
                continue

            matches = LAST_HEADER_PATTERN.findall(line)
            score = len(matches)

            if score > best_score:
                best_score = score
                best_header_idx = i

        # Relocate marker if better location found
        if best_header_idx != old_marker_idx and best_score > 0:
            lines[old_marker_idx] = (
                lines[old_marker_idx].replace("<S>", "").replace("<C>", "").strip()
            )
            if not lines[old_marker_idx]:
                lines[old_marker_idx] = ""
            
            assert old_marker_line is not None
            lines[best_header_idx] = old_marker_line
            corrected_table = "\n".join(lines)

            # Re-extract with corrected table
            corrected_data, corrected_col_map, corrected_col_headers = (
                self._extract_data_driven(CAPTION_REGEX.sub("", corrected_table))
            )

            if corrected_data:
                self.data = corrected_data
                self.col_map = corrected_col_map
                self.col_headers = corrected_col_headers
                self.invalid_table = False

    def _extract_data_driven(
        self, table_text: str
    ) -> Tuple[List[List[str]], Dict[int, Optional[str]], Dict[int, str]]:
        """
        Extract table data:
        1. Find <S> marker to detect column boundaries via <C> positions
        2. Extract header rows (before marker) and data rows (after marker)
        3. Merge sparse columns
        4. Clean and repair rows
        """
        table_text = TABLE_TAG_REGEX.sub("", table_text)
        lines = table_text.split("\n")

        # Find marker line
        marker_line = None
        marker_line_idx = 0
        for i, line in enumerate(lines):
            if S_MARKER_REGEX.search(line):
                marker_line = line
                marker_line_idx = i
                break

        if not marker_line:
            return [], {}, {}

        # Parse column boundaries from <C> positions
        c_positions = [m.start() for m in C_MARKER_REGEX.finditer(marker_line)]
        if not c_positions:
            return [], {}, {}

        # Group nearby <C> positions
        grouped_positions = []
        current_group = [c_positions[0]]
        for pos in c_positions[1:]:
            if pos - current_group[-1] <= 5:
                current_group.append(pos)
            else:
                grouped_positions.append(current_group)
                current_group = [pos]
        grouped_positions.append(current_group)

        # Build column boundaries
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

        # Extract data rows
        data_lines = lines[marker_line_idx + 1 :]
        raw_rows = []
        for line in data_lines:
            if not line.strip():
                continue
            row_cells = []
            for start, end in column_boundaries:
                cell = (
                    line[start : min(end, len(line))].strip()
                    if start < len(line)
                    else ""
                )
                cell = HTML_TAG_REGEX.sub("", cell)
                row_cells.append(cell)
            if any(row_cells):
                raw_rows.append(row_cells)

        # Extract header rows
        header_lines = lines[:marker_line_idx]
        raw_header_rows = []
        for line in header_lines:
            clean_line = line.strip()
            if not clean_line or "<CAPTION>" in clean_line or "<TABLE>" in clean_line:
                continue
            if all(c in "-= " for c in clean_line) and any(
                c in "-=" for c in clean_line
            ):
                continue

            h_cells = []
            for start, end in column_boundaries:
                h_cells.append(
                    line[start : min(end, len(line))].strip()
                    if start < len(line)
                    else ""
                )

            if any(h_cells):
                raw_header_rows.append(h_cells)

        # Merge sparse columns
        merged_rows, col_mapping = self._merge_sparse_columns(
            raw_rows, single_width_col_indices
        )

        # Apply merge to headers
        merged_headers_map = {}
        for h_row in raw_header_rows:
            for old_idx, text in enumerate(h_row):
                if not text:
                    continue
                new_idx = col_mapping.get(old_idx, old_idx)
                if new_idx not in merged_headers_map:
                    merged_headers_map[new_idx] = []
                merged_headers_map[new_idx].append(text)

        final_physical_headers = {}
        for idx, parts in merged_headers_map.items():
            final_physical_headers[idx] = " ".join(parts).strip()

        # Clean and repair rows
        cleaned_rows = []
        for row in merged_rows:
            cleaned_row = self._clean_and_merge_symbols(row)
            cleaned_rows.append(cleaned_row)

        cleaned_rows = self._heal_data_rows(cleaned_rows)
        cleaned_rows = self._repair_split_numbers(cleaned_rows)
        cleaned_rows = self._repair_shifted_currency(cleaned_rows)

        # Filter to active columns
        active_col_indices = set()
        for row in cleaned_rows:
            for col_idx, cell in enumerate(row):
                if cell and len(cell) > 1:
                    active_col_indices.add(col_idx)
        active_col_indices = sorted(active_col_indices)

        filtered_rows = []
        for row in cleaned_rows:
            filtered_row = [row[i] if i < len(row) else "" for i in active_col_indices]
            if any(filtered_row):
                filtered_rows.append(filtered_row)

        # Build column headers with primitive type detection
        col_headers = {}
        col_map = {}

        for local_idx, global_col_idx in enumerate(active_col_indices):
            header_text = final_physical_headers.get(global_col_idx, "")
            col_headers[local_idx] = header_text

            # Primitive type detection from sample data
            sample_cells = [
                row[local_idx]
                for row in filtered_rows
                if local_idx < len(row) and row[local_idx]
            ]
            col_type = self._detect_primitive_type(sample_cells)

            # Refine "value" type using header hints
            if col_type == "value" and header_text:
                header_lower = header_text.lower()
                if any(s in header_text for s in PREFIX_SYMBOLS | SUFFIX_SYMBOLS):
                    col_type = "dollar"
                else:
                    for code, props in MAJOR_CURRENCIES.items():
                        if code.lower() in header_lower or any(n in header_lower for n in props.get("names", [])):
                            col_type = "dollar"
                            break

            # Header hint override: if the header indicates percent, treat as percentage.
            if self._is_percentage_header(header_text) and col_type in {"value", "mixed", None}:
                col_type = "percentage"

            col_map[local_idx] = col_type

        filtered_rows = self._normalize_percentage_columns(filtered_rows, col_map, col_headers)

        return filtered_rows, col_map, col_headers

    def _merge_sparse_columns(
        self, raw_rows: List[List[str]], single_width_cols: Optional[Set] = None
    ) -> Tuple[List[List[str]], Dict[int, int]]:
        """Merge sparse columns (high empty percentage or single-width markers)"""
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

                if strategy == "merge_right":
                    if col_idx + 1 < len(row):
                        next_cell = row[col_idx + 1]
                        merged_row.append((cell + next_cell).strip())
                        skip_next = True
                        row_col_mapping[col_idx] = new_col_idx
                        row_col_mapping[col_idx + 1] = new_col_idx
                    else:
                        merged_row.append(cell)
                        row_col_mapping[col_idx] = new_col_idx

                elif strategy == "merge_left":
                    if merged_row:
                        merged_row[-1] = (merged_row[-1] + cell).strip()
                        row_col_mapping[col_idx] = len(merged_row) - 1
                    else:
                        merged_row.append(cell)
                        row_col_mapping[col_idx] = new_col_idx

                else:
                    merged_row.append(cell)
                    row_col_mapping[col_idx] = new_col_idx

            if not col_mapping:
                col_mapping = row_col_mapping

            merged_rows.append(merged_row)

        return merged_rows, col_mapping

    def _detect_merge_patterns(
        self, raw_rows: List[List[str]], sparse_columns: set
    ) -> Dict[int, str]:
        """Detect if sparse columns should merge left or right"""
        merge_directions = {}

        for col_idx in sparse_columns:
            col_patterns = set()

            for row in raw_rows:
                if col_idx < len(row) and row[col_idx].strip():
                    val = row[col_idx].strip()
                    if val in PREFIX_SYMBOLS:
                        col_patterns.add("prefix")
                    elif val in SUFFIX_SYMBOLS:
                        col_patterns.add("suffix")
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

            has_prefix = "prefix" in col_patterns or "prefix_paren" in col_patterns
            has_suffix = (
                "suffix" in col_patterns
                or "suffix_paren" in col_patterns
                or "suffix_percent" in col_patterns
            )
            has_other = "other" in col_patterns

            if has_prefix and not has_suffix and not has_other:
                merge_directions[col_idx] = "merge_right"
            elif has_suffix and not has_prefix and not has_other:
                merge_directions[col_idx] = "merge_left"
            else:
                merge_directions[col_idx] = "skip"

        return merge_directions

    def _clean_and_merge_symbols(self, row: List[str]) -> List[str]:
        """Clean internal spacing and merge adjacent symbols with numbers"""
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

        # Merge adjacent cells
        final_row = []
        skip_idx = -1

        for i, cell in enumerate(cleaned_row):
            if i <= skip_idx:
                continue

            current_val = cell

            if i + 1 < len(cleaned_row):
                next_val = cleaned_row[i + 1]

                # Merge suffix
                if next_val in SUFFIX_SYMBOLS or next_val in [")", "%"] and current_val:
                    if self._is_numeric_start(current_val):
                        current_val = current_val + next_val
                        skip_idx = i + 1

                # Merge prefix
                elif current_val in PREFIX_SYMBOLS or current_val == "(" and next_val:
                    if self._is_numeric_start(next_val):
                        current_val = current_val + next_val
                        skip_idx = i + 1

            final_row.append(current_val)

        return final_row

    def _is_numeric_start(self, val: str) -> bool:
        """Check if value looks like start of a number"""
        if not val:
            return False
        clean = val
        for symbol in PREFIX_SYMBOLS:
            clean = clean.replace(symbol, "")
        for symbol in SUFFIX_SYMBOLS:
            clean = clean.replace(symbol, "")
        clean = clean.replace(",", "").replace("(", "").replace(" ", "")
        if not clean:
            return False
        return clean[0].isdigit() or clean.startswith("-") or clean.startswith(".")

    def _heal_data_rows(self, rows: List[List[str]]) -> List[List[str]]:
        """Fix rows where text has shifted into data columns"""
        healed_rows = []
        prev_text_row = None

        for row in rows:
            if not row or not any(row):
                continue

            # Shift text to column 0 if needed
            if not row[0].strip() and len(row) > 1:
                first_content_idx = -1
                for idx, cell in enumerate(row):
                    if cell.strip():
                        first_content_idx = idx
                        break

                if first_content_idx > 0:
                    val = row[first_content_idx]
                    if not self._is_numeric(val) and not YEAR_REGEX.match(val):
                        row[0] = val
                        row[first_content_idx] = ""

            # Detect hanging headers/data
            has_text = bool(row[0].strip())
            has_data = any(self._is_numeric(cell) for cell in row[1:])

            if has_text and not has_data:
                if prev_text_row:
                    healed_rows.append(prev_text_row)
                prev_text_row = row
                continue

            elif not has_text and has_data:
                if prev_text_row:
                    row[0] = prev_text_row[0]
                    prev_text_row = None
                healed_rows.append(row)
                continue

            else:
                if prev_text_row:
                    healed_rows.append(prev_text_row)
                    prev_text_row = None
                healed_rows.append(row)

        if prev_text_row:
            healed_rows.append(prev_text_row)

        return healed_rows

    def _repair_split_numbers(self, rows: List[List[str]]) -> List[List[str]]:
        """Stitch numbers split across columns (e.g., '33' + ',252' -> '33,252')"""
        repaired_rows = []
        for row in rows:
            new_row = [x for x in row]

            i = 0
            while i < len(new_row) - 1:
                curr = new_row[i].strip()
                next_val = new_row[i + 1].strip()

                # Pattern: "33" + ",252"
                if (
                    curr
                    and next_val
                    and curr[-1].isdigit()
                    and next_val.startswith(",")
                    and len(next_val) > 1
                    and next_val[1].isdigit()
                ):
                    new_row[i] = curr + next_val
                    new_row[i + 1] = ""
                    i += 1

                # Pattern: "33," + "252"
                elif curr and next_val and curr.endswith(",") and next_val[0].isdigit():
                    new_row[i] = curr + next_val
                    new_row[i + 1] = ""
                    i += 1

                i += 1

            repaired_rows.append(new_row)
        return repaired_rows

    def _repair_shifted_currency(self, rows: List[List[str]]) -> List[List[str]]:
        """Fix currency symbol wrongly concatenated to current column"""
        cleaned_rows = []

        # Build regex for any currency symbol
        currency_symbols_escaped = [
            re.escape(s) for s in PREFIX_SYMBOLS | SUFFIX_SYMBOLS if s
        ]
        if currency_symbols_escaped:
            symbol_pattern = f"({'|'.join(currency_symbols_escaped)})"
            pattern = re.compile(f"^(.*?)\\s+({symbol_pattern})$")
        else:
            pattern = re.compile(r"^(.*?)\s+(\$)$")

        for row in rows:
            for i in range(len(row) - 1):
                current_cell = row[i].strip()
                match = pattern.search(current_cell)

                if match:
                    real_value = match.group(1)
                    symbol = match.group(2)
                    row[i] = real_value
                    next_cell = row[i + 1].strip()
                    row[i + 1] = f"{symbol}{next_cell}"

            row = [x.replace("$$", "$").strip() for x in row]
            cleaned_rows.append(row)

        return cleaned_rows

    def _detect_paragraph_masquerading_as_table(self) -> bool:
        """Check if this is actually a paragraph, not a table"""
        if not self.data:
            return False

        if TABLE_OF_CONTENTS_REGEX.search(
            "\n".join(" ".join(row) for row in self.data)
        ):
            return True

        first_col_max_length = max((len(row[0]) for row in self.data if row), default=0)
        if first_col_max_length > PARAGRAPH_THRESHOLD:
            return True

        return False

    def _is_numeric(self, val: str) -> bool:
        """Check if value is numeric"""
        clean = NUMERIC_WITH_SYMBOLS.sub("", val).strip()
        clean = UNIT_REGEX.sub("", clean)
        return bool(NUMERIC_PATTERN.match(clean))

    def _detect_primitive_type(self, sample_cells: List[str]) -> Optional[str]:
        """
        Detect primitive column type from sample data.
        Returns: 'date', 'percentage', 'dollar', 'text', or None
        """
        if not sample_cells:
            return None

        # Count occurrences of each type
        date_count = 0
        percent_count = 0
        dollar_count = 0
        value_count = 0
        text_count = 0

        for cell in sample_cells:
            if not cell:
                continue

            # Check for date (YYYY or MM/DD/YYYY pattern)
            if YEAR_REGEX.search(cell):
                date_count += 1
            # Check for percentage
            elif "%" in cell:
                percent_count += 1
            # Check for currency (dollar or other currency symbols)
            elif any(symbol in cell for symbol in PREFIX_SYMBOLS | SUFFIX_SYMBOLS):
                dollar_count += 1
            # Check if numeric (without currency)
            elif self._is_numeric(cell):
                value_count += 1
            # Otherwise it's text
            else:
                text_count += 1

        total = len(sample_cells)
        if total == 0:
            return None

        # 1. Text Dominance
        if text_count > total * 0.5:
            return "text"

        # 2. Mixed Detection
        has_date = date_count > total * 0.1
        has_percent = percent_count > total * 0.1
        has_numeric = (dollar_count + value_count) > total * 0.1
        
        if sum([has_date, has_percent, has_numeric]) > 1:
            return "mixed"

        # Determine dominant type (>50% threshold)
        if date_count > total * 0.5:
            return "date"
        elif percent_count > total * 0.5:
            return "percentage"
        elif dollar_count > total * 0.5:
            return "dollar"
        elif value_count > total * 0.5:
            return "value"

        # Combined Numeric
        if (dollar_count + value_count) > total * 0.5:
            return "dollar" if dollar_count > value_count else "value"

        return "mixed"

    def _is_percentage_header(self, header_text: str) -> bool:
        if not header_text:
            return False
        return bool(PERCENT_HEADER_REGEX.search(header_text))

    def _normalize_percentage_columns(
        self,
        rows: List[List[str]],
        col_map: Dict[int, Optional[str]],
        col_headers: Dict[int, str],
    ) -> List[List[str]]:
        """
        For columns explicitly labeled as percentage, ensure numeric values carry '%'.
        """
        percent_cols = {
            idx
            for idx, header in col_headers.items()
            if self._is_percentage_header(header) or col_map.get(idx) == "percentage"
        }
        if not percent_cols:
            return rows

        normalized_rows: List[List[str]] = []
        for row in rows:
            new_row = list(row)
            for idx in percent_cols:
                if idx >= len(new_row):
                    continue
                cell = new_row[idx].strip()
                if not cell or cell in {"-", "—", "N/A", "n/a"}:
                    continue
                if "%" in cell:
                    continue
                if self._is_numeric(cell):
                    new_row[idx] = f"{cell}%"
            normalized_rows.append(new_row)

        return normalized_rows

    def get_data(self) -> List[List[str]]:
        """Return extracted table data"""
        return self.data if not self.invalid_table else []

    def get_headers(self) -> Dict[int, str]:
        """Return column headers"""
        return self.col_headers if not self.invalid_table else {}

    def get_types(self) -> Dict[int, Optional[str]]:
        """Return column types"""
        return self.col_map if not self.invalid_table else {}

    def get_years(self) -> Dict[int, int]:
        """Return column years detected from headers, with forward filling."""
        if self.invalid_table:
            return {}

        years_map = {}
        sorted_indices = sorted(self.col_headers.keys())
        last_year = None

        for idx in sorted_indices:
            header = self.col_headers[idx]
            detected_year = None

            if header:
                extracted_years = []
                matches = YEAR_REGEX.findall(header)
                
                for m in matches:
                    # Handle tuple from regex groups
                    groups = m if isinstance(m, tuple) else [m]
                    for g in groups:
                        if g and g.isdigit():
                            y = int(g)
                            # Handle 2-digit years
                            if y < 100:
                                y += 2000 if y < 50 else 1900
                            extracted_years.append(y)
                
                # Filter for valid 4-digit years
                valid_years = [y for y in extracted_years if 1900 <= y <= 2100]
                
                if valid_years:
                    detected_year = max(valid_years)

            if detected_year:
                years_map[idx] = detected_year
                last_year = detected_year
            elif last_year is not None:
                years_map[idx] = last_year

        return years_map

    def get_row_years(self) -> Dict[int, int]:
        """
        Return row years detected from section headers (transposed tables).
        Logic: If a row has a year in the first column and is otherwise empty,
        it sets the year for subsequent rows.
        """
        if self.invalid_table:
            return {}

        row_years = {}
        current_year = None

        for idx, row in enumerate(self.data):
            if not row:
                continue

            # Check for section header: First cell is year, others empty
            first_cell = row[0].strip()
            is_header = False
            
            # Check emptiness of other cells
            other_cells_empty = True
            for cell in row[1:]:
                if cell.strip():
                    other_cells_empty = False
                    break
            
            if other_cells_empty and first_cell:
                # Check if first cell is a year
                matches = YEAR_REGEX.findall(first_cell)
                valid_years_found = []
                for m in matches:
                    groups = m if isinstance(m, tuple) else [m]
                    for g in groups:
                        if g and g.isdigit():
                            y = int(g)
                            # Handle 2-digit years
                            if y < 100:
                                y += 2000 if y < 50 else 1900
                            if 1900 <= y <= 2100:
                                valid_years_found.append(y)
                
                # Only treat as header if EXACTLY one unique year is found
                unique_years = set(valid_years_found)
                if len(unique_years) == 1:
                    current_year = unique_years.pop()
                    is_header = True
            
            if not is_header and current_year is not None:
                row_years[idx] = current_year

        return row_years

    def get_info(self) -> Dict:
        """Return table metadata"""
        caption_year = None
        if self.caption:
            matches = YEAR_REGEX.findall(self.caption)
            years = []
            for m in matches:
                # Handle regex groups from YEAR_REGEX (tuples)
                if isinstance(m, tuple):
                    for g in m:
                        if g:
                            years.append(int(g))
                else:
                    years.append(int(m))
            
            valid_years = sorted(list(set([y for y in years if 1900 <= y <= 2100])))
            if len(valid_years) == 1:
                caption_year = valid_years[0]

        return {
            "caption": self.caption,
            "caption_year": caption_year,
            "currency": self.table_currency,
            "global_multiplier": self.global_multiplier,
            "invalid": self.invalid_table,
            "num_rows": len(self.data),
            "num_cols": len(self.col_headers),
            "column_types": self.col_map if not self.invalid_table else {},
        }

    def to_string(self) -> str:
        """
        Reconstructs the table string from the processed data.
        Uses GenericTable to format it with SEC tags (<S>, <C>) so it can be re-parsed.
        """
        if self.invalid_table or not self.data:
            return ""

        from defs.table_definitions import GenericTable

        # 1. Prepare Headers
        # col_headers is Dict[int, str], we need List[str]
        if not self.col_headers:
             num_cols = len(self.data[0]) if self.data else 0
             headers = [""] * num_cols
        else:
            num_cols = len(self.col_headers)
            headers = [self.col_headers.get(i, "") for i in range(num_cols)]

        # 2. Prepare Data
        data_rows = self.data
        
        # Safety check: ensure data rows have same length as headers
        if data_rows:
            max_data_cols = max(len(r) for r in data_rows)
            if max_data_cols > num_cols:
                headers.extend([""] * (max_data_cols - num_cols))
                num_cols = max_data_cols

        # 3. Calculate Widths
        widths = [0] * num_cols
        for i, h in enumerate(headers):
            widths[i] = max(widths[i], len(h))
        
        for row in data_rows:
            for i, cell in enumerate(row):
                if i < num_cols:
                    widths[i] = max(widths[i], len(cell))
        
        widths = [max(w, 1) for w in widths]

        # 4. Determine Alignments
        alignments = []
        for i in range(num_cols):
            ctype = self.col_map.get(i, "text")
            alignments.append("l" if ctype == "text" else "r")

        # 5. Build
        return GenericTable(
            headers=headers, data_rows=data_rows, widths=widths, 
            alignments=alignments, title=self.caption or ""
        ).build()

def process_table(table_text: str) -> Dict:
    """
    Standalone function to process a table.

    Returns dict with:
    - data: List of data rows
    - headers: Column header mapping
    - info: Metadata (caption, currency, multiplier, etc.)
    """
    processor = SimpleTableProcessor(table_text)

    return {
        "data": processor.get_data(),
        "headers": processor.get_headers(),
        "types": processor.get_types(),
        "years": processor.get_years(),
        "row_years": processor.get_row_years(),
        "info": processor.get_info(),
        "fixed_table": processor.to_string(),
    }
