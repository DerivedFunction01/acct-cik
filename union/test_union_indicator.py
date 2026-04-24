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
from defs.text_cleaner import (
    CompanyCleaner,
    ConcisenessCleaner,
    ContextualNumberCleaner,
    CurrencyRemover,
    MinimalTextCleaner,
)
from defs.region_regex import Region


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
