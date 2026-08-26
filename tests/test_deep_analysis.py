"""Offline tests for the Phase 8.2B physical Deep Analysis MVP."""

import json

import db
from ai_filter import run_triage_batch
from ai_providers import GeminiProvider
from deep_analysis import (
    ANALYSIS_VERSION,
    DEEP_ANALYSIS_PROMPT,
    MAX_OUTPUT_TOKENS,
    DeepAnalysisResponse,
    DeepAnalysisResult,
    build_deep_analysis_input,
    detect_unsupported_claims,
    parse_deep_analysis_result,
    serialize_input,
)
from models import Product
from tests.test_ai_filter import _candidate
from tests.test_ai_providers import _GeminiClient


def _raw(**updates):
    value = {
        "opportunity_summary": "Test a compact pillow improvement.",
        "evidence": {
            "confirmed_evidence": ["The input describes a pillow comparison."],
            "hypotheses": ["A strap could be worth testing."],
        },
        "customer_problem": "Comfort and stability trade-offs.",
        "existing_solution_gap": "Differentiation requires_validation.",
        "micro_innovation_ideas": ["idea 1", "idea 2", "idea 3"],
        "sourcing_direction": {
            "search_keywords": ["camping pillow"],
            "supplier_type": ["possible outdoor accessory manufacturer"],
            "manufacturing_category": ["outdoor sleep accessory"],
            "supplier_questions": ["What MOQ requires validation?"],
        },
        "validation_needed": ["supplier", "MOQ", "cost", "demand"],
        "feasibility": {
            "technical_complexity": "LOW",
            "manufacturing_complexity": "UNKNOWN",
            "shipping_friendliness": "HIGH",
            "regulatory_risk": "LOW",
            "startup_cost_level": "UNKNOWN",
        },
        "content_marketing_angle": ["comparison", "packing demo"],
        "biggest_risks": ["Demand requires validation."],
        "recommended_next_step": "VALIDATE_SUPPLIER",
        "deep_score": 7,
    }
    value.update(updates)
    return json.dumps(value)


