"""Final strict noon-to-noon production Daily rules."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import config
import db
import run_collection
from business_window import daily_window, effective_evidence_timestamp, record_in_window
from daily_discovery import build_strict_daily_discovery, build_rolling_daily_discovery


ZONE = ZoneInfo("Asia/Shanghai")


def record(source_time=None, observed="2026-09-06T03:00:00+00:00"):
    raw = {} if source_time is None else {"published_at": source_time}
    return {"raw_data": raw, "observation_timestamp": observed}


def test_noon_boundaries_are_exact_and_business_date_is_delivery_date():
    start, end, business_date = daily_window("2026-09-06")
    assert business_date.isoformat() == "2026-09-06"
    assert not record_in_window(record("2026-09-05T11:59:59+08:00"), start, end)
    assert record_in_window(record("2026-09-05T12:00:00+08:00"), start, end)
    assert record_in_window(record("2026-09-06T11:59:59+08:00"), start, end)
    assert not record_in_window(record("2026-09-06T12:00:00+08:00"), start, end)
    assert end.astimezone(ZoneInfo("UTC")).hour == 4
    assert datetime(2026, 9, 6, 13, tzinfo=ZONE).astimezone(ZoneInfo("UTC")).hour == 5


def test_source_timestamp_wins_and_collection_does_not_refresh_old_content():
    timestamp, method = effective_evidence_timestamp(record(
        "2026-09-04T18:00:00+08:00", observed="2026-09-06T02:00:00+00:00",
    ))
    assert timestamp.isoformat().startswith("2026-09-04T18:00:00")
    assert method == "source:published_at"


def test_strict_builder_excludes_old_and_post_cutoff_records(monkeypatch):
    base = {
        "family_id": 1, "canonical_name": "Tool", "canonical_name_zh": "工具",
        "product_type": "PHYSICAL_PRODUCT", "evidence_strength": "MODERATE",
        "evidence_reasons": ["fact"], "latest_observed_at": "2026-09-06T04:30:00+00:00",
        "source_records": [],
    }
    valid = {"product_id": 1, "source_platform": "amazon", "url": "https://example.test/1", "description": "A tool", **record("2026-09-06T11:59:59+08:00")}
    old = {"product_id": 2, "source_platform": "amazon", "url": "https://example.test/2", "description": "Old", **record("2026-09-04T18:00:00+08:00")}
    late = {"product_id": 3, "source_platform": "amazon", "url": "https://example.test/3", "description": "Late", **record("2026-09-06T12:00:00+08:00")}
    monkeypatch.setattr(db, "get_recent_daily_discovery", lambda _cutoff: [{**base, "source_records": [valid, old, late]}])
    monkeypatch.setattr(db, "get_latest_completed_run", lambda: {"run_id": "p"})
    result = build_strict_daily_discovery(business_date="2026-09-06")
    assert [r["product_id"] for r in result["items"][0]["source_records"]] == [1]
    assert result["items"][0]["source_records"][0]["raw_data"]["published_at"] == "2026-09-06T11:59:59+08:00"


def test_fallback_implementation_present_but_default_is_off():
    assert callable(build_rolling_daily_discovery)
    assert config.DAILY_EVIDENCE_FRESHNESS_DAYS == 7
    assert config.DAILY_FALLBACK_ENABLED is False


def test_collection_fetches_but_never_composes_or_notifies(monkeypatch):
    events = []
    monkeypatch.setattr(db, "init_db", lambda: True)
    monkeypatch.setattr(db, "start_pipeline_run", lambda: "collection-run")
    monkeypatch.setattr(db, "get_pipeline_source_failure_count", lambda _run_id: 0)
    monkeypatch.setattr(db, "finish_pipeline_run", lambda *args: events.append(("finish", args)))
    monkeypatch.setattr(run_collection, "run_pipeline", lambda **kwargs: events.append(("fetch", kwargs)) or True)
    monkeypatch.setattr(run_collection, "_persist_user_voice", lambda _run_id: (0, 0))
    assert run_collection.run_collection()
    assert [event[0] for event in events] == ["fetch", "finish"]
