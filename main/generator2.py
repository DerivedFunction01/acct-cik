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


T_HedgedItem = TypeVar("T_HedgedItem", bound="HedgedItem")


@dataclass
class DerivativeInstrument:
    """Base class for a single derivative instrument within our narrative."""
    instrument_id: int # A unique ID to track the same instrument across multiple years.
    instrument_type: str
    category: Literal["IR", "FX", "CP", "EQ", "GEN"] # The category of the derivative
    month: str  # The month this state of the instrument is for.
    year: int  # The year this state of the instrument is for.
    hedge_designation: Optional[Literal["cash_flow", "fair_value", "net_investment", "economic"]] = None
    maturity_month: Optional[str] = None # The maturity month
    maturity_year: Optional[int] = None # The maturity year
    num_instruments: Optional[int] = None # How many total

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
    hedged_item_id: int # A unique ID to track the same hedged item across multiple years.

    def to_dict(self) -> Optional[Dict]:
        """Serializes the hedged item data to a dictionary."""
        data = {k: v for k, v in self.__dict__.items() if v is not None}
        # Ensure the ID is always present if the object exists
        return {"hedged_item_id": self.hedged_item_id, **data} if data else None


@dataclass
class DebtHedgedItem(HedgedItem):
    """Represents a debt instrument being hedged (for IR derivatives)."""
    debt_type: str  # e.g., "variable-rate credit facility", "senior notes"
    month: str # THe month the debt was init
    year: int # The year the debt was init
    maturity_month: str # The maturity month
    maturity_year: int # The maturity year
    principal_amount: int # The initial principal
    interest_rate_type: Literal["fixed", "variable"]
    interest_rate: float
    interest_rate2: float
    payment_frequnecy: str
    other_party: str # The other party of the debt


@dataclass
class CurrencyExposure:
    """Represents a specific currency exposure with its amount."""
    currency: str  # e.g., "EUR", "GBP"
    amount: int    # The notional amount of the exposure in that currency


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
    cost_type: str # Ex. input, extraction, storage
    transaction_type: Literal["purchase", "sale"]
    supplier: Optional[str] # Ex. a third party supplier


@dataclass
class EquityHedgedItem(HedgedItem):
    """Represents an equity instrument being hedged (for EQ derivatives)."""
    # Placeholder for future implementation
    underlying_equity: str # e.g., "S&P 500 Index", "Company Common Stock"
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
        data.update({
            "notional_amount": self.notional_amount,
            "currency": self.currency,
            "hedged_item": self.hedged_item.to_dict() if self.hedged_item else None,
        })
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
    counterparty_details: str = "major financial institutions" # e.g., "major financial institutions"


@dataclass
class CategorySpecificPolicy:
    """Describes policies for a specific category of derivatives (e.g., IR, FX)."""
    category: Literal["IR", "FX", "CP", "EQ", "GEN"]
    effectiveness_testing_method: Optional[str] = None # e.g., "dollar-offset method"
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
# PHASE 1 PART 2: SCENARIO GENERATION
# This section implements the core idea: "Decide the story upfront."
# We define the state of our financial narrative using structured dataclasses.
# =============================================================================

def create_random_scenario() -> GenerationScenario:
    """
    This function will create a random, complex scenario based on the rules
    we've defined. For now, it's a placeholder for the logic that decides
    what kind of story to tell (e.g., a company with 2 active IR swaps and 1 terminated FX forward).
    """
    # TODO: Implement the logic to generate diverse and complex scenarios.
    # For now, let's hardcode the complex example from our TODO.md.
    
    reporting_year = random.randint(2022, 2024)
    reporting_month = random.choice(months)
    scenario = GenerationScenario(
        company_name=random.choice(company_names),
        reporting_year=reporting_year,
        instruments=[],
        policy=RiskManagementPolicy(
            general_policy=GeneralHedgingPolicy(
                does_not_use_for_trading=True,
                counterparty_credit_risk_monitored=True
            ),
            category_policies=[
                CategorySpecificPolicy(
                    category="IR",
                    effectiveness_testing_method="regression analysis",
                    effectiveness_frequency="quarterly",
                    accounting_policy_description="For derivatives designated as cash flow hedges, the effective portion of the change in fair value is recorded in other comprehensive income (OCI)."
                )
            ]
        )
    )
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
    all_sentences.append(f"The company is exposed to market risks, primarily from changes in interest rates and foreign currency exchange rates.")

    # 2. Policy and Strategy
    if scenario.policy and scenario.policy.general_policy.does_not_use_for_trading:
        all_sentences.append("Our risk management strategy involves the use of derivative instruments to mitigate these exposures.")
        all_sentences.append("We do not enter into derivative contracts for trading or speculative purposes.")
    if scenario.policy and scenario.policy.general_policy.counterparty_credit_risk_monitored:
        all_sentences.append(f"Counterparty credit risk is managed by transacting with {scenario.policy.general_policy.counterparty_details}.")

    # 3. Specific Instrument Disclosure (The Core)
    # TODO: This is where the main logic will go. We'll loop through `scenario.instruments`
    # and use templates to describe each one.
    # This will be a much more involved step.
    all_sentences.append(f"As of December 31, {scenario.reporting_year}, the total notional of our outstanding interest rate swaps was $250.0 million.")
    all_sentences.append(f"During the first quarter of {scenario.reporting_year}, our portfolio of foreign currency forward contracts with a notional value of €25.0 million matured and were settled.")
    all_sentences.append(f"Subsequently, we entered into a series of foreign currency collar contracts with a total notional value of £40.0 million, which were outstanding at year-end.")
    all_sentences.append(f"The Company also has an embedded derivative liability related to its convertible senior notes, with a fair value of $12.5 million as of December 31, {scenario.reporting_year}.")

    # 4. Effectiveness and Accounting (if applicable)
    if scenario.policy and scenario.policy.category_policies:
        for cat_policy in scenario.policy.category_policies:
            if cat_policy.effectiveness_testing_method:
                all_sentences.append(f"For our {cat_policy.category} derivative instruments, we assess hedge effectiveness on a {cat_policy.effectiveness_frequency} basis using the {cat_policy.effectiveness_testing_method}.")


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
