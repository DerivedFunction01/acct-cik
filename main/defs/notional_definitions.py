from dataclasses import dataclass
import random
from typing import Callable, Dict, List, Literal, Optional, Tuple
from defs.function_definitions import _get_company_reference, _format_single_notional, _cleanup_sentence, _get_correct_rounding
from defs.common_data import *
from defs.cp_data import CPContextSentence, CommodityHedgedItem, get_random_commodity_and_unit, get_units_for_commodity
from defs.eq_data import EQContextSentence, EquityHedgedItem
from defs.fx_data import FXContextSentence, ForeignCurrencyHedgedItem, all_currencies
from defs.ir_data import DebtContextSentence, DebtHedgedItem, IRInstrument
from defs.instrument_definitions import NotionalInstrument
from defs.instrument_definitions import BaseNarrativeEvidence, DerivativeCategory, SpecificDetails


@dataclass
class NotionalEvidence(BaseNarrativeEvidence):
    """Evidence related to notional or fair value amounts of derivative instruments, with temporal reasoning and validation."""

    aggregate: bool = False
    notional: Optional[int] = None
    prev_notional: Optional[int] = None
    prev2_notional: Optional[int] = None
    month: Optional[str] = None
    year: Optional[int] = None
    prev_year: Optional[int] = None
    prev2_year: Optional[int] = None
    instrument_type: Optional[str] = None
    notional_str: Optional[str] = None
    prev_notional_str: Optional[str] = None
    reporting_year: Optional[int] = None
    maturity_year: Optional[int] = 0
    maturity_value: Optional[int] = None
    value_type: str = "notional"
    currency: str = "USD"
    symbol: Optional[str] = None
    sentence_type: Optional[str] = None
    is_repeated_mention: bool = False
    active_override: bool = False # If no notional is given (None), override to active
    # additional_details is inherited

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
            "GEN": "",
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
                "timeline",
            ]
        ):
            # --- FIX: Restore maturity year to the reasoning for individual instruments. ---
            # This creates a more descriptive reasoning string like "(2020, matures: 2025)".
            if self.maturity_year is not None and self.maturity_year != self.year and self.maturity_year > 0:
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

    # ---------------------------------------------------------------------
    # Core logic
    # ---------------------------------------------------------------------

    def to_string(self) -> str:
        """Generates a detailed reasoning statement describing notional or fair value evidence, 
        while remaining robust to missing fields and providing temporal context."""
        
        category_name = self._category_label()
        category_context = f"{category_name} derivative activity" if category_name else "derivative activity"
        classification_note = ""
        value_desc = "fair value" if self.value_type == "fair_value" else "notional value"

        temporal_info = self._temporal_reasoning() if self.year or self.reporting_year else ""
        warning = self._validate_temporal_consistency()

        # --- Currency and maturity hints ---
        currency_hint = f" (denominated in {self.currency})" if self.currency and self.currency != "USD" else ""
        maturity_hint = (
            f" and maturing in {self.maturity_year}" 
            if self.maturity_year and self.maturity_year > 0 and self.maturity_year != self.year 
            else ""
        )

        # --- Contextual instrument description ---
        base_desc = (
            f"{self.instrument_type}" if self.instrument_type else f"{category_context}"
        )

        # -----------------------------------------------------------------
        # Sentence-type specific handlers
        # -----------------------------------------------------------------
        def summary_handler() -> str:
            parts = []
            if self.notional_str:
                parts.append(f"aggregate {value_desc} of {self.notional_str}")
            else:
                parts.append(f"aggregate {value_desc} with no amount disclosed")
            if self.reporting_year:
                parts.append(f"reported for {base_desc} in {self.reporting_year}")
            return " ".join(parts) + temporal_info + maturity_hint + currency_hint

        def new_individual_handler() -> str:
            desc = f"New {base_desc} recorded"
            if self.notional_str:
                desc += f" with a {value_desc} of {self.notional_str}"
            if self.reporting_year:
                desc += f" in {self.reporting_year}"
            return desc + temporal_info + maturity_hint + currency_hint

        def individual_handler() -> str:
            desc = f"{base_desc.capitalize()} reported"
            if self.notional_str:
                desc += f" with a {value_desc} of {self.notional_str}"
            if self.reporting_year:
                desc += f" for {self.reporting_year}"
            return desc + temporal_info + maturity_hint + currency_hint

        def terminated_individual_handler() -> str:
            desc = f"Terminated {base_desc}"
            if self.notional_str:
                desc += f" previously held a {value_desc} of {self.notional_str}"
            if self.reporting_year:
                desc += f" before {self.reporting_year}"
            return desc + temporal_info + maturity_hint + currency_hint

        def no_instruments_handler() -> str:
            desc = f"The report confirms no outstanding {base_desc}"
            if self.reporting_year:
                desc += f" as of {self.reporting_year}"
            return desc + temporal_info

        def comparative_handler() -> str:
            prev_part = f" {self.prev_notional_str} in {self.prev_year}" if self.prev_notional_str and self.prev_year else ""
            curr_part = f" {self.notional_str} in {self.reporting_year}" if self.notional_str and self.reporting_year else ""
            return (
                f"Comparative disclosure for {base_desc} shows {value_desc} change from{prev_part} to{curr_part}"
                f"{temporal_info}{maturity_hint}{currency_hint}"
            )

        def comparative_no_outstanding_handler() -> str:
            desc = (
                f"No current {base_desc} outstanding in {self.reporting_year}, "
                f"compared with {self.prev_notional_str} in {self.prev_year}"
            )
            return desc + f"{temporal_info}{maturity_hint}{currency_hint}"

        def comparative_no_prior_outstanding_handler() -> str:
            desc = (
                f"New {base_desc} activity in {self.reporting_year}"
                f" with a {value_desc} of {self.notional_str}, where none existed previously"
            )
            return desc + f"{temporal_info}{maturity_hint}{currency_hint}"

        def historical_individual_handler() -> str:
            desc = f"A {base_desc} mention"
            if self.notional_str:
                desc += f" reflecting a {value_desc} of {self.notional_str}"
            return desc + temporal_info + maturity_hint + currency_hint

        def timeline_handler() -> str:
            start_val = (
                f" from {self.prev_notional_str} in {self.prev_year}" 
                if self.prev_notional_str and self.prev_year else ""
            )
            end_val = (
                f" to {self.notional_str} in {self.year}" 
                if self.notional_str and self.year else ""
            )
            return (
                f"A timeline for {base_desc} shows {value_desc} progression"
                f"{start_val}{end_val}{temporal_info}{maturity_hint}{currency_hint}"
            )

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
            "timeline": timeline_handler,
        }

        text = handlers.get(
            self.status,
            lambda: f"Uncategorized notional evidence found for {base_desc}."
        )()

        if warning:
            text = f"{text} {warning}"

        return " ".join(text.split())


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
        "continuing", # For TimelineSentence
        "partial_settlement",  # For TimelineSentence
    ] = "summary"
    is_summary: bool = False
    notional: Optional[int] = None
    prev_notional: Optional[int] = None
    prev2_notional: Optional[int] = None
    currency_symbol: str = "$"
    currency_code: str = "USD"
    # Optional time components
    month: Optional[str] = None
    end_day: Optional[int] = None
    quarter: Optional[str] = None

    # Optional descriptive elements
    company_name: Optional[str] = None
    verb: Optional[str] = None
    prev_year: Optional[int] = None
    prev2_year: Optional[int] = None
    maturity_value: Optional[int] = 0
    maturity_year: Optional[int] = None
    specific_details: Optional[SpecificDetails] = None
    notional_multiplier: int = 1_000_000
    prefer_abbreviated: bool = True
    zero_notional_format: Literal["nil", "zero", "amount"] = "amount"
    preferred_negative_format: Literal[-1, 0, 1, 2] = 0
    instrument: Optional[NotionalInstrument] = None
    is_repeated_mention: bool = False
    optional_chance: float = 0.5
    suppress_sentence: bool = False
    currency_symbol2: str = "$"    

    def __post_init__(self):
        # If comparative_no_outstanding is chosen but there's no prior notional, it's just a 'no_instruments' case.
        if self.sentence_type == "comparative_no_outstanding" and self.notional is None:
            self.sentence_type = "no_instruments"

    def build(self) -> Tuple[str, NotionalEvidence]:
        from defs.template_definitions import (
            multi_year_time_prefixes,
            point_in_time_prefixes,
            NOTIONAL_SENTENCE_TEMPLATES,
            period_of_time_prefixes,
            amount_connectors,
            amount_prefixes,
            hedge_designations,
            hedge_types,
            result_phrases,
            NO_INSTRUMENTS_TEMPLATES,
            portfolio_terms,
            historical_instrument_phrases,
            portfolio_verbs,
            MITIGATION_TEMPLATES,
        )

        """
        Builds a notional sentence and a corresponding NotionalEvidence object.
        Returns: A tuple of (sentence_string, NotionalEvidence_instance).
        """
        if self.value_type == "fair_value":
            if self.notional is not None:
                self.notional = self.generate_fair_value(self.notional)
            if self.prev_notional is not None:
                self.prev_notional = self.generate_fair_value(self.prev_notional)
            if self.prev2_notional is not None:
                self.prev2_notional = self.generate_fair_value(self.prev2_notional)

        # --- FIX: Round the notional amounts to match the multiplier for clean JSON output ---
        # This ensures that a narrative saying "$2.7 million" results in a JSON amount of 2700000, not 2722266.
        # This is the single source of truth for rounding before evidence is created.
        if self.notional_multiplier > 1:
            if self.notional is not None:
                self.notional = _get_correct_rounding(self.notional, self.notional_multiplier)
            if self.prev_notional is not None:
                self.prev_notional = _get_correct_rounding(self.prev_notional, self.notional_multiplier)
            if self.prev2_notional is not None:
                self.prev2_notional = _get_correct_rounding(self.prev2_notional, self.notional_multiplier)

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
            locations_str = f"various {random.choice(geo_locations)}"
            if details.geography:
                locations_str = (
                    ", ".join(details.geography[:-1]) + " and " + details.geography[-1]
                    if len(details.geography) > 1
                    else details.geography[0]
                )
            begin_mitigation = (
                _cleanup_sentence(mitigation_phrase_template.format(
                    risk_action_verb=random.choice(
                        [v for v in risk_management_verbs if not v.endswith("ing")]
                    ),
                    ir_term=random.choice(interest_rate_terms),
                    debt_type=details.debt_type or "debt",
                    risk_term=random.choice(risk_exposure_terms),
                    risk_term2=random.choice(risk_exposure_terms),
                    currencies=currencies_str or "various currencies",
                    geography=locations_str,  # type: ignore
                    commodity=commodities_str,
                    rate_term1=random.choice(specific_rate_terms),
                    rate_term2=random.choice(specific_rate_terms),
                ))
                + ", "
            )

        # 1. Format amount string
        amount_str = ""
        prev_amount_str = ""
        if self.sentence_type.startswith("comparative") and self.notional is not None and self.prev_notional is not None and self.prev2_notional is not None:
            # Special formatting for three-year comparative sentences
            formatted_current = _format_single_notional(
                self.notional,
                self.currency_symbol,
                self.prefer_abbreviated,
                False,
                self.zero_notional_format,
                self.preferred_negative_format,
            )
            formatted_prev = _format_single_notional(
                self.prev_notional,
                self.currency_symbol,
                self.prefer_abbreviated,
                False,
                self.zero_notional_format,
                self.preferred_negative_format,
            )
            formatted_prev2 = _format_single_notional(
                self.prev2_notional,
                self.currency_symbol,
                self.prefer_abbreviated,
                False,
                self.zero_notional_format,
                self.preferred_negative_format,
            )
            amount_str = f"{formatted_current}, {formatted_prev}, and {formatted_prev2}"
        elif self.sentence_type.startswith("comparative") and self.notional is not None and self.prev_notional is not None:
            # Special formatting for comparative sentences
            formatted_current = _format_single_notional(
                self.notional,
                self.currency_symbol,
                self.prefer_abbreviated,
                False,
                self.zero_notional_format,
                self.preferred_negative_format,
            )
            formatted_prev = _format_single_notional(
                self.prev_notional,
                self.currency_symbol,
                self.prefer_abbreviated,
                False,
                self.zero_notional_format,
                self.preferred_negative_format,
            )
            amount_str = f"{formatted_current} and {formatted_prev}"
            prev_amount_str = formatted_prev
        elif self.notional is not None:
            # Standard formatting for single-value sentences
            amount_str = _format_single_notional(
                self.notional,
                self.currency_symbol,
                self.prefer_abbreviated,
                False,
                self.zero_notional_format,
                self.preferred_negative_format,
            )

        # 2. Select time prefix template
        time_prefix = ""
        time_suffix = ""
        if self.sentence_type in [
            "summary",    
            "no_instruments",
            "individual",
        ] or self.sentence_type.startswith("comparative"):
            # --- FIX: Explicitly check for prev2_year to select the correct multi-year prefix ---
            if self.sentence_type.startswith("comparative") and self.prev_year and self.prev2_year:
                time_prefix = random.choice(multi_year_time_prefixes["three_year"])
            elif self.sentence_type.startswith("comparative") and self.prev_year:
                time_prefix = random.choice(multi_year_time_prefixes["two_year"])
            else:
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
            prev_year=self.prev_year,
            prev2_year=self.prev2_year,
            quarter=quarter
        )
        time_suffix = time_prefix

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
        # --- NEW: Handle repeated mentions of similar instrument types ---
        swap_type_to_use = self.swap_type
        # This flag now specifically means "this is a new instrument instance, but its type has been seen before."
        if self.is_repeated_mention:
            # Prepend a word to clarify that this is a *different* instrument of the same type.
            # e.g., "a separate interest rate swap", "an additional hedging agreement"
            repetition_word = random.choice(
                [
                    "another",
                    "additional",
                    "separate",
                    "different",
                ]
                + [f"__counter__{self.instrument.instrument_type}"] if self.instrument else [],  # To use regex at the final join of the narrative
            )
            swap_type_to_use = f"{repetition_word} {self.swap_type}"

        # --- FIX: Make hedge designation clause optional ---
        # NEW: If notional is 0 for a single-year sentence, don't add designation or result clauses.
        is_single_year_zero_notional = (
            self.notional == 0
            and self.sentence_type
            not in ["comparative", "comparative_no_outstanding"]
        )

        hedge_designation_clause = ""
        # Use the provided seed or a new random float
        if not is_single_year_zero_notional and random.random() < self.optional_chance:
            # Choose from templates that are not empty
            designation_template = random.choice([d for d in hedge_designations if d])
            hedge_designation_clause = designation_template.format(
                hedge_type=random.choice(hedge_types),
                hedged="" if self.instrument and self.instrument.hedged_item else "not",
            )

        # 6. Result phrase clause.
        # NEW: The result phrase template is now selected inside the build method.
        result_clause = ""
        # --- FIX: Make result phrase clause optional ---
        if not is_single_year_zero_notional and random.random() < self.optional_chance:
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
                negative_format=self.preferred_negative_format,
                zero_format=self.zero_notional_format,
            )
            # Format currencies into a readable string from the details object
            details = self.specific_details or SpecificDetails()

            # --- FIX: Use the specific commodity from the instrument's hedged item ---
            # This prevents mismatches like hedging 'diesel' to protect against 'asphalt' prices.
            if self.instrument and self.instrument.hedged_item and isinstance(self.instrument.hedged_item, CommodityHedgedItem):
                commodity_to_use = self.instrument.hedged_item.commodity_type
                unit_to_use = self.instrument.hedged_item.unit_of_volume
            else:
                # Fallback to the less specific details if no direct hedged item is available
                if details.commodity:
                    commodity_to_use = random.choice(details.commodity)
                    unit_to_use = random.choice(get_units_for_commodity(commodity_to_use))
                else:
                    # If no commodity context exists at all, generate a random one as a last resort.
                    commodity_to_use, unit_to_use, _ = get_random_commodity_and_unit()

            # Handle currencies and geography from specific_details
            currencies_str = (
                ", ".join(details.currencies) if details.currencies else "various currencies"
            )
            locations_str = f"various {random.choice(geo_locations)}"
            if details.geography:
                locations_str = (
                    ", ".join(details.geography[:-1]) + " and " + details.geography[-1]
                    if len(details.geography) > 1
                    else details.geography[0]
                )

            # Fallback if no commodity is provided in details
            if not details.commodity:
                commodities_str, unit_name, _ = get_random_commodity_and_unit()
            details = self.specific_details or SpecificDetails()
            populated_phrase = result_phrase_template.format(
                mitigation_verb=random.choice(risk_management_verbs_no_ing),  # Use base form
                mitigation_verb_ing=random.choice(risk_management_verbs_ing),
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
                geography=locations_str,  # type: ignore
                commodity=commodity_to_use,
                unit=unit_to_use,
                financial_outcome_verb=outcome_verb,
                company=self.company_name,
                swap_type=self.swap_type,
            )
            result_clause = populated_phrase

        # 6b. Maturity clause, only if the type of sentence is is_ter
        maturity_clause = ""
        should_include_maturity = False
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
                    termination = random.choice(termination_noun)
                    verb_tense = random.choice(
                        [v for v in termination_verbs_present if not v.endswith("ed")]
                    )  # Ensure present tense
                    maturity_clause = (
                        f"which {adverb} {verb_tense} in {self.maturity_year}"
                        if random.random() < 0.5
                        else f"with a {termination} date in {self.maturity_year}"
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
        amount_prefix_to_use = "" if not mentions_amount else amount_prefix_to_use
        chosen_connector = "" if not mentions_amount else chosen_connector
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
                risk_management_verb=random.choice(risk_management_verbs_no_ing),
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
            sentence = _cleanup_sentence(sentence)
            return sentence, evidence

        # 8. Populate placeholders
        sentence = template.format(
            time_prefix=time_prefix,
            company=company_name,
            verb=verb,
            swap_type=swap_type_to_use,  # This now includes "another", etc. if it's a repeat
            amount_connector=chosen_connector,
            amount_prefix=amount_prefix_to_use,
            amount_str=final_notional_str,
            hedge_designation_clause=hedge_designation_clause,
            state_descriptor=random.choice(state_descriptors),
            historical_phrase=(
                random.choice(historical_instrument_phrases)
                if self.year == self.reporting_year
                else f"from {self.year - 2}"
            ),
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
            # The notional passed to the constructor is the prior year's value.
            evidence = NotionalEvidence(
                instrument_id=None,
                status=self.sentence_type,
                category=self.category,  # type: ignore
                aggregate=True,  # This is an aggregate statement
                notional=0,  # Current year notional is zero
                year=self.reporting_year,
                prev_notional=_get_correct_rounding(self.notional or 0, self.notional_multiplier), # The value from the prior year
                prev_notional_str=final_notional_str,  # The formatted amount is for the prior year
                prev_year=self.year - 1,
                instrument_type=self.swap_type,
                reporting_year=self.reporting_year, # type: ignore
                value_type=final_value_type,
                sentence_type=self.sentence_type,
                additional_details={"result_clause": result_clause, "mitigation": begin_mitigation}
            )
            return sentence, evidence

        # 10. Create NotionalEvidence object
        evidence = NotionalEvidence(
            instrument_id=None,  # This is set later for individual instruments
            # --- FIX: Prioritize the instrument's specific currency/symbol if available ---
            # This ensures units like 'LTR' or 'Btu' are passed to the evidence.
            currency=(
                self.instrument.currency if self.instrument else self.currency_code
            ),
            symbol=self.instrument.symbol if self.instrument else self.currency_symbol,
            # -------------------------------------------------------------------------
            status=self.sentence_type,  # type: ignore
            category=self.category,  # type: ignore
            aggregate=self.is_summary,
            notional=_get_correct_rounding(
                final_notional, self.notional_multiplier
            ),  # Use the conditional notional value
            prev_notional=(
                _get_correct_rounding(self.prev_notional, self.notional_multiplier)
                if self.sentence_type.startswith("comparative")
                else None
            ),
            prev2_notional=(
                _get_correct_rounding(self.prev2_notional, self.notional_multiplier)
                if self.sentence_type.startswith("comparative")
                else None
            ),
            year=self.year,
            notional_str=final_notional_str or None,
            prev_notional_str=prev_amount_str or None,
            instrument_type=self.swap_type,  # type: ignore
            maturity_year=(self.maturity_year if should_include_maturity else None),
            reporting_year=self.reporting_year,
            value_type=final_value_type,
            sentence_type=self.sentence_type,
            is_repeated_mention=self.is_repeated_mention,  # active override for no mentions of currency
            active_override=final_notional is None
            and self.notional is not None
            and self.notional > 0
            and self.sentence_type
            not in ["comparative_no_outstanding", "no_instruments"],
            additional_details={
                "result_clause": result_clause,
                "mitigation": begin_mitigation,
            },
        )
        # --- NEW: Append optional detail sentences ---
        optional_sentence = self._build_optional_details(evidence)
        if optional_sentence:
            sentence += " " + optional_sentence

        # --- NEW: Check for the suppress_sentence flag ---
        if self.suppress_sentence:
            return "", evidence

        # --- NEW: With a chance, append a contextual sentence ---
        if random.random() < 0.25: # 25% chance to add context
            context_sentence = self._build_context_sentence()
            if context_sentence:
                sentence += " " + context_sentence

        return sentence, evidence

    def _build_optional_details(self, evidence: NotionalEvidence) -> str:
        from defs.template_definitions import (
            OPTIONAL_DETAIL_TEMPLATES, fair_value_level_examples
        )
        """
        Generates an optional, additional sentence with specific details like
        gains/losses, fair value levels, or payments.
        """
        # Only add details for sentences that describe an actual instrument with a value.
        if (
            evidence.status in ["no_instruments", "comparative_no_outstanding"]
            or evidence.notional is None
            or evidence.notional == 0
        ):
            return ""

        # Randomly decide whether to add a detail, and if so, which kind.
        if random.random() < 0.35:  # 35% chance to add an extra detail sentence
            detail_type = random.choice(list(OPTIONAL_DETAIL_TEMPLATES.keys()))
            template = random.choice(OPTIONAL_DETAIL_TEMPLATES[detail_type])

            # Generate a smaller random amount for the detail sentence
            detail_amount = int(evidence.notional * random.uniform(0.01, 0.15))
            detail_amount_str = _format_single_notional(
                detail_amount,
                self.currency_symbol,
                self.prefer_abbreviated,
                no_unit_word=False,
                negative_format=self.preferred_negative_format,
            )

            level_num = random.randint(1, 3)

            placeholders = {
                "company": _get_company_reference(self.company_name or "The Company"),
                "year": self.year,
                "month": self.month or random.choice(months),
                "end_day": self.end_day or random.randint(28, 31),
                "gain_loss": random.choice(gain_loss_phrases),
                "amount_str": detail_amount_str,
                "swap_type": self.swap_type,
                "location": random.choice(balance_sheet_locations),
                "level_num": level_num,
                "level_input_examples": fair_value_level_examples[level_num],
                "frequency": random.choice(frequencies),
                "paid_received": random.choice(["paid", "received"]),
            }

            sentence = template.format_map(placeholders)
            return _cleanup_sentence(sentence)

        return ""

    def _build_context_sentence(self) -> str:
        """
        Generates a contextual sentence related to the instrument's hedged item.
        This helps to ground the notional amount in a real-world exposure.
        """
        if not self.instrument or not self.instrument.hedged_item:
            return ""

        hedged_item = self.instrument.hedged_item
        context_builder = None

        if isinstance(hedged_item, DebtHedgedItem) and isinstance(self.instrument, IRInstrument):
            context_builder = DebtContextSentence(
                company_name=self.company_name or "The Company",
                reporting_year=self.reporting_year,
                reporting_month=self.month or "December",
                reporting_day=self.end_day or 31,
                hedged_item=hedged_item,
                prefer_abbreviated=self.prefer_abbreviated,
                currency_symbol=self.currency_symbol,
                instrument=self.instrument,
                more_detail=True, # Ask for a more detailed sentence
            )
        elif isinstance(hedged_item, ForeignCurrencyHedgedItem):
            context_builder = FXContextSentence(
                company_name=self.company_name or "The Company",
                reporting_year=self.reporting_year,
                reporting_month=self.month or "December",
                reporting_day=self.end_day or 31,
                hedged_item=hedged_item,
                prefer_abbreviated=self.prefer_abbreviated,
                currency_symbol=self.currency_symbol,
                currency_code=self.currency_code,
                notional_multiplier=self.notional_multiplier,
            )
        elif isinstance(hedged_item, CommodityHedgedItem):
            context_builder = CPContextSentence(
                company_name=self.company_name or "The Company",
                reporting_year=self.reporting_year,
                reporting_month=self.month or "December",
                reporting_day=self.end_day or 31,
                hedged_item=hedged_item,
                prefer_abbreviated=self.prefer_abbreviated,
                currency_symbol=self.currency_symbol2,
                notional_multiplier=self.notional_multiplier,
            )
        # EQContextSentence could be added here in the future if needed.
        elif isinstance(hedged_item, EquityHedgedItem):
            context_builder = EQContextSentence(
                company_name=self.company_name or "The Company",
                reporting_year=self.reporting_year,
                reporting_month=self.month or "December",
                reporting_day=self.end_day or 31,
                hedged_item=hedged_item,
                prefer_abbreviated=self.prefer_abbreviated,
                currency_symbol=self.currency_symbol2,
            )

        return context_builder.build() if context_builder else ""

    def generate_fair_value(self, value: int):
        return max(0, int(value / random.randint(20, 100)))


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
    preferred_negative_format: Literal[-1, 0, 1, 2] = 0
    notional_multiplier: int = 1000

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
        # --- FIX: Handle active instruments correctly by not filtering future years ---
        # Get all years from history where the notional was greater than zero.
        active_history_years = sorted([
            year for year, notional in self.instrument.notional_history.items() if notional > 0
        ])

        # If the instrument is terminated, ensure we don't include years after maturity.
        if self.instrument.maturity_year and self.instrument.maturity_year < self.reporting_year:
            history_years = [y for y in active_history_years if y <= self.instrument.maturity_year]
        else:
            # For active instruments, use all of its active history.
            history_years = active_history_years

        years_to_report = []
        if len(history_years) > 2:
            # Select start, a middle point, and the most recent year from its history.
            years_to_report.append(history_years[0])  # Inception year
            if len(history_years) > 3:
                mid_index = len(history_years) // 2
                years_to_report.append(history_years[mid_index])

            # Add the most recent year from its history, which could be the current reporting year.
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
                notional = max(0, int(notional / random.randint(20, 100)))

            # --- FIX: Correctly format the notional string for each year ---
            formatted_notional = _format_single_notional(
                notional,
                self.currency_symbol,
                self.prefer_abbreviated,
                negative_format=self.preferred_negative_format,
            )
            timeline_notional_strings[year] = formatted_notional

            if i == 0:
                # First mention: Use "inception" template
                sentence_type = "inception"
                name_to_use = self.instrument.instrument_type
            # --- NEW: Check if this is the final year of a terminated instrument's life ---
            elif self.instrument.maturity_year and year == self.instrument.maturity_year and self.instrument.maturity_year < self.reporting_year:
                # This is the maturity year of a past instrument. Use the specific maturity_value.
                sentence_type = "terminated_individual"
                notional = self.instrument.maturity_value or notional # Prioritize maturity_value
                # Use alias for consistency in the story
                name_to_use = self.instrument.instrument_alias
            else:
                # --- NEW: Check for partial settlement ---
                # Re-format the notional string here since it might have been updated for maturity
                formatted_notional = _format_single_notional(
                    notional,
                    self.currency_symbol,
                    self.prefer_abbreviated,
                    negative_format=self.preferred_negative_format,
                )
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
                notional=_get_correct_rounding(notional, self.notional_multiplier),
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
                preferred_negative_format=self.preferred_negative_format,
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
            currency=self.currency_code,
            # --- FIX: Use maturity_value for terminated instruments in the evidence ---
            notional=(
                _get_correct_rounding(
                    self.instrument.maturity_value or 0, self.notional_multiplier
                )
                if self.instrument.maturity_year
                and self.instrument.maturity_year < self.reporting_year
                else _get_correct_rounding(self.instrument.notional_history.get(
                    final_year, 0
                ), self.notional_multiplier)
            ),
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
