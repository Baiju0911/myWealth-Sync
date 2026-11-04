# backend/tracker/classification/enginehelpers/confidence_helpers.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ConfidenceWeights:
    """Configurable scoring weights for deterministic confidence calculation."""

    PAIRED_CONTRA: float = 0.40
    UNILATERAL_INTERNAL: float = 0.25
    REFERENCE_PROOF: float = 0.30
    KNOWN_MERCHANT: float = 0.20
    CLEAN_TOKENS: float = 0.15
    HISTORICAL_RULE_MATCH: float = 0.10


class ConfidenceScorer:
    """
    Evaluates financial and structural invariants to produce a
    deterministic confidence score between 0.00 and 1.00.
    """

    HIGH_THRESHOLD: float = 0.85
    MEDIUM_THRESHOLD: float = 0.50

    @classmethod
    def evaluate(
        cls,
        is_paired_contra: bool = False,
        is_unilateral_internal: bool = False,
        has_ref_proof: bool = False,
        has_known_merchant: bool = False,
        has_clean_tokens: bool = False,
        has_rule_precedent: bool = False,
    ) -> Tuple[float, str, bool]:
        """
        Calculates composite confidence score.

        Returns:
            (score: float, label: str, ok_to_classify: bool)
        """
        score = 0.0

        if is_paired_contra:
            score += ConfidenceWeights.PAIRED_CONTRA
        elif is_unilateral_internal:
            score += ConfidenceWeights.UNILATERAL_INTERNAL

        if has_ref_proof:
            score += ConfidenceWeights.REFERENCE_PROOF

        if has_known_merchant:
            score += ConfidenceWeights.KNOWN_MERCHANT
        elif has_clean_tokens:
            score += ConfidenceWeights.CLEAN_TOKENS

        if has_rule_precedent:
            score += ConfidenceWeights.HISTORICAL_RULE_MATCH

        final_score = min(1.0, round(score, 2))

        if final_score >= cls.HIGH_THRESHOLD:
            label = "HIGH"
            ok_to_classify = True
        elif final_score >= cls.MEDIUM_THRESHOLD:
            label = "MEDIUM"
            ok_to_classify = False
        else:
            label = "LOW"
            ok_to_classify = False

        return final_score, label, ok_to_classify
