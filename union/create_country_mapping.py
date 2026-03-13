import argparse
import csv
from pathlib import Path

from defs.region_regex import (
    ASIA_PACIFIC,
    EUROPE,
    INTERNATIONAL,
    LATIN_AMERICA,
    MIDDLE_EAST_AFRICA,
    NORTH_AMERICA,
    REGION_NAME_MAP,
)


def build_rows():
    rows = []
    region_sets = [
        NORTH_AMERICA,
        EUROPE,
        ASIA_PACIFIC,
        LATIN_AMERICA,
        MIDDLE_EAST_AFRICA,
        INTERNATIONAL,
    ]
    for region_set in region_sets:
        for nation in region_set:
            if not nation.code:
                continue
            rows.append(
                {
                    "code": nation.code,
                    "country": nation.name,
                    "region": nation.region.value,
                    "region_code": REGION_NAME_MAP.get(
                        nation.region.value, nation.region.value
                    ),
                }
            )
    rows.sort(key=lambda r: r["code"])
    return rows


def write_csv(rows, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["code", "country", "region", "region_code"]
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export country/region mapping from defs.region_regex."
    )
    parser.add_argument(
        "--output",
        default="country_mapping.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    rows = build_rows()
    write_csv(rows, Path(args.output))


if __name__ == "__main__":
    main()
