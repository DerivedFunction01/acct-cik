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
    """
TechAdvance Manufacturing operates a diverse global workforce across 
manufacturing, logistics, and technology divisions. As of the end of 2023, 
our total employee base reached approximately 44,000 across all regions.

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
""",
    """ITEM 1. BUSINESS

TechAdvance Manufacturing operates a global business across manufacturing, logistics, and technology. As of December 31, 2023, we employ approximately 200,000 employees worldwide, compared to 250,000 in 2022. Of our workforce, less than 1% are Traditionalists (born before 1928), 12% are Baby Boomers (born 1928-1945), 37% are Generation X (born 1965-1980), 42% are Millennials (born 1981-1996) and less than 9% are Generation Z (born after 1997). 

UNITED STATES OPERATIONS

Our U.S. operations employ a significant workforce engaged in manufacturing and distribution. 

In our automobile manufacturing division, we employ 14,200 hourly production workers, of which 4,000 are women, some working at Auto Trust 2023-1. Of these, 11,644 are represented by the United Auto Workers (UAW) under 10-year collective bargaining agreements at 50 per hour.

Our East Coast distribution centers employ logistics personnel who are unionized and covered by 15 independent labor unions. We do not disclose the exact headcount at this time due to operational sensitivity.

We also have several instructors who are members of Local 140 of the International Union of Instructors.

Under 15 labor contracts, we employ flight crew personnel under ALPA, all of whom are unionized. However, we have not separately disclosed the number of such employees in recent filings.

Our corporate headquarters employs 50,000 administrative, sales, and technical staff. A portion of these corporate employees at Captial One remain unionized, though the exact number is not material to our risk profile.

We employ approximately 20,000 warehouse and fulfillment center workers across multiple U.S. locations. At 7 Eleven, Take Two, 3M, and Six Flags, Union representation in these facilities varies by location; we monitor labor activity closely but do not separately report unionization rates for this workforce segment.

Finally, we may also hire contractors: 10 7 Eleven employees, 20 Six Flags workers, and 15 others.

In Canada, we work closely with Union Texas employees on extraction operations, and maintain service agreements with Brooklyn Union and Atlantic Union for utility and financial services respectively.

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

In India, our Bangalore technology hub employs 45,000 software engineers and support staff. None of our employees have union representation at this facility.

In China, we employ 20,000 workers across multiple manufacturing sites. All of these operations fall under the All-China Federation of Trade Unions (ACFTU) framework as required by law. We maintain zero formal collective bargaining agreements with our Chinese workforce.

In Japan, we employ 12,000 workers. These employees participate in annual Shunto wage negotiations but remain entirely non-unionized in formal terms.

In Southeast Asia (Thailand, Vietnam, Malaysia), we employ approximately 8,000 workers across manufacturing and logistics hubs. Union representation in this region is minimal to non-existent, though we continue to monitor labor developments.

GLOBAL SUMMARY

We do not provide a precise global unionization rate, as certain regional operations do not disclose specific metrics for competitive or operational reasons. We believe our diversified geographic footprint and largely non-unionized workforce provide flexibility for operational efficiency.""",
    """
The Company offers fair terms and conditions of employment. The Company's overall purpose, Code of Conduct, talent development strategies, and employment policies support the principles in the United Nations Universal Declaration of Human Rights, and the International Labor Organization’s Fundamental Principles and Labor Standards.

The Company considers its relationship with its employees to be good. While there have been a small number of minor labor disputes historically, such disputes have not had a significant or lasting impact on the Company's relationship with its employees, and customer perception of its employee practices or its business results. 

Major unions in Europe to which some of the Company's employees belong include: IG Metall in Germany; Unite the union in the United Kingdom; Confédération Générale des Travailleurs (CGT), Confédération Française Démocratique du Travail (CFDT), Confédération Française de l’Encadrement Confédération Générale des cadres (CFE-CGC), Force Ouvrière (FO), Confédération Française des Travailleurs Chrétiens (CFTC), Solidaires, Unitaires, Démocratiques (SUD) and Conféderation Autonome du Travail (CAT) in France; Union General de Trabajadores (UGT), Union Sindical Obrera (USO), Comisiones Obereras (CCOO) and Confederacion General de Trabajadores (CGT) in Spain; IF Metall, Unionen, Sveriges Ingenjörer and Ledarna in Sweden; Industriaal- ja Metallitöötajate Ametiühingute Liit (IMTAL) in Estonia; Vasas Szakszervezeti Szövetség (Hungarian Metallworkers‘ Federation) in Hungary; Samorzadny NiezalezĪny Zwiazek Zawodowy Pracownikow and Zakladowa Organizacja Związkowa NSZZ Solidarnosc in Poland; National Union of Metal Workers South Africa (NUMSA) in South Africa; Union Générale des Travailleurs Tunisiens (UGTT) and Union des travailleurs Tunisiens (UTT) in Tunisia, and Türk Metal Sendikasi in Turkey. 

In addition, the Company’s employees in other regions are represented by the following unions: Unifor in Canada; Sindicato de Jornaleros y Obreros Industriales y de la Industria Maquiladora de H.Matamoros, Tamaulipas (CTM); Sindicato Nacional de Trabajadores de la Industria Metalúrgica y Similares, Federación Valle de Toluca (CTM); Sindicato Nacional “Nueva Cultura Laboral” de trabajadores de la fabricación, manufactura, ensamble de autopartes mecánicas y eléctricas y componentes de la Industria Automotriz, C.R.O.C.; Sindicato Nacional de Trabajadores de la Industria Arnesera, Eléctrica, Automotriz y Aeronáutica de la República Mexicana; “Nueva Cultura Laboral” “de trabajadores de la fabricación, manufactura, ensamble de autopartes mecánicas y eléctricas y componentes de la industria Automotriz (CROC); Sindicato Nacional de Trabajadores de la Industria de Autopartes en General y/o Similares, Conexos y sus Servicios de la República Mexicana, in Mexico; Sindicato Industrial de Trabajadores de la Transformación, Construcción, Automotriz, Agropecuaria, Plásticos y de la Industria en General, del Comercio y Servicios, Similares, anexos y conexos del Estado de Querétaro “Ángel Castillo Resendiz”; Sindicato dos Metalúrgicos de Taubaté e Região in Brazil; Autoliv India Employees Association, Bangalore & Mysore in India; Korean Metal Workers Union (FKTU) in South Korea; Autoliv Japan Roudou Kumiai in Japan, and All-China Federation of Trade Unions in China. 

In many European countries, Canada, Mexico, Brazil and South Korea, wages, salaries and general working conditions are negotiated with local unions and/or are subject to centrally negotiated collective bargaining agreements. The terms of the Company's various agreements with unions typically range between one to three years. Some of the Company's subsidiaries in Europe, Canada, Mexico, Brazil and South Korea must negotiate with the applicable local unions with respect to important changes in operations, working and employment conditions. Twice a year, members of the Company’s management conduct a meeting with the European Works Council (EWC) to provide employee representatives with important information about the Company and a forum for the exchange of ideas and opinions. In many Asia Pacific countries, the central or regional governments provide guidance each year for salary adjustments or statutory minimum wage for workers. The Company's employees may join associations in accordance with local legislation and rules, although the level of unionization varies significantly throughout its operations.
""",
"""On a worldwide basis, we believe that our employee and labor relations are excellent.

On a corporate level, all employees of SAP in the member states of the European Union (with the United Kingdom included for a 
transition period until May 2024) and in the contract states of the European Economic Area are represented by the SAP SE Works 
Council (WoC) (Europe). By law and agreement with SAP, the SAP SE WoC (Europe) is entitled to receive information on certain 
transnational matters and to consult with the Executive Board or a representative thereof. On the legal entity level, the SAP 
SE works council (Germany) represents the employees of SAP SE. The employees of SAP Deutschland SE & Co. KG (SAP Germany), 
Concur (Germany) GmbH, and Emarsys Interactive Services GmbH (Germany) are represented by separate works councils. 
Other employee representatives include the group works council (composed of members of the works councils of SAP SE, SAP Germany, 
Concur (Germany) GmbH and Emarsys Interactive Services GmbH (Germany)), the representatives of severely disabled persons in 
SAP SE and SAP Germany and the spokespersons committee as the representation of the executives of SAP SE (Germany).

Employees of each of SAP France, SAP France Holding, SAP Labs France and Concur (France) SAS are subject to the 
same collective agreement: “SYNTEC”. In France, effective December 31, 2024 the Workers Council, the Health and Safety 
Committee and the employee representative were replaced by a single instance named the “Economic and Social Committee”. 
Today, SAP France/SAP France Holding (in the same legal entity), SAP Labs France and Concur (France) SAS are represented 
by an Economic and Social Committee. The represented unions negotiate agreements with each of SAP France/SAP France Holding 
and SAP Labs France. For Concur (France) SAS the agreements are negotiated with the Economic and Social Committee. In addition, 
the employees of various other SAP entities, including SAP Österreich GmbH (Austria), SAP España – Sistemas, Aplicaciones y Productos 
en la Informática, S.A., SAO D.O.O. (Croatia), SAP Belgium NV/SA., SAP Israel, SAP Nederland B.V., SAP Italia Sistemi Applicazioni 
Prodotti in Data Processing S.p.A., SAP China Beijing Branch, all entities in the Czech Republic (SAP ČR, spol. s r.o., 
SAP Services s.r.o., Ariba Czech s.r.o. and Concur Czech (s.r.o.)), SAP Brasil Ltda, SAP Korea Ltd. (Korea), 
SAP North West Africa Ltd. (Maroc), SAP Slovensko s.r.o. (Slovakia), SAP sistemi, aplikacije in produkti za obdelavo
podatkov d.o.o. (Slovenia), SAP Romania SRL, SAP Svenska Aktiebolag (Sweden), SAP UK Ltd., and SAP Ireland Ltd. 
are represented by works councils, worker representatives, employee consultation forums and/or unions. In addition, some of 
these employees are subject to a collective bargaining agreement.""",
]

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
    company_cleaner = CompanyCleaner()

    # Reporting year context
    reporting_year = 2023
    company_name = "TechAdvance Manufacturing Corp LTD."

    print(f"Testing {company_name} Fictional 10-K Filing (Reporting Year: {reporting_year})\n")
    print("=" * 80)
    print()

    for item in ITEM_1:
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
