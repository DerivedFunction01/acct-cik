# %%
import random
import pandas as pd
from openpyxl import load_workbook
import re
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import json
import multiprocessing as mp
import math

from template.hedges import *
from template.common import *
from template.other import *
from template.w_emb import *

output_file = "./training_data.xlsx"
company_name_file = "./names.xlsx"
parquet_file = "./training_data.parquet"

#%%
# Precompile regex patterns
pattern_we_s = re.compile(r"We's", flags=re.IGNORECASE)
pattern_we_is = re.compile(r"We is", flags=re.IGNORECASE)
pattern_nil = re.compile(r" (0|0.0) (thousand|million|billion)", flags=re.IGNORECASE)
pattern_notional = re.compile(f"notional", flags=re.IGNORECASE)
pattern_spaces = re.compile(r"\s+")
pattern_dots = re.compile(r"\. +")

company_name_df = pd.read_excel(company_name_file)
company_names = list(company_name_df["name"])

def pick_company_name(company_name: str) -> str:
    return random.choices([company_name, "The Company"], weights=[0.75, 0.25], k=1)[0]


def generate_value(haveZero=True, lowerlimit=1, upperlimit=1000):
    """Generate a random previous notional value with chance of being zero,
    and optional rounding for variability. Returns int if whole, else float."""
    if haveZero:
        chance = 0.1
    else:
        chance = 0

    upperlimit = int(upperlimit)
    value = (
        0.0
        if random.random() < chance
        else (1 if upperlimit <= 1 else random.randint(lowerlimit, upperlimit))
    )

    if random.random() < 0.5:
        divisor = random.choice([10, 100])
        decimals = random.randint(1, 2)
        value = round(value / divisor, decimals)

    # Cast to int if it's a whole number with 50% chance
    if isinstance(value, float) and value.is_integer() and random.random() < 0.5:
        value = int(value)

    return value


def cleanup(all_sentences: list[str], reporting_year: int, fullCheck: bool = True):
    """
    Join sentences into a paragraph and apply sanitizing regexes.
    Fixed: assign results of regex.sub back to paragraph so substitutions take effect.
    """
    paragraph = ""
    # Capitalize the first letter
    for i in range(len(all_sentences)):
        sentence = all_sentences[i]
        sentence = sentence[0].upper() + sentence[1:]
        all_sentences[i] = sentence
    try:
        paragraph = ". ".join(all_sentences)
    except:
        print(all_sentences)

    # Apply substitutions and assign back to paragraph
    paragraph = pattern_we_s.sub("Our", paragraph)
    paragraph = pattern_we_is.sub("We are", paragraph)

    if random.random() < 0.35:  # Chance to replace values with nil
        paragraph = pattern_nil.sub(
            random.choice([" nil", " 0", " 0.0", " 0.00"]),
            paragraph,
        )

    if random.random() < 0.5:
        paragraph = pattern_notional.sub("", paragraph)
        
    paragraph = pattern_dots.sub(". ", paragraph)  # Remove double periods
    paragraph = pattern_spaces.sub(" ", paragraph)  # Remove extra whitespace
    
    if (
        fullCheck and (
        paragraph.find("{") != -1
        or paragraph.find(".." ) != -1
        or paragraph.find("[") != -1
        ) or paragraph.find("__NOT_FOUND__") != -1
    ):
        # If it is a not found, print out the __NOT_FOUND__{key}
        if paragraph.find("__NOT_FOUND__") != -1:
            key = paragraph[paragraph.find("{") : paragraph.find("}") + 1]
            print(f"Placeholder not found for {key}")
        else:
            print("Error in format", paragraph)

    paragraph = f"<reportingYear>{reporting_year}</reportingYear> {paragraph}."
    return paragraph


def get_primary_label(labels: dict) -> int:
    """
    Convert a multi-hot label dictionary into a single primary categorical label.

    Selection follows a strict priority order:

    1. **Warrant / Embedded Derivative**  
       - Warrant (`warr`) takes precedence over embedded or hedges.  
       - Embedded derivative (`emb`) next.  
       - Time context (`curr` vs `hist`) is applied when present.

    2. **Actual use of a hedge (_use flags)**  
       - Hedge types are prioritized: IR > FX > CP > EQ > GEN.  
       - Time context (`curr`, `hist`, `spec`) determines which label is returned.  
       - Defaults to current (`curr`) if no time context is specified.

    3. **Speculative mention (spec)**  
       - For hedge types flagged but not actually used (`_use` not set).  
       - Returns the speculative label for the first matching hedge type.

    4. **Context-only mention**  
       - Hedge type flagged but neither `_use` nor `spec` is set.  
       - Returns a context-only label.

    5. **Irrelevant**  
       - Returns the irrelevant label (24) if no other conditions are met.

    Notes:
    - Only a single label is returned.
    - Generic derivatives (`gen`) are treated as lowest-priority hedge type.
    - Designed for fast, deterministic selection for single-label classification from multi-hot predictions.
    - ⚠️ This is **not the final analysis primary label**; it is a simplified generator version and may differ from the multi-label aggregation used in full analysis.
    """

    # --- Warrant ---
    if labels.get("warr"):
        return 21 if labels.get("hist") else 20

    # --- Embedded Derivative ---
    if labels.get("emb"):
        return 23 if labels.get("hist") else 22

    # --- Hedge type label map (current, historic, spec) ---
    hedge_map = {
        "ir": (3, 4, 5),
        "fx": (6, 7, 8),
        "cp": (9, 10, 11),
        "eq": (12, 13, 14),
        "gen": (0, 1, 2),
    }

    # --- Context-only label map (no _use, not spec) ---
    context_map = {
        "gen": 15,
        "ir": 16,
        "fx": 17,
        "cp": 18,
        "eq": 19,
    }

    # --- 1. Check for actual use (_use) ---
    for hedge_type in ["ir", "fx", "cp", "eq", "gen"]:  # prioritized order
        if labels.get(f"{hedge_type}_use"):
            curr_id, hist_id, spec_id = hedge_map[hedge_type]
            if labels.get("curr"):
                return curr_id
            if labels.get("hist"):
                return hist_id
            if labels.get("spec"):
                return spec_id
            # Default to current if _use flagged but no time context
            return curr_id

    # --- 2. Speculative mention (no actual use) ---
    for hedge_type in ["ir", "fx", "cp", "eq", "gen"]:
        if labels.get(hedge_type) and labels.get("spec"):
            return hedge_map[hedge_type][2]

    # --- 3. Context-only (non-use, non-speculative) ---
    for hedge_type in ["ir", "fx", "cp", "eq", "gen"]:
        if labels.get(hedge_type):
            return context_map[hedge_type]

    # --- 4. Irrelevant (only if nothing else matched) ---
    if labels.get("irr"):
        return 24

    # --- 5. Default fallback ---
    return 24

