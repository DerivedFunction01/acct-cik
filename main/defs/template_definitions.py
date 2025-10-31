# New imports for generate_notional_sentence
import re
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
    # Add a space before a clause if the preceding character is not a space or comma
    sentence = re.sub(r"([a-zA-Z0-9,])({hedge_designation_clause}|{result_clause}|{maturity_clause})", r"\1 \2", sentence)

    # Remove any remaining optional placeholders that weren't filled
    sentence = sentence.replace("{hedge_designation_clause}", "")
    sentence = sentence.replace("{result_clause}", "")
    sentence = sentence.replace("{maturity_clause}", "")
    sentence = sentence.replace("{time_suffix}", "")  # If not used, remove it

    # Clean up multiple spaces
    while "  " in sentence:
        sentence = sentence.replace("  ", " ")

    # Clean up comma/space issues more aggressively
    sentence = sentence.replace(" ,", ",")
    sentence = sentence.replace(" ,", ",")
    sentence = sentence.replace(",,", ",")
    sentence = sentence.replace(" .", ".")

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
        "effectively converting {rate_term1} to {rate_term2} {debt_type}",
        "with {frequency} settlements based on the differential between {rate_term1} and {rate_term2} on notional amounts",
        "resulting in a {gain_loss} in interest expense of {formatted_amount}",
        "{mitigation_verb} the potential impact of {gain_loss} in {ir_term}s on its interest-bearing liabilities",
        "which effectively converts the {rate_term1} into a {rate_term2} of {debt_type}",
        "to hedge {formatted_amount} of various {debt_type}",
        "{financial_outcome_verb} interest income (expense) of {formatted_amount} related to these {swap_type}",
        "to cap or fix {company}'s {ir_term} at {pct}% on an agreed upon principal amount of {formatted_amount}",
        "to eliminate the {ir_term} if the {debt_type} were to exceed {pct}%",
        "{mitigation_verb} against the possible negative effects of {ir_term} {risk_term} on {debt_type} obligations",
        "to exchange {rate_term1} and {rate_term2} interest payment obligations",
        "related to the anticipated issuance of {debt_type}",
        "{mitigation_verb} its {ir_term} and cash flow {risk_term} associated with its {debt_type}",
        "with an effective {rate_term1} of {pct}%",
        "",
    ],
    "FX": [
        "{mitigation_verb} foreign currency translation adjustments",
        "{mitigation_verb} {currencies} exchange rate {risk_term} on foreign currency denominated transactions",
        "with translation {gain_loss} of {formatted_amount} {outcome_location}",
        "hedging net investment in foreign operations in {geography}",
        "due to changes in foreign exchange rates and are recorded at fair value",
        "{mitigation_verb} exposure to foreign currency {risk_term}",
        "hedging foreign-denominated cash flows",
        "{mitigation_verb} foreign exchange {risk_term} against {currencies}",
        "denominated in {currencies}",
        "to sell foreign currencies to {currencies}",
        "for {currencies} to hedge {pct}% of {company}'s exposure to other foreign currencies",
        "",
    ],
    "CP": [
        "{mitigation_verb} {commodity} price {risk_term}",
        "{mitigation_verb} {risk_term} to volatile {commodity} prices",
        "{mitigation_verb} cost of goods sold despite {commodity} price {risk_term}",
        "{mitigation_verb} against {gain_loss} in {commodity} costs",
        "effectively hedged {risk_term} in {commodity} costs",
        "{mitigation_verb} exposure to {commodity} price {risk_term}",
        "{mitigation_verb} {commodity} costs",
        "and may be settled upon receipt or deliery of {commodity}",
        "committing to purchase {commodity} at an agreed-upon price at a specified future date",
        "at an average price of {formatted_amount} per {unit}",
        "for the sale or purchase of {commodity} with other parties",
        "",
    ],
    "EQ": [
        "{mitigation_verb} market value changes in the underlying equity positions",
        "{mitigation_verb} exposure to equity market {risk_term}",
        "{mitigation_verb} {gain_loss} on equity investments",
        "hedging exposures tied to equity-based programs",
        "linked to the value of its common stock or market indices",
        "",
    ],
    "GEN": [
        "resulting in {formatted_amount} of unrealized {gain_loss} {outcome_location}",
        "resulting in fair value {gain_loss} {outcome_location}",
        "with changes in fair value {outcome_location}",
        "",
    ],
}

