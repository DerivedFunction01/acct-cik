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
    """On Duke Capital had approximately 11,700 employees.
    A total of 1,998 operating, and maintenance employees were represented by unions. 
    This amount consists of the following:
    
    208 employees represented by the Canadian Pipeline Employees Association
    
    156 employees represented by the International Brotherhood of Electrical Workers
    
    154 employees represented by the United Steelworkers of America
    
    79 employees represented by Sindicato de Trabajadores del Sector Electrico
    
    75 employees represented by the International Union of Operating Engineers
    
    70 employees represented by Sindicato dos Trabalhadores na Industria da Energia Hidroeletrica de Ipaussu
    
    38 employees represented by Sindicato Unico de Centrales de Generacion Electrica-Canon del Pato
    
    29 employees represented by Asociacion del Personal Jerarquico del Agua y la Energia
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
        # summary = analysis_output.get("summary", {})
        report = analysis_output.get("country_report", {})
        risk_summary = analysis_output.get("risk_summary", {})


        # Pretty print results
        print(f"Total Sentences Extracted: {len(results)}\n")
        print(json.dumps(results, indent=2))

        # print("\n" + "=" * 80)
        # print("\nCALCULATED SUMMARY:\n")
        # print(json.dumps(summary, indent=2))

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
