import sqlite3

import db
from ai_filter import SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA
from ai_providers import GeminiTriageResponse
from bilingual_backfill import (
    BilingualEnrichment,
    BilingualEnrichmentResponse,
    build_enrichment_input,
    merge_bilingual_enrichment,
    parse_enrichment,
    save_bilingual_enrichment,
    select_bilingual_backfill,
)
from bilingual_display import preferred_title
from models import AITriageResult


def result(**overrides):
    values = dict(
        candidate_id="c1", triage_status="PASS", triage_score=8,
        confidence="HIGH", primary_reason="Evidence-backed reason.",
        opportunity_type="unmet_demand", key_opportunity="Worth testing.",
        main_risks=["Demand requires validation"], needs_deep_analysis=True,
        provider="gemini", model="gemini-3.5-flash-lite",
    )
    values.update(overrides)
    return AITriageResult(**values)


def test_shared_schema_and_gemini_model_contain_bilingual_fields():
    fields = {"display_title_zh", "primary_reason_zh", "key_opportunity_zh", "main_risks_zh"}
    assert fields <= set(TRIAGE_JSON_SCHEMA["properties"])
    assert fields <= set(TRIAGE_JSON_SCHEMA["required"])
    assert fields <= set(GeminiTriageResponse.model_fields)


def test_prompt_requires_bilingual_grounding_without_new_facts():
    lowered = SYSTEM_PROMPT.casefold()
    assert "simplified chinese" in lowered
    assert "chinese fields must not add facts" in lowered
    assert "supplier" in lowered and "moq" in lowered and "competition" in lowered


def test_old_result_without_chinese_remains_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "legacy.db")
    assert db.init_db()
    assert db.save_triage_result(result())
    loaded = db.get_triage_result("c1", "gemini", "gemini-3.5-flash-lite")
    assert loaded is not None
    assert loaded.triage_status == "PASS"
    assert loaded.primary_reason_zh is None
    assert loaded.main_risks_zh == []


def test_new_bilingual_fields_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bilingual.db")
    assert db.init_db()
    bilingual = result(
        display_title_zh="快速取物腰包", primary_reason_zh="用户需要快速取物。",
        key_opportunity_zh="可验证无拉链结构。", main_risks_zh=["需求仍需验证"],
    )
    assert db.save_triage_result(bilingual)
    assert db.get_triage_result("c1", "gemini", "gemini-3.5-flash-lite") == bilingual


def test_display_title_prefers_ai_chinese_then_mapping_then_english():
    assert preferred_title("Fanny pack without zipper", "AI中文标题") == "AI中文标题"
    assert preferred_title("Fanny pack without zipper", None) == "无拉链快速取物腰包"
    assert preferred_title("Unmapped original", None) == "Unmapped original"


def test_backfill_merge_cannot_change_original_judgment():
    original = result()
    merged = merge_bilingual_enrichment(original, BilingualEnrichment(
        "中文标题", "中文理由", "中文机会", ["中文风险"],
    ))
    assert merged.triage_status == original.triage_status
    assert merged.triage_score == original.triage_score
    assert merged.primary_reason == original.primary_reason
    assert merged.primary_reason_zh == "中文理由"


def test_enrichment_schema_and_input_are_translation_only():
    original = result()
    payload = build_enrichment_input("Original title", original)
    assert set(payload) == {"original_title", "primary_reason", "key_opportunity", "main_risks"}
    assert set(BilingualEnrichmentResponse.model_fields) == {
        "display_title_zh", "primary_reason_zh", "key_opportunity_zh", "main_risks_zh"
    }
    parsed = parse_enrichment('{"display_title_zh":"中文标题","primary_reason_zh":"中文理由","key_opportunity_zh":"中文机会","main_risks_zh":["中文风险"]}')
    assert parsed.display_title_zh == "中文标题"


def test_enrichment_updates_only_chinese_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "enrichment.db")
    assert db.init_db()
    original = result()
    assert db.save_triage_result(original)
    assert save_bilingual_enrichment(original, BilingualEnrichment(
        "中文标题", "中文理由", "中文机会", ["中文风险"],
    ))
    loaded = db.get_triage_result("c1", "gemini", "gemini-3.5-flash-lite")
    assert loaded is not None
    assert loaded.triage_status == original.triage_status
    assert loaded.triage_score == original.triage_score
    assert loaded.confidence == original.confidence
    assert loaded.opportunity_type == original.opportunity_type
    assert loaded.primary_reason == original.primary_reason
    assert loaded.key_opportunity == original.key_opportunity
    assert loaded.main_risks == original.main_risks
    assert loaded.primary_reason_zh == "中文理由"


def test_runtime_backfill_selects_only_existing_gemini_missing_chinese():
    selected = select_bilingual_backfill()
    with sqlite3.connect(db.DB_PATH) as connection:
        expected = connection.execute(
            """SELECT COUNT(*) FROM ai_triage_results
               WHERE provider='gemini' AND model='gemini-3.5-flash-lite'
                 AND (primary_reason_zh IS NULL OR primary_reason_zh=''
                      OR key_opportunity_zh IS NULL OR key_opportunity_zh=''
                      OR main_risks_zh IS NULL OR main_risks_zh='[]')"""
        ).fetchone()[0]
        products = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert len(selected) == expected == 24
    assert len(selected) < products
