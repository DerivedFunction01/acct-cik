from dataclasses import dataclass
from typing import List
import textwrap
from defs.function_definitions import _format_single_notional


@dataclass
class FinancialStatementTable:
    """Base class for financial statement table builders."""

    year: int
    month: str
    day: int
    currency_symbol: str
    notional_multiplier: int
    prefer_abbreviated: bool
    preferred_negative_format: int

    def _money_unit(self) -> str:
        """Returns the string for the money unit (e.g., 'millions', 'billions')."""
        amount_to_string = {
            1_000_000_000_000: "trillions",
            1_000_000_000: "billions",
            1_000_000: "millions",
            1_000: "thousands",
        }
        return amount_to_string.get(self.notional_multiplier, "millions")

    def _get_units(self) -> str:
        """Returns the formatted unit string for table titles, e.g., '($ in millions)'."""
        if self.prefer_abbreviated:
            return f"({self.currency_symbol} in {self._money_unit()})"
        return ""

    def _format_value(self, value: int) -> str:
        """Formats a numerical value into a string for the table."""
        return _format_single_notional(
            value,
            self.currency_symbol,
            self.prefer_abbreviated,
            True,
            negative_format=self.preferred_negative_format, # type: ignore
        )

    def build(self) -> str:
        """Builds the financial statement table. To be implemented by subclasses."""
        raise NotImplementedError


@dataclass
class GenericTable:
    """
    A generic class for building formatted text-based tables with SEC tags.
    This class is responsible only for the layout and formatting, not data preparation.
    """

    headers: Union[List[str], List[List[str]]]
    data_rows: List[List[str]]
    widths: List[int]
    alignments: List[str]  # 'l' for left, 'r' for right, 'c' for center
    title: str

    def _format_row_with_wrapping(
        self, cells: List[str], widths: List[int], alignments: List[str]
    ) -> List[str]:
        """
        Formats a single logical row into multiple physical lines with text wrapping.
        """
        wrapped_cells = []
        max_lines = 0
        for i, cell_content in enumerate(cells):
            lines = textwrap.wrap(cell_content, width=widths[i], break_long_words=False)
            if not lines:  # Handle empty cells
                lines = [""]
            wrapped_cells.append(lines)
            if len(lines) > max_lines:
                max_lines = len(lines)

        # Pad shorter cells with blank lines to match the tallest cell
        for lines in wrapped_cells:
            while len(lines) < max_lines:
                lines.append("")

        # Construct the physical lines for the row
        output_lines = []
        for i in range(max_lines):
            row_parts = []
            for j, lines in enumerate(wrapped_cells):
                align = alignments[j]
                if align == "l":
                    row_parts.append(lines[i].ljust(widths[j]))
                elif align == "c":
                    row_parts.append(lines[i].center(widths[j]))
                else:  # 'r'
                    row_parts.append(lines[i].rjust(widths[j]))
            output_lines.append("  ".join(row_parts))
        return output_lines

    def build(self) -> str:
        """Builds the final table string with SEC tags."""
        header_lines = []
        # --- NEW: Handle both single-line and multi-line headers ---
        if self.headers and isinstance(self.headers[0], list):
            # It's a list of lists (multi-line header)
            for header_row in self.headers:
                header_lines.extend(self._format_row_with_wrapping(header_row, self.widths, self.alignments))
        else:
            # It's a single list of strings (single-line header)
            header_lines.extend(self._format_row_with_wrapping(self.headers, self.widths, self.alignments))

        separator = "  ".join(['-' * w for w in self.widths])
        sec_tags_line = "<S>".ljust(self.widths[0] + 2) + "".join(["<C>".ljust(w + 2) for w in self.widths[1:]]).rstrip()

        all_rows = header_lines + [separator, sec_tags_line]
        for row_data in self.data_rows:
            all_rows.extend(self._format_row_with_wrapping(row_data, self.widths, self.alignments))

        return f"\n\n<TABLE>\n<CAPTION>\n{self.title}\n" + "\n".join(all_rows) + "\n</TABLE>\n\n"