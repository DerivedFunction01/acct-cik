# New imports for generate_notional_sentence
from typing import List, Tuple

def _format_single_notional(
    amount: int,
    currency_symbol: str,
    money_units: List[Tuple[str, int]],
    prefer_abbreviated: bool,
) -> str:
    """Formats a single notional amount into a readable string like '$250.0 million'."""
    if prefer_abbreviated:
        # Sort units from largest to smallest
        for unit_word, divisor in sorted(money_units, key=lambda x: x[1], reverse=True):
            if amount >= divisor:
                # Format to one decimal place
                return f"{currency_symbol}{amount / divisor:.1f} {unit_word}"
    # Fallback to full numeric value with commas
    return f"{currency_symbol}{amount:,}"


def _cleanup_sentence(sentence: str) -> str:
    """Clean up sentence by removing empty placeholders and extra spaces."""
    # Remove any remaining optional placeholders that weren't filled
    sentence = sentence.replace("{hedge_designation_clause}", "")
    sentence = sentence.replace("{result_clause}", "")
    sentence = sentence.replace("{time_suffix}", "")  # If not used, remove it

    # Clean up multiple spaces
    while "  " in sentence:
        sentence = sentence.replace("  ", " ")

    # Clean up comma/space issues
    sentence = sentence.replace(" ,", ",")
    sentence = sentence.replace(",,", ",")

    # Remove trailing commas before period
    sentence = sentence.replace(", .", ".")
    sentence = sentence.replace(" .", ".")  # In case of empty clauses

    return sentence.strip()

# Time prefixes for point-in-time statements (e.g., aggregate summaries, single year)
point_in_time_prefixes = [
    "As of {month} {end_day}, {year}", # This is used by generate_notional_sentence
    "At year-end {year}",
    "As of year-end {year}",
    "At the end of {year}",
    "At the close of {year}",
    "As of {month} {year}",
    "At {month} {end_day}, {year}",
    "At {month} {year}",
]

# Time prefixes for period-of-time statements (e.g., new or terminated instruments, single year)
period_of_time_prefixes = [
    "During {year}", # This is used by generate_notional_sentence
    "In {year}",
    "Throughout {year}",
    "During {month} {year}",
    "In {month} {year}",
    "In the {quarter} quarter of {year}",
    "During the {quarter} quarter of {year}",
]

# Multi-year time prefixes (patterns for 2 or 3 years)
multi_year_time_prefixes = {
    "two_year": [
        "At {month} {end_day}, {year} and {prev_year}", # This is used by generate_notional_sentence
        "As of {month} {end_day}, {year} and {prev_year}",
        "At {month} {year} and {month} {prev_year}",
        "As of {month} {end_day}, {year} and {month} {end_day}, {prev_year}",
        "During {month} {year} and {prev_year}",
    ],
    "three_year": [
        "At {month} {end_day}, {year}, {prev_year}, and {prev2_year}", # This is used by generate_notional_sentence
        "As of {month} {end_day}, {year}, {prev_year}, and {prev2_year}",
        "At {month} {year}, {month} {prev_year}, and {month} {prev2_year}",
        "As of {month} {end_day}, {year}, {month} {end_day}, {prev_year}, and {month} {end_day}, {prev2_year}",
        "During {month} {year}, {prev_year}, and {prev2_year}",
    ],
}

# Connectors for linking an action/instrument to its notional or fair value
amount_connectors = {
    "notional": [
        "with notional amounts totaling",
        "with notional amounts of",
        "with aggregate notional values of",
        "with a notional amount of",
        "with notional values of",
        "in net notional",
    ],
    "fair_value": [
        "with fair value of",
        "with fair values totaling",
        "with fair market value of",
    ],
    "generic": [
        "totaling",
        "with a total of",
        "with a value of",
        "with amounts totaling",
        "in net value",
    ],
}

# Prefixes for describing amounts (e.g., "fair value of", "notional amount of")
amount_prefixes = {
    "notional": [
        "aggregate notional amount",
        "notional value",
        "net notional",
    ],
    "fair_value": [
        "fair value",
        "fair market value",
    ],
    "generic": [
        "aggregate amount",
        "total value",
        "total amount",
        "net value",
        "aggregate value",
    ],
}

# Portfolio terms
portfolio_terms = [
    "derivative portfolio",
    "derivative instruments",
    "{swap_type} portfolio",
    "portfolio",
]

# Portfolio state verbs
portfolio_verbs = [
    "consists of",
    "includes",
    "included",
    "are comprised of",
    "are composed of",
    "consisted of",
    "comprised of",
    "composed of",
]

# Phrases for describing a historical instrument
historical_instrument_phrases = [
    "contracted in a prior year",
    "from a prior period",
    "entered into in a previous year",
    "originating from a prior reporting period",
]

# Outstanding active state descriptors
state_descriptors = ["outstanding", "active", "remaining", "open"]

