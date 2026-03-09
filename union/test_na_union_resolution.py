from analysis import UnionAnalyzer, determine_geo_context


def test_na_union_defaults_to_us_domestic():
    analyzer = UnionAnalyzer()
    s = "Teamsters represents a portion of our employees."
    analysis = analyzer.extractor.analyze_sentence(s)
    ctx = determine_geo_context(
        analysis=analysis,
        last_context=None,
        current_idx=0,
        last_idx=-1,
        domestic_country_code=analyzer.domestic_country_code,
    )

    assert ctx.get("countries")
    assert ctx["countries"][0]["code"] == "US"


def test_na_union_defaults_to_ca_domestic_when_filer_is_ca():
    analyzer = UnionAnalyzer(domestic_country_code="CA")
    s = "Teamsters represents a portion of our employees."
    analysis = analyzer.extractor.analyze_sentence(s)
    ctx = determine_geo_context(
        analysis=analysis,
        last_context=None,
        current_idx=0,
        last_idx=-1,
        domestic_country_code=analyzer.domestic_country_code,
    )

    assert ctx.get("countries")
    assert ctx["countries"][0]["code"] == "CA"


def test_na_union_respects_explicit_canada_context():
    analyzer = UnionAnalyzer()
    s = "In Canada, Teamsters represents part of the workforce."
    analysis = analyzer.extractor.analyze_sentence(s)
    ctx = determine_geo_context(
        analysis=analysis,
        last_context=None,
        current_idx=0,
        last_idx=-1,
        domestic_country_code=analyzer.domestic_country_code,
    )

    country_codes = [c.get("code") for c in ctx.get("countries", [])]
    assert "CA" in country_codes
    assert "Teamsters" in (ctx.get("union_names_map", {}).get("CA") or [])
