from analysis import (
    Entry,
    Scope,
    Tracker,
    UnionAnalyzer,
    get_effective_years,
    has_year_mismatch,
)
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
