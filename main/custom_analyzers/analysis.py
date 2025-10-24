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
    """Handles label ID to name mapping and primary label logic"""

    def __init__(
        self,
        keywords_json_path: str,
        multi_labels: List[str],
        config: Optional[Config] = None,
    ):
        with open(keywords_json_path, "r", encoding="utf-8") as f:
            self.primary_id2label = {int(k): v for k, v in json.load(f).items()}

        self.primary_label2id = {v: k for k, v in self.primary_id2label.items()}
        self.multi_labels = multi_labels
        self.config = config

        # Define hedge type mappings - current, historical, speculative
        # (current, historic, spec, terminated)
        self.hedge_map = {
            "ir": (4, 5, 6, 7),
            "fx": (8, 9, 10, 11),
            "cp": (12, 13, 14, 15),
            "eq": (16, 17, 18, 19),
            "gen": (0, 1, 2, 3),
        }

        # Context-only mentions (no use indicated)
        self.context_map = {
            "gen": 20,
            "ir": 21,
            "fx": 22,
            "cp": 23,
            "eq": 24,
        }

    def get_primary_labels_with_confidence(
        self, labels_dict: Dict[str, float]
    ) -> List[Tuple[str, float, str]]:
        """
        Convert multi-label predictions to primary categorical labels with confidence scores.
        
        Returns:
            List of tuples: (label_name, confidence_score, confidence_tier)
            - label_name: Primary label string
            - confidence_score: Combined score (0.0 to 1.0)
            - confidence_tier: "high" (>0.75), "medium" (0.5-0.75), "low" (threshold-0.5)
        
        Use this for:
        - Selecting high-confidence examples for retraining
        - Flagging low-confidence predictions for manual review
        - Understanding model certainty per label
        """
        results = self._get_labels_with_scores(labels_dict)

        output = []
        for label_name, confidence in results:
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
        return [label for label, score in self._get_labels_with_scores(labels_dict)]

    def _get_labels_with_scores(
        self, labels_dict: Dict[str, float]
    ) -> List[Tuple[str, float]]:
        """
        Convert multi-label predictions to primary categorical labels.
        
        Returns list of labels with HIGHEST PRIORITY FIRST:
        - First label = primary (for inspection)
        - All labels = used for counter increments
        
        Priority for primary label (optimized for detecting CURRENT derivative usage):
        0. Terminated hedge (IR/FX/CP/EQ - by confidence)
        1. Current hedge usage (IR/FX/CP/EQ - by confidence)
        2. Historical hedge usage (IR/FX/CP/EQ - by confidence)
        3. Speculative hedge usage
        4. Warrant/Embedded (explicit usage signal, despite limited training data)
        5. Context with time indicators (soft hedges - ambiguous, no usage flag)
        6. Speculative context
        7. Context-only mentions
        8. Irrelevant
        """
        threshold = getattr(self.config, "confidence_threshold", 0.65)
        term_threshold = getattr(self.config, "termination_threshold", 0.80)

        # Collect all labels with scores for prioritization
        all_labels = []  # (priority_rank, confidence, label_id)

        # === Identify active hedge types ===
        active_hedges = []
        for hedge_type in ["ir", "fx", "cp", "eq", "gen"]:
            context_score = labels_dict.get(hedge_type, 0)
            usage_score = labels_dict.get(f"{hedge_type}_use", 0)

            if context_score >= threshold or usage_score >= threshold:
                active_hedges.append({
                    "type": hedge_type,
                    "has_use": usage_score >= threshold,
                    "context": context_score,
                    "usage": usage_score,
                    "max_score": max(context_score, usage_score)
                })

        # === Identify active time dimensions ===
        active_times = {}
        # Termination (`term`) takes precedence over current (`curr`).
        # If a hedge is terminated, it is considered a historical event for classification purposes.
        if labels_dict.get("term", 0) >= term_threshold:
            active_times["term"] = labels_dict.get("term", 0)
        elif labels_dict.get("curr", 0) >= threshold:
            active_times["curr"] = labels_dict.get("curr", 0)

        if labels_dict.get("hist", 0) >= threshold:
            active_times["hist"] = labels_dict.get("hist", 0)
        if labels_dict.get("spec", 0) >= threshold:
            active_times["spec"] = labels_dict.get("spec", 0)

        # === Build hedge labels (usage) ===
        any_use = any(h["has_use"] for h in active_hedges)
        is_speculative = "spec" in active_times
        # Condition for adding soft hedges: no explicit usage and not speculative
        add_soft_hedges = not any_use and not is_speculative

        for hedge in active_hedges:
            hedge_type = hedge["type"]

            # Initialize priority_penalty for each hedge type
            priority_penalty = 0.0

            # Resolve "gen" to specific type if possible
            resolved_type = hedge_type
            if hedge_type == "gen":
                best_specific = None
                best_score = 0
                for specific in ["ir", "fx", "cp", "eq"]:
                    score = labels_dict.get(specific, 0) + labels_dict.get(f"{specific}_use", 0)
                    if score > best_score and score >= (threshold * 0.7):
                        best_score = score
                        best_specific = specific
                if best_specific:
                    resolved_type = best_specific

            curr_id, hist_id, spec_id, term_id = self.hedge_map[resolved_type]

            # If hedge has USAGE
            if hedge["has_use"] and active_times:
                for time_dim, time_score in active_times.items():
                    # Combined score for prioritization
                    combined_score = hedge["usage"] * time_score

                    if time_dim == "term":  # Priority 0: Termination
                        all_labels.append(
                            (priority_penalty, combined_score, term_id)
                        )
                    elif time_dim == "curr":
                        # Priority 1: Current usage (highest)
                        all_labels.append((1 + priority_penalty, combined_score, curr_id))
                    elif time_dim == "hist":
                        # Priority 2: Historical usage
                        all_labels.append((2 + priority_penalty, combined_score, hist_id))
                    elif time_dim == "spec":
                        # Priority 3: Speculative usage
                        all_labels.append((3 + priority_penalty, combined_score, spec_id))
            # Fallback: If usage is detected but no time dimension is active, default to "historic"
            elif hedge["has_use"] and not active_times:
                # Priority 1.5: Usage with inferred historic time
                # The score is just the usage score, as there's no time_score to multiply
                all_labels.append((1.5 + priority_penalty, hedge["usage"], hist_id))

            # Soft hedge: context + time but no usage flag
            elif add_soft_hedges and not hedge["has_use"] and active_times and hedge["context"] >= threshold:
                for time_dim, time_score in active_times.items():
                    combined_score = hedge["context"] * time_score

                    if time_dim in "term":
                        # Priority 4: Context with termination
                        all_labels.append((4 + priority_penalty, combined_score, term_id))
                    elif time_dim in ["curr", "hist"]:
                        # Priority 5: Context with current/historical time
                        all_labels.append((5 + priority_penalty, combined_score, curr_id if time_dim == "curr" else hist_id))
                    elif time_dim == "spec": # This is speculative context
                        # Priority 5: Speculative context
                        all_labels.append((6 + priority_penalty, combined_score, spec_id))

        # === Warrant / Embedded (lower priority - limited training data) ===
        warr_score = labels_dict.get("warr", 0)
        emb_score = labels_dict.get("emb", 0)

        if warr_score >= threshold:
            if "curr" in active_times:
                # Priority 4: Current warrant (after usage, before soft context)
                all_labels.append((4, warr_score * active_times["curr"], 25))
            else:
                # Priority 6: Historical warrant
                all_labels.append((7, warr_score, 26))

        if emb_score >= threshold:
            if "curr" in active_times:
                # Priority 4: Current embedded
                all_labels.append((4, emb_score * active_times["curr"], 27))
            else:
                # Priority 6: Historical embedded
                all_labels.append((7, emb_score, 28))

        # === Pure context-only mentions (no usage anywhere) ===
        if not any_use:
            for hedge in active_hedges:
                if hedge["context"] >= threshold:
                    resolved_type = hedge["type"]
                    # Resolve gen if possible
                    if hedge["type"] == "gen":
                        best_specific = None
                        best_score = 0
                        for specific in ["ir", "fx", "cp", "eq"]:
                            score = labels_dict.get(specific, 0)
                            if score > best_score and score >= (threshold * 0.7):
                                best_score = score
                                best_specific = specific
                        if best_specific:
                            resolved_type = best_specific

                    # Add a small penalty to equity to deprioritize it
                    priority_penalty = 0.1 if resolved_type == "eq" else 0.0
                    # Priority 8: Context-only mention
                    all_labels.append((8 + priority_penalty, hedge["context"], self.context_map[resolved_type]))

        # === Irrelevant ===
        irr_score = labels_dict.get("irr", 0)
        if irr_score >= threshold:
            # Priority 9: Explicitly irrelevant
            all_labels.append((9, irr_score, 29))

        # === Sort by priority (ascending) then confidence (descending) ===
        all_labels.sort(key=lambda x: (x[0], -x[1]))

        # Extract unique labels with their confidence scores (preserve order)
        results = []
        seen = set()
        for _, confidence, label_id in all_labels:
            if label_id not in seen:
                results.append((label_id, confidence))
                seen.add(label_id)

        # Fallback to irrelevant if nothing found
        if not results:
            results.append((29, 0.0))

        return [(self.primary_id2label[label_id], confidence) for label_id, confidence in results]

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

    def _parse_json_column(self, value):
        """Safely parse JSON column"""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
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
            if isinstance(category_sentences, list):
                flattened_sentences.extend(category_sentences)
        
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
    """Processes model predictions and aggregates to firm-year level"""

    def __init__(self, config: Config, label_mapper: LabelMapper):
        self.config = config
        self.label_mapper = label_mapper

    def _is_valid_prediction(self, prob_dict) -> bool:
        """Check if prediction dictionary is valid"""
        return isinstance(prob_dict, dict) and "error" not in prob_dict

    def _get_sentence_flags(self, prob_dict: Dict[str, float]) -> Dict[str, bool]:
        """
        Determine active labels for a single sentence based on the confidence threshold.
        """
        flags = {label: False for label in self.config.labels}
        if not self._is_valid_prediction(prob_dict):
            return flags

        for label in self.config.labels:
            if prob_dict.get(label, 0.0) >= self.config.confidence_threshold:
                flags[label] = True
        return flags

    def _determine_user_flags(self, predictions: List[dict]) -> Dict[str, int]:
        """
        Determine firm-year user flags by analyzing sentence-level predictions.
        This allows for more granular logic, like associating 'term' with specific hedges.
        """
        # Initialize flags that will be aggregated across all sentences
        firm_year_flags = {
            "model_ir_user": 0,
            "model_fx_user": 0,
            "model_cp_user": 0,
            "model_eq_user": 0,
            "model_warr_user": 0,
            "model_emb_user": 0,
            "model_user": 0,
            "model_user_all": 0,
        }
        
        # Track if any use label is found for the "any_use" flag
        any_use_found = False

        for prob_dict in predictions:
            sentence_flags = self._get_sentence_flags(prob_dict)

            # A sentence indicates "current use" if 'curr' is present and 'term' is not.
            is_current_context = sentence_flags["curr"] and not sentence_flags["term"]

            # Check for current hedge usage. Once a firm is flagged as a user, it stays flagged.
            if is_current_context and sentence_flags["ir_use"]: firm_year_flags["model_ir_user"] = 1
            if is_current_context and sentence_flags["fx_use"]: firm_year_flags["model_fx_user"] = 1
            if is_current_context and sentence_flags["cp_use"]: firm_year_flags["model_cp_user"] = 1
            if is_current_context and sentence_flags["eq_use"]: firm_year_flags["model_eq_user"] = 1
            if is_current_context and sentence_flags["warr"]: firm_year_flags["model_warr_user"] = 1
            if is_current_context and sentence_flags["emb"]: firm_year_flags["model_emb_user"] = 1

            # Check for any derivative use (current or historic) for the 'model_user_all' flag
            if not any_use_found:
                if any(sentence_flags.get(use_label) for use_label in ["ir_use", "fx_use", "cp_use", "eq_use", "warr", "emb"]):
                    any_use_found = True

        # Set the final aggregated flags
        firm_year_flags["model_user"] = int(
            firm_year_flags["model_ir_user"] or firm_year_flags["model_fx_user"] or firm_year_flags["model_cp_user"]
        )
        firm_year_flags["model_user_all"] = int(any_use_found)

        return firm_year_flags

    def process_predictions(self, model_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate model predictions to firm-year level"""
        print(f"Processing {len(model_df):,} model predictions...")

        results = []
        skipped_count = 0

        for _, row in tqdm(
            model_df.iterrows(), total=len(model_df), desc="Aggregating predictions"
        ):
            predictions = row["server_response"]

            if not predictions:
                skipped_count += 1
                continue

            # Determine user flags by processing sentence-level predictions
            user_flags = self._determine_user_flags(predictions)

            results.append(
                {
                    "cik": row["cik"],
                    "year": row["year"],
                    "url": row["url"],
                    **user_flags,
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


class BaseAnalyzer:
    """Base class for all analyzers - can be extended in custom modules"""

    def __init__(self, config: Config, label_mapper: Optional[LabelMapper] = None):
        self.config = config
        self.label_mapper = label_mapper

    def analyze(self, data: pd.DataFrame, **kwargs) -> Dict[str, pd.DataFrame]:
        """Override this method in custom analyzers"""
        raise NotImplementedError("Subclasses must implement analyze()")


# %%
