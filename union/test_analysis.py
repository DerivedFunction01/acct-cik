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
The Company offers fair terms and conditions of employment. The Company's overall purpose, Code of Conduct, talent development strategies, and employment policies support the principles in the United Nations Universal Declaration of Human Rights, and the International Labor Organization’s Fundamental Principles and Labor Standards.

The Company considers its relationship with its employees to be good. While there have been a small number of minor labor disputes historically, such disputes have not had a significant or lasting impact on the Company's relationship with its employees, and customer perception of its employee practices or its business results. 

Major unions in Europe to which some of the Company's employees belong include: IG Metall in Germany; Unite the union in the United Kingdom; Confédération Générale des Travailleurs (CGT), Confédération Française Démocratique du Travail (CFDT), Confédération Française de l’Encadrement Confédération Générale des cadres (CFE-CGC), Force Ouvrière (FO), Confédération Française des Travailleurs Chrétiens (CFTC), Solidaires, Unitaires, Démocratiques (SUD) and Conféderation Autonome du Travail (CAT) in France; Union General de Trabajadores (UGT), Union Sindical Obrera (USO), Comisiones Obereras (CCOO) and Confederacion General de Trabajadores (CGT) in Spain; IF Metall, Unionen, Sveriges Ingenjörer and Ledarna in Sweden; Industriaal- ja Metallitöötajate Ametiühingute Liit (IMTAL) in Estonia; Vasas Szakszervezeti Szövetség (Hungarian Metallworkers‘ Federation) in Hungary; Samorzadny NiezalezĪny Zwiazek Zawodowy Pracownikow and Zakladowa Organizacja Związkowa NSZZ Solidarnosc in Poland; National Union of Metal Workers South Africa (NUMSA) in South Africa; Union Générale des Travailleurs Tunisiens (UGTT) and Union des travailleurs Tunisiens (UTT) in Tunisia, and Türk Metal Sendikasi in Turkey. 

In addition, the Company’s employees in other regions are represented by the following unions: Unifor in Canada; Sindicato de Jornaleros y Obreros Industriales y de la Industria Maquiladora de H.Matamoros, Tamaulipas (CTM); Sindicato Nacional de Trabajadores de la Industria Metalúrgica y Similares, Federación Valle de Toluca (CTM); Sindicato Nacional “Nueva Cultura Laboral” de trabajadores de la fabricación, manufactura, ensamble de autopartes mecánicas y eléctricas y componentes de la Industria Automotriz, C.R.O.C.; Sindicato Nacional de Trabajadores de la Industria Arnesera, Eléctrica, Automotriz y Aeronáutica de la República Mexicana; “Nueva Cultura Laboral” “de trabajadores de la fabricación, manufactura, ensamble de autopartes mecánicas y eléctricas y componentes de la industria Automotriz (CROC); Sindicato Nacional de Trabajadores de la Industria de Autopartes en General y/o Similares, Conexos y sus Servicios de la República Mexicana, in Mexico; Sindicato Industrial de Trabajadores de la Transformación, Construcción, Automotriz, Agropecuaria, Plásticos y de la Industria en General, del Comercio y Servicios, Similares, anexos y conexos del Estado de Querétaro “Ángel Castillo Resendiz”; Sindicato dos Metalúrgicos de Taubaté e Região in Brazil; Autoliv India Employees Association, Bangalore & Mysore in India; Korean Metal Workers Union (FKTU) in South Korea; Autoliv Japan Roudou Kumiai in Japan, and All-China Federation of Trade Unions in China. 

In many European countries, Canada, Mexico, Brazil and South Korea, wages, salaries and general working conditions are negotiated with local unions and/or are subject to centrally negotiated collective bargaining agreements. The terms of the Company's various agreements with unions typically range between one to three years. Some of the Company's subsidiaries in Europe, Canada, Mexico, Brazil and South Korea must negotiate with the applicable local unions with respect to important changes in operations, working and employment conditions. Twice a year, members of the Company’s management conduct a meeting with the European Works Council (EWC) to provide employee representatives with important information about the Company and a forum for the exchange of ideas and opinions. In many Asia Pacific countries, the central or regional governments provide guidance each year for salary adjustments or statutory minimum wage for workers. The Company's employees may join associations in accordance with local legislation and rules, although the level of unionization varies significantly throughout its operations.
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
