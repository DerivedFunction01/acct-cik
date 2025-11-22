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

    sentence_idx: int
    has_policy: bool
    has_existence: bool
    has_notional: bool
    has_pnl: bool
    category: str  # ir, fx, cp, or eq

    @property
    def is_user(self) -> bool:
        """Returns True if this sentence indicates derivative usage (not just policy)"""
        return self.has_existence or self.has_notional or self.has_pnl

    @property
    def classification_type(self) -> str:
        """Returns the highest-priority classification type for this sentence"""
        if self.has_notional:
            return "notional"
        elif self.has_pnl:
            return "pnl"
        elif self.has_existence:
            return "existence"
        elif self.has_policy:
            return "policy"
        return "none"


@dataclass
class FirmYearClassification:
    """Result of aggregating all sentences for a firm-year"""

    # Final binary flags (the source of truth)
    ir_user: int
    fx_user: int
    cp_user: int
    eq_user: int

    @property
    def hedge_user(self) -> int:
        """Returns 1 if firm uses any hedging derivatives (IR, FX, or CP)"""
        return 1 if (self.ir_user or self.fx_user or self.cp_user) else 0

    @property
    def any_user(self) -> int:
        """Returns 1 if firm uses any derivatives (including equity)"""
        return (
            1 if (self.ir_user or self.fx_user or self.cp_user or self.eq_user) else 0
        )

    def to_dict(self, prefix: str = "model_") -> Dict[str, int]:
        """Convert to dictionary with optional prefix for DataFrame columns"""
        return {
            f"{prefix}ir_user": self.ir_user,
            f"{prefix}fx_user": self.fx_user,
            f"{prefix}cp_user": self.cp_user,
            f"{prefix}eq_user": self.eq_user,
            f"{prefix}user": self.hedge_user,
            f"{prefix}user_all": self.any_user,
        }


class ClassificationEngine:
    """
    Centralized logic for classifying derivatives from model predictions.

    This class is the single source of truth for:
    1. Sentence-level classification (from array-based findings)
    2. Firm-year aggregation (for final flags)

    Works with the new array-based findings format where:
    - found_policy: [list of sentence indices with policy evidence]
    - found_existence: [list of sentence indices with existence evidence]
    - found_notional: [list of sentence indices with notional amounts]
    - found_pnl: [list of sentence indices with P&L impact]
    """

    def __init__(self, config):
        self.config = config

    # =========================================================================
    # SENTENCE-LEVEL CLASSIFICATION (for display and sampling)
    # =========================================================================

    def classify_sentences_from_findings(
        self,
        found_policy: List[int],
        found_existence: List[int],
        found_notional: List[int],
        found_pnl: List[int],
        category: str,
    ) -> List[SentenceClassification]:
        """
        Convert array-based findings into sentence-level classifications.

        Args:
            found_policy: List of sentence indices with policy evidence
            found_existence: List of sentence indices with existence evidence
            found_notional: List of sentence indices with notional amounts
            found_pnl: List of sentence indices with P&L impact
            category: The derivative category (ir, fx, cp, eq)

        Returns:
            List of SentenceClassification objects
        """
        # Collect all unique sentence indices that have any finding
        all_indices = set(found_policy + found_existence + found_notional + found_pnl)

        classifications = []
        for idx in sorted(all_indices):
            classifications.append(
                SentenceClassification(
                    sentence_idx=idx,
                    has_policy=idx in found_policy,
                    has_existence=idx in found_existence,
                    has_notional=idx in found_notional,
                    has_pnl=idx in found_pnl,
                    category=category,
                )
            )

        return classifications

    # =========================================================================
    # FIRM-YEAR AGGREGATION (source of truth for final classification)
    # =========================================================================

    def aggregate_to_firm_year(
        self, url_level_data: pd.DataFrame
    ) -> FirmYearClassification:
        """
        Aggregate URL-level classifications into final firm-year flags.

        This is the SOURCE OF TRUTH for firm-year classification.

        Args:
            url_level_data: DataFrame with columns for each category's user status
                          (e.g., 'model_ir_user', 'model_fx_user', etc.)

        Returns:
            FirmYearClassification with binary flags
        """
        # For each category, check if ANY URL for this firm-year shows usage
        ir_user = (
            1 if url_level_data.get("model_ir_user", pd.Series([0])).max() > 0 else 0
        )
        fx_user = (
            1 if url_level_data.get("model_fx_user", pd.Series([0])).max() > 0 else 0
        )
        cp_user = (
            1 if url_level_data.get("model_cp_user", pd.Series([0])).max() > 0 else 0
        )
        eq_user = (
            1 if url_level_data.get("model_eq_user", pd.Series([0])).max() > 0 else 0
        )

        return FirmYearClassification(
            ir_user=ir_user,
            fx_user=fx_user,
            cp_user=cp_user,
            eq_user=eq_user,
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def get_classification_summary(
        self, classifications: List[SentenceClassification]
    ) -> Dict[str, int]:
        """
        Get summary statistics for a list of sentence classifications.

        Returns:
            Dictionary with counts for each classification type
        """
        summary = {
            "total_sentences": len(classifications),
            "with_policy": sum(1 for c in classifications if c.has_policy),
            "with_existence": sum(1 for c in classifications if c.has_existence),
            "with_notional": sum(1 for c in classifications if c.has_notional),
            "with_pnl": sum(1 for c in classifications if c.has_pnl),
            "is_user": sum(1 for c in classifications if c.is_user),
        }
        return summary

    def filter_by_type(
        self, classifications: List[SentenceClassification], classification_type: str
    ) -> List[SentenceClassification]:
        """
        Filter classifications by type (policy, existence, notional, pnl).

        Args:
            classifications: List of SentenceClassification objects
            classification_type: One of 'policy', 'existence', 'notional', 'pnl', 'user'

        Returns:
            Filtered list of classifications
        """
        if classification_type == "policy":
            return [c for c in classifications if c.has_policy]
        elif classification_type == "existence":
            return [c for c in classifications if c.has_existence]
        elif classification_type == "notional":
            return [c for c in classifications if c.has_notional]
        elif classification_type == "pnl":
            return [c for c in classifications if c.has_pnl]
        elif classification_type == "user":
            return [c for c in classifications if c.is_user]
        else:
            raise ValueError(f"Unknown classification type: {classification_type}")
