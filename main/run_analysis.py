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
    run_custom_analyzers: bool = True
    run_disagreement_sampler: bool = False
    generate_sentence_files: bool = True


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
        # AccuracySampler is now initialized later with the correct data
        self.accuracy_sampler = None

        # Create AccuracyConfig from base Config
        self.accuracy_config = self._create_accuracy_config()

        # Registry for custom analyzers
        self.custom_analyzers: Dict[str, BaseAnalyzer] = {}
        self.custom_results: Dict[str, Dict[str, pd.DataFrame]] = {}

        # Map run options to pipeline methods for modular execution
        self._step_map = {
            "run_comparison": self._run_comparison_analysis,
            "run_custom_analyzers": self._run_custom_analyzers,
            "generate_sentence_files": self._run_sentence_generation,
            "run_accuracy_check": self._run_accuracy_check,
            "run_firm_inspector": self._run_firm_inspector,
            "run_disagreement_sampler": self._run_disagreement_sampler,
        }

        # Store data that needs to be passed between steps
        self._pipeline_data = {}
        self._data_loaded = False

    def _create_accuracy_config(self) -> AccuracyConfig:
        """Create an AccuracyConfig instance from the base Config"""
        # Copy all attributes from base config to accuracy config
        accuracy_config = AccuracyConfig()

        # Copy attributes from base config that are common
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

        # Ensure data is loaded before running steps
        if not self._data_loaded:
            print("⚠️ Data not loaded. Please run `pipeline.load_and_process_data()` first.")
            return

        # If no options are provided, use default RunOptions
        if options is None:
            options = RunOptions()

        # Reset comparison results if comparison is not being run, to use original model_agg_df
        if not options.run_comparison and "merged_df" in self._pipeline_data.get("comparison_results", {}):
            self._pipeline_data["model_agg_df"] = self._pipeline_data["original_model_agg_df"]

        # --- 2. Execute Optional Steps based on RunOptions ---
        for step_name, step_func in self._step_map.items():
            # Check if the step is enabled in the options
            if getattr(options, step_name, False):
                try:
                    step_func()
                except Exception as e:
                    print(f"     ❌ Error running step '{step_name}': {e}")
                    # Optionally, decide if you want to stop the pipeline on error
                    # raise e

        self._print_summary()

    def load_and_process_data(self):
        """
        Core data loading and processing step. This runs once to prepare the
        base data required by all other optional steps.
        """
        if self._data_loaded:
            print("ℹ️ Data has already been loaded. Skipping.")
            return

        # 1. Load data
        print("\n[1/4] Loading data...")
        model_df = self.data_loader.load_model_predictions()
        keyword_df = self.data_loader.load_keyword_data()

        # 2. Process model predictions
        print("\n[2/4] Processing predictions...")
        model_agg = self.predictions_processor.process_predictions(model_df)

        # Store data for other steps to use
        self._pipeline_data["model_df"] = model_df
        self._pipeline_data["keyword_df"] = keyword_df
        self._pipeline_data["model_agg_df"] = model_agg
        self._pipeline_data["original_model_agg_df"] = model_agg.copy() # Store a copy
        self._data_loaded = True

    def _run_comparison_analysis(self):
        """Runs the keyword vs. model comparison and saves the workbook."""
        print("\n[Extra] Running Keyword vs. Model Comparison...")
        comparison_analyzer = ComparisonAnalyzer(self.config, self.label_mapper)
        comparison_results = comparison_analyzer.analyze(
            keyword_df=self._pipeline_data["keyword_df"],
            model_df=self._pipeline_data["model_agg_df"],
        )

        # Write comparison workbook
        workbook_manager = WorkbookManager(self.config)
        workbook_manager.write_comparison_workbook(comparison_results)
        # Update the main aggregated dataframe with the merged results
        self._pipeline_data["model_agg_df"] = comparison_results.get("merged_df", self._pipeline_data["model_agg_df"])
        self._pipeline_data["comparison_results"] = comparison_results

    def _run_disagreement_sampler(self):
        """Runs the disagreement sampler if comparison results are available."""
        print("\n[Extra] Running Disagreement Sampler...")
        if "detailed" not in self._pipeline_data.get("comparison_results", {}):
            print("     ❌ Skipping: Disagreement sampler requires 'run_comparison' to be True.")
            return
        sampler = DisagreementSampler(self.config, self.label_mapper, self.data_loader)
        sampler.analyze(self._pipeline_data["comparison_results"]["detailed"])

    def _run_custom_analyzers(self):
        """Execute all registered custom analyzers."""
        print("\n[Extra] Running custom analyzers...")
        for name, analyzer in self.custom_analyzers.items():
            print(f"  -> Running '{name}'...")
            # Ensure the required data is available in the pipeline
            if "model_agg_df" not in self._pipeline_data:
                print(f"     ❌ Skipping '{name}': Required data 'model_agg_df' not found.")
                continue

            try:
                # Pass the aggregated model data to the custom analyzer's analyze method
                results = analyzer.analyze(data=self._pipeline_data["model_agg_df"])
                self.custom_results[name] = results
                print(f"     ✓ '{name}' completed successfully.")
            except Exception as e:
                print(f"     ❌ Error running '{name}': {e}")

    def _run_sentence_generation(self):
        """Generates labeled sentence files."""
        print("\n[Extra] Creating labeled sentence files (this may take a while)...")
        sentence_df = self.data_loader.load_sentence_data()
        # Use the aggregated model data which now contains keyword flags if comparison was run
        user_flags_df = self._pipeline_data["model_agg_df"]
        self.sentence_labeler.create_labeled_files(sentence_df, user_flags_df)

    def _run_accuracy_check(self):
        """Runs the accuracy sampling process."""
        print("\n[Extra] Running Accuracy Check...")
        # Initialize the accuracy sampler with AccuracyConfig and the aggregated data
        self.accuracy_sampler = AccuracySampler(
            self.accuracy_config, self.data_loader, self.label_mapper, self._pipeline_data["model_agg_df"]
        )
        self.accuracy_sampler.run()

    def _run_firm_inspector(self):
        """Runs the standalone firm inspector analysis."""
        print("\n[Extra] Running Firm Inspector...")
        inspector_config = URLAnalysisConfig()
        inspector = URLAnalyzer(inspector_config, self.label_mapper)
        inspector.run()

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
        run_comparison=True,
        run_disagreement_sampler=True,
        generate_sentence_files=False,
        run_accuracy_check=True,
        run_firm_inspector=True,
        run_custom_analyzers=False,
    )

    # Execute the pipeline with the chosen options
    pipeline.run(options=run_options)

# %%
