from defs.emp_sentence import render_employee_sentence
from defs.table_sentences import generate_primitive_sentences


def _build_table(
    headers: dict[int, str],
    col_types: dict[int, str],
    data: list[list[str]],
    caption: str,
    caption_year: int | None = None,
) -> dict:
    return {
        "data": data,
        "headers": headers,
        "types": col_types,  # mirror processor output
        "years": {},
        "row_years": {},
        "info": {
            "caption": caption,
            "caption_year": caption_year,
            "currency": "USD",
            "global_multiplier": 1.0,
            "column_types": col_types,
        },
    }


def _scenario_contract_open_for_amendment() -> dict:
    headers = {
        1: "Number of Employees",
        2: "Union (1)",
        3: "Contract Open for Amendment",
    }
    col_types = {1: "value", 2: "text", 3: "date"}
    data = [
        ["Pilots", "6,288", "ALPA", "January 1, 2010"],
        ["Flight Attendants", "15,392", "AFA", "January 7, 2010"],
        ["Mechanics & Related", "5,551", "AMFA", "January 1, 2010"],
        ["Dispatchers", "160", "PAFCA", "January 1, 2010"],
    ]
    return _build_table(headers, col_types, data, "Employee Groups", 2010)


def _scenario_covered_total_percent() -> dict:
    headers = {
        1: "Employees Covered by Labor Agreements",
        2: "Total Employees",
        3: "Percent Covered",
    }
    col_types = {1: "value", 2: "value", 3: "percentage"}
    data = [
        ["North America", "12,500", "20,000", "62.5%"],
        ["Europe", "4,400", "8,000", "55%"],
    ]
    return _build_table(headers, col_types, data, "Coverage by Region", 2024)


def _scenario_non_union_mix() -> dict:
    headers = {
        1: "Total Employees",
        2: "Non-union Employees",
        3: "Percent Covered",
    }
    col_types = {1: "value", 2: "value", 3: "percentage"}
    data = [
        ["Corporate", "50,000", "47,500", "5%"],
        ["Manufacturing", "25,000", "10,000", "60%"],
    ]
    return _build_table(headers, col_types, data, "Union Exposure Snapshot", 2024)


def _scenario_bargaining_units_with_contract_words() -> dict:
    headers = {
        1: "Employees Covered by Bargaining Units",
        2: "Number of Bargaining Units",
        3: "Collective Bargaining Agreements",
    }
    col_types = {1: "value", 2: "value", 3: "value"}
    data = [
        ["Air Operations", "18,200", "14", "22"],
        ["Ground Operations", "7,900", "9", "13"],
    ]
    return _build_table(headers, col_types, data, "Labor Relations Data", 2023)


def _scenario_bargaining_agreement_words() -> dict:
    headers = {
        1: "Collective Bargaining Agreements",
    }
    col_types = {1: "value"}
    data = [
        ["Air Operations", "10"],
        ["Ground Operations", "2"],
    ]
    return _build_table(headers, col_types, data, "Labor Relations Data", 2023)


def _scenario_union_name_column_fallback() -> dict:
    headers = {
        1: "Number of Employees",
        2: "Union",
        3: "Labor Contract Amendable",
    }
    col_types = {1: "value", 2: "text", 3: "date"}
    data = [
        ["Instructors", "2,240", "Independent Pilots Association", "March 15, 2026"],
        ["Schedulers", "600", "AFA-CWA", "April 2, 2026"],
        ["Engineers", "780", "Custom Engineers Guild", "June 1, 2026"],
    ]
    return _build_table(headers, col_types, data, "Union Representation", 2026)


def _scenario_works_council_representation() -> dict:
    headers = {
        1: "Employees Covered by Works Councils",
        2: "Total Employees",
        3: "Percent Covered",
    }
    col_types = {1: "value", 2: "value", 3: "percentage"}
    data = [
        ["Germany", "2,200", "3,400", "64.7%"],
        ["France", "1,500", "2,100", "71.4%"],
    ]
    return _build_table(headers, col_types, data, "Works Council Representation", 2024)


def _scenario_mixed_covered_realistic() -> dict:
    headers = {
        1: "Employees Covered by Labor Agreements",
        2: "Employees Covered by Works Councils",
        3: "Total Employees",
        4: "Percent Covered",
        5: "Non-union Employees",
    }
    col_types = {1: "value", 2: "value", 3: "value", 4: "percentage", 5: "value"}
    data = [
        ["Germany Operations", "2,900", "1,100", "5,000", "80%", "1,000"],
        ["France Operations", "1,700", "600", "3,000", "76.7%", "700"],
        ["Italy Operations", "1,200", "300", "2,100", "71.4%", "600"],
    ]
    return _build_table(headers, col_types, data, "Mixed Coverage Snapshot", 2024)


def _scenario_date_noise_only() -> dict:
    headers = {
        1: "Contract Expiration Date",
        2: "Amendable Date",
        3: "Status",
    }
    col_types = {1: "date", 2: "date", 3: "text"}
    data = [
        ["Pilots", "January 1, 2027", "January 1, 2025", "Open"],
        ["Flight Attendants", "February 1, 2028", "February 1, 2026", "Open"],
    ]
    return _build_table(headers, col_types, data, "Contract Milestones", 2026)


def run_test():
    scenarios = [
        ("Contract Open for Amendment", _scenario_contract_open_for_amendment()),
        ("Covered / Total / Percent", _scenario_covered_total_percent()),
        ("Non-union Mix", _scenario_non_union_mix()),
        ("BU + Contract Words", _scenario_bargaining_units_with_contract_words()),
        ("Union Name Fallback", _scenario_union_name_column_fallback()),
        ("Works Council Representation", _scenario_works_council_representation()),
        ("Mixed Covered Realistic", _scenario_mixed_covered_realistic()),
        ("Agreement Words", _scenario_bargaining_agreement_words()),
        ("Date Noise Only", _scenario_date_noise_only()),
    ]

    for name, processed_table in scenarios:
        print(f"\n=== Scenario: {name} ===")
        sentences = generate_primitive_sentences(
            processed_table, renderer=render_employee_sentence
        )
        if not sentences:
            print("(no sentences generated)")
            continue
        for s in sentences:
            print(s)


if __name__ == "__main__":
    run_test()
