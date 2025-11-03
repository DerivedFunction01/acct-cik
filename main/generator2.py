# %%
from dataclasses import asdict
import random
import sys
import string
import pandas as pd
from collections import Counter
import json, re
from typing import List, Dict, Literal, Optional, Set, Tuple

from defs.scenario_definitions import GenerationScenario, ScenarioArchetype
from defs.fx_data import ForeignCurrencyHedgedItem, all_currencies, CurrencyExposure, FXInstrument, FXContextSentence
from defs.common_data import *
from defs.cp_data import CPContextSentence, CommodityHedgedItem, CPInstrument, get_random_commodity_and_unit
from defs.instrument_definitions import DERIVATIVE_CATEGORIES, BaseNarrativeEvidence, NotionalInstrument, HedgedItem, GenericInstrument
from defs.policy_definitions import (
    AccountingPolicySentence,
    CounterpartyRiskSentence,
    ExposureEvidence,
    GeneralHedgingPolicy,
    MitigationEvidence,
    MitigationSentence,
    PolicyEvidence,
    PolicySentence,
    RiskManagementPolicy,
    CategorySpecificPolicy,
)
from defs.scenario_definitions import company_names
from defs.ir_data import DebtHedgedItem, DebtType, all_debt_types, IRInstrument, DebtContextSentence
from defs.notional_definitions import NotionalEvidence, NotionalSentence, TimelineSentence, SpecificDetails
from defs.template_definitions import hedge_no_trading_templates, DerivativeTable
from defs.eq_data import EQContextSentence, EQInstrument, EquityHedgedItem, _generate_stock_symbol

DEBUG = True
ACTIVE_INSTRUMENT_MENTION_PROB = 0
TERMINATED_INSTRUMENT_MENTION_PROB = 0
REPEAT_MENTION_PROB = 0

# Probabilities for dropping narrative components to increase variety
PROB_DROP_MITIGATION = 1.0  # 15% chance to skip the MitigationSentence
PROB_DROP_ACCOUNTING_POLICY = 1.0 # 20% chance to skip the entire accounting policy section
PROB_DROP_7A_SUMMARY = 1.0 # 10% chance to skip the entire Item 7A-style summary section
PROB_DROP_GENERAL_POLICY = 1.0 # 15% chance to skip the top-level policy statements

# NEW: Global list to track dropped sentences for debugging or analysis
DROPPED_SENTENCES: List[str] = []

def _get_currency_and_unit_details(scenario: GenerationScenario) -> Tuple[str, str, str]:
    """Returns (currency_symbol, money_unit_word, ISO Code) based on scenario's archetype."""
    currency_code = scenario.archetype.default_currency
    currency_obj = next((c for c in all_currencies if c.code == currency_code), None)
    currency_symbol = currency_obj.symbol if currency_obj else "$"  # Default to $

    return currency_symbol, "million", currency_code


# Define a list of company archetypes to choose from during generation.
SCENARIO_ARCHETYPES = [
    ScenarioArchetype(
        name="Large Multinational",
        debt_exposure_range=(3, 6),
        fx_exposure_range=(3, 6),
        commodity_exposure_range=(3, 6),
        commodity_types=["energy", "metals_minerals", "agriculture"],
        equity_exposure_range=(3, 5),
        generic_instrument_range=(0, 2),
        hedging_propensities={
            "IR": (0.9, 0.9),
            "FX": (0.8, 0.8),
            "CP": (0.6, 0.6),
            "EQ": (0.3, 0.3),
            "GEN": (0.1, 0.1),
        },
        policy_coverage="full",
        comparative_years=3,
        default_currency="USD",
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=True,
        prefers_tables=True,
        preferred_negative_format=-1,  # Accounting style: ($100)
    ),
    ScenarioArchetype(
        name="Domestic Industrial",
        debt_exposure_range=(2, 4),
        fx_exposure_range=(0, 2),
        commodity_exposure_range=(3, 5),
        commodity_types=["metals_minerals", "lumber_wood", "chemicals_plastics"],
        equity_exposure_range=(0, 1),
        generic_instrument_range=(0, 1),
        hedging_propensities={
            "IR": (0.7, 0.7),
            "FX": (0.2, 0.2),
            "CP": (0.8, 0.8),
            "EQ": (0.0, 0.0),
            "GEN": (0.1, 0.1),
        },
        policy_coverage="partial",
        comparative_years=2,
        default_currency="USD",
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=True,
        preferred_negative_format=0,  # Standard minus sign: -$100
    ),
    ScenarioArchetype(
        name="Tech Company",
        debt_exposure_range=(1, 3),
        fx_exposure_range=(2, 5),
        commodity_exposure_range=(0, 0),
        commodity_types=[],
        equity_exposure_range=(2, 4),
        generic_instrument_range=(0, 1),
        hedging_propensities={
            "IR": (0.5, 0.5),
            "FX": (0.7, 0.7),
            "CP": (0.0, 0.0),
            "EQ": (0.6, 0.6),
            "GEN": (0.1, 0.1),
        },
        policy_coverage="partial",
        comparative_years=1,
        default_currency="USD",
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=False,  # Tech companies sometimes use full numbers
        preferred_negative_format=0,  # Standard minus sign: -$100
    ),
    ScenarioArchetype(
        name="Financial Institution",
        debt_exposure_range=(4, 8),
        fx_exposure_range=(4, 8),
        commodity_exposure_range=(0, 2),
        commodity_types=["precious_metals", "energy"],
        equity_exposure_range=(1, 3),
        generic_instrument_range=(1, 2),
        hedging_propensities={
            "IR": (0.95, 0.95),
            "FX": (0.9, 0.9),
            "CP": (0.5, 0.5),
            "EQ": (0.5, 0.5),
            "GEN": (0.2, 0.2),
        },
        policy_coverage="full",
        default_currency="USD",
        comparative_years=2,
        notional_multiplier=1_000_000_000,
        prefers_abbreviated_numbers=True,
        prefers_tables=True,
        preferred_negative_format=-1,  # Accounting style: ($100)
    ),
    ScenarioArchetype(
        name="Policy Only / Light User",
        debt_exposure_range=(0, 2),
        fx_exposure_range=(0, 2),
        commodity_exposure_range=(0, 1),
        commodity_types=["generic"],
        equity_exposure_range=(0, 0),
        generic_instrument_range=(1, 2),
        hedging_propensities={
            "IR": (0.3, 0.3),
            "FX": (0.3, 0.3),
            "CP": (0.1, 0.1),
            "EQ": (0.0, 0.0),
            "GEN": (0.4, 0.4),
        },
        policy_coverage="light",
        comparative_years=1,
        default_currency="USD",
        notional_multiplier=1_000,
        prefers_abbreviated_numbers=False,
        preferred_negative_format=0,
    ),
    ScenarioArchetype(
        name="Potential User",
        debt_exposure_range=(1, 3),  # Has exposures...
        fx_exposure_range=(1, 3),  # ...but won't hedge them.
        commodity_exposure_range=(1, 2),
        commodity_types=["agriculture", "energy"],
        equity_exposure_range=(0, 1),
        generic_instrument_range=(0, 1),
        hedging_propensities={
            "IR": (0.0, 0.0),
            "FX": (0.0, 0.0),
            "CP": (0.0, 0.0),
            "EQ": (0.0, 0.0),
            "GEN": (0.0, 0.0),
        },
        policy_coverage="light",
        comparative_years=2,
        default_currency="USD",
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=False,
        preferred_negative_format=0,
    ),
    ScenarioArchetype(
        name="Non-User",
        debt_exposure_range=(1, 2),  # Has exposures...
        fx_exposure_range=(1, 2),  # ...but will never hedge them.
        commodity_exposure_range=(0, 1),
        commodity_types=["generic"],
        equity_exposure_range=(0, 0),
        generic_instrument_range=(0, 1),
        hedging_propensities={
            "IR": (0.0, -1),
            "FX": (0.0, -1),
            "CP": (0.0, -1),
            "EQ": (0.0, -1),
            "GEN": (0.0, -1),
        },
        policy_coverage="light",
        default_currency="USD",
        comparative_years=2,
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=False,
        preferred_negative_format=0,
    ),
    ScenarioArchetype(
        name="New Hedger",
        debt_exposure_range=(2, 4),
        fx_exposure_range=(2, 4),
        commodity_exposure_range=(0, 1),
        commodity_types=["energy"],
        equity_exposure_range=(0, 0),
        generic_instrument_range=(0, 0),
        # Past propensity is 0, current is high.
        hedging_propensities={
            "IR": (0.0, 0.9),
            "FX": (0.0, 0.9),
            "CP": (0.0, 0.0),
            "EQ": (0.0, 0.0),
            "GEN": (0.0, 0.0),
        },
        policy_coverage="light",
        default_currency="USD",
        comparative_years=3,
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=True,
        preferred_negative_format=1,  # Parentheses around number: $(100)
    ),
    ScenarioArchetype(
        name="Exiting Hedger",
        debt_exposure_range=(2, 4),
        fx_exposure_range=(2, 4),
        commodity_exposure_range=(0, 1),
        commodity_types=["energy"],
        equity_exposure_range=(0, 0),
        generic_instrument_range=(0, 0),
        # Past propensity was high, current is 0.
        hedging_propensities={
            "IR": (1.0, 0.0),
            "FX": (1.0, 0.0),
            "CP": (0.0, 0.0),
            "EQ": (0.0, 0.0),
            "GEN": (0.0, 0.0),
        },
        policy_coverage="light",
        default_currency="USD",
        comparative_years=3,
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=True,
        preferred_negative_format=1,
    ),
    ScenarioArchetype(
        name="Debt-Heavy Exiter",
        debt_exposure_range=(5, 8),
        fx_exposure_range=(1, 3),
        commodity_exposure_range=(0, 1),
        commodity_types=["energy"],
        equity_exposure_range=(0, 0),
        generic_instrument_range=(0, 0),
        # Past propensity for IR was high, current is 0.
        hedging_propensities={
            "IR": (1.0, 0.0),
            "FX": (0.5, 0.0),
            "CP": (0.0, 0.0),
            "EQ": (0.0, 0.0),
            "GEN": (0.0, 0.0),
        },
        policy_coverage="partial",
        default_currency="USD",
        comparative_years=2,
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=True,
        preferred_negative_format=-1,
    ),
    ScenarioArchetype(
        name="Global Consumer Goods",
        debt_exposure_range=(2, 4),
        fx_exposure_range=(4, 7),
        commodity_exposure_range=(3, 5),
        commodity_types=["agriculture", "chemicals_plastics", "energy"],
        equity_exposure_range=(0, 1),
        generic_instrument_range=(0, 1),
        hedging_propensities={
            "IR": (0.6, 0.6),
            "FX": (0.9, 0.9),
            "CP": (0.8, 0.8),
            "EQ": (0.0, 0.0),
            "GEN": (0.1, 0.1),
        },
        policy_coverage="full",
        comparative_years=3,
        default_currency="USD",
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=True,
        preferred_negative_format=0,
    ),
    ScenarioArchetype(
        name="Airline",
        debt_exposure_range=(3, 6),
        fx_exposure_range=(2, 4),
        commodity_exposure_range=(4, 6),
        commodity_types=["energy"],
        equity_exposure_range=(0, 1),
        generic_instrument_range=(0, 1),
        hedging_propensities={
            "IR": (0.8, 0.8),
            "FX": (0.7, 0.7),
            "CP": (0.95, 0.95),
            "EQ": (0.0, 0.0),
            "GEN": (0.1, 0.1),
        },
        policy_coverage="full",
        comparative_years=2,
        default_currency="USD",
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=True,
        preferred_negative_format=-1,
    ),
    ScenarioArchetype(
        name="Biotech/Pharma",
        debt_exposure_range=(1, 3),
        fx_exposure_range=(2, 4),
        commodity_exposure_range=(0, 1),
        commodity_types=["chemicals_plastics"],
        equity_exposure_range=(3, 6),
        generic_instrument_range=(0, 1),
        hedging_propensities={
            "IR": (0.4, 0.4),
            "FX": (0.7, 0.7),
            "CP": (0.1, 0.1),
            "EQ": (0.8, 0.8),
            "GEN": (0.0, 0.0),
        },
        policy_coverage="partial",
        default_currency="CHF",
        comparative_years=2,
        notional_multiplier=1_000_000,
        prefers_abbreviated_numbers=True,
        preferred_negative_format=2,  # Minus after symbol: $-100
    ),
]


