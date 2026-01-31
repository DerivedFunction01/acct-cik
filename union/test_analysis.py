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
    results = analyzer.analyze_paragraph(
        cleaned_text, item_type="item1", reporting_year=reporting_year
    )

    # Pretty print results
    print(f"Total Sentences Extracted: {len(results)}\n")
    print(json.dumps(results, indent=2))

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

    # Test key scenarios
    print("\n" + "=" * 80)
    print("\nKEY TEST SCENARIOS:\n")

    scenarios = [
        ("Simple percentage (USA 22%)", "approximately 22%"),
        ("Specific union (UAW Ohio/Indiana)", "United Auto Workers (UAW)"),
        ("100% union coverage (Teamsters)", "100% of those facilities"),
        ("Percentage with non-covered complement", "65% unionized"),
        (
            "Future temporal marker (Vancouver 2024)",
            "anticipate potential organizing activity in Vancouver during 2024",
        ),
        ("Germany facility split", "Düsseldorf facility (1,800 workers) with 68%"),
        ("Relationship quality (constructive)", "constructive relationships"),
        (
            "Relationship quality (technically complex)",
            "relations with the German works councils can be technically complex",
        ),
        (
            "Divested operation (South Africa 2019)",
            "divested our South African subsidiary in 2019",
        ),
        ("Non-unionized by law (UAE)", "entirely non-union as required by local law"),
        (
            "Chinese legal framework mention",
            "all-China Federation of Trade Unions framework",
        ),
        ("Future growth (China 40%)", "increase hiring in China by 40% through 2025"),
        ("Global rate summary", "global unionization rate stands at approximately 24%"),
        (
            "No false claims about excluded items",
            "should not extract supplier references or third-party",
        ),
    ]

    print("Verifying correct extraction of key scenarios:\n")
    for desc, snippet in scenarios:
        found = any(snippet.lower() in r.get("sentence", "").lower() for r in results)
        status = "✓ FOUND" if found else "✗ NOT FOUND (or intentionally excluded)"
        print(f"  {status:20} | {desc}")

# %%
