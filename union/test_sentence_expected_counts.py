import pytest

from analysis import UnionAnalyzer


CASES = [
    ("Of the 300 employees, 200 are unionized.", 200.0, 100.0, 300.0, 66.67),
    ("Of the 300 employees, 20% are unionized.", 60.0, 240.0, 300.0, 20.0),
    ("For the 500 workers, 50 are under a labor contract.", 50.0, 450.0, 500.0, 10.0),
    (
        "The workforce consists of 300 employees, with 100 that are under a union agreement.",
        100.0,
        200.0,
        300.0,
        33.33,
    ),
    (
        "200 part-time and 100 full-time employees are unionized.",
        300.0,
        None,
        300.0,
        100.0,
    ),
    ("100 of 200 are in a union.", 100.0, 100.0, 200.0, 50.0),
    (
        "100 of the 200 employees are under collective bargaining.",
        100.0,
        100.0,
        200.0,
        50.0,
    ),
    (
        "50% of the 200 employees are under collective bargaining.",
        100.0,
        100.0,
        200.0,
        50.0,
    ),
    ("For 100 employees, 60% are unionized", 60.0, 40.0, 100.0, 60.0),
    (
        "100 are unionzied employees, representing 20% of the workforce.",
       100.0, 400.0, 500.0, 20.0
    ),
    ("60% of the company's 1000 employees are unionized.", 60.0, 40.0, 1000.0, 60.0),
    (
        "20% our our workers are unionized, consisting of 1000 workers.",
        1000.0,
        4000.0,
        5000.0,
        20.0,
    ),
    ("We employed 100 workers and 50 workers are unionized.", 50.0, None, 100.0, 50.0),
    (
        "We employed 100 workers and 10% of the workers are unionized.",
        10.0,
        90.0,
        100.0,
        10.0,
    ),
    ("500 workers are unionized.", 500.0, 0, None, None),
    (
        "There are 200 workers, including 50 salaried employees, and 50 that are under collective bargaining.",
        50.0,
        150.0,
        200.0,
        25.0,
    ),
    (
        "There are 200 workers, of which 50% are salaried employees and 50 that are under collective bargaining.",
        50.0,
        150.0,
        200.0,
        25.0,
    ),
    (
        "There are 200 workers, of which 35% are salaried employees are under collective bargaining.",
        70.0,
        130.0,
        200.0,
        35.0,
    ),
    (
        "The company has 100 workers consisting of 20 pilots, 10 chefs, and 10 auto workers with 50 belonging to a local union.",
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    (
        "The company has 100 workers consisting of 20% that are pilots, 10% that are chefs, and 10% that are auto workers and 50 belonging to a local union.",
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    (
        "The company has 100 workers consisting of 20 pilots, 10 chefs, and 10 auto workers belonging to a local union.",
        40.0,
        60.0,
        100.0,
        40.0,
    ),
    (
        "The company has 100 workers including 20 pilots and 10 auto workers belonging to a local union.",
        30.0,
        70.0,
        100.0,
        30.0,
    ),
    (
        "The company has 100 workers including 20 pilots and 10 auto workers, 50 belonging to a local union.",
        50.0,
        50.0,
        100.0,
        50.0,
    ),
    ("40 warehouse and 20 office workers are in a union.", 60.0, None, 60.0, 100.0),
    ("25 of 80 staff belong to a bargaining unit.", None, None, 80.0, None),
    ("We have 90 employees, and 10 are in a union.", 100.0, None, 100.0, 100.0),
    (
        "The company has 140 workers with 20 belonging to a local union.",
        20.0,
        120.0,
        140.0,
        14.29,
    ),
    (
        "The firm has 90 employees with 10 under a union contract.",
        10.0,
        80.0,
        90.0,
        11.11,
    ),
    ("Among 50 employees, labor contracts cover 20 of them.", 20.0, None, 50.0, 40.0),
    (
        "The firm has 150 staff; with 20 in a bargaining unit.",
        20.0,
        130.0,
        150.0,
        13.33,
    ),
]


@pytest.mark.parametrize(
    "sentence,exp_covered,exp_not_covered,exp_total,exp_pct",
    CASES,
)
def test_sentence_expected_counts(
    sentence,
    exp_covered,
    exp_not_covered,
    exp_total,
    exp_pct,
):
    result = UnionAnalyzer().analyze_paragraph(sentence)
    items = result.get("items", [])
    assert len(items) == 1
    cov = items[0].get("coverage_data", {})

    covered = cov.get("employee_count_covered")
    not_covered = cov.get("employee_count_not_covered")
    total = cov.get("employee_count_total")
    pct = cov.get("percentage")

    if exp_covered is None:
        pass
    else:
        assert covered == pytest.approx(exp_covered, abs=0.01)

    if exp_not_covered is None:
        pass
    else:
        assert not_covered == pytest.approx(exp_not_covered, abs=0.01)

    if exp_total is None:
        pass
    else:
        assert total == pytest.approx(exp_total, abs=0.01)

    if exp_pct is None:
        pass
    else:
        assert pct == pytest.approx(exp_pct, abs=0.01)
