from analysis import UnionAnalyzer
from extraction import UnionExtractor
from defs.region_regex import Region, RegionMatcher


def _geo_map(analysis):
    return {g.geo_code: g for g in analysis.geo_matches if g.geo_code}


def test_outside_exclusion_propagates_across_chained_countries():
    sentence = "Outside US, Canada and Mexico, 100 employees are unionized."
    analysis = UnionExtractor().analyze_sentence(sentence)
    gm = _geo_map(analysis)

    for code in ("US", "CA", "MX"):
        assert code in gm
        assert gm[code].is_excluded is True
        assert gm[code].is_strict is True

    # All excluded countries should share the same list chain and exclusion group.
    list_ids = {gm[c].list_group_id for c in ("US", "CA", "MX")}
    excl_ids = {gm[c].exclusion_group_id for c in ("US", "CA", "MX")}
    assert len(list_ids) == 1
    assert len(excl_ids) == 1


def test_except_excludes_child_country_but_not_container_region():
    sentence = "In Europe except Germany, 300 employees are unionized."
    analysis = UnionExtractor().analyze_sentence(sentence)
    gm = _geo_map(analysis)

    assert "EUR" in gm
    assert gm["EUR"].is_excluded is False

    assert "DE" in gm
    assert gm["DE"].is_excluded is True
    assert gm["DE"].is_strict is False


def test_container_context_prefers_explicit_child_countries():
    sentence = (
        "In North America, we have 15,000 employees in the United States, "
        "Mexico, and Puerto Rico."
    )
    result = UnionAnalyzer().analyze_paragraph(sentence)
    item = result["items"][0]
    countries = item.get("geographic_context", {}).get("countries", [])
    codes = {c.get("code") for c in countries}

    # Container NA should be superseded by explicit children in context.
    assert codes == {"US", "MX", "PR"}


def test_shared_us_city_names_resolve_to_us():
    assert RegionMatcher.get_location("Birmingham") == (
        Region.NORTH_AMERICA,
        "United States",
        "Birmingham",
        "US",
    )
    assert RegionMatcher.get_location("Manchester") == (
        Region.NORTH_AMERICA,
        "United States",
        "Manchester",
        "US",
    )
