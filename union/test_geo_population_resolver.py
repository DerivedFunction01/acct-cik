import pytest

from analysis import UnionAnalyzer


def _country_totals_map(result):
    report = result.get("country_report", {}) or {}
    countries = report.get("countries", []) or []
    out = {}
    for c in countries:
        code = c.get("country_code")
        totals = (c.get("country_totals") or {}).get("tot")
        if code:
            out[code] = totals
    return out


def test_strict_employment_distribution_uses_prior_total_for_next_sentence():
    text = (
        "We employed 1000 employees worldwide. "
        "Approximately 10% of our employees are located domestically and 20% in China."
    )
    result = UnionAnalyzer().analyze_paragraph(text)
    totals = _country_totals_map(result)

    assert totals.get("US") == pytest.approx(100.0, abs=0.01)
    assert totals.get("CN") == pytest.approx(200.0, abs=0.01)


def test_strict_employment_distribution_supports_remaining_balance_with_percent():
    text = (
        "We have 1000 employees. "
        "90% are domestic, with the balance in China."
    )
    result = UnionAnalyzer().analyze_paragraph(text)
    totals = _country_totals_map(result)

    assert totals.get("US") == pytest.approx(900.0, abs=0.01)
    assert totals.get("CN") == pytest.approx(100.0, abs=0.01)


def test_geo_count_distribution_supports_remaining_balance_with_counts():
    text = (
        "We have 1000 employees, 900 are domestic, with the balance in China."
    )
    result = UnionAnalyzer().analyze_paragraph(text)
    totals = _country_totals_map(result)

    assert totals.get("US") == pytest.approx(900.0, abs=0.01)
    assert totals.get("CN") == pytest.approx(100.0, abs=0.01)


def test_strict_employment_distribution_ignored_when_union_semantics_present():
    text = (
        "We employed 1000 employees worldwide. "
        "Approximately 10% of our employees are located domestically and 20% in China under union agreements."
    )
    result = UnionAnalyzer().analyze_paragraph(text)
    totals = _country_totals_map(result)

    assert totals.get("US") is None
    assert totals.get("CN") is None
