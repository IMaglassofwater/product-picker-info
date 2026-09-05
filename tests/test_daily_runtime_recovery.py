from __future__ import annotations

from datetime import datetime, timezone

import db
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
