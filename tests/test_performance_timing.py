"""Network-free performance instrumentation tests."""

from types import SimpleNamespace

import db
import main
from performance_timing import query_profile, record_query, timed_stage, timing_line
from postgres_backend import PostgresConnectionAdapter
from run_daily import run_daily_triage
from tests.test_pipeline import _FailingScraper, _MockScraper, _product
from tests.test_production_daily import FakeGemini, opportunity, setup_triage


def test_timing_logger_is_machine_readable_and_secret_safe():
    messages = []
    with timed_stage(messages.append, "ranking", source="test"):
        pass
    assert messages[0].startswith("[TIMING] source=test stage=ranking duration_s=")
    assert "DATABASE_URL" not in messages[0]
    assert "secret" not in timing_line(stage="safe", duration_s=1.0)


def test_query_counter_reports_repeated_patterns_without_sql_values():
    messages = []
    with query_profile(messages.append, "database") as profile:
        record_query("SELECT * FROM products WHERE id = 123", 0.02)
        record_query("SELECT * FROM products WHERE id = 456", 0.03)
    assert profile.count == 2 and profile.repeated_patterns == 1
    assert "query_count=2" in messages[0]
    assert "123" not in messages[0] and "456" not in messages[0]


def test_postgres_adapter_feeds_query_profiler():
    class Connection:
        def execute(self, _sql, _params):
            return SimpleNamespace(rowcount=1)

    messages = []
    with query_profile(messages.append, "postgres") as profile:
        PostgresConnectionAdapter(Connection()).execute(
            "SELECT * FROM products WHERE id = ?", (1,),
        )
    assert profile.count == 1
    assert "query_count=1" in messages[0]


def test_source_fetch_process_save_timing_and_failure_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "timing.db")
    messages = []
    scrapers = [
        _MockScraper("amazon", [_product("amazon", 1)]),
        _FailingScraper("kickstarter"),
    ]
    assert main.run_pipeline(scrapers=scrapers, output=messages.append)
    output = "\n".join(messages)
    assert "[TIMING] source=amazon stage=fetch" in output
    assert "[TIMING] source=amazon stage=process" in output
    assert "[TIMING] source=amazon stage=save" in output
    assert "[TIMING] source=kickstarter stage=fetch" in output
    assert "kickstarter mock failure" in output
    assert len(db.get_all_products()) == 1


def test_gemini_call_total_save_and_backlog_timing(monkeypatch):
    items = [opportunity(1)]
    setup_triage(monkeypatch, items)
    messages = []
    result = run_daily_triage(
        opportunities=items, limit=1, provider=FakeGemini(), output=messages.append,
    )
    output = "\n".join(messages)
    assert result.successful == 1
    assert "stage=backlog_selection" in output
    assert "stage=gemini_call" in output
    assert "stage=triage_save" in output
    assert "stage=gemini_total" in output


def test_snapshot_timing_is_emitted_without_changing_save_result(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "snapshot.db")
    messages = []
    product = _product(
        "amazon", 1, raw_data={"rank": 1, "rating": 4.8},
    )
    assert db.save_products([product], timing_output=messages.append) == (1, 0)
    assert any("stage=snapshot_writes" in line for line in messages)


def test_specificity_batch_and_triage_coverage_batch_preserve_results(tmp_path, monkeypatch):
    from opportunity_specificity import assess_specificity

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "batch.db")
    assert db.init_db()
    specificity = assess_specificity(
        "Compact organizer", "Simple storage product", ["clear_feature_gap"],
        "demand_opportunity", "reddit",
    )
    assert db.save_specificity_results(
        [("c1", specificity), ("c2", specificity)], rule_version="v1",
    ) == 2
    with db._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM specificity_results"
        ).fetchone()["count"]
    assert count == 2
    assert db.get_triage_candidate_ids("gemini", "model") == set()
