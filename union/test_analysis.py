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
TechAdvance Manufacturing operates a diverse global workforce across 
manufacturing, logistics, and technology divisions. As of the end of 2023, 
our total employee base reached approximately 38,500 across all regions.

In our United States operations, which employ 16,800 workers, approximately 22% 
(3,696 employees) are represented by labor unions. Our largest unionized segment 
comprises 2,100 production workers in our Ohio and Indiana facilities, organized 
under the United Auto Workers (UAW) agreement that became effective in 2022. 
Additionally, our West Coast logistics centers employ 1,596 workers represented 
by the International Brotherhood of Teamsters, covering 100% of those facilities.

Our non-union domestic workforce of 13,104 employees consists primarily of 
engineering, administrative, and management personnel at our headquarters in 
Dallas, Texas, where 4,200 of 5,100 corporate staff operate outside union 
frameworks. The remaining non-union workers are distributed across regional 
sales offices and smaller manufacturing sites. We maintain a neutral stance 
toward unionization efforts and do not actively oppose employee organizing.

In Canada, we employ 2,400 workers across three locations: Toronto, Vancouver, 
and Calgary. The Toronto facility (1,100 workers) is 65% unionized under Unifor 
representation (715 workers), while Vancouver (800 workers) and Calgary (500 workers) 
remain entirely non-union. We anticipate potential organizing activity in Vancouver 
during 2024 but expect no material change to current representation levels.

Our European operations, which employed 8,900 workers at year-end 2023, present 
a more complex landscape. In Germany, we operated two manufacturing plants employing 
3,100 workers total: the Düsseldorf facility (1,800 workers) with 68% IG Metall 
representation (1,224 workers), and the Stuttgart facility (1,300 workers) with 
no formal union representation but subject to German Works Council requirements. 
France is home to our second-largest European facility with 2,400 employees in 
the Paris region; approximately 45% are represented by unions (CFDT, CGT, and FO 
combined), equaling roughly 1,080 workers. The Netherlands facility in Rotterdam 
employs 1,600 workers, of which only 15% (240 workers) maintain union membership 
under the FNV. Our smaller UK operations in Liverpool employ 800 workers with 
minimal union presence at approximately 8% (64 workers) under Unite the Union.

We maintain generally constructive relationships with our European union partners, 
though relations with the German works councils can be technically complex. Our 
French operations have experienced no significant labor disputes in the past three years.

In Asia-Pacific, our footprint is growing but remains under-unionized. Japan 
represents our largest regional presence with 6,200 employees: 4,100 in our Tokyo 
automotive component facility and 2,100 in our Osaka electronics manufacturing. 
The Tokyo facility is 35% unionized (1,435 workers) under the Japanese Association 
of Metal and Allied Workers (JAM), while Osaka is entirely non-union. India is our 
emerging market with 3,400 software engineers at our Bangalore campus; none are 
currently unionized, though we monitor labor developments given local organizing trends. 
Thailand's small facility employs 420 workers entirely outside union frameworks. Australia 
and New Zealand operations employ 850 workers combined, with no formal union representation.

Our Chinese operations, while currently non-unionized with 2,800 workers across Shanghai 
and Shenzhen facilities, present potential future exposure. We note that all Chinese facilities 
operate under the all-China Federation of Trade Unions framework as required by law; however, 
we currently report zero formal representation of our workforce. We plan to increase hiring 
in China by 40% through 2025, which could result in additional union exposure.

In Latin America, we maintain minimal operations: Mexico (1,200 workers at Monterrey plant) 
is 25% unionized (300 workers) under CTM, while our presence in Brazil (280 workers, 
São Paulo) and Colombia (180 workers) remains non-union. We do not anticipate union 
organizing activity in these regions in the near term.

Middle East and Africa operations are limited. Our UAE facility (Dubai, 320 workers) is 
entirely non-union as required by local law. We have no current operations in other 
African markets, having divested our South African subsidiary in 2019.

