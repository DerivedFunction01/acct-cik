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
        year1, year2 = self.year, self.year - 1
        headers = ["", str(year1), str(year2)]
        widths = [45, 20, 20]
        alignments = ["l", "r", "r"]
        data_rows = []
        ### **Current Assets**
        
        current_asset_items = [
            "Cash and cash equivalents",
            "Restricted cash",
            "Marketable securities",
            "Accounts receivable, gross",
            "Allowance for doubtful accounts",
            "Accounts receivable, net",
            "Inventories",
            "Prepaid expenses",
            "Other current assets",
            "Derivative assets, current",
            "Income taxes receivable",
            "Deferred tax assets, current"
        ]
        

        ### **Non-Current Assets**
        
        non_current_asset_items = [
            "Property, plant, and equipment, gross",
            "Accumulated depreciation",
            "Property, plant, and equipment, net",
            "Operating lease right-of-use assets",
            "Goodwill",
            "Intangible assets, gross",
            "Accumulated amortization",
            "Intangible assets, net",
            "Long-term investments",
            "Equity method investments",
            "Deferred tax assets, non-current",
            "Other non-current assets"
        ]
        

        

        ### **Current Liabilities**
        
        current_liability_items = [
            "Accounts payable",
            "Accrued expenses",
            "Accrued compensation and benefits",
            "Short-term debt",
            "Current portion of long-term debt",
            "Operating lease liabilities, current",
            "Finance lease liabilities, current",
            "Deferred revenue, current",
            "Income taxes payable",
            "Derivative liabilities, current",
            "Other current liabilities"
        ]
        

        

        ### **Non-Current Liabilities**
        
        non_current_liability_items = [
            "Long-term debt",
            "Operating lease liabilities, non-current",
            "Finance lease liabilities, non-current",
            "Pension and other postretirement benefit obligations",
            "Deferred tax liabilities, non-current",
            "Asset retirement obligations",
            "Contingent liabilities",
            "Other non-current liabilities"
        ]
        

        

        ### **Equity**
        
        equity_items = [
            "Common stock",
            "Preferred stock",
            "Additional paid-in capital",
            "Retained earnings (accumulated deficit)",
            "Accumulated other comprehensive income (loss)",
            "Treasury stock",
            "Noncontrolling interests",
            "Total stockholders' equity"
        ]

        # Randomly select a subset of items for each category
        selected_current_assets = random.sample(current_asset_items, k=random.randint(2, len(current_asset_items)))
        selected_non_current_assets = random.sample(non_current_asset_items, k=random.randint(2, len(non_current_asset_items)))
        selected_current_liabilities = random.sample(current_liability_items, k=random.randint(2, len(current_liability_items)))
        selected_non_current_liabilities = random.sample(non_current_liability_items, k=random.randint(1, len(non_current_liability_items)))
        selected_equity_items = random.sample(equity_items, k=random.randint(2, len(equity_items)))

        #  Data Simulation 
        total_assets = random.randint(5000, 20000) * self.notional_multiplier
        total_liabilities = int(total_assets * random.uniform(0.4, 0.7))
        total_equity = total_assets - total_liabilities

        prev_total_assets = int(total_assets * random.uniform(0.8, 1.1))
        prev_total_liabilities = int(total_liabilities * random.uniform(0.8, 1.1))
        prev_total_equity = prev_total_assets - prev_total_liabilities

        #  Build Table Rows 
        data_rows.append(["Assets", "", ""])
        data_rows.append(["Current assets:", "", ""])
        current_assets_total = self._generate_and_append_items(data_rows, selected_current_assets, total_assets * 0.4, prev_total_assets * 0.4)
        data_rows.append(["Total current assets", self._format_value(current_assets_total), self._format_value(int(current_assets_total * random.uniform(0.9, 1.1)))])
        data_rows.append(["", "", ""])

        data_rows.append(["Non-current assets:", "", ""])
        non_current_assets_total = self._generate_and_append_items(data_rows, selected_non_current_assets, total_assets * 0.6, prev_total_assets * 0.6)
        data_rows.append(["Total non-current assets", self._format_value(non_current_assets_total), self._format_value(int(non_current_assets_total * random.uniform(0.9, 1.1)))])
        data_rows.append(["", "", ""])

        data_rows.append(["Total Assets", self._format_value(total_assets), self._format_value(prev_total_assets)])
        data_rows.append(["", "", ""])

        data_rows.append(["Liabilities and Equity", "", ""])
        data_rows.append(["Current liabilities:", "", ""])
        current_liabilities_total = self._generate_and_append_items(data_rows, selected_current_liabilities, total_liabilities * 0.5, prev_total_liabilities * 0.5)
        data_rows.append(["Total current liabilities", self._format_value(current_liabilities_total), self._format_value(int(current_liabilities_total * random.uniform(0.9, 1.1)))])
        data_rows.append(["", "", ""])

        data_rows.append(["Non-current liabilities:", "", ""])
        non_current_liabilities_total = self._generate_and_append_items(data_rows, selected_non_current_liabilities, total_liabilities * 0.5, prev_total_liabilities * 0.5)
        data_rows.append(["Total non-current liabilities", self._format_value(non_current_liabilities_total), self._format_value(int(non_current_liabilities_total * random.uniform(0.9, 1.1)))])
        data_rows.append(["", "", ""])

        data_rows.append(["Total Liabilities", self._format_value(total_liabilities), self._format_value(prev_total_liabilities)])
        data_rows.append(["", "", ""])

        data_rows.append(["Stockholders' equity:", "", ""])
        self._generate_and_append_items(data_rows, selected_equity_items, total_equity, prev_total_equity)
        data_rows.append(["Total stockholders' equity", self._format_value(total_equity), self._format_value(prev_total_equity)])
        data_rows.append(["", "", ""])

        data_rows.append(["Total Liabilities and Equity", self._format_value(total_assets), self._format_value(prev_total_assets)])

        table = GenericTable(
            headers=headers,
            data_rows=data_rows,
            widths=widths,
            alignments=alignments,
            title=title,
        )
        return table.build()

    def _generate_and_append_items(self, data_rows, items, total_value, prev_total_value):
        """Generates random values for a list of items and appends them to data_rows."""
        num_items = len(items)
        # Generate random weights that sum to 1
        weights = [random.random() for _ in range(num_items)]
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        sub_total = 0
        for i, item in enumerate(items):
            value = int(total_value * weights[i])
            prev_value = int(prev_total_value * weights[i] * random.uniform(0.8, 1.2))
            data_rows.append([f"  {item}", self._format_value(value), self._format_value(prev_value)])
            sub_total += value
        
        return sub_total


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
