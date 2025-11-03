from typing import Literal, Optional, Union, List
from dataclasses import dataclass
import random
import re

from defs.instrument_definitions import HedgedItem, NotionalInstrument
from defs.function_definitions import _get_company_reference, _cleanup_sentence, _format_single_notional
from defs.table_definitions import GenericTable
from defs.common_data import (
    risk_exposure_terms,
    gain_loss_phrases,
    financial_outcome_verbs,
    balance_sheet_locations,
    state_descriptors,
    warrant_events,
    financing_types,
)

stock_list = [
    "common stock",
    "preferred stock",
    "treasury stock",
    "restricted stock",
    "stock options",
    "employee stock purchase plan (ESPP)",
    "convertible preferred stock",
    "convertible common stock",
    "founder's shares",
    "class A shares",
    "class B shares",
    "warrants",
    "stock option plan",
    "stock option agreement",
    "stock option",
]
@dataclass
class EquityHedgedItem(HedgedItem):
    """Represents an equity instrument being hedged (for EQ derivatives).

    Args:
        equity_type: Literal["market_index", "own_stock", "third_party_stock"] - The type of equity.
        number_of_shares: Optional[int] - The number of shares being hedged.
        share_price: Optional[float] - The share price at a point in time.
        stock_symbol: Optional[str] - The stock ticker symbol.
    """

    equity_type: Literal["market_index", "own_stock", "third_party_stock"]
    number_of_shares: Optional[int] = None
    share_price: Optional[float] = None
    stock_symbol: Optional[str] = None


class EQInstrument(NotionalInstrument[EquityHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="EQ", **kwargs)


def _generate_stock_symbol(company_name: str) -> str:
    """Generates a plausible stock symbol from a company name."""
    # Remove common suffixes like Inc, Corp, Ltd, etc.
    name = re.sub(r'\b(Inc|Corp|Ltd|Co|Group|Holdings)\b', '', company_name, flags=re.IGNORECASE).strip()
    words = name.split()
    
    if len(words) >= 2 and len(words) <= 4:
        # Take the first letter of each word
        symbol = "".join(word[0] for word in words).upper()
    elif len(words) == 1:
        # Take the first 3 or 4 letters of the single word
        symbol = name[:random.choice([3, 4])].upper()
    else: # Fallback for very long or short names
        symbol = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=random.randint(3, 4)))
    return symbol


