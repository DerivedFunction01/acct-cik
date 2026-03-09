from analysis import UnionAnalyzer


def test_bargaining_unit_count_accepts_worker_type_gap_and_unit_s():
    text = (
        "We also have, as of the end of the 2000 fiscal year, union contracts covering "
        "1 truck drivers' bargaining unit and warehouse bargaining unit(s)."
    )
    result = UnionAnalyzer().analyze_paragraph(text)
    items = result.get("items", []) or []

    assert items
    coverage_data = (items[0] or {}).get("coverage_data", {}) or {}
    assert coverage_data.get("bargaining_unit_count") == 1.0


def test_bargaining_unit_count_does_not_accept_generic_long_gap():
    text = "We have 1 very complicated internal organizational bargaining unit."
    result = UnionAnalyzer().analyze_paragraph(text)
    items = result.get("items", []) or []

    assert items
    coverage_data = (items[0] or {}).get("coverage_data", {}) or {}
    assert coverage_data.get("bargaining_unit_count") is None
