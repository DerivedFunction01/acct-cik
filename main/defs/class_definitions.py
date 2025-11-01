from dataclasses import dataclass, field
from typing import Callable, Dict, Generic, List, Literal, Optional, Tuple, TypeVar
import random

# Imports moved here for the NotionalSentence.build() method
from defs.common_data import  *
from defs.template_definitions import *

def _get_company_reference(company_name: str, chance: float = 0.6) -> str:
    """Randomly returns either the full company name or a generic placeholder."""
    return company_name if random.random() < chance else "The Company"

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

@dataclass
class SpecificDetails:
    """Holds specific details for populating a result_phrase template."""

    frequency: Optional[str] = None

    # FX specific
    geography: Optional[str] = None
    currencies: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)

    # CP specific
    commodity: List[str] = field(default_factory=list)
    unit: Optional[str] = None

    # IR specific (debt_type is primarily for IR)
    pct: Optional[float] = None
    debt_type: Optional[str] = None


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
        return "" # This evidence is contextual and does not need to be in the chain of thought.

@dataclass
class MitigationEvidence(BaseNarrativeEvidence):
    """Evidence related to the purpose or strategy of hedging."""

    details: str = ""  # The core statement of the mitigation.
    usage_status: Optional[str] = None  # e.g., "current", "speculative", "non_use"
    verb: Optional[str] = None  # The verb used (e.g., "uses", "may use", "does not use")
    adverb: Optional[str] = None # The adverb used (e.g., "currently", "from time to time")
    instrument_type: Optional[str] = None  # the derivative

    def _category_label(self) -> str:
        """Map short category codes to descriptive names."""
        return {
            "IR": "Interest Rate",
            "FX": "Foreign Exchange",
            "CP": "Commodity",
            "EQ": "Equity",
            "GEN": "Generic",
        }.get(self.category, "Unknown Category")

    def to_string(self) -> str:
        """Generates a reasoning statement for the mitigation evidence."""
        # --- NEW: More analytical reasoning statement ---
        category_name = self._category_label()
        instrument_desc = f"'{self.instrument_type}'" if self.instrument_type else "derivatives"
        
        # --- NEW: Add a classification note for generic categories ---
        classification_note = ""
        if self.category in (None, "GEN"):
            classification_note = ("The disclosure does not specify a clear derivative category (e.g., interest rate, "
                                   "foreign exchange), so this is being treated as a generic reference. "
                                   "I will look for more context to classify it later.")

        # Build the linguistic cue description
        linguistic_cue = ""
        if self.adverb and self.verb:
            linguistic_cue = f"The use of the phrase '{self.adverb} {self.verb}'"
        elif self.verb:
            linguistic_cue = f"The use of the verb '{self.verb}'"

        if self.usage_status == "non_use":
            return f"A statement of non-use was found for {category_name} derivatives. {linguistic_cue} in relation to {instrument_desc} indicates the company does not engage in this type of hedging.{classification_note}"

        # --- FIX: Use more natural language for speculative status ---
        status_description = {
            "current": "a 'current' usage status",
            "historical": "a 'historical' usage status",
            "speculative": "likely future use",
        }.get(self.usage_status, f"an '{self.usage_status}' usage status") # type: ignore

        base_sentence = f"{linguistic_cue} for {instrument_desc} suggests {status_description} for {category_name} derivatives."
        
        return " ".join(filter(None, [base_sentence, classification_note]))


