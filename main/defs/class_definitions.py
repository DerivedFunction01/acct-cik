from dataclasses import dataclass, field
from typing import List, Literal, Optional, Dict, TypeVar, Generic, Tuple
import random

# Imports moved here for the NotionalSentence.build() method
from defs.common_data import  *
from defs.template_definitions import *
from defs.template_definitions import (
    _cleanup_sentence,
    _format_single_notional,
)
from defs.commodity_data import *

# =============================================================================
# SCENARIO DEFINITION - CLASSES
# This file contains the core data structures (dataclasses) that define the
# state of a financial narrative for generation.
# =============================================================================

# Define a central, single source of truth for derivative categories.
DERIVATIVE_CATEGORIES = ("IR", "FX", "CP", "EQ", "GEN")
DerivativeCategory = Literal["IR", "FX", "CP", "EQ", "GEN"]


from dataclasses import dataclass, field
from typing import Optional, Callable, Dict


@dataclass
class BaseNarrativeEvidence:
    """
    Base class for a piece of evidence extracted from the generated narrative.
    This class is meant to be subclassed for specific evidence types.
    """

    category: str  # DerivativeCategory alias simplified to str for this snippet
    status: str  # e.g., "summary", "new", "individual", "terminated_individual", etc.
    year: Optional[int] = None
    instrument_id: Optional[int] = None
    additional_details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Serializes the evidence to a dictionary."""
        return self.__dict__

    def to_string(self) -> str:
        """Generates a human-readable 'chain of thought' sentence for this evidence."""
        return f"Uncategorized evidence found for {self.category}."


@dataclass
class NotionalEvidence(BaseNarrativeEvidence):
    """Evidence related to notional or fair value amounts of derivative instruments, with temporal reasoning and validation."""

    aggregate: Optional[bool] = None
    notional: Optional[int] = None
    month: Optional[str] = None
    year: Optional[int] = None
    prev_year: Optional[int] = None
    prev2_year: Optional[int] = None
    instrument_type: Optional[str] = None
    notional_str: Optional[str] = None
    prev_notional_str: Optional[str] = None
    prev2_notional_str: Optional[str] = None
    reporting_year: Optional[int] = None
    maturity_year: Optional[int] = None
    value_type: str = "notional"
    currency: str = "USD"
    sentence_type: Optional[str] = None

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _category_label(self) -> str:
        """Map short category codes to descriptive names."""
        return {
            "IR": "Interest Rate",
            "FX": "Foreign Exchange",
            "CP": "Commodity",
            "EQ": "Equity",
            "GEN": "Generic",
        }.get(self.category, "Unknown Category")

    def _temporal_reasoning(self, value_desc: str) -> str:
        """Describe time relation of the evidence, with maturity only in past/future cases."""
        if not self.reporting_year or not self.year:
            return ""

        maturity_reason = "" # Only give maturity reason to proper sentences
        if self.maturity_year is not None and self.sentence_type and self.sentence_type in [
            "historical_individual",
            "terminated_individual",
        ]:
            if self.maturity_year >= self.reporting_year:
                maturity_reason = f" and is considered current as its maturity year ({self.maturity_year}) is on or after the reporting year"
            else:
                maturity_reason = f" and is considered historical as it matured in {self.maturity_year}, prior to or at the reporting year"

        if self.year == self.reporting_year:
            if self.notional is None:
                return f" (for the reporting year {self.reporting_year}, confirming current reporting activity{maturity_reason})."
            elif self.notional > 0:
                return f" (for the reporting year {self.reporting_year}, confirming current use with a positive {value_desc}{maturity_reason})."
            else:
                return f" (for the reporting year {self.reporting_year}, confirming no current use with a zero {value_desc}{maturity_reason})."

        elif (
            self.year < self.reporting_year or self.maturity_year == self.reporting_year
        ):
            mismatch_note = ""
            if any(
                [
                    self.notional_str
                    and str(self.reporting_year) not in self.notional_str,
                    self.prev_notional_str
                    and str(self.reporting_year) not in self.prev_notional_str,
                    self.prev2_notional_str
                    and str(self.reporting_year) not in self.prev2_notional_str,
                ]
            ):
                mismatch_note = f" This confirms the disclosed {value_desc} values do not align with the reporting year {self.reporting_year}, reinforcing their historical nature."

            return f" (for a prior year {self.year}, confirming only historical use before the reporting year {self.reporting_year}{maturity_reason}).{mismatch_note}"

        elif self.year > self.reporting_year:
            return f" (for a future year {self.year}, indicating expected or forward activity beyond the reporting year {self.reporting_year}{maturity_reason})."

        return ""

    def _validate_temporal_consistency(self) -> Optional[str]:
        """Detect inconsistent or ambiguous temporal relationships."""
        # If either temporal anchor missing we skip warnings here.
        if not self.reporting_year or not self.year:
            return None

        if self.status == "terminated" and self.year > self.reporting_year:
            return f"[Warning] Terminated instrument dated in the future ({self.year}) after reporting year {self.reporting_year}."
        if self.status == "new" and self.year > self.reporting_year:
            return f"[Warning] 'New' instrument refers to a future year {self.year} beyond reporting year {self.reporting_year}."
        if self.status == "no_instruments" and self.notional and self.notional > 0:
            return f"[Warning] 'No instruments' status conflicts with positive notional value {self.notional}."
        if self.status == "summary" and self.notional is not None and self.notional < 0:
            return f"[Warning] Negative notional value ({self.notional}) is not valid for a summary disclosure."
        return None

    # ---------------------------------------------------------------------
    # Core logic
    # ---------------------------------------------------------------------

    def to_string(self) -> str:
        """Generates a reasoning statement with built-in time validation and generic-category handling."""
        # Category handling with generic classification note
        if self.category in (None, "GEN"):
            category_name = ""
            category_context = "general derivative activity"
            classification_note = (
                " Based on the surrounding context, the disclosure does not specify a clear derivative category "
                "such as interest rate, foreign exchange, commodity, or equity, so it is treated as a generic reference "
                "and I'll come back to it later."
            )
        else:
            category_name = self._category_label()
            category_context = f"{category_name} derivative activity"
            classification_note = ""

        value_desc = (
            "fair value" if self.value_type == "fair_value" else "notional value"
        )
        values_desc = (
            "fair values" if self.value_type == "fair_value" else "notional values"
        )

        # If both temporal anchors are missing, we still can report basic individual mentions.
        if self.year is None or self.reporting_year is None:
            # Allow certain statuses to function without full temporal anchors.
            temporal_info = self._temporal_reasoning(value_desc)  # will be empty string
        else:
            temporal_info = self._temporal_reasoning(value_desc)

        warning = self._validate_temporal_consistency()

        base_desc = (
            f"'{self.instrument_type}' {category_name} derivative"
            if self.instrument_type
            else f"{category_context}"
        )

        # -----------------------------------------------------------------
        # Template-driven status handlers (now consistently include temporal_info)
        # -----------------------------------------------------------------
        def summary_handler() -> str:
            if not self.notional_str and self.notional is None:
                return f"The report provides a summary for {category_context}, confirming activity but no {value_desc} was specified for {self.year}."
            if self.prev_notional_str and not self.notional_str and self.year and self.reporting_year and self.year < self.reporting_year and self.maturity_year:
                return (
                    f"The report references {category_context} with a prior-year {value_desc} of {self.prev_notional_str} for {self.year}. "
                    f"Although no current value is given for the reporting year ({self.reporting_year}), the maturity in {self.maturity_year} suggests it may still be active{temporal_info}"
                )
            if self.prev_notional_str:
                return (
                    f"The report provides an aggregate summary for {category_context}, comparing {values_desc} of {self.notional_str} for {self.year} "
                    f"against {self.prev_notional_str} for {self.prev_year}, indicating continuity{temporal_info}"
                )
            return f"The report mentions an aggregate {value_desc} of {self.notional_str} for {base_desc}{temporal_info}"

        def new_individual_handler() -> str:
            # New: if year == reporting_year we treat as current; otherwise report the year-based context
            prefix = f"The report describes a new {base_desc}"
            value_part = (
                f" with a {value_desc} of {self.notional_str}"
                if self.notional_str
                else ""
            )
            return f"{prefix}{value_part}{temporal_info}"

        def individual_handler() -> str:
            # Individual mention doesn't imply newness. Attach temporal_info if available.
            prefix = f"The report mentions an individual {base_desc}"
            value_part = (
                f" with a {value_desc} of {self.notional_str}"
                if self.notional_str
                else ""
            )
            return f"{prefix}{value_part}{temporal_info}"

        def terminated_individual_handler() -> str:
            if not self.notional_str and self.notional is None:
                return f"The report indicates a {base_desc} was terminated, confirming prior existence but no {value_desc} was disclosed{temporal_info}"
            return f"The report describes a terminated {base_desc} with a prior {value_desc} of {self.notional_str}. Its absence in {self.reporting_year} data indicates settlement or maturity{temporal_info}"

        def no_instruments_handler() -> str:
            return f"The report explicitly states there were no outstanding {category_name} instruments in {self.reporting_year}, confirming no current use{temporal_info}"

        def comparative_handler() -> str:
            # General comparative uses summary logic
            return summary_handler()

        def comparative_no_outstanding_handler() -> str:
            return (
                f"The report confirms no outstanding {category_context} in {self.reporting_year}, "
                f"compared to a prior {value_desc} of {self.prev_notional_str} in {self.prev_year}, indicating termination of activity{temporal_info}"
            )

        def comparative_no_prior_outstanding_handler() -> str:
            return (
                f"The report shows a current {value_desc} of {self.notional_str} for {category_context} in {self.reporting_year}, "
                f"with no such instruments outstanding in the prior year, indicating new activity{temporal_info}"
            )

        def historical_individual_handler() -> str:
            # Historical individual mention uses the individual wording but relies on temporal_info for history
            return individual_handler()

        # Map statuses to handlers
        handlers: Dict[str, Callable[[], str]] = {
            "summary": summary_handler,
            "new_individual": new_individual_handler,
            "individual": individual_handler,
            "terminated_individual": terminated_individual_handler,
            "no_instruments": no_instruments_handler,
            "comparative": comparative_handler,
            "comparative_no_outstanding": comparative_no_outstanding_handler,
            "comparative_no_prior_outstanding": comparative_no_prior_outstanding_handler,
            "historical_individual": historical_individual_handler,
        }

        # Dispatch
        text = handlers.get(
            self.status,
            lambda: f"Uncategorized notional evidence found for {category_name}.",
        )()

        # Append warning and classification note if present
        if warning:
            text = f"{text} {warning}"
        if classification_note:
            text = f"{text}{classification_note}"

        return text.strip()

@dataclass
class PolicyEvidence(BaseNarrativeEvidence):
    """Evidence related to a company's hedging policies or risk exposure."""
    details: str = "" # The core statement of the policy or risk.
    policy_type: Literal[
        "risk_exposure",
        "hedging_strategy",
        "effectiveness_testing",
        "accounting_treatment",
    ] = "risk_exposure"

    def to_string(self) -> str:
        """Generates a reasoning statement for the policy evidence."""
        return f"The report includes a {self.policy_type.replace('_', ' ')} statement for the {self.category} category: '{self.details}'."