# =============================================================================
# PHASE 1 PART 2: SCENARIO GENERATION
# This section implements the core idea: "Decide the story upfront."
# We define the state of our financial narrative using structured dataclasses.
# =============================================================================
class ScenarioBuilder:
    """
    Handles the logic of building a complete GenerationScenario,
    including creating exposures and derivative instruments.
    """

    def __init__(self, scenario: GenerationScenario):
        self.scenario = scenario
        self.archetype = scenario.archetype
        self.reporting_year = scenario.reporting_year
        self.multiplier = self.archetype.notional_multiplier
        self.instrument_id_counter = 1
        self.hedged_item_id_counter = 1
        self.potential_hedged_items: Dict[str, List] = {
            "debt": [],
            "fx": [],
            "commodity": [],
            "equity": [],
        }
        self.all_scenario_base_types: Set[str] = set()

    def _generate_debt_exposures(self, count: int):
        for _ in range(count):
            issuance_year = random.randint(
                self.reporting_year - 15, self.reporting_year - 1
            )
            maturity_year = random.randint(
                self.reporting_year + 2, self.reporting_year + 20
            )
            selected_debt_type: DebtType = random.choice(all_debt_types)
            benchmark_rate = (
                random.choice(selected_debt_type.benchmarks + specific_rate_terms)
                if selected_debt_type.benchmarks
                else None
            )
            debt_currency = self.archetype.default_currency
            if random.random() < 0.20:
                foreign_curr = random.choice(
                    [
                        c
                        for c in all_currencies
                        if c.code != self.archetype.default_currency
                    ]
                )
                debt_currency = foreign_curr.code

            hedged_debt = DebtHedgedItem(
                hedged_item_id=self.hedged_item_id_counter,
                debt_type=selected_debt_type.name,
                currency=debt_currency,
                issuance_year=issuance_year,
                maturity_year=maturity_year,
                principal_amount=random.randint(5, 500) * self.multiplier,
                benchmark_rate=benchmark_rate,
                issuance_month=random.choice(months),
                maturity_month=random.choice(months),
                spread_bps=random.randint(100, 300),
            )
            self.potential_hedged_items["debt"].append(hedged_debt)
            self.hedged_item_id_counter += 1

    def _generate_fx_exposures(self, count: int):
        for _ in range(count):
            exposures = [
                CurrencyExposure(
                    code=cur.code,
                    full_name=cur.full_name,
                    symbol=cur.symbol,
                    adjective=cur.adjective,
                    location=cur.location,
                    amount=random.randint(1, 100) * self.multiplier,
                )
                for cur in random.sample(all_currencies, random.randint(1, 3))
            ]
            self.potential_hedged_items["fx"].append(
                ForeignCurrencyHedgedItem(
                    hedged_item_id=self.hedged_item_id_counter, exposures=exposures
                )
            )
            self.hedged_item_id_counter += 1

    def _generate_commodity_exposures(self, count: int):
        for _ in range(count):
            # --- FIX: Ensure unit and cost_type are specific to the chosen commodity ---
            # 1. Select a random commodity from the full list.
            commodity_name, unit, cost_type = get_random_commodity_and_unit(
                self.scenario.archetype.commodity_types
            )

            self.potential_hedged_items["commodity"].append(
                CommodityHedgedItem(
                    hedged_item_id=self.hedged_item_id_counter,
                    commodity_type=commodity_name,
                    transaction_type=random.choice(transaction_types),
                    quantity=random.randint(100, 400) * self.multiplier,
                    unit_of_volume=unit,
                    price_per_unit=random.uniform(10, 200),
                    cost_type=cost_type,
                    supplier=(
                        random.choice(company_names) if random.random() < 0.2 else None
                    ),
                )
            )
            self.hedged_item_id_counter += 1

    def _generate_equity_exposures(self, count: int):
        for _ in range(count):
            equity_type = random.choice(
                ["market_index", "own_stock", "third_party_stock"]
            )
            stock_symbol = None
            if equity_type == "third_party_stock":
                third_party_name = random.choice([c for c in company_names if c != self.scenario.company_name])
                stock_symbol = _generate_stock_symbol(third_party_name)
            elif equity_type == "own_stock":
                stock_symbol = _generate_stock_symbol(self.scenario.company_name)
            self.potential_hedged_items["equity"].append(
                EquityHedgedItem(
                    hedged_item_id=self.hedged_item_id_counter,
                    equity_type=equity_type,  # type: ignore
                    number_of_shares=random.randint(10000, 500000),
                    share_price=random.uniform(10.0, 250.0),
                    stock_symbol=stock_symbol,
                )
            )
            self.hedged_item_id_counter += 1

    def _build_instruments_for_category(
        self,
        category: str,
        instrument_class: type,
        potential_items: List[HedgedItem],
        available_base_types: List[str],
    ):
        past_prop, current_prop = self.archetype.hedging_propensities.get(
            category, (0.0, 0.0)  # type: ignore
        )  # type: ignore
        num_hedges = round(len(potential_items) * max(0, current_prop))
        items_to_hedge = random.sample(potential_items, num_hedges)

        for item in potential_items:
            hedged_item = None
            notional = 0
            maturity_year = 0

            if item in items_to_hedge:
                hedged_item = item
                if isinstance(item, DebtHedgedItem):
                    maturity_year = item.maturity_year
                    notional = item.principal_amount
                elif isinstance(item, ForeignCurrencyHedgedItem):
                    maturity_year = random.randint(
                        self.reporting_year + 1, self.reporting_year + 3
                    )
                    notional = sum(e.amount for e in item.exposures)
                elif isinstance(item, CommodityHedgedItem):
                    maturity_year = random.randint(
                        self.reporting_year + 1, self.reporting_year + 5
                    )
                    notional = int(item.quantity * item.price_per_unit)
                elif isinstance(item, EquityHedgedItem):
                    maturity_year = random.randint(
                        self.reporting_year + 1, self.reporting_year + 5
                    )
                    assert item.number_of_shares is not None and item.share_price is not None
                    notional = int(item.number_of_shares * item.share_price)
            else:
                is_exiting = past_prop > 0 and current_prop == 0
                if is_exiting or random.random() < past_prop:
                    hedged_item = item
                    maturity_year = random.randint(
                        self.reporting_year - 5, self.reporting_year
                    )
                    notional = random.randint(5, 500) * self.multiplier
                else:
                    continue  # Unhedged exposure

            # Special case for cross-currency swaps
            if (
                isinstance(hedged_item, DebtHedgedItem)
                and hedged_item.currency != self.archetype.default_currency
                and random.random() < 0.5
            ):
                placeholder = "cross-currency interest rate"
                prefix = ""
                base_type = random.choice(DERIVATIVE_COMPONENTS["base_types"])
                suffix = random.choice(DERIVATIVE_COMPONENTS["suffixes"])
                name = f"{placeholder} {base_type} {suffix}"
                alias = base_type + suffix
                
            else:
                prefix, placeholder, base_type, suffix, name, alias = (
                    _generate_instrument_name(
                        category,
                        hedged_item=hedged_item,
                        available_base_types=available_base_types,
                        all_scenario_base_types=self.all_scenario_base_types,
                    )
                )
            
            # --- NEW: For CP, sometimes report in units instead of currency ---
            instrument_currency = self.archetype.default_currency
            instrument_symbol = _get_currency_and_unit_details(self.scenario)[0]
            if category == "CP" and random.random() < 0.35: # 40% chance to use units
                if isinstance(hedged_item, CommodityHedgedItem):
                    # Use the commodity's unit as the "currency"
                    instrument_currency = hedged_item.unit_of_volume.upper()
                    instrument_symbol = hedged_item.unit_of_volume
                    notional = hedged_item.quantity # Notional is now the quantity
            
            # --- NEW: For FX, sometimes report in one of the exposure currencies ---
            if category == "FX" and random.random() < 0.35: # 35% chance
                if isinstance(hedged_item, ForeignCurrencyHedgedItem) and hedged_item.exposures:
                    # Pick one of the specific currency exposures to be the instrument's currency
                    random_exposure = random.choice(hedged_item.exposures)
                    instrument_currency = random_exposure.code
                    instrument_symbol = random_exposure.symbol
                    # The notional amount should now be the amount of that specific exposure
                    notional = random_exposure.amount
                    # For cross-currency swaps, the hedged item might be debt in another currency
                    if isinstance(hedged_item, DebtHedgedItem):
                        notional = hedged_item.principal_amount


            base_args = {
                "instrument_type": name,
                "instrument_alias": alias,
                "notional_amount": notional,
                "start_month": random.choice(months),
                "start_year": random.randint(
                    self.reporting_year - 10, self.reporting_year - 1
                ),
                "currency": instrument_currency,
                "maturity_year": maturity_year,
                "hedged_item": hedged_item,
                "instrument_prefix": prefix,
                "placeholder": placeholder,
                "base_type": base_type,
                "suffix": suffix,
            }

            new_instrument = _create_instrument_with_history(
                scenario=self.scenario,
                instrument_class=instrument_class,
                is_new=(item in items_to_hedge and random.random() < 0.3), # 30% chance a new hedge is brand new this year
                is_past=(hedged_item not in items_to_hedge),
                instrument_id=self.instrument_id_counter,
                base_instrument_args=base_args,
                symbol=instrument_symbol, # Pass the symbol here
            )
            self.scenario.instruments.append(new_instrument)
            self.instrument_id_counter += 1


    def build(self) -> GenerationScenario:
        exposure_counts = self.archetype.get_exposure_counts()

        # Reserve base types for GEN category
        all_base_types = DERIVATIVE_COMPONENTS["base_types"]
        gen_reserved_base_types = random.sample(all_base_types, random.randint(1, 2))
        other_available_base_types = [
            bt for bt in all_base_types if bt not in gen_reserved_base_types
        ]

        # Determine all base types that will appear in the scenario for context-aware aliasing
        if exposure_counts["debt"] > 0:
            self.all_scenario_base_types.add(random.choice(other_available_base_types))
        if exposure_counts["fx"] > 0:
            self.all_scenario_base_types.add(random.choice(other_available_base_types))
        if exposure_counts["commodity"] > 0:
            self.all_scenario_base_types.add(random.choice(other_available_base_types))
        if exposure_counts["equity"] > 0:
            self.all_scenario_base_types.add(random.choice(other_available_base_types))
        if exposure_counts["generic"] > 0:
            self.all_scenario_base_types.add(random.choice(gen_reserved_base_types))

        # Generate all potential exposures
        self._generate_debt_exposures(exposure_counts["debt"])
        self._generate_fx_exposures(exposure_counts["fx"])
        self._generate_commodity_exposures(exposure_counts["commodity"])
        self._generate_equity_exposures(exposure_counts["equity"])

        # Build instruments based on exposures and propensities
        self._build_instruments_for_category(
            "IR",
            IRInstrument,
            self.potential_hedged_items["debt"],
            other_available_base_types,
        )
        self._build_instruments_for_category(
            "FX",
            FXInstrument,
            self.potential_hedged_items["fx"],
            other_available_base_types,
        )
        self._build_instruments_for_category(
            "CP",
            CPInstrument,
            self.potential_hedged_items["commodity"],
            other_available_base_types,
        )
        self._build_instruments_for_category(
            "EQ",
            EQInstrument,
            self.potential_hedged_items["equity"],
            other_available_base_types,
        )

        # Create Generic Instruments (which don't have pre-defined exposures)
        for _ in range(exposure_counts.get("generic", 0)):
            is_terminated = random.random() < 0.4
            maturity_year = (
                random.randint(self.reporting_year - 3, self.reporting_year)
                if is_terminated
                else random.randint(self.reporting_year + 1, self.reporting_year + 5)
            )
            prefix, placeholder, base_type, suffix, name, alias = (
                _generate_instrument_name(
                    "GEN",
                    available_base_types=gen_reserved_base_types,
                    all_scenario_base_types=self.all_scenario_base_types,
                )
            )
            base_args = {
                "instrument_type": name,
                "instrument_alias": alias,
                "notional_amount": random.randint(10, 300) * self.multiplier,
                "start_month": random.choice(months),
                "start_year": random.randint(
                    self.reporting_year - 5, self.reporting_year - 1
                ),
                "currency": self.archetype.default_currency,
                "maturity_year": maturity_year,
                "hedged_item": None,
                "instrument_prefix": prefix,
                "placeholder": placeholder,
                "base_type": base_type,
                "suffix": suffix,
            }
            new_instrument = _create_instrument_with_history(
                scenario=self.scenario,
                instrument_class=GenericInstrument,
                is_new=not is_terminated and random.random() < 0.3, # 30% chance an active instrument is brand new
                is_past=is_terminated,
                instrument_id=self.instrument_id_counter,
                base_instrument_args=base_args,
                symbol=_get_currency_and_unit_details(self.scenario)[0], # Default currency symbol
            )
            self.scenario.instruments.append(new_instrument)
            self.instrument_id_counter += 1

        return self.scenario