# Base sentence structures for notional amounts
# Placeholders: {time_prefix}, {company}, {verb}, {swap_type}, {amount_connector}, {amount_str}, {hedge_designation_clause}, {result_clause}, {time_suffix}
NOTIONAL_SENTENCE_TEMPLATES = {
    "summary": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, {swap_type} {amount_connector} {amount_str} {verb} by {company}{hedge_designation_clause}{result_clause}.",
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, the {amount_prefix} of the {swap_type} was {amount_str}{result_clause}.",
        "The {amount_prefix} of the {swap_type} was {amount_str} {time_suffix}{result_clause}.",
    ],
    "new_individual": [
        "{time_prefix}, {company} {verb} new {swap_type} {amount_connector} {amount_str}{hedge_designation_clause}{result_clause}.",
        "{company} {verb} new {swap_type} {amount_connector} {amount_str} {time_suffix}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, new {swap_type} {amount_connector} {amount_str} {verb} by {company}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, a new {swap_type} was entered into with a {amount_prefix} of {amount_str}{hedge_designation_clause}{result_clause}.",
    ],
    "terminated_individual": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, {swap_type} {amount_connector} {amount_str} {verb} by {company}{hedge_designation_clause}{result_clause}.",
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, {swap_type} with a {amount_prefix} of {amount_str} were {verb}{hedge_designation_clause}{result_clause}.",
    ],
    "comparative": [
        "{company} {verb} {swap_type} {amount_connector} {amount_str}, respectively, {time_suffix}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, {company} were party to {swap_type} totaling {amount_str}, respectively{result_clause}.",
        "The aggregate {amount_prefix} of the {swap_type} were {amount_str} {time_suffix}, respectively{result_clause}.",
    ],
    "individual": [
        "{time_prefix}, {company} {verb} {swap_type} with a {amount_prefix} of {amount_str}{hedge_designation_clause}{maturity_clause}{result_clause}.",
        "A {swap_type} was {state_descriptor} {time_suffix} with a {amount_prefix} of {amount_str}{hedge_designation_clause}{maturity_clause}{result_clause}.",
    ],
    "historical_individual": [
        "A {swap_type} {historical_phrase} remains {state_descriptor}, with a {amount_prefix} of {amount_str} {time_suffix}{hedge_designation_clause}{maturity_clause}{result_clause}.",
        "{company} {verb} a {swap_type} {historical_phrase}, which had a {state_descriptor} {amount_prefix} of {amount_str} {time_suffix}{hedge_designation_clause}{maturity_clause}{result_clause}.",
        "{time_prefix}, a {swap_type} initiated in a prior period had a remaining {amount_prefix} of {amount_str}{maturity_clause}{result_clause}.",
    ],
    "comparative_no_outstanding": [
        "{time_prefix}, {company} had no {state_descriptor} {swap_type}, compared to {amount_str} in the prior year{result_clause}.",
        "There were no {state_descriptor} {swap_type} {time_suffix}, down from {amount_str} at year-end {prev_year}{result_clause}.",
    ],
    "comparative_no_prior_outstanding": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}, whereas no such instruments were {state_descriptor} in the prior year{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, {company} {verb} {swap_type} with a {amount_prefix} of {amount_str}; no comparable instruments were {state_descriptor} during {prev_year}{hedge_designation_clause}{result_clause}.",
        "The {amount_prefix} of {swap_type} was {amount_str} {time_suffix}; there were no such instruments reported in {prev_year}{result_clause}.",
    ],
}

# Templates for when no derivatives are outstanding for a given category for all years
# These templates are designed to be flexible and use other predefined template variables.
NO_INSTRUMENTS_TEMPLATES = [
    "{time_prefix}, {company} {verb} no {state_descriptor} {swap_type} to hedge against {category_risk_phrase} risk.",
    "{time_prefix}, there were no {state_descriptor} {swap_type}.",
    "{company} did not {verb} any {swap_type} {time_suffix}.",
    "As of {month} {end_day}, {year}, the amounts of {state_descriptor} {swap_type} were {immaterial_term}.",
    "There were no such {swap_type} {state_descriptor} {time_suffix}.",
    "{company} did not {verb} any {state_descriptor} {swap_type} {time_suffix}.",
    "{time_prefix}, {company} did not {verb} any {portfolio_term} for {category_risk_phrase} hedging purposes.",
    "During the period, {company} was not a party to any {swap_type}.",
    "{company} {verb} no {state_descriptor} derivative positions as of year-end {year}.",
    "No {portfolio_term} were {verb} by {company} {time_suffix} for hedging {category_risk_phrase} risk."
]


# Outstanding active state descriptors
state_descriptors = ["outstanding", "active", "remaining", "open"]

