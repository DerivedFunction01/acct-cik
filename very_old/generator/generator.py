# %%
import random
import pandas as pd
from openpyxl import load_workbook
import re
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from templates.common import *
from templates.hedges import *
from templates.other import *
from templates.w_ed import *

output_file = "./training_data.xlsx"
company_name_file = "./names.xlsx"
parquet_file = "./training_data.parquet"
# Precompile regex patterns
pattern_we_s = re.compile(r"We's", flags=re.IGNORECASE)
pattern_we_is = re.compile(r"We is", flags=re.IGNORECASE)
pattern_nil = re.compile(r" (0|0.0) (thousand|million|billion)", flags=re.IGNORECASE)
pattern_notional = re.compile(f"notional", flags=re.IGNORECASE)
pattern_spaces = re.compile(r"\s+")
pattern_dots = re.compile(r"\.\.")

company_name_df = pd.read_excel(company_name_file)
company_names = list(company_name_df["name"])

def new_label():
    return {
        "deriv": 0,
        "ir": 0,
        "fx": 0,
        "cp": 0,
        "equity": 0,
        "embed": 0,
        "curr": 0,
        "hist": 0,
        "spec": 0,
        "debt_ctx": 0,
        "fx_ctx": 0,
        "eq_ctx": 0,
        "comm_ctx": 0,
        "emb_ctx": 0,
        "spec_ctx": 0,
        "gen_ctx": 0,
        "irrelevant": 0,
    }

def pick_company_name(company_name: str) -> str:
    return random.choices([company_name, "The Company"], weights=[0.75, 0.25], k=1)[0]


def generate_value(haveZero=True, upperlimit=1000):
    """Generate a random previous notional value with chance of being zero,
    and optional rounding for variability. Returns int if whole, else float."""
    if haveZero:
        chance = 0.1
    else:
        chance = 0
        
    upperlimit = int(upperlimit)
    value = 0.0 if random.random() < chance else (1
    if upperlimit <= 1 else random.randint(1, upperlimit))

    if random.random() < 0.5:
        divisor = random.choice([10, 100])
        decimals = random.randint(1, 2)
        value = round(value / divisor, decimals)

    # Cast to int if it's a whole number with 50% chance
    if isinstance(value, float) and value.is_integer() and random.random() < 0.5:
        value = int(value)

    return value


def cleanup(paragraph: str, reporting_year: int, checkBracket: bool = True):
    pattern_we_s.sub("Our", paragraph)
    paragraph = pattern_we_is.sub("We are", paragraph)
    if random.random() < 0.25:  # Chance to replace values with nil
        paragraph = pattern_nil.sub(
            random.choice([" nil", " 0", " 0.0", " 0.00"]), paragraph
        )

    if random.random() < 0.5:
        paragraph = pattern_notional.sub("", paragraph)
    paragraph = pattern_spaces.sub(" ", paragraph)  # Remove extra whitespace
    paragraph = pattern_dots.sub("", paragraph)  # Remove double periods

    if paragraph.find("{") != -1 or (paragraph.find("[") != -1 and checkBracket):
        print("Error in format", paragraph)
    paragraph = (
        f"<reportingYear>{reporting_year}</reportingYear> "
        + ". ".join(selected_sentences)
        + "."
    )
    return paragraph

def generate_derivative_liability_paragraph(
    label_type,
    max_past_years=random.randint(1, 3),
    year_range=(1990, 2025),
    max_len=random.randint(2, 4),
    company_name=None,
):
    """
    Generate synthetic paragraphs for derivative liabilities/warrants (label 4)
    or embedded derivatives (label 6).

    Args:
        label_type (int): 4 for derivative liabilities/warrants, 6 for embedded derivatives
        year_range (tuple): (min_year, max_year) for reporting year
        max_len (int): Maximum number of sentences

    Returns:
        tuple: (paragraph_text, label)
    """

    current_year = random.randint(year_range[0], year_range[1])
    reporting_year = current_year

    all_sentences = []
    currency_code = random.choice(currency_codes)
    money_units = random.choice(money_unit_list)
    major_currency = random.choice(all_currencies)
    if company_name is None:
        # ~ 75% chance of company name
        if random.random() < 0.85:
            company_name = random.choice(company_names)
        else:
            company_name = "The Company"
    target_companies = [name for name in company_names if name != company_name]

    # ============ LABELS 4 & 5: DERIVATIVE LIABILITIES AND WARRANTS ============
    if label_type in [4, 5]:

        is_past = label_type == 5  # True for label 5, False for label 4

        # For label 5 (past), use historical years
        if is_past:
            past_years = sorted(
                random.sample(
                    range(current_year - 5, current_year),
                    random.randint(1, max_past_years),
                )
            )
            settlement_year = random.choice([current_year - 1, current_year])

        if random.random() < 0.5:
            template = random.choice(warrant_issuance_templates)
            shares = random.choice([50000, 100000, 250000, 500000, 750000, 1000000])
            price = round(random.uniform(1.50, 25.00), 2)
            month = random.choice(months)

            if is_past:
                # Use past years for label 5
                year = random.choice(past_years)
            else:
                # Use current or recent year for label 4
                year = random.choice([current_year, current_year - 1])

            event = random.choice(warrant_events)
            expiry_year = year + random.randint(3, 7)
            sentence = template.format(
                company=pick_company_name(company_name),
                currency_code=currency_code,
                shares=f"{shares:,}",
                price=price,
                month=month,
                year=year,
                event=event,
                expiry_year=expiry_year,
            )
            all_sentences.append(sentence)

        # Add fair value measurement (0-1)
        template = random.choice(warrant_fv_templates)
        amount = round(random.uniform(0.5, 15.0), 1)
        end_day = random.randint(28, 31)
        month = random.choice(months)
        model = random.choice(valuation_models)
        verb = random.choice(assessment_verbs)
        sentence = template.format(
            amount=amount,
            company=pick_company_name(company_name),
            model=model,
            verb=verb,
            currency_code=currency_code,
            month=month,
            end_day=end_day,
            year=current_year,
            money_unit=money_units,
        )
        all_sentences.append(sentence)

        # Add liability classification (0-1)
        template = random.choice(warrant_liability_templates)
        location = random.choice(balance_sheet_locations)
        event = random.choice(warrant_events)
        sentence = template.format(
            location=location, company=pick_company_name(company_name), event=event
        )
        all_sentences.append(sentence)

        # Add general derivative liability (0-1) - only for label 4
        if not is_past:
            template = random.choice(deriv_liability_general_templates)
            amount = round(random.uniform(2.0, 20.0), 1)
            prev_amount = round(amount * random.uniform(0.7, 1.4), 1)
            gain_loss = random.choice(["gain", "loss"])
            model = random.choice(valuation_models)
            sentence = template.format(
                year=current_year,
                amount=amount,
                prev_amount=prev_amount,
                gain_loss=gain_loss,
                month=random.choice(months),
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                model=model,
                end_day=random.randint(28, 31),
            )
            all_sentences.append(sentence)

        # Add down round features (0-1) - only for label 4
        if not is_past and random.random() < 0.4:
            sentence = random.choice(down_round_templates)
            all_sentences.append(sentence.format(company=pick_company_name(company_name)))

        # Add earnout liability (0-1)
        if random.random() < 0.3:
            if is_past:
                # Use past earnout template for label 5
                template = random.choice(earnout_past_templates)
                target = random.choice(target_companies)
                amount = round(random.uniform(5.0, 50.0), 1)
                year = random.choice(past_years)

                sentence = template.format(
                    target=target,
                    amount=amount,
                    year=year,
                    settlement_year=settlement_year,
                    month=random.choice(months),
                    company=pick_company_name(company_name),
                    currency_code=currency_code,
                    major_currency=major_currency,
                    money_unit=money_units,
                    end_day=random.randint(28, 31),
                )
            else:
                # Use current earnout template for label 4
                template = random.choice(earnout_templates)
                target = random.choice(target_companies)
                amount = round(random.uniform(5.0, 50.0), 1)
                year = current_year + random.randint(1, 3)

                sentence = template.format(
                    target=target,
                    amount=amount,
                    year=year,
                    company=pick_company_name(company_name),
                    currency_code=currency_code,
                    major_currency=major_currency,
                    money_unit=money_units,
                    month=random.choice(months),
                    end_day=random.randint(28, 31),
                )
            all_sentences.append(sentence)

        # Add past-specific templates for label 5
        if is_past:
            for _ in range(0, max_len):
                # Add warrant liability extinguishment (0-1)
                if random.random() < 0.6:
                    template = random.choice(warrant_liability_extinguishment_templates)
                    amount = round(random.uniform(1.0, 10.0), 1)
                    year = random.choice(past_years)

                    sentence = template.format(
                        amount=amount,
                        year=year,
                        month=random.choice(months),
                        settlement_year=settlement_year,
                        company=pick_company_name(company_name),
                        currency_code=currency_code,
                        major_currency=major_currency,
                        money_unit=money_units,
                        end_day=random.randint(28, 31),
                    )
                    all_sentences.append(sentence)
        label = label_type

    # ============ LABELS 6 & 7: EMBEDDED DERIVATIVES ============
    elif label_type in [6, 7]:

        is_past = label_type == 7  # True for label 7, False for label 6

        # For label 7 (past), use historical years
        if is_past:
            past_years = sorted(
                random.sample(
                    range(current_year - 5, current_year),
                    random.randint(1, max_past_years),
                )
            )
            settlement_year = random.choice([current_year - 1, current_year])

        # Add embedded derivative identification (1)
        template = random.choice(embedded_identification_templates)
        host_contract = random.choice(host_contracts)
        sentence = template.format(
            host_contract=host_contract,
            company=pick_company_name(company_name),
            verb=random.choice(assessment_verbs),
        )
        all_sentences.append(sentence)

        # Add embedded derivative types (0-1)
        if random.random() < 0.6:
            template = random.choice(embedded_types_templates)
            embedded_type = random.choice(embedded_types)
            host_contract = random.choice(host_contracts)
            location = random.choice(balance_sheet_locations)

            sentence = template.format(
                embedded_type=embedded_type,
                host_contract=host_contract,
                location=location,
                company=pick_company_name(company_name),
            )
            all_sentences.append(sentence)

        # Add convertible debt scenario (0-1)
        if random.random() < 0.5:
            if is_past:
                # Use redemption template for label 7
                template = random.choice(convertible_debt_redemption_templates)
                principal = random.choice([50, 100, 150, 200, 250, 500])
                embedded_fv = round(principal * random.uniform(0.05, 0.15), 1)
                amount = embedded_fv
                month = random.choice(months)
                end_day = random.randint(28, 31)
                year = random.choice(past_years)
                gain_loss = random.choice(["gain", "loss"])
                maturity_year = random.randint(current_year, current_year + 5)
                sentence = template.format(
                    principal=principal,
                    embedded_fv=embedded_fv,
                    amount=amount,
                    month=month,
                    end_day=end_day,
                    year=year,
                    settlement_year=settlement_year,
                    maturity_year=maturity_year,
                    company=pick_company_name(company_name),
                    currency_code=currency_code,
                    money_unit=money_units,
                    gain_loss=gain_loss,
                )
            else:
                # Use issuance template for label 6
                template = random.choice(convertible_debt_templates)
                principal = random.choice([50, 100, 150, 200, 250, 500])
                embedded_fv = round(principal * random.uniform(0.05, 0.15), 1)
                month = random.choice(months)
                year = random.choice([current_year, current_year - 1, current_year - 2])

                sentence = template.format(
                    principal=principal,
                    embedded_fv=embedded_fv,
                    month=month,
                    year=year,
                    company=pick_company_name(company_name),
                    currency_code=currency_code,
                    major_currency=major_currency,
                    money_unit=money_units,
                )
            all_sentences.append(sentence)

        # Add fair value measurement (1) - only for label 6
        if not is_past:
            template = random.choice(embedded_fv_templates)
            amount = round(random.uniform(5.0, 50.0), 1)
            prev_amount = round(amount * random.uniform(0.7, 1.3), 1)
            change_direction = "increase" if amount > prev_amount else "decrease"

            sentence = template.format(
                amount=amount,
                year=current_year,
                month=random.choice(months),
                prev_amount=prev_amount,
                prev_year=current_year - 1,
                change_direction=change_direction,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
            )
            all_sentences.append(sentence)

        # Add valuation methodology (0-1) - only for label 6
        if not is_past and random.random() < 0.6:
            template = random.choice(embedded_valuation_templates)
            model = random.choice(valuation_models)
            assumptions = random.choice(valuation_assumptions)

            sentence = template.format(
                model=model, assumptions=assumptions, company=pick_company_name(company_name)
            )
            all_sentences.append(sentence)

        # Add fair value change (0-1) - only for label 6
        if not is_past and random.random() < 0.5:
            template = random.choice(embedded_fv_change_templates)
            gain_loss = random.choice(["gain", "loss"])
            amount = round(random.uniform(1.0, 20.0), 1)
            location = random.choice(balance_sheet_locations)

            sentence = template.format(
                year=current_year,
                gain_loss=gain_loss,
                month=random.choice(months),
                amount=amount,
                location=location,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
            )
            all_sentences.append(sentence)

        # Add clearly and closely related analysis (0-1) - only for label 6
        if not is_past and random.random() < 0.4:
            sentence = random.choice(ccr_analysis_templates)
            verb = random.choice(assessment_verbs)
            sentence = sentence.format(verb=verb, company=pick_company_name(company_name))
            all_sentences.append(sentence)

        # Add settlement activity (0-1)
        if random.random() < 0.3:
            template = random.choice(embedded_settlement_templates)
            month = random.choice(months)
            quarter = random.choice(quarters)
            principal = random.choice([25, 50, 100, 150])
            amount = round(random.uniform(2.0, 15.0), 1)
            gain_loss = random.choice(["gain", "loss"])

            year_to_use = settlement_year if is_past else current_year

            sentence = template.format(
                month=month,
                year=year_to_use,
                quarter=quarter,
                principal=principal,
                amount=amount,
                gain_loss=gain_loss,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                money_unit=money_units,
            )
            all_sentences.append(sentence)

        # Add embedded FX derivatives (0-1) - only for label 6
        if not is_past and random.random() < 0.3:
            template = random.choice(embedded_fx_templates)
            host_contract = random.choice(host_contracts)
            currency_pair = random.choice(currency_pairs)
            sentence = template.format(
                host_contract=host_contract,
                currency_pair=currency_pair,
                company=pick_company_name(company_name),
            )
            all_sentences.append(sentence)

        # Add past-specific templates for label 7
        if is_past:
            # Add embedded past templates (1-2)
            for _ in range(random.randint(1, 2)):
                template = random.choice(embedded_past_templates)
                host_contract = random.choice(host_contracts)
                verb = random.choice(hedge_use_verbs)
                month = random.choice(months)
                end_day = random.randint(28, 31)
                year = random.choice(past_years)
                sentence = template.format(
                    host_contract=host_contract,
                    verb=verb,
                    year=year,
                    settlement_year=settlement_year,
                    month=month,
                    current_year=current_year,
                    company=pick_company_name(company_name),
                    end_day=end_day,
                )
                all_sentences.append(sentence)

            # Add no longer outstanding statement (0-1)
            if random.random() < 0.7:
                template = random.choice(embedded_no_longer_outstanding_templates)
                amount = round(random.uniform(5.0, 40.0), 1)
                month = random.choice(months)
                end_day = random.randint(28, 31)
                sentence = template.format(
                    settlement_year=settlement_year,
                    current_year=current_year,
                    month=month,
                    end_day=end_day,
                    amount=amount,
                    company=pick_company_name(company_name),
                    currency_code=currency_code,
                    money_unit=money_units,
                )
                all_sentences.append(sentence)

        label = label_type

    elif label_type == 3:
        label = 3
        for _ in range(0, max_len):
            template = random.choice(
                equity_warrant_templates + equity_warrant_activity_templates
            )
            shares = random.choice([50000, 100000, 250000, 500000, 1000000])
            net_shares = int(shares * 0.7)
            price = round(random.uniform(5.00, 50.00), 2)
            amount = round((shares * price) / 1000000, 1)
            expiry_year = current_year + random.randint(2, 5)
            year = current_year - random.randint(0, 5)
            month = random.choice(months)
            event = random.choice(warrant_events)
            prev_month = random.choice(months)
            value = round(shares * random.uniform(0.25, 0.75), 0)

            sentence = template.format(
                shares=f"{shares:,}",
                net_shares=f"{net_shares:,}",
                price=price,
                expiry_year=expiry_year,
                year=year,
                amount=amount,
                month=month,
                prev_month=prev_month,
                prev_year=year - random.randint(1, 2),
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
                event=event,
                quarter=random.choice(quarters),
                value=value,
            )
            all_sentences.append(sentence)
        # Non-cash transactions and equity dilution
        for _ in range(0, max_len):
            noncash_type = random.choice(
                [
                    "stock_debt",
                    "registration",
                    "market_impact",
                    "warrant_adjustment",
                    "fair_value",
                    "share_reservation",
                    "outstanding_options",
                    "dilution_concern",
                    "capital_raising",
                ]
            )
            month = random.choice(months)
            year = random.choice([current_year, current_year - 1])
            end_day = random.randint(28, 31)

            if noncash_type == "stock_debt":
                template = random.choice(stock_debt_issuance_templates)
                shares = random.choice([10000, 15000, 20000, 25000, 50000])
                shares1 = random.choice([10000, 15000, 20000, 25000])
                shares2 = int(shares1 * random.uniform(0.4, 0.6))
                value = round(shares * random.uniform(8, 15) / 1000, 0)
                value1 = round(shares1 * random.uniform(8, 15) / 1000, 0)
                value2 = round(shares2 * random.uniform(2, 8) / 1000, 0)
                financing_type = random.choice(financing_types)

                sentence = template.format(
                    company=pick_company_name(company_name),
                    month=month,
                    year=year,
                    financing_type=financing_type,
                    shares=f"{shares:,}",
                    shares1=f"{shares1:,}",
                    shares2=f"{shares2:,}",
                    value=f"{value:,}",
                    value1=f"{value1:,}",
                    value2=f"{value2:,}",
                    currency_code=currency_code,
                )

            elif noncash_type == "registration":
                template = random.choice(registration_statement_templates)
                shares = random.choice([500000, 1000000, 1500000, 2000000, 3000000])
                days = random.choice([30, 60, 90, 120])

                sentence = template.format(
                    company=pick_company_name(company_name),
                    month=month,
                    year=year,
                    shares=f"{shares:,}",
                    days=days,
                )

            elif noncash_type == "market_impact":
                template = random.choice(market_impact_templates)
                shares = random.choice([500000, 1000000, 2000000, 3000000])

                sentence = template.format(
                    company=pick_company_name(company_name), shares=f"{shares:,}"
                )

            elif noncash_type == "warrant_adjustment":
                template = random.choice(warrant_adjustment_templates)
                shares = random.choice([100000, 200000, 333334, 500000])
                shares1 = int(shares * random.uniform(1.2, 1.8))
                price = round(random.uniform(2.00, 10.00), 2)
                price2 = round(price * random.uniform(0.5, 0.8), 2)

                sentence = template.format(
                    month=month,
                    year=year,
                    shares=f"{shares:,}",
                    shares1=f"{shares1:,}",
                    price=f"{price:.2f}",
                    price2=f"{price2:.2f}",
                    currency_code=currency_code,
                )

            elif noncash_type == "fair_value":
                template = random.choice(fair_value_snapshot_templates)
                shares = random.choice([500000, 1000000, 1500000])
                value = round(shares * random.uniform(3, 12) / 1000000, 1)
                value1 = round(random.uniform(2, 10), 1)
                value2 = round(random.uniform(2, 10), 1)

                sentence = template.format(
                    company=pick_company_name(company_name),
                    month=month,
                    year=year,
                    end_day=end_day,
                    shares=f"{shares:,}",
                    value=f"{value:.1f}",
                    value1=f"{value1:.1f}",
                    value2=f"{value2:.1f}",
                    currency_code=currency_code,
                )

            elif noncash_type == "share_reservation":
                template = random.choice(share_reservation_templates)
                shares = random.choice([1000000, 2000000, 3000000, 5000000])
                shares1 = random.choice([500000, 750000, 1000000])
                shares2 = random.choice([250000, 500000, 750000])

                sentence = template.format(
                    company=pick_company_name(company_name),
                    month=month,
                    year=year,
                    end_day=end_day,
                    shares=f"{shares:,}",
                    shares1=f"{shares1:,}",
                    shares2=f"{shares2:,}",
                )

            elif noncash_type == "outstanding_options":
                template = random.choice(outstanding_options_templates)
                shares = random.choice([500000, 750000, 1000000, 1500000])
                shares1 = int(shares * random.uniform(0.4, 0.7))
                price = round(random.uniform(5.00, 25.00), 2)
                end_year = year + random.randint(5, 10)

                sentence = template.format(
                    company=pick_company_name(company_name),
                    month=month,
                    year=year,
                    end_day=end_day,
                    end_year=end_year,
                    shares=f"{shares:,}",
                    shares1=f"{shares1:,}",
                    price=f"{price:.2f}",
                    currency_code=currency_code,
                )

            elif noncash_type == "dilution_concern":
                template = random.choice(dilution_concern_templates)
                shares = random.choice([1000000, 2000000, 3000000, 5000000])
                shares1 = int(shares * random.uniform(0.5, 0.8))
                pct = round(random.uniform(10, 35), 1)

                sentence = template.format(
                    company=pick_company_name(company_name),
                    month=month,
                    year=year,
                    end_day=end_day,
                    shares=f"{shares:,}",
                    shares1=f"{shares1:,}",
                    pct=pct,
                )

            elif noncash_type == "capital_raising":
                template = random.choice(capital_raising_impact_templates)
                shares = random.choice([1000000, 2000000, 3000000])

                sentence = template.format(
                    company=pick_company_name(company_name), shares=f"{shares:,}"
                )

            all_sentences.append(sentence)

    else:
        raise ValueError("Must be 3 4 5 6 7")

    # Shuffle and select
    random.shuffle(all_sentences)
    selected_sentences = all_sentences[:max_len]
    selected_sentences = [s[0].upper() + s[1:] if s else "" for s in all_sentences]
    # Create paragraph
    # Clean up common formatting issues
    paragraph = cleanup(paragraph, reporting_year)
    return paragraph, label