def create_random_scenario(archetype_index: Optional[int] = None) -> GenerationScenario:
    """
    Creates a random, complex scenario by building a structured `GenerationScenario` object.
    This function acts as the "story planner," deciding upfront which instruments
    a company has, their status (active or terminated), and their key properties.

    Args:
        archetype_index: If provided, selects a specific archetype by its index.
    """
    reporting_year = random.randint(2020, 2024)
    reporting_day = random.randint(28, 31)
    reporting_month = random.choice(months)

    # --- Decide on a company archetype and get exposure counts ---
    if archetype_index is not None and 0 <= archetype_index < len(SCENARIO_ARCHETYPES):
        archetype = SCENARIO_ARCHETYPES[archetype_index]
    else:
        archetype = _create_truly_random_archetype()

    def generate_policy_for_archetype(
        archetype: ScenarioArchetype,
    ) -> RiskManagementPolicy:
        """Generates a realistic RiskManagementPolicy based on the company archetype."""
        general_policy = GeneralHedgingPolicy(
            counterparty_details=random.choice([
                "major financial institutions",
                "a diversified group of highly-rated financial institutions",
            ])
        )
        category_policies = []
        # Determine which categories *could* have policies based on propensity
        possible_policy_categories = [
            cat for cat, props in archetype.hedging_propensities.items()
            if props[0] > 0 or props[1] > 0
        ]

        if archetype.policy_coverage == "full":
            num_policies = len(possible_policy_categories)
        elif archetype.policy_coverage == "partial":
            num_policies = (
                random.randint(1, min(2, len(possible_policy_categories)))
                if len(possible_policy_categories) >= 2
                else 1
            )
        else: # "light"
            num_policies = random.randint(0, min(1, len(possible_policy_categories))) if len(possible_policy_categories) >= 2 else 1

        if possible_policy_categories and num_policies > 0:
            cats_with_policies = random.sample(possible_policy_categories, num_policies)
            for category in cats_with_policies:
                policy = CategorySpecificPolicy(category=category) # type: ignore
                category_policies.append(policy)

        return RiskManagementPolicy(
            general_policy=general_policy,
            category_policies=category_policies
        )

    scenario = GenerationScenario(
        company_name=random.choice(company_names),
        reporting_month=reporting_month,
        reporting_day=reporting_day,
        reporting_year=reporting_year,
        instruments=[],
        policy=generate_policy_for_archetype(archetype),
        number_format_preference=archetype.prefers_abbreviated_numbers,
        archetype=archetype,
    )

    # Use the builder to construct the full scenario
    builder = ScenarioBuilder(scenario)
    return builder.build()

def _create_truly_random_archetype() -> ScenarioArchetype:
    """Creates a ScenarioArchetype with randomized properties."""
    from defs.cp_data import COMMODITIES

    def rand_range(max_val=8):
        a = random.randint(0, max_val)
        b = random.randint(a, max_val)
        return (a, b)

    def rand_propensity():
        # (past_prop, current_prop)
        # -1 means explicit "never"
        past = random.choice([-1, 0.0] + [round(random.uniform(0.1, 1.0), 1) for _ in range(3)])
        if past == -1:
            current = -1
        else:
            current = random.choice([-1, 0.0] + [round(random.uniform(0.1, 1.0), 1) for _ in range(3)])
        return (past, current)

    commodity_keys = list(COMMODITIES.keys())
    num_commodity_types = random.randint(0, 4)

    return ScenarioArchetype(
        name="Truly Random",
        debt_exposure_range=rand_range(),
        fx_exposure_range=rand_range(),
        commodity_exposure_range=rand_range(5),
        commodity_types=(
            random.sample(commodity_keys, num_commodity_types)
            if num_commodity_types > 0
            else []
        ),
        equity_exposure_range=rand_range(6),
        generic_instrument_range=rand_range(2),
        hedging_propensities={
            "IR": rand_propensity(),
            "FX": rand_propensity(),
            "CP": rand_propensity(),
            "EQ": rand_propensity(),
            "GEN": rand_propensity(),
        },
        policy_coverage=random.choice(["full", "partial", "light"]),
        comparative_years=random.randint(1, 3), # type: ignore
        default_currency=random.choice(
            [c.code for c in all_currencies]
        ),
        notional_multiplier=random.choice([1_000, 1_000_000, 1_000_000_000]),
        prefers_abbreviated_numbers=random.choice([True, False]),
        prefers_tables=random.choice([True, False]),
        preferred_negative_format=random.choice([-1, 0, 1, 2]),
        zero_notional_format=random.choice(["nil", "zero", "amount"]),
    )

def _get_smart_instrument_description(instruments: List[NotionalInstrument], category: str, summary:bool = False) -> str:
    """
    Generates a smart, concatenated description of the instruments used.
    """
    if not instruments:
        return "derivatives"

    # --- NEW: For CP, sometimes use the specific commodity name ---
    if category == "CP" and random.random() < 0.4: # 40% chance
        # Get a commodity name from one of the hedged items
        commodity_name = next(
            (inst.hedged_item.commodity_type for inst in instruments if inst.hedged_item and isinstance(inst.hedged_item, CommodityHedgedItem)),
            None
        )
        if commodity_name:
            # --- NEW: Handle multiple commodity types more gracefully ---
            unique_base_types = sorted(list({f"{i.base_type} {i.suffix}".strip() for i in instruments}))
            if len(unique_base_types) <= 2:
                # e.g., "crude oil swaps and contracts"
                return f"{commodity_name} {', '.join(unique_base_types)}"
            else:
                # e.g., "various crude oil hedging instruments"
                quantifier = random.choice(GENERIC_QUANTIFIERS)
                descriptor = random.choice(DERIVATIVE_COMPONENTS["no_alias_types"])
                suffix = random.choice(DERIVATIVE_COMPONENTS["suffixes"])
                plural_suffix = f"{suffix}s" if not suffix.endswith('s') else suffix
                return " ".join(filter(None, [quantifier, commodity_name, descriptor, plural_suffix]))

    count = len(instruments)
    unique_types = sorted(list({i.instrument_type for i in instruments}))

    if count == 1:
        return instruments[0].instrument_type
    # The same instrument
    if count >= 2 and len(unique_types) == 1:
        return f"{unique_types[0]}s"
    # two instruments
    if count == 2 and len(unique_types) > 1:
        return f"{unique_types[0]} and {unique_types[1]}"

    quantifier = random.choice(GENERIC_QUANTIFIERS)
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

        if num_most_common >= 2 and not summary:
            # "interest-rate swaps and other interest rate instruments"
            dominant_instrument_example = next(i.instrument_type for i in instruments if i.placeholder == most_common_placeholder)
            # --- FIX: Use a random suffix for more variety ---
            other_suffix = random.choice(DERIVATIVE_COMPONENTS["suffixes"])
            plural_suffix = (
                f"{other_suffix}s"
                if other_suffix and not other_suffix.endswith("s")
                else other_suffix
            )
            return f"{dominant_instrument_example} and other {plural_suffix}"
        else:
            # "a portfolio of derivative instruments"
            # --- FIX: Use the full category name for a more natural phrase ---
            category_map = {
                "IR": "interest rate",
                "FX": "foreign exchange",
                "CP": "commodity",
                "EQ": "equity",
                "GEN": "various" # Fallback for generic
            }
            descriptive_category = category_map.get(category, "various")
            # --- FIX: Use a random suffix for more variety ---
            # e.g., "a portfolio of interest rate contracts" instead of always "derivative instruments"
            suffix = random.choice(DERIVATIVE_COMPONENTS["suffixes"])
            # Ensure the suffix is pluralized correctly
            plural_suffix = f"{suffix}s" if suffix and not suffix.endswith('s') else suffix
            return f"{quantifier} {descriptive_category} {plural_suffix}"

    # --- FIX: Dynamically generate the generic description, ensuring category is mentioned ---
    # This logic handles cases with 2-3 dissimilar instruments or fallbacks.
    category_map = {
        "IR": "interest rate",
        "FX": "foreign exchange",
        "CP": "commodity",
        "EQ": "equity",
        "GEN": "various"
    }
    # Always prefer the specific category name over a generic descriptor if available.
    descriptor = category_map.get(category, random.choice(GENERIC_DESCRIPTORS))
    suffix = random.choice(DERIVATIVE_COMPONENTS["suffixes"])
    plural_suffix = f"{suffix}s" if not suffix.endswith('s') else suffix

    return " ".join(filter(None, [quantifier, descriptor, plural_suffix]))


def _create_instrument_with_history(
    scenario: GenerationScenario,
    instrument_class: type,
    instrument_id: int,
    base_instrument_args: Dict,
    symbol: str,
    is_new: bool,
    is_past: bool,
) -> NotionalInstrument:
    """
    Creates a single instrument and populates its history (past and optionally future).

    For a single instrument ID, this generates one instrument object containing a
    `notional_history` dictionary, which maps years to notional amounts.
    The history can extend back a variable number of years.

    Args:
        scenario: The GenerationScenario to which instruments will be added.
        instrument_class: The class of the instrument to create (e.g., IRInstrument).
        instrument_id: The unique ID for this instrument and its history.
        base_instrument_args: A dictionary of arguments for the instrument constructor,
        symbol: The currency symbol or unit to be used for formatting.
                              including the notional amount.
        is_new: A flag indicating if the instrument was initiated in the current reporting year.
        is_past: A flag indicating if the instrument is historical (matured before reporting year).

    Returns:
        A single NotionalInstrument instance with its history populated.
    """

    maturity_year = base_instrument_args.get("maturity_year", 0)
    current_year = scenario.reporting_year
    current_notional = base_instrument_args.pop("notional_amount")
    base_instrument_args["maturity_value"] = 0  # Default maturity value
    start_year = base_instrument_args.get(
        "start_year", current_year - random.randint(3, 8)
    )

    # --- FIX: Ensure start_year is always before or same as maturity_year ---
    # This prevents logical inconsistencies for past/terminated instruments.
    if start_year > maturity_year:
        start_year = maturity_year - random.randint(1, 5)

    notional_history = {}

    if not is_past:
        # Active instrument: must have a value for the current reporting year.
        notional_history[current_year] = current_notional

        # Only generate prior-year history if the instrument is NOT new.
        if not is_new:
            # Generate history from the start_year up to the year before the reporting year.
            last_notional = current_notional
            for year in range(current_year - 1, start_year - 1, -1):
                # Simulate a slightly different notional amount for the previous year.
                # The change is more pronounced further in the past.
                last_notional = int(last_notional * random.uniform(0.90, 1.10))
                notional_history[year] = max(0, last_notional)

        # Active instruments have not matured, so their maturity_value is not yet known.
        base_instrument_args["maturity_value"] = None
    else:
        # Past instrument: history exists only up to reporting_year - 1.
        # The 'current_notional' is the notional at maturity.
        base_instrument_args["maturity_value"] = current_notional
        last_notional = current_notional
        # Generate history backwards from the maturity year.
        # The history should only go up to the year *before* the reporting year
        # if the instrument matures in the current year.
        end_of_history_year = maturity_year
        if maturity_year >= current_year:
            # If it matures in the current year or future (which is an error for a 'past' instrument, but we handle it),
            # its year-end notional for the reporting year is 0. The history exists only *before* this year.
            end_of_history_year = current_year - 1

        for year in range(end_of_history_year, start_year - 1, -1):
            # Simulate a slightly different notional amount for the previous year.
            last_notional = int(last_notional * random.uniform(0.85, 1.15))
            notional_history[year] = max(0, last_notional)

        # NEW: Pad with zeros from maturity to current year
        comparative_years = scenario.archetype.comparative_years
        if maturity_year >= current_year - comparative_years:
            for year in range(maturity_year + 1, current_year + 1):
                notional_history[year] = 0

    # Sort years chronologically
    notional_history = dict(sorted(notional_history.items()))

    # --- NEW: With a small chance, set a mid-history year to zero ---
    # This simulates a temporary pause in the instrument's use.
    # It should not be the start year or the most recent year of its history.
    if len(notional_history) > 2 and random.random() < 0.15:  # 15% chance
        # Get all years except the first and last
        eligible_years = sorted(list(notional_history.keys()))[1:-1]
        if eligible_years:
            year_to_zero = random.choice(eligible_years)
            # Ensure we don't zero out the current reporting year for an active instrument
            if not (not is_past and year_to_zero == scenario.reporting_year):
                notional_history[year_to_zero] = 0

    # Create the instrument instance
    instrument = instrument_class(
        instrument_id=instrument_id,
        notional_history=notional_history,
        symbol=symbol,
        **base_instrument_args,
    )

    return instrument


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
    components = DERIVATIVE_COMPONENTS
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
        placeholder = (
            hedged_item.benchmark_rate
            if random.random() < 0.35
            else random.choice(placeholders)
        )
    elif category == "CP" and isinstance(hedged_item, CommodityHedgedItem):
        # For commodities, we can make the placeholder more specific.
        generic_placeholder = random.choice(placeholders)
        if random.random() < 0.85:  # 85% chance to use the specific commodity name
            # e.g., replace "commodity" in "commodity price" with "crude oil" -> "crude oil price"
            placeholder = re.sub(r'commodity', hedged_item.commodity_type, generic_placeholder, flags=re.IGNORECASE)
        else:
            placeholder = generic_placeholder
    else:
        placeholder = random.choice(placeholders)

    base_type = random.choice(base_types)

    # --- Assemble the name ---
    use_special = special_suffixes and random.random() < special_ratio and category != "GEN"
    suffix = ""
    if use_special:
        chosen = random.choice(special_suffixes)
        full_name = " ".join(filter(None, [placeholder, chosen])).strip()
        base_type = chosen  # treat as base for alias/prefix logic
    else:
        suffix = random.choice(suffixes)
        full_name = " ".join(filter(None, [placeholder, base_type, suffix])).strip()

    # --- NEW: Context-aware alias generation ---
    other_base_types = (all_scenario_base_types or set()) - {base_type}
    alias = _create_contextual_alias(base_type, category, placeholder, suffix, other_base_types)

    # --- Optional Prefix (for swaps, swaptions, rate locks) ---
    prefix = ""
    if (
        any(x in base_type for x in ["swap", "swaption", "lock"])
        and random.random() < PAY_PREFIX_RATIO
    ):
        prefix = random.choice(components["swap_prefixes"])

    # --- Optional Prefix (global)
    if not prefix and random.random() < PAY_PREFIX_RATIO:
        prefix = random.choice(components["global_prefixes"])

    return prefix, placeholder, base_type, suffix, full_name, alias


