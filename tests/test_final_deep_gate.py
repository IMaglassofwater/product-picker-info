"""Offline checks for the Phase 9.3 Final Deep Gate."""

from final_deep_gate import evaluate_final_deep_gate
from tests.test_deep_analysis import _result


def test_deep_score_and_drop_dispositions():
    assert evaluate_final_deep_gate(_result(deep_score=7)).status == "PASS"
    assert evaluate_final_deep_gate(_result(deep_score=5)).status == "REVIEW"
    assert evaluate_final_deep_gate(_result(deep_score=3)).status == "DROP"
    dropped = _result(deep_score=9, recommended_next_step="DROP")
    assert evaluate_final_deep_gate(dropped).reason == "deep_drop"


def test_unsupported_claim_is_held_for_human_review():
    result = _result(biggest_risks=["The product has low competition."])
    decision = evaluate_final_deep_gate(result)
    assert decision.status == "HUMAN_REVIEW"
    assert decision.unsupported_claims == ["low competition"]


def test_high_barrier_and_insufficient_gap_are_reviewed():
    feasibility = _result().feasibility.model_copy(update={"technical_complexity": "HIGH"})
    high_barrier = _result().model_copy(update={"feasibility": feasibility})
    assert evaluate_final_deep_gate(high_barrier).status == "REVIEW"
    vague = _result(existing_solution_gap="There is no actionable product gap in the supplied evidence.")
    assert evaluate_final_deep_gate(vague).reason == "insufficient_specificity"
