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
                return f"{currency_symbol} {amount / divisor:.1f} {unit_word}"
    # Fallback to full numeric value with commas
    return f"{currency_symbol} {amount:,}"


def _cleanup_sentence(sentence: str) -> str:
    """Clean up sentence by removing empty placeholders and extra spaces."""
    # Add a space before a clause if the preceding character is not a space or comma
    sentence = re.sub(r"([a-zA-Z0-9,])({hedge_designation_clause}|{result_clause}|{maturity_clause})", r"\1 \2", sentence) #noqa

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

    # Correctly pluralize words ending in a consonant followed by 'y' (e.g., "company" -> "companies").
    # This avoids incorrectly changing words like "always" or "employs".
    sentence = re.sub(r"([^aeiou])ys\b", r"\1ies", sentence, flags=re.IGNORECASE)

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
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {swap_type} {amount_connector} {amount_str} {verb} by {company} {hedge_designation_clause} {result_clause}.",
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, the {amount_prefix} of the {swap_type} was {amount_str} {result_clause}.",
        "The {amount_prefix} of the {swap_type} was {amount_str} {time_suffix} {result_clause}.",
        # Using portfolio terms (ex. portfolio consists of swap)
        "{time_prefix}, {company}'s {portfolio_term} {portfolio_verb} {swap_type} has {amount_str} {hedge_designation_clause} {result_clause}."
    ],
    "new_individual": [
        "{time_prefix}, {company} {verb} new {swap_type} {amount_connector} {amount_str} {hedge_designation_clause} {result_clause}.",
        "{company} {verb} new {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, new {swap_type} {amount_connector} {amount_str} {verb} by {company} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, a new {swap_type} was entered into with a {amount_prefix} of {amount_str} {hedge_designation_clause} {result_clause}.",
    ],
    "terminated_individual": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {swap_type} {amount_connector} {amount_str} {verb} by {company} {hedge_designation_clause} {result_clause}.",
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {swap_type} with a {amount_prefix} of {amount_str} were {verb} {hedge_designation_clause} {result_clause}.",
    ],
    "comparative": [
        "{company} {verb} {swap_type} {amount_connector} {amount_str}, respectively, {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {company} were party to {swap_type} totaling {amount_str}, respectively {result_clause}.",
        "The aggregate {amount_prefix} of the {swap_type} were {amount_str} {time_suffix}, respectively {result_clause}.",
    ],
    "individual": [
        "{time_prefix}, {company} {verb} a {swap_type} with a {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "A {swap_type} was {state_descriptor} {time_suffix}, with a {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
    ],
    "historical_individual": [
        "A {swap_type} {historical_phrase} remains {state_descriptor}, with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "{company} {verb} a {swap_type} {historical_phrase}, which had a {state_descriptor} {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "{time_prefix}, a {swap_type} initiated in a prior period had a remaining {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
    ],
    "comparative_no_outstanding": [
        "{time_prefix}, {company} had no {state_descriptor} {swap_type}, compared to {amount_str} in the prior year {result_clause}.",
        "There were no {state_descriptor} {swap_type} {time_suffix}, down from {amount_str} at year-end {prev_year} {result_clause}.",
    ],
    "comparative_no_prior_outstanding": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}, whereas no such instruments were {state_descriptor} in the prior year {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {company} {verb} {swap_type} with a {amount_prefix} of {amount_str}; no comparable instruments were {state_descriptor} during {prev_year} {hedge_designation_clause} {result_clause}.",
        "The {amount_prefix} of {swap_type} was {amount_str} {time_suffix}; there were no such instruments reported in {prev_year} {result_clause}.",
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

# Templates for "no trading" policy statements
hedge_no_trading_templates = [
    "{company} does not enter into derivative transactions for trading purposes.",
    "{company}'s policy prohibits the use of derivatives for speculative or trading purposes.",
    "Derivatives are {verb} solely for hedging and risk management, not for speculative trading.",
    "{company} does not engage in derivative transactions for speculative purposes.",
    "All derivative transactions are {verb} for hedging purposes and not for trading or speculation.",
    "The use of derivatives is strictly limited to hedging activities, not for speculative trading.",
    "{company} does not utilize derivative instruments for speculative purposes.",
    "Derivatives are {verb} exclusively for hedging identified risks, not for trading gains.",
    "{company} maintains a strict policy against using derivatives for speculative trading.",
    "No derivative transactions are {verb} for trading or speculative activities.",
    "Derivatives are {verb} solely to manage exposures, not for proprietary trading.",
    "{company} prohibits speculative derivative activities.",
    "The company's derivative strategy is focused on risk mitigation, not trading.",
    "Derivatives are {verb} for hedging purposes only, not for speculation.",
    "{company} does not engage in speculative derivative transactions.",
    "All derivative activities are non-trading in nature.",
    "Derivatives are {verb} to hedge specific risks, not for market speculation.",
    "{company} has a policy against using derivatives for trading profits.",
    "The use of derivatives is restricted to hedging, excluding speculative positions.",
    "No derivatives are {verb} for trading accounts.",
    "{company} does not conduct proprietary trading in derivatives.",
    "Derivatives are {verb} exclusively for risk management, not for trading income.",
    "The company's derivative policy forbids speculative trading.",
    "All derivative transactions are {verb} for hedging purposes, not for trading purposes.",
    "{company} does not use derivatives for speculative investments.",
]

# Templates for counterparty risk policy statements
# Placeholders: {company}, {counterparty_details}, {swap_type}, {materiality}, {risk_verb}, {policy_verb}
# Note: {time_adverb} was removed as it was not being populated by the class.
hedge_counterparty_templates = [
    "Most of the counterparties to the {swap_type} are {counterparty_details} and {company} {policy_verb} the associated inherent credit risks.",
    "{company} may enter into {swap_type} contracts with {counterparty_details} and {policy_verb} counterparty credit risk on an ongoing basis.",
    "Counterparties for {swap_type} are limited to {counterparty_details} with strong credit ratings to minimize counterparty risk.",
    "Credit risk from {swap_type} is {risk_verb} by transacting only with highly-rated financial institution counterparties.",
    "{company} {risk_verb} counterparty credit exposure by diversifying its {swap_type} contracts among multiple {counterparty_details}.",
    "The majority of counterparties for {swap_type} are {counterparty_details}, and {company} {policy_verb} inherent credit risks.",
    "{company} {risk_verb} counterparty credit risk by engaging with {counterparty_details} and continuously monitoring their creditworthiness.",
    "To minimize counterparty risk, {company} restricts {swap_type} transactions to {counterparty_details} with high credit ratings.",
    "Counterparty credit risk is {risk_verb} by diversifying {swap_type} agreements across several {counterparty_details}.",
    "{company} primarily transacts with {counterparty_details} for its {swap_type}, and associated credit risks are under continuous review.",
    "Credit risk from {swap_type} is {risk_verb} by limiting transactions to {counterparty_details} with robust credit profiles.",
    "{company} ensures counterparty credit risk is {risk_verb} by diversifying its {swap_type} contracts among multiple highly-rated financial institutions.",
    "Based upon certain factors, including a review of the {swap_type} for {company}'s counterparties, {company} determined its counterparty credit risk to be {materiality}.",
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
        "{company} is exposed to market {risk_term} from changes in {ir_term}s on its {debt_type} and investment portfolios.",
        "Our financing activities, particularly our {debt_type}, expose us to {risk_term} in {ir_term}s that impact borrowing costs.",
        "{company} faces exposure to changes in market {ir_term}s affecting both its {debt_type} and interest-bearing assets.",
        "As part of its funding strategy, {company} {policy_verb} strategies to {risk_action_verb} {risk_term} in {ir_term} movements.",
        "Our exposure to {ir_term} {risk_term} arises primarily from our {debt_type} and cash management activities.",
        "{company}'s borrowing costs on its {debt_type} are influenced by changes in prevailing {ir_term} environments.",
        "{company} actively monitors and manages its exposure to {ir_term} {risk_term}.",
    ],
    "FX": [
        "{company}'s international operations in {locations} expose it to {risk_term} arising from {risk_term} in foreign currency exchange rates.",
        "Due to its global footprint, {company} is exposed to currency translation and transaction {risk_term}, particularly with the {currencies}.",
        "Our cross-border operations in {locations} result in exposure to {risk_term} in exchange rates between functional and reporting currencies such as {currencies}.",
        "Operating in multiple currencies such as {currencies}, {company} is exposed to {risk_term} in exchange rates that can affect its financial results.",
        "With significant operations in {locations}, {company} is subject to {risk_term} from {currencies} exchange rates.",
        "Our revenues, expenses, and cash flows are subject to {risk_term} due to foreign currency exchange rate changes in {currencies}.",
        "{company} operates subsidiaries in {locations}, creating exposure to foreign currency movements when their financial results are translated.",
        "Our net investment in {locations} subsidiaries expose us to {currencies}'s exchange rate {risk_term}.",
        "We are exposed to foreign currency {risk_term} on intercompany loans and transactions between our subsidiaries in {locations}.",
        "Foreign currency {risk_term} impact {company}'s consolidated financial position and cash flows.",
    ],
    "CP": [
        "{company} is exposed to market {risk_term} from changes in {commodity} prices that affect its {cost_type} and revenues.",
        "{risk_term} in {commodity} prices can impact {company}'s profitability and cost structure.",
        "As part of its operations, {company} is exposed to {risk_term} in {commodity} prices.",
        "The profitability of {company}'s operations depends in part on the stability of {commodity} prices.",
        "{company}'s cost of goods sold is affected by {risk_term} in {commodity} market prices.",
        "Our operations are subject to {risk_term} associated with changes in the prices of key commodities such as {commodity}.",
    ],
    "EQ": [
        "{company} is exposed to market {risk_term} related to {risk_term2} in the price of its common stock.",
        "{risk_term} in equity markets affects {company}'s exposure to equity-linked compensation and investment values.",
        "{company}'s share-based compensation costs are influenced by {risk_term} in its stock price and market conditions.",
        "As a publicly traded entity, {company} is exposed to {risk_term} associated with market price {risk_term2} of its shares.",
    ],
    "GEN": [
        "{company} is exposed to various market {risk_term}, including {risk_term2} in interest rates, foreign exchange rates, and commodity prices.",
        "As part of its overall risk management strategy, {company} monitors and manages exposure to {risk_term} in market conditions.",
        "Our global activities expose us to market {risk_term} that arise from {risk_term2} in economic and financial conditions worldwide.",
        "Market {risk_term} represents the potential for losses arising from {risk_term2} in market variables affecting {company}'s earnings or cash flows.",
    ],
    "FX_IR": [  # Combined context
        "{company}'s global operations expose it to various market {risk_term}, including {risk_term2} in foreign currency exchange rates and interest rates.",
        "Our business operations in multiple countries result in exposure to foreign currency exchange rate {risk_term} and {ir_term} {risk_term2}.",
        "As a global entity, {company} faces exposure to exchange rate {risk_term} and {ir_term} {risk_term2} in its operations.",
    ],
}

# Templates for generating sentences about the *purpose* or *mitigation strategy* of a hedge.
# These are often used in conjunction with a verb like "entered into" or "utilizes".
MITIGATION_TEMPLATES = {
    "IR": [
        "to {risk_action_verb} the {ir_term} characteristics of outstanding {debt_type}",
        "to {risk_action_verb} {ir_term} {risk_term} on a portion of its {debt_type}",
        "to {risk_action_verb} against the possible negative effects of {ir_term} {risk_term2} on {debt_type} obligations",
        "to convert {rate_term1} {debt_type} to {rate_term2} instruments",
        "to convert portions of {debt_type} to {rate_term1} to optimize the debt profile",
        "to adjust the effective {ir_term} composition of outstanding {debt_type}",
        "to {risk_action_verb} exposure to {risk_term} in benchmark interest rates",
        "to {risk_action_verb} {ir_term} {risk_term2} on {debt_type} obligations",
        "to {risk_action_verb} the company's borrowing costs",
        "to lock in favorable {ir_term}s prior to anticipated {debt_type} issuances",
        "to {risk_action_verb} {ir_term} {risk_term} on forecasted {debt_type} issuances",
        "to {risk_action_verb} the negative impact of {ir_term} {risk_term2} on earnings and cash flows",
        "to balance {rate_term1} and {rate_term2} obligations across the debt portfolio",
        "to {risk_action_verb} against rising {ir_term}s on planned financings",
        "to secure rates for future {debt_type} financings or fundings",
        "to {risk_action_verb} {rate_term1} exposure over the medium to long term",
        "to {risk_action_verb} {ir_term} and related credit {risk_term} on {debt_type}",
        "to optimize the {ir_term} profile of its debt portfolio",
        "to commit to future {debt_type} fundings at predetermined {ir_term}s",
        "to {risk_action_verb} market {risk_term} in investment purchases and sales",
        "to {risk_action_verb} interest costs and overall financing {risk_term}",
        "to {risk_action_verb} credit exposure",
    ],
    "FX": [
        "to {risk_action_verb} {currencies} translation exposure",
        "to {risk_action_verb} foreign borrowings",
        "to {risk_action_verb} exposure to foreign currency {risk_term} on cross-border transactions in {geography}",
        "to {risk_action_verb} forecasted foreign currency revenues",
        "to {risk_action_verb} translation {risk_term} of foreign subsidiaries located in {geography}",
        "to {risk_action_verb} anticipated foreign currency purchases in {currencies}",
        "to {risk_action_verb} against {risk_term2} in foreign currency receivables",
        "to {risk_action_verb} forecasted foreign currency cash flows",
        "to {risk_action_verb} currency {risk_term} such as {currencies}",
        "to {risk_action_verb} forecasted foreign currency expenditures",
        "to {risk_action_verb} currency-denominated obligations",
        "to {risk_action_verb} foreign currency exposures",
        "to {risk_action_verb} forecasted foreign currency transactions",
        "to {risk_action_verb} foreign exchange rate exposures in {currencies}",
        "to {risk_action_verb} intercompany transactions in {currencies}",
        "to {risk_action_verb} intercompany exposures from operations in {geography}",
        "to {risk_action_verb} currency-denominated cash flows in {currencies}",
        "to {risk_action_verb} receivables and payables for foreign currencies",
        "to {risk_action_verb} exposure related to certain foreign currency commitments denominated in {currencies}",
    ],
    "CP": [
        "to {risk_action_verb} {commodity} price {risk_term}",
        "to {risk_action_verb} {commodity} exposures",
        "to {risk_action_verb} forecasted {commodity} purchases or sales",
        "to {risk_action_verb} {risk_term} in {commodity} prices",
        "for {commodity} risk management",
        "to {risk_action_verb} {risk_term2} in {commodity} costs",
        "to {risk_action_verb} {commodity} price exposure",
        "to {risk_action_verb} {commodity} procurement",
        "to {risk_action_verb} risks from {commodity} price swings",
        "to {risk_action_verb} against {commodity} market {risk_term}",
        "to lock in pricing",
        "to {risk_action_verb} input costs",
        "to {risk_action_verb} its exposure to {commodity} price increases",
        "to commit to purchase {commodity} at an agreed-upon price at a specified future date",
        "to {risk_action_verb} the impact of {risk_term} for {commodity} sales from storage",
    ],
    "EQ": [
        "to manage exposure to changes in the market price of its common stock and related equity-based compensation costs",
        "to hedge variability in compensation expense associated with changes in share price",
        "to mitigate exposure to equity price movements",
        "to manage market risks associated with fluctuations in stock price",
        "to offset potential volatility from changes in share price",
        "to {risk_action_verb} {risk_term} in reported expenses arising from equity-linked compensation",
        "as economic hedges of share price exposure",
        "to {risk_action_verb} the market price {risk_term} associated with stock-based compensation plans",
        "to {risk_action_verb} equity-related market {risk_term}",
        "to {risk_action_verb} {risk_term2} related to equity-linked compensation obligations",
        "to {risk_action_verb} share price exposure",
        "to {risk_action_verb} {risk_term} in stock-based compensation expense",
        "to {risk_action_verb} {risk_term2} in equity valuation",
        "to {risk_action_verb} exposure to its common stock value",
        "to {risk_action_verb} equity-linked exposures",
        "to {risk_action_verb} {risk_term} in stock-based compensation costs",
        "to {risk_action_verb} {risk_term2} in the value of its shares",
        "as part of its equity risk management strategy",
        "to {risk_action_verb} share price {risk_term}",
        "to {risk_action_verb} exposure to its common stock price {risk_term2}",
    ],
    "GEN": [
        "to {risk_action_verb} against unfavorable {risk_term} in market conditions",
        "to {risk_action_verb} {risk_term2} associated with forecasted transactions",
        "to {risk_action_verb} overall earnings {risk_term}",
        "to enhance stability of financial performance",
        "to {risk_action_verb} {risk_term} exposure across multiple markets",
        "to {risk_action_verb} overall exposure to {risk_term2} in market variables",
        "to {risk_action_verb} the company's aggregate {risk_term} profile",
        "to align with the company's overall risk management objectives",
        "to {risk_action_verb} {risk_term} in cash flows and earnings",
        "to {risk_action_verb} exposures arising from normal business operations",
        "to {risk_action_verb} exposure to price, rate, or market {risk_term2}",
        "to provide more predictable financial outcomes",
        "to {risk_action_verb} cash flows from core operations",
        "to {risk_action_verb} adverse effects of market {risk_term}",
        "to {risk_action_verb} forecasted or anticipated transactions",
        "to support financial risk management strategies",
        "to {risk_action_verb} exposures in accordance with the company's hedging policy",
        "to {risk_action_verb} exposure to broad market {risk_term2}",
        "to {risk_action_verb} the impact of market {risk_term} on reported results",
        "to {risk_action_verb} the impact of changing economic conditions",
        "as part of a risk management program",
    ],
}
