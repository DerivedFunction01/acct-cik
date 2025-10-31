# New imports for generate_notional_sentence
import random
from typing import Optional, Literal
from main.definitions.common_data import months_full, quarters, aggregate_use_verbs, individual_use_verbs, termination_verbs

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
amount_connectors = [
    "with notional amounts totaling",
    "with notional amounts of",
    "with aggregate notional values of",
    "with a notional amount of",
    "totaling",
    "with notional values of",
    "with a total of",
    "with a value of",
    "with amounts totaling",
    "with fair value of",
    "with fair values totaling",
    "with fair market value of",
    "in net notional",
    "in net value",
]

# Prefixes for describing amounts (e.g., "fair value of", "notional amount of")
amount_prefixes = [
    "fair value",
    "fair market value",
    "aggregate notional amount",
    "aggregate amount",
    "notional value",
    "total value",
    "total amount",
    "net value",
    "net notional",
    "aggregate value",
]

# Amount formatting strings for different year comparisons
one_year_amount_format = "{currency_code}{notional} {money_unit}"
two_year_amount_format = "{currency_code}{notional} {money_unit} and {currency_code}{prev_notional} {money_unit}"
three_year_amount_format = "{currency_code}{notional} {money_unit}, {currency_code}{prev_notional} {money_unit}, and {currency_code}{prev2_notional} {money_unit}"


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

# Outstanding active state descriptors
state_descriptors = ["outstanding", "active", "remaining", "open"]

# Base sentence structures for notional amounts
# Placeholders: {time_prefix}, {company}, {verb}, {swap_type}, {amount_connector}, {amount_str}, {hedge_designation_clause}, {result_clause}, {time_suffix}
NOTIONAL_SENTENCE_TEMPLATES = {
    "summary": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, {swap_type} {amount_connector} {amount_str} {verb} by {company}{hedge_designation_clause}{result_clause}.",
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix}{hedge_designation_clause}{result_clause}.",
    ],
    "new_individual": [
        "{time_prefix}, {company} {verb} new {swap_type} {amount_connector} {amount_str}{hedge_designation_clause}{result_clause}.",
        "{company} {verb} new {swap_type} {amount_connector} {amount_str} {time_suffix}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, new {swap_type} {amount_connector} {amount_str} {verb} by {company}{hedge_designation_clause}{result_clause}.",
    ],
    "terminated_individual": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, {swap_type} {amount_connector} {amount_str} {verb} by {company}{hedge_designation_clause}{result_clause}.",
        "{company} {verb} {swap_type} {amount_connector} {amount_str} {time_suffix}{hedge_designation_clause}{result_clause}.",
    ],
    "comparative": [
        "{time_prefix}, {company} {verb} {swap_type} {amount_connector} {amount_str}, respectively{hedge_designation_clause}{result_clause}.",
        "{time_prefix}, {swap_type} {amount_connector} {amount_str}, respectively, {verb} by {company}{hedge_designation_clause}{result_clause}.",
        "{swap_type} {amount_connector} {amount_str}, respectively, {time_suffix}{hedge_designation_clause}{result_clause}.",
    ],
}

def _cleanup_sentence(sentence: str) -> str:
    """Clean up sentence by removing empty placeholders and extra spaces."""
    # Remove any remaining optional placeholders that weren't filled
    sentence = sentence.replace("{hedge_designation_clause}", "")
    sentence = sentence.replace("{result_clause}", "")
    sentence = sentence.replace("{time_suffix}", "") # If not used, remove it

    # Clean up multiple spaces
    while "  " in sentence:
        sentence = sentence.replace("  ", " ")

    # Clean up comma/space issues
    sentence = sentence.replace(" ,", ",")
    sentence = sentence.replace(",,", ",")

    # Remove trailing commas before period
    sentence = sentence.replace(", .", ".")
    sentence = sentence.replace(" .", ".") # In case of empty clauses

    return sentence.strip()

