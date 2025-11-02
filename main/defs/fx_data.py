import random
from typing import Callable, Dict, Generic, List, Literal, Optional, Set, Tuple, TypeVar
from dataclasses import dataclass, field

from defs.instrument_definitions import HedgedItem, NotionalInstrument
from defs.common_data import months, balance_sheet_locations
from defs.template_definitions import _cleanup_sentence, _format_single_notional
from defs.function_definitions import _get_company_reference
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


major_currencies = [
    Currency("USD", "U.S. Dollar", "$", "U.S.", "United States"),
    Currency("EUR", "Euro", "€", "European", "Europe"),
    Currency("GBP", "British Pound", "£", "British", "U.K."),
    Currency("JPY", "Japanese Yen", "¥", "Japanese", "Japan"),
    Currency("CAD", "Canadian Dollar", "$", "Canadian", "Canada"),
    Currency("AUD", "Australian Dollar", "$", "Australian", "Australia"),
    Currency("CHF", "Swiss Franc", "CHF", "Swiss", "Switzerland"),
    Currency("CNY", "Chinese Yuan", "¥", "Chinese", "China"),
]

european_currencies = [
    Currency("NOK", "Norwegian Krone", "kr", "Norwegian", "Norway"),
    Currency("SEK", "Swedish Krona", "kr", "Swedish", "Sweden"),
    Currency("DKK", "Danish Krone", "kr", "Danish", "Denmark"),
    Currency("PLN", "Polish Zloty", "zł", "Polish", "Poland"),
    Currency("HUF", "Hungarian Forint", "Ft", "Hungarian", "Hungary"),
    Currency("CZK", "Czech Koruna", "Kč", "Czech", "Czech Republic"),
    Currency("TRY", "Turkish Lira", "₺", "Turkish", "Turkey"),
    Currency("RUB", "Russian Ruble", "₽", "Russian", "Russia"),
    Currency("BGN", "Bulgarian Lev", "лв", "Bulgarian", "Bulgaria"),
    Currency("RON", "Romanian Leu", "lei", "Romanian", "Romania"),
]

asian_currencies = [
    Currency("INR", "Indian Rupee", "₹", "Indian", "India"),
    Currency("KRW", "South Korean Won", "₩", "South Korean", "South Korea"),
    Currency("SGD", "Singapore Dollar", "$", "Singaporean", "Singapore"),
    Currency("HKD", "Hong Kong Dollar", "$", "Hong Kong", "Hong Kong"),
    Currency("THB", "Thai Baht", "฿", "Thai", "Thailand"),
    Currency("MYR", "Malaysian Ringgit", "RM", "Malaysian", "Malaysia"),
]

americas_currencies = [
    Currency("MXN", "Mexican Peso", "$", "Mexican", "Mexico"),
    Currency("BRL", "Brazilian Real", "R$", "Brazilian", "Brazil"),
    Currency("ARS", "Argentine Peso", "$", "Argentine", "Argentina"),
    Currency("CLP", "Chilean Peso", "$", "Chilean", "Chile"),
    Currency("COP", "Colombian Peso", "$", "Colombian", "Colombia"),
]

