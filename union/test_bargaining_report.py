import pytest

from analysis import UnionAnalyzer
from extraction import UnionExtractor


def test_bargaining_report_capture_explicit_units():
    text = (
        "We employ approximately 1,200 ground employees and 800 flight attendants. "
        "3 bargaining units represent our flight operations and one in maintenance."
    )
    result = UnionAnalyzer().analyze_paragraph(text)
    report = result.get("bargaining_report") or {}
    assert report, "Bargaining report should exist"
    assert report.get("tot") == 3
    assert "Unknown" in report.get("entities", [])


def test_bargaining_unit_list_preserves_geo_flags():
    text = (
        "Approximately 4698 employees are represented by 28 domestic and 8 foreign "
        "collective bargaining units."
    )
    analysis = UnionExtractor().analyze_sentence(text)
    geo_codes = {g.geo_code for g in analysis.geo_matches if g.geo_code}

    assert geo_codes == {"DOM", "INT"}
