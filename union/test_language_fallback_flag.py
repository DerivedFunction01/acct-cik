from analysis import UnionAnalyzer


def _get_country(result, code: str):
    countries = (result.get("country_report", {}) or {}).get("countries", []) or []
    for c in countries:
        if c.get("country_code") == code:
            return c
    return None


def test_language_fallback_country_flag_is_set_for_unmentioned_resolution():
    # INT_FR phrase with no explicit country mention should resolve via fallback
    # and be marked in country report.
    text = "Union des travailleurs are present in our operations."
    result = UnionAnalyzer().analyze_paragraph(text)

    # With domestic US context, INT_FR commonly resolves to CA by fallback.
    ca = _get_country(result, "CA")
    assert ca is not None
    assert ca.get("language_fallback_country") is True