def new_label() -> dict[str, float]:
    return {
        # -----------------
        # Context / Mention flags
        # -----------------
        "ir": 0.0,  # Interest rate context mentioned
        "fx": 0.0,  # FX context mentioned
        "cp": 0.0,  # Commodity context mentioned
        "eq": 0.0,  # Equity context mentioned
        "gen": 0.0,  # Generic derivative context mention (not type-specific)
        # -----------------
        # Actual use flags
        # -----------------
        "ir_use": 0.0,  # Actively used interest rate derivative
        "fx_use": 0.0,  # Actively used FX derivative
        "cp_use": 0.0,  # Actively used commodity derivative
        "eq_use": 0.0,  # Actively used equity derivative
        "gen_use": 0.0,  # Turned into any mention of amounts or year
        # -----------------
        # Time / Status flags
        # -----------------
        "curr": 0.0,  # Current derivative user
        "hist": 0.0,  # Historic/past derivative user
        "spec": 0.0,  # Speculative mention (not confirmed use)
        # -----------------
        # Special derivative types
        # -----------------
        "warr": 0.0,  # Warrants
        "emb": 0.0,  # Embedded derivatives
        # -----------------
        # Other
        # -----------------
        "irr": 0.0,  # Irrelevant / not a hedge
    }

def label_paragraph(paragraph: str, labels: dict) -> dict:
    """
    Labels a paragraph by calculating a weighted score based on keyword mentions.
    This creates more realistic, non-binary labels for training data.
    """

    # Define weighted keywords. Stronger indicators get higher weights.
    category_keywords = {
        "ir": {"interest rate": 0.3, "debt": 0.3, "loan": 0.3},
        "fx": {"currency": 0.3, "foreign": 0.3, "international": 0.4, "border": 0.2, "exchange rate": 0.8},
        "cp": {"commodit": 0.7, **{commodity: 0.7 for commodity in commodities}},
        "eq": {"stock": 0.3, "equity": 0.3, "share price": 0.3},
        "gen": {"hedges": 0.3, "derivatives": 0.3},
        "spec": {"derivatives": 0.3, **{verb: 0.3 for verb in hedge_may_use_verbs}},
    }

    # Normalize paragraph for counting
    para_lower = paragraph.lower()

    # Calculate weighted score for each category
    for category, keywords in category_keywords.items():
        score = 0.0
        for keyword, weight in keywords.items():
            # Count occurrences and multiply by weight
            score += para_lower.count(keyword) * weight
        
        # Normalize the score to a 0-1 range using tanh.
        # This prevents scores from becoming too large while rewarding more mentions.
        # A score of 0 remains 0, and any positive score is mapped between 0 and 1.
        normalized_score = round(math.tanh(score), 3)
        
        # Update the label score, keeping the highest value if one already exists
        labels[category] = max(labels.get(category, 0.0), normalized_score)

    return labels

