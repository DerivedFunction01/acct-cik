# %%
import random
import pandas as pd
import re
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import json
from dataclasses import field
import multiprocessing as mp
import math
from dataclasses import dataclass
from typing import List, Literal, Optional, Dict, TypeVar, Generic

from template.hedges import *
from template.common import *
from template.other import *
from template.w_emb import *
from template.tabular import *

output_file = "./training_data.xlsx"
company_name_file = "./names.xlsx"

# %%

company_name_df = pd.read_excel(company_name_file)
company_names = list(company_name_df["name"])


def pick_company_name(company_name: str) -> str:
    return random.choices([company_name, "The Company"], weights=[0.75, 0.25], k=1)[0]


def generate_value(haveZero=True, lowerlimit=1, upperlimit=1000, dashed=False):
    """Generate a random previous notional value with chance of being zero,
    and optional rounding for variability. Returns int if whole, else float."""
    if haveZero:
        chance = 0.15
    else:
        chance = 0

    upperlimit = int(upperlimit)
    value = (
        0.0
        if random.random() < chance
        else (1 if upperlimit <= 1 else random.randint(lowerlimit, upperlimit))
    )

    if value == 0.0 and dashed and random.random() < 0.05:
        return "--"

    if random.random() < 0.5:
        divisor = random.choice([10, 100])
        decimals = random.randint(1, 2)
        value = round(value / divisor, decimals)

    # Cast to int if it's a whole number with 50% chance
    if isinstance(value, float) and value.is_integer() and random.random() < 0.5:
        value = int(value)

    return value


# %%
# =============================================================================
# PHASE 1: SCENARIO DEFINITION - CLASS DEFINITION
# This section implements the core idea: "Decide the story upfront."
# We define the state of our financial narrative using structured dataclasses.
# =============================================================================

# Define a central, single source of truth for derivative categories.
DERIVATIVE_CATEGORIES = ("IR", "FX", "CP", "EQ", "GEN")
DerivativeCategory = Literal["IR", "FX", "CP", "EQ", "GEN"]

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

    currency: str  # e.g., "EUR", "GBP"
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

    def __post_init__(self):
        """Sets the category based on the class type after initialization."""
        if self.__class__ == IRInstrument:
            self.category = "IR"
        elif self.__class__ == FXInstrument:
            self.category = "FX"
        elif self.__class__ == CPInstrument:
            self.category = "CP"
        elif self.__class__ == EQInstrument:
            self.category = "EQ"
        elif self.__class__ == GenericInstrument:
            self.category = "GEN"
        else:
            raise ValueError(f"Unknown instrument type: {self.__class__}")


# Specific instrument types can now be defined cleanly.
# We can add more specific fields to each type later if needed.
class IRInstrument(NotionalInstrument[DebtHedgedItem]):
    pass


class FXInstrument(NotionalInstrument[ForeignCurrencyHedgedItem]):
    pass


class CPInstrument(NotionalInstrument[CommodityHedgedItem]):
    pass


class EQInstrument(NotionalInstrument[EquityHedgedItem]):
    pass


class GenericInstrument(NotionalInstrument[HedgedItem]):
    pass


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
class RiskManagementPolicy:
    """Contains all policy-related information for the narrative."""

    general_policy: GeneralHedgingPolicy = field(default_factory=GeneralHedgingPolicy)
    category_policies: List[CategorySpecificPolicy] = field(default_factory=list)


@dataclass
class GenerationScenario:
    """Holds the entire state for a single, coherent training example."""

    company_name: str
    reporting_year: int
    instruments: List[NotionalInstrument] = field(default_factory=list)
    policy: Optional[RiskManagementPolicy] = None


# =============================================================================
# DUMMY DATA ARRAYS FOR RANDOM GENERATION
# These can be expanded and mapped to your old templates.
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
DUMMY_CURRENCIES = ["EUR", "GBP", "JPY", "CAD", "AUD"]
DUMMY_BENCHMARK_RATES = ["SOFR", "LIBOR", "EURIBOR"]
DUMMY_HEDGE_DESIGNATIONS = ["cash_flow", "fair_value", "net_investment", "economic"]
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
DUMMY_COMMODITY_UNITS = ["MMBtu", "barrels", "metric tons"]
DUMMY_COMMODITY_TRANSACTION_TYPES: List[Literal["purchase", "sale"]] = [
    "purchase",
    "sale",
]
DUMMY_DEFAULT_CURRENCY = "USD"

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


