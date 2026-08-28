"""Offline tests for Phase 8.1 mock AI triage."""

import json
import sqlite3
from dataclasses import replace

import db
from ai_filter import SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA, _parse_result, build_triage_input, run_triage_batch, select_diverse_candidates
from ai_providers import BaseAIProvider, MockAIProvider
from candidate_pool import MicroInnovationCandidate
from models import Product


def test_triage_contract_requests_grounded_bilingual_content():
    for field in ("display_title_zh", "primary_reason_zh", "key_opportunity_zh", "main_risks_zh"):
        assert field in TRIAGE_JSON_SCHEMA["properties"]
        assert field in TRIAGE_JSON_SCHEMA["required"]
    assert "Chinese fields must not add facts" in SYSTEM_PROMPT
    assert TRIAGE_JSON_SCHEMA["properties"]["display_title_zh"] == {"type": "string"}
    assert "must always be a non-empty" in SYSTEM_PROMPT
    assert "never return null or an empty string" in SYSTEM_PROMPT


def _candidate(index=1, kind="demand_opportunity", score=82, signals=None, summary="Clear lightweight organizer pain point"):
    return MicroInnovationCandidate(
        candidate_id=f"c{index}", candidate_type=kind, source_platform="reddit",
        source_url=f"https://example.com/{index}", title=f"Candidate {index}",
        summary=summary, candidate_score=score,
        feasibility_score=80, demand_score=80, market_validation_score=0,
        micro_innovation_score=80, reason="test", signals=signals or ["clear_feature_gap"],
        raw_reference_id=f"r{index}",
    )


def test_mock_is_deterministic_and_structured():
    provider = MockAIProvider()
    payload = build_triage_input(_candidate())
    first = json.loads(provider.analyze(payload, "prompt"))
    second = json.loads(provider.analyze(payload, "prompt"))
    assert first == second
    assert set(first) == {"triage_status", "triage_score", "confidence", "primary_reason", "opportunity_type", "key_opportunity", "main_risks", "needs_deep_analysis"}
    assert 1 <= first["triage_score"] <= 10


def test_mock_status_score_ranges_and_hard_risk():
    cases = [(_candidate(1, score=85), "PASS"), (_candidate(2, score=65), "REVIEW"), (_candidate(3, score=35), "REJECT")]
    provider = MockAIProvider()
    for candidate, expected in cases:
        assert json.loads(provider.analyze(build_triage_input(candidate), ""))["triage_status"] == expected
    hard = _candidate(4, score=95, signals=["wireless", "clear_feature_gap"])
    assert json.loads(provider.analyze(build_triage_input(hard), ""))["triage_status"] == "REJECT"


def test_amazon_commodity_gate():
    amazon = _candidate(1, "consumer_trend")
    for status, expected in (("COMMODITY", 0), ("REVIEW", 0), ("PROMISING", 1)):
        batch = run_triage_batch([amazon], commodity={amazon.candidate_id: (status, 70)})
        assert batch.eligible == expected


def test_prompt_input_is_bounded_and_excludes_raw_data_and_html():
    candidate = _candidate(summary="<div>" + "x" * 800 + "</div>")
    product = Product("p", "reddit", candidate.source_url, "T", "D", "EDC", "https://example.com/i.jpg", {"secret_raw": "never send"})
    payload = build_triage_input(candidate, product)
    serialized = json.dumps(payload)
    assert len(payload["description"]) <= 500
    assert "<div>" not in serialized
    assert "secret_raw" not in serialized
    assert "raw_data" not in serialized


def test_system_prompt_enforces_grounding_boundaries():
    prompt = SYSTEM_PROMPT.casefold()
    assert "supplier" in prompt and "1688 availability" in prompt
    assert "moq" in prompt
    assert "manufacturing cost" in prompt and "material cost" in prompt
    assert "profession/demographics" in prompt
    assert "competition level" in prompt
    assert "requires validation" in prompt
    assert "hypothesis" in prompt


def test_existing_skips_and_force_reanalyze_runs():
    candidate = _candidate()
    skipped = run_triage_batch([candidate], has_result=lambda _id, _provider, _model: True)
    forced = run_triage_batch([candidate], has_result=lambda _id, _provider, _model: True, force_reanalyze=True)
    assert skipped.skipped_existing == 1 and not skipped.processed
    assert len(forced.processed) == 1


def test_batch_limit_and_type_diversity():
    candidates = [_candidate(i, "demand_opportunity", 100 - i) for i in range(25)]
    candidates += [_candidate(30, "validated_product"), _candidate(31, "inspiration_product")]
    selected = select_diverse_candidates(candidates)
    assert len(selected) == 20
    assert {item.candidate_type for item in selected} >= {"demand_opportunity", "validated_product", "inspiration_product"}


