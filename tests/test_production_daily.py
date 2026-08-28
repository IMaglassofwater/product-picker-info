from __future__ import annotations

import json
from pathlib import Path

import db
from ai_providers import AIProviderError
from daily_ranker import OpportunityInput, apply_quality_gate, select_daily_top
from models import AITriageResult
from run_daily import DailyAIResult, execute_daily, run_daily_triage


WORKFLOW = (Path(__file__).parents[1] / ".github/workflows/daily-product-picker.yml").read_text(encoding="utf-8")


def opportunity(index: int, score: int = 70) -> OpportunityInput:
    return OpportunityInput(
        candidate_id=f"c{index}", title=f"Opportunity {index}", summary="Specific simple product gap",
        opportunity_type="Physical", candidate_type="demand_opportunity",
        source_platform="reddit_arctic_shift", source_url=f"https://example.test/{index}",
        candidate_score=score, feasibility_score=70, demand_score=70,
        micro_innovation_score=60, signals=["clear_feature_gap"],
    )


class FakeGemini:
    provider_name = "gemini"
    model_name = "gemini-3.5-flash-lite"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.api_calls_sent = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self.titles: list[str] = []

    def analyze(self, payload, _prompt, _schema):
        self.api_calls_sent += 1
        self.titles.append(payload["title"])
        if self.fail:
            raise AIProviderError("timeout")
        self.usage["input_tokens"] += 10
        self.usage["output_tokens"] += 5
        self.usage["total_tokens"] += 15
        return json.dumps({
            "triage_status": "PASS", "triage_score": 8, "confidence": "MEDIUM",
            "primary_reason": "Evidence supports validation.",
            "opportunity_type": "unmet_demand",
            "key_opportunity": "Could test a simple product improvement.",
            "main_risks": ["Supplier feasibility requires validation"],
            "needs_deep_analysis": True, "display_title_zh": "简单产品机会",
            "primary_reason_zh": "现有证据支持进一步验证。",
            "key_opportunity_zh": "可测试简单产品改进。",
            "main_risks_zh": ["供应链可行性仍需验证"],
        })


def setup_triage(monkeypatch, opportunities, existing=None):
    stored = set(existing or ())
    saved = []
    monkeypatch.setattr("run_daily.load_current_opportunities", lambda: opportunities)
    monkeypatch.setattr("run_daily._re_evaluation_candidates", lambda _items: {})
    monkeypatch.setattr(db, "get_candidate_commodity", lambda: {})
    monkeypatch.setattr(db, "get_all_products", lambda: [])
    monkeypatch.setattr(
        db, "has_triage_result",
        lambda candidate_id, provider, model: candidate_id in stored,
    )
    monkeypatch.setattr(
        db, "get_triage_candidate_ids",
        lambda provider, model: set(stored),
    )

    def save(result, force_reanalyze=False):
        stored.add(result.candidate_id)
        saved.append((result, force_reanalyze))
        return True

    monkeypatch.setattr(db, "save_triage_result", save)
    return stored, saved


def test_daily_limit_new_candidates_first_then_historical_backlog(monkeypatch):
    items = [opportunity(1, 50), opportunity(2, 90), opportunity(3, 80), opportunity(4, 70)]
    _, saved = setup_triage(monkeypatch, items, existing={"c4"})
    provider = FakeGemini()
    result = run_daily_triage(new_candidate_ids={"c1", "c2"}, limit=3, provider=provider)
    assert provider.titles == ["Opportunity 2", "Opportunity 1", "Opportunity 3"]
    assert result.selected == result.calls == result.successful == 3
    assert result.new_selected == 2 and result.backlog_selected == 1
    assert result.skipped_existing == 1 and result.pending == 0
    assert result.total_tokens == 45
    assert saved[0][0].display_title_zh == "简单产品机会"


def test_gemini_failures_continue_and_leave_ai_pending(monkeypatch):
    items = [opportunity(1), opportunity(2), opportunity(3)]
    setup_triage(monkeypatch, items)
    result = run_daily_triage(limit=3, provider=FakeGemini(fail=True))
    assert result.selected == result.calls == result.failed == 3
    assert result.successful == 0 and result.pending == 3