@dataclass
class ScenarioArchetype:
    """Defines the instrument profile for a type of company to make generation more realistic."""

    name: str
    ir_range: tuple[int, int]
    fx_range: tuple[int, int]
    cp_range: tuple[int, int]
    eq_range: tuple[int, int]
    gen_range: tuple[int, int]
    policy_coverage: Literal["full", "partial", "light"]

    def get_instrument_counts(self) -> Dict[str, int]:
        """Generates a dictionary of instrument counts based on the archetype's ranges."""
        return {
            "IR": random.randint(*self.ir_range),
            "FX": random.randint(*self.fx_range),
            "CP": random.randint(*self.cp_range),
            "EQ": random.randint(*self.eq_range),
            "GEN": random.randint(*self.gen_range),
        }


# Define a list of company archetypes to choose from during generation.
SCENARIO_ARCHETYPES = [
    ScenarioArchetype(
        name="Large Multinational",
        ir_range=(2, 4),
        fx_range=(2, 5),
        cp_range=(1, 3),
        eq_range=(0, 2),
        gen_range=(0, 1),
        policy_coverage="full",
    ),
    ScenarioArchetype(
        name="Domestic Industrial",
        ir_range=(1, 3),
        fx_range=(0, 2),
        cp_range=(2, 4),
        eq_range=(0, 1),
        gen_range=(0, 1),
        policy_coverage="partial",
    ),
    ScenarioArchetype(
        name="Tech Company",
        ir_range=(0, 2),
        fx_range=(1, 4),
        cp_range=(0, 0),
        eq_range=(1, 3),
        gen_range=(0, 1),
        policy_coverage="partial",
    ),
    ScenarioArchetype(
        name="Financial Institution",
        ir_range=(2, 5),
        fx_range=(2, 5),
        cp_range=(0, 1),
        eq_range=(0, 2),
        gen_range=(0, 1),
        policy_coverage="full",
    ),
    ScenarioArchetype(
        name="Policy Only / Light User",
        ir_range=(0, 1),
        fx_range=(0, 1),
        cp_range=(0, 0),
        eq_range=(0, 0),
        gen_range=(1, 2),
        policy_coverage="light",
    ),
]

# =============================================================================
# PHASE 1 PART 2: SCENARIO GENERATION
# This section implements the core idea: "Decide the story upfront."
# We define the state of our financial narrative using structured dataclasses.
# =============================================================================


def generate_policy_for_archetype(
    archetype: ScenarioArchetype, instrument_counts: Dict[str, int]
) -> RiskManagementPolicy:
    """Generates a realistic RiskManagementPolicy based on the company archetype and instrument usage."""

    general_policy = GeneralHedgingPolicy(
        does_not_use_for_trading=True,
        counterparty_credit_risk_monitored=True,
        counterparty_details=random.choice(
            [
                "major financial institutions",
                "a diversified group of highly-rated financial institutions",
            ]
        ),
    )

    category_policies = []
    active_categories = [
        cat
        for cat, count in instrument_counts.items()
        if count > 0 and cat not in ["GEN", "EQ"]
    ]

    # Determine how many specific policies to create based on the archetype
    if archetype.policy_coverage == "full":
        # These firms likely have a policy for every risk category they manage
        num_policies_to_generate = len(active_categories)
    elif archetype.policy_coverage == "partial":
        # These firms might have 1 or 2 core policies
        num_policies_to_generate = random.randint(1, min(2, len(active_categories)))
    else:  # "light"
        num_policies_to_generate = random.randint(0, min(1, len(active_categories)))

    # Create the specific policies
    if active_categories and num_policies_to_generate > 0:
        categories_with_policies = random.sample(
            active_categories, num_policies_to_generate
        )
        for category in categories_with_policies:
            policy = CategorySpecificPolicy(
                category=category,  # type: ignore
                effectiveness_testing_method=random.choice(DUMMY_EFFECTIVENESS_METHODS),
                effectiveness_frequency=random.choice(DUMMY_EFFECTIVENESS_FREQUENCIES),
                accounting_policy_description=random.choice(
                    list(DUMMY_ACCOUNTING_DESCRIPTIONS.values())
                ),
            )
            category_policies.append(policy)

    return RiskManagementPolicy(
        general_policy=general_policy, category_policies=category_policies
    )


