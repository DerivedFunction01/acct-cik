from analysis import UnionAnalyzer
from extraction import UnionExtractor
from webpage import extract_home_country
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
    matcher = RegionMatcher()

    assert matcher.get_location("Birmingham") is None
    assert matcher.get_location("Manchester") is None

    assert matcher.get_location("Birmingham, AL") == (
        Region.NORTH_AMERICA,
        "United States",
        "Birmingham, AL",
        "US",
    )
    assert matcher.get_location("Manchester, NH") == (
        Region.NORTH_AMERICA,
        "United States",
        "Manchester, NH",
        "US",
    )
    assert matcher.get_location("Birmingham, UK") == (
        Region.EUROPE,
        "United Kingdom",
        "Birmingham, UK",
        "GB",
    )
    assert matcher.get_location("Manchester, UK") == (
        Region.EUROPE,
        "United Kingdom",
        "Manchester, UK",
        "GB",
    )


def test_warsaw_requires_country_suffix():
    matcher = RegionMatcher()

    assert matcher.get_location("Warsaw") is None
    assert matcher.get_location("Warsaw, Poland") == (
        Region.EUROPE,
        "Poland",
        "Warsaw, Poland",
        "PL",
    )


def test_hamilton_requires_country_suffix():
    matcher = RegionMatcher()

    assert matcher.get_location("Hamilton") is None
    assert matcher.get_location("Hamilton, Canada") == (
        Region.NORTH_AMERICA,
        "Canada",
        "Hamilton, Canada",
        "CA",
    )
    assert matcher.get_location("Hamilton, New Zealand") == (
        Region.ASIA_PACIFIC,
        "New Zealand",
        "Hamilton, New Zealand",
        "NZ",
    )
    assert matcher.get_location("Hamilton, Bermuda") == (
        Region.LATIN_AMERICA,
        "Bermuda",
        "Hamilton, Bermuda",
        "BM",
    )


def test_currency_terms_are_not_geo_locations_but_still_help_home_country():
    matcher = RegionMatcher()

    assert matcher.get_location("lira") is None
    assert matcher.get_location("ruble") is None
    assert matcher.get_location("rub") is None
    assert matcher.get_location("yen") is None
    assert matcher.get_location("yuan") is None
    assert matcher.get_location("rupee") is None
    assert matcher.get_location("dirham") is None
    assert matcher.get_location("riyal") is None
    assert matcher.get_location("shekel") is None
    assert matcher.get_location("rand") is None
    assert matcher.get_location("won") is None

    assert extract_home_country("The reporting currency is lira.") == "TR"
    assert extract_home_country("The reporting currency is rubles.") == "RU"
    assert extract_home_country("The reporting currency is yen.") == "JP"
    assert extract_home_country("The reporting currency is yuan.") == "CN"
    assert extract_home_country("The reporting currency is rupees.") == "IN"
    assert extract_home_country("The reporting currency is dirhams.") == "AE"
    assert extract_home_country("The reporting currency is riyals.") == "SA"
    assert extract_home_country("The reporting currency is shekels.") == "IL"
    assert extract_home_country("The reporting currency is rand.") == "ZA"
    assert extract_home_country("The reporting currency is won.") == "KR"
