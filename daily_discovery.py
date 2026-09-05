"""Authoritative Evidence-First Daily Discovery dataset and presentation models."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Iterable

import db
import config
from business_time import product_picker_business_date
from business_window import daily_window, effective_evidence_timestamp, record_in_window

EVIDENCE_ORDER = {"STRONG": 0, "MODERATE": 1, "WEAK": 2}
WXPUSHER_ITEMS_PER_CHUNK = 20
FEEDBACK_KEYS = ("review_texts", "comment_texts", "feedback_texts", "reviews", "comments")


def _timestamp(value: object) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _actual_feedback(source_records: list[dict]) -> list[dict]:
    """Extract only source-provided text and retain its provenance."""
    output: list[dict] = []
    for source in source_records:
        raw = source.get("raw_data") if isinstance(source.get("raw_data"), dict) else {}
        for key in FEEDBACK_KEYS:
            values = raw.get(key)
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            for value in values:
                text = value.get("text") if isinstance(value, dict) else value
                text = " ".join(str(text or "").split())
                if text:
                    output.append({
                        "text": text[:300], "source_platform": source.get("source_platform", ""),
                        "source_url": source.get("url", ""), "raw_field": key,
                    })
    return output


def _snapshot_item(item: dict) -> dict:
    records = [dict(value) for value in item.get("source_records", [])]
    feedback = _actual_feedback(records)
    english = str(item.get("canonical_name") or "Unnamed product")
    chinese = str(item.get("canonical_name_zh") or english)
    description = " ".join(str(item.get("factual_description") or "").split())[:300]
    return {
        **item,
        "canonical_name": english,
        "canonical_name_zh": chinese,
        "factual_description": description,
        "factual_description_zh": description,
        "source_records": records,
        "actual_feedback": feedback,
        "feedback_available": bool(feedback),
    }


def build_daily_discovery(
    pipeline_run_id: str, *, persist: bool = True, discovery_date: str | None = None,
    reuse_recent_persisted: bool = True,
) -> dict:
    """Build one complete run-scoped snapshot without AI or legacy ranking gates."""
    items = [_snapshot_item(value) for value in db.get_daily_discovery(pipeline_run_id)]
    reused_family_ids: list[int] = []
    if reuse_recent_persisted and len(items) < 20:
        previous = db.get_persisted_daily_discovery()
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=config.DAILY_EVIDENCE_FRESHNESS_DAYS
        )
        current_ids = {int(value["family_id"]) for value in items}
        for value in (previous or {}).get("items", []):
            family_id = int(value.get("family_id", 0) or 0)
            try:
                observed = datetime.fromisoformat(
                    str(value.get("latest_observed_at", "")).replace("Z", "+00:00")
                )
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if family_id and family_id not in current_ids and observed >= cutoff:
                items.append(deepcopy(value))
                current_ids.add(family_id)
                reused_family_ids.append(family_id)
    items.sort(key=lambda value: (
        EVIDENCE_ORDER.get(str(value.get("evidence_strength", "WEAK")).upper(), 3),
        -_timestamp(value.get("latest_observed_at")),
        str(value.get("canonical_name", "")).casefold(),
        int(value.get("family_id", 0)),
    ))
    for order, item in enumerate(items, 1):
        item["display_order"] = order
    result = {
        "pipeline_run_id": pipeline_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "discovery_date": discovery_date or product_picker_business_date().isoformat(),
        "items": items,
        "item_count": len(items),
    }
    if persist:
        result["run_id"] = db.persist_daily_discovery_snapshot(
            pipeline_run_id, items, discovery_date=result["discovery_date"],
            metadata={
                "membership": "observed+eligible+concrete+active-family with bounded recent persisted fallback",
                "ordering": "evidence,freshness,identity",
                "reused_recent_family_ids": reused_family_ids,
                "evidence_freshness_days": config.DAILY_EVIDENCE_FRESHNESS_DAYS,
            },
        )
    return result


def build_rolling_daily_discovery(
    *, days: int = 7, persist: bool = False, discovery_date: str | None = None,
) -> dict:
    """Compose from real persisted observations in a rolling time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    run_ids = db.get_recent_completed_run_ids(cutoff.isoformat())
    items = [_snapshot_item(item) for item in db.get_recent_daily_discovery(cutoff.isoformat())]
    items.sort(key=lambda value: (
        EVIDENCE_ORDER.get(str(value.get("evidence_strength", "WEAK")).upper(), 3),
        -_timestamp(value.get("latest_observed_at")),
        str(value.get("canonical_name", "")).casefold(), int(value["family_id"]),
    ))
    for order, item in enumerate(items, 1):
        item["display_order"] = order
    anchor = run_ids[0] if run_ids else ""
    result = {
        "pipeline_run_id": anchor, "run_id": f"daily:{anchor}" if anchor else "rolling:empty",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "discovery_date": discovery_date or product_picker_business_date().isoformat(),
        "items": items, "item_count": len(items), "window_days": max(1, days),
        "source_run_ids": run_ids,
    }
    if persist and anchor:
        result["run_id"] = db.persist_daily_discovery_snapshot(
            anchor, items, discovery_date=result["discovery_date"],
            metadata={"membership": "rolling persisted observations", "window_days": max(1, days), "source_run_ids": run_ids},
        )
    return result


