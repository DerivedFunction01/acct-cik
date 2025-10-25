# =============================================================================
# CENTRALIZED CLASSIFICATION ENGINE
# =============================================================================

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json
import pandas as pd


@dataclass
class SentenceClassification:
    """Result of classifying a single sentence"""
    # Primary labels for display (prioritized)
    display_labels: List[Tuple[str, float]]  # [(label_name, confidence), ...]
    
    # Raw flags for aggregation
    active_flags: Dict[str, bool]  # {label: True/False}
    
    # Context for debugging
    hedge_types: List[str]  # ['ir', 'fx', etc.]
    time_dimensions: List[str]  # ['curr', 'hist', 'term', 'spec']
    has_usage: bool  # Any _use flag active


@dataclass
class FirmYearClassification:
    """Result of aggregating all sentences for a firm-year"""
    # Final binary flags (the source of truth)
    ir_user: int
    fx_user: int
    cp_user: int
    eq_user: int
    warr_user: int
    emb_user: int
    user: int  # Any of the above
    user_all: int  # Any derivative mention (including soft)
    
    # Termination flags
    ir_terminated: int
    fx_terminated: int
    cp_terminated: int
    
    # Supporting counts for transparency
    ir_current_count: int
    fx_current_count: int
    cp_current_count: int
    ir_terminated_count: int
    fx_terminated_count: int
    cp_terminated_count: int
    ir_hist_count: int
    fx_hist_count: int
    cp_hist_count: int
    ir_soft_count: int
    fx_soft_count: int
    cp_soft_count: int
    
    def to_dict(self, prefix: str = "model_") -> Dict[str, int]:
        """Convert to dictionary with optional prefix for DataFrame columns"""
        return {
            f"{prefix}ir_user": self.ir_user,
            f"{prefix}fx_user": self.fx_user,
            f"{prefix}cp_user": self.cp_user,
            f"{prefix}eq_user": self.eq_user,
            f"{prefix}warr_user": self.warr_user,
            f"{prefix}emb_user": self.emb_user,
            f"{prefix}user": self.user,
            f"{prefix}user_all": self.user_all,
            f"{prefix}ir_terminated": self.ir_terminated,
            f"{prefix}fx_terminated": self.fx_terminated,
            f"{prefix}cp_terminated": self.cp_terminated,
            f"{prefix}ir_current_count": self.ir_current_count,
            f"{prefix}fx_current_count": self.fx_current_count,
            f"{prefix}cp_current_count": self.cp_current_count,
            f"{prefix}ir_terminated_count": self.ir_terminated_count,
            f"{prefix}fx_terminated_count": self.fx_terminated_count,
            f"{prefix}cp_terminated_count": self.cp_terminated_count,
            f"{prefix}ir_hist_count": self.ir_hist_count,
            f"{prefix}fx_hist_count": self.fx_hist_count,
            f"{prefix}cp_hist_count": self.cp_hist_count,
            f"{prefix}ir_soft_count": self.ir_soft_count,
            f"{prefix}fx_soft_count": self.fx_soft_count,
            f"{prefix}cp_soft_count": self.cp_soft_count,
        }


