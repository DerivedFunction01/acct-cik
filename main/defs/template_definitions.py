# New imports for generate_notional_sentence
from dataclasses import dataclass
import random
from typing import Dict, List, Literal, Tuple, Union
from defs.notional_definitions import NotionalEvidence
from defs.instrument_definitions import NotionalInstrument
from defs.common_data import DERIVATIVE_COMPONENTS
from defs.fx_data import CurrencyExposure, ForeignCurrencyHedgedItem
from defs.table_definitions import FinancialStatementTable, GenericTable
from defs.function_definitions import _format_single_notional, _get_correct_rounding

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
        "{time_prefix}, {company} {verb} {swap_type} {hedge_designation_clause} {result_clause}.",  # no amount
        "{time_prefix}, {swap_type} {amount_connector} {amount_str} was {verb} by {company} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {swap_type} was {verb} by {company} {hedge_designation_clause} {result_clause}.",  # no amount
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{company} {verb} {swap_type} {time_suffix} {hedge_designation_clause} {result_clause}.",  # no amount
        "{time_prefix}, the {amount_prefix} of the {swap_type} was {amount_str} {result_clause}.",
        "The {amount_prefix} of the {swap_type} was {amount_str} {time_suffix} {result_clause}.",
        # Using portfolio terms (ex. portfolio consists of swap)
        "{time_prefix}, {company}'s {portfolio_term} {portfolio_verb} {swap_type} has {amount_str} {hedge_designation_clause} {result_clause}.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause}.",
        "{begin_mitigation} {company} {verb} {swap_type} {time_suffix} {hedge_designation_clause}.",  # no amount
    ],
    # For describing an instrument that was newly created in the reporting period.
    "new_individual": [
        "{time_prefix}, {company} {verb} __article__ {swap_type} {amount_connector} {amount_str} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {company} {verb} __article__ {swap_type} {hedge_designation_clause} {result_clause}.",  # no amount
        "{company} {verb} __article__ {swap_type} {amount_connector} {amount_str} {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{company} {verb} __article__ {swap_type} {time_suffix} {hedge_designation_clause} {result_clause}.",  # no amount
        "{time_prefix}, __article__ {swap_type} {amount_connector} {amount_str} was {verb} by {company} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, __article__ {swap_type} was {verb} by {company} {hedge_designation_clause} {result_clause}.",  # no amount
        "{time_prefix}, __article__ {swap_type} was {verb} with a {amount_prefix} of {amount_str} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, __article__ {swap_type} was {verb} {hedge_designation_clause} {result_clause}.",  # no amount
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} {verb} __article__ {swap_type} with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause}.",
        "{begin_mitigation} {company} {verb} __article__ {swap_type} {time_suffix} {hedge_designation_clause}.",  # no amount
    ],
    # For instruments that ended, matured, or were settled during a period.
    "terminated_individual": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}.",
        "{time_prefix}, {company} {verb} {swap_type}.",  # no amount
        "{time_prefix}, __article__ {swap_type} with a {amount_prefix} of {amount_str} was {verb} by {company}.",
        "{time_prefix}, __article__ {swap_type} was {verb} by {company}.",  # no amount
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix}.",
        "{company} {verb} {swap_type} {time_suffix}.",  # no amount
        "{time_prefix}, {swap_type} with a {amount_prefix} of {amount_str} were {verb}.",
        "{time_prefix}, {swap_type} were {verb}.",  # no amount
        "The {swap_type}, which had a {amount_prefix} of {amount_str}, reached {termination_noun} in {year}.",
        "The {swap_type} reached {termination_noun} in {year}.",  # no amount
        "In {year}, the {swap_type} {verb}, concluding with a {amount_prefix} of {amount_str}.",
        "The {swap_type} {verb} in {year}, having a {amount_prefix} of {amount_str} at {termination_noun}.",
    ],
    # For comparing values across multiple years (e.g., "...totaling $100M and $120M, respectively...").
    "comparative": [
        "{company} {verb} {swap_type} {amount_connector} {amount_str}, {time_suffix} {hedge_designation_clause} {result_clause}.",
        "{time_prefix}, {company} {verb} {swap_type} totaling {amount_str}, respectively {result_clause}.",
        "The aggregate {amount_prefix} of the {swap_type} were {amount_str} {time_suffix}, {result_clause}.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} held {swap_type} with aggregate {amount_prefix}s of {amount_str}, {time_suffix}.",
    ],
    # For describing a single, active instrument in the current period.
    "individual": [
        "{time_prefix}, {company} {verb} __article__ {swap_type} with a {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "{time_prefix}, {company} {verb} __article__ {swap_type} {hedge_designation_clause} {maturity_clause} {result_clause}.",  # no amount
        "__article__ {swap_type} was {state_descriptor} {time_suffix}, with a {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "__article__ {swap_type} was {state_descriptor} {time_suffix}, {hedge_designation_clause} {maturity_clause} {result_clause}.",  # no amount
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} {verb} __article__ {swap_type} with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause}.",
        "{begin_mitigation} {company} {verb} __article__ {swap_type} {time_suffix} {hedge_designation_clause} {maturity_clause}.",  # no amount
    ],
    # For describing an instrument that existed in a prior year but is still active.
    "historical_individual": [
        "__article__ {swap_type} {historical_phrase} remains {state_descriptor}, with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "{company} {verb} __article__ {swap_type} {historical_phrase}, which had a {state_descriptor} {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "{time_prefix}, __article__ {swap_type} initiated {historical_phrase} had a remaining {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} __article__ {swap_type} {historical_phrase} remains {state_descriptor}, with a {amount_prefix} of {amount_str} {time_suffix} {hedge_designation_clause} {maturity_clause}.",
    ],
    # For the first mention of an instrument in a historical timeline, describing its creation.
    "inception": [
        "In {year}, {company} {verb} __article__ {swap_type} with an initial {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
        "__article__ {swap_type} was initiated by {company} in {year}, with a starting {amount_prefix} of {amount_str} {hedge_designation_clause} {maturity_clause} {result_clause}.",
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
        "The {amount_prefix} of the {swap_type} was {amount_str} in {year} due to a partial {termination_noun} {result_clause}.",
    ],
    # For cases where there were instruments in a prior year, but none in the current year.
    "comparative_no_outstanding": [
        "{time_prefix}, {company} {verb} no {state_descriptor} {swap_type}, {comparison_phrase} {amount_str} in the prior year.",
        "There were no {state_descriptor} {swap_type} {time_suffix}, {comparison_phrase} {amount_str} at year-end {prev_year}.",
        "All {swap_type} {historical_phrase}, which had a {amount_prefix} of {amount_str}, reached {termination_noun} by year-end {year}.",
        "{company} did not {verb} any {swap_type} as of {month} {end_day}, {year}, {comparison_phrase} the prior year-end balance was {amount_str}.",
    ],
    # For cases where there are instruments now, but there were none in the prior year.
    "comparative_no_prior_outstanding": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str} {hedge_designation_clause} {result_clause}, {comparison_phrase} no such instruments were {state_descriptor} in the prior year.",
        "{time_prefix}, {company} {verb} {swap_type} {hedge_designation_clause} {result_clause}, {comparison_phrase} no such {swap_type} were {state_descriptor} at {prev_year}.",  # no amount
        "{time_prefix}, {company} {verb} {swap_type} with a {amount_prefix} of {amount_str} {hedge_designation_clause} {result_clause}; no comparable instruments were {state_descriptor} during {prev_year}.",
        "The {amount_prefix} of {swap_type} was {amount_str} {time_suffix} {result_clause}; there were no such instruments {verb} in {prev_year}.",
        "{company} initiated the use of {swap_type} {time_suffix}, with an outstanding {amount_prefix} of {amount_str}, {comparison_phrase} none existing at {prev_year}.",
        "Activity in {swap_type} commenced {time_suffix}, resulting in a {amount_prefix} of {amount_str}, {comparison_phrase} zero in the previous year.",
        # --- NEW: begin_mitigation at the beginning ---
        "{begin_mitigation} {company} {verb} {swap_type} with a {amount_prefix} of {amount_str} {time_suffix}, {comparison_phrase} no such instruments were held in the prior year.",
        "{begin_mitigation} {company} {verb} {swap_type} {time_suffix}, {comparison_phrase} no such {swap_type} were {verb} in {prev_year}.",
    ],
}

# Templates for when no derivatives are outstanding for a given category for all years
# These templates are designed to be flexible and use other predefined template variables.
NO_INSTRUMENTS_TEMPLATES = [
    "{time_prefix}, {company} {verb} no {state_descriptor} {swap_type} to {risk_management_verb} against {category_risk_phrase} risk.",
    "{time_prefix}, there were no {state_descriptor} {swap_type}.",
    "{company} did not {verb} any {swap_type} {time_suffix}.",
    "As of {month} {end_day}, {year}, the amounts of {state_descriptor} {swap_type} were {immaterial_term}.",
    "There were no such {swap_type} {state_descriptor} {time_suffix}.",
    "{company} did not {verb} any {state_descriptor} {swap_type} {time_suffix}.",
    "{time_prefix}, {company} did not {verb} any {portfolio_term} for {category_risk_phrase} hedging purposes.",
    "During the period, {company} was not a party to any {swap_type}.",
    "{company} {verb} no {state_descriptor} derivative positions as of year-end {year}.",
    "No {portfolio_term} were {verb} by {company} {time_suffix} for hedging {category_risk_phrase} risk.",
]

