# %%
from custom_analyzers.analysis import (
    BaseAnalyzer,
    Config,
    DataLoader,
    LabelMapper,
    PredictionsProcessor,
    pd,
)
from custom_analyzers.comparison import ComparisonAnalyzer, WorkbookManager
from custom_analyzers.reporting import SentenceLabeler
from custom_analyzers.accuracy import AccuracySampler, AccuracyConfig
from custom_analyzers.disagreement_sampler import DisagreementSampler
from custom_analyzers.firm_inspector import URLAnalyzer, URLAnalysisConfig
from custom_analyzers.qualitative_sampler import QualitativeSampler
from custom_analyzers.key_firms_sampler import KeyFirmsSampler
from typing import Dict, Optional
from dataclasses import dataclass, field

# =============================================================================
# PIPELINE CONFIGURATION
# =============================================================================


@dataclass
class RunOptions:
    """Configuration for which pipeline steps to execute."""

    run_comparison: bool = False
    run_accuracy_check: bool = False
    run_firm_inspector: bool = False
    run_custom_analyzers: bool = False
    run_disagreement_sampler: bool = False
    generate_sentence_files: bool = True
    run_qualitative_sampler: bool = True
    run_key_firms_sampler: bool = True
    backup_server_results: bool = True


# =============================================================================
# ANALYSIS PIPELINE
# =============================================================================