def _create_contextual_alias(
    base_type: str, category: str, placeholder: str, suffix: str, all_other_base_types: Set[str]
) -> str:
    """
    Creates a context-aware alias for an instrument. If the base type is unique
    across the scenario, a simple alias is used. Otherwise, a category prefix is added.

    Args:
        base_type: The base type of the current instrument (e.g., "swap").
        category: The category of the current instrument (e.g., "IR").
        placeholder: The placeholder used in the instrument name (e.g., "cross-currency").
        suffix: The suffix used in the instrument name (e.g., "agreement").
        all_other_base_types: A set of all base types present in the scenario.

    Returns:
        A contextually appropriate alias string.
    """
    # NEW: Handle special suffixes like "put option" explicitly.
    # This ensures the full phrase is treated as the base.
    for special_suffix in DERIVATIVE_COMPONENTS["special_suffixes"]:
        if special_suffix in base_type:
            alias_base = special_suffix
            break
    else:
        # Fallback for other types.
        alias_base = base_type

    is_base_type_unique = base_type not in all_other_base_types
    no_alias_types = DERIVATIVE_COMPONENTS.get("no_alias_types", [])
    no_alias_independent = DERIVATIVE_COMPONENTS.get("no_alias_independent", [])
    is_no_alias_type = any(no_alias_word in base_type for no_alias_word in no_alias_types)
    is_dependent_type = base_type in DERIVATIVE_COMPONENTS.get("dependent_types", [])

    # --- Logic for types that should not be aliased (e.g., "derivative", "hedge") ---
    if is_no_alias_type:
        # For independent no-alias types like "derivative", we might sometimes
        # return just "interest rate derivative" instead of the full name with a suffix.
        if base_type in no_alias_independent and random.random() < 0.3:
            return f"{placeholder} {alias_base}".strip()  # e.g., "IR derivative"
        # Otherwise, return the full name to avoid ambiguity.
        return f"{placeholder} {alias_base} {suffix}".strip() # e.g., "IR hedging contract"

    # --- Logic for standard, aliasable types ---
    if is_base_type_unique:
        # If the base type is unique in the scenario (e.g., only one "swap"), we can use a shorter alias.
        if not is_dependent_type:
            # For standalone types like "swap".
            # Full name: "interest-rate swap contract"
            # Possible aliases: "swap contract", "interest-rate swap", or just "swap".
            if suffix and random.random() < 0.3:
                return f"{alias_base} {suffix}".strip()
            if placeholder and random.random() < 0.3:
                return f"{placeholder} {alias_base}".strip()
            return alias_base
        else:
            # For dependent types like "collar", which need more context.
            # Full name: "interest-rate collar agreement"
            # Possible aliases: "collar agreement" or "interest-rate collar".
            if suffix and random.random() < 0.3:
                return f"{alias_base} {suffix}".strip()
            else:
                return f"{placeholder} {alias_base}".strip()
    else:
        # If the base type is NOT unique (e.g., "swap" and "collar" both exist),
        # return the full name to avoid ambiguity.
        return f"{placeholder} {base_type} {suffix}".strip()


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

        # --- NEW: Generate ExposureEvidence from the generic policy sentence ---
        # This ensures that even a high-level risk statement contributes to the exposure map.
        exposure_evidence = ExposureEvidence(
            category="GEN", status="exposure_mention", details=policy_sentence
        )
        evidence.append(exposure_evidence)

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


def _generate_debt_narrative(
    scenario: GenerationScenario,
) -> Tuple[List[str], List[ExposureEvidence]]:
    """
    Generates a dedicated, detailed narrative section about the company's debt.
    This is separate from the high-level summary in the IR risk section.
    """
    paragraphs = []
    evidence = []

    # Get currency and money unit details for sentence generation
    currency_symbol, _, _ = _get_currency_and_unit_details(scenario)

    # Get all debt items from the scenario.
    all_debt_items = [
        inst.hedged_item
        for inst in scenario.instruments if isinstance(inst.hedged_item, DebtHedgedItem)
    ]
    all_debt_items = list({item.hedged_item_id: item for item in all_debt_items}.values())

    if not all_debt_items:
        return [], []

    # Add a title for this section.
    paragraphs.append("Debt")

    # --- NEW: Decide whether to generate a table or individual paragraphs ---
    if random.random() < 0.6 or len(all_debt_items) <= 2: # More likely to generate paragraphs for fewer items
        # For each debt item, generate a detailed contextual paragraph.
        for debt_item in all_debt_items:
            debt_context_builder = DebtContextSentence(
                company_name=scenario.company_name,
                reporting_year=scenario.reporting_year,
                reporting_month=scenario.reporting_month,
                reporting_day=scenario.reporting_day,
                hedged_item=debt_item,
                prefer_abbreviated=scenario.number_format_preference,
                currency_symbol=currency_symbol,
            )
            debt_paragraph = debt_context_builder.build()
            if debt_paragraph:
                paragraphs.append(debt_paragraph)
                # --- NEW: Create evidence for this exposure ---
                evidence.append(
                    ExposureEvidence(category="IR", status="exposure_mention", details=debt_paragraph)
                )
    else:
        # Generate a single table for all debt items
        debt_context_builder = DebtContextSentence(
            company_name=scenario.company_name,
            reporting_year=scenario.reporting_year,
            reporting_month=scenario.reporting_month,
            reporting_day=scenario.reporting_day,
            hedged_item=all_debt_items, # Pass the whole list
            prefer_abbreviated=scenario.number_format_preference,
            currency_symbol=currency_symbol,
        )
        debt_paragraph = debt_context_builder.build()
        if debt_paragraph:
            paragraphs.append(debt_paragraph)
            # --- NEW: Create evidence for this exposure ---
            evidence.append(
                ExposureEvidence(category="IR", status="exposure_mention", details=debt_paragraph)
            )

    return paragraphs, evidence


def _generate_fx_narrative(
    scenario: GenerationScenario,
) -> Tuple[List[str], List[ExposureEvidence]]:
    """
    Generates a dedicated, detailed narrative section about the company's foreign currency exposures.
    """
    paragraphs = []
    evidence = []

    currency_symbol, _, currency_code = _get_currency_and_unit_details(scenario)

    # Get all unique FX hedged items from the scenario's instruments.
    all_fx_items = list({
        inst.hedged_item.hedged_item_id: inst.hedged_item
        for inst in scenario.instruments
        if isinstance(inst.hedged_item, ForeignCurrencyHedgedItem)
    }.values())

    if not all_fx_items:
        return [], []

    paragraphs.append("Foreign Currency Risk")

    # --- NEW: Decide whether to generate a table or individual paragraphs ---
    if random.random() < 0.6 or len(all_fx_items) <= 2:
        for fx_item in all_fx_items:
            fx_context_builder = FXContextSentence(
                company_name=scenario.company_name,
                reporting_year=scenario.reporting_year,
                reporting_month=scenario.reporting_month,
                reporting_day=scenario.reporting_day,
                hedged_item=fx_item,
                prefer_abbreviated=scenario.number_format_preference,
                currency_symbol=currency_symbol,
                currency_code=currency_code,
            )
            fx_paragraph = fx_context_builder.build()
            if fx_paragraph:
                paragraphs.append(fx_paragraph)
                # --- NEW: Create evidence for this exposure ---
                evidence.append(
                    ExposureEvidence(category="FX", status="exposure_mention", details=fx_paragraph)
                )
    else:
        fx_context_builder = FXContextSentence(
            company_name=scenario.company_name,
            reporting_year=scenario.reporting_year,
            reporting_month=scenario.reporting_month,
            reporting_day=scenario.reporting_day,
            hedged_item=all_fx_items,
            prefer_abbreviated=scenario.number_format_preference,
            currency_symbol=currency_symbol,
            currency_code=currency_code,
        )
        fx_paragraph = fx_context_builder.build()
        if fx_paragraph:
            paragraphs.append(fx_paragraph)
            # --- NEW: Create evidence for this exposure ---
            evidence.append(
                ExposureEvidence(category="FX", status="exposure_mention", details=fx_paragraph)
            )

    return paragraphs, evidence


def _generate_cp_narrative(
    scenario: GenerationScenario,
) -> Tuple[List[str], List[ExposureEvidence]]:
    """
    Generates a dedicated, detailed narrative section about the company's commodity price exposures.
    """
    paragraphs = []
    evidence = []

    currency_symbol, _, _ = _get_currency_and_unit_details(scenario)

    # Get all unique Commodity hedged items from the scenario's instruments.
    all_cp_items = list({
        inst.hedged_item.hedged_item_id: inst.hedged_item
        for inst in scenario.instruments
        if isinstance(inst.hedged_item, CommodityHedgedItem)
    }.values())

    if not all_cp_items:
        return [], []

    paragraphs.append("Commodity Price Risk")

    # --- NEW: Decide whether to generate a table or individual paragraphs ---
    if random.random() < 0.6 or len(all_cp_items) <= 2:
        for cp_item in all_cp_items:
            cp_context_builder = CPContextSentence(
                company_name=scenario.company_name,
                reporting_year=scenario.reporting_year,
                reporting_month=scenario.reporting_month,
                reporting_day=scenario.reporting_day,
                hedged_item=cp_item,
                prefer_abbreviated=scenario.number_format_preference,
                currency_symbol=currency_symbol,
                notional_multiplier=scenario.archetype.notional_multiplier,
            )
            cp_paragraph = cp_context_builder.build()
            if cp_paragraph:
                paragraphs.append(cp_paragraph)
                # --- NEW: Create evidence for this exposure ---
                evidence.append(
                    ExposureEvidence(category="CP", status="exposure_mention", details=cp_paragraph)
                )
    else:
        cp_context_builder = CPContextSentence(
            company_name=scenario.company_name,
            reporting_year=scenario.reporting_year,
            reporting_month=scenario.reporting_month,
            reporting_day=scenario.reporting_day,
            hedged_item=all_cp_items,
            prefer_abbreviated=scenario.number_format_preference,
            currency_symbol=currency_symbol,
            notional_multiplier=scenario.archetype.notional_multiplier,
        )
        cp_paragraph = cp_context_builder.build()
        if cp_paragraph:
            paragraphs.append(cp_paragraph)
            # --- NEW: Create evidence for this exposure ---
            evidence.append(
                ExposureEvidence(category="CP", status="exposure_mention", details=cp_paragraph)
            )

    return paragraphs, evidence


def _generate_eq_narrative(
    scenario: GenerationScenario,
) -> Tuple[List[str], List[ExposureEvidence]]:
    """
    Generates a dedicated, detailed narrative section about the company's equity-related activities.
    """
    paragraphs = []
    evidence = []

    currency_symbol, _, _ = _get_currency_and_unit_details(scenario)

    # Get all unique Equity hedged items from the scenario's instruments.
    all_eq_items = list({
        inst.hedged_item.hedged_item_id: inst.hedged_item
        for inst in scenario.instruments
        if isinstance(inst.hedged_item, EquityHedgedItem)
    }.values())

    if not all_eq_items:
        return [], []

    paragraphs.append("Equity Risk")

    # --- NEW: Decide whether to generate a table or individual paragraphs ---
    if random.random() < 0.6 or len(all_eq_items) <= 2:
        for eq_item in all_eq_items:
            eq_context_builder = EQContextSentence(
                company_name=scenario.company_name,
                reporting_year=scenario.reporting_year,
                reporting_month=scenario.reporting_month,
                reporting_day=scenario.reporting_day,
                hedged_item=eq_item,
                prefer_abbreviated=scenario.number_format_preference,
                currency_symbol=currency_symbol,
            )
            eq_paragraph = eq_context_builder.build()
            if eq_paragraph:
                paragraphs.append(eq_paragraph)
                # --- NEW: Create evidence for this exposure ---
                evidence.append(
                    ExposureEvidence(category="EQ", status="exposure_mention", details=eq_paragraph)
                )
    else:
        eq_context_builder = EQContextSentence(
            company_name=scenario.company_name,
            reporting_year=scenario.reporting_year,
            reporting_month=scenario.reporting_month,
            reporting_day=scenario.reporting_day,
            hedged_item=all_eq_items,
            prefer_abbreviated=scenario.number_format_preference,
            currency_symbol=currency_symbol,
        )
        eq_paragraph = eq_context_builder.build()
        if eq_paragraph:
            paragraphs.append(eq_paragraph)
            # --- NEW: Create evidence for this exposure ---
            evidence.append(
                ExposureEvidence(category="EQ", status="exposure_mention", details=eq_paragraph)
            )

    return paragraphs, evidence


