import re
from typing import List, Dict, Optional, Tuple
from table_cleanup import extract_table_content
from derivative_regex import SOFT_REGEX, TABLE_REGEX, YEAR_REGEX, STRICT_REGEX

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

TABLE_ANCHOR = " T_ "

class TableToTextConverter:
    def __init__(self, table_text: str):
        self.raw_text = table_text

        # 1. Extract & Analyze Caption (New)
        self.caption = self._extract_caption(table_text)
        self.table_default_type = self._analyze_caption_context(self.caption)

        # 2. Extract Data
        self.headers, self.data = extract_table_content(table_text)
        self.flattened_headers = self._flatten_headers()

        # 3. Classify Columns (using caption context)
        self.col_map = {
            i: self._classify_column(h) for i, h in enumerate(self.flattened_headers)
        }

        self._apply_column_heuristics()
        self._resolve_offsetting_conflicts()

    def _extract_caption(self, text: str) -> str:
        """
        Extracts text following the <caption> tag up to the newline.
        Format: <table>\n<caption> My Table Title\n...
        """
        match = re.search(r"<caption>\s*(.*)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def _analyze_caption_context(self, caption: str) -> Optional[str]:
        """
        Determines the default value type for the table based on the caption.
        Useful when headers are just years (e.g. '2023' | '2022').
        """
        if not caption:
            return None

        caption_lower = caption.lower()

        # Check specific types
        if NOTIONAL_HEADERS.search(caption_lower):
            return "notional"
        if VAR_HEADERS.search(caption_lower):
            return "fair_value"  # VaR is treated as FV risk metric
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

        # 1. EXTRACT YEAR FIRST
        year_match = YEAR_REGEX.search(header)
        year_suffix = f"_{year_match.group(0)}" if year_match else ""

        # 2. Identify Type (Header Override)
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

        # 3. Fallback to Caption Context
        # If we found a year but no specific type in the header, look at the caption.
        # e.g. Header="2024", Caption="Notional Amounts" -> Type="notional"
        if not col_type and year_suffix:
            if self.table_default_type:
                col_type = self.table_default_type
            else:
                col_type = "value"  # Generic fallback

        # 4. Combine
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
        # Strip parentheses
        stripped = clean_val.strip("()")
        try:
            num = float(stripped.replace(",", ""))
            # Conditional formatting
            if num == 0:
                return "$0"
            elif num > 1000:
                # Keep whole number with commas, no decimals
                return f"${int(num):,}"
            else:
                # Format with 2 decimals for smaller values
                return f"${num:.2f}"
        except ValueError:
            # If not numeric, assume it's already a currency string
            return clean_val


    def process(self) -> List[str]:
        sentences = []

        # --- PASS 1: SCAN FOR STRONG SIGNALS ---
        # We need to determine if this table is definitively about derivatives
        # before we accept "Soft" matches (like "Natural Gas" or "Options").

        # 1. Check for Notional Columns (Strongest Signal)
        table_has_notional_col = any(
            "notional" in str(v) for v in self.col_map.values()
        ) or (self.table_default_type == "notional")

        table_has_strong_row = False
        candidate_rows = []
        active_context = []

        for row in self.data:
            if not row:
                continue

            if self._is_subheader_row(row):
                active_context = [row[0].strip().rstrip(":")]
                continue

            row_label = row[0].strip()
            if not row_label or "total" in row_label.lower():
                continue

            # Merge values (currency symbols etc)
            row = self._merge_row_values(row)

            # Build Name
            row_context_str = ""
            for i, cell_val in enumerate(row[1:], start=1):
                if self.col_map.get(i) == "context_text":
                    clean_text = re.sub(r"\s+", " ", cell_val).strip()
                    if clean_text and len(clean_text) > 2:
                        row_context_str = f" ({clean_text})"

            full_instrument_name = (
                f"{' '.join(active_context)} {row_label}{row_context_str}"
            )

            # Classification
            row_implies_notional = bool(NOTIONAL_HEADERS.search(full_instrument_name))
            is_strict = bool(STRICT_REGEX.search(full_instrument_name))
            is_table_safe = bool(TABLE_REGEX.search(full_instrument_name))
            is_soft = bool(SOFT_REGEX.search(full_instrument_name))

            # Update Table-Level Signal
            if is_strict or is_table_safe or row_implies_notional:
                table_has_strong_row = True

            # Store for Pass 2
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
        # A table is valid for Soft matches IF:
        # 1. It has at least one Strict/Safe row (e.g. "Swaps")
        # 2. OR it has explicit Notional columns/rows
        table_is_anchored = table_has_strong_row or table_has_notional_col

        # --- PASS 2: GENERATE SENTENCES ---
        for cand in candidate_rows:
            # FILTER LOGIC:
            # 1. Strong matches are always kept.
            # 2. Soft matches are kept ONLY if the table is anchored.
            if cand["is_strong"]:
                pass  # Keep
            elif cand["is_soft"] and table_is_anchored:
                pass  # Keep
            else:
                continue  # Discard (Noise or unanchored soft match)

            # Extract Values
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
                # Strip the clean_val of parenthesis and attempt to convert it to a number. If it fails, it has a currency symbol
                value = self.normalize_value(clean_val)
                # Generate Sentence
                if "notional" in base_type or row_implies_notional:
                    sentences.append(
                        f"{TABLE_ANCHOR} {year_str}The Company held {full_instrument_name} with a notional amount of {value}."
                    )
                elif "fair_value" in base_type or "value" == base_type:
                    sentences.append(
                        f"{TABLE_ANCHOR} {year_str}The Company held {full_instrument_name} with a fair value of {value}."
                    )

        return sentences
