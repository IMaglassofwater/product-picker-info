"""Transparent final gate for grounded physical Deep Analysis results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from deep_analysis import DeepAnalysisResult, detect_unsupported_claims


FinalDeepStatus = Literal["PASS", "REVIEW", "DROP", "HUMAN_REVIEW"]


@dataclass(frozen=True)
class FinalDeepGateResult:
    status: FinalDeepStatus
    reason: str
    unsupported_claims: list[str]


_INSUFFICIENT_GAP_PHRASES = (
    "insufficiently specific",
    "no actionable product gap",
    "no clear product gap",
    "no specific product gap",
    "only general advice",
    "general travel advice",
    "packing setup rather than",
)


def evaluate_final_deep_gate(result: DeepAnalysisResult) -> FinalDeepGateResult:
    """Return a deterministic disposition without changing the analysis score."""
    unsupported = detect_unsupported_claims(result)
    if unsupported:
        return FinalDeepGateResult(
            "HUMAN_REVIEW", "unsupported_claim", unsupported,
        )
    if result.recommended_next_step == "DROP":
        return FinalDeepGateResult("DROP", "deep_drop", [])
    if result.deep_score <= 3:
        return FinalDeepGateResult("DROP", "low_deep_score", [])
    if result.deep_score <= 5:
        return FinalDeepGateResult("REVIEW", "deep_review", [])

    analysis_text = " ".join((
        result.opportunity_summary,
        result.customer_problem,
        result.existing_solution_gap,
        *result.biggest_risks,
    )).casefold()
    if any(phrase in analysis_text for phrase in _INSUFFICIENT_GAP_PHRASES):
        return FinalDeepGateResult("REVIEW", "insufficient_specificity", [])

    feasibility = result.feasibility
    if feasibility.regulatory_risk == "HIGH":
        return FinalDeepGateResult("REVIEW", "high_regulatory_risk", [])
    if (feasibility.technical_complexity == "HIGH"
            or feasibility.manufacturing_complexity == "HIGH"):
        return FinalDeepGateResult("REVIEW", "high_engineering_or_manufacturing_barrier", [])
    return FinalDeepGateResult("PASS", "deep_pass", [])
