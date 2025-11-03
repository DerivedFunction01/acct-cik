from dataclasses import dataclass, field
import random
from typing import List, Literal, Optional, Tuple

from defs.function_definitions import _get_company_reference

from defs.common_data import *
from defs.template_definitions import *
from defs.cp_data import get_cost_types_for_commodity
from defs.fx_data import all_currencies
from defs.instrument_definitions import BaseNarrativeEvidence, DerivativeCategory, SpecificDetails
from defs.function_definitions import _cleanup_sentence


@dataclass
class PolicyEvidence(BaseNarrativeEvidence):
    """Evidence related to a company's hedging policies or risk exposure."""

    details: str = ""  # The core statement of the policy or risk.
    policy_type: Literal[
        "risk_exposure",
        "hedging_strategy",
        "effectiveness_testing",
        "accounting_treatment",
    ] = "risk_exposure"

    def to_string(self) -> str:
        """Generates a reasoning statement for the policy evidence."""
        return (
            ""  # This evidence is contextual and does not need to be in the chain of thought.
        )


@dataclass
class GeneralHedgingPolicy:
    """Describes the company's high-level, non-instrument-specific hedging policies."""

    does_not_use_for_trading: bool = True
    counterparty_credit_risk_monitored: bool = True
    counterparty_details: str = (
        "major financial institutions"  # e.g., "major financial institutions"
    )


@dataclass
class PolicySentence:
    """A data class to hold components for generating a policy or risk context sentence."""

    category: DerivativeCategory
    company_name: str

    # Add specific_details for consistency with NotionalSentence
    specific_details: Optional["SpecificDetails"] = None

    def build(self) -> Tuple[str, PolicyEvidence]:
        """Builds a policy sentence and a corresponding PolicyEvidence object."""
        templates = POLICY_CONTEXT_TEMPLATES.get(
            self.category, POLICY_CONTEXT_TEMPLATES["GEN"]
        )
        template = random.choice(templates)
        details = self.specific_details or SpecificDetails()

        # Populate placeholders
        # TODO: Replace hardcoded fallback strings like "various foreign currencies" with more dynamic generation.
        # Format currencies and locations into human-readable strings
        currencies_str = "various foreign currencies"  # Fallback
        if details.currencies:
            currencies_str = (
                ", ".join(details.currencies[:-1]) + " and " + details.currencies[-1]
                if len(details.currencies) > 1
                else details.currencies[0]
            )

        # --- NEW: Handle multiple commodities ---
        commodities_str = "various commodities"
        if details.commodity:
            if len(details.commodity) > 1:
                commodities_str = (
                    ", ".join(details.commodity[:-1]) + f" and {details.commodity[-1]}"
                )
            else:
                commodities_str = details.commodity[0]
        locations_str = f"international {random.choice(geo_locations)}"
        if details.geography:
            locations_str = (
                ", ".join(details.geography[:-1]) + " and " + details.geography[-1]
                if len(details.geography) > 1
                else details.geography[0]
            )
        risk_terms = random.sample(risk_exposure_terms, k=2)
        sentence = template.format(
            company=_get_company_reference(self.company_name),
            ir_term=random.choice(interest_rate_terms),
            debt_type=details.debt_type or "debt",
            risk_term=risk_terms[0],
            risk_term2=risk_terms[1],
            policy_verb=random.choice(policy_verbs),
            risk_action_verb=random.choice(risk_management_verbs),  # type: ignore
            currencies=currencies_str,
            geography=locations_str,
            commodity=commodities_str,
            cost_type=random.choice(
                get_cost_types_for_commodity(
                    random.choice(details.commodity) if details.commodity else None
                )
            ),
        )

        # Create evidence object
        evidence = PolicyEvidence(
            category=self.category,
            status="policy_mention",
            policy_type="risk_exposure",
            details=sentence,
        )

        return sentence, evidence


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
            "documentation": (
                general_hedge_documentation_templates,
                specific_hedge_documentation_templates,
                "hedging_strategy",
                "documentation_formalized",
            ),
            "effectiveness": (
                general_hedge_effectiveness_templates,
                specific_hedge_effectiveness_templates,
                "effectiveness_testing",
                "effectiveness_testing_method",
            ),
            "accounting": (
                hedge_accounting_policy_templates,
                hedge_accounting_policy_templates,
                "accounting_treatment",
                "accounting_policy_description",
            ),  # No specific/general split for this one
        }

        # Choose a random template from each relevant policy category
        templates_to_use: List[Tuple[List[str], str]] = []
        for policy_name, (
            general_list,
            specific_list,
            evidence_type,
            attr_name,
        ) in policy_map.items():
            if (
                getattr(self.cat_policy, attr_name, None)
                and policy_name not in self.already_mentioned_policies
            ):
                # --- NEW: Use the flag to decide which template list to use ---
                if self.generate_specifics_only:
                    # Filter for templates that are actually specific
                    template_list = [t for t in specific_list if "{swap_type}" in t]
                    if not template_list:  # Fallback if no specific templates exist
                        continue
                else:
                    # Use a mix of general and specific for the first run
                    template_list = general_list + specific_list

                templates_to_use.append((template_list, evidence_type))

        # Add ineffectiveness and discontinuation policies with a certain probability
        # These are less likely to be repeated, but we can suppress them on subsequent runs if needed.
        if not self.generate_specifics_only:
            if "ineffectiveness" not in self.already_mentioned_policies and random.random() < 0.4:
                templates_to_use.append(
                    (hedge_ineffectiveness_policy_templates, "accounting_treatment")
                )
            if "discontinuation" not in self.already_mentioned_policies and random.random() < 0.3:
                templates_to_use.append(
                    (hedge_discontinuation_templates, "accounting_treatment")
                )

        # Populate the chosen templates
        for template_list, evidence_type in templates_to_use:
            template = random.choice(template_list)
            sentence = template.format(
                company=_get_company_reference(self.company_name),
                swap_type=self.swap_type_override or "derivative instruments",
                hedge_type=random.choice(hedge_types),
                verb=random.choice(assessment_verbs),
                metric=random.choice(hedge_metrics),
                frequency=self.cat_policy.effectiveness_frequency
                or random.choice(frequencies),
                method=self.cat_policy.effectiveness_testing_method,
                standard=self.cat_policy.accounting_standard
                or random.choice(hedge_standards),
                gain_loss=random.choice(gain_loss_phrases),
                financial_outcome_verb=random.choice(financial_outcome_verbs),
                termination_verb=random.choice(termination_verbs_past),
                # --- NEW: Populate factored-out placeholders ---
                hedge_accounting_subject=random.choice(hedge_accounting_subjects),
                hedged_item_subject=random.choice(hedged_item_subjects),
                deferred_gain_loss_subject=random.choice(
                    deferred_gain_loss_subjects
                ).format(gain_loss=random.choice(gain_loss_phrases)),
            )

            evidence = PolicyEvidence(
                category=self.cat_policy.category,
                status="policy_mention",
                policy_type=evidence_type, # type: ignore
                details=sentence,
            )  # type: ignore
            sentences_and_evidence.append((sentence, evidence))

        return sentences_and_evidence


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
    """Contains all policy-related information for The report."""

    general_policy: GeneralHedgingPolicy = field(default_factory=GeneralHedgingPolicy)
    category_policies: List[CategorySpecificPolicy] = field(default_factory=list)


