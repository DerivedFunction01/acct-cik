# Raw table-style headers
table_headers = [
    "Derivatives ({number}) {month} {end_day} {year} {prev_year} ({currency_code} in {money_unit})",
    "Derivative Instruments {year} {prev_year} (Currency) ({currency_code} in {money_unit})",
    "Contract/Notional Credit Risk Contract/Notional Credit Risk {year} {prev_year}",
    "Derivative Instruments {year} {prev_year} ({currency_code} in {money_unit})",
    "Fair values recorded in Accumulated Other Comprehensive Income (Loss) ({currency_code} in {money_unit})",
    "Derivatives designated as hedging instruments {year} {prev_year} ({currency_code} in {money_unit})",
    "Derivatives not designated as hedging instruments {year} {prev_year} ({currency_code} in {money_unit})",
    "Realized and unrealized derivative gains and losses  {year} {prev_year} ({currency_code} in {money_unit})",
    "Fair value of derivatives {year} {prev_year} ({currency_code} in {money_unit})",
    "Derivative Liabilties {year} {prev_year} ({currency_code} in {money_unit})",
]

# Raw tabular line templates (lots of numbers, minimal words, only notional, prev_notiona, amout, and amount2)
table_line_templates = [
    "{line_item} {notional} ({prev_notional}) {amount}",
    "{line_item} {notional} {amount} {prev_notional} ({amount2})",
    "{line_item} {currency_code} ({notional}) {money_unit} {prev_notional} {money_unit}",
    "{line_item} {notional} {amount} {prev_notional} {amount2}",
    "{line_item} {year} {currency_code} {notional} {prev_year} {currency_code} {prev_notional}",
    "{line_item} {amount} ({amount2})",
    "{line_item} {notional} {prev_notional} ({amount})",
    "{line_item} ({notional}) {amount} {prev_notional} ({amount2})",
    "{line_item} {currency_code} ({notional}) {money_unit} {prev_notional} {money_unit}",
    "{line_item} ({notional}) {amount} {prev_notional} {amount2}",
    "{line_item} {year} {currency_code} {notional} {prev_year} {currency_code} ({prev_notional})",
    "{line_item} ({amount}) {amount2}",
    "{line_item} {notional} {prev_notional}",
    "{line_item} {currency_code} ({amount})",
    "{line_item} {currency_code} {notional}",
    "{line_item} {currency_code} {amount} {currency_code} ({amount2})",
]

# Headers for non-derivative tables
noise_table_headers = [
    "Consolidated Balance Sheets ({currency_code} in {money_unit})",
    "Statement of Stockholders' Equity {year} and {prev_year}",
    "Schedule of Capital Expenditures",
]

# Total lines (raw table style)
table_totals = [
    "Total derivative assets {currency_code} {amount} {currency_code} {amount2}",
    "Derivatives designated as hedging instruments {currency_code} {amount} {currency_code} {amount2}",
    "Credit risk before cash collateral {amount} {amount2}",
    "Derivatives designated as hedging instruments {currency_code} {amount} {currency_code} {amount2}",
    "Total derivative assets {currency_code} {amount} {currency_code} {amount2}",
    "Total notional amount {currency_code} {amount} {money_unit} {amount2} {money_unit}",
    "Net derivative positions {year} {amount} {prev_year} {amount2}",
    "Total {line_item} {amount} {amount2}",
]

# Total lines for non-derivative tables
noise_table_totals = [
    "Total Assets {currency_code} {amount} {money_unit} {amount2} {money_unit}",
    "Total Liabilities and Equity {currency_code} {amount} {money_unit} {amount2} {money_unit}",
    "Total {line_item} {amount} {amount2}",
]