class ClassificationEngine:
    """
    Centralized logic for classifying derivatives from model predictions.
    
    This class is the single source of truth for:
    1. Sentence-level classification (for display/sampling)
    2. Firm-year aggregation (for final flags)
    
    Replaces the conflicting logic between LabelMapper and PredictionsProcessor.
    """
    
    def __init__(self, config):
        self.config = config
        
        # Thresholds
        self.confidence_threshold = getattr(config, "confidence_threshold", 0.65)
        self.soft_confidence_threshold = getattr(config, "soft_confidence_threshold", 0.50)
        self.termination_threshold = getattr(config, "termination_threshold", 0.80)
        self.term_curr_ratio = getattr(config, "term_curr_ratio", 1.0)
        self.display_threshold = getattr(config, "display_threshold", 0.30)
        
        # Label mappings for display
        self.hedge_map = {
            "ir": (4, 5, 6, 7),  # (curr, hist, spec, term)
            "fx": (8, 9, 10, 11),
            "cp": (12, 13, 14, 15),
            "eq": (16, 17, 18, 19),
            "gen": (0, 1, 2, 3),
        }
        
        self.context_map = {
            "gen": 20,
            "ir": 21,
            "fx": 22,
            "cp": 23,
            "eq": 24,
        }
        
        # Primary label ID to name mapping
        with open(config.keywords_json, "r", encoding="utf-8") as f:
            self.primary_id2label = {int(k): v for k, v in json.load(f).items()}
    
    # =========================================================================
    # SENTENCE-LEVEL CLASSIFICATION (for display and sampling)
    # =========================================================================
    
    def classify_sentence(self, prob_dict: Dict[str, float]) -> SentenceClassification:
        """
        Classify a single sentence for display purposes.
        
        Returns prioritized labels and flags for aggregation.
        """
        if not self._is_valid_prediction(prob_dict):
            return SentenceClassification(
                display_labels=[("Irrelevant", 0.0)],
                active_flags={label: False for label in self.config.labels},
                hedge_types=[],
                time_dimensions=[],
                has_usage=False
            )
        
        # Get active flags (what passes threshold)
        active_flags = self._get_active_flags(prob_dict)
        
        # Get prioritized display labels
        display_labels = self._get_display_labels(prob_dict, active_flags)
        
        # Extract metadata
        hedge_types = [h for h in ["ir", "fx", "cp", "eq", "gen"] 
                      if active_flags.get(h) or active_flags.get(f"{h}_use")]
        time_dimensions = [t for t in ["curr", "hist", "term", "spec"] 
                          if active_flags.get(t)]
        has_usage = any(active_flags.get(f"{h}_use") for h in ["ir", "fx", "cp", "eq", "gen"])
        
        return SentenceClassification(
            display_labels=display_labels,
            active_flags=active_flags,
            hedge_types=hedge_types,
            time_dimensions=time_dimensions,
            has_usage=has_usage
        )
    
    def _get_active_flags(self, prob_dict: Dict[str, float]) -> Dict[str, bool]:
        """Determine which labels are active based on thresholds"""
        flags = {}
        for label in self.config.labels:
            threshold = (self.termination_threshold if label == "term" 
                        else self.confidence_threshold)
            flags[label] = prob_dict.get(label, 0.0) >= threshold
        return flags
    
    def _get_display_labels(
        self, 
        prob_dict: Dict[str, float],
        active_flags: Dict[str, bool]
    ) -> List[Tuple[str, float]]:
        """
        Generate prioritized display labels for a single sentence.
        
        This is ONLY for display/sampling, not for firm-year classification.
        """
        all_labels = []  # (priority_rank, confidence, label_id)
        
        # === Identify active hedge types ===
        active_hedges = []
        for hedge_type in ["ir", "fx", "cp", "eq", "gen"]:
            context_score = prob_dict.get(hedge_type, 0)
            usage_score = prob_dict.get(f"{hedge_type}_use", 0)
            
            if active_flags.get(hedge_type) or active_flags.get(f"{hedge_type}_use"):
                active_hedges.append({
                    "type": hedge_type,
                    "has_use": active_flags.get(f"{hedge_type}_use", False),
                    "context": context_score,
                    "usage": usage_score,
                    "max_score": max(context_score, usage_score)
                })
        
        # === Identify active time dimensions ===
        active_times = {}
        for time_dim in ["curr", "hist", "term", "spec"]:
            if active_flags.get(time_dim):
                active_times[time_dim] = prob_dict.get(time_dim, 0)
        
        # === Build hedge labels ===
        any_use = any(h["has_use"] for h in active_hedges)
        is_speculative = "spec" in active_times
        add_soft_hedges = not any_use and not is_speculative
        
        for hedge in active_hedges:
            hedge_type = hedge["type"]
            priority_penalty = 0.0
            
            # Resolve "gen" to specific type if possible
            resolved_type = self._resolve_gen_type(prob_dict, hedge_type)
            curr_id, hist_id, spec_id, term_id = self.hedge_map[resolved_type]
            
            # If hedge has USAGE
            if hedge["has_use"] and active_times:
                for time_dim, time_score in active_times.items():
                    combined_score = hedge["usage"] * time_score
                    if time_dim == "curr":
                        all_labels.append((1 + priority_penalty, combined_score, curr_id))
                    elif time_dim == "term":
                        all_labels.append((2 + priority_penalty, combined_score, term_id))
                    elif time_dim == "hist":
                        all_labels.append((3 + priority_penalty, combined_score, hist_id))
                    elif time_dim == "spec":
                        all_labels.append((4 + priority_penalty, combined_score, spec_id))
            
            # Fallback: usage without clear time dimension
            elif hedge["has_use"] and not active_times:
                curr_score = prob_dict.get("curr", 0)
                hist_score = prob_dict.get("hist", 0)
                chosen_id = hist_id
                if curr_score > hist_score and curr_score >= self.display_threshold:
                    chosen_id = curr_id
                all_labels.append((1.5 + priority_penalty, hedge["usage"], chosen_id))
            
            # Soft hedge: context + time but no usage flag
            elif add_soft_hedges and not hedge["has_use"] and active_times and hedge["context"] >= self.confidence_threshold:
                for time_dim, time_score in active_times.items():
                    combined_score = hedge["context"] * time_score
                    if time_dim == "curr" or time_dim == "hist":
                        all_labels.append((6 + priority_penalty, combined_score, 
                                         curr_id if time_dim == "curr" else hist_id))
                    elif time_dim == "term":
                        all_labels.append((6 + priority_penalty, combined_score, term_id))
                    elif time_dim == "spec":
                        all_labels.append((7 + priority_penalty, combined_score, spec_id))
        
        # === Warrant / Embedded ===
        self._add_special_derivatives(all_labels, prob_dict, active_flags, active_times)
        
        # === Pure context-only mentions ===
        if not any_use:
            self._add_context_only(all_labels, active_hedges, prob_dict)
        
        # === Irrelevant ===
        if active_flags.get("irr"):
            all_labels.append((10, prob_dict.get("irr", 0), 29))
        
        # Sort by priority then confidence
        all_labels.sort(key=lambda x: (x[0], -x[1]))
        
        # Extract unique labels
        results = []
        seen = set()
        for _, confidence, label_id in all_labels:
            label_name = self.primary_id2label.get(str(label_id))
            if label_name and label_name not in seen:
                results.append((label_name, confidence))
                seen.add(label_name)
        
        # Fallback to irrelevant
        if not results:
            results.append(("Irrelevant", 0.0))
        
        return results
    
    def _resolve_gen_type(self, prob_dict: Dict[str, float], hedge_type: str) -> str:
        """Resolve 'gen' to specific type if possible"""
        if hedge_type != "gen":
            return hedge_type
        
        best_specific = None
        best_score = 0
        for specific in ["ir", "fx", "cp", "eq"]:
            score = prob_dict.get(specific, 0) + prob_dict.get(f"{specific}_use", 0)
            if score > best_score and score >= (self.confidence_threshold * 0.7):
                best_score = score
                best_specific = specific
        
        return best_specific if best_specific else "gen"
    
    def _add_special_derivatives(
        self, 
        all_labels: List, 
        prob_dict: Dict[str, float],
        active_flags: Dict[str, bool],
        active_times: Dict[str, float]
    ):
        """Add warrant and embedded derivative labels"""
        warr_score = prob_dict.get("warr", 0)
        emb_score = prob_dict.get("emb", 0)
        
        if active_flags.get("warr"):
            if "curr" in active_times:
                all_labels.append((5, warr_score * active_times["curr"], 25))
            else:
                all_labels.append((8, warr_score, 26))
        
        if active_flags.get("emb"):
            if "curr" in active_times:
                all_labels.append((5, emb_score * active_times["curr"], 27))
            else:
                all_labels.append((8, emb_score, 28))
    
    def _add_context_only(
        self, 
        all_labels: List, 
        active_hedges: List[Dict],
        prob_dict: Dict[str, float]
    ):
        """Add context-only mentions (no usage)"""
        for hedge in active_hedges:
            if hedge["context"] >= self.confidence_threshold:
                resolved_type = self._resolve_gen_type(prob_dict, hedge["type"])
                priority_penalty = 0.1 if resolved_type == "eq" else 0.0
                label_id = self.context_map.get(resolved_type)
                if label_id is not None:
                    all_labels.append((9 + priority_penalty, hedge["context"], label_id))
    
    # =========================================================================
    # FIRM-YEAR AGGREGATION (source of truth for final classification)
    # =========================================================================
    
    def aggregate_to_firm_year(
        self, 
        sentence_classifications: List[SentenceClassification]
    ) -> FirmYearClassification:
        """
        Aggregate all sentence classifications into final firm-year flags.
        
        This is the SOURCE OF TRUTH for firm-year classification.
        """
        # Initialize counters
        counts = {
            "ir_current": 0, "fx_current": 0, "cp_current": 0,
            "ir_terminated": 0, "fx_terminated": 0, "cp_terminated": 0,
            "ir_hist": 0, "fx_hist": 0, "cp_hist": 0,
            "ir_soft": 0, "fx_soft": 0, "cp_soft": 0,
        }
        
        # Flags for other derivatives
        eq_user = 0
        warr_user = 0
        emb_user = 0
        any_use_found = False
        
        # Process each sentence
        for sent_class in sentence_classifications:
            flags = sent_class.active_flags
            
            # Determine context
            is_current = flags.get("curr") and not flags.get("term")
            is_terminated = flags.get("term") and not flags.get("curr")
            is_historical = flags.get("hist") and not flags.get("curr") and not flags.get("term")
            is_soft = not any(flags.get(f"{h}_use") for h in ["ir", "fx", "cp"])
            
            # Count hedge types by context
            for hedge in ["ir", "fx", "cp"]:
                if flags.get(f"{hedge}_use"):
                    if is_current:
                        counts[f"{hedge}_current"] += 1
                    elif is_terminated:
                        counts[f"{hedge}_terminated"] += 1
                    elif is_historical:
                        counts[f"{hedge}_hist"] += 1
                
                # Soft mentions (context without use)
                if is_soft and flags.get(hedge):
                    counts[f"{hedge}_soft"] += 1
            
            # Other derivatives
            if is_current:
                if flags.get("eq_use"):
                    eq_user = 1
                if flags.get("warr"):
                    warr_user = 1
                if flags.get("emb"):
                    emb_user = 1
            
            # Check for any derivative use
            if not any_use_found:
                if any(flags.get(label) for label in ["ir_use", "fx_use", "cp_use", "eq_use", "warr", "emb"]):
                    any_use_found = True
        
        # Apply firm-year logic
        ir_user, ir_terminated = self._apply_hedge_logic(
            counts["ir_current"], counts["ir_terminated"]
        )
        fx_user, fx_terminated = self._apply_hedge_logic(
            counts["fx_current"], counts["fx_terminated"]
        )
        cp_user, cp_terminated = self._apply_hedge_logic(
            counts["cp_current"], counts["cp_terminated"]
        )
        
        # Overall flags
        user = int(ir_user or fx_user or cp_user)
        user_all = int(any_use_found)
        
        return FirmYearClassification(
            ir_user=ir_user,
            fx_user=fx_user,
            cp_user=cp_user,
            eq_user=eq_user,
            warr_user=warr_user,
            emb_user=emb_user,
            user=user,
            user_all=user_all,
            ir_terminated=ir_terminated,
            fx_terminated=fx_terminated,
            cp_terminated=cp_terminated,
            ir_current_count=counts["ir_current"],
            fx_current_count=counts["fx_current"],
            cp_current_count=counts["cp_current"],
            ir_terminated_count=counts["ir_terminated"],
            fx_terminated_count=counts["fx_terminated"],
            cp_terminated_count=counts["cp_terminated"],
            ir_hist_count=counts["ir_hist"],
            fx_hist_count=counts["fx_hist"],
            cp_hist_count=counts["cp_hist"],
            ir_soft_count=counts["ir_soft"],
            fx_soft_count=counts["fx_soft"],
            cp_soft_count=counts["cp_soft"],
        )
    
    def _apply_hedge_logic(
        self, 
        current_count: int, 
        terminated_count: int
    ) -> Tuple[int, int]:
        """
        Apply the termination logic for a single hedge type.
        
        Returns: (is_user, is_terminated)
        """
        # User if any current mentions
        is_user = 1 if current_count > 0 else 0
        
        # Terminated if term/curr ratio exceeds threshold
        is_terminated = 0
        if terminated_count > 0:
            if current_count == 0 or (terminated_count / current_count) > self.term_curr_ratio:
                is_terminated = 1
        
        # Mutual exclusivity: if terminated, not a user
        if is_terminated:
            is_user = 0
        
        return is_user, is_terminated
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _is_valid_prediction(self, prob_dict: Dict) -> bool:
        """Check if prediction dictionary is valid"""
        return isinstance(prob_dict, dict) and "error" not in prob_dict