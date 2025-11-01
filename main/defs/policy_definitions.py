from dataclasses import dataclass, field
import random
from typing import List, Literal, Optional, Set, Tuple

from defs.class_definitions import (
    BaseNarrativeEvidence,
    CategorySpecificPolicy,
    DerivativeCategory,
    SpecificDetails,
    _get_company_reference,
)
from defs.common_data import *
from defs.template_definitions import *
from defs.commodity_data import get_cost_types_for_commodity


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