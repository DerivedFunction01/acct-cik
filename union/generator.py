# %%
"""
Standalone Collective Bargaining Training Data Generator
Separate from hedge generation system
"""

import random
import pandas as pd
import re
import json
import multiprocessing as mp
from dataclasses import dataclass, field
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from openpyxl import load_workbook

# Import all templates from template.py
from template import *


def load_company_names(file_path="./names.xlsx"):
    """Loads company names from an Excel file."""
    return list(pd.read_excel(file_path)["name"])


# ==============================================================================
# LABEL SYSTEM
# ==============================================================================


def new_cb_label():
    """Initialize empty CB label dictionary"""
    return {
        "cb_coverage": 0,  # Has actual collective bargaining coverage
        "cb_risk": 0,  # Risk factor/speculative mention
        "us_risk": 0,  # US specific risk
        "int_risk": 0,  # International specific risk
        "cb_international": 0,  # Only international operations
        "cb_us": 0,  # Only US operations
        "no_cb": 0,  # Explicit no coverage statement
        "irrelevant": 0,  # Irrelevant to collective bargaining
    }


class PrimaryLabel(Enum):
    """Defines the primary integer labels for classification."""

    CB_COVERAGE = 0
    CB_RISK = 2
    NO_CB_EXPLICIT = 3
    INTERNATIONAL_ONLY = 4
    CB_US_ONLY = 5
    IRRELEVANT = 6


def get_primary_cb_label(labels: dict) -> int:
    """
    Assigns a single primary integer label based on a dictionary of multi-hot labels.

    Priority Order:
    1. US-Only Coverage
    2. International-Only Coverage
    3. General Coverage
    4. Risk Mentions
    5. No Coverage
    6. Irrelevant
    """
    if labels.get("cb_us") and not labels.get("cb_international"):
        return PrimaryLabel.CB_US_ONLY.value

    if labels.get("cb_international") and not labels.get("cb_us"):
        return PrimaryLabel.INTERNATIONAL_ONLY.value

    if labels.get("cb_coverage"):
        return PrimaryLabel.CB_COVERAGE.value

    if labels.get("cb_risk"):
        return PrimaryLabel.CB_RISK.value

    if labels.get("no_cb"):
        return PrimaryLabel.NO_CB_EXPLICIT.value

    return PrimaryLabel.IRRELEVANT.value


# ==============================================================================
# GENERATOR FUNCTIONS
# ==============================================================================


def generate_irrelevant_paragraph(irrelevant_data_pool: list[str]) -> tuple:
    """
    Pulls a random paragraph from the pre-generated financial data pool
    and labels it as irrelevant for the CB model.
    """
    if not irrelevant_data_pool:
        return None, None, None

    # Select a random paragraph of financial text
    paragraph = random.choice(irrelevant_data_pool)
    # Strip out anything between < and >
    paragraph = re.sub(r"<.*?>", "", paragraph).strip()
    # Assign irrelevant labels
    labels = new_cb_label()  # All zeros
    labels["irrelevant"] = 1
    primary_label = get_primary_cb_label(labels)  # Will resolve to IRRELEVANT

    # The text is already cleaned, but we can ensure it's a single line
    cleaned_paragraph = re.sub(r'\s+', ' ', paragraph).strip()

    return cleaned_paragraph, labels, primary_label

