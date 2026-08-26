"""Offline tests for the Phase 9.1 daily ranking engine."""

from dataclasses import replace

from daily_ranker import (
    MAX_PER_THEME, MAX_SOFTWARE, OpportunityInput, RankComponents,
    apply_quality_gate, make_display_title, score_candidate,
    select_daily_top, select_triage_coverage_candidates,
    select_full_qualified,
)
from models import AITriageResult
from tests.test_deep_analysis import _result as deep_result
from tests.test_software_analysis import _result as software_result


def _triage(status="PASS", score=8):
    ranges = {"PASS": 8, "REVIEW": 6, "REJECT": 3}
    score = score if status == "PASS" else ranges[status]
    return AITriageResult(
        "c", status, score, "MEDIUM", "evidence", "unmet_demand",
        "validate", [], status != "REJECT", "gemini", "gemini-3.5-flash-lite",
    )


def _op(index=1, kind="Physical", source="reddit", theme="other", score=80, **updates):
    value = OpportunityInput(
        candidate_id=f"c{index}", title=f"Compact organizer {index}",
        summary="A compact organizer with an explicit storage problem and size requirement.",
        opportunity_type=kind, candidate_type="demand_opportunity" if kind == "Physical" else "software",
        source_platform=source, source_url=f"https://example.com/{index}",
        candidate_score=score, feasibility_score=80, demand_score=80,
        market_validation_score=60, micro_innovation_score=75,
        triage=_triage(), theme=theme, created_at="2099-01-01T00:00:00+00:00",
        signals=["clear_feature_gap", "clear_size_requirement", "low_tech_modification"],
    )
    for key, item in updates.items():
        setattr(value, key, item)
    return value


def test_components_sum_and_final_score_range():
    components = RankComponents(30, 20, 20, 15, 10, 5)
    assert components.total == 100
    ranked = score_candidate(_op())
    assert ranked.final_rank_score == ranked.components.total
    assert 0 <= ranked.final_rank_score <= 100


def test_physical_deep_and_software_analysis_take_priority_over_triage():
    physical = _op(1, physical_analysis=deep_result())
    software = _op(2, "Software", software_analysis=software_result())
    assert score_candidate(physical).analysis_source == "Physical Deep Analysis"
    assert score_candidate(software).analysis_source == "Software Analysis"
    assert score_candidate(physical).components.ai_quality == deep_result().deep_score * 3
    assert score_candidate(software).components.ai_quality == software_result().software_score * 3


def test_analysis_missing_falls_back_to_triage_then_candidate_score():
    triage = score_candidate(_op()).analysis_source
    no_triage = _op(2, triage=None)
    assert triage == "Cheap Triage Fallback"
    assert score_candidate(no_triage).analysis_source == "Candidate Score Fallback"
    assert score_candidate(no_triage).needs_analysis is True


def test_reject_drop_and_hard_risk_fail_quality_gate():
    rejected = _op(1, triage=_triage("REJECT"))
    dropped = _op(2, physical_analysis=deep_result().model_copy(update={"recommended_next_step": "DROP"}))
    risky = _op(3, risk_flags=["weapon_or_blade"])
    assert apply_quality_gate(rejected)[0] is False
    assert apply_quality_gate(dropped)[0] is True
    assert select_daily_top([dropped]).deep_gate_held_or_removed[0].exclusion_reason == "deep_drop"
    assert apply_quality_gate(risky)[1] == "hard_risk"


def test_software_quota_zero_software_and_no_forced_fill():
    software = [_op(i, "Software", theme="software", software_analysis=software_result()) for i in range(1, 5)]
    result = select_daily_top(software)
    assert len(result.final) <= MAX_SOFTWARE
    physical_only = select_daily_top([_op(i) for i in range(10, 13)])
    assert all(x.candidate.opportunity_type == "Physical" for x in physical_only.final)
    weak = _op(20, score=1, feasibility_score=0, demand_score=0, market_validation_score=0, micro_innovation_score=0, triage=_triage(score=8))
    weak.created_at = "2000-01-01T00:00:00+00:00"
    weak.source_platform = "yanko_design"
    assert len(select_daily_top([weak]).final) < 10


