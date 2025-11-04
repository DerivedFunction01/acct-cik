import random
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, field

from defs.instrument_definitions import HedgedItem, NotionalInstrument
from defs.common_data import balance_sheet_locations
from defs.function_definitions import _get_company_reference, _cleanup_sentence, _format_single_notional
from defs.table_definitions import GenericTable
from defs.common_data import (
    risk_exposure_terms,
    gain_loss_phrases,
    financial_outcome_verbs,
    balance_sheet_locations,
    comparison_phrases,
    geo_locations,
)


@dataclass
class Currency:
    code: str
    full_name: str
    symbol: str
    adjective: str
    location: str
    symbol_first: bool = True # Default to symbol before the number (e.g., $100)


major_currencies = [
    Currency("USD", "U.S. Dollar", "$", "U.S.", "United States"),
    Currency("EUR", "Euro", "€", "European", "Europe"),
    Currency("GBP", "British Pound", "£", "British", "U.K."),
    Currency("JPY", "Japanese Yen", "¥", "Japanese", "Japan"),
    Currency("CAD", "Canadian Dollar", "C$", "Canadian", "Canada"),
    Currency("AUD", "Australian Dollar", "A$", "Australian", "Australia"),
    Currency("CHF", "Swiss Franc", "CHF", "Swiss", "Switzerland"),
    Currency("CNY", "Chinese Yuan", "¥", "Chinese", "China"),
]

european_currencies = [
    Currency("NOK", "Norwegian Krone", "kr", "Norwegian", "Norway", symbol_first=False),
    Currency("SEK", "Swedish Krona", "kr", "Swedish", "Sweden", symbol_first=False),
    Currency("DKK", "Danish Krone", "kr", "Danish", "Denmark", symbol_first=False),
    Currency("PLN", "Polish Zloty", "zł", "Polish", "Poland", symbol_first=False),
    Currency("HUF", "Hungarian Forint", "Ft", "Hungarian", "Hungary", symbol_first=False),
    Currency("CZK", "Czech Koruna", "Kč", "Czech", "Czech Republic", symbol_first=False),
    Currency("TRY", "Turkish Lira", "₺", "Turkish", "Turkey", symbol_first=False),
    Currency("RUB", "Russian Ruble", "₽", "Russian", "Russia", symbol_first=False),
    Currency("BGN", "Bulgarian Lev", "лв", "Bulgarian", "Bulgaria", symbol_first=False),
    Currency("RON", "Romanian Leu", "lei", "Romanian", "Romania", symbol_first=False),
]

asian_currencies = [
    Currency("INR", "Indian Rupee", "₹", "Indian", "India"),
    Currency("KRW", "South Korean Won", "₩", "South Korean", "South Korea"),
    Currency("SGD", "Singapore Dollar", "S$", "Singaporean", "Singapore"),
    Currency("HKD", "Hong Kong Dollar", "HK$", "Hong Kong", "Hong Kong"),
    Currency("THB", "Thai Baht", "฿", "Thai", "Thailand", symbol_first=False),
    Currency("MYR", "Malaysian Ringgit", "RM", "Malaysian", "Malaysia"),
]

americas_currencies = [
    Currency("MXN", "Mexican Peso", "Mex$", "Mexican", "Mexico"),
    Currency("BRL", "Brazilian Real", "R$", "Brazilian", "Brazil", symbol_first=False),
    Currency("ARS", "Argentine Peso", "ARS$", "Argentine", "Argentina"),
    Currency("CLP", "Chilean Peso", "CLP$", "Chilean", "Chile"),
    Currency("COP", "Colombian Peso", "COL$", "Colombian", "Colombia"),
]

other_currencies = [
    Currency("NZD", "New Zealand Dollar", "NZ$", "New Zealand", "Oceania", symbol_first=True),
    Currency("ZAR", "South African Rand", "R", "South African", "south Africa", symbol_first=True),
    Currency("AED", "UAE Dirham", "د.إ", "Emirati", "United Arab Emirates", symbol_first=False),
    Currency("SAR", "Saudi Riyal", "ر.س", "Saudi", "Saudi Arabia", symbol_first=False),
]


all_currencies = (
    major_currencies
    + european_currencies
    + asian_currencies
    + americas_currencies
    + other_currencies
)
@dataclass
class CurrencyExposure(Currency):
    """Represents a specific currency exposure with its amount.

    Args:
        (Inherited from Currency): code, full_name, symbol, adjective, location
        amount: int - The notional amount of the exposure in that currency.
    """
    amount: int = 0
    def to_dict(self) -> Dict:
        """Serializes the currency exposure to a dictionary, including inherited fields."""
        # Get the dictionary from the parent class
        data = super().__dict__
        data["amount"] = self.amount
        return data


