from dataclasses import dataclass, field
from typing import List, Literal, Optional, Dict, TypeVar, Generic
import random

# Imports moved here for the NotionalSentence.build() method
from main.definitions.common_data import (
    months_full,
    quarters,
    aggregate_use_verbs,
    individual_use_verbs,
    termination_verbs,
)
from main.definitions.template_definitions import *
from main.definitions.template_definitions import _cleanup_sentence, _format_single_notional
# =============================================================================
# SCENARIO DEFINITION - CLASSES
# This file contains the core data structures (dataclasses) that define the
# state of a financial narrative for generation.
# =============================================================================

# Define a central, single source of truth for derivative categories.
DERIVATIVE_CATEGORIES = ("IR", "FX", "CP", "EQ", "GEN")
DerivativeCategory = Literal["IR", "FX", "CP", "EQ", "GEN"]

@dataclass
class NarrativeEvidence:
    """Represents a piece of evidence extracted from the generated narrative.
    
    Args:
        instrument_id: Optional[int] - Link to the specific instrument, if applicable
        status: Literal["summary", "new", "terminated", "none"] - The status of the evidence
        category: DerivativeCategory - The category of the derivative
        aggregate: Optional[bool] - Whether it's an aggregate statement or individual
        notional: Optional[int] - If notional amount is mentioned
        month: Optional[str] - e.g., "January" is mentioned
        year: Optional[int] - e.g., "2023" is mentioned
        instrument_type: Optional[str] - e.g., "interest rate swap"
        additional_details: Optional[Dict] - Any other relevant details
    """
    instrument_id: Optional[int]  
    status: Literal["summary", "new", "terminated", "none"]
    category: DerivativeCategory
    aggregate: Optional[bool] = None
    notional: Optional[int] = None
    month: Optional[str] = None
    year: Optional[int] = None
    instrument_type: Optional[str] = None
    additional_details: Optional[Dict] = field(default_factory=dict)
    def to_dict(self) -> Dict:
        return self.__dict__

T_HedgedItem = TypeVar("T_HedgedItem", bound="HedgedItem")


@dataclass
class DerivativeInstrument:
    """Base class for a single derivative instrument within our narrative.
    
    Args:
        instrument_id: int - A unique ID to track the same instrument across multiple years.
        instrument_type: str - The type of derivative instrument (e.g., "interest rate swap").
        instrument_prefix: Optional[str] - The prefix of the instrument (e.g., "pay-fixed").
        instrument_name: str - The core name of the instrument (e.g., "interest rate swap").
        instrument_alias: str - A shorter alias for the instrument (e.g., "swap").
        category: DerivativeCategory - The category of the derivative
        month: str - The month this state of the instrument is for.
        year: int - The year this state of the instrument is for.
        hedge_designation: Optional[str] - The hedge designation, if any.
        maturity_month: Optional[str] - The maturity month
        maturity_year: Optional[int] - The maturity year
    """

    instrument_id: int
    instrument_type: str
    instrument_prefix: Optional[str]
    instrument_name: str
    instrument_alias: str
    category: DerivativeCategory
    month: str
    year: int
    hedge_designation: Optional[str] = None
    maturity_month: Optional[str] = None
    maturity_year: Optional[int] = None

    def to_dict(self) -> Dict:
        """Serializes the common instrument data to a dictionary for JSON output."""
        return {
            "instrument_id": self.instrument_id,
            "instrument_type": self.instrument_type,
            "instrument_prefix": self.instrument_prefix,
            "instrument_name": self.instrument_name,
            "instrument_alias": self.instrument_alias,
            "category": self.category,
            "hedge_designation": self.hedge_designation,
        }


@dataclass
class HedgedItem:
    """Base class for the item being hedged."""

    hedged_item_id: (
        int  # A unique ID to track the same hedged item across multiple years.
    )

    def to_dict(self) -> Optional[Dict]:
        """Serializes the hedged item data to a dictionary."""
        data = {k: v for k, v in self.__dict__.items() if v is not None}
        # Ensure the ID is always present if the object exists
        return {"hedged_item_id": self.hedged_item_id, **data} if data else None


