# =============================================================================
# MNLI CLASSIFICATION ANALYSIS PIPELINE
# =============================================================================
# Comprehensive analysis framework for MNLI-based derivative classification
# Supports multiple analyzers, streaming data processing, and modular execution
# =============================================================================

import pandas as pd
import json
import sqlite3
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing as mp

# =============================================================================
# CONFIGURATION
# =============================================================================
CONFIG_FILE = "mnli_pipeline_config.json"

@dataclass
class AnalysisConfig:
    """Centralized configuration for MNLI analysis pipeline"""

    # Database paths
    db_path: str = "clean_web_data.db"

    # Output configuration
    output_dir: Path = field(default_factory=lambda: Path("./mnli_analysis_output"))
    comparison_excel: str = "mnli_keyword_comparison.xlsx"

    # Google Colab / Drive settings
    drive_path: str = "./drive/MyDrive/db"
    is_colab: Optional[bool] = None

    # Processing settings
    num_workers: int = field(default_factory=mp.cpu_count)
    chunk_size: int = 1000

    # Category mappings
    category_mapping: Dict[str, str] = field(
        default_factory=lambda: {
            "ir": "Interest Rate",
            "fx": "Foreign Exchange",
            "cp": "Commodity",
            "eq": "Equity",
        }
    )

    # Finding types
    finding_types: List[str] = field(
        default_factory=lambda: ["policy", "existence", "notional", "pnl"]
    )

    def __post_init__(self):
        """Auto-configure based on environment"""
        # Detect Colab
        if self.is_colab is None:
            self.is_colab = Path(self.drive_path).exists()

        if self.is_colab:
            print("🔵 Running in Google Colab environment")
            drive_root = Path(self.drive_path)
            self.output_dir = drive_root / "mnli_analysis_output"

        # Create output directory
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"💾 Output directory: {self.output_dir}")


# =============================================================================
# DATA LOADER
# =============================================================================


class MNLIDataLoader:
    """Handles loading data from the MNLI classification database"""

    def __init__(self, config: AnalysisConfig):
        self.config = config

    def _get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.config.db_path)

    def load_classification_results(self) -> pd.DataFrame:
        """Load all classification results"""
        query = """
            SELECT 
                url, cik, year, category,
                found_policy, found_existence, found_notional, found_pnl,
                status, duration_s, error_message
            FROM classification_results
        """

        conn = self._get_connection()
        df = pd.read_sql(query, conn)
        conn.close()

        # Parse JSON arrays
        for col in self.config.finding_types:
            col_name = f"found_{col}"
            df[col_name] = df[col_name].apply(self._parse_json_array)

        return df

    def load_keyword_data(self) -> pd.DataFrame:
        """
        Load keyword-based derivatives data from the original database.
        This assumes you have a derivatives_data.csv or similar from keyword extraction.
        """
        # Adjust this path based on your actual keyword data location
        keyword_path = Path("./derivatives_data.csv")

        if not keyword_path.exists():
            print("⚠️  Keyword data file not found. Creating empty DataFrame.")
            return pd.DataFrame(
                columns=["cik", "year", "ir_user", "fx_user", "cp_user", "user"]
            )

        df = pd.read_csv(keyword_path)
        df["cik"] = df["cik"].astype(int)

        # Aggregate to cik-year level
        keyword_flags = (
            df.groupby(["cik", "year"])[["user", "fx_user", "ir_user", "cp_user"]]
            .max()
            .reset_index()
        )

        return keyword_flags

    def get_sentences_for_url(self, url: str, category: str) -> List[str]:
        """Retrieve sentences for a specific URL and category"""
        conn = self._get_connection()
        c = conn.cursor()

        # Map category short name to database column
        category_col_map = {
            "ir": "ir_matches",
            "fx": "fx_matches",
            "cp": "cp_matches",
            "eq": "eq_matches",
        }

        col_name = category_col_map.get(category)
        if not col_name:
            return []

        c.execute(f"SELECT {col_name} FROM derivative_type_matches WHERE url=?", (url,))
        result = c.fetchone()
        conn.close()

        if not result or not result[0]:
            return []

        return self._parse_json_array(result[0])

    @staticmethod
    def _parse_json_array(value: Any) -> List:
        """Safely parse JSON array"""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return []
        elif isinstance(value, list):
            return value
        return []


