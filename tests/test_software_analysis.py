"""Offline tests for the Lightweight Software Analysis MVP."""

import json

import db
from ai_providers import GeminiProvider
from models import Product
from software_analysis import (
    ANALYSIS_VERSION,
    MAX_OUTPUT_TOKENS,
    SOFTWARE_ANALYSIS_PROMPT,
    SoftwareAnalysisResponse,
    SoftwareAnalysisResult,
    build_software_analysis_input,
    parse_software_analysis_result,
    serialize_input,
)
from tests.test_ai_providers import _GeminiClient


def _product(description="Manual research is time-consuming. Is there a small app for this?"):
    return Product(
        "p", "reddit", "https://example.com/software", "Niche workflow app",
        description, "software", "https://example.com/image.jpg", {"secret": "never send"},
    )


def _raw(**updates):
    value = {
        "opportunity_summary": "Test a narrow workflow helper.",
        "confirmed_evidence": ["The input describes time-consuming manual research."],
        "hypotheses": ["A guided tool could be worth testing."],
        "user_problem": "Manual comparison takes time.",
        "existing_solution_gap": "requires_validation",
        "mvp_idea": ["Collect three inputs", "Return a rule-based comparison"],
        "implementation_path": {
            "possible_interfaces": ["web_app"],
            "possible_building_blocks": ["simple form", "rules"],
            "unknowns": ["API availability requires validation"],
        },
        "open_source_or_ai_leverage": {
            "search_direction": ["search GitHub and public model catalogs"],
            "possible_leverage": ["AI-assisted summarization may be worth testing"],
            "validation_needed": ["availability", "license", "cost"],
        },
        "monetization_direction": ["freemium"],
        "validation_needed": ["demand", "competition", "willingness to pay"],
        "acquisition_angle": ["Show manual versus guided comparison"],
        "biggest_risks": ["Demand and implementation assumptions are unverified."],
        "recommended_next_step": "VALIDATE_DEMAND",
        "software_score": 6,
        "complexity": {
            "development_complexity": "UNKNOWN",
            "ongoing_cost": "UNKNOWN",
            "infrastructure_complexity": "UNKNOWN",
            "solo_builder_fit": "UNKNOWN",
        },
    }
    value.update(updates)
    return json.dumps(value)


def _result(version=ANALYSIS_VERSION, **updates):
    result = parse_software_analysis_result(
        "software-candidate", _raw(**updates), "gemini", "gemini-3.5-flash-lite",
        900, {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    )
    return result.model_copy(update={"analysis_version": version})


def test_input_is_allowlisted_and_under_2000_characters():
    value = build_software_analysis_input(_product("<p>pain " + "x" * 5000 + "</p>"), existing_score=63, signals=["software"])
    serialized = serialize_input(value)
    assert len(serialized) <= 2000
    assert "raw_data" not in serialized and "secret" not in serialized and "<p>" not in serialized


def test_required_fields_evidence_hypotheses_and_unknown_complexity():
    value = SoftwareAnalysisResponse.model_validate_json(_raw())
    required = set(SoftwareAnalysisResponse.model_fields)
    assert required >= {"opportunity_summary", "confirmed_evidence", "hypotheses", "mvp_idea", "software_score"}
    assert value.confirmed_evidence and value.hypotheses
    assert value.complexity.development_complexity == "UNKNOWN"


def test_mvp_and_other_lists_are_bounded_and_score_clamped():
    result = _result(
        mvp_idea=["1", "2", "3", "4"],
        confirmed_evidence=["1", "2", "3", "4"],
        hypotheses=["1", "2", "3", "4"],
        acquisition_angle=["1", "2", "3", "4"],
        biggest_risks=["1", "2", "3", "4"],
        software_score=15,
    )
    assert len(result.mvp_idea) == 3
    assert len(result.confirmed_evidence) == len(result.hypotheses) == 3
    assert len(result.acquisition_angle) == len(result.biggest_risks) == 3
    assert result.software_score == 10


def test_grounding_prompt_blocks_unverified_software_claims_and_targets_500_tokens():
    prompt = SOFTWARE_ANALYSIS_PROMPT.casefold()
    for phrase in (
        "github repository", "confirmed api", "development time or cost",
        "willingness to pay", "market size", "competition", "requires_validation",
    ):
        assert phrase in prompt
    assert "search directions only" in prompt
    assert MAX_OUTPUT_TOKENS == 500 and "under 500 tokens" in prompt


def test_software_score_prompt_is_evidence_and_business_calibrated():
    prompt = SOFTWARE_ANALYSIS_PROMPT.casefold()
    for phrase in (
        "score 10 is extremely rare",
        "evidence strength",
        "demand validation",
        "monetization evidence",
        "usage-frequency or retention risk",
        "competition unknowns",
        "technical simplicity does not equal a validated business opportunity",
    ):
        assert phrase in prompt
    assert "not a mechanical hard cap" in prompt
    assert "validate_demand without strong demand evidence is usually no higher than 7" in prompt


def test_next_step_enum_and_complexity_are_enforced():
    assert _result().recommended_next_step == "VALIDATE_DEMAND"
    bad = json.loads(_raw()); bad["recommended_next_step"] = "BUILD_PLATFORM"
    try:
        SoftwareAnalysisResponse.model_validate(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid software next step accepted")


def test_gemini_uses_constraint_light_pydantic_schema():
    schema = json.dumps(SoftwareAnalysisResponse.model_json_schema())
    for keyword in ("additionalProperties", "maxLength", "maxItems", "minimum", "maximum"):
        assert keyword not in schema
    request = GeminiProvider("key", "model", _GeminiClient()).build_request({}, SOFTWARE_ANALYSIS_PROMPT, SoftwareAnalysisResponse)
    assert request["config"]["response_schema"] is SoftwareAnalysisResponse


def test_database_unique_key_versions_and_force_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "software.db")
    v1 = _result("v1")
    v2 = _result("v2")
    assert db.save_software_analysis_result(v1) is True
    assert db.save_software_analysis_result(v1) is False
    assert db.save_software_analysis_result(v2) is True
    updated = v1.model_copy(update={"software_score": 8, "updated_at": "later"})
    assert db.save_software_analysis_result(updated, force_reanalyze=True) is True
    assert db.get_software_analysis_result(v1.candidate_id, v1.provider, v1.model, "v1").software_score == 8
    assert db.get_software_analysis_result(v2.candidate_id, v2.provider, v2.model, "v2").software_score == 6


def test_software_table_does_not_affect_physical_deep_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "software.db")
    assert db.save_software_analysis_result(_result()) is True
    assert db.get_deep_analysis_result("physical", "gemini", "model", "v2") is None
    loaded = db.get_software_analysis_result("software-candidate", "gemini", "gemini-3.5-flash-lite", "v1")
    assert isinstance(loaded, SoftwareAnalysisResult)