def create_random_scenario() -> GenerationScenario:
    """
    Creates a random, complex scenario by building a structured `GenerationScenario` object.
    This function acts as the "story planner," deciding upfront which instruments
    a company has, their status (active or terminated), and their key properties.
    """
    reporting_year = random.randint(2020, 2024)

    # --- Decide on a company archetype and get instrument counts ---
    archetype = random.choice(SCENARIO_ARCHETYPES)
    instrument_counts = archetype.get_instrument_counts()

    scenario = GenerationScenario(
        company_name=random.choice(company_names),
        reporting_year=reporting_year,
        instruments=[],
        policy=generate_policy_for_archetype(archetype, instrument_counts),
    )

    instrument_id_counter = 1
    hedged_item_id_counter = 1

    # --- Create IR Instruments ---
    for _ in range(instrument_counts["IR"]):
        is_terminated = (
            random.random() < 0.3
        )  # 30% chance of being a terminated instrument
        issuance_year = random.randint(reporting_year - 8, reporting_year - 1)
        hedged_debt = None
        notional = 0

        if is_terminated:
            maturity_year = random.randint(issuance_year + 1, reporting_year)
            notional = random.randint(5, 500) * 1_000_000
        else:
            maturity_year = random.randint(reporting_year + 2, reporting_year + 10)
            hedged_debt = DebtHedgedItem(
                hedged_item_id=hedged_item_id_counter,
                debt_type=random.choice(DUMMY_DEBT_TYPES),
                issuance_month=random.choice(months),
                issuance_year=issuance_year,
                maturity_month=random.choice(months),
                maturity_year=maturity_year,
                principal_amount=random.randint(5, 500) * 1_000_000,
                interest_rate_type="variable",
                benchmark_rate=random.choice(DUMMY_BENCHMARK_RATES),
                spread_bps=random.randint(100, 300),
            )
            notional = hedged_debt.principal_amount
            hedged_item_id_counter += 1

        ir_swap = IRInstrument(
            category="IR",
            instrument_id=instrument_id_counter,
            instrument_type=random.choice(DUMMY_IR_INSTRUMENT_TYPES),
            month=random.choice(months),
            year=reporting_year,
            notional_amount=notional,
            currency=DUMMY_DEFAULT_CURRENCY,
            maturity_year=maturity_year,
            hedge_designation=random.choice(DUMMY_HEDGE_DESIGNATIONS),
            hedged_item=hedged_debt,
        )
        instrument_id_counter += 1
        scenario.instruments.append(ir_swap)

    # --- Create FX Instruments ---
    for _ in range(instrument_counts["FX"]):
        is_terminated = random.random() < 0.3
        hedged_fx = None
        notional = 0

        if is_terminated:
            maturity_year = random.randint(reporting_year - 2, reporting_year)
            notional = random.randint(10, 200) * 1_000_000
        else:
            maturity_year = random.randint(reporting_year + 1, reporting_year + 3)
            num_exposures = random.randint(1, 3)
            exposures = [
                CurrencyExposure(
                    currency=cur, amount=random.randint(1, 100) * 1_000_000
                )
                for cur in random.sample(DUMMY_CURRENCIES, num_exposures)
            ]
            hedged_fx = ForeignCurrencyHedgedItem(
                hedged_item_id=hedged_item_id_counter, exposures=exposures
            )
            notional = sum(e.amount for e in exposures)  # Simplified USD equivalent
            hedged_item_id_counter += 1

        fx_instrument = FXInstrument(
            category="FX",
            instrument_id=instrument_id_counter,
            instrument_type=random.choice(DUMMY_FX_INSTRUMENT_TYPES),
            month=random.choice(months),
            year=reporting_year,
            notional_amount=notional,
            currency=DUMMY_DEFAULT_CURRENCY,
            maturity_year=maturity_year,
            hedge_designation=random.choice(DUMMY_HEDGE_DESIGNATIONS),
            hedged_item=hedged_fx,
        )
        instrument_id_counter += 1
        scenario.instruments.append(fx_instrument)

    # --- Create CP Instruments ---
    for _ in range(instrument_counts["CP"]):
        is_terminated = random.random() < 0.3
        hedged_commodity = None
        notional = 0

        if is_terminated:
            maturity_year = random.randint(reporting_year - 2, reporting_year)
            notional = random.randint(5, 100) * 1_000_000
        else:
            maturity_year = random.randint(reporting_year + 1, reporting_year + 5)
            notional = random.randint(5, 100) * 1_000_000
            hedged_commodity = CommodityHedgedItem(
                hedged_item_id=hedged_item_id_counter,
                commodity_type=random.choice(DUMMY_COMMODITY_TYPES),
                transaction_type=random.choice(DUMMY_COMMODITY_TRANSACTION_TYPES),
                quantity=random.randint(100, 10000),
                unit_of_volume=random.choice(DUMMY_COMMODITY_UNITS),
                price_per_unit=random.uniform(10, 200),
                cost_type=random.choice(cost_types),
                supplier=(
                    random.choice(company_names) if random.random() < 0.2 else None
                ),
            )
            hedged_item_id_counter += 1

        cp_instrument = CPInstrument(
            category="CP",
            instrument_id=instrument_id_counter,
            instrument_type=random.choice(DUMMY_CP_INSTRUMENT_TYPES),
            month=random.choice(months),
            year=reporting_year,
            notional_amount=notional,
            currency=DUMMY_DEFAULT_CURRENCY,
            maturity_year=maturity_year,
            hedge_designation=random.choice(DUMMY_HEDGE_DESIGNATIONS),
            hedged_item=hedged_commodity,
        )
        instrument_id_counter += 1
        scenario.instruments.append(cp_instrument)

    # --- Create EQ Instruments ---
    for _ in range(instrument_counts.get("EQ", 0)):
        is_terminated = random.random() < 0.3
        hedged_equity = None
        notional = 0

        if is_terminated:
            maturity_year = random.randint(reporting_year - 2, reporting_year)
            notional = random.randint(1, 50) * 1_000_000
        else:
            maturity_year = random.randint(reporting_year + 1, reporting_year + 5)
            notional = random.randint(1, 100) * 1_000_000
            hedged_equity = EquityHedgedItem(
                hedged_item_id=hedged_item_id_counter,
                underlying_equity=random.choice(DUMMY_EQUITY_UNDERLYINGS).format(
                    company_name=scenario.company_name
                ),
                equity_type=random.choice(DUMMY_EQUITY_TYPES),
                reason=random.choice(DUMMY_EQUITY_REASONS),
            )
            hedged_item_id_counter += 1

        eq_instrument = EQInstrument(
            category="EQ",
            instrument_id=instrument_id_counter,
            instrument_type=random.choice(DUMMY_EQ_INSTRUMENT_TYPES),
            month=random.choice(months),
            year=reporting_year,
            notional_amount=notional,
            currency=DUMMY_DEFAULT_CURRENCY,
            maturity_year=maturity_year,
            hedge_designation=random.choice(DUMMY_HEDGE_DESIGNATIONS),
            hedged_item=hedged_equity,
        )
        instrument_id_counter += 1
        scenario.instruments.append(eq_instrument)

    # --- Create Generic Instruments ---
    for _ in range(instrument_counts.get("GEN", 0)):
        is_terminated = random.random() < 0.4
        maturity_year = (
            random.randint(reporting_year - 3, reporting_year)
            if is_terminated
            else random.randint(reporting_year + 1, reporting_year + 5)
        )

        gen_instrument = GenericInstrument(
            category="GEN",
            instrument_id=instrument_id_counter,
            instrument_type=random.choice(DUMMY_GENERIC_INSTRUMENT_TYPES),
            month=random.choice(months),
            year=reporting_year,
            notional_amount=random.randint(10, 300) * 1_000_000,
            currency=DUMMY_DEFAULT_CURRENCY,
            maturity_year=maturity_year,
            hedge_designation=random.choice(DUMMY_HEDGE_DESIGNATIONS),
            hedged_item=None,  # Generic instruments often don't have a specific hedged item
        )
        instrument_id_counter += 1
        scenario.instruments.append(gen_instrument)

    return scenario


