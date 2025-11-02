from dataclasses import dataclass, field
import random
from typing import Callable, Dict, List, Literal, Optional, Tuple
from defs.function_definitions import _get_company_reference
from defs.common_data import *
from defs.template_definitions import *
from defs.cp_data import get_random_commodity_and_unit, get_units_for_commodity
from defs.fx_data import all_currencies
from defs.instrument_definitions import NotionalInstrument
from defs.template_definitions import _format_single_notional
from defs.template_definitions import _cleanup_sentence
from defs.instrument_definitions import BaseNarrativeEvidence, DerivativeCategory, SpecificDetails

@dataclass
class NotionalEvidence(BaseNarrativeEvidence):
    """Evidence related to notional or fair value amounts of derivative instruments, with temporal reasoning and validation."""

    aggregate: Optional[bool] = None
    notional: Optional[int] = None
    month: Optional[str] = None
    year: Optional[int] = None
    prev_year: Optional[int] = None
    prev2_year: Optional[int] = None
    instrument_type: Optional[str] = None
    notional_str: Optional[str] = None
    prev_notional_str: Optional[str] = None
    prev2_notional_str: Optional[str] = None
    reporting_year: Optional[int] = None
    maturity_year: Optional[int] = None
    maturity_value: Optional[int] = None
    value_type: str = "notional"
    currency: str = "USD"
    sentence_type: Optional[str] = None
    is_repeated_mention: bool = False

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _category_label(self) -> str:
        """Map short category codes to descriptive names."""
        return {
            "IR": "Interest Rate",
            "FX": "Foreign Exchange",
            "CP": "Commodity",
            "EQ": "Equity",
            "GEN": "Generic",
        }.get(self.category, "Unknown Category")

    def _temporal_reasoning(self) -> str:
        """Generates a concise temporal reasoning string, e.g., '(2023, current maturity)'."""
        if not self.reporting_year or not self.year:
            return ""
        if (
            self.sentence_type
            and self.sentence_type
            in [
                "historical_individual",
                "new_individual",
                "individual",
                "terminated_individual",
                "inception",
                "continuing",
            ]
        ):
            # --- FIX: Restore maturity year to the reasoning for individual instruments. ---
            # This creates a more descriptive reasoning string like "(2020, matures: 2025)".
            if self.maturity_year is not None and self.maturity_year != self.year:
                return f" ({self.year}, matures: {self.maturity_year})"
            else:
                # If maturity is unknown or same as the data year, just show the year.
                return f" ({self.year})"

        # Fallback for aggregate summaries and other cases.
        return f" ({self.year})"

    def _validate_temporal_consistency(self) -> Optional[str]:
        """Detect inconsistent or ambiguous temporal relationships."""
        # If either temporal anchor missing we skip warnings here.
        if not self.reporting_year or not self.year:
            return None

        if self.status == "terminated" and self.year > self.reporting_year:
            return f"[Warning] Terminated instrument dated in the future ({self.year}) after reporting year {self.reporting_year}."
        if self.status == "new" and self.year > self.reporting_year:
            return f"[Warning] 'New' instrument refers to a future year {self.year} beyond reporting year {self.reporting_year}."
        if self.status == "no_instruments" and self.notional and self.notional > 0:
            return f"[Warning] 'No instruments' status conflicts with positive notional value {self.notional}."
        if self.status == "summary" and self.notional is not None and self.notional < 0:
            return f"[Warning] Negative notional value ({self.notional}) is not valid for a summary disclosure."
        return None

    def _get_repetition_reasoning(self, base_desc: str) -> str:
        """Generates the 'aha' moment reasoning for a repeated instrument mention."""
        if not self.is_repeated_mention:
            return ""

        # The instrument_type here is the name used in the sentence (could be full name or alias)
        instrument_name_in_sentence = self.instrument_type or "the instrument"

        # A simple heuristic is to check if the base description contains the used name, but not vice-versa, suggesting an alias.
        if (
            base_desc
            and instrument_name_in_sentence
            and base_desc != instrument_name_in_sentence
            and instrument_name_in_sentence in base_desc
            and len(instrument_name_in_sentence.split()) < len(base_desc.split())
        ):
            reason = (
                f"Wait, the term '{instrument_name_in_sentence}' appears to be an alias for the previously mentioned '{base_desc}'. "
                f"Given the similar context, I'll treat this as another reference to the same instrument."
            )
        else:
            reason = f"Wait, another mention of the same '{base_desc}' has appeared."

        return reason + " "

    # ---------------------------------------------------------------------
    # Core logic
    # ---------------------------------------------------------------------

    def to_string(self) -> str:
        """Generates a reasoning statement with built-in time validation and generic-category handling."""
        # --- NEW: Relocated category handling and classification note logic ---
        category_name = self._category_label()
        category_context = f"{category_name} derivative activity"
        classification_note = ""
        if self.category in (None, "GEN"):
            classification_note = (
                ". Based on the surrounding context, the disclosure does not specify a clear derivative category "
                ", so it is treated as a generic reference "
                "and I'll come back to it later."
            )

        value_desc = (
            "fair value" if self.value_type == "fair_value" else "notional value"
        )

        if self.year is None or self.reporting_year is None:
            temporal_info = ""
        else:
            temporal_info = self._temporal_reasoning()

        warning = self._validate_temporal_consistency()

        # --- NEW: Construct a more descriptive base_desc, including the suffix if available ---
        # The instrument_type could be the full name or an alias.
        base_desc = (
            f"{self.instrument_type}" if self.instrument_type else f"{category_context}"
        )

        # -----------------------------------------------------------------
        # Template-driven status handlers (now consistently include temporal_info)
        # -----------------------------------------------------------------
        def summary_handler() -> str:
            # Summary is always aggregate, so it won't have a specific "aha" moment for an individual instrument.
            # Its logic remains focused on aggregate values. The phrase "An aggregate..." is sufficient.
            value_part = (
                f" of {self.notional_str}"
                if self.notional_str or self.notional is not None
                else " with no value specified"
            )
            return f"An aggregate {value_desc}{value_part} was identified for {base_desc} activity{temporal_info}"

        def new_individual_handler() -> str:
            value_part = (
                f" with a {value_desc} of {self.notional_str}"
                if self.notional_str
                else ""
            )
            return f"A new individual {base_desc} was identified{value_part}{classification_note}{temporal_info}"

        def individual_handler() -> str:
            value_part = (
                f" with a {value_desc} of {self.notional_str}"
                if self.notional_str
                else ""
            )
            return f"An individual {base_desc} was identified{value_part}{classification_note}{temporal_info}"

        def terminated_individual_handler() -> str:
            value_part = (
                f" with a prior {value_desc} of {self.notional_str}"
                if self.notional_str
                else ""
            )
            return f"A terminated {base_desc} was identified{value_part}{temporal_info}"

        def no_instruments_handler() -> str:
            return f"The report explicitly states there were no outstanding {category_name} instruments in {self.reporting_year}, confirming no current use{temporal_info}"

        def comparative_handler() -> str:
            # General comparative uses summary logic
            return summary_handler()

        def comparative_no_outstanding_handler() -> str:
            return (
                f"The report confirms no outstanding {category_context} in {self.reporting_year}, "
                f"compared to a prior {value_desc} of {self.prev_notional_str} in {self.prev_year}, indicating termination of activity{temporal_info}"
            )

        def comparative_no_prior_outstanding_handler() -> str:
            return (
                f"The report shows a current {value_desc} of {self.notional_str} for {category_context} in {self.reporting_year}, "
                f"with no such instruments outstanding in the prior year, indicating new activity{temporal_info}"
            )

        def historical_individual_handler() -> str:
            # Historical individual mention uses the individual wording but relies on temporal_info for history
            return individual_handler()

        def inception_handler() -> str:
            # Inception is a specific type of individual mention.
            # We can reuse the individual handler as it correctly describes the instrument.
            # The temporal reasoning will provide the historical context.
            return individual_handler()

        def timeline_handler() -> str:
            # Custom handler for the consolidated timeline evidence.
            # This creates a single, coherent reasoning statement for an instrument's history.
            return (
                f"A historical timeline for a {base_desc} was identified, "
                f"showing a {value_desc} of {self.prev_notional_str} at inception in {self.prev_year} "
                f"and a value of {self.notional_str} in {self.year}{temporal_info}"
            )

        # Map statuses to handlers
        handlers: Dict[str, Callable[[], str]] = {
            "summary": summary_handler,
            "new_individual": new_individual_handler,
            "individual": individual_handler,
            "terminated_individual": terminated_individual_handler,
            "no_instruments": no_instruments_handler,
            "comparative": comparative_handler,
            "comparative_no_outstanding": comparative_no_outstanding_handler,
            "comparative_no_prior_outstanding": comparative_no_prior_outstanding_handler,
            "historical_individual": historical_individual_handler,
            # Add handlers for timeline sentence types
            "inception": inception_handler,
            "continuing": individual_handler,  # Treat 'continuing' like a standard 'individual' mention
            "timeline": timeline_handler,  # Handler for the consolidated timeline object
        }

        # Dispatch
        text = handlers.get(
            self.status,
            lambda: f"Uncategorized notional evidence found for {category_name}.",
        )()

        # --- NEW: Prepend the "aha" moment reasoning ---
        repetition_reasoning = self._get_repetition_reasoning(base_desc)
        text = repetition_reasoning + text

        # Append warning if present
        if warning:
            text = f"{text} {warning}"

        return " ".join(text.split())  # Clean up any extra spaces