@dataclass
class PolicySentence:
    """A data class to hold components for generating a policy or risk context sentence."""
    category: DerivativeCategory
    company_name: str    
    currencies: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)

    # Add result_details for consistency with NotionalSentence
    result_details: Optional["ResultPhraseDetails"] = None

    def build(self) -> Tuple[str, PolicyEvidence]:
        """Builds a policy sentence and a corresponding PolicyEvidence object."""
        templates = POLICY_CONTEXT_TEMPLATES.get(self.category, POLICY_CONTEXT_TEMPLATES["GEN"])
        template = random.choice(templates)

        # Populate placeholders
        # TODO: Replace hardcoded fallback strings like "various foreign currencies" with more dynamic generation.
        # Format currencies and locations into human-readable strings
        currencies_str = "various foreign currencies"
        if self.currencies:
            currencies_str = ", ".join(self.currencies[:-1]) + " and " + self.currencies[-1] if len(self.currencies) > 1 else self.currencies[0]

        # TODO: Replace hardcoded fallback strings like f"international {random.choice(geo_locations)}" with more dynamic generation.
        locations_str = f"international {random.choice(geo_locations)}"
        if self.locations:
            locations_str = ", ".join(self.locations[:-1]) + " and " + self.locations[-1] if len(self.locations) > 1 else self.locations[0]

        details = self.result_details or ResultPhraseDetails()
        risk_terms = random.sample(risk_exposure_terms, k=2)
        sentence = template.format(
            # TODO: These random.choice() calls are selecting from dummy data lists. This logic will be replaced by the generative model.
            company=self.company_name,
            ir_term=random.choice(interest_rate_terms),
            debt_type=details.debt_type or "debt",
            risk_term=risk_terms[0],
            risk_term2=risk_terms[1],
            policy_verb=random.choice(policy_verbs),
            risk_action_verb=random.choice(risk_management_verbs),  # type: ignore
            currencies=currencies_str,
            locations=locations_str,
            commodity=details.commodity or "various commodities",
            cost_type=random.choice(get_cost_types_for_commodity(details.commodity)),
        )

        # Create evidence object
        evidence = PolicyEvidence(category=self.category, status="policy_mention", policy_type="risk_exposure", details=sentence)

        return sentence, evidence

