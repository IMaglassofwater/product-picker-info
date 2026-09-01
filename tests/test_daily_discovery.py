"""Phase 11F single-source-of-truth tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import db
from daily_discovery import (
    build_daily_discovery, filter_today_items, render_wxpusher_chunks,
    today_renderer_items, wxpusher_family_ids,
)
from evidence_shadow import process_products_for_run
from models import Product


def product(index: int, *, source="amazon", title=None, raw=None) -> Product:
    return Product(
        f"daily-{index}", source, f"https://example.com/{index}",
        title or f"Artifact {index:03d} unique object", f"Factual description {index}",
        "home", f"https://example.com/{index}.jpg", raw or {},
    )


def dataset(tmp_path, monkeypatch, count=3, raw=None):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "daily.sqlite")
    names = ("Travel backpack", "Camping lantern", "Manual can opener", "Ceramic pet bowl", "Desk organizer")
    items = [product(i, title=names[(i - 1) % len(names)], raw=raw if i == 1 else None) for i in range(1, count + 1)]
    assert db.save_products(items)[0] == count
    run_id = db.start_pipeline_run()
    process_products_for_run(run_id, items)
    db.finish_pipeline_run(run_id, "COMPLETED")
    result = build_daily_discovery(run_id)
    return result, items


def test_persistence_membership_and_ai_independence(tmp_path, monkeypatch):
    result, _ = dataset(tmp_path, monkeypatch, 4)
    loaded = db.get_persisted_daily_discovery(pipeline_run_id=result["pipeline_run_id"])
    assert loaded and loaded["item_count"] == 4
    assert [x["family_id"] for x in loaded["items"]] == [x["family_id"] for x in result["items"]]
    with sqlite3.connect(db.DB_PATH) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ai_triage_results").fetchone()[0] == 0


def test_historical_favorite_not_today_but_observed_favorite_is(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "favorite.sqlite")
    old, current = product(1, title="Compact desk organizer"), product(2, title="Portable camping lantern")
    db.save_products([old, current])
    old_run = db.start_pipeline_run(); process_products_for_run(old_run, [old]); db.finish_pipeline_run(old_run, "COMPLETED")
    old_family = db.get_daily_discovery(old_run)[0]["family_id"]
    assert db.save_family_feedback(old_family, "FAVORITE")
    new_run = db.start_pipeline_run(); process_products_for_run(new_run, [current]); db.finish_pipeline_run(new_run, "COMPLETED")
    assert old_family not in {x["family_id"] for x in build_daily_discovery(new_run)["items"]}
    seen_run = db.start_pipeline_run(); process_products_for_run(seen_run, [old]); db.finish_pipeline_run(seen_run, "COMPLETED")
    assert old_family in {x["family_id"] for x in build_daily_discovery(seen_run)["items"]}


def test_stable_order_weak_included_and_renderer_parity(tmp_path, monkeypatch):
    result, _ = dataset(tmp_path, monkeypatch, 5)
    base = result["items"]
    result["items"] = [
        {**base[index % len(base)], "family_id": index + 100, "canonical_name": f"Synthetic {index:03d}", "display_order": index + 1}
        for index in range(45)
    ]
    assert any(x["evidence_strength"] == "WEAK" for x in result["items"])
    today = today_renderer_items(result)
    chunks = render_wxpusher_chunks(result, items_per_chunk=20)
    ids = [x["family_id"] for x in result["items"]]
    assert ids == [x["family_id"] for x in today] == wxpusher_family_ids(chunks)
    assert [len(x["items"]) for x in chunks] == [20, 20, 5]
    assert [x["display_order"] for x in result["items"]] == list(range(1, 46))


def test_no_feedback_is_not_invented_and_real_feedback_keeps_provenance(tmp_path, monkeypatch):
    result, _ = dataset(tmp_path, monkeypatch, 2, raw={"review_texts": ["Useful compact shape"]})
    by_order = result["items"]
    with_feedback = next(item for item in by_order if item["actual_feedback"])
    without = next(item for item in by_order if not item["actual_feedback"])
    assert with_feedback["actual_feedback"][0]["text"] == "Useful compact shape"
    assert with_feedback["actual_feedback"][0]["source_url"]
    assert without["feedback_available"] is False
    html = "".join(x["content"] for x in render_wxpusher_chunks(result))
    assert "暂无用户文字反馈" in html


def test_family_favorite_and_soft_hide_do_not_mutate_snapshot(tmp_path, monkeypatch):
    result, _ = dataset(tmp_path, monkeypatch, 2)
    family_id = result["items"][0]["family_id"]
    assert db.save_family_feedback(family_id, "FAVORITE")
    assert len(filter_today_items(result["items"])) == 2
    assert db.save_family_feedback(family_id, "HIDDEN", "太复杂", "manual")
    assert len(filter_today_items(result["items"])) == 1
    assert len(db.get_persisted_daily_discovery(pipeline_run_id=result["pipeline_run_id"])["items"]) == 2
    state = db.get_family_feedback_map()[family_id]
    assert state["details"] == {"reason": "太复杂", "note": "manual"}


def test_failed_rebuild_does_not_corrupt_existing_snapshot(tmp_path, monkeypatch):
    result, _ = dataset(tmp_path, monkeypatch, 2)
    before = db.get_persisted_daily_discovery(pipeline_run_id=result["pipeline_run_id"])
    monkeypatch.setattr(db, "persist_daily_discovery_snapshot", lambda *a, **k: None)
    build_daily_discovery(result["pipeline_run_id"])
    after = db.get_persisted_daily_discovery(pipeline_run_id=result["pipeline_run_id"])
    assert after == before


def test_missing_translation_falls_back_without_removal(tmp_path, monkeypatch):
    result, _ = dataset(tmp_path, monkeypatch, 1)
    item = result["items"][0]
    assert item["canonical_name_zh"] == item["canonical_name"]
    assert result["item_count"] == 1


def test_postgres_schema_contains_daily_snapshot_tables():
    from postgres_backend import POSTGRES_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS daily_discovery_runs" in POSTGRES_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS daily_discovery_items" in POSTGRES_SCHEMA


def test_streamlit_evidence_today_renders_persisted_dataset(tmp_path, monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    result, _ = dataset(tmp_path, monkeypatch, 3)
    monkeypatch.setenv("EVIDENCE_FIRST_TODAY_ENABLED", "true")
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=20).run(timeout=20)
    assert not app.exception
    app.radio[0].set_value("🔥 今日机会 / Today").run(timeout=20)
    assert not app.exception
    rendered = [value.value for value in app.subheader]
    assert f"今天发现 {result['item_count']} 个产品" in rendered
    assert {item["canonical_name_zh"] for item in result["items"]}.issubset(rendered)
    st.cache_data.clear()
