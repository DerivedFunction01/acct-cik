# %%
import random
import pandas as pd
from collections import Counter
import json, re
from typing import List, Dict, Optional, Tuple, Set

from defs.common_data import *
from defs.commodity_data import get_random_commodity_and_unit, get_cost_types_for_commodity
from defs.debt_data import *
from defs.template_definitions import *
from defs.class_definitions import (
    BaseNarrativeEvidence,
    HedgedItem,
    MitigationEvidence,
    NotionalEvidence,
    ResultPhraseDetails,
    PolicySentence,
    NotionalSentence,
    NotionalInstrument,
    DebtHedgedItem,
    MitigationSentence,
    ForeignCurrencyHedgedItem,
    CommodityHedgedItem,
    EquityHedgedItem,
    IRInstrument,
    FXInstrument,
    CPInstrument,
    EQInstrument,
    GenericInstrument,
    ScenarioArchetype,
    CurrencyExposure,
    GenerationScenario,
    RiskManagementPolicy,
    CategorySpecificPolicy,
    GeneralHedgingPolicy,
    DERIVATIVE_CATEGORIES,
)
from defs.dummy_data import *

output_file = "./training_data.xlsx"
company_name_file = "./names.xlsx"
try:
    company_name_df = pd.read_excel(company_name_file)
except FileNotFoundError:
    company_name_df = pd.DataFrame(columns=["name"])
company_names = list(company_name_df["name"])


def _get_currency_and_unit_details(scenario: GenerationScenario) -> Tuple[str, str, str]:
    """Returns (currency_symbol, money_unit_word, ISO Code) based on scenario's archetype."""
    # Get currency symbol
    currency_code = scenario.archetype.default_currency
    currency_obj = next((c for c in all_currencies if c.code == currency_code), None)
    currency_symbol = currency_obj.symbol if currency_obj else "$"  # Default to $

    # Get money unit word (e.g., "million")
    money_unit_word = (
        scenario.archetype.money_units[0][0]
        if scenario.archetype.money_units
        else "million"
    )

    return currency_symbol, money_unit_word, currency_code