Overall, our global unionization rate stands at approximately 24% of our total workforce. 
We believe our labor relations profile is stable, with no significant pending negotiations 
or anticipated labor disputes. We remain committed to fair labor practices and transparent 
engagement with employee representative bodies.
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

ITEM_COMBINED = """
ITEM 1. BUSINESS

We have 10,000 employees in the Asia‑Pacific region, of which 6,000 are in China and 2,000 are in India, 
with the remaining in Japan and the Philippines. Our Central American workforce consists of 2,000 employees in 
Costa Rica and Guatemala, and 4,000 in Panama. We employ approximately 8,000 workers in Atlantic financial jurisdictions, 
including 5,000 in Bermuda and 2,000 in the Cayman Islands, with the remaining in the British Virgin Islands. Our workforce 
includes 500 employees in Canada, compared to 1,000 in the United Kingdom and 200 in South Korea. In Southeast Asia, 
we have 900 employees located in Vietnam, Thailand, and Malaysia. We have 5,000 employees in Mainland Europe, 
consisting of 3,000 in Germany, Italy, and Sweden, and 2,000 in France. We have an additional 5,000 employees in Eastern Europe, 
consisting of 2,000 in Romania and Bulgaria, with the remaining in Slovakia. We also maintain 7,500 employees in the
Extended Asia region, of which 3,000 are in Mongolia and 1,500 in Laos, with the remaining in Timor‑Leste and Brunei. 
Our Caribbean and Lesser Antilles division includes 3,500 employees, with 1,200 in Saint Lucia, 1,000 in Dominica, and 
the remaining in Grenada. In the Nordic Microstates cluster, we employ 1,100 workers, including 400 in Iceland, 300 in 
the Faroe Islands. Our European Micro‑Territories group consists of 2,400 employees, with 1,000 
in Luxembourg, 800 in Andorra, and the remaining in Liechtenstein. Finally, we have 4,200 employees in the Balkan 
Extended Region, of which 1,800 are in Moldova and 1,200 in North Macedonia, with the remaining in Kosovo. We also have 
5,000 employees across Belgium, Austria, and Portugal. Our Nordic operations employ 2,000 people in Norway, Denmark,
Finland, and Estonia. In South America, we have 1,500 workers in Chile and Peru, and 800 in Suriname and Bolivia. 
We employ 10,000 staff in Taiwan, Singapore, and Hong Kong. Our workforce includes 4,000 employees in Ireland, Netherlands, 
and Switzerland. We have 3,000 employees in Poland and Czech Republic, and 2,000 in Hungary and Ukraine. In North America, we have 15,000 employees in 
the United States, Mexico, and Puerto Rico. Our Southeast Asia division has 2,500 workers in Cambodia, Myanmar, 
Indonesia, and the Maldives. We employ 1,200 people in Australia and New Zealand. In the Middle East, we have 900 employees in 
UAE, Saudi Arabia, and Qatar. We also maintain 3,000 employees in Israel, Jordan, and Oman. In Sub‑Saharan Africa, we have 2,200 
employees in Kenya, Ghana, and Tanzania.
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

    # Combined Consistency Test
    print("\n" + "=" * 80)
    print("Testing Combined Consistency Case\n")
    cleaned_combined = cleaner.clean(ITEM_COMBINED)
    cleaned_combined = currency_remover.clean(cleaned_combined)
    cleaned_combined = contextual_cleaner.clean(cleaned_combined)
    cleaned_combined = conciseness_cleaner.clean(cleaned_combined)
    
    print("Cleaned Text:\n")
    print(cleaned_combined)
    print("-" * 40)
    analyzer.domestic_country_code = "CN"
    analysis_output_combined = analyzer.analyze_paragraph(
        cleaned_combined, item_type="item1", reporting_year=reporting_year
    )
    
    for item in analysis_output_combined.get("items", []):
        print(item["sentence"])
        print(item.get("census_note") or item.get("note"))
        print()

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
