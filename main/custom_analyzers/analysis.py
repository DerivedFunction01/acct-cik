# %%
import pandas as pd
import json
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm
import multiprocessing as mp
import psutil
from contextlib import contextmanager
from .classification_engine import ClassificationEngine

# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class Config:
    """Centralized configuration"""

    # Database and file paths
    db_path: str = "web_data.db"
    derivatives_csv: str = "./derivatives_data.csv"
    keywords_json: str = "./keywords_find.json"

    # Output paths
    output_dir: Path = field(default_factory=lambda: Path("./analysis_output"))
    comparison_excel: str = "keyword_model_comparison.xlsx"
    sentences_dir: str = "labeled_sentences"

    # Google Colab / Drive settings
    drive_path: str = "./drive/MyDrive/db"
    is_colab: Optional[bool] = None

    # Model settings
    confidence_threshold: float = 0.65
    soft_confidence_threshold: float = 0.50
    termination_threshold: float = 0.80
    term_curr_ratio: float = 1.0 # More mentions of termination than current means terminated
    display_threshold: float = 0.30 # For display purposes

    # Multi-label names (from training)
    labels: Optional[List[str]] = None

    # Processing settings
    num_workers: int = field(default_factory=mp.cpu_count)
    chunk_size: int = 1000

    def __post_init__(self):
        """Dynamically configure settings based on system resources."""
        # System resource detection
        cpu_cores = mp.cpu_count()
        ram_gb = psutil.virtual_memory().total / (1024**3)
        print(f"🖥️  System Detected: {cpu_cores} CPU cores, {ram_gb:.2f} GB RAM")

        # Set num_workers based on CPU cores
        self.num_workers = cpu_cores

        # Set chunk_size based on RAM
        if ram_gb > 32:  # High-RAM machine
            self.chunk_size = 10000
        elif ram_gb > 16:  # Medium-RAM machine
            self.chunk_size = 5000
        else:  # Low-RAM machine
            self.chunk_size = 2000

        print(
            f"⚙️  Configuration: NUM_WORKERS={self.num_workers}, CHUNK_SIZE={self.chunk_size}"
        )

        # Detect Colab environment
        if self.is_colab is None:
            self.is_colab = Path(self.drive_path).exists()

        if self.is_colab:
            print("🔵 Running in Google Colab environment")
            if not Path(self.db_path).exists():
                print(
                    f"📥 Loading database from Google Drive: {self.drive_path}/{self.db_path}"
                )
                import subprocess

                subprocess.run(f"cp {self.drive_path}/{self.db_path} .", shell=True)
            drive_root = Path(self.drive_path)
            self.output_dir = drive_root / "analysis_output"
            print(f"💾 Setting output directory to Google Drive: {self.output_dir}")
        else:
            print("💻 Running in local environment")

        # Create output directories
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        sentences_path = self.output_dir / self.sentences_dir
        sentences_path.mkdir(parents=True, exist_ok=True)

        if self.labels is None:
            self.labels = [
                "ir",
                "fx",
                "cp",
                "eq",
                "gen",
                "ir_use",
                "fx_use",
                "cp_use",
                "eq_use",
                "gen_use",
                "curr",
                "hist",
                "term",
                "spec",
                "warr",
                "emb",
                "irr",
            ]


# =============================================================================
# LABEL MAPPING
# =============================================================================


