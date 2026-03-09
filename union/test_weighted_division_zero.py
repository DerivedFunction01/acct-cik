from defs.region_regex import weighted_division


def test_weighted_division_skips_when_value_is_zero():
    dist, note = weighted_division(
        0.0,
        [{"key": "US"}, {"key": "CA"}],
    )
    assert dist == {"US": 0.0, "CA": 0.0}
    assert note == ""