class _BrokenProvider(BaseAIProvider):
    provider_name = "broken"
    model_name = "broken"
    def analyze(self, payload, system_prompt, json_schema=None):
        if payload["title"].endswith("1"):
            raise ValueError("failure")
        return "not-json"


def test_provider_errors_and_malformed_json_are_contained():
    batch = run_triage_batch([_candidate(1), _candidate(2)], provider=_BrokenProvider())
    assert batch.errors == 2
    assert batch.processed == []


def test_provider_and_model_are_mock():
    result = run_triage_batch([_candidate()]).processed[0]
    assert result.provider == "mock" and result.model == "mock"


def test_gemini_result_constraints_are_normalized_without_another_call():
    raw = json.dumps({
        "triage_status": "PASS",
        "triage_score": 11,
        "confidence": "HIGH",
        "primary_reason": "r" * 130,
        "opportunity_type": "unmet_demand",
        "key_opportunity": "k" * 170,
        "main_risks": ["x" * 90, "two", "three", "four"],
        "needs_deep_analysis": True,
    })
    provider = _GeminiMock()
    result = _parse_result("candidate", raw, provider)
    assert result.triage_score == 10
    assert len(result.primary_reason) == 120
    assert len(result.key_opportunity) == 160
    assert len(result.main_risks) == 3
    assert len(result.main_risks[0]) == 80


def test_triage_database_round_trip_and_unique(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "triage.db")
    result = run_triage_batch([_candidate()]).processed[0]
    assert db.has_triage_result(result.candidate_id, "mock", "mock") is False
    assert db.save_triage_result(result) is True
    assert db.has_triage_result(result.candidate_id, "mock", "mock") is True
    loaded = db.get_triage_result(result.candidate_id, "mock", "mock")
    assert loaded == result


def test_provider_model_results_coexist_and_force_is_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "triage.db")
    mock = run_triage_batch([_candidate()]).processed[0]
    gemini = replace(mock, provider="gemini", model="gemini-3.5-flash-lite")
    gemini_other = replace(mock, provider="gemini", model="gemini-2.5-flash")
    openai = replace(mock, provider="openai", model="gpt-5.4-nano")

    assert db.save_triage_result(mock) is True
    assert db.save_triage_result(gemini) is True
    assert db.save_triage_result(gemini) is False
    assert db.save_triage_result(gemini_other) is True
    assert db.save_triage_result(openai) is True
    assert len(db.get_triage_results(mock.candidate_id)) == 4
    assert db.get_triage_result(mock.candidate_id, "mock", "mock") == mock

    updated = replace(
        gemini, triage_status="REVIEW", triage_score=6,
        primary_reason="Updated Gemini result only.",
    )
    assert db.save_triage_result(updated, force_reanalyze=True) is True
    assert db.get_triage_result(mock.candidate_id, "gemini", "gemini-3.5-flash-lite") == updated
    assert db.get_triage_result(mock.candidate_id, "mock", "mock") == mock


class _GeminiMock(MockAIProvider):
    provider_name = "gemini"
    model_name = "gemini-3.5-flash-lite"


def test_mock_result_does_not_skip_gemini(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "triage.db")
    candidate = _candidate()
    mock = run_triage_batch([candidate]).processed[0]
    assert db.save_triage_result(mock) is True
    gemini_batch = run_triage_batch(
        [candidate], provider=_GeminiMock(), has_result=db.has_triage_result,
        save_result=db.save_triage_result,
    )
    assert gemini_batch.skipped_existing == 0
    assert len(gemini_batch.processed) == 1
    assert len(db.get_triage_results(candidate.candidate_id)) == 2


def test_legacy_unique_candidate_migration_preserves_mock(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE ai_triage_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL UNIQUE, triage_status TEXT NOT NULL,
            triage_score INTEGER NOT NULL, confidence TEXT NOT NULL,
            primary_reason TEXT NOT NULL, opportunity_type TEXT NOT NULL,
            key_opportunity TEXT NOT NULL, main_risks TEXT NOT NULL,
            needs_deep_analysis INTEGER NOT NULL, provider TEXT NOT NULL,
            model TEXT NOT NULL, analyzed_at TEXT NOT NULL)""")
        connection.execute("""INSERT INTO ai_triage_results
            (candidate_id, triage_status, triage_score, confidence,
             primary_reason, opportunity_type, key_opportunity, main_risks,
             needs_deep_analysis, provider, model, analyzed_at)
            VALUES ('legacy', 'REVIEW', 6, 'MEDIUM', 'kept', 'unknown',
                    'check', '[]', 1, 'mock', 'mock', '2026-01-01')""")
    assert db.init_db() is True
    assert db.has_triage_result("legacy", "mock", "mock") is True
    assert db.save_triage_result(replace(
        run_triage_batch([_candidate()]).processed[0], candidate_id="legacy",
        provider="gemini", model="gemini-3.5-flash-lite",
    )) is True
    assert len(db.get_triage_results("legacy")) == 2
