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
ITEM 1. BUSINESS

TechAdvance Manufacturing operates a global business across manufacturing, logistics, and technology. As of December 31, 2023, we employ approximately 150,000 employees worldwide.

UNITED STATES OPERATIONS

Our U.S. operations employ a significant workforce engaged in manufacturing and distribution. 

In our automobile manufacturing division, we employ 14,200 hourly production workers. Of these, 11,644 are represented by the United Auto Workers (UAW) under collective bargaining agreements. This represents 82% unionization in this division.

Our East Coast distribution centers employ logistics personnel who are unionized. We do not disclose the exact headcount at this time due to operational sensitivity.

We employ flight crew personnel under ALPA, all of whom are unionized. However, we have not separately disclosed the number of such employees in recent filings.

Our corporate headquarters employs administrative, sales, and technical staff. A portion of these 50,000 corporate employees remain unionized, though the exact number is not material to our risk profile.

We employ approximately 20,000 warehouse and fulfillment center workers across multiple U.S. locations. Union representation in these facilities varies by location; we monitor labor activity closely but do not separately report unionization rates for this workforce segment.

EUROPEAN OPERATIONS

We maintain operations across Europe, employing approximately 6,000 workers.

In France, we operate a manufacturing facility. French labor law requires substantial employee representation through works councils and collective agreements. We employ approximately 2,500 workers at this location, substantially all of whom participate in mandatory industry-wide bargaining.

In Germany, we operate two principal locations employing 3,500 workers total. Our Hamburg plant employs 2,000 workers with IG Metall membership. Our Munich office employs 1,500 workers subject to German codetermination requirements.

We maintain operations in the United Kingdom. A portion of our U.K. workforce is represented by trade unions, though specific unionization rates are not disclosed.

LATIN AMERICAN OPERATIONS

We employ approximately 3,000 workers across Latin America.

In Mexico, we operate manufacturing facilities. We do not publicly disclose the unionization status of these operations due to local business practices.

In Brazil, we employ approximately 1,200 workers. Our Brazilian operations are subject to annual industry-wide union negotiations, but exact unionization rates remain proprietary.

ASIA-PACIFIC OPERATIONS

We employ approximately 85,000 workers across Asia-Pacific, primarily in technology and manufacturing.

In India, our Bangalore technology hub employs 45,000 software engineers and support staff. We do not currently have union representation at this facility.

In China, we employ 20,000 workers across multiple manufacturing sites. These operations fall under the All-China Federation of Trade Unions (ACFTU) framework as required by law. We maintain zero formal collective bargaining agreements with our Chinese workforce.

In Japan, we employ 12,000 workers. These employees participate in annual Shunto wage negotiations but remain entirely non-unionized in formal terms.

In Southeast Asia (Thailand, Vietnam, Malaysia), we employ approximately 8,000 workers across manufacturing and logistics hubs. Union representation in this region is minimal to non-existent, though we continue to monitor labor developments.

GLOBAL SUMMARY

We do not provide a precise global unionization rate, as certain regional operations do not disclose specific metrics for competitive or operational reasons. We believe our diversified geographic footprint and largely non-unionized workforce provide flexibility for operational efficiency.
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