@dataclass
class PolicySentence:
    """A data class to hold components for generating a policy or risk context sentence."""
    category: DerivativeCategory
    company_name: str

    # Add specific_details for consistency with NotionalSentence
    specific_details: Optional["SpecificDetails"] = None

    def build(self) -> Tuple[str, PolicyEvidence]:
        """Builds a policy sentence and a corresponding PolicyEvidence object."""
        templates = POLICY_CONTEXT_TEMPLATES.get(self.category, POLICY_CONTEXT_TEMPLATES["GEN"])
        template = random.choice(templates)
        details = self.specific_details or SpecificDetails()

        # Populate placeholders
        # TODO: Replace hardcoded fallback strings like "various foreign currencies" with more dynamic generation.
        # Format currencies and locations into human-readable strings
        currencies_str = "various foreign currencies" # Fallback
        if details.currencies:
            currencies_str = ", ".join(details.currencies[:-1]) + " and " + details.currencies[-1] if len(details.currencies) > 1 else details.currencies[0]

        # --- NEW: Handle multiple commodities ---
        commodities_str = "various commodities"
        if details.commodity:
            if len(details.commodity) > 1:
                commodities_str = ", ".join(details.commodity[:-1]) + f" and {details.commodity[-1]}"
            else:
                commodities_str = details.commodity[0]
        # TODO: Replace hardcoded fallback strings like f"international {random.choice(geo_locations)}" with more dynamic generation.
        locations_str = f"international {random.choice(geo_locations)}"
        if details.locations:
            locations_str = (
                ", ".join(details.locations[:-1]) + " and " + details.locations[-1]
                if len(details.locations) > 1
                else details.locations[0]
            )
        risk_terms = random.sample(risk_exposure_terms, k=2)
        sentence = template.format(
            # TODO: These random.choice() calls are selecting from dummy data lists. This logic will be replaced by the generative model.
            company=_get_company_reference(self.company_name),
            ir_term=random.choice(interest_rate_terms),
            debt_type=details.debt_type or "debt",
            risk_term=risk_terms[0],
            risk_term2=risk_terms[1],
            policy_verb=random.choice(policy_verbs),
            risk_action_verb=random.choice(risk_management_verbs),  # type: ignore
            currencies=currencies_str,
            locations=locations_str,
            commodity=commodities_str,
            cost_type=random.choice(get_cost_types_for_commodity(random.choice(details.commodity) if details.commodity else None)),
        )

        # Create evidence object
        evidence = PolicyEvidence(category=self.category, status="policy_mention", policy_type="risk_exposure", details=sentence)

        return sentence, evidence

