from dataclasses import dataclass, field
import random
from typing import Dict, List, Literal, Optional, Tuple

from defs.function_definitions import _get_company_reference

from defs.common_data import *
from defs.template_definitions import (
    POLICY_CONTEXT_TEMPLATES,
    MITIGATION_TEMPLATES,
    general_hedge_documentation_templates,
    specific_hedge_documentation_templates,
    general_hedge_effectiveness_templates,
    specific_hedge_effectiveness_templates,
    hedge_accounting_policy_templates,
    hedge_ineffectiveness_policy_templates,
    hedge_discontinuation_templates,
    hedge_accounting_subjects,
    hedged_item_subjects,
    deferred_gain_loss_subjects,
    hedge_types,
    hedge_methods,
    hedge_standards,
    hedge_counterparty_templates,
    hedge_no_trading_templates,
    hedge_change_policy_templates,
    hedge_additional_definition_templates,
    general_policy_templates,
    shared_effective_date_templates,
    shared_adoption_status_templates,
    shared_adoption_impact_templates,
    shared_transition_templates,
    shared_disclosure_change_templates,
    shared_practical_expedient_templates,
    shared_evaluation_templates,
    shared_adoption_methods,
    shared_transition_features,
    shared_purposes,
    general_descriptions,
    general_additional_features,
    hedging_descriptions,
    hedging_additional_features,
    shared_standards_templates,
    other_topics,
    other_standards,
    hedge_definition_templates,
)
from defs.instrument_definitions import AccountingStandardEvidence
from defs.cp_data import get_cost_types_for_commodity
from defs.fx_data import all_currencies
from defs.instrument_definitions import BaseNarrativeEvidence, DerivativeCategory, SpecificDetails
from defs.function_definitions import _cleanup_sentence


@dataclass
class ExposureEvidence(BaseNarrativeEvidence):
    """Evidence that a company has exposure to a certain market risk, even if not hedged."""

    details: str = ""  # The sentence describing the exposure.

    def to_string(self) -> str:
        """Generates a reasoning statement for the exposure evidence."""
        exposure_type_map = {
            "IR": "debt obligations or other interest-rate sensitive items",
            "FX": "foreign currency transactions or international operations",
            "CP": "commodity price fluctuations",
            "EQ": "equity price changes or stock-based activities",
            "GEN": "general market risks",
        }
        exposure_description = exposure_type_map.get(
            self.category, "an unknown risk category"
        )
        # Return a concise statement for the chain of thought.
        # This now returns just the description, to be combined later.
        return exposure_description


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
            risk_action_verb=random.choice(risk_management_verbs_no_ing),  # type: ignore
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
                "effectiveness_testing", # type: ignore
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
            sentences_and_evidence.append((_cleanup_sentence(sentence), evidence))

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
    is_hedge_related: bool = False
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
    is_implied: bool = False  # NEW: Flag to indicate if the evidence is from a dropped sentence

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
        # --- FIX: Handle implied evidence from dropped sentences ---
        if self.is_implied:
            if self.usage_status == "current":
                return f"The presence of active {self._category_label()} derivatives implies a 'current' usage status."
            elif self.usage_status == "historical":
                return f"The presence of only terminated {self._category_label()} derivatives implies a 'historical' usage status."
            # For 'non_use' or 'speculative', if the sentence is dropped, there's no evidence to generate.
            return ""

        # --- FIX: More analytical reasoning statement ---
        category_name = self._category_label()
        instrument_desc = (
            f"'{self.instrument_type}'" if self.instrument_type else "derivatives"
        )

        # Build the linguistic cue description
        linguistic_cue = ""
        if self.adverb and self.verb:
            linguistic_cue = f"The use of the phrase '{self.adverb} {self.verb}'" # type: ignore
        elif self.verb:
            linguistic_cue = f"The use of the verb '{self.verb}'"

        if self.usage_status == "non_use":
            base_sentence = f"{linguistic_cue} in relation to {instrument_desc} indicates the company does not engage in this type of hedging for {category_name} risk."
            return base_sentence

        # --- FIX: Use more natural language for speculative/historical status ---
        status_description = {
            "current": "a 'current' usage status",
            "historical": "likely use",
            "speculative": "likely use",
        }.get(
            self.usage_status, f"an '{self.usage_status}' usage status" # type: ignore
        )  # type: ignore

        base_sentence = f"{linguistic_cue} for {instrument_desc} suggests {status_description} for {category_name} risk."

        return base_sentence.strip()


