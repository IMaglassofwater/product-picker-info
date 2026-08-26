from __future__ import annotations

from pathlib import Path

import db
from database_backend import get_database_settings
from postgres_backend import POSTGRES_SCHEMA, PostgresConnectionAdapter, _translate_sql
from scripts.cloud_smoke_test import run_smoke
from scripts.migrate_sqlite_to_postgres import inspect_production_selection


ROOT = Path(__file__).parents[1]
WORKFLOW = (ROOT / ".github/workflows/daily-product-picker.yml").read_text(encoding="utf-8")


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self


def test_postgres_database_url_selects_postgres_backend_without_exposing_url():
    settings = get_database_settings("postgresql://host/database")
    assert settings.backend == "postgresql"
    assert settings.sqlite_path is None
    assert "database_url" not in repr(settings)


def test_postgres_adapter_translates_placeholders_and_insert_ignore():
    assert _translate_sql("SELECT * FROM products WHERE url = ?").endswith("url = %s")
    translated = _translate_sql("INSERT OR IGNORE INTO processed_projects (url) VALUES (?)")
    assert "INSERT INTO" in translated
    assert "%s" in translated
    assert translated.endswith("ON CONFLICT DO NOTHING")
    fake = FakeConnection()
    PostgresConnectionAdapter(fake).execute("SELECT ?", (1,))
    assert fake.calls == [("SELECT %s", (1,))]


def test_postgres_schema_uses_cloud_types_constraints_and_indexes():
    assert "TIMESTAMPTZ" in POSTGRES_SCHEMA
    assert "JSONB" in POSTGRES_SCHEMA
    assert "BOOLEAN" in POSTGRES_SCHEMA
    assert "UNIQUE(candidate_id, provider, model)" in POSTGRES_SCHEMA
    assert "idx_products_source" in POSTGRES_SCHEMA
    assert "idx_feedback_entity" in POSTGRES_SCHEMA


def test_production_filter_and_skipped_product_reason_are_documented():
    plan = inspect_production_selection()
    assert plan["Products"].keep == 652
    assert plan["Products"].skip == 1
    assert plan["Gemini Triage"].keep == 24
    assert plan["Mock Triage"].keep == 0
    document = (ROOT / "docs/production_data_migration_plan.md").read_text(encoding="utf-8")
    assert "source_platform=Test" in document
    assert "invalid development record" in document


def test_workflow_has_schedule_manual_trigger_and_only_secret_references():
    assert "schedule:" in WORKFLOW
    assert 'cron: "0 23 * * *"' in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
    assert "push:" not in WORKFLOW
    assert "secrets.DATABASE_URL" in WORKFLOW
    assert "secrets.GEMINI_API_KEY" in WORKFLOW
    assert "postgresql://" not in WORKFLOW
    assert "AIza" not in WORKFLOW


def test_cloud_smoke_read_only_does_not_write_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "smoke.db")
    result = run_smoke(read_only=True)
    assert result["backend"] == "sqlite"
    assert result["feedback_writable"] == "not tested"
    with db._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM user_product_feedback").fetchone()[0] == 0


def test_web_and_worker_entries_remain_separate():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    worker = (ROOT / "run_daily.py").read_text(encoding="utf-8")
    assert "run_daily" not in app
    assert "run_pipeline" not in app
    assert "streamlit" not in worker.casefold()
    assert 'if db.DATABASE_SETTINGS.backend == "sqlite"' in (ROOT / "dashboard_data.py").read_text(encoding="utf-8")