other_currencies = [
    Currency("NZD", "New Zealand Dollar", "$", "New Zealand", "Oceania"),
    Currency("ZAR", "South African Rand", "R", "South African", "African"),
    Currency("AED", "UAE Dirham", "د.إ", "Emirati", "United Arab Emirates"),
    Currency("SAR", "Saudi Riyal", "ر.س", "Saudi", "Saudi Arabia"),
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

    amount: int

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
    hedged_item: Optional[ForeignCurrencyHedgedItem]
    prefer_abbreviated: bool
    currency_symbol: str
    currency_code: str

    def build(self) -> str:
        """Builds a multi-sentence paragraph about the company's FX exposures."""
        num_sentences = random.choices([1, 2, 3], weights=[0.2, 0.6, 0.2], k=1)[0]
        sentences = []

        # Determine the primary currencies and their locations to talk about
        currencies_to_mention_objects = []
        if self.hedged_item and self.hedged_item.exposures:
            currencies_to_mention_objects = self.hedged_item.exposures
        else:
            # Pick 1-3 random currencies if no specific hedged item is provided
            num_currencies = random.randint(1, 3)
            currencies_to_mention_objects = random.sample(
                [c for c in all_currencies if c.code != self.currency_code], num_currencies
            )
        
        currencies_to_mention = [c.full_name for c in currencies_to_mention_objects]
        locations_to_mention = list(set([c.location for c in currencies_to_mention_objects]))

        # Format the currency list for display
        if len(currencies_to_mention) > 1:
            currencies_str = ", ".join(currencies_to_mention[:-1]) + f" and {currencies_to_mention[-1]}"
        else:
            currencies_str = currencies_to_mention[0]
        
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
                "currencies": currencies_str,
                "currencies_list": currencies_str, # Alias for the same thing
                "locations": locations_str,
                "gain_loss": gain_loss1,
                "gain_loss2": gain_loss2,
                "financial_outcome_verb": random.choice(financial_outcome_verbs),
                "location": random.choice(balance_sheet_locations),
                "currency_code": self.currency_code,
                "amount_str": _format_single_notional(amount1, self.currency_symbol, self.prefer_abbreviated),
                "amount_str2": _format_single_notional(amount2, self.currency_symbol, self.prefer_abbreviated),
                "comparison_phrase": random.choice(comparison_phrases),
                "pct": f"{random.uniform(1.5, 7.5):.1f}",
                "pct2": f"{random.uniform(1.5, 7.5):.1f}",
                # New placeholders for more variety
                "impact_verb": random.choice(["affect", "impact", "influence"]),
                "income_statement_item": random.choice(
                    ["revenues", "operating income", "net income", "earnings"]
                ),
                "balance_sheet_item": random.choice(
                    ["intercompany balances", "monetary assets", "receivables and payables"]
                ),
                "strength_weakness": strength_weakness,
                "quantifier_phrase": random.choice(["Substantially all", "A significant portion", "The majority"]),
                "impact_adverb": impact_adverb,
                "impact_verb_past": impact_verb_past,
                "impact_adjective": impact_adj,

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
        "{company} operates in multiple countries and is exposed to foreign currency exchange rate {risk_term}, particularly related to the {currencies}, that affect reported revenues and expenses.",
        "{company}'s international operations in {locations} subject it to foreign currency {risk_term}, primarily related to the {currencies}.",
        "Foreign currency transaction {gain_loss} related to our {locations} operations are {financial_outcome_verb} {location} as incurred.",
        "{quantifier_phrase} of {company}'s foreign subsidiaries in {locations} use their local currency as their functional currency, such as the {currencies}.",
        "{company}'s results of operations are {impact_adverb} affected by changes in foreign currency exchange rates, particularly {risk_term} in the {currencies}.",
    ],
    "translation": [
        "Assets and liabilities of foreign subsidiaries are translated to {currency_code} at period-end exchange rates, while revenues and expenses are translated at average exchange rates for the period.",
        "Translation adjustments resulting from the process of translating foreign currency financial statements into {currency_code} are {financial_outcome_verb} accumulated other comprehensive income.",
        "The cumulative translation adjustment {financial_outcome_verb} accumulated other comprehensive income was {amount_str} as of {month} {end_day}, {year}.",
        "Foreign currency translation adjustments {impact_verb_past} stockholders' equity by {amount_str} during {year}.",
        "{company} {financial_outcome_verb} a foreign currency translation {gain_loss} of {amount_str} in other comprehensive income for the year ended {month} {end_day}, {year}.",
        "The {strength_weakness} of the {currencies} against the {currency_code} resulted in an {impact_adjective} translation impact of {amount_str} in {year}.",
        "Changes in foreign exchange rates resulted in translation {gain_loss} of {amount_str} {financial_outcome_verb} other comprehensive income during {year}.",
    ],
    "transaction": [
        "Foreign currency transaction {gain_loss} included in {location} totaled {amount_str} for the year ended {month} {end_day}, {year}.",
        "{company} recognized foreign exchange {gain_loss} of {amount_str} during {year}, primarily related to intercompany balances denominated in {currencies}.",
        "{company} {financial_outcome_verb} foreign currency transaction {gain_loss} of {amount_str} in {year} {comparison_phrase} {gain_loss2} of {amount_str2} in {prev_year} from its operations in {locations}.",
        "Foreign exchange {gain_loss} on remeasurement of monetary assets and liabilities totaled {amount_str} in {year}.",
        "Transaction {gain_loss} on foreign currency ({currencies}) denominated receivables and payables are {financial_outcome_verb} earnings as exchange rates fluctuate.",
    ],
    "functional_currency": [
        "The functional currency for most of {company}'s foreign subsidiaries is the local currency of the country in which the subsidiary operates.",
        "For subsidiaries operating in highly inflationary economies, the {currency_code} is used as the functional currency.",
        "{company} determines the functional currency of each subsidiary based on the primary economic environment in which the entity operates.",
        "The functional currencies of {company}'s significant foreign operations include {currencies_list}.",
        "Remeasurement of foreign subsidiary financial statements from local currency to functional currency resulted in {gain_loss} of {amount_str} in {year}.",
    ],
    "impact": [
        "Foreign currency exchange rate {risk_term} had an {impact_direction} impact on revenues of approximately {amount_str}, or {pct}%, during {year}.",
        "Changes in foreign exchange rates {impact_direction} impacted operating income by {amount_str} in {year}.",
        "Foreign currency {risk_term} had a {impact_direction} effect on revenues of {pct}% in {year}, primarily due to the strengthening of the {currencies}.",
        "Excluding the impact of foreign currency translation, revenues would have increased {pct}% in {year} compared to {prev_year}.",
        "The translation impact of changes in foreign exchange rates {impact_direction} reported revenues by {amount_str} year-over-year.",
        "On a constant currency basis, revenues increased {pct}% compared to the prior year, versus {pct2}% on a reported basis.",
    ],
    "intercompany": [
        "{company} has intercompany loans denominated in various currencies that are remeasured each reporting period with gains and losses recorded in earnings.",
        "Intercompany foreign currency transactions resulted in remeasurement {gain_loss} of {amount_str} during {year}.",
        "{company} has {amount_str} in intercompany receivables denominated in {currencies} as of {month} {end_day}, {year}.",
        "Remeasurement of intercompany balances denominated in currencies other than the functional currency resulted in {gain_loss} of {amount_str} in {year}.",
    ],
}