def _result(candidate_id="c1", version=ANALYSIS_VERSION, **updates):
    parsed = parse_deep_analysis_result(
        candidate_id, _raw(**updates), "gemini", "gemini-3.5-flash-lite", 1000,
        {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    )
    return parsed.model_copy(update={"analysis_version": version})


def test_input_is_allowlisted_and_within_character_budget():
    candidate = _candidate(summary="<p>problem evidence " + "x" * 6000 + "</p>")
    triage = run_triage_batch([candidate]).processed[0]
    product = Product("p", "reddit", candidate.source_url, "T", "D", "EDC", "https://example.com/i.jpg", {"secret": "never send"})
    value = build_deep_analysis_input(candidate, triage, product)
    serialized = serialize_input(value)
    assert len(serialized) <= 2500
    assert "secret" not in serialized and "raw_data" not in serialized and "<p>" not in serialized


def test_evidence_hypotheses_and_grounding_prompt_are_explicit():
    parsed = DeepAnalysisResponse.model_validate_json(_raw())
    assert parsed.evidence.confirmed_evidence
    assert parsed.evidence.hypotheses
    prompt = DEEP_ANALYSIS_PROMPT.casefold()
    for phrase in ("confirmed_evidence", "hypotheses", "supplier", "moq", "cost", "competition", "requires validation"):
        assert phrase in prompt
    assert "never mix hypotheses" in prompt
    assert "launch below 10,000 rmb" in prompt
    assert "search direction only" in prompt
    assert "existing_solution_gap may use only supplied evidence" in prompt
    assert MAX_OUTPUT_TOKENS == 800 and "never exceed 800" in prompt


def test_market_grounding_distinguishes_observed_products_from_market_claims():
    prompt = DEEP_ANALYSIS_PROMPT.casefold()
    for forbidden in ("market dominated", "highly saturated", "low competition"):
        assert forbidden in prompt
    assert "competition requires validation" in prompt
    assert "multiple recognizable brands appear in the current evidence" in prompt


def test_output_lists_and_score_are_safely_normalized():
    result = _result(
        evidence={
            "confirmed_evidence": ["1", "2", "3", "4"],
            "hypotheses": ["1", "2", "3", "4"],
        },
        micro_innovation_ideas=["1", "2", "3", "4"],
        content_marketing_angle=["1", "2", "3", "4"],
        biggest_risks=["1", "2", "3", "4"],
        validation_needed=["1", "2", "3", "4", "5", "6"],
        sourcing_direction={
            "search_keywords": ["pillow"],
            "supplier_type": ["possible category"],
            "manufacturing_category": ["outdoor"],
            "supplier_questions": ["1", "2", "3", "4", "5", "6"],
        },
        deep_score=15,
    )
    assert len(result.evidence.confirmed_evidence) == 3
    assert len(result.evidence.hypotheses) == 3
    assert len(result.micro_innovation_ideas) == 3
    assert len(result.validation_needed) == 5
    assert len(result.sourcing_direction.supplier_questions) == 5
    assert len(result.content_marketing_angle) == 3
    assert len(result.biggest_risks) == 3
    assert result.deep_score == 10


def test_startup_cost_defaults_to_unknown_without_verified_cost_data():
    raw = json.loads(_raw())
    raw["feasibility"]["startup_cost_level"] = "LOW"
    raw["feasibility"]["manufacturing_complexity"] = "LOW"
    result = parse_deep_analysis_result(
        "c", json.dumps(raw), "gemini", "model", 1000,
        has_verified_supplier_cost_data=False,
    )
    assert result.feasibility.startup_cost_level == "UNKNOWN"
    assert result.feasibility.manufacturing_complexity == "UNKNOWN"


def test_next_step_enum_and_feasibility_enum_are_enforced():
    assert _result().recommended_next_step == "VALIDATE_SUPPLIER"
    bad = json.loads(_raw())
    bad["recommended_next_step"] = "BUY_NOW"
    try:
        DeepAnalysisResponse.model_validate(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid next step accepted")


def test_sourcing_is_direction_not_verified_supplier_claim():
    result = _result()
    text = result.sourcing_direction.model_dump_json().casefold()
    assert "possible" in text and "validation" in text
    assert "confirmed supplier" not in text and "supplier found" not in text


def test_unverified_market_dominance_phrase_is_detected():
    result = _result(biggest_risks=["Established brands dominate the current backpacking pillow market."])
    assert detect_unsupported_claims(result)


def test_gemini_pydantic_schema_is_constraint_light_and_used():
    schema = json.dumps(DeepAnalysisResponse.model_json_schema())
    for keyword in ("additionalProperties", "maxLength", "maxItems", "minimum", "maximum"):
        assert keyword not in schema
    request = GeminiProvider("key", "model", _GeminiClient()).build_request(
        {"title": "test"}, DEEP_ANALYSIS_PROMPT, DeepAnalysisResponse
    )
    assert request["config"]["response_schema"] is DeepAnalysisResponse


def test_database_version_key_duplicate_and_force_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "deep.db")
    v1 = _result(version="v1")
    v2 = _result(version="v2")
    assert db.save_deep_analysis_result(v1) is True
    assert db.save_deep_analysis_result(v1) is False
    assert db.save_deep_analysis_result(v2) is True
    updated = v1.model_copy(update={"deep_score": 8, "updated_at": "later"})
    assert db.save_deep_analysis_result(updated, force_reanalyze=True) is True
    assert db.get_deep_analysis_result(v1.candidate_id, v1.provider, v1.model, "v1").deep_score == 8
    assert db.get_deep_analysis_result(v2.candidate_id, v2.provider, v2.model, "v2").deep_score == 7


def test_deep_table_does_not_affect_triage_results(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "deep.db")
    candidate = _candidate()
    triage = run_triage_batch([candidate]).processed[0]
    assert db.save_triage_result(triage) is True
    assert db.save_deep_analysis_result(_result(candidate.candidate_id)) is True
    assert db.get_triage_result(candidate.candidate_id, "mock", "mock") == triage


def test_result_round_trip_contains_usage_and_version():
    result = _result()
    loaded = DeepAnalysisResult.model_validate_json(result.model_dump_json())
    assert loaded.analysis_version == ANALYSIS_VERSION == "v2"
    assert loaded.total_tokens == 30
