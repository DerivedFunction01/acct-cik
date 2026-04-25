import pytest

from analysis import UnionAnalyzer, determine_geo_context
from defs.region_regex import Region, RegionMatcher


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


@pytest.mark.parametrize(
    "union_name",
    [
        "UAW",
        "United Auto Workers",
        "International Union, United Automobile, Aerospace and Agricultural Implement Workers of America",
        "UFCW",
        "United Food and Commercial Workers",
        "USW",
        "USWA",
        "United Steelworkers",
        "CWA",
        "Communications Workers of America",
        "SEIU",
        "Service Employees International Union",
        "UNITE HERE",
        "UMWA",
        "United Mine Workers",
        "ILA",
        "International Longshoremen's Association",
        "IATSE",
        "International Alliance of Theatrical Stage Employees",
        "IAHFIAW",
        "HFIAW",
        "International Association of Heat and Frost Insulators and Allied Workers",
        r"International Association of Heat and Frost Insulators and Asbestos Workers",
        "IUOE",
        "International Union of Operating Engineers",
        "ILWU",
        "LIUNA",
        "Laborers' International Union of North America",
        "SMART",
        "Sheet Metal, Air, Rail and Transportation Workers",
        "SMWIA",
        "BMWED",
        "TWU",
        "Transport Workers Union",
        "ATU",
        "Amalgamated Transit Union",
        "IFPTE",
        "International Federation of Professional and Technical Engineers",
        "BCTGM",
        "Bakery, Confectionery, Tobacco Workers and Grain Millers",
        "Brotherhood of Maintenance of Way Employes",
        "BAC",
        "International Bricklayers of America",
        "IW",
        "UBC",
        "IUPAT",
        "OPCMIA",
        r"International Longshore(?:mans'|men)? and Warehouse(?:mans'|men)? Union",
    ],
)
def test_moved_north_america_union_aliases_resolve_to_north_america(union_name):
    matcher = RegionMatcher()
    region, country, code = matcher.get_union(union_name)

    assert region == Region.NORTH_AMERICA
    assert country == "North America"
    assert code == "NA"
