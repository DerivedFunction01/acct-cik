import pytest

from analysis import UnionAnalyzer


CASES = [
    (
        "We have 10000 employees in the Asia Pacific region of which 6000 are in China and 2000 are in India with the remaining in Japan and the Philippines.",
        {"CN", "IN", "JP", "PH"},
        {"Asia/Pacific": 10000.0, "CN": 6000.0, "IN": 2000.0, "JP": 1631.0, "PH": 369.0},
        10000.0,
        10000.0,
    ),
    (
        "Our Central American workforce consists of 2000 employees in Costa Rica and Guatemala and 4000 in Panama.",
        {"CAM", "CR", "GT", "PA"},
        {"Latin America": 6000.0, "CAM": 2000.0, "PA": 4000.0},
        6000.0,
        4000.0,
    ),
    (
        "We employ approximately 8000 workers in Atlantic financial jurisdictions including 5000 in Bermuda and 2000 in the Cayman Islands with the remaining in the British Virgin Islands.",
        {"BM", "KY", "VG"},
        {"Latin America": 8000.0, "BM": 5000.0, "KY": 2000.0, "VG": 1000.0},
        8000.0,
        8000.0,
    ),
    (
        "Our workforce includes 500 employees in Canada compared to 1000 in the United Kingdom and 200 in South Korea.",
        {"CA", "GB", "KR"},
        {"North America": 500.0, "Europe": 1000.0, "Asia/Pacific": 200.0, "Aggregate": 1000.0, "CA": 500.0, "GB": 1000.0, "KR": 200.0},
        1000.0,
        1700.0,
    ),
    (
        "We have 5000 employees in Mainland Europe consisting of 3000 in Germany Italy and Sweden and 2000 in France.",
        {"DE", "IT", "SE", "FR"},
        {"Europe": 7000.0, "DE": 5000.0, "FR": 2000.0},
        5000.0,
        7000.0,
    ),
]


def _country_codes(item):
    geo = item.get("geographic_context", {}) or {}
    return {
        c.get("code")
        for c in geo.get("countries", []) or []
        if c.get("code")
    }


@pytest.mark.parametrize("sentence,expected_codes,expected_lookup,expected_potential_total,expected_summary_total", CASES)
def test_geo_total_before_breakdown(
    sentence,
    expected_codes,
    expected_lookup,
    expected_potential_total,
    expected_summary_total,
):
    result = UnionAnalyzer().analyze_paragraph(sentence)
    items = result.get("items", [])
    assert len(items) == 1

    item = items[0]
    assert _country_codes(item) == expected_codes

    lookup = item.get("lookup_totals", {}) or {}
    for key, value in expected_lookup.items():
        assert lookup.get(key) == pytest.approx(value, abs=0.01)

    assert item.get("potential_total") == pytest.approx(expected_potential_total, abs=0.01)

    cov = item.get("coverage_data", {}) or {}
    assert cov.get("type") == "NONE"
    assert cov.get("employee_count_covered") is None
    assert cov.get("employee_count_not_covered") is None
    assert cov.get("employee_count_total") is None
    assert cov.get("percentage") is None

    summary = result.get("summary", {}) or {}
    assert summary.get("likely_percentage") == 0.0
    assert summary.get("global_total_count") == pytest.approx(expected_summary_total, abs=0.01)
