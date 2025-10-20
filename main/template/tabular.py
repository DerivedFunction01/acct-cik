# Raw table-style headers
table_headers = [
    "Derivatives ({number}) {month} {end_day} {year} {prev_year} ({currency_code} in {money_unit})",
    "Contract/Notional Credit Risk Contract/Notional Credit Risk",
    "Derivative Instruments {year} {prev_year} ({currency_code} in {money_unit})",
]

# Raw tabular line templates (lots of numbers, minimal words)
table_line_templates = [
    "{line_item} {notional} {prev_notional} {amount}",
    "{line_item} {currency_code} {notional} {money_unit} {prev_notional} {money_unit}",
    "{line_item} {notional} {amount} {prev_notional} {amount2}",
    "{line_item} {year} {notional} {prev_year} {prev_notional}",
]

# Total lines (raw table style)
table_totals = [
    "Credit risk before cash collateral {amount} {amount2}",
    "Derivatives designated as hedging instruments {currency_code} {amount} {currency_code} {amount2}",
    "Total derivative assets {currency_code} {amount} {currency_code} {amount2}",
    "Total notional amount {currency_code} {amount} {money_unit} {amount2} {money_unit}",
    "Net derivative positions {year} {amount} {prev_year} {amount2}",
    "Total {line_item} {amount} {amount2}",
]
