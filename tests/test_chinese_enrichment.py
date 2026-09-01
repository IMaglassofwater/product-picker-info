"""Phase 11F.2 factual Chinese enrichment tests (no network)."""

from __future__ import annotations

import json

import pytest

import db
from ai_providers import AIProviderError, GeminiProvider
from chinese_enrichment import (
    TranslationBatch, TranslationItem, apply_cached, apply_deterministic_fallback,
    connectivity_probe, deterministic_description, deterministic_name,
    enrich_items, identity_fingerprint, validate_translation,
)


class FakeProvider:
    model_name = "fake"

    def __init__(self, responses):
        self.responses = iter(responses)

    def analyze(self, *_args, **_kwargs):
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def item(family_id=1, name="Manual Can Opener"):
    return {
        "family_id": family_id, "canonical_name": name, "canonical_name_zh": name,
        "factual_description": "A handheld tool used to open cans.",
        "factual_description_zh": "A handheld tool used to open cans.",
        "product_type": "PHYSICAL_PRODUCT", "evidence_reasons": ["Source listing"],
        "source_records": [{"source_title": name}], "source_platforms": ["amazon"],
        "display_order": family_id,
    }


def test_missing_gemini_key_is_rejected():
    with pytest.raises(AIProviderError):
        GeminiProvider("", "gemini-3.5-flash-lite")


def test_connectivity_probe_failure_is_explicit():
    result = connectivity_probe(FakeProvider([TimeoutError("read timed out")]))
    assert result.success is False
    assert result.error_type == "TimeoutError"


def test_structured_response_and_invalid_output_validation():
    parsed = TranslationBatch.model_validate_json(
        '{"items":[{"family_id":1,"name_zh":"手动开罐器","description_zh":"一款用于打开金属罐头的手持工具。"}]}'
    )
    assert validate_translation(parsed.items[0], {1}) is None
    assert validate_translation(TranslationItem(family_id=1, name_zh="Manual Can Opener", description_zh="English echo"), {1}) == "ENGLISH_ECHO"
    assert validate_translation(TranslationItem(family_id=1, name_zh="开罐器", description_zh="这是一款具有巨大商机的产品。"), {1}) == "OPPORTUNITY_LANGUAGE"


def test_batch_partial_failure_preserves_membership(monkeypatch):
    items = [item(1), item(2, "Map App")]
    dataset = {"run_id": "daily:test", "items": items}
    response = json.dumps({"items": [{"family_id": 1, "name_zh": "手动开罐器", "description_zh": "一款用于打开罐头的手持工具。"}]}, ensure_ascii=False)
    monkeypatch.setattr(db, "save_family_enrichment", lambda *a, **k: True)
    monkeypatch.setattr(db, "update_daily_discovery_item_language", lambda *a, **k: True)
    stats = enrich_items(FakeProvider([response]), dataset, items, batch_size=5)
    assert stats["succeeded"] == 1 and stats["failed"] == 1
    assert [value["family_id"] for value in dataset["items"]] == [1, 2]
    assert dataset["items"][1]["canonical_name_zh"] == "Map App"


def test_cache_reuse_and_fingerprint_invalidation(monkeypatch):
    value = item()
    dataset = {"run_id": "daily:test", "items": [value]}
    fingerprint = identity_fingerprint(value)
    monkeypatch.setattr(db, "get_family_enrichment", lambda family_id, supplied, version=None: {
        "canonical_name_zh": "手动开罐器", "factual_description_zh": "一款用于打开罐头的工具。"
    } if supplied == fingerprint else None)
    monkeypatch.setattr(db, "update_daily_discovery_item_language", lambda *a, **k: True)
    assert apply_cached(dataset) == 1
    changed = {**value, "factual_description": "Materially changed identity"}
    assert identity_fingerprint(changed) != fingerprint


def test_failed_batch_does_not_change_items(monkeypatch):
    values = [item(1), item(2)]
    original = [dict(value) for value in values]
    stats = enrich_items(FakeProvider([TimeoutError("timeout")]), {"run_id": "daily:test", "items": values}, values)
    assert stats["failed"] == 2
    assert values == original


@pytest.mark.parametrize(("english", "expected"), (
    ("Frost Insulated Tumbler", "Frost 保温杯"),
    ("STANLEY Insulated Tumbler", "STANLEY 保温杯"),
    ("OLIXIS Metal Platform Bed Frame", "OLIXIS 金属平台床架"),
    ("Portable USB Desk Fan", "便携 USB 桌面风扇"),
))
def test_deterministic_product_terms_preserve_brands(english, expected):
    value = item(name=english)
    translated, _ = deterministic_name(value)
    assert translated == expected


def test_software_suffix_and_safe_unknown_fallback():
    software = {**item(name="Acme Task Manager"), "product_type": "SOFTWARE_PRODUCT"}
    assert deterministic_name(software)[0] == "Acme Task 管理工具"
    unknown = item(name="ZXQ-47 Unclassified Object")
    assert deterministic_name(unknown) == ("ZXQ-47 Unclassified Object", False)


def test_deterministic_description_is_factual_and_non_promotional():
    value = item(name="Frost Insulated Tumbler")
    name, _ = deterministic_name(value)
    description, success = deterministic_description(value, name)
    assert success and description == "该产品为Frost 保温杯。"
    assert all(term not in description for term in ("商机", "市场潜力", "利润", "推荐"))


def test_brand_and_model_are_preserved_in_long_titles():
    toothbrush = {**item(name="The most BIFL premium toothbrush: Oral-B iO Series"), "product_type": "SOFTWARE_PRODUCT"}
    keyboard = item(name="MCHOSE x Unbox Therapy - UT98 Mechanical Keyboard")
    assert deterministic_name(toothbrush)[0] == "Oral-B iO 系列牙刷"
    assert deterministic_name(keyboard)[0] == "MCHOSE UT98 键盘"


def test_deterministic_timeout_fallback_never_changes_membership(monkeypatch):
    values = [item(1, "Frost Insulated Tumbler"), item(2, "Unknown Gizmo")]
    dataset = {"run_id": "daily:test", "items": values}
    monkeypatch.setattr(db, "get_family_enrichment", lambda *a: None)
    monkeypatch.setattr(db, "save_family_enrichment", lambda *a, **k: True)
    monkeypatch.setattr(db, "update_daily_discovery_item_language", lambda *a, **k: True)
    stats = apply_deterministic_fallback(dataset)
    assert [value["family_id"] for value in values] == [1, 2]
    assert stats["deterministic_names"] == 1 and stats["english_only"] == 1
