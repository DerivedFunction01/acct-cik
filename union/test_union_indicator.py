from analysis import (
    Entry,
    Scope,
    Tracker,
    UnionAnalyzer,
    get_effective_years,
    has_year_mismatch,
)
from filter_paragraphs import filter_content, init_worker
from extraction import SentenceAnalysis
from defs.union_regex import LABOR_CONTRACT_BYPASS_REGEX
from defs.text_cleaner import (
    CompanyCleaner,
    ConcisenessCleaner,
    ContextualNumberCleaner,
    CurrencyRemover,
    MinimalTextCleaner,
)
from defs.region_regex import Region, RegionMatcher


def _get_country(result, code: str):
    countries = (result.get("country_report", {}) or {}).get("countries", []) or []
    for c in countries:
        if c.get("country_code") == code:
            return c
    return None


def test_union_indicator_is_zero_for_explicit_non_coverage():
    text = "Our 1000 US employees are not covered by unions."
    result = UnionAnalyzer().analyze_paragraph(text)
    us = _get_country(result, "US")

    assert us is not None
    assert us.get("union_indicator") == 0
    assert "method_breakdown" not in us


def test_international_promotes_to_global_when_domestic_missing():
    tracker = Tracker(domestic_country_code="US")
    tracker.entries = [
        Entry(
            scope=Scope.REGION,
            key=Region.INTERNATIONAL.value,
            covered_count=70.0,
            total_count=100.0,
            percentage=70.0,
            is_union_record=True,
        )
    ]

    report = tracker.build_country_provenance_report()
    global_obj = report.get("global") or {}

    assert global_obj.get("country_code") == "GLO"
    assert global_obj.get("global_source") == "promoted_from_international"
    assert global_obj.get("global_source_code") == "INT"


def test_international_not_promoted_when_explicitly_non_covered():
    tracker = Tracker(domestic_country_code="US")
    tracker.entries = [
        Entry(
            scope=Scope.REGION,
            key=Region.INTERNATIONAL.value,
            not_covered_count=100.0,
            total_count=100.0,
            percentage=0.0,
            is_union_record=True,
            is_negated=True,
        )
    ]

    report = tracker.build_country_provenance_report()

    assert report.get("global") is None


def test_shared_us_ca_signal_keeps_domestic_only_for_us():
    tracker = Tracker(domestic_country_code="US")
    tracker.entries = [
        Entry(
            scope=Scope.COUNTRY,
            key="US",
            covered_count=70.0,
            total_count=100.0,
            percentage=70.0,
            is_union_record=True,
        ),
        Entry(
            scope=Scope.COUNTRY,
            key="CA",
            covered_count=70.0,
            total_count=100.0,
            percentage=70.0,
            is_union_record=True,
        ),
    ]

    report = tracker.build_country_provenance_report()
    codes = [c.get("country_code") for c in report.get("countries", [])]

    assert "US" in codes
    assert "CA" not in codes


def test_shared_us_ca_signal_keeps_domestic_only_for_ca():
    tracker = Tracker(domestic_country_code="CA")
    tracker.entries = [
        Entry(
            scope=Scope.COUNTRY,
            key="US",
            covered_count=70.0,
            total_count=100.0,
            percentage=70.0,
            is_union_record=True,
        ),
        Entry(
            scope=Scope.COUNTRY,
            key="CA",
            covered_count=70.0,
            total_count=100.0,
            percentage=70.0,
            is_union_record=True,
        ),
    ]

    report = tracker.build_country_provenance_report()
    codes = [c.get("country_code") for c in report.get("countries", [])]

    assert "CA" in codes
    assert "US" not in codes


def test_shared_us_ca_signal_does_not_collapse_across_sentences():
    tracker = Tracker(domestic_country_code="US")
    tracker.entries = [
        Entry(
            scope=Scope.COUNTRY,
            key="US",
            covered_count=70.0,
            total_count=100.0,
            percentage=70.0,
            is_union_record=True,
            sent_idx=1,
        ),
        Entry(
            scope=Scope.COUNTRY,
            key="CA",
            covered_count=70.0,
            total_count=100.0,
            percentage=70.0,
            is_union_record=True,
            sent_idx=2,
        ),
    ]

    report = tracker.build_country_provenance_report()
    codes = [c.get("country_code") for c in report.get("countries", [])]

    assert "US" in codes
    assert "CA" in codes


def test_previous_year_promotes_to_reporting_year_without_historical_language():
    analysis = SentenceAnalysis(text="As of January 1, 2019, the company had 100 employees.")
    analysis.years = [2019]

    assert get_effective_years(analysis, reporting_year=2020) == [2020]