def test_existing_gemini_is_skipped(monkeypatch):
    items = [opportunity(1), opportunity(2)]
    setup_triage(monkeypatch, items, existing={"c1"})
    provider = FakeGemini()
    result = run_daily_triage(limit=5, provider=provider)
    assert result.skipped_existing == 1
    assert provider.titles == ["Opportunity 2"]


def test_re_evaluate_forces_only_requested_candidate(monkeypatch):
    item = opportunity(1)
    _, saved = setup_triage(monkeypatch, [item], existing={"c1"})
    monkeypatch.setattr("run_daily._re_evaluation_candidates", lambda _items: {"c1": 7})
    completed = []
    monkeypatch.setattr(db, "complete_re_evaluation", lambda request_id: completed.append(request_id) or True)
    result = run_daily_triage(limit=1, provider=FakeGemini())
    assert result.re_evaluated == 1 and completed == [7]
    assert saved == [(saved[0][0], True)]


def test_source_failure_is_partial_and_pipeline_stats_are_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily.db")

    def partial_pipeline(run_id):
        db.record_pipeline_source_run(run_id, "amazon", failed=True, error="unavailable")
        db.record_pipeline_source_run(run_id, "reddit_arctic_shift", fetched=2, new_count=2)
        return True

    result = execute_daily(
        pipeline_step=partial_pipeline,
        ai_step=lambda: DailyAIResult(30),
        lock_path=tmp_path / "daily.lock",
    )
    assert result.status == "PARTIAL"
    with db._connect() as connection:
        row = connection.execute(
            "SELECT status, stats_json FROM pipeline_runs WHERE run_id=?", (result.run_id,)
        ).fetchone()
    stats = json.loads(row["stats_json"])
    assert row["status"] == "PARTIAL"
    assert stats["new_products"] == 2
    assert len(stats["sources"]) == 2


def test_all_sources_failed_is_degraded_not_database_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily.db")

    def unavailable_sources(run_id):
        db.record_pipeline_source_run(run_id, "amazon", failed=True, error="offline")
        return True

    result = execute_daily(
        pipeline_step=unavailable_sources,
        ai_step=lambda: DailyAIResult(30),
        lock_path=tmp_path / "daily.lock",
    )
    assert result.status == "PARTIAL"


def test_missing_chinese_title_does_not_make_pipeline_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily.db")
    ai = DailyAIResult(5, successful=1)
    result = execute_daily(
        pipeline_step=lambda _run_id: True,
        ai_step=lambda: ai,
        lock_path=tmp_path / "daily.lock",
    )
    assert result.status == "SUCCESS"


def test_database_initialization_failure_is_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "init_db", lambda: False)
    result = execute_daily(
        pipeline_step=lambda _run_id: True,
        ai_step=lambda: DailyAIResult(5),
        lock_path=tmp_path / "daily.lock",
    )
    assert result.status == "FAILED"


def test_not_interested_is_excluded_from_today():
    item = opportunity(1)
    item.triage = AITriageResult(
        "c1", "PASS", 8, "MEDIUM", "reason", "unmet_demand", "test",
        [], False, "gemini", "gemini-3.5-flash-lite",
    )
    item.manual_status = "NOT_INTERESTED"
    assert apply_quality_gate(item) == (False, "not_interested")
    assert select_daily_top([item]).final == []


def test_production_workflow_schedule_manual_limit_and_neon_only():
    assert 'cron: "0 23 * * *"' in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
    assert 'default: "5"' in WORKFLOW
    assert "MAX_DAILY_TRIAGE_CALLS:" in WORKFLOW and "'30'" in WORKFLOW
    assert "if: github.event_name == 'workflow_dispatch' || vars.DAILY_SCHEDULE_ENABLED == 'true'" in WORKFLOW
    assert "DAILY_SCHEDULE_ENABLED: ${{ vars.DAILY_SCHEDULE_ENABLED || 'false' }}" in WORKFLOW
    assert 'PRODUCTION_DAILY: "true"' in WORKFLOW
    assert "secrets.DATABASE_URL" in WORKFLOW
    assert "product_picker.db" not in WORKFLOW and "D:\\" not in WORKFLOW
    assert "stats_json JSONB" in (Path(__file__).parents[1] / "postgres_backend.py").read_text(encoding="utf-8")
