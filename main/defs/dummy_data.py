from typing import List, Literal

# TODO: This entire file consists of "dummy data" lists used for the template-based
# generation system. As part of the migration to a generative model, these static
# lists will be deprecated. The new model will learn to generate these terms
# contextually rather than selecting them from a predefined list.

# =============================================================================
# DUMMY DATA AND ARCHETYPES
# This file contains the lists of dummy data and the ScenarioArchetype class
# used for generating random scenarios.
# =============================================================================

DUMMY_IR_INSTRUMENT_TYPES = [
    "interest rate swap",
    "pay-fixed interest rate swap",
    "interest rate cap",
    "interest rate collar",
]
DUMMY_FX_INSTRUMENT_TYPES = [
    "foreign currency forward",
    "foreign exchange contract",
    "currency option",
    "FX collar",
]
DUMMY_CP_INSTRUMENT_TYPES = [
    "commodity swap",
    "natural gas futures",
    "crude oil option",
]
DUMMY_EQ_INSTRUMENT_TYPES = ["equity swap", "equity forward"]
DUMMY_DEBT_TYPES = [
    "variable-rate credit facility",
    "senior notes",
    "term loan",
    "revolving credit agreement",
]
DUMMY_COMMODITY_TYPES = ["Natural Gas", "Crude Oil", "Aluminum", "Diesel Fuel"]
DUMMY_BENCHMARK_RATES = ["SOFR", "LIBOR", "EURIBOR"]
DUMMY_EQUITY_UNDERLYINGS = ["S&P 500 Index", "{company_name} Common Stock"]
DUMMY_EQUITY_TYPES: List[Literal["market_index", "own_stock", "third_party_stock"]] = [
    "market_index",
    "own_stock",
    "third_party_stock",
]
DUMMY_EQUITY_REASONS = [
    "stock-based compensation",
    "strategic investment",
    "market risk management",
]
DUMMY_GENERIC_INSTRUMENT_TYPES = [
    "derivative contracts",
    "hedging instruments",
    "financial instruments",
]

DUMMY_EFFECTIVENESS_METHODS = [
    "regression analysis",
    "the dollar-offset method",
    "quantitative analysis",
    "statistical methods",
]
DUMMY_EFFECTIVENESS_FREQUENCIES = [
    "quarterly",
    "annually",
    "at inception and on an ongoing basis",
]
DUMMY_ACCOUNTING_DESCRIPTIONS = {
    "cash_flow": "For derivatives designated as cash flow hedges, the effective portion of the change in fair value is recorded in other comprehensive income (OCI).",
    "fair_value": "For derivatives designated as fair value hedges, changes in fair value are recognized in earnings, offsetting the change in the hedged item's fair value.",
    "net_investment": "For net investment hedges, foreign currency translation gains or losses are recorded in other comprehensive income (OCI) to offset the translation of the net investment.",
}