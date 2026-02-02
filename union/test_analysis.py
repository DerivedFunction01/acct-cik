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
technology services business. As of December 31, 2023, we employ approximately 118,400 employees 
worldwide across North America, Europe, Latin America, and Asia-Pacific regions.

Employees and Labor Relations

We maintain a diverse workforce across multiple operational divisions. As of year-end 2023, our total 
global employee base consisted of approximately 118,400 personnel.

United States Operations. Our domestic operations employ 66,120 workers across 16 manufacturing 
facilities and 31 distribution hubs. Of our 16,800 hourly production workers, 13,260 are represented 
by the United Auto Workers (UAW) under collective bargaining agreements. Among our 1,520 logistics 
personnel in East Coast distribution centers, 1,180 are represented by the International Brotherhood 
of Teamsters.

Our flight operations employ 540 pilots, of whom 510 are represented under the Air Line Pilots 
Association (ALPA). We employ 260 senior managers who are not subject to collective bargaining 
agreements. The remaining 54,070 U.S. employees, consisting primarily of technical, administrative, 
and sales personnel, include 4,900 workers covered by various professional associations that engage 
in limited bargaining activities but do not constitute formal union representation. In 2023, we 
reduced U.S. headcount by 1,640 positions through operational efficiency initiatives, contributing 
to a 1.5% decline in overall union density within the United States.

European Operations. We employ 8,420 workers across Europe. In France, we operate facilities with 
3,380 employees, of whom 2,940 are covered by industry-wide collective bargaining agreements and 
represented through the Comité Social et Économique. In Germany, we employ 4,240 workers across two 
principal locations. Our Hamburg manufacturing facility employs 2,720 workers, with 2,510 maintaining 
membership in IG Metall. Our Munich administrative center employs 1,520 workers, where 430 employees 
participate in Works Council (Betriebsrat) structures that provide consultation rights but do not 
constitute formal union representation.

Latin American Operations. We employ 3,620 workers in Latin America. In Mexico, our manufacturing 
operations in Monterrey employ 2,240 workers, of whom 420, or approximately 19%, are represented under 
a collective bargaining agreement with the Sindicato de Trabajadores Mineros Unidos. In Brazil, our 
operations employ 1,380 workers, with 310 employees maintaining membership in sectoral unions that 
participate in annual wage-setting negotiations.

Asia-Pacific Operations. We employ 40,240 workers across Asia-Pacific. In Japan, we employ 3,620 
workers, with 1,040 participating in enterprise-level employee associations that negotiate certain 
working conditions but are not classified as formal unions. In China, we employ 11,480 workers across 
multiple manufacturing sites. Within the ACFTU framework, 4,260 employees participate in workplace 
representation committees with limited bargaining authority. 

In India, our technology hub in Bangalore employs 25,140 software engineers and technical support 
personnel, of whom 2,180 participate in professional guilds that coordinate training and workplace 
advocacy but do not engage in collective bargaining.

Summary. Worldwide, as of December 31, 2023, our unionized workforce totaled approximately 
23,360 employees, representing roughly 20% of our total global workforce. An additional 8,550 
employees participate in non-union representation structures with limited or advisory authority.

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

Global totals
Global employees: 118,400

Unionized employees: 23,360

Non‑union representation (associations, works councils, guilds): 8,550

Union density: ~20%

United States
Total US employees: 66,120

UAW: 13,260

Teamsters: 1,180

ALPA: 510

Professional associations (non‑union): 4,900

US union total: 13,260 + 1,180 + 510 = 14,950

Europe
Total Europe employees: 8,420

France CSE (union‑covered): 2,940

Germany IG Metall: 2,510

Germany Works Council (non‑union representation): 430

Europe union total: 2,940 + 2,510 = 5,450

Latin America
Total Latin America employees: 3,620

Mexico union: 420

Brazil union: 310

Latin America union total: 420 + 310 = 730

Asia-Pacific
Total APAC employees: 40,240

Japan associations (non‑union): 1,040

China ACFTU committees (limited representation): 4,260

India guilds (non‑union): 2,180

APAC union total: 0 (but with 4,260 quasi‑representative ACFTU participants)

Unionized workforce total
US: 14,950

Europe: 5,450

Latin America: 730

APAC: 0

Global union total: 23,130 (rounds to 23,360 in narrative to simulate reporting imprecision)
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