def _generate_category_narrative(
    category: str,
    yearly_data: Dict,
    scenario: GenerationScenario,
    part: Literal["summary", "details"],
    mentioned_instrument_types: Optional[Set[str]] = None,
    allow_random_drops: bool = False,
    suppress_text_output: bool = False,
    mentioned_instrument_ids: Optional[Set[int]] = None,
) -> Tuple[List[str], List[BaseNarrativeEvidence], Optional[str]]:
    """
    Generates a narrative section for a single derivative category (e.g., Interest Rate Risk).
    This includes context, a summary of instruments, and details on changes.

    Args:
        mentioned_instrument_ids: A set to track specific instrument IDs that have been mentioned.
        mentioned_instrument_types: A set to track instrument full names that have already been mentioned.
        part: "summary" to generate policy/mitigation/aggregate, "details" for individual instruments.
        suppress_text_output: If True, only generate evidence, not sentences.
    """
    sentences, evidence, used_name = [], [], None
    reporting_year, reporting_month, reporting_day = (
        scenario.reporting_year,
        scenario.reporting_month,
        scenario.reporting_day,
    )
    current_year_data = yearly_data.get(reporting_year)
    prev_year_data = yearly_data.get(reporting_year - 1)
    prev2_year_data = yearly_data.get(reporting_year - 2)

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
                    specific_details.commodity.append(hedged_item.commodity_type)
                    specific_details.unit = hedged_item.unit_of_volume
                elif isinstance(hedged_item, ForeignCurrencyHedgedItem):
                    locations = [exp.location for exp in hedged_item.exposures]
                    location_names = list(set(locations))
                    if location_names:
                        specific_details.geography = location_names
                    currencies = [exp.full_name for exp in hedged_item.exposures]
                    currency_names = list(set(currencies))
                    if currency_names:
                        specific_details.currencies = currency_names
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
        )
        context_sentence, _ = policy_sentence_obj.build()
        if not suppress_text_output:
            sentences.append(context_sentence)

        # --- NEW: Add debt context for IR category ---
        if category == "IR":
            # Get all debt items from the scenario. This includes both hedged and unhedged debt.
            all_debt_hedged_items = [inst.hedged_item for inst in scenario.instruments if isinstance(inst.hedged_item, DebtHedgedItem)]

            # For each debt item, generate a contextual paragraph.
            # Let's limit it to 1-2 paragraphs to avoid making the text too long.
            items_to_describe = random.sample(all_debt_hedged_items, k=min(len(all_debt_hedged_items), 2))
            debt_context_builder = DebtContextSentence(
                company_name=scenario.company_name,
                reporting_year=scenario.reporting_year,
                reporting_month=scenario.reporting_month,
                reporting_day=scenario.reporting_day,
                hedged_item=items_to_describe,
                prefer_abbreviated=scenario.number_format_preference,
                currency_symbol=currency_symbol,
            )
            debt_paragraph = debt_context_builder.build()
            if debt_paragraph and not suppress_text_output:
                sentences.append(debt_paragraph)

        # --- NEW: Add FX context for FX category (similar to IR/Debt) ---
        if category == "FX":
            all_fx_hedged_items = [inst.hedged_item for inst in scenario.instruments if isinstance(inst.hedged_item, ForeignCurrencyHedgedItem)]
            items_to_describe = random.sample(all_fx_hedged_items, k=min(len(all_fx_hedged_items), 1)) # Describe 1 item
            fx_context_builder = FXContextSentence(
                company_name=scenario.company_name,
                reporting_year=scenario.reporting_year,
                reporting_month=scenario.reporting_month,
                reporting_day=scenario.reporting_day,
                hedged_item=items_to_describe,
                prefer_abbreviated=scenario.number_format_preference,
                currency_symbol=currency_symbol,
                notional_multiplier=scenario.archetype.notional_multiplier,
                currency_code=currency_code,
            )
            fx_paragraph = fx_context_builder.build()
            if fx_paragraph and not suppress_text_output:
                sentences.append(fx_paragraph)

        # --- NEW: Add CP context for CP category ---
        if category == "CP":
            all_cp_hedged_items = [inst.hedged_item for inst in scenario.instruments if isinstance(inst.hedged_item, CommodityHedgedItem)]
            items_to_describe = random.sample(all_cp_hedged_items, k=min(len(all_cp_hedged_items), 1))
            cp_context_builder = CPContextSentence(
                company_name=scenario.company_name,
                reporting_year=scenario.reporting_year,
                reporting_month=scenario.reporting_month,
                reporting_day=scenario.reporting_day,
            hedged_item=items_to_describe,
                prefer_abbreviated=scenario.number_format_preference,
                currency_symbol=currency_symbol,
                notional_multiplier=scenario.archetype.notional_multiplier,
            )
            cp_paragraph = cp_context_builder.build()
            if cp_paragraph and not suppress_text_output:
                sentences.append(cp_paragraph)

        # --- NEW: Add EQ context for EQ category ---
        if category == "EQ":
            all_eq_hedged_items = [inst.hedged_item for inst in scenario.instruments if isinstance(inst.hedged_item, EquityHedgedItem)]
            # Describe context for one of the hedged items, if any exist.
            items_to_describe = random.sample(all_eq_hedged_items, k=min(len(all_eq_hedged_items), 1))

            # --- FIX: If no specific hedged items, generate a generic context sentence ---
            eq_context_builder = EQContextSentence(
                company_name=scenario.company_name,
                reporting_year=scenario.reporting_year,
                # --- FIX: Pass correct date components ---
                reporting_month=scenario.reporting_month,
                reporting_day=scenario.reporting_day,
            hedged_item=items_to_describe if items_to_describe else None,
                prefer_abbreviated=scenario.number_format_preference,
                currency_symbol=currency_symbol,
            )
            eq_paragraph = eq_context_builder.build()
            if eq_paragraph and not suppress_text_output:
                sentences.append(eq_paragraph)

            # --- FIX: Handle case where there are no EQ instruments but exposure exists ---
            if not all_eq_hedged_items:
                eq_context_builder = EQContextSentence(
                    company_name=scenario.company_name, reporting_year=scenario.reporting_year,
                    reporting_month=scenario.reporting_month, reporting_day=scenario.reporting_day,
                hedged_item=None, prefer_abbreviated=scenario.number_format_preference, currency_symbol=currency_symbol,
                )
                if not suppress_text_output:
                    sentences.append(eq_context_builder.build())

        # 1b. Mitigation/Purpose Sentence
        has_active_instruments = bool(
            current_year_data and current_year_data["instruments"] and sum(
                inst.notional_history.get(reporting_year, 0) > 0 for inst in current_year_data["instruments"]
            ) > 0
        ) # type: ignore
        past_prop, current_prop = scenario.archetype.hedging_propensities.get(category, (0.0, 0.0))  # type: ignore
        has_past_instruments = bool(prev_year_data and prev_year_data["instruments"] and sum(inst.notional_history.get(reporting_year - 1, 0) > 0 for inst in prev_year_data["instruments"]) > 0)

        # --- FIX: Only sometimes generate an explicit "no use" statement ---
        # This reflects that firms don't always state their non-use.
        is_explicit_non_use = current_prop < 0 and random.random() < 0.6  # 60% chance to state non-use

        usage = (
            "current"
            if has_active_instruments
            else (
                "non_use"  # This will only be chosen if the conditions above are met
                if is_explicit_non_use
                else (
                    "historical" # If no active instruments now, but there were in the past
                    if not has_active_instruments and has_past_instruments
                    else "speculative"
                )
            )
        )

        if has_active_instruments and current_year_data:
            instrument_type = _get_smart_instrument_description(current_year_data["instruments"], category, random.random() < 0.5)
        else:
            # For speculative cases, generate a plausible instrument name instead of just "derivatives"
            _, _, _, _, name, _ = _generate_instrument_name(category)
            # 50% chance to make it plural for better sentence flow
            instrument_type = f"{name}s" if random.random() < 0.5 else name

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

        # --- NEW: Probabilistically drop the mitigation sentence ---
        # This simulates filings that are less explicit about their strategy.
        # If the whole 7A is suppressed, this is always implied.
        if suppress_text_output or (allow_random_drops and random.random() < PROB_DROP_MITIGATION):
            # We still generate the evidence so the JSON output is correct,
            # but we mark it as implied since the sentence won't be in the text.
            mitigation_evidence.is_implied = True
            # but we don't add the sentence to the narrative text.
            evidence.append(mitigation_evidence)
        else:
            DROPPED_SENTENCES.append(f"[MITIGATION_DROP][{category}] {mitigation_sentence}")
            # If we are suppressing text output, we should not append the sentence.
            # This check is redundant due to the `if` condition but adds clarity.
            if suppress_text_output:
                raise Exception("Logic error: Should not be generating sentence text when suppress_text_output is True.")
            # The common case: generate both the sentence and the evidence.
            sentences.append(mitigation_sentence)
            evidence.append(mitigation_evidence)

        # 1c. Optional Aggregate Summary
        is_non_use_mitigation = mitigation_evidence.usage_status == "non_use"
        if (
            current_year_data
            and mitigation_evidence.usage_status != "non_use" # Don't summarize if we just said we don't use them
            and current_year_data["instruments"]
            and not is_non_use_mitigation and not suppress_text_output
            and random.random() < 0.5
        ):
            # --- NEW: Logic to choose between summary, comparative, or comparative_no_prior ---
            current_notional = (
                current_year_data["total_notional"] if current_year_data else 0
            )
            prev_notional = prev_year_data["total_notional"] if prev_year_data else 0
            prev2_notional = prev2_year_data["total_notional"] if prev2_year_data else 0

            sentence_type_to_use = "summary"  # Default
            notional_to_report = current_notional

            # --- FIX: Implement comparative sentence logic ---
            prev_notional_to_report = None
            prev2_notional_to_report = None
            prev_year_to_report = None
            prev2_year_to_report = None
            swap_type_for_summary = instrument_type  # Default to the single-year description

            # --- NEW: Use archetype to determine comparative years ---
            comparative_years = scenario.archetype.comparative_years
            use_three_year_comparative = (comparative_years == 3 and prev_notional > 0 and prev2_notional > 0)
            use_two_year_comparative = (comparative_years == 2 and prev_notional > 0)

            # Add a random chance to still generate a comparative sentence even if not the default
            if not (use_three_year_comparative or use_two_year_comparative) and random.random() < 0.3:
                if comparative_years > 1 and prev_notional > 0:
                    use_two_year_comparative = True

            if use_three_year_comparative:
                sentence_type_to_use = "comparative"
                notional_to_report = current_notional
                prev_notional_to_report = prev_notional
                prev2_notional_to_report = prev2_notional
                prev_year_to_report = reporting_year - 1
                prev2_year_to_report = reporting_year - 2
                # Generate a combined description for all three years
                combined_instruments = (current_year_data.get("instruments", []) +
                                        prev_year_data.get("instruments", []) + # type: ignore
                                        prev2_year_data.get("instruments", [])) # type: ignore
                # Remove duplicates by instrument ID
                unique_instruments = list({inst.instrument_id: inst for inst in combined_instruments}.values())
                swap_type_for_summary = _get_smart_instrument_description(unique_instruments, category, True)
            elif use_two_year_comparative:
                sentence_type_to_use = "comparative"
                notional_to_report = current_notional
                prev_notional_to_report = prev_notional
                prev_year_to_report = reporting_year - 1
                # --- FIX: Generate a combined description for the comparative sentence ---
                # This ensures the description covers instruments from both years.
                combined_instruments = (current_year_data.get("instruments", []) +
                                        prev_year_data.get("instruments", [])) # type: ignore
                # Remove duplicates by instrument ID
                unique_instruments = list({inst.instrument_id: inst for inst in combined_instruments}.values())
                swap_type_for_summary = _get_smart_instrument_description(unique_instruments, category, True)
            elif current_notional > 0 and prev_notional == 0:
                sentence_type_to_use = "comparative_no_prior_outstanding"
                notional_to_report = current_notional

            if notional_to_report > 0:
                use_fair_value = random.random() < 0.2
                value_type_to_use = "fair_value" if use_fair_value else "notional"

                summary_sentence_obj = NotionalSentence(
                    swap_type=swap_type_for_summary,
                    year=reporting_year,
                    notional=notional_to_report,
                    prev_notional=prev_notional_to_report,
                    prev2_notional=prev2_notional_to_report,
                    prev_year=prev_year_to_report,
                    prev2_year=prev2_year_to_report,
                    currency_code=currency_code,
                    currency_symbol=currency_symbol,
                    zero_notional_format=scenario.archetype.zero_notional_format,
                    month=reporting_month,
                    end_day=reporting_day,
                    notional_multiplier=scenario.archetype.notional_multiplier,
                    prefer_abbreviated=scenario.number_format_preference,
                    category=category,  # type: ignore
                    reporting_year=reporting_year,
                    value_type=value_type_to_use,
                    specific_details=specific_details,
                    sentence_type=sentence_type_to_use,  # type: ignore
                    is_summary=True,
                    preferred_negative_format=scenario.archetype.preferred_negative_format,
                )
                summary_sentence_text, evidence_obj = summary_sentence_obj.build()
                summary_sentence_obj.preferred_negative_format = scenario.archetype.preferred_negative_format
                sentences.append(summary_sentence_text)
                evidence.append(evidence_obj)

    # --- Part 2: Generate Detailed Individual Instrument Sentences ---
    elif part == "details":
        # This will be a list of paragraph strings.
        paragraphs = []
        if mentioned_instrument_ids is None:
            mentioned_instrument_ids = set()
        if mentioned_instrument_types is None:
            # This should be passed from the calling function, but as a fallback, initialize it.
            mentioned_instrument_types = set()

        # --- NEW: Table Generation Logic ---
        table_generated_for_category = False
        # If the archetype prefers tables and there are instruments, generate a table instead of individual paragraphs.
        if (
            scenario.archetype.prefers_tables
            and current_year_data
            and current_year_data["instruments"]
            and random.random() < 0.7 # 70% chance to generate a table if preferred
        ): # type: ignore
            cat_to_map = {
                "IR": "Interest Rate",
                "FX": "Foreign Currency",
                "CP": "Commodity",
                "EQ": "Equity",
                "GEN": "",
            }
            table_builder = DerivativeTable(
                instruments=current_year_data["instruments"],
                category=cat_to_map.get(category, ""), yearly_data=yearly_data,
                reporting_year=reporting_year,
                reporting_day=reporting_day,
                reporting_month=reporting_month,
                currency_symbol=currency_symbol,
                notional_multiplier=scenario.archetype.notional_multiplier,
                preferred_negative_format=scenario.archetype.preferred_negative_format,
                prefer_abbreviated=scenario.number_format_preference,
                currency_code=currency_code,
            )
            # --- MODIFIED: build() now returns remaining instruments ---
            table_str, table_evidence, remaining_instruments = table_builder.choose_and_build()
            if table_str:
                # The table string itself is the "paragraph". We also need to generate evidence for the instruments in it.
                paragraphs.append(table_str)
                evidence.extend(table_evidence)
                # --- NEW: Update the list of instruments to process with the remainder ---
                table_generated_for_category = True
                # This allows us to process the rest of the instruments below.
                current_year_data["instruments"] = remaining_instruments
            
            # If no table was generated, or if there are remaining instruments,
            # the code will now continue to the loop below instead of returning.

        if current_year_data and current_year_data["instruments"]:
            # --- NEW: Randomly decide which active instruments to mention ---
            # This simulates incomplete disclosure by sometimes omitting an instrument,
            # but only when `allow_random_drops` is True.
            instruments_to_mention = current_year_data["instruments"]
            if allow_random_drops:
                instruments_to_mention = [
                    inst for inst in instruments_to_mention if random.random() < ACTIVE_INSTRUMENT_MENTION_PROB
                ]

            # --- NEW: With a small chance, add a duplicate instrument to the list to test aliasing ---
            if instruments_to_mention and random.random() < REPEAT_MENTION_PROB: # 25% chance to add a repeat mention
                # Pick a random instrument that is already slated to be mentioned
                instrument_to_repeat = random.choice(instruments_to_mention)
                # Insert it at a random position in the list
                insert_position = random.randint(0, len(instruments_to_mention))
                instruments_to_mention.insert(insert_position, instrument_to_repeat)

            for instrument in instruments_to_mention:
                # --- FIX: Initialize report variables at the top of the loop ---
                year_to_report = reporting_year
                notional_to_report = 0
                sentence_type = "individual"  # Default sentence type

                use_fair_value = random.random() < 0.2
                # --- FIX: Distinguish between a repeated TYPE and a repeated INSTANCE ---
                # is_repeated_type is for context ("another swap...")
                # is_repeated_instance is for aliasing ("the swap...")
                is_repeated_type = (
                    instrument.instrument_type in mentioned_instrument_types
                )
                is_repeated_instance = (
                    instrument.instrument_id in mentioned_instrument_ids
                )

                value_type = "fair_value" if use_fair_value else "notional"
                value_to_report = instrument.notional_history.get(reporting_year, 0)

                # --- FIX: Decide whether to use the full name or the alias ---
                # If we've seen this instrument before, there's a high chance of using its alias.
                # An alias is only used if this specific instrument INSTANCE has been seen before.
                use_alias = is_repeated_instance and random.random() < 0.75
                name_to_use = (
                    instrument.instrument_alias
                    if use_alias and instrument.instrument_alias
                    else instrument.instrument_type
                )

                # Determine if the instrument is "historical" (existed in a prior year) # type: ignore
                is_historical = False
                if prev_year_data:
                    prev_ids = {i.instrument_id for i in prev_year_data["instruments"]}
                    if (
                        instrument.instrument_id in prev_ids
                        and instrument.instrument_id
                        not in (current_year_data.get("new_ids", set()))  # type: ignore
                    ):
                        is_historical = True

                # --- NEW: Timeline generation for instruments with a long history ---
                history_length = len(instrument.notional_history)
                is_long_history_timeline = (
                    is_historical and history_length > 1 and random.random() < 0.15
                )

                # --- NEW: Use TimelineSentence class for long histories ---
                if is_long_history_timeline:
                    timeline_builder = TimelineSentence(
                        instrument=instrument,
                        company_name=scenario.company_name,
                        reporting_year=reporting_year,
                        currency_symbol=currency_symbol,
                        preferred_negative_format=scenario.archetype.preferred_negative_format,
                        currency_code=instrument.currency,
                        prefer_abbreviated=scenario.number_format_preference,
                        value_type=value_type,
                    )
                    timeline_paragraph, timeline_evidence = timeline_builder.build()

                    if timeline_paragraph:
                        paragraphs.append(timeline_paragraph)
                        evidence.append(timeline_evidence)
                        # Mark as mentioned for all future references
                        mentioned_instrument_ids.add(instrument.instrument_id)
                        mentioned_instrument_types.add(instrument.instrument_type)

                    continue  # Skip the normal individual sentence generation for this instrument

                # --- Standard sentence generation (current, historical, or inception) ---
                else:
                    # --- FIX: Use the 'new_individual' sentence type for new instruments ---
                    is_new_instrument = instrument.start_year == reporting_year
                    if is_new_instrument:
                        # --- NEW: For new instruments, check if there were none prior to use comparative sentence ---
                        if (
                            prev_year_data
                            and prev_year_data["total_notional"] == 0
                            and random.random() < 0.4
                        ):
                            sentence_type = "comparative_no_prior_outstanding"
                        else:
                            sentence_type = "new_individual"
                    elif is_historical:
                        # --- NEW: Use a weighted choice system for historical instruments ---
                        options = ["individual", "historical_individual", "comparative"]
                        weights = [0.45, 0.35, 0.20]  # Base weights

                        # Adjust weights based on archetype and data availability
                        if (
                            scenario.archetype.comparative_years == 3
                            and instrument.notional_history.get(reporting_year - 2, 0)
                            > 0
                        ):
                            weights[2] += 0.25  # Boost comparative chance
                        elif (
                            scenario.archetype.comparative_years == 2
                            and instrument.notional_history.get(reporting_year - 1, 0)
                            > 0
                        ):
                            weights[2] += 0.15  # Boost comparative chance

                        # Normalize weights to sum to 1
                        total_weight = sum(weights)
                        normalized_weights = [w / total_weight for w in weights]

                        sentence_type = random.choices(
                            options, weights=normalized_weights, k=1
                        )[0]

                        # If historical_individual is chosen, set up its specific data
                        if sentence_type == "historical_individual":
                            # 50% chance to talk about the inception year vs. a random past year
                            if (
                                random.random() < 0.5
                                and instrument.start_year in instrument.notional_history
                            ):
                                year_to_report = instrument.start_year
                                notional_to_report = instrument.notional_history[
                                    instrument.start_year
                                ]
                            else:
                                past_years = [
                                    y
                                    for y in instrument.notional_history.keys()
                                    if y < reporting_year
                                ]
                                if past_years:
                                    year_to_report = random.choice(past_years)
                                    notional_to_report = instrument.notional_history[
                                        year_to_report
                                    ]
                                else:
                                    # Fallback if no past years exist (should be rare for historical)
                                    year_to_report = reporting_year
                                    notional_to_report = value_to_report
                    else:
                        sentence_type = "individual"

                    # If the sentence type wasn't a special historical case, set defaults
                    if sentence_type not in ["historical_individual"]:
                        year_to_report = reporting_year
                        notional_to_report = value_to_report

                    individual_sentence_obj = NotionalSentence(
                        swap_type=name_to_use,
                        year=year_to_report,
                        notional=notional_to_report,
                        currency_symbol=instrument.symbol,
                        currency_code=instrument.currency,
                        company_name=scenario.company_name,
                        sentence_type=sentence_type,  # type: ignore
                        prev_notional=instrument.notional_history.get(reporting_year - 1, 0) if sentence_type == "comparative" else None,  # type: ignore
                        prev2_notional=instrument.notional_history.get(reporting_year - 2, 0) if sentence_type == "comparative" and scenario.archetype.comparative_years == 3 else None,  # type: ignore
                        prev_year=reporting_year - 1 if sentence_type == "comparative" else None,  # type: ignore
                        prev2_year=reporting_year - 2 if sentence_type == "comparative" and scenario.archetype.comparative_years == 3 else None,  # type: ignore
                        maturity_year=instrument.maturity_year,
                        prefer_abbreviated=scenario.number_format_preference,
                        zero_notional_format=scenario.archetype.zero_notional_format,
                        category=category,  # type: ignore
                        reporting_year=reporting_year,
                        value_type=value_type,
                        is_repeated_mention=is_repeated_type,  # Pass the TYPE check for contextual phrasing
                        preferred_negative_format=scenario.archetype.preferred_negative_format,
                        instrument=instrument, # Pass the full instrument object
                    )
                    individual_sentence_text, evidence_obj = (
                        individual_sentence_obj.build()
                    )
                    evidence_obj.instrument_id = (
                        instrument.instrument_id  # type: ignore
                    )
                    paragraphs.append(individual_sentence_text)
                    evidence.append(evidence_obj)
                    mentioned_instrument_ids.add(
                        instrument.instrument_id
                    )  # Mark instance as mentioned
                    mentioned_instrument_types.add(
                        instrument.instrument_type
                    )  # Mark as mentioned

        # Describe terminated instruments by looking at the previous year's data
        # Describe terminated instruments by checking for zero notional in current year
        if current_year_data and prev_year_data:
            # Find instruments that have zero notional this year but had value last year
            terminated_instruments = [
                inst
                for inst in current_year_data["instruments"]
                if inst.notional_history.get(scenario.reporting_year, 0) == 0
                and (inst.notional_history.get(scenario.reporting_year - 1, 0) > 0
                )
            ]

            # --- NEW: Randomly decide which terminated instruments to mention ---
            terminated_to_mention = terminated_instruments
            if allow_random_drops:
                terminated_to_mention = [
                    inst for inst in terminated_instruments if random.random() < TERMINATED_INSTRUMENT_MENTION_PROB
                ]

            for instrument in terminated_to_mention:

                # --- NEW: Give expired hedges a chance to use a timeline for more variety ---
                history_length = len(instrument.notional_history)
                use_timeline_for_terminated = (
                    history_length > 1 and random.random() < 0.15
                )

                is_repeated_type_terminated = (
                    instrument.instrument_type in mentioned_instrument_types
                )
                is_repeated_instance_terminated = (
                    instrument.instrument_id in mentioned_instrument_ids
                )

                if use_timeline_for_terminated:
                    timeline_builder = TimelineSentence(
                        instrument=instrument,
                        company_name=scenario.company_name,
                        reporting_year=reporting_year,
                        currency_symbol=currency_symbol,
                        preferred_negative_format=scenario.archetype.preferred_negative_format,
                        currency_code=currency_code,
                        prefer_abbreviated=scenario.number_format_preference,
                        value_type="notional",  # Keep it simple for terminated timelines
                    )
                    timeline_paragraph, timeline_evidence = timeline_builder.build()
                    if timeline_paragraph:
                        paragraphs.append(timeline_paragraph)
                        evidence.append(timeline_evidence)
                        mentioned_instrument_ids.add(instrument.instrument_id)
                        mentioned_instrument_types.add(instrument.instrument_type)
                else:
                    # --- NEW: Use a weighted choice for describing terminated instruments ---
                    options = ["terminated_individual", "comparative_no_outstanding", "comparative"]
                    weights = [0.50, 0.35, 0.15] # Base weights

                    # A 'comparative' sentence is only possible if there are at least two prior years of history.
                    can_do_comparative = len(instrument.notional_history) >= 2
                    if not can_do_comparative:
                        # Remove 'comparative' option and re-normalize weights
                        options.pop()
                        weights.pop()
                        total_weight = sum(weights)
                        weights = [w / total_weight for w in weights]

                    sentence_type_to_use = random.choices(options, weights=weights, k=1)[0]

                    # Set up data based on the chosen sentence type
                    notional_to_report = 0
                    if sentence_type_to_use == "terminated_individual":
                        # The 'notional' is the final value from the prior year.
                        notional_to_report = instrument.maturity_value or instrument.notional_history.get(reporting_year - 1, 0)
                    elif sentence_type_to_use == "comparative_no_outstanding":
                        # The 'notional' is the prior year's value, which will be compared against zero.
                        notional_to_report = instrument.notional_history.get(reporting_year - 1, 0)
                    elif sentence_type_to_use == "comparative":
                        # The 'notional' is the value from reporting_year - 1.
                        # The 'prev_notional' will be from reporting_year - 2.
                        notional_to_report = instrument.notional_history.get(reporting_year - 1, 0)

                    use_alias_terminated = is_repeated_instance_terminated and random.random() < 0.75
                    name_to_use_terminated = instrument.instrument_alias if use_alias_terminated and instrument.instrument_alias else instrument.instrument_type

                    terminated_instrument_obj = NotionalSentence(
                        swap_type=name_to_use_terminated,
                        year=reporting_year,
                        notional=notional_to_report,
                        currency_symbol=instrument.symbol,
                        currency_code=instrument.currency,
                        company_name=scenario.company_name,
                        sentence_type=sentence_type_to_use,  # type: ignore
                        # Pass prior year data only for the 'comparative' type
                        prev_notional=instrument.notional_history.get(reporting_year - 2, 0) if sentence_type_to_use == "comparative" else None,
                        prev_year=reporting_year - 1 if sentence_type_to_use == "comparative" else None,
                        maturity_year=instrument.maturity_year,
                        prefer_abbreviated=scenario.number_format_preference,
                        zero_notional_format=scenario.archetype.zero_notional_format,
                        category=category,  # type: ignore
                        reporting_year=reporting_year,
                        value_type="notional",
                        is_repeated_mention=is_repeated_type_terminated,
                        preferred_negative_format=scenario.archetype.preferred_negative_format,
                        instrument=instrument,
                    )
                    terminated_instrument_text, evidence_obj = (
                        terminated_instrument_obj.build()
                    )
                    evidence_obj.instrument_id = instrument.instrument_id
                    paragraphs.append(terminated_instrument_text)
                    mentioned_instrument_ids.add(instrument.instrument_id)
                    mentioned_instrument_types.add(instrument.instrument_type)
                    evidence.append(evidence_obj)

        # If there are no current instruments, check for a comparative no-outstanding sentence
        if (
            not (current_year_data and current_year_data["instruments"]) and not table_generated_for_category
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
                notional=prev_year_data[
                    "total_notional"
                ],  # Pass the prior year notional for the template
                sentence_type="comparative_no_outstanding",  # type: ignore
                category=category,  # type: ignore
                reporting_year=reporting_year,
                preferred_negative_format=scenario.archetype.preferred_negative_format,
                prefer_abbreviated=scenario.number_format_preference,
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
    # --- MODIFIED: This function will now return paragraphs instead of sentences ---
    all_paragraphs: List[str] = []  # Each string in this list will be a full paragraph

    # --- NEW: Probabilistically drop the entire accounting policy section ---
    if random.random() < PROB_DROP_ACCOUNTING_POLICY:
        # NEW: Log that the section was dropped.
        # Since sentences are generated inside the loop, we can't log them here.
        # We'll just log a general message.
        DROPPED_SENTENCES.append("[ACCOUNTING_POLICY_DROP] Entire accounting policy section was dropped.")
        return [], []


    all_evidence: List[BaseNarrativeEvidence] = []  # type: ignore
    mentioned_policies = set()
    
    # --- NEW: Generate accounting policies for each category with instruments ---
    if scenario.policy and scenario.policy.category_policies:
        active_categories = {
            inst.category
            for inst in scenario.instruments
            if inst.notional_history.get(scenario.reporting_year, 0) > 0
        }

        policies_to_generate = [
            p for p in scenario.policy.category_policies if p.category in active_categories
        ]

        # --- FIX: Create a separate paragraph for each category's policies ---
        is_first_policy_run = True
        for cat_policy in policies_to_generate:
            category_sentences = []
            instruments_in_cat = [i for i in scenario.instruments if i.category == cat_policy.category]
            swap_type_desc = _get_smart_instrument_description(instruments_in_cat, cat_policy.category)

            policy_sentence_builder = AccountingPolicySentence(
                cat_policy=cat_policy,
                company_name=scenario.company_name,
                already_mentioned_policies=mentioned_policies,
                swap_type_override=swap_type_desc,
                # --- NEW: Pass the flag to control general vs. specific sentences ---
                generate_specifics_only=not is_first_policy_run
            )
            generated_items = policy_sentence_builder.build()
            for sentence, evidence in generated_items:
                category_sentences.append(sentence)
                all_evidence.append(evidence) # type: ignore
                if isinstance(evidence, PolicyEvidence):
                    mentioned_policies.add(evidence.policy_type)
            
            # Join the sentences for this specific category into a single paragraph
            if category_sentences:
                # After the first successful run, all subsequent runs should be specifics-only
                is_first_policy_run = False
                all_paragraphs.append(" ".join(s for s in category_sentences))

    return all_paragraphs, all_evidence


def generate_narrative_from_scenario(
    scenario: GenerationScenario,
    allow_random_drops: bool = False,
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
    mentioned_instrument_types: Set[str] = set() # Tracks full type names
    mentioned_instrument_ids: Set[int] = set() # Tracks specific instrument IDs

    # 1. Generate the top-level general policy statement.
    # --- NEW: Probabilistically drop the entire general policy section ---
    # This simulates cases where the initial summary text is not extracted.
    if not (allow_random_drops and random.random() < PROB_DROP_GENERAL_POLICY):
        policy_sentences, policy_evidence = _generate_narrative_policy(scenario)
        DROPPED_SENTENCES.append(f"[GENERAL_POLICY_DROP] General policy section was dropped.")
        if policy_sentences: # This becomes its own section
            item_7a_sections.append(" ".join(s for s in policy_sentences if s))
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

    # --- NEW: Randomize the order of category processing ---
    category_order = ["IR", "FX", "CP", "EQ", "GEN"]
    random.shuffle(category_order)

    # --- Part 1: Build the "Item 7A" Summary Section ---
    # --- NEW: Probabilistically drop the entire 7A summary section ---
    # This simulates filings that jump straight to the detailed notes.
    if allow_random_drops and random.random() < PROB_DROP_7A_SUMMARY:
        # Even if we drop the text, we MUST generate the underlying evidence
        DROPPED_SENTENCES.append("[7A_SUMMARY_DROP] Entire Item 7A summary section was dropped.")
        # (especially MitigationEvidence) so the JSON output is correct.
        # We mark the evidence as 'implied' since the text isn't there.
        for category in category_order:
            if category in aggregated_data or all_relevant_categories.get(category, False):
                _, summary_evidence, _ = _generate_category_narrative(
                    category,
                    aggregated_data.get(category, {}),
                    scenario,
                    part="summary",
                    suppress_text_output=True, # New flag to only generate evidence
                )
                all_evidence.extend(summary_evidence)
    else:
        # The common case: generate the full summary text and evidence.
        for category in category_order:
            has_instruments = category in aggregated_data
            has_exposure = all_relevant_categories.get(category, False)

            if has_instruments or (has_exposure and category != "GEN"):
                yearly_data_for_cat = aggregated_data.get(category, {})
                summary_sentences, summary_evidence, _ = _generate_category_narrative(
                    category, yearly_data_for_cat, scenario, part="summary",
                    allow_random_drops=allow_random_drops,
                )
                item_7a_sections.append(" ".join(s for s in summary_sentences if s))
                all_evidence.extend(summary_evidence)

    # --- NEW: Part 2.5: Build the dedicated "Debt" Section ---
    # This section provides detailed context on all debt instruments.
    debt_paragraphs, debt_evidence = _generate_debt_narrative(scenario)
    if debt_paragraphs:
        derivative_details_sections.extend(debt_paragraphs)
        all_evidence.extend(debt_evidence)

    # --- NEW: Part 2.6: Build the dedicated "Foreign Currency Risk" Section ---
    fx_paragraphs, fx_evidence = _generate_fx_narrative(scenario)
    if fx_paragraphs:
        derivative_details_sections.extend(fx_paragraphs)
        all_evidence.extend(fx_evidence)

    # --- NEW: Part 2.7: Build the dedicated "Commodity Price Risk" Section ---
    cp_paragraphs, cp_evidence = _generate_cp_narrative(scenario)
    if cp_paragraphs:
        derivative_details_sections.extend(cp_paragraphs)
        all_evidence.extend(cp_evidence)
    
    # --- NEW: Part 2.8: Build the dedicated "Equity Risk" Section ---
    eq_paragraphs, eq_evidence = _generate_eq_narrative(scenario)
    if eq_paragraphs:
        derivative_details_sections.extend(eq_paragraphs)
        all_evidence.extend(eq_evidence)

    # --- Part 2: Build the "Derivative Financial Instruments" Details Section ---
    # Add a title for this section if there are any details to report.
    has_any_details = any(
        cat in aggregated_data for cat in ["IR", "FX", "CP", "EQ", "GEN"]
    )
    if has_any_details:
        # This is a simple way to add a section header.
        derivative_details_sections.append("Derivative Financial Instruments")

    for category in category_order:
        if category in aggregated_data:
            yearly_data_for_cat = aggregated_data.get(category, {})
            detail_sentences, detail_evidence, _ = _generate_category_narrative(
                category,
                yearly_data_for_cat,
                scenario,
                part="details",
                mentioned_instrument_types=mentioned_instrument_types,
                mentioned_instrument_ids=mentioned_instrument_ids,
                allow_random_drops=allow_random_drops,
            )
            # NEW: Join the generated paragraphs with newlines.
            # This ensures timelines and individual instruments get their own paragraphs.
            category_details_paragraph = "\n\n".join(s for s in detail_sentences if s)
            derivative_details_sections.append(category_details_paragraph)
            all_evidence.extend(detail_evidence)

    # --- NEW: Part 2.9: Generate Optional Standalone "Additional" Tables ---
    # These tables (AOCI, Maturity, etc.) often appear as separate disclosures.
    if has_any_details and scenario.archetype.prefers_tables and random.random() < 0.6:
        # Get currency and money unit details for table generation.
        currency_symbol, _, currency_code = _get_currency_and_unit_details(scenario)

        # We can generate one of these tables for each category that has instruments.
        # Let's pick one or two categories at random to generate a table for.
        cats_with_instruments = list(aggregated_data.keys())
        if cats_with_instruments:
            num_tables_to_gen = random.randint(1, len(cats_with_instruments))
            cats_for_tables = random.sample(cats_with_instruments, num_tables_to_gen)
            cat_to_map = {
                "IR": "interest rate",
                "FX": "foreign currency",
                "CP": "commodity",
                "EQ": "equity",
                "GEN": "",
            }
            for category in cats_for_tables:
                # We need all instruments for the table, not just the ones for a specific year.
                all_instruments_for_cat = [
                    inst for inst in scenario.instruments if inst.category == category
                ]
                table_builder = DerivativeTable(
                    instruments=all_instruments_for_cat,
                    category=cat_to_map.get(category, ""),
                    yearly_data=aggregated_data.get(category, {}),
                    reporting_year=scenario.reporting_year,
                    reporting_day=scenario.reporting_day,
                    reporting_month=scenario.reporting_month,
                    currency_symbol=currency_symbol,
                    notional_multiplier=scenario.archetype.notional_multiplier,
                    prefer_abbreviated=scenario.number_format_preference,
                    currency_code=currency_code,
                    preferred_negative_format=scenario.archetype.preferred_negative_format,
                )
                # Call build with additional=True to get the other table formats
                table_str, table_evidence, _ = table_builder.choose_and_build(additional=True)
                if table_str:
                    derivative_details_sections.append(table_str)
                    all_evidence.extend(table_evidence)

    # 3. Effectiveness and Accounting Section
    accounting_sentences, accounting_evidence = _generate_narrative_accounting(scenario)
    # This can be appended to the details section or be its own section.
    # Let's add it to the end of the details for now.
    if accounting_sentences and derivative_details_sections:
        # --- MODIFIED: Join with newlines to create separate paragraphs ---
        accounting_section_paragraph = "\n\n".join(s for s in accounting_sentences if s)
        derivative_details_sections.append(accounting_section_paragraph)
        all_evidence.extend(accounting_evidence)

    # =========================================================================
    # FINAL ASSEMBLY: Join sections with newlines for a prettier output.
    # =========================================================================

    # Assemble the final narrative from the generated parts
    narrative_sections = []
    narrative_sections.extend(item_7a_sections)
    narrative_sections.extend(derivative_details_sections)
    narrative = "\n\n".join(section for section in narrative_sections if section)
    # strip out more than 2 newlines
    narrative = re.sub(r"\n{3,}", "\n\n", narrative)
    # Prepend the reporting year tag.
    full_narrative = (
        f"<reportingYear>{scenario.reporting_year}</reportingYear> {narrative}"
    )
    # --- NEW: Post-generation warnings for leftover placeholders ---
    warnings = []
    if "None" in full_narrative: warnings.append("The word 'none' was found.")
    if re.search(r'[\{\}\[\]]', full_narrative): warnings.append("Leftover template characters like '{}' or '[]' were found.")
    if warnings:
        full_narrative += f"\n\n[WARNING: Please review for potential ambiguity or unintended implications. Issues found: {'; '.join(warnings)}]"
    return full_narrative, all_evidence


def _generate_debug_output(scenario: GenerationScenario, evidence: List[BaseNarrativeEvidence]) -> str:
    global DEBUG
    if not DEBUG:
        return ""
    """
    Generates a formatted string containing debug information about the scenario,
    including archetype, instruments, and their hedged items (exposures).
    """
    debug_lines = ["\n\n--- DEBUG INFO ---"]
    debug_lines.append(f"Archetype: {scenario.archetype.name}")
    # --- NEW: Add exposure counts to debug output ---
    exposure_counts = scenario.archetype.get_exposure_counts()
    debug_lines.append(f"Exposures: Debt({exposure_counts['debt']}), "
                       f"FX({exposure_counts['fx']}), "
                       f"Commodity({exposure_counts['commodity']}), "
                       f"Equity({exposure_counts['equity']})")
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
        debug_lines.append(f"  - Currency: {inst.currency}")
        debug_lines.append(f"  - Start: {inst.start_month} {inst.start_year}")
        debug_lines.append(f"  - Maturity: {inst.maturity_year}")
        debug_lines.append(f"  - Maturity Value: {inst.maturity_value}")
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

    # # --- NEW: Add evidence objects to debug output ---
    # debug_lines.append("\n" + "=" * 20)
    # debug_lines.append(f"\nEvidence Objects ({len(evidence)}):")
    # for i, ev in enumerate(evidence):
    #     # Use asdict for a clean, serializable representation
    #     evidence_dict = asdict(ev)
    #     debug_lines.append(f"  - Evidence {i+1}:")
    #     # Pretty-print the dictionary
    #     debug_lines.append(f"    {json.dumps(evidence_dict, indent=6)}")

    # --- NEW: Add dropped sentences to debug output ---
    if DROPPED_SENTENCES:
        debug_lines.append("\n" + "=" * 20)
        debug_lines.append(f"\nDropped Sentences/Sections ({len(DROPPED_SENTENCES)}):")
        for i, dropped in enumerate(DROPPED_SENTENCES):
            debug_lines.append(f"  {i+1}. {dropped}")
        DROPPED_SENTENCES.clear() # Clear the list for the next run

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

    # --- NEW: Generate exposure map based on the collected ExposureEvidence ---
    # This ensures the map only reflects what was actually written in the narrative.
    exposure_map = {
        cat: False for cat in DERIVATIVE_CATEGORIES
    }
    for ev in evidence:
        if isinstance(ev, ExposureEvidence):
            if ev.category in exposure_map:
                exposure_map[ev.category] = True

    # --- NEW: Mitigation status is now "current", "historical", or "never" ---
    # It's driven by the usage_status in the MitigationEvidence objects.
    # --- FIX: Default to "unknown" if exposure exists but no evidence, "none" if no exposure. ---
    mitigation_map = {
        # If there's exposure but no mention of hedging, the status is "unknown".
        cat: "unknown" if exposure_map.get(cat) else "none"
        for cat in DERIVATIVE_CATEGORIES
    }
    for ev in evidence:
        if isinstance(ev, MitigationEvidence):
            status = ev.usage_status
            category = ev.category
            if category in mitigation_map:
                # If the evidence is from a dropped sentence (is_implied), only trust it
                # if it's based on concrete instrument presence ('current' or 'historical').
                # A speculative or non-use statement that was never written should not change the status from 'unknown'.
                if ev.is_implied:
                    if status in ("current", "historical"):
                        mitigation_map[category] = status
                # If the evidence is from a written sentence, trust its status.
                elif status == "current":
                    mitigation_map[category] = "current"
                elif status == "historical":
                    mitigation_map[category] = "historical"
                elif status == "non_use":
                    mitigation_map[category] = "never"
                elif status == "speculative": # "may use", "from time to time", etc.
                    mitigation_map[category] = "likely"
    chain_of_thought = "\n".join([e.to_string() for e in evidence])

    # --- Append a final reasoning statement for any GENERIC derivatives ---
    # This logic is now centralized here, instead of in the Evidence class.
    has_generic_evidence = any(ev.category == "GEN" and ev.status =="current" for ev in evidence)
    if has_generic_evidence:
        # Find other specific instrument types that were identified in the text.
        all_seen_types = sorted(
            list({
                ev.instrument_type
                for ev in evidence
                if (
                    (isinstance(ev, NotionalEvidence) or isinstance(ev, MitigationEvidence))
                    and ev.category != "GEN"
                    and ev.instrument_type
                    and "derivative" not in ev.instrument_type
                    and "instrument" not in ev.instrument_type
                )
            })
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

        generic_reasoning = (
            "After reviewing the full text, I found a reference to a derivative that lacks sufficient context "
            "to determine its specific category"
        )
        if display_types:
            generic_reasoning += (
                f" (unlike other instruments identified, such as {', '.join(display_types)}), "
                "so it is treated as a generic reference."
            )
        else:
            generic_reasoning += ", so it is treated as a generic reference."
        chain_of_thought += "\n" + generic_reasoning.strip()

    # --- NEW: Add warning checks to the chain of thought, similar to the narrative ---
    warnings = []
    if "None" in chain_of_thought:
        warnings.append("The word 'none' was found.")
    if re.search(r'[\{\}\[\]]', chain_of_thought):
        warnings.append("Leftover template characters like '{}' or '[]' were found.")
    if warnings:
        chain_of_thought += f"\n\n[WARNING: Chain of thought may be flawed. Issues found: {'; '.join(warnings)}]"

    # --- Build the derivatives list ONLY from what was mentioned in the evidence. ---

    # This ensures the JSON perfectly matches the narrative. Each piece of evidence
    # that points to a specific instrument contributes to its entry in the final JSON.
    derivatives_list = []

    # --- NEW: Use a more specific key to handle multiple evidence types for one instrument ID ---
    # (e.g., a parent FX Forward and its multiple currency exposures from a table)
    # The key will be a tuple: (instrument_id, instrument_type, value_type)
    instrument_evidence_map: Dict[Tuple[int, str, str], Dict] = {}

    for ev in evidence:
        # We only care about evidence that has an instrument ID and notional value.
        # Why evidence? Because during training, we would not append every reference to every instrument
        # To prevent hallucinations on fictional instruments it hasn't seen via evidence.
        if (
            not isinstance(ev, NotionalEvidence) or ev.instrument_id is None
            or ev.instrument_type is None or ev.value_type is None
            or ev.notional is None
        ):
            continue

        instrument_id = ev.instrument_id
        value_type_key = ev.value_type
        instrument_type_key = ev.instrument_type
        unique_key = (instrument_id, instrument_type_key, value_type_key)

        # --- FIX: Look up the instrument directly to get the correct currency/unit ---
        # This is the single source of truth for the instrument's properties.
        instrument_obj = next(
            (inst for inst in scenario.instruments if inst.instrument_id == instrument_id), None
        )
        
        # --- FIX: Correctly determine status for terminated instruments ---
        is_terminated_evidence = (
            (ev.maturity_value is not None and ev.maturity_value > 0) or
            (ev.maturity_year and ev.maturity_year < scenario.reporting_year) or
            (ev.notional == 0 and ev.year == scenario.reporting_year and ev.value_type != "notional_exposure") or
            ev.sentence_type in ["terminated_individual", "comparative_no_outstanding", "historical_individual"]
        )
        if is_terminated_evidence:
            continue # Don't care about terminated, only about active ones

        # --- FIX: Always process the evidence, don't skip if key exists ---

        # Precompute values to avoid nested conditionals in the dict
        if instrument_obj:
            inst_type = instrument_obj.instrument_type
            category = instrument_obj.category
            currency = (
                instrument_obj.currency
                if ev.value_type != "notional_exposure"
                else ev.currency
            )
        else:
            inst_type = ev.instrument_type or "Unknown"
            category = ev.category
            currency = ev.currency

        value_type = ev.value_type.replace("_", " ")

        instrument_evidence_map[unique_key] = {
            "type": inst_type.strip(),
            "category": category,
            "status": "current",
            "amount": ev.notional,  # This will be updated if more evidence is found
            "currency": currency,
            "value_type": value_type,
            "level": "individual",
        }


    # Convert the aggregated map into the final list.
    # This creates one entry per unique instrument ID found in the evidence.
    derivatives_list = list(instrument_evidence_map.values())

    # Additionally, add entries for aggregate summaries that don't have an instrument ID
    for ev in evidence:
        if (
            isinstance(ev, NotionalEvidence) and ev.aggregate
            and ev.notional is not None
            and ev.notional > 0
            and ev.year == scenario.reporting_year # Only include current year summaries
            and ev.status != "timeline" # Exclude timelines
        ):
            derivatives_list.append(
                {
                    "type": ev.instrument_type,
                    "category": ev.category,
                    "level": "aggregate",
                    "status": "current",
                    "amount": ev.notional,
                    "currency": ev.currency,
                    "value_type": ev.value_type.replace("_", " ")
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


def generate_training_sample(archetype_index=None):
    """Generates a single, complete training sample (narrative + JSON)."""
    # --- NEW: Determine if random drops should be allowed ---
    # Drops are only allowed if no specific archetype index is given.
    allow_random_drops = archetype_index is None

    # 1. Create a random scenario that defines the story.
    scenario = create_random_scenario(archetype_index)

    # 2. Generate the narrative text and the evidence list based on that scenario.
    narrative_text, evidence = generate_narrative_from_scenario(scenario, allow_random_drops=allow_random_drops)

    # --- NEW: Append debug output to the narrative text ---
    debug_output = _generate_debug_output(scenario, evidence)
    narrative_text += debug_output

    # 3. Generate the corresponding JSON label using the evidence from the narrative.
    json_output = generate_json_from_scenario(scenario, evidence)

    # The final output is a tuple of the text and the JSON object (or string).
    return (narrative_text, json_output)


# %%
if __name__ == "__main__":
    # Example of how to generate one sample
    # --- NEW: Allow selecting a scenario via command-line argument ---
    archetype_idx = None
    if len(sys.argv) > 1:
        try:
            archetype_idx = int(sys.argv[1])
            if not (0 <= archetype_idx < len(SCENARIO_ARCHETYPES)):
                print(f"Error: Index {archetype_idx} is out of bounds. Please use an index between 0 and {len(SCENARIO_ARCHETYPES) - 1}.")
                sys.exit(1)
            print(f"--- Generating specific scenario for archetype index: {archetype_idx} ({SCENARIO_ARCHETYPES[archetype_idx].name}) ---")
        except ValueError:
            print(f"Error: Could not parse '{sys.argv[1]}' as an integer index.")
            sys.exit(1)

    text, json_data = generate_training_sample(archetype_index=archetype_idx)

    print("--- GENERATED NARRATIVE ---")
    print(text)
    print("\n--- GENERATED JSON ---")
    print(json.dumps(json_data, indent=2))
# %%
