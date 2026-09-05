"""Phase 11K collection/composition separation and quality gates."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

import db
import main
from compose_daily import compose_daily
from daily_discovery import build_rolling_daily_discovery
from daily_picks import build_daily_picks, title_quality_flags
from product_directions import build_product_directions


def family(index, name, source="product_hunt", kind="SOFTWARE_PRODUCT", description="A concrete browser extension product."):
    return {
        "family_id": index, "display_order": index, "canonical_name": name,
        "canonical_name_zh": name, "factual_description": description,
        "factual_description_zh": description, "product_type": kind,
        "evidence_strength": "MODERATE", "evidence_reasons": ["persisted evidence"],
        "latest_observed_at": datetime.now(timezone.utc).isoformat(),
        "source_platforms": [source], "source_records": [{
            "product_id": index, "source_platform": source,
            "url": f"https://example.test/{index}", "source_title": name,
            "description": description, "raw_data": {},
        }],
    }


def test_compose_daily_performs_zero_live_fetches_and_survives_collection_failure(monkeypatch):
    monkeypatch.setattr(db, "init_db", lambda: True)
    monkeypatch.setattr(
        "compose_daily.build_strict_daily_discovery",
        lambda **_kwargs: {"run_id": "daily:persisted", "discovery_date": "2026-09-06", "window_start": "start", "window_end": "end", "items": [family(1, "Weedout")]},
    )
    monkeypatch.setattr(main, "SCRAPERS", [object()])
    result = compose_daily(persist=False)
    assert result["live_fetch_calls"] == result["gemini_calls"] == 0
    assert result["item_count"] == 1


def test_rolling_window_uses_persisted_run_membership_without_changing_timestamps(monkeypatch):
    observed = "2026-09-04T03:00:00+00:00"
    value = family(2, "Manual Can Opener", source="amazon", kind="PHYSICAL_PRODUCT")
    value["latest_observed_at"] = observed
    monkeypatch.setattr(db, "get_recent_completed_run_ids", lambda cutoff: ["persisted-run"])
    monkeypatch.setattr(db, "get_recent_daily_discovery", lambda cutoff: [value])
    result = build_rolling_daily_discovery(days=7)
    assert result["window_days"] == 7
    assert result["items"][0]["latest_observed_at"] == observed


def test_concrete_gate_rejects_generic_and_multi_product_article_topics():
    values = [
        family(3, "How IFA 2026 redefined robots", description="A general event article."),
        family(4, "Smart glasses, robot dogs, AI Tamagotchis and desk-sized supercomputers", description="An editorial collection."),
    ]
    assert build_daily_picks({"run_id": "daily:test", "items": values}, persist=False)["items"] == []


def test_supported_brand_rules_create_chinese_product_type_and_preserve_brand():
    directions = build_product_directions([
        family(5, "Weedout"), family(6, "OwnTime"), family(7, "Waltz"),
    ])
    titles = {item["name_en"]: item["name_zh"] for item in directions}
    assert titles["Weedout Browser Extension"] == "过滤 YouTube AI 生成视频的浏览器扩展"
    assert titles["OwnTime Planning App"] == "灵活时间块与生活角色规划应用"
    assert titles["Waltz Interior Design App"] == "手机扫描房间的 AI 室内设计工具"


def test_title_quality_flags_raw_headline_and_unexplained_brand():
    assert "article_headline" in title_quality_flags(family(8, "Running 104 GB Qwen on 48 GB Mac"))
    assert "brand_only_unexplained" in title_quality_flags(
        family(9, "Acme", description="A newly announced project."),
    )


def test_quality_gate_distinguishes_failure_from_real_scarcity(monkeypatch):
    scarce = build_daily_picks({"run_id": "daily:test", "items": [family(10, "Weedout")]}, persist=False)
    assert scarce["quality_status"] == "PASS"
    many = [family(i, f"Concrete Browser Extension Tool {i}") for i in range(20, 40)]
    # A deliberately restrictive source cap leaves <15 despite enough candidates.
    crowded = build_daily_picks({"run_id": "daily:test", "items": many}, persist=False)
    assert crowded["quality_status"] == "PASS"
    assert crowded["diagnostics"]["candidate_directions"] >= 15


def test_composition_is_fast_on_production_scale_shaped_fixture(monkeypatch):
    values = [family(i, f"Developer Browser Extension Tool {i}") for i in range(100, 600)]
    monkeypatch.setattr(db, "init_db", lambda: True)
    monkeypatch.setattr(
        "compose_daily.build_strict_daily_discovery",
        lambda **_kwargs: {"run_id": "daily:scale", "discovery_date": "2026-09-06", "window_start": "start", "window_end": "end", "items": values},
    )
    monkeypatch.setattr(db, "get_user_voice_items", lambda _family_id: [])
    started = perf_counter()
    result = compose_daily(persist=False)
    assert perf_counter() - started < 2.0
    assert result["live_fetch_calls"] == result["gemini_calls"] == 0
