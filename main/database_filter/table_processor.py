import re
from typing import List, Dict, Optional, Tuple
from table_cleanup import extract_table_content
from derivative_regex import SOFT_REGEX, YEAR_REGEX

# --- 1. EXPANDED HEADER DEFINITIONS ---

# Context/Purpose Headers
CONTEXT_HEADERS = re.compile(
    r"purpose|risk|objective|hedged item|comments|description", re.IGNORECASE
)

# Value at Risk (Strong Signal)
VAR_HEADERS = re.compile(r"\bvar\b|value[- ]at[- ]risk", re.IGNORECASE)

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

# Location
LOCATION_HEADERS = re.compile(r"location|sheet|line item", re.IGNORECASE)

# Noise to Ignore
NOISE_HEADERS = re.compile(
    r"strike|exercise|shares|units|count|ratio|rate|maturity|date|weighted",
    re.IGNORECASE,
)

# Context Row Keywords
SECTION_KEYWORDS = re.compile(
    r"designated as|hedging instruments|underlying risk|derivatives not designated|"
    r"cash flow|fair value|net investment|assets|liabilities|equity contracts|warrants|"
    r"embedded|offsetting|trading|non[- ]?trading|held for|financial instruments",
    re.IGNORECASE,
)


class TableToTextConverter:
    def __init__(self, table_text: str):
        self.raw_text = table_text
        self.headers, self.data = extract_table_content(table_text)
        self.flattened_headers = self._flatten_headers()

        # 1. Initial Classification via Headers
        self.col_map = {
            i: self._classify_column(h) for i, h in enumerate(self.flattened_headers)
        }

        # 2. Heuristic Refinement (The "Second Column" Rule)
        self._apply_column_heuristics()

        # 3. Conflict Resolution (Gross vs Net)
        self._resolve_offsetting_conflicts()

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
        if CONTEXT_HEADERS.search(header):
            return "context_text"
        if VAR_HEADERS.search(header):
            return "fair_value"
        if NOTIONAL_HEADERS.search(header):
            return "notional"
        if NET_HEADERS.search(header):
            return "net_fair_value"
        if GROSS_HEADERS.search(header):
            return "gross_fair_value"
        if LEVEL_HEADERS.search(header):
            return "fair_value"
        if VALUE_HEADERS.search(header):
            if ASSET_HEADERS.search(header):
                return "asset_fair_value"
            if LIABILITY_HEADERS.search(header):
                return "liability_fair_value"
            return "fair_value"
        if GAIN_LOSS_HEADERS.search(header):
            return "gain_loss"
        if LOCATION_HEADERS.search(header):
            return "location"
        year_match = YEAR_REGEX.search(header)
        if year_match:
            return f"value_{year_match.group(0)}"
        return None

    def _is_valid_value(self, val: str) -> bool:
        clean = re.sub(r"[(),$€£¥%]", "", val).strip()
        if clean in ["-", "—", "0", "0.0", ""]:
            return False
        return bool(re.match(r"^-?\d+(?:\.\d+)?$", clean))

    def _apply_column_heuristics(self):
        """
        Applies data-driven heuristics to classify ambiguous columns.
        Specific Rule: If Column 2 (Index 1) is unclassified AND contains text (not numbers),
        treat it as a Context/Purpose column.
        """
        # Target Index 1 (Second column)
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

    def process(self) -> List[str]:
        sentences = []
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

            # 1. Scan for Row-Specific Context (Purpose Column)
            row_context_str = ""
            for i, cell_val in enumerate(row[1:], start=1):
                if self.col_map.get(i) == "context_text":
                    clean_text = re.sub(r"\s+", " ", cell_val).strip()
                    if clean_text and len(clean_text) > 2:
                        row_context_str = f" ({clean_text})"

            # 2. Build Full Name
            # "Interest Rate Contracts" + "Swaps" + " (Hedge of Debt)"
            full_instrument_name = (
                f"{' '.join(active_context)} {row_label}{row_context_str}"
            )

            if not SOFT_REGEX.search(full_instrument_name):
                continue

            for i, cell_val in enumerate(row[1:], start=1):
                col_type = self.col_map.get(i)
                # Skip invalid values AND skip the context column we just consumed
                if (
                    not col_type
                    or col_type == "context_text"
                    or not self._is_valid_value(cell_val)
                ):
                    continue

                clean_val = cell_val.replace("$", "").strip()

                if col_type == "notional":
                    sentences.append(
                        f"Tabular-Data: The Company held {full_instrument_name} with a notional amount of {clean_val}."
                    )

                elif "fair_value" in col_type:
                    sentences.append(
                        f"Tabular-Data: The Company held {full_instrument_name} with a fair value of {clean_val}."
                    )

                elif col_type == "gain_loss":
                    sentences.append(
                        f"Tabular-Data: The Company recognized a gain or loss on {full_instrument_name} of {clean_val}."
                    )

                elif col_type.startswith("value_"):
                    year = col_type.split("_")[1]
                    sentences.append(
                        f"Tabular-Data: In {year}, the Company held {full_instrument_name} with a value of {clean_val}."
                    )

        return sentences