@dataclass
class MitigationSentence:
    """A data class to hold components for generating a sentence about hedging mitigation/purpose."""

    category: DerivativeCategory
    company_name: str
    swap_type: str
    has_active_instruments: bool
    usage_status: Literal["current", "speculative", "historical", "non_use"]
    is_active_user: bool = False # NEW: Flag to allow more flexible adverb use
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

        # --- FIX: Treat 'historical' like 'speculative' to imply potential future use. ---
        # Choose an adverb and verb based on the usage status.
        effective_status = (
            "speculative" if final_usage_status == "historical" else final_usage_status
        )
        adverb = ""
        verb = ""
        special_current = False
        # --- NEW: Allow active users to sometimes use speculative adverbs like "periodically" ---
        # This makes the language more realistic, as firms describe ongoing programs.
        if final_usage_status == "current" and random.random() < 0.3: # 30% chance
            special_current = True
            # If an active user, sometimes use adverbs from the 'speculative' list
            adverb_list = time_adverbs.get("speculative", [])
            if adverb_list:
                adverb_list.remove("in the future") if "in the future" in adverb_list else None
                adverb = random.choice(adverb_list)
        else:
            # Original logic for all other cases
            adverb_list = time_adverbs.get(effective_status, [])
            if adverb_list:
                adverb = random.choice(adverb_list)

        # --- Original verb selection logic ---
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
        locations_str = f"various {random.choice(geo_locations)}"
        if details.geography:
            locations_str = (
                ", ".join(details.geography[:-1]) + " and " + details.geography[-1]
                if len(details.geography) > 1
                else details.geography[0]
            )
        # Populate placeholders in the chosen mitigation phrase
        interest_rates = random.sample(specific_rate_terms, k=2)
        risk_terms = random.sample(risk_exposure_terms, k=2)
        populated_phrase = mitigation_phrase.format(
            debt_type=details.debt_type or "debt",
            currencies=currencies_str,
            geography=locations_str,
            commodity=commodities_str,
            rate_term1=interest_rates[0],
            rate_term2=interest_rates[1],
            risk_action_verb=random.choice(risk_management_verbs_no_ing),  # type: ignore
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
                f"{{company}} {{combined_verb}} {{swap_type}} {time_suffix}, {populated_phrase}."
            ]
        else:
            # Or: "{mitigation_phrase}, {company} {verb} {swap_type}."
            sentence_structures = [  # type: ignore
                f"{{company}} {{combined_verb}} {{swap_type}} {time_suffix}, {populated_phrase}.",
                f"{{adverb_front}} {{company}} {verb} {{swap_type}} {time_suffix}, {populated_phrase}.",
                f"{_cleanup_sentence(populated_phrase)}, {{company}} {{combined_verb}} {{swap_type}} {time_suffix}.",
            ]
        combined_verb = ""
        # --- FIX: Track modified adverb and verb for evidence consistency ---
        final_adverb = adverb
        final_verb = verb

        if final_usage_status == "non_use":
            combined_verb = f"{adverb} {verb}"
        elif final_usage_status == "speculative" or special_current:
            if adverb == "may":
                combined_verb = f"{adverb} {verb}"
                final_adverb, final_verb = adverb, verb
            else:
                roll = random.random()
                if roll < 0.35:
                    combined_verb = f"{adverb} may {verb}"
                    final_adverb, final_verb = f"{adverb} may", verb
                elif roll < 0.85:
                    combined_verb = f"may {adverb} {verb}"
                    final_adverb, final_verb = f"may {adverb}", verb
                else:
                    combined_verb = f"{adverb} {verb}"
                    final_adverb, final_verb = adverb, verb
        else:
            combined_verb = f"{adverb} {verb}"
            final_adverb, final_verb = adverb, verb

        sentence_template = random.choice(sentence_structures)
        sentence = sentence_template.format(
            company=_get_company_reference(self.company_name),
            swap_type=self.swap_type,
            combined_verb=combined_verb,
            adverb_front=adverb + ", " if adverb else "",
        )

        if special_current:
            final_usage_status = "speculative"

        # Create evidence object
        evidence = MitigationEvidence(  # type: ignore
            category=self.category,
            status="mitigation_purpose",
            usage_status=final_usage_status,
            details=populated_phrase,
            verb=final_verb,
            adverb=final_adverb,
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
            suffix = random.choice(DERIVATIVE_COMPONENTS["suffixes"])
            instrument_term = random.choice(
                [
                    f"financial {suffix}",
                    suffix,
                ]
            )

        sentence = template.format(
            company=_get_company_reference(self.company_name),
            counterparty_details=self.counterparty_details,
            swap_type=instrument_term,
            risk_verb=random.choice(risk_management_verbs_no_ing),
            policy_verb=random.choice(policy_verbs),
            materiality=random.choice(immaterial),
        )

        return _cleanup_sentence(sentence)


@dataclass
class AccountingStandardUpdateSentence:
    """Generates a paragraph about the adoption or evaluation of a new accounting standard."""

    company_name: str
    update: "AccountingStandardUpdate"
    year: int
    month: str
    day: int

    def build(self) -> Tuple[str, List[AccountingStandardEvidence]]:
        """Builds a multi-sentence paragraph about the accounting standard update."""
        sentences = []
        evidence_list = []

        # --- 1. ISSUANCE STATEMENT ---
        # Decide if it's a general standard or a hedging-specific one
        is_hedge_specific = self.update.is_hedge_related

        # --- NEW: Use shared_standards_templates with a 30% chance for more variety ---
        if random.random() < 0.3:
            template = random.choice(shared_standards_templates)
            sentence = template.format(
                month=random.choice(months),
                year=self.update.effective_year - random.randint(1, 3) if self.update.effective_year else self.year - 2,
                issuer=self.update.issuer,
                standard=self.update.standard_name,
                topic=self.update.topic,
                standard_purpose=random.choice(shared_purposes),
                standard_description=self.update.impact_description,
            )
        else:
            if is_hedge_specific:
                template = random.choice(hedge_change_policy_templates)
                description = random.choice(hedging_descriptions)
                feature = random.choice(hedging_additional_features)
                sentence = template.format(
                    month=random.choice(months),
                    year=self.update.effective_year - random.randint(1, 3) if self.update.effective_year else self.year - 2,
                    issuer=self.update.issuer,
                    standard=self.update.standard_name,
                    topic=self.update.topic,
                    hedge_description=description,
                    hedge_feature=feature,
                    eff_day=random.randint(15, 31),
                )
            else: # General standard
                template = random.choice(general_policy_templates)
                description = random.choice(general_descriptions)
                feature = random.choice(general_additional_features)
                sentence = template.format(
                    month=random.choice(months),
                    year=self.update.effective_year - random.randint(1, 3) if self.update.effective_year else self.year - 2,
                    issuer=self.update.issuer,
                    standard=self.update.standard_name,
                    topic=self.update.topic,
                    standard_purpose=random.choice(shared_purposes),
                    policy_description=description,
                    policy_feature=feature,
                )
        
        evidence_list.append(AccountingStandardEvidence(
            category="GEN",
            status="policy_mention",
            standard_name=self.update.standard_name,
            adoption_status="issuance",
            details=sentence,
        ))
        sentences.append(_cleanup_sentence(sentence))

        # --- 2. EFFECTIVE DATE (Optional) ---
        if self.update.effective_year and random.random() < 0.7:
            template = random.choice(shared_effective_date_templates)
            sentence = template.format(
                month=random.choice(months),
                day=random.randint(1, 28),
                end_day=random.randint(28, 31),
                year=self.update.effective_year,
                company=_get_company_reference(self.company_name),
            )
            sentences.append(_cleanup_sentence(sentence))

        # --- 3. ADOPTION STATUS & IMPACT ---
        if self.update.is_adopted:
            template = random.choice(shared_adoption_status_templates)
            # Ensure we don't pick a "will adopt" or "evaluating" template
            while "will adopt" in template or "evaluating" in template:
                template = random.choice(shared_adoption_status_templates)

            sentence = template.format(
                company=_get_company_reference(self.company_name),
                standard=self.update.standard_name,
                month=random.choice(months),
                day=random.randint(1, 28),
                year=self.update.adoption_year,
                adoption_method=self.update.adoption_method or random.choice(shared_adoption_methods),
            )
            sentences.append(_cleanup_sentence(sentence))
            evidence_list.append(AccountingStandardEvidence(
                category="GEN",
                status="policy_mention",
                standard_name=self.update.standard_name,
                adoption_status="adopted",
                details=sentence,
            ))

            # Add impact sentence
            if self.update.impact_description:
                impact_template = random.choice(shared_adoption_impact_templates)
                impact_sentence = impact_template.format(
                    company=_get_company_reference(self.company_name),
                    adoption_impact=self.update.impact_description,
                )
                sentences.append(_cleanup_sentence(impact_sentence))
        else: # Not yet adopted
            # Choose between "will adopt" and "evaluating"
            if random.random() < 0.6: # "will adopt"
                template = random.choice([s for s in shared_adoption_status_templates if "will adopt" in s])
                sentence = template.format(
                    company=_get_company_reference(self.company_name),
                    year=self.update.effective_year or self.year + 1,
                )
                evidence_list.append(AccountingStandardEvidence(
                    category="GEN",
                    status="policy_mention",
                    standard_name=self.update.standard_name,
                    adoption_status="will_adopt",
                    details=sentence,
                ))
                sentences.append(_cleanup_sentence(sentence))
            else: # "evaluating"
                template = random.choice(shared_evaluation_templates)
                sentence = template.format(company=_get_company_reference(self.company_name))
                evidence_list.append(AccountingStandardEvidence(
                    category="GEN",
                    status="policy_mention",
                    standard_name=self.update.standard_name,
                    adoption_status="evaluating",
                    details=sentence,
                ))
                sentences.append(_cleanup_sentence(sentence))

        # --- 4. OTHER DETAILS (Optional) ---
        if random.random() < 0.25:
            template = random.choice(shared_transition_templates)
            sentence = template.format(
                company=_get_company_reference(self.company_name),
                adoption_method=self.update.adoption_method or random.choice(shared_adoption_methods),
                transition_feature=random.choice(shared_transition_features),
            )
            sentences.append(_cleanup_sentence(sentence))

        if random.random() < 0.25:
            template = random.choice(shared_disclosure_change_templates)
            sentence = template.format(
                disclosure_topic=random.choice(other_topics),
                disclosure_topic2=random.choice(other_topics),
                company=_get_company_reference(self.company_name),
                year=self.update.effective_year or self.year + 1,
            )
            sentences.append(_cleanup_sentence(sentence))

        if random.random() < 0.2:
            template = random.choice(shared_practical_expedient_templates)
            sentence = template.format(
                company=_get_company_reference(self.company_name),
                expedient_description=random.choice(shared_transition_features),
            )
            sentences.append(_cleanup_sentence(sentence))

        return ". ".join(sentences) + ".", evidence_list


@dataclass
class HedgeDefinitionSentence:
    """
    Generates a legalistic definition of a derivative type, often found in
    detailed policy disclosures.
    """

    def build(self) -> str:
        """Builds a sentence defining a derivative type."""
        # Choose a base type to define, like "swap" or "option"
        base_type = random.choice(DERIVATIVE_COMPONENTS["base_types"])
        # Make it plural for the definition title
        swap_type = f"{base_type}s" if not base_type.endswith("s") else base_type
        swap_type.capitalize()
        # Build up a list of definitions
        num_definitions = random.randint(1, 3)
        definitions = []
        for i in range(num_definitions):
            # Create a complex-sounding definition, e.g., "any interest rate, currency, or commodity swap"
            s_types = random.sample(
                ["rate", "basis", "commodity", "currency", "debt", "equity"],
                random.randint(2, 4),
            )
            suffix = random.choice(DERIVATIVE_COMPONENTS["suffixes"])
            definition_item = f"any {', '.join(s_types)} {base_type} {suffix}"
            definitions.append(f"{i+1}) {definition_item}")
        # Add some generic follow-on definitions
        for _ in range(random.randint(1, 2)):
            additional_def = random.choice(hedge_additional_definition_templates)
            definitions.append(additional_def.format(suffix=random.choice(DERIVATIVE_COMPONENTS["suffixes"])))

        template = random.choice(hedge_definition_templates)
        return template.format(swap_type=swap_type, swap_definitions="; ".join(definitions))