# =============================================================================
# RESULTS PROCESSOR
# =============================================================================


class ResultsProcessor:
    """Processes MNLI classification results into analysis-ready format"""

    def __init__(self, config: AnalysisConfig):
        self.config = config

    def aggregate_to_firm_year(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate classification results to firm-year level.
        Creates binary flags for each finding type and category combination.
        """
        print("Aggregating results to firm-year level...")

        # Create binary flags for findings
        for finding_type in self.config.finding_types:
            col_name = f"found_{finding_type}"
            results_df[f"has_{finding_type}"] = results_df[col_name].apply(
                lambda x: 1 if len(x) > 0 else 0
            )

        # Aggregate by (cik, year, category)
        agg_dict = {f"has_{ft}": "max" for ft in self.config.finding_types}
        agg_dict["url"] = "first"  # Keep one URL for reference
        agg_dict["duration_s"] = "mean"

        category_level = (
            results_df.groupby(["cik", "year", "category"]).agg(agg_dict).reset_index()
        )

        # Pivot to get category-specific columns
        pivot_data = []
        for finding_type in self.config.finding_types:
            pivot = category_level.pivot_table(
                index=["cik", "year"],
                columns="category",
                values=f"has_{finding_type}",
                fill_value=0,
            )
            # Rename columns to include finding type
            pivot.columns = [f"mnli_{cat}_{finding_type}" for cat in pivot.columns]
            pivot_data.append(pivot)

        # Combine all pivoted data
        firm_year_df = pd.concat(pivot_data, axis=1).reset_index()

        # Create "user" flags (has evidence of usage)
        # A firm is a "user" if they have existence OR pnl evidence
        for cat in ["ir", "fx", "cp", "eq"]:
            existence_col = f"mnli_{cat}_existence"
            pnl_col = f"mnli_{cat}_pnl"

            if (
                existence_col in firm_year_df.columns
                and pnl_col in firm_year_df.columns
            ):
                firm_year_df[f"mnli_{cat}_user"] = (
                    (firm_year_df[existence_col] == 1) | (firm_year_df[pnl_col] == 1)
                ).astype(int)

        # Create overall user flag (any derivative usage)
        user_cols = [col for col in firm_year_df.columns if col.endswith("_user")]
        if user_cols:
            firm_year_df["mnli_user"] = firm_year_df[user_cols].max(axis=1)

        print(f"✅ Aggregated to {len(firm_year_df):,} firm-year observations")

        return firm_year_df


# =============================================================================
# BASE ANALYZER
# =============================================================================


class BaseAnalyzer:
    """Base class for all analyzers"""

    def __init__(self, config: AnalysisConfig):
        self.config = config

    def analyze(self, data: pd.DataFrame, **kwargs) -> Dict[str, pd.DataFrame]:
        """Override this method in subclasses"""
        raise NotImplementedError("Subclasses must implement analyze()")


# =============================================================================
# COMPARISON ANALYZER
# =============================================================================


class ComparisonAnalyzer(BaseAnalyzer):
    """Compares MNLI results with keyword-based classifications"""

    def merge_data(
        self, keyword_df: pd.DataFrame, mnli_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Merge keyword and MNLI data"""
        merged = pd.merge(mnli_df, keyword_df, on=["cik", "year"], how="inner")

        # Fill NaN with 0 for flag columns
        flag_cols = [col for col in merged.columns if col not in ["cik", "year", "url"]]
        merged[flag_cols] = merged[flag_cols].fillna(0).astype(int)

        return merged

    def calculate_metrics(
        self, keyword_col: str, mnli_col: str, df: pd.DataFrame
    ) -> Dict:
        """Calculate confusion matrix metrics"""
        tp = ((df[keyword_col] == 1) & (df[mnli_col] == 1)).sum()
        fp = ((df[keyword_col] == 0) & (df[mnli_col] == 1)).sum()
        tn = ((df[keyword_col] == 0) & (df[mnli_col] == 0)).sum()
        fn = ((df[keyword_col] == 1) & (df[mnli_col] == 0)).sum()

        total = len(df)
        accuracy = (tp + tn) / total if total > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        return {
            "True_Positives": int(tp),
            "False_Positives": int(fp),
            "True_Negatives": int(tn),
            "False_Negatives": int(fn),
            "Total": int(total),
            "Accuracy": round(accuracy * 100, 2),
            "Precision": round(precision * 100, 2),
            "Recall": round(recall * 100, 2),
            "F1_Score": round(f1 * 100, 2),
        }

    def analyze(
        self, keyword_df: pd.DataFrame, mnli_df: pd.DataFrame, **kwargs
    ) -> Dict[str, pd.DataFrame]:
        """Generate comprehensive comparison report"""
        merged_df = self.merge_data(keyword_df, mnli_df)

        print(f"Generating comparison metrics for {len(merged_df):,} firm-years...")

        comparisons = {
            "IR Users": ("ir_user", "mnli_ir_user"),
            "FX Users": ("fx_user", "mnli_fx_user"),
            "CP Users": ("cp_user", "mnli_cp_user"),
            "Overall Users": ("user", "mnli_user"),
        }

        results = {}
        summary_data = []

        for name, (kw_col, mnli_col) in comparisons.items():
            if kw_col not in merged_df.columns or mnli_col not in merged_df.columns:
                print(f"⚠️  Skipping {name}: columns not found")
                continue

            metrics = self.calculate_metrics(kw_col, mnli_col, merged_df)
            summary_data.append({"Category": name, **metrics})

            # Create confusion matrix
            confusion = pd.crosstab(
                merged_df[kw_col].map({0: "Keyword_No", 1: "Keyword_Yes"}),
                merged_df[mnli_col].map({0: "MNLI_No", 1: "MNLI_Yes"}),
                rownames=["Keyword"],
                colnames=["MNLI"],
                margins=True,
            )

            results[f'confusion_{name.lower().replace(" ", "_")}'] = confusion

        results["summary"] = pd.DataFrame(summary_data)
        results["merged_df"] = merged_df

        # Create detailed view with classifications
        detailed_df = merged_df.copy()
        for name, (kw_col, mnli_col) in comparisons.items():
            if kw_col not in merged_df.columns or mnli_col not in merged_df.columns:
                continue

            conditions = [
                (detailed_df[kw_col] == 1) & (detailed_df[mnli_col] == 1),
                (detailed_df[kw_col] == 0) & (detailed_df[mnli_col] == 0),
                (detailed_df[kw_col] == 0) & (detailed_df[mnli_col] == 1),
            ]
            choices = ["True Positive", "True Negative", "False Positive"]
            col_name = f'class_{name.lower().replace(" ", "_")}'
            detailed_df[col_name] = np.select(
                conditions, choices, default="False Negative"
            )

        results["detailed"] = detailed_df

        print(f"✅ Comparison analysis complete")
        return results


# =============================================================================
# FINDING STATISTICS ANALYZER
# =============================================================================


class FindingStatsAnalyzer(BaseAnalyzer):
    """Analyzes patterns in MNLI findings (notional, policy, etc.)"""

    def analyze(self, data: pd.DataFrame, **kwargs) -> Dict[str, pd.DataFrame]:
        """Generate statistics about findings"""
        results_df = kwargs.get("results_df")
        if results_df is None:
            print("⚠️  Need raw results_df with array data")
            return {}

        print("Analyzing finding patterns...")

        stats = []
        for category in ["ir", "fx", "cp", "eq"]:
            cat_df = results_df[results_df["category"] == category]

            if len(cat_df) == 0:
                continue

            row = {"category": category, "total_records": len(cat_df)}

            for finding_type in self.config.finding_types:
                col_name = f"found_{finding_type}"

                # Count records with findings
                with_findings = (cat_df[col_name].apply(len) > 0).sum()
                row[f"{finding_type}_count"] = with_findings
                row[f"{finding_type}_pct"] = round(with_findings / len(cat_df) * 100, 2)

                # Average number of matches per record (when found)
                lengths = cat_df[col_name].apply(len)
                avg_matches = lengths[lengths > 0].mean() if (lengths > 0).any() else 0
                row[f"{finding_type}_avg_matches"] = round(avg_matches, 2)

            stats.append(row)

        stats_df = pd.DataFrame(stats)

        print("✅ Finding statistics complete")
        return {"finding_stats": stats_df}


# =============================================================================
# WORKBOOK MANAGER
# =============================================================================


class WorkbookManager:
    """Manages writing analysis results to Excel"""

    def __init__(self, config: AnalysisConfig):
        self.config = config

    def write_workbook(self, results: Dict[str, pd.DataFrame], filename: str):
        """Write results to Excel workbook"""
        output_path = self.config.output_dir / filename
        print(f"\nWriting workbook to {output_path}...")

        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
            writer.book.strings_to_urls = False

            # Write each result to a separate sheet
            for sheet_name, df in results.items():
                # Truncate sheet names to 31 chars (Excel limit)
                safe_name = sheet_name[:31]
                is_index = sheet_name.startswith("confusion_")
                df.to_excel(writer, sheet_name=safe_name, index=is_index)

        print(f"✅ Workbook saved: {output_path}")


# =============================================================================
# MAIN PIPELINE
# =============================================================================


@dataclass
class RunOptions:
    """Configuration for which pipeline steps to execute"""

    run_comparison: bool = True
    run_finding_stats: bool = True
    export_detailed_results: bool = True


class MNLIAnalysisPipeline:
    """Main analysis pipeline orchestrator"""

    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.data_loader = MNLIDataLoader(config)
        self.processor = ResultsProcessor(config)
        self.workbook_manager = WorkbookManager(config)

        self._data_loaded = False
        self._pipeline_data = {}

    def load_data(self):
        """Load and process all necessary data"""
        if self._data_loaded:
            print("ℹ️  Data already loaded")
            return

        print("\n[1/3] Loading MNLI classification results...")
        results_df = self.data_loader.load_classification_results()
        self._pipeline_data["results_df"] = results_df

        print("\n[2/3] Aggregating to firm-year level...")
        firm_year_df = self.processor.aggregate_to_firm_year(results_df)
        self._pipeline_data["firm_year_df"] = firm_year_df

        print("\n[3/3] Loading keyword data...")
        keyword_df = self.data_loader.load_keyword_data()
        self._pipeline_data["keyword_df"] = keyword_df

        self._data_loaded = True
        print(f"\n✅ Data loading complete")
        print(f"   - Classification results: {len(results_df):,} records")
        print(f"   - Firm-year level: {len(firm_year_df):,} records")
        print(f"   - Keyword data: {len(keyword_df):,} records")

    def run(self, options: RunOptions = RunOptions()):
        """Execute analysis pipeline"""
        print("=" * 70)
        print("MNLI CLASSIFICATION ANALYSIS PIPELINE")
        print("=" * 70)

        if not self._data_loaded:
            self.load_data()

        all_results = {}

        # Run comparison analysis
        if options.run_comparison:
            print("\n[Analysis] Running Keyword vs. MNLI Comparison...")
            analyzer = ComparisonAnalyzer(self.config)
            comparison_results = analyzer.analyze(
                keyword_df=self._pipeline_data["keyword_df"],
                mnli_df=self._pipeline_data["firm_year_df"],
            )
            all_results.update(comparison_results)

            # Write comparison workbook
            self.workbook_manager.write_workbook(
                comparison_results, self.config.comparison_excel
            )

        # Run finding statistics
        if options.run_finding_stats:
            print("\n[Analysis] Analyzing Finding Patterns...")
            stats_analyzer = FindingStatsAnalyzer(self.config)
            stats_results = stats_analyzer.analyze(
                data=self._pipeline_data["firm_year_df"],
                results_df=self._pipeline_data["results_df"],
            )
            all_results.update(stats_results)

            # Write stats workbook
            if stats_results:
                self.workbook_manager.write_workbook(
                    stats_results, "finding_statistics.xlsx"
                )

        # Export detailed results
        if options.export_detailed_results:
            print("\n[Export] Writing detailed results...")
            detailed = {
                "classification_results": self._pipeline_data["results_df"],
                "firm_year_aggregated": self._pipeline_data["firm_year_df"],
            }
            self.workbook_manager.write_workbook(detailed, "detailed_results.xlsx")

        self._print_summary()
        return all_results

    def _print_summary(self):
        """Print pipeline execution summary"""
        print("\n" + "=" * 70)
        print("ANALYSIS COMPLETE!")
        print(f"Results saved to: {self.config.output_dir}")
        print("=" * 70)


# =============================================================================
# CONFIGURATION MANAGER
# =============================================================================


class PipelineConfigManager:
    """Handles loading and saving of the mnli_pipeline_config.json file"""

    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = Path(config_path)
        self.config_data = self._load_config()

    def _create_default_config(self) -> Dict:
        """Creates a default configuration file if one doesn't exist"""
        print(f"-> No config file found. Creating default '{self.config_path}'...")

        # Dynamically get configurable arguments from analyzer classes
        analyzer_classes = {
            "finding_stats": FindingStatsAnalyzer,
            "comparison": ComparisonAnalyzer,
        }

        analyzer_args = {
            name: self._get_configurable_args(cls)
            for name, cls in analyzer_classes.items()
        }

        default_config = {
            "run_options": asdict(RunOptions()),
            "analyzer_args": analyzer_args,
            "global_config": {
                "db_path": "clean_web_data.db",
                "output_dir": "./mnli_analysis_output",
                "comparison_excel": "mnli_keyword_comparison.xlsx",
                "num_workers": mp.cpu_count(),
                "chunk_size": 1000,
            },
        }

        self.save_config(default_config)
        return default_config

    def _get_configurable_args(self, cls) -> Dict:
        """Extract configurable arguments from a class's __init__ method"""
        import inspect

        args = {}
        try:
            sig = inspect.signature(cls.__init__)
            for param in sig.parameters.values():
                # Skip standard parameters
                if param.name in ["self", "config"]:
                    continue
                # Only include parameters with defaults
                if param.default is not inspect.Parameter.empty:
                    args[param.name] = param.default
        except (TypeError, ValueError):
            pass
        return args

    def _load_config(self) -> Dict:
        """Loads the configuration from the JSON file"""
        if not self.config_path.exists():
            return self._create_default_config()

        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"⚠️  Error reading config file: {e}")
            print("   Creating backup and generating new default config...")
            backup_path = self.config_path.with_suffix(".json.backup")
            self.config_path.rename(backup_path)
            return self._create_default_config()

    def save_config(self, config_data: Optional[Dict] = None):
        """Saves the configuration to the JSON file"""
        data_to_save = config_data if config_data is not None else self.config_data
        with open(self.config_path, "w") as f:
            json.dump(data_to_save, f, indent=2)
        print(f"   ✅ Configuration saved to '{self.config_path}'")

    def get_run_options(self) -> RunOptions:
        """Get RunOptions from config file"""
        options_dict = self.config_data.get("run_options", {})
        return RunOptions(**options_dict)

    def apply_global_config(self, config: AnalysisConfig):
        """Apply global settings from config file to AnalysisConfig object"""
        global_settings = self.config_data.get("global_config", {})
        for key, value in global_settings.items():
            if hasattr(config, key):
                setattr(config, key, value)