class LabelMapper:
    """
    Backward-compatibility shim for LabelMapper.
    This class now delegates all classification logic to the centralized
    ClassificationEngine to ensure consistency.
    """

    def __init__(
        self,
        keywords_json_path: str,
        multi_labels: Optional[List[str]],
        config: Optional[Config] = None,
    ):
        print("⚠️  LabelMapper is now using ClassificationEngine internally.")
        print("    Consider migrating to ClassificationEngine directly for new code.")
        self.config = config
        self.engine = ClassificationEngine(config)
        self.primary_id2label = self.engine.primary_id2label
        self.primary_label2id = {v: k for k, v in self.primary_id2label.items()}

    def get_primary_labels_with_confidence(
        self, labels_dict: Dict[str, float]
    ) -> List[Tuple[str, float, str]]:
        display_labels = self.engine._get_display_labels(
            labels_dict, self.engine._get_active_flags(labels_dict)
        )
        output = []
        for label_name, confidence in display_labels:
            if confidence >= 0.75:
                tier = "high"
            elif confidence >= 0.5:
                tier = "medium"
            else:
                tier = "low"
            output.append((label_name, confidence, tier))
        return output

    def get_primary_labels(self, labels_dict: Dict[str, float]) -> List[str]:
        """Returns a prioritized list of primary label names."""
        sent_class = self.engine.classify_sentence(labels_dict)
        return [label for label, _ in sent_class.display_labels]

    def get_label_category(self, label_id: int) -> str:
        """Get category name for a label ID"""
        label_text = self.primary_id2label.get(label_id, "Unknown")
        return label_text.split(" (")[0].replace(" ", "_")


# =============================================================================
# DATA LOADER
# =============================================================================


class DataLoader:
    """Handles loading data from database and CSV files"""

    def __init__(self, config: Config):
        self.config = config

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.config.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _parse_json_column(self, value: str):
        """Safely parse JSON column"""
        if isinstance(value, str):
            try:
                # Standard JSON with double quotes
                return json.loads(value)
            except json.JSONDecodeError:
                try:
                    # Handle non-standard JSON with single quotes
                    return json.loads(value.replace("'", '"'))
                except (json.JSONDecodeError, AttributeError):
                    return None
        return value

    def _flatten_matches(self, matches_dict):
        """Flatten a dictionary of sentence lists into a single list."""
        if not isinstance(matches_dict, dict):
            # Fallback for old format or unexpected data
            if isinstance(matches_dict, list):
                return matches_dict
            return []

        flattened_sentences = []
        for category_sentences in matches_dict.values():
            if not isinstance(category_sentences, list):
                continue
            for item in category_sentences:
                if isinstance(item, dict) and 'sentence' in item:
                    # Handle new format: list of dicts with a 'sentence' key
                    flattened_sentences.append(item['sentence'])
                elif isinstance(item, str):
                    # Handle old format: list of strings
                    flattened_sentences.append(item)

        return flattened_sentences

    def load_model_predictions(self) -> pd.DataFrame:
        """Load model predictions from database"""
        query = """
            SELECT
                r.cik,
                r.year,
                s.url,
                s.server_response
            FROM server_result s
            JOIN report_data r ON s.url = r.url
        """

        with self._get_connection() as conn:
            df = pd.read_sql(query, conn)

        # Parse JSON server response
        df["server_response"] = df["server_response"].apply(self._parse_json_column)

        # Remove rows with failed JSON parsing
        df = df[df["server_response"].notna()].reset_index(drop=True)

        return df

    def load_keyword_data(self) -> pd.DataFrame:
        """Load keyword-based derivatives data"""
        df = pd.read_csv(self.config.derivatives_csv)
        df["cik"] = df["cik"].astype(int)

        # Aggregate to cik-year level
        keyword_flags = (
            df.groupby(["cik", "year"])[["user", "fx_user", "ir_user", "cp_user"]]
            .max()
            .reset_index()
        )

        return keyword_flags

    def load_sentence_data(self, urls: Optional[List[str]] = None) -> pd.DataFrame:
        """Load sentence-level data with matches"""
        query = """
            SELECT
                r.cik,
                r.year,
                w.url,
                w.matches,
                s.server_response
            FROM webpage_result w
            JOIN report_data r ON w.url = r.url
            JOIN server_result s ON w.url = s.url
        """
        params = ()

        if urls:
            # Create placeholders for the URLs to prevent SQL injection
            placeholders = ", ".join("?" for _ in urls)
            query += f" WHERE w.url IN ({placeholders})"
            params = tuple(urls)

        with self._get_connection() as conn:
            try:
                df = pd.read_sql(query, conn, params=params)
            except Exception as e:
                print(f"Error executing query: {e}")
                return pd.DataFrame()

        # Parse JSON columns
        df["matches"] = df["matches"].apply(self._parse_json_column)
        df["matches"] = df["matches"].apply(self._flatten_matches)
        df["server_response"] = df["server_response"].apply(self._parse_json_column)

        # Remove rows with failed JSON parsing
        df = df[(df["matches"].notna()) & (df["server_response"].notna())].reset_index(
            drop=True
        )

        return df


