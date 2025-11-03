from dataclasses import dataclass
import random
from defs.table_definitions import GenericTable
from defs.function_definitions import _format_single_notional


@dataclass
class FinancialStatementTable:
    """Base class for financial statement table builders."""

    year: int
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


class BalanceSheetTableBuilder(FinancialStatementTable):
    """Builds a simplified two-year comparative balance sheet."""

    def build(self) -> str:
        title = f"Consolidated Balance Sheets {self._get_units()}"
        headers = ["", str(self.year), str(self.year - 1)]
        widths = [45, 20, 20]
        alignments = ["l", "r", "r"]
        data_rows = []

        # Simulate some data
        assets = random.randint(5000, 20000) * self.notional_multiplier
        liabilities = int(assets * random.uniform(0.4, 0.7))
        equity = assets - liabilities

        prev_assets = int(assets * random.uniform(0.8, 1.1))
        prev_liabilities = int(liabilities * random.uniform(0.8, 1.1))
        prev_equity = prev_assets - prev_liabilities

        data_rows.append(["Assets", "", ""])
        data_rows.append(
            [
                "  Current Assets",
                self._format_value(int(assets * 0.4)),
                self._format_value(int(prev_assets * 0.4)),
            ]
        )
        data_rows.append(
            [
                "  Non-current Assets",
                self._format_value(int(assets * 0.6)),
                self._format_value(int(prev_assets * 0.6)),
            ]
        )
        data_rows.append(
            [
                "Total Assets",
                self._format_value(assets),
                self._format_value(prev_assets),
            ]
        )
        data_rows.append(["", "", ""])  # Spacer
        data_rows.append(["Liabilities and Equity", "", ""])
        data_rows.append(
            [
                "  Current Liabilities",
                self._format_value(int(liabilities * 0.5)),
                self._format_value(int(prev_liabilities * 0.5)),
            ]
        )
        data_rows.append(
            [
                "  Non-current Liabilities",
                self._format_value(int(liabilities * 0.5)),
                self._format_value(int(prev_liabilities * 0.5)),
            ]
        )
        data_rows.append(
            [
                "Total Liabilities",
                self._format_value(liabilities),
                self._format_value(prev_liabilities),
            ]
        )
        data_rows.append(
            [
                "Total Stockholders' Equity",
                self._format_value(equity),
                self._format_value(prev_equity),
            ]
        )
        data_rows.append(
            [
                "Total Liabilities and Equity",
                self._format_value(assets),
                self._format_value(prev_assets),
            ]
        )

        table = GenericTable(
            headers=headers,
            data_rows=data_rows,
            widths=widths,
            alignments=alignments,
            title=title,
        )
        return table.build()


class IncomeStatementTableBuilder(FinancialStatementTable):
    """Builds a simplified two-year comparative income statement."""

    def build(self) -> str:
        title = f"Consolidated Statements of Income {self._get_units()}"
        headers = [
            "For the year ended December 31,",
            str(self.year),
            str(self.year - 1),
        ]
        widths = [45, 20, 20]
        alignments = ["l", "r", "r"]
        data_rows = []

        # Simulate data
        revenue = random.randint(10000, 50000) * self.notional_multiplier
        cogs = int(revenue * random.uniform(0.5, 0.7))
        gross_profit = revenue - cogs
        operating_expenses = int(gross_profit * random.uniform(0.6, 0.8))
        operating_income = gross_profit - operating_expenses
        net_income = int(operating_income * random.uniform(0.7, 0.9))

        prev_revenue = int(revenue * random.uniform(0.9, 1.1))
        prev_cogs = int(prev_revenue * random.uniform(0.5, 0.7))
        prev_gross_profit = prev_revenue - prev_cogs
        prev_operating_expenses = int(prev_gross_profit * random.uniform(0.6, 0.8))
        prev_operating_income = prev_gross_profit - prev_operating_expenses
        prev_net_income = int(prev_operating_income * random.uniform(0.7, 0.9))

        data_rows.append(
            ["Revenue", self._format_value(revenue), self._format_value(prev_revenue)]
        )
        data_rows.append(
            [
                "Cost of Goods Sold",
                self._format_value(cogs),
                self._format_value(prev_cogs),
            ]
        )
        data_rows.append(
            [
                "Gross Profit",
                self._format_value(gross_profit),
                self._format_value(prev_gross_profit),
            ]
        )
        data_rows.append(
            [
                "Operating Expenses",
                self._format_value(operating_expenses),
                self._format_value(prev_operating_expenses),
            ]
        )
        data_rows.append(
            [
                "Operating Income",
                self._format_value(operating_income),
                self._format_value(prev_operating_income),
            ]
        )
        data_rows.append(
            [
                "Net Income",
                self._format_value(net_income),
                self._format_value(prev_net_income),
            ]
        )

        table = GenericTable(
            headers=headers,
            data_rows=data_rows,
            widths=widths,
            alignments=alignments,
            title=title,
        )
        return table.build()