# =============================================================================
# ENHANCED PIPELINE WITH CONFIG FILE SUPPORT
# =============================================================================


class MNLIAnalysisPipelineWithConfig(MNLIAnalysisPipeline):
    """Enhanced pipeline with configuration file support"""

    def __init__(self, config: AnalysisConfig, config_manager: PipelineConfigManager):
        super().__init__(config)
        self.config_manager = config_manager

        # Apply global config settings
        self.config_manager.apply_global_config(self.config)

        # Recreate components with updated config
        self.data_loader = MNLIDataLoader(self.config)
        self.processor = ResultsProcessor(self.config)
        self.workbook_manager = WorkbookManager(self.config)

    def run_interactive(self):
        """Run pipeline with interactive menu"""
        while True:
            # Reload config at the start of each loop
            self.config_manager.config_data = self.config_manager._load_config()
            run_options_dict = self.config_manager.config_data.get("run_options", {})

            print("\n" + "=" * 70)
            print("MNLI ANALYSIS PIPELINE - Current Configuration")
            print("=" * 70)
            print("\nRun Options:")
            for key, value in run_options_dict.items():
                status = "✅ Enabled" if value else "❌ Disabled"
                print(f"  - {key:<30}: {status}")

            print("\n" + "=" * 70)
            print("Select an action:")
            print("  1. Load/Reload data")
            print("  2. Run pipeline with current options")
            print("  3. Reload configuration from file")
            print("  4. Show data summary")
            print("  5. Exit")
            print("=" * 70)

            choice = input("\nEnter your choice (1-5): ").strip() or "2"

            if choice == "1":
                print("\n🔄 Loading data...")
                self.load_data()

            elif choice == "2":
                if not self._data_loaded:
                    print("\n⚠️  Data not loaded. Loading now...")
                    self.load_data()

                print("\n🚀 Running pipeline...")
                options = self.config_manager.get_run_options()
                self.run(options)

            elif choice == "3":
                print("\n🔄 Reloading configuration...")
                self.config_manager.config_data = self.config_manager._load_config()
                self.config_manager.apply_global_config(self.config)
                print("   ✅ Configuration reloaded")

            elif choice == "4":
                if not self._data_loaded:
                    print("\n⚠️  No data loaded yet. Please load data first (option 1).")
                else:
                    self._print_data_summary()

            elif choice == "5":
                print("\n👋 Exiting pipeline. Goodbye!")
                break

            else:
                print("\n❌ Invalid choice. Please enter 1-5.")

    def _print_data_summary(self):
        """Print summary of loaded data"""
        print("\n" + "=" * 70)
        print("DATA SUMMARY")
        print("=" * 70)

        if "results_df" in self._pipeline_data:
            results_df = self._pipeline_data["results_df"]
            print(f"\n📊 Classification Results:")
            print(f"   Total records: {len(results_df):,}")
            print(f"   Unique firms: {results_df['cik'].nunique():,}")
            print(
                f"   Year range: {results_df['year'].min()}-{results_df['year'].max()}"
            )
            print(f"\n   By Category:")
            print(results_df["category"].value_counts().to_string())

            print(f"\n   By Status:")
            print(results_df["status"].value_counts().to_string())

            # Finding statistics
            print(f"\n   Finding Statistics:")
            for finding_type in self.config.finding_types:
                col_name = f"found_{finding_type}"
                count = (results_df[col_name].apply(len) > 0).sum()
                pct = count / len(results_df) * 100
                print(f"   - {finding_type:12}: {count:5,} ({pct:5.2f}%)")

        if "firm_year_df" in self._pipeline_data:
            firm_year_df = self._pipeline_data["firm_year_df"]
            print(f"\n📈 Firm-Year Level:")
            print(f"   Total observations: {len(firm_year_df):,}")

            user_cols = [col for col in firm_year_df.columns if col.endswith("_user")]
            for col in user_cols:
                count = firm_year_df[col].sum()
                pct = count / len(firm_year_df) * 100
                print(f"   - {col:20}: {count:5,} ({pct:5.2f}%)")

        if "keyword_df" in self._pipeline_data:
            keyword_df = self._pipeline_data["keyword_df"]
            print(f"\n🔑 Keyword Data:")
            print(f"   Total observations: {len(keyword_df):,}")

        print("=" * 70)


# =============================================================================
# ENTRY POINT
# =============================================================================


if __name__ == "__main__":
    # Initialize configuration manager
    config_manager = PipelineConfigManager(CONFIG_FILE)

    # Initialize analysis configuration
    config = AnalysisConfig()

    # Create pipeline with config file support
    pipeline = MNLIAnalysisPipelineWithConfig(config, config_manager)

    # Run interactive menu
    pipeline.run_interactive()
