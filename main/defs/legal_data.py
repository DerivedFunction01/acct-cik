import random
from dataclasses import dataclass
from typing import Optional, List

from defs.function_definitions import _get_company_reference, _cleanup_sentence, _format_single_notional
from defs.common_data import assessment_verbs, quarters, immaterial, material, change_phrases_noun


@dataclass
class LegalContextSentence:
    """Generates contextual sentences about legal matters related to derivatives lawsuits."""
    company_name: str
    reporting_year: int
    reporting_month: str
    reporting_day: int
    currency_symbol: str
    currency_code: str
    prefer_abbreviated: bool

    def build(self) -> str:
        """Builds a multi-sentence paragraph about the company's legal proceedings."""
        num_sentences = random.randint(1, 3)
        sentences: List[str] = []

        # The first sentence is often a general statement.
        template = random.choice(litigation_templates)
        placeholders = self._get_placeholders()
        sentences.append(_cleanup_sentence(template.format_map(placeholders)))

        # Add more specific sentences
        for _ in range(num_sentences - 1):
            # Randomly choose between a specific lawsuit detail, an assessment, or an outcome.
            choice = random.random()
            if choice < 0.4:
                template = random.choice(specific_lawsuit_templates)
            elif choice < 0.8:
                template = random.choice(litigation_assessment_templates)
            else:
                template = random.choice(lawsuit_outcome_templates)

            placeholders = self._get_placeholders()
            sentences.append(_cleanup_sentence(template.format_map(placeholders)))

        return " ".join(sentences)

    def _get_placeholders(self) -> dict:
        """Helper to generate a dictionary of placeholders for formatting templates."""
        amount = random.randint(1, 200) * 1_000_000
        return {
            "company": _get_company_reference(self.company_name),
            "year": self.reporting_year,
            "month": self.reporting_month,
            "end_day": self.reporting_day,
            "litigation_examples": _generate_case_types(),
            "court_name": _generate_court_name(),
            "lawsuit_allegation": _generate_allegation(),
            "assess_verb": random.choice(assessment_verbs),
            "quarter": random.choice(quarters),
            "currency_code": self.currency_code,
            "amount": _format_single_notional(amount, self.currency_symbol, self.prefer_abbreviated, no_unit_word=True),
            "money_unit": "million" if self.prefer_abbreviated else "",
        }


def _generate_court_name() -> str:
    """Dynamically generates a realistic court name from various components."""
    
    # Define templates for different court structures
    court_templates = {
        "federal_district": [
            "United States District Court for the {district} of {state}",
            "U.S. District Court for the {district} of {state}",
        ],
        "federal_appeals": [
            "United States Court of Appeals for the {circuit} Circuit",
            "U.S. Court of Appeals for the {circuit} Circuit",
        ],
        "federal_specialty": [
            "United States Supreme Court",
            "United States Court of Federal Claims",
            "United States Tax Court",
            "United States Bankruptcy Court for the District of {state}",
            "United States Court of International Trade",
        ],
        "state_superior": [
            "Superior Court of {state}",
            "Superior Court of the State of {state}",
            "{state} Superior Court",
        ],
        "state_county": [
            "{court_type} of {county} County, {state}",
            "{state} {court_type}, {county} County",
        ],
        "state_chancery": [
            "Court of Chancery of the State of {state}",
            "{state} Court of Chancery",
        ],
        "state_supreme": [
            "{state} Supreme Court",
            "Supreme Court of the State of {state}",
        ],
    }

    # Choose a category of court to generate
    court_category = random.choices(
        list(court_templates.keys()),
        weights=[40, 15, 10, 10, 15, 5, 5], # Weights to control frequency
        k=1
    )[0]

    template = random.choice(court_templates[court_category])

    # Get random components for the chosen template
    state_name, county_name = random.choice(states_and_counties)

    placeholders = {
        "district": random.choice(federal_districts),
        "state": state_name,
        "circuit": random.choice(federal_circuits),
        "court_type": random.choice(state_court_types),
        "county": county_name,
    }

    # Special handling for single-district states
    if placeholders["district"] == "District" and "of" in template:
        template = template.replace("{district} of", "District of")

    return template.format_map(placeholders)


def _generate_case_types() -> str:
    """Dynamically generates a string of example legal case types."""
    num_examples = random.randint(2, 3)
    
    # Combine different categories for variety
    subjects = random.sample(legal_subjects, k=num_examples)
    actions = random.sample(legal_actions, k=num_examples)
    areas = random.sample(legal_areas, k=num_examples)
    
    # Mix and match to create phrases like "product liability, employment matters, and commercial disputes"
    examples = [f"{subjects[i]} {actions[i]}" for i in range(num_examples)]
    
    if len(examples) > 1:
        return ", ".join(examples[:-1]) + f", and {examples[-1]}"
    return examples[0]