# %%
# =============================================================================
# PHASE 2: NARRATIVE AND JSON GENERATION
# These functions will take a `GenerationScenario` object and produce the
# final output: the narrative text and the structured JSON label.
# =============================================================================


def generate_narrative_from_scenario(scenario: GenerationScenario) -> str:
    """
    Constructs a coherent, multi-paragraph narrative from a scenario object.
    This function will replace the old `generate_hedge_paragraph`.
    """
    all_sentences = []

    # 1. Introduction (Market Risk Disclosure)
    # TODO: Use templates like `hedge_begin_context_templates`
    all_sentences.append(
        f"The company is exposed to market risks, primarily from changes in interest rates and foreign currency exchange rates."
    )

    # 2. Policy and Strategy
    if scenario.policy and scenario.policy.general_policy.does_not_use_for_trading:
        all_sentences.append(
            "Our risk management strategy involves the use of derivative instruments to mitigate these exposures."
        )
        all_sentences.append(
            "We do not enter into derivative contracts for trading or speculative purposes."
        )
    if (
        scenario.policy
        and scenario.policy.general_policy.counterparty_credit_risk_monitored
    ):
        all_sentences.append(
            f"Counterparty credit risk is managed by transacting with {scenario.policy.general_policy.counterparty_details}."
        )

    # 3. Specific Instrument Disclosure (The Core)
    # TODO: This is where the main logic will go. We'll loop through `scenario.instruments`
    # and use templates to describe each one.
    # This will be a much more involved step.
    all_sentences.append(
        f"As of December 31, {scenario.reporting_year}, the total notional of our outstanding interest rate swaps was $250.0 million."
    )
    all_sentences.append(
        f"During the first quarter of {scenario.reporting_year}, our portfolio of foreign currency forward contracts with a notional value of €25.0 million matured and were settled."
    )
    all_sentences.append(
        f"Subsequently, we entered into a series of foreign currency collar contracts with a total notional value of £40.0 million, which were outstanding at year-end."
    )
    all_sentences.append(
        f"The Company also has an embedded derivative liability related to its convertible senior notes, with a fair value of $12.5 million as of December 31, {scenario.reporting_year}."
    )

    # 4. Effectiveness and Accounting (if applicable)
    if scenario.policy and scenario.policy.category_policies:
        for cat_policy in scenario.policy.category_policies:
            if cat_policy.effectiveness_testing_method:
                all_sentences.append(
                    f"For our {cat_policy.category} derivative instruments, we assess hedge effectiveness on a {cat_policy.effectiveness_frequency} basis using the {cat_policy.effectiveness_testing_method}."
                )

    # TODO: Cleanup and formatting logic will go here.
    narrative = ". ".join(all_sentences) + "."
    return f"<reportingYear>{scenario.reporting_year}</reportingYear> {narrative}"


