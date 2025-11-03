from dataclasses import dataclass
import random
from typing import List
from defs.table_definitions import FinancialStatementTable, GenericTable
from defs.function_definitions import _format_single_notional, _get_correct_rounding


class BalanceSheetTableBuilder(FinancialStatementTable):
    """Builds a simplified two-year comparative balance sheet."""

    def build(self) -> str:
        title = f"Consolidated Balance Sheets\nAs of {self.month} {self.day}, {self.year} and {self.year - 1} {self._get_units()}"
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
        # ------------------------------------------------------------------ #
        # 1. Header & layout
        # ------------------------------------------------------------------ #
        title = f"Consolidated Statements of Income\nFor the Years Ended {self.month} {self.day}, {self.year} and {self.year - 1} {self._get_units()}"
        year1, year2 = self.year, self.year - 1
        headers = ["", str(year1), str(year2)]
        widths = [45, 20, 20]
        alignments = ["l", "r", "r"]
        data_rows: List[List[str]] = []

        # ------------------------------------------------------------------ #
        # 2. Item pools
        # ------------------------------------------------------------------ #
        revenue_items = [
            "Product revenue",
            "Service revenue",
            "Subscription revenue",
            "Licensing revenue",
        ]
        cogs_items = [
            "Cost of product revenue",
            "Cost of service revenue",
            "Cost of subscription revenue",
        ]
        operating_expense_items = [
            "Research and development",
            "Selling, general and administrative",
            "Marketing and sales",
            "Depreciation and amortization",
            "Impairment of goodwill and intangible assets",
            "Restructuring charges",
        ]
        other_income_expense_items = [
            "Interest income",
            "Interest expense",
            "Other income (expense), net",
            "Gain (loss) on sale of investments",
            "Foreign currency exchange gain (loss)",
        ]

        # Randomly pick which line-items appear this year
        sel_revenue = random.sample(
            revenue_items, k=random.randint(1, len(revenue_items))
        )
        sel_cogs = random.sample(cogs_items, k=random.randint(1, len(cogs_items)))
        sel_opex = random.sample(
            operating_expense_items, k=random.randint(2, len(operating_expense_items))
        )
        sel_other = random.sample(
            other_income_expense_items,
            k=random.randint(1, len(other_income_expense_items)),
        )

        # ------------------------------------------------------------------ #
        # 3. High-level numbers (top-down simulation)
        # ------------------------------------------------------------------ #
        total_revenue = random.randint(10_000, 50_000) * self.notional_multiplier

        # Previous year is ±20% of current year
        prev_total_revenue = int(total_revenue * random.uniform(0.8, 1.2))

        # ------------------------------------------------------------------ #
        # 4. Revenue section
        # ------------------------------------------------------------------ #
        data_rows.append(["Revenue:", "", ""])
        total_rev_current = self._generate_and_append_items(
            data_rows, sel_revenue, total_revenue, prev_total_revenue, is_expense=False
        )
        data_rows.append(
            [
                "Total revenue",
                self._format_value(total_rev_current),
                self._format_value(prev_total_revenue),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 5. Cost of Goods Sold
        # ------------------------------------------------------------------ #
        data_rows.append(["Cost of revenue:", "", ""])
        total_cogs = self._generate_and_append_items(
            data_rows,
            sel_cogs,
            int(total_rev_current * random.uniform(0.50, 0.70)),
            int(prev_total_revenue * random.uniform(0.50, 0.70)),
            is_expense=True,
        )
        data_rows.append(
            [
                "Total cost of revenue",
                self._format_value(total_cogs),
                self._format_value(int(total_cogs * random.uniform(0.8, 1.2))),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 6. Gross Profit
        # ------------------------------------------------------------------ #
        gross_profit = total_rev_current - total_cogs
        prev_gross_profit = prev_total_revenue - int(
            total_cogs * random.uniform(0.8, 1.2)
        )
        data_rows.append(
            [
                "Gross profit",
                self._format_value(gross_profit),
                self._format_value(prev_gross_profit),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 7. Operating Expenses
        # ------------------------------------------------------------------ #
        data_rows.append(["Operating expenses:", "", ""])
        total_opex = self._generate_and_append_items(
            data_rows,
            sel_opex,
            int(gross_profit * random.uniform(0.60, 0.80)),
            int(prev_gross_profit * random.uniform(0.60, 0.80)),
            is_expense=True,
        )
        data_rows.append(
            [
                "Total operating expenses",
                self._format_value(total_opex),
                self._format_value(int(total_opex * random.uniform(0.8, 1.2))),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 8. Operating Income
        # ------------------------------------------------------------------ #
        operating_income = gross_profit - total_opex
        prev_operating_income = prev_gross_profit - int(
            total_opex * random.uniform(0.8, 1.2)
        )
        data_rows.append(
            [
                "Operating income",
                self._format_value(operating_income),
                self._format_value(prev_operating_income),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 9. Other Income / (Expense)
        # ------------------------------------------------------------------ #
        data_rows.append(["Other income (expense):", "", ""])
        other_total = self._generate_and_append_items(
            data_rows,
            sel_other,
            operating_income * 0.10,  # base ~10% of operating income
            prev_operating_income * 0.10,
            is_expense=True,
        )
        prev_other_total = int(other_total * random.uniform(0.8, 1.2))
        data_rows.append(
            [
                "Total other income (expense), net",
                self._format_value(other_total),
                self._format_value(prev_other_total),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 10. Income before tax & Tax provision
        # ------------------------------------------------------------------ #
        income_before_tax = operating_income + other_total
        prev_income_before_tax = prev_operating_income + prev_other_total

        tax_rate = random.uniform(0.15, 0.25)
        tax_provision = int(income_before_tax * tax_rate)
        prev_tax_provision = int(prev_income_before_tax * tax_rate)

        data_rows.append(
            [
                "Income before income taxes",
                self._format_value(income_before_tax),
                self._format_value(prev_income_before_tax),
            ]
        )
        data_rows.append(
            [
                "Provision for income taxes",
                self._format_value(tax_provision),
                self._format_value(prev_tax_provision),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 11. Net Income
        # ------------------------------------------------------------------ #
        net_income = income_before_tax - tax_provision
        prev_net_income = prev_income_before_tax - prev_tax_provision
        data_rows.append(
            [
                "Net Income",
                self._format_value(net_income),
                self._format_value(prev_net_income),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 12. Earnings Per Share
        # ------------------------------------------------------------------ #
        basic_shares = random.randint(100, 500) * 1_000_000
        diluted_shares = int(basic_shares * 1.02)

        def _eps(current, prev_shares_factor: float = 1.0):
            cur = current / basic_shares
            prev = current / (basic_shares * prev_shares_factor)
            return cur, prev

        basic_eps, prev_basic_eps = _eps(net_income, random.uniform(0.98, 1.02))
        diluted_eps, prev_diluted_eps = _eps(net_income, random.uniform(0.98, 1.02))

        data_rows.append(["Earnings per share:", "", ""])
        data_rows.append(
            [
                f"  Basic",
                f"{self.currency_symbol}{basic_eps:.2f}",
                f"{self.currency_symbol}{prev_basic_eps:.2f}",
            ]
        )
        data_rows.append(
            [
                f"  Diluted",
                f"{self.currency_symbol}{diluted_eps:.2f}",
                f"{self.currency_symbol}{prev_diluted_eps:.2f}",
            ]
        )
        data_rows.append(["", "", ""])

        # Shares outstanding
        prev_basic_shares = basic_shares * random.uniform(0.98, 1.02)
        prev_diluted_shares = diluted_shares * random.uniform(0.98, 1.02)

        data_rows.append(["Weighted-average shares outstanding (millions):", "", ""])
        data_rows.append(
            [
                f"  Basic",
                f"{basic_shares/1_000_000:.1f}",
                f"{prev_basic_shares/1_000_000:.1f}",
            ]
        )
        data_rows.append(
            [
                f"  Diluted",
                f"{diluted_shares/1_000_000:.1f}",
                f"{prev_diluted_shares/1_000_000:.1f}",
            ]
        )

        # ------------------------------------------------------------------ #
        # 13. Build & return the table
        # ------------------------------------------------------------------ #
        table = GenericTable(
            headers=headers,
            data_rows=data_rows,
            widths=widths,
            alignments=alignments,
            title=title,
        )
        return table.build()

    # ---------------------------------------------------------------------- #
    # Helper – unchanged except for type hints & tiny clean-ups
    # ---------------------------------------------------------------------- #
    def _generate_and_append_items(
        self,
        data_rows: List[List[str]],
        items: List[str],
        total_value: int | float,
        prev_total_value: int | float,
        *,
        is_expense: bool = False,
    ) -> int:
        """Distribute *total_value* across *items* and append rows."""
        if not items:
            return 0

        num = len(items)
        weights = [random.random() for _ in range(num)]
        total_w = sum(weights)
        weights = [w / total_w for w in weights]

        sub_total = 0
        for item, w in zip(items, weights):
            value = int(total_value * w)
            # Occasionally turn an expense into income (or vice-versa)
            if is_expense and random.random() < 0.10:
                value = -value

            prev_value = int(value * random.uniform(0.8, 1.2))
            data_rows.append(
                [f"  {item}", self._format_value(value), self._format_value(prev_value)]
            )
            sub_total += value

        return sub_total


import random
from typing import List


class CashFlowStatementTableBuilder(FinancialStatementTable):
    """Builds a simplified two-year comparative statement of cash flows."""

    def build(self) -> str:
        title = f"Consolidated Statements of Cash Flows\nFor the Years Ended {self.month} {self.day}, {self.year} and {self.year - 1} {self._get_units()}"
        year1, year2 = self.year, self.year - 1
        headers = ["", str(year1), str(year2)]
        widths = [45, 20, 20]
        alignments = ["l", "r", "r"]
        data_rows: List[List[str]] = []

        # ------------------------------------------------------------------ #
        # 1. Item pools
        # ------------------------------------------------------------------ #
        operating_items = [
            "Depreciation and amortization",
            "Stock-based compensation",
            "Deferred income taxes",
            "Gain on sale of assets",
            "Impairment charges",
            "Changes in operating assets and liabilities:",
            "  Accounts receivable",
            "  Inventories",
            "  Prepaid expenses and other assets",
            "  Accounts payable",
            "  Accrued expenses and other liabilities",
            "  Deferred revenue",
        ]

        investing_items = [
            "Capital expenditures",
            "Purchases of marketable securities",
            "Proceeds from sales of marketable securities",
            "Acquisitions, net of cash acquired",
            "Proceeds from sale of property and equipment",
            "Investments in private companies",
        ]

        financing_items = [
            "Proceeds from issuance of common stock",
            "Repurchase of common stock",
            "Proceeds from long-term debt",
            "Repayment of long-term debt",
            "Payment of dividends",
            "Principal payments on finance leases",
        ]

        # Randomly select which items appear
        sel_operating = random.sample(
            operating_items, k=random.randint(4, len(operating_items))
        )
        sel_investing = random.sample(
            investing_items, k=random.randint(2, len(investing_items))
        )
        sel_financing = random.sample(
            financing_items, k=random.randint(2, len(financing_items))
        )

        # ------------------------------------------------------------------ #
        # 2. High-level simulation
        # ------------------------------------------------------------------ #
        net_income = random.randint(1000, 5000) * self.notional_multiplier
        prev_net_income = int(net_income * random.uniform(0.8, 1.2))

        # ------------------------------------------------------------------ #
        # 3. Operating Activities
        # ------------------------------------------------------------------ #
        data_rows.append(["Cash flows from operating activities:", "", ""])

        # Start with net income
        data_rows.append(
            [
                "  Net income",
                self._format_value(net_income),
                self._format_value(prev_net_income),
            ]
        )

        # Add non-cash and working capital items
        op_adjustments = int(net_income * random.uniform(0.3, 0.7))
        prev_op_adjustments = int(prev_net_income * random.uniform(0.3, 0.7))

        total_op_cash = net_income + self._generate_and_append_items(
            data_rows,
            sel_operating,
            op_adjustments,
            prev_op_adjustments,
            is_expense=False,
        )

        # Net cash from operating activities
        prev_total_op_cash = prev_net_income + int(
            op_adjustments * random.uniform(0.8, 1.2)
        )
        data_rows.append(
            [
                "Net cash provided by operating activities",
                self._format_value(total_op_cash),
                self._format_value(prev_total_op_cash),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 4. Investing Activities
        # ------------------------------------------------------------------ #
        data_rows.append(["Cash flows from investing activities:", "", ""])

        inv_base = int(total_op_cash * random.uniform(0.4, 0.8))
        prev_inv_base = int(prev_total_op_cash * random.uniform(0.4, 0.8))

        total_inv_cash = self._generate_and_append_items(
            data_rows, sel_investing, inv_base, prev_inv_base, is_expense=True
        )

        prev_total_inv_cash = int(total_inv_cash * random.uniform(0.8, 1.2))
        data_rows.append(
            [
                "Net cash used in investing activities",
                self._format_value(total_inv_cash),
                self._format_value(prev_total_inv_cash),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 5. Financing Activities
        # ------------------------------------------------------------------ #
        data_rows.append(["Cash flows from financing activities:", "", ""])

        fin_base = int(total_op_cash * random.uniform(0.2, 0.6))
        prev_fin_base = int(prev_total_op_cash * random.uniform(0.2, 0.6))

        total_fin_cash = self._generate_and_append_items(
            data_rows, sel_financing, fin_base, prev_fin_base, is_expense=True
        )

        prev_total_fin_cash = int(total_fin_cash * random.uniform(0.8, 1.2))
        data_rows.append(
            [
                "Net cash provided by (used in) financing activities",
                self._format_value(total_fin_cash),
                self._format_value(prev_total_fin_cash),
            ]
        )
        data_rows.append(["", "", ""])

        # ------------------------------------------------------------------ #
        # 6. Net Change in Cash
        # ------------------------------------------------------------------ #
        net_change = total_op_cash + total_inv_cash + total_fin_cash
        prev_net_change = prev_total_op_cash + prev_total_inv_cash + prev_total_fin_cash

        data_rows.append(
            [
                "Net increase (decrease) in cash, cash equivalents and restricted cash",
                self._format_value(net_change),
                self._format_value(prev_net_change),
            ]
        )
        data_rows.append(["", "", ""])

        # Optional: Beginning / Ending cash (for completeness)
        beginning_cash = random.randint(500, 3000) * self.notional_multiplier
        ending_cash = beginning_cash + net_change
        prev_beginning_cash = int(beginning_cash * random.uniform(0.9, 1.1))
        prev_ending_cash = prev_beginning_cash + prev_net_change

        data_rows.append(
            [
                "Cash, cash equivalents and restricted cash at beginning of period",
                self._format_value(beginning_cash),
                self._format_value(prev_beginning_cash),
            ]
        )
        data_rows.append(
            [
                "Cash, cash equivalents and restricted cash at end of period",
                self._format_value(ending_cash),
                self._format_value(prev_ending_cash),
            ]
        )

        # ------------------------------------------------------------------ #
        # 7. Build Table
        # ------------------------------------------------------------------ #
        table = GenericTable(
            headers=headers,
            data_rows=data_rows,
            widths=widths,
            alignments=alignments,
            title=title,
        )
        return table.build()

    # ---------------------------------------------------------------------- #
    # Reusable helper (same as IncomeStatementTableBuilder)
    # ---------------------------------------------------------------------- #
    def _generate_and_append_items(
        self,
        data_rows: List[List[str]],
        items: List[str],
        total_value: int,
        prev_total_value: int,
        *,
        is_expense: bool = False,
    ) -> int:
        """Distribute total_value across items and append indented rows."""
        if not items:
            return 0

        # Filter out nested items under "Changes in..." if not root
        clean_items = []
        for item in items:
            if item.startswith("  ") and "Changes in operating assets" in " ".join(
                clean_items
            ):
                continue  # Skip sub-items if parent already included
            clean_items.append(item)

        num = len(clean_items)
        weights = [random.random() for _ in range(num)]
        total_w = sum(weights)
        weights = [w / total_w for w in weights]

        sub_total = 0
        for item, w in zip(clean_items, weights):
            value = int(total_value * w)
            if is_expense and random.random() < 0.3:
                value = -value  # Allow inflows in investing/financing

            prev_value = int(value * random.uniform(0.8, 1.2))
            data_rows.append(
                [f"  {item}", self._format_value(value), self._format_value(prev_value)]
            )
            sub_total += value

        return sub_total
