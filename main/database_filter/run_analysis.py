# run_analysis.py
import sys
import argparse
from pathlib import Path
from custom_analyzers.analysis import Config
from custom_analyzers.qualitative_sampler import QualitativeSampler
from custom_analyzers.comparison import ComparisonAnalyzer


def run_sampler_mode(db_path, sample_size=50):
    """Generates an HTML visualizer for the specific DB."""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"❌ DB not found: {db_path}")
        return

    print(f"\n🔎 SAMPLING: {db_path.name}")

    # Initialize Config with the specific DB
    config = Config(db_path=str(db_path))

    # Run Sampler
    sampler = QualitativeSampler(config, sample_size=sample_size)
    sampler.analyze()


def run_comparison_mode(file_a, file_b):
    """Generates an Excel Diff report between two CSVs."""
    # Config defaults are fine here as we pass paths manually
    config = Config()

    analyzer = ComparisonAnalyzer(config)
    analyzer.compare_checkpoints(file_a, file_b)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline Analysis Tool")
    subparsers = parser.add_subparsers(dest="command", help="Action to perform")

    # Command: sample
    # Usage: python run_analysis.py sample active_data.db
    p_sample = subparsers.add_parser("sample", help="Generate HTML visual sample")
    p_sample.add_argument("db_path", help="Path to SQLite database")
    p_sample.add_argument("--size", type=int, default=50, help="Sample size")

    # Command: compare
    # Usage: python run_analysis.py compare 1.csv 2.csv
    p_compare = subparsers.add_parser("compare", help="Compare two CSV checkpoints")
    p_compare.add_argument("file_a", help="First CSV file (Start)")
    p_compare.add_argument("file_b", help="Second CSV file (End)")

    args = parser.parse_args()

    if args.command == "sample":
        run_sampler_mode(args.db_path, args.size)
    elif args.command == "compare":
        run_comparison_mode(args.file_a, args.file_b)
    else:
        parser.print_help()