def test_previous_year_stays_previous_with_historical_language():
    analysis = SentenceAnalysis(text="During the preceding fiscal year, the company had 100 employees.")
    analysis.years = [2019]
    analysis.has_historical = True

    assert get_effective_years(analysis, reporting_year=2020) == [2019]


def test_year_mismatch_helper_detects_lone_prior_year():
    analysis = SentenceAnalysis(text="As of January 1, 2019, the company had 100 employees.")
    analysis.years = [2019]

    assert has_year_mismatch(analysis, reporting_year=2020) is True


def test_country_report_surfaces_year_mismatch_flag():
    tracker = Tracker(domestic_country_code="US")
    tracker.year_mismatch_detected = True

    report = tracker.build_country_provenance_report()

    assert report.get("year_mismatch") is True


def test_context_total_fallback_drops_small_noise_numbers():
    sentence = "We had 50000 employees and footnote 1."
    analysis = UnionAnalyzer().extractor.analyze_sentence(sentence, context_total=50000)

    assert 1.0 not in analysis.numbers


def test_contextual_cleaner_removes_forward_small_union_breakdown_clauses():
    cleaned = ContextualNumberCleaner().clean(
        "8 unions (4 in Canada, 1 in Mexico, 1 in Venezuela and 2 in Brazil).",
        home_country="US",
    )

    assert "unions" in cleaned
    assert "4 in Canada" not in cleaned
    assert "1 in Mexico" not in cleaned
    assert "1 in Venezuela" not in cleaned
    assert "2 in Brazil" not in cleaned


def test_single_country_aggregate_is_reported_as_explicit_not_weighted():
    blocks = [
        "At the end of fiscal 2008, we had approximately 13,800 employees. We are party to the following collective bargaining agreements with the:",
        "United Steel, Paper and Forestry, Rubber, Manufacturing, Energy, Allied Industrial and Service Workers International Union (290 employees in Baltimore, MD), which expires in April 2009",
        "United Steelworkers of America (33 employees in Vancouver, WA), which expires in January 2011",
        "Unite Here Local 150 (111 employees in Bloomington, MN), which expires in March 2009",
        "United Automobile, Aerospace, and Agricultural Implement Workers of America, Local 882 (69 employees in Columbus, GA) which expires in October 2009 and",
        "United Steel, Paper and Forestry, Rubber, Manufacturing, Energy, Allied Industrial and Service Workers International Union, AFL-CIO, Local 1008 (102 employees in Constantine, MI) which expires in December 2009",
        "None of our other domestic employees are covered by collective bargaining agreements. We believe our relations with our employees are good.",
    ]

    init_worker()
    cleaned = " ".join(
        filter_content(blocks, year=2008, home_country="US")[0]
    )
    result = UnionAnalyzer().analyze_paragraph(cleaned, reporting_year=2008)
    us = _get_country(result, "US")

    assert us is not None
    method_breakdown = us.get("method_breakdown") or {}
    assert "EXPLICIT" in method_breakdown
    assert "WEIGHTED_DIVISION" not in method_breakdown


def test_filter_content_keeps_capitalized_agreement_lines_split():
    blocks = [
        "At the end of fiscal 2008, we had approximately 13,800 employees. We are party to the following collective bargaining agreements with the:",
        "United Steel, Paper and Forestry, Rubber, Manufacturing, Energy, Allied Industrial and Service Workers International Union (290 employees in Baltimore, MD), which expires in April 2009",
        "United Steelworkers of America (33 employees in Vancouver, WA), which expires in January 2011",
    ]

    init_worker()
    filtered = filter_content(blocks, year=2008, home_country="US")[0]

    assert len(filtered) >= 2
    assert "United Steel" not in filtered[0]
    assert any("United Steel" in block for block in filtered[1:])


def test_filter_content_allows_customer_language_with_labor_contract_context():
    blocks = [
        "Our customers include a union, but the employees work under collective bargaining agreements with the following unions: Allied International Union and Special & Superior Officers Benevolent Association.",
    ]

    init_worker()
    filtered = filter_content(blocks, year=1995, home_country="US")[0]

    assert filtered
    assert any("collective bargaining agreements" in block for block in filtered)


def test_filter_content_still_excludes_customer_language_without_labor_context():
    blocks = [
        "Our customers include a union and our services are sold to clients across the country.",
    ]

    init_worker()
    filtered = filter_content(blocks, year=1995, home_country="US")[0]

    assert not filtered


