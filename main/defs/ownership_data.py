import random
from dataclasses import dataclass
from typing import Tuple, Union

from defs.function_definitions import _get_company_reference, _cleanup_sentence
from defs.instrument_definitions import BaseNarrativeEvidence, ContextEvidence
from defs.scenario_definitions import company_names

# Ported from old/template/other.py

sec_forms = ["Schedule 13G", "Schedule 13D", "Form 13F"]

insider_actions = [
    "purchases",
    "sales",
    "exercises",
    "grants",
    "net purchases",
    "net sales",
]

institutional_ownership_templates = [
    "As of {month} {end_day}, {year}, institutional investors held approximately {pct}% of {company}'s outstanding shares",
    "{company2} reported a {pct}% ownership stake in {company} as of {month} {end_day}, {year}",
    "{company}'s largest shareholders include {company2} ({pct}%), {company3} ({pct2}%), and other institutional investors",
    "Beneficial ownership by institutional investors increased to {pct}% as of {month} {end_day}, {year}",
    "Hedge funds and asset managers collectively own approximately {pct}% of outstanding common stock",
    "{company2} disclosed a {pct}% position in {company} in its {form} filing dated {month} {year}",
    "Institutional ownership decreased from {pct2}% to {pct}% during {year}",
    "{company}'s top ten institutional shareholders hold approximately {pct}% of outstanding shares",
]

insider_ownership_templates = [
    "Directors and executive officers collectively beneficially own approximately {pct}% of outstanding common stock as of {month} {end_day}, {year}",
    "{company}'s Chief Executive Officer owns {shares} shares, representing {pct}% of shares outstanding",
    "Insider transactions during {year} included {shares} shares by executive officers and directors",
    "As of {month} {end_day}, {year}, executive officers and directors held options to purchase {shares} shares of common stock",
]


@dataclass
class HedgeFundContextEvidence(BaseNarrativeEvidence):
    """Evidence that a sentence mentions a 'hedge fund' as an entity, not a hedging instrument."""

    details: str = ""

    def to_string(self) -> str:
        """Generates a reasoning statement that explicitly distinguishes hedge funds from hedging instruments."""
        return (
            "The text mentions 'hedge funds' in the context of security ownership, which are investment entities "
            "and should not be confused with 'hedging instruments' (derivatives) used for risk management."
        )

@dataclass
class OwnershipContextSentence:
    """Generates contextual sentences about institutional or insider ownership."""

    company_name: str
    reporting_year: int
    reporting_month: str
    reporting_day: int

    def build(self) -> Tuple[str, Union[ContextEvidence, HedgeFundContextEvidence]]:
        """Builds a paragraph about ownership and returns it with corresponding evidence."""
        # --- NEW: Give a dedicated chance to generate the hedge fund sentence ---
        if random.random() < 0.35:  # 35% chance to specifically mention hedge funds
            template = "Hedge funds and asset managers collectively own approximately {pct}% of outstanding common stock"
        # Otherwise, choose from the other templates
        elif random.random() < 0.6:  # Adjusted probability for other institutional mentions
            # Exclude the hedge fund template to avoid duplication if the first check fails
            other_institutional_templates = [
                t for t in institutional_ownership_templates if "Hedge funds" not in t
            ]
            template = random.choice(other_institutional_templates)
        else:
            template = random.choice(insider_ownership_templates)

        # Generate placeholders
        placeholders = self._get_placeholders()
        sentence = _cleanup_sentence(template.format_map(placeholders))

        # --- NEW: If the sentence mentions hedge funds, use the specific evidence type ---
        if "hedge fund" in sentence.lower():
            evidence = HedgeFundContextEvidence(category="OWN", status="context_mention", details=sentence)
        else:
            # Otherwise, use the generic ownership context evidence
            evidence = ContextEvidence(category="OWN", status="context_mention", details=sentence)

        return sentence, evidence

    def _get_placeholders(self) -> dict:
        """Helper to generate a dictionary of placeholders for formatting templates."""
        # Find two different company names for the placeholders
        other_companies = random.sample(
            [c for c in company_names if c != self.company_name], 2
        )

        return {
            "company": _get_company_reference(self.company_name),
            "company2": other_companies[0],
            "company3": other_companies[1],
            "year": self.reporting_year,
            "month": self.reporting_month,
            "end_day": self.reporting_day,
            "pct": f"{random.uniform(5, 40):.1f}",
            "pct2": f"{random.uniform(1, 10):.1f}",
            "form": random.choice(sec_forms),
            "shares": f"{random.randint(100_000, 5_000_000):,}",
        }