def generate_json_from_scenario(scenario: GenerationScenario, narrative: str) -> Dict:
    """
    Generates the target JSON output from the scenario object.
    The `narrative` is passed to help generate the summary and chain_of_thought.
    """

    # TODO: Implement logic to generate a dynamic summary and chain_of_thought.
    # For now, we'll use a hardcoded version based on our complex example.
    analysis_summary = "The company holds multiple active interest rate swaps, has recently entered into new foreign currency collars after settling previous forwards, and carries an embedded derivative liability from convertible notes."
    chain_of_thought = "The text details two separate interest rate swaps: one existing ($150M) and a new one ($100M), confirming 'current' IR use. For FX, it explicitly states that €25.0M in forwards 'matured and were settled', indicating termination. However, it then describes new, 'outstanding' foreign currency collars in GBP, confirming 'current' FX use. It also mentions a historic commodity swap and a current embedded derivative."

    derivatives_list = [inst.to_dict() for inst in scenario.instruments]

    return {
        "analysis_summary": analysis_summary,
        "chain_of_thought": chain_of_thought,
        "derivatives": derivatives_list,
    }


# %%
# =============================================================================
# PHASE 3: MAIN GENERATION LOOP
# This will be the new entry point, replacing the old `generate()` function.
# =============================================================================


def generate_training_sample():
    """Generates a single, complete training sample (narrative + JSON)."""

    # 1. Create a random scenario that defines the story.
    scenario = create_random_scenario()

    # 2. Generate the narrative text based on that scenario.
    narrative_text = generate_narrative_from_scenario(scenario)

    # 3. Generate the corresponding JSON label from the same scenario.
    json_output = generate_json_from_scenario(scenario, narrative_text)

    # The final output is a tuple of the text and the JSON object (or string).
    return (narrative_text, json_output)


if __name__ == "__main__":
    # Example of how to generate one sample
    text, json_data = generate_training_sample()

    print("--- GENERATED NARRATIVE ---")
    print(text)
    print("\n--- GENERATED JSON ---")
    print(json.dumps(json_data, indent=2))