@dataclass
class EQContextSentence:
    """Generates contextual sentences about equity-related activities without mentioning derivatives."""

    company_name: str
    reporting_year: int
    reporting_month: str
    reporting_day: int
    hedged_item: Optional[Union[EquityHedgedItem, List[EquityHedgedItem]]]
    prefer_abbreviated: bool
    currency_symbol: str

    def build(self) -> str:
        """Builds a multi-sentence paragraph about the company's equity exposures."""
        if isinstance(self.hedged_item, list) and self.hedged_item and random.random() < 0.4:
            table_str = self._build_equity_table()
            if table_str:
                # Prepend an introductory sentence to the table.
                intro_sentence = self._build_eq_sentence(None) # Generate a generic intro
                return f"{intro_sentence}{table_str}"
            # Fall through to generate a normal sentence if table building fails

        if isinstance(self.hedged_item, list):
            if not self.hedged_item: return ""
            item_to_describe = self.hedged_item[0]
        else:
            item_to_describe = self.hedged_item

        return self._build_eq_sentence(item_to_describe)

    def _build_equity_table(self) -> str:
        """Builds a text-based table summarizing equity investments or stock-based compensation."""
        if not isinstance(self.hedged_item, list) or not self.hedged_item:
            return ""

        # --- NEW: Add more table types for variety ---
        table_type = random.choice(["investments", "stock_comp_activity", "stock_comp_expense", "share_repurchase"])

        # --- 1. Equity Investments Summary ---
        if table_type == "investments":
            title = f"Summary of Equity Investments as of {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
            headers = ["Investment (Symbol)", "Shares", "Fair Value"]
            widths = [30, 20, 20]
            alignments = ['l', 'r', 'r']
            data_rows = []
            for item in self.hedged_item:
                if item.equity_type == "third_party_stock" and item.stock_symbol and item.number_of_shares and item.share_price:
                    value = item.number_of_shares * item.share_price
                    value_str = _format_single_notional(value, self.currency_symbol, self.prefer_abbreviated, True)
                    data_rows.append([f"Investment in {item.stock_symbol}", f"{item.number_of_shares:,}", value_str])

        # --- 2. Stock Option Activity (Roll-forward) ---
        elif table_type == "stock_comp_activity":
            title = f"Stock Option Activity For the Year Ended {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
            headers = ["", "Shares", "Weighted-Avg. Price"]
            widths = [35, 20, 20]
            alignments = ['l', 'r', 'r']
            data_rows = []
            # Simulate stock comp activity
            data_rows.append(["Beginning balance", f"{random.randint(1,5)*1_000_000:,}", f"{self.currency_symbol}{random.uniform(10, 20):.2f}"])
            data_rows.append(["Granted", f"{random.randint(100_000, 500_000):,}", f"{self.currency_symbol}{random.uniform(20, 30):.2f}"])
            data_rows.append(["Exercised", f"({random.randint(50_000, 200_000):,})", f"{self.currency_symbol}{random.uniform(12, 18):.2f}"])
            data_rows.append(["Ending balance", f"{random.randint(1,5)*1_000_000:,}", f"{self.currency_symbol}{random.uniform(22, 28):.2f}"])

        # --- 3. Stock-Based Compensation Expense ---
        elif table_type == "stock_comp_expense":
            title = f"Stock-Based Compensation Expense For the Year Ended {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
            headers = ["Award Type", "Compensation Cost"]
            widths = [35, 25]
            alignments = ['l', 'r']
            data_rows = []
            total_cost = 0
            award_types = ["Stock options", "Restricted stock units (RSUs)", "Performance share units (PSUs)"]
            for award in award_types:
                cost = random.randint(5, 50) * 1_000_000
                total_cost += cost
                cost_str = _format_single_notional(cost, self.currency_symbol, self.prefer_abbreviated, True)
                data_rows.append([award, cost_str])
            total_cost_str = _format_single_notional(total_cost, self.currency_symbol, self.prefer_abbreviated, True)
            data_rows.append(["-"*widths[0], "-"*widths[1]])
            data_rows.append(["Total stock-based compensation", total_cost_str])

        # --- 4. Share Repurchase Activity ---
        else: # share_repurchase
            title = f"Share Repurchase Activity For the Year Ended {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
            headers = ["", "Shares", "Average Price Paid"]
            widths = [40, 20, 25]
            alignments = ['l', 'r', 'r']
            data_rows = []
            shares_repurchased = random.randint(500_000, 5_000_000)
            avg_price = random.uniform(25.0, 150.0)
            total_cost = shares_repurchased * avg_price
            data_rows.append([f"Shares repurchased under program", f"{shares_repurchased:,}", f"{self.currency_symbol}{avg_price:.2f}"])
            data_rows.append([f"Total cost of shares repurchased", _format_single_notional(total_cost, self.currency_symbol, self.prefer_abbreviated, True), ""])

        if not data_rows:
            return ""

        table_builder = GenericTable(headers=headers, data_rows=data_rows, widths=widths, alignments=alignments, title=title)
        return table_builder.build()

    def _build_eq_sentence(self, item_to_describe: Optional[EquityHedgedItem]) -> str:
        num_sentences = random.choices([1, 2, 3], weights=[0.2, 0.6, 0.2], k=1)[0]
        sentences = []

        # Determine the primary equity type to talk about
        if item_to_describe:
            equity_type = item_to_describe.equity_type
            stock_symbol = item_to_describe.stock_symbol
        else:
            equity_type = random.choice(["market_index", "own_stock", "third_party_stock"])
            stock_symbol = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=4)) if equity_type != "market_index" else None

        # Select a few template categories to build the paragraph
        template_categories = random.sample(list(eq_context_templates.keys()), k=num_sentences)

        for category in template_categories:
            template = random.choice(eq_context_templates[category])

            # Generate random financial data for placeholders
            amount1 = random.randint(1, 200) * 1_000_000
            amount2 = random.randint(1, 200) * 1_000_000
            shares1 = random.randint(100_000, 2_000_000)
            shares2 = random.randint(100_000, 2_000_000)
            net_shares = random.randint(int(shares1 / 4), int(shares1 / 2))
            price1 = random.uniform(5.0, 75.0)
            price2 = random.uniform(5.0, 75.0)
            maturity_year = self.reporting_year + random.randint(2, 10)
            short_int = random.randint(30, 90)

            # Format placeholders
            placeholders = {
                "company": _get_company_reference(self.company_name),
                "year": self.reporting_year,
                "prev_year": self.reporting_year - 1,
                "month": self.reporting_month,
                "end_day": self.reporting_day,
                "risk_term": random.choice(risk_exposure_terms),
                "gain_loss": random.choice(gain_loss_phrases),
                "financial_outcome_verb": random.choice(financial_outcome_verbs),
                "location": random.choice(balance_sheet_locations),
                "amount_str": _format_single_notional(amount1, self.currency_symbol, self.prefer_abbreviated),
                "amount_str2": _format_single_notional(amount2, self.currency_symbol, self.prefer_abbreviated),
                "shares_str": f"{shares1:,}",
                "shares_str2": f"{shares2:,}",
                "net_shares_str": f"{net_shares:,}",
                "pct": f"{random.uniform(1.5, 15.5):.1f}",
                "stock_symbol": stock_symbol or "a market index",
                "equity_type": equity_type.replace("_", " "),
                "stock_plan_name": f"{self.reporting_year - random.randint(2,5)} Equity Incentive Plan",
                "vesting_period": f"{random.randint(2,5)} years",
                "valuation_model": random.choice(["Black-Scholes model", "a lattice model", "Monte Carlo simulation"]),
                # Placeholders from old/template/other.py
                "price_str": f"{self.currency_symbol}{price1:.2f}",
                "price_str2": f"{self.currency_symbol}{price2:.2f}",
                "maturity_year": maturity_year,
                "stock_event": random.choice(warrant_events),
                "financing_type": random.choice(financing_types),
                "short_int": short_int,
                "state_descriptor": random.choice(state_descriptors),
                "quarter": random.choice(["first", "second", "third", "fourth"]),
            }

            # Use format_map to safely populate the template
            sentence = template.format_map(placeholders)
            sentences.append(_cleanup_sentence(sentence))

        return " ".join(sentences)