def test_theme_quota_and_near_duplicate_control():
    themed = [_op(i, theme="bags_and_carry") for i in range(1, 6)]
    result = select_daily_top(themed)
    assert sum(x.candidate.theme == "bags_and_carry" for x in result.final) <= MAX_PER_THEME
    a = _op(10, theme="outdoor_accessories", opportunity_group="backpacking_pillow")
    b = _op(11, theme="outdoor_accessories", opportunity_group="backpacking_pillow")
    duplicate = select_daily_top([a, b])
    assert duplicate.near_duplicates_removed == 1


def test_cross_source_confirmation_requires_independent_sources():
    candidate = _op(1, opportunity_group="key_organizer")
    independent = score_candidate(candidate, {"key_organizer": {"reddit", "amazon"}})
    same = score_candidate(candidate, {"key_organizer": {"reddit"}})
    assert independent.components.cross_source > 0
    assert same.components.cross_source == 0


def test_yanko_amazon_reddit_and_kickstarter_evidence_rules():
    yanko = score_candidate(_op(1, source="yanko_design"))
    amazon = score_candidate(_op(2, source="amazon", raw_data={"rank": 1, "review_count": 50}))
    reddit = score_candidate(_op(3, source="reddit", demand_score=90))
    kickstarter = score_candidate(_op(4, source="kickstarter", market_validation_score=90))
    assert yanko.components.evidence == 6
    assert amazon.components.evidence == 17
    assert reddit.components.evidence == 18
    assert kickstarter.components.evidence == 19


def test_yanko_cross_source_is_only_inspiration_confirmation():
    candidate = _op(1, source="yanko_design", opportunity_group="desk_lamp")
    ranked = score_candidate(candidate, {"desk_lamp": {"yanko_design", "reddit"}})
    assert ranked.components.cross_source == 5


def test_selection_and_exclusion_reasons_and_stable_order():
    candidates = [_op(i, theme=f"theme{i}") for i in range(1, 13)]
    first = select_daily_top(candidates)
    second = select_daily_top(list(reversed(candidates)))
    assert all(item.selection_reason for item in first.final)
    assert all(item.exclusion_reason for item in first.next_ten)
    assert [x.candidate.candidate_id for x in first.final] == [x.candidate.candidate_id for x in second.final]
    assert len(first.final) <= 10


def test_missing_review_and_reject_reasons_are_distinct():
    missing = _op(1, triage=None)
    review = _op(2, triage=_triage("REVIEW"))
    reject = _op(3, triage=_triage("REJECT"))
    mock = _op(4, triage=replace(_triage(), provider="mock", model="mock"))
    assert apply_quality_gate(missing)[1] == "missing_triage"
    assert apply_quality_gate(review)[1] == "triage_review"
    assert apply_quality_gate(reject)[1] == "triage_reject"
    assert apply_quality_gate(mock)[1] == "missing_triage"


def test_triage_coverage_is_bounded_physical_first_and_skips_existing():
    physical = [_op(i, triage=None) for i in range(1, 20)]
    software = [_op(100 + i, "Software", triage=None, summary="A complete simple workflow productivity web app idea") for i in range(6)]
    existing = _op(200, triage=_triage(), score=100)
    selected = select_triage_coverage_candidates(physical + software + [existing])
    assert len(selected) <= 20
    assert sum(x.opportunity_type == "Software" for x in selected) <= 4
    assert selected[0].opportunity_type == "Physical"
    assert existing not in selected


def test_display_title_fallback_does_not_change_original_title():
    candidate = _op(1, title="My", summary="PaperRepublic was too expensive, so I made a leather journal myself.")
    assert candidate.title == "My"
    assert candidate.display_title == "PaperRepublic alternative / DIY leather journal"
    assert make_display_title("Help", "Need a compact organizer for daily cables and keys.").startswith("Need a compact")