def _generate_allegation() -> str:
    """Dynamically generates a plausible lawsuit allegation."""
    num_allegations = random.randint(1, 3)
    
    # Pick from the new component lists
    subjects = random.sample(legal_subjects, k=num_allegations)
    actions = random.sample(legal_actions, k=num_allegations)
    
    # Create phrases like "breach of contract and misappropriation of trade secrets"
    allegation_phrases = []
    for i in range(num_allegations):
        # 50% chance to have a more descriptive allegation
        if random.random() < 0.5:
            allegation_phrases.append(f"{subjects[i]} {actions[i]}")
        else:
            allegation_phrases.append(f"{random.choice(legal_verbs)} of {subjects[i]}")

    if len(allegation_phrases) > 1:
        return ", ".join(allegation_phrases[:-1]) + f" and {allegation_phrases[-1]}"
    return allegation_phrases[0]


# =============================================================================
# Legal "Noise" Templates
# Ported from the "LAW" section of noise_templates in old/template/other.py
# These describe legal issues that mention derivatives but are not about hedging use.
# =============================================================================

# ============ LITIGATION AND LEGAL MATTERS ============

litigation_templates = [
    "{company} is involved in various legal proceedings and claims arising in the ordinary course of business, including {litigation_examples}",
    "As of {month} {end_day}, {year}, {company} is a defendant in several lawsuits related to {litigation_examples}",
    "{company} is subject to litigation and regulatory inquiries concerning {litigation_examples} in the normal course of operations",
    "Various legal actions, proceedings, and claims are pending or may be instituted against {company}, including {litigation_examples}",
    "As of {month} {end_day}, {year}, {company} is a defending against several derivative lawsuits related to {litigation_examples}",
    'All securities holders of {company} are hereby notified that a settlement (the "Settlement") has been reached as to claims asserted in the above-captioned consolidated shareholder derivative action pending in a {court_name} (the "Derivative Action") on behalf of {company} against certain of its current or former directors and officers',
    "On {month} {end_day}, {year}, a shareholder derivative suit was filed in the {court_name} for the against {company}",
]

# =============================================================================
# Legal "Noise" Templates
# Ported from the "LAW" section of noise_templates in old/template/other.py
# These describe legal issues that mention derivatives but are not about hedging use.
# =============================================================================

# ============ LITIGATION AND LEGAL MATTERS ============

litigation_assessment_templates = [
    "Management believes that the ultimate resolution of these matters will not have a {materiality} adverse effect on {company}'s financial position, results of operations, or cash flows",
    "While the outcome of these proceedings cannot be predicted with certainty, management does not believe they will have a {materiality} impact on the consolidated financial statements",
    "{company} believes it has meritorious defenses and intends to vigorously defend against these claims",
    "{company} intend to vigorously defend against these claims. At this time, {company} cannot predict the outcome, or provide a reasonable estimate or range of estimates of the possible outcome or loss, if any, in this matter",
    "Based on currently available information, management does not expect these matters to result in a {materiality} loss",
    "{company} has {assess_verb} the likelihood of loss as remote and has not recorded any provisions related to these contingencies",
    "The potential {change_noun} in the estimated liability for these legal matters is considered {materiality} by management.",
]

specific_lawsuit_templates = [
    "In {month} {year}, a lawsuit was filed against {company} in the {court_name} alleging {lawsuit_allegation}. {company} filed a motion to dismiss in {month} {year}",
    "{company} is defending a class action lawsuit filed in {year} claiming {lawsuit_allegation}, with damages sought of approximately {currency_code}{amount} {money_unit}",
    "During {year}, {company} reached a settlement in a lawsuit related to {lawsuit_allegation} for a {materiality} amount of {currency_code}{amount} {money_unit}, which was accrued in prior periods",
    "A complaint was filed against {company} in the {court_name} during {quarter} quarter {year} alleging {lawsuit_allegation}",
    "A provision of {currency_code}{amount} {money_unit} was recorded in the {quarter} quarter of {year} for a potential settlement related to claims of {lawsuit_allegation}, though the final outcome is uncertain.",
]