T_HedgedItem = TypeVar("T_HedgedItem", bound="HedgedItem")


@dataclass
class DerivativeInstrument:
    """Base class for a single derivative instrument within our narrative.

    Args:
        instrument_id: int - A unique ID to track the same instrument across multiple years.
        instrument_type: str - The type of derivative instrument (e.g., "interest rate swap").
        instrument_prefix: Optional[str] - The prefix of the instrument (e.g., "pay-fixed").
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
        benchmark_rate: Optional[str] - Any type of rate.
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
    currency: str = "USD"
    benchmark_rate: Optional[str] = None
    spread_bps: Optional[int] = None
    fixed_rate_pct: Optional[float] = None
    change_rate_pct: Optional[float] = None
    payment_amount: Optional[int] = None
    payment_frequency: Optional[str] = None


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
        DerivativeCategory, Tuple[float, float]
    ]  # Per-category likelihood of hedging (past, current).
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
    """Contains all policy-related information for The report."""

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
class ResultPhraseDetails:
    """Holds specific details for populating a result_phrase template."""
   
    frequency: Optional[str] = None
    
    # FX specific
    geography: Optional[str] = None
    currencies: List[str] = field(default_factory=list)

    # CP specific
    commodity: Optional[str] = None
    unit: Optional[str] = None

    # IR specific (debt_type is primarily for IR)
    pct: Optional[float] = None
    debt_type: Optional[str] = None


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
    currency_code: str = "US Dollar"
    money_unit_word: str = "million"
    value_type: Literal["notional", "fair_value"] = "notional"
    sentence_type: Literal[
        "summary", # phrases stating total amount across all derivative type
        "new_individual", # phrases with new swap in past or current year
        "individual", # phrases with any swap in past or current year
        "terminated_individual", # phrases an individual swap being terminated in past or current year
        "historical_individual", # phrases with a swap in an old year that expires in past or future year
        "comparative", # Phrases with comparative values
        "comparative_no_outstanding", # Phrases with explicit mention of no outstanding for current year, values in past
        "comparative_no_prior_outstanding", # Phrases with current value for current year, but no other values in prior
        "no_instruments", # No such derivatives at all
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
    maturity_year: Optional[int] = None
    commodity: Optional[str] = None
    result_details: Optional[ResultPhraseDetails] = None
    reporting_year: Optional[int] = None

    # Formatting preferences
    money_units: List[Tuple[str, int]] = field(
        default_factory=lambda: [("million", 1_000_000)]
    )
    prefer_abbreviated: bool = True

    def build(self) -> Tuple[str, NotionalEvidence]:
        """
        Builds a notional sentence and a corresponding NotionalEvidence object.
        Returns: A tuple of (sentence_string, NotionalEvidence_instance).
        """

        # Default values for optional components
        month = self.month or random.choice(months)
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
            self.notional,
            self.currency_symbol,
            self.money_units,
            self.prefer_abbreviated,
        )
        formatted_prev_notional = None
        formatted_prev2_notional = None

        if num_years == 1:
            amount_str = formatted_notional
        elif num_years == 2:
            assert self.prev_notional is not None
            formatted_prev_notional = _format_single_notional(  # type: ignore
                self.prev_notional,
                self.currency_symbol,
                self.money_units,
                self.prefer_abbreviated,
            )
            amount_str = f"{formatted_notional} and {formatted_prev_notional}"
        elif num_years == 3:
            assert self.prev_notional is not None and self.prev2_notional is not None
            formatted_prev_notional = _format_single_notional(  # type: ignore
                self.prev_notional,
                self.currency_symbol,
                self.money_units,
                self.prefer_abbreviated,
            )
            formatted_prev2_notional = _format_single_notional(  # type: ignore
                self.prev2_notional,
                self.currency_symbol,
                self.money_units,
                self.prefer_abbreviated,
            )
            amount_str = f"{formatted_notional}, {formatted_prev_notional}, and {formatted_prev2_notional}"

        # 2. Select time prefix template
        time_prefix = ""
        time_suffix = ""
        # TODO: The logic for selecting and formatting time prefixes/suffixes is template-based and should be replaced by generative logic.
        if self.sentence_type in ["summary", "comparative", "no_instruments"]:
            if num_years == 1:
                time_prefix = random.choice(point_in_time_prefixes)
            elif num_years == 2:
                time_prefix = random.choice(multi_year_time_prefixes["two_year"])
            else:  # num_years == 3
                time_prefix = random.choice(multi_year_time_prefixes["three_year"])
        elif self.sentence_type in ["new_individual", "terminated_individual"]:
            time_prefix = random.choice(period_of_time_prefixes)

        time_prefix = time_prefix.format(
            month=month,
            end_day=end_day,
            year=self.year,
            prev_year=self.prev_year,
            prev2_year=self.prev2_year,
            quarter=quarter,
        )
        if num_years == 2:
            time_suffix = f"as of {month} {end_day}, {self.year} and {self.prev_year}, respectively"
        elif num_years == 3:
            time_suffix = f"as of {month} {end_day}, {self.year}, {self.prev_year}, and {self.prev2_year}, respectively"
        else:
            time_suffix = f"as of {month} {end_day}, {self.year}"

        # 3. Select verb
        verb = self.verb
        if verb is None:
            if self.sentence_type == "new_individual":
                verb = random.choice(individual_use_verbs)
            elif self.sentence_type == "terminated_individual":
                verb = random.choice(termination_verbs_past)
            else:  # summary, comparative
                verb = random.choice(aggregate_use_verbs)

        # 4. Select amount connector
        # Choose from the specific list if available, otherwise fall back to generic
        specific_connectors = amount_connectors.get(self.value_type, [])
        all_possible_connectors = specific_connectors + amount_connectors["generic"]
        chosen_connector = random.choice(all_possible_connectors)

        # 4b. Select amount prefix (for templates that don't use a company/verb)
        specific_prefixes = amount_prefixes.get(self.value_type, [])
        all_possible_prefixes = specific_prefixes + amount_prefixes["generic"]
        chosen_prefix = random.choice(all_possible_prefixes)

        # --- Refine value_type based on the chosen connector/prefix ---
        # If a generic term was chosen, it's more likely to be interpreted as 'notional' in a real filing.
        final_value_type = self.value_type
        is_generic_connector = chosen_connector in amount_connectors["generic"]
        is_generic_prefix = chosen_prefix in amount_prefixes["generic"]
        if (
            is_generic_connector or is_generic_prefix
        ) and self.value_type == "fair_value":
            final_value_type = "notional"

        # 5. Hedge designation clause
        # TODO: Replace hardcoded hedge designation clauses with generative logic.
        hedge_designation_clause = ""
        if self.hedge_designation:
            hedge_designation_clause = self.hedge_designation.format(
                hedge_type=random.choice(hedge_types)
            )

        # 6. Result phrase clause
        # TODO: The construction of the result_clause is template-based and should be replaced by generative logic.
        result_clause = ""
        if self.result_phrase:
            # Populate new placeholders within the result phrase itself
            outcome_verb = random.choice(financial_outcome_verbs)
            outcome_loc = random.choice(balance_sheet_locations)

            # Choose two different specific rate terms for templates that need them
            rate_terms = random.sample(specific_rate_terms, 2)
            rate_term1 = rate_terms[0]
            rate_term2 = rate_terms[1]

            # Generate a random amount for the result phrase and format it
            random_amount = int(self.notional * random.randint(1, 50) / 100)
            formatted_amount_result = _format_single_notional(
                random_amount,
                self.currency_symbol,
                self.money_units,
                self.prefer_abbreviated,
            )
            # Format currencies into a readable string from the details object
            details = self.result_details or ResultPhraseDetails()
            currencies_str = ""
            if details.currencies:
                currencies_str = (
                    ", ".join(details.currencies[:-1])
                    + " and "
                    + details.currencies[-1]
                    if len(details.currencies) > 1
                    else details.currencies[0]
                )

            details = self.result_details or ResultPhraseDetails()
            risk_terms = random.sample(risk_exposure_terms, k=2)
            populated_phrase = self.result_phrase.format(
                mitigation_verb=random.choice(risk_management_verbs),
                gain_loss=random.choice(gain_loss_phrases),
                outcome_location=f"{outcome_verb} {outcome_loc}",
                frequency=details.frequency or random.choice(frequencies),
                risk_term=risk_terms[0],
                risk_term2=risk_terms[1],
                ir_term=random.choice(interest_rate_terms),  # type: ignore
                debt_type=details.debt_type or "debt",
                currencies=currencies_str,
                currency_code=self.currency_code,
                rate_term1=rate_term1,
                rate_term2=rate_term2,
                formatted_amount=formatted_amount_result,  # type: ignore
                pct=details.pct or random.uniform(1.5, 7.5),
                geography=details.geography or random.choice([c.location for c in all_currencies]),  # type: ignore
                commodity=details.commodity,
                unit=details.unit,
                financial_outcome_verb=random.choice(financial_outcome_verbs),
            )
            result_clause = populated_phrase

        # 6b. Maturity clause, only if the type of sentence is is_ter
        maturity_clause = ""
        if (
            self.maturity_year
            and self.reporting_year
            and self.sentence_type in ["historical_individual", "terminated_individual"]
        ):
            if self.maturity_year > self.reporting_year:
                adverb = random.choice(future_adverbs)
                verb_tense = random.choice([v for v in termination_verbs_present if not v.endswith('ed')]) # Ensure present tense
                maturity_clause = f"which {adverb} {verb_tense} in {self.maturity_year}"
            else:  # maturity_year <= reporting_year
                verb_tense = random.choice([v for v in termination_verbs_past if v.endswith('ed')]) # Ensure past tense
                maturity_clause = f"which {verb_tense} in {self.maturity_year}"

        # 7. Select main sentence template
        templates_for_type = NOTIONAL_SENTENCE_TEMPLATES.get(
            self.sentence_type, NOTIONAL_SENTENCE_TEMPLATES["summary"]
        )
        template = random.choice(templates_for_type)

        # --- NEW LOGIC: Check if the template actually uses a notional amount placeholder. ---
        mentions_amount = (
            "{amount_str}" in template
            or "{amount_connector}" in template
            or "{amount_prefix}" in template
        )
        final_notional = self.notional if mentions_amount else None
        final_formatted_notional = formatted_notional if mentions_amount else None
        final_formatted_prev_notional = (
            formatted_prev_notional if mentions_amount else None
        )
        final_formatted_prev2_notional = (
            formatted_prev2_notional if mentions_amount else None
        )

        # Handle "no_instruments" case specifically
        if self.sentence_type == "no_instruments":
            # TODO: This entire block for "no_instruments" uses hardcoded templates and should be replaced by generative logic.
            # Select a template from the new list
            template = random.choice(NO_INSTRUMENTS_TEMPLATES)
            category_map = {
                "IR": "interest rate",
                "FX": "foreign currency",
                "CP": "commodity price",
                "EQ": "equity",
                "GEN": "",
            }
            # Define a descriptive phrase for the category
            category_risk_phrase = category_map.get(self.category or "GEN", "")

            # Populate the chosen template
            sentence = template.format(
                time_prefix=time_prefix,
                company=company_name,
                verb=random.choice(non_use_verbs),  # e.g., "did not hold"
                swap_type=(f"{self.swap_type}" or f"{category_risk_phrase} derivative") + "s",
                category_risk_phrase=category_risk_phrase,  # type: ignore
                time_suffix=time_suffix,
                year=self.year,
                month=month,
                end_day=end_day,
                state_descriptor=random.choice(state_descriptors),
                immaterial_term=random.choice(immaterial),
                portfolio_term=random.choice(portfolio_terms).format(
                    swap_type=(f"{self.swap_type}"
                    or f"{category_risk_phrase} derivative") + "s"
                ),
            )
            evidence = NotionalEvidence(
                status="no_instruments",
                category=self.category,  # type: ignore
                notional=0,
                instrument_type="none",
                year=self.year,
                prev_year=self.prev_year,
                prev2_year=self.prev2_year,
                currency=self.currency_code,
                reporting_year=self.reporting_year,
                sentence_type=self.sentence_type,
            )
            return sentence, evidence

        # 8. Populate placeholders
        sentence = template.format(
            time_prefix=time_prefix,
            company=company_name,
            verb=verb,
            swap_type=self.swap_type,
            amount_connector=chosen_connector,
            amount_prefix=chosen_prefix,
            amount_str=amount_str,
            hedge_designation_clause=hedge_designation_clause,
            state_descriptor=random.choice(state_descriptors),
            historical_phrase=random.choice(historical_instrument_phrases),
            result_clause=result_clause,
            portfolio_term=random.choice(portfolio_terms).format(
                    swap_type=f"{self.swap_type}" + "s"
                ),
            portfolio_verb=random.choice(portfolio_verbs),
            maturity_clause=maturity_clause,
            time_suffix=time_suffix,
        )

        # 9. Cleanup
        sentence = _cleanup_sentence(sentence)

        # 10. Create NotionalEvidence object
        evidence = NotionalEvidence(
            instrument_id=None,  # This will be set later for individual instruments
            status=self.sentence_type,  # type: ignore
            category=self.category,  # type: ignore
            aggregate=self.sentence_type in ["summary", "comparative"],
            notional=final_notional,  # Use the conditional notional value
            year=self.year,
            prev_year=self.prev_year,
            prev2_year=self.prev2_year,
            instrument_type=self.swap_type,
            notional_str=final_formatted_notional,
            prev_notional_str=final_formatted_prev_notional,
            prev2_notional_str=final_formatted_prev2_notional,
            maturity_year=self.maturity_year,
            reporting_year=self.reporting_year,
            value_type=final_value_type,
            sentence_type=self.sentence_type,
        )

        return sentence, evidence
