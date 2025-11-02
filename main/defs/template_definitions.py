# New imports for generate_notional_sentence
from dataclasses import dataclass
import random
from typing import Dict, List, Literal, Tuple
from defs.notional_definitions import NotionalEvidence
from defs.instrument_definitions import NotionalInstrument
from defs.common_data import DERIVATIVE_COMPONENTS
from defs.function_definitions import _format_single_notional

# Time prefixes for point-in-time statements (e.g., aggregate summaries, single year)
point_in_time_prefixes = [
    "as of {month} {end_day}, {year}", # This is used by generate_notional_sentence
    "at year-end {year}",
    "as of year-end {year}",
    "at the end of {year}",
    "at the close of {year}",
    "as of {month} {year}",
    "at {month} {end_day}, {year}",
    "at {month} {year}",
]

# Time prefixes for period-of-time statements (e.g., new or terminated instruments, single year)
period_of_time_prefixes = [
    "during {year}", # This is used by generate_notional_sentence
    "in {year}",
    "throughout {year}",
    "during {month} {year}",
    "in {month} {year}",
    "in the {quarter} quarter of {year}",
    "during the {quarter} quarter of {year}",
]

# Multi-year time prefixes (patterns for 2 or 3 years)
multi_year_time_prefixes = {
    "two_year": [
        "at {month} {end_day}, {year} and {prev_year}, respectively", # This is used by generate_notional_sentence
        "as of {month} {end_day}, {year} and {prev_year}",
        "at {month} {year} and {prev_year}, respectively",
        "as of {month} {end_day}, {year} and {prev_year}, respectively",
        "for the years ended {month} {end_day}, {year} and {prev_year}",
    ],
    "three_year": [
        "at {month} {end_day}, {year}, {prev_year}, and {prev2_year}, respectively", # This is used by generate_notional_sentence
        "as of {month} {end_day}, {year}, {prev_year}, and {prev2_year}, respectively",
        "at {month} {year}, {prev_year}, and {prev2_year}, respectively",
        "for the years ended {month} {end_day}, {year}, {prev_year}, and {prev2_year}",
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

# Base sentence structures for notional amounts
# Placeholders: {time_prefix}, {company}, {verb}, {swap_type}, {amount_connector}, {amount_str}, {hedge_designation_clause}, {result_clause}, {time_suffix}
NOTIONAL_SENTENCE_TEMPLATES = {
    # For aggregate summaries of multiple instruments in a single period.
    "summary": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {swap_type} {amount_connector} {amount_str} was {verb} by {company} {hedge_designation_clause} {result_clause}.",
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, the {amount_prefix} of the {swap_type} was {amount_str} {result_clause}.",
        "The {amount_prefix} of the {swap_type} was {amount_str} {time_suffix} {result_clause}.",
        # Using portfolio terms (ex. portfolio consists of swap)
        "{time_prefix}, {company}'s {portfolio_term} {portfolio_verb} {swap_type} has {amount_str} {hedge_designation_clause} {result_clause}.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause}.",
    ],
    # For describing an instrument that was newly created in the reporting period.
    "new_individual": [
        "{time_prefix}, {company} {verb} a {swap_type} {amount_connector} {amount_str} {hedge_designation_clause} {result_clause}.",
        "{company} {verb} a {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, a {swap_type} {amount_connector} {amount_str} was {verb} by {company} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, a {swap_type} was entered into with a {amount_prefix} of {amount_str} {hedge_designation_clause} {result_clause}.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} {verb} a {swap_type} with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause}.",
    ],
    # For instruments that ended, matured, or were settled during a period.
    "terminated_individual": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}.",
        "{time_prefix}, a {swap_type} with a {amount_prefix} of {amount_str} was {verb} by {company}.",
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix}.",
        "{time_prefix}, {swap_type} with a {amount_prefix} of {amount_str} were {verb}.",
        "The {swap_type}, which had a {amount_prefix} of {amount_str}, reached {termination_noun} in {year}.",
        "In {year}, the {swap_type} {verb}, concluding with a {amount_prefix} of {amount_str}.",
        "The {swap_type} {verb} in {year}, having a {amount_prefix} of {amount_str} at {termination_noun}.",
    ],
    # For comparing values across multiple years (e.g., "...totaling $100M and $120M, respectively...").
    "comparative": [
        "{company} {verb} {swap_type} {amount_connector} {amount_str}, respectively, {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {company} were party to {swap_type} totaling {amount_str}, respectively {result_clause}.",
        "The aggregate {amount_prefix} of the {swap_type} were {amount_str} {time_suffix}, respectively {result_clause}.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} held {swap_type} with aggregate {amount_prefix}s of {amount_str}, respectively, {time_suffix}.",
    ],
    # For describing a single, active instrument in the current period.
    "individual": [
        "{time_prefix}, {company} {verb} a {swap_type} with a {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "A {swap_type} was {state_descriptor} {time_suffix}, with a {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} {verb} a {swap_type} with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause}.",
    ],
    # For describing an instrument that existed in a prior year but is still active.
    "historical_individual": [
        "A {swap_type} {historical_phrase} remains {state_descriptor}, with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "{company} {verb} a {swap_type} {historical_phrase}, which had a {state_descriptor} {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "{time_prefix}, a {swap_type} initiated {historical_phrase} had a remaining {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} a {swap_type} {historical_phrase} remains {state_descriptor}, with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause}.",
    ],
    # For the first mention of an instrument in a historical timeline, describing its creation.
    "inception": [
        "In {year}, {company} {verb} a {swap_type} with an initial {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "A {swap_type} was initiated by {company} in {year}, with a starting {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
    ],
    # For subsequent mentions of an instrument in a historical timeline.
    "continuing": [
        "By {year}, its {amount_prefix} was {amount_str}.",
        "As of {year}, the {swap_type} had a {amount_prefix} of {amount_str}.",
        "The {amount_prefix} of this {swap_type} stood at {amount_str} in {year}.",
        "In {year}, the position's {amount_prefix} was {amount_str}.",
    ],
    # For when a portion of an instrument was settled, reducing its notional amount.
    "partial_settlement": [
        "In {year}, a portion of the {swap_type} was {verb}, reducing its {amount_prefix} to {amount_str} {result_clause}.",
        "A partial {termination_noun} occurred in {year}, bringing the remaining {amount_prefix} to {amount_str} {result_clause}.",
        "By {year}, after a partial {termination_noun}, the {state_descriptor} {amount_prefix} was {amount_str} {result_clause}.",
        "{company} partially {verb} its {swap_type} position in {year}, with the remaining {amount_prefix} at {amount_str} {result_clause}.",
        "Following a partial {termination_noun} in {year}, the {swap_type} had an {state_descriptor} {amount_prefix} of {amount_str} {result_clause}.",
        "The {amount_prefix} of the {swap_type} was {comparison_phrase} {amount_str} in {year} due to a partial {termination_noun} {result_clause}.",
    ],
    # For cases where there were instruments in a prior year, but none in the current year.
    "comparative_no_outstanding": [
        "{time_prefix}, {company} had no {state_descriptor} {swap_type}, compared to {amount_str} in the prior year.",
        "There were no {state_descriptor} {swap_type} {time_suffix}, down from {amount_str} at year-end {prev_year}.",
        "All {swap_type} {historical_phrase}, which had a {amount_prefix} of {amount_str}, were terminated or expired by year-end {year}.",
        "{company} did not hold any {swap_type} as of {month} {end_day}, {year}, whereas the prior year-end balance was {amount_str}.",
    ],
    # For cases where there are instruments now, but there were none in the prior year.
    "comparative_no_prior_outstanding": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str} {hedge_designation_clause} {result_clause}, whereas no such instruments were {state_descriptor} in the prior year.",
        "{time_prefix}, {company} {verb} {swap_type} with a {amount_prefix} of {amount_str} {hedge_designation_clause} {result_clause}; no comparable instruments were {state_descriptor} during {prev_year}.",
        "The {amount_prefix} of {swap_type} was {amount_str} {time_suffix} {result_clause}; there were no such instruments reported in {prev_year}.",
        "{company} initiated the use of {swap_type} {time_suffix}, with an outstanding {amount_prefix} of {amount_str}, where none existed in the prior year.",
        "Activity in {swap_type} commenced {time_suffix}, resulting in a {amount_prefix} of {amount_str}, up from zero in the previous year.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} {verb} {swap_type} with a {amount_prefix} of {amount_str} {time_suffix}, whereas no such instruments were held in the prior year.",
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
    "{company} may enter into {swap_type} contracts with {counterparty_details} and {policy_verb} counterparty credit risk on an ongoing basis.", # `policy_verb` should be a monitoring verb like 'monitors'
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
        "effectively converting a {rate_term1} to a {rate_term2} on its {debt_type}",
        "with {frequency} settlements based on the differential between {rate_term1} and {rate_term2} rates",
        "resulting in a {gain_loss} in interest expense of {formatted_amount}",
        "which {mitigation_verb} the potential impact of {gain_loss} in {ir_term} on its interest-bearing liabilities",
        "which effectively converts the {rate_term1} into a {rate_term2} of {debt_type}",
        "to hedge {formatted_amount} of various {debt_type}",
        "which {financial_outcome_verb} interest income (expense) of {formatted_amount} related to these {swap_type}", # `financial_outcome_verb` should be 'generated', 'resulted in'
        "to cap our {ir_term} at {pct}% on a principal amount of {formatted_amount}",
        "to eliminate the incremental {ir_term} if the {debt_type} were to exceed {pct}%",
        "which {mitigation_verb} against the possible negative effects of {ir_term} {risk_term} on {debt_type} obligations",
        "to exchange {rate_term1} and {rate_term2} interest payment obligations",
        "related to the anticipated issuance of {debt_type}",
        "which {mitigation_verb} its {ir_term} and cash flow {risk_term} associated with its {debt_type}",
        "with an effective {rate_term1} of {pct}%",
        "",
    ],
    "FX": [
        "which {mitigation_verb} foreign currency translation adjustments",
        "which {mitigation_verb} {currencies} exchange rate {risk_term} on foreign currency denominated transactions",
        "with translation {gain_loss} of {formatted_amount} {outcome_location}",
        "hedging net investment in foreign operations in {geography}",
        "due to changes in foreign exchange rates and are recorded at fair value",
        "which {mitigation_verb} exposure to foreign currency {risk_term}",
        "hedging foreign-denominated cash flows",
        "which {mitigation_verb} foreign exchange {risk_term} against {currencies}",
        "denominated in {currencies}",
        "to sell foreign currencies to {currencies}",
        "for {currencies} to hedge {pct}% of our exposure to other foreign currencies",
        "",
    ],
    "CP": [
        "which {mitigation_verb} {commodity} price {risk_term}",
        "which {mitigation_verb} {risk_term} to volatile {commodity} prices",
        "which {mitigation_verb} cost of goods sold despite {commodity} price {risk_term}",
        "which {mitigation_verb} against {gain_loss} in {commodity} costs",
        "effectively hedged {risk_term} in {commodity} costs",
        "which {mitigation_verb} exposure to {commodity} price {risk_term}",
        "which {mitigation_verb} {commodity} costs",
        "and may be settled upon receipt or deliery of {commodity}",
        "committing to purchase {commodity} at an agreed-upon price at a specified future date",
        "at an average price of {formatted_amount} per {unit}",
        "for the sale or purchase of {commodity} with other parties",
        "",
    ],
    "EQ": [
        "which {mitigation_verb} market value changes in the underlying equity positions",
        "which {mitigation_verb} exposure to equity market {risk_term}",
        "which {mitigation_verb} {gain_loss} on equity investments",
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
        "{company} is exposed to various market {risk_term} arising from the normal course of operations.",
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
        "to {risk_action_verb} risks associated with the prices of {commodity}",
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

# ==============================================================================
# OPTIONAL DETAIL TEMPLATES (Gains/Losses, Fair Value, etc.)
# Sourced from old/template/w_emb.py and other files.
# ==============================================================================

OPTIONAL_DETAIL_TEMPLATES = {
    "gain_loss": [
        "For the year ended {month} {end_day}, {year}, the Company recognized a {gain_loss} of {amount_str} on these {swap_type}s in {location}.",
        "The change in fair value of the {swap_type} resulted in a {gain_loss} of {amount_str} for the year, which was recorded in {location}.",
        "Unrealized {gain_loss}es on the {swap_type} portfolio totaled {amount_str} for the year ended {month} {end_day}, {year}.",
        "During {year}, the Company recorded a {gain_loss} of {amount_str} related to the change in fair value of its derivative instruments.",
        "The mark-to-market adjustment on the {swap_type}s contributed a {gain_loss} of {amount_str} to {location} in {year}.",
    ],
    "fair_value_level": [
        "The fair value of these {swap_type}s is determined using Level {level_num} inputs, such as {level_input_examples}.",
        "These derivative instruments are classified as Level {level_num} within the fair value hierarchy.",
        "The Company estimates the fair value of its {swap_type}s based on Level {level_num} inputs, which include {level_input_examples}.",
        "As of {month} {end_day}, {year}, the {swap_type}s were measured at fair value on a recurring basis using Level {level_num} inputs.",
    ],
    "settlement_payment": [
        "Under the terms of the {swap_type}, settlements occur {frequency}, with net payments of {amount_str} made during {year}.",
        "The {swap_type} requires {frequency} cash settlement of the net differential between the fixed and floating rates.",
        "During {year}, the Company {paid_received} a net amount of {amount_str} related to the settlement of its {swap_type}s.",
        "Net cash {paid_received} on the {swap_type}s for the year ended {month} {end_day}, {year} was {amount_str}.",
    ],
}

fair_value_level_examples = {
    1: "quoted prices in active markets for identical assets",
    2: "quoted prices for similar instruments, interest rate curves, and credit spreads",
    3: "internally developed models, discounted cash flow analyses, and other unobservable inputs",
}

# ==============================================================================
# HEDGE POLICY TEMPLATES (Ported from old/template/hedges.py)
# ==============================================================================

# --- NEW: Factored-out components for more variety ---

hedge_accounting_subjects = [
    "Hedge accounting",
    "The application of hedge accounting",
    "Hedge accounting treatment",
]

hedged_item_subjects = [
    "a forecasted transaction",
    "the hedged forecasted transaction",
    "the hedged item",
    "the underlying forecasted transaction",
]

deferred_gain_loss_subjects = [
    "any related unrealized {gain_loss}",
    "accumulated {gain_loss}",
    "deferred {gain_loss}",
    "amounts previously deferred in other comprehensive income",
    "any accumulated {gain_loss}",
]
# ==============================================================================
# HEDGE POLICY TEMPLATES (Ported from old/template/hedges.py)
# ==============================================================================

# --- Documentation Policy (Specific - mentions swap_type) ---
specific_hedge_documentation_templates = [
    "For a {swap_type} to qualify as a hedge at inception and throughout the hedged period, {company} formally document the nature and relationships between the hedging instruments and hedged item.",
    "For a {swap_type} designated as a {hedge_type} hedge, the {gain_loss} is {financial_outcome_verb} in earnings in the period of change together with the offsetting loss or gain on the risk being hedged.",
    "{company} prepares formal documentation for all hedges, detailing the hedging {swap_type}, hedged item, and risk management strategy.",
    "At hedge inception, {company} documents the relationship between the {swap_type} and the hedged item, including the risk management objective.",
    "Hedge documentation includes the risk management objective, hedging {swap_type}, and hedged item, prepared at inception.",
]

# --- Documentation Policy (General) ---
general_hedge_documentation_templates = [
    "{company} maintains formal documentation of all hedging relationships, including the risk management objective and strategy for undertaking the hedge.",
    "Hedge accounting requires formal documentation at inception describing the hedging relationship and {company}'s risk management objectives.",
    "{company} document our hedging relationships and risk management strategies at inception in accordance with applicable accounting standards.",
    "{company} maintains detailed documentation of hedging relationships to comply with hedge accounting requirements.",
    "{company} formally document all hedging relationships at inception, including the strategy and objectives for risk management.",
    "{company} records formal documentation for hedges, outlining the relationship and risk management strategy.",
    "{company} document the hedging relationship and risk management objectives at the start of each hedge in line with accounting standards.",
]

# --- Effectiveness Policy (Specific - mentions swap_type or metric) ---
specific_hedge_effectiveness_templates = [
    "{company} {verb}, both at inception and on an on-going basis, whether the {swap_type} that are utilized in {hedge_type} hedging transactions are highly effective in offsetting the {metric} of hedged items.",
    "{company} {verb} {frequency} tests of hedge effectiveness for {swap_type} to offset changes in {metric}.",
    "{company} {verb} {swap_type} effectiveness {frequency} to ensure they offset {metric} as intended.",
    "{company} {verb} the effectiveness of {swap_type} {frequency} to offset changes in {metric} per {standard}.",
]

# --- Effectiveness Policy (General) ---
general_hedge_effectiveness_templates = [
    "{company} {verb} hedge effectiveness {frequency} to ensure derivatives continue to meet the criteria for hedge accounting.",
    "Hedge effectiveness is {verb} {frequency} using {method} in accordance with {standard}.",
    "{company} {verb} {frequency} assessments of hedge effectiveness to determine whether hedging relationships remain highly effective.",
    "{company} {verb} hedge effectiveness {frequency} in accordance with {standard}.",
    "{company} {verb} hedge effectiveness {frequency} using {method} to ensure compliance with {standard}.",
    "Hedge effectiveness is {verb} {frequency} to verify that derivatives qualify for hedge accounting under {standard}.", # 'is' is not a placeholder, but it works with all verbs in assessment_verbs
    "{company} {verb} effectiveness of {swap_type} {frequency} using {method} per {standard}.",
    "{company} {verb} {frequency} hedge effectiveness tests using {method} to comply with {standard}.",
    "Hedge effectiveness is {verb} {frequency} for {swap_type} to meet {standard} requirements.",
    "{company} {verb} {frequency} assessments of {swap_type} effectiveness using {method}.",
    "{company} {verb} hedge effectiveness {frequency} for {swap_type} in accordance with {standard}.",
    "{company} {verb} {swap_type} effectiveness {frequency} to confirm compliance with {standard}.", # 'verb' is already a placeholder
    "{company}'s hedge positions in {swap_type} are continually {verb} to determine whether new or offsetting transactions are required.",
]

# --- Ineffectiveness Policy ---
hedge_ineffectiveness_policy_templates = [
    "{company} {verb} hedge ineffectiveness {frequency} and {financial_outcome_verb} the {gain_loss} related to the ineffective portion of its {swap_type}, if any, to current earnings.",
    "Any hedge ineffectiveness is {financial_outcome_verb} immediately in earnings in the period identified.",
    "Ineffectiveness related to {swap_type}, if present, is {verb} {frequency} and {financial_outcome_verb} in the consolidated statements of operations.",
    "{company} {financial_outcome_verb} any ineffective portion of hedging instruments in current period earnings.",
    "{gain_loss} from the ineffective portion of {swap_type} are {financial_outcome_verb} in earnings {frequency}.",
    "{company} {verb} hedge ineffectiveness on its {swap_type} and {financial_outcome_verb} any such amounts in the statement of operations for the relevant period.",
    "Ineffective amounts arising from hedging relationships are {financial_outcome_verb} in earnings as part of the assessment {frequency}.",
    "{company} {verb} hedge effectiveness on its {swap_type} and immediately {financial_outcome_verb} any ineffectiveness in income.",
    "Hedge ineffectiveness, when identified, is {financial_outcome_verb} in earnings for the reporting period in which it occurs.",
    "The ineffective portion of designated {swap_type} hedges is calculated and {financial_outcome_verb} in current earnings {frequency}.",
]

# --- Discontinuation Policy ---
hedge_discontinuation_templates = [
    "If {company} determine that {hedged_item_subject} is no longer probable of occurring, {company} {termination_verb} hedge accounting and {deferred_gain_loss_subject} on the derivative instrument is {financial_outcome_verb} in current earnings.",
    "{hedge_accounting_subject} is {termination_verb} if {hedged_item_subject} is no longer expected to occur, with {deferred_gain_loss_subject} {financial_outcome_verb} to earnings.",
    "When {hedged_item_subject} becomes improbable, {company} dedesignates the hedging relationship and {financial_outcome_verb} {deferred_gain_loss_subject} immediately.",
    "If {hedged_item_subject} fails to occur, {deferred_gain_loss_subject} are {financial_outcome_verb} to current period earnings.",
    "{company} ceases hedge accounting for derivatives when {hedged_item_subject} is no longer expected to occur, with {deferred_gain_loss_subject} {financial_outcome_verb} in earnings.",
    "{deferred_gain_loss_subject} on discontinued hedges are {financial_outcome_verb} immediately in the consolidated statements of operations.",
    "Upon dedesignation of a hedge, the ineffective and deferred portions of derivative instruments are {financial_outcome_verb} in current period earnings.",
    "{hedge_accounting_subject} is discontinued when {hedged_item_subject} is no longer probable, with {deferred_gain_loss_subject} {financial_outcome_verb} to income.",
    "If {hedged_item_subject} did not materialize, accumulated OCI amounts for the hedge are {financial_outcome_verb} to current earnings.",
    "{company} derecognizes hedge accounting when criteria are no longer met, and any associated {gain_loss} are {financial_outcome_verb} in the period of discontinuation.",
    "{swap_type} being accounted for as a {hedge_type} hedge did not qualify for hedge accounting because it is no longer highly effective in offsetting {metric} of a hedged item.",
    "If the {swap_type} expires or is sold, terminated or exercised, or if management determines that designation of the {swap_type} as a hedge instrument is no longer appropriate, hedge accounting would be discontinued.",
    "When a hedge is discontinued because it is no longer effective, the derivative is no longer designated as a hedge, and subsequent changes in fair value are {financial_outcome_verb} in earnings.",
    "For discontinued {hedge_type} hedges, any gains or losses previously deferred in other comprehensive income are recognized in earnings when the hedged transaction affects earnings.",
    "{company} may terminate or de-designate a {swap_type} at any time, at which point hedge accounting is discontinued prospectively.",
]

# --- General Accounting Policy ---
hedge_accounting_policy_templates = [
    "Changes in the fair value of {swap_type} are recorded each period in current earnings or other comprehensive income (loss), depending on whether a derivative instrument is designated as part of a hedging transaction and, if it is, the type of hedging transaction.",
    "{swap_type} are measured at fair value with {gain_loss} {financial_outcome_verb} in earnings or accumulated other comprehensive income based on hedge designation.",
    "{company} accounts for {swap_type} at fair value, with changes in fair value {financial_outcome_verb} in either net income or other comprehensive income depending on the nature of the hedging relationship.",
    "Fair value changes in {swap_type} are reflected in the financial statements through either the income statement or other comprehensive income, based on whether hedge accounting is applied.",
    "{company} {financial_outcome_verb} {swap_type} at fair value, with changes {financial_outcome_verb} in earnings or OCI depending on hedge designation.",
    "Changes in derivative fair values are {financial_outcome_verb} in net income or accumulated OCI, based on the type of hedge and its designation.",
    "{swap_type} are accounted for at fair value, with {gain_loss} {financial_outcome_verb} in earnings or other comprehensive income per hedge accounting rules.",
    "{company} {financial_outcome_verb} fair value changes of {swap_type} in either current earnings or OCI, depending on the hedging relationship.",
    "{gain_loss} on {swap_type} are {financial_outcome_verb} currently in earnings.",
    "The accounting for the changes in the fair value of the {swap_type} depends on the intended use of the {swap_type} and the resulting designation.",
    "For a {swap_type} that did not qualify as a {hedge_type} hedge, the change in {hedge_type} is {financial_outcome_verb} currently in net income.",
    "If the derivative such as {swap_type} is a hedge, changes in the fair value of derivatives may be {financial_outcome_verb} in other comprehensive income until the hedged item is {financial_outcome_verb} in earnings.",
]

# --- Shared placeholders for policy templates ---
hedge_methods = [
    "regression analysis",
    "the dollar-offset method",
    "quantitative analysis",
    "statistical methods",
    "prospective and retrospective testing",
]

hedge_standards = ["ASC 815", "applicable accounting guidance", "U.S. GAAP", "accounting standards", "ASU 2017-12", "Topic 815"]

# For simplicity in the AccountingPolicySentence class, we can combine the split templates.
hedge_documentation_templates = general_hedge_documentation_templates + specific_hedge_documentation_templates
hedge_effectiveness_policy_templates = general_hedge_effectiveness_templates + specific_hedge_effectiveness_templates

@dataclass
class Table:
    """
    Generates formatted text-based tables for displaying derivative instrument data.
    """

    def __init__(
        self,
        instruments: List[NotionalInstrument],
        yearly_data: Dict,
        reporting_month: str,
        reporting_day: int,
        reporting_year: int,
        notional_multiplier: int,
        currency_symbol: str,
        prefer_abbreviated: bool,
        category: str,
    ):
        self.instruments = instruments
        self.month = reporting_month
        self.day = reporting_day
        self.notional_multiplier = notional_multiplier # for (in millions, etc)
        self.yearly_data = yearly_data
        self.reporting_year = reporting_year
        self.currency_symbol = currency_symbol
        self.prefer_abbreviated = prefer_abbreviated
        self.category = category

    def money_unit(self) -> str:
        amount_to_string = {
         1_000_000_000_000: "trillions",
         1_000_000_000: "billions",
         1_000_000: "millions",
         1_000: "thousands"
        }
        if self.notional_multiplier in amount_to_string:
            return amount_to_string[self.notional_multiplier]
        return "in millions"

    def build(self) -> Tuple[str, List[NotionalEvidence]]:
        """
        Selects a table format at random and builds the table string.
        """
        formats = [
            self._build_year_over_year_table,
            self._build_notional_vs_fair_value_table,
            # self._build_maturity_grouping_table, # This one is aggregate, doesn't produce individual evidence
            self._build_asset_liability_fair_value_table,
        ]
        chosen_format = random.choice(formats)
        return chosen_format()

    def _get_value(
        self, instrument: NotionalInstrument, year: int, value_type: Literal["notional", "fair_value"]
    ) -> int:
        """Helper to get notional or fair value for a given year."""
        notional = instrument.notional_history.get(year, 0)
        if value_type == "fair_value":
            # Simulate a fair value that is a small fraction of the notional
            return max(0, int(notional * random.uniform(0.01, 0.1)))
        return notional

    def _build_year_over_year_table(self) -> Tuple[str, List[NotionalEvidence]]:
        """
        Builds a table comparing notional/fair values year-over-year.
        Format:
            Instrument | Year 1 | Year 2
        """
        evidence_list = []
        year1 = self.reporting_year
        year2 = self.reporting_year - 1
        value_type_str = random.choice(["Notional Amount", "Fair Value"])
        value_type: Literal["notional", "fair_value"] = "fair_value" if "Fair" in value_type_str else "notional"

        header = f"| {'Instrument':<45} | {value_type_str} {year1} | {value_type_str} {year2} |"
        separator = "-" * len(header)
        rows = [header, separator]

        # Use a set to avoid describing the same instrument type multiple times
        described_types = set()

        for inst in self.instruments:
            # Use alias for subsequent mentions of the same type
            name_to_use = inst.instrument_type
            if inst.instrument_type in described_types:
                name_to_use = inst.instrument_alias
            described_types.add(inst.instrument_type)

            val1 = self._get_value(inst, year1, value_type)
            val2 = self._get_value(inst, year2, value_type)

            # Only include instruments that were active in at least one of the years
            if val1 == 0 and val2 == 0:
                continue

            val1_str = _format_single_notional(
                val1, inst.symbol, self.prefer_abbreviated, False
            )
            val2_str = _format_single_notional(
                val2, inst.symbol, self.prefer_abbreviated, False
            )

            row_str = f"| {name_to_use:<45} | {val1_str:>15} | {val2_str:>15} |"
            rows.append(row_str)

            # Create evidence for the current year if value is > 0
            if val1 > 0:
                evidence_list.append(NotionalEvidence(
                    instrument_id=inst.instrument_id,
                    status="individual",
                    category=inst.category,
                    notional=val1,
                    year=year1,
                    instrument_type=name_to_use,
                    reporting_year=self.reporting_year,
                    value_type=value_type,
                    currency=inst.currency,
                    sentence_type="individual", # From a table
                ))

        if len(rows) <= 2:  # Only header and separator
            return "", []

        # Add a title
        category_map = {
            "IR": "Interest Rate",
            "FX": "Foreign Exchange",
            "CP": "Commodity",
            "EQ": "Equity",
            "GEN": "Derivative",
        }
        title = f"Outstanding {category_map.get(self.category, 'Derivative')} {random.choice(DERIVATIVE_COMPONENTS["suffixes"])} (in {self.currency_symbol} {self.money_unit()})"
        return f"{title}\n" + "\n".join(rows), evidence_list

    def _build_notional_vs_fair_value_table(self) -> Tuple[str, List[NotionalEvidence]]:
        """
        Builds a table comparing notional vs. fair value, grouped by year.
        Format:
            Year 20XX
            Instrument | Notional | Fair Value
        """
        evidence_list = []
        year1 = self.reporting_year
        year2 = self.reporting_year - 1
        all_rows = []

        category_map = {
            "IR": "Interest Rate",
            "FX": "Foreign Exchange",
            "CP": "Commodity",
            "EQ": "Equity",
            "GEN": "Generic",
        }
        title = f"Notional and Fair Value of {category_map.get(self.category, 'Derivative')} {random.choice(DERIVATIVE_COMPONENTS["suffixes"])}"
        all_rows.append(title)

        for year in [year1, year2]:
            instruments_in_year = [
                inst
                for inst in self.instruments
                if inst.notional_history.get(year, 0) > 0
            ]

            if not instruments_in_year:
                continue

            all_rows.append(f"\nAs of {self.month} {self.day}, {year} (in {self.money_unit()})")
            header = (
                f"| {'Instrument':<45} | {'Notional Amount':>20} | {'Fair Value':>20} |"
            )
            separator = "-" * len(header)
            all_rows.extend([header, separator])

            described_types = set()
            for inst in instruments_in_year:
                name_to_use = inst.instrument_type
                if inst.instrument_type in described_types:
                    name_to_use = inst.instrument_alias
                described_types.add(inst.instrument_type)

                notional_val = self._get_value(inst, year, "notional")
                fair_val = self._get_value(inst, year, "fair_value")

                notional_str = _format_single_notional(
                    notional_val, inst.symbol, self.prefer_abbreviated, no_unit_word=True
                )
                fair_val_str = _format_single_notional(
                    fair_val, self.currency_symbol, self.prefer_abbreviated, no_unit_word=True
                )

                row_str = (
                    f"| {name_to_use:<45} | {notional_str:>20} | {fair_val_str:>20} |"
                )
                all_rows.append(row_str)

                # Create evidence for the current year if value is > 0
                if year == self.reporting_year and notional_val > 0:
                    evidence_list.append(NotionalEvidence(
                        instrument_id=inst.instrument_id,
                        status="individual",
                        category=inst.category,
                        notional=notional_val,
                        year=self.reporting_year,
                        instrument_type=name_to_use,
                        reporting_year=self.reporting_year,
                        value_type="notional",
                        currency=inst.currency,
                        sentence_type="individual", # From a table
                    ))

        if len(all_rows) <= 1:  # Only title
            return "", []

        return "\n".join(all_rows), evidence_list

    def _build_maturity_grouping_table(self) -> Tuple[str, List[NotionalEvidence]]:
        """
        Builds a table grouping instruments by maturity year ranges.
        Format:
            Maturity      | Notional Amount
        """
        maturity_groups = {
            "Less than 1 year": 0,
            "1-3 years": 0,
            "3-5 years": 0,
            "More than 5 years": 0,
        }

        active_instruments = [
            inst
            for inst in self.instruments
            if inst.notional_history.get(self.reporting_year, 0) > 0
        ]

        if not active_instruments:
            return "", []

        for inst in active_instruments:
            years_to_maturity = inst.maturity_year - self.reporting_year if inst.maturity_year else 100

            if years_to_maturity <= 1:
                maturity_groups["Less than 1 year"] += inst.notional_history.get(
                    self.reporting_year, 0
                )
            elif 1 < years_to_maturity <= 3:
                maturity_groups["1-3 years"] += inst.notional_history.get(
                    self.reporting_year, 0
                )
            elif 3 < years_to_maturity <= 5:
                maturity_groups["3-5 years"] += inst.notional_history.get(
                    self.reporting_year, 0
                )
            else:
                maturity_groups["More than 5 years"] += inst.notional_history.get(
                    self.reporting_year, 0
                )

        title = f"Notional Amount by Maturity as of {self.month} {self.day}, {self.reporting_year}"
        header = f"| {'Maturity':<20} | {'Notional Amount':>20} |"
        separator = "-" * len(header)
        rows = [title, header, separator]

        for group, total_notional in maturity_groups.items():
            if total_notional > 0:
                notional_str = _format_single_notional(
                    total_notional, self.currency_symbol, self.prefer_abbreviated, True
                )
                row_str = f"| {group:<20} | {notional_str:>20} |"
                rows.append(row_str)

        if len(rows) <= 3:  # Only title, header, and separator
            return "", []

        return "\n".join(rows), [] # No individual evidence from this aggregate table

    def _build_asset_liability_fair_value_table(self) -> Tuple[str, List[NotionalEvidence]]:
        """
        Builds a table showing derivative assets and liabilities.
        Format:
            Instrument | Asset Fair Value | Liability Fair Value
        """
        year = self.reporting_year
        active_instruments = [
            inst
            for inst in self.instruments
            if inst.notional_history.get(year, 0) > 0
        ]

        if not active_instruments:
            return "", []

        title = f"Fair Value of Derivative {random.choice(DERIVATIVE_COMPONENTS["suffixes"])} as of {self.month} {self.day}, {self.reporting_year}"
        header = f"| {'Instrument':<45} | {'Asset Fair Value':>20} | {'Liability Fair Value':>22} |"
        separator = "-" * len(header)
        rows = [title, header, separator]

        for inst in active_instruments:
            fair_value = self._get_value(inst, year, "fair_value")
            # Randomly decide if the fair value is an asset or liability
            is_asset = random.random() < 0.5

            asset_val_str = "-"
            liab_val_str = "-"

            if is_asset:
                asset_val_str = _format_single_notional(
                    fair_value, self.currency_symbol, self.prefer_abbreviated, True
                )
            else:
                liab_val_str = _format_single_notional(
                    fair_value, self.currency_symbol, self.prefer_abbreviated, True
                )

            row_str = f"| {inst.instrument_type:<45} | {asset_val_str:>20} | {liab_val_str:>22} |"
            rows.append(row_str)

        if len(rows) <= 3:
            return "", []

        return "\n".join(rows), [] # This table shows fair value, not notional, so we don't create NotionalEvidence
