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


def test_language_specific_union_keywords_do_not_attach_to_unrelated_country():
    result = UnionAnalyzer().analyze_paragraph(
        "In Japan we have employees then 79 employees represented by Sindicato de Trabajadores del Sector Electrico."
    )

    jp = _get_country(result, "JP")
    mx = _get_country(result, "MX")

    assert jp is not None
    assert "INT_ES::Sindicato de Trabajadores" not in (jp.get("country_keywords") or {})
    assert mx is not None
    assert (mx.get("country_keywords") or {}).get("INT_ES::Sindicato de Trabajadores") == 1


def test_language_specific_portuguese_union_resolves_to_brazil_not_us():
    result = UnionAnalyzer().analyze_paragraph(
        "In the United States, 70 employees represented by Sindicato dos Trabalhadores na Industria da Energia Hidroeletrica de Ipaussu."
    )

    us = _get_country(result, "US")
    br = _get_country(result, "BR")

    assert us is not None
    assert "INT_PT::Sindicato dos Trabalhadores" not in (us.get("country_keywords") or {})
    assert br is not None
    assert (br.get("country_keywords") or {}).get("INT_PT::Sindicato dos Trabalhadores") == 1


def test_int_es_resolves_to_argentina_when_argentina_is_mentioned():
    result = UnionAnalyzer().analyze_paragraph(
        "In Argentina, 29 employees represented by Asociacion del Personal Jerarquico del Agua y la Energia."
    )

    ar = _get_country(result, "AR")
    mx = _get_country(result, "MX")

    assert ar is not None
    assert (ar.get("country_keywords") or {}).get("Asociacion del Personal Jerarquico") == 1
    assert mx is None or "Asociacion del Personal Jerarquico" not in (
        mx.get("country_keywords") or {}
    )


def test_specific_union_name_does_not_leak_into_language_bucket():
    result = UnionAnalyzer().analyze_paragraph(
        "75 employees represented by the International Union of Operating Engineers 70 employees represented by Sindicato dos Trabalhadores na Industria da Energia Hidroeletrica de Ipaussu."
    )

    us = _get_country(result, "US")
    br = _get_country(result, "BR")

    assert us is not None
    assert (us.get("country_keywords") or {}).get(
        "International Union of Operating Engineers"
    ) == 1
    assert br is not None
    assert "International Union of Operating Engineers" not in (
        br.get("country_keywords") or {}
    )
