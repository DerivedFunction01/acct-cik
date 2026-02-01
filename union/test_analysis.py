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
our total employee base reached approximately 124,800 across all regions.

Compared to year-end 2022, the Company and its subsidiaries employed 
approximately 138,200 workers worldwide, of which nearly 9% were represented 
by various labor organizations. This modest representation reflects our 
long-standing preference for direct employee engagement.

In our United States operations, we operate 18 automobile assembly plants 
which employ 14,200 hourly production workers, of which approximately 
82% (11,644 employees) are represented by labor unions under multiple 
agreements with the United Auto Workers (UAW). Our primary UAW-covered 
facility in Michigan employs 3,800 workers, whom are all unionized.

Additionally, our East Coast distribution centers employ 920 workers, all 
of whom are represented by the International Brotherhood of Teamsters 
(100% coverage).

Our non-union domestic workforce totals 89,400 employees and consists 
primarily of software engineers, data scientists, corporate staff, sales, 
and salaried technical personnel across our campuses in California, 
Washington, and Texas. None of these employees are represented by labor 
unions or covered by collective bargaining agreements.

In Europe, our German operations employ 4,100 workers total. The Hamburg 
facility (2,600 workers) maintains 95% IG Metall representation 
(2,470 workers), while our Munich administrative center (1,500 workers) 
has no union representation but is subject to German Works Council rules.

Our Asia-Pacific technology division, headquartered in Bangalore, India, 
employs 68,500 software development and support personnel; none are 
currently unionized. We monitor regional labor trends but anticipate no 
material organizing activity in the foreseeable future.

Our smaller manufacturing sites in Japan (Tokyo and Osaka, combined 
3,200 workers) remain entirely non-union. Thailand, Vietnam, and 
Malaysia facilities employ 6,800 workers combined, with no union 
representation.

Our Chinese operations employ 18,900 workers across multiple sites and 
operate under the All-China Federation of Trade Unions framework as 
required by law; however, we currently report zero formal collective 
bargaining representation for our workforce.

In Latin America, our Mexico plant (Monterrey) employs 1,800 workers, 
of which 15% (270 workers) are represented under a local agreement. 
Remaining operations in Brazil and Argentina (combined 1,100 workers) 
are non-union.


Overall, our global unionization rate stands at approximately 12% of our 
total workforce. We believe our approach to labor relations supports 
flexibility, innovation, and direct dialogue with employees.
"""

"""
- **Company total employees (2023)**: 124,800
- **Explicit global unionization rate**: **12%** → ~14,976 unionized employees

Breakdown of unionized headcounts from explicit statements:
- US auto hourly: 11,644 unionized (82% of 14,200)
- US distribution (Teamsters): 920 unionized (100%)
- Germany Hamburg (IG Metall): 2,470 unionized (95% of 2,600)
- Mexico: 270 unionized (15% of 1,800)
- **Total explicit unionized**: 11,644 + 920 + 2,470 + 270 = **15,304**

Non-unionized / zero-union blocks (explicit or strongly implied):
- US non-union domestic: 89,400 (0%)
- India tech division: 68,500 (0%)
- Japan: 3,200 (0%)
- Thailand+Vietnam+Malaysia: 6,800 (0%)
- China: 18,900 (explicit "zero formal representation")
- Germany Munich: 1,500 (0% formal union)
- Latin America non-Mexico: 1,100 (0%)
- **Approximate total non-unionized**: ~189,400 (but note: some overlap with total; real non-union is total minus union pockets)

**True weighted reality** (reconciling overlaps):
- The large India (68,500) + US non-union (89,400) + China (18,900) alone = ~176,800 mostly/fully non-union employees.
- Unionized pockets are small in number but high-density.
- When you sum **all** reasonably non-overlapping totals → denominator ≈ 124,000–125,000.
- Numerator (unionized) ≈ 15,300.
- **True weighted % ≈ 12.2–12.3%** — matches the explicit global 12% very closely.

### Expected parser behavior & stress points

| Scenario / Bias Type                  | Likely Parser Output (without fixes) | Desired / Correct Behavior          |
|---------------------------------------|--------------------------------------|-------------------------------------|
| Naive sum only union pockets          | ~100% (only high-% sentences summed) | Flag as biased; ignore or down-weight |
| Weighted avg of %s only               | 50–70%+ (driven by 82%, 95%, 100%)   | Overstated; needs raw-count priority |
| Raw count unionized / raw total       | ~12–13% (if non-union blocks included)| Matches explicit 12%                |
| Denominator coverage                  | 30–50% if non-union blocks skipped   | Should reach ~95–100%               |
| China ACFTU legal framework           | 0% (if text-honoring) or 100% (wrong)| 0% per explicit "report zero"       |
| Germany Works Council                 | 0% formal union (correct)            | Correct                             |

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

    print(f"Testing {company_name} Fictional 10-K Filing (Reporting Year: {reporting_year})\n")
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
