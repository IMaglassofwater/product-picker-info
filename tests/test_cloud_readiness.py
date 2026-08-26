from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import db
from bilingual_display import bilingual_content
from database_backend import DEFAULT_SQLITE_PATH, get_database_settings
from models import Product
from run_daily import execute_daily
from scripts.check_secrets import scan_project
from scripts.migrate_sqlite_to_postgres import (
    inspect_production_selection,
    inspect_sqlite,
    main as migration_main,
)
from time_utils import format_tokyo, to_tokyo


def test_database_url_absent_uses_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = get_database_settings()
    assert settings.backend == "sqlite"
    assert settings.sqlite_path == DEFAULT_SQLITE_PATH


def test_postgresql_url_routes_to_future_backend():
    settings = get_database_settings("postgresql://example.invalid/app")
    assert settings.backend == "postgresql"
    assert settings.sqlite_path is None
    assert "database_url" not in repr(settings)


def test_existing_sqlite_data_is_readable():
    report = inspect_sqlite()
    assert report.table_counts["products"] > 0


def test_app_does_not_import_scrapers_or_pipeline():
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    assert "scrapers" not in source
    assert "run_pipeline" not in source


def test_run_daily_does_not_import_streamlit():
    source = (Path(__file__).parents[1] / "run_daily.py").read_text(encoding="utf-8")
    assert "streamlit" not in source.casefold()


def test_gemini_failure_keeps_product_and_marks_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily.db")

    def save_one(_run_id: str) -> bool:
        product = Product(
            project_id="cloud-test", source_platform="test", url="https://example.test/product",
            title="Test product", description="Simple product", category="test",
            image_url="https://example.test/product.jpg", raw_data={},
        )
        db.create_product(product)
        return True

    def unavailable_ai() -> int:
        raise TimeoutError("provider unavailable")

    result = execute_daily(
        pipeline_step=save_one, ai_step=unavailable_ai,
        lock_path=tmp_path / "daily.lock",
    )
    assert result.status == "PARTIAL"
    assert len(db.get_all_products()) == 1
    assert db.get_triage_results("missing") == []


def test_migration_dry_run_counts_every_table(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "migration.db")
    assert db.init_db()
    report = inspect_sqlite(db.DB_PATH)
    assert "products" in report.table_counts
    assert "pipeline_runs" in report.table_counts
    assert migration_main(["--source", str(db.DB_PATH)]) == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_production_only_classification_and_dry_run_are_read_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "production.db")
    assert db.init_db()
    with db._connect() as connection:
        connection.execute(
            "INSERT INTO products (project_id,source_platform,url,title,description,category,image_url,raw_data) VALUES ('real','amazon','https://real','Real','','home','https://image','{}')"
        )
        connection.execute(
            "INSERT INTO products (project_id,source_platform,url,title,description,category,image_url,raw_data) VALUES ('test','Test','https://test','Test','','test','https://image','{}')"
        )
        for provider, model in (("gemini", "gemini-3.5-flash-lite"), ("mock", "mock")):
            connection.execute(
                """INSERT INTO ai_triage_results
                   (candidate_id,triage_status,triage_score,confidence,primary_reason,
                    opportunity_type,key_opportunity,main_risks,needs_deep_analysis,
                    provider,model,analyzed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (provider, "PASS", 8, "HIGH", "reason", "unknown", "opportunity", "[]", 0, provider, model, "2026-01-01T00:00:00+00:00"),
            )
    before = db.DB_PATH.read_bytes()
    plan = inspect_production_selection(db.DB_PATH)
    assert plan["Products"].keep == 1 and plan["Products"].skip == 1
    assert plan["Gemini Triage"].keep == 1
    assert plan["Mock Triage"].keep == 0 and plan["Mock Triage"].skip == 1
    assert migration_main(["--source", str(db.DB_PATH), "--dry-run", "--production-only"]) == 0
    assert db.DB_PATH.read_bytes() == before
    output = capsys.readouterr().out
    assert "Products: KEEP 1 / SKIP 1" in output
    assert "Mock Triage: KEEP 0 / SKIP 1" in output


def test_project_source_has_no_potential_secrets():
    assert scan_project() == []


def test_tokyo_helpers_convert_from_utc():
    value = datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc)
    assert to_tokyo(value).hour == 9
    assert format_tokyo(value).endswith("JST")


def test_bilingual_fallback_uses_english_as_primary():
    fallback = bilingual_content("English evidence", None)
    assert fallback.primary == "English evidence"
    assert fallback.chinese_pending is True
    translated = bilingual_content("English evidence", "中文证据")
    assert translated.primary == "中文证据"
    assert translated.english_comparison == "English evidence"
