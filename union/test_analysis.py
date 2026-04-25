# %%
"""
Comprehensive test paragraph for union extraction with fictional company,
specific reporting year, and mix of simple and complex statements.

Company: TechAdvance Manufacturing Corp (TAMC)
Reporting Year: 2023 (10-K filing dated 2024)
Test Focus: Rigidity - ensure no false claims while handling variations
"""

import json
from analysis import UnionAnalyzer
from defs.text_cleaner import CompanyCleaner, CurrencyRemover, MinimalTextCleaner, ContextualNumberCleaner, ConcisenessCleaner


ITEM_1 = [
    """The Harbin Municipal Government promulgated regulations that were effective <1994>, which provide for the establishment of a pension fund program to which both employer and employee must contribute. Harbin Bearing is required to contribute a monthly amount equivalent to 20% of its employees' aggregate monthly income, and each employee is required to contribute a monthly amount that is equivalent to 2% of such employees' monthly income.

The employees of Harbin Bearing are members of a trade union. 
Labour contract covering the recruitment, employment, dismissal and resignation, wages, labour insurance, welfare, rewards, penalty and other matters concerning the staff and workers of the joint venture company shall be drawn up between the joint venture company and the Trade Union of the joint venture company as a whole or individual employees in accordance with the "Regulations of the People's Republic of China on Labour Management in Joint Ventures Using Chinese and Foreign Investment" and its implementation rules.

The labour contracts shall, after being signed, be filed with the local labour management department
""",
]


if __name__ == "__main__":
    # Test setup
    analyzer = UnionAnalyzer()
    cleaner = MinimalTextCleaner()
    currency_remover = CurrencyRemover()
    contextual_cleaner = ContextualNumberCleaner()
    conciseness_cleaner = ConcisenessCleaner()
    company_cleaner = CompanyCleaner()

    # Reporting year context
    reporting_year = 1995
    company_name = "TechAdvance Manufacturing Corp LTD."

    for item in ITEM_1[0:]:
        # Clean the text
        cleaned_text = company_cleaner.clean(item, company_name)
        cleaned_text = cleaner.clean(cleaned_text, company_name)
        cleaned_text = currency_remover.clean(cleaned_text)
        cleaned_text = contextual_cleaner.clean(cleaned_text)
        cleaned_text = conciseness_cleaner.clean(cleaned_text)
        print("="* 80)
        print("Cleaned Text:\n")
        print(cleaned_text)
        print("\n" + "=" * 80)

        # Analyze with context
        analysis_output = analyzer.analyze_paragraph(
            cleaned_text, item_type="item1", reporting_year=reporting_year
        )

        results = analysis_output.get("items", [])
        summary = analysis_output.get("summary", {})
        report = analysis_output.get("country_report", {})
        risk_summary = analysis_output.get("risk_summary", {})


        # Pretty print results
        print(f"Total Sentences Extracted: {len(results)}\n")
        print(json.dumps(results, indent=2))

        # print("\n" + "=" * 80)
        print("\nCALCULATED SUMMARY:\n")
        print(json.dumps(summary, indent=2))

        print("\n" + "=" * 80)
        print("\nCOUNTRY REPORT:\n")
        print(json.dumps(report, indent=2))

        print("\n" + "=" * 80)
        print("\nRISK SUMMARY:\n")
        print(json.dumps(risk_summary, indent=2))

    # # Combined Consistency Test
    # print("\n" + "=" * 80)
    # print("Testing Combined Consistency Case\n")
    # cleaned_combined = cleaner.clean(ITEM_COMBINED)
    # cleaned_combined = currency_remover.clean(cleaned_combined)
    # cleaned_combined = contextual_cleaner.clean(cleaned_combined)
    # cleaned_combined = conciseness_cleaner.clean(cleaned_combined)

    # print("Cleaned Text:\n")
    # print(cleaned_combined)
    # print("-" * 40)
    # analyzer.domestic_country_code = "CN"
    # analysis_output_combined = analyzer.analyze_paragraph(
    #     cleaned_combined, item_type="item1", reporting_year=reporting_year
    # )

    # for item in analysis_output_combined.get("items", []):
    #     print(item["sentence"])
    #     print(item.get("census_note") or item.get("note"))
    #     print()

    # Item 1A
    # print("="* 80)
    # print("Cleaned Text (Item 1A):\n")
    # print(cleaned_text)
    # print("\n" + "=" * 80)

    # analysis_output_1a = analyzer.analyze_paragraph(
    #     cleaned_text, item_type="item1a", reporting_year=reporting_year
    # )

    # results_1a = analysis_output_1a.get("items", [])

    # print(f"Total Risk Factors Extracted: {len(results_1a)}\n")
    # print(json.dumps(results_1a, indent=2))

# %%