class CashFlowStatementTableBuilder(FinancialStatementTable):
    """Builds a simplified two-year comparative statement of cash flows."""

    def build(self) -> str:
        title = f"Consolidated Statements of Cash Flows {self._get_units()}"
        headers = [
            "For the year ended December 31,",
            str(self.year),
            str(self.year - 1),
        ]
        widths = [45, 20, 20]
        alignments = ["l", "r", "r"]
        data_rows = []

        # Simulate data
        net_income = random.randint(1000, 5000) * self.notional_multiplier
        depreciation = int(net_income * random.uniform(0.2, 0.5))
        op_cash_flow = (
            net_income + depreciation + int(net_income * random.uniform(-0.1, 0.1))
        )
        inv_cash_flow = -int(op_cash_flow * random.uniform(0.5, 0.9))
        fin_cash_flow = (
            op_cash_flow + inv_cash_flow + int(op_cash_flow * random.uniform(-0.1, 0.1))
        )
        net_change = op_cash_flow + inv_cash_flow + fin_cash_flow

        prev_net_income = int(net_income * random.uniform(0.9, 1.1))
        prev_depreciation = int(depreciation * random.uniform(0.9, 1.1))
        prev_op_cash_flow = (
            prev_net_income
            + prev_depreciation
            + int(prev_net_income * random.uniform(-0.1, 0.1))
        )
        prev_inv_cash_flow = -int(prev_op_cash_flow * random.uniform(0.5, 0.9))
        prev_fin_cash_flow = (
            prev_op_cash_flow
            + prev_inv_cash_flow
            + int(prev_op_cash_flow * random.uniform(-0.1, 0.1))
        )
        prev_net_change = prev_op_cash_flow + prev_inv_cash_flow + prev_fin_cash_flow

        data_rows.append(["Cash flows from operating activities:", "", ""])
        data_rows.append(
            [
                "  Net income",
                self._format_value(net_income),
                self._format_value(prev_net_income),
            ]
        )
        data_rows.append(
            [
                "  Depreciation and amortization",
                self._format_value(depreciation),
                self._format_value(prev_depreciation),
            ]
        )
        data_rows.append(
            [
                "Net cash provided by operating activities",
                self._format_value(op_cash_flow),
                self._format_value(prev_op_cash_flow),
            ]
        )
        data_rows.append(["", "", ""])  # Spacer
        data_rows.append(["Cash flows from investing activities:", "", ""])
        data_rows.append(
            [
                "  Capital expenditures",
                self._format_value(inv_cash_flow),
                self._format_value(prev_inv_cash_flow),
            ]
        )
        data_rows.append(
            [
                "Net cash used in investing activities",
                self._format_value(inv_cash_flow),
                self._format_value(prev_inv_cash_flow),
            ]
        )
        data_rows.append(["", "", ""])  # Spacer
        data_rows.append(["Cash flows from financing activities:", "", ""])
        data_rows.append(
            [
                "  Net borrowings (repayments) of debt",
                self._format_value(fin_cash_flow),
                self._format_value(prev_fin_cash_flow),
            ]
        )
        data_rows.append(
            [
                "Net cash provided by (used in) financing activities",
                self._format_value(fin_cash_flow),
                self._format_value(prev_fin_cash_flow),
            ]
        )
        data_rows.append(["", "", ""])  # Spacer
        data_rows.append(
            [
                "Net increase (decrease) in cash",
                self._format_value(net_change),
                self._format_value(prev_net_change),
            ]
        )

        table = GenericTable(
            headers=headers,
            data_rows=data_rows,
            widths=widths,
            alignments=alignments,
            title=title,
        )
        return table.build()