# Hedge designation phrases (optional endings)
hedge_designations = [
    "",
    "designated as hedges",
    "designated as hedging instruments",
    "not designated as hedges",
    "not designated as hedging instruments",
    "designated as {hedge_type} hedges",
    "used for hedging purposes",
    "remaining designated as hedges",
    "as part of its hedging strategy",
    "as part of its risk management strategy",
    "within its hedging program",
    "and is a highly effective {hedge_type} hedge on hedged item",
]
hedge_types = [
    "net investment",
    "fair value",
    "cash flow",
    "economic"
]

result_phrases = {
    "IR": [
        "effectively converting fixed-rate to floating-rate {debt_type}",
        "effectively converting floating-rate to fixed-rate {debt_type}",
        "effectively changes {debt_type} of {company} from a fixed rate to a floating rate of interest",
        "with quarterly settlements based on the differential between fixed and floating rates on notional amounts",
        "resulting in a decrease in interest expense of {currency_code}{amount} {money_unit}",
        "resulting in an increase in interest expense of {currency_code}{amount} {money_unit}",
        "recognizing the gains and losses on derivative instruments as an adjustment to interest expense",
        "reducing the potential impact of increases in interest rates on its interest-bearing liabilities",
        "which effectively converts the variable rate into a fixed rate of {debt_type}",
        "to hedge {currency_code}{amount} {money_unit} of various {debt_type}",
        "recognizing interest income (expense) of {currency_code}{amount} {money_unit} related to these {swap_type}",
        "to cap or fix {company}'s interest rate at {pct}% on an agreed upon principal amount of {currency_code}{amount} {money_unit}",
        "to eliminate the incremental cost if the {debt_type} were to exceed {pct}%",
        "to hedge against the possible negative effects of interest rate fluctuations on {debt_type} obligations",
        "to exchange fixed and variable rate interest payment obligations",
        "related to the anticipated issuance of {debt_type}",
        "manage its interest rate and cash flow risks associated with its {debt_type}",
        "and would receive payments on a {frequency} basis if the {debt_type}'s interest rate exceeds {pct}%",
        "with an effective fixed rate of {pct}%",
        ""
    ],
    "FX": [
        "offsetting foreign currency translation adjustments",
        "mitigating {currencies} exchange rate fluctuations on foreign currency denominated transactions",
        "with translation gains of {currency_code}{notional} {money_unit} recognized in other comprehensive income",
        "with translation losses of {currency_code}{notional} {money_unit} recognized in other comprehensive income",
        "hedging net investment in foreign operations in {geography}",
        "due to changes in foreign exchange rates and are recorded at fair value",
        "mitigating exposure to foreign currency fluctuations",
        "hedging foreign-denominated cash flows",
        "mitigating foreign exchange risk against {currencies}",
        "protecting against currency fluctuations of {currencies}",
        "protecting against exchange rate movements of {currencies}",
        "denominated in {currencies}",
        "to sell foreign currencies to {currencies}",
        "for {currencies} to hedge {pct}% of {company}'s exposure to other foreign currencies",
        ""
    ],
    "CP": [
        "offsetting {commodity} price fluctuations",
        "mitigating exposure to volatile {commodity} prices",
        "stabilizing cost of goods sold despite {commodity} price movements",
        "hedging against increases in {commodity} costs",
        "hedging against decreases in {commodity} sale prices",
        "effectively hedged volatility in {commodity} costs",
        "mitigating exposure to {commodity} price fluctuations",
        "protecting against changes in {commodity} prices",
        "protecting against {commodity} market volatility",
        "hedging against {commodity} price increases",
        "mitigating {commodity} price risk",
        "stabilizing {commodity} costs",
        "offsetting {commodity} cost fluctuations",
        "protecting against {commodity} price changes",
        "hedging against {commodity} market volatility",
        "mitigating exposure to {commodity} market fluctuations",
        "stabilizing input costs despite {commodity} price movements",
        "and may be settled upon receipt or deliery of {commodity}",
        "committing to purchase {commodity} at an agreed-upon price at a specified future date",
        "at an average price of {currency_code} {amount} per {unit}",
        "for the sale or purchase of {commodity} with other parties",
        ""
    ],
    "EQ": [
        "offsetting market value changes in the underlying equity positions",
        "mitigating exposure to equity market volatility",
        "offsetting losses on equity investments",
        "offsetting gains on equity investments",
        "hedging exposures tied to equity-based programs",
        "linked to the value of its common stock or market indices",
        ""
    ],
    "GEN": [
        "resulting in {currency_code}{amount} {money_unit} of unrealized losses recorded in accumulated OCI",
        "resulting in fair value losses recorded in equity",
        "resulting in {currency_code}{amount} {money_unit} of unrealized gains recorded in accumulated OCI",
        "resulting in fair value gains recorded in equity",
        "with changes in fair value recognized in equity",
        "with changes in fair value recognized in earnings",
        ""
    ],
}