def generate_notional_sentence(
    swap_type: str,
    year: int,
    notional: int,
    currency_symbol: str = "$",
    money_unit_word: str = "million",
    month: Optional[str] = None,
    end_day: Optional[int] = None,
    quarter: Optional[str] = None,
    prev_year: Optional[int] = None,
    prev_notional: Optional[int] = None,
    prev2_year: Optional[int] = None,
    prev2_notional: Optional[int] = None,
    hedge_designation: Optional[str] = None,
    result_phrase: Optional[str] = None,
    company_name: Optional[str] = None,
    verb: Optional[str] = None,
    sentence_type: Literal["summary", "new_individual", "terminated_individual", "comparative"] = "summary",
    include_time_prefix: bool = True,
    include_amount_connector: bool = True,
    include_hedge_designation: bool = False,
    include_result: bool = False,
) -> str:
    """
    Generates a notional amount sentence based on the provided configuration.
    """
    # Default values for optional components
    month = month or random.choice(months_full)
    end_day = end_day or random.randint(28, 31)
    quarter = quarter or random.choice(quarters)
    company_name = company_name or "The Company"

    # Determine number of years for comparison
    num_years = 1
    if prev_year is not None and prev_notional is not None:
        num_years = 2
        if prev2_year is not None and prev2_notional is not None:
            num_years = 3

    # 1. Format amount string
    amount_str = ""
    if num_years == 1:
        amount_str = one_year_amount_format.format(
            currency_code=currency_symbol, notional=notional, money_unit=money_unit_word
        )
    elif num_years == 2:
        amount_str = two_year_amount_format.format(
            currency_code=currency_symbol, notional=notional, money_unit=money_unit_word,
            prev_notional=prev_notional
        )
    elif num_years == 3:
        amount_str = three_year_amount_format.format(
            currency_code=currency_symbol, notional=notional, money_unit=money_unit_word,
            prev_notional=prev_notional, prev2_notional=prev2_notional
        )

    # 2. Select time prefix template
    time_prefix = ""
    time_suffix = ""
    if include_time_prefix:
        if sentence_type in ["summary", "comparative"]:
            if num_years == 1:
                time_prefix = random.choice(point_in_time_prefixes)
            elif num_years == 2:
                time_prefix = random.choice(multi_year_time_prefixes["two_year"])
            else: # num_years == 3
                time_prefix = random.choice(multi_year_time_prefixes["three_year"])
        else: # new_individual, terminated_individual
            time_prefix = random.choice(period_of_time_prefixes)

        time_prefix = time_prefix.format(
            month=month, end_day=end_day, year=year,
            prev_year=prev_year or year - 1,
            prev2_year=prev2_year or year - 2,
            quarter=quarter
        )
        time_suffix = f"as of {month} {end_day}, {year}" # Generic suffix for end of sentence

    # 3. Select verb
    if verb is None:
        if sentence_type == "new_individual":
            verb = random.choice(individual_use_verbs)
        elif sentence_type == "terminated_individual":
            verb = random.choice(termination_verbs)
        else: # summary, comparative
            verb = random.choice(aggregate_use_verbs)

    # 4. Select amount connector
    amount_connector = ""
    if include_amount_connector:
        amount_connector = random.choice(amount_connectors)

    # 5. Hedge designation clause
    hedge_designation_clause = ""
    if include_hedge_designation and hedge_designation:
        hedge_designation_clause = f", designated as {hedge_designation}"

    # 6. Result phrase clause
    result_clause = ""
    if include_result and result_phrase:
        result_clause = f", {result_phrase}"

    # 7. Select main sentence template
    templates_for_type = NOTIONAL_SENTENCE_TEMPLATES.get(sentence_type, NOTIONAL_SENTENCE_TEMPLATES["summary"])
    template = random.choice(templates_for_type)

    # 8. Populate placeholders
    sentence = template.format(
        time_prefix=time_prefix,
        company=company_name,
        verb=verb,
        swap_type=swap_type,
        amount_connector=amount_connector,
        amount_str=amount_str,
        hedge_designation_clause=hedge_designation_clause,
        result_clause=result_clause,
        time_suffix=time_suffix
    )

    # 9. Cleanup
    sentence = _cleanup_sentence(sentence)

    return sentence

# Outstanding active state descriptors
state_descriptors = ["outstanding", "active", "remaining", "open"]