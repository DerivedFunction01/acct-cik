from analysis import UnionAnalyzer


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
