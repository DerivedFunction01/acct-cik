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
from analysis import UnionAnalyzer
from defs.text_cleaner import CurrencyRemover, MinimalTextCleaner, ContextualNumberCleaner


TEST_PARAGRAPH = """
TechAdvance Manufacturing operates a diverse global workforce across 
manufacturing, logistics, and technology divisions. As of December 31, 2023, 
our total employee base stood at approximately 41,200 across all regions.

Compared to December 31, 2022, when the Company and its subsidiaries employed 
approximately 79,300 workers worldwide, of which nearly 71% were represented by 
various labor organizations. This figure reflects a meaningful reduction from 
year-end 2021, when the Company employed roughly 92,800 workers. The workforce 
decline was driven primarily by continued supply-chain constraints and component 
shortages linked to the Russia–Ukraine conflict, which required the Company to 
furlough approximately 7,400 production employees during the second half of 2023. 
With improving availability of steel, semiconductors, and certain electronic 
components, the Company now plans to recall roughly 2,300 assembly technicians 
in the second quarter of 2024 and anticipates fewer permanent reductions among 
engineering staff than earlier forecasts. Management continues to monitor global 
supply and geopolitical developments closely and expects further workforce 
adjustments should material shortages re-emerge.

In our United States operations, we own 15 automobile manufacturing facilities 
which employ 17,200 auto workers, of which approximately 28% (4,816 employees) 
are represented by labor unions. Our largest unionized segment comprises 2,400 
production workers in our Ohio and Indiana facilities, organized under the United 
Auto Workers (UAW) agreement that became effective in 2022. Additionally, our 
West Coast logistics centers employ 1,720 workers represented by the International 
Brotherhood of Teamsters, covering 100% of those facilities. We maintain a 
mutually beneficial relationship with both the UAW and Teamsters.

Our non-union domestic workforce of 12,900 employees consists primarily of 
engineering, administrative, and management personnel. At our headquarters in 
Dallas, Texas, 4,400 of 5,300 corporate staff operate outside union frameworks. 
The remaining non-union workers are distributed across regional sales offices 
and smaller manufacturing sites. We maintain a neutral stance toward unionization 
efforts and do not actively oppose employee organizing activities.

In Canada, we employ 2,600 workers across three locations: Toronto, Vancouver, 
and Calgary. The Toronto facility (1,200 workers) is 70% unionized under Unifor 
representation (840 workers), while Vancouver (900 workers) and Calgary (500 
workers) remain entirely non-union. We anticipate limited organizing interest 
in Vancouver during 2024 but expect no material change to current representation 
levels.

Our European operations, which employed 9,400 workers at year-end 2023, present 
a more complex labor environment. In Germany, we operate two manufacturing plants 
employing 3,300 workers total: the Düsseldorf facility (1,900 workers) with 72% 
IG Metall representation (1,368 workers), and the Stuttgart facility (1,400 
workers) with no formal union representation but subject to German Works Council 
requirements. France is home to our second-largest European facility with 2,500 
employees in the Paris region; approximately 52% are represented by unions (CFDT, 
CGT, and FO combined), equaling roughly 1,300 workers. The Netherlands facility 
in Rotterdam employs 1,700 workers, of which 22% (374 workers) maintain union 
membership under the FNV. Our smaller UK operations in Liverpool employ 900 
workers with modest union presence at approximately 12% (108 workers) under 
Unite the Union.

We maintain generally constructive relationships with our European union partners, 
although relations with German works councils can involve technical complexity. 
Our French operations have experienced no significant labor disputes in the past 
three years.

In Asia-Pacific, our footprint is expanding but remains predominantly 
non-unionized. Japan represents our largest regional presence with 6,800 
employees: 4,500 in our Tokyo automotive component facility and 2,300 in our 
Osaka electronics manufacturing. The Tokyo facility is 42% unionized (1,890 
workers) under the Japanese Association of Metal and Allied Workers (JAM), while 
Osaka is entirely non-union. India is our emerging market with 3,800 software 
engineers at our Bangalore campus; none are currently unionized, though we 
monitor local labor developments given emerging organizing trends. Thailand’s 
small facility employs 480 workers entirely outside union frameworks. Australia 
and New Zealand operations employ 950 workers combined, with no formal union 
representation.

Our Chinese operations, while currently non-unionized with 3,100 workers across 
Shanghai and Shenzhen facilities, carry potential future exposure. We note that 
all Chinese facilities operate under the All-China Federation of Trade Unions 
framework as required by law; however, we currently report zero formal 
representation of our workforce. We plan to increase hiring in China by 35% 
through 2025, which could result in additional union exposure.

In Latin America, we maintain minimal operations: Mexico (1,400 workers at 
Monterrey plant) is 32% unionized (448 workers) under CTM, while our presence 
in Brazil (320 workers, São Paulo) and Colombia (200 workers) remains non-union. 
We do not anticipate material union organizing activity in these regions in the 
near term.

Middle East and Africa operations are limited. Our UAE facility (Dubai, 350 
workers) is entirely non-union as required by local law. We have no current 
operations in other African markets, having divested our South African subsidiary 
in 2019.

Overall, our global unionization rate stands at approximately 31% of our total 
workforce. We believe our labor relations profile remains stable, with no 
significant pending negotiations or anticipated labor disputes. We remain 
committed to fair labor practices and transparent engagement with employee 
representative bodies.
"""

"""
Global total (2023): 41,200 employees → 31% unionized ≈ 12,772 covered
United States auto + logistics: 17,200 + 1,720 = 18,920 → 28% + 100% blended ≈ 33–34% unionized
US non-union portion (explicit): ~12,900 (mostly HQ + scattered)
Canada: 2,600 total → Toronto 70% → blended ≈ 32% unionized
Europe: 9,400 total → weighted average ≈ 42% unionized (Germany 41%, France 52%, NL 22%, UK 12%)
Asia-Pacific ex-China (Japan + India + Thailand + AU/NZ): ≈ 11,980 → Japan 28% blended, others 0% → overall ≈ 16% unionized
China: 3,100 → 0% (explicitly reported as zero formal representation)
Latin America: 1,920 total → Mexico 32%, others 0% → blended ≈ 23% unionized
Middle East (UAE): 350 → 0%

"""


if __name__ == "__main__":
    # Test setup
    analyzer = UnionAnalyzer()
    cleaner = MinimalTextCleaner()
    currency_remover = CurrencyRemover()
    contextual_cleaner = ContextualNumberCleaner()

    # Reporting year context
    reporting_year = 2023
    company_name = "TechAdvance Manufacturing Corp LTD."

    print(f"Testing {company_name} 10-K Filing (Reporting Year: {reporting_year})\n")
    print("=" * 80)
    print()

    # Clean the text
    cleaned_text = cleaner.clean(TEST_PARAGRAPH)
    cleaned_text = currency_remover.clean(cleaned_text)
    cleaned_text = contextual_cleaner.clean(cleaned_text)
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

# %%
