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
from defs.text_cleaner import CurrencyRemover, MinimalTextCleaner, ContextualNumberCleaner, ConcisenessCleaner


ITEM_1 = """
The Company has 850 full-time and three part-time employees. The facility in Pennsylvania are unionized except for sales personnel. None of our other employees are subject to collective bargaining. Approximately 266 employees were represented by international or independent labor unions.

"""

ITEM_1A = """

ITEM 1A. RISK FACTORS

The following risk factors may materially affect our business, financial condition, or results of operations.

Labor Relations and Unionization Risks

Our business is subject to labor relations risks, particularly in jurisdictions where our workforce 
is unionized or subject to collective bargaining arrangements.

United States Labor Relations Risk. In the United States, approximately 13,100 employees, or 23% of 
our domestic workforce, are covered by collective bargaining agreements. While our historical relationship 
with the United Auto Workers has been stable, we face ongoing risks related to wage, benefit, and cost 
structure negotiations in future contract renewals. The airline industry, represented by our ALPA-represented 
pilots, faces inherent labor-cost volatility. Any material increase in wages or benefits, or failure to 
reach agreement in future contract negotiations, could adversely affect our operational costs and financial performance.

European Labor Relations Risk. In Europe, we face heightened labor relations risks due to mandatory employee 
representation structures and industry-wide bargaining frameworks. In France, our workforce is substantially
covered by national and industry-wide collective bargaining agreements that may impose wage and benefit floors 
that increase our operating costs. In Germany, our operations are subject to codetermination requirements 
through Works Councils and IG Metall union representation, which provide employees with significant consultation 
and dispute resolution rights. Changes in German labor law or IG Metall contract terms could materially impact 
our manufacturing costs in that region. We cannot guarantee that future labor negotiations in Europe will 
be resolved on terms favorable to us.

Latin American Labor Relations Risk. In Mexico, we are currently engaged in contract renewal negotiations with 
the Sindicato de Trabajadores Mineros Unidos regarding our Monterrey facility. Additionally, we are monitoring 
labor organizing activity and potential work stoppage risk by Gremios de Transportistas (transportation workers' unions) 
in our distribution operations, which could disrupt logistics and supply chain operations if labor actions occur. In Brazil, 
while formal unionization remains low, we continue to participate in mandated annual wage and benefits negotiations, 
which could result in increased labor costs industry-wide.

Emerging Market Labor Risk. In Asia-Pacific, while our Japanese, Chinese, and Indian operations currently remain 
largely non-unionized, we face risks related to emerging labor organization campaigns and changing labor laws in 
these regions. In China, although our workforce operates under ACFTU auspices with zero formal collective bargaining, 
we face regulatory and reputational risks if labor conditions or local labor disputes arise. In India, our large technology 
workforce remains non-unionized, but rapid labor market tightening could increase unionization risk in future periods. We 
monitor regional labor trends in Asia-Pacific closely and anticipate no material near-term organizing activity, though 
this cannot be assured.

Labor Cost Inflation. Across all regions, we face risks related to labor cost inflation, including wage pressures, 
benefits inflation, and potential unfunded pension liabilities in jurisdictions with defined benefit obligations. 
Unionized workforces, particularly in Europe and North America, may demand wage increases that exceed inflation 
or productivity gains, which could adversely affect our competitiveness.

Supply Chain and Third-Party Labor Risk. Our supply chain and logistics operations are exposed to labor actions by 
our unionized employees (Teamsters) and potential labor campaigns by external transportation and logistics unions in
markets where we operate. Any work stoppage or disruption in our distribution network could delay customer deliveries
and damage customer relationships.

Regulatory and Reputational Risk. Labor relations disputes, labor law changes, or adverse publicity regarding labor
conditions could result in regulatory investigations, fines, or reputational harm that affects our ability to 
attract talent and maintain customer relationships, particularly among customers with corporate social responsibility requirements.

"""


if __name__ == "__main__":
    # Test setup
    analyzer = UnionAnalyzer()
    cleaner = MinimalTextCleaner()
    currency_remover = CurrencyRemover()
    contextual_cleaner = ContextualNumberCleaner()
    conciseness_cleaner = ConcisenessCleaner()

    # Reporting year context
    reporting_year = 2023
    company_name = "TechAdvance Manufacturing Corp LTD."

    print(f"Testing {company_name} Fictional 10-K Filing (Reporting Year: {reporting_year})\n")
    print("=" * 80)
    print()

    # Clean the text
    cleaned_text = cleaner.clean(ITEM_1)
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

    # Pretty print results
    print(f"Total Sentences Extracted: {len(results)}\n")
    print(json.dumps(results, indent=2))

    print("\n" + "=" * 80)
    print("\nCALCULATED SUMMARY:\n")
    print(json.dumps(summary, indent=2))

    # Summary statistics
    print("\n" + "=" * 80)
    print("\nSUMMARY STATISTICS:\n")

    total_with_percentage = len(
        [r for r in results if r.get("coverage_data", {}).get("percentage")]
    )
    total_with_counts = len(
        [r for r in results if r.get("coverage_data", {}).get("employee_count_covered")]
    )
    negated_items = len(
        [r for r in results if r.get("coverage_data", {}).get("negated")]
    )
    inherited_geo = len(
        [
            r
            for r in results
            if r.get("geographic_context", {}).get("specificity") == "INHERITED_PREV"
        ]
    )

    print(f"Sentences with explicit/calculated percentage: {total_with_percentage}")
    print(f"Sentences with employee counts: {total_with_counts}")
    print(f"Negated coverage statements: {negated_items}")
    print(f"Inherited geographic context: {inherited_geo}")

    # Item 1A
    cleaned_text = cleaner.clean(ITEM_1A)
    cleaned_text = currency_remover.clean(cleaned_text)
    cleaned_text = contextual_cleaner.clean(cleaned_text)
    cleaned_text = conciseness_cleaner.clean(cleaned_text)

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