@dataclass
class VariableGenerator:
    """Generates and holds all random variables for a paragraph."""

    company_names: list[str]
    year_range: tuple[int, int] = (1999, 2025)
    geographic_context: str = "generic"
    variables: dict = field(default_factory=dict)

    def __post_init__(self):
        self.generate_all()

    def generate_all(self):
        """Generate all variables and store them."""
        year = random.randint(self.year_range[0], self.year_range[1])
        month = random.choice(months)

        total = random.randint(100, 50000)
        pct = random.randint(5, 95)
        cb_count = int(total * pct / 100)
        us_count = int(total * 0.6)

        company = (
            random.choice(self.company_names)
            if random.random() < 0.9
            else "The Company"
        )

        # Always generate both US and international entities
        us_location = random.choice(us_locations)
        us_union = random.choice(us_unions)
        intl_location = random.choice(international_locations)
        intl_union = random.choice(international_unions)
        generic_union_choice = random.choice(generic_unions)

        # For the new contextual system
        curr_location, other_location = "", ""
        curr_union, other_union = random.choice(generic_unions), random.choice(generic_unions)

        # Set primary location/union based on context
        if self.geographic_context == "us":
            location = us_location
        elif self.geographic_context == "international":
            location = intl_location
        else:  # generic
            location = random.choice(us_locations + international_locations)

        # Map to curr/other based on context
        if self.geographic_context == "us":
            curr_location, other_location = us_location, intl_location
            curr_union, other_union = us_union, intl_union
        elif self.geographic_context == "international":
            curr_location, other_location = intl_location, us_location
            curr_union, other_union = intl_union, us_union
        # else: generic - leave as empty strings

        facility = random.choice(facilities)

        self.variables = {
            "{year}": str(year),
            "{past_year}": str(random.randint(year - 10, year - 1)),
            "{month}": month,
            "{day}": str(random.randint(1, 28)),
            "{quarter}": random.choice(quarters),
            "{expiration_month}": random.choice(months),
            "{expiration_year}": str(random.randint(year, year + 5)),
            "{total}": f"{total:,}",
            "{pct}": str(pct),
            "{pct2}": str(random.randint(5, 50)),
            "{intl_pct}": str(random.randint(20, 70)),
            "{cb_count}": f"{cb_count:,}",
            "{cb_count2}": f"{random.randint(50, 500):,}",
            "{full_time}": f"{int(total * 0.9):,}",
            "{part_time}": f"{total - int(total * 0.9):,}",
            "{us_count}": f"{us_count:,}",
            "{intl_count}": f"{total - us_count:,}",
            "{company}": company,
            "{facility}": facility,
            "{generic_union}": generic_union_choice,
            "{location}": location,
            # New contextual placeholders
            "{curr_location}": curr_location,
            "{curr_union}": curr_union,
            "{other_location}": other_location,
            "{other_union}": other_union,
            "{industry}": random.choice(industries),
            "{quality}": random.choice(relationship_quality),
            "{num_unions}": str(random.randint(2, 15)),
            "{num_locations}": str(random.randint(5, 60)),
            "{expiration}": random.choice(expiration_phrases),
            "{negotiation_status}": random.choice(negotiation_status),
            "{risk_verb}": random.choice(risk_verbs),
            "{risk_event}": random.choice(risk_events),
            "{risk_consequence}": random.choice(risk_consequences),
        }

    def get(self, key: str) -> str:
        """Get a specific variable."""
        return self.variables.get(key, "")

    def get_all(self) -> dict:
        """Get all generated variables."""
        return self.variables


def _get_template_and_labels(
    cb_type: str, var_gen: VariableGenerator
) -> tuple[str, dict]:
    """
    Selects a template and returns its corresponding labels based on the cb_type.

    Args:
        cb_type: Type of template to select
        var_gen: Variable generator instance
    """
    labels = new_cb_label()
    template = ""

    if cb_type == "coverage":
        labels["cb_coverage"] = 1
        template_pool = (
            coverage_with_numbers_templates
            if random.random() < 0.7
            else coverage_vague_templates
        )
        template = random.choice(template_pool)

    elif cb_type == "no_coverage":
        labels["no_cb"] = 1
        template = random.choice(no_coverage_templates)

    elif cb_type == "risk":
        labels["cb_risk"] = 1
        if var_gen.geographic_context in ["us", "international"]:
            if var_gen.geographic_context == "us":
                labels["us_risk"] = 1
            else: # international
                labels["int_risk"] = 1
            template = random.choice(contextual_risk_templates)
        else:
            # Fallback to general risk if context is not us/intl
            template = random.choice(
                risk_factor_templates
                + existing_coverage_risk_templates
                + risk_combination_templates
            )

    elif cb_type == "international":
        template = random.choice(exclusive_coverage_templates)
        labels["cb_coverage"] = 1

    elif cb_type == "adversarial":
        labels["no_cb"] = 1
        adversarial_template_map = {
            "historical": historical_templates,
            "conditional": conditional_templates,
            "third_party": third_party_templates,
        }
        adv_type = random.choice(list(adversarial_template_map.keys()))
        template = random.choice(adversarial_template_map[adv_type])

    elif cb_type == "us_only":
        template = random.choice(exclusive_coverage_templates)
        labels["cb_coverage"] = 1

    return template, labels



def _resolve_placeholders(text: str, replacements: dict) -> str:
    """Iteratively replaces placeholders to handle nested cases."""
    # First, resolve the dummy/negation placeholders back to their standard form
    text = text.replace("{neg_other_location}", "{other_location}")
    text = text.replace("{neg_curr_location}", "{curr_location}")
    text = text.replace("{neg_curr_union}", "{curr_union}")
    text = text.replace("{neg_other_union}", "{other_union}")

    for _ in range(3):
        for key, value in replacements.items():
            text = text.replace(key, value)

    if "{" in text or "}" in text:
        print(f"Warning: Unresolved placeholder found in text: {text}")
    return text


