from __future__ import annotations

from datetime import datetime, timezone
import multiprocessing
from pathlib import Path
from time import perf_counter, sleep

import db
import main
from business_time import product_picker_business_date
from run_daily import DailyAIResult, execute_daily


def test_business_date_crosses_utc_boundary_into_shanghai_next_day():
    assert product_picker_business_date(
        datetime(2026, 9, 4, 23, 0, tzinfo=timezone.utc)
    ).isoformat() == "2026-09-05"


def test_business_date_normal_utc_daytime_is_same_shanghai_day():
    assert product_picker_business_date(
        datetime(2026, 9, 5, 6, 0, tzinfo=timezone.utc)
    ).isoformat() == "2026-09-05"


def test_budget_exhaustion_is_partial_and_daily_generation_continues(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily.db")
    ai = DailyAIResult(30, pending=4, budget_exhausted=True)
    result = execute_daily(
        pipeline_step=lambda _run_id: True,
        ai_step=lambda: ai,
        lock_path=tmp_path / "daily.lock",
    )
    assert result.status == "PARTIAL"
    assert "budget exhausted" in result.error
    assert "daily_discovery_count" in result.stats


def test_stale_running_pipeline_is_recovered_but_recent_one_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily.db")
    assert db.init_db()
    with db._connect() as connection:
        connection.execute(
            "INSERT INTO pipeline_runs(run_id, started_at, status) VALUES (?, ?, 'RUNNING')",
            ("old", "2026-09-05T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO pipeline_runs(run_id, started_at, status) VALUES (?, ?, 'RUNNING')",
            ("recent", "2026-09-05T01:45:00+00:00"),
        )
    recovered = db.recover_stale_pipeline_runs(
        stale_after_minutes=60,
        now=datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc),
    )
    assert recovered == ["old"]
    with db._connect() as connection:
        rows = {
            row["run_id"]: (row["status"], row["error"])
            for row in connection.execute(
                "SELECT run_id, status, error FROM pipeline_runs ORDER BY run_id"
            ).fetchall()
        }
    assert rows["old"] == (
        "FAILED", "stale run recovered after external cancellation",
    )
    assert rows["recent"] == ("RUNNING", "")


class _SlowCollector:
    def __init__(self, source_name: str, delay: float):
        self.source_name = source_name
        self.delay = delay

    def fetch(self):
        sleep(self.delay)
        return []


class _NonCooperativeCollector:
    source_name = "noncooperative"

    def __init__(self, marker: str):
        self.marker = marker

    def fetch(self):
        sleep(0.2)
        Path(self.marker).write_text("worker survived", encoding="utf-8")
        return []


def test_source_network_wall_clock_cannot_bypass_budget():
    started = perf_counter()
    try:
        main._fetch_with_wall_clock(_SlowCollector("slow", 0.25), 0.02)
    except Exception as exc:
        assert "wall-clock budget" in str(exc)
    else:
        raise AssertionError("slow collector unexpectedly completed")
    assert perf_counter() - started < 0.15


def test_noncooperative_collector_is_terminated_and_reaped(tmp_path):
    marker = tmp_path / "survived.txt"
    try:
        main._fetch_with_wall_clock(_NonCooperativeCollector(str(marker)), 0.02)
    except Exception as exc:
        assert "worker terminated" in str(exc)
    else:
        raise AssertionError("noncooperative collector unexpectedly completed")
    sleep(0.25)
    assert not marker.exists()
    assert not any(
        child.name == "collector-noncooperative"
        for child in multiprocessing.active_children()
    )


def test_actual_orchestration_reaches_daily_tail_after_slow_collectors(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily.db")
    monkeypatch.setattr(
        main, "SCRAPERS",
        [_SlowCollector(f"slow_{index}", 0.03) for index in range(4)],
    )
    monkeypatch.setattr(main.config, "DAILY_SOURCE_BUDGET_SECONDS", 0.04)
    tail: list[str] = []

    def discovery(run_id, **_kwargs):
        tail.append("daily")
        return {"run_id": f"daily:{run_id}", "items": [], "item_count": 0}

    def picks(_snapshot, **_kwargs):
        tail.append("picks")
        return {"run_id": "picks:test", "item_count": 0, "items": []}

    monkeypatch.setattr("daily_discovery.build_daily_discovery", discovery)
    monkeypatch.setattr("daily_picks.build_daily_picks", picks)
    messages: list[str] = []
    started = perf_counter()
    result = execute_daily(
        ai_step=lambda: DailyAIResult(30), lock_path=tmp_path / "daily.lock",
        output=messages.append, preparation_budget_seconds=0.05,
    )
    # Windows spawn startup is intentionally included; the important bound is
    # that the non-cooperative work cannot approach its own sleep/runtime.
    assert perf_counter() - started < 2.0
    assert result.status == "PARTIAL"
    assert tail == ["daily", "picks"]
    assert "DAILY_GENERATION_START" in messages
    assert any("SOURCE_SKIPPED_BUDGET" in value for value in messages)


def test_short_budget_orchestration_persists_daily_run_and_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "short-budget.db")
    monkeypatch.setattr(
        main, "SCRAPERS", [_SlowCollector("blocked", 5.0)],
    )
    monkeypatch.setattr(main.config, "DAILY_SOURCE_BUDGET_SECONDS", 0.03)
    messages: list[str] = []

    result = execute_daily(
        ai_step=lambda: DailyAIResult(30), lock_path=tmp_path / "daily.lock",
        output=messages.append, preparation_budget_seconds=0.05,
    )

    assert result.status == "PARTIAL"
    assert "DAILY_GENERATION_START" in messages
    with db._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM daily_discovery_runs"
        ).fetchone()["count"] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_recent_persisted_daily_evidence_is_reused_without_fake_freshness(monkeypatch):
    from daily_discovery import build_daily_discovery

    old = {
        "family_id": 7, "canonical_name": "Existing product",
        "canonical_name_zh": "已有产品", "factual_description": "Known facts",
        "latest_observed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_strength": "MODERATE", "source_records": [],
    }
    monkeypatch.setattr(db, "get_daily_discovery", lambda _run_id: [])
    monkeypatch.setattr(
        db, "get_persisted_daily_discovery", lambda **_identity: {"items": [old]},
    )
    result = build_daily_discovery("new-run", persist=False)
    assert [value["family_id"] for value in result["items"]] == [7]
    assert result["items"][0]["latest_observed_at"] == old["latest_observed_at"]