def generate_hedge_paragraph(
    has_active_derivative: bool,
    swapType=None,
    year_range=(1990, 2025),
    max_past_years: int = 3,
    include_policy=None,
    company_name=None,
):
    labels = new_label()
    # Decide whether to include policy statements
    if include_policy is None and random.random() < 0.35:
        include_policy = True

    # If has_active_derivative not given, default to speculative/policy
    if has_active_derivative is None:
        include_policy = True

    # Pick company name
    if company_name is None:
        company_name = (
            random.choice(company_names) if random.random() < 0.95 else "The Company"
        )

    # Determine swap type if not provided
    if swapType is None:
        swapType = random.choice(["ir", "fx", "cp", "eq", "gen"])
    swap_types = derivative_keywords[swapType]

    # Currency and year setup
    money_units = random.choice(money_unit_list)
    currency_code = random.choice(currency_codes)
    major_currency = random.choice(all_currencies)

    current_year = random.randint(year_range[0], year_range[1])
    reporting_year = current_year
    num_past_years = random.randint(1, max_past_years)
    past_years = sorted(
        random.sample(range(current_year - 30, current_year), num_past_years)
    )
    month = random.choice(months)
    end_day = random.randint(28, 31)
    quarter = random.choice(quarters)

    cost_type = random.choice(cost_types)
    hedge_type = random.choice(hedge_types)
    swap_type = random.choice(swap_types)

    # Swaps Setup
    swaps_list = []
    for _ in range(random.randint(1, 3)):
        swaps_list.append(random.choice([s for s in swap_types if s not in swaps_list]))

    swaps_list = list(set(swaps_list))  # Remove duplicates
    swaps = (
        ", ".join(swaps_list[:-1]) + " and " + swaps_list[-1]
        if len(swaps_list) > 1
        else swaps_list[0] if swaps_list else ""
    )

    # Commodity setup
    commodity = random.choice(commodities)
    selected_cps = ""
    if swapType == "cp":  # A various number of commodities
        cp_list = [commodity]
        for _ in range(random.randint(1, 2)):
            cp_list.append(random.choice(commodities))

        cp_list = list(set(cp_list))  # Remove duplicates
        selected_cps = (
            ", ".join(cp_list[:-1]) + " and " + cp_list[-1]
            if len(cp_list) > 1
            else cp_list[0] if cp_list else ""
        )
        selected_cps = selected_cps if random.random() < 0.85 else "commodity"
    all_sentences = []

    # =====================
    # Assign multi-labels. The training data is only specific, but we need to watch out during actual model classification
    # =====================
    # Initialize labels
    labels = new_label()

    
    # -----------------------
    # Actual use
    # -----------------------
    labels["gen"] = 1
    if has_active_derivative is not None:
        # Mark specific hedge type as used
        labels[f"{swapType}_use"] = 1

        # Mark generic hedge use
        labels["gen_use"] = 1

        # Mark current vs historic
        if has_active_derivative:
            labels["curr"] = 1
        else:
            labels["hist"] = 1

    # -----------------------
    # Speculative mention
    # -----------------------
    if include_policy:
        # Only set spec if not actively using (optional, depends on your logic)
        labels["spec"] = 1

    def generate_debt() -> list[str]:
        sentences = []
        # Build the debt type combination
        debt_type_list = [random.choice(debt_types_list) for _ in range(random.randint(1, 3))]
        selected_debt = ", ".join(debt_type_list)

        debt_templates_pool = debt_templates + sum(noise_templates.get("IR", []), [])
        
        for _ in range(random.randint(2, 4)):
            template = random.choice(debt_templates_pool)
            
            replacements = {
                "{amount}": str(generate_value(False)),
                "{amount2}": str(generate_value(False)),
                "{year}": str(current_year + random.randint(3, 10)),
                "{month}": month,
                "{current_year}": str(current_year),
                "{debt_types}": selected_debt,
                "{debt_type}": random.choice(debt_types_list),
                "{maturity_year}": str(current_year + random.randint(3, 10)),
                "{company}": pick_company_name(company_name),
                "{currency_code}": currency_code,
                "{major_currency}": major_currency,
                "{money_unit}": money_units,
                "{end_day}": str(end_day),
                "{pct}": str(generate_value(False, 1, 8)),
                "{pct2}": str(generate_value(False, 1, 20)),
                "{small_int}": str(random.randint(3, 10)),
                "{small_int2}": str(random.randint(3, 10)),
                "{short_int}": str(random.randint(10, 90)),
                "{short_int2}": str(random.randint(60, 270)),
                "{hedge_type}": hedge_type,
            }

            sentence = template
            for key, value in replacements.items():
                sentence = sentence.replace(key, str(value))
            sentences.append(sentence)
        return sentences

    def generate_commodity() -> list[str]:
        sentences = []
        cp_templates = sum(noise_templates.get("CP", []), [])
        if not cp_templates:
            return []
        for _ in range(random.randint(1, 3)):
            template = random.choice(cp_templates)
            
            replacements = {
                "{amount}": str(generate_value(False)),
                "{amount2}": str(generate_value(False)),
                "{year}": str(current_year),
                "{prev_year}": str(current_year - 1),
                "{month}": month,
                "{company}": pick_company_name(company_name),
                "{currency_code}": currency_code,
                "{money_unit}": money_units,
                "{end_day}": str(end_day),
                "{commodities}": selected_cps,
                "{commodity}": random.choice(commodities),
                "{inventory_method}": random.choice(inventory_methods),
                "{unit}": random.choice(volume_units),
                "{pct}": str(generate_value(False, 1, 8)),
                "{pct2}": str(generate_value(False, 1, 20)),
                "{small_int}": str(random.randint(3, 9)),
                "{integer}": str(random.randint(1000, 10000)),
                "{short_int2}": str(random.randint(60, 270)),
            }

            sentence = template
            for key, value in replacements.items():
                sentence = sentence.replace(key, str(value))
            sentences.append(sentence)
        return sentences

    def generate_fx() -> list[str]:
        sentences = []
        fx_templates = sum(noise_templates.get("FX", []), [])
        if not fx_templates:
            return []
        for _ in range(random.randint(1, 3)):
            template = random.choice(fx_templates)
            
            _currencies = random.sample(all_currencies, min(3, len(all_currencies)))
            currency_list = ", ".join(_currencies)

            replacements = {
                "{amount}": str(generate_value(False)),
                "{amount2}": str(generate_value(False)),
                "{year}": str(current_year),
                "{prev_year}": str(current_year - 1),
                "{month}": month,
                "{company}": pick_company_name(company_name),
                "{currency_code}": currency_code,
                "{major_currency}": _currencies[0] if _currencies else "",
                "{currency2}": _currencies[1] if len(_currencies) > 1 else "",
                "{currency3}": _currencies[2] if len(_currencies) > 2 else "",
                "{money_unit}": money_units,
                "{end_day}": str(end_day),
                "{location}": random.choice(balance_sheet_locations),
                "{pct}": str(generate_value(False, 1, 8)),
                "{pct2}": str(generate_value(False, 1, 20)),
            }

            sentence = template
            for key, value in replacements.items():
                sentence = sentence.replace(key, str(value))
            sentences.append(sentence)
        return sentences

    def generate_derivative_sentences() -> list[str]:
        labels[swapType] = 1  # Context for the specific hedge type
        """Generate derivative-related sentences for FX, IR, CP, or generic types."""
        sentences = []

        # --- Common fields ---
        verb = random.choice(hedge_use_verbs)

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

        # Add a chance of context sentences
        if swapType == "ir" and random.random() < 0.15:
            sentences.extend(generate_debt())
        elif swapType == "cp" and random.random() < 0.15:
            sentences.extend(generate_commodity())
        elif swapType == "fx" and random.random() < 0.15:
            sentences.extend(generate_fx())

        # --- Time logic & Template Selection ---
        if has_active_derivative:
            year = current_year
            template = random.choice(hedge_position_templates[swapType])
            notional = generate_value(False)
            prev_notional = generate_value()
            prev2_notional = generate_value()
        else:
            if random.random() < 0.75:
                template = random.choice(hedge_position_templates[swapType])
                prev_notional = generate_value()
                prev2_notional = generate_value()
                if random.random() < 0.5: # no notional amount if we pick a current year and not active
                    year = current_year 
                    notional = 0 
                else: # If we pick a past year, we can have a notional amount
                    year = random.choice(past_years)
                    notional = generate_value(haveZero=False, lowerlimit=1)
            else:
                template = random.choice(zero_current_vs_prior_notional_templates)
                notional = 0
                prev_notional = generate_value(haveZero=False, lowerlimit=1)
                prev2_notional = generate_value(haveZero=False, lowerlimit=1)
                year = current_year

        prev_year, prev2_year = year - 1, year - 2
        old_year = year - random.randint(1, 20) if past_years else prev_year
        end_of_year = random.choice([f"{month} {end_day}, {year}", f"{year}", f"{end_day} {month}, {year}"])

        future_year = (
            random.randint(current_year + 1, current_year + 20)
            if has_active_derivative
            else random.randint(old_year - 1, prev_year)
        )
        
        old_notional = generate_value(False)
        gain_loss = random.choice(["gain", "loss"])

        # --- Build main sentence ---
        sentence = template.format(
            company=pick_company_name(company_name),
            verb=verb,
            swap_type=swap_type,
            swap_types=swaps,
            commodity=commodity,
            month=month,
            end_day=end_day,
            end_of_year=end_of_year,
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
            gain_loss=gain_loss,
            location=random.choice(balance_sheet_locations),
        )
        sentences.append(sentence)

        # --- Expired hedges for non-active derivatives ---
        if not has_active_derivative and random.random() < 0.05:
            sentences.append(expire_hedge())
        # --- Chance of payment
        if random.random() < 0.15:
            sentences.append(hedge_payment())

        random.shuffle(sentences)
        return sentences

    def expire_hedge(use_current_year=False) -> str:
        labels["hist"] = 1
        # pick a random template from termination
        template = random.choice(hedge_termination_templates)
        term_year = random.choice(past_years) if not use_current_year else current_year 
        verb = random.choice(hedge_use_verbs)
        sentence = template.format(
            company=pick_company_name(company_name),
            swap_type=swap_type,
            month=random.choice(months),
            quarter=quarter,
            year=term_year,
            end_day=random.randint(28, 31),
            verb=verb,
        )
        return sentence

    def hedge_payment() -> str:
        # pick a random template from payment
        template = random.choice(hedge_payment_templates)
        notional = generate_value(False)
        sentence = template.format(
            company=pick_company_name(company_name),
            swap_type=swap_type,
            notional=notional,
            currency_code=currency_code,
            money_unit=money_units,
            month=month,
        )
        return sentence

    def hedge_policy() -> list[str]:
        labels["spec"] = 1 #  A speculation
        labels[swapType] = 0 # Not related to any swap
        sentences = []
        # Accounting policy (always)
        act_template = random.choice(hedge_policy_templates)
        swap_type = (
            random.choice(derivative_keywords["gen"]) if random.random() < 0.5 else "derivatives"
        )
        sentences.append(
            act_template.format(
                company=pick_company_name(company_name),
                swap_type=swap_type,
                hedge_type=hedge_type,
            )
        )
        # No trading policy (always)
        nt_template = random.choice(hedge_no_trading_templates)
        sentences.append(
            nt_template.format(
                company=pick_company_name(company_name),
                verb=random.choice(hedge_may_use_verbs),
            )
        )

        # Chance of documentation:
        if random.random() < 0.5:
            doc_template = random.choice(hedge_documentation_templates)
            sentences.append(
                doc_template.format(company=pick_company_name(company_name), hedge_type=hedge_type)
            )
        # Chance of hedge effectiveness or hedge ineffectiveness (frequency, verb, swap_type, method, metric, standard)
        if random.random() < 0.5:
            eff_template = random.choice(hedge_effectiveness_templates)
            verb = random.choice(assessment_verbs)
            method = random.choice(hedge_methods)
            metric = random.choice(hedge_metrics)
            standard = random.choice(hedge_standards)
            frequency = random.choice(frequencies)
            sentences.append(
                eff_template.format(
                    company=pick_company_name(company_name),
                    verb=verb,
                    swap_type=swap_type,
                    method=method,
                    metric=metric,
                    standard=standard,
                    frequency=frequency,
                    hedge_type=hedge_type,
                )
            )
        else:  # company, freqency
            ineff_template = random.choice(hedge_ineffectiveness_templates)
            frequency = random.choice(frequencies)
            sentences.append(
                ineff_template.format(
                    company=pick_company_name(company_name),
                    frequency=frequency,
                )
            )
        # Discontinuation
        if random.random() < 0.5:
            discont_template = random.choice(hedge_discontinuation_templates)
            sentences.append(
                discont_template.format(
                    company=pick_company_name(company_name),
                    swap_type=swap_type,
                    hedge_type=hedge_type,
                    metric=random.choice(hedge_metrics),
                )
            )
        # Risk
        if random.random() < 0.5:
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
            sentences.append(template)
        # Counterparty
        if random.random() < 0.5:
            counterparty_template = random.choice(hedge_counterparty_templates)
            sentences.append(
                counterparty_template.format(
                    company=pick_company_name(company_name), 
                )
            )
        random.shuffle(sentences)
        return sentences

    def hedge_type_policy() -> list[str]:
        labels[swapType] = 1
        labels[f"{swapType}_use"] =max(0.7, labels[f"{swapType}_use"]) # We may use it, but it is neither current nor historic
        labels["gen_use"] =max(0.7, labels["gen_use"]) # Generic use as well
        labels["spec"] = 1
        labels["curr"] = max(0.7, labels["curr"]) if has_active_derivative else 0
        labels["hist"] = 0 if has_active_derivative else max(0.7, labels["hist"])
        sentences = []
        # begin context template (company, verb)
        beg_ctx_template = random.choice(hedge_begin_context_templates[swapType])
        verb = (
            random.choice(hedge_use_verbs)
            if has_active_derivative
            else random.choice(hedge_may_use_verbs)
        )
        sentences.append(
            beg_ctx_template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_type=swaps,
                commodity=selected_cps,
            )
        )
        # mitigation template
        ctx_template = random.choice(hedge_mitigation_templates[swapType])
        sentences.append(
            ctx_template.format(
                company=pick_company_name(company_name),
                verb=verb,
                swap_type=swaps,
                commodity=selected_cps,
            )
        )
        # If we don't have an active derivative, add a no such outstanding sentence
        if not has_active_derivative and random.random() < 0.25:
           sentences.append(expire_hedge(use_current_year=True))
        random.shuffle(sentences)
        return sentences

    def generate_hedge_policy_update():
        sentences = []
        labels["spec"] = 1
        labels[swapType] = 0 # Not related to any swap
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

    # Main Execution
    if has_active_derivative is None:
        if swapType is not None:
            # Specific hedge type policy
            all_sentences.extend(hedge_type_policy())
        else:
            # Generic policy if no hedge type is given
            if random.random() < 0.65:
                all_sentences.extend(hedge_policy())
            else:
                all_sentences.extend(generate_hedge_policy_update())
    else:
        if random.random() < 0.75:
            all_sentences.extend(generate_derivative_sentences())
            # Chance to include policy
            if include_policy:
                all_sentences.extend(hedge_type_policy())
        else: # Plain policy that states use currently or historically
            all_sentences.extend(hedge_type_policy())
  
    paragraph = cleanup(all_sentences, current_year)
    labels = label_paragraph(paragraph, labels)
    label = get_primary_label(labels)
    return paragraph, labels, label