def generate_labeled_hedge_paragraph(
    has_active_derivative,
    swapType=None,  # Added parameter
    year_range=(1990, 2025),
    max_past_years=3,
    max_len=random.randint(2, 3),
    include_policy=None,
    company_name=None,
):
    """
        Generate a synthetic hedge paragraph with known label.

        Args:
            has_active_derivative (bool or None):
                - True: firm has active derivative in reporting year (label=0)
                - False: firm does not have active derivative (label=1)
                - None: policy/disclosure only, no specific positions (label=2)
            swap_type (str): Type of derivative ('ir', 'fx', 'cp', 'gen')
            year_range (tuple): (min_year, max_year) for the reporting year
            max_past_years (int): Max number of prior years to include
            max_len (int): Maximum number of sentences
            include_policy (bool): Whether to include policy sentences with labels 0/1
                                  If None, randomly decides (70% chance)
            company_name (str): Company name to use
    """

    labels = new_label()

    # Decide whether to include policy statements
    if include_policy is None and random.random() < 0.15:
        include_policy = True

    # If has_active_derivative not given, default to speculative/policy
    if has_active_derivative is None:
        include_policy = True

    # Pick company name
    if company_name is None:
        company_name = (
            random.choice(company_names) if random.random() < 0.75 else "The Company"
        )

    # Determine swap type if not provided
    if swapType is None:
        swapType = random.choice(["ir", "fx", "cp", "gen", "mixed"])

    # Handle mixed swap types
    if swapType == "mixed":
        num_types = random.randint(2, 3)
        selected_types = random.sample(["ir", "fx", "cp"], num_types)
        swap_types = []
        for st in selected_types:
            swap_types.extend(derivative_keywords[st])
        swap_types = list(dict.fromkeys(swap_types))
        mixed_types = selected_types
    else:
        swap_types = derivative_keywords[swapType]
        mixed_types = None

    # Currency and year setup
    money_units = random.choice(money_unit_list)
    currency_code = random.choice(currency_codes)
    major_currency = random.choice(all_currencies)

    current_year = random.randint(year_range[0], year_range[1])
    reporting_year = current_year
    num_past_years = random.randint(1, max_past_years)
    past_years = sorted(
        random.sample(range(current_year - 5, current_year), num_past_years)
    )

    commodity = random.choice(commodities)
    all_sentences = []

    # =====================
    # Assign multi-labels
    # =====================
    labels["deriv"] = 1  # Always a derivative mention

    if swapType in ["ir", "fx", "cp", "gen"]:
        labels[swapType] = 1  # Mark the hedge type

    # Current / Historic / Speculative
    if has_active_derivative is True:
        labels["curr"] = 1
    elif has_active_derivative is False:
        labels["hist"] = 1
    else:  # None or speculative
        labels["spec"] = 1
        labels["spec_ctx"] = 1

    # Contextual relationships
    if swapType == "ir":
        labels["debt_ctx"] = 1
    elif swapType == "fx":
        labels["fx_ctx"] = 1
    elif swapType == "cp":
        labels["eq_ctx"] = 1
    elif swapType == "gen" and include_policy:
        labels["gen_ctx"] = 1

    def generate_fx_policy():
        sentences = []
        # Set the base labels for this FX policy block
        labels["deriv"] = 1
        labels["fx"] = 1
        labels["fx_ctx"] = 1

        # Set current/historic/speculative context
        if has_active_derivative:
            labels["curr"] = 1
            labels["spec"] = 0  # override speculative since it's current
        else:
            labels["spec"] = 1
            labels["spec_ctx"] = 1

        if has_active_derivative:
            verbs = hedge_use_verbs
            mit_verbs = hedge_mitigation_verbs
        else:
            verbs = hedge_may_use_verbs
            mit_verbs = hedge_may_mitigation_verbs
        selected_fx = []
        for _ in range(3):
            selected_fx.append(random.choice(swap_types))
            if random.random() < 0.5:
                break
        selected_fx_list = (
            ", ".join(selected_fx[:-1]) + " and " + selected_fx[-1]
            if len(selected_fx) > 1
            else selected_fx[0]
        )
        # Context sentences
        template = random.choice(fx_context_templates)
        sentences.append(template.format(company=pick_company_name(company_name)))

        # Impact sentences
        template = random.choice(fx_impact_templates)
        verb = random.choice(hedge_change_verbs)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                major_currency=major_currency,
                verb=verb,
            )
        )

        # Mitigation sentences
        template = random.choice(fx_mitigation_templates)
        verb = random.choice(mit_verbs)
        swap_verb = random.choice(verbs)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_types=selected_fx_list,
                swap_verb=swap_verb,
                major_currency=major_currency,
            )
        )
        # May use hedge
        template = random.choice(fx_may_use_templates)
        verb = random.choice(verbs)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_types=selected_fx_list,
            )
        )
        # Alternative management (0-1)
        template = random.choice(fx_alternative_management_templates)
        may_verb = random.choice(hedge_may_use_verbs)
        use_verb = random.choice(verbs)
        sentences.append(
            template.format(
                may_verb=may_verb,
                use_verb=use_verb,
                swap_types=selected_fx_list,
                company=pick_company_name(company_name),
            )
        )
        # Generic hedge (0-1)
        template = random.choice(fx_generic_hedge_templates)
        verb = random.choice(verbs)
        hedge_type = random.choice(hedge_types)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                hedge_type=hedge_type,
                swap_types=selected_fx_list,
            )
        )

        # Specific hedge (0-1)
        template = random.choice(fx_specific_hedge_templates)
        swap_type = random.choice(swap_types)
        notional_currency = random.choice(currency_codes)
        notional_amount = generate_value(False)
        expiry_year = current_year + 1
        currency_pair = random.choice(currency_pairs)
        hedged_item = random.choice(hedged_items)
        sentence = template.format(
            company=pick_company_name(company_name),
            swap_type=swap_type,
            notional_currency=notional_currency,
            notional_amount=notional_amount,
            money_unit=money_units,
            expiry_year=expiry_year,
            currency_pair=currency_pair,
            hedged_item=hedged_item,
        )
        sentences.append(sentence)

        # Cash pooling arrangements (0-1)
        template = random.choice(fx_cash_pooling_templates)
        verb = random.choice(verbs)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                major_currency=major_currency,
            )
        )

        # Debt optimization strategies (0-1)
        template = random.choice(fx_debt_optimization_templates)
        verb = random.choice(verbs)
        sentence = template.format(
            company=pick_company_name(company_name),
            verb=verb,
            currency_code=currency_code,
            swap_type=random.choice(swap_types),
            swap_types=selected_fx_list,
        )
        sentences.append(sentence)

        # Collar strategy
        template = random.choice(fx_strategy_templates)
        swap_type = random.choice(swap_types)
        verb = random.choice(hedge_use_verbs)
        collar_year = random.choice(past_years) if past_years else current_year
        if has_active_derivative:
            collar_year = current_year
        sentence = template.format(
            company=pick_company_name(company_name),
            verb=verb,
            swap_type=swap_type,
            quarter=random.choice(quarters),
            month=random.choice(months),
            year=collar_year,
            major_currency=major_currency,
        )
        sentences.append(sentence)
        return sentences

    def generate_ir_policy():
        labels["deriv"] = 1  # generic derivative mention
        labels["ir"] = 1  # interest rate hedge
        labels["debt_ctx"] = 1  # IR usually relates to debt context

        if has_active_derivative:
            labels["curr"] = 1
        else:
            labels["hist"] = 1  # mark as historic
            if random.random() < 0.4:
                labels["spec"] = 1  # some historic mentions can be speculative/policy

        # Generic context
        labels["gen_ctx"] = 1
        if random.random() < 0.2:
            labels["spec_ctx"] = 1  # sometimes policy discussion overlaps with IR

        sentences = []
        if has_active_derivative:
            verbs = hedge_use_verbs
            mit_verbs = hedge_mitigation_verbs
        else:
            verbs = hedge_may_use_verbs
            mit_verbs = hedge_may_mitigation_verbs
        selected_ir = []
        for _ in range(3):
            selected_ir.append(random.choice(swap_types))
            if random.random() < 0.5:
                break
        selected_ir_list = (
            ", ".join(selected_ir[:-1]) + " and " + selected_ir[-1]
            if len(selected_ir) > 1
            else selected_ir[0]
        )
        # Context sentences
        verb = random.choice(verbs)
        template = random.choice(ir_context_templates)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_types=selected_ir_list,
            )
        )
        template = random.choice(fx_ir_context_templates)
        sentences.append(template.format(company=pick_company_name(company_name)))
        # Mitigation sentences
        template = random.choice(fx_ir_mitigation_templates)
        verb = random.choice(mit_verbs)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_types=selected_ir_list,
            )
        )
        # May use hedge
        template = random.choice(ir_may_use_templates)
        verb = random.choice(verbs)
        swap_type = random.choice(swap_types)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_types=selected_ir_list,
            )
        )
        # Optional hedging template (0-1)
        template = random.choice(ir_optional_templates)
        verb = random.choice(verbs)
        swap_type = random.choice(swap_types)
        hedge_type = random.choice(hedge_types)
        sentence = template.format(
            company=pick_company_name(company_name),
            verb=verb,
            swap_types=selected_ir_list,
            hedge_type=hedge_type,
        )
        sentences.append(sentence)

        # Debt optimization (0-1)
        template = random.choice(ir_debt_optimization_templates)
        verb = random.choice(verbs)
        sentence = template.format(
            company=pick_company_name(company_name),
            verb=verb,
            swap_types=selected_ir_list,
        )
        sentences.append(sentence)
        return sentences

    def generate_cp_policy(commodity="commodity"):
        
        labels["deriv"] = 1
        labels["cp"] = 1
        labels["comm_ctx"] = 1

        if has_active_derivative:
            labels["curr"] = 1
        else:
            labels["spec"] = 1
            labels["spec_ctx"] = 1
        
        sentences = []
        selected_cp = []
        for _ in range(3):
            selected_cp.append(random.choice(swap_types))
            if random.random() < 0.5:
                break
        selected_cp_list = (
            ", ".join(selected_cp[:-1]) + " and " + selected_cp[-1]
            if len(selected_cp) > 1
            else selected_cp[0]
        )
        selected_co = [commodity if not commodity == "commodity" else commodity]
        for _ in range(2):
            selected_co.append(random.choice(commodities))
            if random.random() < 0.5:
                break
        selected_co_list = (
            ", ".join(selected_co[:-1]) + " and " + selected_co[-1]
            if len(selected_co) > 1
            else selected_co[0]
        )
        selected_co_list = selected_co_list if random.random() < 0.85 else "commodity"
        if has_active_derivative:
            verbs = hedge_use_verbs
        else:
            verbs = hedge_may_use_verbs
        # Context sentences
        template = random.choice(cp_context_templates)
        verb = random.choice(verbs)
        swap_type = random.choice(swap_types)
        cost_type = random.choice(cost_types)
        volume = generate_value(False)
        volume_unit = random.choice(volume_units)
        months_ahead = random.randint(6, 24)
        price = generate_value(False, 100)
        pct = generate_value(False, 99)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                commodity=selected_co_list,
                swap_types=selected_cp_list,
                cost_type=cost_type,
                currency_code=currency_code,
                months=months_ahead,
                volume=volume,
                volume_unit=volume_unit,
                price=price,
                pct=pct,
            )
        )

        # Impact sentences
        template = random.choice(cp_impact_templates)
        verb = random.choice(hedge_change_verbs)
        cost_type = random.choice(cost_types)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                commodity=selected_co_list,
                verb=verb,
                cost_type=cost_type,
            )
        )

        # May use hedge
        template = random.choice(cp_may_use_templates)
        verb = random.choice(verbs)
        swap_type = random.choice(swap_types)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_types=selected_cp_list,
                commodity=selected_co_list,
            )
        )

        template = random.choice(cp_strategy_templates)
        verb = random.choice(hedge_use_verbs)
        swap_type = random.choice(swap_types)
        amount = generate_value(False)
        notional = generate_value(False)
        event_year = random.choice(past_years) if past_years else current_year
        cost_type = random.choice(cost_types)
        sentence = template.format(
            company=pick_company_name(company_name),
            verb=verb,
            swap_type=swap_type,
            commodity=selected_co_list,
            month=random.choice(months),
            year=event_year,
            quarter=random.choice(quarters),
            currency_code=currency_code,
            amount=amount,
            notional=notional,
            money_unit=money_units,
            cost_type=cost_type,
        )
        sentences.append(sentence)
        return sentences

    def generate_hedge_policy():
        labels["deriv"] = 1
        labels["gen_ctx"] = 1
        
        if has_active_derivative:
            labels["curr"] = 1
        else:
            labels["spec"] = 1
            labels["spec_ctx"] = 1

        sentences = []
        if has_active_derivative:
            verbs = hedge_use_verbs
            mit_verbs = hedge_mitigation_verbs
        else:
            verbs = hedge_may_use_verbs
            mit_verbs = hedge_may_mitigation_verbs
        # Context (0-1)
        template = random.choice(hedge_context_templates)
        sentences.append(template.format(company=pick_company_name(company_name)))

        # Impact (0-1)
        template = random.choice(hedge_impact_templates)
        verb = random.choice(hedge_change_verbs)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                verb=verb,
            )
        )

        # Mitigation (0-1)
        template = random.choice(hedge_mitigation_templates)
        verb = random.choice(mit_verbs)
        sentences.append(
            template.format(company=pick_company_name(company_name), verb=verb)
        )

        # May use hedge
        may_use_template = random.choice(hedge_may_use_templates)
        verb = random.choice(verbs)
        swap_type = random.choice(swap_types)
        sentences.append(
            may_use_template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_type=swap_type,
            )
        )

        # Risk
        materiality_choice = random.choice(materiality)
        template = random.choice(risk_templates)
        item = (
            random.choice(swap_types)
            if random.random() < 0.5
            else random.choice(risk_items_derivative)
        )
        template.format(
            item=item,
            company=pick_company_name(company_name),
            materiality=materiality_choice,
        )
        return sentences

    def generate_hedge_policy_update():
        sentences = []
        labels["deriv"] = 1
        labels["spec"] = 1
        labels["spec_ctx"] = 1
        labels["gen_ctx"] = 1
        # ==============================
        # 1. ISSUANCE STATEMENT
        # ==============================
        template = random.choice(hedge_change_policy_templates)
        issuer = random.choice(shared_issuers)
        standard = random.choice(hedge_standards)
        topic = random.choice(
            [
                "derivatives and hedging",
                "hedging activities",
                "cash flow hedges",
                "fair value hedges",
            ]
        )
        purpose = random.choice(shared_purposes)
        description = random.choice(hedging_descriptions)
        extra = random.choice(hedging_additional_features)

        issue_month = random.choice(months)
        issue_year = random.randint(current_year - 8, current_year)
        effective_year = issue_year + random.randint(2, 4)
        eff_month = random.choice(months)
        eff_day = random.randint(15, 31)

        issuance_sentence = template.format(
            month=issue_month,
            year=issue_year,
            issuer=issuer,
            standard=standard,
            topic=topic,
            purpose=purpose,
            description=description,
            additional_feature=extra,
            eff_month=eff_month,
            eff_day=eff_day,
            eff_year=effective_year,
            company=pick_company_name(company_name),
        )
        sentences.append(issuance_sentence)

        # Optional: Add effective date
        if random.random() < 0.25:
            eff_line = random.choice(shared_effective_date_templates).format(
                company=pick_company_name(company_name),
                month=eff_month,
                day=random.randint(15, 31),
                end_day=random.randint(15, 31),
                year=effective_year,
            )
            sentences.append(eff_line)

        # Optional: Add transition/disclosure/practical expedient
        if random.random() < 0.2:
            trans_line = random.choice(shared_transition_templates).format(
                company=pick_company_name(company_name),
                method=random.choice(shared_adoption_methods),
                feature=random.choice(shared_transition_features),
            )
            sentences.append(trans_line)

        if random.random() < 0.2:
            disclosure_line = random.choice(shared_disclosure_change_templates).format(
                company=pick_company_name(company_name),
                disclosure_topic=random.choice(
                    ["derivative disclosures", "risk management strategies"]
                ),
                disclosure_topic2=random.choice(
                    ["hedge effectiveness", "notional amounts"]
                ),
                year=effective_year,
            )
            sentences.append(disclosure_line)

        if random.random() < 0.15:
            expedient_line = random.choice(shared_practical_expedient_templates).format(
                company=pick_company_name(company_name),
                expedient_description=random.choice(shared_transition_features),
            )
            sentences.append(expedient_line)

        # ==============================
        # 2. ADOPTION STATEMENT
        # ==============================
        adopt_template = random.choice(shared_adoption_status_templates)
        adopt_standard = random.choice(hedge_standards)
        adopt_method = random.choice(shared_adoption_methods)
        adopt_month = random.choice(months)
        adopt_day = random.randint(1, 28)
        adopt_year = random.randint(current_year - 8, current_year + 4)

        adoption_sentence = adopt_template.format(
            company=pick_company_name(company_name),
            standard=adopt_standard,
            method=adopt_method,
            month=adopt_month,
            day=adopt_day,
            year=adopt_year,
        )
        sentences.append(adoption_sentence)

        # Optional: Adoption impact
        if random.random() < 0.25:
            impact_line = random.choice(shared_adoption_impact_templates).format(
                company=pick_company_name(company_name),
                impact=random.choice(
                    [
                        "a reduction in earnings volatility",
                        "an increase in OCI from effective hedge portions",
                        "no material impact on the consolidated financial statements",
                    ]
                ),
            )
            sentences.append(impact_line)

        # ==============================
        # 3. EVALUATION STATEMENT
        # ==============================
        evaluation_sentence = random.choice(shared_evaluation_templates).format(
            company=pick_company_name(company_name)
        )
        sentences.append(evaluation_sentence)

        # Optional: Recently issued pronouncement
        if random.random() < 0.2:
            pronouncement = random.choice(shared_recent_pronouncement_templates).format(
                company=pick_company_name(company_name),
                issuer=random.choice(shared_issuers),
                standard=random.choice(hedge_standards),
                topic=random.choice(
                    [
                        "hedging relationships",
                        "cash flow hedge presentation",
                        "fair value hedge accounting",
                    ]
                ),
                month=random.choice(months),
                year=random.randint(current_year - 2, current_year),
                adoption_year=random.randint(current_year, current_year + 3),
            )
            sentences.append(pronouncement)

        return sentences

    def expire_hedge():
        sentences = []
        labels["deriv"] = 1
        labels["hist"] = 1
        # Termination (0-1)
        if random.random() < 0.05:
            template = random.choice(hedge_termination_templates)
            swap_type = random.choice(swap_types)
            term_year = random.choice(past_years) if past_years else current_year
            verb = random.choice(hedge_use_verbs)
            sentence = template.format(
                company=pick_company_name(company_name),
                swap_type=swap_type,
                quarter=random.choice(quarters),
                month=random.choice(months),
                year=term_year,
                end_day=random.randint(28, 31),
                verb=verb,
            )
            sentences.append(sentence)

        # Expiration (0-1)
        elif random.random() < 0.05:
            template = random.choice(hedge_expiration_templates)
            verb = random.choice(hedge_use_verbs)
            swap_type = random.choice(swap_types)
            exp_year = random.choice(past_years) if past_years else current_year
            sentence = template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_type=swap_type,
                quarter=random.choice(quarters),
                month=random.choice(months),
                year=exp_year,
            )
            sentences.append(sentence)
        elif random.random() < 0.05:
            template = random.choice(hedge_dedesignation_templates)
            swap_type = random.choice(swap_types)
            dedes_year = random.choice(past_years) if past_years else current_year
            sentence = template.format(
                company=pick_company_name(company_name),
                swap_type=swap_type,
                quarter=random.choice(quarters),
                month=random.choice(months),
                year=dedes_year,
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)
        return sentences

    def generate_additional_events():
        sentences = []
         labels["deriv"] = 1
        # Inherit curr/hist from has_active_derivative status
        if has_active_derivative:
            labels["curr"] = 1
        else:
            labels["hist"] = 1
        template = random.choice(hedge_quarterly_termination_templates)
        swap_type = random.choice(swap_types)
        past_year = random.choice(past_years)
        notional = generate_value(False)
        settlement = generate_value(False)
        sentence = template.format(
            company=pick_company_name(company_name),
            swap_type=swap_type,
            quarter=random.choice(quarters),
            month=random.choice(months),
            year=past_year,
            currency_code=currency_code,
            notional=notional,
            settlement=settlement,
            money_unit=money_units,
        )
        sentences.append(sentence)
        # Hedge transaction
        template = random.choice(hedge_transaction_templates)
        swap_type = random.choice(swap_types)
        notional = generate_value(False)
        sentences.append(
            template.format(
                company=pick_company_name(company_name),
                swap_type=swap_type,
                notional=notional,
                currency_code=currency_code,
                money_unit=money_units,
            )
        )
        template = random.choice(hedge_fv_position_templates)
        swap_type = random.choice(swap_types)
        position_type = random.choice(position_types)
        amount = generate_value(False)
        oci_amount = generate_value(False)
        oci_action = random.choice(oci_actions)
        sentence = template.format(
            company=pick_company_name(company_name),
            swap_type=swap_type,
            month=random.choice(months),
            end_day=random.randint(28, 31),
            year=current_year if has_active_derivative else current_year - 1,
            currency_code=currency_code,
            amount=amount,
            oci_amount=oci_amount,
            oci_action=oci_action,
            position_type=position_type,
            money_unit=money_units,
        )
        sentences.append(sentence)
        # Optional comparative (0-1)
        template = random.choice(hedge_optional_templates)
        verb = random.choice(hedge_use_verbs)
        swap_type = random.choice(swap_types)
        notional1 = generate_value(False) if has_active_derivative else 0
        notional2 = generate_value()
        year = current_year if has_active_derivative else current_year - 1
        prev_year = year - 1
        prev2_year = prev_year - 1
        sentence = template.format(
            company=pick_company_name(company_name),
            verb=verb,
            swap_type=swap_type,
            month=random.choice(months),
            end_day=random.randint(28, 31),
            year=year,
            prev_year=prev_year,
            prev2_year=prev2_year,
            currency_code=currency_code,
            notional1=notional1,
            notional2=notional2,
            money_unit=money_units,
        )
        sentences.append(sentence)
        return sentences

    def generate_derivative_sentences(positionOnly=False):
        """Generate derivative-related sentences for FX, IR, CP, or generic types."""
        sentences = []

        # --- Common fields ---
        verb = random.choice(hedge_use_verbs)
        swap_type = random.choice(swap_types)
        commodity = random.choice(commodities)
        cost_type = random.choice(cost_types)
        hedge_type = random.choice(hedge_types)

        month = random.choice(months)
        end_day = random.randint(28, 31)
        quarter = random.choice(quarters)

        selected_swap = []
        for _ in range(3):
            selected_swap.append(random.choice(swap_types))
            if random.random() < 0.5:
                break
        selected_swap_list = (
            ", ".join(selected_swap[:-1]) + " and " + selected_swap[-1]
            if len(selected_swap) > 1
            else selected_swap[0]
        )

        # --- FX: add currency description sentence (0-1 chance) ---
        if swapType == "fx" and random.random() < 0.6:
            selected = random.sample(major_currencies, random.randint(2, 3))
            if random.random() < 0.5:
                selected += random.sample(european_currencies, random.randint(1, 2))
            if random.random() < 0.4:
                selected += random.sample(asian_currencies, random.randint(1, 2))
            if random.random() < 0.3:
                selected += random.sample(americas_currencies, random.randint(1, 2))
            selected = list(dict.fromkeys(selected))
            currency_list = (
                ", ".join(selected[:-1]) + " and " + selected[-1]
                if len(selected) > 1
                else selected[0]
            )
            if random.random() < 0.3:
                currency_list += " and other European and Latin American currencies"
            sentences.append(
                random.choice(fx_currency_templates).format(
                    company=pick_company_name(company_name),
                    currencies=currency_list,
                )
            )
        # IR: Add a chance of debt
        if swapType == "ir" and random.random() < 0.15:
            labels["debt_ctx"] = 1  # IR usually relates to debt context
            debt_type_list = []
            # Build the debt type combination
            for _ in range(3):
                debt_type_list.append(random.choice(debt_types_list))
                if random.random() < 0.95:
                    break
            selected_debt = (
                ", ".join(debt_type_list[:-1]) + " and " + debt_type_list[-1]
                if len(debt_type_list) > 1
                else debt_type_list[0]
            )
            for _ in range(random.randint(1, 3)):
                template = random.choice(debt_templates)
                amount = generate_value(False)
                amount2 = generate_value(False)
                pct = generate_value(False, 8)
                pct2 = generate_value(False, 20)
                outstanding = random.randint(0, int(amount) // 2)
                debt_type = random.choice(debt_types_list)
                maturity_year = current_year + random.randint(3, 10)
                years = random.randint(3, 10)
                sentence = template.format(
                    amount=amount,
                    amount2=amount2,
                    year=maturity_year,
                    month=month,
                    outstanding=outstanding,
                    current_year=current_year,
                    debt_types=selected_debt,
                    debt_type=debt_type,
                    maturity_year=maturity_year,
                    company=pick_company_name(company_name),
                    currency_code=currency_code,
                    major_currency=major_currency,
                    money_unit=money_units,
                    end_day=end_day,
                    pct=pct,
                    pct2=pct2,
                    years=years,
                    hedge_type=hedge_type,
                )
                sentences.append(sentence)

        # --- Select appropriate template set ---
        chance = random.random() < 0.90 or not has_active_derivative or positionOnly
        if swapType == "fx":
            if chance:
                template = random.choice(fx_position_template)
            else:
                template = random.choice(fx_may_use_templates)
                verb = random.choice(hedge_use_verbs)
        elif swapType == "ir":
            if chance:
                template = random.choice(ir_position_template)
            else:
                template = random.choice(ir_may_use_templates)
                verb = random.choice(hedge_use_verbs)
        elif swapType == "cp":
            if chance:
                template = random.choice(cp_position_template)
            else:
                template = random.choice(cp_may_use_templates)
                verb = random.choice(hedge_use_verbs)
        else:
            if chance:
                # generic fallback
                template = random.choice(
                    hedge_position_templates
                    if random.random() < 0.85
                    else eq_position_templates
                )
            else:
                template = random.choice(hedge_may_use_templates)
                verb = random.choice(hedge_use_verbs)

        # --- Time logic ---
        year = current_year if has_active_derivative else current_year - 1
        prev_year, prev2_year = year - 1, year - 2
        old_year = random.choice(past_years) - 1 if past_years else prev_year
        future_year = (
            random.randint(current_year + 1, current_year + 5)
            if has_active_derivative
            else random.randint(old_year - 1, prev_year)
        )

        # --- Notionals ---
        notional = (
            generate_value(False)
            if has_active_derivative
            else (generate_value(False) if random.random() < 0.5 else 0)
        )
        prev_notional = generate_value()
        prev2_notional = generate_value()
        old_notional = generate_value(False)

        # --- Build main sentence ---
        sentence = template.format(
            company=pick_company_name(company_name),
            verb=verb,
            swap_type=swap_type,
            swap_types=selected_swap_list,
            commodity=commodity,
            month=month,
            end_day=end_day,
            quarter=quarter,
            year=year,
            prev_year=prev_year,
            prev2_year=prev2_year,
            old_year=old_year,
            future_year=future_year,
            currency_code=currency_code,
            notional=notional,
            prev_notional=prev_notional,
            prev2_notional=prev2_notional,
            old_notional=old_notional,
            money_unit=money_units,
            cost_type=cost_type,
            hedge_type=hedge_type,
        )
        sentences.append(sentence)

        # --- Expired hedges for non-active derivatives ---
        if not has_active_derivative:
            sentences.extend(expire_hedge())

        return sentences

    # Label 2: Policy/disclosure only (no specific positions)
    if has_active_derivative is None:
        labels["deriv"] = 1
        labels["spec"] = 1
        labels["spec_ctx"] = 1
        labels["gen_ctx"] = 1
        # Accounting policy (always)
        act_template = random.choice(hedge_policy_templates)
        swap_type = (
            random.choice(swap_types) if random.random() < 0.5 else "derivatives"
        )
        hedge_type = random.choice(hedge_types)
        all_sentences.append(
            act_template.format(
                company=pick_company_name(company_name),
                swap_type=swap_type,
                hedge_type=hedge_type,
            )
        )

        # No trading policy (always)
        nt_template = random.choice(hedge_no_trading_templates)
        all_sentences.append(
            nt_template.format(
                company=pick_company_name(company_name),
                verb=random.choice(hedge_may_use_verbs),
            )
        )
        # Documentation (0-1)
        template = random.choice(hedge_documentation_templates)
        hedge_type = random.choice(hedge_types)
        all_sentences.append(
            template.format(
                company=pick_company_name(company_name),
                hedge_type=hedge_type,
            )
        )

        # Effectiveness (0-1)
        template = random.choice(hedge_effectiveness_templates)
        hedge_type = random.choice(hedge_types)
        swap_type = random.choice(swap_types)
        metric = random.choice(hedge_metrics)
        frequency = random.choice(frequencies)
        verb = random.choice(assessment_verbs)
        method = random.choice(hedge_methods)
        standard = random.choice(hedge_standards)
        sentence = template.format(
            company=pick_company_name(company_name),
            hedge_type=hedge_type,
            swap_type=swap_type,
            metric=metric,
            frequency=frequency,
            verb=verb,
            method=method,
            standard=standard,
        )
        all_sentences.append(sentence)

        # Ineffectiveness (0-1)
        template = random.choice(hedge_ineffectiveness_templates)
        frequency = random.choice(frequencies)
        all_sentences.append(
            template.format(
                company=pick_company_name(company_name),
                frequency=frequency,
            )
        )

        # Discontinuation (0-1)
        template = random.choice(hedge_discontinuation_templates)
        all_sentences.append(
            template.format(
                company=pick_company_name(company_name),
            )
        )

        # Counterparty risk (0-1)
        template = random.choice(hedge_counterparty_templates)
        all_sentences.append(template.format(company=pick_company_name(company_name)))
    # Labels 0 and 1: Specific positions
    else:
        # Past event (0-1)
        if random.random() < 0.10:
            labes["hist"] = 1
            template = random.choice(hedge_no_such_outstanding_template)
            swap_type = random.choice(swap_types)
            verb = random.choice(hedge_use_verbs)
            year = current_year if not has_active_derivative else current_year - 1
            prev_year = year - 1
            prev2_year = prev_year - 1
            sentence = template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_type=swap_type,
                month=random.choice(months),
                end_day=random.randint(28, 31),
                year=year,
                prev_year=prev_year,
                prev2_year=prev2_year,
                quarter=random.choice(quarters),
            )
            all_sentences.append(sentence)

        # Main generator
        all_sentences.extend(generate_derivative_sentences())

    # Shuffle and select sentences
    random.shuffle(all_sentences)
    if has_active_derivative is None:
        # Policy only no need for label management
        selected_sentences = all_sentences[:max_len]
    else:
        selected_sentences = all_sentences
    # Context sentences
    if include_policy or len(selected_sentences) < 2:
        if (
            has_active_derivative is not None
            and random.random() < 0.33
            or len(selected_sentences) < 2
        ):
            if random.random() < 0.35:
                sentences = generate_additional_events()
            else:
                sentences = generate_derivative_sentences(True)
        else:
            if swapType == "cp":
                sentences = generate_cp_policy(commodity)
            elif swapType == "ir":
                sentences = generate_ir_policy()
                # Pick only 1-2 sentences
                random.shuffle(sentences)
            elif swapType == "fx":
                sentences = generate_fx_policy()
            else:
                if random.random() < 0.5:
                    sentences = generate_hedge_policy()
                else:
                    sentences = generate_hedge_policy_update()
        sentences = sentences[: random.randint(1, 2)]
        selected_sentences.extend(sentences)
        random.shuffle(selected_sentences)
    # Capitalize first letter of each sentence
    selected_sentences = [
        s[0].upper() + s[1:] if s and len(s) > 0 else "" for s in selected_sentences
    ]
    # Clean up common formatting issues
    paragraph = cleanup(paragraph, reporting_year)

    return paragraph, label, labels


