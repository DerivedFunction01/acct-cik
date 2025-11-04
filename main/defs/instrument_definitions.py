from typing import Dict, Generic, List, Literal, Optional, TypeVar
from dataclasses import dataclass, field

# Define a central, single source of truth for derivative categories.
DERIVATIVE_CATEGORIES = ("IR", "FX", "CP", "EQ", "GEN")
DerivativeCategory = Literal["IR", "FX", "CP", "EQ", "GEN"]

T_HedgedItem = TypeVar("T_HedgedItem", bound="HedgedItem")

@dataclass
class ContextSentence:
    """Base class for generating contextual sentences about a hedged item (exposure)."""

    hedged_item: "HedgedItem"
    company_name: str

    def build(self) -> str:
        """Builds a contextual sentence. This should be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement the build() method.")

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
class SpecificDetails:
    """Holds specific details for populating a result_phrase template."""

    frequency: Optional[str] = None

    # FX specific
    geography: List[str] = field(default_factory=list)
    currencies: List[str] = field(default_factory=list)

    # CP specific
    commodity: List[str] = field(default_factory=list)
    unit: Optional[str] = None

    # IR specific (debt_type is primarily for IR)
    pct: Optional[float] = None
    debt_type: Optional[str] = None


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
    placeholder: str
    base_type: str
    symbol: str
    suffix: str
    category: DerivativeCategory
    start_month: str
    start_year: int
    maturity_month: Optional[str] = None
    maturity_year: Optional[int] = None

    def to_dict(self) -> Dict:
        """Serializes the common instrument data to a dictionary for JSON output."""
        return {
            "instrument_id": self.instrument_id,
            "instrument_type": self.instrument_type,
            "instrument_prefix": self.instrument_prefix,
            "instrument_alias": self.instrument_alias,
            "placeholder": self.placeholder,
            "base_type": self.base_type,
            "suffix": self.suffix,
            "category": self.category
        }


@dataclass
class NotionalInstrument(DerivativeInstrument, Generic[T_HedgedItem]):
    """A derivative instrument primarily defined by a notional amount.

    Args:
        notional_amount: int - The notional amount of the instrument.
        currency: str - The currency of the instrument.
        hedged_item: Optional[T_HedgedItem] - The item being hedged by this instrument.
    """

    notional_history: Dict[int, int] = field(
        default_factory=dict
    )  # {year: notional_amount}
    currency: str = "USD"
    hedged_item: Optional[T_HedgedItem] = None
    maturity_value: Optional[int] = 0

    def to_dict(self) -> Dict:
        """Extends the base to_dict to include notional-specific fields."""
        # This now correctly handles the nested HedgedItem object.
        data = super().to_dict()
        data.update(
            {
                "notional_history": self.notional_history,
                "currency": self.currency,
                "hedged_item": self.hedged_item.to_dict() if self.hedged_item else None,
            }
        )
        return data


class GenericInstrument(NotionalInstrument[HedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="GEN", **kwargs)


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
class AccountingStandardEvidence(BaseNarrativeEvidence):
    """Evidence related to the adoption or evaluation of an accounting standard."""

    standard_name: str = ""
    adoption_status: Literal["adopted", "evaluating", "will_adopt", "monitoring", "issuance"] = "monitoring"
    details: str = "" # The specific sentence providing the evidence


@dataclass
class ContextEvidence(BaseNarrativeEvidence):
    """Evidence that a sentence provides context about a risk exposure but does not mention a derivative."""

    details: str = ""

    def to_string(self) -> str:
        """Generates a reasoning statement for the contextual evidence."""
        exposure_type_map = {
            "IR": "interest rate risk from debt obligations",
            "FX": "foreign currency exchange risk",
            "CP": "commodity price risk",
            "EQ": "equity price risk",
            "LAW": "legal proceedings",
            "GEN": "general market risks",
        }
        exposure_description = exposure_type_map.get(
            self.category, "an unknown risk category"
        )
        return f"The text discusses exposure to {exposure_description} but does not mention any derivative instruments used to hedge this exposure."