@dataclass
class MitigationSentence:
    """A data class to hold components for generating a sentence about hedging mitigation/purpose."""
    category: DerivativeCategory
    company_name: str
    swap_type: str
    has_active_instruments: bool
    usage_status: Literal["current", "speculative", "historical", "non_use"]
    specific_details: Optional["SpecificDetails"] = None
    # Add time components for context
    year: Optional[int] = None
    month: Optional[str] = None
    end_day: Optional[int] = None

    def build(self) -> Tuple[str, MitigationEvidence]:
        """Builds a sentence describing the purpose of a hedge. Returns the sentence and a MitigationEvidence object."""
        # Select the appropriate set of mitigation phrases
        templates = MITIGATION_TEMPLATES.get(self.category, MITIGATION_TEMPLATES["GEN"])
        mitigation_phrase = random.choice(templates)

        # --- FIX: Prevent contradiction. If there are active instruments, status cannot be 'non_use'. ---
        final_usage_status = self.usage_status
        if self.has_active_instruments and self.usage_status == "non_use":
            final_usage_status = "current"

        # --- NEW: Treat 'historical' like 'speculative' to imply potential future use. ---
        # Choose an adverb and verb based on the usage status.
        effective_status = "speculative" if final_usage_status == "historical" else final_usage_status
        adverb = ""
        verb = ""
        adverb_list = time_adverbs.get(effective_status, [])
        if adverb_list:
            adverb = random.choice(adverb_list)

        if final_usage_status == "current":
            verb = random.choice(policy_verbs) # e.g., "uses", "employs"
        elif effective_status == "speculative":
            verb = random.choice(non_use_verbs) # e.g., "may use", "may employ", "may enter into"
        elif final_usage_status == "non_use":
            verb = random.choice(non_use_verbs) # e.g., "does not use"
        else: # historical or other speculative cases
            verb = random.choice(individual_use_verbs + aggregate_use_verbs) # e.g., "used", "employed"

        # Format currencies and other details from the specific_details object
        details = self.specific_details or SpecificDetails()
        currencies_str = ""
        if details.currencies:
            currencies_str = (
                ", ".join(details.currencies[:-1]) + " and " + details.currencies[-1]
                if len(details.currencies) > 1
                else details.currencies[0]
            )

        # --- NEW: Handle multiple commodities ---
        commodities_str = "commodities"
        if details.commodity:
            if len(details.commodity) > 1:
                commodities_str = ", ".join(details.commodity[:-1]) + f" and {details.commodity[-1]}"
            else:
                commodities_str = details.commodity[0]

        # Populate placeholders in the chosen mitigation phrase
        interest_rates = random.sample(specific_rate_terms, k=2)
        risk_terms = random.sample(risk_exposure_terms, k=2)
        populated_phrase = mitigation_phrase.format(
            debt_type=details.debt_type or "debt",
            currencies=currencies_str,
            geography=details.geography or random.choice([c.location for c in all_currencies]),
            commodity=commodities_str,
            rate_term1=interest_rates[0],
            rate_term2=interest_rates[1],
            risk_action_verb=random.choice(risk_management_verbs),  # type: ignore
            ir_term=random.choice(interest_rate_terms),
            risk_term=risk_terms[0],
            risk_term2=risk_terms[1],
        )

        # Add time context suffix
        time_suffix = ""
        if self.year and self.month and self.end_day and random.random() < 0.5:
            time_suffix = f"as of {self.month} {self.end_day}, {self.year}"

        # Combine into a final sentence
        # Structure: "{Company} {verb} {swap_type}, {mitigation_phrase}."
        # --- FIX: For non_use, always use the company-first structure for better flow. ---
        if final_usage_status == "non_use":
            sentence_structures = [f"{{company}} {{adverb}} {{verb}} {{swap_type}} {time_suffix}, {populated_phrase}."]
        else:
            # Or: "{mitigation_phrase}, {company} {verb} {swap_type}."
            sentence_structures = [ # type: ignore
                f"{{company}} {{adverb}} {{verb}} {{swap_type}} {time_suffix}, {populated_phrase}.",
                f"{populated_phrase.capitalize()}, {{company}} {{adverb}} {{verb}} {{swap_type}} {time_suffix}."
            ]
        sentence_template = random.choice(sentence_structures)
        sentence = sentence_template.format(company=self.company_name, adverb=adverb, verb=verb, swap_type=self.swap_type)

        # Create evidence object
        evidence = MitigationEvidence( # type: ignore
            category=self.category,
            status="mitigation_purpose",
            usage_status=final_usage_status,
            details=populated_phrase,
            verb=verb,
            adverb=adverb,
            instrument_type=self.swap_type,
        )

        return _cleanup_sentence(sentence), evidence

@dataclass
class CounterpartyRiskSentence:
    """A data class to hold components for generating a counterparty risk sentence."""
    company_name: str
    counterparty_details: str
    has_active_derivatives: bool

    def build(self) -> str:
        """Builds a counterparty risk sentence. No evidence is generated as this is a general policy statement."""
        template = random.choice(hedge_counterparty_templates)

        # If the company has no active derivatives, use a more generic term.
        # This prevents the policy from incorrectly implying derivative use.
        if self.has_active_derivatives:
            instrument_term = "derivatives"
        else:
            instrument_term = random.choice([
                "financial instruments",
                "transactions",
                "financial contracts",
            ])

        sentence = template.format(
            company=_get_company_reference(self.company_name),
            counterparty_details=self.counterparty_details,
            swap_type=instrument_term,
            risk_verb=random.choice(risk_management_verbs),
            policy_verb=random.choice(policy_verbs),
            materiality=random.choice(immaterial),
        )

        return _cleanup_sentence(sentence)