def test_specificity_too_broad_and_review_are_not_selected_by_default():
    specific = _op(1, title="Fanny pack without zipper", summary="Need a work fanny pack without a zipper.")
    broad = _op(2, title="Packing and bag advice for 8 day Swiss Alps trip", summary="Help review my packing list.", signals=[])
    review = _op(3, title="Compact travel storage", summary="Need compact storage while traveling.", signals=["storage_or_organization"])
    result = select_daily_top([specific, broad, review])
    assert [item.candidate.candidate_id for item in result.final] == [specific.candidate_id]
    assert result.removed_too_broad == 1
    assert result.held_for_review == 1
    assert {item.exclusion_reason for item in result.removed_or_held} == {"specificity_too_broad", "specificity_review"}


def test_specificity_gate_does_not_change_software_selection_rules():
    software = _op(1, "Software", theme="software", software_analysis=software_result())
    result = select_daily_top([software])
    assert len(result.final) == 1
    assert result.final[0].specificity is None


def test_final_deep_gate_prioritizes_deep_score_and_holds_non_pass():
    high = _op(1, physical_analysis=deep_result(deep_score=8))
    review = _op(2, physical_analysis=deep_result(candidate_id="c2", deep_score=5))
    low = _op(3, physical_analysis=deep_result(candidate_id="c3", deep_score=3))
    result = select_daily_top([high, review, low], require_physical_analysis=True)
    assert [item.candidate.candidate_id for item in result.final] == ["c1"]
    assert result.deep_gate_counts == {"PASS": 1, "REVIEW": 1, "DROP": 1, "HUMAN_REVIEW": 0}
    assert {item.exclusion_reason for item in result.deep_gate_held_or_removed} == {"deep_review", "low_deep_score"}
    assert result.final[0].analysis_source == "Physical Deep Analysis"
    assert result.final[0].components.ai_quality == 24


def test_deep_analysis_can_change_order_without_forced_fill():
    formerly_high = _op(1, triage=_triage(score=9), physical_analysis=deep_result(deep_score=6))
    formerly_lower = _op(2, triage=_triage(score=8), physical_analysis=deep_result(candidate_id="c2", deep_score=8))
    result = select_daily_top([formerly_high, formerly_lower], require_physical_analysis=True)
    assert [item.candidate.candidate_id for item in result.final] == ["c2", "c1"]
    assert len(result.final) == 2


def test_required_missing_deep_analysis_is_blocked_not_triage_fallback():
    candidate = _op(1, physical_analysis=None, triage=_triage(score=9))
    result = select_daily_top([candidate], require_physical_analysis=True)
    assert result.final == []
    assert result.deep_gate_held_or_removed[0].exclusion_reason == "analysis_failed"
    assert result.deep_gate_counts["HUMAN_REVIEW"] == 1


def test_daily_default_allows_missing_deep_analysis_and_grounding_fallback():
    missing = _op(1, physical_analysis=None)
    unsupported = deep_result(biggest_risks=["The product has low competition."])
    grounded_fallback = _op(2, physical_analysis=unsupported)
    result = select_daily_top([missing, grounded_fallback])
    assert {item.candidate.candidate_id for item in result.final} == {"c1", "c2"}
    sources = {item.candidate.candidate_id: item.analysis_source for item in result.final}
    assert sources == {"c1": "Cheap Triage Fallback", "c2": "Cheap Triage Fallback"}


def test_daily_default_still_excludes_explicit_deep_drop():
    dropped = _op(1, physical_analysis=deep_result(recommended_next_step="DROP", deep_score=8))
    result = select_daily_top([dropped])
    assert result.final == []
    assert result.deep_gate_held_or_removed[0].exclusion_reason == "deep_drop"


def test_full_qualified_keeps_lower_score_and_ignores_display_quotas():
    physical = [_op(i, theme="bags_and_carry") for i in range(1, 13)]
    software = [_op(100 + i, "Software", theme="software") for i in range(4)]
    full = select_full_qualified(physical + software)
    assert len(full) == 16
    assert sum(x.candidate.opportunity_type == "Software" for x in full) == 4


def test_full_qualified_still_rejects_core_gate_failures():
    rejected = _op(1, triage=_triage("REJECT"))
    risky = _op(2, risk_flags=["weapon_or_blade"])
    broad = _op(3, title="Packing and bag advice for a trip", summary="Review my packing list.", signals=[])
    assert select_full_qualified([rejected, risky, broad]) == []