def generate_warrant_paragraph(
    use_case,  # 'current', 'historical', or 'speculative'
    year_range=(1990, 2025),
    max_past_years: int = 3,
    company_name=None,
):
    labels = new_label()
    labels['warr'] = 1
    labels['gen'] = 1

    if use_case == 'current':
        labels['curr'] = 1
    elif use_case == 'historical':
        labels['hist'] = 1
    elif use_case == 'speculative':
        labels['spec'] = 1

    # Setup common variables
    if company_name is None:
        company_name = random.choice(company_names) if random.random() < 0.95 else "The Company"

    money_units = random.choice(money_unit_list)
    currency_code = random.choice(currency_codes)

    current_year = random.randint(year_range[0], year_range[1])
    reporting_year = current_year
    num_past_years = random.randint(1, max_past_years)
    past_years = sorted(random.sample(range(current_year - 5, current_year), num_past_years))
    month = random.choice(months)
    end_day = random.randint(28, 31)

    # Warrant specific variables
    shares = generate_value(False, 50000, 5000000)
    price = generate_value(False, 1, 25)
    expiry_year = current_year + random.randint(1, 10)
    amount = generate_value(False)
    settlement_year = random.choice(past_years) if past_years else current_year - 1

    # Select template pool
    if use_case == 'current':
        template_pool = sum(warrant_templates_for_ml['current_use'], [])
    elif use_case == 'historical':
        template_pool = sum(warrant_templates_for_ml['historical_use'], [])
    else: # speculative
        template_pool = sum(warrant_templates_for_ml['speculative'], [])

    if not template_pool:
        return None, None, None

    template = random.choice(template_pool)

    # Format sentence
    replacements = {
        "{company}": pick_company_name(company_name),
        "{shares}": str(shares),
        "{currency_code}": currency_code,
        "{price}": str(price),
        "{expiry_year}": str(expiry_year),
        "{month}": month,
        "{end_day}": str(end_day),
        "{year}": str(current_year),
        "{amount}": str(amount),
        "{money_unit}": money_units,
        "{settlement_year}": str(settlement_year),
        "{current_year}": str(current_year),
        "{quarter}": random.choice(quarters),
    }

    sentence = template
    for key, value in replacements.items():
        sentence = sentence.replace(key, value)

    all_sentences = [sentence]

    paragraph = cleanup(all_sentences, reporting_year)
    labels = label_paragraph(paragraph, labels)
    label = get_primary_label(labels)
    return paragraph, labels, label