def test_pct_only_aggregate_sentence_is_explicit_not_weighted():
    text = (
        "As of <2009>, approximately 40% of our North American packaging plant "
        "employees and most of our packaging plant employees in Europe were "
        "covered by collective bargaining agreements."
    )

    result = UnionAnalyzer().analyze_paragraph(text, reporting_year=2009)

    country_report = result.get("country_report", {}) or {}
    assert country_report.get("agg")
    assert country_report["agg"][0].get("source_type") == "EXPLICIT"

    countries = country_report.get("countries", []) or []
    for country in countries:
        method_breakdown = country.get("method_breakdown") or {}
        assert "WEIGHTED_DIVISION" not in method_breakdown


def test_same_region_aggregate_collapses_to_region_row():
    tracker = Tracker(domestic_country_code="US")
    tracker.entries = [
        Entry(
            scope=Scope.COUNTRY,
            key="US",
            covered_count=50.0,
            total_count=50.0,
            percentage=100.0,
            is_union_record=True,
        ),
        Entry(
            scope=Scope.COUNTRY,
            key="CA",
            covered_count=50.0,
            total_count=50.0,
            percentage=100.0,
            is_union_record=True,
        ),
        Entry(
            scope=Scope.AGGREGATE,
            key=Region.AGGREGATE.value,
            covered_count=100.0,
            total_count=100.0,
            percentage=100.0,
            is_union_record=True,
            related_geo_codes=["US", "CA"],
        ),
    ]

    report = tracker.build_country_provenance_report()
    na = _get_country({"country_report": report}, "NA")

    assert na is not None
    assert na.get("country_totals", {}).get("tot") == 100.0
    assert na.get("country_totals", {}).get("cov") == 100.0
    assert na.get("country_totals", {}).get("pct") == 100.0
    assert not report.get("agg")


def test_same_region_aggregate_with_mexico_collapses_to_na():
    tracker = Tracker(domestic_country_code="US")
    tracker.entries = [
        Entry(
            scope=Scope.COUNTRY,
            key="US",
            covered_count=40.0,
            total_count=40.0,
            percentage=100.0,
            is_union_record=True,
        ),
        Entry(
            scope=Scope.COUNTRY,
            key="CA",
            covered_count=30.0,
            total_count=30.0,
            percentage=100.0,
            is_union_record=True,
        ),
        Entry(
            scope=Scope.COUNTRY,
            key="MX",
            covered_count=30.0,
            total_count=30.0,
            percentage=100.0,
            is_union_record=True,
        ),
        Entry(
            scope=Scope.AGGREGATE,
            key=Region.AGGREGATE.value,
            covered_count=100.0,
            total_count=100.0,
            percentage=100.0,
            is_union_record=True,
            related_geo_codes=["US", "CA", "MX"],
        ),
    ]

    report = tracker.build_country_provenance_report()
    na = _get_country({"country_report": report}, "NA")

    assert na is not None
    assert na.get("country_totals", {}).get("tot") == 100.0
    assert na.get("country_totals", {}).get("cov") == 100.0
    assert "MX" in [c.get("country_code") for c in report.get("countries", [])]
    assert not report.get("agg")


def test_labor_contract_bypass_regex_is_unambiguous():
    assert LABOR_CONTRACT_BYPASS_REGEX.search("collective bargaining agreements")
    assert LABOR_CONTRACT_BYPASS_REGEX.search("union contracts")
    assert LABOR_CONTRACT_BYPASS_REGEX.search("labor contracts")
    assert not LABOR_CONTRACT_BYPASS_REGEX.search("labor union customers")
    assert not LABOR_CONTRACT_BYPASS_REGEX.search("a labor union")


def test_region_matcher_keeps_acronym_unions_case_sensitive():
    matcher = RegionMatcher()

    assert matcher.get_union("SMART") is not None
    assert matcher.get_union("smart") is None
    assert matcher.get_union("AFL-CIO") is not None
    assert matcher.get_union("afl-cio") is None


def test_union_extractor_strips_leading_fillers_from_union_matches():
    sentence = "The United Steelworkers of America represent employees in the US."
    analysis = UnionAnalyzer().extractor.analyze_sentence(sentence)

    assert "United Steelworkers of America" in analysis.union_terms
    assert all(
        not term.lower().startswith(("the ", "our ", "a ", "an "))
        for term in analysis.union_terms
    )


def test_contextual_cleaner_keeps_location_words_while_stripping_forward_counts():
    cleaned = ContextualNumberCleaner().clean(
        "8 union/contracts/employee groups ... 2 in Brazil, 1 in Mexico, and 30 distribution and manufacturing center employees.",
        home_country="US",
    )

    assert "union/contracts/employee groups" in cleaned
    assert "Brazil" in cleaned
    assert "Mexico" in cleaned
    assert "2 in Brazil" not in cleaned
    assert "1 in Mexico" not in cleaned
    assert "30 distribution and manufacturing center employees" in cleaned
