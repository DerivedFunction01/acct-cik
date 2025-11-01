# %%
import random
import pandas as pd
from collections import Counter
import json, re
from typing import List, Dict, Optional, Set, Tuple

from defs.common_data import *
from defs.commodity_data import get_random_commodity_and_unit, get_cost_types_for_commodity
from defs.debt_data import *
from defs.template_definitions import *
from defs.class_definitions import (
    AccountingPolicySentence,
    BaseNarrativeEvidence,
    HedgedItem,
    MitigationEvidence,
    NotionalEvidence,
    PolicyEvidence, # type: ignore
    SpecificDetails,
    PolicySentence,
    NotionalSentence,
    TimelineSentence,
    NotionalInstrument,
    DebtHedgedItem,
    CounterpartyRiskSentence,
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


def _create_contextual_alias(base_type: str, category: str, placeholder: str, all_other_base_types: Set[str]) -> str:
    """
    Creates a context-aware alias for an instrument. If the base type is unique
    across the scenario, a simple alias is used. Otherwise, a category prefix is added.

    Args:
        base_type: The base type of the current instrument (e.g., "swap").
        category: The category of the current instrument (e.g., "IR").
        placeholder: The placeholder used in the instrument name (e.g., "cross-currency").
        all_other_base_types: A set of all base types present in the scenario.

    Returns:
        A contextually appropriate alias string.
    """
    # NEW: Handle special suffixes like "put option" explicitly.
    # This ensures the full two-word phrase is treated as the base.
    for special_suffix in DERIVATIVE_COMPONENTS["special_suffixes"]:
        if special_suffix in base_type:
            alias_base = special_suffix
            break
    else:
        # Fallback for other types.
        alias_base = " ".join(base_type.split()[-2:]) if len(base_type.split()) > 1 else base_type

    is_base_type_unique = base_type not in all_other_base_types

    # --- NEW: Prevent aliasing for certain generic types ---
    no_alias_types = DERIVATIVE_COMPONENTS.get("no_alias_types", [])
    if any(no_alias_word in base_type for no_alias_word in no_alias_types):
        return base_type

    # If the base type is unique, or a generic term, or already specific (like cross-currency), don't add a prefix.
    if is_base_type_unique or alias_base in ["swap"] or "cross-currency" in placeholder:
        return alias_base
    
    category_prefix_map = {"IR": "IR", "FX": "FX", "CP": "commodity", "EQ": "equity"}
    category_prefix = category_prefix_map.get(category, "")
    return f"{category_prefix} {alias_base}".strip()

# --- Dynamic Instrument Type Generation ---
def _generate_instrument_name(
    category: str,
    hedged_item: Optional["HedgedItem"] = None,
    available_base_types: Optional[List[str]] = None,
    all_scenario_base_types: Optional[Set[str]] = None,
) -> Tuple[str, str, str, str, str, str]:
    """
    Dynamically generates a derivative instrument name based on category and context.
    This replaces the pre-expanded `derivative_keywords` logic.

    Returns:
        A tuple of (prefix, placeholder, base_type, suffix, full_name, alias).
    """
    components= DERIVATIVE_COMPONENTS
    placeholders = components["placeholders"].get(category, [""])
    base_types = available_base_types or components["base_types"]
    suffixes = components["suffixes"]  # e.g., contract, agreement
    special_suffixes = components["special_suffixes"]  # e.g., put option
    special_ratio = 0.10  # configurable

    if (
        category == "IR"
        and isinstance(hedged_item, DebtHedgedItem)
        and hedged_item.benchmark_rate
    ):
        # 35% chance to use the specific placeholder if found, otherwise use the generic "interest-rate".
        placeholder = hedged_item.benchmark_rate if random.random() < 0.35 else random.choice(placeholders)
    else:
        placeholder = random.choice(placeholders)

    base_type = random.choice(base_types)

    # --- Assemble the name ---
    use_special = special_suffixes and random.random() < special_ratio
    suffix = ""
    if use_special:
        chosen = random.choice(special_suffixes)
        full_name = " ".join(filter(None, [placeholder, chosen])).strip()
        base_type = chosen # treat as base for alias/prefix logic
    else:
        suffix = random.choice(suffixes)
        full_name = " ".join(filter(None, [placeholder, base_type, suffix])).strip()

    # --- NEW: Context-aware alias generation ---
    other_base_types = (all_scenario_base_types or set()) - {base_type}
    alias = _create_contextual_alias(base_type, category, placeholder, other_base_types)

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

    return prefix, placeholder, base_type, suffix, full_name, alias

def _create_instrument_with_history(
    scenario: GenerationScenario,
    instrument_class: type,
    instrument_id: int,
    base_instrument_args: Dict,
) -> NotionalInstrument:
    """
    Creates a single instrument and populates its history for previous years.

    For a single instrument ID, this generates one instrument object containing a
    `notional_history` dictionary, which maps years to notional amounts.
    The history can extend back a variable number of years.

    Args:
        scenario: The GenerationScenario to which instruments will be added.
        instrument_class: The class of the instrument to create (e.g., IRInstrument).
        instrument_id: The unique ID for this instrument and its history.
        base_instrument_args: A dictionary of arguments for the instrument constructor,
                              including the notional amount for the *current* reporting year.

    Returns:
        A single NotionalInstrument instance with its history populated.
    """
    current_year = scenario.reporting_year
    current_notional = base_instrument_args.pop("notional_amount")

    # The history dictionary will store {year: notional}
    notional_history = {current_year: current_notional}

    # Create historical versions for the previous 2-7 years
    num_historical_years = random.randint(2, 7)
    last_notional = current_notional
    for i in range(1, num_historical_years + 1):
        historical_year = current_year - i
        # Simulate a slightly different notional amount for the previous year
        last_notional = int(last_notional * random.uniform(0.85, 1.15))
        notional_history[historical_year] = max(0, last_notional) # Ensure notional doesn't become negative

    # Create the single instrument instance with the complete history
    instrument = instrument_class(
        instrument_id=instrument_id,
        notional_history=notional_history,
        **base_instrument_args,
    )

    return instrument


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

    # --- NEW: Pre-determine all base types that will be used in the scenario ---
    # This allows for context-aware alias generation.
    all_base_types = DERIVATIVE_COMPONENTS["base_types"]
    num_to_reserve = random.randint(1, 2)
    gen_reserved_base_types = random.sample(all_base_types, num_to_reserve)
    other_available_base_types = [bt for bt in all_base_types if bt not in gen_reserved_base_types]
    
    potential_hedged_items: Dict[str, List] = {
        "debt": [],
        "fx": [],
        "commodity": [],
        "equity": [],
    }

    # --- NEW: Determine the set of all base_types that will appear in this scenario ---
    # This is a proxy; the actual instruments are created later.
    all_scenario_base_types = set()
    if exposure_counts["debt"] > 0: all_scenario_base_types.add(random.choice(other_available_base_types))
    if exposure_counts["fx"] > 0: all_scenario_base_types.add(random.choice(other_available_base_types))
    if exposure_counts["commodity"] > 0: all_scenario_base_types.add(random.choice(other_available_base_types))
    if exposure_counts["equity"] > 0: all_scenario_base_types.add(random.choice(other_available_base_types))
    if exposure_counts["generic"] > 0: all_scenario_base_types.add(random.choice(gen_reserved_base_types))


    # --- Generate Debt Exposures ---
    for _ in range(exposure_counts["debt"]):
        issuance_year = random.randint(reporting_year - 15, reporting_year - 1)
        maturity_year = random.randint(reporting_year + 2, reporting_year + 20)

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
        suffix = ""

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
                maturity_year = random.randint(reporting_year - 5, reporting_year) # Expired in the last 5 years
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
            prefix, placeholder, base_type, suffix, name, alias = _generate_instrument_name("IR", hedged_item=debt_item, available_base_types=other_available_base_types, all_scenario_base_types=all_scenario_base_types)

        base_args = {
            "instrument_type": name,
            "instrument_alias": alias,            
            "notional_amount": notional,
            "start_month": random.choice(months),
            "start_year": random.randint(reporting_year - 10, reporting_year -1),
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": hedged_debt,
            "instrument_prefix": prefix,
            "placeholder": placeholder,
            "base_type": base_type,
            "suffix": suffix,
        }

        # Create the single instrument object with its full history
        new_instrument = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=FXInstrument if is_cross_currency else IRInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.append(new_instrument)
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

        prefix, placeholder, base_type, suffix, name, alias = _generate_instrument_name("FX", available_base_types=other_available_base_types, all_scenario_base_types=all_scenario_base_types)

        base_args = {
            "instrument_type": name,
            "instrument_alias": alias,
            "start_month": random.choice(months),
            "start_year": random.randint(reporting_year - 5, reporting_year -1),
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": hedged_fx,
            "instrument_prefix": prefix,
            "placeholder": placeholder,
            "base_type": base_type,
            "suffix": suffix,
        }

        new_instrument = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=FXInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.append(new_instrument)
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

        prefix, placeholder, base_type, suffix, name, alias = _generate_instrument_name("CP", available_base_types=other_available_base_types, all_scenario_base_types=all_scenario_base_types)

        base_args = {
            "instrument_type": name,
            "instrument_alias": alias,
            "start_month": random.choice(months),
            "start_year": random.randint(reporting_year - 5, reporting_year -1),
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": hedged_commodity,
            "instrument_prefix": prefix,
            "placeholder": placeholder,
            "base_type": base_type,
            "suffix": suffix,
        }

        new_instrument = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=CPInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.append(new_instrument)
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

        prefix, placeholder, base_type, suffix, name, alias = _generate_instrument_name("EQ", available_base_types=other_available_base_types, all_scenario_base_types=all_scenario_base_types)

        base_args = {
            "instrument_type": name,
            "instrument_alias": alias,
            "start_month": random.choice(months),
            "start_year": random.randint(reporting_year - 5, reporting_year -1),
            "notional_amount": notional,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": hedged_equity,
            "instrument_prefix": prefix,
            "placeholder": placeholder,
            "base_type": base_type,
            "suffix": suffix,
        }

        new_instrument = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=EQInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.append(new_instrument)
        instrument_id_counter += 1

    # --- Create Generic Instruments ---
    for _ in range(exposure_counts.get("generic", 0)):

        is_terminated = random.random() < 0.4
        maturity_year = (
            random.randint(reporting_year - 3, reporting_year)
            if is_terminated
            else random.randint(reporting_year + 1, reporting_year + 5)
        )

        prefix, placeholder, base_type, suffix, name, alias = _generate_instrument_name("GEN", available_base_types=gen_reserved_base_types, all_scenario_base_types=all_scenario_base_types)

        base_args = {
            "instrument_type": name,
            "instrument_alias": alias,
            "start_month": random.choice(months),
            "start_year": random.randint(reporting_year - 5, reporting_year -1),
            "notional_amount": random.randint(10, 300) * multiplier,
            "currency": archetype.default_currency,
            "maturity_year": maturity_year,
            "hedge_designation": random.choice(hedge_designations),
            "hedged_item": None,  # Generic instruments often don't have a specific hedged item
            "instrument_prefix": prefix,
            "placeholder": placeholder,
            "base_type": base_type,
            "suffix": suffix,
        }

        new_instrument = _create_instrument_with_history(
            scenario=scenario,
            instrument_class=GenericInstrument,
            instrument_id=instrument_id_counter,
            base_instrument_args=base_args,
        )
        scenario.instruments.append(new_instrument)
        instrument_id_counter += 1

    return scenario

def _get_smart_instrument_description(instruments: List[NotionalInstrument], category: str) -> str:
    """
    Generates a smart, concatenated description of the instruments used.
    """
    if not instruments:
        return "derivatives"

    count = len(instruments)
    unique_types = sorted(list({i.instrument_type for i in instruments}))

    if count == 1:
        return instruments[0].instrument_type

    if count == 2 and len(unique_types) > 1:
        return f"{unique_types[0]} and {unique_types[1]}"

    # Check for similarity based on placeholder
    placeholders = {i.placeholder for i in instruments}
    if len(placeholders) == 1:
        placeholder = list(placeholders)[0]
        # Concatenate base_type + suffix
        combined_names = []
        for inst in instruments:
            # Combine base_type and suffix, but handle cases where one is empty
            # e.g., "put option" might have base_type "put option" and empty suffix
            if inst.base_type and inst.suffix and inst.base_type in inst.suffix:
                combined_names.append(inst.suffix)
            else:
                combined_names.append(f"{inst.base_type} {inst.suffix}".strip())

        unique_combined = sorted(list(set(combined_names)))
        if len(unique_combined) <= 3:
            # "interest-rate swaps, contracts, and agreements"
            return f"{placeholder} {', '.join(unique_combined[:-1])} and {unique_combined[-1]}"

    # Fallback for 4+ instruments or dissimilar instruments
    if count >= 4:
        # Check for a dominant placeholder
        placeholder_counts = Counter(i.placeholder for i in instruments)
        most_common_placeholder, num_most_common = placeholder_counts.most_common(1)[0]

        if num_most_common >= 2:
            # "interest-rate swaps and other interest rate instruments"
            dominant_instrument_example = next(i.instrument_type for i in instruments if i.placeholder == most_common_placeholder)
            return f"{dominant_instrument_example} and other {most_common_placeholder} instruments"
        else:
            # "a portfolio of derivative instruments"
            return f"a {random.choice(portfolio_terms).format(swap_type=f'{category} derivatives')}"

    return "various derivative instruments"

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
        # --- Always generate a high-level, generic risk exposure sentence first ---
        # This acts as a standard introductory statement, similar to Item 7A.
        policy_sentence_obj = PolicySentence(
            category="GEN", # Always start with a generic context
            company_name=scenario.company_name,
        )
        policy_sentence, policy_evidence = policy_sentence_obj.build()
        sentences.append(policy_sentence)

        # Determine if there are any active instruments in the reporting year.
        has_active_derivatives = any(
            inst.notional_history.get(scenario.reporting_year, 0) > 0
            for inst in scenario.instruments
        )
        instrument_categories_in_year = [inst.category for inst in scenario.instruments if has_active_derivatives]

        # Only add evidence if there are actual instruments. A general policy
        # statement for a non-user is just context, not evidence of a derivative.
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
        if scenario.policy.general_policy.counterparty_credit_risk_monitored:
            counterparty_sentence_obj = CounterpartyRiskSentence(
                company_name=scenario.company_name,
                counterparty_details=scenario.policy.general_policy.counterparty_details,
                has_active_derivatives=has_active_derivatives,
            )
            sentence = counterparty_sentence_obj.build()
            sentences.append(sentence) # No evidence is generated for this policy statement
    return sentences, evidence


def _generate_category_narrative(
    category: str,
    yearly_data: Dict,
    scenario: GenerationScenario,
    part: Literal["summary", "details"],
    mentioned_instrument_fingerprints: Optional[Set[Tuple[str, int, str]]] = None,
) -> Tuple[List[str], List[BaseNarrativeEvidence], Optional[str]]:
    """
    Generates a narrative section for a single derivative category (e.g., Interest Rate Risk).
    This includes context, a summary of instruments, and details on changes.

    Args:
        mentioned_instrument_fingerprints: A set to track instrument "fingerprints" that have already been mentioned.
        part: "summary" to generate policy/mitigation/aggregate, "details" for individual instruments.
    """
    sentences, evidence, used_name = [], [], None
    reporting_year, reporting_month, reporting_day = (
        scenario.reporting_year,
        scenario.reporting_month,
        scenario.reporting_day,
    )
    current_year_data = yearly_data.get(reporting_year)
    prev_year_data = yearly_data.get(reporting_year - 1)

    # Get currency and money unit details for sentence generation
    currency_symbol, money_unit_word, currency_code = _get_currency_and_unit_details(
        scenario
    )

    # --- Part 1: Generate Policy, Mitigation, and optional Aggregate Summary ---
    if part == "summary":
        # 1a. Context Sentence (e.g., "To manage our interest rate risk...")
        specific_details = SpecificDetails()  # type: ignore
        location_names = []
        if current_year_data and current_year_data["instruments"]:
            instrument_with_hedged_item = next(
                (inst for inst in current_year_data["instruments"] if inst.hedged_item),
                None,
            )
            if instrument_with_hedged_item:
                hedged_item = instrument_with_hedged_item.hedged_item
                if isinstance(hedged_item, CommodityHedgedItem):
                    specific_details.commodity = hedged_item.commodity_type
                    specific_details.unit = hedged_item.unit_of_volume
                elif isinstance(hedged_item, ForeignCurrencyHedgedItem):
                    locations = [exp.location for exp in hedged_item.exposures]
                    location_names = list(set(locations))
                    if location_names:
                        specific_details.geography = random.choice(location_names)
                elif isinstance(hedged_item, DebtHedgedItem):
                    specific_details.debt_type = hedged_item.debt_type
                    specific_details.pct = (
                        hedged_item.fixed_rate_pct or hedged_item.change_rate_pct
                    )
                    specific_details.frequency = hedged_item.payment_frequency

        policy_sentence_obj = PolicySentence(
            category=category, # type: ignore
            company_name=scenario.company_name,
            specific_details=specific_details,
            locations=location_names,
        )
        context_sentence, _ = policy_sentence_obj.build()
        sentences.append(context_sentence)

        # 1b. Mitigation/Purpose Sentence
        has_active_instruments = bool(
            current_year_data and current_year_data["instruments"]
        ) # type: ignore
        past_prop, current_prop = scenario.archetype.hedging_propensities.get(category, (0.0, 0.0)) # type: ignore
        usage = (
            "current"
            if has_active_instruments
            else (
                "non_use"
                if current_prop < 0
                else (
                    "historical"
                    if past_prop > 0 and current_prop == 0
                    else "speculative"
                )
            )
        )
        instrument_type = _get_smart_instrument_description(current_year_data["instruments"], category) if has_active_instruments and current_year_data else "derivatives"

        mitigation_sentence_obj = MitigationSentence(
            category=category, # type: ignore
            company_name=scenario.company_name,
            swap_type=instrument_type,
            has_active_instruments=has_active_instruments,
            usage_status=usage,
            year=reporting_year,
            month=reporting_month,
            end_day=reporting_day,
            specific_details=specific_details,
        )
        mitigation_sentence, mitigation_evidence = mitigation_sentence_obj.build()
        sentences.append(mitigation_sentence)
        evidence.append(mitigation_evidence)

        # 1c. Optional Aggregate Summary
        is_non_use_mitigation = mitigation_evidence.usage_status == "non_use"
        if (
            current_year_data
            and current_year_data["instruments"]
            and not is_non_use_mitigation
            and random.random() < 0.5
        ):
            total_notional = current_year_data["total_notional"]
            use_fair_value = random.random() < 0.2 # type: ignore
            value_type_to_use = "fair_value" if use_fair_value else "notional"
            value_to_report = (
                max(1, int(total_notional / random.randint(20, 100)))
                if use_fair_value
                else total_notional
            )

            summary_sentence_obj = NotionalSentence(
                swap_type=instrument_type,
                year=reporting_year,
                notional=value_to_report,
                currency_symbol=currency_symbol,
                month=reporting_month,
                end_day=reporting_day,
                money_units=scenario.archetype.money_units,
                prefer_abbreviated=scenario.number_format_preference,
                category=category, # type: ignore
                reporting_year=reporting_year,
                value_type=value_type_to_use,
                specific_details=specific_details,
            )
            summary_sentence_text, evidence_obj = summary_sentence_obj.build()
            sentences.append(summary_sentence_text)
            evidence.append(evidence_obj)

    # --- Part 2: Generate Detailed Individual Instrument Sentences ---
    elif part == "details":
        # NEW: This will be a list of paragraph strings.
        if mentioned_instrument_fingerprints is None:
            # This should be passed from the calling function, but as a fallback, initialize it.
            mentioned_instrument_fingerprints = set()

        paragraphs = []

        # Describe individual instruments that are currently active
        if current_year_data and current_year_data["instruments"]:
            for instrument in current_year_data["instruments"]:
                use_fair_value = random.random() < 0.2
                # --- NEW: Create a "fingerprint" for the instrument based on its properties ---
                instrument_fingerprint = (instrument.instrument_type, instrument.maturity_year, instrument.currency)
                is_repeated = instrument_fingerprint in mentioned_instrument_fingerprints

                value_type = "fair_value" if use_fair_value else "notional"
                value_to_report = instrument.notional_history.get(reporting_year, 0)
                if use_fair_value:
                    value_to_report = max(
                        1, int(value_to_report / random.randint(20, 100))
                    )

                # --- NEW: Decide whether to use the full name or the alias ---
                # If we've seen this instrument before, there's a high chance of using its alias.
                # Otherwise, there's a small chance to use the alias for variety.
                use_alias = (is_repeated and random.random() < 0.75) or (random.random() < 0.2)
                name_to_use = instrument.instrument_alias if use_alias and instrument.instrument_alias else instrument.instrument_type

                # Determine if the instrument is "historical" (existed in a prior year) # type: ignore
                is_historical = False
                if prev_year_data:
                    prev_ids = {i.instrument_id for i in prev_year_data["instruments"]}
                    if (
                        instrument.instrument_id in prev_ids
                        and instrument.instrument_id
                        not in (current_year_data.get("new_ids", set())) # type: ignore
                    ):
                        is_historical = True

                # --- NEW: Timeline generation for instruments with a long history ---
                history_length = len(instrument.notional_history)
                # 25% chance to generate a timeline for instruments with 5+ years of history
                is_long_history_timeline = is_historical and history_length > 4 and random.random() < 0.25

                # --- NEW: Use TimelineSentence class for long histories ---
                if is_long_history_timeline:
                    timeline_builder = TimelineSentence(
                        instrument=instrument,
                        company_name=scenario.company_name,
                        reporting_year=reporting_year,
                        currency_symbol=currency_symbol,
                        currency_code=currency_code,
                        money_units=scenario.archetype.money_units,
                        prefer_abbreviated=scenario.number_format_preference,
                        value_type=value_type,
                    )
                    timeline_paragraph, timeline_evidence = timeline_builder.build()

                    if timeline_paragraph:
                        paragraphs.append(timeline_paragraph)
                        evidence.extend(timeline_evidence)
                        # Mark as mentioned for all future references
                        mentioned_instrument_fingerprints.add(instrument_fingerprint)

                    continue  # Skip the normal individual sentence generation for this instrument

                # --- Standard sentence generation (current, historical, or inception) ---
                else:
                    sentence_type = "individual"
                    year_to_report = reporting_year
                    notional_to_report = value_to_report

                    if is_historical and random.random() < 0.35: # 35% chance for a historical sentence
                        sentence_type = "historical_individual"
                        # 50% chance to talk about the inception year vs. a random past year
                        if random.random() < 0.5 and instrument.start_year in instrument.notional_history:
                            year_to_report = instrument.start_year
                            notional_to_report = instrument.notional_history[instrument.start_year]
                            if use_fair_value:
                                notional_to_report = max(1, int(notional_to_report / random.randint(20, 100)))
                        else:
                            past_years = [y for y in instrument.notional_history.keys() if y < reporting_year]
                            if past_years:
                                year_to_report = random.choice(past_years)
                                notional_to_report = instrument.notional_history[year_to_report]
                                if use_fair_value:
                                    notional_to_report = max(1, int(notional_to_report / random.randint(20, 100)))

                    individual_sentence_obj = NotionalSentence(
                        swap_type=name_to_use, year=year_to_report, notional=notional_to_report,
                        currency_symbol=currency_symbol, company_name=scenario.company_name, sentence_type=sentence_type, # type: ignore
                        money_units=scenario.archetype.money_units,
                        maturity_year=instrument.maturity_year, prefer_abbreviated=scenario.number_format_preference,
                        category=category, reporting_year=reporting_year, value_type=value_type, # type: ignore
                        is_repeated_mention=is_repeated,
                    )
                individual_sentence_text, evidence_obj = individual_sentence_obj.build()
                evidence_obj.instrument_id = (
                    instrument.instrument_id # type: ignore
                )
                paragraphs.append(individual_sentence_text)
                evidence.append(evidence_obj)
                mentioned_instrument_fingerprints.add(instrument_fingerprint) # Mark as mentioned
        # Describe terminated instruments by looking at the previous year's data
        if prev_year_data:
            terminated_instrument_ids = {
                i.instrument_id for i in prev_year_data["instruments"]
            } - {
                i.instrument_id
                for i in (current_year_data["instruments"] if current_year_data else [])
            }
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
                    use_fair_value_terminated = random.random() < 0.2
                    value_type_terminated = (
                        "fair_value" if use_fair_value_terminated else "notional"
                    ) # type: ignore
                    value_to_report_terminated = instrument.notional_history.get(reporting_year - 1, 0)
                    if use_fair_value_terminated:
                        value_to_report_terminated = max( # type: ignore
                            1, int(value_to_report_terminated / random.randint(20, 100))
                        )

                    instrument_fingerprint_terminated = (instrument.instrument_type, instrument.maturity_year, instrument.currency)
                    is_repeated_terminated = instrument_fingerprint_terminated in mentioned_instrument_fingerprints
                    # Decide whether to use alias for terminated instruments as well
                    use_alias_terminated = (is_repeated_terminated and random.random() < 0.75) or (random.random() < 0.2)
                    name_to_use_terminated = instrument.instrument_alias if use_alias_terminated and instrument.instrument_alias else instrument.instrument_type

                    terminated_instrument_obj = NotionalSentence(
                        swap_type=name_to_use_terminated,
                        year=reporting_year,
                        notional=value_to_report_terminated,
                        currency_symbol=currency_symbol,
                        company_name=scenario.company_name,
                        sentence_type="terminated_individual", # type: ignore
                        money_units=scenario.archetype.money_units,
                        maturity_year=instrument.maturity_year,
                        prefer_abbreviated=scenario.number_format_preference,
                        category=category, reporting_year=reporting_year, value_type=value_type_terminated, # type: ignore
                        is_repeated_mention=is_repeated_terminated,
                    )
                    terminated_instrument_text, evidence_obj = (
                        terminated_instrument_obj.build()
                    )
                    evidence_obj.instrument_id = instrument.instrument_id
                    paragraphs.append(terminated_instrument_text)
                    mentioned_instrument_fingerprints.add(instrument_fingerprint_terminated) # Mark as mentioned
                    evidence.append(evidence_obj)

        # If there are no current instruments, check for a comparative no-outstanding sentence
        if (
            not (current_year_data and current_year_data["instruments"])
            and prev_year_data
            and prev_year_data["total_notional"] > 0
        ):
            instrument_type = (
                prev_year_data["instrument_types"][0]
                if prev_year_data["instrument_types"]
                else "derivative instrument"
            )
            # Create specific_details for the comparative sentence
            comparative_no_outstanding_obj = NotionalSentence(
                swap_type=instrument_type,
                year=reporting_year,
                notional=prev_year_data["total_notional"], # Pass the prior year notional for the template
                sentence_type="comparative_no_outstanding", # type: ignore
            )
            no_instrument_text, evidence_obj = comparative_no_outstanding_obj.build()
            paragraphs.append(no_instrument_text)
            evidence.append(evidence_obj)

        # Return the list of paragraphs instead of a flat list of sentences
        sentences = paragraphs

    return sentences, evidence, used_name # type: ignore


def _generate_narrative_accounting(
    scenario: GenerationScenario,
) -> Tuple[List[str], List[BaseNarrativeEvidence]]:
    """Generates sentences about accounting treatment and hedge effectiveness."""
    all_sentences: List[str] = []
    all_evidence: List[BaseNarrativeEvidence] = []  # type: ignore
    mentioned_policies = set()
    
    # --- NEW: Generate accounting policies for each category with instruments ---
    if scenario.policy and scenario.policy.category_policies:
        # Get all categories that have active instruments in the reporting year
        active_categories = {
            inst.category
            for inst in scenario.instruments
            if inst.notional_history.get(scenario.reporting_year, 0) > 0
        }

        # Find the corresponding policies for those active categories
        policies_to_generate = [
            p for p in scenario.policy.category_policies if p.category in active_categories
        ]

        for cat_policy in policies_to_generate:
            # Generate a descriptive instrument type for the category
            instruments_in_cat = [i for i in scenario.instruments if i.category == cat_policy.category]
            swap_type_desc = _get_smart_instrument_description(instruments_in_cat, cat_policy.category)

            policy_sentence_builder = AccountingPolicySentence(
                cat_policy=cat_policy,
                company_name=scenario.company_name,
                already_mentioned_policies=mentioned_policies,
                swap_type_override=swap_type_desc, # Pass the specific swap type
            )
            generated_items = policy_sentence_builder.build()
            for sentence, evidence in generated_items:
                all_sentences.append(sentence)
                all_evidence.append(evidence) # type: ignore
                # --- FIX: Update the set with the policy type that was just used ---
                # This ensures it is not repeated for the next category.
                if isinstance(evidence, PolicyEvidence):
                    mentioned_policies.add(evidence.policy_type)

    return all_sentences, all_evidence


def generate_narrative_from_scenario(
    scenario: GenerationScenario,
) -> Tuple[str, List[BaseNarrativeEvidence]]:
    """
    Constructs a coherent, multi-paragraph narrative from a scenario object.
    This function will replace the old `generate_hedge_paragraph`.
    """
    item_7a_sections, derivative_details_sections = [], []
    all_evidence = []

    # =========================================================================
    # AGGREGATION: Summarize instruments by category and year.
    # =========================================================================
    aggregated_data: Dict[str, Dict[int, Dict]] = {}
    for instrument in scenario.instruments: # type: ignore
        cat = instrument.category # type: ignore
        for year, notional in instrument.notional_history.items(): # type: ignore
            if cat not in aggregated_data:
                aggregated_data[cat] = {}

            if year not in aggregated_data[cat]:
                aggregated_data[cat][year] = {
                    "total_notional": 0,
                    "count": 0,
                    "instrument_types": [],
                    "instruments": [],
                }

            aggregated_data[cat][year]["total_notional"] += notional
            aggregated_data[cat][year]["count"] += 1
            aggregated_data[cat][year]["instrument_types"].append(instrument.instrument_type) # type: ignore
            aggregated_data[cat][year]["instruments"].append(instrument)

    # =========================================================================
    # NARRATIVE CONSTRUCTION: Build the story section by section.
    # =========================================================================

    # --- NEW: Track which instruments have been mentioned (by fingerprint) to allow for "aha" moments ---
    mentioned_instrument_fingerprints: Set[Tuple[str, int, str]] = set()

    # 1. Generate the top-level general policy statement.
    policy_sentences, policy_evidence = _generate_narrative_policy(scenario)
    if policy_sentences: # This becomes its own section
        item_7a_sections.append(" ".join(s.strip() for s in policy_sentences if s))
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

    # --- Part 1: Build the "Item 7A" Summary Section ---
    for category in ["IR", "FX", "CP", "EQ", "GEN"]:
        has_instruments = category in aggregated_data
        has_exposure = all_relevant_categories.get(category, False)

        if has_instruments or (has_exposure and category != "GEN"):
            yearly_data_for_cat = aggregated_data.get(category, {})
            summary_sentences, summary_evidence, _ = _generate_category_narrative(
                category, yearly_data_for_cat, scenario, part="summary", mentioned_instrument_fingerprints=mentioned_instrument_fingerprints
            )
            item_7a_sections.append(" ".join(s.strip() for s in summary_sentences if s))
            all_evidence.extend(summary_evidence)

    # --- Part 2: Build the "Derivative Financial Instruments" Details Section ---
    # Add a title for this section if there are any details to report.
    has_any_details = any(
        cat in aggregated_data for cat in ["IR", "FX", "CP", "EQ", "GEN"]
    )
    if has_any_details:
        # This is a simple way to add a section header.
        derivative_details_sections.append("Derivative Financial Instruments")

    for category in ["IR", "FX", "CP", "EQ", "GEN"]:
        if category in aggregated_data:
            yearly_data_for_cat = aggregated_data.get(category, {})
            detail_sentences, detail_evidence, _ = _generate_category_narrative(
                category, yearly_data_for_cat, scenario, part="details", mentioned_instrument_fingerprints=mentioned_instrument_fingerprints
            )
            # NEW: Join the generated paragraphs with newlines.
            # This ensures timelines and individual instruments get their own paragraphs.
            category_details_paragraph = "\n\n".join(s.strip() for s in detail_sentences if s)
            derivative_details_sections.append(category_details_paragraph)
            all_evidence.extend(detail_evidence)

    # 3. Effectiveness and Accounting Section
    accounting_sentences, accounting_evidence = _generate_narrative_accounting(scenario)
    # This can be appended to the details section or be its own section.
    # Let's add it to the end of the details for now.
    if accounting_sentences and derivative_details_sections:
        accounting_section = " ".join(s.strip() for s in accounting_sentences if s)
        derivative_details_sections.append(accounting_section)
        all_evidence.extend(accounting_evidence)

    # =========================================================================
    # FINAL ASSEMBLY: Join sections with newlines for a prettier output.
    # =========================================================================

    # Assemble the final narrative from the generated parts
    narrative_sections = []
    narrative_sections.extend(item_7a_sections)
    narrative_sections.extend(derivative_details_sections)
    narrative = "\n\n".join(section for section in narrative_sections if section)
    # Prepend the reporting year tag.
    full_narrative = (
        f"<reportingYear>{scenario.reporting_year}</reportingYear> {narrative}"
    )
    # Post-warning: Check for the word "none" in the final narrative
    if "none" in full_narrative.lower():
        full_narrative += "\n\n[WARNING: The word 'none' was found in the narrative. Please review for potential ambiguity or unintended implications.]"
    return full_narrative, all_evidence


def _generate_debug_output(scenario: GenerationScenario) -> str:
    """
    Generates a formatted string containing debug information about the scenario,
    including archetype, instruments, and their hedged items (exposures).
    """
    debug_lines = ["\n\n--- DEBUG INFO ---"]
    debug_lines.append(f"Archetype: {scenario.archetype.name}")
    debug_lines.append(f"Reporting Year: {scenario.reporting_year}")
    debug_lines.append(f"Total Instruments: {len(scenario.instruments)}")
    debug_lines.append("=" * 20)

    # Create a set of all hedged item IDs to identify unhedged exposures
    hedged_item_ids = {
        inst.hedged_item.hedged_item_id
        for inst in scenario.instruments
        if inst.hedged_item
    }

    for i, inst in enumerate(scenario.instruments):
        debug_lines.append(f"\nInstrument {i+1}/{len(scenario.instruments)} (ID: {inst.instrument_id})")
        debug_lines.append(f"  - Type: {inst.instrument_type}")
        debug_lines.append(f"  - Category: {inst.category}")
        debug_lines.append(f"  - Start: {inst.start_month} {inst.start_year}")
        debug_lines.append(f"  - Maturity: {inst.maturity_year}")
        debug_lines.append(f"  - Notional History: {inst.notional_history}")

        if inst.hedged_item:
            hedged_item = inst.hedged_item
            debug_lines.append("  - Hedged Item (Exposure):")
            debug_lines.append(f"    - ID: {hedged_item.hedged_item_id}")
            debug_lines.append(f"    - Type: {type(hedged_item).__name__}")
            # Convert hedged item to dict for clean printing, excluding the ID which is already shown
            details = hedged_item.to_dict()
            if details:
                details.pop("hedged_item_id", None)
                debug_lines.append(f"    - Details: {json.dumps(details, indent=4)}")
        else:
            debug_lines.append("  - Hedged Item (Exposure): None")

    return "\n".join(debug_lines)


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
    # --- NEW: Join with newlines for readability ---
    chain_of_thought = "\n".join([e.to_string() for e in evidence])

    # --- Append a final reasoning statement for any GENERIC derivatives ---
    # This logic is now centralized here, instead of in the Evidence class.
    has_generic_evidence = any(ev.category == "GEN" for ev in evidence)
    if has_generic_evidence:
        # Find other specific instrument types that were identified in the text.
        all_seen_types = sorted(
            list(
                {
                    ev.instrument_type
                    for ev in evidence
                    if isinstance(ev, NotionalEvidence) and ev.category != "GEN" and ev.instrument_type
                }
            )
        )
        
        # --- NEW: Select a few similar-sounding instruments to mention ---
        # If there are only a few, list them all. Otherwise, be selective.
        if len(all_seen_types) > 4:
            # Pick a random instrument as a "seed"
            seed_instrument = random.choice(all_seen_types)
            seed_words = set(seed_instrument.split())
            
            # Find other instruments that share at least one word with the seed
            similar_instruments = {seed_instrument}
            for inst_type in all_seen_types:
                if inst_type != seed_instrument and seed_words.intersection(inst_type.split()):
                    similar_instruments.add(inst_type)
            
            # Limit to a small, random number (2 to 4) of examples
            # FIX: The lower bound must not be greater than the upper bound.
            # If there's only 1 similar instrument, randint(2, 1) would fail.
            # We now choose a number between 1 and the number of instruments (up to 4).
            upper_bound = min(4, len(similar_instruments))
            num_to_show = random.randint(1, upper_bound) if upper_bound > 0 else 0
            display_types = sorted(list(random.sample(list(similar_instruments), num_to_show)))
        else:
            display_types = all_seen_types
            
        generic_reasoning = " A generic derivative reference was identified. Because the statement does not specify a clear derivative category"
        if display_types:
            generic_reasoning += f" (such as the other instruments found: {', '.join(display_types)}), I cannot link it to a specific known type and will therefore treat it as a generic reference."
        else:
            generic_reasoning += ", I cannot link it to a specific known type and will therefore treat it as a generic reference."
        chain_of_thought += "\n" + generic_reasoning.strip()

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
            # Determine status directly from the evidence's own status field. # type: ignore
            status = "terminated" if ev.status == "terminated_individual" else "current"

            instrument_evidence_map[instrument_id] = {
                "type": ev.instrument_type or "Unknown",
                "category": ev.category,
                "status": status,
                "amount": 0,
                "currency": ev.currency,
                "value_type": ev.value_type,
                "level": "individual",
            }

        # Update the notional amount. This will capture the most relevant value
        # (e.g., the 'new' or 'terminated' value for that instrument).
        instrument_evidence_map[instrument_id]["amount"] = ev.notional

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
                    "level": "aggregate",
                    "status": "current",
                    "amount": ev.notional,
                    "currency": ev.currency,
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

    # --- NEW: Append debug output to the narrative text ---
    debug_output = _generate_debug_output(scenario)
    narrative_text += debug_output

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