class AnalysisPipeline:
    """Main analysis pipeline orchestrator"""

    def __init__(self, config: Config):
        self.config = config
        self.label_mapper = LabelMapper(config.keywords_json, config.labels)
        self.data_loader = DataLoader(config)
        self.predictions_processor = PredictionsProcessor(config, self.label_mapper)
        self.sentence_labeler = SentenceLabeler(config, self.label_mapper)

        # Create AccuracyConfig from base Config
        self.accuracy_config = self._create_accuracy_config()

        # Registry for custom analyzers
        self.custom_analyzers: Dict[str, BaseAnalyzer] = {}
        self.custom_results: Dict[str, Dict[str, pd.DataFrame]] = {}

        # Map run options to pipeline methods for modular execution
        self._step_map = {
            "backup_server_results": self._backup_server_results,
            # Fast analysis goes first
            "run_qualitative_sampler": self._run_qualitative_sampler,
            "run_firm_inspector": self._run_firm_inspector,
            "run_key_firms_sampler": self._run_key_firms_sampler,
            # Then slower ones
            "run_comparison": self._run_comparison_analysis,
            "run_custom_analyzers": self._run_custom_analyzers,
            # Run slowest ones last
            "run_accuracy_check": self._run_accuracy_check,
            "run_disagreement_sampler": self._run_disagreement_sampler,
            "generate_sentence_files": self._run_sentence_generation,
        }

        # Store data that needs to be passed between steps
        self._pipeline_data = {}
        self._data_loaded = False

    def _create_accuracy_config(self) -> AccuracyConfig:
        """Create an AccuracyConfig instance from the base Config"""
        accuracy_config = AccuracyConfig()

        for attr in dir(self.config):
            if not attr.startswith("_") and hasattr(accuracy_config, attr):
                setattr(accuracy_config, attr, getattr(self.config, attr))

        return accuracy_config

    def register_analyzer(self, name: str, analyzer: BaseAnalyzer):
        """Register a custom analyzer to run in the pipeline"""
        self.custom_analyzers[name] = analyzer
        print(f"✓ Registered custom analyzer: {name}")

    def run(self, options: Optional[RunOptions] = None):
        """Execute full analysis pipeline based on the provided run options."""
        print("=" * 70)
        print("MODULAR CLASSIFICATION ANALYSIS PIPELINE")
        print("=" * 70)

        if not self._data_loaded:
            print(
                "⚠️ Data not loaded. Please run `pipeline.load_and_process_data()` first."
            )
            return

        if options is None:
            options = RunOptions()

        # Reset comparison results if comparison is not being run
        if not options.run_comparison and "merged_df" in self._pipeline_data.get(
            "comparison_results", {}
        ):
            self._pipeline_data["model_agg_df"] = self._pipeline_data[
                "original_model_agg_df"
            ]

        # Execute optional steps based on RunOptions
        for step_name, step_func in self._step_map.items():
            if getattr(options, step_name, False):
                try:
                    step_func()
                except Exception as e:
                    print(f"     ❌ Error running step '{step_name}': {e}")

        self._print_summary()

    def load_and_process_data(self):
        """
        Core data loading and processing step.
        Now: loads model predictions and aggregates them.
        No longer: loads all sentence data (uses streaming instead).
        """
        if self._data_loaded:
            print("ℹ️ Data has already been loaded. Skipping.")
            return

        print("\n[1/3] Loading model predictions...")
        model_df = self.data_loader.load_model_predictions()

        print("\n[2/3] Processing predictions to firm-year level...")
        model_agg = self.predictions_processor.process_predictions(model_df)

        print("\n[3/3] Loading keyword data for comparison...")
        keyword_df = self.data_loader.load_keyword_data()

        # Store data for other steps
        self._pipeline_data["keyword_df"] = keyword_df
        self._pipeline_data["model_agg_df"] = model_agg
        self._pipeline_data["original_model_agg_df"] = model_agg.copy()
        self._data_loaded = True

        print(f"✅ Data loading complete")
        print(f"   - Model predictions: {len(model_df):,} records")
        print(f"   - Aggregated to firm-year: {len(model_agg):,} records")
        print(f"   - Keyword comparisons: {len(keyword_df):,} records")

    def _run_comparison_analysis(self):
        """Runs the keyword vs. model comparison and saves the workbook."""
        print("\n[Extra] Running Keyword vs. Model Comparison...")
        # This analyzer is now a standalone component with its own run method.
        comparison_analyzer = ComparisonAnalyzer(self.config, self.label_mapper)
        comparison_analyzer.run()

    def _backup_server_results(self):
        """Backs up the entire server_result table to an Excel file."""
        print("\n[Extra] Backing up server_result table...")
        try:
            # The existing data loader can fetch all model predictions, which is what we need.
            server_results_df = self.data_loader.load_model_predictions()
            output_path = self.config.output_dir / "server_results_backup.xlsx"
            temp_output_path = output_path.with_suffix('.xlsx.tmp')

            with pd.ExcelWriter(temp_output_path, engine="xlsxwriter") as writer:
                # Disable automatic URL conversion to prevent Excel's hyperlink limit error.
                writer.book.strings_to_urls = False
                server_results_df.to_excel(writer, index=False)
                
            # Atomically rename the temporary file to the final destination
            import os
            try:
                os.rename(temp_output_path, output_path)
            except: # Try replaceing
                os.replace(temp_output_path, output_path)
            print(f"   ✅ Server results backed up to: {output_path}")
        except Exception as e:
            print(f"     ❌ Error during server results backup: {e}")

    def _run_qualitative_sampler(self):
        """Runs the qualitative review sampler."""
        print("\n[Extra] Running Qualitative Review Sampler...")
        # This analyzer needs the merged comparison data to show both flags.
        # We'll create it here if it doesn't exist.
        if "merged_df" not in self._pipeline_data:
            print("   -> Merging keyword and model data for sampler...")
            keyword_df = self._pipeline_data["keyword_df"]
            model_agg_df = self._pipeline_data["model_agg_df"]
            merged_df = pd.merge(
                keyword_df, model_agg_df, on=["cik", "year"], how="outer"
            ).fillna(0)
            self._pipeline_data["merged_df"] = merged_df

        sampler = QualitativeSampler(
            self.config,
            self.label_mapper,
            only_terminated=False, # Set to True to filter for terminated reports
        )
        # The analyze method is called with the merged data
        sampler.analyze(data=self._pipeline_data["merged_df"])

    def _run_disagreement_sampler(self):
        """Runs the disagreement sampler if comparison results are available."""
        print("\n[Extra] Running Disagreement Sampler...")
        sampler = DisagreementSampler(
            config=self.config,
            label_mapper=self.label_mapper,
            data_loader=self.data_loader,
            sentence_df=None,  # No longer needed - uses streaming internally
        )
        sampler.run()

    def _run_custom_analyzers(self):
        """Execute all registered custom analyzers."""
        print("\n[Extra] Running custom analyzers...")
        for name, analyzer in self.custom_analyzers.items():
            print(f"  -> Running '{name}'...")
            # Custom analyzers are expected to have a `run` method if they are to be
            # executed independently in this pipeline.
            if "model_agg_df" not in self._pipeline_data:
                print(
                    f"     ❌ Skipping '{name}': Required data 'model_agg_df' not found."
                )
                continue

            try:
                results = analyzer.analyze(data=self._pipeline_data["model_agg_df"])
                self.custom_results[name] = results
                print(f"     ✓ '{name}' completed successfully.")
            except Exception as e:
                print(f"     ❌ Error running '{name}': {e}")

    def _run_sentence_generation(self):
        """Generates labeled sentence files using streaming (no need to load all sentences first)."""
        print(
            "\n[Extra] Creating labeled sentence files (streaming mode - memory efficient)..."
        )
        labeler = SentenceLabeler(self.config, self.label_mapper)
        labeler.run()

    def _run_accuracy_check(self):
        """Runs the accuracy sampling process using streaming."""
        print("\n[Extra] Running Accuracy Check (streaming mode - memory efficient)...")
        sampler = AccuracySampler(
            config=self.accuracy_config,
            data_loader=self.data_loader,
            label_mapper=self.label_mapper,
            sentence_df=None,  # No longer needed - uses streaming internally
            model_agg_df=None,  # Not used with streaming approach
        )
        sampler.run()

    def _run_firm_inspector(self):
        """Runs the standalone firm inspector analysis."""
        print("\n[Extra] Running Firm Inspector...")
        inspector_config = URLAnalysisConfig() # Uses its own config
        inspector = URLAnalyzer(inspector_config, self.label_mapper) # Initializes its own DataLoader
        inspector.run()

    def _run_key_firms_sampler(self):
        """Runs the new key firms sampler."""
        sampler = KeyFirmsSampler(self.config)
        sampler.run(model_agg_df=self._pipeline_data["model_agg_df"])

    def _print_summary(self):
        """Prints a final summary of the pipeline execution."""
        print("\n" + "=" * 70)
        print("ANALYSIS COMPLETE!")
        if self.custom_results:
            print("\nCustom Analysis Results:")
            for name, results in self.custom_results.items():
                print(f"  - {name}: Generated {len(results)} result table(s).")
        print(f"Results saved to: {self.config.output_dir}")
        print("=" * 70)