@dataclass
class DebtHedgedItem(HedgedItem):
    """Represents a debt instrument being hedged (for IR derivatives).
    
    Args:
        debt_type: str - The type of debt instrument being hedged.
        issuance_month: Optional[str] - The issuance month of the debt.
        issuance_year: int - The issuance year of the debt.
        maturity_month: Optional[str] - The maturity month of the debt.
        maturity_year: int - The maturity year of the debt.
        principal_amount: int - The principal amount of the debt.
        interest_rate_type: Literal["fixed", "variable"] - The type of interest rate.
        benchmark_rate: Optional[str] - The benchmark rate if variable (e.g., "LIBOR").
        spread_bps: Optional[int] - The spread in basis points over the benchmark.
        fixed_rate_pct: Optional[float] - The fixed interest rate percentage.
        change_rate_pct: Optional[float] - The new interest rate percentage after a change.
        payment_amount: Optional[int] - The payment amount.
        payment_frequency: Optional[str] - The payment frequency (e.g., "quarterly").
    """

    debt_type: str
    issuance_month: Optional[str]
    issuance_year: int
    maturity_month: Optional[str]
    maturity_year: int
    principal_amount: int
    interest_rate_type: Literal["fixed", "variable"]
    benchmark_rate: Optional[str] = None 
    spread_bps: Optional[int] = None
    fixed_rate_pct: Optional[float] = None
    change_rate_pct: Optional[float] = None
    payment_amount: Optional[int] = None
    payment_frequency: Optional[str] = None


@dataclass
class Currency:
    code: str
    full_name: str
    symbol: str
    adjective: str
    location: str


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
class CommodityHedgedItem(HedgedItem):
    """Represents a commodity being hedged (for CP derivatives).
    
    Args:
        commodity_type: str - The type of commodity being hedged.
        quantity: int - The quantity of the commodity.
        unit_of_volume: str - The unit of volume of the commodity.
        price_per_unit: float - The price per unit of the commodity.
        cost_type: str - The cost type of the commodity (e.g., "input").
        transaction_type: Literal["purchase", "sale"] - The transaction type (e.g., "purchase").
        supplier: Optional[str] - The supplier of the commodity if purchased.
    """

    commodity_type: str
    quantity: int
    unit_of_volume: str
    price_per_unit: float
    cost_type: str
    transaction_type: str
    supplier: Optional[str]


@dataclass
class EquityHedgedItem(HedgedItem):
    """Represents an equity instrument being hedged (for EQ derivatives).
    
    Args:
        underlying_equity: str - The underlying equity being hedged.
        equity_type: Literal["market_index", "own_stock", "third_party_stock"] - The type of equity.
        reason: str - The reason for hedging this equity exposure.
    """

    # Placeholder for future implementation
    underlying_equity: str
    equity_type: Literal["market_index", "own_stock", "third_party_stock"]
    reason: str


@dataclass
class NotionalInstrument(DerivativeInstrument, Generic[T_HedgedItem]):
    """A derivative instrument primarily defined by a notional amount.
    
    Args:
        notional_amount: int - The notional amount of the instrument.
        currency: str - The currency of the instrument.
        hedged_item: Optional[T_HedgedItem] - The item being hedged by this instrument.
    """

    notional_amount: int = 0
    currency: str = "USD"
    hedged_item: Optional[T_HedgedItem] = None

    def to_dict(self) -> Dict:
        """Extends the base to_dict to include notional-specific fields."""
        # This now correctly handles the nested HedgedItem object.
        data = super().to_dict()
        data.update(
            {
                "notional_amount": self.notional_amount,
                "currency": self.currency,
                "hedged_item": self.hedged_item.to_dict() if self.hedged_item else None,
            }
        )
        return data


