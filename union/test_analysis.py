# %%
"""
Comprehensive test paragraph for union extraction with fictional company,
specific reporting year, and mix of simple and complex statements.

Company: TechAdvance Manufacturing Corp (TAMC)
Reporting Year: 2023 (10-K filing dated 2024)
Test Focus: Rigidity - ensure no false claims while handling variations
"""

import json
from extraction import UnionExtractor
from analysis_copy import UnionAnalyzer
from defs.text_cleaner import CurrencyRemover, MinimalTextCleaner, ContextualNumberCleaner, ConcisenessCleaner


ITEM_1 = """
ITEM 1. BUSINESS

TechAdvance Manufacturing Corp and its subsidiaries operate a global manufacturing, logistics, and 
technology services business. As of December 31, 2023, we employ approximately 100,000 employees 
worldwide across North America, Europe, Latin America, and Asia-Pacific regions.

Employees and Labor Relations

We maintain a diverse workforce across multiple operational divisions. As of year-end 2023, our total 
global employee base consisted of approximately 100,000 personnel.

United States Operations. Our domestic operations employ 57,520 workers across 15 manufacturing 
facilities and 30 distribution hubs. Of our 14,200 hourly production workers, 11,644 are represented 
by the United Auto Workers (UAW) under collective bargaining agreements. Additionally, 920 logistics 
personnel in our East Coast distribution centers are fully represented by the International Brotherhood 
of Teamsters. 

Our flight operations employ 500 pilots, all of whom are unionized under the Air Line Pilots Association (ALPA).
We employ 200 senior managers who are not subject to collective bargaining agreements. The remaining 44,256 
U.S. employees, consisting primarily of technical, administrative, and sales personnel, are non-union. 
In 2023, we reduced U.S. headcount by 1,500 positions through operational efficiency initiatives, 
which contributed to a 3% decline in overall union density within the United States.

European Operations. We employ 7,100 workers across Europe. In France, we operate facilities with 3,000 
employees who are substantially all covered by industry-wide collective bargaining agreements and represented 
through the Comité Social et Économique, a mandatory French employee representation structure. In Germany, 
we employ 4,100 workers across two principal locations. Our Hamburg manufacturing facility employs 2,600 workers, 
of whom 95%, or approximately 2,470 employees, maintain membership in IG Metall. Our Munich administrative center
employs 1,500 workers and operates under German Works Council (Betriebsrat) provisions, which provide for 
employee consultation and co-determination rights, though we maintain no formal union contract at this location.

Latin American Operations. We employ 2,900 workers in Latin America. In Mexico, our manufacturing operations 
in Monterrey employ 1,800 workers. Approximately 270 employees, or 15% of our Mexican workforce, are 
represented under a collective bargaining agreement with the Sindicato de Trabajadores Mineros Unidos. 
In Brazil, our operations employ 1,100 workers. While subject to annual industry-wide union negotiations 
and wage setting mechanisms, formal union membership among our Brazilian workforce remains limited.

Asia-Pacific Operations. We employ 33,200 workers across Asia-Pacific. In Japan, we employ 3,200 workers 
who participate in the annual Shunto wage negotiation process; however, these employees remain entirely
non-union. In China, we employ 10,000 workers across multiple manufacturing sites. Our Chinese operations 
operate within the All-China Federation of Trade Unions (ACFTU) framework as required by applicable law. 
However, we report zero formal collective bargaining representation for our Chinese workforce. 

In India, our technology hub in Bangalore employs 20,000 software engineers and technical support 
personnel, none of whom are currently unionized.

Summary. Worldwide, as of December 31, 2023, our unionized workforce totaled approximately 
18,800 employees, representing approximately 19% of our total global workforce. This represented a 
modest decline from prior year due to operational changes and divestitures.
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

"""

## Breakdown of True Unionization Rate

**Covered (Unionized) Employees:**
- UAW (U.S. manufacturing): 11,644
- Teamsters (U.S. logistics): 920
- ALPA (U.S. pilots): 500
- France (Comité Social): 3,000
- Germany/IG Metall (Hamburg): 2,470
- Mexico (Sindicato): 270
- **Total covered: 18,804**

**Not Covered (Non-Union) Employees:**
- U.S. non-union: 44,256
- U.S. senior managers: 200
- Germany/Works Council only (Munich): 1,500
- Japan (Shunto, non-union): 3,200
- China (ACFTU, zero formal bargaining): 10,000
- India (non-unionized): 20,000
- Brazil (low formal membership): 1,100
- **Total not covered: 80,256**

**Global Workforce Total: 99,060**

**Global Unionization Rate: 18,804 ÷ 99,060 = 18.98% ≈ 19%**

**By Region:**
- **U.S.**: 13,064 / 57,520 = 22.7%
- **Europe**: 5,470 / 7,100 = 77.0%
- **Latin America**: 270 / 2,900 = 9.3%
- **Asia-Pacific**: 0 / 33,200 = 0.0%
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
