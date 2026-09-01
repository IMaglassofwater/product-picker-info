"""Production-preview safety and artifact tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.phase11f_production_preview import write_preview_artifacts


def _dataset() -> dict:
    return {"run_id": "daily:test", "pipeline_run_id": "test", "item_count": 2, "items": [
        {"family_id": 1, "display_order": 1, "canonical_name": "Desk organizer", "canonical_name_zh": "桌面收纳盒", "factual_description": "A compact organizer.", "factual_description_zh": "一款紧凑的桌面收纳盒。", "product_type": "PHYSICAL_PRODUCT", "evidence_strength": "WEAK", "evidence_reasons": ["Source listing"], "actual_feedback": [], "source_records": [{"source_platform": "amazon", "url": "https://example.test/1"}]},
        {"family_id": 2, "display_order": 2, "canonical_name": "Map app", "canonical_name_zh": "地图应用", "factual_description": "A map application.", "factual_description_zh": "一款地图应用。", "product_type": "SOFTWARE_PRODUCT", "evidence_strength": "MODERATE", "evidence_reasons": ["HN comments"], "actual_feedback": [], "source_records": [{"source_platform": "hacker_news", "url": "https://example.test/2"}]},
    ]}


def test_preview_artifacts_have_complete_parity_and_do_not_send(tmp_path, monkeypatch):
    import wxpusher_notifier
    monkeypatch.setattr(wxpusher_notifier.WxPusherNotifier, "send", lambda *a, **k: (_ for _ in ()).throw(AssertionError("live send")))
    result = write_preview_artifacts(tmp_path, {"pipeline_run_id": "test"}, _dataset())
    assert result["parity"]["family_id_parity"] is True
    assert result["parity"]["wxpusher_count"] == 2
    assert result["ready"] is True
    assert {path.name for path in tmp_path.iterdir()} == {
        "daily_discovery_preview.json", "parity_report.json", "chinese_quality_report.json",
        "today_preview.html", "wxpusher_preview.html", "cutover_readiness.md",
    }


def test_chinese_failure_fallback_blocks_cutover_but_keeps_membership(tmp_path):
    data = _dataset()
    data["items"][1]["canonical_name_zh"] = data["items"][1]["canonical_name"]
    data["items"][1]["factual_description_zh"] = data["items"][1]["factual_description"]
    result = write_preview_artifacts(tmp_path, {}, data, {"ai_failures": 1, "api_calls": 1})
    assert result["ready"] is False
    assert result["chinese"]["english_name_fallbacks"] == 1
    assert result["parity"]["dataset_count"] == 2


def test_production_today_cutover_enabled_without_enabling_wxpusher():
    example = Path(".env.example").read_text(encoding="utf-8")
    assert "EVIDENCE_FIRST_TODAY_ENABLED=true" in example
    assert "EVIDENCE_FIRST_WXPUSHER_ENABLED=false" in example
    app = Path("app.py").read_text(encoding="utf-8")
    assert 'os.getenv("EVIDENCE_FIRST_TODAY_ENABLED", "true")' in app
    workflow = Path(".github/workflows/daily-product-picker.yml").read_text(encoding="utf-8")
    assert 'EVIDENCE_FIRST_WXPUSHER_ENABLED: "false"' in workflow
