from analysis import UnionAnalyzer


def test_language_only_union_context_is_code_tagged_and_safe():
    text = "Union des travailleurs are present in our operations."
    result = UnionAnalyzer().analyze_paragraph(text)
    items = result.get("items", []) or []
    assert items

    item = items[0]
    geo = item.get("geographic_context", {}) or {}
    # Regression: should preserve unresolved language inference safely
    # without requiring countries[0].
    assert geo.get("union_name_code", "").startswith("INT_")
