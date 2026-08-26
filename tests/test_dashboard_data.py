from datetime import datetime, timezone
import json
import sqlite3

import db
from candidate_pool import MicroInnovationCandidate
from dashboard_data import (
    ProductFilters,
    clear_manual_status,
    enqueue_re_evaluation,
    filter_products,
    load_dashboard_snapshot,
    save_manual_status,
)
from models import AITriageResult, Product


def product(index=1, *, source="reddit_arctic_shift", description="", category="organization"):
    return Product(
        project_id=f"p{index}", source_platform=source,
        url=f"https://example.com/{index}", title=f"Desk organizer {index}",
        description=description, category=category, image_url=f"https://example.com/{index}.jpg",
        raw_data={"rank": index},
    )


def setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    assert db.init_db()
    return db.DB_PATH


def test_runtime_dashboard_loads_every_database_product():
    with sqlite3.connect(db.DB_PATH) as connection:
        stored = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert stored >= 653
    assert len(load_dashboard_snapshot().products) == stored


def test_empty_description_remains_loadable_and_not_analyzed(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    assert db.create_product(product(description=""))
    assert db.get_all_products()[0].description == ""
    item = load_dashboard_snapshot().products[0]
    assert item.description == ""
    assert item.gemini_status == "NOT_ANALYZED"


def test_keyword_source_date_type_and_status_filters(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    reddit = product(1, description="Compact cable storage")
    software = product(2, source="product_hunt", description="Browser workspace", category="software")
    db.save_products([reddit, software])
    with db._connect() as connection:
        connection.execute("UPDATE products SET record_role='software', opportunity_type='software' WHERE url=?", (software.url,))
        connection.execute("UPDATE products SET filter_status='rejected' WHERE url=?", (reddit.url,))
    items = load_dashboard_snapshot().products
    assert [p.id for p in filter_products(items, ProductFilters(keyword="cable"))] == [1]
    assert [p.id for p in filter_products(items, ProductFilters(sources=("Product Hunt",)))] == [2]
    assert len(filter_products(items, ProductFilters(date_range="today"))) == 2
    assert [p.id for p in filter_products(items, ProductFilters(product_types=("software",)))] == [2]
    assert len(filter_products(items, ProductFilters(gemini_statuses=("AI_PENDING",)))) == 1
    assert len(filter_products(items, ProductFilters(gemini_statuses=("NOT_ANALYZED",)))) == 1
    assert [p.id for p in filter_products(items, ProductFilters(rule_statuses=("rejected",)))] == [1]
    assert [p.id for p in filter_products(items, ProductFilters(rejected_only=True))] == [1]


def test_feedback_is_mutually_exclusive_and_re_evaluation_persists(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    db.create_product(product())
    assert save_manual_status(1, "FAVORITE")
    assert load_dashboard_snapshot().products[0].manual_status == "FAVORITE"
    assert save_manual_status(1, "WATCH")
    assert load_dashboard_snapshot().products[0].manual_status == "WATCH"
    assert save_manual_status(1, "NOT_INTERESTED")
    with db._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM user_product_feedback").fetchone()[0] == 1
    assert enqueue_re_evaluation(1)
    assert len(load_dashboard_snapshot().re_evaluation_queue) == 1
    assert clear_manual_status(1)
    assert load_dashboard_snapshot().products[0].manual_status == ""


def test_ai_reject_can_still_be_favorited(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    item = product(description="Simple organizer")
    db.create_product(item)
    candidate = MicroInnovationCandidate(
        candidate_id="c1", candidate_type="validated_product", source_platform=item.source_platform,
        source_url=item.url, title=item.title, summary=item.description,
        candidate_score=70, feasibility_score=70, demand_score=0,
        market_validation_score=0, micro_innovation_score=60,
        reason="test", signals=[], raw_reference_id=item.project_id,
    )
    db.save_candidates([candidate])
    db.save_triage_result(AITriageResult(
        candidate_id="c1", triage_status="REJECT", triage_score=3,
        confidence="HIGH", primary_reason="Not suitable", opportunity_type="product_improvement",
        key_opportunity="None", main_risks=[], needs_deep_analysis=False,
        provider="gemini", model="gemini-3.5-flash-lite",
    ))
    assert load_dashboard_snapshot().products[0].gemini_status == "REJECT"
    assert save_manual_status(1, "FAVORITE")
    assert load_dashboard_snapshot().products[0].manual_status == "FAVORITE"


def test_metric_history_and_pipeline_status_are_loaded(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    item = product(source="amazon", description="Simple home item")
    db.save_products([item])
    run_id = db.start_pipeline_run()
    assert db.record_pipeline_source_run(run_id, "amazon", fetched=3, new_count=1, updated_count=2)
    assert db.finish_pipeline_run(run_id, "COMPLETED")
    snapshot = load_dashboard_snapshot()
    assert snapshot.products[0].metric_history[0]["rank"] == 1
    assert snapshot.pipeline_sources[0]["fetched"] == 3
    assert snapshot.pipeline_sources[0]["run"]["status"] == "COMPLETED"


def test_dashboard_objects_do_not_expose_raw_data_or_secrets(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    item = product(description="Visible text")
    item.raw_data = {"GEMINI_API_KEY": "secret", "private": "hidden"}
    db.create_product(item)
    dashboard_item = load_dashboard_snapshot().products[0]
    assert not hasattr(dashboard_item, "raw_data")
    assert "secret" not in repr(dashboard_item)