# Templates for generating policy and risk context sentences
POLICY_CONTEXT_TEMPLATES = {
    "IR": [
        "{company} is exposed to market risks from changes in {ir_term}s on its {debt_type} and investment portfolios.",
        "Our financing activities, particularly our {debt_type}, expose us to {risk_term} in {ir_term}s that impact borrowing costs.",
        "{company} faces exposure to changes in market {ir_term}s affecting both its {debt_type} and interest-bearing assets.",
        "As part of its funding strategy, {company} {policy_verb} strategies to {risk_action_verb} {risk_nature_phrases} {ir_term} movements.",
        "Our exposure to {ir_term} {risk_term} arises primarily from our {debt_type} and cash management activities.",
        "{company}'s borrowing costs on its {debt_type} are influenced by changes in prevailing {ir_term} environments.",
        "{company} actively monitors and manages its exposure to {ir_term} {risk_term}.",
    ],
    "FX": [
        "{company}'s international operations expose it to risks arising from {risk_term} in foreign currency exchange rates.",
        "Due to its global footprint, {company} is exposed to currency translation and transaction risks, particularly with the {currencies}.",
        "Our cross-border operations in {locations} result in exposure to changes in exchange rates between functional and reporting currencies such as {currencies}.",
        "Operating in multiple currencies such as {currencies}, {company} is exposed to {risk_term} in exchange rates that can affect its financial results.",
        "With significant operations in {locations}, {company} is subject to {risk_term} from {currencies} exchange rates.",
        "Our revenues, expenses, and cash flows are subject to {risk_term} due to foreign currency exchange rate changes in {currencies}",
        "Foreign currency {risk_term} impact {company}'s consolidated financial position and cash flows.",
    ],
    "CP": [
        "{company} is exposed to market risks from changes in {commodity} prices that affect its {cost_type} and revenues.",
        "Fluctuations in {commodity} prices can impact {company}'s profitability and cost structure.",
        "As part of its operations, {company} is exposed to {risk_term} in {commodity} prices.",
        "The profitability of {company}'s operations depends in part on the stability of {commodity} prices.",
        "{company}'s cost of goods sold is affected by {risk_term} in {commodity} market prices.",
        "Our operations are subject to risks associated with changes in the prices of key commodities such as {commodity}.",
    ],
    "EQ": [
        "{company} is exposed to market risks related to {risk_term} in the price of its common stock.",
        "Volatility in equity markets affects {company}'s exposure to equity-linked compensation and investment values.",
        "{company}'s share-based compensation costs are influenced by changes in its stock price and market conditions.",
        "As a publicly traded entity, {company} is exposed to risks associated with market price {risk_term} of its shares.",
    ],
    "GEN": [
        "{company} is exposed to various market risks, including changes in interest rates, foreign exchange rates, and commodity prices.",
        "As part of its overall risk management strategy, {company} monitors and manages exposure to {risk_term} in market conditions.",
        "Our global activities expose us to market risks that arise from changes in economic and financial conditions worldwide.",
        "Market risk represents the potential for losses arising from {risk_term} in market variables affecting {company}'s earnings or cash flows.",
    ],
    "FX_IR": [ # Combined context
        "{company}'s global operations expose it to various market risks, including {risk_term} in foreign currency exchange rates and interest rates.",
        "Our business operations in multiple countries result in exposure to foreign currency exchange rate {risk_term} and {ir_term} {risk_term}.",
        "As a global entity, {company} faces exposure to exchange rate {risk_term} and {ir_term} risks in its operations.",
    ],
}