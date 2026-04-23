from analysis import Entry, Scope, Tracker, UnionAnalyzer
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