# --- Dynamic Instrument Type Generation ---
def _generate_instrument_name(
    category: str,
    hedged_item: Optional["HedgedItem"] = None,
    available_base_types: Optional[List[str]] = None,
) -> Tuple[str, str, str]:
    """
    Dynamically generates a derivative instrument name based on category and context.
    This replaces the pre-expanded `derivative_keywords` logic.

    Returns:
        A tuple of (prefix, full_name, alias).
    """
    components= DERIVATIVE_COMPONENTS
    placeholders = components["placeholders"].get(category, [""])
    base_types = available_base_types or components["base_types"]
    suffixes = components["suffixes"]  # e.g., contract, agreement
    special_suffixes = components["special_suffixes"]  # e.g., put option
    special_ratio = 0.10  # configurable

    # --- Context-Aware Placeholder Selection (for IR) ---
    placeholder = ""
    if (
        category == "IR"
        and isinstance(hedged_item, DebtHedgedItem)
        and hedged_item.benchmark_rate
    ):
        # 35% chance to use the specific placeholder if found, otherwise use the generic "interest-rate".
        if random.random() < 0.35:
            placeholder = hedged_item.benchmark_rate
        else:
            placeholder = random.choice(placeholders)
    else:
        placeholder = random.choice(placeholders)

    base_type = random.choice(base_types)

    # --- Assemble the name ---
    use_special = special_suffixes and random.random() < special_ratio
    if use_special:
        chosen = random.choice(special_suffixes)
        full_name = " ".join(filter(None, [placeholder, chosen])).strip()
        alias = " ".join(chosen.split()[-2:]) if len(chosen.split()) > 1 else chosen
        base_type = chosen  # treat as base for alias/prefix logic
    else:
        suffix = random.choice(suffixes)
        full_name = " ".join(filter(None, [placeholder, base_type, suffix])).strip()
        alias = (
            " ".join(base_type.split()[-2:])
            if len(base_type.split()) > 1
            else base_type
        )

    # --- Optional Prefix (for swaps, swaptions, rate locks) ---
    prefix = ""
    if (
        
        any(x in base_type for x in ["swap", "swaption", "lock"])
        and random.random() < PAY_PREFIX_RATIO
    ):
        prefix = random.choice(components["swap_prefixes"])
            
    # --- Optional Prefix (global)
    if (
        
        not prefix and random.random() < PAY_PREFIX_RATIO
    ):
        prefix = random.choice(components["global_prefixes"]
    )

    return prefix, full_name, alias

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
        hedging_propensities={"IR": (0.9, 0.9), "FX": (0.8, 0.8), "CP": (0.6, 0.6), "EQ": (0.3, 0.3), "GEN": (0.1, 0.1)},
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
        hedging_propensities={"IR": (0.7, 0.7), "FX": (0.2, 0.2), "CP": (0.8, 0.8), "EQ": (0.0, 0.0), "GEN": (0.1, 0.1)},
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
        hedging_propensities={"IR": (0.5, 0.5), "FX": (0.7, 0.7), "CP": (0.0, 0.0), "EQ": (0.6, 0.6), "GEN": (0.1, 0.1)},
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
        hedging_propensities={"IR": (0.95, 0.95), "FX": (0.9, 0.9), "CP": (0.5, 0.5), "EQ": (0.5, 0.5), "GEN": (0.2, 0.2)},
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
        hedging_propensities={"IR": (0.3, 0.3), "FX": (0.3, 0.3), "CP": (0.1, 0.1), "EQ": (0.0, 0.0), "GEN": (0.4, 0.4)},
        policy_coverage="light",
        default_currency="USD",
        money_units=[("thousand", 1_000), ("million", 1_000_000)],
        prefers_abbreviated_numbers=False,
    ),
    ScenarioArchetype(
        name="Potential User",
        debt_exposure_range=(1, 3), # Has exposures...
        fx_exposure_range=(1, 3), # ...but won't hedge them.
        commodity_exposure_range=(1, 2),
        equity_exposure_range=(0, 1),
        generic_instrument_range=(0, 1),
        hedging_propensities={"IR": (0.0, 0.0), "FX": (0.0, 0.0), "CP": (0.0, 0.0), "EQ": (0.0, 0.0), "GEN": (0.0, 0.0)},
        policy_coverage="light",
        default_currency="USD",
        money_units=[("million", 1_000_000)],
        prefers_abbreviated_numbers=False,
    ),
    ScenarioArchetype(
        name="Non-User",
        debt_exposure_range=(1, 2), # Has exposures...
        fx_exposure_range=(1, 2), # ...but will never hedge them.
        commodity_exposure_range=(0, 1),
        equity_exposure_range=(0, 0),
        generic_instrument_range=(0, 1),
        hedging_propensities={"IR": (0.0, -1), "FX": (0.0, -1), "CP": (0.0, -1), "EQ": (0.0, -1), "GEN": (0.0, -1)},
        policy_coverage="light",
        default_currency="USD",
        money_units=[("million", 1_000_000)],
        prefers_abbreviated_numbers=False,
    ),
    ScenarioArchetype(
        name="New Hedger",
        debt_exposure_range=(2, 4),
        fx_exposure_range=(2, 4),
        commodity_exposure_range=(0, 1),
        equity_exposure_range=(0, 0),
        generic_instrument_range=(0, 0),
        # Past propensity is 0, current is high.
        hedging_propensities={"IR": (0.0, 0.9), "FX": (0.0, 0.9), "CP": (0.0, 0.0), "EQ": (0.0, 0.0), "GEN": (0.0, 0.0)},
        policy_coverage="light",
        default_currency="USD",
        money_units=[("million", 1_000_000)],
        prefers_abbreviated_numbers=True,
    ),
    ScenarioArchetype(
        name="Exiting Hedger",
        debt_exposure_range=(2, 4),
        fx_exposure_range=(2, 4),
        commodity_exposure_range=(0, 1),
        equity_exposure_range=(0, 0),
        generic_instrument_range=(0, 0),
        # Past propensity was high, current is 0.
        hedging_propensities={"IR": (1.0, 0.0), "FX": (1.0, 0.0), "CP": (0.0, 0.0), "EQ": (0.0, 0.0), "GEN": (0.0, 0.0)},
        policy_coverage="light",
        default_currency="USD",
        money_units=[("million", 1_000_000)],
        prefers_abbreviated_numbers=True,
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
        # TODO: Replace hardcoded counterparty details with more varied, generated text.
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
                # TODO: These random.choice() calls select from dummy data lists. This will be replaced by the generative model.
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
    reporting_day = random.randint(28, 31)
    reporting_month = random.choice(months)

    # --- Decide on a company archetype and get exposure counts ---
    archetype = random.choice(SCENARIO_ARCHETYPES)
    exposure_counts = archetype.get_exposure_counts()

    # --- Decide on the scale of money for this scenario ---
    money_unit, multiplier = random.choice(archetype.money_units)

    # This is a proxy for how many instruments will be created, used for policy generation
    # It's an estimate because of the hedging_propensity logic
    instrument_counts_proxy = {
        # Use the 'current' propensity (index 1) for this proxy
        "IR": int(exposure_counts["debt"] * max(0, archetype.hedging_propensities.get("IR", (0.0, 0.0))[1])),
        "FX": int(exposure_counts["fx"] * max(0, archetype.hedging_propensities.get("FX", (0.0, 0.0))[1])),
        "CP": int(exposure_counts["commodity"] * max(0, archetype.hedging_propensities.get("CP", (0.0, 0.0))[1])),
        "EQ": int(exposure_counts["equity"] * max(0, archetype.hedging_propensities.get("EQ", (0.0, 0.0))[1])),
        "GEN": exposure_counts["generic"],
    }

    scenario = GenerationScenario(
        company_name=random.choice(company_names),
        reporting_month=reporting_month,
        reporting_day=reporting_day,
        reporting_year=reporting_year,
        instruments=[],
        policy=generate_policy_for_archetype(archetype, instrument_counts_proxy),
        number_format_preference=archetype.prefers_abbreviated_numbers,
        archetype=archetype,
    )

    # =========================================================================

    instrument_id_counter = 1
    hedged_item_id_counter = 1

    # --- NEW: Reserve base types for the GEN category for this scenario ---
    all_base_types = DERIVATIVE_COMPONENTS["base_types"]
    # Reserve 1 or 2 base types for GEN
    num_to_reserve = random.randint(1, 2)
    gen_reserved_base_types = random.sample(all_base_types, num_to_reserve)
    # The rest are available for other categories
    other_available_base_types = [bt for bt in all_base_types if bt not in gen_reserved_base_types]

    # =========================================================================

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

        # --- NEW: Context-aware debt and benchmark selection ---
        selected_debt_type: DebtType = random.choice(all_debt_types)
        benchmark_rate = None
        debt_currency = archetype.default_currency

        # 20% chance for the debt to be in a foreign currency
        if random.random() < 0.20:
            foreign_curr = random.choice([c for c in all_currencies if c.code != archetype.default_currency])
            debt_currency = foreign_curr.code

        if selected_debt_type.benchmarks:
            benchmark_rate = random.choice(
                selected_debt_type.benchmarks + specific_rate_terms
            )

        hedged_debt = DebtHedgedItem(
            hedged_item_id=hedged_item_id_counter,
            debt_type=selected_debt_type.name,
            currency=debt_currency,
            issuance_month=random.choice(months),
            issuance_year=issuance_year,
            maturity_month=random.choice(months),
            maturity_year=maturity_year,
            principal_amount=random.randint(5, 500) * multiplier,
            benchmark_rate=benchmark_rate,
            spread_bps=random.randint(100, 300),
        )
        potential_hedged_items["debt"].append(hedged_debt)
        hedged_item_id_counter += 1

    # --- Generate FX Exposures ---
    for _ in range(exposure_counts["fx"]):
        num_exposures = random.randint(1, 3)
        exposures = [
            CurrencyExposure(
                code=cur.code,
                full_name=cur.full_name,
                symbol=cur.symbol,
                adjective=cur.adjective,
                location=cur.location,
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
        commodity_name, unit, cost_types = get_random_commodity_and_unit()
        hedged_commodity = CommodityHedgedItem(
            hedged_item_id=hedged_item_id_counter,
            commodity_type=commodity_name,
            transaction_type=random.choice(transaction_types),
            quantity=random.randint(100, 10000),
            unit_of_volume=unit,
            price_per_unit=random.uniform(10, 200),
            cost_type=cost_types,
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
    past_prop, current_prop = archetype.hedging_propensities.get("IR", (0.0, 0.0))
    num_ir_hedges = round(len(potential_debt_items) * max(0, current_prop))
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
            # This is especially true for "Exiting Hedger" archetypes where past_prop > 0 and current_prop == 0.
            is_exiting_hedger = past_prop > 0 and current_prop == 0
            should_create_historical = is_exiting_hedger or (random.random() < past_prop)

            if should_create_historical:
                maturity_year = random.randint(issuance_year + 1, reporting_year)
                notional = random.randint(5, 500) * multiplier
            else:
                continue  # This exposure remains unhedged

        # --- NEW: Handle Cross-Currency Interest Rate Swaps as a special case ---
        is_cross_currency = debt_item.currency != archetype.default_currency and random.random() < 0.5
        if is_cross_currency:
            # This is a hybrid instrument. We'll name it accordingly but categorize it as FX.
            instrument_category = "FX"
            placeholder = "cross-currency interest rate"
            base_type = random.choice([s for s in DERIVATIVE_COMPONENTS["base_types"] if "swap" in s or "agreement" in s])
            name = f"{placeholder} {base_type}"
            alias = " ".join(base_type.split()[-2:])
            prefix = "" # Prefixes don't make sense for this type
        else:
            # Standard IR hedge
            instrument_category = "IR"
            prefix, name, alias = _generate_instrument_name("IR", hedged_item=debt_item, available_base_types=other_available_base_types)

        base_args = {
            "instrument_type": name,
            "instrument_alias": alias,
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": hedged_debt,
            "instrument_prefix": prefix,
        }

        # Create the instrument and its history
        new_instruments = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=FXInstrument if is_cross_currency else IRInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.extend(new_instruments)
        instrument_id_counter += 1

    # --- Create FX Instruments (deterministically based on FX propensity) ---
    potential_fx_items = potential_hedged_items["fx"]
    past_prop, current_prop = archetype.hedging_propensities.get("FX", (0.0, 0.0))
    num_fx_hedges = round(len(potential_fx_items) * max(0, current_prop))
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
            is_exiting_hedger = past_prop > 0 and current_prop == 0
            should_create_historical = is_exiting_hedger or (random.random() < past_prop)

            if should_create_historical:
                maturity_year = random.randint(reporting_year - 2, reporting_year)
                notional = random.randint(10, 200) * multiplier
            else:
                continue

        prefix, name, alias = _generate_instrument_name("FX", available_base_types=other_available_base_types)

        base_args = {
            "instrument_type": name,
            
            "instrument_alias": alias,
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": hedged_fx,
            "instrument_prefix": prefix,
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
    past_prop, current_prop = archetype.hedging_propensities.get("CP", (0.0, 0.0))
    num_cp_hedges = round(len(potential_cp_items) * max(0, current_prop))
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
            is_exiting_hedger = past_prop > 0 and current_prop == 0
            should_create_historical = is_exiting_hedger or (random.random() < past_prop)

            if should_create_historical:
                maturity_year = random.randint(reporting_year - 2, reporting_year)
                notional = random.randint(5, 100) * multiplier
            else:
                continue

        prefix, name, alias = _generate_instrument_name("CP", available_base_types=other_available_base_types)

        base_args = {
            "instrument_type": name,
            
            "instrument_alias": alias,
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": hedged_commodity,
            "instrument_prefix": prefix,
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
    past_prop, current_prop = archetype.hedging_propensities.get("EQ", (0.0, 0.0))
    num_eq_hedges = round(len(potential_eq_items) * max(0, current_prop))
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
            is_exiting_hedger = past_prop > 0 and current_prop == 0
            should_create_historical = is_exiting_hedger or (random.random() < past_prop)

            if should_create_historical:
                maturity_year = random.randint(reporting_year - 2, reporting_year)
                notional = random.randint(1, 50) * multiplier
            else:
                continue

        prefix, name, alias = _generate_instrument_name("EQ", available_base_types=other_available_base_types)

        base_args = {
            "instrument_type": name,
            
            "instrument_alias": alias,
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": hedged_equity,
            "instrument_prefix": prefix,
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

        prefix, name, alias = _generate_instrument_name("GEN", available_base_types=gen_reserved_base_types)

        base_args = {
            "instrument_type": name,
            
            "instrument_alias": alias,
            "month": random.choice(months),
            "year": reporting_year,
            "notional_amount": random.randint(10, 300) * multiplier,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": None,  # Generic instruments often don't have a specific hedged item
            "instrument_prefix": prefix,
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


# =============================================================================
# PHASE 2: NARRATIVE AND JSON GENERATION
# These functions will take a `GenerationScenario` object and produce the
# final output: the narrative text and the structured JSON label.
# =============================================================================


def _generate_narrative_policy(
    scenario: GenerationScenario,
) -> Tuple[List[str], List[BaseNarrativeEvidence]]:
    """Generates sentences describing the company's hedging policy and risk exposures.""" # noqa
    sentences = []
    evidence = [] # This function will now also produce evidence

    if scenario.policy:
        # --- Generate a high-level risk exposure sentence ---
        # Determine the primary risk category by finding the most common one.
        instrument_categories_in_year = []
        for inst in scenario.instruments:
            if inst.year == scenario.reporting_year:
                instrument_categories_in_year.append(inst.category)

        counts = Counter(instrument_categories_in_year)
        # If there are no instruments, the primary category is GEN, otherwise it's the most common.
        primary_category = counts.most_common(1)[0][0] if counts else "GEN"

        policy_sentence_obj = PolicySentence(
            category=primary_category, # type: ignore
            company_name=scenario.company_name,
        )
        policy_sentence, policy_evidence = policy_sentence_obj.build()
        sentences.append(policy_sentence)

        # Only add the evidence if there are actual instruments. A general policy
        # statement for a non-user is just context, not evidence of a "GEN" derivative.
        if instrument_categories_in_year:
            evidence.append(policy_evidence)

        # --- Generate standard policy statements ---
        if scenario.policy.general_policy.does_not_use_for_trading:
             # Select a random template for the "no trading" policy
            template = random.choice(hedge_no_trading_templates)
            sentence = template.format(
                company=scenario.company_name, verb=random.choice(policy_verbs)
            )
            sentences.append(sentence)
        # TODO: This is a hardcoded sentence template and should be replaced by generative logic.
        if scenario.policy.general_policy.counterparty_credit_risk_monitored:
            sentences.append(
                f"Counterparty credit risk is managed by transacting with {scenario.policy.general_policy.counterparty_details}."
            )
    return sentences, evidence


def _generate_category_narrative(
    category: str,
    yearly_data: Dict,
    scenario: GenerationScenario,
) -> Tuple[List[str], List[BaseNarrativeEvidence], Optional[str]]:
    """
    Generates a narrative section for a single derivative category (e.g., Interest Rate Risk).
    This includes context, a summary of instruments, and details on changes.
    """
    sentences, evidence, used_name = [], [], None
    reporting_year, reporting_month, reporting_day = (
        scenario.reporting_year,
        scenario.reporting_month,
        scenario.reporting_day,
    )
    evidence = []
    current_year_data = yearly_data.get(reporting_year)
    prev_year_data = yearly_data.get(reporting_year - 1)

    # Get currency and money unit details for sentence generation
    currency_symbol, money_unit_word, currency_code = _get_currency_and_unit_details(
        scenario
    )

    # 1. Context Sentence (e.g., "To manage our interest rate risk...")
    # First, get specific details from the scenario's instruments for this category.
    commodity_name = None
    commodity_unit = None
    currency_names = []
    debt_type_name = None
    location_names = []
    cost_type_name = None
    result_details = ResultPhraseDetails()

    if current_year_data and current_year_data["instruments"]:
        # Find an instrument in the current year that has a hedged item to extract details from.
        instrument_with_hedged_item = next(
            (inst for inst in current_year_data["instruments"] if inst.hedged_item),
            None,
        )

        if instrument_with_hedged_item:
            hedged_item = instrument_with_hedged_item.hedged_item
            if isinstance(hedged_item, CommodityHedgedItem):
                commodity_name = hedged_item.commodity_type
                commodity_unit = hedged_item.unit_of_volume
                result_details.commodity = commodity_name
                result_details.unit = commodity_unit
                cost_type_name = hedged_item.cost_type
            elif isinstance(hedged_item, ForeignCurrencyHedgedItem):
                currency_names = [exp.full_name for exp in hedged_item.exposures]
                locations = [exp.location for exp in hedged_item.exposures]
                location_names = list(set(locations))  # Unique locations
                if location_names:
                    result_details.geography = random.choice(location_names)
            elif isinstance(hedged_item, DebtHedgedItem):
                debt_type_name = hedged_item.debt_type
                result_details.debt_type = hedged_item.debt_type
                result_details.pct = (
                    hedged_item.fixed_rate_pct or hedged_item.change_rate_pct
                )
                result_details.frequency = hedged_item.payment_frequency

    # Use the PolicySentence builder which correctly populates all placeholders.
    # This replaces the manual formatting that was here before.
    policy_sentence_obj = PolicySentence(
        category=category,  # type: ignore
        company_name=scenario.company_name,
        result_details=result_details,
        locations=location_names,
    )
    context_sentence, policy_evidence = policy_sentence_obj.build()
    sentences.append(context_sentence)
    # We can decide if we want to add this specific evidence to our main list.
    # For now, we'll just use the sentence.

    # 1b. Mitigation/Purpose Sentence (e.g., "The company uses swaps to hedge interest rate risk...")
    # This adds a sentence explaining *why* the company is using the derivative.
    is_non_use_mitigation = False
    has_active_instruments = bool(current_year_data and current_year_data["instruments"])
    # --- FIX: Determine usage status based on actual data first, then fall back to propensity. ---
    past_prop, current_prop = scenario.archetype.hedging_propensities.get(category, (0.0, 0.0)) # type: ignore
    if has_active_instruments:
        usage = "current"
    elif current_prop < 0: # Explicit non-user
        usage = "non_use"
    elif past_prop > 0 and current_prop == 0: # Exiting hedger
        usage = "historical"
    else: # No active instruments, and not an explicit non-user -> speculative
        usage = "speculative"

    # Use the most common instrument type for the sentence, or a generic one if no instruments exist.
    instrument_type = "derivatives" # Default for non-users
    if has_active_instruments and current_year_data:
        instrument_type = Counter(current_year_data["instrument_types"]).most_common(1)[0][0]

    mitigation_sentence_obj = MitigationSentence(
        category=category,  # type: ignore
        company_name=scenario.company_name,
        swap_type=instrument_type,
        has_active_instruments=has_active_instruments,
        usage_status=usage,
        year=reporting_year,
        month=reporting_month,
        end_day=reporting_day,
        result_details=result_details,
    )
    mitigation_sentence, mitigation_evidence = mitigation_sentence_obj.build()
    sentences.append(mitigation_sentence)
    evidence.append(mitigation_evidence)
    is_non_use_mitigation = (mitigation_evidence.usage_status == "non_use")

    # 2. Aggregate Summary OR Individual Instrument Descriptions.
    # --- FIX: Do not generate a notional sentence if the mitigation sentence already stated non-use. ---
    # Also check if there are any instruments at all, to avoid this block for non-users.
    if current_year_data and current_year_data["instruments"] and not is_non_use_mitigation:
        # --- NEW LOGIC: Decide whether to summarize or detail ---
        # Check for the specific case where there are current instruments but no prior ones.
        if prev_year_data is None or prev_year_data["total_notional"] == 0:
            # 15% chance to generate a specific "no prior" sentence
            if random.random() < 0.15:
                # This logic will be handled in the comparative summary section below
                pass

        num_instruments_current_year = len(current_year_data["instruments"])

        # If there are few instruments, describe them individually.
        if 0 < num_instruments_current_year <= 2:
            
            for instrument in current_year_data["instruments"]:
                use_fair_value = random.random() < 0.2
                value_type = "fair_value" if use_fair_value else "notional"
                value_to_report = instrument.notional_amount
                if use_fair_value:
                    value_to_report = max(
                        1, int(instrument.notional_amount / random.randint(20, 100))
                    )

                # Determine if the instrument is "historical" (existed in a prior year)
                is_historical = False
                if prev_year_data:
                    prev_ids = {i.instrument_id for i in prev_year_data["instruments"]}
                    if instrument.instrument_id in prev_ids:
                        is_historical = True
                
                # 20% chance to use the historical template if applicable
                sentence_type = "historical_individual" if is_historical and random.random() < 0.2 else "individual"

                individual_sentence_obj = NotionalSentence(
                    swap_type=instrument.instrument_type,
                    year=reporting_year,
                    notional=value_to_report,
                    currency_symbol=currency_symbol,
                    company_name=scenario.company_name,
                    sentence_type=sentence_type,
                    hedge_designation=instrument.hedge_designation,
                    money_units=scenario.archetype.money_units,
                    maturity_year=instrument.maturity_year,
                    prefer_abbreviated=scenario.number_format_preference,
                    category=category,  # type: ignore
                    reporting_year=reporting_year,
                    value_type=value_type,
                    result_phrase=random.choice(
                        # Pass the commodity name to the sentence builder
                        result_phrases.get(category, result_phrases["GEN"])
                    ),
                )
                individual_sentence_text, evidence_obj = individual_sentence_obj.build()
                evidence_obj.instrument_id = instrument.instrument_id
                sentences.append(individual_sentence_text)
                evidence.append(evidence_obj)

        # If there are many instruments, provide an aggregate summary.
        else:
            # Use the most common instrument type for the summary, or just the first one

            counts = Counter(current_year_data["instrument_types"])
            instrument_type = (
                counts.most_common(1)[0][0] if counts else "derivative instrument"
            )
            used_name = instrument_type  # Track the name we used for this category

            total_notional = current_year_data["total_notional"]
            
            use_fair_value = random.random() < 0.2
            value_type_to_use = "fair_value" if use_fair_value else "notional"
            value_to_report = total_notional
            if use_fair_value:
                value_to_report = max(1, int(total_notional / random.randint(20, 100)))

            summary_sentence_obj = NotionalSentence(
                swap_type=instrument_type,
                year=reporting_year,
                notional=value_to_report,
                currency_symbol=currency_symbol,
                currency_code=currency_code,
                month=reporting_month,
                end_day=reporting_day,
                money_units=scenario.archetype.money_units,
                prefer_abbreviated=scenario.number_format_preference,
                category=category,  # type: ignore
                reporting_year=reporting_year,
                value_type=value_type_to_use,
                result_phrase=random.choice(
                    # Pass the commodity name to the sentence builder
                    result_phrases.get(category, result_phrases["GEN"])
                ),
                result_details=result_details,
            )
            summary_sentence_text, evidence_obj = summary_sentence_obj.build()
            sentences.append(summary_sentence_text)
            evidence.append(evidence_obj)

            # Add comparative summary if previous year data exists
            if prev_year_data and prev_year_data["total_notional"] > 0:
                prev_total_notional = prev_year_data["total_notional"]
                prev_value_to_report = prev_total_notional
                if use_fair_value:
                    prev_value_to_report = max(
                        1, int(prev_total_notional / random.randint(20, 100))
                    )

                comparative_summary_obj = NotionalSentence(
                    swap_type=instrument_type,
                    year=reporting_year,
                    notional=value_to_report,
                    currency_symbol=currency_symbol,
                    month=reporting_month,
                    end_day=reporting_day,
                    prev_year=reporting_year - 1,
                    prev_notional=prev_value_to_report,
                    sentence_type="comparative",
                    money_units=scenario.archetype.money_units,
                    prefer_abbreviated=scenario.number_format_preference,
                    category=category,  # type: ignore
                    reporting_year=reporting_year,
                    value_type=value_type_to_use,
                )
                comparative_summary_text, evidence_obj = comparative_summary_obj.build()
                sentences.append(comparative_summary_text)
            # NEW: Handle case where there were no prior instruments
            elif prev_year_data is None or prev_year_data["total_notional"] == 0:
                comparative_no_prior_obj = NotionalSentence(
                    swap_type=instrument_type,
                    year=reporting_year,
                    notional=value_to_report,
                    currency_symbol=currency_symbol,
                    month=reporting_month,
                    end_day=reporting_day,
                    prev_year=reporting_year - 1,
                    prev_notional=0, # Explicitly zero
                    sentence_type="comparative_no_prior_outstanding",
                    money_units=scenario.archetype.money_units,
                    prefer_abbreviated=scenario.number_format_preference,
                    category=category,  # type: ignore
                    reporting_year=reporting_year,
                    value_type=value_type_to_use,
                )
                comparative_summary_text, evidence_obj = comparative_no_prior_obj.build()
                sentences.append(comparative_summary_text)
    else:
        # --- NEW: If there are no current instruments, check if there were prior ones
        # to generate a "comparative_no_outstanding" sentence.
        if prev_year_data and prev_year_data["total_notional"] > 0:
            instrument_type = prev_year_data["instrument_types"][0] if prev_year_data["instrument_types"] else "derivative instrument"
            comparative_no_outstanding_obj = NotionalSentence(
                swap_type=instrument_type,
                year=reporting_year,
                notional=0, # No notional this year
                currency_symbol=currency_symbol,
                month=reporting_month,
                end_day=reporting_day,
                prev_year=reporting_year - 1,
                prev_notional=prev_year_data["total_notional"],
                sentence_type="comparative_no_outstanding",
                money_units=scenario.archetype.money_units,
                prefer_abbreviated=scenario.number_format_preference,
                category=category,  # type: ignore
                reporting_year=reporting_year,
            )
            no_instrument_text, evidence_obj = comparative_no_outstanding_obj.build()
            sentences.append(no_instrument_text)
            evidence.append(evidence_obj)
        else:
            # Only generate a generic "no instruments" sentence if there's no history to compare to.
            no_instrument_obj = NotionalSentence(
                swap_type="",  # Not needed
                year=scenario.reporting_year,
                notional=0,
                month=reporting_month,
                end_day=reporting_day,
                sentence_type="no_instruments",
                category=category,  # type: ignore
                company_name=scenario.company_name,
                reporting_year=reporting_year,
            )
            no_instrument_text, evidence_obj = no_instrument_obj.build()
            sentences.append(no_instrument_text)
            evidence.append(evidence_obj)

    # 3. Detailed Sentences (New, Terminated) by comparing current and previous years.
    current_ids = (
        {i.instrument_id for i in current_year_data["instruments"]}
        if current_year_data
        else set()
    )

    prev_ids = (
        {i.instrument_id for i in prev_year_data["instruments"]}
        if prev_year_data
        else set()
    )

    new_instrument_ids = current_ids - prev_ids
    terminated_instrument_ids = prev_ids - current_ids

    # Describe new instruments
    if current_year_data and new_instrument_ids:
        for instrument_id in new_instrument_ids:
            # Find the new instrument in the current year's data
            instrument = next(
                (
                    i
                    for i in current_year_data["instruments"]
                    if i.instrument_id == instrument_id
                ),
                None,
            )
            if instrument:

                # Decide whether to use 'notional' or 'fair_value'
                
                use_fair_value_individual = random.random() < 0.2
                value_type_individual = (
                    "fair_value" if use_fair_value_individual else "notional"
                )
                value_to_report_individual = instrument.notional_amount
                if use_fair_value_individual:
                    value_to_report_individual = max(
                        1, int(instrument.notional_amount / random.randint(20, 100))
                    )

                # Generate new individual instrument sentence
                new_instrument_obj = NotionalSentence(
                    swap_type=instrument.instrument_type,
                    year=reporting_year,
                    notional=value_to_report_individual,
                    currency_symbol=currency_symbol,
                    company_name=scenario.company_name,
                    sentence_type="new_individual",
                    hedge_designation=instrument.hedge_designation,
                    money_units=scenario.archetype.money_units,
                    maturity_year=instrument.maturity_year,
                    prefer_abbreviated=scenario.number_format_preference,
                    category=category,  # type: ignore
                    reporting_year=reporting_year,
                    value_type=value_type_individual,
                    result_phrase=random.choice(
                        # Pass the commodity name to the sentence builder
                        result_phrases.get(category, result_phrases["GEN"])
                    ),
                )
                new_instrument_text, evidence_obj = new_instrument_obj.build()
                evidence_obj.instrument_id = (
                    instrument.instrument_id
                )  # Link to specific instrument
                sentences.append(new_instrument_text)
                evidence.append(evidence_obj)

    # Describe terminated instruments
    if prev_year_data and terminated_instrument_ids:
        for instrument_id in terminated_instrument_ids:
            instrument = next(
                (
                    i
                    for i in prev_year_data["instruments"]
                    if i.instrument_id == instrument_id
                ),
                None,
            )
            if instrument:

                # Decide whether to use 'notional' or 'fair_value'
                
                use_fair_value_terminated = random.random() < 0.2
                value_type_terminated = (
                    "fair_value" if use_fair_value_terminated else "notional"
                )
                value_to_report_terminated = instrument.notional_amount
                if use_fair_value_terminated:
                    value_to_report_terminated = max(
                        1, int(instrument.notional_amount / random.randint(20, 100))
                    )

                # Generate terminated individual instrument sentence
                terminated_instrument_obj = NotionalSentence(
                    swap_type=instrument.instrument_type,
                    year=reporting_year,  # Reporting year is when it was terminated
                    notional=value_to_report_terminated,
                    currency_symbol=currency_symbol,
                    company_name=scenario.company_name,
                    sentence_type="terminated_individual",
                    money_units=scenario.archetype.money_units,
                    maturity_year=instrument.maturity_year,
                    prefer_abbreviated=scenario.number_format_preference,
                    category=category,  # type: ignore
                    reporting_year=reporting_year,
                    value_type=value_type_terminated,
                    result_phrase=random.choice(
                        # Pass the commodity name to the sentence builder
                        result_phrases.get(category, result_phrases["GEN"])
                    ),
                )
                terminated_instrument_text, evidence_obj = (
                    terminated_instrument_obj.build()
                )
                evidence_obj.instrument_id = (
                    instrument.instrument_id
                )  # Link to specific instrument
                sentences.append(terminated_instrument_text)
                evidence.append(evidence_obj)

    return sentences, evidence, used_name


def _generate_narrative_accounting(
    scenario: GenerationScenario,
) -> Tuple[List[str], List[BaseNarrativeEvidence]]:
    """Generates sentences about accounting treatment and hedge effectiveness."""
    sentences = []
    if scenario.policy and scenario.policy.category_policies:  # Check if policy exists
        # TODO: This is a hardcoded sentence template and should be replaced by generative logic.
        for cat_policy in scenario.policy.category_policies:
            if cat_policy.effectiveness_testing_method:
                sentences.append(
                    f"For our {cat_policy.category} derivative instruments, we assess hedge effectiveness on a {cat_policy.effectiveness_frequency} basis using the {cat_policy.effectiveness_testing_method}."
                )
    return sentences, []  # Return an empty list for evidence for now


def generate_narrative_from_scenario(
    scenario: GenerationScenario,
) -> Tuple[str, List[BaseNarrativeEvidence]]:
    """
    Constructs a coherent, multi-paragraph narrative from a scenario object.
    This function will replace the old `generate_hedge_paragraph`.
    """
    narrative_sections = []
    all_evidence = []

    # =========================================================================
    # AGGREGATION: Summarize instruments by category and year.
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

    # 1. Policy and Strategy Section
    policy_sentences, policy_evidence = _generate_narrative_policy(scenario)
    if policy_sentences:
        narrative_sections.append(" ".join(s.strip() for s in policy_sentences if s))
    all_evidence.extend(policy_evidence)

    # 2. Category-Specific Sections (IR, FX, CP, etc.)
    # --- NEW: Get all potential categories from the archetype's exposures to ensure we discuss risk even if not hedged. ---
    archetype_exposures = scenario.archetype.get_exposure_counts()
    all_relevant_categories = {
        "IR": archetype_exposures["debt"] > 0,
        "FX": archetype_exposures["fx"] > 0,
        "CP": archetype_exposures["commodity"] > 0,
        "EQ": archetype_exposures["equity"] > 0,
        "GEN": archetype_exposures["generic"] > 0,
    }

    # Iterate in a standard order to mimic real filings.
    for category in ["IR", "FX", "CP", "EQ", "GEN"]:
        # --- FIX: Generate a narrative section if the category has either instruments OR an underlying exposure. ---
        has_instruments = category in aggregated_data
        has_exposure = all_relevant_categories.get(category, False)

        if has_instruments or has_exposure:
            # If there are no instruments, yearly_data will be empty, but the function can still generate context.
            yearly_data_for_cat = aggregated_data.get(category, {})
            category_sentences, category_evidence, _ = _generate_category_narrative(
                category, yearly_data_for_cat, scenario
            )
            if category_sentences:
                narrative_sections.append(" ".join(s.strip() for s in category_sentences if s))
            all_evidence.extend(category_evidence)

    # 3. Effectiveness and Accounting Section
    accounting_sentences, accounting_evidence = _generate_narrative_accounting(scenario)
    if accounting_sentences:
        narrative_sections.append(" ".join(s.strip() for s in accounting_sentences if s))
    all_evidence.extend(accounting_evidence)

    # =========================================================================
    # FINAL ASSEMBLY: Join sections with newlines for a prettier output.
    # =========================================================================
    # Join the sections with double newlines to create distinct paragraphs.
    narrative = "\n\n".join(section for section in narrative_sections if section)

    # Prepend the reporting year tag.
    full_narrative = f"<reportingYear>{scenario.reporting_year}</reportingYear> {narrative}"
    return full_narrative, all_evidence


def _generate_analysis_summary(
    scenario: GenerationScenario, evidence: List[BaseNarrativeEvidence]
) -> str:
    """Dynamically generates a one-sentence analysis summary."""
    summary_phrases = set()
    for item in evidence:
        if item.status in ["summary", "new", "comparative", "individual"]:
            summary_phrases.add(f"utilizes {item.category} derivatives")

    if not summary_phrases:
        return "The company does not appear to use derivative instruments."

    return f"The company's risk management strategy {', '.join(sorted(list(summary_phrases)))} to hedge market exposures."


def generate_json_from_scenario(
    scenario: GenerationScenario, evidence: List[BaseNarrativeEvidence]
) -> Dict:
    """
    Generates the target JSON output from the scenario object.
    The `evidence` from the narrative is used to generate the summary and chain_of_thought.
    """
    analysis_summary = _generate_analysis_summary(scenario, evidence)

    # --- NEW: Generate exposure and mitigation maps ---
    # Exposure is based on the archetype's potential risks.
    archetype_exposures = scenario.archetype.get_exposure_counts()
    exposure_map = {
        "IR": archetype_exposures["debt"] > 0,
        "FX": archetype_exposures["fx"] > 0,
        "CP": archetype_exposures["commodity"] > 0,
        "EQ": archetype_exposures["equity"] > 0,
        "GEN": archetype_exposures["generic"] > 0,
    }

    # --- NEW: Mitigation status is now "current", "historical", or "never" ---
    # It's driven by the usage_status in the MitigationEvidence objects.
    # --- NEW: Use "none" if no exposure exists, otherwise default to "never". ---
    mitigation_map = {
        cat: "never" if exposure_map.get(cat) else "none"
        for cat in DERIVATIVE_CATEGORIES
    }
    for ev in evidence:
        if isinstance(ev, MitigationEvidence):
            status = ev.usage_status
            category = ev.category
            if category in mitigation_map:
                # Map the detailed usage_status to the simpler "current", "historical", "never"
                if status == "current":
                    mitigation_map[category] = "current"
                elif status == "historical":
                    mitigation_map[category] = "historical"
                elif status == "speculative":
                    mitigation_map[category] = "unknown"
                # "non_use" maps to "never" as it's an explicit statement of non-activity.

    chain_of_thought = " ".join([e.to_string() for e in evidence])

    # --- Append a final reasoning statement for any GENERIC derivatives ---
    # This logic is now centralized here, instead of in the Evidence class.
    has_generic_evidence = any(ev.category == "GEN" for ev in evidence)
    if has_generic_evidence:
        # Find other specific instrument types that were identified in the text.
        seen_instrument_types = sorted(
            list(
                {
                    ev.instrument_type
                    for ev in evidence
                    if isinstance(ev, NotionalEvidence) and ev.category != "GEN" and ev.instrument_type
                }
            )
        )

        generic_reasoning = " A generic derivative reference was identified. Because the statement does not specify a clear derivative category"
        if seen_instrument_types:
            generic_reasoning += f" (such as the other instruments found: {', '.join(seen_instrument_types)}), I cannot link it to a specific known type and will therefore treat it as a generic reference."
        else:
            generic_reasoning += ", I cannot link it to a specific known type and will therefore treat it as a generic reference."
        chain_of_thought += generic_reasoning

    # --- Build the derivatives list ONLY from what was mentioned in the evidence. ---

    # This ensures the JSON perfectly matches the narrative. Each piece of evidence
    # that points to a specific instrument contributes to its entry in the final JSON.
    derivatives_list = []
    # Use a dictionary to aggregate evidence for each instrument ID mentioned.
    # This allows us to build a detailed picture of each derivative.
    instrument_evidence_map: Dict[int, Dict] = {}

    for ev in evidence:
        # We only care about evidence that has an instrument ID and notional value.
        if (
            not isinstance(ev, NotionalEvidence)
            or ev.instrument_id is None
            or ev.notional is None
        ):
            continue

        instrument_id = ev.instrument_id

        # Initialize the instrument if it's the first time we see it
        if instrument_id not in instrument_evidence_map:
            # Determine status directly from the evidence's own status field.
            status = "terminated" if ev.status == "terminated_individual" else "current"

            instrument_evidence_map[instrument_id] = {
                "type": ev.instrument_type or "Unknown",
                "category": ev.category,
                "status": status,
                "notional_amount": 0,
                "currency": ev.currency,
                "value_type": ev.value_type,
            }

        # Update the notional amount. This will capture the most relevant value
        # (e.g., the 'new' or 'terminated' value for that instrument).
        instrument_evidence_map[instrument_id]["notional_amount"] = ev.notional

        # Update status based on evidence type. 'terminated' is a final state.
        if ev.status == "terminated_individual":
            instrument_evidence_map[instrument_id]["status"] = "terminated"


    # Convert the aggregated map into the final list, matching the TODO.md schema.
    # This creates one entry per unique instrument ID found in the evidence.
    derivatives_list = list(instrument_evidence_map.values())

    # Additionally, add entries for aggregate summaries that don't have an instrument ID
    for ev in evidence:
        if (
            isinstance(ev, NotionalEvidence)
            and ev.instrument_id is None
            and ev.status == "summary"
            and ev.notional is not None
            and ev.notional > 0
        ):
            derivatives_list.append(
                {
                    "type": ev.instrument_type,
                    "category": ev.category,
                    "status": "current",
                    "notional_amount": ev.notional,
                    "currency": ev.currency,
                    # Add value_type to summary entries as well
                    "value_type": ev.value_type,
                }
            )

    return {
        "chain_of_thought": chain_of_thought,
        "analysis_summary": analysis_summary,
        "exposure": exposure_map,
        "mitigation": mitigation_map,
        "derivatives": derivatives_list,
    }

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
