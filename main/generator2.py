# %%
import random
import pandas as pd
import json
from dataclasses import field
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

from common_data import *
from scenario_definitions import (
    NarrativeEvidence,
    DerivativeCategory,
    HedgedItem,
    NotionalInstrument,
    DebtHedgedItem,
    ForeignCurrencyHedgedItem,
    CommodityHedgedItem,
    EquityHedgedItem,
    IRInstrument,
    FXInstrument,
    CPInstrument,
    EQInstrument,
    GenericInstrument,
    ScenarioArchetype,
    CurrencyExposure
)
from dummy_data import *

output_file = "./training_data.xlsx"
company_name_file = "./names.xlsx"
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
class GenerationScenario:
    """Holds the entire state for a single, coherent training example."""

    company_name: str
    reporting_year: int
    instruments: List[NotionalInstrument] = field(default_factory=list)
    policy: Optional[RiskManagementPolicy] = None
    number_format_preference: bool = (
        True  # True for abbreviated, False for full numeric
    )
    accounting_updates: List[AccountingStandardUpdate] = field(default_factory=list)


def _create_instrument_with_history(
    scenario: GenerationScenario,
    instrument_class: type,
    instrument_id: int,
    base_instrument_args: Dict,
) -> List[NotionalInstrument]:
    """
    Creates a primary instrument and its historical versions for previous years.

    For a single instrument ID, this generates multiple instrument "states," one for
    the current reporting year and others for the preceding 1-2 years, each with
    slightly varied notional amounts to simulate historical data.

    Args:
        scenario: The GenerationScenario to which instruments will be added.
        instrument_class: The class of the instrument to create (e.g., IRInstrument).
        instrument_id: The unique ID for this instrument and its history.
        base_instrument_args: A dictionary of arguments for the instrument constructor.

    Returns:
        A list of all created instrument instances (current and historical).
    """
    created_instruments = []
    current_year = base_instrument_args["year"]

    # Create instrument for the current reporting year
    current_instrument = instrument_class(
        instrument_id=instrument_id, **base_instrument_args
    )
    created_instruments.append(current_instrument)

    # Create historical versions for the previous 1-2 years
    for i in range(1, random.randint(2, 3)):  # For prev_year and prev2_year
        historical_args = base_instrument_args.copy()
        historical_args["year"] = current_year - i
        # Simulate a slightly different notional amount for the previous year
        historical_args["notional_amount"] = int(
            base_instrument_args["notional_amount"] * random.uniform(0.85, 1.15)
        )
        historical_instrument = instrument_class(
            instrument_id=instrument_id, **historical_args
        )
        created_instruments.append(historical_instrument)

    return created_instruments


