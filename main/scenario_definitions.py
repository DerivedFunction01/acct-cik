from dataclasses import dataclass, field
from typing import List, Literal, Optional, Dict, TypeVar, Generic
import random
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
    """Represents a piece of evidence extracted from the generated narrative."""
    category: DerivativeCategory
    instrument_type: str
    notional: int
    status: Literal["summary", "new", "terminated", "none"]

    def to_dict(self) -> Dict:
        return self.__dict__

T_HedgedItem = TypeVar("T_HedgedItem", bound="HedgedItem")


@dataclass
class DerivativeInstrument:
    """Base class for a single derivative instrument within our narrative."""

    instrument_id: (
        int  # A unique ID to track the same instrument across multiple years.
    )
    instrument_type: str
    category: DerivativeCategory  # The category of the derivative
    month: str  # The month this state of the instrument is for.
    year: int  # The year this state of the instrument is for.
    hedge_designation: Optional[str] = None
    maturity_month: Optional[str] = None  # The maturity month
    maturity_year: Optional[int] = None  # The maturity year

    def to_dict(self) -> Dict:
        """Serializes the common instrument data to a dictionary for JSON output."""
        return {
            "instrument_id": self.instrument_id,
            "instrument_type": self.instrument_type,
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
    """Represents a debt instrument being hedged (for IR derivatives)."""

    debt_type: str  # e.g., "variable-rate credit facility", "senior notes", "term loan"
    issuance_month: Optional[str]
    issuance_year: int
    maturity_month: Optional[str]
    maturity_year: int
    principal_amount: int
    interest_rate_type: Literal["fixed", "variable"]
    benchmark_rate: Optional[str] = None  # e.g., "LIBOR", "SOFR"
    spread_bps: Optional[int] = None  # Basis points over the benchmark
    fixed_rate_pct: Optional[float] = None  # The fixed rate percentage
    change_rate_pct: Optional[float] = None  # The new rate percentage
    payment_amount: Optional[int] = None  # The payment amount
    payment_frequency: Optional[str] = None  # Payment frequency


@dataclass
class CurrencyExposure:
    """Represents a specific currency exposure with its amount."""

    code: str  # e.g., "EUR", "GBP"
    name: str  # e.g., "Euro", "British Pound"
    symbol: str  # e.g., "€", "£"
    amount: int  # The notional amount of the exposure in that currency


@dataclass
class ForeignCurrencyHedgedItem(HedgedItem):
    """Represents foreign currency exposure being hedged (for FX derivatives)."""

    exposures: List[CurrencyExposure] = field(default_factory=list)


@dataclass
class CommodityHedgedItem(HedgedItem):
    """Represents a commodity being hedged (for CP derivatives)."""

    commodity_type: str
    quantity: int
    unit_of_volume: str
    price_per_unit: float
    cost_type: str  # Ex. input, extraction, storage
    transaction_type: Literal["purchase", "sale"]
    supplier: Optional[str]  # Ex. a third party supplier


@dataclass
class EquityHedgedItem(HedgedItem):
    """Represents an equity instrument being hedged (for EQ derivatives)."""

    # Placeholder for future implementation
    underlying_equity: str  # e.g., "S&P 500 Index", "Company Common Stock"
    equity_type: Literal["market_index", "own_stock", "third_party_stock"]
    reason: str


@dataclass
class NotionalInstrument(DerivativeInstrument, Generic[T_HedgedItem]):
    """A derivative instrument primarily defined by a notional amount."""

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