lawsuit_outcome_templates = [
    # Settlements
    "{company} reached a settlement agreement in the matter of {lawsuit_allegation}, agreeing to pay {currency_code}{amount} {money_unit} without admitting any wrongdoing.",
    "A settlement was reached in the {court_name} regarding claims of {lawsuit_allegation}, for which {company} has accrued {currency_code}{amount} {money_unit}.",
    "In {month} {year}, the parties agreed to a settlement to resolve the litigation concerning {lawsuit_allegation}, the financial terms of which are confidential but are not expected to be {materiality}.",
    "The shareholder derivative action was settled for a {materiality} amount of {currency_code}{amount} {money_unit}, funded by insurance proceeds.",
    # Dismissals
    "The {court_name} granted {company}'s motion to dismiss the lawsuit alleging {lawsuit_allegation} in its entirety.",
    "On {month} {end_day}, {year}, the court dismissed all claims against {company} related to the {lawsuit_allegation} matter.",
    "{company} successfully obtained a dismissal of the class action lawsuit concerning {lawsuit_allegation}.",
    # Judgments (Favorable and Adverse)
    "A judgment was entered in favor of {company} in the {court_name} on all counts related to the {lawsuit_allegation} case.",
    "An adverse judgment of {currency_code}{amount} {money_unit} was entered against {company} in the lawsuit alleging {lawsuit_allegation}, which {company} intends to appeal.",
    "Following a trial, the jury returned a verdict in favor of {company}, finding no liability on the claims of {lawsuit_allegation}.",
]

# --- Dynamic Court Name Components ---

federal_districts = ["Northern District", "Southern District", "Eastern District", "Western District", "Central District", "District"]
federal_circuits = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "D.C.", "Federal"]
state_court_types = ["Superior Court", "Circuit Court", "District Court", "Court of Common Pleas"]

# A sample of states and major counties to create realistic local court names
states_and_counties = [
    ("California", "Los Angeles"), ("California", "San Francisco"), ("California", "Orange"),
    ("New York", "New York"), ("New York", "Kings"), ("New York", "Queens"),
    ("Texas", "Harris"), ("Texas", "Dallas"), ("Texas", "Travis"),
    ("Florida", "Miami-Dade"), ("Florida", "Broward"), ("Florida", "Hillsborough"),
    ("Illinois", "Cook"), ("Illinois", "DuPage"),
    ("Pennsylvania", "Philadelphia"), ("Pennsylvania", "Allegheny"),
    ("Ohio", "Cuyahoga"), ("Ohio", "Franklin"),
    ("Georgia", "Fulton"), ("Georgia", "DeKalb"),
    ("Massachusetts", "Suffolk"), ("Massachusetts", "Middlesex"),
    ("New Jersey", "Bergen"), ("New Jersey", "Essex"),
    ("Virginia", "Fairfax"), ("Virginia", "Loudoun"),
    ("Washington", "King"),
    ("Colorado", "Denver"),
    ("Arizona", "Maricopa"),
    ("Delaware", "New Castle"),
    ("Nevada", "Clark"),
    ("Connecticut", "Hartford"),
    ("District of Columbia", "District of Columbia"),    ("Maryland", "Baltimore"),
    ("Michigan", "Wayne"),
    ("Minnesota", "Hennepin"),
    ("Missouri", "St. Louis"),
    ("North Carolina", "Wake"),
    ("Oregon", "Multnomah"),
    ("Tennessee", "Davidson"),
    ("Wisconsin", "Milwaukee"),
    ("Indiana", "Marion"),
    ("Kansas", "Johnson"),
    ("Kentucky", "Jefferson"),
    ("Louisiana", "Orleans"),
    ("Nebraska", "Douglas"),
    ("New Mexico", "Bernalillo"),
    ("Oklahoma", "Oklahoma"),
    ("South Carolina", "Richland"),
    ("Utah", "Salt Lake"),
    
]


# --- Dynamic Allegation and Case Type Components ---

legal_subjects = [
    "product liability", "intellectual property", "environmental", "patent", "contract",
    "securities", "data privacy", "fiduciary duty", "tax", "trade secrets", "federal securities laws",
    "employment discrimination", "antitrust", "product risks", "proprietary materials",
    "Fair Labor Standards Act", "insider trading", "whistleblowers", "Clean Air Act",
    "consumer protection", "assets", "trade practices", "workplace safety", "corporate governance",
    "customs duties", "international trade",
]

legal_actions = [
    "matters", "infringement", "claims", "litigation", "disputes", "violations", "breaches",
    "actions", "proceedings", "inquiries", "investigations", "disputes", "liabilities",
    "recalls", "fines", "class actions", "allegations",
]

legal_areas = [
    "commercial disputes", "employment claims", "regulatory compliance", "customer disputes",
    "tax disputes", "consumer class actions", "corporate governance disputes", "trade compliance",
]

legal_verbs = [
    "breach", "violation", "misappropriation", "infringement", "failure to comply with",
    "negligence in", "violations of", "unlawful", "failure to warn of", "fraudulent",
]

placeholders = {
    "materiality": random.choice(immaterial + material),
    "change_noun": random.choice(change_phrases_noun),
}