def cleanup(text: str) -> str:
    """Clean up final paragraph formatting."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+\.", ".", text)
    text = text.strip()
    if text:
        text = text[0].upper() + text[1:]
    if not text.endswith("."):
        text += "."
    return text


def generate_cb_paragraph(
    cb_type=None,
    year_range=(1999, 2025),
    company_names=None,
):
    """
    Generate a single CB paragraph with proper geographic labeling.
    """
    labels = new_cb_label()

    if cb_type is None:
        cb_type = random.choice(
            [
                "coverage",
                "coverage",
                "coverage",
                "no_coverage",
                "no_coverage",
                "risk",
                "international",
                "us_only",
                "adversarial",
                "irrelevant", # Added for external data
            ]
        )

    # Determine geographic context
    if cb_type == "us_only":
        geo_context = "us"
    elif cb_type == "international":
        geo_context = "international"
    elif cb_type == "risk":
        # For risk, explicitly choose geography
        geo_context = random.choice(["us", "international", "generic"])
    else:
        geo_context = random.choice(["us", "international", "generic"])

    var_gen = VariableGenerator(
        company_names, year_range, geographic_context=geo_context
    )
    replacements = var_gen.get_all()
    company = var_gen.get("{company}")

    # Single-type paragraphs
    template, labels = _get_template_and_labels(cb_type, var_gen)

    # --- Paragraph Assembly ---
    # Always generate 2-4 sentences to create more realistic paragraphs.
    sentences = [template]
    
    # Create a pool of relevant supplemental sentences with their associated labels
    supplemental_pool_with_labels = []
    
    def add_to_pool(templates, label_updates):
        for t in templates:
            supplemental_pool_with_labels.append((t, label_updates))

    if cb_type in ["coverage", "us_only", "international"]:
        add_to_pool(relationship_templates, {})
        add_to_pool(expiration_templates, {"cb_coverage": 1})
        add_to_pool(negotiation_templates, {"cb_coverage": 1})
    elif cb_type == "no_coverage":
        add_to_pool(relationship_templates, {})
        add_to_pool(risk_factor_templates, {"cb_risk": 1}) # Add potential future risks
    elif cb_type == "risk":
        # Ensure supplemental sentences match the geographic context
        if geo_context in ["us", "international"]:
            add_to_pool(contextual_risk_templates, {"cb_risk": 1})
        else: # generic
            add_to_pool(risk_factor_templates, {"cb_risk": 1})

    elif cb_type == "adversarial":
        add_to_pool(no_coverage_templates, {"no_cb": 1})
        add_to_pool(relationship_templates, {})

    # Add 1 to 3 additional sentences
    num_supplemental = random.randint(1, 3)
    if supplemental_pool_with_labels:
        added_sentences = random.sample(supplemental_pool_with_labels, k=min(num_supplemental, len(supplemental_pool_with_labels)))
        for sentence_template, label_updates in added_sentences:
            sentences.append(sentence_template)
            for key, value in label_updates.items():
                if value: labels[key] = 1

    random.shuffle(sentences)
    paragraph = ". ".join(sentences)

    # Add Human Capital intro
    if random.random() < 0.15:
        human_capital_intros = [
            "Human Capital Resources. ",
            "Human Capital. ",
            "Our principal asset is our employees. ",
        ]
        paragraph = (
            random.choice(human_capital_intros) + paragraph[0].lower() + paragraph[1:]
        )

    # Scan the final template string for placeholders to set geo labels.
    # This is more reliable than relying on cb_type alone.
    has_curr_union = "{curr_union" in paragraph
    has_curr_location = "{curr_location" in paragraph
    has_other_union = "{other_union" in paragraph
    has_other_location = "{other_location" in paragraph


    if has_curr_union:
        if geo_context == "us":
            labels["cb_us"] = 1
        elif geo_context == "international":
            labels["cb_international"] = 1
    if has_curr_location:
        if geo_context == "us":
            labels["cb_us"] = 1
        elif geo_context == "international":
            labels["cb_international"] =1

    if has_other_union:
        if geo_context == "us":
            labels["cb_us"] = 1
        elif geo_context == "international":
            labels["cb_international"] = 1
    if has_other_location:
        if geo_context == "us":
            labels["cb_us"] = 1
        elif geo_context == "international":
            labels["cb_international"] = 1

    # Resolve placeholders and clean up
    resolved_paragraph = _resolve_placeholders(paragraph, replacements)
    final_paragraph = cleanup(resolved_paragraph)

    # Get primary label
    primary_label = get_primary_cb_label(labels)

    return final_paragraph, labels, primary_label


# ==============================================================================
# BATCH GENERATION
# ==============================================================================


def generate(size_per_label=1000, company_names=None):
    """Generate full CB training dataset."""
    all_samples = []

    generation_plan = {
        "coverage": size_per_label * 3,
        "no_coverage": size_per_label * 2,
        "irrelevant": size_per_label, # Add irrelevant data to the plan
        "risk": size_per_label,
        "international": size_per_label,
        "us_only": size_per_label,
        "adversarial": size_per_label * 2,
    }

    def submit_tasks(executor):
        futures = []
        # Load the irrelevant data pool once
        try:
            irrelevant_pool = pd.read_parquet("./irr_training_data.parquet")['sentence'].tolist()
            print(f"✅ Loaded {len(irrelevant_pool):,} paragraphs for irrelevant data generation.")
        except FileNotFoundError:
            irrelevant_pool = []
            print("⚠️  Could not find './irr_training_data.parquet'. Skipping irrelevant data generation from this source.")

        for cb_type, count in generation_plan.items():
            for _ in range(count):
                if cb_type == "irrelevant":
                    futures.append(executor.submit(generate_irrelevant_paragraph, irrelevant_pool))
                else:
                    futures.append(
                        executor.submit(
                            generate_cb_paragraph,
                            cb_type=cb_type,
                            company_names=company_names,
                        )
                    )
        return futures

    with ThreadPoolExecutor(max_workers=max(mp.cpu_count() * 2, 8)) as executor:
        futures = submit_tasks(executor)
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Generating training samples",
        ):
            result = future.result()
            if result and result[0] is not None:
                paragraph, labels, label = result
                all_samples.append((paragraph, labels, label))

    df = pd.DataFrame(all_samples, columns=["sentence", "labels", "label"])
    df["labels"] = df["labels"].apply(json.dumps)
    df.sort_values(by=["label", "sentence"], ascending=[True, True], inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    output_file = "./cb_training_data.xlsx"
    parquet_file = "./cb_training_data.parquet"
    company_name_file = "./names.xlsx"

    try:
        company_names_list = load_company_names(company_name_file)
    except FileNotFoundError:
        print(
            f"Warning: Company name file not found at '{company_name_file}'. Using default names."
        )
        company_names_list = None

    print("Generating Collective Bargaining training data...")
    df = generate(size_per_label=250, company_names=company_names_list)
    df.drop_duplicates(subset=["sentence"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    df.to_excel(output_file, sheet_name="CB_Data", index=False)
    print(f"\n{len(df)} samples written to {output_file}")

    df.to_parquet(parquet_file, index=False)
    print(f"Also saved to {parquet_file}")

    print("\nLabel Distribution:")
    label_names = {
        PrimaryLabel.CB_COVERAGE.value: "CB_Coverage_Disclosed",
        PrimaryLabel.CB_RISK.value: "CB_Risk_Only",
        PrimaryLabel.NO_CB_EXPLICIT.value: "No_CB_Explicit",
        PrimaryLabel.INTERNATIONAL_ONLY.value: "International_Only",
        PrimaryLabel.CB_US_ONLY.value: "CB_US_Only",
        PrimaryLabel.IRRELEVANT.value: "Irrelevant",
    }

    for label_id, count in df["label"].value_counts().sort_index().items():
        print(f"  {label_id} ({label_names.get(label_id, 'Unknown')}): {count:,}")

    # Debug: Show sample of geographic labels
    print("\nGeographic Label Distribution:")
    label_data = df["labels"].apply(json.loads)
    print(f"  cb_us: {sum(l.get('cb_us', 0) for l in label_data):,}")
    print(
        f"  cb_international: {sum(l.get('cb_international', 0) for l in label_data):,}"
    )
    print(f"  us_risk: {sum(l.get('us_risk', 0) for l in label_data):,}")
    print(f"  int_risk: {sum(l.get('int_risk', 0) for l in label_data):,}")
    print(
        f"  cb_coverage (total): {sum(l.get('cb_coverage', 0) for l in label_data):,}"
    )
    print(f"  cb_risk (total): {sum(l.get('cb_risk', 0) for l in label_data):,}")

#%%