from analysis import refine_generic_code
from defs.region_regex import GeoCode


def test_refine_container_code_to_domestic_fallback():
    code, name = refine_generic_code("NA", [], domestic_country_code="CA")
    assert code == "CA"
    assert name == "CA"


def test_refine_container_code_prefers_explicit_candidate():
    code, name = refine_generic_code(
        "NA",
        [{"code": "US", "name": "United States"}],
        domestic_country_code="CA",
    )
    assert code == "US"
    assert name == "United States"


def test_refine_int_language_does_not_force_invalid_domestic_fallback():
    code, name = refine_generic_code(
        GeoCode.INT_LANG.value + "ES",
        [],
        domestic_country_code="US",
    )
    assert code == GeoCode.INT_LANG.value + "ES"
    assert name is None
