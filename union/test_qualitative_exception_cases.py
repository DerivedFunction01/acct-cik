"""
Targeted scenario matrix for SimpleCoverage qualitative/exception behavior.

Run:
  python3 test_qualitative_exception_cases.py

What this file helps validate:
1) Qualitative union/non-union statements with and without exception clauses.
2) Single-sentence vs two-sentence merged behavior.
3) Compatibility of totals (same scope vs mismatched scope).
4) "except" vs "outside" phrasing.
5) Multi-country exception snippets (to compare with mixed-coverage behavior).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

from analysis import UnionAnalyzer
from defs.text_cleaner import (
    CompanyCleaner,
    CurrencyRemover,
    MinimalTextCleaner,
    ContextualNumberCleaner,
    ConcisenessCleaner,
)


@dataclass
class Scenario:
    name: str
    text: str
    notes: Optional[str] = None
    company_name: Optional[str] = "ExampleCo Holdings Inc."
    home_country: Optional[str] = "US"


SCENARIOS: List[Scenario] = [
    # ------------------------------------------------------------------
    # A. Single sentence, qualitative without exception
    # ------------------------------------------------------------------
    Scenario(
        name="A1 some-union no-exception single",
        text="Some of our employees are unionized.",
        notes="Ambiguous positive qualitative baseline.",
    ),
    Scenario(
        name="A2 majority-nonunion no-exception single",
        text="Majority of our employees are non-unionized.",
        notes="Negated qualitative baseline.",
    ),
    Scenario(
        name="A3 all-union no-exception single",
        text="All employees are unionized.",
        notes="Extreme positive qualitative baseline.",
    ),
    Scenario(
        name="A4 none-union no-exception single",
        text="None of our employees are unionized.",
        notes="Extreme zero qualitative baseline.",
    ),
    # ------------------------------------------------------------------
    # B. Single sentence, qualitative with exception
    # ------------------------------------------------------------------
    Scenario(
        name="B1 some-union except-US single",
        text="Some of our employees are unionized except for the US.",
        notes="Ambiguous positive + exception.",
    ),
    Scenario(
        name="B2 majority-nonunion except-US single",
        text="Majority of our employees are non-unionized except for the US.",
        notes="Negated qualitative + exception.",
    ),
    Scenario(
        name="B3 all-union except-US single",
        text="All employees are unionized except for the US.",
        notes="Extreme positive + exception.",
    ),
    Scenario(
        name="B4 none-union except-US single",
        text="None of our employees are unionized except for the US.",
        notes="Extreme negative + exception.",
    ),
    Scenario(
        name="B5 majority-nonunion outside-US single",
        text="Majority of our employees are non-unionized outside the US.",
        notes="outside-variant for exclusion parsing.",
    ),
    # ------------------------------------------------------------------
    # C. Two-sentence merged (compatible total context)
    # ------------------------------------------------------------------
    Scenario(
        name="C1 merged some-union except-US compatible-total",
        text="We have 1000 employees. Some of our employees are unionized except for the US.",
        notes="Classic merge path with local total.",
    ),
    Scenario(
        name="C2 merged majority-nonunion except-US compatible-total",
        text="We have 1000 employees. Majority of our employees are non-unionized except for the US.",
        notes="Merge path + split logic candidate.",
    ),
    Scenario(
        name="C3 merged all-union except-US compatible-total",
        text="We have 1000 employees. All employees are unionized except for the US.",
        notes="Merge + extreme + exception.",
    ),
    Scenario(
        name="C4 merged none-union except-US compatible-total",
        text="We have 1000 employees. None of our employees are unionized except for the US.",
        notes="Merge + zero + exception.",
    ),
    # ------------------------------------------------------------------
    # D. Two-sentence non-merge / weak-merge contexts
    # ------------------------------------------------------------------
    Scenario(
        name="D1 total-in-region sentence + exception-on-US",
        text="We have 1000 employees in Europe. Some of our employees are unionized except for the US.",
        notes="Potentially incompatible scope for count inheritance.",
    ),
    Scenario(
        name="D2 total-in-NA + exception-on-US",
        text="We have 1000 employees in North America. Majority of our employees are non-unionized except for the US.",
        notes="Compatible regional scope but excluded-country sub-scope.",
    ),
    Scenario(
        name="D3 total-US + exception-on-US",
        text="We have 1000 employees in the US. Some of our employees are unionized except for the US.",
        notes="Pathological contradiction case.",
    ),
    # ------------------------------------------------------------------
    # E. Explicit count + qualitative + exception (single sentence)
    # ------------------------------------------------------------------
    Scenario(
        name="E1 majority-nonunion of-1000 except-US single",
        text="Majority of our 1000 employees are non-unionized except for the US.",
        notes="Single-value pathway with count + qualitative + exception.",
    ),
    Scenario(
        name="E2 some-union of-1000 except-US single",
        text="Some of our 1000 employees are unionized except for the US.",
        notes="Ambiguous membership term + explicit total + exception.",
    ),
    # ------------------------------------------------------------------
    # F. Multi-country exception snippets (not simpleCoverage-focused, useful contrast)
    # ------------------------------------------------------------------
    Scenario(
        name="F1 all-union except-US-and-Canada",
        text="All employees are unionized except for the US and Canada.",
        notes="Multiple excluded countries.",
    ),
    Scenario(
        name="F2 majority-nonunion outside-US-Canada-Mexico",
        text="Majority of employees are non-unionized outside the US, Canada, and Mexico.",
        notes="Outside + chained excluded geos.",
    ),
]


def summarize_items(items: List[dict]) -> List[dict]:
    rows = []
    for i, item in enumerate(items):
        cov = item.get("coverage_data", {})
        geo = item.get("geographic_context", {})
        countries = [c.get("code") for c in geo.get("countries", []) if c.get("code")]
        rows.append(
            {
                "idx": i,
                "sent_idx": item.get("sentence_index"),
                "region": geo.get("region"),
                "countries": countries,
                "specificity": geo.get("specificity"),
                "is_union": item.get("is_union"),
                "pct": cov.get("percentage"),
                "cov": cov.get("employee_count_covered"),
                "not_cov": cov.get("employee_count_not_covered"),
                "tot": cov.get("employee_count_total"),
                "type": cov.get("type"),
                "neg": cov.get("negated"),
                "neg_type": cov.get("negation_type"),
                "amb_mult": cov.get("ambiguity_multiplier"),
                "has_exceptions": cov.get("has_exceptions"),
                "is_exception_entry": cov.get("is_exception_entry"),
                "is_exception_remainder": cov.get("is_exception_remainder"),
                "note": cov.get("note"),
            }
        )
    return rows


def run_scenario(analyzer: UnionAnalyzer, scenario: Scenario) -> dict:
    company_cleaner = CompanyCleaner()
    cleaner = MinimalTextCleaner()
    currency_remover = CurrencyRemover()
    contextual_cleaner = ContextualNumberCleaner()
    conciseness_cleaner = ConcisenessCleaner()

    cleaned_text = company_cleaner.clean(scenario.text, scenario.company_name)
    cleaned_text = cleaner.clean(cleaned_text, scenario.company_name)
    cleaned_text = currency_remover.clean(cleaned_text)
    cleaned_text = contextual_cleaner.clean(cleaned_text, home_country=scenario.home_country)
    cleaned_text = conciseness_cleaner.clean(cleaned_text)

    analyzer.domestic_country_code = scenario.home_country or "US"
    result = analyzer.analyze_paragraph(cleaned_text, item_type="item1", reporting_year=2023)
    items = result.get("items", [])
    summary = summarize_items(items)
    return {
        "name": scenario.name,
        "notes": scenario.notes,
        "raw_text": scenario.text,
        "cleaned_text": cleaned_text,
        "item_count": len(items),
        "items": summary,
    }


def main() -> None:
    analyzer = UnionAnalyzer()
    outputs = []

    for sc in SCENARIOS:
        outputs.append(run_scenario(analyzer, sc))

    print(json.dumps(outputs, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
