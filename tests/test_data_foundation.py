"""Phase 9.5B lifecycle, history, run tracking, and feedback tests."""

import json
import sqlite3

import db
from candidate_pool import MicroInnovationCandidate
from commodity_filter import CommodityResult
from models import AITriageResult, Product
from opportunity_specificity import SpecificityResult
from rule_filter import FilterResult


def _product(raw=None, title="Compact organizer"):
    return Product(
        "p1", "amazon", "https://example.com/p1", title,
        "Simple compact organizer", "home", "https://example.com/i.jpg",
        raw or {"rank": 5, "rating": 4.5, "review_count": 10},
    )


def test_lifecycle_duplicate_updates_raw_data_and_metric_changes_only(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "db.sqlite")
    first = _product()
    assert db.save_products([first]) == (1, 0)
    lifecycle1 = db.get_product_lifecycle(first.url)
    snapshots1 = db.get_metric_snapshots(lifecycle1["id"])
    assert lifecycle1["first_seen_at"] and lifecycle1["last_seen_at"] and lifecycle1["updated_at"]
    assert len(snapshots1) == 1

    assert db.save_products([_product()]) == (0, 1)
    assert len(db.get_metric_snapshots(lifecycle1["id"])) == 1
    changed = _product({"rank": 3, "rating": 4.6, "review_count": 12})
    changed.description = "Updated public description"
    assert db.save_products([changed]) == (0, 1)
    lifecycle2 = db.get_product_lifecycle(first.url)
    assert lifecycle2["first_seen_at"] == lifecycle1["first_seen_at"]
    assert lifecycle2["last_seen_at"] >= lifecycle1["last_seen_at"]
    assert len(db.get_metric_snapshots(lifecycle1["id"])) == 2
    assert db.get_product_by_url(first.url).raw_data["rank"] == 3
    assert db.get_product_by_url(first.url).description == "Updated public description"


def test_pipeline_run_source_stats_are_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "db.sqlite")
    assert db.init_db()
    run_id = db.start_pipeline_run()
    assert run_id
    assert db.record_pipeline_source_run(run_id, "reddit", fetched=5, new_count=3, updated_count=2, rejected=1, candidates_created=1)
    assert db.finish_pipeline_run(run_id, "COMPLETED")
    with sqlite3.connect(db.DB_PATH) as connection:
        assert connection.execute("SELECT status FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()[0] == "COMPLETED"
        assert connection.execute("SELECT fetched FROM pipeline_source_runs WHERE run_id=?", (run_id,)).fetchone()[0] == 5


def test_specificity_and_user_feedback_actions_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "db.sqlite")
    assert db.init_db()
    specificity = SpecificityResult("TOO_BROAD", 20, "No product gap.", ["general_advice"])
    assert db.save_specificity_result("c1", specificity, rule_version="v1")
    for status in ("FAVORITE", "WATCH", "NOT_INTERESTED"):
        assert db.save_user_feedback("candidate", "c1", status)
        with sqlite3.connect(db.DB_PATH) as connection:
            assert connection.execute("SELECT feedback_type FROM user_product_feedback").fetchone()[0] == status
    assert db.request_re_evaluation("candidate", "c1", "rules changed")
    with sqlite3.connect(db.DB_PATH) as connection:
        assert connection.execute("SELECT specificity_status FROM specificity_results").fetchone()[0] == "TOO_BROAD"
        assert connection.execute("SELECT status FROM re_evaluation_requests").fetchone()[0] == "PENDING"


def test_rejected_commodity_and_gemini_reject_do_not_delete_product(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "db.sqlite")
    product = _product()
    rule = FilterResult(1, "rejected", "regulated", "physical")
    commodity = CommodityResult("COMMODITY", 10, "mature", ["highly_mature_category"])
    assert db.save_products([product], {product.url: rule}, commodity_results={product.url: commodity}) == (1, 0)
    triage = AITriageResult("c1", "REJECT", 2, "HIGH", "No fit", "unknown", "Drop", ["risk"], False, "gemini", "model")
    assert db.save_triage_result(triage)
    assert db.get_product_by_url(product.url) is not None
    with sqlite3.connect(db.DB_PATH) as connection:
        row = connection.execute("SELECT filter_status, commodity_status FROM products").fetchone()
        assert row == ("rejected", "COMMODITY")


def test_migration_backfills_old_product_and_preserves_old_tables(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite"
    monkeypatch.setattr(db, "DB_PATH", path)
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
            source_platform TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
            image_url TEXT NOT NULL, raw_data TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("""INSERT INTO products
            (project_id,source_platform,url,title,description,category,image_url,raw_data,created_at)
            VALUES ('p','legacy','https://example.com/old','Old','Old','old','https://example.com/i','{}','2025-01-01 00:00:00')""")
    assert db.init_db()
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT first_seen_at,last_seen_at,updated_at FROM products").fetchone()
        assert row == ("2025-01-01 00:00:00",) * 3
        assert connection.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
        tables = {x[0] for x in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"ai_triage_results", "deep_analysis_results", "software_analysis_results"}.issubset(tables)