@dataclass
class NotionalSentence:
    """
    A data class that holds all the components required to generate a sentence
    about notional amounts. This structure is passed to a sentence generation function.
    """

    # Core sentence components
    swap_type: str
    year: int
    category: DerivativeCategory
    reporting_year: int
    value_type: Literal["notional", "fair_value"] = "notional"
    sentence_type: Literal[
        "summary",  # phrases stating total amount across all derivative type
        "new_individual",  # phrases with new swap in past or current year
        "individual",  # phrases with any swap in past or current year
        "terminated_individual",  # phrases an individual swap being terminated in past or current year
        "historical_individual",  # phrases with a swap in an old year that expires in past or future year
        "comparative",  # Phrases with comparative values
        "comparative_no_outstanding",  # Phrases with explicit mention of no outstanding for current year, values in past
        "comparative_no_prior_outstanding",  # Phrases with current value for current year, but no other values in prior
        "no_instruments",  # No such derivatives at all
        "inception",
        "continuing",
        "partial_settlement",  # For TimelineSentence
    ] = "summary"

    notional: Optional[int] = None
    currency_symbol: str = "$"
    currency_code: str = "US Dollar"
    # Optional time components
    month: Optional[str] = None
    end_day: Optional[int] = None
    quarter: Optional[str] = None

    # Optional descriptive elements
    company_name: Optional[str] = None
    verb: Optional[str] = None
    maturity_value: Optional[int] = None
    maturity_year: Optional[int] = None
    specific_details: Optional[SpecificDetails] = None
    notional_multiplier: int = 1_000_000
    prefer_abbreviated: bool = True
    is_repeated_mention: bool = False
    optional_chance: float = 0.5

    def __post_init__(self):
        # If comparative_no_outstanding is chosen but there's no prior notional, it's just a 'no_instruments' case.
        if self.sentence_type == "comparative_no_outstanding" and self.notional is None:
            self.sentence_type = "no_instruments"

    def build(self) -> Tuple[str, NotionalEvidence]:
        """
        Builds a notional sentence and a corresponding NotionalEvidence object.
        Returns: A tuple of (sentence_string, NotionalEvidence_instance).
        """

        # Default values for optional components
        month = self.month or random.choice(months)
        end_day = self.end_day or random.randint(28, 31)
        quarter = self.quarter or random.choice(quarters)
        company_name = _get_company_reference(self.company_name or "The Company")

        # Determine number of years for comparison
        # This is now simplified, as we only handle one point in time.
        # Comparative sentences will be built differently.

        # --- NEW: Generate a mitigation phrase for the 'begin_mitigation' placeholder ---
        begin_mitigation = ""
        # Only generate this for templates that actually use it, and only some of the time.
        if random.random() < self.optional_chance:  # 50% chance to add this clause
            mitigation_templates = MITIGATION_TEMPLATES.get(self.category, MITIGATION_TEMPLATES["GEN"])  # type: ignore
            mitigation_phrase_template = random.choice(mitigation_templates)

            # Populate the mitigation phrase with relevant details
            details = self.specific_details or SpecificDetails()
            currencies_str = ""
            if details.currencies:
                currencies_str = (
                    ", ".join(details.currencies[:-1])
                    + " and "
                    + details.currencies[-1]
                    if len(details.currencies) > 1
                    else details.currencies[0]
                )

            # --- FIX: Handle multiple commodities ---
            commodities_str = "various commodities"
            if details.commodity:
                if len(details.commodity) > 1:
                    commodities_str = (
                        ", ".join(details.commodity[:-1])
                        + f" and {details.commodity[-1]}"
                    )
                else:
                    commodities_str = details.commodity[0]

            begin_mitigation = (
                mitigation_phrase_template.format(
                    risk_action_verb=random.choice(
                        [v for v in risk_management_verbs if not v.endswith("ing")]
                    ),
                    ir_term=random.choice(interest_rate_terms),
                    debt_type=details.debt_type or "debt",
                    risk_term=random.choice(risk_exposure_terms),
                    risk_term2=random.choice(risk_exposure_terms),
                    currencies=currencies_str or "various currencies",
                    geography=details.geography or random.choice([c.location for c in all_currencies]),  # type: ignore
                    commodity=commodities_str,
                    rate_term1=random.choice(specific_rate_terms),
                    rate_term2=random.choice(specific_rate_terms),
                ).capitalize()
                + ", "
            )

        # 1. Format amount string
        amount_str = ""
        if self.notional is not None:
            formatted_notional = _format_single_notional(
                self.notional,
                self.currency_symbol,
                self.prefer_abbreviated,
            )
            amount_str = formatted_notional

        # 2. Select time prefix template
        time_prefix = ""
        time_suffix = ""
        if self.sentence_type in [
            "summary",
            "comparative",
            "no_instruments",
            "individual",
        ]:
            # Simplified: Always use single-year prefixes for now.
            # Comparative logic will be handled by specific templates.
            time_prefix = random.choice(point_in_time_prefixes)
        elif self.sentence_type in [
            "new_individual",
            "terminated_individual",
            "historical_individual",
        ]:
            time_prefix = random.choice(period_of_time_prefixes)

        time_prefix = time_prefix.format(
            month=month,
            end_day=end_day,
            year=self.year,
            quarter=quarter,
        )
        time_suffix = f"as of {month} {end_day}, {self.year}"

        # 3. Select verb
        verb = self.verb
        if verb is None:
            if self.sentence_type == "new_individual":
                verb = random.choice(individual_use_verbs)
            elif self.sentence_type == "terminated_individual":
                verb = random.choice(termination_verbs_past)
            else:  # summary, comparative
                verb = random.choice(aggregate_use_verbs)

        # 4. Select amount connector
        # Choose from the specific list if available, otherwise fall back to generic
        specific_connectors = amount_connectors.get(self.value_type, [])
        all_possible_connectors = specific_connectors + amount_connectors["generic"]
        chosen_connector = random.choice(all_possible_connectors)

        # 4b. Select amount prefix (for templates that don't use a company/verb)
        specific_prefixes = amount_prefixes.get(self.value_type, [])
        all_possible_prefixes = specific_prefixes + amount_prefixes["generic"]
        chosen_prefix = random.choice(all_possible_prefixes)

        # --- FIX: Dynamically add context words based on sentence type ---
        swap_type_to_use = self.swap_type
        if self.sentence_type == "new_individual":
            swap_type_to_use = f"new {self.swap_type}"

        amount_prefix_to_use = chosen_prefix
        if self.sentence_type == "terminated_individual":
            prefix_word = random.choice(["prior", "final"])
            amount_prefix_to_use = f"{prefix_word} {chosen_prefix}"

        # --- Refine value_type based on the chosen connector/prefix ---
        # If a generic term was chosen, it's more likely to be interpreted as 'notional' in a real filing.
        final_value_type = self.value_type
        is_generic_connector = chosen_connector in amount_connectors["generic"]
        is_generic_prefix = chosen_prefix in amount_prefixes["generic"]
        if (
            is_generic_connector or is_generic_prefix
        ) and self.value_type == "fair_value":
            final_value_type = "notional"

        # 5. Hedge designation clause
        # --- FIX: Make hedge designation clause optional ---
        hedge_designation_clause = ""
        # Use the provided seed or a new random float
        if random.random() < self.optional_chance:  # 50% chance to add this clause
            # Choose from templates that are not empty
            designation_template = random.choice([d for d in hedge_designations if d])
            hedge_designation_clause = designation_template.format(
                hedge_type=random.choice(hedge_types)
            )

        # 6. Result phrase clause.
        # NEW: The result phrase template is now selected inside the build method.
        result_clause = ""
        # --- FIX: Make result phrase clause optional ---
        if random.random() < self.optional_chance:  # 50% chance to add this clause
            # Choose from templates that are not empty
            result_phrase_template = random.choice([r for r in result_phrases.get(self.category, result_phrases["GEN"]) if r])  # type: ignore
            # Populate new placeholders within the result phrase itself
            outcome_verb = random.choice(financial_outcome_verbs)
            outcome_loc = random.choice(balance_sheet_locations)

            # Generate a random amount for the result phrase and format it

            random_amount = int(
                (self.notional or random.randint(1, 300) * self.notional_multiplier)
                * random.randint(1, 50)
                / 100
            )
            formatted_amount_result = _format_single_notional(
                random_amount,
                self.currency_symbol,
                
                self.prefer_abbreviated,
            )
            # Format currencies into a readable string from the details object
            details = self.specific_details or SpecificDetails()
            currencies_str = ""
            # --- NEW: Handle multiple commodities and sensible fallbacks ---
            commodities_str = "various commodities"
            unit_name = "units"
            if details.commodity:
                if len(details.commodity) > 1:
                    commodities_str = (
                        ", ".join(details.commodity[:-1])
                        + f" and {details.commodity[-1]}"
                    )
                else:
                    commodities_str = details.commodity[0]
                unit_name = random.choice(
                    get_units_for_commodity(random.choice(details.commodity))
                )

            if details.currencies:
                currencies_str = (
                    ", ".join(details.currencies[:-1])
                    + " and "
                    + details.currencies[-1]
                    if len(details.currencies) > 1
                    else details.currencies[0]
                )

            # Fallback if no commodity is provided in details
            if not details.commodity:
                commodities_str, unit_name, _ = get_random_commodity_and_unit()
            details = self.specific_details or SpecificDetails()
            populated_phrase = result_phrase_template.format(
                mitigation_verb=random.choice(
                    [v for v in risk_management_verbs if not v.endswith("ing")]
                ),  # Use base form
                gain_loss=random.choice(gain_loss_phrases),
                outcome_location=f"{outcome_verb} {outcome_loc}",
                frequency=details.frequency or random.choice(frequencies),
                risk_term=random.choice(risk_exposure_terms),
                risk_term2=random.choice(
                    risk_exposure_terms
                ),  # A second random one for variety
                ir_term=random.choice(interest_rate_terms),  # type: ignore
                debt_type=details.debt_type or "debt",
                currencies=currencies_str or "various currencies",
                currency_code=self.currency_code,
                rate_term1=random.choice(specific_rate_terms),
                rate_term2=random.choice(specific_rate_terms),
                formatted_amount=formatted_amount_result,  # type: ignore
                pct=f"{(details.pct or random.uniform(1.5, 7.5)):.2f}",
                geography=details.geography or random.choice([c.location for c in all_currencies]),  # type: ignore
                commodity=commodities_str,
                unit=details.unit
                or unit_name,  # Use the unit from details if provided, otherwise the derived one
                financial_outcome_verb=outcome_verb,
                company=self.company_name,
                swap_type=self.swap_type,
            )
            result_clause = populated_phrase

        # 6b. Maturity clause, only if the type of sentence is is_ter
        maturity_clause = ""
        if self.maturity_year and self.sentence_type:
            # Determine if we should include the maturity date based on sentence type and a random chance.
            # Always include for terminated instruments.
            # Sparingly include for other individual instruments, especially historical ones.
            should_include_maturity = self.sentence_type == "terminated_individual" or (
                self.sentence_type
                in ["historical_individual", "individual", "new_individual"]
                and random.random() < 0.10
            )

            if should_include_maturity:
                if self.reporting_year and self.maturity_year > self.reporting_year:
                    adverb = random.choice(future_adverbs)
                    verb_tense = random.choice(
                        [v for v in termination_verbs_present if not v.endswith("ed")]
                    )  # Ensure present tense
                    maturity_clause = (
                        f"which {adverb} {verb_tense} in {self.maturity_year}"
                        if random.random() < 0.5
                        else f"with a maturity date in {self.maturity_year}"
                    )
                else:  # maturity_year <= reporting_year
                    verb_tense = random.choice(
                        [v for v in termination_verbs_past if v.endswith("ed")]
                    )  # Ensure past tense
                    maturity_clause = f"which {verb_tense} in {self.maturity_year}"

        # 7. Select main sentence template
        templates_for_type = NOTIONAL_SENTENCE_TEMPLATES.get(
            self.sentence_type, NOTIONAL_SENTENCE_TEMPLATES["summary"]
        )
        template = random.choice(templates_for_type)

        # --- NEW LOGIC: Check if the template actually uses a notional amount placeholder. ---
        mentions_amount = (
            "{amount_str}" in template
            or "{amount_connector}" in template
            or "{amount_prefix}" in template
        )
        final_notional = self.notional if mentions_amount else None

        final_notional_str = amount_str if mentions_amount else None
        # --- NEW: These are now generated inside the build method for specific templates ---
        termination_noun_local = random.choice(termination_noun)
        comparison_phrase_local = random.choice(comparison_phrases)

        # Handle "no_instruments" case specifically
        if self.sentence_type == "no_instruments":
            template = random.choice(NO_INSTRUMENTS_TEMPLATES)
            category_map = {
                "IR": "interest rate",
                "FX": "foreign currency",
                "CP": "commodity price",
                "EQ": "equity",
                "GEN": "",
            }
            # Define a descriptive phrase for the category
            category_risk_phrase = category_map.get(self.category or "GEN", "")

            # Populate the chosen template
            sentence = template.format(
                time_prefix=time_prefix,
                company=company_name,
                verb=random.choice(non_use_verbs),  # e.g., "did not hold"
                swap_type=(f"{self.swap_type}" or f"{category_risk_phrase} derivative")
                + "s",
                category_risk_phrase=category_risk_phrase,  # type: ignore
                time_suffix=time_suffix,
                year=self.year,
                month=month,
                end_day=end_day,
                state_descriptor=random.choice(state_descriptors),
                immaterial_term=random.choice(immaterial),
                portfolio_term=random.choice(portfolio_terms).format(
                    swap_type=(
                        f"{self.swap_type}" or f"{category_risk_phrase} derivative"
                    )
                    + "s"
                ),
            )
            evidence = NotionalEvidence(
                status="no_instruments",
                category=self.category,  # type: ignore
                notional=0,
                instrument_type="none",
                year=self.year,
                currency=self.currency_code,
                reporting_year=self.reporting_year,
                sentence_type=self.sentence_type,
            )
            return sentence, evidence

        # 8. Populate placeholders
        sentence = template.format(
            time_prefix=time_prefix,
            company=company_name,
            verb=verb,
            swap_type=swap_type_to_use,
            amount_connector=chosen_connector,
            amount_prefix=amount_prefix_to_use,
            amount_str=amount_str,
            hedge_designation_clause=hedge_designation_clause,
            state_descriptor=random.choice(state_descriptors),
            historical_phrase=random.choice(historical_instrument_phrases),
            result_clause=result_clause,
            portfolio_term=random.choice(portfolio_terms).format(
                swap_type=f"{self.swap_type}" + "s"
            ),
            portfolio_verb=random.choice(portfolio_verbs),
            maturity_clause=maturity_clause,
            time_suffix=time_suffix,
            termination_noun=termination_noun_local,
            comparison_phrase=comparison_phrase_local,
            year=self.year,
            prev_year=self.year - 1,
            prev2_year=self.year - 2,
            month=month,
            end_day=end_day,
            begin_mitigation=begin_mitigation,
        )

        # 9. Cleanup
        sentence = _cleanup_sentence(sentence)

        # --- FIX for comparative_no_outstanding ---
        # For this specific case, the 'notional' passed in is actually the *previous* year's notional.
        # The current year's notional is zero. We need to reflect this in the evidence.
        if self.sentence_type == "comparative_no_outstanding":
            evidence = NotionalEvidence(
                instrument_id=None,
                status=self.sentence_type,
                category=self.category,  # type: ignore
                aggregate=True,  # This is an aggregate statement
                notional=0,  # Current year notional is zero
                year=self.year,
                notional_str=None,  # No notional string for current year
                prev_notional_str=final_notional_str,  # The formatted amount is for the prior year
                prev_year=self.year - 1,
                instrument_type=self.swap_type,
                reporting_year=self.reporting_year,
                value_type=final_value_type,
                sentence_type=self.sentence_type,
            )
            return sentence, evidence

        # 10. Create NotionalEvidence object
        evidence = NotionalEvidence(
            instrument_id=None,  # This is set later for individual instruments
            status=self.sentence_type,  # type: ignore
            category=self.category,  # type: ignore
            aggregate=self.sentence_type in ["summary", "comparative"],
            notional=final_notional,  # Use the conditional notional value
            year=self.year,
            notional_str=final_notional_str,
            prev_notional_str=None,  # Explicitly set to None for single sentences
            instrument_type=self.swap_type,
            maturity_year=self.maturity_year,
            reporting_year=self.reporting_year,
            value_type=final_value_type,
            sentence_type=self.sentence_type,
            is_repeated_mention=self.is_repeated_mention,
        )

        return sentence, evidence