def generate_emb_paragraph(
    use_case,  # 'current', 'historical', or 'speculative'
    year_range=(1990, 2025),
    max_past_years: int = 3,
    company_name=None,
):
    labels = new_label()
    labels['emb'] = 1
    labels['gen'] = 1

    if use_case == 'current':
        labels['curr'] = 1
    elif use_case == 'historical':
        labels['hist'] = 1
    elif use_case == 'speculative':
        labels['spec'] = 1

    # Setup common variables
    if company_name is None:
        company_name = random.choice(company_names) if random.random() < 0.95 else "The Company"

    money_units = random.choice(money_unit_list)
    currency_code = random.choice(currency_codes)

    current_year = random.randint(year_range[0], year_range[1])
    reporting_year = current_year
    prev_year = current_year - 1
    num_past_years = random.randint(1, max_past_years)
    past_years = sorted(random.sample(range(current_year - 5, current_year), num_past_years))
    month = random.choice(months)
    end_day = random.randint(28, 31)

    # Embedded deriv specific variables
    amount = generate_value(False)
    prev_amount = generate_value(False)
    principal = generate_value(False, 100000, 5000000)
    embedded_fv = generate_value(False, int(principal/20), int(principal/10)) if principal > 0 else 0

    # Select template pool
    if use_case == 'current':
        template_pool = sum(embedded_templates_for_ml['current_use'], [])
    elif use_case == 'historical':
        template_pool = sum(embedded_templates_for_ml['historical_use'], [])
    else: # speculative
        template_pool = sum(embedded_templates_for_ml['speculative'], [])

    if not template_pool:
        return None, None, None

    template = random.choice(template_pool)

    # Format sentence
    replacements = {
        "{company}": pick_company_name(company_name),
        "{currency_code}": currency_code,
        "{month}": month,
        "{end_day}": str(end_day),
        "{year}": str(current_year),
        "{prev_year}": str(prev_year),
        "{amount}": str(amount),
        "{prev_amount}": str(prev_amount),
        "{money_unit}": money_units,
        "{current_year}": str(current_year),
        "{settlement_year}": str(random.choice(past_years) if past_years else current_year - 1),
        "{currency_pair}": f"{random.choice(currency_codes)}/{random.choice(currency_codes)}",
        "{principal}": str(principal),
        "{embedded_fv}": str(embedded_fv),
        "{target}": random.choice(company_names),
        "{price}": str(generate_value(False, 1, 100)),
        "{shares}": str(generate_value(False, 100000, 500000)),
        "{expiry_year}": str(current_year + random.randint(1, 10)),
        "{quarter}": random.choice(quarters)
    }

    sentence = template
    for key, value in replacements.items():
        sentence = sentence.replace(key, value)

    all_sentences = [sentence]

    
    paragraph = cleanup(all_sentences, reporting_year)
    labels = label_paragraph(paragraph, labels)
    label = get_primary_label(labels)
    return paragraph, labels, label