# %%
# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    # Initialize configuration
    config = Config()

    # Initialize the pipeline
    pipeline = AnalysisPipeline(config)

    # --- Step 1: Load and process data once ---
    pipeline.load_and_process_data()

    # %%
    # --- Step 2: Run the analysis with specific options ---
    # You can now re-run this cell with different options without reloading data.

    # Define which parts of the pipeline to run
    run_options = RunOptions(
        run_comparison=False,
        run_disagreement_sampler=False,
        generate_sentence_files=False,  # Now uses streaming - much faster!
        run_accuracy_check=False,  # Now uses streaming - much faster!
        run_firm_inspector=False,
        run_custom_analyzers=False,
        run_qualitative_sampler=True,
        run_key_firms_sampler=False,
        backup_server_results=True,
    )

    # %%
    # Interactive environment menu to load the run_options, run pipeline, or exit
    while True:
        print("=" * 70)   
        print("\nSelect an action:")
        print("  1. Run pipeline with current options")
        print("  2. Modify run options")
        print("  3. Exit")
        choice = input("Enter your choice (1-3): ") or "1"

        if choice == "1":
            pipeline.run(options=run_options)
        elif choice == "2":
            print("\n--- Modify Run Options ---")
            for attr in dir(run_options):
                if not attr.startswith("_") and not callable(getattr(run_options, attr)):
                    current_value = getattr(run_options, attr)
                    new_value_str = input(
                        f"  {attr} (current: {current_value}) [y/n/skip]: "
                    ).lower()
                    if new_value_str == "y":
                        setattr(run_options, attr, True)
                    elif new_value_str == "n":
                        setattr(run_options, attr, False)
                    # else: skip, keep current value
            print("Run options updated.")
        elif choice == "3":
            print("Exiting analysis pipeline.")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")        

# %%
