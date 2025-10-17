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
    confidence_threshold: float = 0.45

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
            drive_root = Path(self.drive_path).parent
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
        self.hedge_map = {
            "ir": (3, 4, 5),
            "fx": (6, 7, 8),
            "cp": (9, 10, 11),
            "eq": (12, 13, 14),
            "gen": (0, 1, 2),
        }

        # Context-only mentions (no use indicated)
        self.context_map = {
            "gen": 15,
            "ir": 16,
            "fx": 17,
            "cp": 18,
            "eq": 19,
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
        1. Current hedge usage (IR/FX/CP/EQ - by confidence)
        2. Historical hedge usage (IR/FX/CP/EQ - by confidence)
        3. Speculative hedge usage
        4. Warrant/Embedded (explicit usage signal, despite limited training data)
        5. Context with time indicators (soft hedges - ambiguous, no usage flag)
        6. Speculative context
        7. Context-only mentions
        8. Irrelevant
        """
        threshold = getattr(self.config, "confidence_threshold", 0.35)
        
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
        if labels_dict.get("curr", 0) >= threshold:
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
            
            curr_id, hist_id, spec_id = self.hedge_map[resolved_type]
            
            # If hedge has USAGE
            if hedge["has_use"] and active_times:
                for time_dim, time_score in active_times.items():
                    # Combined score for prioritization
                    combined_score = hedge["usage"] * time_score
                    
                    if time_dim == "curr":
                        # Priority 1: Current usage (highest)
                        all_labels.append((1 + priority_penalty, combined_score, curr_id))
                    elif time_dim == "hist":
                        # Priority 2: Historical usage
                        all_labels.append((2 + priority_penalty, combined_score, hist_id))
                    elif time_dim == "spec":
                        # Priority 3: Speculative usage
                        all_labels.append((3 + priority_penalty, combined_score, spec_id))
            # Fallback: If usage is detected but no time dimension is active, default to "current"
            elif hedge["has_use"] and not active_times:
                # Priority 1.5: Usage with inferred current time
                # The score is just the usage score, as there's no time_score to multiply
                all_labels.append((1.5 + priority_penalty, hedge["usage"], curr_id))
            
            # Soft hedge: context + time but no usage flag
            elif add_soft_hedges and not hedge["has_use"] and active_times and hedge["context"] >= threshold:
                for time_dim, time_score in active_times.items():
                    combined_score = hedge["context"] * time_score
                    
                    if time_dim in ["curr", "hist"]:
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
                all_labels.append((4, warr_score * active_times["curr"], 20))
            else:
                # Priority 6: Historical warrant
                all_labels.append((7, warr_score, 21))
        
        if emb_score >= threshold:
            if "curr" in active_times:
                # Priority 4: Current embedded
                all_labels.append((4, emb_score * active_times["curr"], 22))
            else:
                # Priority 6: Historical embedded
                all_labels.append((7, emb_score, 23))
        
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
            all_labels.append((9, irr_score, 24))
        
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
            results.append((24, 0.0))
        
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

    def load_sentence_data(self) -> pd.DataFrame:
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

        with self._get_connection() as conn:
            df = pd.read_sql(query, conn)

        # Parse JSON columns
        df["matches"] = df["matches"].apply(self._parse_json_column)
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

    def _count_labels(self, predictions: List[dict]) -> Dict[str, int]:
        """Count label occurrences across all predictions"""
        label_counts = {label: 0 for label in self.config.labels}

        for prob_dict in predictions:
            if not self._is_valid_prediction(prob_dict):
                continue

            # Apply confidence threshold
            for label in self.config.labels:
                if prob_dict.get(label, 0.0) >= self.config.confidence_threshold:
                    label_counts[label] += 1

        return label_counts

    def _determine_user_flags(self, label_counts: Dict[str, int]) -> Dict[str, int]:
        """Determine user flags based on label counts"""

        # Helper to check if label exists with current context
        def has_current_use(use_label: str) -> bool:
            return (
                label_counts.get(use_label, 0) > 0 and label_counts.get("curr", 0) > 0
            )

        # Specific hedge types (must have current usage)
        has_ir = has_current_use("ir_use")
        has_fx = has_current_use("fx_use")
        has_cp = has_current_use("cp_use")
        has_eq = has_current_use("eq_use")
        has_warr = label_counts.get("warr", 0) > 0 and label_counts.get("curr", 0) > 0
        has_emb = label_counts.get("emb", 0) > 0 and label_counts.get("curr", 0) > 0

        # Any use (current or historic)
        any_use = any(
            [
                label_counts.get("ir_use", 0) > 0,
                label_counts.get("fx_use", 0) > 0,
                label_counts.get("cp_use", 0) > 0,
                label_counts.get("eq_use", 0) > 0,
                label_counts.get("warr", 0) > 0,
                label_counts.get("emb", 0) > 0,
            ]
        )

        return {
            "model_ir_user": int(has_ir),
            "model_fx_user": int(has_fx),
            "model_cp_user": int(has_cp),
            "model_eq_user": int(has_eq),
            "model_warr_user": int(has_warr),
            "model_emb_user": int(has_emb),
            "model_user": int(
                has_ir or has_fx or has_cp
            ),  # Original: Any hedge (IR/FX/CP)
            "model_user_all": int(any_use),  # All derivatives
        }

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

            # Count labels across all sentences
            label_counts = self._count_labels(predictions)

            # Determine user flags
            user_flags = self._determine_user_flags(label_counts)

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