# =============================================================================
# MODEL PREDICTIONS PROCESSOR
# =============================================================================


class PredictionsProcessor:
    """
    Backward-compatibility shim for PredictionsProcessor.
    Delegates all logic to the centralized ClassificationEngine.
    """

    def __init__(self, config: Optional[Config], label_mapper: Optional[LabelMapper]):
        self.config = config
        self.label_mapper = label_mapper
        print("✅ PredictionsProcessor now using ClassificationEngine")
        self.engine = ClassificationEngine(config)

    def process_predictions(self, model_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate model predictions to firm-year level"""
        print(f"Processing {len(model_df):,} model predictions...")

        results = []
        skipped_count = 0

        for _, row in tqdm(
            model_df.iterrows(), total=len(model_df), desc="Aggregating predictions"
        ):
            predictions = row["server_response"]

            if not predictions or not isinstance(predictions, list):
                skipped_count += 1
                continue

            # Use the new engine for classification
            sentence_classes = [self.engine.classify_sentence(p) for p in predictions]
            firm_year_class = self.engine.aggregate_to_firm_year(sentence_classes)

            results.append(
                {
                    "cik": row["cik"],
                    "year": row["year"],
                    "url": row["url"],
                    **firm_year_class.to_dict(),
                }
            )

        if skipped_count > 0:
            print(
                f"⚠️  Skipped {skipped_count} reports with empty or invalid predictions"
            )

        agg_df = pd.DataFrame(results)

        # Aggregate to firm-year level (max across multiple URLs)
        # If a firm-year has multiple URLs, we need to decide which URL to keep.
        # A simple approach is to keep the first one encountered for each group.
        agg_cols = [col for col in agg_df.columns if col.startswith("model_")]
        
        # Group by cik and year, aggregate flags with max(), and keep the first URL.
        firm_year_agg = agg_df.groupby(["cik", "year"]).agg(
            {**{col: 'max' for col in agg_cols}, 'url': 'first'}
        ).reset_index()

        print(f"✅ Aggregated to {len(firm_year_agg):,} firm-year observations")

        return firm_year_agg


# =============================================================================
# BASE ANALYZER (Abstract)
# =============================================================================


import inspect

class BaseAnalyzer:
    """Base class for all analyzers - can be extended in custom modules"""

    def __init__(self, config: Config, label_mapper: Optional[LabelMapper] = None, data_loader: Optional[DataLoader] = None):
        self.config = config
        self.label_mapper = label_mapper
        self.data_loader = data_loader

    @classmethod
    def get_configurable_args(cls) -> Dict:
        """
        Inspects the __init__ method to find configurable arguments with default values.
        This allows for dynamic configuration without hardcoding.
        It automatically skips 'self', 'config', and 'label_mapper'.
        """
        args = {}
        try:
            sig = inspect.signature(cls.__init__)
            for param in sig.parameters.values():
                # We only want parameters with default values that are not the standard ones.
                if param.name not in ['self', 'config', 'label_mapper'] and param.default is not inspect.Parameter.empty:
                    args[param.name] = param.default
        except (TypeError, ValueError):
            # Fails gracefully if __init__ is not a standard Python function
            pass
        return args

    def analyze(self, data: pd.DataFrame, **kwargs) -> Dict[str, pd.DataFrame]:
        """Override this method in custom analyzers"""
        raise NotImplementedError("Subclasses must implement analyze()")


# %%