@dataclass
class TimelineSentence:
    """
    Generates a multi-sentence paragraph describing the history of a single
    derivative instrument over several years.
    """

    instrument: NotionalInstrument
    company_name: str
    reporting_year: int
    currency_symbol: str
    currency_code: str
    prefer_abbreviated: bool
    value_type: Literal["notional", "fair_value"]

    def build(self) -> Tuple[str, NotionalEvidence]:
        """
        Builds a historical timeline paragraph for a single instrument.

        Returns:
            A tuple containing:
            - A single paragraph string describing the instrument's history.
            - A list of NotionalEvidence objects, one for each point in time mentioned.
        """  # type: ignore
        sentences = []
        evidence_list = []

        # --- Select years and sort them ---
        # --- FIX: Filter out years from history that are after the instrument's maturity date ---
        history_years = sorted([
            year for year in self.instrument.notional_history.keys()
            if self.instrument.maturity_year and year <= self.instrument.maturity_year
        ])
        years_to_report = []
        if len(history_years) > 2:
            # Select start, a middle point, and the most recent year before the reporting year
            years_to_report.append(history_years[0])  # Inception year
            if len(history_years) > 3:
                mid_index = len(history_years) // 2
                years_to_report.append(history_years[mid_index])
            # Add the most recent year that is not the inception year
            if history_years[-1] != history_years[0]:
                years_to_report.append(history_years[-1])
        else:
            years_to_report = history_years

        # Ensure unique, sorted years
        selected_years = sorted(list(set(years_to_report)))

        # --- FIX: Store formatted notional strings for the evidence object ---
        timeline_notional_strings: Dict[int, str] = {}

        # --- Generate sentences for each selected year ---
        for i, year in enumerate(selected_years):
            prev_notional = (
                self.instrument.notional_history.get(selected_years[i - 1])
                if i > 0
                else None
            )
            notional = self.instrument.notional_history[year]
            if self.value_type == "fair_value":
                notional = max(1, int(notional / random.randint(20, 100)))

            # --- FIX: Correctly format the notional string for each year ---
            formatted_notional = _format_single_notional(
                notional,
                self.currency_symbol,
                self.prefer_abbreviated,
            )
            timeline_notional_strings[year] = formatted_notional

            if i == 0:
                # First mention: Use "inception" template
                sentence_type = "inception"
                name_to_use = self.instrument.instrument_type
            # --- NEW: Check if this is the final year of a terminated instrument's life ---
            elif self.instrument.maturity_year and year == self.instrument.maturity_year and self.instrument.maturity_year < self.reporting_year:
                # This is the maturity year, so use a termination template.
                sentence_type = "terminated_individual"
                # Use alias for consistency in the story
                name_to_use = self.instrument.instrument_alias
            else:
                # --- NEW: Check for partial settlement ---
                # If notional decreased by more than 30%, it's a partial settlement.
                if (
                    prev_notional
                    and notional < prev_notional * 0.7
                    and random.random() < 0.8
                ):
                    sentence_type = "partial_settlement"
                else:
                    # Otherwise, it's just a continuing mention.
                    sentence_type = "continuing"
                # Use the alias for subsequent mentions to make the text more natural
                name_to_use = self.instrument.instrument_alias

            sentence_obj = NotionalSentence(
                swap_type=name_to_use,
                year=year,
                # --- FIX: Pass the correctly formatted string ---
                notional=notional,
                sentence_type=sentence_type,  # type: ignore
                # Pass additional details for the partial_settlement templates
                # No specific_details needed here, as TimelineSentence doesn't have hedged item context.
                company_name=self.company_name,
                # Use a past-tense verb for partial settlements
                verb=(
                    random.choice(termination_verbs_past)
                    if sentence_type == "partial_settlement"
                    else None
                ),
                currency_symbol=self.currency_symbol,
                currency_code=self.currency_code,
                
                prefer_abbreviated=self.prefer_abbreviated,
                maturity_year=self.instrument.maturity_year,
                category=self.instrument.category,
                reporting_year=self.reporting_year,
                value_type=self.value_type,
            )
            sentence_text, evidence = sentence_obj.build()
            sentences.append(sentence_text)

        # --- FIX: Create a single, consolidated evidence object for the entire timeline ---
        # This makes the chain_of_thought much more coherent.
        inception_year = selected_years[0]
        final_year = selected_years[-1]

        consolidated_evidence = NotionalEvidence(
            instrument_id=self.instrument.instrument_id,
            status="timeline",  # A new status for our custom handler
            category=self.instrument.category,
            notional=self.instrument.notional_history[final_year],
            notional_str=timeline_notional_strings[final_year],
            prev_notional_str=timeline_notional_strings.get(inception_year),
            year=final_year,
            prev_year=inception_year,
            instrument_type=self.instrument.instrument_type,
            maturity_year=self.instrument.maturity_year,
            reporting_year=self.reporting_year,
            value_type=self.value_type,
        )

        # Combine sentences into a single, flowing paragraph
        full_paragraph = " ".join(sentences)

        return full_paragraph, consolidated_evidence