# Define a list of company archetypes to choose from during generation.
SCENARIO_ARCHETYPES = [
    ScenarioArchetype(
        name="Large Multinational",
        debt_exposure_range=(3, 6),
        fx_exposure_range=(3, 6),
        commodity_exposure_range=(2, 4),
        equity_exposure_range=(1, 3),
        generic_instrument_range=(0, 2),
        hedging_propensities={"IR": 0.9, "FX": 0.8, "CP": 0.6, "EQ": 0.3, "GEN": 0.1},
        policy_coverage="full",
        default_currency="USD",
        money_units=[("million", 1_000_000), ("billion", 1_000_000_000)],
        prefers_abbreviated_numbers=True,
    ),
    ScenarioArchetype(
        name="Domestic Industrial",
        debt_exposure_range=(2, 4),
        fx_exposure_range=(0, 2),
        commodity_exposure_range=(3, 5),
        equity_exposure_range=(0, 1),
        generic_instrument_range=(0, 1),
        hedging_propensities={"IR": 0.7, "FX": 0.2, "CP": 0.8, "EQ": 0.0, "GEN": 0.1},
        policy_coverage="partial",
        default_currency="USD",
        money_units=[("million", 1_000_000)],
        prefers_abbreviated_numbers=True,
    ),
    ScenarioArchetype(
        name="Tech Company",
        debt_exposure_range=(1, 3),
        fx_exposure_range=(2, 5),
        commodity_exposure_range=(0, 0),
        equity_exposure_range=(2, 4),
        generic_instrument_range=(0, 1),
        hedging_propensities={"IR": 0.5, "FX": 0.7, "CP": 0.0, "EQ": 0.6, "GEN": 0.1},
        policy_coverage="partial",
        default_currency="USD",
        money_units=[("million", 1_000_000)],
        prefers_abbreviated_numbers=False,  # Tech companies sometimes use full numbers
    ),
    ScenarioArchetype(
        name="Financial Institution",
        debt_exposure_range=(4, 8),
        fx_exposure_range=(4, 8),
        commodity_exposure_range=(0, 2),
        equity_exposure_range=(1, 3),
        generic_instrument_range=(1, 2),
        hedging_propensities={"IR": 0.95, "FX": 0.9, "CP": 0.5, "EQ": 0.5, "GEN": 0.2},
        policy_coverage="full",
        default_currency="USD",
        money_units=[("billion", 1_000_000_000)],
        prefers_abbreviated_numbers=True,
    ),
    ScenarioArchetype(
        name="Policy Only / Light User",
        debt_exposure_range=(0, 2),
        fx_exposure_range=(0, 2),
        commodity_exposure_range=(0, 1),
        equity_exposure_range=(0, 0),
        generic_instrument_range=(1, 2),
        hedging_propensities={"IR": 0.3, "FX": 0.3, "CP": 0.1, "EQ": 0.0, "GEN": 0.4},
        policy_coverage="light",
        default_currency="USD",
        money_units=[("thousand", 1_000), ("million", 1_000_000)],
        prefers_abbreviated_numbers=False,
    ),
    ScenarioArchetype(
        name="Potential User",
        debt_exposure_range=(1, 3),
        fx_exposure_range=(1, 3),
        commodity_exposure_range=(0, 2),
        equity_exposure_range=(0, 1),
        generic_instrument_range=(0, 0),
        hedging_propensities={"IR": 0.0, "FX": 0.0, "CP": 0.0, "EQ": 0.0, "GEN": 0.0},
        policy_coverage="light",
        default_currency="USD",
        money_units=[("thousand", 1_000), ("million", 1_000_000)],
        prefers_abbreviated_numbers=False,
    ),
    ScenarioArchetype(
        name="Non-User",
        debt_exposure_range=(0, 0),
        fx_exposure_range=(0, 0),
        commodity_exposure_range=(0, 0),
        equity_exposure_range=(0, 0),
        generic_instrument_range=(0, 0),
        hedging_propensities={"IR": 0.0, "FX": 0.0, "CP": 0.0, "EQ": 0.0, "GEN": 0.0},
        policy_coverage="light",
        default_currency="USD",
        money_units=[("thousand", 1_000), ("million", 1_000_000)],
        prefers_abbreviated_numbers=False,
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

    # --- Decide on a company archetype and get exposure counts ---
    archetype = random.choice(SCENARIO_ARCHETYPES)
    exposure_counts = archetype.get_exposure_counts()

    # --- Decide on the scale of money for this scenario ---
    money_unit, multiplier = random.choice(archetype.money_units)

    # This is a proxy for how many instruments will be created, used for policy generation
    # It's an estimate because of the hedging_propensity logic
    instrument_counts_proxy = {
        "IR": int(
            exposure_counts["debt"] * archetype.hedging_propensities.get("IR", 0.0)
        ),
        "FX": int(
            exposure_counts["fx"] * archetype.hedging_propensities.get("FX", 0.0)
        ),
        "CP": int(
            exposure_counts["commodity"] * archetype.hedging_propensities.get("CP", 0.0)
        ),
        "EQ": int(
            exposure_counts["equity"] * archetype.hedging_propensities.get("EQ", 0.0)
        ),
        "GEN": exposure_counts["generic"],
    }

    scenario = GenerationScenario(
        company_name=random.choice(company_names),
        reporting_year=reporting_year,
        instruments=[],
        policy=generate_policy_for_archetype(archetype, instrument_counts_proxy),
        number_format_preference=archetype.prefers_abbreviated_numbers,
    )

    instrument_id_counter = 1
    hedged_item_id_counter = 1

    # =========================================================================
    # STAGE 1: GENERATE THE POOL OF POTENTIAL HEDGED ITEMS (EXPOSURES)
    # =========================================================================

    potential_hedged_items: Dict[str, List] = {
        "debt": [],
        "fx": [],
        "commodity": [],
        "equity": [],
    }

    # --- Generate Debt Exposures ---
    for _ in range(exposure_counts["debt"]):
        issuance_year = random.randint(reporting_year - 8, reporting_year - 1)
        maturity_year = random.randint(reporting_year + 2, reporting_year + 10)
        hedged_debt = DebtHedgedItem(
            hedged_item_id=hedged_item_id_counter,
            debt_type=random.choice(DUMMY_DEBT_TYPES),
            issuance_month=random.choice(months),
            issuance_year=issuance_year,
            maturity_month=random.choice(months),
            maturity_year=maturity_year,
            principal_amount=random.randint(5, 500) * multiplier,
            interest_rate_type="variable",
            benchmark_rate=random.choice(DUMMY_BENCHMARK_RATES),
            spread_bps=random.randint(100, 300),
        )
        potential_hedged_items["debt"].append(hedged_debt)
        hedged_item_id_counter += 1

    # --- Generate FX Exposures ---
    for _ in range(exposure_counts["fx"]):
        num_exposures = random.randint(1, 3)
        exposures = [
            CurrencyExposure(
                code=cur[0],
                name=cur[1],
                symbol=cur[2],
                amount=random.randint(1, 100) * multiplier,
            )
            for cur in random.sample(all_currencies, num_exposures)
        ]
        hedged_fx = ForeignCurrencyHedgedItem(
            hedged_item_id=hedged_item_id_counter, exposures=exposures
        )
        potential_hedged_items["fx"].append(hedged_fx)
        hedged_item_id_counter += 1

    # --- Generate Commodity Exposures ---
    for _ in range(exposure_counts["commodity"]):
        hedged_commodity = CommodityHedgedItem(
            hedged_item_id=hedged_item_id_counter,
            commodity_type=random.choice(DUMMY_COMMODITY_TYPES),
            transaction_type=random.choice(DUMMY_COMMODITY_TRANSACTION_TYPES),
            quantity=random.randint(100, 10000),
            unit_of_volume=random.choice(DUMMY_COMMODITY_UNITS),
            price_per_unit=random.uniform(10, 200),
            cost_type=random.choice(cost_types),
            supplier=(random.choice(company_names) if random.random() < 0.2 else None),
        )
        potential_hedged_items["commodity"].append(hedged_commodity)
        hedged_item_id_counter += 1

    # --- Generate Equity Exposures ---
    for _ in range(exposure_counts["equity"]):
        # The underlying equity can be the company's own stock or an index
        underlying = random.choice(DUMMY_EQUITY_UNDERLYINGS).format(
            company_name=scenario.company_name
        )
        equity_type = (
            "own_stock" if scenario.company_name in underlying else "market_index"
        )

        hedged_equity = EquityHedgedItem(
            hedged_item_id=hedged_item_id_counter,
            underlying_equity=underlying,
            equity_type=equity_type,  # type: ignore
            reason=random.choice(DUMMY_EQUITY_REASONS),
        )
        potential_hedged_items["equity"].append(hedged_equity)
        hedged_item_id_counter += 1

    # =========================================================================
    # STAGE 2: CREATE INSTRUMENTS BASED ON EXPOSURES AND HEDGING PROPENSITY
    # =========================================================================

    # --- Create IR Instruments (deterministically based on IR propensity) ---
    potential_debt_items = potential_hedged_items["debt"]
    num_ir_hedges = round(
        len(potential_debt_items) * archetype.hedging_propensities.get("IR", 0.0)
    )
    debt_items_to_hedge = random.sample(potential_debt_items, num_ir_hedges)

    for debt_item in potential_debt_items:
        issuance_year = random.randint(reporting_year - 8, reporting_year - 1)
        hedged_debt = None
        notional = 0
        maturity_year = 0  # Initialize to satisfy linter

        if debt_item in debt_items_to_hedge:
            # Create an active hedge for this existing debt exposure
            hedged_debt = debt_item
            maturity_year = hedged_debt.maturity_year
            notional = hedged_debt.principal_amount
        else:
            # For unhedged exposures, there's a chance to create a story about a terminated instrument.
            if (
                random.random() < 0.15
            ):  # Small chance to create a terminated instrument story
                maturity_year = random.randint(issuance_year + 1, reporting_year)
                notional = random.randint(5, 500) * multiplier
            else:
                continue  # This exposure remains unhedged

        base_args = {
            "instrument_type": random.choice(DUMMY_IR_INSTRUMENT_TYPES),
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(DUMMY_HEDGE_DESIGNATIONS),
            "hedged_item": hedged_debt,
        }

        # Create the instrument and its history
        new_instruments = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=IRInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.extend(new_instruments)
        instrument_id_counter += 1

    # --- Create FX Instruments (deterministically based on FX propensity) ---
    potential_fx_items = potential_hedged_items["fx"]
    num_fx_hedges = round(
        len(potential_fx_items) * archetype.hedging_propensities.get("FX", 0.0)
    )
    fx_items_to_hedge = random.sample(potential_fx_items, num_fx_hedges)

    for fx_item in potential_fx_items:
        hedged_fx = None
        notional = 0
        maturity_year = 0  # Initialize to satisfy linter

        if fx_item in fx_items_to_hedge:
            hedged_fx = fx_item
            maturity_year = random.randint(reporting_year + 1, reporting_year + 3)
            notional = sum(
                e.amount for e in hedged_fx.exposures
            )  # Simplified USD equivalent
        else:
            if random.random() < 0.15:
                maturity_year = random.randint(reporting_year - 2, reporting_year)
                notional = random.randint(10, 200) * multiplier
            else:
                continue

        base_args = {
            "instrument_type": random.choice(DUMMY_FX_INSTRUMENT_TYPES),
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(DUMMY_HEDGE_DESIGNATIONS),
            "hedged_item": hedged_fx,
        }

        new_instruments = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=FXInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.extend(new_instruments)
        instrument_id_counter += 1

    # --- Create CP Instruments (deterministically based on CP propensity) ---
    potential_cp_items = potential_hedged_items["commodity"]
    num_cp_hedges = round(
        len(potential_cp_items) * archetype.hedging_propensities.get("CP", 0.0)
    )
    cp_items_to_hedge = random.sample(potential_cp_items, num_cp_hedges)

    for cp_item in potential_cp_items:
        hedged_commodity = None
        notional = 0
        maturity_year = 0  # Initialize to satisfy linter

        if cp_item in cp_items_to_hedge:
            hedged_commodity = cp_item
            maturity_year = random.randint(reporting_year + 1, reporting_year + 5)
            notional = random.randint(5, 100) * multiplier
        else:
            if random.random() < 0.15:
                maturity_year = random.randint(reporting_year - 2, reporting_year)
                notional = random.randint(5, 100) * multiplier
            else:
                continue

        base_args = {
            "instrument_type": random.choice(DUMMY_CP_INSTRUMENT_TYPES),
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(DUMMY_HEDGE_DESIGNATIONS),
            "hedged_item": hedged_commodity,
        }

        new_instruments = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=CPInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.extend(new_instruments)
        instrument_id_counter += 1

    # --- Create EQ Instruments (deterministically based on EQ propensity) ---
    potential_eq_items = potential_hedged_items["equity"]
    num_eq_hedges = round(
        len(potential_eq_items) * archetype.hedging_propensities.get("EQ", 0.0)
    )
    eq_items_to_hedge = random.sample(potential_eq_items, num_eq_hedges)

    for eq_item in potential_eq_items:
        hedged_equity = None
        notional = 0
        maturity_year = 0  # Initialize to satisfy linter

        if eq_item in eq_items_to_hedge:
            hedged_equity = eq_item
            maturity_year = random.randint(reporting_year + 1, reporting_year + 5)
            notional = random.randint(1, 100) * multiplier
        else:
            if random.random() < 0.15:
                maturity_year = random.randint(reporting_year - 2, reporting_year)
                notional = random.randint(1, 50) * multiplier
            else:
                continue

        base_args = {
            "instrument_type": random.choice(DUMMY_EQ_INSTRUMENT_TYPES),
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(DUMMY_HEDGE_DESIGNATIONS),
            "hedged_item": hedged_equity,
        }

        new_instruments = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=EQInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.extend(new_instruments)
        instrument_id_counter += 1

    # --- Create Generic Instruments ---
    for _ in range(exposure_counts.get("generic", 0)):
        is_terminated = random.random() < 0.4
        maturity_year = (
            random.randint(reporting_year - 3, reporting_year)
            if is_terminated
            else random.randint(reporting_year + 1, reporting_year + 5)
        )

        base_args = {
            "instrument_type": random.choice(DUMMY_GENERIC_INSTRUMENT_TYPES),
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": random.randint(10, 300) * multiplier,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(DUMMY_HEDGE_DESIGNATIONS),
            "hedged_item": None,  # Generic instruments often don't have a specific hedged item
        }

        new_instruments = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=GenericInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.extend(new_instruments)
        instrument_id_counter += 1

    return scenario


def pretty_print_scenario(scenario: GenerationScenario):
    """
    Prints a human-readable summary of the generated scenario, focusing on instruments and hedged items.
    """
    print("\n" + "=" * 80)
    print(f"SCENARIO SUMMARY for {scenario.company_name} ({scenario.reporting_year})")
    print("=" * 80)

    if not scenario.instruments:
        print("No instruments generated in this scenario.")
        print("=" * 80)
        return

    print(f"\n--- {len(scenario.instruments)} Instruments Generated ---")
    for i, instrument in enumerate(scenario.instruments, 1):
        print(
            f"\n{i}. Instrument ID: {instrument.instrument_id} ({instrument.category} - {instrument.instrument_type})"
        )
        print(f"   - Notional: {instrument.currency} {instrument.notional_amount:,}")
        print(f"   - Maturity: {instrument.maturity_year}")
        status = "Terminated/Naked" if not instrument.hedged_item else "Active Hedge"
        print(f"   - Status: {status}")

        if instrument.hedged_item:
            hedged_item = instrument.hedged_item
            print(f"   - Hedged Item (ID: {hedged_item.hedged_item_id}):")
            if isinstance(hedged_item, DebtHedgedItem):
                print(f"     - Type: {hedged_item.debt_type}")
                print(f"     - Principal: {hedged_item.principal_amount:,}")
                print(f"     - Maturity: {hedged_item.maturity_year}")
            elif isinstance(hedged_item, ForeignCurrencyHedgedItem):
                exposures = [
                    f"{exp.code} {exp.amount:,}" for exp in hedged_item.exposures
                ]
                print(f"     - Type: Foreign Currency Exposure")
                print(f"     - Exposures: {', '.join(exposures)}")
            elif isinstance(hedged_item, CommodityHedgedItem):
                print(
                    f"     - Type: {hedged_item.commodity_type} ({hedged_item.transaction_type})"
                )
                print(
                    f"     - Quantity: {hedged_item.quantity} {hedged_item.unit_of_volume}"
                )
            elif isinstance(hedged_item, EquityHedgedItem):
                print(
                    f"     - Type: {hedged_item.underlying_equity} ({hedged_item.equity_type})"
                )
                print(f"     - Reason: {hedged_item.reason}")


# %%
# =============================================================================
# PHASE 2: NARRATIVE AND JSON GENERATION
# These functions will take a `GenerationScenario` object and produce the
# final output: the narrative text and the structured JSON label.
# =============================================================================


def _format_notional(amount: int, scenario: GenerationScenario) -> str:
    """Formats a large number into a more readable string like '$250.0 million'."""
    if scenario.number_format_preference:
        if amount >= 1_000_000_000:
            return f"${amount / 1_000_000_000:.1f} billion"
        if amount >= 1_000_000:
            return f"${amount / 1_000_000:.1f} million"
        if amount >= 1_000:
            return f"${amount / 1_000:.1f} thousand"
    else:
        # Format with commas for full numeric value
        return f"${amount:,}"
    return f"${amount}"


def _generate_narrative_intro(scenario: GenerationScenario) -> List[str]:
    """Generates the introductory sentences about market risk."""
    # TODO: Use templates like `hedge_begin_context_templates`
    return [
        f"The company is exposed to market risks, primarily from changes in interest rates and foreign currency exchange rates."
    ]


def _generate_narrative_policy(scenario: GenerationScenario) -> List[str]:
    """Generates sentences describing the company's hedging policy."""
    sentences = []
    if scenario.policy:
        if scenario.policy.general_policy.does_not_use_for_trading:
            sentences.append(
                "Our risk management strategy involves the use of derivative instruments to mitigate these exposures."
            )
            sentences.append(
                "We do not enter into derivative contracts for trading or speculative purposes."
            )
        if scenario.policy.general_policy.counterparty_credit_risk_monitored:
            sentences.append(
                f"Counterparty credit risk is managed by transacting with {scenario.policy.general_policy.counterparty_details}."
            )
    return sentences


def _generate_category_narrative(
    category: str,
    yearly_data: Dict,
    scenario: GenerationScenario,
) -> Tuple[List[str], List[NarrativeEvidence]]:
    """
    Generates a narrative section for a single derivative category (e.g., Interest Rate Risk).
    This includes context, a summary of instruments, and details on changes.
    """
    sentences = []
    reporting_year = scenario.reporting_year
    evidence = []
    current_year_data = yearly_data.get(reporting_year)
    prev_year_data = yearly_data.get(reporting_year - 1)

    # 1. Context Sentence (e.g., "To manage our interest rate risk...")
    # TODO: Make this more dynamic based on templates.
    if category == "IR":
        sentences.append(
            "To manage our interest rate risk, we utilize interest rate swaps to hedge our variable-rate debt."
        )
    elif category == "FX":
        sentences.append(
            "We use foreign currency forward contracts to mitigate the impact of currency fluctuations on our international operations."
        )
    elif category == "CP":
        sentences.append(
            "The Company enters into commodity derivative contracts to manage price risk associated with raw materials."
        )

    # 2. Aggregate Summary
    summary_sentence = [] # Use connectors, and then join at the end to create the full sentence.
    if current_year_data and current_year_data["total_notional"] > 0:
        instrument_type = current_year_data["instrument_types"][0]
        total_notional = current_year_data["total_notional"]
        total_notional_str = _format_notional(total_notional, scenario)
        summary_sentence.append(
            f"As of December 31, {reporting_year}, the aggregate notional value for our {instrument_type} was {total_notional_str}."
        )
    
        evidence.append(
            NarrativeEvidence(
                category=category,  # type: ignore
                instrument_id=None,  # This is an aggregate summary, not a specific instrument
                instrument_type=instrument_type,
                aggregate=True,  # This indicates it's an aggregate summary
                notional=total_notional,
                status="summary",
            )
        )
        if prev_year_data and prev_year_data["total_notional"] > 0:
            prev_total_notional_str = _format_notional(
                prev_year_data["total_notional"], scenario
            )
            evidence.append(
                NarrativeEvidence(
                    category=category,  # type: ignore
                    instrument_id=None,
                    instrument_type=instrument_type,
                    aggregate=True,
                    notional=prev_year_data["total_notional"],
                    year=reporting_year - 1,
                    status="summary",
                )
            )
    else:
        # If no active instruments, state that.
        sentences.append(
            f"As of December 31, {reporting_year}, we had no outstanding derivative instruments to hedge against {category}."
        )
        evidence.append(
            NarrativeEvidence(
                category=category, # type: ignore
                instrument_id=None,
                instrument_type="none",
                notional=0,
                status="none",
            )
        )

    # 3. Detailed Sentences (New, Terminated) by comparing current and previous years.
    current_ids = {
        i.instrument_id for i in current_year_data["instruments"]
    } if current_year_data else set()

    prev_ids = {
        i.instrument_id for i in prev_year_data["instruments"]
    } if prev_year_data else set()

    new_instrument_ids = current_ids - prev_ids
    terminated_instrument_ids = prev_ids - current_ids

    # Describe new instruments
    if current_year_data and new_instrument_ids:
        for instrument_id in new_instrument_ids:
            # Find the new instrument in the current year's data
            instrument = next((i for i in current_year_data["instruments"] if i.instrument_id == instrument_id), None)
            if instrument:
                notional_str = _format_notional(instrument.notional_amount, scenario)
                sentences.append(
                     f"During {reporting_year}, we entered into new {instrument.instrument_type} with an aggregate notional value of {notional_str}."
                 )
                evidence.append(
                     NarrativeEvidence(
                         category=category, # type: ignore
                         instrument_id=instrument.instrument_id,
                         instrument_type=instrument.instrument_type,
                         notional=instrument.notional_amount,
                         status="new",
                     )
                 )

    # Describe terminated instruments
    if prev_year_data and terminated_instrument_ids:
        for instrument_id in terminated_instrument_ids:
            instrument = next((i for i in prev_year_data["instruments"] if i.instrument_id == instrument_id), None)
            if instrument:
                notional_str = _format_notional(instrument.notional_amount, scenario)
                sentences.append(f"During {reporting_year}, {instrument.instrument_type} with a notional value of {notional_str} were terminated or matured.")
                evidence.append(
                     NarrativeEvidence(
                         category=category, # type: ignore
                         instrument_id=instrument.instrument_id,
                         instrument_type=instrument.instrument_type,
                         notional=instrument.notional_amount,
                         status="terminated",
                     )
                 )

    return sentences, evidence


def _generate_narrative_accounting(scenario: GenerationScenario) -> List[str]:
    """Generates sentences about accounting treatment and hedge effectiveness."""
    sentences = []
    if scenario.policy and scenario.policy.category_policies:  # Check if policy exists
        for cat_policy in scenario.policy.category_policies:
            if cat_policy.effectiveness_testing_method:
                sentences.append(
                    f"For our {cat_policy.category} derivative instruments, we assess hedge effectiveness on a {cat_policy.effectiveness_frequency} basis using the {cat_policy.effectiveness_testing_method}."
                )
    # TODO: Add a generic sentence about embedded derivatives if they exist.
    # This is a placeholder for a more robust check.
    if random.random() < 0.3:
        sentences.append(
            f"The Company also has an embedded derivative liability related to its convertible senior notes, with a fair value of $12.5 million as of December 31, {scenario.reporting_year}."
        )
    return sentences


def generate_narrative_from_scenario(scenario: GenerationScenario) -> Tuple[str, List[NarrativeEvidence]]:
    """
    Constructs a coherent, multi-paragraph narrative from a scenario object.
    This function will replace the old `generate_hedge_paragraph`.
    """
    all_sentences = []
    all_evidence = []

    # =========================================================================
    # AGGREGATION STEP: Summarize instruments by category and year.
    # =========================================================================
    aggregated_data: Dict[str, Dict[int, Dict]] = {}
    for instrument in scenario.instruments:
        cat = instrument.category
        year = instrument.year

        if cat not in aggregated_data:
            aggregated_data[cat] = {}

        if year not in aggregated_data[cat]:
            aggregated_data[cat][year] = {
                "total_notional": 0,
                "count": 0,
                "instrument_types": [],
                "instruments": [],
            }

        aggregated_data[cat][year]["total_notional"] += instrument.notional_amount
        aggregated_data[cat][year]["count"] += 1
        aggregated_data[cat][year]["instrument_types"].append(
            instrument.instrument_type
        )
        aggregated_data[cat][year]["instruments"].append(instrument)

    # =========================================================================
    # NARRATIVE CONSTRUCTION: Build the story section by section.
    # =========================================================================

    # 1. Introduction (Broad market risk statement)
    all_sentences.extend(_generate_narrative_intro(scenario))

    # 2. Policy and Strategy (High-level hedging approach)
    all_sentences.extend(_generate_narrative_policy(scenario))

    # 3. Category-Specific Sections (IR, FX, CP, etc.)
    # Iterate in a standard order to mimic real filings.
    for category in ["IR", "FX", "CP", "EQ"]:
        if category in aggregated_data:
            category_sentences, category_evidence = _generate_category_narrative(
                    category, aggregated_data[category], scenario
            )
            all_sentences.extend(category_sentences)
            all_evidence.extend(category_evidence)
        elif random.random() < 0.2:  # Occasionally mention non-use
            # Add a sentence stating no derivatives are used for this category.
            # TODO: Make this more robust.
            pass
            continue

    # 4. Effectiveness and Accounting (Concluding details)
    all_sentences.extend(_generate_narrative_accounting(scenario))

    # TODO: Cleanup and formatting logic will go here.
    narrative = ". ".join(all_sentences) + "."
    full_narrative = (
        f"<reportingYear>{scenario.reporting_year}</reportingYear> {narrative}"
    )
    return full_narrative, all_evidence


def _generate_chain_of_thought(
    scenario: GenerationScenario, evidence: List[NarrativeEvidence]
) -> str:
    """Dynamically generates the chain_of_thought based on the scenario's instruments."""
    thoughts = []

    # A mapping from category code to a more descriptive name
    category_names = {
        "IR": "Interest Rate",
        "FX": "Foreign Exchange",
        "CP": "Commodity",
    }

    for item in evidence:
        category = item.category
        if category in category_names:
            category_name = category_names[category]
            instrument_type = item.instrument_type
            notional_str = _format_notional(item.notional, scenario)
            status = item.status

            if status == "summary":
                thoughts.append(
                    f"The narrative mentions an aggregate notional value of {notional_str} for {instrument_type}, indicating {category_name} derivative activity."
                )
            elif status == "new":
                thoughts.append(
                    f"A new {instrument_type} with a notional of {notional_str} was entered into, confirming 'current' {category} use."
                )
            elif status == "terminated":
                thoughts.append(
                    f"A {instrument_type} with a notional of {notional_str} matured, indicating 'terminated' {category} use."
                )
            elif status == "none":
                thoughts.append(
                    f"The narrative states no outstanding {instrument_type} for {category_name}, indicating no current use."
                )

    if not thoughts:
        return "The company does not appear to use derivative instruments based on the provided narrative."

    return " ".join(thoughts)


def _generate_analysis_summary(
    scenario: GenerationScenario, evidence: List[NarrativeEvidence]
) -> str:
    """Dynamically generates a one-sentence analysis summary."""
    summary_phrases = set()
    for item in evidence:
        summary_phrases.add(f"utilizes {item.category} derivatives")

    if not summary_phrases:
        return "The company does not use derivative instruments."

    return f"The company's risk management strategy {', '.join(sorted(list(summary_phrases)))} to hedge market exposures."


def generate_json_from_scenario(
    scenario: GenerationScenario, evidence: List[NarrativeEvidence]
) -> Dict:
    """
    Generates the target JSON output from the scenario object.
    The `evidence` from the narrative is used to generate the summary and chain_of_thought.
    """
    analysis_summary = _generate_analysis_summary(scenario, evidence)
    chain_of_thought = _generate_chain_of_thought(scenario, evidence)

    # --- Build the derivatives list ONLY from what was mentioned in the evidence. ---
    # This ensures the JSON perfectly matches the narrative. Each piece of evidence
    # that points to a specific instrument contributes to its entry in the final JSON.
    derivatives_list = []
    # Use a dictionary to aggregate evidence for each instrument ID
    instrument_evidence_map: Dict[int, Dict] = {}

    for ev in evidence:
        # We only care about evidence pointing to a specific, non-summary instrument
        if ev.instrument_id is None:
            continue

        # Find the full instrument object from the scenario to get base details
        instrument = next(
            (inst for inst in scenario.instruments if inst.instrument_id == ev.instrument_id and inst.year == scenario.reporting_year),
            None
        )
        if not instrument:
            continue

        # If we haven't seen this instrument ID yet, initialize it
        if ev.instrument_id not in instrument_evidence_map:
            instrument_evidence_map[ev.instrument_id] = {
                "instrument_id": instrument.instrument_id,
                "category": instrument.category,
                "hedge_designation": instrument.hedge_designation,
            }

        # Add details from the current piece of evidence if they exist
        if ev.instrument_type is not None:
            instrument_evidence_map[ev.instrument_id]["instrument_type"] = ev.instrument_type
        if ev.notional is not None:
            instrument_evidence_map[ev.instrument_id]["notional_amount"] = ev.notional

    derivatives_list = list(instrument_evidence_map.values())

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

    # 2. Generate the narrative text and the evidence list based on that scenario.
    narrative_text, evidence = generate_narrative_from_scenario(scenario)

    # 3. Generate the corresponding JSON label using the evidence from the narrative.
    json_output = generate_json_from_scenario(scenario, evidence)

    # The final output is a tuple of the text and the JSON object (or string).
    return (narrative_text, json_output)

# %%
if __name__ == "__main__":
    # Example of how to generate one sample
    text, json_data = generate_training_sample()

    print("--- GENERATED NARRATIVE ---")
    print(text)
    print("\n--- GENERATED JSON ---")
    print(json.dumps(json_data, indent=2))

# %%
