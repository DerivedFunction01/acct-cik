import pytest

from analysis import UnionAnalyzer


CASES = [
    (
        "Our total employees consist of 458 Argentine employees and 1035 French employees, including 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "Our total employees consist of 458 Argentine employees and 1035 French employees, of which 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "Our total employees consist of 458 Argentine employees and 1035 French employees, with 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "Our total employees consist of 1493 employees in Argentina and France, including 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "The company has 100 Italian and Argentine workers including 20 pilots and 10 auto workers belonging to a local union.",
        {"IT", "AR"},
        30.0,
        90.0,
        120.0,
        25.0,
    ),
    (
        "The company has 100 German and Mexican workers including 20 pilots and 10 auto workers belonging to a local union.",
        {"DE", "MX"},
        30.0,
        90.0,
        120.0,
        25.0,
    ),
    (
        "The company has 100 French and Chinese workers including 20 pilots and 10 auto workers belonging to a local union.",
        {"FR", "CN"},
        30.0,
        90.0,
        120.0,
        25.0,
    ),
    (
        "The company has 100 Italian and Argentine workers consisting of 20 pilots, 10 chefs, and 10 auto workers with 50 belonging to a local union.",
        {"IT", "AR"},
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    (
        "The company has 100 German and Mexican workers consisting of 20 pilots, 10 chefs, and 10 auto workers with 50 belonging to a local union.",
        {"DE", "MX"},
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    (
        "The company has 100 French and Chinese workers including 20 pilots and 10 auto workers, 50 belonging to a local union.",
        {"FR", "CN"},
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    (
        "The company has 100 Italian and Argentine workers consisting of 20% that are pilots, 10% that are chefs, and 10% that are auto workers and 50 belonging to a local union.",
        {"IT", "AR"},
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    (
        "The company has 100 German and Mexican workers consisting of 20% that are pilots, 10% that are chefs, and 10% that are auto workers and 50 belonging to a local union.",
        {"DE", "MX"},
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    (
        "The company has 100 French and Chinese workers consisting of 20% that are pilots, 10% that are chefs, and 10% that are auto workers and 50 belonging to a local union.",
        {"FR", "CN"},
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    (
        "We have 1493 employees of which France and Argentina account for 665 unionized workers.",
        {"FR", "AR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "We have 1493 employees in Europe of which France and Germany account for 665 unionized workers.",
        {"FR", "DE"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "We have 10000 employees in Asia Pacific of which China and India account for 8000 unionized workers.",
        {"CN", "IN"},
        8000.0,
        2000.0,
        10000.0,
        80.0,
    ),
    (
        "We have 1493 Argentine and French employees, of which 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "We have 1493 employees, of which 458 Argentine employees and 1035 French employees, including 665 unionized workers.",
        {"AR", "FR"},
        665.0,
        828.0,
        1493.0,
        44.54,
    ),
    (
        "We have 1493 employees in Europe, of which 458 French employees and 1035 German employees, including 665 unionized workers.",
        {"FR", "DE"},
        665.0,
        828.0,
        1493.0,
        44.54,
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


@pytest.mark.parametrize("sentence,exp_covered,exp_not_covered,exp_total,exp_pct", [
    (CASES[0][0], CASES[0][2], CASES[0][3], CASES[0][4], CASES[0][5]),
    (CASES[3][0], CASES[3][2], CASES[3][3], CASES[3][4], CASES[3][5]),
    (CASES[6][0], CASES[6][2], CASES[6][3], CASES[6][4], CASES[6][5]),
    (CASES[9][0], CASES[9][2], CASES[9][3], CASES[9][4], CASES[9][5]),
])
def test_mixed_coverage_worker_types_preserves_global_provenance_totals(
    sentence,
    exp_covered,
    exp_not_covered,
    exp_total,
    exp_pct,
):
    result = UnionAnalyzer().analyze_paragraph(sentence)
    country_report = result.get("country_report", {}) or {}
    global_obj = country_report.get("global") or {}
    reported = global_obj.get("reported_totals", {}) or {}

    assert global_obj.get("country_code") == "GLO"
    assert global_obj.get("global_source") == "promoted_from_aggregate"
    assert reported.get("cov") == pytest.approx(exp_covered, abs=0.01)
    if exp_not_covered is None:
        assert reported.get("not_cov") is None
    else:
        assert reported.get("not_cov") == pytest.approx(exp_not_covered, abs=0.01)
    assert reported.get("tot") == pytest.approx(exp_total, abs=0.01)
    assert reported.get("pct") == pytest.approx(exp_pct, abs=0.01)


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


@pytest.mark.parametrize(
    "sentence,exp_codes,exp_covered,exp_not_covered,exp_total,exp_pct,exp_global_source",
    [
        (
            CASES[-3][0],
            CASES[-3][1],
            CASES[-3][2],
            CASES[-3][3],
            CASES[-3][4],
            CASES[-3][5],
            "promoted_from_aggregate",
        ),
        (
            CASES[-2][0],
            CASES[-2][1],
            CASES[-2][2],
            CASES[-2][3],
            CASES[-2][4],
            CASES[-2][5],
            "promoted_from_aggregate",
        ),
        (
            CASES[-1][0],
            CASES[-1][1],
            CASES[-1][2],
            CASES[-1][3],
            CASES[-1][4],
            CASES[-1][5],
            None,
        ),
    ],
)
def test_mixed_country_worker_types_total_before_breakdown_keeps_provenance(
    sentence,
    exp_codes,
    exp_covered,
    exp_not_covered,
    exp_total,
    exp_pct,
    exp_global_source,
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

    country_report = result.get("country_report", {}) or {}
    global_obj = country_report.get("global") or {}
    if exp_global_source is None:
        assert global_obj == {}
        return

    assert global_obj.get("country_code") == "GLO"
    assert global_obj.get("global_source") == exp_global_source
    reported = global_obj.get("reported_totals", {}) or {}
    assert reported.get("cov") == pytest.approx(exp_covered, abs=0.01)
    assert reported.get("not_cov") == pytest.approx(exp_not_covered, abs=0.01)
    assert reported.get("tot") == pytest.approx(exp_total, abs=0.01)
    assert reported.get("pct") == pytest.approx(exp_pct, abs=0.01)


def test_disjoint_synthetic_aggregates_stay_as_agg_when_country_totals_exist():
    sentence = (
        "We have 1493 Argentine and French employees of which 665 unionized workers. "
        "We have 800 German and Italian employees of which 100 unionized workers."
    )

    result = UnionAnalyzer().analyze_paragraph(sentence)
    country_report = result.get("country_report", {}) or {}
    agg = country_report.get("agg") or []
    global_obj = country_report.get("global") or {}
    reported = global_obj.get("reported_totals", {}) or {}

    assert len(agg) == 2
    assert global_obj == {}
    assert reported == {}
