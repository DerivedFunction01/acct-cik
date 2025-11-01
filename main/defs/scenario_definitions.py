from dataclasses import dataclass, field
from typing import List, Literal, Optional, Dict, TypeVar, Generic, Tuple
import random

from defs.instrument_definitions import DerivativeCategory, NotionalInstrument
from defs.policy_definitions import AccountingStandardUpdate, RiskManagementPolicy


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
    commodity_types: List[str] = field(
        default_factory=list
    )  # e.g. ["energy", "metals_minerals"]

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