def generate_accounting_noise_paragraph(
    year_range=(1990, 2025), max_len=random.randint(2, 4), company_name=None
):
    """
    Generate synthetic accounting paragraphs that are pure noise - nothing to do with derivatives.
    This is Label 3: accounting discussions about lawsuits, equity warrants, balance sheet items,
    revenue recognition, inventory, PP&E, leases, etc. - but NO derivative instruments.

    Args:
        year_range (tuple): (min_year, max_year) for reporting year
        max_len (int): Maximum number of sentences

    Returns:
        tuple: (paragraph_text, label=3)
    """

    if company_name is None:
        if random.random() < 0.85:
            company_name = random.choice(company_names)
        else:
            company_name = "The Company"

    acquisition_targets = [name for name in company_names if name != company_name]
    current_year = random.randint(year_range[0], year_range[1])
    reporting_year = current_year
    all_sentences = []
    money_units = random.choice(money_unit_list)
    currency_code = random.choice(currency_codes)
    major_currency = random.choice(all_currencies)
    target_companies = [name for name in company_names if name != company_name]

    def generate_other_policy_update():
        sentences = []

        # ==============================
        # 1. ISSUANCE STATEMENT
        # ==============================
        template = random.choice(general_policy_templates)
        issuer = random.choice(shared_issuers)
        standard = random.choice(other_standard_names)
        topic = random.choice(shared_topics)
        purpose = random.choice(shared_purposes)
        description = random.choice(general_descriptions)
        extra = random.choice(general_additional_features)

        issue_month = random.choice(months)
        issue_year = random.randint(current_year - 5, current_year)
        effective_year = issue_year + random.randint(2, 4)
        eff_month = random.choice(months)
        eff_day = random.randint(15, 31)

        issuance_sentence = template.format(
            month=issue_month,
            year=issue_year,
            issuer=issuer,
            standard=standard,
            topic=topic,
            purpose=purpose,
            description=description,
            additional_feature=extra,
            eff_month=eff_month,
            eff_day=eff_day,
            eff_year=effective_year,
            company=pick_company_name(company_name),
        )
        sentences.append(issuance_sentence)

        # Optional: Add effective date, transition, disclosure, expedient
        if random.random() < 0.3:
            eff_line = random.choice(shared_effective_date_templates).format(
                company=pick_company_name(company_name),
                month=eff_month,
                day=random.randint(1, 28),
                end_day=random.randint(15, 31),
                year=effective_year,
            )
            sentences.append(eff_line)

        if random.random() < 0.2:
            trans_line = random.choice(shared_transition_templates).format(
                company=pick_company_name(company_name),
                method=random.choice(shared_adoption_methods),
                feature=random.choice(shared_transition_features),
            )
            sentences.append(trans_line)

        if random.random() < 0.25:
            disclosure_line = random.choice(shared_disclosure_change_templates).format(
                company=pick_company_name(company_name),
                disclosure_topic=random.choice(
                    [
                        "lease assets",
                        "revenue recognition policies",
                        "credit loss assumptions",
                    ]
                ),
                disclosure_topic2=random.choice(
                    ["disaggregation of revenue", "allowance methodology"]
                ),
                year=effective_year,
            )
            sentences.append(disclosure_line)

        if random.random() < 0.15:
            expedient_line = random.choice(shared_practical_expedient_templates).format(
                company=pick_company_name(company_name),
                expedient_description=random.choice(shared_transition_features),
            )
            sentences.append(expedient_line)

        # ==============================
        # 2. ADOPTION STATEMENT
        # ==============================
        adopt_template = random.choice(shared_adoption_status_templates)
        adopt_standard = random.choice(other_standard_names)
        adopt_method = random.choice(shared_adoption_methods)
        adopt_month = random.choice(months)
        adopt_day = random.randint(1, 28)
        adopt_year = random.randint(current_year - 8, current_year + 4)

        adoption_sentence = adopt_template.format(
            company=pick_company_name(company_name),
            standard=adopt_standard,
            method=adopt_method,
            month=adopt_month,
            day=adopt_day,
            year=adopt_year,
        )
        sentences.append(adoption_sentence)

        # Optional: Adoption impact
        if random.random() < 0.3:
            impact_line = random.choice(shared_adoption_impact_templates).format(
                company=pick_company_name(company_name),
                impact=random.choice(
                    [
                        "recognition of additional lease liabilities",
                        "a change in timing of revenue recognition",
                        "no material impact on consolidated results",
                    ]
                ),
            )
            sentences.append(impact_line)

        # ==============================
        # 3. EVALUATION STATEMENT
        # ==============================
        evaluation_sentence = random.choice(shared_evaluation_templates).format(
            company=pick_company_name(company_name)
        )
        sentences.append(evaluation_sentence)

        # Optional: Recently issued pronouncement
        if random.random() < 0.25:
            pronouncement = random.choice(shared_recent_pronouncement_templates).format(
                company=pick_company_name(company_name),
                issuer=random.choice(shared_issuers),
                standard=random.choice(other_standard_names),
                topic=random.choice(shared_topics),
                month=random.choice(months),
                year=random.randint(current_year - 2, current_year),
                adoption_year=random.randint(current_year, current_year + 3),
            )
            sentences.append(pronouncement)

        # Risk
        materiality_choice = random.choice(materiality)
        template = random.choice(risk_templates)
        item = random.choice(risk_items_other)
        sentence = template.format(
            item=item,
            company=pick_company_name(company_name),
            materiality=materiality_choice,
        )
        sentences.append(sentence)
        return sentences

    # ================== SENTENCE GENERATION ==================
    # Litigation (0-2 sentences)
    num_litigation = random.randint(1, 3)
    for _ in range(num_litigation):
        sentences = []
        template = random.choice(litigation_templates)
        case_type = random.choice(case_types)
        court = random.choice(courts)
        sentence = template.format(
            year=current_year,
            case_types=case_type,
            company=pick_company_name(company_name),
            court=court,
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
            month=random.choice(months),
            end_day=random.randint(28, 31),
        )
        sentences.append(sentence)
        if random.random() < 0.5:
            template = random.choice(litigation_assessment_templates)
            verb = random.choice(assessment_verbs)
            sentence = template.format(
                company=pick_company_name(company_name), verb=verb
            )
            sentences.append(sentence)
        if random.random() < 0.5:
            template = random.choice(guarantee_templates)
            amount = round(random.uniform(10, 100), 1)
            payments = round(amount * random.uniform(0.1, 0.3), 1)
            guarantee_type = random.choice(guarantee_types)
            sentence = template.format(
                amount=amount,
                year=current_year,
                month=random.choice(months),
                payments=payments,
                guarantee_type=guarantee_type,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)
        all_sentences.append(sentences)

    # Restructuring (0-1)
    template = random.choice(restructuring_templates)
    amount = round(random.uniform(10, 80), 1)
    purpose = random.choice(restructuring_purposes)
    expense_type = random.choice(restructuring_expense_types)
    month = random.choice(months)
    sentence = template.format(
        year=current_year,
        amount=amount,
        purpose=purpose,
        expense_type=expense_type,
        month=month,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    all_sentences.append([sentence])

    # Non-cash transactions (0-1)
    sentences = []
    if random.random() < 0.8:
        # Warrant issuance as debt costs
        template = random.choice(warrant_debt_issuance_templates)
        month = random.choice(months)
        year = random.choice([current_year, current_year - 1])
        financing_type = random.choice(financing_types)
        shares1 = random.choice([100000, 200000, 333334, 400000, 496875])
        shares2 = random.choice([20834, 50000, 100000, 150000])
        value1 = round(shares1 * random.uniform(0.25, 0.75), 0)
        value2 = round(shares2 * random.uniform(0.15, 0.50), 0)
        shares = shares1
        value = value1

        sentence = template.format(
            month=month,
            year=year,
            end_day=random.randint(28, 31),
            financing_type=financing_type,
            shares1=f"{shares1:,}",
            shares2=f"{shares2:,}",
            value1=f"{value1:,}",
            value2=f"{value2:,}",
            shares=f"{shares:,}",
            value=f"{value:,}",
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
        )
        sentences.append(sentence)

    if random.random() < 0.5:
        # Warrant amortization
        template = random.choice(warrant_amortization_templates)
        asset_type = random.choice(asset_types)
        value = round(random.uniform(50, 500), 0)
        value2 = round(random.uniform(50, 500), 0)
        sentence = template.format(
            asset_type=asset_type,
            value=f"{value:,}",
            value2=f"{value:,}",
            year=current_year,
            prev_year=current_year - 1,
            month=random.choice(months),
            end_day=random.randint(28, 31),
            debt_types_list=random.choice(debt_types_list),
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
            price=random.choice([5000, 10000, 15000, 17500, 20000]),
        )
        sentences.append(sentence)
    if random.random() < 0.5:
        # Non-cash settlements
        template = random.choice(non_cash_settlement_templates)
        shares = random.choice([5000, 10000, 15000, 17500, 20000])
        value = round(shares * random.uniform(4, 8), 0)
        service_type = random.choice(service_types)
        month = random.choice(months)
        year = random.choice([current_year, current_year - 1])

        sentence = template.format(
            shares=f"{shares:,}",
            value=f"{value:,}",
            service_type=service_type,
            month=month,
            end_day=random.randint(28, 31),
            year=year,
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
        )
        sentences.append(sentence)
    all_sentences.append(sentences)

    # Acquisitions (0-1)
    template = random.choice(acquisition_templates)
    target = random.choice(acquisition_targets)
    amount = round(random.uniform(50, 500), 1)
    goodwill = round(amount * random.uniform(0.3, 0.5), 1)
    intangibles = round(amount * random.uniform(0.2, 0.4), 1)
    month = random.choice(months)
    purpose = random.choice(acquisition_purposes)
    funding = random.choice(acquisition_funding)
    sentence = template.format(
        month=month,
        year=current_year,
        target=target,
        amount=amount,
        goodwill=goodwill,
        intangibles=intangibles,
        purpose=purpose,
        funding=funding,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    all_sentences.append([sentence])

    # Lawsuits (0-1)
    template = random.choice(specific_lawsuit_templates)
    month = random.choice(months)
    year = random.choice([current_year, current_year - 1])
    dismiss_year = year + 1
    court = random.choice(courts)
    allegation = random.choice(allegations)
    amount = random.choice([10, 25, 50, 75, 100, 150, 200])
    quarter = random.choice(quarters)

    sentence = template.format(
        month=month,
        year=year,
        dismiss_year=dismiss_year,
        court=court,
        allegation=allegation,
        amount=amount,
        quarter=quarter,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    all_sentences.append([sentence])

    # Revenue recognition (0-1)
    sentences = []
    sentence = random.choice(revenue_recognition_templates)
    sentence = sentence.format(company=pick_company_name(company_name))
    sentences.append(sentence)
    if random.random() < 0.75:
        template = random.choice(deferred_revenue_templates)
        amount = round(random.uniform(10, 100), 1)
        prev_amount = round(amount * random.uniform(0.8, 1.2), 1)
        sentence = template.format(
            year=current_year,
            month=random.choice(months),
            amount=amount,
            prev_amount=prev_amount,
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
            end_day=random.randint(28, 31),
        )
        sentences.append(sentence)
    all_sentences.append(sentences)

    # Inventory (0-1)
    sentences = []
    template = random.choice(inventory_templates)
    method = random.choice(inventory_methods)
    amount = round(random.uniform(50, 300), 1)
    reserve = round(amount * random.uniform(0.05, 0.15), 1)
    selected_co = []
    for _ in range(3):
        selected_co.append(random.choice(commodities))
        if random.random() < 0.5:
            break
    selected_co_list = (
        ", ".join(selected_co[:-1]) + " and " + selected_co[-1]
        if len(selected_co) > 1
        else selected_co[0]
    )
    sentence = template.format(
        method=method,
        year=current_year,
        month=random.choice(months),
        amount=amount,
        reserve=reserve,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
        items=selected_co_list,
    )
    sentences.append(sentence)
    if random.random() < 0.75:
        template = random.choice(inventory_writedown_templates)
        amount = round(random.uniform(2, 20), 1)
        prev_amount = round(random.uniform(amount, amount + 20), 1)
        sentence = template.format(
            year=current_year,
            amount=amount,
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
            month=random.choice(months),
            end_day=random.randint(28, 31),
            prev_amount=prev_amount,
            items=selected_co_list,
        )
        sentences.append(sentence)
    all_sentences.append(sentences)

    # PP&E (0-1)
    sentences = []
    template = random.choice(ppe_templates)
    amount = round(random.uniform(100, 500), 1)
    purpose = random.choice(capex_purposes)
    sentence = template.format(
        month=random.choice(months),
        end_day=random.randint(28, 31),
        amount=amount,
        year=current_year,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        purpose=purpose,
    )
    sentences.append(sentence)
    if random.random() < 0.7:
        template = random.choice(capex_templates)
        amount = round(random.uniform(20, 150), 1)
        purpose = random.choice(capex_purposes)
        sentence = template.format(
            year=current_year,
            month=random.choice(months),
            amount=amount,
            purpose=purpose,
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
        )
        sentences.append(sentence)
    if random.random() < 0.7:
        template = random.choice(impairment_templates)
        amount = round(random.uniform(5, 50), 1)
        asset_type = random.choice(asset_types)
        quarter = random.choice(quarters)
        sentence = template.format(
            amount=amount,
            year=current_year,
            month=random.choice(months),
            quarter=quarter,
            asset_type=asset_type,
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
            end_day=random.randint(28, 31),
        )
        sentences.append(sentence)
    all_sentences.append(sentences)

    # Leases (0-1)
    sentences = []
    template = random.choice(lease_templates)
    min_term = random.randint(1, 3)
    max_term = random.randint(5, 15)
    amount = round(random.uniform(50, 200), 1)
    liability = round(amount * random.uniform(1.0, 1.1), 1)
    adoption_year = random.randint(2019, 2020)
    sentence = template.format(
        min_term=min_term,
        max_term=max_term,
        year=current_year,
        month=random.choice(months),
        amount=amount,
        liability=liability,
        adoption_year=adoption_year,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    sentences.append(sentence)
    if random.random() < 0.7:
        template = random.choice(lease_commitment_templates)
        amount = round(random.uniform(100, 800), 1)
        amount2 = round(random.uniform(100, 600), 1)
        amount3 = round(random.uniform(100, 400), 1)
        pv_amount = round(random.uniform(100, 900), 1)
        years = round(random.uniform(3, 8), 1)
        rate = (round(random.uniform(3.0, 7.0), 1),)
        sentence = template.format(
            amount=amount,
            amount2=amount2,
            amount3=amount3,
            year=current_year,
            next_year=current_year + 1,
            next2_year=current_year + 2,
            years=years,
            month=random.choice(months),
            rate=rate,
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
            end_day=random.randint(28, 31),
            pv_amount=pv_amount,
        )
        sentences.append(sentence)
    all_sentences.append(sentences)

    # Goodwill and Intangibles (0-1)
    sentences = []
    template = random.choice(goodwill_templates)
    amount = round(random.uniform(200, 1000), 1)
    quarter = random.choice(quarters)
    sentence = template.format(
        amount=amount,
        year=current_year,
        quarter=quarter,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        month=random.choice(months),
        end_day=random.randint(28, 31),
        verb=random.choice(assessment_verbs),
    )
    sentences.append(sentence)
    template = random.choice(intangible_templates)
    amount = round(random.uniform(50, 300), 1)
    years = round(random.uniform(5, 12), 1)
    intangible_type = random.choice(intangible_types)
    sentence = template.format(
        intangible_types=intangible_type,
        amount=amount,
        year=current_year,
        month=random.choice(months),
        years=years,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    sentences.append(sentence)
    all_sentences.append(sentences)

    # Debt (0-1)
    for _ in range(2):
        sentences = []
        debt_type_list = []

        # Build the debt type combination
        for _ in range(3):
            debt_type_list.append(random.choice(debt_types_list))
            if random.random() < 0.5:
                break

        selected_debt = (
            ", ".join(debt_type_list[:-1]) + " and " + debt_type_list[-1]
            if len(debt_type_list) > 1
            else debt_type_list[0]
        )

        # --- Generate multiple related debt statements ---
        for _ in range(random.randint(5, 10)):  # Boost debt related topics
            amount = generate_value(False)
            amount2 = generate_value(False)
            pct = generate_value(False, 8)
            pct2 = generate_value(False, 20)
            outstanding = random.randint(0, int(amount) // 2)
            debt_type = random.choice(debt_types_list)
            maturity_year = current_year + random.randint(3, 10)
            years = random.randint(3, 10)
            template = random.choice(debt_templates)
            sentence = template.format(
                amount=amount,
                amount2=amount2,
                year=maturity_year,
                month=random.choice(months),
                outstanding=outstanding,
                current_year=current_year,
                debt_types=selected_debt,
                debt_type=debt_type,
                maturity_year=maturity_year,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
                pct=pct,
                pct2=pct2,
                years=years,
            )
            sentences.append(sentence)

        # --- Add a covenant / compliance statement at the end ---
        if random.random() < 0.5:
            template = random.choice(debt_covenant_templates)
            ratio = round(random.uniform(2.5, 4.0), 1)
            coverage = round(random.uniform(2.0, 4.0), 1)
            covenant_sentence = template.format(
                year=current_year,
                month=random.choice(months),
                end_day=random.randint(28, 31),
                ratio=ratio,
                coverage=coverage,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
            )
            sentences.append(covenant_sentence)

        # --- Merge into a single coherent text block ---
        merged_text = ". ".join(sentences)
        all_sentences.append([merged_text])

    # Income taxes (0-1)
    sentences = []
    template = random.choice(tax_templates)
    amount = round(random.uniform(20, 150), 1)
    rate = round(random.uniform(15, 30), 1)
    prev_rate = round(rate * random.uniform(0.9, 1.1), 1)
    source = random.choice(tax_sources)
    start_year = current_year + 1
    end_year = current_year + random.randint(10, 20)
    sentence = template.format(
        amount=amount,
        year=current_year,
        rate=rate,
        month=random.choice(months),
        prev_rate=prev_rate,
        sources=source,
        start_year=start_year,
        end_year=end_year,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    sentences.append(sentence)
    if random.random() < 0.5:
        template = random.choice(uncertain_tax_templates)
        amount = round(random.uniform(5, 50), 1)
        sentence = template.format(
            amount=amount,
            year=current_year,
            month=random.choice(months),
            end_day=random.randint(28, 31),
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
        )
        sentences.append(sentence)
    all_sentences.append(sentences)

    # Pension (0-1)
    sentences = []
    template = random.choice(pension_templates)
    assets = round(random.uniform(200, 800), 1)
    obligations = round(assets * random.uniform(1.0, 1.2), 1)
    amount = round(random.uniform(20, 100), 1)
    sentence = template.format(
        assets=assets,
        obligations=obligations,
        year=current_year,
        month=random.choice(months),
        amount=amount,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    sentences.append(sentence)
    if random.random() < 0.5:
        template = random.choice(opeb_templates)
        amount = round(random.uniform(50, 200), 1)
        sentence = template.format(
            amount=amount,
            year=current_year,
            month=random.choice(months),
            end_day=random.randint(28, 31),
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
        )
        sentences.append(sentence)
    all_sentences.append(sentences)

    # Commitments (0-1)
    sentences = []
    template = random.choice(purchase_commitment_templates)
    amount = round(random.uniform(50, 300), 1)
    years = random.randint(3, 7)
    sentence = template.format(
        amount=amount,
        year=current_year,
        years=years,
        month=random.choice(months),
        end_day=random.randint(28, 31),
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
    )
    sentences.append(sentence)
    if random.random() < 0.5:
        template = random.choice(guarantee_templates)
        amount = round(random.uniform(10, 100), 1)
        payments = round(amount * random.uniform(0.1, 0.3), 1)
        guarantee_type = random.choice(guarantee_types)
        sentence = template.format(
            amount=amount,
            year=current_year,
            month=random.choice(months),
            payments=payments,
            guarantee_type=guarantee_type,
            company=pick_company_name(company_name),
            currency_code=currency_code,
            major_currency=major_currency,
            money_unit=money_units,
            end_day=random.randint(28, 31),
        )
        sentences.append(sentence)
    all_sentences.append(sentences)

    # Restructuring (0-1)
    template = random.choice(restructuring_templates)
    amount = round(random.uniform(10, 80), 1)
    purpose = random.choice(restructuring_purposes)
    expense_type = random.choice(restructuring_expense_types)
    month = random.choice(months)
    sentence = template.format(
        year=current_year,
        amount=amount,
        purpose=purpose,
        expense_type=expense_type,
        month=month,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    all_sentences.append([sentence])

    # Acquisitions (0-1)
    template = random.choice(acquisition_templates)
    target = random.choice(acquisition_targets)
    amount = round(random.uniform(50, 500), 1)
    goodwill = round(amount * random.uniform(0.3, 0.5), 1)
    intangibles = round(amount * random.uniform(0.2, 0.4), 1)
    month = random.choice(months)
    purpose = random.choice(acquisition_purposes)
    funding = random.choice(acquisition_funding)
    sentence = template.format(
        month=month,
        year=current_year,
        target=target,
        amount=amount,
        goodwill=goodwill,
        intangibles=intangibles,
        purpose=purpose,
        funding=funding,
        company=pick_company_name(company_name),
        currency_code=currency_code,
        major_currency=major_currency,
        money_unit=money_units,
        end_day=random.randint(28, 31),
    )
    all_sentences.append([sentence])

    # Balance sheet changes (0-2 sentences)
    num_bs_changes = random.randint(0, 2)
    for _ in range(num_bs_changes):
        sentences = []

        if random.random() < 0.5:
            template = random.choice(ar_templates)
            amount = round(random.uniform(10, 150), 1)
            prev_amount = round(amount * random.uniform(0.8, 1.2), 1)
            ending = round(random.uniform(50, 300), 1)
            days = random.randint(35, 75)
            prev_days = random.randint(40, 80)

            sentence = template.format(
                money_unit=money_units,
                currency_code=currency_code,
                end_day=random.randint(28, 31),
                month=random.choice(months),
                company=pick_company_name(company_name),
                amount=amount,
                prev_amount=prev_amount,
                ending=ending,
                year=current_year,
                prev_year=current_year - 1,
                days=days,
                prev_days=prev_days,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(ap_templates)
            amount = round(random.uniform(5, 100), 1)
            prev_amount = round(amount * random.uniform(0.7, 1.3), 1)
            days = random.randint(30, 60)
            prev_days = random.randint(25, 55)
            reason = random.choice(balance_sheet_reasons)

            sentence = template.format(
                money_unit=money_units,
                end_day=random.randint(28, 31),
                currency_code=currency_code,
                month=random.choice(months),
                company=pick_company_name(company_name),
                amount=amount,
                prev_amount=prev_amount,
                year=current_year,
                prev_year=current_year - 1,
                days=days,
                prev_days=prev_days,
                reason=reason,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(accrued_liabilities_templates)
            amount = round(random.uniform(5, 80), 1)
            change = round(random.uniform(2, 30), 1)
            reason = random.choice(accrued_reasons)

            sentence = template.format(
                amount=amount,
                change=change,
                year=current_year,
                currency_code=currency_code,
                reason=reason,
                money_unit=money_units,
                end_day=random.randint(28, 31),
                month=random.choice(months),
                company=pick_company_name(company_name),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(working_capital_templates)
            amount = round(random.uniform(50, 300), 1)
            prev_amount = round(amount * random.uniform(0.8, 1.2), 1)
            direction = random.choice(["use", "source"])
            reason = random.choice(balance_sheet_reasons)

            sentence = template.format(
                amount=amount,
                prev_amount=prev_amount,
                direction=direction,
                currency_code=currency_code,
                year=current_year,
                prev_year=current_year - 1,
                reason=reason,
                money_unit=money_units,
                end_day=random.randint(28, 31),
                month=random.choice(months),
                company=pick_company_name(company_name),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(other_current_assets_templates)
            amount = round(random.uniform(5, 50), 1)
            ending = round(random.uniform(20, 100), 1)
            reason = random.choice(other_asset_reasons)

            sentence = template.format(
                amount=amount,
                ending=ending,
                year=current_year,
                currency_code=currency_code,
                reason=reason,
                money_unit=money_units,
                end_day=random.randint(28, 31),
                month=random.choice(months),
                company=pick_company_name(company_name),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(other_liabilities_templates)
            amount = round(random.uniform(10, 100), 1)
            prev_amount = round(amount * random.uniform(0.8, 1.2), 1)
            ending = round(random.uniform(50, 200), 1)
            reason = random.choice(liability_reasons)

            sentence = template.format(
                amount=amount,
                prev_amount=prev_amount,
                currency_code=currency_code,
                ending=ending,
                year=current_year,
                reason=reason,
                money_unit=money_units,
                end_day=random.randint(28, 31),
                month=random.choice(months),
                company=pick_company_name(company_name),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            if random.random() < 0.5:
                template = random.choice(stockholders_equity_templates)
                amount = round(random.uniform(20, 200), 1)
                prev_amount = round(amount * random.uniform(0.7, 1.3), 1)
                ending = round(random.uniform(100, 500), 1)
                reason = random.choice(equity_reasons)
                month = random.choice(months)

                sentence = template.format(
                    amount=amount,
                    prev_amount=prev_amount,
                    ending=ending,
                    year=current_year,
                    currency_code=currency_code,
                    prev_year=current_year - 1,
                    reason=reason.format(
                        month=month, year=current_year, end_day=random.randint(28, 31)
                    ),
                    money_unit=money_units,
                    end_day=random.randint(28, 31),
                    month=random.choice(months),
                    company=pick_company_name(company_name),
                )
            else:
                template = random.choice(retained_earnings_templates)
                amount = round(random.uniform(50, 500), 1)
                ni = round(random.uniform(30, 200), 1)
                div = round(random.uniform(5, 50), 1)
                ending = round(random.uniform(100, 600), 1)

                sentence = template.format(
                    amount=amount,
                    ni=ni,
                    div=div,
                    ending=ending,
                    year=current_year,
                    money_unit=money_units,
                    currency_code=currency_code,
                    end_day=random.randint(28, 31),
                    month=random.choice(months),
                    company=pick_company_name(company_name),
                )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(cash_flow_statement_templates)
            amount = round(random.uniform(20, 200), 1)
            prev_amount = round(amount * random.uniform(0.7, 1.3), 1)
            reason = random.choice(balance_sheet_reasons)

            sentence = template.format(
                amount=amount,
                prev_amount=prev_amount,
                year=current_year,
                prev_year=current_year - 1,
                currency_code=currency_code,
                reason=reason,
                money_unit=money_units,
                end_day=random.randint(28, 31),
                month=random.choice(months),
                company=pick_company_name(company_name),
            )
            sentences.append(sentence)

        if random.random() < 0.5:  # general balance sheet changes
            template = random.choice(balance_sheet_change_templates)
            amount = round(random.uniform(5, 100), 1)
            ending = round(random.uniform(50, 200), 1)
            reason = random.choice(balance_sheet_reasons)

            sentence = template.format(
                amount=amount,
                ending=ending,
                year=current_year,
                prev_year=current_year - 1,
                currency_code=currency_code,
                reason=reason,
                money_unit=money_units,
                end_day=random.randint(28, 31),
                month=random.choice(months),
                company=pick_company_name(company_name),
            )
            sentences.append(sentence)

        random.shuffle(sentences)
        sentences = sentences[: random.randint(1, len(sentences))] if len(sentences) > 2 else sentences
        merged_text = ". ".join(sentences)
        all_sentences.append([merged_text])

    # CEO and executive compensation (0-2 sentences)
    num_exec_comp = random.randint(0, 2)
    for _ in range(num_exec_comp):
        sentences = []

        if random.random() < 0.5:
            template = random.choice(ceo_compensation_templates)
            total_amount = round(random.uniform(8, 25), 1)
            salary = round(random.uniform(1, 2), 1)
            bonus = round(random.uniform(2, 6), 1)
            equity = round(total_amount - salary - bonus, 1)
            prev_amount = round(total_amount * random.uniform(0.8, 1.2), 1)

            sentence = template.format(
                amount=total_amount,
                salary=salary,
                bonus=bonus,
                equity=equity,
                prev_amount=prev_amount,
                prev_year=current_year - 1,
                year=current_year,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                month=random.choice(months),
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(executive_compensation_templates)
            amount = round(random.uniform(30, 80), 1)
            equity = round(amount * random.uniform(0.4, 0.6), 1)
            change = round(random.uniform(5, 20), 1)
            increase_decrease = random.choice(["an increase", "a decrease"])

            sentence = template.format(
                amount=amount,
                equity=equity,
                year=current_year,
                increase_decrease=increase_decrease,
                change=change,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                month=random.choice(months),
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(equity_grant_templates)
            shares = random.choice([50000, 75000, 100000, 150000, 200000])
            amount = round(random.uniform(3, 12), 1)
            price = round(random.uniform(30, 150), 2)
            years = random.choice([3, 4, 5])
            month = random.choice(months)
            metric = random.choice(performance_metrics)
            vesting = random.choice(vesting_periods)

            sentence = template.format(
                month=month,
                year=current_year,
                shares=f"{shares:,}",
                amount=amount,
                price=price,
                years=years,
                metric=metric,
                vesting_period=vesting,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(severance_templates)
            multiple = random.choice([2, 2.5, 3])
            amount = round(random.uniform(5, 20), 1)

            sentence = template.format(
                multiple=multiple,
                amount=amount,
                year=current_year,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                month=random.choice(months),
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(employment_agreement_templates)
            salary = round(random.uniform(0.8, 2.0), 1)
            bonus_pct = random.choice([100, 125, 150, 200])
            month = random.choice(months)

            sentence = template.format(
                month=month,
                year=random.choice([current_year, current_year - 1, current_year - 2]),
                salary=salary,
                bonus_pct=bonus_pct,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(compensation_committee_templates)
            consultant = random.choice(acquisition_targets)
            sentence = template.format(consultant=consultant)
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(say_on_pay_templates)
            pct = round(random.uniform(75, 95), 1)
            month = random.choice(months)

            sentence = template.format(
                year=current_year,
                pct=pct,
                month=month,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(deferred_comp_templates)
            pct = random.choice([50, 75, 100])
            bonus_pct = random.choice([50, 100])
            amount = round(random.uniform(10, 50), 1)

            sentence = template.format(
                pct=pct,
                bonus_pct=bonus_pct,
                amount=amount,
                year=current_year,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                month=random.choice(months),
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(perquisites_templates)
            amount = random.choice([50, 75, 100, 150, 200])
            perq_type = random.choice(perq_types)

            sentence = template.format(
                amount=f"{amount:,}",
                year=current_year,
                perq_type=perq_type,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                month=random.choice(months),
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(clawback_templates)
            sentence = template.format(company=pick_company_name(company_name))
            sentences.append(sentence)
        if random.random() < 0.5:
            template = random.choice(stock_comp_templates)
            amount = round(random.uniform(10, 80), 1)
            shares = random.choice([50000, 100000, 250000, 500000])
            price = round(random.uniform(20, 100), 2)
            sentence = template.format(
                amount=amount,
                year=current_year,
                month=random.choice(months),
                shares=f"{shares:,}",
                price=price,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                end_day=random.randint(28, 31),
            )
            sentences.append(sentence)
        if random.random() < 0.5:
            template = random.choice(stock_comp_valuation_templates)
            amount = round(random.uniform(5, 25), 2)
            model = random.choice(valuation_models)
            sentence = template.format(
                year=current_year,
                month=random.choice(months),
                amount=amount,
                company=pick_company_name(company_name),
                currency_code=currency_code,
                major_currency=major_currency,
                money_unit=money_units,
                model=model,
            )
            sentences.append(sentence)
        random.shuffle(sentences)
        sentences = sentences[: random.randint(1, len(sentences))] if len(sentences) > 2 else sentences
        merged_text = ". ".join(sentences)
        all_sentences.append([merged_text])

    # Market prices and trading (0-1)
    category = random.choice(["stock_price", "trading_volume"])
    if category == "stock_price":
        template = random.choice(stock_price_templates)
        exchange = random.choice(exchanges)
        ticker = ''.join(random.choices(string.ascii_uppercase, k=random.randint(3, 4)))
        price = round(random.uniform(10, 200), 2)
        prev_price = round(price * random.uniform(0.7, 1.3), 2)
        low = round(price * random.uniform(0.6, 0.9), 2)
        high = round(price * random.uniform(1.1, 1.5), 2)
        volume = random.choice([500000, 1000000, 2000000, 5000000])
        market_cap = round(random.uniform(500, 5000), 0)
        shares = random.choice([50, 75, 100, 150, 200])
        direction = "increase" if price > prev_price else "decrease"
        pct = abs(round(((price - prev_price) / prev_price) * 100, 1))
        month = random.choice(months)
        end_day = random.randint(28, 31)

        sentence = template.format(
            exchange=exchange,
            ticker=ticker,
            currency_code=currency_code,
            price=price,
            prev_price=prev_price,
            low=low,
            high=high,
            volume=f"{volume:,}",
            market_cap=f"{market_cap:,}",
            money_unit=money_units,
            shares=f"{shares:,}",
            direction=direction,
            pct=pct,
            month=month,
            end_day=end_day,
            year=current_year,
            prev_year=current_year - 1,
            company=pick_company_name(company_name),
        )
    else:
        template = random.choice(trading_volume_templates)
        volume = random.choice([500000, 1000000, 2000000, 3000000])
        volatility = random.choice(volatility_levels)
        pct = round(random.uniform(5, 50), 1)
        improved_decreased = random.choice(["improved", "decreased"])

        sentence = template.format(
            year=current_year,
            prev_year=current_year - 1,
            volume=f"{volume:,}",
            volatility=volatility,
            pct=pct,
            improved_decreased=improved_decreased,
            company=pick_company_name(company_name),
        )
    all_sentences.append([sentence])

    # Company description (0-1)
    template = random.choice(company_description_templates)
    industry = random.choice(industries)
    business_activity = random.choice(business_activities)
    products_services = random.choice(
        ["products and services", "solutions", "technology platforms"]
    )
    geography = random.choice(geographies)
    founding_year = random.randint(1950, 2010)
    city = random.choice(cities)
    state = random.choice(states)
    market_segment = random.choice(
        ["enterprise", "consumer", "industrial", "healthcare"]
    )
    activities = random.choice(business_activities)
    employees = random.choice([5000, 10000, 25000, 50000, 100000])
    locations = random.randint(50, 500)
    segments = random.choice([2, 3, 4])
    segment_names = random.choice(segment_examples)
    mission = (
        "deliver innovative solutions that create value for customers and shareholders"
    )
    month = random.choice(months)
    end_day = random.randint(28, 31)

    sentence = template.format(
        industry=industry,
        business_activity=business_activity,
        company=pick_company_name(company_name),
        products_services=products_services,
        geography=geography,
        founding_year=founding_year,
        city=city,
        state=state,
        market_segment=market_segment,
        activities=activities,
        employees=f"{employees:,}",
        locations=locations,
        month=month,
        end_day=end_day,
        year=current_year,
        segments=segments,
        segment_names=segment_names,
        mission_statement=mission,
    )
    all_sentences.append([sentence])

    # Institutional/hedge fund ownership (0-1)
    category = random.choice(["institutional", "insider"])
    if category == "institutional":
        template = random.choice(institutional_ownership_templates)
        fund_name = random.choice(target_companies)
        fund_name2 = random.choice([f for f in target_companies if f != fund_name])
        pct = round(random.uniform(5, 15), 1)
        pct2 = round(random.uniform(3, 10), 1)
        prev_pct = round(pct * random.uniform(0.8, 1.2), 1)
        form = random.choice(sec_forms)
        month = random.choice(months)
        end_day = random.randint(28, 31)

        sentence = template.format(
            month=month,
            end_day=end_day,
            year=current_year,
            pct=pct,
            pct2=pct2,
            prev_pct=prev_pct,
            fund_name=fund_name,
            fund_name2=fund_name2,
            form=form,
            company=pick_company_name(company_name),
        )
    else:
        template = random.choice(insider_ownership_templates)
        pct = round(random.uniform(1, 8), 1)
        shares = random.choice([500000, 1000000, 2000000])
        action = random.choice(insider_actions)
        month = random.choice(months)
        end_day = random.randint(28, 31)

        sentence = template.format(
            pct=pct,
            shares=f"{shares:,}",
            action=action,
            month=month,
            end_day=end_day,
            year=current_year,
            company=pick_company_name(company_name),
        )

    all_sentences.append([sentence])

    # Forward-looking statements (0-1)
    category = random.choice(["forward_looking", "safe_harbor"])

    if category == "forward_looking":
        template = random.choice(forward_looking_templates)
        topics = random.choice(forward_looking_topics)
        words = random.choice(forward_looking_words)
        risk_factors = random.choice(risk_factors_examples)
        month = random.choice(months)
        end_day = random.randint(28, 31)

        sentence = template.format(
            topics=topics,
            words=words,
            company=pick_company_name(company_name),
            risk_factors=risk_factors,
            month=month,
            end_day=end_day,
            year=current_year,
        )
    else:
        sentence = random.choice(safe_harbor_templates)
    sentence = sentence.format(company=pick_company_name(company_name))
    all_sentences.append([sentence])

    # Analyst coverage (0-1)
    template = random.choice(analyst_coverage_templates)
    number = random.randint(8, 25)
    number2 = random.randint(3, 12)
    number3 = random.randint(0, 5)
    eps = round(random.uniform(1.50, 8.00), 2)
    revenue = round(random.uniform(500, 5000), 0)
    target = round(random.uniform(50, 200), 2)
    direction = random.choice(["upside", "downside"])
    pct = round(random.uniform(10, 40), 1)
    low = round(eps * 0.8, 2)
    high = round(eps * 1.2, 2)

    sentence = template.format(
        number=number,
        number2=number2,
        number3=number3,
        year=current_year,
        currency_code=currency_code,
        eps=eps,
        revenue=f"{revenue:,}",
        money_unit=money_units,
        target=target,
        direction=direction,
        pct=pct,
        low=low,
        high=high,
        company=pick_company_name(company_name),
    )

    all_sentences.append([sentence])

    # Credit ratings (0-1)
    template = random.choice(credit_rating_templates)
    agency = random.choice(credit_agencies)
    agency2 = random.choice([a for a in credit_agencies if a != agency])
    agency3 = random.choice([a for a in credit_agencies if a not in [agency, agency2]])
    rating = random.choice(credit_ratings)
    rating2 = random.choice(credit_ratings)
    rating3 = random.choice(credit_ratings)
    outlook = random.choice(rating_outlooks)
    action = random.choice(rating_actions)
    month = random.choice(months)
    end_day = random.randint(28, 31)

    sentence = template.format(
        rating=rating,
        rating2=rating2,
        rating3=rating3,
        agency=agency,
        agency2=agency2,
        agency3=agency3,
        outlook=outlook,
        action=action,
        month=month,
        end_day=end_day,
        year=current_year,
        company=pick_company_name(company_name),
    )

    all_sentences.append([sentence])

    # Dividend/capital allocation (0-1)
    for _ in range(1):
        sentences = []
        template = random.choice(dividend_policy_templates)
        amount = round(random.uniform(0.25, 2.00), 2)
        pct = round(random.uniform(20, 60), 1)
        pct2 = round(random.uniform(30, 70), 1)
        prev_pct = round(pct * random.uniform(0.9, 1.1), 1)
        yield_pct = round(random.uniform(1.5, 4.5), 1)
        month = random.choice(months)
        end_day = random.randint(1, 28)
        start_year = random.randint(1990, 2010)

        sentence = template.format(
            year=start_year,
            month=month,
            end_day=end_day,
            currency_code=currency_code,
            amount=amount,
            pct=pct,
            pct2=pct2,
            prev_pct=prev_pct,
            prev_year=current_year - 1,
            company=pick_company_name(company_name),
        )
        sentences.append(sentence)
        template = random.choice(share_repurchase_templates)
        shares = random.choice([1000000, 2000000, 5000000, 10000000])
        amount = round(random.uniform(50, 500), 0)
        prev_amount = round(amount * random.uniform(0.7, 1.3), 0)
        remaining = round(random.uniform(100, 400), 0)
        month = random.choice(months)
        end_day = random.randint(28, 31)

        sentence = template.format(
            year=current_year,
            shares=f"{shares:,}",
            currency_code=currency_code,
            amount=f"{amount:,}",
            prev_amount=f"{prev_amount:,}",
            remaining=f"{remaining:,}",
            money_unit=money_units,
            month=month,
            end_day=end_day,
            prev_year=current_year - 1,
            company=pick_company_name(company_name),
        )
        sentences.append(sentence)
        random.shuffle(sentences)
        sentences = sentences[: random.randint(1, len(sentences))] if len(sentences) > 2 else sentences
        merged_text = ". ".join(sentences)
        all_sentences.append([merged_text])

    # Competition (0-1)
    template = random.choice(competition_templates)
    characteristics = random.choice(competitive_characteristics)
    competitor1 = random.choice(target_companies)
    competitor2 = random.choice([c for c in target_companies if c != competitor1])
    competitor3 = random.choice(
        [c for c in target_companies if c not in [competitor1, competitor2]]
    )
    factors = random.choice(competitive_factors)
    pct = round(random.uniform(10, 35), 1)
    reasons = "new market entrants, pricing pressures, and technological disruption"
    advantages = random.choice(competitive_advantages)

    sentence = template.format(
        characteristics=characteristics,
        competitor1=competitor1,
        competitor2=competitor2,
        competitor3=competitor3,
        factors=factors,
        pct=pct,
        year=current_year,
        reasons=reasons,
        advantages=advantages,
        company=pick_company_name(company_name),
    )

    all_sentences.append([sentence])

    # Regulatory (0-1)
    template = random.choice(regulatory_templates)
    regulators_list = random.choice(regulators)
    areas = random.choice(regulatory_areas)
    amount = round(random.uniform(5, 50), 1)
    approvals = "product registrations and environmental permits"
    matters = "regulatory audits and compliance reviews"

    sentence = template.format(
        regulators=regulators_list,
        areas=areas,
        currency_code=currency_code,
        amount=amount,
        money_unit=money_units,
        year=current_year,
        approvals=approvals,
        matters=matters,
        company=pick_company_name(company_name),
    )

    all_sentences.append([sentence])

    # Insurance (0-1)
    template = random.choice(insurance_templates)
    amount = round(random.uniform(10, 100), 1)
    risks = random.choice(self_insured_risks)
    incident = random.choice(
        ["property damage", "business interruption", "product liability claims"]
    )
    coverage_types_list = random.choice(coverage_types)
    month = random.choice(months)
    end_day = random.randint(28, 31)

    sentence = template.format(
        currency_code=currency_code,
        amount=amount,
        money_unit=money_units,
        month=month,
        end_day=end_day,
        year=current_year,
        risks=risks,
        incident=incident,
        coverage_types=coverage_types_list,
        company=pick_company_name(company_name),
    )
    all_sentences.append([sentence])

    all_sentences.append(generate_other_policy_update())

    noise = generate_sec_noise(
        company=pick_company_name(company_name),
        currency_unit=money_units,
        month=random.choice(months),
        year=current_year,
    )
    all_sentences.append(noise)

    # Foreign currency risk/translation (0-2 sentences)
    num_fx = random.randint(1, 2)
    for _ in range(num_fx):
        sentences = []

        currency2 = random.choice([c for c in all_currencies if c != major_currency])
        currency3 = random.choice(
            [c for c in all_currencies if c not in [major_currency, currency2]]
        )
        month = random.choice(months)
        end_day = random.randint(28, 31)
        location = random.choice(balance_sheet_locations)
        if random.random() < 0.5:
            template = random.choice(foreign_currency_exposure_templates)
            sentence = template.format(
                company=pick_company_name(company_name),
                major_currency=major_currency,
                currency2=currency2,
                currency3=currency3,
                location=location,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(foreign_currency_translation_templates)
            amount = generate_value(False)
            sentence = template.format(
                company=pick_company_name(company_name),
                currency_code=currency_code,
                amount=amount,
                month=month,
                end_day=end_day,
                year=current_year,
                major_currency=major_currency,
                currency2=currency2,
                money_unit=money_units,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(foreign_currency_transaction_templates)
            amount = generate_value(False)
            prev_amount = generate_value(False, amount)
            sentence = template.format(
                company=pick_company_name(company_name),
                currency_code=currency_code,
                amount=amount,
                prev_amount=prev_amount,
                location=location,
                month=month,
                end_day=end_day,
                year=current_year,
                prev_year=current_year - 1,
                major_currency=major_currency,
                money_unit=money_units,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(functional_currency_templates)
            amount = generate_value(False)
            sentence = template.format(
                company=pick_company_name(company_name),
                major_currency=major_currency,
                currency2=currency2,
                currency3=currency3,
                currency_code=currency_code,
                amount=amount,
                year=current_year,
                money_unit=money_units,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(fx_impact_on_results_templates)
            amount = generate_value(False)
            pct = generate_value(False, 10)
            reported_pct = round(pct + random.uniform(-2, 2), 1)
            sentence = template.format(
                company=pick_company_name(company_name),
                currency_code=currency_code,
                amount=amount,
                money_unit=money_units,
                pct=pct,
                reported_pct=reported_pct,
                year=current_year,
                prev_year=current_year - 1,
                major_currency=major_currency,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(intercompany_fx_templates)
            amount = generate_value(False)
            sentence = template.format(
                company=pick_company_name(company_name),
                currency_code=currency_code,
                amount=amount,
                money_unit=money_units,
                major_currency=major_currency,
                month=month,
                end_day=end_day,
                year=current_year,
            )
            sentences.append(sentence)
        random.shuffle(sentences)
        sentences = sentences[: random.randint(1, len(sentences))] if len(sentences) > 2 else sentences
        merged_text = ". ".join(sentences)
        all_sentences.append([merged_text])

    # Commodity prices/risk/inventory (0-2 sentences)
    num_commodity = random.randint(1, 2)
    for _ in range(num_commodity):
        sentences = []

        commodity = random.choice(commodities)
        commodity2 = random.choice([c for c in commodities if c != commodity])
        commodity3 = random.choice(
            [c for c in commodities if c not in [commodity, commodity2]]
        )
        unit = random.choice(volume_units)
        month = random.choice(months)
        end_day = random.randint(28, 31)

        if random.random() < 0.5:
            template = random.choice(commodity_price_exposure_templates)
            low_price = generate_value(False, 100)
            high_price = round(low_price * random.uniform(1.3, 2.0), 2)
            sentence = template.format(
                company=pick_company_name(company_name),
                commodity=commodity,
                commodity2=commodity2,
                commodity3=commodity3,
                currency_code=currency_code,
                low_price=low_price,
                high_price=high_price,
                unit=unit,
                year=current_year,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(commodity_cost_impact_templates)
            amount = generate_value(False, 150)
            pct = generate_value(False, 40)
            prev_pct = generate_value(False, 40)
            sentence = template.format(
                company=pick_company_name(company_name),
                currency_code=currency_code,
                amount=amount,
                money_unit=money_units,
                pct=pct,
                prev_pct=prev_pct,
                commodity=commodity,
                commodity2=commodity2,
                year=current_year,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(commodity_inventory_valuation_templates)
            amount = generate_value(False, 100)
            volume = generate_value(False, 50000)
            method = random.choice(inventory_methods)
            sentence = template.format(
                company=pick_company_name(company_name),
                commodity=commodity,
                commodity2=commodity2,
                volume=f"{volume:,}",
                unit=unit,
                currency_code=currency_code,
                amount=amount,
                money_unit=money_units,
                month=month,
                end_day=end_day,
                year=current_year,
                method=method,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(commodity_pricing_strategies_templates)
            pct = generate_value(False, 50)
            num_months = generate_value(False, 12)
            sentence = template.format(
                company=pick_company_name(company_name),
                pct=pct,
                months=num_months,
                commodity=commodity,
                year=current_year,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(commodity_supply_risk_templates)
            pct = generate_value(False, 90)
            sentence = template.format(
                company=pick_company_name(company_name),
                commodity=commodity,
                pct=pct,
                year=current_year,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(commodity_exposure_quantification_templates)
            pct = generate_value(False, 10)
            pct2 = generate_value(False, 25)
            amount = generate_value(False, 100)
            change = generate_value(False, 20)
            sentence = template.format(
                company=pick_company_name(company_name),
                pct=pct,
                pct2=pct2,
                commodity=commodity,
                commodity2=commodity2,
                currency_code=currency_code,
                amount=amount,
                money_unit=money_units,
                change=change,
                unit=unit,
            )
            sentences.append(sentence)

        if random.random() < 0.5:
            template = random.choice(physical_commodity_operations_templates)
            volume = generate_value(False, 10000)
            amount = generate_value(False, 500)
            pct = generate_value(False, 25)
            cost = generate_value(False, 80)
            prev_cost = round(cost * random.uniform(0.7, 1.2), 2)
            sentence = template.format(
                company=pick_company_name(company_name),
                commodity=commodity,
                volume=f"{volume:,}",
                unit=unit,
                year=current_year,
                prev_year=current_year-1,
                currency_code=currency_code,
                amount=amount,
                money_unit=money_units,
                pct=pct,
                cost=cost,
                prev_cost=prev_cost,
                month=month,
                end_day=end_day,
            )
            sentences.append(sentence)
        random.shuffle(sentences)
        sentences = sentences[: random.randint(1, len(sentences))] if len(sentences) > 2 else sentences
        merged_text = ". ".join(sentences)
        all_sentences.append([merged_text])

    # Shuffle and select
    random.shuffle(all_sentences)
    selected_sentences = []
    for i in range(max_len):
        sentence = all_sentences[i]
        selected_sentences.extend(sentence)
        if random.random() < 0.25 or len(sentence) > 400:
            break
    selected_sentences = [s[0].upper() + s[1:] if s else "" for s in selected_sentences]

    # Clean up common formatting issues
    paragraph = cleanup(paragraph, reporting_year, False)

    return paragraph, 3


def generate_sec_noise(company, currency_unit, month, year):
    def generate_toc_line():
        template = random.choice(sec_toc_patterns)
        page_num = random.randint(1, 200)  # simulate TOC page numbers
        return (
            template.format(
                page=page_num,
                company=pick_company_name(company),
            )
            + " "
        )

    phrases = [
        "Commission file number " + str(random.randint(1, 99999)).zfill(5),
        f"ANNUAL REPORT PURSUANT TO SECTION {random.choice(['13','15(d)'])} OF THE SECURITIES EXCHANGE ACT OF 1934",
        f"Registrant's telephone number, including area code ({random.randint(100,999)}) {random.randint(100,999)}-{random.randint(1000,9999)}",
        f"For the fiscal year ended {month} {random.randint(28, 31)} {year}",
        f"For the transition period from {month} {random.randint(28, 31)} {year - 1} to {month} {random.randint(28, 31)} {year}",
        f"{company} (Exact Name , of Registrant as Specified in its Charter)",
        f"Indicate by check mark if the registrant is a well-known seasoned issuer. Yes {random.choice(['[x]','[]'])} No {random.choice(['[x]','[]'])}",
        f"Indicate by check mark whether the registrant (1) has filed all reports required to be filed by Section 13 or Section 15(d) of the Securities Exchange Act of 1934 during the preceding 12 months (or for such shorter period that the registrant was required to file such reports), and (2) has been subject to such filing requirements for the past 90 days. Yes {random.choice(['[x]','[]'])} No {random.choice(['[x]','[]'])}",
        f"Note — Checking the box above will not relieve any registrant required to file reports pursuant to Section 13 or 15(d) of the Exchange Act from their obligations under those Sections",
        f"Indicate by check mark whether the registrant has submitted electronically and posted on its corporate Website, if any, every Interactive Data File required to be submitted and posted to Rule 405 of Regulations S-T (§232.405 of this chapter) during the preceding 12 months (or for such shorter period that the registrant was required to submit and post such files). Yes {random.choice(['[x]','[]'])} No {random.choice(['[x]','[]'])}",
        f'Indicate by check mark whether the registrant is a large accelerated filer, an accelerated filer, a non-accelerated filer, or a smaller reporting company. See the definitions of "large accelerated filer," "accelerated filer" and "smaller reporting company" in Rule 12b-2 of the Exchange Act Yes {random.choice(['[x]','[]'])} No {random.choice(['[x]','[]'])}',
        f"The aggregate market value of the common shares held by non-affiliates was {currency_unit}{random.randint(10**6,10**9):,}",
        f"{random.randint(50_000_000,200_000_000):,} common shares outstanding as of {random.randint(1,12)}/{random.randint(1,28)}/{random.randint(2000,2024)}",
        f"Part III incorporates certain information by reference from the registrant's proxy statement for the {year} Annual Meeting of Shareholders expected to be held on {month} {random.randint(1,28)}, {year + 1} . Such proxy statement will be filed no later than 120 days after the close of the registrant's fiscal year ended {month} {random.randint(1,28)},  {year}.",
    ]

    gibberish = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=random.randint(6, 12))
    ) + random.choice([".htm", ".txt"])

    # Randomly choose 8–15 fragments
    chunks = random.sample(
        headers + phrases + [gibberish] + [generate_toc_line()], k=random.randint(8, 15)
    )
    return chunks


# def deboost_keywords_batch(batch_id, batch_size=2, max_words_per_sentence=8, min_words_per_sentence=4):
#     """
#     Generate a single batch of deboost sentences.
#     This function is called by each worker thread.

#     Args:
#         batch_id: Identifier for this batch (for reproducibility if needed)
#         batch_size: Number of sentences per swap type
#         max_words_per_sentence: Maximum words in a sentence
#         min_words_per_sentence: Minimum words in a sentence

#     Returns:
#         List of (sentence, label) tuples
#     """
#     # Set random seed based on batch_id for reproducibility (optional)
#     # random.seed(batch_id)

#     sentences = []

#     # [Insert all the template definitions from previous version here]
#     derivative_specific = [
#         "equity swap", "forward contract", "futures contract", "swaption",
#         "total return swap", "credit default swap", "variance swap",
#         "basis swap", "credit spread option", "interest rate cap", "interest rate floor"
#     ]

#     gen_standalone = [
#         "option", "collar", "call", "put", "over-the-counter",
#         "receive-equity", "pay-fixed", "receive-floating", "pay-equity",
#         "pay-floating", "receive-fixed", "equity collar", "total return",
#         "swap", "future", "forward", "call option", "put option", "OTC",
#         "swaption", "cap", "floor", "straddle", "strangle"
#     ]

#     accounting_buzzwords = [
#         "interest rate", "average interest rate", "floating rate", "fixed rate",
#         "foreign currency", "currency", "exchange rate", "currency translation",
#         "commodity price", "market price", "spot price", "fair value",
#         "OCI", "other comprehensive income", "cash flow", "mark to market",
#         "notional amount", "exposure", "sensitivity", "risk management",
#         "assets", "liabilities", "contract", "debt", "warrant", "embedded",
#         "hedge accounting", "hedge effectiveness", "hedge designation",
#         "accumulated other comprehensive income", "fair value hierarchy",
#         "Level 1", "Level 2", "Level 3", "carrying value", "book value",
#         "hedge fund", "fund", "outstanding", "terminate", "expire", "termination", "expiration",
#         "dedesignation", "dedesignate", "swap", "forward", "future", "cap", "floor", "agreement"
#     ]

#     connectors = [
#         "and", "or", "with", "including", "related to", "consisting of",
#         "totaling", "aggregating", "measured at", "recorded in", "recognized in",
#         "as of", "during", "throughout", "within", "under"
#     ]

#     accounting_phrases = [
#         "recorded in the balance sheet",
#         "recognized in earnings",
#         "deferred in other comprehensive income",
#         "measured at fair value",
#         "designated as hedging instruments",
#         "subject to periodic assessment",
#         "evaluated for effectiveness",
#         "classified as Level 2",
#         "included in the consolidated financial statements",
#         "disclosed in the footnotes"
#     ]

#     commodity_specific_terms = []
#     for commodity in commodities:
#         commodity_specific_terms.extend([
#             f"{commodity} price",
#             f"{commodity} inventory",
#             f"{commodity} risk",
#             f"{commodity} market",
#             commodity]
#         )

#     # --- Label 3: Irrelevant / Unrelated Context ---
#     num_label_3 = batch_size // 4  # Adjust ratio as needed
#     for _ in range(num_label_3):
#         sentence_parts = []

#         if random.random() < 0.8:
#             sentence_parts.extend(random.sample(
#                 accounting_buzzwords,
#                 min(random.randint(2, 4), len(accounting_buzzwords))
#             ))

#         if random.random() < 0.6:
#             sentence_parts.append(random.choice(connectors))

#         sentence_parts.extend(random.sample(
#             accounting_buzzwords,
#             min(random.randint(1, 3), len(accounting_buzzwords))
#         ))
#         if random.random() < 0.3:
#             sentence_parts.extend(random.sample(commodity_specific_terms, random.randint(1, 3)))

#         if random.random() < 0.3:
#             sentence_parts.append(random.choice(gen_standalone))
#             if random.random() < 0.5:
#                 sentence_parts.append(random.choice(connectors))
#                 sentence_parts.append(random.choice(gen_standalone))

#         if random.random() < 0.4:
#             sentence_parts.append(random.choice(accounting_phrases))

#         while len(sentence_parts) < min_words_per_sentence:
#             sentence_parts.append(random.choice(accounting_buzzwords))

#         sentence_parts = sentence_parts[:max_words_per_sentence + random.randint(0, 5)]

#         seen = set()
#         unique_parts = []
#         for part in sentence_parts:
#             if part not in seen:
#                 seen.add(part)
#                 unique_parts.append(part)

#         sentence = " ".join(unique_parts)
#         sentences.append((sentence, 3))

#     # --- Label 2: Gen/Unknown Hedge Der. Speculative/Policy ---
#     num_label_2 = batch_size // 4
#     for _ in range(num_label_2):
#         sentence_parts = []

#         sentence_parts.extend(random.sample(
#             gen_standalone,
#             min(random.randint(2, 4), len(gen_standalone))
#         ))

#         if random.random() < 0.6:
#             sentence_parts.append(random.choice(connectors))

#         if random.random() < 0.5:
#             sentence_parts.extend(random.sample(
#                 accounting_buzzwords,
#                 min(random.randint(1, 3), len(accounting_buzzwords))
#             ))

#         if random.random() < 0.2:
#             sentence_parts.append(random.choice(derivative_specific))

#         if random.random() < 0.5:
#             sentence_parts.append(random.choice(connectors))
#             sentence_parts.append(random.choice(accounting_phrases))


#         while len(sentence_parts) < min_words_per_sentence:
#             sentence_parts.append(random.choice(gen_standalone))

#         sentence_parts = sentence_parts[:max_words_per_sentence + random.randint(0, 5)]

#         seen = set()
#         unique_parts = []
#         for part in sentence_parts:
#             if part not in seen:
#                 seen.add(part)
#                 unique_parts.append(part)

#         sentence = " ".join(unique_parts)
#         sentences.append((sentence, 2))

#     # --- Labels 14/15/16: Type-specific ---
#     swap_types = {
#         "ir": 14,
#         "fx": 15,
#         "cp": 16
#     }
#     for prefix, label in swap_types.items():
#         for _ in range(batch_size):
#             sentence_parts = []

#             num_swaps = random.randint(2, 4)
#             for _ in range(num_swaps):
#                 swap_type = random.choice(derivative_keywords.get(prefix, []))
#                 sentence_parts.append(swap_type)

#             if random.random() < 0.7:
#                 sentence_parts.append(random.choice(connectors))

#             if random.random() < 0.4:
#                 sentence_parts.extend(random.sample(
#                     gen_standalone,
#                     min(random.randint(1, 2), len(gen_standalone))
#                 ))

#             if random.random() < 0.3:
#                 sentence_parts.extend(random.sample(
#                     accounting_buzzwords,
#                     min(random.randint(1, 3), len(accounting_buzzwords))
#                 ))

#             if random.random() < 0.2:
#                 other_prefix = random.choice([p for p in swap_types.keys() if p != prefix])
#                 cross_contamination = random.choice(derivative_keywords.get(other_prefix, []))
#                 sentence_parts.append(cross_contamination)

#             if random.random() < 0.5:
#                 sentence_parts.append(random.choice(accounting_phrases))

#             while len(sentence_parts) < min_words_per_sentence:
#                 swap_type = random.choice(derivative_keywords.get(prefix, []))
#                 sentence_parts.append(swap_type)

#             sentence_parts = sentence_parts[:max_words_per_sentence + random.randint(0, 6)]

#             seen = set()
#             unique_parts = []
#             for part in sentence_parts:
#                 if part not in seen:
#                     seen.add(part)
#                     unique_parts.append(part)

#             sentence = " ".join(unique_parts)
#             sentences.append((sentence, label))
#     random.shuffle(sentences)
#     return sentences[:batch_size]


# def generate_deboost_dataset_concurrent(
#     total_batches=100,
#     batch_size=20,
#     max_workers=8,
#     max_words_per_sentence=8,
#     min_words_per_sentence=4
# ):
#     """
#     Generate deboost dataset using concurrent processing with tqdm progress bar.

#     Args:
#         total_batches: Number of batches to generate
#         batch_size: Size of each batch
#         max_workers: Number of parallel workers
#         max_words_per_sentence: Max words per sentence
#         min_words_per_sentence: Min words per sentence

#     Returns:
#         List of (sentence, label) tuples
#     """
#     all_sentences = []

#     # Create progress bar
#     with tqdm(total=total_batches, desc="Generating deboost sentences", unit="batch") as pbar:
#         # Use ThreadPoolExecutor for I/O-bound or CPU-bound tasks
#         with ThreadPoolExecutor(max_workers=max_workers) as executor:
#             # Submit all tasks
#             futures = {
#                 executor.submit(
#                     deboost_keywords_batch,
#                     batch_id=i,
#                     batch_size=batch_size,
#                     max_words_per_sentence=max_words_per_sentence,
#                     min_words_per_sentence=min_words_per_sentence
#                 ): i for i in range(total_batches)
#             }

#             # Process completed tasks
#             for future in as_completed(futures):
#                 batch_id = futures[future]
#                 try:
#                     batch_sentences = future.result()
#                     all_sentences.extend(batch_sentences)
#                     pbar.update(1)
#                 except Exception as e:
#                     print(f"\nError in batch {batch_id}: {e}")
#                     pbar.update(1)

#     # Remove duplicates
#     all_sentences = list(set(all_sentences))
#     return all_sentences

def generate(size_per_label=100, max_workers=8):
    all_samples = []
    swap_types = ["ir", "fx", "cp", "gen"]
    numSwaps = len(swap_types)
    count = size_per_label // numSwaps
    swap_counts = count * 3

    def submit_tasks(executor):
        futures = []
        # Parallel hedge generation
        for prefix in swap_types:
            for _ in range(swap_counts):
                futures.append(
                    executor.submit(
                        generate_labeled_hedge_paragraph,
                        has_active_derivative=True,
                        swapType=prefix,
                    )
                )
            for _ in range(swap_counts):
                futures.append(
                    executor.submit(
                        generate_labeled_hedge_paragraph,
                        has_active_derivative=False,
                        swapType=prefix,
                    )
                )
            for _ in range(count):
                futures.append(
                    executor.submit(
                        generate_labeled_hedge_paragraph,
                        has_active_derivative=None,
                        swapType=prefix,
                    )
                )

        # Parallel liability paragraphs
        for label_type in [4, 5, 6, 7, 3]:
            for _ in range(count // 2):
                futures.append(
                    executor.submit(
                        generate_derivative_liability_paragraph, label_type=label_type
                    )
                )

        # Parallel accounting noise
        for _ in range(size_per_label * 2):
            futures.append(executor.submit(generate_accounting_noise_paragraph))

        return futures

    # --- Parallel execution with tqdm progress bar ---
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = submit_tasks(executor)
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Generating samples",
        ):
            # try:
            paragraph, label = future.result()
            all_samples.append((paragraph, label))
            # except Exception as e:
            #     print(f"Error during generation: {e}")
    # Deboosting
    # all_samples.extend(generate_deboost_dataset_concurrent(size_per_label))

    # --- Create and sort DataFrame ---
    df_new = pd.DataFrame(all_samples, columns=["sentence", "label"])
    df_new.sort_values(by=["label", "sentence"], ascending=[True, True], inplace=True)
    df_new.reset_index(drop=True, inplace=True)

    # --- Write or append to Excel ---
    try:
        book = load_workbook(output_file)
        with pd.ExcelWriter(
            output_file, engine="openpyxl", mode="a", if_sheet_exists="overlay"
        ) as writer:
            df_new.to_excel(writer, sheet_name="Generated_Data", index=False)
    except FileNotFoundError:
        df_new.to_excel(output_file, sheet_name="Generated_Data", index=False)

    print(f"\n{len(all_samples)} samples written/appended to {output_file} (sorted)")


generate(1000)
