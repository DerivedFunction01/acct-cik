import pytest

from analysis import UnionAnalyzer


CASES = [
    (
        "Our total employees consist of 458 employees in Argentina and 1035 employees in France, including 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "Our total employees consist of 458 employees in Argentina and 1035 employees in France, of which 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "Our total employees consist of 458 employees in Argentina and 1035 employees in France, with 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "Our total employees consist of 320 salaried employees in Germany and 240 hourly employees in France, including 150 unionized workers.",
        {"DE", "FR"},
        150.0,
        410.0,
        560.0,
        26.79,
    ),
    (
        "Our total employees consist of 320 salaried employees in Germany and 240 hourly employees in France, of which 150 unionized workers.",
        {"DE", "FR"},
        150.0,
        410.0,
        560.0,
        26.79,
    ),
    (
        "The company has 100 workers in Italy and Russia including 20 pilots and 10 auto workers belonging to a local union.",
        {"IT", "RU"},
        30.0,
        None,
        100.0,
        30.0,
    ),
    (
        "The company has 100 workers in Italy and Russia, with 20 pilots and 10 auto workers belonging to a local union.",
        {"IT", "RU"},
        30.0,
        10.0,
        100.0,
        30.0,
    ),
    (
        "The company has 100 workers in Italy and Russia, of which 20 pilots and 10 auto workers belong to a local union.",
        {"IT", "RU"},
        30.0,
        None,
        100.0,
        30.0,
    ),
]


def _geo_codes(item):
    geo = item.get("geographic_context", {}) or {}
    return [c.get("code") for c in geo.get("countries", []) or [] if c.get("code")]


@pytest.mark.parametrize("sentence,exp_codes,exp_covered,exp_not_covered,exp_total,exp_pct", CASES)
def test_mixed_coverage_with_worker_types_keeps_combined_country_total(
    sentence,
    exp_codes,
    exp_covered,
    exp_not_covered,
    exp_total,
    exp_pct,
):
    result = UnionAnalyzer().analyze_paragraph(sentence)
    items = result.get("items", [])
    assert len(items) == 1

    item = items[0]
    assert set(_geo_codes(item)) == exp_codes

    cov = item.get("coverage_data", {})
    assert cov.get("employee_count_covered") == pytest.approx(exp_covered, abs=0.01)
    assert cov.get("employee_count_not_covered") == pytest.approx(exp_not_covered, abs=0.01)
    assert cov.get("employee_count_total") == pytest.approx(exp_total, abs=0.01)
    assert cov.get("percentage") == pytest.approx(exp_pct, abs=0.01)


def test_mixed_country_worker_types_can_promote_aggregate_to_global():
    sentence = (
        "Our total employees consist of 458 employees in Argentina and 1035 employees in France, "
        "including 665 unionized workers."
    )

    result = UnionAnalyzer().analyze_paragraph(sentence)
    country_report = result.get("country_report", {}) or {}
    global_obj = country_report.get("global") or {}

    assert global_obj.get("country_code") == "GLO"
    assert global_obj.get("global_source") == "promoted_from_aggregate"
    assert global_obj.get("reported_totals", {}).get("tot") == pytest.approx(1493.0, abs=0.01)
    assert global_obj.get("reported_totals", {}).get("cov") == pytest.approx(665.0, abs=0.01)
    assert global_obj.get("reported_totals", {}).get("not_cov") == pytest.approx(828.0, abs=0.01)
    assert global_obj.get("reported_totals", {}).get("pct") == pytest.approx(44.54, abs=0.01)
