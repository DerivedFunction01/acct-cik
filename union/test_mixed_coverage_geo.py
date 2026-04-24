import pytest

from analysis import UnionAnalyzer


CASES = [
    (
        "In Germany, we have 300 employees, with 120 unionized. In France, we have 200 employees, with 50 unionized.",
        [
            {"code": "DE", "covered": 120.0, "not_covered": None, "total": 300.0, "pct": 40.0},
            {"code": "FR", "covered": 50.0, "not_covered": None, "total": 200.0, "pct": 25.0},
        ],
    ),
    (
        "Germany has 300 employees with 120 unionized, while France has 200 employees with 50 under union contracts.",
        [
            {"code": "DE", "covered": 120.0, "not_covered": None, "total": 300.0, "pct": 40.0},
            {"code": "FR", "covered": 50.0, "not_covered": None, "total": 200.0, "pct": 25.0},
        ],
    ),
    (
        "In Germany, 40% of 300 employees are unionized. In France, 25% of 200 employees are under labor contracts.",
        [
            {"code": "DE", "covered": 120.0, "not_covered": 180.0, "total": 300.0, "pct": 40.0},
            {"code": "FR", "covered": 50.0, "not_covered": 150.0, "total": 200.0, "pct": 25.0},
        ],
    ),
    (
        "France is home to our second-largest European facility with 2400 employees in the Paris region; approximately 45% are represented by unions (CFDT, CGT, and FO combined), equaling roughly 1080 workers.",
        [
            {"code": "FR", "covered": 1080.0, "not_covered": 1320.0, "total": 2400.0, "pct": 45.0},
        ],
    ),
    (
        "The Netherlands in Rotterdam employs 1600 workers, of which only 15% (240 workers) maintain union membership under the FNV.",
        [
            {"code": "NL", "covered": 240.0, "not_covered": 1360.0, "total": 1600.0, "pct": 15.0},
        ],
    ),
    (
        "Our smaller UK operations in Liverpool employ 800 workers with minimal union presence at approximately 8% (64 workers) under Unite the Union.",
        [
            {"code": "GB", "covered": 64.0, "not_covered": 736.0, "total": 800.0, "pct": 8.0},
        ],
    ),
]


def _entry_code(item):
    geo = item.get("geographic_context", {})
    countries = geo.get("countries", []) or []
    if not countries:
        return None
    if len(countries) != 1:
        return None
    return countries[0].get("code")


@pytest.mark.parametrize("text,expected_rows", CASES)
def test_mixed_coverage_with_geo(text, expected_rows):
    result = UnionAnalyzer().analyze_paragraph(text)
    items = result.get("items", [])

    by_code = {}
    for item in items:
        code = _entry_code(item)
        if code is not None:
            by_code[code] = item

    assert len(by_code) == len(expected_rows)

    for exp in expected_rows:
        code = exp["code"]
        assert code in by_code
        cov = by_code[code]["coverage_data"]

        assert cov.get("employee_count_covered") == pytest.approx(exp["covered"], abs=0.01)
        if exp["not_covered"] is None:
            assert cov.get("employee_count_not_covered") is None
        else:
            assert cov.get("employee_count_not_covered") == pytest.approx(exp["not_covered"], abs=0.01)
        assert cov.get("employee_count_total") == pytest.approx(exp["total"], abs=0.01)
        assert cov.get("percentage") == pytest.approx(exp["pct"], abs=0.01)


def test_weighted_division_children_sum_to_parent_total():
    text = "Germany and France have 500 employees, of which 170 are unionized."
    result = UnionAnalyzer().analyze_paragraph(text)
    items = result.get("items", [])

    aggregate_item = next(
        (
            item
            for item in items
            if set((c.get("code") for c in item.get("geographic_context", {}).get("countries", []) or [] if c.get("code")))
            == {"DE", "FR"}
        ),
        None,
    )
    assert aggregate_item is not None

    cov = aggregate_item.get("coverage_data", {})
    assert cov.get("employee_count_total") == pytest.approx(500.0, abs=0.01)
    assert cov.get("employee_count_covered") == pytest.approx(170.0, abs=0.01)
    assert cov.get("percentage") == pytest.approx(34.0, abs=0.01)
