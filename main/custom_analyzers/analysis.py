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
    db_path: str = "clean_web_data.db"
    derivatives_csv: str = "./derivatives_data.csv"

    # Output paths
    output_dir: Path = field(default_factory=lambda: Path("./analysis_output"))
    comparison_excel: str = "keyword_model_comparison.xlsx"
    sentences_dir: str = "labeled_sentences"

    # Google Colab / Drive settings
    drive_path: str = "./drive/MyDrive/db"
    is_colab: Optional[bool] = None

    # Model settings

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
            ]


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
                if isinstance(item, str):
                    # Handle old format: list of strings
                    flattened_sentences.append(item)
                else:
                    print(item)

        return flattened_sentences

    def load_model_predictions(self) -> pd.DataFrame:
        """
        Load model predictions from the new 'classification_results' table.
        This table contains pre-classified findings for each (url, category) pair.
        """
        query = """
            SELECT
                r.cik,
                r.year,
                cr.url,
                cr.category,
                cr.found_policy,
                cr.found_existence,
                cr.found_notional,
                cr.found_pnl
            FROM classification_results cr
            JOIN report_data r ON cr.url = r.url
        """

        with self._get_connection() as conn:
            try:
                df = pd.read_sql(query, conn)
            except Exception as e:
                print(f"Error executing query on 'classification_results': {e}")
                # Check for a common error: table not found
                if "no such table" in str(e):
                    print("   -> The 'classification_results' table does not exist.")
                    print("   -> Please run the 'classify_from_db.py' script first to generate it.")
                return pd.DataFrame()

        # Parse JSON array columns for the 'found_*' fields
        for col in ["found_policy", "found_existence", "found_notional", "found_pnl"]:
            df[col] = df[col].apply(self._parse_json_column)

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
        """Load sentence-level data from the new derivative_type_matches table."""
        query = """
            SELECT
                r.cik,
                r.year,
                r.url
                dt.ir_matches,
                dt.fx_matches,
                dt.cp_matches,
                dt.eq_matches,
            FROM derivative_type_matches dt
            JOIN report_data r ON dt.url = r.url
        """
        params = ()

        if urls:
            # Create placeholders for the URLs to prevent SQL injection
            placeholders = ", ".join("?" for _ in urls)
            query += f" WHERE dt.url IN ({placeholders})"
            params = tuple(urls)
        df = pd.DataFrame()
        with self._get_connection() as conn:
            try:
                df = pd.read_sql(query, conn, params=params)
            except Exception as e:
                print(f"Error executing query on 'derivative_type_matches': {e}")
                return pd.DataFrame()
        return df

# =============================================================================
# MODEL PREDICTIONS PROCESSOR
# =============================================================================


class PredictionsProcessor:
    """
    Processes the pre-classified data from the 'classification_results' table
    to generate firm-year level flags.
    """

    def __init__(self, config: Config, label_mapper=None):
        self.config = config

    def process_predictions(self, model_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate model predictions from the new DB format to firm-year level.
        The input `model_df` comes from `load_model_predictions` and contains
        one row per (url, category) with `found_*` columns.
        """
        print(f"Processing {len(model_df):,} pre-classified records...")

        if model_df.empty:
            print("   ⚠️  Input DataFrame is empty. Cannot process predictions.")
            return pd.DataFrame()

        # A "user" is defined as having found evidence for existence, notional, or pnl.
        # The `found_*` columns contain lists of sentence indices. An empty list means no finding.
        model_df["is_user"] = model_df.apply(
            lambda row: 1 if (
                len(row.get("found_existence", [])) > 0 or
                len(row.get("found_notional", [])) > 0 or
                len(row.get("found_pnl", [])) > 0
            ) else 0,
            axis=1
        )

        # Create specific user flags for each category (ir, fx, cp)
        # Pivot the table to get one row per URL and columns for each category's user status.
        url_level_flags = model_df.pivot_table(
            index=["cik", "year", "url"],
            columns="category",
            values="is_user",
            fill_value=0
        ).reset_index()

        # Rename columns to match the expected format (e.g., 'model_ir_user')
        url_level_flags.rename(columns={
            "ir": "model_ir_user", "fx": "model_fx_user", "cp": "model_cp_user", "eq": "model_eq_user"
        }, inplace=True)

        # Aggregate to firm-year level (max across multiple URLs)
        # If a firm-year has multiple URLs, we need to decide which URL to keep.
        # A simple approach is to keep the first one encountered for each group.
        agg_cols = [col for col in url_level_flags.columns if col.startswith("model_")]
        
        # Group by cik and year, aggregate flags with max(), and keep the first URL.
        firm_year_agg = url_level_flags.groupby(["cik", "year"]).agg(
            {**{col: 'max' for col in agg_cols}, 'url': 'first'}
        ).reset_index()

        print(f"✅ Aggregated to {len(firm_year_agg):,} firm-year observations")

        return firm_year_agg

    def _get_firm_year_flags(self, df_group: pd.DataFrame) -> pd.Series:
        """Helper to aggregate flags for a single firm-year group."""
        # The max() will correctly propagate the 1 if any report for that year is a user.
        ir_user = df_group["model_ir_user"].max()
        fx_user = df_group["model_fx_user"].max()
        cp_user = df_group["model_cp_user"].max()
        eq_user = df_group["model_eq_user"].max()
        return pd.Series([ir_user, fx_user, cp_user, eq_user])

# =============================================================================
# BASE ANALYZER (Abstract)
# =============================================================================


import inspect

class BaseAnalyzer:
    """Base class for all analyzers - can be extended in custom modules"""

    def __init__(self, config: Config, data_loader: Optional[DataLoader] = None):
        self.config = config
        self.data_loader = data_loader

    @classmethod
    def get_configurable_args(cls) -> Dict:
        """
        Inspects the __init__ method to find configurable arguments with default values.
        This allows for dynamic configuration without hardcoding.
        It automatically skips 'self', 'config'
        """
        args = {}
        try:
            sig = inspect.signature(cls.__init__)
            for param in sig.parameters.values():
                # We only want parameters with default values that are not the standard ones.
                if param.name not in ['self', 'config'] and param.default is not inspect.Parameter.empty:
                    args[param.name] = param.default
        except (TypeError, ValueError):
            # Fails gracefully if __init__ is not a standard Python function
            pass
        return args

    def analyze(self, data: pd.DataFrame, **kwargs) -> Dict[str, pd.DataFrame]:
        """Override this method in custom analyzers"""
        raise NotImplementedError("Subclasses must implement analyze()")


# %%
