import pytest

from analysis import UnionAnalyzer


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