@dataclass
class AccountingPolicySentence:
    """
    A data class to hold components for generating sentences about accounting policies,
    effectiveness testing, and documentation for a specific derivative category.
    """
    cat_policy: "CategorySpecificPolicy"
    company_name: str
    swap_type_override: Optional[str] = None
    generate_specifics_only: bool = False
    already_mentioned_policies: set[str] = field(default_factory=set)

    def build(self) -> List[Tuple[str, "PolicyEvidence"]]:
        """
        Builds a list of sentences and corresponding evidence objects based on the policy.
        """
        sentences_and_evidence = []

        # Define a mapping from policy attributes to templates and evidence types
        policy_map = {
            "documentation": (general_hedge_documentation_templates, specific_hedge_documentation_templates, "hedging_strategy", "documentation_formalized"),
            "effectiveness": (general_hedge_effectiveness_templates, specific_hedge_effectiveness_templates, "effectiveness_testing", "effectiveness_testing_method"),
            "accounting": (hedge_accounting_policy_templates, hedge_accounting_policy_templates, "accounting_treatment", "accounting_policy_description"), # No specific/general split for this one
        }

        # Choose a random template from each relevant policy category
        templates_to_use: List[Tuple[List[str], str]] = []
        for policy_name, (general_list, specific_list, evidence_type, attr_name) in policy_map.items():
            if getattr(self.cat_policy, attr_name, None) and policy_name not in self.already_mentioned_policies:
                # --- NEW: Use the flag to decide which template list to use ---
                if self.generate_specifics_only:
                    # Filter for templates that are actually specific
                    template_list = [t for t in specific_list if '{swap_type}' in t]
                    if not template_list: # Fallback if no specific templates exist
                        continue
                else:
                    # Use a mix of general and specific for the first run
                    template_list = general_list + specific_list

                templates_to_use.append((template_list, evidence_type))

        # Add ineffectiveness and discontinuation policies with a certain probability
        # These are less likely to be repeated, but we can suppress them on subsequent runs if needed.
        if not self.generate_specifics_only:
            if "ineffectiveness" not in self.already_mentioned_policies and random.random() < 0.4:
                templates_to_use.append((hedge_ineffectiveness_policy_templates, "accounting_treatment"))
            if "discontinuation" not in self.already_mentioned_policies and random.random() < 0.3:
                templates_to_use.append((hedge_discontinuation_templates, "accounting_treatment"))

        # Populate the chosen templates
        for template_list, evidence_type in templates_to_use:
            template = random.choice(template_list)
            sentence = template.format(
                company=_get_company_reference(self.company_name),
                swap_type=self.swap_type_override or "derivative instruments",
                hedge_type=random.choice(hedge_types),
                verb=random.choice(assessment_verbs),
                metric=random.choice(hedge_metrics),
                frequency=self.cat_policy.effectiveness_frequency or random.choice(frequencies),
                method=self.cat_policy.effectiveness_testing_method,
                standard=self.cat_policy.accounting_standard or random.choice(hedge_standards),
                gain_loss=random.choice(gain_loss_phrases),
                financial_outcome_verb=random.choice(financial_outcome_verbs),
                termination_verb=random.choice(termination_verbs_past),
                # --- NEW: Populate factored-out placeholders ---
                hedge_accounting_subject=random.choice(hedge_accounting_subjects),
                hedged_item_subject=random.choice(hedged_item_subjects),
                deferred_gain_loss_subject=random.choice(deferred_gain_loss_subjects).format(gain_loss=random.choice(gain_loss_phrases)),
            )
            
            evidence = PolicyEvidence(category=self.cat_policy.category, status="policy_mention", policy_type=evidence_type, details=sentence) # type: ignore
            sentences_and_evidence.append((sentence, evidence))

        return sentences_and_evidence

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
    suffix: str
    category: DerivativeCategory
    start_month: str
    start_year: int
    maturity_month: Optional[str] = None
    hedge_designation: Optional[str] = None
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
        equity_type: Literal["market_index", "own_stock", "third_party_stock"] - The type of equity.
        number_of_shares: Optional[int] - The number of shares being hedged.
        share_price: Optional[float] - The share price at a point in time.
        stock_symbol: Optional[str] - The stock ticker symbol.
    """
    equity_type: Literal["market_index", "own_stock", "third_party_stock"]
    number_of_shares: Optional[int] = None
    share_price: Optional[float] = None
    stock_symbol: Optional[str] = None


@dataclass
class NotionalInstrument(DerivativeInstrument, Generic[T_HedgedItem]):
    """A derivative instrument primarily defined by a notional amount.

    Args:
        notional_amount: int - The notional amount of the instrument.
        currency: str - The currency of the instrument.
        hedged_item: Optional[T_HedgedItem] - The item being hedged by this instrument.
    """

    notional_history: Dict[int, int] = field(default_factory=dict)  # {year: notional_amount}
    currency: str = "USD"
    hedged_item: Optional[T_HedgedItem] = None

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