def generate_sec_noise():
    # Generate random data for placeholders
    company = random.choice(company_names)
    month = random.choice(months)
    year = random.randint(1990, 2025)
    currency_unit = random.choice(money_unit_list)
    reporting_year = year

    # Inner function to generate a line for the Table of Contents
    def generate_toc_line():
        template = random.choice(sec_toc_patterns)
        page_num = random.randint(1, 200)
        return template.format(page=page_num, company=pick_company_name(company))

    # Populate placeholders for the phrase templates
    placeholders = {
        "file_number": str(random.randint(1, 99999)).zfill(5),
        "section": random.choice(["13", "15(d)"]),
        "area_code": random.randint(100, 999),
        "phone_number": f"{random.randint(100, 999)}-{random.randint(1000, 9999)}",
        "month": month,
        "day": random.randint(28, 31),
        "day2": random.randint(28, 31),
        "year": year,
        "prev_year": year - 1,
        "next_year": year + 1,
        "company": company,
        "choice1": random.choice(["[x]", "[]"]),
        "choice2": random.choice(["[x]", "[]"]),
        "currency_unit": currency_unit,
        "market_value": f"{random.randint(10**6, 10**9):,}",
        "shares_outstanding": f"{random.randint(50_000_000, 200_000_000):,}",
        "date": f"{random.randint(1, 12)}/{random.randint(1, 28)}/{random.randint(2000, 2024)}",
        "page": random.randint(1, 200),
    }

    # Format phrases from templates
    phrases = [p.format(**placeholders) for p in sec_phrases]

    # Generate gibberish filename
    gibberish = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=random.randint(6, 12))
    ) + random.choice([".htm", ".txt"])

    # Combine all parts and randomly sample
    chunks = random.sample(
        headers + phrases + [gibberish] + [generate_toc_line()], k=random.randint(8, 15)
    )

    # Create paragraph and labels for compatibility
    labels = new_label()
    labels["irr"] = 1
    label = get_primary_label(labels)

    # Cleanup and return
    return cleanup(chunks, reporting_year, fullCheck=False), labels, label