def build_strict_daily_discovery(
    *, business_date: str | None = None, persist: bool = False,
) -> dict:
    """Build only from evidence in the fixed Shanghai noon-to-noon window."""
    start, end, selected_date = daily_window(business_date)
    # Query from window start onward so a source item published before noon but
    # persisted during the one-hour compose buffer remains eligible.
    raw_items = db.get_recent_daily_discovery(start.astimezone(timezone.utc).isoformat())
    items = []
    timestamp_limitations = 0
    for raw in raw_items:
        item = _snapshot_item(raw)
        records = []
        for record in item.get("source_records", []):
            timestamp, method = effective_evidence_timestamp(record)
            if timestamp is not None and start <= timestamp < end:
                value = dict(record)
                value["daily_evidence_timestamp"] = timestamp.isoformat()
                value["daily_timestamp_method"] = method
                records.append(value)
                timestamp_limitations += int(method == "observation")
        if not records:
            continue
        item["source_records"] = records
        item["source_platforms"] = sorted({r["source_platform"] for r in records})
        descriptions = [" ".join(str(r.get("description") or "").split()) for r in records if str(r.get("description") or "").strip()]
        item["factual_description"] = min(descriptions, key=len)[:300] if descriptions else ""
        item["factual_description_zh"] = item["factual_description_zh"] if item["factual_description"] else ""
        items.append(item)
    items.sort(key=lambda value: (
        EVIDENCE_ORDER.get(str(value.get("evidence_strength", "WEAK")).upper(), 3),
        -_timestamp(value.get("latest_observed_at")), str(value.get("canonical_name", "")).casefold(),
    ))
    for order, item in enumerate(items, 1):
        item["display_order"] = order
    latest = db.get_latest_completed_run() or {}
    anchor = str(latest.get("run_id") or "")
    result = {
        "pipeline_run_id": anchor, "run_id": f"daily:{anchor}" if anchor else "strict:empty",
        "generated_at": datetime.now(timezone.utc).isoformat(), "discovery_date": selected_date.isoformat(),
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "fallback_enabled": False, "timestamp_observation_fallback_count": timestamp_limitations,
        "source_failures": db.get_source_failures_between(
            start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat(),
        ),
        "items": items, "item_count": len(items),
    }
    if persist and anchor:
        result["run_id"] = db.persist_daily_discovery_snapshot(
            anchor, items, discovery_date=result["discovery_date"], metadata={
                "membership": "strict Shanghai noon-to-noon evidence window",
                "window_start": start.isoformat(), "window_end": end.isoformat(),
                "fallback_enabled": False,
                "timestamp_observation_fallback_count": timestamp_limitations,
            },
        )
    return result


def load_daily_discovery(**identity: str) -> dict | None:
    return db.get_persisted_daily_discovery(**identity)


def today_renderer_items(dataset: dict) -> list[dict]:
    """Return the authoritative ordered items; interactive filters operate on a copy."""
    return list(dataset.get("items", []))


def filter_today_items(
    items: Iterable[dict], *, product_type: str = "ALL", evidence: str = "ALL",
    source: str = "ALL", include_hidden: bool = False,
) -> list[dict]:
    feedback = db.get_family_feedback_map()
    output = []
    for item in items:
        state = feedback.get(int(item["family_id"]), {})
        if not include_hidden and state.get("feedback_type") in {"HIDDEN", "DISMISSED"}:
            continue
        if product_type != "ALL" and item.get("product_type") != product_type:
            continue
        if evidence != "ALL" and item.get("evidence_strength") != evidence:
            continue
        if source != "ALL" and source not in item.get("source_platforms", []):
            continue
        output.append(item)
    return output


def render_wxpusher_chunks(dataset: dict, *, items_per_chunk: int = WXPUSHER_ITEMS_PER_CHUNK) -> list[dict]:
    """Render every persisted family in order; this function never sends messages."""
    if items_per_chunk < 1:
        raise ValueError("items_per_chunk must be positive")
    items = list(dataset.get("items", []))
    total = max(1, (len(items) + items_per_chunk - 1) // items_per_chunk)
    chunks = []
    for index in range(total if items else 0):
        subset = items[index * items_per_chunk:(index + 1) * items_per_chunk]
        blocks = []
        for item in subset:
            signals = "; ".join(map(str, item.get("evidence_reasons", []))) or "暂无来源原生指标"
            feedback = "；".join(value["text"] for value in item.get("actual_feedback", [])[:2])
            feedback = feedback or "暂无用户文字反馈"
            links = " · ".join(
                f'<a href="{escape(str(value.get("url", "")), quote=True)}">{escape(str(value.get("source_platform", "source")))}</a>'
                for value in item.get("source_records", []) if value.get("url")
            )
            blocks.append(
                f"<p><b>{item['display_order']}. {escape(str(item['canonical_name_zh']))}</b><br>"
                f"<small>{escape(str(item['canonical_name']))}</small><br>"
                f"类型：{escape(str(item.get('product_type', 'unknown')))} · Evidence: {escape(str(item.get('evidence_strength', 'WEAK')))}<br>"
                f"{escape(str(item.get('factual_description_zh') or '暂无事实描述'))}<br>"
                f"市场信号：{escape(signals)}<br>用户反馈：{escape(feedback)}<br>来源：{links or '暂无链接'}</p>"
            )
        chunks.append({
            "title": f"今日发现 {index + 1}/{total}", "content": "\n".join(blocks),
            "family_ids": [value["family_id"] for value in subset], "items": subset,
        })
    return chunks


def wxpusher_family_ids(chunks: Iterable[dict]) -> list[int]:
    return [family_id for chunk in chunks for family_id in chunk.get("family_ids", [])]