# Templates for "no trading" policy statements
hedge_no_trading_templates = [
    "{company} does not {verb} derivative transactions for trading purposes.",
    "{company}'s policy prohibits the {verb} of derivatives for speculative or trading purposes.",
    "Derivatives are {verb} solely for hedging and risk management, not for speculative trading.",
    "{company} does not {verb} derivative transactions for speculative purposes.",
    "All derivative transactions are {verb} for hedging purposes and not for trading or speculation.",
    "The use of derivatives is strictly limited to hedging activities, not for speculative trading.",
    "{company} does not {verb} derivative instruments for speculative purposes.",
    "Derivatives are {verb} exclusively for hedging identified risks, not for trading gains.",
    "{company} maintains a strict policy against using derivatives for speculative trading.",
    "No derivative transactions are {verb} for trading or speculative activities.",
    "Derivatives are {verb} solely to manage exposures, not for proprietary trading.",
    "{company} prohibits speculative derivative activities.",
    "The company's derivative strategy is focused on risk mitigation, not trading.",
    "Derivatives are {verb} for hedging purposes only, not for speculation.",
    "{company} does not {verb} speculative derivative transactions.",
    "All derivative activities are non-trading in nature.",
    "Derivatives are {verb} to hedge specific risks, not for market speculation.",
    "{company} has a policy against using derivatives for trading profits.",
    "The use of derivatives is restricted to hedging, excluding speculative positions.",
    "No derivatives are {verb} for trading accounts.",
    "{company} does not conduct proprietary trading in derivatives.",
    "Derivatives are {verb} exclusively for risk management, not for trading income.",
    "The company's derivative policy forbids speculative trading.",
    "All derivative transactions are {verb} for hedging purposes, not for trading purposes.",
    "{company} does not {verb} derivatives for speculative investments.",
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
    "{hedged} designated as {hedge_type} hedges",
    "{hedged} designated as {hedge_type} hedging instruments",
    "{hedged} designated as {hedge_type} hedges",
    "{hedged} used for {hedge_type} hedging purposes",
    "remaining {hedged} designated as {hedge_type} hedges",
    "as {hedged} part of its {hedge_type} hedging strategy",
    "as {hedged} part of its risk management strategy",
    "{hedged} within its {hedge_type} hedging program",
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
        "{company}'s international operations in {geography} expose it to {risk_term} arising from {risk_term} in foreign currency exchange rates.",
        "Due to its global footprint, {company} is exposed to currency translation and transaction {risk_term}, particularly with the {currencies}.",
        "Our cross-border operations in {geography} result in exposure to {risk_term} in exchange rates between functional and reporting currencies such as {currencies}.",
        "Operating in multiple currencies such as {currencies}, {company} is exposed to {risk_term} in exchange rates that can affect its financial results.",
        "With significant operations in {geography}, {company} is subject to {risk_term} from {currencies} exchange rates.",
        "Our revenues, expenses, and cash flows are subject to {risk_term} due to foreign currency exchange rate changes in {currencies}.",
        "{company} operates subsidiaries in {geography}, creating exposure to foreign currency movements when their financial results are translated.",
        "Our net investment in {geography} subsidiaries expose us to {currencies}'s exchange rate {risk_term}.",
        "We are exposed to foreign currency {risk_term} on intercompany loans and transactions between our subsidiaries in {geography}.",
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
        "to {risk_action_verb} forecasted foreign currency revenues in {currencies}",
        "to {risk_action_verb} translation {risk_term} of foreign subsidiaries located in {geography}",
        "to {risk_action_verb} anticipated foreign currency purchases in {currencies}",
        "to {risk_action_verb} against {risk_term2} in foreign currency receivables",
        "to {risk_action_verb} forecasted foreign currency cash flows in {currencies}",
        "to {risk_action_verb} currency {risk_term} such as {currencies}",
        "to {risk_action_verb} forecasted foreign currency expenditures",
        "to {risk_action_verb} currency-denominated obligations",
        "to {risk_action_verb} foreign currency exposures in {geography}",
        "to {risk_action_verb} forecasted foreign currency transactions",
        "to {risk_action_verb} foreign exchange rate exposures in {currencies}",
        "to {risk_action_verb} intercompany transactions in {currencies}",
        "to {risk_action_verb} intercompany exposures from operations in {geography}",
        "to {risk_action_verb} currency-denominated cash flows in {currencies}",
        "to {risk_action_verb} receivables and payables for foreign currencies in {currencies}",
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
    "For __article__ {swap_type} to qualify as a hedge at inception and throughout the hedged period, {company} formally document the nature and relationships between the hedging instruments and hedged item.",
    "For __article__ {swap_type} designated as a {hedge_type} hedge, the {gain_loss} is {financial_outcome_verb} in earnings in the period of change together with the offsetting loss or gain on the risk being hedged.",
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
    "{company} may terminate or de-designate __article__ {swap_type} at any time, at which point hedge accounting is discontinued prospectively.",
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
    "For __article__ {swap_type} that did not qualify as a {hedge_type} hedge, the change in {hedge_type} is {financial_outcome_verb} currently in net income.",
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


# ==============================================================================
# ACCOUNTING STANDARDS TEMPLATES (Ported from old/template/hedges.py and other.py)
# ==============================================================================

shared_issuers = [
    "FASB",
    "Financial Accounting Standards Board",
    "SEC",
    "IASB",
    "International Accounting Standards Board",
    "PCAOB",
    "FASB's Emerging Issues Task Force",
]

other_topics = [
    "revenue recognition",
    "lease accounting",
    "credit losses",
    "financial instruments",
    "business combinations",
    "stock compensation",
    "fair value measurements",
    "income taxes",
    "segment reporting",
    "consolidation",
    "intangible assets",
    "debt modifications",
    "defined benefit plans",
    "collaborative arrangements",
    "insurance contracts",
]

other_standards = [
    "ASU 2016-02",  # Leases (ASC 842)
    "ASU 2014-09",  # Revenue Recognition (ASC 606)
    "ASU 2016-13",  # Credit Losses (ASC 326)
    "ASC 842",  # Leases
    "ASC 606",  # Revenue
    "ASC 326",  # Credit Losses
    "ASC 718",  # Stock Compensationg
    "ASC 805",  # Business Combinations
    "ASC 740",  # Income Taxes
    "ASC 820",  # Fair Value Measurement
    "Topic 842",  # Leases
    "Topic 606",  # Revenue Recognition
]

shared_purposes = [
    "improve financial reporting and provide additional disclosures",
    "align accounting practices with economic substance",
    "enhance transparency and comparability",
    "simplify the accounting model",
    "provide clarification on implementation issues",
    "expand presentation and disclosure requirements",
    "address practice diversity and implementation questions",
    "converge U.S. GAAP with international standards",
    "expand the related presentation and disclosure requirements",
    "change how companies assess effectiveness",
    "eliminate the separate measurement and reporting of hedge ineffectiveness",
]

shared_additional_features_templates = [
    "The guidance also {policy_feature}",
    "Additionally, the standard {policy_feature}",
    "The new guidance {policy_feature}",
    "The update also {policy_feature}",
]

shared_effective_date_templates = [
    "The guidance is effective in fiscal year {year}, with early adoption permitted",
    "The standard is effective for fiscal years beginning after {month} {day}, {year}",
    "This guidance becomes effective for annual periods beginning after {month} {end_day}, {year}, with early application permitted",
    "The amendments are effective for fiscal years, and interim periods within those years, beginning after {month} {end_day}, {year}",
    "Effective date is for annual reporting periods beginning after {month} {end_day}, {year}",
    "{company} must adopt this guidance no later than fiscal year {year}",
]

shared_adoption_status_templates = [
    "{company} adopted this guidance on {month} {day}, {year} using the {adoption_method}",
    "{company} adopted {standard} effective {month} {day}, {year}",
    "{company} early adopted the standard in {year}",
    "{company} will adopt the guidance in fiscal year {year}",
    "{company} is currently evaluating the impact of adopting this guidance",
    "{company} does not expect the adoption of this standard to have a material impact on its consolidated financial statements",
    "{company} adopted the new guidance prospectively",
    "The standard was adopted retrospectively with a cumulative-effect adjustment to retained earnings",
]

shared_adoption_methods = [
    "modified retrospective approach",
    "full retrospective method",
    "prospective method",
    "cumulative-effect adjustment",
    "practical expedient package",
    "modified retrospective transition method",
]

shared_adoption_impact_templates = [
    "The adoption resulted in {adoption_impact}",
    "Upon adoption, {company} recognized {adoption_impact}",
    "The cumulative effect of adoption was {adoption_impact}",
    "Implementation of the standard resulted in {adoption_impact}",
    "As a result of adoption, {adoption_impact}",
]

shared_evaluation_templates = [
    "{company} is currently evaluating the potential impact of this guidance on its consolidated financial statements and related disclosures",
    "{company} has not yet completed its assessment of the impact of adopting this standard",
    "{company} is analyzing the effects of the new guidance on its accounting policies and internal controls",
    "Management is in the process of evaluating the provisions of the standard to determine its impact",
    "{company} has established an implementation team to assess the requirements and impacts of the new guidance",
    "{company} does not expect this guidance to have a material effect on its financial position or results of operations",
]

shared_transition_templates = [
    "{company} will apply the {adoption_method} upon adoption",
    "{company} elected to apply the practical expedients available under the transition guidance",
    "{company} intends to adopt the standard using the {adoption_method} with {transition_feature}",
    "{company} selected the {adoption_method} for transition purposes",
]

shared_transition_features = [
    "the option to not restate comparative periods",
    "application of hindsight",
    "certain relief provisions",
    "portfolio-level application where appropriate",
    "use of transition practical expedients",
]

shared_disclosure_change_templates = [
    "The new standard requires additional disclosures regarding {disclosure_topic}",
    "Enhanced disclosures are required for {disclosure_topic}",
    "The guidance eliminates disclosure of {disclosure_topic} while adding requirements for {disclosure_topic2}",
    "New qualitative and quantitative disclosure requirements focus on {disclosure_topic}",
    "{company} will provide expanded disclosures about {disclosure_topic} beginning in fiscal year {year}",
]

shared_practical_expedient_templates = [
    "{company} elected to apply the practical expedient to {expedient_description}",
    "{company} utilized practical expedients available under the transition guidance, including {expedient_description}",
    "{company} did not elect the practical expedient related to {expedient_description}",
    "Available practical expedients include the option to {expedient_description}",
]

shared_recent_pronouncement_templates = [
    "Recently issued accounting pronouncements not yet adopted include {standard}, which addresses {topic}",
    "In {month} {year}, the {issuer} issued {standard} related to {topic}, which {company} will adopt in {year}",
    "Management continues to monitor new accounting pronouncements issued by the {issuer} for potential impact",
    "Other new accounting guidance issued but not yet effective is not expected to have a material impact on the consolidated financial statements",
    "{company} reviews all recently issued accounting standards to determine their applicability and impact",
]

shared_standards_templates = [
    "In {month} {year}, the {issuer} issued guidance on {topic} to {standard_purpose}",
    "The {issuer} issued {standard} in {year}, which {standard_description}",
    "New accounting guidance issued by the {issuer} in {month} {year} addresses {topic}",
    "{standard} was issued in {year} to {standard_purpose}",
    "During {year}, the {issuer} released updated guidance on {topic}",
]

# ========== HEDGING / DERIVATIVE POLICY ==========
hedging_descriptions = [
    "expand presentation and disclosure requirements, change how companies assess hedge effectiveness, and eliminate separate measurement of hedge ineffectiveness",
    "improves alignment of hedge accounting with risk management strategies",
    "modifies the treatment of fair value and cash flow hedges to reflect underlying economics",
]

hedging_additional_features = [
    "enables more financial and nonfinancial hedging strategies to become eligible for hedge accounting",
    "aligns accounting treatment with risk management activities",
    "simplifies the application of hedge accounting",
    "allows designation of component risks in nonfinancial hedges",
    "permits hedging of contractually specified components in cash flow exposures",
]

hedge_change_policy_templates = [
    "In {month} {year}, the {issuer} issued {standard} related to hedging activities. The guidance {hedge_description}. Additionally, it {hedge_feature}",
    "The {issuer} issued {standard} to address {topic}. This update {hedge_description}. The new guidance {hedge_feature}",
    "Hedging Activities: In {month} {year}, {issuer} released guidance on {topic}. It {hedge_description} and {hedge_feature}",
    "The amendment to Topic 815 {hedge_description} and {hedge_feature}. Effective for fiscal years beginning after {month} {eff_day}, {year}",
]

hedge_definition_templates = [
    '"{swap_type}" means: any {swap_definitions}',
    '"{swap_type}" refers to: {swap_definitions}',
]

hedge_additional_definition_templates = [
    "any other similar {suffix}",
    "any option to enter any {suffix}",
    "any {suffix} providing any of the foregoing",
    "any combination of the {suffix}",
    "any master agreement for any of the foregoing",
    "any confirmation for any of the foregoing",
    "any schedule for any of the foregoing",
    "any document or {suffix} evidencing any of the foregoing",
    "any {suffix} (including any guarantee or collateral agreement) with respect to any of the foregoing",
]

# ========== GENERAL ACCOUNTING POLICY ==========
general_descriptions = [
    "requires recognition of lease assets and liabilities for operating leases",
    "changes the impairment model for financial instruments to an expected credit loss model",
    "establishes a revenue recognition framework based on transfer of control",
    "updates classification and measurement guidance for financial instruments",
    "updates accounting for share-based payments",
    "clarifies business combination definition and asset vs business acquisition criteria",
    "simplifies goodwill impairment testing",
    "updates income tax recognition for intra-entity asset transfers",
]

general_additional_features = [
    "simplifies certain aspects of accounting application",
    "provides transition relief and expedients",
    "permits practical expedients for implementation",
    "reduces disclosure complexity while maintaining transparency",
    "allows entities to apply hindsight in transition",
]

general_policy_templates = [
    "In {month} {year}, the {issuer} issued {standard} addressing {topic}. The standard {policy_description}. Additionally, it {policy_feature}",
    "The {issuer} issued {standard} to {standard_purpose}. The guidance {policy_description} and {policy_feature}",
    "Accounting Update: In {month} {year}, {issuer} released {standard} covering {topic}. It {policy_description}. The update {policy_feature}",
    "During {year}, the {issuer} issued guidance under {standard} to {standard_purpose}. {policy_description}. Additionally, it {policy_feature}",
]


hedge_topics = [
    "derivatives and hedging",
    "hedging activities",
    "cash flow hedges",
    "fair value hedges",
]
def _group_instruments_by_type(
    instruments: List[NotionalInstrument],
) -> Dict[Tuple[str, str, str], Dict[str, Union[str, int, float]]]:
    """
    Groups instruments by their placeholder, base type, and currency, preparing them for aggregation.

    Returns:
        A dictionary where keys are (placeholder, base_type, currency) and values are dicts
        containing aggregated values and common properties like currency and category.
    """
    grouped: Dict[Tuple[str, str, str], Dict] = {}
    for inst in instruments:
        key = (inst.placeholder, inst.base_type, inst.currency)
        if key not in grouped:
            grouped[key] = {
                "instruments": [],
                "currency": inst.currency,
                "symbol": inst.symbol,
                "category": inst.category,
            }
        grouped[key]["instruments"].append(inst)
    return grouped


@dataclass
class DerivativeTableBuilder:
    """Base class for specific table builders."""

    def __init__(
        self,
        instruments: List[NotionalInstrument],
        yearly_data: Dict,
        reporting_month: str,
        reporting_day: int,
        reporting_year: int,
        notional_multiplier: int,
        currency_symbol: str,
        currency_code: str,
        prefer_abbreviated: bool,
        preferred_negative_format: int,  # Literal[-1, 0, 1, 2]
        category: str,
    ):
        self.instruments = instruments
        self.month = reporting_month
        self.day = reporting_day
        self.notional_multiplier = notional_multiplier # for (in millions, etc)
        self.yearly_data = yearly_data
        self.reporting_year = reporting_year
        self.currency_symbol = currency_symbol
        self.currency_code = currency_code
        self.prefer_abbreviated = prefer_abbreviated
        self.preferred_negative_format = preferred_negative_format
        self.category = category

    def _money_unit(self) -> str:
        amount_to_string = {
         1_000_000_000_000: "trillions",
         1_000_000_000: "billions",
         1_000_000: "millions",
         1_000: "thousands"
        }
        if self.notional_multiplier in amount_to_string:
            return amount_to_string[self.notional_multiplier]
        return "millions"

    def choose_and_build(
        self, additional: bool = False
    ) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Selects a table format at random and builds the table string.
        This method acts as a factory for different table types.
        """
        # Store common arguments in a dictionary to avoid repetition.
        builder_args = {
            "instruments": self.instruments,
            "yearly_data": self.yearly_data,
            "reporting_month": self.month,
            "reporting_day": self.day,
            "reporting_year": self.reporting_year,
            "notional_multiplier": self.notional_multiplier,
            "currency_symbol": self.currency_symbol,
            "currency_code": self.currency_code,
            "prefer_abbreviated": self.prefer_abbreviated,
            "preferred_negative_format": self.preferred_negative_format,
            "category": self.category,
        }

        # List of builder classes
        format_builders = [
            YearOverYearTableBuilder,
            ThreeYearComparativeTableBuilder,
            NotionalVsFairValueTableBuilder,
        ]
        additional_format_builders = [
            MaturityGroupingTableBuilder,
            AssetLiabilityFairValueTableBuilder,
            AOCIReconciliationTableBuilder,
            AOCIReclassificationImpactTableBuilder,
            FairValueHierarchyTableBuilder,
            DerivativeImpactTableBuilder,
        ]
        # --- NEW: Add a specific table format for FX exposures ---
        if self.category == "FX":
            format_builders.append(FXExposureTableBuilder)

        chosen_builder_class = random.choice(additional_format_builders if additional else format_builders)
        builder_instance = chosen_builder_class(**builder_args)
        return builder_instance.build()

    def _get_units(self) -> str:
        return f"(in {self.currency_symbol} {self._money_unit()})" if self.prefer_abbreviated else f"(in {self.currency_code})"

    def _get_value(
        self, instrument: NotionalInstrument, year: int, value_type: Literal["notional", "fair_value"]
    ) -> int:
        """Helper to get notional or fair value for a given year."""
        notional = instrument.notional_history.get(year, 0)
        if value_type == "fair_value":
            # Simulate a fair value that is a small fraction of the notional
            return max(0, int(notional * random.uniform(0.01, 0.1)))
        return notional


class YearOverYearTableBuilder(DerivativeTableBuilder): # Already refactored, shown for context
    """Builds a table comparing notional/fair values year-over-year."""

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a table comparing notional/fair values year-over-year.
        Format:
            Instrument      Notional Amount 20XX    Notional Amount 20XX-1
        """ # noqa
        evidence_list = []
        year1 = self.reporting_year
        year2 = self.reporting_year - 1
        value_type_str = random.choice(["Notional Amount", "Fair Value"])
        value_type: Literal["notional", "fair_value"] = "fair_value" if "Fair" in value_type_str else "notional"

        headers = ["Instrument", f"{value_type_str} {year1}", f"{value_type_str} {year2}"]
        widths = [45, 20, 20]
        alignments = ['l', 'r', 'r'] # l for left, r for right

        data_rows = []

        # --- NEW: Group instruments by placeholder and base_type ---
        grouped_instruments: Dict[Tuple[str, str], Dict] = {}
        for inst in self.instruments:
            key = (inst.placeholder, inst.base_type)
            if key not in grouped_instruments:
                grouped_instruments[key] = {"year1_val": 0, "year2_val": 0, "currency": inst.currency, "symbol": inst.symbol, "category": inst.category}

            grouped_instruments[key]["year1_val"] += self._get_value(inst, year1, value_type)
            grouped_instruments[key]["year2_val"] += self._get_value(inst, year2, value_type)

        for (placeholder, base_type), values in grouped_instruments.items():
            val1 = values["year1_val"]
            val2 = values["year2_val"]

            if val1 == 0 and val2 == 0: continue

            # --- NEW: Create a descriptive name for the group ---
            # e.g., "Interest rate swap agreements"
            plural_suffix = "s" if not base_type.endswith("s") else ""
            name_to_use = f"{placeholder} {base_type}{plural_suffix}".strip().capitalize()

            val1_str = _format_single_notional(val1, values["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format) # type: ignore
            val2_str = _format_single_notional(val2, values["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format) # type: ignore

            row_cells = [name_to_use, val1_str, val2_str]
            data_rows.append(row_cells)

            # --- NEW: Create a single summary evidence object for the group ---
            if val1 > 0:
                evidence_notional_str = _format_single_notional(
                    val1, values["symbol"], self.prefer_abbreviated, False, negative_format=self.preferred_negative_format # type: ignore
                )
                evidence_list.append(NotionalEvidence(
                    instrument_id=None, # This is an aggregate of a group
                    status="summary",
                    category=values["category"],
                    aggregate=True,
                    notional=_get_correct_rounding(val1, self.notional_multiplier) if self.notional_multiplier > 1 else val1,
                    notional_str=evidence_notional_str,
                    year=year1,
                    instrument_type=name_to_use,
                    reporting_year=self.reporting_year, # type: ignore
                    value_type=value_type,
                    currency=values["currency"],
                    sentence_type="summary", # From a table
                ))

        if not data_rows:
            return "", [], []

        # Add a title
        category_map = {
            "IR": "Interest Rate",
            "FX": "Foreign Exchange",
            "CP": "Commodity",
            "EQ": "Equity",
            "GEN": "Derivative",
        }
        title = f"Outstanding {category_map.get(self.category, 'Derivative')} {random.choice(DERIVATIVE_COMPONENTS['suffixes'])}s {self._get_units()}"
        
        # Use the generic table builder to format the output
        generic_table = GenericTable(
            headers=headers,
            data_rows=data_rows,
            widths=widths,
            alignments=alignments,
            title=title,
        )
        table_str = generic_table.build()

        return table_str, evidence_list, []


class NotionalVsFairValueTableBuilder(DerivativeTableBuilder):
    """Builds a table comparing notional vs. fair value, grouped by year."""

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a table comparing notional vs. fair value, grouped by year.
        """
        evidence_list = []
        year1 = self.reporting_year
        year2 = self.reporting_year - 1
        all_table_parts = []

        # Process each year separately
        for year in [year1, year2]:
            instruments_in_year = [
                inst
                for inst in self.instruments
                if inst.notional_history.get(year, 0) > 0
            ]
            if not instruments_in_year:
                continue

            # Group instruments for the current year
            grouped_for_year = _group_instruments_by_type(instruments_in_year)
            data_rows = []

            for (placeholder, base_type, _), group_data in grouped_for_year.items():
                assert (
                    isinstance(group_data["category"], str)
                    and isinstance(group_data["currency"], str)
                    and isinstance(group_data["symbol"], str)
                    and isinstance(group_data["instruments"], list)
                )
                # Aggregate notional and fair values for the group
                total_notional = sum(
                    self._get_value(inst, year, "notional")
                    for inst in group_data["instruments"] if isinstance(inst, NotionalInstrument)
                )
                total_fair_value = sum(
                    self._get_value(inst, year, "fair_value")
                    for inst in group_data["instruments"]
                    if isinstance(inst, NotionalInstrument)
                )

                if total_notional == 0 and total_fair_value == 0:
                    continue

                # Create descriptive name for the group
                plural_suffix = "s" if not base_type.endswith("s") else ""
                name_to_use = (
                    f"{placeholder} {base_type}{plural_suffix}".strip().capitalize()
                )

                # Format values for the table row
                notional_str = _format_single_notional(
                    total_notional,
                    group_data["symbol"],
                    self.prefer_abbreviated,
                    True,
                    negative_format=self.preferred_negative_format,
                )
                fair_val_str = _format_single_notional(
                    total_fair_value,
                    group_data["symbol"],
                    self.prefer_abbreviated,
                    True,
                    negative_format=self.preferred_negative_format,
                )

                data_rows.append([name_to_use, notional_str, fair_val_str])

                # Create summary evidence for the current reporting year
                if year == self.reporting_year:
                    # Notional Evidence
                    evidence_notional_str = _format_single_notional(
                        total_notional, group_data["symbol"], self.prefer_abbreviated, False
                    )
                    evidence_list.append(
                        NotionalEvidence(
                            instrument_id=None, status="summary", category=group_data["category"], aggregate=True,
                            notional=_get_correct_rounding(total_notional, self.notional_multiplier),
                            notional_str=evidence_notional_str, year=year, instrument_type=name_to_use,
                            reporting_year=self.reporting_year, value_type="notional", currency=group_data["currency"],
                            sentence_type="summary",
                        )
                    )
                    # Fair Value Evidence
                    evidence_fair_val_str = _format_single_notional(
                        total_fair_value, group_data["symbol"], self.prefer_abbreviated, False
                    )
                    evidence_list.append(
                        NotionalEvidence(
                            instrument_id=None, status="summary", category=group_data["category"], aggregate=True,
                            notional=_get_correct_rounding(total_fair_value, self.notional_multiplier),
                            notional_str=evidence_fair_val_str, year=year, instrument_type=name_to_use,
                            reporting_year=self.reporting_year, value_type="fair_value", currency=group_data["currency"],
                            sentence_type="summary",
                        )
                    )

            if not data_rows:
                continue

            # Build the sub-table for the current year
            sub_table_title = f"\nAs of {self.month} {self.day}, {year}"
            headers = [
                random.choice(DERIVATIVE_COMPONENTS["suffixes"]).capitalize(),
                "Notional Amount",
                "Fair Value",
            ]
            widths = [45, 20, 20]
            alignments = ["l", "r", "r"]
            sub_table = GenericTable(headers, data_rows, widths, alignments, sub_table_title)
            all_table_parts.append(sub_table.build().replace("<TABLE>", "").replace("</TABLE>", "").replace("<CAPTION>", "").replace("</CAPTION>", ""))

        if not all_table_parts:
            return "", [], []
        category_map = {
            "IR": "Interest Rate",
            "FX": "Foreign Exchange",
            "CP": "Commodity",
            "EQ": "Equity",
            "GEN": "Derivative",
        }

        # Combine the sub-tables into a single table string with one caption
        title = f"Notional and Fair Value of {category_map.get(self.category, 'Derivative')} {random.choice(DERIVATIVE_COMPONENTS['suffixes'])}s {self._get_units()}"
        full_table_str = f"<TABLE>\n<CAPTION>\n{title}\n" + "\n".join(all_table_parts) + "\n</TABLE>"

        return full_table_str, evidence_list, []

class MaturityGroupingTableBuilder(DerivativeTableBuilder):
    """Builds a table grouping instruments by maturity year ranges."""

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a table grouping instruments by maturity year ranges.
        Format:
            Maturity       Notional Amount
        """ # noqa
        maturity_groups = {
            "Less than 1 year": 0,
            "1-3 years": 0,
            "3-5 years": 0,
            "More than 5 years": 0,
        }

        evidence_list = []
        active_instruments = [
            inst
            for inst in self.instruments
            if inst.notional_history.get(self.reporting_year, 0) > 0
        ]

        if not active_instruments:
            return "", [], []

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

        title = f"Notional Amount of {random.choice(DERIVATIVE_COMPONENTS['no_alias_types']).capitalize()} {random.choice(DERIVATIVE_COMPONENTS['suffixes'])} by Maturity as of {self.month} {self.day}, {self.reporting_year} {self._get_units()}"
        columns = ["Maturity", "Notional Amount"]
        widths = [25, 25]
        alignments = ['l', 'r']
        rows = [title]

        header_lines = GenericTable(headers=columns, data_rows=[], widths=widths, alignments=alignments, title="")._format_row_with_wrapping(columns, widths, alignments)
        rows.extend(header_lines)
        separator = "  ".join(['-' * w for w in widths])
        rows.append(separator)
        sec_tags_line = "<S>".ljust(widths[0] + 2) + "<C>".ljust(widths[1])
        rows.append(sec_tags_line)

        for group, total_notional in maturity_groups.items():
            if total_notional > 0:
                notional_str = _format_single_notional(
                    total_notional,
                    self.currency_symbol,
                    self.prefer_abbreviated,
                    True,
                    negative_format=self.preferred_negative_format,  # type: ignore
                )
                evidence_notional_str = _format_single_notional(
                    total_notional,
                    self.currency_symbol,
                    self.prefer_abbreviated,
                    False,  # Generate with unit word for sentence
                    negative_format=self.preferred_negative_format,  # type: ignore
                )
                # Create aggregate evidence for this maturity group
                evidence_list.append(NotionalEvidence(
                    instrument_id=None,  # Aggregate, no single ID
                    status="summary",
                    category=self.category,
                    notional=_get_correct_rounding(total_notional, self.notional_multiplier) if self.notional_multiplier > 1 else total_notional,
                    notional_str=evidence_notional_str,
                    year=self.reporting_year,
                    instrument_type=f"Derivatives with maturity of {group.lower()}",
                    reporting_year=self.reporting_year,
                    value_type="notional", # type: ignore
                    currency=self.currency_code,
                    sentence_type="summary", # type: ignore
                    aggregate=True,
                ))
                row_cells = [group, notional_str]
                rows.extend(GenericTable(headers=[], data_rows=[], widths=widths, alignments=alignments, title="")._format_row_with_wrapping(row_cells, widths, alignments))

        if len(rows) <= 4:  # Only title, header lines, separator, and tags
            return "", [], []

        full_table_str = "<TABLE>\n<CAPTION>\n" + "\n".join(rows) + "\n</TABLE>"
        return full_table_str, evidence_list, []

class AOCIReconciliationTableBuilder(DerivativeTableBuilder):
    """Builds a table showing the roll-forward of the AOCI balance for cash flow hedges."""

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a table showing the roll-forward of the AOCI balance for cash flow hedges.
        Format:
            AOCI - Cash Flow Hedges
            Beginning Balance  Unrealized Gains  Reclassification  Ending Balance
        """
        evidence_list = []
        year = self.reporting_year

        # This table is most relevant for categories with active cash flow hedges.
        # We'll simulate the values.
        active_instruments = [
            inst
            for inst in self.instruments
            if inst.notional_history.get(year, 0) > 0
        ]

        if not active_instruments:
            return "", [], []

        # Simulate AOCI roll-forward values
        beginning_balance = random.randint(-50, 50) * self.notional_multiplier / 100
        unrealized_gain_loss = random.randint(-75, 75) * self.notional_multiplier / 100
        reclassification = random.randint(-40, 40) * self.notional_multiplier / 100
        ending_balance = beginning_balance + unrealized_gain_loss + reclassification

        # Format values for the table
        bal_str = _format_single_notional(
            beginning_balance,
            self.currency_symbol,
            self.prefer_abbreviated,
            True,
            negative_format=self.preferred_negative_format,   # type: ignore
        )
        gain_str = _format_single_notional(
            unrealized_gain_loss,
            self.currency_symbol,
            self.prefer_abbreviated,
            True,
            negative_format=self.preferred_negative_format,  # type: ignore
        )
        reclass_str = _format_single_notional(
            reclassification,
            self.currency_symbol,
            self.prefer_abbreviated,
            True,
            negative_format=self.preferred_negative_format,  # type: ignore
        )
        end_bal_str = _format_single_notional(
            ending_balance,
            self.currency_symbol,
            self.prefer_abbreviated,
            True,
            negative_format=self.preferred_negative_format,  # type: ignore
        )

        # Build table
        title = f"Accumulated Other Comprehensive Income (AOCI) Activity for Cash Flow Hedges\nFor the Year Ended {self.month} {self.day}, {self.reporting_year} {self._get_units()}"

        rows = [
            f"Beginning Balance, {self.month} {self.day}, {year - 1:<28} {bal_str}",
            f"  Unrealized gains (losses) on {self.category} derivatives {gain_str:>22}",
            f"  Reclassification to earnings {reclass_str:>32}",
            "-" * 70,
            f"Ending Balance, {self.month} {self.day}, {year:<32} {end_bal_str}",
        ]

        # Create a single, aggregate evidence object for the table's main point
        evidence_end_bal_str = _format_single_notional(
            ending_balance, self.currency_symbol, self.prefer_abbreviated, False, negative_format=self.preferred_negative_format  # type: ignore
        )
        evidence_list.append(NotionalEvidence(
            instrument_id=None,
            status="summary",
            category=self.category,
            notional=_get_correct_rounding(ending_balance, self.notional_multiplier) if self.notional_multiplier > 1 else int(ending_balance),
            notional_str=evidence_end_bal_str,
            year=year,
            instrument_type=f"AOCI balance for {self.category} cash flow hedges",
            reporting_year=self.reporting_year,
            value_type="fair_value",  # AOCI balance is a fair value concept
            currency=self.currency_code,
            sentence_type="summary",
            aggregate=True,
        ))

        full_table_str = "<TABLE>\n<CAPTION>\n" + f"{title}\n" + "\n".join(rows) + "\n</TABLE>"
        return full_table_str, evidence_list, []

class ThreeYearComparativeTableBuilder(DerivativeTableBuilder):
    """Builds a table comparing notional/fair values over three years."""

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a table comparing notional/fair values over three years.
        Format:
            Instrument  Year 1  Year 2  Year 3
        """ # noqa
        evidence_list = []
        year1 = self.reporting_year
        year2 = self.reporting_year - 1
        year3 = self.reporting_year - 2

        available_years = list(self.yearly_data.keys())
        if not available_years or self.reporting_year - min(available_years) < 2:
            return "", [], []

        value_type_str = random.choice(["Notional Amount", "Fair Value"])
        value_type: Literal["notional", "fair_value"] = "fair_value" if "Fair" in value_type_str else "notional"

        # Define column properties
        headers = [random.choice(DERIVATIVE_COMPONENTS["suffixes"]).capitalize(), str(year1), str(year2), str(year3)]
        widths = [40, 18, 18, 18]
        alignments = ['l', 'r', 'r', 'r']
        data_rows = []

        # --- NEW: Group instruments by placeholder and base_type ---
        grouped_instruments = _group_instruments_by_type(self.instruments)

        for (placeholder, base_type, currency), group_data in grouped_instruments.items():
            # Aggregate values for the group across all three years
            assert (
                isinstance(group_data["category"], str)
                and isinstance(group_data["currency"], str)
                and isinstance(group_data["symbol"], str)
                and isinstance(group_data["instruments"], list)
            )
            val1 = sum(self._get_value(inst, year1, value_type) for inst in group_data["instruments"] if isinstance(inst, NotionalInstrument))
            val2 = sum(self._get_value(inst, year2, value_type) for inst in group_data["instruments"] if isinstance(inst, NotionalInstrument))
            val3 = sum(
                self._get_value(inst, year3, value_type)
                for inst in group_data["instruments"]
                if isinstance(inst, NotionalInstrument)
            )

            if val1 == 0 and val2 == 0 and val3 == 0:
                continue

            # Create descriptive name for the group
            plural_suffix = "s" if not base_type.endswith("s") else ""
            # --- FIX: Include currency/unit in name if it's not the default ---
            currency_note = f" ({currency})" if currency != self.currency_code else ""
            name_to_use = f"{placeholder} {base_type}{plural_suffix}{currency_note}".strip().capitalize()

            # Format values for the table row
            val1_str = _format_single_notional(val1, group_data["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format) # type: ignore
            val2_str = _format_single_notional(val2, group_data["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format) # type: ignore
            val3_str = _format_single_notional(val3, group_data["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format) # type: ignore

            row_cells = [name_to_use, val1_str, val2_str, val3_str]
            data_rows.append(row_cells)

            # --- NEW: Create a single summary evidence object for the group for the current year ---
            if val1 > 0:
                evidence_notional_str = _format_single_notional(
                    val1, group_data["symbol"], self.prefer_abbreviated, False, negative_format=self.preferred_negative_format # type: ignore
                )
                evidence_list.append(
                    NotionalEvidence(
                        instrument_id=None, # This is an aggregate of a group
                        status="summary",
                        category=group_data["category"],
                        aggregate=True,
                        notional=_get_correct_rounding(val1, self.notional_multiplier),
                        notional_str=evidence_notional_str,
                        year=year1,
                        instrument_type=name_to_use,
                        reporting_year=self.reporting_year,
                        value_type=value_type,
                        currency=group_data["currency"],
                        sentence_type="summary", # From a table
                    )
                )

        if not data_rows:
            return "", [], []

        title = f"{value_type_str}s of Outstanding {self.category} Derivatives {self._get_units()}"
        table = GenericTable(headers, data_rows, widths, alignments, title)
        full_table_str = table.build()

        return full_table_str, evidence_list, []

class AOCIReclassificationImpactTableBuilder(DerivativeTableBuilder):
    """Builds a table showing the impact of amounts reclassified from AOCI to the income statement."""
    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a table showing the impact of amounts reclassified from AOCI to the income statement.
        Format:
            Derivative Instrument  Gain/(Loss) Reclassified from AOCI  Affected Line Item in Income Statement
        """ # noqa
        evidence_list = []
        year = self.reporting_year
        active_instruments = [inst for inst in self.instruments if inst.notional_history.get(year, 0) > 0]

        if not active_instruments:
            return "", [], []

        title = f"Gains and Losses on {random.choice(hedge_types)} Hedges Reclassified from AOCI to Income\nFor the Year Ended {self.month} {self.day}, {self.reporting_year} {self._get_units()}"
        headers = [f"{random.choice(DERIVATIVE_COMPONENTS['no_alias_types']).capitalize()} {random.choice(DERIVATIVE_COMPONENTS['suffixes'])}", "Gain/(Loss) Reclassified from AOCI", "Affected Line Item in Income Statement"]
        widths = [35, 25, 40]
        alignments = ['l', 'r', 'l']
        data_rows = []

        income_statement_locations = [
            "Cost of sales", "Net sales", "Interest expense, net",
            "Other income (expense), net", "Operating expenses"
        ]

        # --- NEW: Group instruments by type ---
        grouped_instruments = _group_instruments_by_type(active_instruments)

        for (placeholder, base_type, currency), group_data in grouped_instruments.items():
            # Simulate a reclassification amount
            # This is now an aggregate amount for the group
            assert (
                isinstance(group_data["category"], str)
                and isinstance(group_data["currency"], str)
                and isinstance(group_data["symbol"], str)
                and isinstance(group_data["instruments"], list)
            )
            reclass_amount = sum(
                int(inst.notional_history.get(year, 0) * random.uniform(-0.05, 0.05))
                for inst in group_data["instruments"] if isinstance(inst, NotionalInstrument)
            )
            if reclass_amount == 0:
                continue

            # Create descriptive name for the group
            plural_suffix = "s" if not base_type.endswith("s") else ""
            currency_note = f" ({currency})" if currency != self.currency_code else ""
            name_to_use = f"{placeholder} {base_type}{plural_suffix}{currency_note}".strip().capitalize()

            reclass_str = _format_single_notional(
                reclass_amount, group_data["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format # type: ignore
            )
            location = random.choice(income_statement_locations)

            row_cells = [name_to_use, reclass_str, location]
            data_rows.append(row_cells)

            evidence_reclass_str = _format_single_notional(
                reclass_amount, group_data["symbol"], self.prefer_abbreviated, False, negative_format=self.preferred_negative_format # type: ignore
            )
            evidence_list.append(NotionalEvidence(
                instrument_id=None,
                status="summary",
                category=group_data["category"],
                aggregate=True,
                notional=_get_correct_rounding(reclass_amount, self.notional_multiplier) if self.notional_multiplier > 1 else int(reclass_amount),
                notional_str=evidence_reclass_str, year=year,
                instrument_type=f"AOCI reclassification for {name_to_use}",
                reporting_year=self.reporting_year, value_type="fair_value",
                currency=group_data["currency"], sentence_type="summary",
            ))

        if not data_rows:
            return "", [], []

        table = GenericTable(headers, data_rows, widths, alignments, title)
        full_table_str = table.build()
        return full_table_str, evidence_list, []

class FXExposureTableBuilder(DerivativeTableBuilder):
    """Builds a two-year comparative table listing the currency exposures for a specific FX instrument."""

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a two-year comparative table listing the currency exposures for a specific FX instrument.
        Format:
            Currency Exposure  Amount 20XX  Amount 20XX-1
        Returns the table string, evidence, and the list of instruments NOT used in this table.
        """
        evidence_list = []

        # Find instruments that are FX and have exposures to detail
        fx_instruments_with_exposures = [
            inst for inst in self.instruments
            if inst.category == "FX"
            and isinstance(inst.hedged_item, ForeignCurrencyHedgedItem)
            and inst.hedged_item.exposures
        ]

        if not fx_instruments_with_exposures:
            return "", [], self.instruments

        # Pick one instrument to detail its exposures
        instrument_to_detail = random.choice(fx_instruments_with_exposures)
        hedged_item: ForeignCurrencyHedgedItem = instrument_to_detail.hedged_item # type: ignore

        # --- NEW: Find the last active year to use as the primary year for the table ---
        # This allows the table to be generated even for expired instruments.
        last_active_year = None
        for year in sorted(instrument_to_detail.notional_history.keys(), reverse=True):
            if instrument_to_detail.notional_history[year] > 0:
                last_active_year = year
                break

        # If no active year is found (unlikely), fall back to the reporting year.
        year1 = last_active_year if last_active_year is not None else self.reporting_year
        year2 = year1 - 1

        title = f"Foreign Currency Exposures Hedged by {instrument_to_detail.instrument_type}"
        columns = ["Currency", f"Amount {year1}", f"Amount {year2}"]
        widths = [25, 25, 25]
        alignments = ['l', 'r', 'r']
        rows = [title]

        header_lines = GenericTable(headers=columns, data_rows=[], widths=widths, alignments=alignments, title="")._format_row_with_wrapping(columns, widths, alignments)
        rows.extend(header_lines)
        separator = "  ".join(['-' * w for w in widths])
        rows.append(separator)
        sec_tags_line = "<S>".ljust(widths[0] + 2) + "<C>".ljust(widths[1] + 2) + "<C>".ljust(widths[2])
        rows.append(sec_tags_line)
        
        for exposure in hedged_item.exposures:
            # The exposure amount from the hedged item corresponds to the last active year.
            amount_year1 = exposure.amount

            # --- NEW: Calculate prior year exposure based on the instrument's notional history ratio ---
            notional_year1 = instrument_to_detail.notional_history.get(year1, 0)
            notional_year2 = instrument_to_detail.notional_history.get(year2, 0)

            if notional_year1 > 0 and notional_year2 > 0:
                # Use the ratio of the instrument's notional change to calculate the exposure change
                ratio = notional_year2 / notional_year1
                amount_year2 = int(amount_year1 * ratio)
            else: # Fallback to simulation if history is not available for one of the years
                amount_year2 = int(amount_year1 * random.uniform(0.8, 1.2))

            amount_str1 = _format_single_notional(
                amount_year1,
                exposure.symbol,
                self.prefer_abbreviated,
                True,
                negative_format=self.preferred_negative_format,   # type: ignore
            )
            amount_str2 = _format_single_notional(
                amount_year2,
                exposure.symbol,
                self.prefer_abbreviated,
                True,
                negative_format=self.preferred_negative_format,  # type: ignore
            )

            row_cells = [exposure.full_name, amount_str1, amount_str2]
            rows.extend(GenericTable(headers=[], data_rows=[], widths=widths, alignments=alignments, title="")._format_row_with_wrapping(row_cells, widths, alignments))
            
            # --- Create evidence for BOTH years ---

            # Evidence for the primary year (year1)
            if amount_year1 > 0:
                evidence_amount_str1 = _format_single_notional(
                    amount_year1, exposure.symbol, self.prefer_abbreviated, False, negative_format=self.preferred_negative_format  # type: ignore
                )
                evidence_list.append(NotionalEvidence(
                    instrument_id=instrument_to_detail.instrument_id,
                    status="individual" if year1 == self.reporting_year else "historical_individual", category="FX",
                    notional=_get_correct_rounding(amount_year1, self.notional_multiplier) if self.notional_multiplier > 1 else amount_year1,
                    year=year1, notional_str=evidence_amount_str1,
                    instrument_type=f"Exposure to {exposure.full_name} in {instrument_to_detail.instrument_type}",
                    reporting_year=self.reporting_year, value_type="notional_exposure",
                    currency=exposure.code, symbol=exposure.symbol, sentence_type="individual",
                ))

            # Evidence for the preceding year (year2)
            if amount_year2 > 0:
                evidence_amount_str2 = _format_single_notional(
                    amount_year2, exposure.symbol, self.prefer_abbreviated, False, negative_format=self.preferred_negative_format  # type: ignore
                )
                evidence_list.append(
                    NotionalEvidence(
                        instrument_id=instrument_to_detail.instrument_id,
                        status="historical_individual",
                        category="FX",  # This will always be historical
                        notional=_get_correct_rounding(amount_year2, self.notional_multiplier) if self.notional_multiplier > 1 else amount_year2,
                        year=year2,
                        notional_str=evidence_amount_str2,
                        instrument_type=f"Exposure to {exposure.full_name} in {instrument_to_detail.instrument_type}",
                        reporting_year=self.reporting_year,
                        value_type="notional_exposure",
                        currency=exposure.code,
                        symbol=exposure.symbol,
                        sentence_type="historical_individual",
                    )
                )

        # --- NEW: Return the list of instruments that were NOT detailed in this table ---
        remaining_instruments = [inst for inst in self.instruments if inst.instrument_id != instrument_to_detail.instrument_id]

        full_table_str = "<TABLE>\n<CAPTION>\n" + "\n".join(rows) + "\n</TABLE>"
        return full_table_str, evidence_list, remaining_instruments

class AssetLiabilityFairValueTableBuilder(DerivativeTableBuilder):
    """Builds a table showing derivative assets and liabilities."""

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a table showing derivative assets and liabilities.
        Format:
            Instrument  Asset Fair Value  Liability Fair Value
        """ # noqa
        evidence_list = []
        year = self.reporting_year
        active_instruments = [
            inst
            for inst in self.instruments
            if inst.notional_history.get(year, 0) > 0
        ]

        if not active_instruments:
            return "", [], []

        title = f"Fair Value of {random.choice(DERIVATIVE_COMPONENTS['no_alias_types']).capitalize()} {random.choice(DERIVATIVE_COMPONENTS['suffixes'])}s as of {self.month} {self.day}, {self.reporting_year} {self._get_units()}"
        headers = ["Instrument", "Asset Fair Value", "Liability Fair Value"]
        widths = [45, 20, 22]
        alignments = ['l', 'r', 'r']
        data_rows = []

        # --- NEW: Group instruments by placeholder and base_type ---
        grouped_instruments = _group_instruments_by_type(active_instruments)

        for (placeholder, base_type, currency), group_data in grouped_instruments.items():
            assert (
                isinstance(group_data["category"], str)
                and isinstance(group_data["currency"], str)
                and isinstance(group_data["symbol"], str)
                and isinstance(group_data["instruments"], list)
            )
            fair_value = sum(self._get_value(inst, year, "fair_value") for inst in group_data["instruments"] if isinstance(inst, NotionalInstrument))
            if fair_value == 0: continue

            # Randomly decide if the fair value is an asset or liability
            is_asset = random.random() < 0.5

            asset_val_str = "-"
            liab_val_str = "-"

            # Create descriptive name for the group
            plural_suffix = "s" if not base_type.endswith("s") else ""
            # --- FIX: Include currency/unit in name if it's not the default ---
            currency_note = f" ({currency})" if currency != self.currency_code else ""
            name_to_use = f"{placeholder} {base_type}{plural_suffix}{currency_note}".strip().capitalize()

            if is_asset:
                asset_val_str = _format_single_notional(
                    fair_value, group_data["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format # type: ignore
                )
            else:
                liab_val_str = _format_single_notional(
                    fair_value, group_data["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format # type: ignore
                )

            row_cells = [name_to_use, asset_val_str, liab_val_str]
            data_rows.append(row_cells)

            # Create evidence for the fair value of this instrument
            evidence_fair_value_str = _format_single_notional(
                fair_value, self.currency_symbol, self.prefer_abbreviated, False, negative_format=self.preferred_negative_format # type: ignore
            )
            evidence_list.append(
                NotionalEvidence(
                    instrument_id=None,
                    status="summary",
                    category=group_data["category"],
                    aggregate=True,
                    notional=_get_correct_rounding(fair_value, self.notional_multiplier) if self.notional_multiplier > 1 else fair_value,
                    notional_str=evidence_fair_value_str,
                    year=year,
                    instrument_type=name_to_use,
                    reporting_year=self.reporting_year,
                    value_type="fair_value",
                    currency=group_data["currency"],
                    sentence_type="summary",
                )
            )

        if not data_rows:
            return "", [], []

        table = GenericTable(headers, data_rows, widths, alignments, title)
        full_table_str = table.build()
        return full_table_str, evidence_list, []

class FairValueHierarchyTableBuilder(DerivativeTableBuilder):
    """Builds a table showing derivative assets and liabilities by fair value hierarchy level."""

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        """
        Builds a table showing derivative assets and liabilities by fair value hierarchy level.
        Format:
                                Level 1  Level 2  Level 3  Total
            Assets:
             Instrument Type      -       XX.X     -      XX.X
            Liabilities:
             Instrument Type      -       XX.X     -      XX.X
        """ # noqa
        evidence_list = []
        year = self.reporting_year
        active_instruments = [
            inst for inst in self.instruments if inst.notional_history.get(year, 0) > 0
        ]

        if not active_instruments:
            return "", [], []

        # Data structure to hold values: { 'Assets': {'Level 1': 0, ...}, 'Liabilities': ... }
        hierarchy_data: Dict[str, Dict[str, float]] = {
            "Assets": {"Level 1": 0, "Level 2": 0, "Level 3": 0, "Total": 0},
            "Liabilities": {"Level 1": 0, "Level 2": 0, "Level 3": 0, "Total": 0},
        }
        instrument_rows: Dict[str, List[List[str]]] = {"Assets": [], "Liabilities": []}

        # --- NEW: Group instruments by placeholder and base_type ---
        grouped_instruments = _group_instruments_by_type(active_instruments)

        for (placeholder, base_type, currency), group_data in grouped_instruments.items():
            assert (
                isinstance(group_data["category"], str)
                and isinstance(group_data["currency"], str)
                and isinstance(group_data["symbol"], str)
                and isinstance(group_data["instruments"], list)
            )
            fair_value = sum(self._get_value(inst, year, "fair_value") for inst in group_data["instruments"] if isinstance(inst, NotionalInstrument))
            if fair_value == 0:
                continue

            # Randomly decide if the fair value is an asset or liability
            asset_or_liability = "Assets" if random.random() < 0.5 else "Liabilities"
            # Most derivatives are Level 2. Some options/complex might be Level 3. Level 1 is rare.
            level = random.choices(["Level 1", "Level 2", "Level 3"], weights=[0.05, 0.85, 0.10], k=1)[0]

            # Create descriptive name for the group
            plural_suffix = "s" if not base_type.endswith("s") else ""
            # --- FIX: Include currency/unit in name if it's not the default ---
            currency_note = f" ({currency})" if currency != self.currency_code else ""
            name_to_use = f"{placeholder} {base_type}{plural_suffix}{currency_note}".strip().capitalize()

            # Update totals
            hierarchy_data[asset_or_liability][level] += fair_value
            hierarchy_data[asset_or_liability]["Total"] += fair_value

            # Create the row for this specific instrument
            row_values = ["-", "-", "-"]
            level_index = int(level.split(" ")[1]) - 1
            row_values[level_index] = _format_single_notional(
                fair_value, group_data["symbol"], self.prefer_abbreviated, True, negative_format=self.preferred_negative_format # type: ignore
            )
            instrument_rows[asset_or_liability].append([f"  {name_to_use}"] + row_values)

            # Create evidence for this instrument's fair value
            evidence_fair_value_str = _format_single_notional(
                fair_value, self.currency_symbol, self.prefer_abbreviated, False, negative_format=self.preferred_negative_format # type: ignore
            )
            evidence_list.append(NotionalEvidence(
                instrument_id=None,
                status="summary",
                category=group_data["category"],
                aggregate=True,
                notional=_get_correct_rounding(fair_value, self.notional_multiplier) if self.notional_multiplier > 1 else fair_value,
                notional_str=evidence_fair_value_str, year=year,
                instrument_type=f"{name_to_use} ({asset_or_liability[:-1]} classified as {level})",
                reporting_year=self.reporting_year, value_type="fair_value",
                currency=group_data["currency"], sentence_type="summary",
            ))

        title = f"Fair Value Measurements of Derivative Instruments as of {self.month} {self.day}, {self.reporting_year} {self._get_units()}"
        headers = ["", "Level 1", "Level 2", "Level 3", "Total"]
        widths = [35, 15, 15, 15, 15]
        alignments = ['l', 'r', 'r', 'r', 'r']
        data_rows = []

        for group in ["Assets", "Liabilities"]:
            if hierarchy_data[group]["Total"] > 0:
                data_rows.append([group + ":", "", "", "", ""])
                data_rows.extend(instrument_rows[group])
                # Add total row for the group
                total_row = [f"Total {group}"] + [
                    _format_single_notional(hierarchy_data[group][f"Level {i}"], self.currency_symbol, self.prefer_abbreviated, True, negative_format=self.preferred_negative_format) # type: ignore
                    if hierarchy_data[group][f"Level {i}"] > 0 else "-"
                    for i in [1, 2, 3]
                ] + [_format_single_notional(hierarchy_data[group]["Total"], self.currency_symbol, self.prefer_abbreviated, True, negative_format=self.preferred_negative_format)] # type: ignore
                data_rows.append(total_row)

        if not data_rows:
            return "", [], []

        table_builder = GenericTable(headers=headers, data_rows=data_rows, widths=widths, alignments=alignments, title=title)
        return table_builder.build(), evidence_list, []

class DerivativeTable(DerivativeTableBuilder):
    """
    This class now acts as a factory for building various table types.
    It inherits from DerivativeTableBuilder and uses its `build` method.
    """
    pass

class DerivativeImpactTableBuilder(DerivativeTableBuilder):
    """
    Builds a table summarizing the impact of derivative hedging activities on the
    income statement, similar to a common disclosure format.
    """

    def build(self) -> Tuple[str, List[NotionalEvidence], List[NotionalInstrument]]:
        # 1. Define new table structure and headers
        year1, year2 = self.reporting_year, self.reporting_year - 1
        title = f"Hedge Accounting Impact on Income Statement\n{self._get_units()}"

        # Define the multi-level header structure
        sub_headers = ["Sales", "Cost of Products Sold", "R&D Expense", "Interest Expense", "Other Expense"]
        num_data_cols = len(sub_headers)

        header_line_1 = [""] + sub_headers + sub_headers
        header_line_2 = [f"For the Year Ended {self.month} {self.day}, {year1}"] + [""] * (num_data_cols) + [str(year2)] + [""] * (num_data_cols - 1)

        headers = [header_line_1, header_line_2]
        label_width = 45
        data_width = 12
        widths = [label_width] + [data_width] * num_data_cols * 2
        alignments = ['l'] + ['r'] * num_data_cols * 2
        data_rows = []
        evidence_list = []

        # 2. Group instruments by hedge type
        hedge_groups = {
            "Fair Value Hedge": [i for i in self.instruments if i.category == "IR"], # Simplified for example
            "Net Investment Hedge": [i for i in self.instruments if i.category == "FX"],
            "Cash Flow Hedge": [i for i in self.instruments if i.category in ["FX", "CP", "IR"]],
        }

        # 3. Generate data for each group
        for hedge_type, instruments in hedge_groups.items():
            if not instruments:
                continue

            # Add a main header for the hedge type
            data_rows.append([f"Gain (Loss) on {hedge_type} relationship:"] + [""] * (num_data_cols * 2))

            # --- NEW: Use the standardized grouping function ---
            grouped_instruments = _group_instruments_by_type(instruments)

            for (placeholder, base_type, currency), group_data in grouped_instruments.items():
                plural_suffix = "s" if not base_type.endswith("s") else ""
                currency_note = f" ({currency})" if currency != self.currency_code else ""
                group_name = f"  {placeholder.capitalize()} {base_type}{plural_suffix}{currency_note}".strip()
                data_rows.append([group_name] + [""] * (num_data_cols * 2))
                sub_instruments = group_data["instruments"]
                assert isinstance(sub_instruments, list)
                # Simulate data for this group
                for year_idx, year in enumerate([year1, year2]):
                    active_in_year = any(inst.notional_history.get(year, 0) > 0 for inst in sub_instruments if isinstance(inst, NotionalInstrument))
                    if not active_in_year:
                        continue

                    total_notional = sum(
                        inst.notional_history.get(year, 0)
                        for inst in sub_instruments
                        if isinstance(inst, NotionalInstrument)
                    )
                    if total_notional == 0: continue

                    # Simulate values based on hedge type
                    if hedge_type == "Fair Value Hedge":
                        # Hedged items and derivatives affect Interest Expense
                        hedged_item_val = int(total_notional * random.uniform(0.01, 0.08))
                        derivative_val = -hedged_item_val + int(total_notional * random.uniform(-0.005, 0.005)) # Simulate ineffectiveness

                        hedged_row = [f"    Amount of gain or (loss) on hedged items ({base_type})"] + ["-"] * (num_data_cols * 2)
                        deriv_row = ["    Derivatives designated as hedging instruments"] + ["-"] * (num_data_cols * 2)

                        col_offset = year_idx * num_data_cols
                        hedged_row[1 + 3 + col_offset] = self._format_value(hedged_item_val)
                        deriv_row[1 + 3 + col_offset] = self._format_value(derivative_val)

                        data_rows.extend([hedged_row, deriv_row])

                        # --- NEW: Create evidence for these values ---
                        evidence_list.append(NotionalEvidence(
                            status="individual", category=self.category, notional=hedged_item_val,
                            notional_str=self._format_value(hedged_item_val), year=year,
                            instrument_type=f"hedged item impact for {base_type} contracts",
                            reporting_year=self.reporting_year, value_type="fair_value",
                            currency=self.currency_code, sentence_type="individual",
                            additional_details={"hedge_type": hedge_type, "line_item": "Interest Expense"}
                        ))
                        evidence_list.append(NotionalEvidence(
                            status="individual", category=self.category, notional=derivative_val,
                            notional_str=self._format_value(derivative_val), year=year,
                            instrument_type=f"derivative impact for {base_type} contracts",
                            reporting_year=self.reporting_year, value_type="fair_value",
                            currency=self.currency_code, sentence_type="individual",
                            additional_details={"hedge_type": hedge_type, "line_item": "Interest Expense"}
                        ))

                    elif hedge_type == "Net Investment Hedge":
                        # Affects Other Expense for income and AOCI
                        income_val = int(total_notional * random.uniform(0.01, 0.05))
                        aoci_val = int(total_notional * random.uniform(-0.1, 0.1)) # Can be gain or loss

                        income_row = ["    Amount of gain or (loss) recognized in income"] + ["-"] * (num_data_cols * 2)
                        aoci_row = ["    Amount of gain or (loss) recognized in AOCI"] + ["-"] * (num_data_cols * 2)

                        col_offset = year_idx * num_data_cols
                        income_row[1 + 4 + col_offset] = self._format_value(income_val)
                        # For Net Investment Hedges, the main impact is in AOCI, which is not an income statement line. We'll represent it in the "Other" column.
                        aoci_row[1 + 4 + col_offset] = self._format_value(aoci_val) 

                        data_rows.extend([income_row, aoci_row])

                        # --- NEW: Create evidence for these values ---
                        evidence_list.append(NotionalEvidence(
                            status="individual", category=self.category, notional=income_val,
                            notional_str=self._format_value(income_val), year=year,
                            instrument_type=f"income impact for {base_type} contracts",
                            reporting_year=self.reporting_year, value_type="fair_value",
                            currency=self.currency_code, sentence_type="individual",
                            additional_details={"hedge_type": hedge_type, "line_item": "Other Expense"}
                        ))
                        evidence_list.append(NotionalEvidence(
                            status="individual", category=self.category, notional=aoci_val,
                            notional_str=self._format_value(aoci_val), year=year,
                            instrument_type=f"AOCI impact for {base_type} contracts",
                            reporting_year=self.reporting_year, value_type="fair_value",
                            currency=self.currency_code, sentence_type="individual",
                            additional_details={"hedge_type": hedge_type, "line_item": "AOCI (Other Expense)"}
                        ))

                    elif hedge_type == "Cash Flow Hedge":
                        # Affects multiple lines for reclassification and AOCI
                        reclass_val = int(total_notional * random.uniform(0.01, 0.05))
                        aoci_val = int(total_notional * random.uniform(0.01, 0.1))

                        reclass_row = ["    Amount of gain or (loss) reclassified from AOCI into income"] + ["-"] * (num_data_cols * 2)
                        aoci_row = ["    Amount of gain or (loss) recognized in AOCI"] + ["-"] * (num_data_cols * 2)

                        # Distribute values across a few random columns
                        affected_indices = random.sample(range(num_data_cols), k=random.randint(1, 2))
                        col_offset = year_idx * num_data_cols
                        for idx in affected_indices:
                            # Make values positive or negative
                            reclass_part = int(reclass_val / len(affected_indices)) * random.choice([-1, 1])
                            aoci_part = int(aoci_val / len(affected_indices)) * random.choice([-1, 1])
                            reclass_row[1 + idx + col_offset] = self._format_value(reclass_part)
                            aoci_row[1 + idx + col_offset] = self._format_value(aoci_part)

                        data_rows.extend([reclass_row, aoci_row])

                        # --- NEW: Create evidence for these values ---
                        evidence_list.append(NotionalEvidence(
                            status="individual", category=self.category, notional=reclass_val,
                            notional_str=self._format_value(reclass_val), year=year,
                            instrument_type=f"reclassification from AOCI for {base_type} contracts",
                            reporting_year=self.reporting_year, value_type="fair_value",
                            currency=self.currency_code, sentence_type="individual",
                            additional_details={"hedge_type": hedge_type, "line_item": "Various"}
                        ))
                        evidence_list.append(NotionalEvidence(
                            status="individual", category=self.category, notional=aoci_val,
                            notional_str=self._format_value(aoci_val), year=year,
                            instrument_type=f"AOCI impact for {base_type} contracts",
                            reporting_year=self.reporting_year, value_type="fair_value",
                            currency=self.currency_code, sentence_type="individual",
                            additional_details={"hedge_type": hedge_type, "line_item": "AOCI"}
                        ))

            data_rows.append([""] * (num_data_cols * 2 + 1)) # Add a spacer row between hedge types

        if not data_rows:
            return "", [], []

        # Use GenericTable to build the final string
        table_builder = GenericTable(
            headers=headers,
            data_rows=data_rows,
            widths=widths,
            alignments=alignments,
            title=title
        )
        table_str = table_builder.build()

        return table_str, evidence_list, self.instruments

    def _format_value(self, value: int) -> str:
        """Formats a numerical value into a string for the table."""
        return _format_single_notional(
            value,
            self.currency_symbol,
            self.prefer_abbreviated,
            True,
            negative_format=self.preferred_negative_format, # type: ignore
        )