# Specific instrument types can now be defined cleanly.
# We can add more specific fields to each type later if needed.
class IRInstrument(NotionalInstrument[DebtHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="IR", **kwargs)


class FXInstrument(NotionalInstrument[ForeignCurrencyHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="FX", **kwargs)


class CPInstrument(NotionalInstrument[CommodityHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="CP", **kwargs)


class EQInstrument(NotionalInstrument[EquityHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="EQ", **kwargs)


class GenericInstrument(NotionalInstrument[HedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="GEN", **kwargs)


@dataclass
class ScenarioArchetype:
    """Defines the instrument profile for a type of company to make generation more realistic."""

    name: str
    debt_exposure_range: tuple[int, int]
    fx_exposure_range: tuple[int, int]
    commodity_exposure_range: tuple[int, int]
    equity_exposure_range: tuple[int, int]
    generic_instrument_range: tuple[int, int]
    hedging_propensities: Dict[
        DerivativeCategory, float
    ]  # Per-category likelihood of hedging.
    policy_coverage: Literal["full", "partial", "light"]
    default_currency: str
    money_units: List[
        tuple[str, int]
    ]  # e.g., [("million", 1_000_000), ("billion", 1_000_000_000)]
    prefers_abbreviated_numbers: bool = True
    can_have_accounting_update: bool = True

    def get_exposure_counts(self) -> Dict[str, int]:
        """Generates a dictionary of exposure counts based on the archetype's ranges."""
        return {
            "debt": random.randint(*self.debt_exposure_range),
            "fx": random.randint(*self.fx_exposure_range),
            "commodity": random.randint(*self.commodity_exposure_range),
            "equity": random.randint(*self.equity_exposure_range),
            "generic": random.randint(*self.generic_instrument_range),
        }

@dataclass
class GeneralHedgingPolicy:
    """Describes the company's high-level, non-instrument-specific hedging policies."""

    does_not_use_for_trading: bool = True
    counterparty_credit_risk_monitored: bool = True
    counterparty_details: str = (
        "major financial institutions"  # e.g., "major financial institutions"
    )


@dataclass
class CategorySpecificPolicy:
    """Describes policies for a specific category of derivatives (e.g., IR, FX)."""

    category: DerivativeCategory
    effectiveness_testing_method: Optional[str] = None  # e.g., "dollar-offset method"
    effectiveness_frequency: Optional[str] = "quarterly"
    documentation_formalized: bool = True
    # Describes the general accounting policy for this category
    accounting_policy_description: Optional[str] = None
    accounting_standard: Optional[str] = None

@dataclass
class AccountingStandardUpdate:
    """Represents the adoption or discussion of a new accounting standard."""

    standard_name: str
    issuer: str
    topic: str
    adoption_year: int
    impact_description: str
    adoption_method: Optional[str] = None
    effective_year: Optional[int] = None
    is_adopted: bool = False


@dataclass
class RiskManagementPolicy:
    """Contains all policy-related information for the narrative."""

    general_policy: GeneralHedgingPolicy = field(default_factory=GeneralHedgingPolicy)
    category_policies: List[CategorySpecificPolicy] = field(default_factory=list)


@dataclass
class GenerationScenario:
    """Holds the entire state for a single, coherent training example."""

    company_name: str
    reporting_month: str
    reporting_day: int
    reporting_year: int
    archetype: ScenarioArchetype
    instruments: List[NotionalInstrument] = field(default_factory=list)
    policy: Optional[RiskManagementPolicy] = None
    number_format_preference: bool = (
        True  # True for abbreviated, False for full numeric
    )
    accounting_updates: List[AccountingStandardUpdate] = field(default_factory=list)

@dataclass
class NotionalSentence:
    """
    A data class that holds all the components required to generate a sentence
    about notional amounts. This structure is passed to a sentence generation function.
    """

    # Core sentence components
    swap_type: str
    year: int
    notional: int
    currency_symbol: str = "$"
    money_unit_word: str = "million"
    sentence_type: Literal[
        "summary",
        "new_individual",
        "terminated_individual",
        "comparative",
        "no_instruments",
    ] = "summary"

    # Optional time components
    month: Optional[str] = None
    end_day: Optional[int] = None
    quarter: Optional[str] = None

    # Optional comparison data for multi-year sentences
    prev_year: Optional[int] = None
    prev_notional: Optional[int] = None
    prev2_year: Optional[int] = None
    prev2_notional: Optional[int] = None

    # Optional descriptive elements
    hedge_designation: Optional[str] = None
    result_phrase: Optional[str] = None
    company_name: Optional[str] = None
    verb: Optional[str] = None
    category: Optional[DerivativeCategory] = None

    # Formatting preferences
    money_units: List[Tuple[str, int]] = field(
        default_factory=lambda: [("million", 1_000_000)]
    )
    prefer_abbreviated: bool = True

    def build(self) -> Tuple[str, Dict]:
        """
        Builds a notional sentence from the instance's configuration and returns
        the sentence string and a dictionary of the components used.
        """
        used_components = {}

        # Default values for optional components
        month = self.month or random.choice(months_full)
        end_day = self.end_day or random.randint(28, 31)
        quarter = self.quarter or random.choice(quarters)
        company_name = self.company_name or "The Company"

        # Determine number of years for comparison
        num_years = 1
        if self.prev_year is not None and self.prev_notional is not None:
            num_years = 2
            if self.prev2_year is not None and self.prev2_notional is not None:
                num_years = 3

        # 1. Format amount string
        amount_str = ""
        formatted_notional = _format_single_notional(
            self.notional, self.currency_symbol, self.money_units, self.prefer_abbreviated
        )
        used_components["amount"] = formatted_notional

        if num_years == 1:
            amount_str = formatted_notional
        elif num_years == 2:
            assert self.prev_notional is not None
            formatted_prev_notional = _format_single_notional(
                self.prev_notional, self.currency_symbol, self.money_units, self.prefer_abbreviated
            )
            amount_str = f"{formatted_notional} and {formatted_prev_notional}"
            used_components["prev_amount"] = formatted_prev_notional
        elif num_years == 3:
            assert self.prev_notional is not None and self.prev2_notional is not None
            formatted_prev_notional = _format_single_notional(
                self.prev_notional, self.currency_symbol, self.money_units, self.prefer_abbreviated
            )
            formatted_prev2_notional = _format_single_notional(
                self.prev2_notional, self.currency_symbol, self.money_units, self.prefer_abbreviated
            )
            amount_str = f"{formatted_notional}, {formatted_prev_notional}, and {formatted_prev2_notional}"
            used_components["prev_amount"] = formatted_prev_notional
            used_components["prev2_amount"] = formatted_prev2_notional

        used_components["amount_str"] = amount_str

        # 2. Select time prefix template
        time_prefix = ""
        time_suffix = ""
        if self.sentence_type in ["summary", "comparative"]:
            if num_years == 1:
                time_prefix = random.choice(point_in_time_prefixes)
            elif num_years == 2:
                time_prefix = random.choice(multi_year_time_prefixes["two_year"])
            else:  # num_years == 3
                time_prefix = random.choice(multi_year_time_prefixes["three_year"])
        else:  # new_individual, terminated_individual
            time_prefix = random.choice(period_of_time_prefixes)

        time_prefix = time_prefix.format(
            month=month,
            end_day=end_day,
            year=self.year,
            prev_year=self.prev_year or self.year - 1,
            prev2_year=self.prev2_year or self.year - 2,
            quarter=quarter,
        )
        time_suffix = f"as of {month} {end_day}, {self.year}"
        used_components["time_prefix"] = time_prefix
        used_components["time_suffix"] = time_suffix

        # 3. Select verb
        verb = self.verb
        if verb is None:
            if self.sentence_type == "new_individual":
                verb = random.choice(individual_use_verbs)
            elif self.sentence_type == "terminated_individual":
                verb = random.choice(termination_verbs)
            else:  # summary, comparative
                verb = random.choice(aggregate_use_verbs)
        used_components["verb"] = verb

        # 4. Select amount connector
        amount_connector = random.choice(amount_connectors)
        used_components["amount_connector"] = amount_connector

        # 5. Hedge designation clause
        hedge_designation_clause = ""
        if self.hedge_designation:
            hedge_designation_clause = f", designated as {self.hedge_designation}"
            used_components["hedge_designation_clause"] = hedge_designation_clause

        # 6. Result phrase clause
        result_clause = ""
        if self.result_phrase:
            result_clause = f", {self.result_phrase}"
            used_components["result_clause"] = result_clause

        # 7. Select main sentence template
        templates_for_type = NOTIONAL_SENTENCE_TEMPLATES.get(
            self.sentence_type, NOTIONAL_SENTENCE_TEMPLATES["summary"]
        )
        template = random.choice(templates_for_type)

        # 8. Populate placeholders
        sentence = template.format(
            time_prefix=time_prefix,
            company=company_name,
            verb=verb,
            swap_type=self.swap_type,
            amount_connector=amount_connector,
            amount_str=amount_str,
            hedge_designation_clause=hedge_designation_clause,
            result_clause=result_clause,
            time_suffix=time_suffix,
        )

        # 9. Cleanup
        sentence = _cleanup_sentence(sentence)

        # Add final components to the used dictionary
        used_components["company"] = company_name
        used_components["swap_type"] = self.swap_type
        used_components["year"] = self.year

        return sentence, used_components