def generate_noise_paragraph(
    noise_type,
    year_range=(1990, 2025),
    max_past_years: int = 3,
    company_name=None,
):
    labels = new_label()
    labels['irr'] = 1

    # Setup common variables
    if company_name is None:
        company_name = random.choice(company_names) if random.random() < 0.95 else "The Company"

    # Ensure distinct company names
    company_names_unique = random.sample(company_names, min(3, len(company_names)))
    company1 = company_name
    company2 = company_names_unique[0] if len(company_names_unique) > 0 else "Another Company"
    company3 = company_names_unique[1] if len(company_names_unique) > 1 else "Third Company"

    money_units = random.choice(money_unit_list)
    currency_code = random.choice(currency_codes)
    currencies = random.sample(all_currencies, min(3, len(all_currencies)))
    major_currency = currencies[0] if len(currencies) > 0 else random.choice(all_currencies)
    currency2 = currencies[1] if len(currencies) > 1 else random.choice(all_currencies)
    currency3 = currencies[2] if len(currencies) > 2 else random.choice(all_currencies)

    current_year = random.randint(year_range[0], year_range[1])
    reporting_year = current_year
    num_past_years = random.randint(1, max_past_years)
    past_years = sorted(random.sample(range(current_year - 5, current_year), num_past_years))
    month = random.choice(months)
    end_day = random.randint(28, 31)
    quarter = random.choice(quarters)
    prev_year = current_year - 1
    next_year = current_year + 1

    # Specific variables for noise templates
    amount = generate_value(False, 10, 150)
    amount2 = generate_value(False, 50, 250)
    amount3 = generate_value(False, 200, 700)
    shares = generate_value(False, 100000, 5000000)
    shares2 = generate_value(False, 100000, 5000000)
    event = random.choice(warrant_events)
    net_shares = generate_value(False, int(shares/4), int(shares/2)) if shares > 0 else 0
    pct = generate_value(False, 5, 80)
    pct2 = generate_value(False, 5, 80)
    debt_type = random.choice(debt_types_list)
    maturity_year = current_year + random.randint(3, 10)
    small_int = random.randint(3, 9)
    small_int2 = random.randint(3, 9)
    short_int = random.randint(10, 90)
    short_int2 = random.randint(60, 270)

    # Ensure distinct credit agencies and ratings
    agencies = random.sample(credit_agencies, min(3, len(credit_agencies)))
    ratings = random.sample(credit_ratings, min(3, len(credit_ratings)))
    agency1 = agencies[0] if len(agencies) > 0 else random.choice(credit_agencies)
    agency2 = agencies[1] if len(agencies) > 1 else random.choice(credit_agencies)
    agency3 = agencies[2] if len(agencies) > 2 else random.choice(credit_agencies)
    rating1 = ratings[0] if len(ratings) > 0 else random.choice(credit_ratings)
    rating2 = ratings[1] if len(ratings) > 1 else random.choice(credit_ratings)
    rating3 = ratings[2] if len(ratings) > 2 else random.choice(credit_ratings)
    
    # Debt combo 
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
    
    def generate_other_policy_update():
        sentences = []
        labels["spec"] = 1 # It is a speculative, but not related to derivatives
        # ==============================
        # 1. ISSUANCE STATEMENT
        # ==============================
        template = random.choice(general_policy_templates)
        issuer = random.choice(shared_issuers)
        standard = random.choice(other_standards)
        topic = random.choice(other_topics)
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
            standard_purpose=purpose,
            policy_description=description,
            policy_feature=extra,
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
                adoption_method=random.choice(shared_adoption_methods),
                transition_feature=random.choice(shared_transition_features),
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
        adopt_standard = random.choice(other_standards)
        adopt_method = random.choice(shared_adoption_methods)
        adopt_month = random.choice(months)
        adopt_day = random.randint(1, 28)
        adopt_year = random.randint(current_year - 8, current_year + 4)

        adoption_sentence = adopt_template.format(
            company=pick_company_name(company_name),
            standard=adopt_standard,
            adoption_method=adopt_method,
            month=adopt_month,
            day=adopt_day,
            year=adopt_year,
        )
        sentences.append(adoption_sentence)

        # Optional: Adoption impact
        if random.random() < 0.3:
            impact_line = random.choice(shared_adoption_impact_templates).format(
                company=pick_company_name(company_name),
                adoption_impact=random.choice(
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
                standard=random.choice(other_standards),
                topic=random.choice(other_topics),
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
            risk_item=item,
            company=pick_company_name(company_name),
            materiality=materiality_choice,
        )
        sentences.append(sentence)
        return sentences

    template_pool = []
    all_sentences = []
    if noise_type == "eq" or noise_type == "warr":  # ex. equity, warrant, stock
        labels["eq"] = 0.3
        template_pool.extend(sum(noise_templates["EQ"], []))
    elif noise_type == "cp":  # ex. inventory
        labels["cp"] = 0.3
        template_pool.extend(sum(noise_templates["CP"], []))
    elif noise_type == "ir":  # ex. debt
        labels["ir"] = 0.3
        template_pool.extend(sum(noise_templates["IR"], []))
    elif noise_type == "fx":  # ex. currency
        labels["fx"] = 0.3
        template_pool.extend(sum(noise_templates["FX"], []))
    elif noise_type == "law":  # ex. derivative lawsuits (irr)
        template_pool.extend(sum(noise_templates["LAW"], []))
    elif noise_type == "spec":  # ex. acct standards (irr)
        all_sentences = generate_other_policy_update()
    else:
        # Everything else can be mixed together
        template_pool.extend(other_templates)
    if not template_pool and not all_sentences:
        return None, None, None

    # Commodity setup
    commodity = random.choice(commodities)
    cp_list = [commodity if commodity != "commodity" else random.choice(commodities)]
    for _ in range(2):
        cp_list.append(random.choice(commodities))
        if random.random() < 0.5:
            break
    selected_cps = (
        ", ".join(cp_list[:-1]) + " and " + cp_list[-1]
        if len(cp_list) > 1
        else cp_list[0]
    )
    selected_cps = selected_cps if random.random() < 0.85 else "commodity"

    # Reordered replacements with value1 and value2 removed
    replacements = {
        # Company-related
        "{company}": pick_company_name(company1),
        "{company2}": pick_company_name(company2),
        "{company3}": pick_company_name(company3),

        # Numeric and financial values
        "{integer}": str(random.randint(10000, 100000)),
        "{small_int}": str(small_int),
        "{small_int2}": str(small_int2),
        "{short_int}": str(short_int),
        "{short_int2}": str(short_int2),
        "{amount}": str(amount),
        "{amount2}": str(amount2),
        "{amount3}": str(amount3),
        "{shares}": str(shares),
        "{shares2}": str(shares2),
        "{net_shares}": str(net_shares),
        "{pct}": str(pct),
        "{pct2}": str(pct2),
        
        # Currency-related
        "{currency_code}": currency_code,
        "{money_unit}": money_units,
        "{major_currency}": major_currency,
        "{currency2}": currency2,
        "{currency3}": currency3,

        # Time-related
        "{year}": str(current_year),
        "{prev_year}": str(prev_year),
        "{next_year}": str(next_year),
        "{past_year}": str(random.choice(past_years)),
        "{maturity_year}": str(maturity_year),
        "{month}": month,
        "{end_day}": str(end_day),
        "{quarter}": quarter,

        # Financial instruments and events
        "{debt_type}": debt_type,
        "{debt_types}": selected_debt,
        "{stock_event}": event,
        "{financing_type}": random.choice(financing_types),
        "{asset_type}": random.choice(asset_types),
        "{service_type}": random.choice(service_types),
        "{inventory_method}": random.choice(inventory_methods),
        "{commodities}": selected_cps,
        "{vesting_period}": random.choice(vesting_periods),
        "{perq_type}": random.choice(perq_types),

        # Balance sheet and financial reasons
        "{bs_reason}": random.choice(balance_sheet_reasons),
        "{accrued_reason}": random.choice(accrued_reasons),
        "{asset_reason}": random.choice(other_asset_reasons),
        "{liability_reason}": random.choice(liability_reasons),
        "{equity_reason}": random.choice(equity_reasons),
        "{cfs_reason}": random.choice(cfs_reasons),
        "{capex_purpose}": random.choice(capex_purposes),
        "{restructuring_purpose}": random.choice(restructuring_purposes),
        "{restructuring_expense_type}": random.choice(restructuring_expense_types),
        "{acquisition_purpose}": random.choice(acquisition_purposes),
        "{acquisition_funding}": random.choice(acquisition_funding),
        "{guarantee_type}": random.choice(guarantee_types),
        "{intangible_type_examples}": random.choice(intangible_types),
        "{tax_sources_examples}": random.choice(tax_sources),

        # Legal and regulatory
        "{litigation_examples}": random.choice(case_types),
        "{lawsuit_allegation}": random.choice(allegations),
        "{court_name}": random.choice(courts),
        "{regulatory_agencies}": random.choice(regulators),
        "{regulatory_areas}": random.choice(regulatory_areas),
        "{regulatory_approvals}": random.choice(regulatory_approvals),
        "{regulatory_matters}": random.choice(regulatory_matters),

        # Credit ratings
        "{rating}": rating1,
        "{rating2}": rating2,
        "{rating3}": rating3,
        "{agency}": agency1,
        "{agency2}": agency2,
        "{agency3}": agency3,
        "{outlook}": random.choice(rating_outlooks),
        "{rating_action}": random.choice(rating_actions),

        # Accounting and policy
        "{standard_purpose}": random.choice(shared_purposes),
        "{standard_description}": random.choice(general_descriptions),
        "{policy_description}": random.choice(general_descriptions),
        "{policy_feature}": random.choice(general_additional_features),
        "{adoption_method}": random.choice(shared_adoption_methods),
        "{transition_feature}": random.choice(shared_transition_features),
        "{adoption_impact}": random.choice(adoption_impacts),

        # Hedging and risk
        "{hedge_description}": random.choice(hedging_descriptions),
        "{hedge_feature}": random.choice(hedging_additional_features),
        "{self_insured_risks}": random.choice(self_insured_risks),
        "{insurance_incident}": random.choice(insurance_incidents),
        "{insurance_coverage_types}": random.choice(coverage_types),
        "{risk_factors}": random.choice(risk_factors_examples),
        "{risk_item}": random.choice(risk_items_other),

        # Competitive and market
        "{competitive_characteristics}": random.choice(competitive_characteristics),
        "{competitive_factors}": random.choice(competitive_factors),
        "{competitive_pressure_reasons}": random.choice(competitive_pressure_reasons),
        "{competitive_advantages}": random.choice(competitive_advantages),
        "{volatility}": random.choice(volatility_levels),

        # Miscellaneous
        "{location}": random.choice(balance_sheet_locations),
        "{unit}": random.choice(volume_units),
        "{exchange}": random.choice(exchanges),
        "{mission_statement}": random.choice(mission_statements),
        "{industry}": random.choice(industries),
        "{segment_names}": random.choice(segment_examples),
        "{form}": random.choice(sec_forms),
        "{state}": random.choice(states),
        "{city}": random.choice(cities),
        "{p_metric}": random.choice(performance_metrics),
        "{model}": random.choice(valuation_models),
        "{ticker}": "".join(random.choices(string.ascii_uppercase, k=random.randint(3, 4))),
        "{words}": random.choice(forward_looking_words),
        "{topics}": random.choice(forward_looking_topics),
        "{increase_decrease}": random.choice(["increase", "decrease", "improved", "decreased"]),
        "{assess_verb}": random.choice(assessment_verbs),
    }
    if template_pool:
        for _ in range(random.randint(3, 4)):
            template = random.choice(template_pool)
            sentence = template
            all_placeholders = re.findall(r'{\w+}', sentence)
            for key in all_placeholders:
                value = replacements.get(key, f"__NOT_FOUND__{key}")
                sentence = sentence.replace(key, str(value))
            all_sentences.append(sentence)
    # Fix any remaining placeholders
    for idx, _ in enumerate(all_sentences):
        for key, value in replacements.items():
            all_sentences[idx] = all_sentences[idx].replace(key, str(value))
    label = get_primary_label(labels)
    paragraph = cleanup(all_sentences, reporting_year, fullCheck=False)
    return paragraph, labels, label

def generate(size_per_label=100):
    """
    Generate the dataset. Fixed:
      - Ensure DataFrame columns match the tuple order appended to all_samples.
      - Convert the 'labels' dict column to JSON strings before sorting.
      - Add a defensive assertion that each item is (sentence, labels_dict, label_int).
    """
    all_samples = []
    swap_types = ["ir", "fx", "cp", "eq", "gen"]
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
                        generate_hedge_paragraph,
                        has_active_derivative=True,
                        swapType=prefix,
                    )
                )
            for _ in range(swap_counts):
                futures.append(
                    executor.submit(
                        generate_hedge_paragraph,
                        has_active_derivative=False,
                        swapType=prefix,
                    )
                )
            for _ in range(count):
                futures.append(
                    executor.submit(
                        generate_hedge_paragraph,
                        has_active_derivative=None,
                        swapType=prefix,
                    )
                )
        for _ in range(count):
            futures.append(
                executor.submit(
                    generate_hedge_paragraph,
                    has_active_derivative=None,
                    swapType=None,
                )
            )

        # Warrant and Embedded Derivative Generation
        warr_emb_count = count * 2 
        for _ in range(warr_emb_count):
            futures.append(executor.submit(generate_warrant_paragraph, use_case='current'))
            futures.append(executor.submit(generate_warrant_paragraph, use_case='historical'))
            futures.append(executor.submit(generate_warrant_paragraph, use_case='speculative'))
            futures.append(executor.submit(generate_emb_paragraph, use_case='current'))
            futures.append(executor.submit(generate_emb_paragraph, use_case='historical'))
            futures.append(executor.submit(generate_emb_paragraph, use_case='speculative'))

        # Noise Generation
        noise_count = count * 2
        noise_types = ['eq', 'cp', 'ir', 'fx', 'law', 'spec']
        for _ in range(noise_count):
            for noise_type in noise_types:
                futures.append(executor.submit(generate_noise_paragraph, noise_type=noise_type))
        for _ in range(size_per_label): # Any random noise
            futures.append(executor.submit(generate_noise_paragraph, noise_type=None))
            
        for _ in range(count // 2):
            futures.append(executor.submit(generate_sec_noise))
        return futures

    # --- Parallel execution with tqdm progress bar ---
    with ThreadPoolExecutor(max_workers=max(mp.cpu_count() * 2, 8)) as executor:
        futures = submit_tasks(executor) # This is where the tasks are submitted
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Generating samples",
        ):
            result = future.result()
            if result and result[0] is not None:
                paragraph, labels, label = result
                # Defensive checks to catch wrong tuple order early
                assert isinstance(paragraph, str), "expected paragraph string as first item"
                assert isinstance(labels, dict), "expected labels dict as second item"
                assert isinstance(label, int), "expected integer label as third item"
                all_samples.append((paragraph, labels, label))

    # --- Create and sort DataFrame ---
    # IMPORTANT: tuple order is (sentence, labels_dict, label_int) so columns must match that order
    df_new = pd.DataFrame(all_samples, columns=["sentence", "labels", "label"])

    # Convert labels dicts → JSON strings for Excel compatibility
    df_new["labels"] = df_new["labels"].apply(json.dumps)

    # Sort by numeric label and sentence text (both are hashable/scalar)
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

# %%
generate(1000)

# %%
df = pd.read_excel(output_file)
df.to_parquet(parquet_file, index=False)