@dataclass
class MitigationEvidence(BaseNarrativeEvidence):
    """Evidence related to the purpose or strategy of hedging."""

    details: str = ""  # The core statement of the mitigation.
    usage_status: Optional[str] = None  # e.g., "current", "speculative", "non_use"
    verb: Optional[str] = (
        None  # The verb used (e.g., "uses", "may use", "does not use")
    )
    adverb: Optional[str] = (
        None  # The adverb used (e.g., "currently", "from time to time")
    )
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
        instrument_desc = (
            f"'{self.instrument_type}'" if self.instrument_type else "derivatives"
        )

        # --- NEW: Add a classification note for generic categories ---
        classification_note = ""
        if self.category in (None, "GEN"):
            classification_note = (
                "The disclosure does not specify a clear derivative category (e.g., interest rate, "
                "foreign exchange), so this is being treated as a generic reference. "
                "I will look for more context to classify it later."
            )

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
            "historical": "likely use",
            "speculative": "likely use",
        }.get(
            self.usage_status, f"an '{self.usage_status}' usage status" # type: ignore
        )  # type: ignore

        base_sentence = f"{linguistic_cue} for {instrument_desc} suggests {status_description} for {category_name} derivatives."

        return " ".join(filter(None, [base_sentence, classification_note]))


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
        effective_status = (
            "speculative" if final_usage_status == "historical" else final_usage_status
        )
        adverb = ""
        verb = ""
        adverb_list = time_adverbs.get(effective_status, [])
        if adverb_list:
            adverb = random.choice(adverb_list)

        if final_usage_status == "current":
            verb = random.choice(policy_verbs)  # e.g., "uses", "employs"
        elif effective_status == "speculative":
            verb = random.choice(
                non_use_verbs
            )  # e.g., "may use", "may employ", "may enter into"
        elif final_usage_status == "non_use":
            verb = random.choice(non_use_verbs)  # e.g., "does not use"
        else:  # historical or other speculative cases
            verb = random.choice(
                individual_use_verbs + aggregate_use_verbs
            )  # e.g., "used", "employed"

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
                commodities_str = (
                    ", ".join(details.commodity[:-1]) + f" and {details.commodity[-1]}"
                )
            else:
                commodities_str = details.commodity[0]

        # Populate placeholders in the chosen mitigation phrase
        interest_rates = random.sample(specific_rate_terms, k=2)
        risk_terms = random.sample(risk_exposure_terms, k=2)
        populated_phrase = mitigation_phrase.format(
            debt_type=details.debt_type or "debt",
            currencies=currencies_str,
            geography=details.geography
            or random.choice([c.location for c in all_currencies]),
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
            sentence_structures = [
                f"{{company}} {{adverb}} {{verb}} {{swap_type}} {time_suffix}, {populated_phrase}."
            ]
        else:
            # Or: "{mitigation_phrase}, {company} {verb} {swap_type}."
            sentence_structures = [  # type: ignore
                f"{{company}} {{adverb}} {{verb}} {{swap_type}} {time_suffix}, {populated_phrase}.",
                f"{populated_phrase.capitalize()}, {{company}} {{adverb}} {{verb}} {{swap_type}} {time_suffix}.",
            ]
        sentence_template = random.choice(sentence_structures)
        sentence = sentence_template.format(
            company=_get_company_reference(self.company_name),
            adverb=adverb,
            verb=verb,
            swap_type=self.swap_type,
        )

        # Create evidence object
        evidence = MitigationEvidence(  # type: ignore
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
            instrument_term = random.choice(
                [
                    "financial instruments",
                    "transactions",
                    "financial contracts",
                ]
            )

        sentence = template.format(
            company=_get_company_reference(self.company_name),
            counterparty_details=self.counterparty_details,
            swap_type=instrument_term,
            risk_verb=random.choice(risk_management_verbs),
            policy_verb=random.choice(policy_verbs),
            materiality=random.choice(immaterial),
        )

        return _cleanup_sentence(sentence)