@dataclass
class ForeignCurrencyHedgedItem(HedgedItem):
    """Represents foreign currency exposure being hedged (for FX derivatives)."""

    exposures: List[CurrencyExposure] = field(default_factory=list)

    def to_dict(self) -> Optional[Dict]:
        """Serializes the hedged item, including its currency exposures."""
        data = super().to_dict()
        if data:
            data["exposures"] = [exp.to_dict() for exp in self.exposures]
        return data

@dataclass
class FXInstrument(NotionalInstrument[ForeignCurrencyHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="FX", **kwargs)

@dataclass
class FXContextSentence:
    """Generates contextual sentences about foreign currency exposure without mentioning derivatives."""

    company_name: str
    reporting_year: int
    reporting_month: str
    reporting_day: int
    hedged_item: Optional[Union[ForeignCurrencyHedgedItem, List[ForeignCurrencyHedgedItem]]]
    prefer_abbreviated: bool
    currency_symbol: str
    currency_code: str
    notional_multiplier: int = 1_000_000  # Default to millions

    def build(self) -> str:
        """Builds a multi-sentence paragraph about the company's FX exposures."""
        # If a list of items is provided, there's a chance to build a table.
        if isinstance(self.hedged_item, list) and self.hedged_item and random.random() < 0.4:
            table_str = self._build_fx_exposure_table()
            if table_str:
                # Prepend an introductory sentence to the table.
                intro_sentence = self._build_fx_sentence(None) # Generate a generic intro
                return f"{intro_sentence}{table_str}"
            # Fall through to generate a normal sentence if table building fails

        # Fallback to existing sentence generation.
        if isinstance(self.hedged_item, list):
            # If it's a list but we're not building a table, just describe the first item.
            if not self.hedged_item: return ""
            item_to_describe = self.hedged_item[0]
        else:
            item_to_describe = self.hedged_item

        return self._build_fx_sentence(item_to_describe)

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
        return f"({self.currency_symbol} in {self._money_unit()})" if self.prefer_abbreviated else ""

    def _build_fx_exposure_table(self) -> str:
        """Builds a text-based table summarizing foreign currency exposures."""
        if not isinstance(self.hedged_item, list) or not self.hedged_item:
            return ""

        all_tables_str = []
        available_table_types = ["exposure_summary", "translation_impact", "transaction_gains", "exchange_rates"]
        num_tables = random.randint(1, min(len(available_table_types), 3)) # Generate 1, 2, or 3 tables

        # Ensure we don't pick the same table type twice
        selected_table_types = random.sample(available_table_types, num_tables)

        for table_type in selected_table_types:
            data_rows = []
            # --- 1. Exposure Summary (existing logic) ---
            if table_type == "exposure_summary":
                title = f"Summary of Foreign Currency Exposure as of {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
                headers = ["Currency", "Exposure Amount"]
                widths = [30, 25]
                alignments = ['l', 'r']
                # Aggregate all exposures from all items
                all_exposures: Dict[str, CurrencyExposure] = {}
                for item in self.hedged_item:
                    for exp in item.exposures:
                        if exp.code in all_exposures:
                            all_exposures[exp.code].amount += exp.amount
                        else:
                            # Create a copy to avoid modifying the original object
                            all_exposures[exp.code] = CurrencyExposure(**exp.__dict__)

                for code, exposure in all_exposures.items():
                    amount_str = _format_single_notional(
                        exposure.amount, exposure.symbol, self.prefer_abbreviated, True
                    )
                    data_rows.append([exposure.full_name, amount_str])

            # --- 2. Translation Impact ---
            elif table_type == "translation_impact":
                title = f"Impact of Foreign Currency Translation on Net Revenues For the Year Ended {self.reporting_month} {self.reporting_day}, {self.reporting_year} {self._get_units()}"
                headers = ["Currency", "Change in Exchange Rate (%)", "Impact on Net Revenues"]
                widths = [25, 25, 25]
                alignments = ['l', 'r', 'r']
                unique_exposures = list({exp.code: exp for item in self.hedged_item for exp in item.exposures}.values())
                for exp in unique_exposures:
                    change_pct = f"{random.uniform(-15.0, 15.0):.1f}%"
                    impact_amount = random.randint(-50, 50) * 1_000_000
                    impact_str = _format_single_notional(impact_amount, self.currency_symbol, self.prefer_abbreviated, True, negative_format=0)
                    data_rows.append([exp.full_name, change_pct, impact_str])

            # --- 3. Transaction Gains/Losses ---
            elif table_type == "transaction_gains":
                year1 = self.reporting_year
                year2 = self.reporting_year - 1
                title = f"Foreign Currency Transaction Gains (Losses) For the Years Ended {self.reporting_month} {self.reporting_day} {self._get_units()}"
                headers = ["Currency", f"Gains (Losses) {year1}", f"Gains (Losses) {year2}"]
                widths = [25, 25, 25]
                alignments = ['l', 'r', 'r']
                unique_exposures = list({exp.code: exp for item in self.hedged_item for exp in item.exposures}.values())
                for exp in unique_exposures:
                    gain_loss1 = random.randint(-20, 20) * 1_000_000
                    gain_loss2 = random.randint(-20, 20) * 1_000_000
                    gain_loss1_str = _format_single_notional(gain_loss1, self.currency_symbol, self.prefer_abbreviated, True, negative_format=0)
                    gain_loss2_str = _format_single_notional(gain_loss2, self.currency_symbol, self.prefer_abbreviated, True, negative_format=0)
                    data_rows.append([exp.full_name, gain_loss1_str, gain_loss2_str])

            # --- 4. Exchange Rates ---
            else: # exchange_rates
                title = f"Key Exchange Rates (vs. {self.currency_code}) as of {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
                headers = ["Currency", f"Average Rate {self.reporting_year}", f"Period-End Rate {self.reporting_year}"]
                widths = [25, 25, 25]
                alignments = ['l', 'r', 'r']
                unique_exposures = list({exp.code: exp for item in self.hedged_item for exp in item.exposures}.values())
                for exp in unique_exposures:
                    # Simulate some plausible exchange rates. This is highly simplified.
                    base_rate = random.uniform(0.7, 1.5) if "Dollar" in exp.full_name or "Euro" in exp.full_name else random.uniform(10, 1500)
                    avg_rate = base_rate * random.uniform(0.98, 1.02)
                    end_rate = base_rate * random.uniform(0.95, 1.05)
                    # Format based on magnitude
                    rate_format = "{:.4f}" if base_rate < 5 else "{:.2f}"
                    data_rows.append([exp.full_name, rate_format.format(avg_rate), rate_format.format(end_rate)])

            if data_rows:
                table_builder = GenericTable(headers=headers, data_rows=data_rows, widths=widths, alignments=alignments, title=title)
                all_tables_str.append(table_builder.build())

        return "\n\n".join(all_tables_str)

    def _build_fx_sentence(self, item_to_describe: Optional[ForeignCurrencyHedgedItem]) -> str:
        """Generates the narrative sentence(s) for FX context."""
        num_sentences = random.choices([1, 2, 3], weights=[0.2, 0.6, 0.2], k=1)[0]
        sentences = []

        # Determine the primary currencies and their locations to talk about
        currencies_to_mention_objects = []
        if item_to_describe and item_to_describe.exposures:
            currencies_to_mention_objects = item_to_describe.exposures
        else:
            # Pick 1-3 random currencies if no specific hedged item is provided
            num_currencies = random.randint(1, 3)
            currencies_to_mention_objects = random.sample(
                [c for c in all_currencies if c.code != self.currency_code], num_currencies
            )

        # --- NEW: Create both full name and ISO code lists ---
        currency_full_names = [c.full_name for c in currencies_to_mention_objects]
        currency_iso_codes = [c.code for c in currencies_to_mention_objects]
        locations_to_mention = list(set([c.location for c in currencies_to_mention_objects]))

        # Format the currency list for display
        if len(currency_full_names) > 1:
            currencies_full_str = ", ".join(currency_full_names[:-1]) + f" and {currency_full_names[-1]}"
            currencies_iso_str = ", ".join(currency_iso_codes[:-1]) + f" and {currency_iso_codes[-1]}"
        else:
            currencies_full_str = currency_full_names[0]
            currencies_iso_str = currency_iso_codes[0]

        # --- NEW: Randomly choose which currency format to use in the sentence ---
        currencies_to_display = random.choice([currencies_full_str, currencies_iso_str])

        # --- NEW: Create a list of currencies with their amounts ---
        currencies_with_amounts_list = []
        for exp in currencies_to_mention_objects:
            amount_str = _format_single_notional(exp.amount if isinstance(exp, CurrencyExposure) else random.randint(1, 200) * 1_000_000, exp.symbol, self.prefer_abbreviated)
            # e.g., "Euro (€50.0 million)"
            currencies_with_amounts_list.append(f"{exp.full_name} ({amount_str})")
        if len(currencies_with_amounts_list) > 1:
            currencies_with_amounts_str = ", ".join(currencies_with_amounts_list[:-1]) + f" and {currencies_with_amounts_list[-1]}"
        else:
            currencies_with_amounts_str = currencies_with_amounts_list[0] if currencies_with_amounts_list else ""

        # --- NEW: Create exchange rate pair string ---
        exchange_rate_pair_str = ""
        if len(currencies_to_mention_objects) >= 2:
            # e.g., "EUR/GBP"
            pair = random.sample(currency_iso_codes, 2)
            exchange_rate_pair_str = f"{pair[0]}/{pair[1]}"
        elif len(currencies_to_mention_objects) == 1:
            # e.g., "EUR/USD"
            exchange_rate_pair_str = f"{currency_iso_codes[0]}/{self.currency_code}"

        if len(locations_to_mention) > 1:
            locations_str = ", ".join(locations_to_mention[:-1]) + f" and {locations_to_mention[-1]}"
        else:
            locations_str = locations_to_mention[0] if locations_to_mention else f"various international {random.choice(geo_locations)}"

        # Select a few template categories to build the paragraph
        template_categories = random.sample(list(fx_context_templates.keys()), k=num_sentences)

        for category in template_categories:
            template = random.choice(fx_context_templates[category])

            # Generate random financial data for placeholders
            amount1 = random.randint(1, 500) * 1_000_000
            amount2 = random.randint(1, 500) * 1_000_000
            gain_loss1, gain_loss2 = random.sample(gain_loss_phrases, 2)
            # --- NEW: Split impact placeholders for better grammar ---
            impact_adverb = random.choice(["favorably", "unfavorably", "negatively", "positively"])
            impact_verb_past = random.choice(["decreased", "increased", "reduced", "enhanced"])
            impact_adj = random.choice(["favorable", "unfavorable", "adverse", "beneficial"])
            strength_weakness = random.choice(["strengthening", "weakening"])

            # Format placeholders
            placeholders = {
                "company": _get_company_reference(self.company_name),
                "year": self.reporting_year,
                "prev_year": self.reporting_year - 1,
                "month": self.reporting_month,
                "end_day": self.reporting_day,
                "risk_term": random.choice(risk_exposure_terms),
                "currencies": currencies_to_display,
                "gain_loss": gain_loss1,
                "gain_loss2": gain_loss2,
                "financial_outcome_verb": random.choice(financial_outcome_verbs),
                "location": random.choice(balance_sheet_locations),
                "currency_code": self.currency_code,
                "amount_str": _format_single_notional(
                    amount1, self.currency_symbol, self.prefer_abbreviated
                ),
                "amount_str2": _format_single_notional(
                    amount2, self.currency_symbol, self.prefer_abbreviated
                ),
                "comparison_phrase": random.choice(comparison_phrases),
                "pct": f"{random.uniform(1.5, 7.5):.1f}",
                "pct2": f"{random.uniform(1.5, 7.5):.1f}",
                # New placeholders for more variety
                "impact_verb": random.choice(["affect", "impact", "influence"]),
                "income_statement_item": random.choice(
                    ["revenues", "operating income", "net income", "earnings"]
                ),
                "balance_sheet_item": random.choice(
                    [
                        "intercompany balances",
                        "monetary assets",
                        "receivables and payables",
                    ]
                ),
                "strength_weakness": strength_weakness,
                "quantifier_phrase": random.choice(
                    ["Substantially all", "A significant portion", "The majority"]
                ),
                "impact_adverb": impact_adverb,
                "impact_verb_past": impact_verb_past,
                "impact_adjective": impact_adj,
                "exchange_rate_pair": exchange_rate_pair_str,
                "currencies_with_amounts": currencies_with_amounts_str,
                # New placeholders for functional currency
                "primary_economic_env": random.choice(
                    [
                        "the primary economic environment",
                        "the economic environment",
                        "the local economy",
                    ]
                ),
                "functional_currency_basis": random.choice(
                    [
                        "is the local currency",
                        "is typically the local currency",
                        "is the currency of the primary economic environment in which the entity operates",
                    ]
                ),
                "inflation_level": random.choice(
                    ["highly inflationary", "hyperinflationary", "inflationary"]
                ),
                "geography": locations_str,
            }

            # Use format_map to safely populate the template
            sentence = template.format_map(placeholders)
            sentences.append(_cleanup_sentence(sentence))

        return " ".join(sentences)


# =============================================================================
# FX Contextual "Noise" Templates
# Ported from old/template/other.py
# These describe FX-related business activities without mentioning derivatives.
# =============================================================================

fx_context_templates = {
    "exposure": [
        "{company} operates in multiple countries and is exposed to foreign currency exchange rate {risk_term}, particularly related to {currencies_with_amounts}, that affect reported revenues and expenses.",
        "{company}'s international operations in {geography} subject it to foreign currency {risk_term}, primarily related to the {exchange_rate_pair} exchange rate.",
        "Foreign currency transaction {gain_loss} related to our {geography} operations are {financial_outcome_verb} {location} as incurred.",
        "{quantifier_phrase} of {company}'s foreign subsidiaries in {geography} use their local currency as their functional currency, such as the {currencies}.",
        "{company}'s results of operations are {impact_adverb} affected by changes in foreign currency exchange rates, particularly {risk_term} in the {currencies}.",
    ],
    "translation": [
        "Assets and liabilities of foreign subsidiaries in {geography} are translated to {currency_code} at period-end exchange rates, while revenues and expenses are translated at average exchange rates for the period.",
        "Translation adjustments resulting from the process of translating foreign currency financial statements into {currency_code} are {financial_outcome_verb} accumulated other comprehensive income.",
        "The cumulative translation adjustment {financial_outcome_verb} accumulated other comprehensive income was {amount_str} as of {month} {end_day}, {year}.",
        "Foreign currency translation adjustments {impact_verb_past} stockholders' equity by {amount_str} during {year}.",
        "{company} {financial_outcome_verb} a foreign currency translation {gain_loss} of {amount_str} in other comprehensive income for the year ended {month} {end_day}, {year}.",
        "The {strength_weakness} of the {exchange_rate_pair} exchange rate resulted in an {impact_adjective} translation impact of {amount_str} in {year}.",
        "Changes in foreign exchange rates resulted in translation {gain_loss} of {amount_str} {financial_outcome_verb} other comprehensive income during {year}.",
    ],
    "transaction": [
        "Foreign currency transaction {gain_loss} included in {geography} totaled {amount_str} for the year ended {month} {end_day}, {year}.",
        "{company} recognized foreign exchange {gain_loss} of {amount_str} during {year}, primarily related to intercompany balances denominated in {currencies}.",
        "{company} {financial_outcome_verb} foreign currency transaction {gain_loss} of {amount_str} in {year} {comparison_phrase} {gain_loss2} of {amount_str2} in {prev_year} from its operations in {geography}.",
        "Foreign exchange {gain_loss} on remeasurement of monetary assets and liabilities totaled {amount_str} in {year}.",
        "Transaction {gain_loss} on foreign currency ({currencies}) denominated receivables and payables are {financial_outcome_verb} earnings as exchange rates fluctuate.",
    ],
    "functional_currency": [
        "The functional currency for most of {company}'s foreign subsidiaries {functional_currency_basis} of the country in which the subsidiary operates.",
        "For our {geography} subsidiaries operating in {inflation_level} economies, the {currency_code} is used as the functional currency.",
        "{company} determines the functional currency of each subsidiary based on {primary_economic_env} in which the entity operates.",
        "The functional currencies of {company}'s significant foreign operations include {currencies}, representing exposures of {currencies_with_amounts}.",
        "Remeasurement of our subsidiary financial statements in {geography} from local currency to functional currency resulted in {gain_loss} of {amount_str} in {year}.",
    ],
    "impact": [
        "Foreign currency exchange rate {risk_term} had an {impact_adjective} impact on {income_statement_item} of approximately {amount_str}, or {pct}%, during {year}.",
        "Changes in foreign exchange rates {impact_adverb} impacted {income_statement_item} by {amount_str} in {year}.",
        "Foreign currency {risk_term} had a {impact_adjective} effect on {income_statement_item} of {pct}% in {year}, primarily due to the {strength_weakness} of the {currencies}.",
        "Excluding the impact of foreign currency translation, {income_statement_item} would have {impact_verb_past} by {pct}% in {year} {comparison_phrase} {prev_year}.",
        "The translation impact of changes in foreign exchange rates {impact_verb_past} reported {income_statement_item} by {amount_str} year-over-year.",
        "On a constant currency basis, {income_statement_item} {impact_verb_past} by {pct}%  the prior year, versus {pct2}% on a reported basis.",
    ],
    "intercompany": [
        "{company} has intercompany loans denominated in {currencies} that are remeasured each reporting period with {gain_loss} {financial_outcome_verb} in earnings.",
        "Intercompany foreign currency transactions resulted in remeasurement {gain_loss} of {amount_str} during {year}.",
        "{company} has {amount_str} in intercompany receivables denominated in {currencies} as of {month} {end_day}, {year}.",
        "Remeasurement of intercompany balances denominated in currencies other than the functional currency resulted in {gain_loss} of {amount_str} in {year}.",
    ],
}