# =============================================================================
# EQ Contextual "Noise" Templates
# These describe EQ-related business activities without mentioning derivatives.
# =============================================================================

eq_context_templates = {
    "exposure": [
        "{company} is exposed to market {risk_term} related to {risk_term} in the price of its common stock.",
        "{risk_term} in equity markets affects {company}'s exposure to equity-linked compensation and investment values.",
        "{company}'s share-based compensation costs are influenced by {risk_term} in its stock price and market conditions.",
        "As a publicly traded entity, {company} is exposed to {risk_term} associated with market price {risk_term} of its shares.",
    ],
    "stock_comp": [
        "Stock-based compensation expense was {amount_str} for the year ended {month} {end_day}, {year}.",
        "{company} grants stock options, restricted stock units (RSUs), and performance share units (PSUs) to employees and directors under its {stock_plan_name}.",
        "During {year}, {company} granted {shares_str} stock options with a weighted-average exercise price of {price_str} per share.",
        "Total unrecognized compensation cost related to unvested awards was {amount_str} as of {month} {end_day}, {year}, expected to be recognized over a weighted-average period of {vesting_period}.",
        "The fair value of stock options is estimated using the {valuation_model}, with assumptions for volatility, risk-free interest rate, and expected term.",
    ],
    "investments": [
        "{company} holds strategic investments in equity securities of other companies, which are recorded at fair value with changes {financial_outcome_verb} {location}.",
        "As of {month} {end_day}, {year}, the fair value of our equity investments was {amount_str}.",
        "During {year}, {company} recognized an unrealized {gain_loss} of {amount_str} on its portfolio of equity securities.",
        "Our investment portfolio includes equity securities of publicly traded companies, primarily in the technology sector, such as {stock_symbol}.",
        "The value of our equity investments is subject to market {risk_term} and can significantly impact our financial results.",
    ],
    "shareholder_equity": [
        "Total stockholders' equity was {amount_str} as of {month} {end_day}, {year}, an increase of {pct}% from the prior year.",
        "During {year}, {company} repurchased {shares_str} shares of its common stock for a total cost of {amount_str2}.",
        "The change in accumulated other comprehensive income was primarily due to unrealized {gain_loss} on available-for-sale equity securities.",
        "As of {year}, {shares_str} shares of common stock were issued and outstanding.",
    ],
    "warrants_and_options": [
        "{company} has {shares_str} equity-classified warrants {state_descriptor} with an exercise price of {price_str} per share, exercisable until {maturity_year}.",
        "Outstanding equity warrants for {shares_str} shares at {price_str} per share are classified in stockholders' equity and are not remeasured.",
        "During {year}, warrant holders exercised {shares_str} warrants, resulting in proceeds of {amount_str}.",
        "In the {quarter} quarter of {year}, {company} modified the terms of {state_descriptor} warrants, extending the expiration date to {maturity_year} and adjusting the exercise price to {price_str2}.",
        "In connection with the {stock_event}, {company} issued warrants to purchase up to {shares_str} shares of common stock at an exercise price of {price_str} per share.",
        "As of {month} {end_day}, {year}, there are {shares_str} issued and {state_descriptor} options to purchase common stock.",
        "The original exercisable shares of {shares_str} and exercise price of {price_str} was adjusted to {shares_str2} and {price_str2}, respectively, to account for the {month} {year} Private Placement.",
        "{shares_str} warrants were exercised on a cashless basis during {year}, resulting in the issuance of {net_shares_str} net shares.",
    ],
    "capital_structure": [
        "In conjunction with its {month} {year} {financing_type}, {company} issued {shares_str} shares of common stock valued at {amount_str}, which were recorded as debt issuance costs.",
        "{company} has reserved {shares_str} shares of the common stock for issuance upon the exercise of {state_descriptor} warrants and {shares_str2} shares for stock options.",
        "The overhang of {shares_str} shares underlying convertible securities may impair {company}'s ability to raise capital through future equity offerings.",
        "The potential issuance of {shares_str} shares upon exercise of warrants and conversion of notes could dilute current shareholders by approximately {pct}%.",
        "If all of the warrants are exercised and the debt is fully converted to {company}'s stock, current stockholders will experience a significant dilution in their ownership of the company.",
    ],
    "registration_and_market": [
        "{company} filed a registration statement on Form S-3 in {month} {year} to register {shares_str} shares of common stock underlying convertible securities for resale by holders.",
        "The resale of {shares_str} shares registered under the registration statement could adversely affect the market price of {company}'s common stock.",
        "Sales of substantial amounts of common stock in the public market following effectiveness of the registration statement could adversely affect prevailing market prices.",
        "{company} is obligated to file a registration statement within {short_int} days following {month} {year} covering shares issuable upon conversion of notes and warrants.",
        "Shares of common stock closed at {price_str} on {month} {end_day}, {year}, compared to {price_str2} at {month} {end_day}, {prev_year}.",
        "{company}'s stock price ranged from a low of {price_str} to a high of {price_str2} during {year}.",
    ],
}
